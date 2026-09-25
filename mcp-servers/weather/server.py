"""
Weather MCP Server
==================
Gives the agent two tools:
  - get_current_weather(city)
  - get_forecast(city, days)

Data source: Open-Meteo (https://open-meteo.com) -> free, NO API key needed.

Run it:
    python server.py
It listens at: http://127.0.0.1:8001/mcp   (Streamable HTTP transport)
"""

import os

import httpx
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

# Load settings from the project's .env file (one folder up from /servers)
load_dotenv()  # local runs: finds the project .env | Docker: env comes from compose

HOST = os.getenv("MCP_HOST", "127.0.0.1")
PORT = int(os.getenv("WEATHER_PORT", "8001"))

# 1) Create the MCP server. The name shows up in the agent's tool list.
mcp = FastMCP("weather", host=HOST, port=PORT)

GEO_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

# Open-Meteo returns numeric "weather codes". This maps them to plain English.
WEATHER_CODES = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Rime fog",
    51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
    61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
    71: "Slight snow", 73: "Moderate snow", 75: "Heavy snow",
    80: "Rain showers", 81: "Moderate rain showers", 82: "Violent rain showers",
    95: "Thunderstorm", 96: "Thunderstorm with hail", 99: "Severe thunderstorm with hail",
}


async def _geocode(client: httpx.AsyncClient, city: str) -> dict | None:
    """Convert a city name into latitude/longitude."""
    resp = await client.get(GEO_URL, params={"name": city, "count": 1})
    resp.raise_for_status()
    results = resp.json().get("results") or []
    return results[0] if results else None


def _place_label(place: dict) -> str:
    parts = [place.get("name"), place.get("admin1"), place.get("country")]
    return ", ".join(p for p in parts if p)


# 2) Each function decorated with @mcp.tool() becomes a tool the agent can call.
#    The docstring is IMPORTANT: the LLM reads it to decide when to use the tool.
@mcp.tool()
async def get_current_weather(city: str) -> str:
    """Get the current weather for a city.

    Args:
        city: City name, for example "Hyderabad" or "London".
    """
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            place = await _geocode(client, city)
            if not place:
                return f"Could not find a city named '{city}'."

            resp = await client.get(FORECAST_URL, params={
                "latitude": place["latitude"],
                "longitude": place["longitude"],
                "current": "temperature_2m,apparent_temperature,relative_humidity_2m,"
                           "wind_speed_10m,weather_code",
                "timezone": "auto",
            })
            resp.raise_for_status()
            cur = resp.json()["current"]
    except httpx.HTTPError as e:
        return f"Weather service error: {e}"

    condition = WEATHER_CODES.get(cur.get("weather_code"), "Unknown")
    return (
        f"Current weather in {_place_label(place)} (local time {cur['time']}):\n"
        f"- Condition: {condition}\n"
        f"- Temperature: {cur['temperature_2m']} °C (feels like {cur['apparent_temperature']} °C)\n"
        f"- Humidity: {cur['relative_humidity_2m']} %\n"
        f"- Wind: {cur['wind_speed_10m']} km/h"
    )


@mcp.tool()
async def get_forecast(city: str, days: int = 3) -> str:
    """Get a daily weather forecast for a city.

    Args:
        city: City name, for example "Bengaluru".
        days: Number of days to forecast (1 to 7). Default is 3.
    """
    days = max(1, min(int(days), 7))
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            place = await _geocode(client, city)
            if not place:
                return f"Could not find a city named '{city}'."

            resp = await client.get(FORECAST_URL, params={
                "latitude": place["latitude"],
                "longitude": place["longitude"],
                "daily": "temperature_2m_max,temperature_2m_min,"
                         "precipitation_probability_max,weather_code",
                "forecast_days": days,
                "timezone": "auto",
            })
            resp.raise_for_status()
            daily = resp.json()["daily"]
    except httpx.HTTPError as e:
        return f"Weather service error: {e}"

    lines = [f"{days}-day forecast for {_place_label(place)}:"]
    for i, date in enumerate(daily["time"]):
        condition = WEATHER_CODES.get(daily["weather_code"][i], "Unknown")
        rain = daily["precipitation_probability_max"][i]
        lines.append(
            f"- {date}: {condition}, "
            f"{daily['temperature_2m_min'][i]}–{daily['temperature_2m_max'][i]} °C, "
            f"rain chance {f'{rain} %' if rain is not None else 'n/a'}"
        )
    return "\n".join(lines)


# 3) Start the server using the Streamable HTTP transport.
if __name__ == "__main__":
    print(f"🌤  Weather MCP server running at http://{HOST}:{PORT}/mcp")
    mcp.run(transport="streamable-http")
