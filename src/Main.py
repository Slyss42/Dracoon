"""
Main.py
Point d'entrée de Dracoon.
Assemble la classe App depuis les mixins de chaque onglet.
"""

import json
import os
import queue
import threading
import webbrowser
import logging
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "ui"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "core"))

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QStackedWidget, QDialog, QCheckBox,
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QIcon, QPixmap, QImage, QCursor

from core.config import (
    APP_VERSION, WIN32_OK, WINSDK_OK, KEYBOARD_OK, TRAY_OK,
    ICON_PATH, APP_GITHUB, APP_TWITTER, LOG_PATH,
    load_config, save_config, build_config,
    _decode_af_overrides, _decode_char_icons, setup_file_logger,
)
from core.dradidasmode import DradidasManager
from core.shortcuts import _unhook_all, CtrlShiftManager, _release_modifier_keys
from core.windows import unlock_foreground_switching, restore_foreground_lock
from core.icons import restore_all_original_icons, set_window_icon
from core.i18n import t
from core.single_instance import acquire_single_instance
from core.reg_migration import migrate_registry_if_needed

from ui.theme import BoolVar, Styles, Palette

from UI_Tab_Personnages  import TabPersonnagesMixin
from UI_Tab_Raccourcis   import TabRaccourcisMixin
from UI_Tab_Outils       import TabOutilsMixin
from UI_Tab_Parametres   import TabParametresMixin
from UI_Tab_Infos        import TabInfosMixin
from UI_UpdatePopup      import UpdatePopupMixin #supprimer si offline

try:
    import pystray
    from PIL import Image, ImageDraw
except Exception:
    pass

try:
    import keyboard
except Exception:
    pass

# ---------------------------------------------------------------------------
# LOGGING / EXCEPTHOOK
# ---------------------------------------------------------------------------

_TAG_TO_LEVEL = {
    "info":  logging.INFO,
    "ok":    logging.INFO,
    "warn":  logging.WARNING,
    "error": logging.ERROR,
    "dim":   logging.DEBUG,
    "debug": logging.DEBUG,
    "time":  logging.INFO,
}


def _install_excepthooks(logger: logging.Logger):
    def _hook(exc_type, exc, tb):
        logger.error("Uncaught exception", exc_info=(exc_type, exc, tb))
    sys.excepthook = _hook
    try:
        def _thook(args):
            name = args.thread.name if args.thread else "?"
            logger.error("Uncaught exception in thread %s", name,
                         exc_info=(args.exc_type, args.exc_value, args.exc_traceback))
        threading.excepthook = _thook
    except Exception:
        pass

# ---------------------------------------------------------------------------
# Application principale
# ---------------------------------------------------------------------------

