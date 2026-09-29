import requests

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"


class GeocodingError(Exception):
    """Raised when the geocoding provider can't be reached or errors out."""


def geocode_address(query, count=5, timeout=10):
    """Look up lat/lon candidates for a free-text address or city name.

    Uses Open-Meteo's geocoding API, which is free and needs no API key -
    unlike OpenWeatherMap's geocoder, which would require the weather API
    key before it's collected in the wizard.
    """
    try:
        response = requests.get(
            GEOCODE_URL,
            params={"name": query, "count": count, "language": "en", "format": "json"},
            timeout=timeout,
        )
    except requests.RequestException as exc:
        raise GeocodingError(f"Could not reach the geocoding service: {exc}") from exc

    if response.status_code != 200:
        raise GeocodingError(
            f"Geocoding service returned HTTP {response.status_code}: {response.text[:200]}"
        )

    results = response.json().get("results") or []
    return [
        {
            "name": r.get("name"),
            "admin1": r.get("admin1"),
            "country": r.get("country"),
            "latitude": r.get("latitude"),
            "longitude": r.get("longitude"),
        }
        for r in results
    ]
