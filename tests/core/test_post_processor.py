"""
Tests for PostProcessor class.
Tests only the interface, defaults, and graceful fallback behavior.
Does NOT require actual model files or llama-server binary.
"""

import tempfile
import pytest


class TestPostProcessorDefaults:
    """Test PostProcessor default state and constructor."""

    def setup_method(self):
        """Patch get_app_data_path to use a temp dir so tests don't see real model files."""
        self.tmpdir = tempfile.mkdtemp()
        import utils.resource_path as rp_mod
        self._orig_get_app_data_path = rp_mod.get_app_data_path

        def _fake_get_app_data_path(subdir=""):
            import os
            path = os.path.join(self.tmpdir, subdir) if subdir else self.tmpdir
            os.makedirs(path, exist_ok=True)
            return path

        rp_mod.get_app_data_path = _fake_get_app_data_path

        # Also patch the module-level reference in post_processor
        import core.post_processor as pp_mod
        self._orig_pp_get_app_data_path = pp_mod.get_app_data_path
        pp_mod.get_app_data_path = _fake_get_app_data_path

    def teardown_method(self):
        """Restore original get_app_data_path."""
        import utils.resource_path as rp_mod
        rp_mod.get_app_data_path = self._orig_get_app_data_path

        import core.post_processor as pp_mod
        pp_mod.get_app_data_path = self._orig_pp_get_app_data_path

    def test_default_backend_is_llama_server(self):
        from core.post_processor import PostProcessor
        pp = PostProcessor()
        assert pp.backend == "llama-server"

    def test_custom_backend_via_constructor(self):
        from core.post_processor import PostProcessor
        pp = PostProcessor(backend="onnx")
        assert pp.backend == "onnx"

    def test_is_loaded_returns_false_initially(self):
        from core.post_processor import PostProcessor
        pp = PostProcessor()
        assert pp.is_loaded() is False

    def test_process_empty_string_returns_empty(self):
        from core.post_processor import PostProcessor
        pp = PostProcessor()
        assert pp.process("") == ""

    def test_process_returns_text_unchanged_when_not_loaded(self):
        from core.post_processor import PostProcessor
        pp = PostProcessor()
        # Model is not loaded, so process should return text unchanged
        assert pp.process("hello world") == "hello world"

    def test_process_returns_text_on_unknown_backend(self):
        from core.post_processor import PostProcessor
        pp = PostProcessor(backend="nonexistent")
        pp._loaded = True  # Force loaded state to test backend dispatch
        result = pp.process("hello world")
        assert result == "hello world"

    def test_shutdown_when_not_loaded(self):
        from core.post_processor import PostProcessor
        pp = PostProcessor()
        # Should not raise
        pp.shutdown()
        assert pp.is_loaded() is False

    def test_is_model_downloaded_false_when_files_missing(self):
        from core.post_processor import PostProcessor
        pp = PostProcessor()
        # Temp dir has no model files, should return False
        assert pp.is_model_downloaded() is False

    def test_is_model_downloaded_false_for_onnx_when_files_missing(self):
        from core.post_processor import PostProcessor
        pp = PostProcessor(backend="onnx")
        assert pp.is_model_downloaded() is False
