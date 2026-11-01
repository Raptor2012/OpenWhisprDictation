"""Duck other apps' audio while Maeve speaks or the user dictates.

Uses WASAPI per-app session volumes (the Volume Mixer sliders) through comtypes. It never touches the
master volume or the default devices. Our own process is never ducked. Original levels are journaled
so a crash mid-duck is undone on the next start.
"""
import ctypes
import json
import os
import threading
import time
from ctypes import POINTER, byref, c_float, c_int, c_uint, c_void_p
from ctypes.wintypes import BOOL, DWORD, LPWSTR
from pathlib import Path

DUCK_LEVEL = 0.10          # "reduce by 90%"
FADE_DOWN, FADE_UP = 0.15, 0.6   # seconds for a full 1.0 <-> DUCK_LEVEL ramp


class DuckBook:
    """Pure bookkeeping (no COM): remembers each ducked session's own level and says what to set."""

    def __init__(self):
        self.original, self.applied = {}, {}

    def plan(self, sessions, factor):
        """sessions: {key: current volume}. factor: 1.0 = untouched .. DUCK_LEVEL = fully ducked.
        Returns {key: volume to set}."""
        changes = {}
        for key, vol in sessions.items():
            if key not in self.original:
                if factor >= 1:
                    continue
                self.original[key] = vol
            elif abs(vol - self.applied.get(key, vol)) > 0.02:
                # The user moved this slider while ducked: that becomes the level to restore.
                self.original[key] = min(1.0, vol / max(factor, 1e-3)) if factor < 1 else vol
            target = self.original[key] * min(1.0, factor)
            # Mid-fade steps skip tiny changes; the final restore always writes the exact original.
            if abs(target - vol) > (1e-6 if factor >= 1 else 1e-3):
                changes[key] = target
            self.applied[key] = target
        for gone in set(self.original) - set(sessions):
            self.original.pop(gone, None)
            self.applied.pop(gone, None)
        if factor >= 1:
            self.original.clear()
            self.applied.clear()
        return changes


def step_factor(factor, want, dt):
    """Linear fade between 1.0 and DUCK_LEVEL: quick down so speech is clear at once, gentle up."""
    span = 1.0 - DUCK_LEVEL
    if want:
        return max(DUCK_LEVEL, factor - span * dt / FADE_DOWN)
    return min(1.0, factor + span * dt / FADE_UP)


