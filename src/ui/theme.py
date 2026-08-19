"""
theme.py
Constantes partagées de thème : BoolVar, Styles, Palette.
"""

from PyQt6.QtGui import QFont


class BoolVar:
    """Remplace tk.BooleanVar — conserve l'interface .get() / .set()."""
    def __init__(self, value: bool = False):
        self._value = value
    def get(self) -> bool:
        return self._value
    def set(self, value: bool):
        self._value = value


class Styles:
    class Titre:
        font  = QFont("Segoe UI", 14, QFont.Weight.Bold)
        padx  = 16

    class OngletActif:
        font  = QFont("Segoe UI", 11, QFont.Weight.Bold)

    class Bouton:
        font_standard         = QFont("Segoe UI", 11)
        padx_standard         = 22
        pady_standard         = 12

        font_principal        = QFont("Segoe UI", 12, QFont.Weight.Bold)
        padx_principal        = 16
        pady_principal        = 7

        font_type_notif       = QFont("Segoe UI", 11, QFont.Weight.Bold)
        padx_type_notif       = 10
        pady_type_notif       = 4

        font_type_notifnobold = QFont("Segoe UI", 11)
        padx_type_notifnobold = 10
        pady_type_notifnobold = 4

        font_petit            = QFont("Segoe UI", 11)
        padx_petit            = 12
        pady_petit            = 5

    class EnTete:
        font       = QFont("Segoe UI", 12, QFont.Weight.Bold)
        pady_titre = (14, 2)
        pady_sous  = (0, 10)

    class Info:
        font = QFont("Segoe UI", 11, QFont.Weight.Normal)


class Palette:
    BG        = "#0f1117"
    PANEL     = "#181c26"
    CARD      = "#1a1f2e"
    ACCENT    = "#f5a623"
    GREEN     = "#4caf78"
    RED       = "#e05252"
    BLUE      = "#4a90d9"
    GRAY      = "#6b7280"
    TEXT      = "#e8e8e8"
    FONT_MONO = QFont("Consolas", 10)
    FONT_UI   = QFont("Segoe UI", 10)

    TYPE_COLORS = {
        "combat":  "#e05252",
        "echange": "#f5a623",
        "groupe":  "#4caf78",
        "mp":      "#4a90d9",
        "defi":    "#c97bdb",
        "craft":   "#e8a040",
        "pvp":     "#e05252",
    }
