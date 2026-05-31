from __future__ import annotations

import sys
import json
import shutil
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple

try:
    from platformdirs import user_config_dir
except ImportError:
    user_config_dir = None

from PySide6.QtCore import Qt, QTimer, QPointF, QByteArray
from PySide6.QtGui import (
    QColor,
    QPainter,
    QPen,
    QPolygonF,
    QIcon,
    QPixmap,
)
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGraphicsDropShadowEffect,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

APP_NAME = "PillTracker"
APP_AUTHOR = "Mandy"
APP_VERSION = "2.2.0"


# =========================
# App paths
# =========================

def app_dir() -> Path:
    if user_config_dir:
        return Path(user_config_dir(APP_NAME, APP_AUTHOR))
    return Path.home() / ".pilltracker"


CONFIG_DIR = app_dir()
CONFIG_DIR.mkdir(parents=True, exist_ok=True)

CONFIG_PATH = CONFIG_DIR / "settings.json"
LOG_PATH = CONFIG_DIR / "pill_log.txt"

ASSET_ICON_PATH = Path(__file__).resolve().parent / "assets" / "icon.ico"


# =========================
# Log file helpers
# =========================

def ensure_log_file(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.touch()


def parse_log_line(line: str):
    """
    Supported formats:
      YYYY-mm-dd HH:MM:SS [pill_id]
      YYYY-mm-dd HH:MM:SS [pill name]
    """
    line = line.strip()
    if not line:
        return None
    try:
        ts_part, pill_part = line.split(" [", 1)
        pill_raw = pill_part.rstrip("]")
        ts = datetime.strptime(ts_part, "%Y-%m-%d %H:%M:%S")
        return ts, pill_raw
    except Exception:
        return None


def read_log(path: Path):
    ensure_log_file(path)
    entries = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            parsed = parse_log_line(line)
            if parsed:
                entries.append(parsed)
    except Exception:
        pass
    return entries


def read_log_from_file(path: Path):
    entries = []
    try:
        if not path.exists():
            return entries
        for line in path.read_text(encoding="utf-8").splitlines():
            parsed = parse_log_line(line)
            if parsed:
                entries.append(parsed)
    except Exception:
        pass
    return entries


def last_taken(entries, pill_id: str):
    times = [ts for ts, pid in entries if pid == pill_id]
    return max(times) if times else None


def log_pill_take(path: Path, pill_id: str):
    ensure_log_file(path)
    now = datetime.now()
    with path.open("a", encoding="utf-8") as f:
        f.write(f"{now:%Y-%m-%d %H:%M:%S} [{pill_id}]\n")


def normalize_name_to_id(name: str) -> str:
    return "_".join(name.strip().lower().split())


def detect_interval_minutes(timestamps: List[datetime], fallback: int = 8 * 60) -> int:
    """
    Detect estimated cycle from historical timestamps.
    Uses median gap between consecutive doses.
    """
    if len(timestamps) < 2:
        return fallback

    times_sorted = sorted(timestamps)
    diffs = []
    for a, b in zip(times_sorted, times_sorted[1:]):
        diff_min = int((b - a).total_seconds() // 60)
        if diff_min > 0:
            diffs.append(diff_min)

    if not diffs:
        return fallback

    try:
        median_val = int(statistics.median(diffs))
    except Exception:
        median_val = fallback

    return max(1, median_val)


def analyze_imported_log(entries: List[Tuple[datetime, str]]) -> Dict[str, Tuple[str, int]]:
    """
    Returns:
      {pill_id: (display_name, interval_minutes)}

    If imported log uses pill names, we preserve them as display names.
    If it uses pill_ids, we create a title-ish display name from the id.
    """
    grouped: Dict[str, List[datetime]] = {}
    display_names: Dict[str, str] = {}

    for ts, raw_name in entries:
        raw_name = raw_name.strip()
        if not raw_name:
            continue

        pid = normalize_name_to_id(raw_name)
        grouped.setdefault(pid, []).append(ts)

        # Preserve first seen pretty label
        if pid not in display_names:
            if "_" in raw_name or raw_name == raw_name.lower():
                # likely ID-ish
                display_names[pid] = " ".join(part.capitalize() for part in pid.split("_"))
            else:
                display_names[pid] = raw_name

    result: Dict[str, Tuple[str, int]] = {}
    for pid, timestamps in grouped.items():
        interval = detect_interval_minutes(timestamps)
        result[pid] = (display_names.get(pid, pid), interval)

    return result


def rewrite_import_entries_to_internal_ids(entries: List[Tuple[datetime, str]]) -> List[Tuple[datetime, str]]:
    """
    Convert imported raw names/ids into normalized internal pill_id values.
    """
    rewritten = []
    for ts, raw in entries:
        pid = normalize_name_to_id(raw)
        rewritten.append((ts, pid))
    return rewritten


def merge_log_entries(dest_path: Path, entries: List[Tuple[datetime, str]]) -> int:
    """
    Merge entries into destination log, deduplicating exact timestamp+pill_id.
    Returns number of newly added entries.
    """
    ensure_log_file(dest_path)
    existing = set(read_log(dest_path))
    incoming = set(entries)

    merged = sorted(existing | incoming, key=lambda x: (x[0], x[1]))
    added = len((existing | incoming) - existing)

    with dest_path.open("w", encoding="utf-8") as f:
        for ts, pid in merged:
            f.write(f"{ts:%Y-%m-%d %H:%M:%S} [{pid}]\n")

    return added


# =========================
# Time/status helpers
# =========================

def format_td(td: timedelta) -> str:
    total = int(td.total_seconds())
    if total <= 0:
        return "0m"
    hours, rem = divmod(total, 3600)
    minutes, _ = divmod(rem, 60)
    if hours and minutes:
        return f"{hours}h {minutes}m"
    if hours:
        return f"{hours}h"
    return f"{minutes}m"


def pill_status(now: datetime, last_taken_time: Optional[datetime], duration: timedelta):
    if last_taken_time is None:
        return "Ready now", timedelta(0)

    next_time = last_taken_time + duration
    remaining = next_time - now

    if remaining.total_seconds() <= 0:
        return "Ready now", timedelta(0)

    return f"Wait {format_td(remaining)}", remaining


# =========================
# Icons + color helpers
# =========================

def color_to_hex(c: QColor) -> str:
    return c.name(QColor.HexRgb)


def hex_to_color(value: str, fallback: str) -> QColor:
    c = QColor(value)
    return c if c.isValid() else QColor(fallback)


def load_app_icon() -> QIcon:
    if ASSET_ICON_PATH.exists():
        return QIcon(str(ASSET_ICON_PATH))
    return QIcon()


def svg_icon(svg_text: str, size: int = 18) -> QIcon:
    renderer = QSvgRenderer(QByteArray(svg_text.encode("utf-8")))
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    renderer.render(painter)
    painter.end()
    return QIcon(pix)


def make_gear_icon(size: int = 18) -> QIcon:
    svg = """
    <svg width="64" height="64" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35A1.724 1.724 0 005.38 7.753c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.573-1.066z" stroke="currentColor" stroke-width="1.7"/>
      <circle cx="12" cy="12" r="3.2" stroke="currentColor" stroke-width="1.7"/>
    </svg>
    """
    return svg_icon(svg, size)


def make_plus_icon(size: int = 18) -> QIcon:
    svg = """
    <svg width="64" height="64" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M12 5v14M5 12h14" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/>
    </svg>
    """
    return svg_icon(svg, size)


def make_minus_icon(size: int = 18) -> QIcon:
    svg = """
    <svg width="64" height="64" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M5 12h14" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/>
    </svg>
    """
    return svg_icon(svg, size)


def make_import_icon(size: int = 18) -> QIcon:
    svg = """
    <svg width="64" height="64" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M12 3v11" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/>
      <path d="M8 10l4 4 4-4" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>
      <path d="M4 19h16" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/>
    </svg>
    """
    return svg_icon(svg, size)


def make_export_icon(size: int = 18) -> QIcon:
    svg = """
    <svg width="64" height="64" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M12 21V10" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/>
      <path d="M8 14l4-4 4 4" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>
      <path d="M4 5h16" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/>
    </svg>
    """
    return svg_icon(svg, size)


THEMES = {
    "Dark": {
        "windowBg": "#0f1115",
        "cardBg": "#171a21",
        "accent": "#6ea8fe",
        "text": "#ecf2ff",
        "mutedText": "#9aa4b2",
        "border": "#2a3040",
        "clockColor": "#9fd3ff",
        "overdueColor": "#ff6b81",
    },
    "Light": {
        "windowBg": "#f3f6fb",
        "cardBg": "#ffffff",
        "accent": "#3b82f6",
        "text": "#172033",
        "mutedText": "#64748b",
        "border": "#d8e0ea",
        "clockColor": "#2563eb",
        "overdueColor": "#dc2626",
    },
    "Midnight": {
        "windowBg": "#0a0f1f",
        "cardBg": "#11182b",
        "accent": "#7c9cff",
        "text": "#edf2ff",
        "mutedText": "#94a3b8",
        "border": "#24304a",
        "clockColor": "#7dd3fc",
        "overdueColor": "#fb7185",
    },
    "Forest": {
        "windowBg": "#0f1712",
        "cardBg": "#17241b",
        "accent": "#4ade80",
        "text": "#edfdf2",
        "mutedText": "#98b6a3",
        "border": "#294233",
        "clockColor": "#86efac",
        "overdueColor": "#f87171",
    },
    "Rose": {
        "windowBg": "#1a1116",
        "cardBg": "#241720",
        "accent": "#f472b6",
        "text": "#fff1f7",
        "mutedText": "#c7a7b7",
        "border": "#453041",
        "clockColor": "#f9a8d4",
        "overdueColor": "#fb7185",
    },
    "Ocean": {
        "windowBg": "#0c1720",
        "cardBg": "#132330",
        "accent": "#22c55e",
        "text": "#eefcff",
        "mutedText": "#9cb7c3",
        "border": "#28404d",
        "clockColor": "#38bdf8",
        "overdueColor": "#f97316",
    },
}


# =========================
# Per-pill model
# =========================

@dataclass
class Pill:
    pill_id: str
    name: str
    intervalMinutes: int = 8 * 60

    @staticmethod
    def make_id(name: str) -> str:
        return "_".join(name.strip().lower().split())


@dataclass
class Settings:
    fontSize: int = 28
    showAnalog: bool = True
    showDigital: bool = True
    themeName: str = "Dark"

    pills: Dict[str, Pill] = field(default_factory=dict)

    windowBg: QColor = field(default_factory=lambda: QColor(THEMES["Dark"]["windowBg"]))
    cardBg: QColor = field(default_factory=lambda: QColor(THEMES["Dark"]["cardBg"]))
    accent: QColor = field(default_factory=lambda: QColor(THEMES["Dark"]["accent"]))
    textColor: QColor = field(default_factory=lambda: QColor(THEMES["Dark"]["text"]))
    mutedText: QColor = field(default_factory=lambda: QColor(THEMES["Dark"]["mutedText"]))
    border: QColor = field(default_factory=lambda: QColor(THEMES["Dark"]["border"]))
    digitalClockColor: QColor = field(default_factory=lambda: QColor(THEMES["Dark"]["clockColor"]))
    overdueColor: QColor = field(default_factory=lambda: QColor(THEMES["Dark"]["overdueColor"]))

    def apply_theme(self, theme_name: str):
        if theme_name not in THEMES:
            return
        t = THEMES[theme_name]
        self.themeName = theme_name
        self.windowBg = QColor(t["windowBg"])
        self.cardBg = QColor(t["cardBg"])
        self.accent = QColor(t["accent"])
        self.textColor = QColor(t["text"])
        self.mutedText = QColor(t["mutedText"])
        self.border = QColor(t["border"])
        self.digitalClockColor = QColor(t["clockColor"])
        self.overdueColor = QColor(t["overdueColor"])

    def ensure_defaults(self):
        if not self.pills:
            for nm in ["Morning Vitamins", "Afternoon Supplement"]:
                pid = Pill.make_id(nm)
                self.pills[pid] = Pill(pill_id=pid, name=nm, intervalMinutes=8 * 60)

    @classmethod
    def load(cls, path: Path) -> "Settings":
        s = cls()
        if not path.exists():
            s.ensure_defaults()
            return s
        try:
            data = json.loads(path.read_text(encoding="utf-8"))

            s.fontSize = int(data.get("fontSize", s.fontSize))
            s.showAnalog = bool(data.get("showAnalog", s.showAnalog))
            s.showDigital = bool(data.get("showDigital", s.showDigital))
            s.themeName = data.get("themeName", s.themeName)

            if s.themeName in THEMES and s.themeName != "Custom":
                s.apply_theme(s.themeName)

            colors = data.get("colors", {})
            s.windowBg = hex_to_color(colors.get("windowBg", color_to_hex(s.windowBg)), color_to_hex(s.windowBg))
            s.cardBg = hex_to_color(colors.get("cardBg", color_to_hex(s.cardBg)), color_to_hex(s.cardBg))
            s.accent = hex_to_color(colors.get("accent", color_to_hex(s.accent)), color_to_hex(s.accent))
            s.textColor = hex_to_color(colors.get("textColor", color_to_hex(s.textColor)), color_to_hex(s.textColor))
            s.mutedText = hex_to_color(colors.get("mutedText", color_to_hex(s.mutedText)), color_to_hex(s.mutedText))
            s.border = hex_to_color(colors.get("border", color_to_hex(s.border)), color_to_hex(s.border))
            s.digitalClockColor = hex_to_color(colors.get("digitalClockColor", color_to_hex(s.digitalClockColor)), color_to_hex(s.digitalClockColor))
            s.overdueColor = hex_to_color(colors.get("overdueColor", color_to_hex(s.overdueColor)), color_to_hex(s.overdueColor))

            pills_raw = data.get("pills", {})
            pills: Dict[str, Pill] = {}
            if isinstance(pills_raw, dict):
                for pid, pinfo in pills_raw.items():
                    try:
                        name = str(pinfo.get("name", pid))
                        interval = int(pinfo.get("intervalMinutes", 8 * 60))
                        interval = max(1, interval)
                        pills[pid] = Pill(pill_id=pid, name=name, intervalMinutes=interval)
                    except Exception:
                        continue
            elif isinstance(pills_raw, list):
                for nm in pills_raw:
                    pid = Pill.make_id(str(nm))
                    pills[pid] = Pill(pill_id=pid, name=str(nm), intervalMinutes=8 * 60)

            s.pills = pills
            s.ensure_defaults()

        except Exception:
            s = cls()
            s.ensure_defaults()
        return s

    def save(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)

        pills_out = {
            pid: {"name": p.name, "intervalMinutes": int(p.intervalMinutes)}
            for pid, p in self.pills.items()
        }

        data = {
            "version": APP_VERSION,
            "fontSize": self.fontSize,
            "showAnalog": self.showAnalog,
            "showDigital": self.showDigital,
            "themeName": self.themeName,
            "colors": {
                "windowBg": color_to_hex(self.windowBg),
                "cardBg": color_to_hex(self.cardBg),
                "accent": color_to_hex(self.accent),
                "textColor": color_to_hex(self.textColor),
                "mutedText": color_to_hex(self.mutedText),
                "border": color_to_hex(self.border),
                "digitalClockColor": color_to_hex(self.digitalClockColor),
                "overdueColor": color_to_hex(self.overdueColor),
            },
            "pills": pills_out,
        }
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")


# =========================
# UI components
# =========================

class Card(QFrame):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("Card")
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(30)
        shadow.setOffset(0, 10)
        shadow.setColor(QColor(0, 0, 0, 80))
        self.setGraphicsEffect(shadow)


class AnalogClock(QWidget):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setMinimumSize(180, 180)
        self.clock_color = QColor("#9fd3ff")
        self.text_color = QColor("#ecf2ff")
        self.border_color = QColor("#2a3040")
        self.card_color = QColor("#171a21")

    def set_theme_colors(self, clock_color: QColor, text_color: QColor, border_color: QColor, card_color: QColor):
        self.clock_color = clock_color
        self.text_color = text_color
        self.border_color = border_color
        self.card_color = card_color
        self.update()

    def paintEvent(self, event):
        side = min(self.width(), self.height())
        now = datetime.now()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.translate(self.width() / 2, self.height() / 2)
        painter.scale(side / 220.0, side / 220.0)

        painter.setPen(Qt.NoPen)
        painter.setBrush(self.card_color)
        painter.drawEllipse(QPointF(0, 0), 100, 100)

        painter.setPen(QPen(self.border_color, 3))
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(QPointF(0, 0), 100, 100)

        painter.setPen(QPen(self.text_color, 2))
        for i in range(12):
            painter.save()
            painter.rotate(i * 30)
            painter.drawLine(0, -84, 0, -94)
            painter.restore()

        hour_hand = QPolygonF([QPointF(-4, 8), QPointF(4, 8), QPointF(2, -45), QPointF(-2, -45)])
        minute_hand = QPolygonF([QPointF(-3, 10), QPointF(3, 10), QPointF(2, -68), QPointF(-2, -68)])

        hour = now.hour % 12 + now.minute / 60.0
        minute = now.minute + now.second / 60.0

        painter.save()
        painter.rotate(hour * 30)
        painter.setPen(Qt.NoPen)
        painter.setBrush(self.text_color)
        painter.drawConvexPolygon(hour_hand)
        painter.restore()

        painter.save()
        painter.rotate(minute * 6)
        painter.setPen(Qt.NoPen)
        painter.setBrush(self.clock_color)
        painter.drawConvexPolygon(minute_hand)
        painter.restore()

        painter.setPen(QPen(self.clock_color, 2))
        painter.drawLine(0, 0, 0, -78)
        painter.setBrush(self.clock_color)
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QPointF(0, 0), 5, 5)


class PillRow(QWidget):
    def __init__(self, pill_id: str, pill_name: str, parent=None):
        super().__init__(parent)
        self.pill_id = pill_id
        self.pill_name = pill_name

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        self.dot = QFrame()
        self.dot.setFixedSize(14, 14)
        self.dot.setObjectName("Dot")

        self.item = QFrame()
        self.item.setFixedHeight(54)
        self.item.setObjectName("ListItem")

        item_layout = QHBoxLayout(self.item)
        item_layout.setContentsMargins(16, 0, 16, 0)
        item_layout.setSpacing(12)

        self.name_label = QLabel(pill_name)
        self.name_label.setObjectName("ListItemText")

        self.status_label = QLabel("Loading...")
        self.status_label.setObjectName("ListItemStatus")

        self.take_button = QPushButton("Take")
        self.take_button.setObjectName("TakeButton")

        item_layout.addWidget(self.name_label, 2)
        item_layout.addWidget(self.status_label, 3)
        item_layout.addWidget(self.take_button)

        layout.addWidget(self.dot)
        layout.addWidget(self.item, 1)

    def set_name(self, name: str):
        self.pill_name = name
        self.name_label.setText(name)


# =========================
# First run dialog
# =========================

class FirstRunDialog(QDialog):
    def __init__(self, parent=None, icon: Optional[QIcon] = None):
        super().__init__(parent)
        self.setWindowTitle("Welcome to PillTracker")
        self.setModal(True)
        self.setMinimumWidth(620)
        if icon:
            self.setWindowIcon(icon)

        self.pills: Dict[str, Pill] = {}

        root = QVBoxLayout(self)
        root.setSpacing(16)

        title = QLabel("First-time setup")
        title.setObjectName("SetupTitle")
        subtitle = QLabel("Add the pills you take and set each pill's dose interval.")
        subtitle.setObjectName("SetupSubtitle")
        root.addWidget(title)
        root.addWidget(subtitle)

        group_pills = QGroupBox("Pills")
        p_lay = QVBoxLayout(group_pills)

        add_row = QHBoxLayout()
        self.pill_input = QLineEdit()
        self.pill_input.setPlaceholderText("e.g. Vitamin D")

        self.spin = QSpinBox()
        self.spin.setRange(1, 10000)
        self.spin.setValue(8)

        self.unit = QComboBox()
        self.unit.addItems(["hours", "minutes"])

        self.btn_add = QPushButton("Add")
        self.btn_add.setIcon(make_plus_icon())
        self.btn_rem = QPushButton("Remove")
        self.btn_rem.setIcon(make_minus_icon())

        add_row.addWidget(self.pill_input, 2)
        add_row.addWidget(QLabel("Interval:"), 0)
        add_row.addWidget(self.spin, 0)
        add_row.addWidget(self.unit, 0)
        add_row.addWidget(self.btn_add, 0)
        add_row.addWidget(self.btn_rem, 0)

        self.list_widget = QListWidget()

        p_lay.addLayout(add_row)
        p_lay.addWidget(self.list_widget)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)

        root.addWidget(group_pills)
        root.addWidget(btns)

        self.btn_add.clicked.connect(self.add_pill)
        self.btn_rem.clicked.connect(self.remove_pill)
        btns.accepted.connect(self.validate)
        btns.rejected.connect(self.reject)

    def _current_interval_minutes(self) -> int:
        v = self.spin.value()
        return v * 60 if self.unit.currentText() == "hours" else v

    def add_pill(self):
        name = self.pill_input.text().strip()
        if not name:
            return
        pid = Pill.make_id(name)
        interval = max(1, int(self._current_interval_minutes()))
        self.pills[pid] = Pill(pill_id=pid, name=name, intervalMinutes=interval)
        self.list_widget.addItem(f"{name}  —  every {format_td(timedelta(minutes=interval))}")
        self.pill_input.clear()

    def remove_pill(self):
        row = self.list_widget.currentRow()
        if row < 0:
            return
        pid = list(self.pills.keys())[row]
        self.pills.pop(pid, None)
        self.list_widget.takeItem(row)

    def validate(self):
        if not self.pills:
            QMessageBox.warning(self, "No pills", "Add at least one pill.")
            return
        self.accept()


