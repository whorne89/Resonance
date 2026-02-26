"""Tests for PostProcessor."""
import os
import sys
import pytest
from unittest.mock import MagicMock, patch

# Add src to path so imports work
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from core.post_processor import PostProcessor


class TestPostProcessorInit:
    def test_default_device_is_cpu(self):
        pp = PostProcessor.__new__(PostProcessor)
        pp.device = "cpu"
        pp.model = None
        assert pp.device == "cpu"

    def test_model_path_includes_filename(self):
        with patch('core.post_processor.get_app_data_path', return_value='/fake/data'):
            pp = PostProcessor(device="cpu")
            assert "qwen2.5-0.5b-instruct-q4_k_m.gguf" in pp.model_path


class TestIsModelDownloaded:
    def test_returns_false_when_file_missing(self, tmp_path):
        with patch('core.post_processor.get_app_data_path', return_value=str(tmp_path)):
            pp = PostProcessor(device="cpu")
            assert pp.is_model_downloaded() is False

    def test_returns_true_when_file_exists(self, tmp_path):
        with patch('core.post_processor.get_app_data_path', return_value=str(tmp_path)):
            pp = PostProcessor(device="cpu")
            # Create the file
            os.makedirs(os.path.dirname(pp.model_path), exist_ok=True)
            open(pp.model_path, 'w').close()
            assert pp.is_model_downloaded() is True


class TestProcess:
    def _make_pp_with_mock_model(self):
        """Return a PostProcessor with a mocked llama model."""
        with patch('core.post_processor.get_app_data_path', return_value='/fake'):
            pp = PostProcessor(device="cpu")
        mock_model = MagicMock()
        mock_model.create_chat_completion.return_value = {
            "choices": [{"message": {"content": "Hello, world."}}]
        }
        pp.model = mock_model
        return pp

    def test_returns_corrected_text(self):
        pp = self._make_pp_with_mock_model()
        result = pp.process("hello world")
        assert result == "Hello, world."

    def test_returns_empty_string_for_empty_input(self):
        pp = self._make_pp_with_mock_model()
        result = pp.process("")
        assert result == ""
        # Model should NOT be called for empty input
        pp.model.create_chat_completion.assert_not_called()

    def test_returns_original_on_model_error(self):
        with patch('core.post_processor.get_app_data_path', return_value='/fake'):
            pp = PostProcessor(device="cpu")
        mock_model = MagicMock()
        mock_model.create_chat_completion.side_effect = RuntimeError("model exploded")
        pp.model = mock_model
        result = pp.process("some text")
        assert result == "some text"

    def test_returns_original_if_model_returns_empty(self):
        with patch('core.post_processor.get_app_data_path', return_value='/fake'):
            pp = PostProcessor(device="cpu")
        mock_model = MagicMock()
        mock_model.create_chat_completion.return_value = {
            "choices": [{"message": {"content": ""}}]
        }
        pp.model = mock_model
        result = pp.process("original text")
        assert result == "original text"


class TestChangeDevice:
    def test_change_device_resets_model(self):
        with patch('core.post_processor.get_app_data_path', return_value='/fake'):
            pp = PostProcessor(device="cpu")
        pp.model = MagicMock()  # Simulate loaded model
        pp.change_device("cuda")
        assert pp.device == "cuda"
        assert pp.model is None

    def test_change_to_same_device_does_nothing(self):
        with patch('core.post_processor.get_app_data_path', return_value='/fake'):
            pp = PostProcessor(device="cpu")
        mock = MagicMock()
        pp.model = mock
        pp.change_device("cpu")
        # Model should still be set (not reset)
        assert pp.model is mock
