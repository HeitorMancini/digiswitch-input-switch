import re
import threading
import time
import uuid
from ctypes import wintypes

from PySide6.QtCore import (QAbstractNativeEventFilter, QObject, QPointF, QSize, Qt,
                            QTimer, Signal)
from PySide6.QtGui import (QAction, QColor, QFont, QIcon, QImage, QPainter, QPainterPath,
                           QPen, QPixmap)
from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
                               QFrame, QGridLayout, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
                               QMainWindow, QMenu, QPushButton, QScrollArea, QToolButton,
                               QVBoxLayout, QWidget)

from . import autostart, ddc
from .config import ICON_DIR, Config

BG, CARD, BORDER = "#0d0f13", "#161920", "#262a33"
TEXT, MUTED, ACCENT = "#e7e9ee", "#8a909c", "#6d8dff"
ACCENT_SOFT, ACCENT_BG, ERR = "#b4c3ff", "#232c4d", "#f87171"
SURFACE, SURFACE_HI = "#1d2129", "#262b35"

QSS = f"""
* {{ font-family: 'Segoe UI Variable Text', 'Segoe UI'; color: {TEXT}; }}
QMainWindow, QDialog, QWidget#root {{ background: {BG}; }}
QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; border: none; }}
QFrame#card {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 16px; }}
QLabel#h1 {{ font-size: 20px; font-weight: 600; }}
QLabel#title {{ font-size: 15px; font-weight: 600; }}
QLabel#sub {{ color: {MUTED}; font-size: 11px; }}
QLabel#status {{ color: {MUTED}; font-size: 12px; }}
QLabel#status[state="ok"] {{ color: {ACCENT_SOFT}; }}
QLabel#status[state="error"] {{ color: {ERR}; }}
QLabel#empty {{ color: {MUTED}; font-size: 13px; }}
QToolButton#input {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 12px;
    padding: 8px 4px; font-size: 12px; color: {MUTED}; }}
QToolButton#input:hover {{ background: {SURFACE_HI}; border-color: #3a4050; color: {TEXT}; }}
QToolButton#input:pressed {{ background: {BORDER}; }}
QToolButton#input:focus {{ border-color: {ACCENT}; }}
QToolButton#input[active="true"] {{ background: {ACCENT_BG}; border: 2px solid {ACCENT};
    color: {TEXT}; font-weight: 600; }}
QToolButton#input[dim="true"] {{ color: {MUTED}; border-style: dashed; }}
QToolButton#flat, QPushButton#flat {{ background: transparent; border: 1px solid transparent;
    border-radius: 8px; color: {MUTED}; padding: 4px 10px; font-size: 14px; }}
QToolButton#flat:hover, QPushButton#flat:hover {{ background: {SURFACE}; color: {TEXT}; }}
QToolButton#flat:focus, QPushButton#flat:focus {{ border-color: {ACCENT}; }}
QToolButton#flat::menu-indicator {{ image: none; }}
QPushButton {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 8px; padding: 6px 14px; }}
QPushButton:hover {{ background: {SURFACE_HI}; }}
QPushButton:pressed {{ background: {BORDER}; }}
QPushButton:focus {{ border-color: {ACCENT}; }}
QPushButton:default {{ background: {ACCENT}; border-color: {ACCENT}; color: {BG}; font-weight: 600; }}
QLineEdit {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 8px; padding: 6px 8px;
    selection-background-color: {ACCENT}; }}
QLineEdit:focus {{ border-color: {ACCENT}; }}
QCheckBox {{ spacing: 8px; color: {MUTED}; }}
QCheckBox:hover, QCheckBox:focus {{ color: {TEXT}; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border-radius: 4px; border: 1px solid #3a4050;
    background: {SURFACE}; }}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}
QMenu {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 8px; padding: 4px; }}
QMenu::item {{ padding: 6px 18px; border-radius: 6px; }}
QMenu::item:selected {{ background: {SURFACE_HI}; }}
QToolTip {{ background: {SURFACE}; color: {TEXT}; border: 1px solid {BORDER}; padding: 4px 6px; }}
QScrollBar:vertical {{ background: transparent; width: 8px; }}
QScrollBar::handle:vertical {{ background: {SURFACE_HI}; border-radius: 4px; min-height: 24px; }}
QScrollBar::handle:vertical:hover {{ background: #3a4050; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
"""


