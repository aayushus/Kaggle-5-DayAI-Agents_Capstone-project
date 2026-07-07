from __future__ import annotations

from functools import lru_cache
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from typing import Any

import yaml


ROOT_DIR = Path(__file__).resolve().parents[2]
SKILL_DIR = ROOT_DIR / ".agent" / "skills" / "scout"


def _load_module(path: Path, module_name: str):
    spec = spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load module from {path}")
    module = module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


@lru_cache(maxsize=1)
def load_verify_links_module():
    return _load_module(SKILL_DIR / "scripts" / "verify_links.py", "scout_skill_verify_links")


@lru_cache(maxsize=1)
def load_tam_formula_module():
    return _load_module(SKILL_DIR / "scripts" / "fetch_tam_formula.py", "scout_skill_fetch_tam_formula")


@lru_cache(maxsize=1)
def load_evidence_normalizer_module():
    return _load_module(SKILL_DIR / "scripts" / "evidence_normalizer.py", "scout_skill_evidence_normalizer")


@lru_cache(maxsize=1)
def load_pricing_normalizer_module():
    return _load_module(SKILL_DIR / "scripts" / "pricing_normalizer.py", "scout_skill_pricing_normalizer")


@lru_cache(maxsize=1)
def load_artifact_qa_module():
    return _load_module(SKILL_DIR / "scripts" / "artifact_qa.py", "scout_skill_artifact_qa")


@lru_cache(maxsize=1)
def load_market_schema() -> dict[str, Any]:
    schema_path = SKILL_DIR / "schemas" / "market_schema.yaml"
    return yaml.safe_load(schema_path.read_text(encoding="utf-8")) or {}
