#!/usr/bin/env python3
"""Export pre-consultation OpenAPI schema to docs/openapi/pre-consultation-openapi.json."""

import json
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

OUTPUT_PATH = PROJECT_ROOT / "docs" / "openapi" / "pre-consultation-openapi.json"


def main() -> int:
    schema = generate_pre_consultation_openapi_schema()
    path_count = len(schema.get("paths", {}))
    if path_count == 0:
        print("No pre-consultation paths found in schema.", file=sys.stderr)
        return 1

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(f"{json.dumps(schema, indent=2)}\n")
    print(
        f"Exported {path_count} paths to {OUTPUT_PATH} ({OUTPUT_PATH.stat().st_size} bytes)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