# ----- minimal WASAPI session interfaces -----
def _com():
    from comtypes import COMMETHOD, GUID, HRESULT, IUnknown

    class ISimpleAudioVolume(IUnknown):
        _iid_ = GUID('{87CE5498-68D6-44E5-9215-6DA47EF883D8}')
        _methods_ = [
            COMMETHOD([], HRESULT, 'SetMasterVolume', (['in'], c_float, 'level'), (['in'], POINTER(GUID), 'ctx')),
            COMMETHOD([], HRESULT, 'GetMasterVolume', (['out'], POINTER(c_float), 'level')),
            COMMETHOD([], HRESULT, 'SetMute', (['in'], BOOL, 'mute'), (['in'], POINTER(GUID), 'ctx')),
            COMMETHOD([], HRESULT, 'GetMute', (['out'], POINTER(BOOL), 'mute')),
        ]

    class IAudioSessionControl(IUnknown):
        _iid_ = GUID('{F4B1A599-7266-4319-A8CA-E70ACB11E8CD}')
        _methods_ = [
            COMMETHOD([], HRESULT, 'GetState', (['out'], POINTER(c_int), 'state')),
            COMMETHOD([], HRESULT, 'GetDisplayName', (['out'], POINTER(c_void_p), 'name')),
            COMMETHOD([], HRESULT, 'SetDisplayName', (['in'], LPWSTR, 'name'), (['in'], POINTER(GUID), 'ctx')),
            COMMETHOD([], HRESULT, 'GetIconPath', (['out'], POINTER(c_void_p), 'path')),
            COMMETHOD([], HRESULT, 'SetIconPath', (['in'], LPWSTR, 'path'), (['in'], POINTER(GUID), 'ctx')),
            COMMETHOD([], HRESULT, 'GetGroupingParam', (['out'], POINTER(GUID), 'param')),
            COMMETHOD([], HRESULT, 'SetGroupingParam', (['in'], POINTER(GUID), 'param'), (['in'], POINTER(GUID), 'ctx')),
            COMMETHOD([], HRESULT, 'RegisterAudioSessionNotification', (['in'], c_void_p, 'client')),
            COMMETHOD([], HRESULT, 'UnregisterAudioSessionNotification', (['in'], c_void_p, 'client')),
        ]

    class IAudioSessionControl2(IAudioSessionControl):
        _iid_ = GUID('{BFB7FF88-7239-4FC9-8FA2-07C950BE9C6D}')
        _methods_ = [
            COMMETHOD([], HRESULT, 'GetSessionIdentifier', (['out'], POINTER(c_void_p), 'id')),
            COMMETHOD([], HRESULT, 'GetSessionInstanceIdentifier', (['out'], POINTER(c_void_p), 'id')),
            COMMETHOD([], HRESULT, 'GetProcessId', (['out'], POINTER(DWORD), 'pid')),
            COMMETHOD([], HRESULT, 'IsSystemSoundsSession'),
            COMMETHOD([], HRESULT, 'SetDuckingPreference', (['in'], BOOL, 'optOut')),
        ]

    class IAudioSessionEnumerator(IUnknown):
        _iid_ = GUID('{E2F5BB11-0570-40CA-ACDD-3AA01277DEE8}')
        _methods_ = [
            COMMETHOD([], HRESULT, 'GetCount', (['out'], POINTER(c_int), 'count')),
            COMMETHOD([], HRESULT, 'GetSession', (['in'], c_int, 'index'),
                      (['out'], POINTER(POINTER(IAudioSessionControl)), 'session')),
        ]

    class IAudioSessionManager2(IUnknown):
        _iid_ = GUID('{77AA99A0-1BD6-484F-8BC7-2C654C9A9B6F}')
        _methods_ = [
            COMMETHOD([], HRESULT, 'GetAudioSessionControl', (['in'], POINTER(GUID), 'guid'), (['in'], DWORD, 'flags'),
                      (['out'], POINTER(POINTER(IAudioSessionControl)), 'control')),
            COMMETHOD([], HRESULT, 'GetSimpleAudioVolume', (['in'], POINTER(GUID), 'guid'), (['in'], DWORD, 'flags'),
                      (['out'], POINTER(POINTER(ISimpleAudioVolume)), 'volume')),
            COMMETHOD([], HRESULT, 'GetSessionEnumerator', (['out'], POINTER(POINTER(IAudioSessionEnumerator)), 'sessions')),
            COMMETHOD([], HRESULT, 'RegisterSessionNotification', (['in'], c_void_p, 'client')),
            COMMETHOD([], HRESULT, 'UnregisterSessionNotification', (['in'], c_void_p, 'client')),
            COMMETHOD([], HRESULT, 'RegisterDuckNotification', (['in'], LPWSTR, 'id'), (['in'], c_void_p, 'client')),
            COMMETHOD([], HRESULT, 'UnregisterDuckNotification', (['in'], c_void_p, 'client')),
        ]

    class IMMDevice(IUnknown):
        _iid_ = GUID('{D666063F-1587-4E43-81F1-B948E807363F}')
        _methods_ = [
            COMMETHOD([], HRESULT, 'Activate', (['in'], POINTER(GUID), 'iid'), (['in'], DWORD, 'ctx'),
                      (['in'], c_void_p, 'params'), (['out'], POINTER(POINTER(IUnknown)), 'iface')),
            COMMETHOD([], HRESULT, 'OpenPropertyStore', (['in'], DWORD, 'access'), (['out'], POINTER(c_void_p), 'store')),
            COMMETHOD([], HRESULT, 'GetId', (['out'], POINTER(c_void_p), 'id')),
            COMMETHOD([], HRESULT, 'GetState', (['out'], POINTER(DWORD), 'state')),
        ]

    class IMMDeviceCollection(IUnknown):
        _iid_ = GUID('{0BD7A1BE-7A1A-44DB-8397-CC5392387B5E}')
        _methods_ = [
            COMMETHOD([], HRESULT, 'GetCount', (['out'], POINTER(c_uint), 'count')),
            COMMETHOD([], HRESULT, 'Item', (['in'], c_uint, 'index'), (['out'], POINTER(POINTER(IMMDevice)), 'device')),
        ]

    class IMMDeviceEnumerator(IUnknown):
        _iid_ = GUID('{A95664D2-9614-4F35-A746-DE8DB63617E6}')
        _methods_ = [
            COMMETHOD([], HRESULT, 'EnumAudioEndpoints', (['in'], c_int, 'flow'), (['in'], DWORD, 'mask'),
                      (['out'], POINTER(POINTER(IMMDeviceCollection)), 'devices')),
            COMMETHOD([], HRESULT, 'GetDefaultAudioEndpoint', (['in'], c_int, 'flow'), (['in'], c_int, 'role'),
                      (['out'], POINTER(POINTER(IMMDevice)), 'device')),
            COMMETHOD([], HRESULT, 'GetDevice', (['in'], LPWSTR, 'id'), (['out'], POINTER(POINTER(IMMDevice)), 'device')),
            COMMETHOD([], HRESULT, 'RegisterEndpointNotificationCallback', (['in'], c_void_p, 'client')),
            COMMETHOD([], HRESULT, 'UnregisterEndpointNotificationCallback', (['in'], c_void_p, 'client')),
        ]

    return dict(GUID=GUID, ISimpleAudioVolume=ISimpleAudioVolume, IAudioSessionControl2=IAudioSessionControl2,
                IAudioSessionManager2=IAudioSessionManager2, IMMDeviceEnumerator=IMMDeviceEnumerator)


def _take_string(ptr):
    """WASAPI returns CoTaskMem strings; copy and free them so polling does not leak."""
    if not ptr:
        return ''
    try:
        return ctypes.wstring_at(ptr)
    finally:
        ctypes.windll.ole32.CoTaskMemFree(ctypes.c_void_p(ptr))