# =========================
# Settings dialog
# =========================

class SettingsDialog(QDialog):
    def __init__(self, settings: Settings, parent=None, icon: Optional[QIcon] = None):
        super().__init__(parent)
        self.setWindowTitle("Application Settings")
        self.setModal(True)
        self.setMinimumWidth(820)
        self.setMinimumHeight(680)
        if icon:
            self.setWindowIcon(icon)

        self.temp_settings = Settings(
            fontSize=settings.fontSize,
            showAnalog=settings.showAnalog,
            showDigital=settings.showDigital,
            themeName=settings.themeName,
            pills={pid: Pill(pill_id=p.pill_id, name=p.name, intervalMinutes=p.intervalMinutes) for pid, p in settings.pills.items()},
            windowBg=QColor(settings.windowBg),
            cardBg=QColor(settings.cardBg),
            accent=QColor(settings.accent),
            textColor=QColor(settings.textColor),
            mutedText=QColor(settings.mutedText),
            border=QColor(settings.border),
            digitalClockColor=QColor(settings.digitalClockColor),
            overdueColor=QColor(settings.overdueColor),
        )

        self.parent_window = parent

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("SettingsTabs")

        # --- TAB 1: Appearance ---
        self.tab_appearance = QWidget()
        lay_app = QVBoxLayout(self.tab_appearance)
        lay_app.setSpacing(15)

        grp_base = QGroupBox("Theme & Clocks")
        form_base = QFormLayout(grp_base)

        self.theme_combo = QComboBox()
        self.theme_combo.addItems(list(THEMES.keys()) + ["Custom"])
        self.theme_combo.setCurrentText(self.temp_settings.themeName)

        self.font_spin = QSpinBox()
        self.font_spin.setRange(12, 72)
        self.font_spin.setValue(self.temp_settings.fontSize)

        self.chk_analog = QCheckBox("Enable Analog Clock")
        self.chk_analog.setChecked(self.temp_settings.showAnalog)
        self.chk_digital = QCheckBox("Enable Digital Clock")
        self.chk_digital.setChecked(self.temp_settings.showDigital)

        form_base.addRow("Global Theme:", self.theme_combo)
        form_base.addRow("Clock Font Size:", self.font_spin)
        form_base.addRow(self.chk_analog)
        form_base.addRow(self.chk_digital)
        lay_app.addWidget(grp_base)

        self.grp_custom = QGroupBox("Custom Theme Designer")
        form_custom = QFormLayout(self.grp_custom)
        self.c_btns = {}
        attrs = [
            ("windowBg", "Window Background"),
            ("cardBg", "Card Background"),
            ("accent", "Accent Color"),
            ("textColor", "Primary Text"),
            ("mutedText", "Muted Text"),
            ("border", "Border Color"),
            ("digitalClockColor", "Clock Color"),
            ("overdueColor", "Overdue Alert"),
        ]
        for attr, label in attrs:
            btn = QPushButton()
            btn.setMinimumHeight(34)
            self.c_btns[attr] = btn
            btn.clicked.connect(lambda chk=False, a=attr: self.pick_color(a))
            form_custom.addRow(f"{label}:", btn)
        lay_app.addWidget(self.grp_custom)
        lay_app.addStretch()

        # --- TAB 2: Medication ---
        self.tab_meds = QWidget()
        lay_meds = QVBoxLayout(self.tab_meds)
        lay_meds.setSpacing(14)

        grp_list = QGroupBox("Pill List")
        lay_list = QVBoxLayout(grp_list)

        row_input = QHBoxLayout()
        self.p_input = QLineEdit()
        self.p_input.setPlaceholderText("Add new pill...")

        self.p_int_spin = QSpinBox()
        self.p_int_spin.setRange(1, 10000)
        self.p_int_spin.setValue(8)

        self.p_int_unit = QComboBox()
        self.p_int_unit.addItems(["hours", "minutes"])

        self.b_add = QPushButton("Add")
        self.b_add.setIcon(make_plus_icon())
        self.b_rem = QPushButton("Remove")
        self.b_rem.setIcon(make_minus_icon())

        row_input.addWidget(self.p_input, 2)
        row_input.addWidget(QLabel("Interval:"), 0)
        row_input.addWidget(self.p_int_spin, 0)
        row_input.addWidget(self.p_int_unit, 0)
        row_input.addWidget(self.b_add, 0)
        row_input.addWidget(self.b_rem, 0)

        self.p_list = QListWidget()

        lay_list.addLayout(row_input)
        lay_list.addWidget(self.p_list)

        grp_edit = QGroupBox("Edit selected pill interval")
        form_edit = QFormLayout(grp_edit)

        self.sel_interval_spin = QSpinBox()
        self.sel_interval_spin.setRange(1, 10000)

        self.sel_interval_unit = QComboBox()
        self.sel_interval_unit.addItems(["hours", "minutes"])

        self.btn_apply_interval = QPushButton("Apply interval to selected pill")

        form_edit.addRow("Interval:", self._hbox_widget([self.sel_interval_spin, self.sel_interval_unit]))
        form_edit.addRow(self.btn_apply_interval)

        grp_io = QGroupBox("Log Import / Export")
        io_lay = QVBoxLayout(grp_io)

        io_row = QHBoxLayout()
        self.btn_import_log = QPushButton("Import Log")
        self.btn_import_log.setIcon(make_import_icon())
        self.btn_export_log = QPushButton("Export Log")
        self.btn_export_log.setIcon(make_export_icon())
        io_row.addWidget(self.btn_import_log)
        io_row.addWidget(self.btn_export_log)

        self.io_info = QLabel(
            "Import a previous log file to auto-detect pill names and estimated intervals.\n"
            "Export saves a copy of the current normalized app log."
        )
        self.io_info.setWordWrap(True)
        self.io_info.setObjectName("StatusText")

        io_lay.addLayout(io_row)
        io_lay.addWidget(self.io_info)

        lay_meds.addWidget(grp_list)
        lay_meds.addWidget(grp_edit)
        lay_meds.addWidget(grp_io)
        lay_meds.addStretch()

        # --- TAB 3: About ---
        self.tab_about = QWidget()
        lay_about = QVBoxLayout(self.tab_about)
        info = QLabel(
            f"<h2 style='color:#6ea8fe'>{APP_NAME}</h2>"
            f"<b>Version:</b> {APP_VERSION}<br>"
            f"<b>Developer:</b> {APP_AUTHOR}<br><br>"
            "A high-performance, modern pill tracking dashboard built with PySide6.<br>"
            "Designed by Mandy."
        )
        info.setWordWrap(True)
        info.setAlignment(Qt.AlignCenter)
        lay_about.addStretch()
        lay_about.addWidget(info)
        lay_about.addStretch()

        self.tabs.addTab(self.tab_appearance, "Appearance")
        self.tabs.addTab(self.tab_meds, "Medication")
        self.tabs.addTab(self.tab_about, "About")

        root.addWidget(self.tabs)

        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        root.addWidget(btns)

        self.theme_combo.currentTextChanged.connect(self.on_theme_change)
        self.b_add.clicked.connect(self.add_p)
        self.b_rem.clicked.connect(self.rem_p)
        self.p_list.currentRowChanged.connect(self.on_pill_selected)
        self.btn_apply_interval.clicked.connect(self.apply_selected_interval)
        self.btn_import_log.clicked.connect(self.import_log)
        self.btn_export_log.clicked.connect(self.export_log)
        btns.accepted.connect(self.save_and_close)
        btns.rejected.connect(self.reject)

        self.refresh_c_btns()
        self.on_theme_change(self.theme_combo.currentText())

        self.refresh_pill_list()
        if self.p_list.count() > 0:
            self.p_list.setCurrentRow(0)

    def _hbox_widget(self, widgets: List[QWidget]) -> QWidget:
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        for x in widgets:
            lay.addWidget(x)
        lay.addStretch()
        return w

    def _interval_minutes(self, spin: QSpinBox, unit: QComboBox) -> int:
        v = spin.value()
        return v * 60 if unit.currentText() == "hours" else v

    def refresh_pill_list(self):
        self.p_list.clear()
        for pid, p in self.temp_settings.pills.items():
            self.p_list.addItem(f"{p.name}  —  every {format_td(timedelta(minutes=p.intervalMinutes))}")

    def _selected_pill_id(self) -> Optional[str]:
        row = self.p_list.currentRow()
        if row < 0:
            return None
        return list(self.temp_settings.pills.keys())[row]

    def on_pill_selected(self, row: int):
        pid = self._selected_pill_id()
        if not pid:
            return
        p = self.temp_settings.pills[pid]
        if p.intervalMinutes % 60 == 0:
            self.sel_interval_spin.setValue(p.intervalMinutes // 60)
            self.sel_interval_unit.setCurrentText("hours")
        else:
            self.sel_interval_spin.setValue(p.intervalMinutes)
            self.sel_interval_unit.setCurrentText("minutes")

    def apply_selected_interval(self):
        pid = self._selected_pill_id()
        if not pid:
            return
        minutes = max(1, int(self._interval_minutes(self.sel_interval_spin, self.sel_interval_unit)))
        self.temp_settings.pills[pid].intervalMinutes = minutes
        self.refresh_pill_list()
        idx = list(self.temp_settings.pills.keys()).index(pid)
        self.p_list.setCurrentRow(idx)

    def add_p(self):
        name = self.p_input.text().strip()
        if not name:
            return
        pid = Pill.make_id(name)
        if pid in self.temp_settings.pills:
            QMessageBox.warning(self, "Duplicate", "A pill with that name/id already exists.")
            return
        minutes = max(1, int(self._interval_minutes(self.p_int_spin, self.p_int_unit)))
        self.temp_settings.pills[pid] = Pill(pill_id=pid, name=name, intervalMinutes=minutes)
        self.p_input.clear()
        self.refresh_pill_list()
        self.p_list.setCurrentRow(self.p_list.count() - 1)

    def rem_p(self):
        pid = self._selected_pill_id()
        if not pid:
            return
        if len(self.temp_settings.pills) <= 1:
            QMessageBox.warning(self, "Error", "Pill list cannot be empty.")
            return
        self.temp_settings.pills.pop(pid, None)
        self.refresh_pill_list()
        self.p_list.setCurrentRow(0)

    def on_theme_change(self, name: str):
        is_custom = (name == "Custom")
        if name in THEMES:
            self.temp_settings.apply_theme(name)
            self.refresh_c_btns()
        self.grp_custom.setEnabled(is_custom)
        if is_custom:
            self.temp_settings.themeName = "Custom"

    def refresh_c_btns(self):
        for attr, btn in self.c_btns.items():
            col = getattr(self.temp_settings, attr)
            btn.setText(col.name().upper())
            btn.setStyleSheet(
                f"background-color: {col.name()}; "
                f"color: {'#000' if col.lightness() > 150 else '#fff'}; "
                "border-radius: 8px; border: 1px solid #555; font-weight: bold;"
            )

    def pick_color(self, attr: str):
        curr = getattr(self.temp_settings, attr)
        new_c = QColorDialog.getColor(curr, self, f"Pick {attr}")
        if new_c.isValid():
            setattr(self.temp_settings, attr, new_c)
            self.theme_combo.setCurrentText("Custom")
            self.refresh_c_btns()

    def import_log(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Import past log",
            str(Path.home()),
            "Text Files (*.txt);;All Files (*)"
        )
        if not file_path:
            return

        src = Path(file_path)
        imported_entries = read_log_from_file(src)
        if not imported_entries:
            QMessageBox.warning(
                self,
                "Import failed",
                "No valid log lines were found.\nExpected format:\nYYYY-mm-dd HH:MM:SS [pill_name_or_id]"
            )
            return

        detected = analyze_imported_log(imported_entries)
        rewritten_entries = rewrite_import_entries_to_internal_ids(imported_entries)
        added_count = merge_log_entries(LOG_PATH, rewritten_entries)

        added_pills = 0
        updated_pills = 0

        for pid, (name, interval) in detected.items():
            if pid in self.temp_settings.pills:
                # Only update interval if existing pill still has default-like value or user wants import influence
                self.temp_settings.pills[pid].intervalMinutes = interval
                if not self.temp_settings.pills[pid].name:
                    self.temp_settings.pills[pid].name = name
                updated_pills += 1
            else:
                self.temp_settings.pills[pid] = Pill(
                    pill_id=pid,
                    name=name,
                    intervalMinutes=interval
                )
                added_pills += 1

        self.refresh_pill_list()
        if self.p_list.count() > 0:
            self.p_list.setCurrentRow(0)

        QMessageBox.information(
            self,
            "Import complete",
            f"Imported log successfully.\n\n"
            f"New log entries added: {added_count}\n"
            f"Pills added from history: {added_pills}\n"
            f"Pills updated from history: {updated_pills}"
        )

    def export_log(self):
        ensure_log_file(LOG_PATH)
        default_name = f"pill_log_export_{datetime.now():%Y%m%d_%H%M%S}.txt"
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export log",
            str(Path.home() / default_name),
            "Text Files (*.txt);;All Files (*)"
        )
        if not file_path:
            return

        try:
            shutil.copyfile(LOG_PATH, file_path)
            QMessageBox.information(self, "Export complete", f"Log exported to:\n{file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Export failed", f"Could not export log:\n{e}")

    def save_and_close(self):
        if not self.temp_settings.pills:
            QMessageBox.warning(self, "Error", "Pill list cannot be empty.")
            return
        self.temp_settings.fontSize = self.font_spin.value()
        self.temp_settings.showAnalog = self.chk_analog.isChecked()
        self.temp_settings.showDigital = self.chk_digital.isChecked()
        self.accept()


