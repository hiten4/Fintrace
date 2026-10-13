"""Phase 0 smoke tests: environment works, config is sane."""
import importlib

import duckdb
import pytest

from src.config import load_config

LIBS = [
    "duckdb", "pandas", "numpy", "networkx", "lightgbm", "sklearn",
    "shap", "langgraph", "fastapi", "streamlit", "yaml", "pyarrow",
]


@pytest.mark.parametrize("name", LIBS)
def test_library_imports(name: str) -> None:
    importlib.import_module(name)


def test_duckdb_runs_sql() -> None:
    assert duckdb.sql("SELECT 42 AS x").fetchone() == (42,)


def test_config_split_is_temporal_and_sums_to_one() -> None:
    cfg = load_config()
    split = cfg["split"]
    assert split["method"] == "temporal"
    total = split["train_frac"] + split["val_frac"] + split["test_frac"]
    assert abs(total - 1.0) < 1e-9


def test_config_agent_guardrails() -> None:
    agent = load_config()["agent"]
    assert agent["never_declare_guilt"] is True
    assert agent["verifier_required"] is True