class App(
    TabPersonnagesMixin,
    TabRaccourcisMixin,
    TabOutilsMixin,
    TabParametresMixin,
    TabInfosMixin,
    UpdatePopupMixin, #supprimer si offline
    QMainWindow,
):
    # ---- Palette de couleurs ----
    BG        = Palette.BG
    PANEL     = Palette.PANEL
    CARD      = Palette.CARD
    ACCENT    = Palette.ACCENT
    GREEN     = Palette.GREEN
    RED       = Palette.RED
    BLUE      = Palette.BLUE
    GRAY      = Palette.GRAY
    TEXT      = Palette.TEXT
    FONT_MONO = Palette.FONT_MONO
    FONT_UI   = Palette.FONT_UI
    S         = Styles
    TYPE_COLORS = Palette.TYPE_COLORS

    NO_SHORTCUT = None

    # ------------------------------------------------------------------
    # Helpers QSS
    # ------------------------------------------------------------------

    @staticmethod
    def _qss_color(hex_color: str) -> str:
        return f"background-color: {hex_color};"

    def _stylesheet_base(self) -> str:
        return f"""
        QMainWindow, QWidget {{
            background-color: {self.BG};
            color: {self.TEXT};
            font-family: "Segoe UI";
            font-size: 12pt;
        }}
        QScrollArea {{
            border: none;
            background-color: transparent;
        }}
        QScrollBar:vertical {{
            width: 6px;
            background: {self.PANEL};
        }}
        QScrollBar::handle:vertical {{
            background: {self.GRAY};
            border-radius: 3px;
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0;
        }}
        QTextEdit {{
            background-color: {self.CARD};
            color: {self.TEXT};
            border: none;
            font-family: Consolas;
            font-size: 10pt;
        }}
        QLineEdit {{
            background-color: {self.CARD};
            color: {self.TEXT};
            border: 1px solid {self.GRAY};
            border-radius: 4px;
            padding: 4px 8px;
        }}
        QLabel {{
            color: {self.TEXT};
        }}
        QPushButton {{
            background-color: {self.PANEL};
            color: {self.TEXT};
            border: 1px solid {self.GRAY};
            border-radius: 5px;
            padding: 6px 14px;
            font-family: "Segoe UI";
            font-size: 10pt;
        }}
        QPushButton:hover {{
            background-color: {self.CARD};
            border-color: {self.ACCENT};
        }}
        QPushButton:pressed {{
            background-color: {self.ACCENT};
            color: #000;
        }}
        QMenu {{
            background-color: {self.PANEL};
            color: {self.TEXT};
            border: 1px solid {self.GRAY};
        }}
        QMenu::item:selected {{
            background-color: {self.ACCENT};
            color: #000;
        }}
        """

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def __init__(self, _t=None):
        if _t is None:
            _t = lambda label: None   # no-op si appelé sans profiler

        super().__init__()
        _t("super().__init__")
        
        self._logger = setup_file_logger()
        _install_excepthooks(self._logger)
        #self._logger.info("Dracoon %s — démarrage", APP_VERSION)

        self.setWindowTitle(t("app.description"))
        self.setStyleSheet(self._stylesheet_base())
        self.resize(1200, 800)
        self.setMinimumSize(900, 670)
        _t("setWindowTitle / setStyleSheet / resize")

        cfg = load_config()
        self._lang = cfg.get("lang", "fr")
        _t("load_config")

        self._running       = False
        self._loop          = None
        self._n_notifs      = 0
        self._n_matches     = 0
        self._n_focus       = 0
        self._char_order: list[tuple[int, str]] = []
        
        self._drag_idx      = None
        self._row_tops: list[int] = []
        self._row_height    = 48
        self._tray_icon     = None
        self._tray_thread   = None
        self._window_snapshot: dict[int, str] = {}

        raw_next = cfg.get("shortcut_next", "ctrl+right")
        raw_prev = cfg.get("shortcut_prev", "ctrl+left")
        raw_back = cfg.get("shortcut_back", None)
        raw_main = cfg.get("shortcut_main", None)
        self._shortcut_next: str | None = raw_next
        self._shortcut_prev: str | None = raw_prev
        self._shortcut_back: str | None = raw_back
        self._shortcut_main: str | None = raw_main
        self._shortcut_move: str | None = cfg.get("shortcut_move", None)

        self._move_cycle_delay_ms: int = int(cfg.get("move_cycle_delay") or 95)
        self._move_enabled: bool = cfg.get("move_enabled", "1") == "1"

        self._shortcut_dradidas: str | None = cfg.get("shortcut_dradidas", None)
        self._dradidas_enabled: bool = cfg.get("dradidas_enabled", "1") == "1"
        self._dradidas_turns: int = int(cfg.get("dradidas_turns") or 3)

        self._shortcut_ctrl_shift: str | None = cfg.get("shortcut_ctrl_shift", None)
        self._ctrl_shift_manager = CtrlShiftManager()
        self._shortcut_queue = queue.SimpleQueue()
        self._shortcut_worker = threading.Thread(target=self._shortcut_action_worker, daemon=True)
        self._shortcut_worker.start()

        _raw_sadidas = cfg.get("dradidas_sadidas", "[]") or "[]"
        try:
            _sadidas_set = set(json.loads(_raw_sadidas))
        except Exception:
            _sadidas_set = set()

        self._dradidas_manager = DradidasManager(turns=self._dradidas_turns)
        self._dradidas_manager.set_sadidas(_sadidas_set)

        _raw_main = cfg.get("char_main", "") or None
        self._char_main: str | None = _raw_main

        self._char_af_overrides: dict[str, dict[str, bool]] = _decode_af_overrides(
            cfg.get("char_af_overrides", "")
        )

        self._prev_hwnd: int | None = None

        _raw_skip = cfg.get("char_skip_names", "[]") or "[]"
        try:
            self._char_skip_names: set[str] = set(json.loads(_raw_skip))
        except Exception:
            self._char_skip_names: set[str] = set()

        self._char_icons: dict[str, dict] = _decode_char_icons(
            cfg.get("char_icons", "")
        )
        # {pseudo: {"color": "e05252"|None, "portrait": "iop_f"|None}}    

        self._welcome_shown: bool = cfg.get("welcome_shown", "0") == "1"

        self.remove_notif_var       = BoolVar(cfg.get("remove_notif",       "1") == "1")
        self.maximize_on_launch_var = BoolVar(cfg.get("maximize_on_launch", "1") == "1")
        self.move_overlay_var       = BoolVar(cfg.get("move_overlay",       "1") == "1")
        self.shorten_title_var      = BoolVar(cfg.get("shorten_title",      "0") == "1")
        self.check_update_on_launch_var = BoolVar(cfg.get("check_update_on_launch", "1") == "1")
        self.debug_var              = BoolVar(False)
        _t("init variables / config")

        self._central = QWidget()
        self.setCentralWidget(self._central)
        self._root_layout = QVBoxLayout(self._central)
        self._root_layout.setContentsMargins(0, 0, 0, 0)
        self._root_layout.setSpacing(0)
        _t("central widget")

        self._build_ui(_t)
        _t("_build_ui")

        self._init_update_checker() #supprimer si offline
        _t("_init_update_checker") #supprimer si offline


        try:
            _ico = QIcon(ICON_PATH)
            self.setWindowIcon(_ico)
            self._app_icon = _ico
        except Exception:
            pass
        _t("setWindowIcon")

        if not WIN32_OK:
            self.log_msg("pywin32 manquant → pip install pywin32", "error")
        if not WINSDK_OK:
            self.log_msg("winsdk manquant → pip install winsdk", "error")
        if not KEYBOARD_OK:
            self.log_msg("keyboard non chargé → pip install keyboard", "warn")
        if not TRAY_OK:
            self.log_msg("pystray/pillow manquants → pip install pystray pillow", "warn")

        if WIN32_OK and WINSDK_OK:
            self._start()
        _t("_start")

        if KEYBOARD_OK:
             QTimer.singleShot(0, lambda: self._apply_shortcuts(silent=True))
        _t("_apply_shortcuts")

        if self.shorten_title_var.get():
            from core.windows import apply_shorten_titles
            QTimer.singleShot(800, lambda: apply_shorten_titles(True))

        if not self._welcome_shown:
            QTimer.singleShot(200, self._show_welcome_popup)

        QTimer.singleShot(1500, lambda: self._check_for_updates(silent=True)) #supprimer si offline
        _t("__init__ terminé")

    # ------------------------------------------------------------------
    # Événements fenêtre
    # ------------------------------------------------------------------

    def closeEvent(self, event):
        self._quit()
        event.ignore()

    # ------------------------------------------------------------------
    # Quitter
    # ------------------------------------------------------------------

    def _quit(self):

        if self.shorten_title_var.get():
            from core.windows import apply_shorten_titles
            apply_shorten_titles(False)
            restore_all_original_icons()

        self._persist_config()
        _unhook_all()
        _release_modifier_keys()
        restore_foreground_lock()
        self._running = False
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._tray_icon:
            try:
                self._tray_icon.stop()
            except Exception:
                pass
        self.close()
        os._exit(0)

    # ------------------------------------------------------------------
    # Popup de bienvenue
    # ------------------------------------------------------------------

    def _show_welcome_popup(self):
        TIMER_SECONDS = 30

        import subprocess

        popup = QDialog(self)
        popup.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.WindowTitleHint | Qt.WindowType.WindowCloseButtonHint)
        popup.setWindowTitle(t("popup.title"))
        popup.setStyleSheet(f"background-color: {self.BG}; color: {self.TEXT};")
        popup.setMinimumSize(780, 600)
        popup.setWindowModality(Qt.WindowModality.ApplicationModal)

        FONT_TITRE   = QFont("Segoe UI", 14, QFont.Weight.Bold)
        FONT_SECTION = QFont("Segoe UI", 10, QFont.Weight.Bold)
        FONT_BODY    = QFont("Segoe UI", 10)
        FONT_SMALL   = QFont("Segoe UI", 9)
        FONT_BTN     = QFont("Segoe UI", 12, QFont.Weight.Bold)

        root_layout = QVBoxLayout(popup)
        root_layout.setContentsMargins(28, 22, 28, 20)
        root_layout.setSpacing(0)

        # ── Ligne titre + flags ───────────────────────────────────────────────
        top_row = QWidget()
        top_row.setStyleSheet("background: transparent;")
        top_rl = QHBoxLayout(top_row)
        top_rl.setContentsMargins(0, 0, 0, 0)
        top_rl.setSpacing(8)

        lbl_titre = QLabel(t("popup.title"))
        lbl_titre.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        lbl_titre.setStyleSheet(f"color: {self.ACCENT}; background: transparent;")
        top_rl.addWidget(lbl_titre, stretch=1)

        for lang, flag in [("fr", "FR"), ("en", "EN"), ("es", "ES")]:
            btn_flag = QPushButton(flag)
            btn_flag.setFixedSize(50, 28)
            btn_flag.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
            btn_flag.setFlat(True)
            btn_flag.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            btn_flag.setStyleSheet(f"""
                QPushButton {{
                    background: #252b3b;
                    color: {self.GRAY};
                    border: 1px solid #252b3b;
                    border-radius: 4px;
                }}
                QPushButton:hover {{
                    color: {self.TEXT};
                    border-color: {self.ACCENT};
                }}
            """)
            btn_flag.clicked.connect(lambda checked=False, l=lang: self._set_lang(l))
            top_rl.addWidget(btn_flag)

        lbl_lang_hint = QLabel("")
        lbl_lang_hint.setFont(FONT_SMALL)
        lbl_lang_hint.setStyleSheet(f"color: {self.GRAY}; background: transparent;")
        top_rl.addWidget(lbl_lang_hint)
        self._lbl_popup_lang_hint = lbl_lang_hint  # ← stocke la référence

        root_layout.addWidget(top_row)

        # ── Sous-titre ────────────────────────────────────────────────────────
        lbl_sub = QLabel(t("popup.subtitle"))
        lbl_sub.setFont(QFont("Segoe UI", 12))
        lbl_sub.setStyleSheet(f"color: {self.GRAY}; background: transparent;")
        root_layout.addWidget(lbl_sub)
        root_layout.addSpacing(14)

        # ── Helper : ligne item ───────────────────────────────────────────────
        def _item_row(parent_layout, icon: str, title: str, subtitle: str, ms_settings: str = None):
            from PyQt6.QtWidgets import QFrame
            row = QFrame()
            row.setStyleSheet(f"background-color: #131927; border-radius: 6px;")
            rl = QHBoxLayout(row)
            rl.setContentsMargins(14, 10, 14, 10)
            rl.setSpacing(12)

            lbl_icon = QLabel(icon)
            lbl_icon.setFont(QFont("Segoe UI", 14))
            lbl_icon.setFixedWidth(24)
            lbl_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl_icon.setStyleSheet("background: transparent;")
            rl.addWidget(lbl_icon)

            text_col = QWidget()
            text_col.setStyleSheet("background: transparent;")
            tcl = QVBoxLayout(text_col)
            tcl.setContentsMargins(0, 0, 0, 0)
            tcl.setSpacing(2)

            lbl_title = QLabel(title)
            lbl_title.setFont(FONT_SECTION)
            lbl_title.setStyleSheet(f"color: {self.TEXT}; background: transparent;")
            tcl.addWidget(lbl_title)

            lbl_sub = QLabel(subtitle)
            lbl_sub.setFont(FONT_SMALL)
            lbl_sub.setStyleSheet(f"color: {self.GRAY}; background: transparent;")
            tcl.addWidget(lbl_sub)

            rl.addWidget(text_col, stretch=1)

            if ms_settings:
                btn = QPushButton(t("popup.open"))
                btn.setFont(FONT_SMALL)
                btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                btn.setFixedHeight(26)
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: transparent;
                        color: #5b9bd5;
                        border: 1px solid #2e3547;
                        border-radius: 4px;
                        padding: 0px 10px;
                    }}
                    QPushButton:hover {{ color: {self.TEXT}; border-color: #5b9bd5; }}
                """)
                def _open(checked=False, uri=ms_settings, b=btn):
                    subprocess.run(["start", uri], shell=True)
                    b.setText(t("popup.opened"))
                    b.setStyleSheet(f"""
                        QPushButton {{
                            background: transparent;
                            color: #4caf50;
                            border: 1px solid #4caf50;
                            border-radius: 4px;
                            padding: 0px 10px;
                        }}
                    """)
                btn.clicked.connect(_open)
                rl.addWidget(btn)

            parent_layout.addWidget(row)
            parent_layout.addSpacing(4)

        # ── Helper : carte section ────────────────────────────────────────────
        def _section(parent_layout, label: str, color: str, bg: str = None):
            from PyQt6.QtWidgets import QFrame
            card = QFrame()
            card.setStyleSheet(f"background-color: {bg or self.CARD}; border-radius: 8px;")
            cl = QVBoxLayout(card)
            cl.setContentsMargins(16, 14, 16, 10)
            cl.setSpacing(8)

            lbl = QLabel(label)
            lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            lbl.setStyleSheet(f"color: {color}; background: transparent; letter-spacing: 1px;")
            cl.addWidget(lbl)

            parent_layout.addWidget(card)
            parent_layout.addSpacing(10)
            return cl

        # ── Prérequis ─────────────────────────────────────────────────────────
        cl_pre = _section(root_layout, t("popup.prerequis"), self.ACCENT)

        _item_row(cl_pre,
            "🔔",
            t("popup.prerequise1title"),
            t("popup.prerequise1subtitle"),
            "ms-settings:privacy-notifications"
        )
        _item_row(cl_pre,
            "🔔",
            t("popup.prerequise2title"),
            t("popup.prerequise2subtitle"),
            "ms-settings:notifications"
        )
        _item_row(cl_pre,
            "🔔",
            t("popup.prerequise4title"),
            t("popup.prerequise4subtitle"),
            "ms-settings:quiethours"
        )
        _item_row(cl_pre,
            "🔔",
            t("popup.prerequise3title"),
            t("popup.prerequise3subtitle"),
        )
        
        # ── Recommandations ───────────────────────────────────────────────────
        cl_rec = _section(root_layout, t("popup.recommendations"), self.GRAY)

        _item_row(cl_rec,
            "🔇",
            t("popup.recommendation1title"),
            t("popup.recommendation1subtitle"),
            "ms-settings:notifications"
        )
        lbl_tips = QLabel("💡 " + t("popup.recommendation2title"))
        lbl_tips.setFont(FONT_SMALL)
        lbl_tips.setWordWrap(True)
        lbl_tips.setStyleSheet(f"color: {self.GRAY}; background: transparent; padding: 2px 4px;")
        cl_rec.addWidget(lbl_tips)

        # ── Avertissement sécurité ────────────────────────────────────────────
        cl_warn = _section(root_layout, t("popup.security"), self.RED, "#2a1a1a")

        lbl_warn = QLabel(t("popup.security.text"))
        lbl_warn.setFont(FONT_BODY)
        lbl_warn.setWordWrap(True)
        lbl_warn.setStyleSheet(f"color: {self.TEXT}; background: transparent;")
        cl_warn.addWidget(lbl_warn)

        root_layout.addStretch()

        # ── Bouton + checkbox ─────────────────────────────────────────────────
        close_btn = QPushButton(f"{t('popup.validation')} ({TIMER_SECONDS})")
        close_btn.setFont(FONT_BTN)
        close_btn.setEnabled(False)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {self.GRAY};
                color: {self.PANEL};
                border: none;
                border-radius: 5px;
                padding: {self.S.Bouton.pady_principal}px {self.S.Bouton.padx_principal}px;
            }}
            QPushButton:disabled {{
                background-color: {self.GRAY};
                color: {self.PANEL};
            }}
        """)
        root_layout.addWidget(close_btn)
        root_layout.addSpacing(6)

        dont_show_var = BoolVar(False)
        chk = QCheckBox(t("popup.unshow"))
        chk.setFont(FONT_BODY)
        chk.setStyleSheet(f"""
            QCheckBox {{ color: {self.GRAY}; background: transparent; }}
            QCheckBox::indicator {{ background-color: {self.CARD}; border: 1px solid {self.GRAY}; border-radius: 3px; }}
            QCheckBox::indicator:checked {{ background-color: {self.ACCENT}; }}
        """)
        chk.toggled.connect(lambda checked: dont_show_var.set(checked))
        root_layout.addWidget(chk)

        def _close():
            if dont_show_var.get():
                self._welcome_shown = True
                self._persist_config()
            popup.accept()

        def _countdown(remaining: int):
            if remaining > 0:
                close_btn.setText(f"{t('popup.validation')} ({remaining})")
                QTimer.singleShot(1000, lambda: _countdown(remaining - 1))
            else:
                close_btn.setText(t("popup.validation"))
                close_btn.setEnabled(True)
                close_btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {self.ACCENT};
                        color: {self.BG};
                        border: none;
                        border-radius: 5px;
                        padding: {self.S.Bouton.pady_principal}px {self.S.Bouton.padx_principal}px;
                    }}
                    QPushButton:hover {{ background-color: #e0952a; }}
                """)
                close_btn.clicked.connect(_close)

        QTimer.singleShot(1000, lambda: _countdown(TIMER_SECONDS - 1))

        def _on_reject():
            if close_btn.isEnabled():
                _close()

        def _center_popup():
            pw = popup.width()
            ph = popup.height()
            rx = self.x() + (self.width()  - pw) // 2
            ry = self.y() + (self.height() - ph) // 2
            popup.move(rx, ry)
        
        popup.rejected.connect(_on_reject)
        popup.open()
        QTimer.singleShot(0, _center_popup)  # ← après le rendu


        

    # ------------------------------------------------------------------
    # Icône système (tray)
    # ------------------------------------------------------------------

    def _make_tray_image(self):
        try:
            img = Image.open(ICON_PATH).convert("RGBA").resize((64, 64), Image.LANCZOS)
            return img
        except Exception:
            pass
        size = 64
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        d   = ImageDraw.Draw(img)
        d.ellipse([2, 2, size - 2, size - 2], fill=self.ACCENT)
        d.ellipse([8, 8, size - 8, size - 8], fill="#0f1117")
        d.text((16, 18), "DR", fill=self.ACCENT)
        return img

    def _on_header_close(self):
        if TRAY_OK:
            self._minimize_to_tray()
        else:
            self._quit()

    def _minimize_to_tray(self):
        if self._tray_thread and self._tray_thread.is_alive():
            self.hide()
            return
        self.hide()
        menu = pystray.Menu(
            pystray.MenuItem(t("app.tray.afficher"), self._tray_show, default=True),
            pystray.MenuItem(t("app.tray.quitter"),  self._tray_quit),
        )
        self._tray_icon = pystray.Icon(
            "Dracoon", self._make_tray_image(), "Dracoon", menu)
        self._tray_thread = threading.Thread(target=self._tray_icon.run, daemon=True)
        self._tray_thread.start()

    def _tray_show(self, icon=None, item=None):
        if self._tray_icon:
            self._tray_icon.stop()
            self._tray_icon = None
        QTimer.singleShot(0,  self.show)
        QTimer.singleShot(50, self.raise_)

    def _tray_quit(self, icon=None, item=None):
        if self._tray_icon:
            self._tray_icon.stop()
            self._tray_icon = None
        QTimer.singleShot(0, self._quit)

    # ------------------------------------------------------------------
    # Construction de l'UI principale (header + onglets)
    # ------------------------------------------------------------------

    def _build_ui(self, _t=lambda l: None):
        # Header
        from PyQt6.QtWidgets import QFrame
        header = QFrame()
        header.setStyleSheet(f"background-color: {self.PANEL};")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 12, 0, 20)
        header_layout.setSpacing(0)
        _t("_build_ui: header frame créé")

        try:
            from PIL import Image as _PilImg
            _raw  = _PilImg.open(ICON_PATH).convert("RGBA").resize((40, 40), _PilImg.LANCZOS)
            _data = _raw.tobytes("raw", "RGBA")
            _qimg = QImage(_data, 40, 40, QImage.Format.Format_RGBA8888)
            self._header_icon = QPixmap.fromImage(_qimg)
            lbl_icon = QLabel()
            lbl_icon.setPixmap(self._header_icon)
            lbl_icon.setStyleSheet("background: transparent;")
            header_layout.addWidget(lbl_icon)
            header_layout.addSpacing(10)
        except Exception:
            pass
        _t("_build_ui: icône PIL chargée")

        lbl_title = QLabel("DRACOON")
        lbl_title.setFont(self.S.Titre.font)
        lbl_title.setStyleSheet(f"color: {self.ACCENT}; font-size: 16pt; background: transparent;")
        header_layout.addWidget(lbl_title)
        header_layout.addSpacing(self.S.Titre.padx)
        header_layout.addStretch()

        # ── Badge mise à jour ──  #supprimer si offline
        self._update_badge = QPushButton("")
        self._update_badge.setFont(self.S.Bouton.font_petit)
        self._update_badge.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._update_badge.setFlat(True)
        self._update_badge.setVisible(False)
        self._update_badge.setStyleSheet(f"""
            QPushButton {{
                background-color: {self.CARD};
                color: {self.ACCENT};
                border: 1px solid {self.ACCENT};
                border-radius: 12px;
                padding: 4px 12px;
            }}
            QPushButton:hover {{ background-color: {self.ACCENT}; color: {self.BG}; }}
        """)
        self._update_badge.clicked.connect(
            lambda: self._show_update_popup(self._last_update_info)
            if getattr(self, "_last_update_info", None) else None
        )
        header_layout.addWidget(self._update_badge)
        header_layout.addSpacing(12)
        #supprimer si offline (fin badge)        

        # ── Drapeaux ──
        flags_widget = QWidget()
        flags_widget.setStyleSheet("background: transparent;")
        flags_layout = QHBoxLayout(flags_widget)
        flags_layout.setContentsMargins(0, 0, 0, 0)
        flags_layout.setSpacing(6)

        for lang, flag in [("fr", "FR"), ("en", "EN"), ("es", "ES")]:
            btn_flag = QPushButton(flag)
            btn_flag.setFixedSize(50, 28)
            btn_flag.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
            btn_flag.setFlat(True)
            btn_flag.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            btn_flag.setStyleSheet(f"""
                QPushButton {{
                    background: #252b3b;
                    color: {self.GRAY};
                    border: 1px solid #252b3b;
                    border-radius: 4px;
                }}
                QPushButton:hover {{
                    color: {self.TEXT};
                    border-color: {self.ACCENT};
                }}
            """)

            btn_flag.clicked.connect(lambda checked=False, l=lang: self._set_lang(l))
            flags_layout.addWidget(btn_flag)

        header_layout.addWidget(flags_widget)

        self._lbl_lang_hint = QLabel("")
        self._lbl_lang_hint.setFont(self.S.Info.font)
        self._lbl_lang_hint.setStyleSheet(f"color: {self.GRAY}; background: transparent;")
        self._lbl_lang_hint.setContentsMargins(4, 0, 0, 0)
        header_layout.addWidget(self._lbl_lang_hint)

        header_layout.addSpacing(20)  # espace avant le ⊟

        btn_close = QPushButton("⊟")
        btn_close.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        btn_close.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_close.setFlat(True)
        btn_close.setStyleSheet(f"""
            QPushButton {{
                color: {self.ACCENT};
                background-color: {self.PANEL};
                border: none;
                padding: 0px 14px;
                font-size: 24pt;
            }}
            QPushButton:hover {{ background-color: {self.CARD}; }}
        """)
        btn_close.clicked.connect(self._on_header_close)
        header_layout.addWidget(btn_close)
        self._root_layout.addWidget(header)

        # Barre d'onglets
        tab_bar = QFrame()
        tab_bar.setStyleSheet(f"background-color: {self.PANEL};")
        tab_bar_layout = QHBoxLayout(tab_bar)
        tab_bar_layout.setContentsMargins(0, 0, 0, 0)
        tab_bar_layout.setSpacing(0)

        self._tab_btns:   dict[str, QPushButton] = {}
        self._tab_frames: dict[str, QWidget]     = {}
        self._tab_bars:   dict[str, QFrame]      = {}

        # APRÈS :
        for key, label in [("personnages", t("app.tab.personnages")),
                           ("raccourcis", t("app.tab.raccourcis")),
                           ("outils", t("app.tab.outils")),
                           ("parametres", t("app.tab.parametres")),
                           ("info", t("app.tab.info"))]:
            container = QWidget()
            container.setStyleSheet("background: transparent;")
            c_layout = QVBoxLayout(container)
            c_layout.setContentsMargins(0, 0, 0, 0)
            c_layout.setSpacing(0)

            btn = QPushButton(label)
            btn.setFont(self.S.Bouton.font_standard)
            btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            btn.setFlat(True)
            btn.setStyleSheet(self._tab_btn_style(active=False))
            btn.clicked.connect(lambda checked=False, k=key: self._switch_tab(k))
            c_layout.addWidget(btn)

            bar = QFrame()
            bar.setFixedHeight(3)
            bar.setStyleSheet(f"background-color: transparent; border: none;")
            c_layout.addWidget(bar)

            tab_bar_layout.addWidget(container)
            self._tab_btns[key] = btn
            self._tab_bars[key] = bar  # stocker la référence à la barre

        tab_bar_layout.addStretch()
        self._root_layout.addWidget(tab_bar)

        # Zone de contenu
        self._content = QStackedWidget()
        self._content.setStyleSheet(f"background-color: {self.BG};")
        self._root_layout.addWidget(self._content, stretch=1)
        _t("_build_ui: QStackedWidget créé")

        self._tabs_built = set()
        self._build_tab_now("personnages")
        _t("_build_ui: onglet personnages builté")
        self._switch_tab("personnages")
        _t("_build_ui: switch_tab fait")

    def _tab_btn_style(self, active: bool) -> str:
        fg          = self.ACCENT if active else self.GRAY
        bg          = self.BG     if active else self.PANEL
        font_weight = "bold" if active else "normal"
        font_size   = (self.S.OngletActif.font.pointSize() if active
                       else self.S.Bouton.font_standard.pointSize())
        return f"""
            QPushButton {{
                color: {fg};
                background-color: {bg};
                border: none;
                font-family: "Segoe UI";
                font-size: {font_size}pt;
                font-weight: {font_weight};
                padding: {self.S.Bouton.pady_standard}px {self.S.Bouton.padx_standard}px;
            }}
            QPushButton:hover {{
                background-color: {self.BG};
                color: {self.ACCENT};
            }}
        """

    def _switch_tab(self, key: str):
        try:
            self._build_tab_now(key)
        except Exception as e:
            import traceback
            traceback.print_exc()
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Erreur onglet", f"{key} :\n{e}")
            return
        for k, btn in self._tab_btns.items():
            btn.setStyleSheet(self._tab_btn_style(active=(k == key)))
            self._tab_bars[k].setStyleSheet(
                f"background-color: {self.ACCENT}; border: none;"
                if k == key
                else "background-color: transparent; border: none;"
            )
        self._content.setCurrentWidget(self._tab_frames[key])

    def _build_tab_now(self, key: str):
        if key in self._tabs_built:
            return
        builders = {
            "personnages": self._build_tab_personnages,
            "raccourcis":  self._build_tab_raccourcis,
            "outils":      self._build_tab_outils,
            "parametres":  self._build_tab_parametres,
            "info":        self._build_tab_info,
        }
        builders[key]()
        self._tabs_built.add(key)

    # ------------------------------------------------------------------
    # Persistance de la configuration
    # ------------------------------------------------------------------

    def _persist_config(self):
        save_config(build_config(
            self._shortcut_next, self._shortcut_prev, self._shortcut_back,
            self._char_af_overrides, self._shortcut_main, self._char_main,
            self._welcome_shown, self._char_skip_names,
            self.remove_notif_var.get(),
            self.maximize_on_launch_var.get(),
            self._shortcut_move,
            self.move_overlay_var.get(),
            self._move_cycle_delay_ms,
            self._move_enabled,
            dradidas_enabled   = self._dradidas_enabled,
            dradidas_turns     = self._dradidas_turns,
            dradidas_sadidas   = self._dradidas_manager.sadida_pseudos,
            shortcut_dradidas  = self._shortcut_dradidas,
            shortcut_ctrl_shift = self._shortcut_ctrl_shift,
            lang                = self._lang,
            shorten_title       = self.shorten_title_var.get(),
            char_icons          = self._char_icons,
            check_update_on_launch = self.check_update_on_launch_var.get(),
        ))

    def _set_lang(self, lang: str):
        self._lang = lang
        self._persist_config()
        self._lbl_lang_hint.setText("↺ " +t("app.redemarrez"))
        if hasattr(self, "_lbl_popup_lang_hint"):  # ← si la popup est ouverte
            self._lbl_popup_lang_hint.setText("↺ " + t("app.redemarrez"))


# ------------------------------------------------------------------
# log_msg — stub silencieux (plus d'onglet dédié, appels conservés)
# ------------------------------------------------------------------

    def log_msg(self, msg: str, tag: str = "info"):
        level = _TAG_TO_LEVEL.get(tag, logging.INFO) if not tag.startswith("type_") else logging.INFO
        try:
            self._logger.log(level, msg)
        except Exception:
            pass 

# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    import time
    from core.i18n import load_translations
    from core.config import load_config, setup_file_logger

    _T0 = time.perf_counter()
    def _t(label):
        print(f"[PERF] {label:45s} {(time.perf_counter() - _T0)*1000:7.1f} ms")

    _t("début __main__")

    logger = setup_file_logger()
    _t("setup_file_logger")

    # --- Migration registre DofusRetro -> Dracoon (une seule fois, voir reg_migration.py) ---
    migrate_registry_if_needed(logger=logger)
    _t("migrate_registry_if_needed")

    load_translations(load_config().get("lang", "fr"))
    _t("load_translations")

    # --- Mutex : une seule instance ---
    if not acquire_single_instance(window_title=t("app.description")):
        sys.exit(0)
    _t("acquire_single_instance")

    logger.info("──────── Dracoon %s — démarrage (instance principale) ────────", APP_VERSION)

    app = QApplication(sys.argv)
    _t("QApplication()")

    app.setStyle("Fusion")
    _t("setStyle Fusion")

    # import traceback
    # try:
    #     window = App(_t)
    #     _t("App() terminé")
    # except Exception as e:
    #     traceback.print_exc()
    #     input("Appuie sur Entrée pour quitter...")
    #     sys.exit(1)

    # window.show()
    # _t("window.show()")
    # sys.exit(app.exec())

    window = App(_t)          # on passe _t à App pour mesurer l'intérieur
    _t("App() terminé")

    window.show()
    _t("window.show()")

    unlock_foreground_switching()
    _t("unlock_foreground_switching()")

    sys.exit(app.exec())    
