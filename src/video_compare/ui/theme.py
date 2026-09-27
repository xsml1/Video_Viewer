"""Colour families, variants and the flat application stylesheet.

Each family (莫兰迪/奶油/复古/赛博朋克/马卡龙/清爽极简) ships several variants,
and every variant drives a full palette (window, surfaces, canvas, accent).
The picker also offers the family theme colours with five shade steps plus a
standard colour row, so a single swatch can be used as the accent colour.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from video_compare.services.settings import AppSettings

FONT_FAMILY = "Microsoft YaHei UI"
FOLLOW = "follow"


@dataclass(frozen=True, slots=True)
class Family:
    key: str
    label: str
    colors: tuple[str, ...]
    base: str

    @property
    def primary(self) -> str:
        return self.base


FAMILIES: dict[str, Family] = {
    "codex": Family(
        "codex",
        "清爽极简",
        ("#3b6ff5", "#1f2937", "#64748b", "#0ea5e9", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6"),
        "#3b6ff5",
    ),
    "morandi": Family(
        "morandi",
        "莫兰迪",
        ("#8a9a8b", "#9aa7a5", "#b3ae9e", "#c7bfae", "#8f9aa8", "#a9a2b0", "#c9a99a", "#6f7a72"),
        "#8a9a8b",
    ),
    "cream": Family(
        "cream",
        "奶油风",
        ("#e0a96d", "#f3d5b5", "#c98d5c", "#8c6a4f", "#e8c39e", "#d9b382", "#b98a5e", "#f7e7d3"),
        "#e0a96d",
    ),
    "retro": Family(
        "retro",
        "复古",
        ("#b85c38", "#2f4f4f", "#d9a441", "#7a5c3e", "#8c3b3b", "#40615a", "#c98d5c", "#e8dcc0"),
        "#b85c38",
    ),
    "cyberpunk": Family(
        "cyberpunk",
        "赛博朋克",
        ("#00e5ff", "#ff2e97", "#b14aff", "#39ff14", "#5a189a", "#3a0ca3", "#ffd60a", "#4361ee"),
        "#00e5ff",
    ),
    "macaron": Family(
        "macaron",
        "马卡龙",
        ("#f48fb1", "#7fd1c1", "#ffd166", "#9bb7ff", "#c8a2ff", "#ffb4a2", "#a0e7b4", "#f8c8dc"),
        "#f48fb1",
    ),
}

FAMILY_LABELS = {key: family.label for key, family in FAMILIES.items()}

STANDARD_COLORS: tuple[str, ...] = (
    "#000000",
    "#404040",
    "#7f7f7f",
    "#bfbfbf",
    "#ffffff",
    "#c00000",
    "#ff0000",
    "#ffc000",
    "#ffff00",
    "#92d050",
    "#00b050",
    "#00b0f0",
    "#0070c0",
    "#002060",
    "#7030a0",
)

SHADE_STEPS: tuple[float, ...] = (0.8, 0.6, 0.4, -0.25, -0.5)


@dataclass(frozen=True, slots=True)
class CanvasColors:
    background: str = "#0e0e10"
    surface: str = "#18181b"
    border: str = "#2b2b30"
    text: str = "#e8e8ec"
    muted: str = "#9b9ba6"
    accent: str = "#5a8dff"
    accent_fill: str = "#335a8dff"
    overlay: str = "#00b050"
    overlay_backdrop: str = "#99000000"
    warning: str = "#f59e0b"


@dataclass(frozen=True, slots=True)
class Palette:
    window: str
    surface: str
    surface_alt: str
    border: str
    text: str
    muted: str
    accent: str
    accent_text: str
    hover: str
    pressed: str
    disabled: str


def mix(first: str, second: str, ratio: float) -> str:
    """Blend two colours; ratio 0 keeps ``first`` and 1 returns ``second``."""
    a, b = QColor(first), QColor(second)
    clamped = max(0.0, min(1.0, ratio))
    return QColor(
        round(a.red() + (b.red() - a.red()) * clamped),
        round(a.green() + (b.green() - a.green()) * clamped),
        round(a.blue() + (b.blue() - a.blue()) * clamped),
    ).name()


def readable_text(color: str) -> str:
    return "#101014" if QColor(color).lightness() > 150 else "#ffffff"


def is_color(value: str) -> bool:
    return QColor.isValidColorName(value) and value.startswith("#")


def shade(color: str, step: float) -> str:
    """Office-like shade step: positive lightens, negative darkens."""
    return mix(color, "#ffffff" if step > 0 else "#000000", abs(step))


def resolve_family(name: str, fallback: str = "codex") -> Family:
    if name == FOLLOW or name not in FAMILIES:
        return FAMILIES.get(fallback, FAMILIES["codex"])
    return FAMILIES[name]


def theme_rows(family: Family) -> tuple[tuple[str, ...], ...]:
    """Theme colours row plus five shade rows, like a fill colour picker."""
    return (family.colors,) + tuple(
        tuple(shade(color, step) for color in family.colors) for step in SHADE_STEPS
    )


def is_dark(settings: AppSettings, app: QApplication) -> bool:
    if settings.theme == "dark":
        return True
    if settings.theme == "light":
        return False
    scheme = app.styleHints().colorScheme()
    if scheme is Qt.ColorScheme.Dark:
        return True
    if scheme is Qt.ColorScheme.Light:
        return False
    return app.palette().color(QPalette.ColorRole.Window).lightness() < 128


def role_color(settings: AppSettings, role: str) -> str:
    """Base colour of one role: an explicit pick, or the family colour."""
    family = resolve_family(settings.scheme)
    explicit = {
        "workspace": settings.workspace_color,
        "function": settings.function_color,
        "accent": settings.accent,
        "overlay": settings.overlay_color,
    }[role]
    if explicit != FOLLOW and is_color(explicit):
        return explicit
    return family.base


def overlay_color(settings: AppSettings) -> str:
    return role_color(settings, "overlay")


def _accent(settings: AppSettings, *, dark: bool) -> str:
    color = role_color(settings, "accent")
    if dark and QColor(color).lightness() < 150:
        return mix(color, "#ffffff", 0.22)
    return color


def palette_for(settings: AppSettings, app: QApplication) -> Palette:
    dark = is_dark(settings, app)
    base = role_color(settings, "function")
    accent = _accent(settings, dark=dark)
    if dark:
        window = mix(base, "#0a0a0c", 0.88)
        surface = mix(base, "#0a0a0c", 0.78)
        text = mix("#ffffff", base, 0.10)
    else:
        window = mix(base, "#ffffff", 0.90)
        surface = mix(base, "#ffffff", 0.72)
        text = mix("#14171c", base, 0.16)
    muted = mix(text, surface, 0.48)
    return Palette(
        window=window,
        surface=surface,
        surface_alt=mix(surface, text, 0.06),
        border=mix(surface, text, 0.16),
        text=text,
        muted=muted,
        accent=accent,
        accent_text=readable_text(accent),
        hover=mix(surface, accent, 0.10),
        pressed=mix(surface, accent, 0.20),
        disabled=mix(muted, surface, 0.45),
    )


def canvas_colors_for(settings: AppSettings, app: QApplication) -> CanvasColors:
    dark = is_dark(settings, app)
    base = role_color(settings, "workspace")
    accent = _accent(settings, dark=dark)
    if dark:
        background = mix(base, "#000000", 0.86)
        surface = mix(base, "#000000", 0.74)
        text = mix("#ffffff", base, 0.10)
    else:
        background = mix(base, "#ffffff", 0.78)
        surface = mix(base, "#ffffff", 0.92)
        text = mix("#14171c", base, 0.16)
    fill = QColor(accent)
    fill.setAlpha(0x3D if dark else 0x33)
    backdrop = QColor("#000000")
    backdrop.setAlpha(150)
    return CanvasColors(
        background=background,
        surface=surface,
        border=mix(surface, text, 0.18),
        text=text,
        muted=mix(text, surface, 0.42),
        accent=accent,
        accent_fill=fill.name(QColor.NameFormat.HexArgb),
        overlay=overlay_color(settings),
        overlay_backdrop=backdrop.name(QColor.NameFormat.HexArgb),
        warning="#f0b429" if dark else "#c2760a",
    )


def stylesheet(palette: Palette) -> str:
    return f"""
