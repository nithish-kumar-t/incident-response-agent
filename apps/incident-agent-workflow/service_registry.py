import json
from config import settings


def _load() -> dict:
    try:
        with open(settings.SERVICE_REGISTRY_PATH, "r") as f:
            data = json.load(f)
        return {k: v for k, v in data.items() if not k.startswith("_")}
    except Exception:
        return {}


def get_service_config(service_name: str) -> dict | None:
    return _load().get(service_name)


def list_services() -> list[str]:
    return list(_load().keys())
