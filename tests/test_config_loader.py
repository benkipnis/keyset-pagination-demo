"""
Phase 1: Unit tests for config loading.
No MongoDB required; tests use a fixture YAML or the example config.
"""

import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

from src.config_loader import (
    MONGODB_URI_ENV,
    ConfigError,
    get_mongodb_uri,
    load_config,
)

# Directory containing the test file; project root is parent of tests/
TESTS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = TESTS_DIR.parent
CONFIG_EXAMPLE = PROJECT_ROOT / "config" / "config.example.yaml"


def test_load_config_from_example_file():
    """Load config from config.example.yaml; assert database, collection, page size, tiers."""
    assert CONFIG_EXAMPLE.exists(), "config.example.yaml should exist"
    config = load_config(CONFIG_EXAMPLE, require_uri=False)

    assert "mongodb" in config
    assert config["mongodb"]["database"] == "pov_claims"
    assert config["mongodb"]["collection"] == "claims"

    assert "query" in config
    assert config["query"]["default_page_size"] == 100

    assert "data_generation" in config
    dg = config["data_generation"]
    assert dg["total_claims_target"] == 3_000_000
    assert "date_start" in dg
    assert "date_end" in dg
    assert "tiers" in dg
    tiers = dg["tiers"]
    assert isinstance(tiers, list)
    assert len(tiers) >= 7  # 1K, 5K, 10K, 50K, 100K, 500K, 1M
    tier_sizes = {t["claims_per_provider"] for t in tiers}
    assert 1_000 in tier_sizes
    assert 1_000_000 in tier_sizes
    assert dg["batch_size"] == 10_000

    assert "performance" in config
    perf = config["performance"]
    assert perf["iterations"] == 10
    assert "tiers_to_test" in perf
    assert 1000 in perf["tiers_to_test"]
    assert 1_000_000 in perf["tiers_to_test"]


def test_load_config_does_not_include_uri_when_require_uri_false():
    """With require_uri=False, config should not contain mongodb.uri from env."""
    # Ensure we don't leak env into config when not required
    config = load_config(CONFIG_EXAMPLE, require_uri=False)
    assert "uri" not in config.get("mongodb", {})


def test_load_config_injects_uri_when_require_uri_true_and_env_set(monkeypatch):
    """With require_uri=True and MONGODB_URI set, config should contain mongodb.uri."""
    monkeypatch.setenv(MONGODB_URI_ENV, "mongodb://localhost:27017")
    config = load_config(CONFIG_EXAMPLE, require_uri=True)
    assert config["mongodb"]["uri"] == "mongodb://localhost:27017"


def test_load_config_raises_when_require_uri_true_but_env_unset(monkeypatch):
    """With require_uri=True and MONGODB_URI unset, load_config raises ConfigError."""
    monkeypatch.delenv(MONGODB_URI_ENV, raising=False)
    with pytest.raises(ConfigError) as exc_info:
        load_config(CONFIG_EXAMPLE, require_uri=True)
    assert MONGODB_URI_ENV in str(exc_info.value)


def test_get_mongodb_uri_returns_value_when_set(monkeypatch):
    """get_mongodb_uri() returns the env value when set."""
    monkeypatch.setenv(MONGODB_URI_ENV, "mongodb+srv://cluster.example.com/")
    assert get_mongodb_uri() == "mongodb+srv://cluster.example.com/"


def test_get_mongodb_uri_raises_when_unset(monkeypatch):
    """get_mongodb_uri() raises ConfigError when MONGODB_URI is not set."""
    monkeypatch.delenv(MONGODB_URI_ENV, raising=False)
    with pytest.raises(ConfigError) as exc_info:
        get_mongodb_uri()
    assert MONGODB_URI_ENV in str(exc_info.value)


def test_load_config_raises_when_file_missing():
    """load_config raises ConfigError when the file does not exist."""
    with pytest.raises(ConfigError) as exc_info:
        load_config(PROJECT_ROOT / "config" / "nonexistent.yaml")
    assert "not found" in str(exc_info.value).lower()


def test_load_config_raises_on_invalid_yaml(tmp_path):
    """load_config raises ConfigError when YAML is invalid."""
    bad_yaml = tmp_path / "bad.yaml"
    bad_yaml.write_text("not: valid: yaml: [")
    with pytest.raises(ConfigError) as exc_info:
        load_config(bad_yaml)
    assert "invalid" in str(exc_info.value).lower() or "yaml" in str(exc_info.value).lower()


def test_tier_counts_sum_near_total_target():
    """Tiers in example config should sum to approximately total_claims_target."""
    config = load_config(CONFIG_EXAMPLE, require_uri=False)
    target = config["data_generation"]["total_claims_target"]
    tiers = config["data_generation"]["tiers"]
    total = sum(t["claims_per_provider"] * t["num_providers"] for t in tiers)
    assert abs(total - target) < 100_000, f"Tier total {total} should be near target {target}"


def test_dotenv_loaded_uri_available(tmp_path, monkeypatch):
    """When .env file contains MONGODB_URI, load_dotenv() makes it available to get_mongodb_uri()."""
    # Clear so we don't use real .env from project
    monkeypatch.delenv(MONGODB_URI_ENV, raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("MONGODB_URI=mongodb://localhost:27017/test\n")
    load_dotenv(env_file, override=True)
    assert get_mongodb_uri() == "mongodb://localhost:27017/test"
