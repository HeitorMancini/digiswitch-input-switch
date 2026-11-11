"""
Troca a entrada do monitor via DDC/CI (Windows). Testado em teoria com Samsung Odyssey G5.

Uso:
  python input_switch.py list          -> lista monitores e entrada atual
  python input_switch.py hdmi          -> muda para HDMI
  python input_switch.py dp            -> muda para DisplayPort
  python input_switch.py toggle        -> alterna entre DP e HDMI
  python input_switch.py set 0x12      -> envia um codigo VCP 0x60 qualquer (para testar)

Opcoes: --monitor N (indice do monitor, padrao: todos)
"""
import ctypes
import sys
from ctypes import wintypes

# Codigos padrao MCCS para o VCP 0x60 (Input Source). Samsung costuma usar estes.
CODES = {"dp": 0x0F, "hdmi": 0x11}
VCP_INPUT = 0x60

user32 = ctypes.windll.user32
dxva2 = ctypes.windll.dxva2


class PHYSICAL_MONITOR(ctypes.Structure):
    _pack_ = 1
    _fields_ = [("hPhysicalMonitor", wintypes.HANDLE),
                ("szPhysicalMonitorDescription", wintypes.WCHAR * 128)]


def get_monitors():
    handles = []
    proc_t = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC,
                                ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)

    def cb(hmon, hdc, rect, data):
        n = wintypes.DWORD()
        if dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR(hmon, ctypes.byref(n)) and n.value:
            arr = (PHYSICAL_MONITOR * n.value)()
            if dxva2.GetPhysicalMonitorsFromHMONITOR(hmon, n.value, arr):
                handles.extend(arr)
        return True

    user32.EnumDisplayMonitors(None, None, proc_t(cb), 0)
    return handles


def get_input(h):
    cur, mx = wintypes.DWORD(), wintypes.DWORD()
    ok = dxva2.GetVCPFeatureAndVCPFeatureReply(h, VCP_INPUT, None, ctypes.byref(cur), ctypes.byref(mx))
    return cur.value & 0xFF if ok else None


def set_input(h, value):
    return bool(dxva2.SetVCPFeature(h, VCP_INPUT, value))


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return
    only = None
    if "--monitor" in args:
        i = args.index("--monitor")
        only = int(args[i + 1])
        del args[i:i + 2]
    cmd = args[0].lower()

    mons = get_monitors()
    if not mons:
        print("Nenhum monitor com DDC/CI encontrado. Verifique se DDC/CI esta ativo no menu do monitor.")
        return

    for idx, m in enumerate(mons):
        if only is not None and idx != only:
            continue
        h = m.hPhysicalMonitor
        cur = get_input(h)
        cur_txt = f"0x{cur:02X}" if cur is not None else "desconhecida"
        print(f"[{idx}] {m.szPhysicalMonitorDescription} | entrada atual: {cur_txt}")

        if cmd == "list":
            continue
        if cmd in CODES:
            target = CODES[cmd]
        elif cmd == "toggle":
            target = CODES["hdmi"] if cur == CODES["dp"] else CODES["dp"]
        elif cmd == "set":
            target = int(args[1], 0)
        else:
            print("Comando invalido.")
            break
        print(f"    enviando 0x{target:02X} ->", "ok" if set_input(h, target) else "FALHOU")

    dxva2.DestroyPhysicalMonitors(len(mons), (PHYSICAL_MONITOR * len(mons))(*mons))


if __name__ == "__main__":
    main()