def port_icon(kind, color=TEXT, size=64):
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    pen = QPen(QColor(color), size / 16)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    s = size / 64
    path = QPainterPath()
    if kind == "hdmi":
        pts = [(10, 22), (54, 22), (54, 36), (46, 46), (18, 46), (10, 36)]
    elif kind == "dp":
        pts = [(10, 22), (54, 22), (54, 46), (22, 46), (10, 34)]
    elif kind == "vga":
        pts = [(10, 22), (54, 22), (48, 46), (16, 46)]
    else:
        path.addRoundedRect(8 * s, 24 * s, 48 * s, 20 * s, 10 * s, 10 * s)
        pts = None
    if pts:
        path.moveTo(pts[0][0] * s, pts[0][1] * s)
        for x, y in pts[1:]:
            path.lineTo(x * s, y * s)
        path.closeSubpath()
    p.drawPath(path)
    if kind == "usbc":
        p.drawRoundedRect(20 * s, 31 * s, 24 * s, 6 * s, 3 * s, 3 * s)
    else:
        for x in range(18, 48, 6):
            p.drawLine(QPointF(x * s, 30 * s), QPointF(x * s, 38 * s))
    p.end()
    return QIcon(pm)


def app_icon():
    size = 256
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor(ACCENT))
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(16, 16, 224, 224, 56, 56)
    p.setBrush(QColor(BG))
    p.drawRoundedRect(52, 62, 152, 98, 14, 14)
    p.setBrush(QColor("white"))
    p.drawRoundedRect(112, 172, 32, 12, 4, 4)
    p.drawRoundedRect(86, 188, 84, 10, 5, 5)
    p.setPen(QPen(QColor("white"), 12, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.drawLine(84, 111, 172, 111)
    p.drawLine(150, 90, 172, 111)
    p.drawLine(150, 132, 172, 111)
    p.end()
    return QIcon(pm)


class Bridge(QObject):
    done = Signal(object, object, object)

    def __init__(self):
        super().__init__()
        self.done.connect(self._dispatch)

    @staticmethod
    def _dispatch(cb, res, err):
        try:
            cb(res, err)
        except RuntimeError:  # widget ja destruido
            pass


_bridge = None


def run_async(fn, cb):
    def work():
        try:
            res, err = fn(), None
        except Exception as ex:  # noqa: BLE001
            res, err = None, ex
        _bridge.done.emit(cb, res, err)

    threading.Thread(target=work, daemon=True).start()


def import_icon(src):
    """Copia/reduz o icone escolhido (png/jpg/ico) para a pasta do app e devolve o nome do arquivo."""
    img = QImage(src)
    if img.isNull():
        try:
            from PIL import Image
            tmp = Image.open(src).convert("RGBA")
            img = QImage(tmp.tobytes("raw", "RGBA"), tmp.width, tmp.height,
                         QImage.Format_RGBA8888).copy()
        except Exception:  # noqa: BLE001
            return None
    if img.isNull():
        return None
    img = img.scaled(128, 128, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    ICON_DIR.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex}.png"
    img.save(str(ICON_DIR / name), "PNG")
    return name


class InputDialog(QDialog):
    def __init__(self, parent, default_name, entry):
        super().__init__(parent)
        self.setWindowTitle("Editar entrada")
        self.setMinimumWidth(340)
        self.icon_file = entry.get("icon")
        self.name = QLineEdit(entry.get("name", ""))
        self.name.setPlaceholderText(default_name)
        self.preview = QLabel()
        self.preview.setFixedSize(48, 48)
        pick = QPushButton("Escolher ícone…")
        clear = QPushButton("Remover")
        pick.clicked.connect(self._pick)
        clear.clicked.connect(self._clear)
        self.hidden = QCheckBox("Ocultar esta entrada")
        self.hidden.setChecked(bool(entry.get("hidden")))
        row = QHBoxLayout()
        row.addWidget(self.preview)
        row.addWidget(pick)
        row.addWidget(clear)
        row.addStretch()
        form = QFormLayout()
        form.addRow("Nome", self.name)
        form.addRow("Ícone", row)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 18, 18, 18)
        lay.setSpacing(12)
        lay.addLayout(form)
        lay.addWidget(self.hidden)
        lay.addWidget(buttons)
        self._refresh()

    def _refresh(self):
        pm = QPixmap(str(ICON_DIR / self.icon_file)) if self.icon_file else QPixmap()
        self.preview.setPixmap(pm.scaled(48, 48, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                               if not pm.isNull() else QPixmap())

    def _pick(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Escolher ícone", "", "Imagens (*.png *.jpg *.jpeg *.ico)")
        if path:
            name = import_icon(path)
            if name:
                self.icon_file = name
                self._refresh()

    def _clear(self):
        self.icon_file = None
        self._refresh()

    def result_entry(self):
        return {"name": self.name.text().strip(), "icon": self.icon_file,
                "hidden": self.hidden.isChecked()}


class InputButton(QToolButton):
    def __init__(self, code):
        super().__init__()
        self.code = code
        self.icons = None  # (normal, ativo) para icones desenhados; None para icones do usuario
        self.setObjectName("input")
        self.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        self.setIconSize(QSize(34, 34))
        self.setFixedSize(112, 86)
        self.setCursor(Qt.PointingHandCursor)
        self.setContextMenuPolicy(Qt.CustomContextMenu)

    def set_state(self, active, dim):
        if self.icons:
            self.setIcon(self.icons[1] if active else self.icons[0])
        self.setProperty("active", active)
        self.setProperty("dim", dim)
        self.style().unpolish(self)
        self.style().polish(self)


class MonitorCard(QFrame):
    COLS = 4

    def __init__(self, win, mid, desc):
        super().__init__()
        self.win, self.mid, self.desc = win, mid, desc
        self.cfg = win.cfg
        self.setObjectName("card")
        self.current = None
        self.codes = list(ddc.DEFAULT_CODES)
        self.show_hidden = False
        self.buttons = []

        self.title = QLabel()
        self.title.setObjectName("title")
        m = re.search(r"DISPLAY#([^#]+)#", mid)
        self.sub = QLabel(f"ID {m.group(1)}" if m else mid)
        self.sub.setObjectName("sub")
        self.status = QLabel("Carregando…")
        self.status.setObjectName("status")
        self.status.setWordWrap(True)

        menu_btn = QToolButton()
        menu_btn.setObjectName("flat")
        menu_btn.setText("⋯")
        menu_btn.setPopupMode(QToolButton.InstantPopup)
        menu = QMenu(menu_btn)
        menu.addAction("Renomear monitor…", self.rename)
        self.act_hidden = QAction("Mostrar entradas ocultas", menu, checkable=True)
        self.act_hidden.toggled.connect(self._toggle_hidden)
        menu.addAction(self.act_hidden)
        menu.addAction("Reler entradas do monitor", self.reload_caps)
        menu_btn.setMenu(menu)

        head = QVBoxLayout()
        head.setSpacing(0)
        head.addWidget(self.title)
        head.addWidget(self.sub)
        top = QHBoxLayout()
        top.addLayout(head, 1)
        top.addWidget(menu_btn, 0, Qt.AlignTop)

        self.grid = QGridLayout()
        self.grid.setSpacing(8)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 14)
        lay.setSpacing(12)
        lay.addLayout(top)
        lay.addLayout(self.grid)
        lay.addWidget(self.status)
        self.update_title()
        self.rebuild()

    def set_status(self, text, state=""):
        self.status.setText(text)
        self.status.setProperty("state", state)
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)

    @property
    def mcfg(self):
        return self.cfg.monitor(self.mid)

    def update_title(self):
        self.title.setText(self.mcfg.get("name") or self.desc)

    def rename(self):
        text, ok = QInputDialog.getText(self, "Renomear monitor", "Nome:",
                                        text=self.mcfg.get("name", ""))
        if ok:
            self.mcfg["name"] = text.strip()
            self.cfg.save()
            self.update_title()

    def _toggle_hidden(self, on):
        self.show_hidden = on
        self.rebuild()

    def rebuild(self):
        for b in self.buttons:
            self.grid.removeWidget(b)
            b.deleteLater()
        self.buttons = []
        shown = 0
        for code in self.codes:
            entry = self.cfg.input(self.mid, code)
            hidden = bool(entry.get("hidden"))
            if hidden and not self.show_hidden:
                continue
            btn = InputButton(code)
            btn.setText(entry.get("name") or ddc.input_name(code))
            pm = QPixmap(str(ICON_DIR / entry["icon"])) if entry.get("icon") else QPixmap()
            if pm.isNull():
                kind = ddc.input_kind(code)
                btn.icons = (port_icon(kind, MUTED), port_icon(kind, ACCENT_SOFT))
            else:
                btn.setIcon(QIcon(pm))
            btn.setToolTip(f"Trocar para {btn.text()}")
            btn.set_state(code == self.current, hidden)
            btn.clicked.connect(lambda _=False, c=code: self.switch(c))
            btn.customContextMenuRequested.connect(lambda pos, b=btn: self._input_menu(b, pos))
            self.grid.addWidget(btn, shown // self.COLS, shown % self.COLS)
            self.buttons.append(btn)
            shown += 1
        if shown == 0:
            self.set_status("Todas as entradas estão ocultas. Use ⋯ → Mostrar entradas ocultas.")

    def _input_menu(self, btn, pos):
        menu = QMenu(self)
        menu.addAction("Editar…", lambda: self.edit_input(btn.code))
        entry = self.cfg.input(self.mid, btn.code)
        menu.addAction("Mostrar" if entry.get("hidden") else "Ocultar",
                       lambda: self._set_hidden(btn.code, not entry.get("hidden")))
        menu.exec(btn.mapToGlobal(pos))

    def _set_hidden(self, code, value):
        self.cfg.input(self.mid, code)["hidden"] = value
        self.cfg.save()
        self.rebuild()

    def edit_input(self, code):
        entry = self.cfg.input(self.mid, code)
        dlg = InputDialog(self, ddc.input_name(code), entry)
        if dlg.exec():
            entry.clear()
            entry.update({k: v for k, v in dlg.result_entry().items() if v})
            self.cfg.save()
            self.rebuild()

    def switch(self, code):
        self.set_status("Trocando entrada…")
        self.current = code
        for b in self.buttons:
            b.set_state(b.code == code, bool(self.cfg.input(self.mid, b.code).get("hidden")))

        def done(ok, err):
            if err or not ok:
                self.set_status("Não foi possível trocar a entrada. Ative o DDC/CI no menu do monitor.",
                                "error")
            QTimer.singleShot(2500, self.load_state)

        run_async(lambda: ddc.set_input(self.mid, code), done)

    def reload_caps(self):
        self.mcfg.pop("caps", None)
        self.load_state()

    def load_state(self):
        have_caps = bool(self.mcfg.get("caps"))

        def fetch():
            cur = ddc.get_input(self.mid)
            caps = None if have_caps else ddc.get_capabilities(self.mid)
            return cur, caps

        def done(res, err):
            if err or res is None:
                self.set_status("Monitor indisponível. Verifique o cabo e se o monitor está ligado.",
                                "error")
                return
            cur, caps = res
            if caps:
                self.mcfg["caps"] = caps
                self.cfg.save()
            codes = ddc.complete_inputs(self.mid, self.mcfg.get("caps") or ddc.DEFAULT_CODES)
            if cur is not None and cur not in codes:
                codes.append(cur)
            self.current, self.codes = cur, codes
            self.rebuild()
            if cur is None:
                self.set_status("Entrada atual desconhecida. Ative o DDC/CI no menu do monitor.", "error")
            else:
                self.set_status("Entrada atual: " + (
                    self.cfg.input(self.mid, cur).get("name") or ddc.input_name(cur)), "ok")

        run_async(fetch, done)


class DisplayWatcher(QAbstractNativeEventFilter):
    WM_DISPLAYCHANGE, WM_DEVICECHANGE = 0x007E, 0x0219

    def __init__(self, on_change):
        super().__init__()
        self.on_change = on_change

    def nativeEventFilter(self, event_type, message):
        if event_type == b"windows_generic_MSG":
            msg = wintypes.MSG.from_address(int(message))
            if msg.message in (self.WM_DISPLAYCHANGE, self.WM_DEVICECHANGE):
                self.on_change()
        return False, 0


class MainWindow(QMainWindow):
    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg
        self.cards = {}
        self.last_activate = 0
        self.setWindowTitle("Input Switch")
        self.setWindowIcon(app_icon())
        self.resize(560, 420)

        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        lay = QVBoxLayout(root)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(12)

        head = QHBoxLayout()
        title = QLabel("Monitores")
        title.setObjectName("h1")
        refresh = QPushButton("⟳ Atualizar")
        refresh.setObjectName("flat")
        refresh.setCursor(Qt.PointingHandCursor)
        refresh.clicked.connect(self.refresh)
        head.addWidget(title)
        head.addStretch()
        head.addWidget(refresh)
        lay.addLayout(head)

        self.empty = QLabel("Nenhum monitor com DDC/CI encontrado")
        self.empty.setObjectName("empty")
        self.empty.setAlignment(Qt.AlignCenter)
        self.empty.hide()
        self.list = QVBoxLayout()
        self.list.setSpacing(12)
        self.list.addStretch()
        holder = QWidget()
        holder.setLayout(self.list)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidget(holder)
        lay.addWidget(self.empty)
        lay.addWidget(scroll, 1)

        self.auto = QCheckBox("Iniciar com o Windows")
        self.auto.setChecked(autostart.is_enabled())
        self.auto.toggled.connect(autostart.set_enabled)
        lay.addWidget(self.auto)

        self.debounce = QTimer(self, singleShot=True, interval=1200)
        self.debounce.timeout.connect(self.refresh)
        self.refresh()

    def schedule_refresh(self):
        self.debounce.start()

    def refresh(self):
        run_async(ddc.list_monitors, self._monitors_ready)

    def _monitors_ready(self, mons, err):
        mons = mons or []
        ids = [m["id"] for m in mons]
        for mid in [m for m in self.cards if m not in ids]:
            self.cards.pop(mid).deleteLater()
        for m in mons:
            if m["id"] not in self.cards:
                card = MonitorCard(self, m["id"], m["desc"])
                self.cards[m["id"]] = card
                self.list.insertWidget(self.list.count() - 1, card)
            self.cards[m["id"]].load_state()
        self.empty.setVisible(not mons)

    def changeEvent(self, e):
        if self.isActiveWindow() and time.monotonic() - self.last_activate > 3 and self.cards:
            self.last_activate = time.monotonic()
            for c in self.cards.values():
                c.load_state()
        super().changeEvent(e)


def init_bridge():
    global _bridge
    _bridge = Bridge()