# =========================
# Main Window
# =========================

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.app_icon = load_app_icon()
        if not self.app_icon.isNull():
            self.setWindowIcon(self.app_icon)

        self.settings = Settings.load(CONFIG_PATH)
        self.settings.ensure_defaults()

        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.resize(1200, 800)

        self.pill_rows: Dict[str, PillRow] = {}

        central = QWidget()
        self.setCentralWidget(central)

        self.root = QVBoxLayout(central)
        self.root.setContentsMargins(25, 25, 25, 25)
        self.root.setSpacing(20)

        top = QHBoxLayout()
        t_lay = QVBoxLayout()
        self.lab_t = QLabel(APP_NAME)
        self.lab_t.setObjectName("AppTitle")
        self.lab_s = QLabel("Live Medication Dashboard")
        self.lab_s.setObjectName("AppSubtitle")
        t_lay.addWidget(self.lab_t)
        t_lay.addWidget(self.lab_s)
        top.addLayout(t_lay)
        top.addStretch()

        self.btn_set = QToolButton()
        self.btn_set.setObjectName("IconButton")
        self.btn_set.setIcon(make_gear_icon(22))
        self.btn_set.clicked.connect(self.open_settings)
        top.addWidget(self.btn_set)
        self.root.addLayout(top)

        content = QHBoxLayout()
        content.setSpacing(20)
        self.root.addLayout(content, 1)

        self.card_m = Card()
        self.card_s = Card()
        content.addWidget(self.card_m, 3)
        content.addWidget(self.card_s, 2)

        self.setup_main_card()
        self.setup_status_card()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(1000)

        self.apply_ui_settings()
        self.tick()

        if not CONFIG_PATH.exists():
            QTimer.singleShot(500, self.first_run)

    def setup_main_card(self):
        lay = QVBoxLayout(self.card_m)
        lay.setContentsMargins(30, 30, 30, 30)
        lay.setSpacing(20)

        st = QLabel("Health Status")
        st.setObjectName("SectionTitle")
        lay.addWidget(st)

        self.lab_clock = QLabel("00:00:00")
        self.lab_clock.setObjectName("ClockLabel")
        self.lab_clock.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.lab_clock)

        self.analog = AnalogClock()
        lay.addWidget(self.analog, 1, Qt.AlignCenter)

        self.lab_int = QLabel("")
        self.lab_int.setObjectName("IntervalLabel")
        self.lab_int.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.lab_int)

        pt = QLabel("Active Medications")
        pt.setObjectName("MiniTitle")
        lay.addWidget(pt)

        self.p_cont = QWidget()
        self.p_lay = QVBoxLayout(self.p_cont)
        self.p_lay.setContentsMargins(0, 0, 0, 0)
        self.p_lay.setSpacing(12)
        lay.addWidget(self.p_cont)
        lay.addStretch()

    def setup_status_card(self):
        lay = QVBoxLayout(self.card_s)
        lay.setContentsMargins(30, 30, 30, 30)
        lay.setSpacing(18)

        st = QLabel("Statistics")
        st.setObjectName("SectionTitle")
        lay.addWidget(st)

        self.s_time = QLabel("")
        self.s_time.setObjectName("StatusValue")
        lay.addWidget(self.s_time)

        self.s_date = QLabel("")
        self.s_date.setObjectName("StatusText")
        lay.addWidget(self.s_date)

        self.s_theme = QLabel("")
        self.s_theme.setObjectName("StatusText")
        lay.addWidget(self.s_theme)

        self.s_cnt = QLabel("")
        self.s_cnt.setObjectName("StatusText")
        lay.addWidget(self.s_cnt)

        self.s_log = QLabel("")
        self.s_log.setObjectName("StatusText")
        lay.addWidget(self.s_log)

        lay.addStretch()

    def apply_ui_settings(self):
        s = self.settings
        self.setStyleSheet(f"""
            QMainWindow {{ background: {s.windowBg.name()}; }}
            QFrame#Card {{ background: {s.cardBg.name()}; border: 1px solid {s.border.name()}; border-radius: 28px; }}
            QLabel#AppTitle {{ font-size: 32px; font-weight: 900; color: {s.textColor.name()}; }}
            QLabel#AppSubtitle {{ font-size: 14px; color: {s.mutedText.name()}; }}
            QLabel#SectionTitle {{ font-size: 22px; font-weight: 700; color: {s.textColor.name()}; }}
            QLabel#MiniTitle {{ font-size: 13px; font-weight: 800; color: {s.accent.name()}; text-transform: uppercase; }}
            QLabel#ClockLabel {{ font-size: {s.fontSize}px; font-weight: 800; color: {s.digitalClockColor.name()}; }}
            QLabel#StatusValue {{ font-size: 34px; font-weight: 900; color: {s.accent.name()}; }}
            QLabel#StatusText, QLabel#IntervalLabel {{ font-size: 14px; color: {s.mutedText.name()}; }}
            QLabel#ListItemText {{ font-size: 16px; font-weight: bold; color: {s.textColor.name()}; }}
            QLabel#ListItemStatus {{ font-size: 13px; color: {s.mutedText.name()}; }}
            QFrame#ListItem {{ background: rgba(255,255,255,0.03); border: 1px solid {s.border.name()}; border-radius: 18px; }}
            QFrame#Dot {{ border-radius: 7px; }}
            QPushButton, QLineEdit, QSpinBox, QComboBox, QListWidget {{
                background: {s.cardBg.name()};
                color: {s.textColor.name()};
                border: 1px solid {s.border.name()};
                border-radius: 12px;
                padding: 8px;
            }}
            QPushButton#TakeButton {{
                min-width: 85px;
                font-weight: 800;
                background: {s.accent.name()};
                color: {s.windowBg.name()};
                border: none;
            }}
            QPushButton#TakeButton:disabled {{
                background: {s.border.name()};
                color: {s.mutedText.name()};
            }}
            QToolButton#IconButton {{
                background: {s.cardBg.name()};
                border: 1px solid {s.border.name()};
                border-radius: 15px;
                padding: 10px;
            }}
            QTabWidget::pane {{
                border: 1px solid {s.border.name()};
                border-radius: 15px;
                background: {s.cardBg.name()};
                top: -1px;
            }}
            QTabBar::tab {{
                background: transparent;
                color: {s.mutedText.name()};
                padding: 12px 25px;
                font-weight: bold;
            }}
            QTabBar::tab:selected {{
                color: {s.accent.name()};
                border-bottom: 2px solid {s.accent.name()};
            }}
            QGroupBox {{
                font-weight: bold;
                color: {s.accent.name()};
                border: 1px solid {s.border.name()};
                border-radius: 15px;
                margin-top: 15px;
                padding-top: 15px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 15px;
                padding: 0 5px;
            }}
            QDialog {{ background: {s.windowBg.name()}; }}
        """)

        self.lab_clock.setVisible(s.showDigital)
        self.analog.setVisible(s.showAnalog)
        self.analog.set_theme_colors(s.digitalClockColor, s.textColor, s.border, s.cardBg)

        intervals = [p.intervalMinutes for p in s.pills.values()] or [0]
        mn, mx = min(intervals), max(intervals)
        if mn == mx:
            self.lab_int.setText(f"All pills interval: {format_td(timedelta(minutes=mn))}")
        else:
            self.lab_int.setText(f"Intervals: {format_td(timedelta(minutes=mn))} .. {format_td(timedelta(minutes=mx))}")

        self.s_theme.setText(f"Theme: {s.themeName}")
        self.s_cnt.setText(f"Medications: {len(s.pills)}")

        self.refresh_pills()

    def refresh_pills(self):
        while self.p_lay.count():
            w = self.p_lay.takeAt(0).widget()
            if w:
                w.deleteLater()
        self.pill_rows.clear()

        for pid, pill in self.settings.pills.items():
            row = PillRow(pid, pill.name)
            row.take_button.clicked.connect(lambda chk=False, p=pid: self.take_p(p))
            self.pill_rows[pid] = row
            self.p_lay.addWidget(row)

    def take_p(self, pill_id: str):
        log_pill_take(LOG_PATH, pill_id)
        self.tick()

    def tick(self):
        now = datetime.now()
        self.lab_clock.setText(now.strftime("%H:%M:%S"))
        self.s_time.setText(now.strftime("%H:%M:%S"))
        self.s_date.setText(now.strftime("%A, %B %d"))

        entries = read_log(LOG_PATH)

        for pid, row in self.pill_rows.items():
            pill = self.settings.pills.get(pid)
            if not pill:
                continue
            interval = timedelta(minutes=max(1, int(pill.intervalMinutes)))
            last = last_taken(entries, pid)
            status, rem = pill_status(now, last, interval)

            row.status_label.setText(f"{status}  •  every {format_td(interval)}")
            ready = rem.total_seconds() <= 0

            row.dot.setStyleSheet(
                f"background: {self.settings.accent.name() if ready else self.settings.overdueColor.name()};"
            )
            row.take_button.setEnabled(ready)

        if entries:
            ts, pid = max(entries, key=lambda x: x[0])
            nm = self.settings.pills.get(pid).name if pid in self.settings.pills else pid
            self.s_log.setText(f"Last taken: {nm} at {ts.strftime('%H:%M')}")
        else:
            self.s_log.setText("No log history")

    def first_run(self):
        d = FirstRunDialog(self, self.app_icon)
        if d.exec() == QDialog.Accepted:
            self.settings.pills = d.pills
            self.settings.save(CONFIG_PATH)
            self.apply_ui_settings()

    def open_settings(self):
        d = SettingsDialog(self.settings, self, self.app_icon)
        if d.exec() == QDialog.Accepted:
            self.settings = d.temp_settings
            self.settings.save(CONFIG_PATH)
            self.apply_ui_settings()
            self.tick()

    def closeEvent(self, event):
        self.settings.save(CONFIG_PATH)
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)

    win = MainWindow()
    win.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
