from django.db import models

class GSODStation(models.Model):
    station_id = models.CharField(max_length=20, unique=True)  # USAF + WBAN 11 characters
    usaf = models.CharField(max_length=6)  # USAF 
    wban = models.CharField(max_length=5)  # WBAN 
    station_name = models.CharField(max_length=128)  # Station name
    country = models.CharField(max_length=64, blank=True) 
    state = models.CharField(max_length=64, blank=True) 
    icao = models.CharField(max_length=64, blank=True)  
    latitude = models.FloatField() 
    longitude = models.FloatField()  
    elevation_m = models.FloatField()  
    begin_date = models.CharField(max_length=8)  # BEGIN (YYYYMMDD)
    end_date = models.CharField(max_length=8, blank=True)  # END (YYYYMMDD)

    def __str__(self):
        return f"{self.name} ({self.station_id})"

class NOAAData(models.Model):
    filename = models.CharField(max_length=255)
    bucket = models.CharField(max_length=100)
    city_name = models.CharField(max_length=100)
    station = models.ForeignKey(GSODStation, on_delete=models.CASCADE)
    year_start = models.IntegerField()
    year_end = models.IntegerField()
    record_count = models.IntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"NOAA {self.city_name} ({self.year_start}-{self.year_end})"

class OpenAQData(models.Model):
    filename = models.CharField(max_length=255)
    bucket = models.CharField(max_length=100)
    city_name = models.CharField(max_length=100)
    parameter = models.CharField(max_length=10)  # e.g., pm25
    year_start = models.IntegerField()
    year_end = models.IntegerField()
    record_count = models.IntegerField()
    location_ids = models.JSONField()  # List of OpenAQ location IDs
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"OpenAQ {self.city_name} {self.parameter} ({self.year_start}-{self.year_end})"

class MergedData(models.Model):
    train_filename = models.CharField(max_length=255,blank=True, null=True)
    test_filename = models.CharField(max_length=255,blank=True, null=True)
    bucket = models.CharField(max_length=100,blank=True, null=True)
    noaa_dataset = models.ForeignKey(NOAAData, on_delete=models.CASCADE,blank=True, null=True)
    openaq_dataset = models.ForeignKey(OpenAQData, on_delete=models.CASCADE,blank=True, null=True)
    unhealthy_threshold = models.FloatField(blank=True, null=True)
    train_record_count = models.IntegerField(blank=True, null=True)
    test_record_count = models.IntegerField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Merged {self.noaa_dataset.city_name} ({self.created_at})"

class TrainedModel(models.Model):
    model_name = models.CharField(max_length=100)
    model_path = models.CharField(max_length=255)
    bucket = models.CharField(max_length=100)
    merged_dataset = models.ForeignKey(MergedData, on_delete=models.CASCADE)
    leaderboard = models.JSONField()  # AutoGluon leaderboard
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Model {self.model_name} ({self.created_at})"

class GeneratedImage(models.Model):
    filename = models.CharField(max_length=255)
    bucket = models.CharField(max_length=100)
    city_name = models.CharField(max_length=100)
    aqi = models.FloatField()
    theme = models.CharField(max_length=50)
    presigned_url = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Image {self.city_name} AQI {self.aqi} ({self.created_at})"