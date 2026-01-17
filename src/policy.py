# src/policy.py

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional, List

from pydantic import BaseModel, Field


class FirmPolicy(BaseModel):
    # ---- Identity / traceability ----
    name: str = Field(default="Default")
    version: str = Field(default="1.0")

    # ---- Thresholds (numbers) ----
    long_absence_medium_days: int = Field(default=90, ge=1)
    long_absence_high_days: int = Field(default=180, ge=1)
    travel_overlap_employment_min_days: int = Field(default=90, ge=1)
    executive_summary_top_n: int = Field(default=5, ge=1, le=10)

    # ---- Output inclusion rules ----
    clarification_include_priorities: List[str] = Field(
        default_factory=lambda: ["P0", "P1"]
    )
    clarification_include_topics: Optional[List[str]] = None

    # ---- Wording / tone ----
    use_soft_language: bool = True
    disclaimer_text: Optional[str] = "Draft QC output. Attorney review required."
    

DEFAULT_POLICY = FirmPolicy()


def load_policy(path: str | Path | None) -> FirmPolicy:
    """Load FirmPolicy from YAML (.yml/.yaml) or JSON (.json)."""
    if path is None:
        return DEFAULT_POLICY

    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Policy file not found: {p}")

    suffix = p.suffix.lower()
    raw: dict[str, Any]

    if suffix in {".yml", ".yaml"}:
        try:
            import yaml  # type: ignore
        except Exception as e:
            raise RuntimeError(
                "YAML policy requested but PyYAML is not installed. "
                "Install with: pip install pyyaml"
            ) from e
        raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):
            raise ValueError("YAML policy must contain a mapping/object at the top level.")
        return FirmPolicy(**raw)

    if suffix == ".json":
        import json
        raw = json.loads(p.read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):
            raise ValueError("JSON policy must contain an object at the top level.")
        return FirmPolicy(**raw)

    raise ValueError(f"Unsupported policy file type: {suffix} (use .yaml/.yml or .json)")