import logging
import time
from pathlib import Path as FilePath

from fastapi import FastAPI, HTTPException, Path, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
import httpx
from prometheus_fastapi_instrumentator import Instrumentator

LOG_DIR = FilePath(__file__).resolve().parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_DIR / "app.log"),
    ],
)
logger = logging.getLogger("weather-app1")

app = FastAPI(title="Weather API Service")
Instrumentator().instrument(app).expose(app)

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"


@app.middleware("http")
async def log_failed_requests(request: Request, call_next):
    start_time = time.perf_counter()

    try:
        response = await call_next(request)
    except Exception:
        duration_ms = (time.perf_counter() - start_time) * 1000
        logger.exception(
            "request_failed method=%s path=%s duration_ms=%.2f",
            request.method,
            request.url.path,
            duration_ms,
        )
        raise

    duration_ms = (time.perf_counter() - start_time) * 1000
    if response.status_code >= 400:
        logger.warning(
            "request_completed status=%s method=%s path=%s client=%s duration_ms=%.2f",
            response.status_code,
            request.method,
            request.url.path,
            request.client.host if request.client else "unknown",
            duration_ms,
        )

    return response


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.warning(
        "validation_failed method=%s path=%s client=%s errors=%s",
        request.method,
        request.url.path,
        request.client.host if request.client else "unknown",
        exc.errors(),
    )
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors()},
    )


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
        logger.exception(
            "weather_provider_timeout latitude=%s longitude=%s",
            latitude,
            longitude,
        )
        raise HTTPException(
            status_code=504,
            detail="Weather API request timed out"
        )

    except httpx.HTTPStatusError as e:
        logger.exception(
            "weather_provider_error latitude=%s longitude=%s status_code=%s",
            latitude,
            longitude,
            e.response.status_code,
        )
        raise HTTPException(
            status_code=502,
            detail=f"Weather API returned error: {e.response.status_code}"
        )

    except Exception as e:
        logger.exception(
            "unexpected_weather_error latitude=%s longitude=%s",
            latitude,
            longitude,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected error: {str(e)}"
        )
