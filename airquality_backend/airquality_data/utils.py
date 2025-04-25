#utils.py
def calculate_aqi(pollutant, concentration):
    """Calculate AQI based on PM2.5 concentration using EPA breakpoints."""
    if pollutant != 'pm25':
        return 0
    if concentration < 0:
        return 0
    breakpoints = [
        (0.0, 12.0, 0, 50),
        (12.1, 35.4, 51, 100),
        (35.5, 55.4, 101, 150),
        (55.5, 150.4, 151, 200),
        (150.5, 250.4, 201, 300),
        (250.5, 500.4, 301, 500)
    ]
    for (c_low, c_high, i_low, i_high) in breakpoints:
        if c_low <= concentration <= c_high:
            aqi = ((i_high - i_low) / (c_high - c_low)) * (concentration - c_low) + i_low
            return round(aqi, 2)
    return 0

def get_aqi_category(aqi):
    """Return AQI descriptor and color based on AQI value."""
    if 0 <= aqi <= 50:
        return {"descriptor": "Good", "color": "Green"}
    elif 51 <= aqi <= 100:
        return {"descriptor": "Moderate", "color": "Yellow"}
    elif 101 <= aqi <= 150:
        return {"descriptor": "Unhealthy for Sensitive Groups", "color": "Orange"}
    elif 151 <= aqi <= 200:
        return {"descriptor": "Unhealthy", "color": "Red"}
    elif 201 <= aqi <= 300:
        return {"descriptor": "Very Unhealthy", "color": "Purple"}
    else:  # 301+
        return {"descriptor": "Hazardous", "color": "Maroon"}
    

def get_aqi_prompt(descriptor):
        """Return the appropriate prompt based on AQI descriptor."""
        prompts = {
            "Good": "A bright, clear cityscape with blue skies, lush greenery, reflecting clean and fresh air.  800x600.",
            "Moderate": "A cityscape with slightly hazy skies, mild sunlight filtering through, and people going about daily activities with caution.  800x600.",
            "Unhealthy for Sensitive Groups": "A city with noticeable haze, muted colors, and some people wearing masks, indicating caution for sensitive groups.  800x600.",
            "Unhealthy": "A city shrouded in thick haze, dim sunlight, and limited visibility, with people avoiding outdoor activities. 800x600.",
            "Very Unhealthy": "A gloomy cityscape with heavy smog, dark skies, and deserted streets, reflecting dangerous air quality.  800x600.",
            "Hazardous": "A dystopian cityscape engulfed in dense, toxic smog, with no visible greenery or activity, symbolizing hazardous air conditions. 800x600."
        }
        return prompts.get(descriptor, prompts["Good"])  # Default to Good if descriptor not found