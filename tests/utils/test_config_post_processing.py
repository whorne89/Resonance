"""Tests for new post-processing config keys."""
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from utils.config import ConfigManager


@pytest.fixture
def config(tmp_path):
    """Fresh config with temp file."""
    return ConfigManager(config_file=str(tmp_path / "settings.json"))


class TestProcessingDevice:
    def test_default_device_is_cpu(self, config):
        assert config.get_processing_device() == "cpu"

    def test_set_and_get_device(self, config):
        config.set_processing_device("cuda")
        assert config.get_processing_device() == "cuda"

    def test_device_persists_after_save_load(self, tmp_path):
        cfg = ConfigManager(config_file=str(tmp_path / "s.json"))
        cfg.set_processing_device("cuda")
        cfg.save()
        cfg2 = ConfigManager(config_file=str(tmp_path / "s.json"))
        assert cfg2.get_processing_device() == "cuda"


class TestPostProcessingEnabled:
    def test_default_disabled(self, config):
        assert config.get_post_processing_enabled() is False

    def test_set_and_get_enabled(self, config):
        config.set_post_processing_enabled(True)
        assert config.get_post_processing_enabled() is True

    def test_enabled_persists_after_save_load(self, tmp_path):
        cfg = ConfigManager(config_file=str(tmp_path / "s.json"))
        cfg.set_post_processing_enabled(True)
        cfg.save()
        cfg2 = ConfigManager(config_file=str(tmp_path / "s.json"))
        assert cfg2.get_post_processing_enabled() is True
