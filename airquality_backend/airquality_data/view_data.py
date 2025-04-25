import pandas as pd
from io import StringIO, BytesIO
from botocore.config import Config
from botocore import UNSIGNED
from minio import Minio
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
import boto3,os,logging,requests,gzip
import numpy as np
from datetime import datetime
from django.conf import settings
from .models import GSODStation, NOAAData, OpenAQData, MergedData, TrainedModel
from .serializers import (NOAADataSerializer, OpenAQDataSerializer, PrepareTrainingDataSerializer,
                          TrainModelSerializer, ForecastAQISerializer, MergedDataSerializer,
                          TrainedModelSerializer)
from .mockdata import CITIES


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
NOAA_BUCKET = 'noaa-data'
OPENAQ_BUCKET = 'openaq-data'
MERGED_BUCKET = 'merged-data'
MODEL_BUCKET = 'models'
for bucket in [NOAA_BUCKET, OPENAQ_BUCKET, MERGED_BUCKET, MODEL_BUCKET]:
    if not minio_client.bucket_exists(bucket):
        minio_client.make_bucket(bucket)
# Local data directory
DATA_DIR = "aq_data"
YEAR = 2023
AQ_S3_BUCKET = "openaq-data-archive"

class FetchNOAADataView(APIView):
    def get(self, request):
        """Fetch NOAA data for all cities for 2022 and save to MinIO."""
        results = []
        year_start = 2023
        year_end = 2023

        for city_name, city_data in CITIES.items():
            city_name_lower = city_name.lower()

            try:
                # Get or create station in the database
                station, created = GSODStation.objects.get_or_create(
                    station_id=city_data['station_id'],
                    defaults={
                        'usaf': city_data['usaf'],
                        'wban': city_data['wban'],
                        'station_name': city_data['station_name'],
                        'country': city_data['country'],
                        'state': city_data['state'],
                        'icao': city_data['icao'],
                        'latitude': city_data['latitude'],
                        'longitude': city_data['longitude'],
                        'elevation_m': city_data['elevation_m'],
                        'begin_date': city_data['begin_date'],
                        'end_date': city_data['end_date']
                    }
                )

                # Fetch NOAA data
                noaa_df = pd.DataFrame()
                bucket_name = 'noaa-gsod-pds'
                station_id = city_data['station_id']
                for year in range(year_start, year_end + 1):
                    key = f'{year}/{station_id}.csv'
                    logger.info(f'Fetching NOAA data from S3: {key}')
                    try:
                        obj = s3_client.get_object(Bucket=bucket_name, Key=key)
                        csv_string = obj['Body'].read().decode('utf-8')
                        year_df = pd.read_csv(StringIO(csv_string))
                        noaa_df = pd.concat([noaa_df, year_df], ignore_index=True)
                    except Exception as e:
                        logger.warning(f"Failed to fetch NOAA data for year {year} for {city_name}: {str(e)}")
                        continue

                if noaa_df.empty:
                    results.append({
                        "status": "error",
                        "message": f"No NOAA data retrieved for {city_name}",
                        "city": city_name
                    })
                    continue

                # Feature engineering for NOAA data
                noaa_df['MONTH'] = pd.to_datetime(noaa_df['DATE']).dt.month
                columns = ['DATE', 'LATITUDE', 'LONGITUDE', 'DEWP', 'WDSP', 'MAX', 'MIN', 'PRCP', 'MONTH']
                noaa_df = noaa_df[columns]

                # Save NOAA data to MinIO
                noaa_filename = f'noaa_{station_id}_{city_name_lower}_{year_start}-{year_end}.csv'
                csv_buffer = StringIO()
                noaa_df.to_csv(csv_buffer, index=False)
                minio_client.put_object(
                    NOAA_BUCKET,
                    noaa_filename,
                    BytesIO(csv_buffer.getvalue().encode("utf-8")),
                    length=len(csv_buffer.getvalue()),
                    content_type='text/csv'
                )

                # Save NOAA data to database
                noaa_dataset = NOAAData.objects.create(
                    filename=noaa_filename,
                    bucket=NOAA_BUCKET,
                    city_name=city_name_lower,
                    station=station,
                    year_start=year_start,
                    year_end=year_end,
                    record_count=len(noaa_df)
                )

                # Prepare result for this city
                results.append({
                    "status": "success",
                    "message": f"Successfully processed and uploaded NOAA data for {city_name}",
                    "city": city_name,
                    "minio_file": noaa_filename,
                    "noaa_data": NOAADataSerializer(noaa_dataset).data
                })

            except Exception as e:
                logger.error(f"Error processing {city_name}: {str(e)}")
                results.append({
                    "status": "error",
                    "message": f"Error processing {city_name}: {str(e)}",
                    "city": city_name
                })

        # Prepare response
        response_data = {
            "results": results,
            "total_processed": len(results),
            "successful": len([r for r in results if r["status"] == "success"]),
            "failed": len([r for r in results if r["status"] == "error"])
        }

        return Response(response_data, status=status.HTTP_200_OK)
        

