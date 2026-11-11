import sys
import winreg
from pathlib import Path

_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_NAME = "InputSwitch"


def _command():
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    pyw = Path(sys.executable).with_name("pythonw.exe")
    script = Path(sys.argv[0]).resolve()
    return f'"{pyw}" "{script}"'


def is_enabled():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _KEY) as k:
            winreg.QueryValueEx(k, _NAME)
            return True
    except OSError:
        return False


def set_enabled(enabled):
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _KEY, 0, winreg.KEY_SET_VALUE) as k:
        if enabled:
            winreg.SetValueEx(k, _NAME, 0, winreg.REG_SZ, _command())
        else:
            try:
                winreg.DeleteValue(k, _NAME)
            except FileNotFoundError:
                pass
