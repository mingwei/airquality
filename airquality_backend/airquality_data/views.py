
import boto3,os,requests,logging,io,base64,tempfile,zipfile
from http import HTTPStatus
from dashscope import ImageSynthesis
import requests
from urllib.parse import urlparse, unquote
from pathlib import PurePosixPath
from tempfile import TemporaryDirectory
import pandas as pd
from io import StringIO, BytesIO
from fuzzywuzzy import process
from botocore.config import Config
from botocore import UNSIGNED
from minio import Minio
from autogluon.tabular import TabularPredictor
from .utils import calculate_aqi,get_aqi_category,get_aqi_prompt
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from datetime import datetime, timedelta
from django.conf import settings
from .models import GSODStation, NOAAData, OpenAQData, MergedData, TrainedModel, GeneratedImage
from .serializers import (FetchNOAADataSerializer, FetchOpenAQDataSerializer, PrepareTrainingDataSerializer,
                          TrainModelSerializer, ForecastAQISerializer, GenerateCityImageSerializer,
                          NOAADataSerializer, OpenAQDataSerializer, MergedDataSerializer,
                          TrainedModelSerializer)
from openai import OpenAI
# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# MinIO client configuration
minio_client = Minio(
    settings.MINIO_ENDPOINT,
    access_key=settings.MINIO_ACCESS_KEY,
    secret_key=settings.MINIO_SECRET_KEY,
    secure=settings.MINIO_USE_SSL
)

# AWS S3 client for public datasets
s3_client = boto3.client('s3', config=Config(signature_version=UNSIGNED))


# MinIO buckets

STATION_BUCKET = 'station-data'
NOAA_BUCKET = 'noaa-data'
OPENAQ_BUCKET = 'openaq-data'
MERGED_BUCKET = 'merged-data'
MODEL_BUCKET = 'models'
IMAGE_BUCKET = 'generated-images'

