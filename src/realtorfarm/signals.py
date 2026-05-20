from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "signals.json"


@lru_cache(maxsize=1)
def load_signal_config(path: str | Path = CONFIG_PATH) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def normalize_signal(raw: str, config: dict | None = None) -> tuple[str, str]:
    cfg = config or load_signal_config()
    lookup = {}
    for tier, names in cfg["tiers"].items():
        for name, aliases in names.items():
            lookup[name.lower()] = (name, tier)
            for alias in aliases:
                lookup[alias.lower()] = (name, tier)
    key = raw.strip().lower()
    if key not in lookup:
        raise ValueError(f"Unknown distressed-property signal: {raw!r}")
    return lookup[key]