class AQDataProcessView(APIView):
    def get(self, request):
        """Process AQ data for all cities for 2022 and save to MinIO."""
        # Create data directory
        os.makedirs(DATA_DIR, exist_ok=True)

        results = []

        # Process each city
        for city_key, city_info in CITIES.items():
            city_name = city_info["station_name"]
            location_id = city_info["aq_location_id"]
            logger.info(f"Processing city: {city_name} (ID: {location_id})")
            result = download_and_process_city(location_id, city_name)
            results.append(result)

        # Prepare response
        response_data = {
            "results": results,
            "total_processed": len(results),
            "successful": len([r for r in results if r["status"] == "success"]),
            "failed": len([r for r in results if r["status"] == "error"])
        }

        return Response(response_data, status=status.HTTP_200_OK)
    


def download_and_process_city(location_id: str, city_name: str) -> dict:
    """Download, process, merge sensors data, and upload to MinIO for a single city."""
    # Create directory for city data
    city_dir = os.path.join(DATA_DIR, f"{location_id}_{YEAR}")
    os.makedirs(city_dir, exist_ok=True)

    # S3 prefix for the city's data
    prefix = f"records/csv.gz/locationid={location_id}/year={YEAR}/"

    # Initialize DataFrame
    aq_df = pd.DataFrame()

    try:
        # List objects in S3 prefix
        logger.info(f"Fetching S3 objects for {city_name}: s3://{AQ_S3_BUCKET}/{prefix}")
        response = s3_client.list_objects_v2(Bucket=AQ_S3_BUCKET, Prefix=prefix)
        
        if 'Contents' not in response:
            logger.warning(f"No data found for location {location_id} in year {YEAR}")
            return {
                "status": "error",
                "message": f"No data found for location {location_id} in year {YEAR}",
                "city": city_name
            }

        # Download and process each .csv.gz file
        for obj in response['Contents']:
            key = obj['Key']
            if key.endswith('.csv.gz'):
                local_file = os.path.join(city_dir, os.path.basename(key))
                
                # Download file
                logger.info(f"Downloading S3 object: {key}")
                s3_client.download_file(AQ_S3_BUCKET, key, local_file)

                # Decompress and read file
                try:
                    with gzip.open(local_file, "rb") as f:
                        csv_data = f.read().decode("utf-8")
                        year_df = pd.read_csv(StringIO(csv_data))
                        aq_df = pd.concat([aq_df, year_df], ignore_index=True)
                except Exception as e:
                    logger.warning(f"Failed to process {local_file}: {str(e)}")
                    continue

    except Exception as e:
        logger.error(f"Failed to fetch S3 data for location {location_id}: {str(e)}")
        return {
            "status": "error",
            "message": f"Failed to fetch S3 data for location {location_id}: {str(e)}",
            "city": city_name
        }

    if aq_df.empty:
        logger.warning(f"No data processed for location {location_id}")
        return {
            "status": "error",
            "message": f"No data processed for location {location_id}",
            "city": city_name
        }

    # Merge rows with same datetime but different sensors
    try:
        # Ensure datetime is in the correct format
        aq_df['datetime'] = pd.to_datetime(aq_df['datetime'])

        # Create a pivot table to merge rows
        # Rows with same location_id and datetime will be merged into one row
        # Each parameter becomes a column with its value
        merged_df = aq_df.pivot_table(
            index=['location_id', 'datetime', 'lat', 'lon'],
            columns='parameter',
            values='value',
            aggfunc='first'  # Take the first value if multiple exist (shouldn't happen per sensor)
        ).reset_index()

        # Flatten the column names (e.g., 'pm25', 'no2', 'co' become 'pm25_value', 'no2_value', 'co_value')
        merged_df.columns = [f"{col}_value" if col in ['pm25', 'no2', 'co', 'bc'] else col for col in merged_df.columns]

        # Add units columns for each parameter
        units_df = aq_df.pivot_table(
            index=['location_id', 'datetime'],
            columns='parameter',
            values='units',
            aggfunc='first'
        ).reset_index()

        # Flatten the units column names (e.g., 'pm25', 'no2', 'co' become 'pm25_units', 'no2_units', 'co_units')
        units_df.columns = [f"{col}_units" if col in ['pm25', 'no2', 'co', 'bc'] else col for col in units_df.columns]

        # Merge the units back into the main DataFrame
        merged_df = merged_df.merge(
            units_df.drop(columns=['location_id', 'datetime']),
            left_index=True,
            right_index=True
        )

    except Exception as e:
        logger.error(f"Failed to merge sensor data for location {location_id}: {str(e)}")
        return {
            "status": "error",
            "message": f"Failed to merge sensor data for location {location_id}: {str(e)}",
            "city": city_name
        }

    # Save merged data to a single CSV
    output_filename = f"openaq_{city_name.replace(' ', '_')}_{YEAR}_{location_id}.csv"
    csv_buffer = StringIO()
    merged_df.to_csv(csv_buffer, index=False)

    # Upload to MinIO
    try:
        minio_client.put_object(
            bucket_name=OPENAQ_BUCKET,
            object_name=output_filename,
            data=BytesIO(csv_buffer.getvalue().encode("utf-8")),
            length=len(csv_buffer.getvalue()),
            content_type="text/csv"
        )
        logger.info(f"Uploaded {output_filename} to MinIO bucket {OPENAQ_BUCKET}")
        return {
            "status": "success",
            "message": f"Successfully processed and uploaded data for {city_name}",
            "city": city_name,
            "minio_file": output_filename
        }
    except Exception as e:
        logger.error(f"Failed to upload {output_filename} to MinIO: {str(e)}")
        return {
            "status": "error",
            "message": f"Failed to upload {output_filename} to MinIO: {str(e)}",
            "city": city_name
        }