class PrepareTrainingDataView(APIView):
    def post(self, request):
        serializer = PrepareTrainingDataSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        noaa_filename = serializer.validated_data['noaa_filename']
        openaq_filename = serializer.validated_data['openaq_filename']
        pollutant = serializer.validated_data['pollutant']  # e.g., 'pm25', 'no2'

        try:
            # Load data from MinIO
            noaa_response = minio_client.get_object(NOAA_BUCKET, noaa_filename)
            noaa_df = pd.read_csv(noaa_response)

            openaq_response = minio_client.get_object(OPENAQ_BUCKET, openaq_filename)
            aq_df = pd.read_csv(openaq_response)

            # Step 1: Preprocess OpenAQ data - Parse datetime with timezone and select 12:00 AM
            # Parse the datetime column with timezone awareness
            aq_df['datetime'] = pd.to_datetime(aq_df['datetime'], utc=True)

            # Convert to local time based on the offset (e.g., -08:00)
            aq_df['local_datetime'] = aq_df['datetime'].dt.tz_convert('America/Los_Angeles')

            # Extract the date and hour in local time
            aq_df['date'] = aq_df['local_datetime'].dt.date
            aq_df['hour'] = aq_df['local_datetime'].dt.hour

            # Filter for 12:00 AM (midnight) rows in local time
            aq_df_midnight = aq_df[aq_df['hour'] == 0].copy()

            # Transform date format to YYYY/MM/DD
            aq_df_midnight['datetime'] = aq_df_midnight['date'].apply(
                lambda x: x.strftime('%Y/%m/%d')
            )

            # Step 2: Prepare NOAA data - Ensure date is in YYYY/MM/DD format
            noaa_df['DATE'] = pd.to_datetime(noaa_df['DATE']).dt.strftime('%Y/%m/%d')

            # Step 3: Merge datasets on date
            merged_df = pd.merge(
                noaa_df,
                aq_df_midnight,
                how='inner',
                left_on='DATE',
                right_on='datetime',
                suffixes=('_noaa', '_aq')
            )
            print(merged_df[:5])

            # Step 4: Calculate AQI for the selected pollutant
            pollutant_column = f'{pollutant}_value'
            if pollutant_column not in aq_df.columns:
                return Response(
                    {'error': f'Pollutant {pollutant} not found in OpenAQ data'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            merged_df['AQI'] = merged_df[pollutant_column].apply(
                lambda x: calculate_aqi(pollutant, x)
            )

            # Step 5: Drop unnecessary columns
            drop_columns = [
            'LATITUDE', 'LONGITUDE', 'lat', 'lon',
                'location_id', f'{pollutant}_units', 'hour', 'date', 'local_datetime'
            ]
            merged_df = merged_df.drop(columns=[col for col in drop_columns if col in merged_df.columns])

            # Step 6: Split data: Jan-Oct (training), Nov-Dec (validation/test)
            # Since DATE_noaa is dropped, we need to preserve the date for splitting
            # Let's keep a copy of the date before dropping
            merged_df['merge_date'] = merged_df['DATE']  # Save the date before dropping
            merged_df['MONTH'] = pd.to_datetime(merged_df['merge_date']).dt.month
            train_df = merged_df[merged_df['MONTH'].isin(range(1, 11))]
            validate_df = merged_df[merged_df['MONTH'].isin([11, 12])]
            test_df = validate_df.drop(columns=['AQI'])  # Remove true labels for testing

            # Drop the temporary merge_date column
            merged_df = merged_df.drop(columns=['merge_date'])
            train_df = train_df.drop(columns=['merge_date'])
            validate_df = validate_df.drop(columns=['merge_date'])
            test_df = test_df.drop(columns=['merge_date'])

            # Step 7: Save to MinIO
            train_filename = f'train_{pollutant}_{noaa_filename.split(".")[0]}.csv'
            validate_filename = f'validate_{pollutant}_{noaa_filename.split(".")[0]}.csv'
            test_filename = f'test_{pollutant}_{noaa_filename.split(".")[0]}.csv'

            for df, filename in [
                (train_df, train_filename),
                (validate_df, validate_filename),
                (test_df, test_filename)
            ]:
                buffer = StringIO()
                df.to_csv(buffer, index=False)
                minio_client.put_object(
                    MERGED_BUCKET,
                    filename,
                    BytesIO(buffer.getvalue().encode('utf-8')),
                    length=len(buffer.getvalue())
                )
            print(f'Finished processing {pollutant} for {noaa_filename}')
            # Step 8: Save metadata to database
            noaa_dataset = NOAAData.objects.get(filename=noaa_filename, bucket=NOAA_BUCKET)
            #openaq_dataset = OpenAQData.objects.get(filename=openaq_filename, bucket=OPENAQ_BUCKET)
            merged_dataset = MergedData.objects.create(
                train_filename=train_filename,
                #validate_filename=validate_filename,
                test_filename=test_filename,
                bucket=MERGED_BUCKET,
                #noaa_dataset=noaa_dataset,
                #openaq_dataset=openaq_dataset,
                #pollutant=pollutant,
                train_record_count=len(train_df),

                test_record_count=len(test_df)
            )
 


            print(f'Finished saving metadata for step 9')
            return Response(MergedDataSerializer(merged_dataset).data, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error in PrepareTrainingDataView: {str(e)}")
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
class TrainModelView(APIView):
    def post(self, request):
        serializer = TrainModelSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        train_filename = serializer.validated_data['train_filename']
        merged_data_id = serializer.validated_data['merged_data_id']
        model_name = serializer.validated_data.get('model_name', 'aqi_predictor')
        time_limit = serializer.validated_data.get('time_limit', 3600)
        models_to_train = serializer.validated_data.get('models_to_train', ['RF', 'XT', 'XGB', 'GBM'])  # Default models

        try:
            # Validate merged dataset
            merged_dataset = MergedData.objects.get(id=merged_data_id)
            if merged_dataset.train_filename != train_filename:
                return Response(
                    {'error': 'Train filename does not match merged dataset'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Load training data
            response = minio_client.get_object('merged-data', train_filename)
            train_df = pd.read_csv(response)

            # Verify columns
            required_columns = ['DEWP', 'WDSP', 'MAX', 'MIN', 'PRCP', 'MONTH', 'pm25_value', 'AQI']
            missing_cols = [col for col in required_columns if col not in train_df.columns]
            if missing_cols:
                return Response(
                    {'error': f'Missing columns in training data: {missing_cols}'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Features and target
            features = ['DEWP', 'WDSP', 'MAX', 'MIN', 'PRCP', 'MONTH', 'pm25_value']
            target = 'AQI'

            # Define hyperparameters for selected models
            valid_models = {
                'RF': 'RandomForestMSE',  # RandomForest
                'XT': 'ExtraTreesMSE',    # ExtraTrees
                'XGB': 'XGBoost',         # XGBoost
                'GBM': 'LightGBM',        # LightGBM
                'CAT': 'CatBoost',        # CatBoost
                'NN_TORCH': 'NeuralNetTorch',  # NeuralNetTorch
                'FASTAI': 'NeuralNetFastAI'    # NeuralNetFastAI
            }
            hyperparameters = {model: {} for model in valid_models if model in models_to_train}
            if not hyperparameters:
                return Response(
                    {'error': f'Invalid models_to_train: {models_to_train}. Choose from {list(valid_models.keys())}'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Log selected models
            logger.info(f"Training models: {list(hyperparameters.keys())}")

            # Train with AutoGluon in a temporary directory
            with TemporaryDirectory() as temp_dir:
                predictor = TabularPredictor(
                    label=target,
                    path=temp_dir,
                    problem_type='regression',
                    eval_metric='rmse',
                    verbosity=2
                )
                try:
                    predictor.fit(
                        train_data=train_df[features + [target]],
                        time_limit=time_limit,
                        hyperparameters=hyperparameters,
                        num_bag_folds=5,  # Moderate bagging for robustness
                        num_stack_levels=0,  # Disable stacking to reduce models
                        excluded_model_types=['CAT', 'FASTAI']  # Exclude problematic models
                    )
                except ImportError as e:
                    logger.error(f"Dependency error during training: {str(e)}")
                    return Response(
                        {'error': f'Missing dependency: {str(e)}. Install required packages.'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR
                    )

                # Get leaderboard
                leaderboard = predictor.leaderboard(silent=True).to_dict()
                logger.info(f"Leaderboard: {leaderboard}")

                # Create ZIP file of model directory
                zip_path = f"/tmp/{model_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
                with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    for root, _, files in os.walk(temp_dir):
                        for file in files:
                            file_path = os.path.join(root, file)
                            arcname = os.path.relpath(file_path, temp_dir)
                            zipf.write(file_path, arcname)

                # Log ZIP file size
                zip_size = os.path.getsize(zip_path)
                logger.info(f"Model ZIP file size: {zip_size} bytes")

                # Upload ZIP to MinIO
                model_path = f'models/{model_name}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.zip'
                with open(zip_path, 'rb') as file_data:
                    file_stat = os.stat(zip_path)
                    minio_client.put_object(
                        'models',
                        model_path,
                        file_data,
                        length=file_stat.st_size
                    )

                # Clean up
                os.remove(zip_path)

                # Save metadata
                trained_model = TrainedModel.objects.create(
                    model_name=model_name,
                    model_path=model_path,
                    bucket='models',
                    merged_dataset=merged_dataset,
                    leaderboard=leaderboard
                )

                logger.info(f"Model {model_name} trained and saved to MinIO at {model_path}")
                return Response(
                    {
                        'model_id': trained_model.id,
                        'model_name': model_name,
                        'model_path': model_path,
                        'leaderboard': leaderboard,
                        'zip_size_bytes': zip_size
                    },
                    status=status.HTTP_200_OK
                )

        except Exception as e:
            logger.error(f"Error in TrainModelView: {str(e)}")
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class ForecastAQIView(APIView):
    def post(self, request):
        serializer = ForecastAQISerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        model_id = serializer.validated_data['model_id']
        city_name = serializer.validated_data['city_name']
        forecast_data = serializer.validated_data['forecast_data']

        try:
            # Load model metadata
            trained_model = TrainedModel.objects.get(id=model_id)
            model_path = trained_model.model_path

            # Download and extract model ZIP
            with TemporaryDirectory() as temp_dir:
                zip_response = minio_client.get_object('models', model_path)
                zip_path = os.path.join(temp_dir, 'model.zip')
                with open(zip_path, 'wb') as f:
                    f.write(zip_response.read())

                # Extract ZIP
                with zipfile.ZipFile(zip_path, 'r') as zipf:
                    zipf.extractall(temp_dir)

                # Load predictor
                predictor = TabularPredictor.load(temp_dir)

                # Create DataFrame from forecast data
                features = ['DEWP', 'WDSP', 'MAX', 'MIN', 'PRCP', 'MONTH', 'pm25_value']
                test_df = pd.DataFrame([forecast_data], columns=features)

                # Verify features
                missing_features = [f for f in features if f not in test_df.columns]
                if missing_features:
                    return Response(
                        {'error': f'Missing features in forecast data: {missing_features}'},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                # Predict
                prediction = predictor.predict(test_df)[0]

                # Calculate AQI
                pm25_value = test_df['pm25_value'][0]
                calculated_aqi = calculate_aqi('pm25', pm25_value)

                # Get AQI category for predicted AQI
                predicted_category = get_aqi_category(prediction)

                # Format forecast
                tomorrow = datetime.now() + timedelta(days=1)
                forecast = {
                    'date': tomorrow.strftime('%Y/%m/%d'),
                    'city_name': city_name,
                    'pm25_value': float(pm25_value),
                    'predicted_aqi': float(prediction),
                    'calculated_aqi': float(calculated_aqi),
                    'descriptor': predicted_category['descriptor'],
                    'color': predicted_category['color']
                }

                logger.info(f"24-hour AQI forecast generated for {city_name}: {forecast}")
                return Response(
                    {
                        'city_name': city_name,
                        'forecast': forecast
                    },
                    status=status.HTTP_200_OK
                )

        except Exception as e:
            logger.error(f"Error in ForecastAQIView: {str(e)}")
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        

class ForecastAQIWithImageView(APIView):
    def post(self, request):
        serializer = ForecastAQISerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        model_id = serializer.validated_data['model_id']
        city_name = serializer.validated_data['city_name']
        forecast_data = serializer.validated_data['forecast_data']

        try:
            trained_model = TrainedModel.objects.get(id=model_id)
            model_path = trained_model.model_path

            with TemporaryDirectory() as temp_dir:
                zip_response = minio_client.get_object('models', model_path)
                zip_path = os.path.join(temp_dir, 'model.zip')
                with open(zip_path, 'wb') as f:
                    f.write(zip_response.read())

                with zipfile.ZipFile(zip_path, 'r') as zipf:
                    zipf.extractall(temp_dir)

                predictor = TabularPredictor.load(temp_dir)

                features = ['DEWP', 'WDSP', 'MAX', 'MIN', 'PRCP', 'MONTH', 'pm25_value']
                test_df = pd.DataFrame([forecast_data], columns=features)

                missing_features = [f for f in features if f not in test_df.columns]
                if missing_features:
                    return Response(
                        {'error': f'Missing features in forecast data: {missing_features}'},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                prediction = predictor.predict(test_df)[0]

                pm25_value = test_df['pm25_value'][0]
                calculated_aqi = calculate_aqi('pm25', pm25_value)

                predicted_category = get_aqi_category(prediction)

                tomorrow = datetime.now() + timedelta(days=1)
                forecast = {
                    'date': tomorrow.strftime('%Y/%m/%d'),
                    'city_name': city_name,
                    'pm25_value': float(pm25_value),
                    'predicted_aqi': float(prediction),
                    'calculated_aqi': float(calculated_aqi),
                    'descriptor': predicted_category['descriptor'],
                    'color': predicted_category['color']
                }

                # Generate image using Ali GenAI
                prompt = get_aqi_prompt(predicted_category['descriptor'])
                image_response = ImageSynthesis.call(
                    api_key="sk-1631d84fcc1e415e8d55dbc99edfae47",
                    model=ImageSynthesis.Models.wanx_v1,
                    prompt=prompt,
                    n=1,
                    style='<watercolor>',
                    size='1024*1024'
                )
                print(f"*** response: {image_response}")
                image_url = None
                local_image_url = None
                if image_response.status_code == HTTPStatus.OK and image_response.output.task_status == 'SUCCEEDED':
                    for result in image_response.output.results:
                        image_url = result.url
                        # Download and store the image locally
                        try:
                            # Extract filename from the URL as per the official sample
                            file_name = PurePosixPath(unquote(urlparse(image_url).path)).parts[-1]
                            local_path = os.path.join(settings.MEDIA_ROOT, 'air_quality_images', file_name)
                            
                            # Ensure the directory exists
                            os.makedirs(os.path.dirname(local_path), exist_ok=True)
                            
                            # Download and save the image
                            image_download_response = requests.get(image_url)
                       
                            with open(local_path, 'wb') as f:
                                f.write(image_download_response.content)
                            
                            # Generate the local URL
                            local_image_url = f"{settings.MEDIA_URL}air_quality_images/{file_name}"
                           
                        except Exception as e:
                            logger.error(f"Error downloading image from {image_url}: {str(e)}")
                else:
                    logger.error(
                        f"Image generation failed: status_code={image_response.status_code}, "
                        f"code={image_response.code}, message={image_response.message}"
                    )


                logger.info(f"24-hour AQI forecast with image data generated for {city_name}: {forecast}")
                return Response(
                    {
                        'city_name': city_name,
                        'forecast': forecast,
                        'image_url': local_image_url
                    },
                    status=status.HTTP_200_OK
                )

        except Exception as e:
            logger.error(f"Error in ForecastAQIWithImageView: {str(e)}")
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)