'use client';

import { useSearchParams } from 'next/navigation';
import { ApiResponse } from '@/app/(forecasting)/types/type';
import { useState } from 'react';
import Image from 'next/image';
import Link from 'next/link';

export default function Forecast() {
  const searchParams = useSearchParams();
  const data = searchParams.get('data');

  if (!data) {
    return (
      <div className="min-h-screen bg-gray-100 flex items-center justify-center">
        <p>Loading...</p>
      </div>
    );
  }

  let forecastData: ApiResponse;
  try {
    forecastData = JSON.parse(decodeURIComponent(data));
  } catch (err) {
    return (
      <div className="min-h-screen bg-gray-100 flex items-center justify-center">
        <p className="text-red-500">Error parsing forecast data</p>
      </div>
    );
  }

  const { city_name, forecast, image_url } = forecastData;
  // Prepend Django server URL to relative image_url
  const fullImageUrl = image_url ? `http://localhost:8000${image_url}` : null;

  return (
    <div className="min-h-screen bg-gray-100 py-8 px-4">
      <div className="max-w-4xl mx-auto bg-white p-8 rounded-lg shadow-lg">
        <h1 className="text-3xl font-bold mb-6 text-center">
          Air Quality Forecast for {city_name}
        </h1>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
          <div>
            <h2 className="text-xl font-semibold mb-4">Forecast Details</h2>
            <p><strong>Date:</strong> {forecast.date}</p>
            <p><strong>PM2.5 Value:</strong> {forecast.pm25_value.toFixed(2)} µg/m³</p>
            <p><strong>Predicted AQI:</strong> {forecast.predicted_aqi.toFixed(2)}</p>
            <p><strong>Calculated AQI:</strong> {forecast.calculated_aqi.toFixed(2)}</p>
            <p><strong>Category:</strong> {forecast.descriptor}</p>
            <p>
              <strong>Color:</strong>
              <span
                className="inline-block w-4 h-4 ml-2 rounded-full"
                style={{ backgroundColor: forecast.color.toLowerCase() }}
              ></span>
            </p>
            <p>
              <strong>Image URL:</strong>{' '}
              {fullImageUrl ? (
                <a
                  href={fullImageUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-blue-600 hover:underline"
                >
                  View Image
                </a>
              ) : (
                'No image available'
              )}
            </p>
          </div>
          <div>
            <h2 className="text-xl font-semibold mb-4">Air Quality Visualization</h2>
            {fullImageUrl ? (
              <Image
                src={fullImageUrl}
                alt={`Air quality visualization for ${city_name}`}
                width={800}
                height={600}
                className="w-full h-auto rounded-lg shadow-md"
              />
            ) : (
              <p className="text-gray-500">No image available</p>
            )}
          </div>
        </div>
        <Link href="/">
          <button className="mt-6 w-full bg-blue-600 text-white py-2 px-4 rounded-md hover:bg-blue-700 transition-colors">
            Back to Input
          </button>
        </Link>
      </div>
    </div>
  );
}