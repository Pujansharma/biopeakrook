#!/usr/bin/env python3
"""Validate pre-consultation OpenAPI schema."""

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import django
from django.conf import settings

if not settings.configured:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings.development")
    django.setup()

from pre_consultation.utils.schema import generate_pre_consultation_openapi_schema

REQUIRED_PUT_REQUEST_PATHS = (
    "/pre-consultation/session/patient_goals_priorities/",
    "/pre-consultation/session/patient_lifestyle_environment/",
)


def main() -> int:
    schema = generate_pre_consultation_openapi_schema()
    paths = schema.get("paths", {})
    path_count = len(paths)
    if path_count == 0:
        print("No pre-consultation paths found in schema.", file=sys.stderr)
        return 1

    missing_requests: list[str] = []
    for path_key in REQUIRED_PUT_REQUEST_PATHS:
        put_operation = paths.get(path_key, {}).get("put", {})
        if not put_operation.get("requestBody"):
            missing_requests.append(path_key)

    if missing_requests:
        for path_key in missing_requests:
            print(f"Missing PUT requestBody: {path_key}", file=sys.stderr)
        return 1

    print(f"Pre-consultation OpenAPI schema valid ({path_count} paths).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
