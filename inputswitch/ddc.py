"""Acesso DDC/CI (VCP 0x60 - entrada) via dxva2. Sem estado: handles abertos por chamada."""
import ctypes
import re
import threading
import time
from contextlib import contextmanager
from ctypes import wintypes

VCP_INPUT = 0x60

INPUT_NAMES = {
    0x01: "VGA 1", 0x02: "VGA 2", 0x03: "DVI 1", 0x04: "DVI 2",
    0x0F: "DisplayPort 1", 0x10: "DisplayPort 2",
    0x11: "HDMI 1", 0x12: "HDMI 2", 0x13: "HDMI 3", 0x14: "HDMI 4",
    0x1B: "USB-C",
}
DEFAULT_CODES = [0x0F, 0x10, 0x11, 0x12, 0x1B]


def input_name(code):
    return INPUT_NAMES.get(code, f"Entrada 0x{code:02X}")


def input_kind(code):
    if code in (0x0F, 0x10):
        return "dp"
    if code in (0x11, 0x12, 0x13, 0x14):
        return "hdmi"
    if code == 0x1B:
        return "usbc"
    return "vga"


dxva2 = ctypes.WinDLL("dxva2")
user32 = ctypes.WinDLL("user32")
_lock = threading.RLock()


class PHYSICAL_MONITOR(ctypes.Structure):
    _pack_ = 1
    _fields_ = [("handle", wintypes.HANDLE), ("desc", wintypes.WCHAR * 128)]


class MONITORINFOEXW(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD),
                ("szDevice", wintypes.WCHAR * 32)]


class DISPLAY_DEVICEW(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("DeviceName", wintypes.WCHAR * 32),
                ("DeviceString", wintypes.WCHAR * 128), ("StateFlags", wintypes.DWORD),
                ("DeviceID", wintypes.WCHAR * 128), ("DeviceKey", wintypes.WCHAR * 128)]


_ENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC,
                               ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)
user32.EnumDisplayMonitors.argtypes = [wintypes.HDC, ctypes.c_void_p, _ENUMPROC, wintypes.LPARAM]
user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(MONITORINFOEXW)]
user32.EnumDisplayDevicesW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD,
                                       ctypes.POINTER(DISPLAY_DEVICEW), wintypes.DWORD]
dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR.argtypes = [wintypes.HMONITOR, ctypes.POINTER(wintypes.DWORD)]
dxva2.GetPhysicalMonitorsFromHMONITOR.argtypes = [wintypes.HMONITOR, wintypes.DWORD, ctypes.POINTER(PHYSICAL_MONITOR)]
dxva2.DestroyPhysicalMonitors.argtypes = [wintypes.DWORD, ctypes.POINTER(PHYSICAL_MONITOR)]
dxva2.GetVCPFeatureAndVCPFeatureReply.argtypes = [
    wintypes.HANDLE, wintypes.BYTE, ctypes.c_void_p,
    ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD)]
dxva2.SetVCPFeature.argtypes = [wintypes.HANDLE, wintypes.BYTE, wintypes.DWORD]
dxva2.GetCapabilitiesStringLength.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
dxva2.CapabilitiesRequestAndCapabilitiesReply.argtypes = [wintypes.HANDLE, ctypes.c_char_p, wintypes.DWORD]


def _hmonitors():
    found = []

    def cb(hmon, hdc, rect, lp):
        found.append(hmon)
        return True

    user32.EnumDisplayMonitors(None, None, _ENUMPROC(cb), 0)
    return found


def _interface_id(hmon):
    """ID estavel: caminho de interface do monitor (nao depende de ordem/indice)."""
    info = MONITORINFOEXW()
    info.cbSize = ctypes.sizeof(info)
    if not user32.GetMonitorInfoW(hmon, ctypes.byref(info)):
        return None, (0, 0)
    dd = DISPLAY_DEVICEW()
    dd.cb = ctypes.sizeof(dd)
    ident = info.szDevice
    if user32.EnumDisplayDevicesW(info.szDevice, 0, ctypes.byref(dd), 1) and dd.DeviceID:
        ident = dd.DeviceID
    return ident, (info.rcMonitor.left, info.rcMonitor.top)


