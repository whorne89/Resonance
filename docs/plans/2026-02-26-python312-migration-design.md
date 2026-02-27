# Python 3.12 Migration + Versioning Design

## Summary

Migrate Resonance from Python 3.13 to Python 3.12 for pre-built wheel compatibility, clean up the failed post-processing branch, cherry-pick valuable UI work, and establish a single source of truth for the app version.

## Goals

- All dependencies install via pre-built wheels (no source compilation)
- GPU transcription works on any machine with an NVIDIA GPU
- Version shown in About dialog always matches pyproject.toml automatically
- Clean main branch ready for future development and eventual packaging

## Branch Strategy

Abandon `feat/post-processing`. Switch to `main`. Cherry-pick from the branch:
- Distil-whisper model additions to the model dropdown
- Processing device (CPU/GPU) setting in the settings UI

Drop entirely: all llama-cpp-python / grammar post-processor work.

## Python 3.12

Install Python 3.12 alongside existing 3.13 (no uninstall). Pin project to 3.12 via `.python-version` file and `requires-python = ">=3.12,<3.13"` in pyproject.toml. Recreate venv — all core deps have pre-built 3.12 wheels.

## Versioning

Single source of truth: `pyproject.toml` version field.

`system_tray.py` About dialog reads version at runtime:
```python
from importlib.metadata import version
app_version = version('resonance')
```

Starting version: `1.2.0` (reflects Python 3.12 migration + GPU settings work).

Config schema version in `config.py` remains independent (tracks config file format for migrations).

Convention going forward: bump `pyproject.toml` version on meaningful changes. No other files to update.
