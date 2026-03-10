"""
Media playback control for Resonance.
Pauses/resumes media during recording using system media keys.
Only pauses if audio is actually playing — avoids starting music when nothing is active.
"""

import sys

from utils.logger import get_logger

logger = get_logger()


def _is_audio_playing():
    """
    Detect whether audio is currently playing on the system.

    Returns True if audio is playing, False if silent.
    Falls back to True on any error (safe default: pause anyway).
    """
    if sys.platform == "win32":
        return _is_audio_playing_windows()
    elif sys.platform == "darwin":
        return _is_audio_playing_macos()
    else:
        return _is_audio_playing_linux()


def _is_audio_playing_windows():
    """Windows: Query Core Audio IAudioMeterInformation for peak level."""
    try:
        import ctypes
        from ctypes import wintypes, byref, POINTER, c_float, c_void_p

        ole32 = ctypes.windll.ole32

        CLSCTX_ALL = 0x17
        COINIT_APARTMENTTHREADED = 0x2
        RPC_E_CHANGED_MODE = 0x80010106 & 0xFFFFFFFF

        # GUIDs
        class GUID(ctypes.Structure):
            _fields_ = [
                ("Data1", ctypes.c_ulong),
                ("Data2", ctypes.c_ushort),
                ("Data3", ctypes.c_ushort),
                ("Data4", ctypes.c_ubyte * 8),
            ]

        def _make_guid(s):
            import uuid
            u = uuid.UUID(s)
            return GUID(u.time_low, u.time_mid, u.time_hi_version,
                        (ctypes.c_ubyte * 8)(*u.bytes[8:]))

        CLSID_MMDeviceEnumerator = _make_guid("{BCDE0395-E52F-467C-8E3D-C4579291692E}")
        IID_IMMDeviceEnumerator = _make_guid("{A95664D2-9614-4F35-A746-DE8DB63617E6}")
        IID_IAudioMeterInformation = _make_guid("{C02216F6-8C67-4B5B-9D00-D008E73E0064}")

        eRender = 0
        eMultimedia = 1

        def _vtbl(p, idx):
            """Call COM vtable method by index."""
            vt = ctypes.cast(
                ctypes.cast(p, POINTER(c_void_p))[0],
                POINTER(c_void_p)
            )
            fn_type = ctypes.CFUNCTYPE(ctypes.HRESULT, c_void_p)
            return vt[idx]

        def _release(p):
            """Call IUnknown::Release (vtable index 2)."""
            fn = ctypes.cast(
                ctypes.cast(
                    ctypes.cast(p, POINTER(c_void_p))[0],
                    POINTER(c_void_p)
                )[2],
                ctypes.CFUNCTYPE(ctypes.c_ulong, c_void_p)
            )
            fn(p)

        # Initialize COM (Qt may have already done this)
        hr = ole32.CoInitializeEx(None, COINIT_APARTMENTTHREADED)
        need_uninit = (hr == 0)  # S_OK means we initialized it
        if hr not in (0, 1) and (hr & 0xFFFFFFFF) != RPC_E_CHANGED_MODE:
            return True  # COM init failed, fall back to pausing

        try:
            # Create MMDeviceEnumerator
            enumerator = c_void_p()
            hr = ole32.CoCreateInstance(
                byref(CLSID_MMDeviceEnumerator), None, CLSCTX_ALL,
                byref(IID_IMMDeviceEnumerator), byref(enumerator)
            )
            if hr != 0:
                return True

            try:
                # GetDefaultAudioEndpoint (vtable index 4)
                device = c_void_p()
                get_default = ctypes.cast(
                    ctypes.cast(
                        ctypes.cast(enumerator, POINTER(c_void_p))[0],
                        POINTER(c_void_p)
                    )[4],
                    ctypes.CFUNCTYPE(ctypes.HRESULT, c_void_p,
                                     ctypes.c_uint, ctypes.c_uint,
                                     POINTER(c_void_p))
                )
                hr = get_default(enumerator, eRender, eMultimedia, byref(device))
                if hr != 0:
                    return True

                try:
                    # Activate IAudioMeterInformation (vtable index 3)
                    meter = c_void_p()
                    activate = ctypes.cast(
                        ctypes.cast(
                            ctypes.cast(device, POINTER(c_void_p))[0],
                            POINTER(c_void_p)
                        )[3],
                        ctypes.CFUNCTYPE(ctypes.HRESULT, c_void_p,
                                         POINTER(GUID), ctypes.c_uint,
                                         c_void_p, POINTER(c_void_p))
                    )
                    hr = activate(device, byref(IID_IAudioMeterInformation),
                                  CLSCTX_ALL, None, byref(meter))
                    if hr != 0:
                        return True

                    try:
                        # GetPeakValue (vtable index 3)
                        peak = c_float()
                        get_peak = ctypes.cast(
                            ctypes.cast(
                                ctypes.cast(meter, POINTER(c_void_p))[0],
                                POINTER(c_void_p)
                            )[3],
                            ctypes.CFUNCTYPE(ctypes.HRESULT, c_void_p,
                                             POINTER(c_float))
                        )
                        hr = get_peak(meter, byref(peak))
                        if hr != 0:
                            return True

                        is_playing = peak.value > 0.001
                        logger.debug(f"Audio peak level: {peak.value:.6f}, playing: {is_playing}")
                        return is_playing

                    finally:
                        _release(meter)
                finally:
                    _release(device)
            finally:
                _release(enumerator)
        finally:
            if need_uninit:
                ole32.CoUninitialize()

    except Exception as e:
        logger.debug(f"Windows audio detection failed, assuming playing: {e}")
        return True


