import json
import urllib.request

RAINY_TERMS = ("shower", "rain", "thunder", "drizzle")
FORECAST_URLS = (
    "https://api-open.data.gov.sg/v2/real-time/api/two-hr-forecast",
    "https://api.data.gov.sg/v1/environment/2-hour-weather-forecast",
)


def weather_risk_for(locality):
    forecast = ""
    last_error = ""
    for url in FORECAST_URLS:
        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
            forecast = find_forecast(payload, locality)
            if forecast:
                break
            last_error = "Forecast unavailable"
        except Exception as error:
            last_error = f"Weather API unavailable ({error.__class__.__name__})"

    if not forecast:
        return last_error or "Weather check pending", "Unknown"
    if any(term in forecast.lower() for term in RAINY_TERMS):
        return forecast, "High"
    if "cloudy" in forecast.lower():
        return forecast, "Medium"
    return forecast, "Low"


def find_forecast(payload, locality):
    data = payload.get("data", payload)
    forecasts = data.get("items", [{}])[0].get("forecasts", [])
    return next((item["forecast"] for item in forecasts if item.get("area") == locality), "")
