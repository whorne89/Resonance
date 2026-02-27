"""
Tests for post-processing configuration in ConfigManager.
"""

import tempfile


class TestPostProcessingConfig:
    """Test post-processing settings in ConfigManager."""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        import utils.config as config_mod
        self._orig = config_mod.get_app_data_path
        config_mod.get_app_data_path = lambda *a, **kw: self.tmpdir
        from utils.config import ConfigManager
        self.config = ConfigManager()

    def teardown_method(self):
        import utils.config as config_mod
        config_mod.get_app_data_path = self._orig

    def test_post_processing_disabled_by_default(self):
        assert self.config.get_post_processing_enabled() is False

    def test_set_and_get_post_processing_enabled(self):
        self.config.set_post_processing_enabled(True)
        assert self.config.get_post_processing_enabled() is True

        self.config.set_post_processing_enabled(False)
        assert self.config.get_post_processing_enabled() is False

    def test_default_backend_is_llama_server(self):
        assert self.config.get_post_processing_backend() == "llama-server"

    def test_set_and_get_backend(self):
        self.config.set_post_processing_backend("onnx")
        assert self.config.get_post_processing_backend() == "onnx"

        self.config.set_post_processing_backend("llama-server")
        assert self.config.get_post_processing_backend() == "llama-server"

    def test_post_processing_settings_persist_after_save_and_reload(self):
        """Verify settings survive a save/reload cycle."""
        self.config.set_post_processing_enabled(True)
        self.config.set_post_processing_backend("onnx")
        self.config.save()

        # Create a new ConfigManager that reads from the same file
        import utils.config as config_mod
        reloaded = config_mod.ConfigManager()
        assert reloaded.get_post_processing_enabled() is True
        assert reloaded.get_post_processing_backend() == "onnx"
