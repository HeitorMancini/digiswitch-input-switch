import sys
import tempfile

from PySide6.QtCore import QLockFile
from PySide6.QtWidgets import QApplication

from . import ui
from .config import Config


def main():
    app = QApplication(sys.argv)
    lock = QLockFile(tempfile.gettempdir() + "\\InputSwitch.lock")
    lock.setStaleLockTime(0)
    if not lock.tryLock(100):
        return 0
    app.setStyle("Fusion")
    app.setStyleSheet(ui.QSS)
    ui.init_bridge()
    win = ui.MainWindow(Config())
    watcher = ui.DisplayWatcher(win.schedule_refresh)
    app.installNativeEventFilter(watcher)
    win.show()
    code = app.exec()
    lock.unlock()
    return code
