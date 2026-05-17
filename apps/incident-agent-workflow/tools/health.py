import httpx


async def check_service_health(health_url: str) -> dict:
    """Call a service's health endpoint and return its live status."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get(health_url)
            try:
                body = response.json()
            except Exception:
                body = response.text[:500]
            return {
                "url": health_url,
                "status_code": response.status_code,
                "healthy": 200 <= response.status_code < 300,
                "response": body,
            }
        except httpx.TimeoutException:
            return {"url": health_url, "healthy": False, "error": "request timed out — service may be overloaded"}
        except httpx.ConnectError:
            return {"url": health_url, "healthy": False, "error": "connection refused — service is likely down"}
        except Exception as e:
            return {"url": health_url, "healthy": False, "error": str(e)}