QWidget {{
    font-family: "{FONT_FAMILY}";
    font-size: 9pt;
    color: {palette.text};
}}
QMainWindow, QDialog {{
    background: {palette.window};
}}
QLabel {{
    background: transparent;
}}
QLabel#SectionTitle {{
    color: {palette.muted};
    font-size: 8.5pt;
    font-weight: 600;
    padding: 2px 2px 2px 2px;
}}
QLabel#AppTitle {{
    font-size: 10.5pt;
    font-weight: 600;
    padding: 0 2px;
}}
QLabel#Hint, QLabel#Status {{
    color: {palette.muted};
}}
QFrame#Card, QFrame#TopBar, QFrame#Transport {{
    background: {palette.surface};
    border: 1px solid {palette.border};
    border-radius: 10px;
}}
QFrame#TopBar {{
    border-radius: 12px;
}}
QPushButton {{
    background: {palette.surface};
    border: 1px solid {palette.border};
    border-radius: 8px;
    padding: 5px 10px;
    min-height: 16px;
}}
QPushButton:hover {{
    background: {palette.hover};
    border-color: {palette.accent};
}}
QPushButton:pressed {{
    background: {palette.pressed};
}}
QPushButton:checked {{
    background: {palette.accent};
    border-color: {palette.accent};
    color: {palette.accent_text};
}}
QPushButton:disabled {{
    background: {palette.surface_alt};
    color: {palette.disabled};
    border-color: {palette.border};
}}
QPushButton#Primary {{
    background: {palette.accent};
    border-color: {palette.accent};
    color: {palette.accent_text};
    font-weight: 600;
}}
QPushButton#Primary:disabled {{
    background: {palette.surface_alt};
    color: {palette.disabled};
}}
QPushButton#Ghost {{
    background: transparent;
    border-color: transparent;
    color: {palette.muted};
    padding: 4px 8px;
}}
QPushButton#Ghost:hover {{
    background: {palette.hover};
    color: {palette.text};
    border-color: {palette.border};
}}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
    background: {palette.surface};
    border: 1px solid {palette.border};
    border-radius: 8px;
    padding: 5px 8px;
    min-height: 16px;
    selection-background-color: {palette.accent};
    selection-color: {palette.accent_text};
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
    border: 1px solid {palette.accent};
}}
QLineEdit:disabled, QComboBox:disabled {{
    color: {palette.disabled};
    background: {palette.surface_alt};
}}
QComboBox QAbstractItemView {{
    background: {palette.surface};
    border: 1px solid {palette.border};
    border-radius: 8px;
    padding: 4px;
    selection-background-color: {palette.accent};
    selection-color: {palette.accent_text};
    outline: none;
}}
QListWidget {{
    background: {palette.surface_alt};
    border: 1px solid {palette.border};
    border-radius: 10px;
    padding: 4px;
    outline: none;
}}
QListWidget::item {{
    border-radius: 6px;
    padding: 6px 8px;
    margin: 1px 2px;
}}
QListWidget::item:hover {{
    background: {palette.hover};
}}
QListWidget::item:selected {{
    background: {palette.accent};
    color: {palette.accent_text};
}}
QSlider::groove:horizontal {{
    height: 4px;
    border-radius: 2px;
    background: {palette.border};
}}
QSlider::sub-page:horizontal {{
    height: 4px;
    border-radius: 2px;
    background: {palette.accent};
}}
QSlider::handle:horizontal {{
    width: 13px;
    height: 13px;
    margin: -5px 0;
    border-radius: 6px;
    background: {palette.accent};
    border: 2px solid {palette.surface};
}}
QSlider::handle:horizontal:hover {{
    border-color: {palette.text};
}}
QScrollBar:vertical, QScrollBar:horizontal {{
    background: transparent;
    margin: 0px;
    border: none;
}}
QScrollBar:vertical {{
    width: 10px;
}}
QScrollBar:horizontal {{
    height: 10px;
}}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
    background: {palette.border};
    border-radius: 5px;
    min-height: 24px;
    min-width: 24px;
}}
QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {{
    background: {palette.muted};
}}
QScrollBar::add-line, QScrollBar::sub-line {{
    width: 0px;
    height: 0px;
}}
QScrollBar::add-page, QScrollBar::sub-page {{
    background: transparent;
}}
QSplitter::handle {{
    background: transparent;
    width: 6px;
}}
QSplitter::handle:hover {{
    background: {palette.border};
}}
QToolButton#Swatch {{
    border: 1px solid {palette.border};
    border-radius: 4px;
}}
QToolButton#Swatch:hover {{
    border: 2px solid {palette.text};
}}
QToolButton#Swatch:checked {{
    border: 2px solid {palette.accent};
}}
QToolTip {{
    background: {palette.surface};
    color: {palette.text};
    border: 1px solid {palette.border};
    border-radius: 6px;
    padding: 4px 6px;
}}
QCheckBox, QRadioButton {{
    background: transparent;
    spacing: 6px;
}}
QMessageBox {{
    background: {palette.window};
}}
QGroupBox {{
    border: 1px solid {palette.border};
    border-radius: 10px;
    margin-top: 10px;
    padding: 8px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    color: {palette.muted};
}}
"""


def apply_theme(app: QApplication, settings: AppSettings) -> CanvasColors:
    palette = palette_for(settings, app)
    app.setStyleSheet(stylesheet(palette))
    return canvas_colors_for(settings, app)
