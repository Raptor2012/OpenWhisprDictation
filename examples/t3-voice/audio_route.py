"""Follow Windows audio endpoints so plugging in headphones, Bluetooth or a USB mic just works.

PortAudio snapshots the device list and the system defaults once, at initialisation. A stream opened on
"the default" keeps playing to whatever was default at that moment, and new devices never appear. Windows
tells us (IMMNotificationClient) when a device arrives, leaves or becomes the default; once those
notifications go quiet we compare the endpoint signature and call `on_change` if it really changed, so the
caller can re-initialise PortAudio and reopen its streams. Idle cost is zero: no polling.
"""
import ctypes
from ctypes import Structure, c_int
from ctypes.wintypes import DWORD, LPCWSTR
import threading

from audio_duck import _com, _take_string

SETTLE = 0.4      # Bluetooth arrives in steps (endpoint added, then made default); act once it is quiet
FALLBACK_POLL = 2.0   # only if Windows refuses the notification callback


def endpoint_signature(enumerator):
    """(default render id, default capture id, active render ids, active capture ids). ~30 ms of RPC."""
    def default(flow):
        try:
            return _take_string(enumerator.GetDefaultAudioEndpoint(flow, 0).GetId())   # eConsole
        except Exception:
            return ''                       # no device of this kind at all

    def active(flow):
        devices = enumerator.EnumAudioEndpoints(flow, 1)                             # DEVICE_STATE_ACTIVE
        return tuple(sorted(_take_string(devices.Item(i).GetId()) for i in range(devices.GetCount())))

    return default(0), default(1), active(0), active(1)


def settle(wake, stop, quiet):
    """After a notification, wait until none has arrived for `quiet` seconds. False if stopping."""
    while not stop.is_set():
        wake.clear()
        if not wake.wait(quiet):
            return True
    return False


def _client_class():
    from comtypes import COMMETHOD, COMObject, GUID, HRESULT, IUnknown

    class PROPERTYKEY(Structure):
        _fields_ = [('fmtid', GUID), ('pid', DWORD)]

    class IMMNotificationClient(IUnknown):
        _iid_ = GUID('{7991EEC9-7E89-4D85-8390-6C703CEC60C0}')
        _methods_ = [
            COMMETHOD([], HRESULT, 'OnDeviceStateChanged', (['in'], LPCWSTR, 'id'), (['in'], DWORD, 'state')),
            COMMETHOD([], HRESULT, 'OnDeviceAdded', (['in'], LPCWSTR, 'id')),
            COMMETHOD([], HRESULT, 'OnDeviceRemoved', (['in'], LPCWSTR, 'id')),
            COMMETHOD([], HRESULT, 'OnDefaultDeviceChanged', (['in'], c_int, 'flow'), (['in'], c_int, 'role'),
                      (['in'], LPCWSTR, 'id')),
            COMMETHOD([], HRESULT, 'OnPropertyValueChanged', (['in'], LPCWSTR, 'id'), (['in'], PROPERTYKEY, 'key')),
        ]

    class Client(COMObject):
        """Called on Windows' own thread: only flag the change; the watch thread does the work."""
        _com_interfaces_ = [IMMNotificationClient]

        def __init__(self, wake):
            super().__init__()
            self.wake = wake

        def OnDeviceStateChanged(self, id, state):
            self.wake.set()
            return 0

        def OnDeviceAdded(self, id):
            self.wake.set()
            return 0

        def OnDeviceRemoved(self, id):
            self.wake.set()
            return 0

        def OnDefaultDeviceChanged(self, flow, role, id):
            self.wake.set()
            return 0

        def OnPropertyValueChanged(self, id, key):     # names, formats, icons: nothing to reroute
            return 0

    return IMMNotificationClient, Client


class EndpointWatch:
    def __init__(self, on_change, quiet=SETTLE):
        self.on_change = on_change
        self.quiet = quiet
        self.error = None
        self.changes = 0
        self.notified = False
        self._wake = threading.Event()
        self._stop = threading.Event()

    def start(self):
        threading.Thread(target=self._run, daemon=True, name='endpoint-watch').start()
        return self

    def stop(self):
        self._stop.set()
        self._wake.set()

    def check(self, signature, last):
        """Settle, then fire on_change if the signature moved. Returns the signature now in force."""
        if not settle(self._wake, self._stop, self.quiet):
            return last
        current = signature()
        if current != last:
            self.changes += 1
            try:
                self.on_change()
            except Exception as exc:
                self.error = type(exc).__name__
        return current

    def _run(self):
        import comtypes
        comtypes.CoInitialize()
        registered = client = None
        try:
            c = _com()
            enumerator = comtypes.CoCreateInstance(c['GUID']('{BCDE0395-E52F-467C-8E3D-C4579291692E}'),
                                                   c['IMMDeviceEnumerator'], comtypes.CLSCTX_INPROC_SERVER)
            signature = lambda: endpoint_signature(enumerator)
            last = signature()
            try:
                interface, Client = _client_class()
                client = Client(self._wake)
                registered = ctypes.cast(client.QueryInterface(interface), ctypes.c_void_p)
                enumerator.RegisterEndpointNotificationCallback(registered)
                self.notified = True
            except Exception as exc:
                self.error, registered = type(exc).__name__, None
            while not self._stop.is_set():
                if not self._wake.wait(None if self.notified else FALLBACK_POLL) and self.notified:
                    continue
                if self._stop.is_set():
                    break
                try:
                    last = self.check(signature, last)
                except Exception as exc:        # a device vanishing mid-enumeration; the next event retries
                    self.error = type(exc).__name__
            if registered is not None:
                enumerator.UnregisterEndpointNotificationCallback(registered)
        except Exception as exc:
            self.error = type(exc).__name__
        finally:
            comtypes.CoUninitialize()
