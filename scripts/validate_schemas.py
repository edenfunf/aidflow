#!/usr/bin/env python3
"""Validate that schemas/*.json are valid JSON Schemas (Draft 2020-12) and that
the mapped sample payloads validate against them. Exit 1 on any failure.

Requires: jsonschema  (pip install jsonschema)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    from jsonschema import Draft202012Validator
    from jsonschema.exceptions import SchemaError, ValidationError
except ImportError:  # pragma: no cover
    print("[FAIL] missing dependency: jsonschema (pip install jsonschema)")
    sys.exit(1)

ROOT = Path(__file__).resolve().parent.parent
SCHEMAS_DIR = ROOT / "schemas"
SAMPLES_DIR = ROOT / "samples"

# (sample filename, schema filename, required?)
SAMPLE_MAP = [
    ("report-create.json", "report-create.schema.json", True),
    ("report-create-no-location.json", "report-create.schema.json", True),
    ("platform-create.json", "platform-create.schema.json", True),
    ("geo-feature-shelter.json", "geo-feature.schema.json", True),
    ("public-case.json", "public-case.schema.json", True),
    ("case-event.json", "case-event.schema.json", True),
]

failures = 0


def fail(msg: str) -> None:
    global failures
    failures += 1
    print(f"[FAIL] {msg}")


def load_json(path: Path):
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def main() -> int:
    if not SCHEMAS_DIR.is_dir():
        fail(f"schemas directory not found: {SCHEMAS_DIR}")
        return 1

    schema_files = sorted(SCHEMAS_DIR.glob("*.json"))
    if not schema_files:
        fail("no schemas/*.json found")
        return 1

    schemas: dict[str, dict] = {}
    for path in schema_files:
        try:
            schema = load_json(path)
        except json.JSONDecodeError as e:
            fail(f"invalid JSON: schemas/{path.name} ({e})")
            continue
        try:
            Draft202012Validator.check_schema(schema)
        except SchemaError as e:
            fail(f"invalid JSON Schema: schemas/{path.name} ({e.message})")
            continue
        schemas[path.name] = schema
        print(f"[OK] schema valid: schemas/{path.name}")

    for sample_name, schema_name, required in SAMPLE_MAP:
        sample_path = SAMPLES_DIR / sample_name
        if not sample_path.exists():
            if required:
                fail(f"required sample not found: samples/{sample_name}")
            else:
                print(f"[WARN] sample not found: samples/{sample_name}")
            continue

        schema = schemas.get(schema_name)
        if schema is None:
            fail(f"schema missing for sample {sample_name}: schemas/{schema_name}")
            continue

        try:
            data = load_json(sample_path)
        except json.JSONDecodeError as e:
            fail(f"invalid JSON: samples/{sample_name} ({e})")
            continue

        try:
            Draft202012Validator(schema).validate(data)
        except ValidationError as e:
            loc = "/".join(str(p) for p in e.absolute_path) or "<root>"
            fail(f"sample invalid: samples/{sample_name} at {loc}: {e.message}")
            continue

        print(f"[OK] sample valid: samples/{sample_name}")

    if failures:
        print(f"\nSchema validation FAILED with {failures} error(s).")
        return 1

    print("\nSchema validation passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