def _is_audio_playing_macos():
    """macOS: Query CoreAudio for whether the default output device is running."""
    try:
        import ctypes
        import ctypes.util

        ca_path = ctypes.util.find_library("CoreAudio")
        if not ca_path:
            return True
        ca = ctypes.cdll.LoadLibrary(ca_path)

        # kAudioObjectSystemObject = 1
        # kAudioHardwarePropertyDefaultOutputDevice selector = 'dOut' = 0x644F7574
        # kAudioObjectPropertyScopeGlobal = 'glob' = 0x676C6F62
        # kAudioObjectPropertyElementMain = 0
        # kAudioDevicePropertyDeviceIsRunningSomewhere = 'gone' = 0x676F6E65

        class AudioObjectPropertyAddress(ctypes.Structure):
            _fields_ = [
                ("mSelector", ctypes.c_uint32),
                ("mScope", ctypes.c_uint32),
                ("mElement", ctypes.c_uint32),
            ]

        # Get default output device
        prop = AudioObjectPropertyAddress(0x644F7574, 0x676C6F62, 0)
        device_id = ctypes.c_uint32()
        size = ctypes.c_uint32(ctypes.sizeof(device_id))

        hr = ca.AudioObjectGetPropertyData(
            ctypes.c_uint32(1),  # kAudioObjectSystemObject
            ctypes.byref(prop),
            ctypes.c_uint32(0), None,
            ctypes.byref(size), ctypes.byref(device_id)
        )
        if hr != 0:
            return True

        # Query if device is running somewhere
        prop.mSelector = 0x676F6E65  # kAudioDevicePropertyDeviceIsRunningSomewhere
        is_running = ctypes.c_uint32()
        size = ctypes.c_uint32(ctypes.sizeof(is_running))

        hr = ca.AudioObjectGetPropertyData(
            device_id, ctypes.byref(prop),
            ctypes.c_uint32(0), None,
            ctypes.byref(size), ctypes.byref(is_running)
        )
        if hr != 0:
            return True

        playing = is_running.value != 0
        logger.debug(f"macOS audio device running: {playing}")
        return playing

    except Exception as e:
        logger.debug(f"macOS audio detection failed, assuming playing: {e}")
        return True


def _is_audio_playing_linux():
    """Linux: Use playerctl to check if any media player is currently playing."""
    try:
        import subprocess
        result = subprocess.run(
            ["playerctl", "status"],
            capture_output=True, text=True, timeout=2
        )
        playing = result.stdout.strip() == "Playing"
        logger.debug(f"playerctl status: {result.stdout.strip()}, playing: {playing}")
        return playing
    except FileNotFoundError:
        logger.debug("playerctl not installed, assuming playing")
        return True
    except Exception as e:
        logger.debug(f"Linux audio detection failed, assuming playing: {e}")
        return True


def _send_media_play_pause():
    """Send the media play/pause key using the platform-native API."""
    if sys.platform == "win32":
        import ctypes
        VK_MEDIA_PLAY_PAUSE = 0xB3
        KEYEVENTF_EXTENDEDKEY = 0x0001
        KEYEVENTF_KEYUP = 0x0002
        ctypes.windll.user32.keybd_event(VK_MEDIA_PLAY_PAUSE, 0, KEYEVENTF_EXTENDEDKEY, 0)
        ctypes.windll.user32.keybd_event(VK_MEDIA_PLAY_PAUSE, 0, KEYEVENTF_EXTENDEDKEY | KEYEVENTF_KEYUP, 0)
    else:
        from pynput.keyboard import Controller, Key
        Controller().tap(Key.media_play_pause)


class MediaController:
    """Sends media play/pause key to pause and resume background media."""

    def __init__(self):
        self._did_pause = False

    def pause_if_playing(self):
        """Send media play/pause key only if audio is actually playing."""
        try:
            if not _is_audio_playing():
                logger.debug("No audio playing, skipping media pause")
                self._did_pause = False
                return
            _send_media_play_pause()
            self._did_pause = True
        except Exception:
            self._did_pause = False

    def resume_if_paused(self):
        """Send media play/pause key only if we previously paused."""
        if not self._did_pause:
            return
        try:
            _send_media_play_pause()
        except Exception:
            pass
        finally:
            self._did_pause = False

    def cancel(self):
        """Reset state without sending any key."""
        self._did_pause = False
