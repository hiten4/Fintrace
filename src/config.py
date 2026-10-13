"""Config loader. The only code in Phase 0 (no modeling)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

ROOT: Path = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG: Path = ROOT / "configs" / "config.yaml"


def load_config(path: Path | str = DEFAULT_CONFIG) -> dict[str, Any]:
    """Load the YAML config and return it as a dict."""
    with open(path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    if not isinstance(cfg, dict):
        raise ValueError(f"Config at {path} must be a YAML mapping.")
    return cfg