import json
from pathlib import Path

_REGISTRY_PATH = Path(__file__).parent / "service_registry.json"

with open(_REGISTRY_PATH, encoding="utf-8") as _f:
    _REGISTRY: dict = {k: v for k, v in json.load(_f).items() if not k.startswith("_")}


def get_service_config(service_name: str) -> dict | None:
    """Return the registry entry for service_name, or None if unknown."""
    return _REGISTRY.get(service_name)


def list_services() -> list[str]:
    return list(_REGISTRY.keys())
