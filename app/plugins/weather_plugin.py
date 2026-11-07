import requests
from typing import Dict, Any
from app.plugins.base import BasePlugin


class WeatherPlugin(BasePlugin):
    name = "weather_tracker"
    description = "Fetches local weather & temperature forecast using 100% free Open-Meteo API (no key needed)."

    def run(self, latitude: float = 30.48, longitude: float = 76.59, **kwargs) -> Dict[str, Any]:
        """
        Default coordinates set to Rajpura/Punjab region or pass custom lat/lon.
        Free endpoint with no API keys.
        """
        try:
            url = (
                f"https://api.open-meteo.com/v1/forecast?"
                f"latitude={latitude}&longitude={longitude}&current_weather=true"
            )
            res = requests.get(url, timeout=10)
            res.raise_for_status()
            data = res.json().get("current_weather", {})
            return {
                "success": True,
                "temperature_celsius": data.get("temperature"),
                "windspeed_kmh": data.get("windspeed"),
                "weather_code": data.get("weathercode"),
                "timestamp": data.get("time")
            }
        except Exception as e:
            return {"success": False, "error": str(e)}


# Expose run() function for simple modular discovery
plugin_instance = WeatherPlugin()


def run(**kwargs):
    return plugin_instance.run(**kwargs)
