import json
import os
from pathlib import Path

APP_DIR = Path(os.environ.get("APPDATA", Path.home())) / "InputSwitch"
ICON_DIR = APP_DIR / "icons"


class Config:
    def __init__(self, path=None):
        self.path = Path(path) if path else APP_DIR / "config.json"
        self.data = {"monitors": {}}
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(loaded.get("monitors"), dict):
                self.data = loaded
        except (OSError, ValueError, AttributeError):
            pass

    def monitor(self, mid):
        m = self.data["monitors"].setdefault(mid, {})
        m.setdefault("inputs", {})
        return m

    def input(self, mid, code):
        return self.monitor(mid)["inputs"].setdefault(str(code), {})

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.path)
