from rest_framework import serializers
from .models import NOAAData, OpenAQData, MergedData, TrainedModel, GeneratedImage



class FetchNOAADataSerializer(serializers.Serializer):
    city_name = serializers.CharField(required=True)
    year_start = serializers.IntegerField(default=2016)
    year_end = serializers.IntegerField(default=2022)

class FetchOpenAQDataSerializer(serializers.Serializer):
    city_name = serializers.CharField(required=True)
    parameter = serializers.CharField(default='pm25')
    year_start = serializers.IntegerField(default=2016)
    year_end = serializers.IntegerField(default=2022)
    radius_meters = serializers.IntegerField(default=16100)


class PrepareTrainingDataSerializer(serializers.Serializer):
    noaa_filename = serializers.CharField(required=True)
    openaq_filename = serializers.CharField(required=True)
    pollutant = serializers.ChoiceField(
        choices=['pm25', 'no2', 'co', 'o3'],  # Supported pollutants
        required=True
    )


class TrainModelSerializer(serializers.Serializer):
    train_filename = serializers.CharField(max_length=255)
    merged_data_id = serializers.IntegerField()
    model_name = serializers.CharField(max_length=100, required=False)
    time_limit = serializers.IntegerField(required=False)
    models_to_train = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        default=['RF', 'XT', 'XGB', 'GBM']
    )

class ForecastAQISerializer(serializers.Serializer):
    model_id = serializers.IntegerField()
    city_name = serializers.CharField(max_length=100)
    forecast_data = serializers.DictField(
        child=serializers.FloatField(),
        help_text="Dictionary with DEWP, WDSP, MAX, MIN, PRCP, MONTH, pm25_value"
    )

    def validate_forecast_data(self, value):
        required_keys = ['DEWP', 'WDSP', 'MAX', 'MIN', 'PRCP', 'MONTH', 'pm25_value']
        missing_keys = [key for key in required_keys if key not in value]
        if missing_keys:
            raise serializers.ValidationError(f"Missing keys in forecast_data: {missing_keys}")
        return value

class GenerateCityImageSerializer(serializers.Serializer):
    city = serializers.CharField(required=True)
    aqi = serializers.FloatField(required=True)
    theme = serializers.CharField(default='daily')

class NOAADataSerializer(serializers.ModelSerializer):
    station_id = serializers.CharField(source='station.station_id')
    station_name = serializers.CharField(source='station.station_name')
    station_lat = serializers.FloatField(source='station.latitude')
    station_lon = serializers.FloatField(source='station.longitude')

    class Meta:
        model = NOAAData
        fields = ['filename', 'bucket', 'city_name', 'station_id', 'year_start', 'year_end',
                  'record_count', 'created_at', 'station_name', 'station_lat', 'station_lon']

class OpenAQDataSerializer(serializers.ModelSerializer):
    class Meta:
        model = OpenAQData
        fields = ['filename', 'bucket', 'city_name', 'parameter', 'year_start', 'year_end',
                  'record_count', 'location_ids', 'created_at']

class MergedDataSerializer(serializers.ModelSerializer):
    class Meta:
        model = MergedData
        fields = ['train_filename', 'test_filename', 'bucket', 'noaa_dataset', 'openaq_dataset',
                  'unhealthy_threshold', 'train_record_count', 'test_record_count', 'created_at']

class TrainedModelSerializer(serializers.ModelSerializer):
    class Meta:
        model = TrainedModel
        fields = ['model_name', 'model_path', 'bucket', 'merged_dataset', 'leaderboard', 'created_at']

class GeneratedImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = GeneratedImage
        fields = ['filename', 'bucket', 'city_name', 'aqi', 'theme', 'presigned_url', 'created_at']