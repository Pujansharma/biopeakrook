import hashlib
import json
from typing import Any

SOURCE_FIELDS = {
    "data_source",
    "source_of_data",
    "source_of_data_string",
    "sources_of_data",
    "sources_of_data_array",
    "source",
}

CANONICAL_SOURCE_NAMES = {
    name.replace(" ", "").lower(): name
    for name in [
        "Apple Health",
        "Health Connect",
        "Samsung Health",
        "Garmin",
        "Oura",
        "Whoop",
        "Polar",
        "Withings",
        "Fitbit",
        "Dexcom",
        "Android",
        "Strava",
        "Mi Fitness",
        "Xiaomi",
        "Zepp",
    ]
}


def canonical_source(value: Any) -> str:
    source = str(value).strip()
    normalized = source.replace(" ", "").replace("_", "").lower()
    return CANONICAL_SOURCE_NAMES.get(normalized, source[:120])


def source_values(value: Any) -> list[str]:
    if isinstance(value, str) and value.strip():
        if value.startswith(("[", "{")):
            try:
                return source_values(json.loads(value))
            except json.JSONDecodeError:
                return [canonical_source(value)]
        return [canonical_source(value)]
    if isinstance(value, list):
        return [source for item in value for source in source_values(item)]
    if isinstance(value, dict):
        return [
            source
            for key, item in value.items()
            if key in SOURCE_FIELDS
            for source in source_values(item)
        ]
    return []


def append_unique_devices(devices: list[dict], values: Any) -> None:
    if not isinstance(values, list):
        return
    existing = {json.dumps(device, sort_keys=True, default=str) for device in devices}
    for value in values:
        if not isinstance(value, dict):
            continue
        serialized = json.dumps(value, sort_keys=True, default=str)
        if serialized not in existing:
            devices.append(value)
            existing.add(serialized)


def walk_provenance(
    node: Any,
    *,
    path: str,
    sources: set[str],
    devices: list[dict],
    contexts: list[dict],
) -> None:
    if isinstance(node, dict):
        local_sources = {
            source
            for key, value in node.items()
            if key in SOURCE_FIELDS
            for source in source_values(value)
        }
        sources.update(local_sources)
        device_metadata = node.get("device_source_data_array")
        append_unique_devices(devices, device_metadata)
        if local_sources or isinstance(device_metadata, list):
            contexts.append(
                {
                    "path": path,
                    "sources": sorted(local_sources),
                    "devices": device_metadata or [],
                }
            )
        for key, value in node.items():
            if key == "device_source_data_array":
                continue
            child_path = f"{path}.{key}" if path else key
            walk_provenance(
                value,
                path=child_path,
                sources=sources,
                devices=devices,
                contexts=contexts,
            )
        return
    if isinstance(node, list):
        for index, value in enumerate(node):
            walk_provenance(
                value,
                path=f"{path}[{index}]",
                sources=sources,
                devices=devices,
                contexts=contexts,
            )


def extract_provenance(payload: dict) -> dict:
    sources: set[str] = set()
    devices: list[dict] = []
    contexts: list[dict] = []
    walk_provenance(
        payload,
        path="",
        sources=sources,
        devices=devices,
        contexts=contexts,
    )
    ordered_sources = sorted(sources) or ["unspecified"]
    source_key = hashlib.sha256(
        json.dumps(ordered_sources, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:24]
    return {
        "source_key": source_key,
        "data_sources": ordered_sources,
        "source_label": " + ".join(ordered_sources),
        "multi_source": len(ordered_sources) > 1,
        "device_metadata": devices,
        "source_contexts": contexts,
    }

