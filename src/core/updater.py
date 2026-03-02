"""
Auto-updater for Resonance.
Checks GitHub Releases for new versions and applies updates.
"""

import json
import os
import sys
import zipfile
import tempfile
import subprocess
from dataclasses import dataclass
from urllib.request import urlopen, Request
from urllib.error import URLError

from packaging.version import Version

from utils.resource_path import get_app_data_path, is_bundled
from utils.logger import get_logger

GITHUB_REPO = "whorne89/Resonance"
RELEASES_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"


@dataclass
class UpdateInfo:
    """Information about an available update."""
    version_str: str
    tag_name: str
    download_url: str


class UpdateChecker:
    """Checks for and applies Resonance updates from GitHub Releases."""

    def __init__(self):
        self.logger = get_logger()
        try:
            from importlib.metadata import version as pkg_version
            self.current_version = pkg_version("resonance")
        except Exception:
            self.current_version = "0.0.0"

    def check_for_update(self):
        """
        Check GitHub Releases for a newer version.

        Returns:
            UpdateInfo if a newer version is available, None otherwise.
        """
        try:
            req = Request(RELEASES_URL, headers={"Accept": "application/vnd.github.v3+json"})
            with urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            tag = data.get("tag_name", "")
            # Strip leading 'v' from tag (e.g., "v3.1.0" -> "3.1.0")
            version_str = tag.lstrip("v")

            if not version_str:
                return None

            remote = Version(version_str)
            local = Version(self.current_version)

            if remote <= local:
                self.logger.info(f"Up to date: local={local}, remote={remote}")
                return None

            # Find .zip asset in release assets
            download_url = None
            for asset in data.get("assets", []):
                if asset.get("name", "").endswith(".zip"):
                    download_url = asset["browser_download_url"]
                    break

            if not download_url:
                self.logger.warning("Update found but no .zip asset in release")
                return None

            self.logger.info(f"Update available: {version_str} (current: {self.current_version})")
            return UpdateInfo(
                version_str=version_str,
                tag_name=tag,
                download_url=download_url,
            )

        except (URLError, json.JSONDecodeError, ValueError) as e:
            self.logger.warning(f"Update check failed: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error during update check: {e}")
            return None

    def download_update(self, update_info, progress_callback=None):
        """
        Download the update asset to .resonance/updates/.

        Args:
            update_info: UpdateInfo with the download URL.
            progress_callback: Optional callable(downloaded_bytes, total_bytes).

        Returns:
            Path to the downloaded file, or None on failure.
        """
        try:
            updates_dir = get_app_data_path("updates")
            filename = f"Resonance-{update_info.version_str}.zip"
            dest_path = os.path.join(updates_dir, filename)

            # Remove previous download if it exists
            if os.path.exists(dest_path):
                os.remove(dest_path)

            req = Request(update_info.download_url)
            with urlopen(req, timeout=60) as resp:
                total = int(resp.headers.get("Content-Length", 0))
                downloaded = 0
                chunk_size = 64 * 1024

                with open(dest_path, "wb") as f:
                    while True:
                        chunk = resp.read(chunk_size)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        if progress_callback:
                            progress_callback(downloaded, total)

            self.logger.info(f"Update downloaded to {dest_path}")
            return dest_path

        except Exception as e:
            self.logger.error(f"Update download failed: {e}")
            return None

    def apply_update(self, downloaded_path):
        """
        Apply an update for bundled EXE installs.

        Extracts the ZIP to a temp directory, writes a batch script that
        waits for this process to exit, copies new files over, relaunches,
        and cleans up.

        Args:
            downloaded_path: Path to the downloaded .zip file.

        Returns:
            True if the update script was launched, False on failure.
        """
        if not is_bundled():
            self.logger.warning("apply_update called on non-bundled install")
            return False

        try:
            # Extract to a temp directory next to the app
            app_dir = os.path.dirname(sys.executable)
            extract_dir = tempfile.mkdtemp(prefix="resonance_update_", dir=app_dir)

            with zipfile.ZipFile(downloaded_path, "r") as zf:
                zf.extractall(extract_dir)

            # If the ZIP contains a single top-level folder, use its contents
            entries = os.listdir(extract_dir)
            if len(entries) == 1 and os.path.isdir(os.path.join(extract_dir, entries[0])):
                extract_dir = os.path.join(extract_dir, entries[0])

            pid = os.getpid()
            exe_path = sys.executable
            zip_path = downloaded_path

            # Write batch script
            bat_path = os.path.join(app_dir, "_resonance_update.bat")
            bat_content = (
                "@echo off\n"
                ":waitloop\n"
                f'tasklist /FI "PID eq {pid}" 2>NUL | find /I "{pid}" >NUL\n'
                "if not errorlevel 1 (timeout /t 1 /nobreak >NUL & goto waitloop)\n"
                f'xcopy /E /Y /Q "{extract_dir}\\*" "{app_dir}\\"\n'
                f'start "" "{exe_path}"\n'
                f'rd /S /Q "{extract_dir}" 2>NUL\n'
                f'del /F /Q "{zip_path}" 2>NUL\n'
                '(goto) 2>NUL & del /F /Q "%~f0"\n'
            )

            with open(bat_path, "w", encoding="utf-8") as f:
                f.write(bat_content)

            # Launch the batch script detached
            subprocess.Popen(
                ["cmd.exe", "/c", bat_path],
                creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW,
                close_fds=True,
            )

            self.logger.info("Update script launched, application will restart")
            return True

        except Exception as e:
            self.logger.error(f"Failed to apply update: {e}")
            return False

    @staticmethod
    def get_source_update_message(update_info):
        """
        Get instructions for updating a source (non-bundled) install.

        Args:
            update_info: UpdateInfo for the available update.

        Returns:
            String with update instructions.
        """
        return f"Resonance {update_info.version_str} is available.\nRun: git pull && uv sync"