class SessionMixer:
    """Live audio sessions on every active render endpoint, keyed by session instance id. COM-thread bound."""

    def __init__(self, exclude_pids=(), only_pids=None):
        import comtypes
        from comtypes import CLSCTX_ALL
        self.c = _com()
        self.clsctx = CLSCTX_ALL
        self.exclude = set(exclude_pids)
        self.only = set(only_pids) if only_pids is not None else None
        self.enumerator = comtypes.CoCreateInstance(self.c['GUID']('{BCDE0395-E52F-467C-8E3D-C4579291692E}'),
                                                    self.c['IMMDeviceEnumerator'], comtypes.CLSCTX_INPROC_SERVER)
        self.volumes = {}

    def scan(self):
        """Returns {key: volume} and keeps the ISimpleAudioVolume handles for set()."""
        found = {}
        devices = self.enumerator.EnumAudioEndpoints(0, 1)          # eRender, DEVICE_STATE_ACTIVE
        for i in range(devices.GetCount()):
            try:
                unknown = devices.Item(i).Activate(byref(self.c['IAudioSessionManager2']._iid_), self.clsctx, None)
                manager = unknown.QueryInterface(self.c['IAudioSessionManager2'])
                sessions = manager.GetSessionEnumerator()
                for j in range(sessions.GetCount()):
                    try:
                        control = sessions.GetSession(j)
                        if control.GetState() == 2:                  # AudioSessionStateExpired
                            continue
                        control2 = control.QueryInterface(self.c['IAudioSessionControl2'])
                        pid = control2.GetProcessId()
                        if pid in self.exclude or (self.only is not None and pid not in self.only):
                            continue
                        key = _take_string(control2.GetSessionInstanceIdentifier())
                        volume = control.QueryInterface(self.c['ISimpleAudioVolume'])
                        found[key] = (volume, float(volume.GetMasterVolume()))
                    except Exception:
                        continue
            except Exception:
                continue
        self.volumes = {key: handle for key, (handle, _) in found.items()}
        return {key: level for key, (_, level) in found.items()}

    def set(self, key, level):
        handle = self.volumes.get(key)
        if handle is not None:
            try:
                handle.SetMasterVolume(max(0.0, min(1.0, level)), None)
            except Exception:
                pass


class AudioDucker:
    """Engine sets .want; a private COM thread fades every other session to 10% and back."""

    def __init__(self, journal, exclude_pids=None, only_pids=None, mixer_factory=SessionMixer):
        self.journal = Path(journal)
        self.exclude = set(exclude_pids if exclude_pids is not None else (os.getpid(),))
        self.only = only_pids
        self.mixer_factory = mixer_factory
        self.want = False
        self.factor = 1.0
        self.ducked = 0
        self.error = ''
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        self._thread = threading.Thread(target=self._run, name='audio-duck', daemon=True)
        self._thread.start()
        return self

    def stop(self, timeout=2.0):
        self.want = False
        self._stop.set()
        if self._thread:
            self._thread.join(timeout)

    # journal: the original levels of currently ducked sessions, so a crash can be undone
    def _write_journal(self, book):
        """Only when the remembered levels change, and atomically, so a crash never leaves half a file."""
        snapshot = dict(book.original)
        if snapshot == getattr(self, '_journaled', None):
            return
        try:
            if snapshot:
                temp = self.journal.with_suffix('.tmp')
                temp.write_text(json.dumps(snapshot), encoding='utf-8')
                os.replace(temp, self.journal)
            elif self.journal.exists():
                self.journal.unlink()
            self._journaled = snapshot
        except OSError:
            pass

    def _recover(self, mixer):
        try:
            saved = json.loads(self.journal.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return
        current = mixer.scan()
        for key, level in saved.items():
            if key in current and isinstance(level, (int, float)) and current[key] < level:
                mixer.set(key, float(level))
        try:
            self.journal.unlink()
        except OSError:
            pass

    def _run(self):
        import comtypes
        comtypes.CoInitialize()
        try:
            mixer = self.mixer_factory(exclude_pids=self.exclude, only_pids=self.only)
            self._recover(mixer)
            book, last, last_scan, sessions = DuckBook(), time.monotonic(), 0.0, {}
            while not self._stop.is_set() or self.factor < 1.0:
                now = time.monotonic()
                dt, last = min(0.1, now - last), now
                want = self.want and not self._stop.is_set()
                if self.factor >= 1.0 and not want:
                    time.sleep(0.03)                      # idle: no COM traffic at all
                    continue
                target_before = self.factor
                self.factor = step_factor(self.factor, want, dt)
                ramping = self.factor != target_before
                if ramping or now - last_scan > 0.25:     # pick up apps that start playing mid-duck
                    sessions, last_scan = mixer.scan(), now
                for key, level in book.plan(sessions, self.factor).items():
                    mixer.set(key, level)
                    sessions[key] = level
                self.ducked = len(book.original)
                self._write_journal(book)
                time.sleep(0.015 if ramping else 0.05)
            self.ducked = 0
        except Exception as exc:
            self.error = type(exc).__name__
        finally:
            comtypes.CoUninitialize()
