from fastapi import FastAPI, HTTPException, Path
import httpx
from prometheus_fastapi_instrumentator import Instrumentator

app = FastAPI(title="Weather API Service")
Instrumentator().instrument(app).expose(app)

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"


@app.get("/")
def health_check():
    return {
        "status": "ok",
        "message": "Weather service is running"
    }


@app.get("/weather/latitude={latitude}&longitude={longitude}")
async def get_weather(
    latitude: float = Path(..., ge=-90, le=90, example=41.8781),
    longitude: float = Path(..., ge=-180, le=180, example=-87.6298)
):
    """
    Fetch weather data for a given latitude and longitude.
    Example:
    /weather/latitude=41.8781&longitude=-87.6298
    """

    return await fetch_weather(latitude, longitude)


async def fetch_weather(latitude: float, longitude: float):
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": (
            "temperature_2m,relative_humidity_2m,apparent_temperature,"
            "is_day,precipitation,rain,showers,snowfall,weather_code,"
            "cloud_cover,pressure_msl,surface_pressure,wind_speed_10m,"
            "wind_direction_10m,wind_gusts_10m"
        ),
        "hourly": (
            "temperature_2m,relative_humidity_2m,apparent_temperature,"
            "precipitation_probability,precipitation,rain,showers,snowfall,"
            "weather_code,pressure_msl,surface_pressure,cloud_cover,"
            "visibility,wind_speed_10m,wind_direction_10m,wind_gusts_10m"
        ),
        "daily": (
            "weather_code,temperature_2m_max,temperature_2m_min,"
            "apparent_temperature_max,apparent_temperature_min,sunrise,sunset,"
            "daylight_duration,sunshine_duration,uv_index_max,"
            "precipitation_sum,rain_sum,showers_sum,snowfall_sum,"
            "precipitation_probability_max,wind_speed_10m_max,"
            "wind_gusts_10m_max,wind_direction_10m_dominant"
        ),
        "timezone": "auto"
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(OPEN_METEO_URL, params=params)

        response.raise_for_status()
        return response.json()

    except HTTPException:
        raise

    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail="Weather API request timed out"
        )

    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Weather API returned error: {e.response.status_code}"
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected error: {str(e)}"
        )
