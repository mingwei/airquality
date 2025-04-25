export interface ForecastData {
    DEWP: number;
    WDSP: number;
    MAX: number;
    MIN: number;
    PRCP: number;
    MONTH: number;
    pm25_value: number;
  }
  
  export interface Forecast {
    date: string;
    city_name: string;
    pm25_value: number;
    predicted_aqi: number;
    calculated_aqi: number;
    descriptor: string;
    color: string;
  }
  
  export interface ApiResponse {
    city_name: string;
    forecast: Forecast;
    image_url: string | null;
  }
  
  export interface FormData {
    model_id: number;
    city_name: string;
    forecast_data: ForecastData;
  }