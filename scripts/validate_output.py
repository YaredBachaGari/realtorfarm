#!/usr/bin/env python3
"""Validate that a RealtorFarm output file follows the requested data= JSON shape."""
from __future__ import annotations

import argparse
import json


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("file")
    args = p.parse_args()
    text = open(args.file, encoding="utf-8").read().strip()
    if not text.startswith("data= "):
        raise SystemExit("output must start with 'data= '")
    payload = json.loads(text.removeprefix("data= "))
    assert "accessed_date" in payload and isinstance(payload.get("properties"), list)
    for prop in payload["properties"]:
        for key in ["Owner", "property address", "parcel id", "Signals"]:
            assert key in prop, f"missing {key}: {prop}"
    print(f"valid: {len(payload['properties'])} properties")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