def _physical(hmon):
    n = wintypes.DWORD()
    if not dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR(hmon, ctypes.byref(n)) or n.value == 0:
        return None
    arr = (PHYSICAL_MONITOR * n.value)()
    if not dxva2.GetPhysicalMonitorsFromHMONITOR(hmon, n.value, arr):
        return None
    return arr


def list_monitors():
    """[{id, desc}] ordenados por posicao na area de trabalho."""
    with _lock:
        out = []
        for hmon in _hmonitors():
            base, pos = _interface_id(hmon)
            arr = _physical(hmon)
            if base is None or arr is None:
                continue
            try:
                for i, m in enumerate(arr):
                    mid = base if len(arr) == 1 else f"{base}#{i}"
                    out.append((pos, {"id": mid, "desc": m.desc}))
            finally:
                dxva2.DestroyPhysicalMonitors(len(arr), arr)
        out.sort(key=lambda t: t[0])
        return [d for _, d in out]


@contextmanager
def open_monitor(mid):
    with _lock:
        for hmon in _hmonitors():
            base, _ = _interface_id(hmon)
            arr = _physical(hmon)
            if base is None or arr is None:
                continue
            try:
                for i, m in enumerate(arr):
                    if (base if len(arr) == 1 else f"{base}#{i}") == mid:
                        yield m.handle
                        return
            finally:
                dxva2.DestroyPhysicalMonitors(len(arr), arr)
        raise LookupError("Monitor nao encontrado")


# Samsung Odyssey (G5) tem DDC/CI instavel: falha esporadicamente, por isso ha novas tentativas.
RETRIES = 3
RETRY_DELAY = 0.25


def _read_input(h):
    cur, mx = wintypes.DWORD(), wintypes.DWORD()
    if dxva2.GetVCPFeatureAndVCPFeatureReply(h, VCP_INPUT, None, ctypes.byref(cur), ctypes.byref(mx)):
        return cur.value & 0xFF
    return None


def get_input(mid):
    with open_monitor(mid) as h:
        for attempt in range(RETRIES):
            val = _read_input(h)
            if val is not None:
                return val
            if attempt < RETRIES - 1:
                time.sleep(RETRY_DELAY)
    return None


def set_input(mid, code):
    with open_monitor(mid) as h:
        for attempt in range(RETRIES):
            if dxva2.SetVCPFeature(h, VCP_INPUT, code):
                return True
            # O monitor as vezes troca mas reporta erro: confere antes de tentar de novo.
            time.sleep(RETRY_DELAY)
            if _read_input(h) == code:
                return True
    return False


SAMSUNG_CODES = [0x0F, 0x11, 0x12]  # Odyssey G5: DP, HDMI 1, HDMI 2


def complete_inputs(mid, codes):
    """Samsung omite das capacidades as entradas sem sinal; garante as portas conhecidas do Odyssey."""
    codes = list(codes)
    if "#SAM" in mid.upper():
        codes += [c for c in SAMSUNG_CODES if c not in codes]
    return codes


def parse_inputs(caps):
    m = re.search(r"(?:^|[\s(])60\s*\(([^()]*)\)", caps)
    if not m:
        return []
    return [int(t, 16) for t in m.group(1).split() if re.fullmatch(r"[0-9A-Fa-f]{1,2}", t)]


def get_capabilities(mid):
    """Entradas suportadas (lista de codigos) ou None se o monitor nao informar."""
    with open_monitor(mid) as h:
        n = wintypes.DWORD()
        if not dxva2.GetCapabilitiesStringLength(h, ctypes.byref(n)) or n.value == 0:
            return None
        buf = ctypes.create_string_buffer(n.value)
        if not dxva2.CapabilitiesRequestAndCapabilitiesReply(h, buf, n.value):
            return None
        codes = parse_inputs(buf.value.decode("ascii", "ignore"))
        return codes or None
