"""Current conditions from Open-Meteo.

Open-Meteo needs no API key, which is why the original picked it.  The location
is a free-text place name, so it goes through the geocoding endpoint first and
the resolved coordinates are cached for the process lifetime.
"""

from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request
from typing import Any

from shell.modules.base import Module
from shell.theme import GLYPHS

logger = logging.getLogger(__name__)

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
TIMEOUT_SECONDS = 10

#: WMO weather codes -> (label, glyph attribute).  Grouped rather than
#: enumerated: the pill has room for a word, not for "light freezing drizzle".
_CODES: tuple[tuple[range, str, str], ...] = (
    (range(0, 1), "clear", "weather_clear"),
    (range(1, 4), "cloudy", "weather_cloudy"),
    (range(45, 49), "fog", "weather_fog"),
    (range(51, 68), "rain", "weather_rain"),
    (range(71, 78), "snow", "weather_snow"),
    (range(80, 83), "showers", "weather_rain"),
    (range(85, 87), "snow", "weather_snow"),
    (range(95, 100), "storm", "weather_storm"),
)


def describe_code(code: int) -> tuple[str, str]:
    for span, label, glyph_attr in _CODES:
        if code in span:
            return label, getattr(GLYPHS, glyph_attr)
    return "unknown", GLYPHS.weather_cloudy


class WeatherModule(Module):
    name = "weather"
    poll_interval_ms = 3_600_000

    def __init__(
        self,
        location: str = "Delhi",
        units: str = "metric",
        interval_ms: int = 3_600_000,
        parent: object | None = None,
    ) -> None:
        super().__init__(parent)  # type: ignore[arg-type]
        self._location = location
        self._units = units
        self.poll_interval_ms = interval_ms
        self._coords: tuple[float, float] | None = None

    def configure(self, location: str, units: str, interval_ms: int) -> None:
        if location != self._location:
            self._coords = None
        self._location = location
        self._units = units
        self.poll_interval_ms = interval_ms

    def refresh(self) -> None:
        self.run_async(self._fetch, self._apply)

    def _apply(self, data: dict[str, Any] | None) -> None:
        if data:
            self.update(**data)

    # -- network -----------------------------------------------------------

    def _get_json(self, url: str, params: dict[str, Any]) -> Any:
        query = urllib.parse.urlencode(params)
        with urllib.request.urlopen(f"{url}?{query}", timeout=TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8"))

    def _resolve_location(self) -> tuple[float, float] | None:
        if self._coords is not None:
            return self._coords
        try:
            payload = self._get_json(GEOCODE_URL, {"name": self._location, "count": 1, "format": "json"})
        except Exception as exc:
            logger.warning("could not geocode %r: %s", self._location, exc)
            return None
        results = payload.get("results") or []
        if not results:
            logger.warning("no such place: %r", self._location)
            return None
        self._coords = (float(results[0]["latitude"]), float(results[0]["longitude"]))
        return self._coords

    def _fetch(self) -> dict[str, Any] | None:
        coords = self._resolve_location()
        if coords is None:
            return None
        latitude, longitude = coords
        imperial = self._units == "imperial"
        try:
            payload = self._get_json(
                FORECAST_URL,
                {
                    "latitude": latitude,
                    "longitude": longitude,
                    "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m",
                    "daily": "temperature_2m_max,temperature_2m_min",
                    "forecast_days": 1,
                    "temperature_unit": "fahrenheit" if imperial else "celsius",
                    "wind_speed_unit": "mph" if imperial else "kmh",
                    "timezone": "auto",
                },
            )
        except Exception as exc:
            logger.warning("weather fetch failed: %s", exc)
            return None

        current = payload.get("current", {})
        daily = payload.get("daily", {})
        code = int(current.get("weather_code", 0))
        label, glyph = describe_code(code)
        degree = "°F" if imperial else "°C"
        temperature = current.get("temperature_2m")
        return {
            "location": self._location,
            "temperature": temperature,
            "temperature_text": f"{round(temperature)}{degree}" if temperature is not None else "--",
            "high": _first(daily.get("temperature_2m_max")),
            "low": _first(daily.get("temperature_2m_min")),
            "humidity": current.get("relative_humidity_2m"),
            "wind": current.get("wind_speed_10m"),
            "code": code,
            "label": label,
            "glyph": glyph,
        }


def _first(value: Any) -> Any:
    return value[0] if isinstance(value, list) and value else None
