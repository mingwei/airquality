from django.urls import path
from .view_data import FetchNOAADataView,AQDataProcessView
from .views import  PrepareTrainingDataView ,TrainModelView ,ForecastAQIView,ForecastAQIWithImageView

urlpatterns = [

    path('fetch-noaa/', FetchNOAADataView.as_view(), name='fetch_noaa_aq_data'),
    path('fetch-openaq/', AQDataProcessView.as_view(), name='fetch_openaq_data'),
    path('train-model/', TrainModelView.as_view(), name='train_model'),
    path('prepare-training/', PrepareTrainingDataView.as_view(), name='prepare_training_data'),
    path('forecast-aqi/', ForecastAQIView.as_view() , name='forecast_aqi'),
    path('forecast-aqi-withimg/', ForecastAQIWithImageView.as_view() , name='forecast_aqi_img'),

]
"""



    path('upload-stations/', UploadStationsView.as_view(), name='upload_stations'),
    path('fetch-noaa/', FetchNOAADataView.as_view(), name='fetch_noaa_data'),
    
"""