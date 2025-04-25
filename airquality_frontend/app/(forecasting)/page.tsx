'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { FormData, ForecastData } from '@/app/(forecasting)/types/type';

export default function Home() {
  const router = useRouter();
  const [formData, setFormData] = useState<FormData>({
    model_id: 2,
    city_name: 'Los Angeles',
    forecast_data: {
      DEWP: 54.0,
      WDSP: 6.0,
      MAX: 73.0,
      MIN: 60.0,
      PRCP: 0.0,
      MONTH: 4,
      pm25_value: 9.6,
    },
  });
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);

  const handleInputChange = (
    e: React.ChangeEvent<HTMLInputElement>,
    isForecastData: boolean = false
  ) => {
    const { name, value } = e.target;
    if (isForecastData) {
      setFormData({
        ...formData,
        forecast_data: {
          ...formData.forecast_data,
          [name]: parseFloat(value) || 0,
        },
      });
    } else {
      setFormData({
        ...formData,
        [name]: name === 'model_id' ? parseInt(value) || 0 : value,
      });
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsLoading(true);

    try {
      const response = await fetch('http://localhost:8000/airquality/forecast-aqi-withimg/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(formData),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error || 'Failed to fetch forecast');
      }

      const data = await response.json();
      router.push(`/forecast?data=${encodeURIComponent(JSON.stringify(data))}`);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-100 flex items-center justify-center p-4">
      <div className="bg-white p-8 rounded-lg shadow-lg w-full max-w-md relative">
        <h1 className="text-2xl font-bold mb-6 text-center">Air Quality Forecast</h1>
        {error && <p className="text-red-500 mb-4 text-center">{error}</p>}
        {isLoading && (
          <div className="absolute inset-0 flex items-center justify-center bg-white bg-opacity-75">
            <div className="w-8 h-8 border-4 border-blue-600 border-t-transparent rounded-full animate-spin"></div>
          </div>
        )}
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700">Model ID</label>
            <input
              type="number"
              name="model_id"
              value={formData.model_id}
              onChange={(e) => handleInputChange(e)}
              className="mt-1 block w-full border-gray-300 rounded-md shadow-sm focus:ring-blue-500 focus:border-blue-500"
              required
              disabled={isLoading}
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700">City Name</label>
            <input
              type="text"
              name="city_name"
              value={formData.city_name}
              onChange={(e) => handleInputChange(e)}
              className="mt-1 block w-full border-gray-300 rounded-md shadow-sm focus:ring-blue-500 focus:border-blue-500"
              required
              disabled={isLoading}
            />
          </div>
          {Object.keys(formData.forecast_data).map((field) => (
            <div key={field}>
              <label className="block text-sm font-medium text-gray-700">{field}</label>
              <input
                type="number"
                step="any"
                name={field}
                value={formData.forecast_data[field as keyof ForecastData]}
                onChange={(e) => handleInputChange(e, true)}
                className="mt-1 block w-full border-gray-300 rounded-md shadow-sm focus:ring-blue-500 focus:border-blue-500"
                required
                disabled={isLoading}
              />
            </div>
          ))}
          <button
            type="submit"
            className={`w-full py-2 px-4 rounded-md text-white transition-colors ${
              isLoading ? 'bg-blue-400 cursor-not-allowed' : 'bg-blue-600 hover:bg-blue-700'
            }`}
            disabled={isLoading}
          >
            {isLoading ? 'Processing...' : 'Get Forecast'}
          </button>
        </form>
      </div>
    </div>
  );
}