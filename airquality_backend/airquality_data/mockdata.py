#mockdata.py
#Get Station data from isd-history.csv
## Station ID,USAF,WBAN,City,State,Country,Lat,Lon,Elev

#Get aqLocation data from https://explore.openaq.org/locations/605
## should include: Pm2.5, O3, NO2, CO, SO2, PM10, AQI, aq_location_id, city, country, latitude, longitude, state


CITIES = {
    "Los Angeles": {
        "station_id": "72295023174",
        "latitude": 33.938, 
        "longitude": -118.387,
        "aq_location_id":"2138",
        "usaf": "722950",
        "wban": "23174",
        "station_name": "LOS ANGELES INTERNATIONAL AIRPORT",
        "country": "US",
        "state": "CA",
        "icao": "KLAX",
        "elevation_m": 29.7,
        "begin_date": "19430101",
        "end_date": "20250416"
    },


    "San Francisco": {
        "station_id": "99847999999",
        "latitude": 37.798,  
        "longitude": -122.393,
        "aq_location_id":"2009",
        "usaf": "998479",
        "wban": "99999",
        "station_name": "SAN FRANCISCO (PIER 1)",
        "country": "US",
        "state": "CA",
        "icao": "",
        "elevation_m": 10.0,
        "begin_date": "19430101",
        "end_date": "20251231"
    },
    "PHILADELPHIA": {	
        "station_id": "72408013739",
        "latitude": 39.873, 
        "longitude": -75.227,
        "aq_location_id":"1884",
        "usaf": "724080",
        "wban": "13739",
        "station_name": "PHILADELPHIA INTERNATIONAL AIRPORT",
        "country": "US",
        "state": "PA",
        "icao": "KPHL",
        "elevation_m": 2.2,
        "begin_date": "19430101",
        "end_date": "20251231"
    }


}
