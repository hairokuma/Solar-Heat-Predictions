import requests

CURRENT_WEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"
FORECAST_URL = "https://api.openweathermap.org/data/2.5/forecast"


class WeatherProviderError(Exception):
    """Raised when the weather provider can't be reached or rejects the request."""


def fetch_current_weather(latitude, longitude, api_key, timeout=10):
    try:
        response = requests.get(
            CURRENT_WEATHER_URL,
            params={
                "lat": latitude,
                "lon": longitude,
                "appid": api_key,
                "units": "metric",
            },
            timeout=timeout,
        )
    except requests.RequestException as exc:
        raise WeatherProviderError(f"Could not reach OpenWeatherMap: {exc}") from exc

    if response.status_code != 200:
        raise WeatherProviderError(
            f"OpenWeatherMap returned HTTP {response.status_code}: {response.text[:200]}"
        )

    return response.json()


def fetch_forecast(latitude, longitude, api_key, timeout=10):
    try:
        response = requests.get(
            FORECAST_URL,
            params={
                "lat": latitude,
                "lon": longitude,
                "appid": api_key,
                "units": "metric",
            },
            timeout=timeout,
        )
    except requests.RequestException as exc:
        raise WeatherProviderError(f"Could not reach OpenWeatherMap: {exc}") from exc

    if response.status_code != 200:
        raise WeatherProviderError(
            f"OpenWeatherMap returned HTTP {response.status_code}: {response.text[:200]}"
        )

    return response.json()
