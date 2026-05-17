import httpx
from config import settings


async def check_service_health(service_name: str) -> dict:
    url = settings.SERVICE_HEALTH_URL_TEMPLATE.format(service_name=service_name)
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get(url)
            try:
                body = response.json()
            except Exception:
                body = response.text[:500]
            return {
                "service": service_name,
                "url": url,
                "status_code": response.status_code,
                "healthy": 200 <= response.status_code < 300,
                "response": body,
            }
        except httpx.TimeoutException:
            return {"service": service_name, "healthy": False, "error": "request timed out — service may be overloaded"}
        except httpx.ConnectError:
            return {"service": service_name, "healthy": False, "error": "connection refused — service is likely down"}
        except Exception as e:
            return {"service": service_name, "healthy": False, "error": str(e)}
