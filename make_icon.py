"""Gera assets/app.ico a partir do icone desenhado em inputswitch.ui."""
from pathlib import Path

from PySide6.QtWidgets import QApplication

from inputswitch.ui import app_icon

app = QApplication([])
out = Path(__file__).parent / "assets"
out.mkdir(exist_ok=True)
png = out / "app.png"
app_icon().pixmap(256, 256).save(str(png), "PNG")

from PIL import Image
Image.open(png).save(out / "app.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
