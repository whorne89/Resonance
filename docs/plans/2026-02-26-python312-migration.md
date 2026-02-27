# Python 3.12 Migration + Versioning Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Switch Resonance to Python 3.12, clean up the post-processing branch mess, cherry-pick valuable UI improvements, and establish a single versioning source of truth.

**Architecture:** Stay on `main` branch. Capture useful uncommitted changes from `feat/post-processing` as a patch before switching. Rebuild venv under Python 3.12. Version reads dynamically from `importlib.metadata` at runtime.

**Tech Stack:** Python 3.12, uv, PySide6, faster-whisper, pytest

---

### Task 1: Install Python 3.12

**Step 1: Download and install Python 3.12**

Go to https://www.python.org/downloads/release/python-3120/ and download the Windows 64-bit installer.
During install: check "Add Python to PATH". Do NOT uninstall 3.13 — they coexist.

**Step 2: Verify both versions are available**

```bash
py -3.12 --version   # should print Python 3.12.x
py -3.13 --version   # should still print Python 3.13.x
```

---

### Task 2: Save useful changes before switching branches

The working directory on `feat/post-processing` has uncommitted changes worth keeping:
- `src/core/transcriber.py` — `is_model_downloaded()` handles full HF repo IDs
- `src/gui/settings_dialog.py` — cublas DLL check for CUDA 12 and 13

**Step 1: Save patches for the files we want**

```bash
cd F:/Resonance-main
git diff src/core/transcriber.py > /tmp/transcriber.patch
git diff src/gui/settings_dialog.py > /tmp/settings.patch
```

**Step 2: Stash or discard everything else**

```bash
git checkout -- .
```

---

### Task 3: Switch to main and apply saved changes

**Step 1: Switch to main**

```bash
cd F:/Resonance-main
git checkout main
```

**Step 2: Apply the patches**

```bash
git apply /tmp/transcriber.patch
git apply /tmp/settings.patch
```

If apply fails due to context mismatch, manually apply the relevant sections — the diffs are small.

---

### Task 4: Update pyproject.toml for Python 3.12

**Files:**
- Modify: `pyproject.toml`

**Step 1: Update requires-python and version**

In `pyproject.toml`, change:
```toml
requires-python = ">=3.9"
version = "1.0.0"
```
To:
```toml
requires-python = ">=3.12,<3.13"
version = "1.2.0"
```

**Step 2: Create .python-version file**

```bash
echo "3.12" > F:/Resonance-main/.python-version
```

This tells uv which Python to use for the project.

---

### Task 5: Rebuild the venv with Python 3.12

**Step 1: Delete the old venv**

```bash
rm -rf F:/Resonance-main/.venv
```

**Step 2: Create new venv with Python 3.12**

```bash
cd F:/Resonance-main
uv venv --python 3.12
```

**Step 3: Install all dependencies**

```bash
uv sync --dev
```

**Step 4: Verify Python version in venv**

```bash
uv run python --version
```
Expected: `Python 3.12.x`

---

### Task 6: Fix versioning — single source of truth

**Files:**
- Modify: `src/gui/system_tray.py`

The About dialog currently has a hardcoded version string. Replace it with a dynamic read from `importlib.metadata`.

**Step 1: Update show_about() in system_tray.py**

Find the `show_about` method (~line 169). Replace the `about_text` block so the version line reads:

```python
def show_about(self):
    """Show about dialog window."""
    from importlib.metadata import version as pkg_version, PackageNotFoundError
    try:
        app_version = pkg_version("resonance")
    except PackageNotFoundError:
        app_version = "dev"

    about_text = (
        "Resonance - Voice to Text Application\n\n"
        "Resonance is a voice-to-text application that is toggled\n"
        "by using a configurable hotkey. Hold the hotkey while\n"
        "speaking, then release to transcribe your speech into text.\n\n"
        "Uses local Whisper AI - no internet required,\n"
        "completely private and secure.\n\n"
        "Created by William Horne\n\n"
        f"Version {app_version}"
    )
    # rest of method unchanged
```

**Step 2: Install the package in editable mode so importlib.metadata can find it**

```bash
cd F:/Resonance-main
uv pip install -e .
```

**Step 3: Verify version reads correctly**

```bash
uv run python -c "from importlib.metadata import version; print(version('resonance'))"
```
Expected: `1.2.0`

---

### Task 7: Add distil-whisper models to the settings dropdown

**Files:**
- Modify: `src/gui/settings_dialog.py`
- Modify: `src/core/transcriber.py`

This is the one UI improvement worth keeping from the branch work.

**Step 1: Update model list in settings_dialog.py**

Find where `model_combo` is populated. Replace the simple string list with a display-name → model-ID mapping:

```python
self.model_combo = QComboBox()
models = [
    ("tiny",            "tiny"),
    ("base",            "base"),
    ("small",           "small"),
    ("distil-small.en", "Systran/faster-distil-whisper-small.en"),
    ("distil-large-v3", "Systran/faster-distil-whisper-large-v3"),
]
for display_name, model_id in models:
    self.model_combo.addItem(display_name, userData=model_id)
```

Update `load_current_settings()` to use `findData()` instead of `findText()`:
```python
idx = self.model_combo.findData(self.config.get_model_size())
if idx >= 0:
    self.model_combo.setCurrentIndex(idx)
```

Update `save_settings()` to use `currentData()` for the model ID:
```python
self.config.set_model_size(self.model_combo.currentData())
```

**Step 2: Update transcriber.py is_model_downloaded() for HF repo IDs**

The existing method assumes short model names like `"small"`. Add handling for full HF repo IDs:

```python
def is_model_downloaded(self, model_size):
    if '/' in model_size:
        cache_name = "models--" + model_size.replace('/', '--')
    else:
        cache_name = f"models--Systran--faster-whisper-{model_size}"
    model_path = os.path.join(self.models_dir, cache_name)
    # rest of method unchanged
```

---

### Task 8: Run tests and verify

**Step 1: Run the full test suite**

```bash
cd F:/Resonance-main
uv run pytest tests/ -v
```

Expected: all existing tests pass. (Post-processor tests will be gone since we're on main.)

**Step 2: Smoke test the app launches**

```bash
uv run python src/main.py
```

Check: app starts, tray icon appears, About dialog shows "Version 1.2.0".

---

### Task 9: Commit

**Step 1: Stage and commit**

```bash
cd F:/Resonance-main
git add pyproject.toml .python-version src/gui/system_tray.py src/gui/settings_dialog.py src/core/transcriber.py docs/
git commit -m "feat: migrate to Python 3.12, add distil-whisper models, single-source versioning"
```

---

## Convention Going Forward

**Bumping the version:** Edit only `pyproject.toml`. The About dialog reads it automatically.

**Semantic versioning:**
- `1.2.x` — bug fixes
- `1.x.0` — new features
- `x.0.0` — breaking changes or major rewrites
