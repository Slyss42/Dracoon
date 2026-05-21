"""
UI_Tab_Personnages.py
Onglet « Personnages » — liste drag & drop + moteur AutoFocus intégral.

Remplace UI_Tab_Autofocus.py (peut être supprimé).
"""

import asyncio
import threading
import time

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QScrollArea, QFrame, QApplication,
)
from PyQt6.QtCore import Qt, QTimer, QPoint, QEvent, QObject
from PyQt6.QtGui import QFont, QCursor

from logic import (
    WIN32_OK, WINSDK_OK,
    NOTIF_TYPES,
    get_dofus_windows, reorder_with_ungroup_regroup,
    focus_dofus_window, list_dofus_windows,
    extract_pseudo_from_title, _is_dofus_pid, t,
    load_order_presets, save_order_preset, delete_order_preset, apply_order_preset,
)

try:
    import win32gui, win32process
except Exception:
    pass

try:
    import winsdk.windows.ui.notifications.management as winman
    import winsdk.windows.ui.notifications as winnot
except Exception:
    pass

try:
    import win32con
except Exception:
    pass


# Ordre d'affichage des types de notification (même ordre que l'ancien autofocus)
_TYPE_ORDER = [
    ("combat",  "⚔️"),
    ("mp",      "💬"),
    ("groupe",  "👥"),
    ("echange", "🔄"),
    ("craft",   "🔨"),
    ("defi",    "🏆"),
    ("pvp",     "🛡️"),
]



class TabPersonnagesMixin:
    """
    Mixin unique pour la classe App.
    Fournit :
      - _build_tab_personnages, refresh_characters, _rebuild_char_list, _create_char_row
      - drag & drop, _save_order
      - _toggle_char_skip, _toggle_char_main
      - _toggle_type, _toggle_char_af_type, _update_global_btn_style
      - log_msg (stub silencieux — les logs ne sont plus affichés dans l'UI)
      - _start, _stop, _run_async_loop, _watch_windows, _listen  (moteur AF complet)
      - _rebuild_af_char_list (compat)
    """

    # ------------------------------------------------------------------
    # log_msg — stub silencieux (plus d'onglet dédié, appels conservés)
    # ------------------------------------------------------------------

    def log_msg(self, msg: str, tag: str = "info"):
        """Affiche dans la console ; l'UI log a été supprimée."""
        print(f"[{tag.upper()}] {msg}")

    # ------------------------------------------------------------------
    # Construction de l'onglet
    # ------------------------------------------------------------------

    def _build_tab_personnages(self):
        from Main import _BoolVar

        f = QWidget()
        f.setStyleSheet(f"background-color: {self.BG};")
        self._tab_frames["personnages"] = f
        self._content.addWidget(f)

        outer_layout = QVBoxLayout(f)
        outer_layout.setContentsMargins(0, 10, 0, 10)
        outer_layout.setSpacing(0)

        # ── En-tête ──────────────────────────────────────────────────
        top = QWidget()
        top.setStyleSheet(f"background-color: {self.BG};")
        top_layout = QHBoxLayout(top)
        top_layout.setContentsMargins(16, 12, 16, 8)
        top_layout.setSpacing(0)

        left = QWidget()
        left.setStyleSheet(f"background-color: {self.BG};")
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(2)

        top_layout.addWidget(left, stretch=1)
        outer_layout.addWidget(top)

        # ── Ligne d'en-têtes colonnes ────────────────────────────────
        ##outer_layout.addWidget(self._build_col_header())

        # ── Ligne globale AutoFocus ──────────────────────────────────
        # Initialiser type_vars ici avant _build_global_af_row
        self.type_vars: dict = {}
        self.type_btns: dict = {}
        for key, _ in _TYPE_ORDER:
            self.type_vars[key] = _BoolVar(True)


        outer_layout.addWidget(self._build_col_header_with_af())
        
        # ── Zone scrollable des personnages ──────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"""
            QScrollArea {{ background-color: {self.BG}; border: none; }}
            QScrollBar:vertical {{ width: 6px; background: {self.PANEL}; }}
            QScrollBar::handle:vertical {{ background: {self.GRAY}; border-radius: 3px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """)

        self._char_inner = QWidget()
        self._char_inner.setStyleSheet(f"background-color: {self.BG};")
        self._char_inner_layout = QVBoxLayout(self._char_inner)
        self._char_inner_layout.setContentsMargins(14, 0, 14, 0)
        self._char_inner_layout.setSpacing(4)
        self._char_inner_layout.addStretch()

        scroll.setWidget(self._char_inner)
        outer_layout.addWidget(scroll, stretch=1)
        self._char_scroll = scroll

        # ── Légende ──────────────────────────────────────────────────
        outer_layout.addWidget(self._build_legend())

        # ── Zone presets + footer ─────────────────────────────────────
        outer_layout.addWidget(self._build_preset_zone())

        # ── Compteurs internes pour _listen (remplacent les lbl_* supprimés) ──
        self._n_notifs  = getattr(self, "_n_notifs",  0)
        self._n_matches = getattr(self, "_n_matches", 0)
        self._n_focus   = getattr(self, "_n_focus",   0)

    # ------------------------------------------------------------------
    # Zone presets + bouton enregistrer l'ordre
    # ------------------------------------------------------------------

    def _build_preset_zone(self) -> QWidget:
        """
        Footer : une seule ligne, tout aligné à droite.
          lien discret "Enregistrer le preset" | dropdown | bouton jaune
        """
        zone = QWidget()
        zone.setStyleSheet(f"background-color: {self.BG};")
        row_layout = QHBoxLayout(zone)
        row_layout.setContentsMargins(14, 6, 14, 10)
        row_layout.setSpacing(10)

        row_layout.addStretch()

        # ── Lien discret "Enregistrer le preset" ─────────────────────
        lnk = QPushButton(t("tab.personnages.savepreset"))
        lnk.setFont(QFont("Segoe UI", 10))
        lnk.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        lnk.setFlat(True)
        lnk.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {self.GRAY};
                border: none;
                padding: 0;
                text-decoration: underline;
            }}
            QPushButton:hover {{ color: {self.TEXT}; }}
        """)
        lnk.clicked.connect(self._open_preset_popup)
        row_layout.addWidget(lnk)

        # ── Dropdown presets ──────────────────────────────────────────
        self._preset_dropdown_btn = QPushButton(t("tab.personnages.loadpreset"))
        self._preset_dropdown_btn.setFont(QFont("Segoe UI", 10))
        self._preset_dropdown_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._preset_dropdown_btn.setFlat(True)
        self._preset_dropdown_btn.setFixedHeight(32)
        self._preset_dropdown_btn.setMinimumWidth(250)
        self._preset_dropdown_btn.setStyleSheet(f"""
            QPushButton {{
                background: {self.CARD};
                color: {self.GRAY};
                border: 1px solid #2e3547;
                border-radius: 4px;
                padding: 0px 12px;
            }}
            QPushButton:hover {{ color: {self.TEXT}; border-color: {self.ACCENT}; }}
        """)
        self._preset_dropdown_btn.clicked.connect(self._toggle_preset_dropdown)
        row_layout.addWidget(self._preset_dropdown_btn)

        # ── Bouton jaune Enregistrer l'ordre ─────────────────────────
        btn_save = QPushButton(t("tab.personnages.saveorder"))
        btn_save.setFont(self.S.Bouton.font_principal)
        btn_save.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_save.setStyleSheet(f"""
            QPushButton {{
                background-color: {self.ACCENT};
                color: {self.BG};
                border: none;
                border-radius: 5px;
                padding: {self.S.Bouton.pady_principal}px {self.S.Bouton.padx_principal}px;
                font-size: 12pt;
            }}
            QPushButton:hover {{ background-color: #e0952a; }}
        """)
        btn_save.clicked.connect(self._save_order)
        row_layout.addWidget(btn_save)

        # ── Menu déroulant (positionné dynamiquement) ─────────────────
        # Construit une fois, caché, réancré au clic
        self._preset_menu = QFrame(self)
        self._preset_menu.setObjectName("presetMenu")
        self._preset_menu.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.NoDropShadowWindowHint)
        self._preset_menu.setStyleSheet(f"""
            QFrame#presetMenu {{
                background-color: {self.CARD};
                border: 1px solid #2e3547;
                border-radius: 6px;
            }}
            QFrame#presetMenu QLabel {{
                border: none;
                background: transparent;
            }}
        """)
        self._preset_menu.setMinimumWidth(250)
        self._preset_menu_layout = QVBoxLayout(self._preset_menu)
        self._preset_menu_layout.setContentsMargins(0, 4, 0, 4)
        self._preset_menu_layout.setSpacing(0)
        self._preset_menu.hide()

        def _focus_out(e):
            self._preset_menu.hide()
        self._preset_menu.focusOutEvent = _focus_out

        self._rebuild_preset_menu()

        return zone

    def _toggle_preset_dropdown(self):
        """Affiche / cache le menu au-dessus du bouton dropdown."""
        if self._preset_menu.isVisible():
            self._preset_menu.hide()
            return
        self._rebuild_preset_menu()
        btn = self._preset_dropdown_btn
        self._preset_menu.setFixedWidth(btn.width())
        self._preset_menu.adjustSize()
        pos = btn.mapToGlobal(btn.rect().topLeft())
        pos.setY(pos.y() - self._preset_menu.height())
        self._preset_menu.move(pos)
        self._preset_menu.show()
        self._preset_menu.raise_()
        self._preset_menu.setFocus()

    def _rebuild_preset_menu(self):
        """Vide et repeuple le menu déroulant."""
        while self._preset_menu_layout.count():
            item = self._preset_menu_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        presets = load_order_presets()

        if not presets:
            lbl = QLabel(t("tab.personnages.nopreset"))
            lbl.setFont(QFont("Segoe UI", 10))
            lbl.setStyleSheet(f"color: {self.GRAY}; background: transparent; padding: 8px 14px;")
            self._preset_menu_layout.addWidget(lbl)
        else:
            for name, pseudos in presets.items():
                row = self._build_preset_menu_row(name, pseudos)
                self._preset_menu_layout.addWidget(row)

        self._preset_menu.adjustSize()

    def _build_preset_menu_row(self, name: str, pseudos: list[str]) -> QWidget:
        """Une ligne dans le menu : nom (fixe) | compteur (fixe) | ✕ (toujours visible, rouge au survol)."""
        nb_connected = sum(1 for _, p in self._char_order if p in pseudos)

        # Colonnes fixes :  nom=150px  compteur=38px  croix=24px
        NAME_W  = 150
        COUNT_W = 38
        DEL_W   = 24

        row = QWidget()
        row.setFixedHeight(32)
        row.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        row.setStyleSheet("background: transparent;")
        rl = QHBoxLayout(row)
        rl.setContentsMargins(12, 0, 8, 0)
        rl.setSpacing(0)

        lbl_name = QLabel(name)
        lbl_name.setFont(QFont("Segoe UI", 10))
        lbl_name.setFixedWidth(NAME_W)
        lbl_name.setStyleSheet(f"color: {self.TEXT}; background: transparent;")
        lbl_name.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        rl.addWidget(lbl_name)

        lbl_count = QLabel(f"{nb_connected}/{len(pseudos)}")
        lbl_count.setFont(QFont("Segoe UI", 9))
        lbl_count.setFixedWidth(COUNT_W)
        lbl_count.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        lbl_count.setStyleSheet(f"color: {self.GRAY}; background: transparent;")
        lbl_count.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        rl.addWidget(lbl_count)

        rl.addSpacing(8)

        lbl_del = QLabel("✕")
        lbl_del.setFont(QFont("Segoe UI", 9))
        lbl_del.setFixedSize(DEL_W, DEL_W)
        lbl_del.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_del.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        lbl_del.setStyleSheet(f"color: {self.GRAY}; background: transparent; border-radius: 3px;")
        rl.addWidget(lbl_del)

        # Clic sur la ligne : zone droite (croix) → supprimer, reste → appliquer
        del_x_start = 12 + NAME_W + COUNT_W + 8  # offset gauche de la croix

        def _mouse_press(e):
            if e.position().x() >= lbl_del.geometry().x():
                self._delete_preset(name)
            else:
                self._apply_preset(name, pseudos)

        row.mousePressEvent = _mouse_press

        # Hover sur toute la ligne → fond + croix blanche, rouge si dans zone croix
        def _enter(e):
            row.setStyleSheet("background: #252b3b;")
            lbl_del.setStyleSheet(f"color: {self.TEXT}; background: transparent; border-radius: 3px;")

        def _leave(e):
            row.setStyleSheet("background: transparent;")
            lbl_del.setStyleSheet(f"color: {self.GRAY}; background: transparent; border-radius: 3px;")

        def _mouse_move(e):
            if e.position().x() >= del_x_start:
                lbl_del.setStyleSheet(f"color: {self.RED}; background: #3a1a1a; border-radius: 3px;")
            else:
                lbl_del.setStyleSheet(f"color: {self.TEXT}; background: transparent; border-radius: 3px;")

        row.enterEvent = _enter
        row.leaveEvent = _leave
        row.mouseMoveEvent = _mouse_move
        row.setMouseTracking(True)

        return row

    # ------------------------------------------------------------------
    # Popup "Nom du preset"
    # ------------------------------------------------------------------

    def _open_preset_popup(self):
        from PyQt6.QtWidgets import QDialog, QLineEdit, QDialogButtonBox

        if not self._char_order:
            return

        dlg = QDialog(self)
        dlg.setWindowTitle(t("tab.personnages.savepreset"))
        dlg.setModal(True)
        dlg.setFixedSize(320, 140)
        dlg.setStyleSheet(f"""
            QDialog {{
                background-color: {self.PANEL};
            }}
        """)

        # Centrer sur la fenêtre principale
        rx = self.x() + (self.width()  - 320) // 2
        ry = self.y() + (self.height() - 140) // 2
        dlg.move(rx, ry)

        dlg_layout = QVBoxLayout(dlg)
        dlg_layout.setContentsMargins(20, 18, 20, 16)
        dlg_layout.setSpacing(14)

        lbl = QLabel(t("tab.personnages.savepresetname"))
        lbl.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        lbl.setStyleSheet(f"color: {self.TEXT}; background: transparent;")
        dlg_layout.addWidget(lbl)

        field = QLineEdit()
        field.setPlaceholderText(t("tab.personnages.savepresetexample"))
        field.setMaxLength(24)
        field.setFont(QFont("Segoe UI", 11))
        field.setFixedHeight(32)
        field.setStyleSheet(f"""
            QLineEdit {{
                background-color: {self.CARD};
                color: {self.TEXT};
                border: 1px solid #2e3547;
                border-radius: 4px;
                padding: 4px 10px;
            }}
            QLineEdit:focus {{ border-color: {self.ACCENT}; }}
        """)
        dlg_layout.addWidget(field)

        btns_row = QWidget()
        btns_row.setStyleSheet("background: transparent;")
        btns_layout = QHBoxLayout(btns_row)
        btns_layout.setContentsMargins(0, 0, 0, 0)
        btns_layout.setSpacing(8)
        btns_layout.addStretch()

        btn_cancel = QPushButton(t("tab.personnages.savepresetbutton2"))
        btn_cancel.setFont(self.S.Bouton.font_petit)
        btn_cancel.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_cancel.setFlat(True)
        btn_cancel.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {self.GRAY};
                border: 1px solid #2e3547;
                border-radius: 4px;
                padding: 5px 14px;
            }}
            QPushButton:hover {{ color: {self.TEXT}; }}
        """)
        btn_cancel.clicked.connect(dlg.reject)
        btns_layout.addWidget(btn_cancel)

        btn_ok = QPushButton(t("tab.personnages.savepresetbutton1"))
        btn_ok.setFont(self.S.Bouton.font_petit)
        btn_ok.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_ok.setStyleSheet(f"""
            QPushButton {{
                background-color: {self.ACCENT};
                color: {self.BG};
                border: none;
                border-radius: 4px;
                padding: 5px 14px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background-color: #e0952a; }}
        """)

        def _confirm():
            name = field.text().strip()
            if not name:
                return
            pseudos = [p for _, p in self._char_order]
            save_order_preset(name, pseudos)
            self._rebuild_preset_menu()
            dlg.accept()

        btn_ok.clicked.connect(_confirm)
        field.returnPressed.connect(_confirm)
        btns_layout.addWidget(btn_ok)

        dlg_layout.addWidget(btns_row)
        field.setFocus()
        dlg.exec()

    # ------------------------------------------------------------------
    # Actions preset
    # ------------------------------------------------------------------

    def _apply_preset(self, name: str, pseudos: list[str]):
        self._char_order = apply_order_preset(pseudos, self._char_order)
        self._preset_menu.hide()
        self._preset_dropdown_btn.setText(f"{name}  ▾")
        self._preset_dropdown_btn.setStyleSheet(f"""
            QPushButton {{
                background: {self.CARD};
                color: {self.TEXT};
                border: 1px solid #2e3547;
                border-radius: 4px;
                padding: 0px 12px;
            }}
            QPushButton:hover {{ color: {self.TEXT}; border-color: {self.ACCENT}; }}
        """)
        self._rebuild_char_list()

    def _delete_preset(self, name: str):
        delete_order_preset(name)
        self._rebuild_preset_menu()
        # Remettre le label par défaut si c'était le preset affiché
        if name in self._preset_dropdown_btn.text():
            self._preset_dropdown_btn.setText("Charger un preset…  ▾")
            self._preset_dropdown_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {self.CARD};
                    color: {self.GRAY};
                    border: 1px solid #2e3547;
                    border-radius: 4px;
                    padding: 0px 12px;
                }}
                QPushButton:hover {{ color: {self.TEXT}; border-color: {self.ACCENT}; }}
            """)
    def _reset_preset_btn(self):
        self._preset_dropdown_btn.setText(t("tab.personnages.loadpreset"))
        self._preset_dropdown_btn.setStyleSheet(f"""
            QPushButton {{
                background: {self.CARD};
                color: {self.GRAY};
                border: 1px solid #2e3547;
                border-radius: 4px;
                padding: 0px 12px;
            }}
            QPushButton:hover {{ color: {self.TEXT}; border-color: {self.ACCENT}; }}
        """)        

    # ------------------------------------------------------------------
    # En-tête des colonnes : Personnage | ⚡ Autofocus | Actions
    # ------------------------------------------------------------------

    def _build_col_header_with_af(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background: transparent;")
        layout = QHBoxLayout(w)
        layout.setContentsMargins(24, 4, 24, 4)
        layout.setSpacing(0)

        # ── Gauche ────────────────────────────────────────────────────
        lbl_perso = QLabel(t("tab.personnages.1c"))
        lbl_perso.setFont(QFont("Segoe UI", 9))
        lbl_perso.setStyleSheet(f"color: {self.GRAY}; background: transparent;")
        lbl_perso.setFixedWidth(340)
        lbl_perso.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl_perso)

        layout.addStretch()

        # ── Centre ────────────────────────────────────────────────────
        center = QWidget()
        center.setStyleSheet("background: transparent;")
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(2)
        center_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        lbl_af = QLabel(t("tab.personnages.2c"))
        lbl_af.setFont(QFont("Segoe UI", 9))
        lbl_af.setStyleSheet(f"color: {self.GRAY}; background: transparent;")
        lbl_af.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        center_layout.addWidget(lbl_af)

        btn_row = QWidget()
        btn_row.setStyleSheet("background: transparent;")
        brl = QHBoxLayout(btn_row)
        brl.setContentsMargins(0, 0, 0, 0)
        brl.setSpacing(3)
        brl.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        for key, icon in _TYPE_ORDER:
            btn = QPushButton(icon)
            btn.setFont(self.S.Bouton.font_type_notifnobold)
            btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            btn.setFlat(True)
            btn.setFixedSize(30, 26)
            self._style_global_af_btn(btn, state="active")
            btn.clicked.connect(lambda checked=False, k=key: self._toggle_type(k))
            brl.addWidget(btn)
            self.type_btns[key] = btn

        center_layout.addWidget(btn_row)
        layout.addWidget(center)

        layout.addStretch()

        # ── Droite ────────────────────────────────────────────────────
        lbl_actions = QLabel(t("tab.personnages.3c"))
        lbl_actions.setFont(QFont("Segoe UI", 9))
        lbl_actions.setStyleSheet(f"color: {self.GRAY}; background: transparent;")
        lbl_actions.setFixedWidth(280)
        lbl_actions.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        lbl_actions.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl_actions)

        return w
    # ------------------------------------------------------------------
    # Légende des types
    # ------------------------------------------------------------------

    def _get_type_labels(self) -> dict:
        return {
            "combat":  t("autofocus.combat"),
            "mp":      t("autofocus.message"),
            "groupe":  t("autofocus.group.guild"),
            "echange": t("autofocus.echange"),
            "craft":   t("autofocus.craft"),
            "defi":    t("autofocus.defi"),
            "pvp":     t("autofocus.pvp"),
        }

    def _build_legend(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet(f"background: transparent; border-top: 1px solid {self.CARD};")
        layout = QHBoxLayout(w)
        layout.setContentsMargins(14, 6, 14, 6)
        layout.setSpacing(12)

        for key, icon in _TYPE_ORDER:
            item = QWidget()
            item.setStyleSheet("background: transparent;")
            il = QHBoxLayout(item)
            il.setContentsMargins(0, 0, 0, 0)
            il.setSpacing(3)

            lbl_icon = QLabel(icon)
            lbl_icon.setFont(QFont("Segoe UI", 10))
            lbl_icon.setStyleSheet("background: transparent;")
            il.addWidget(lbl_icon)

            lbl_txt = QLabel(self._get_type_labels()[key])
            lbl_txt.setFont(QFont("Segoe UI", 9))
            lbl_txt.setStyleSheet(f"color: {self.GRAY}; background: transparent;")
            il.addWidget(lbl_txt)

            layout.addWidget(item)

        layout.addStretch()
        return w

    # ------------------------------------------------------------------
    # Rafraîchissement de la liste
    # ------------------------------------------------------------------

    def refresh_characters(self):
        if getattr(self, "_preset_needs_reset", False):
            self._preset_needs_reset = False
            if hasattr(self, "_preset_dropdown_btn"):
                self._reset_preset_btn()
        if not WIN32_OK:
            return
        windows  = get_dofus_windows()
        win_map  = {h: p for h, p in windows}
        known    = set(win_map.keys())
        new_order = [(h, win_map[h]) for h, _ in self._char_order if h in known]
        existing = {h for h, _ in new_order}
        for h, p in windows:
            if h not in existing:
                new_order.append((h, p))
        self._char_order = new_order       
        self._rebuild_char_list()

    def _rebuild_char_list(self, highlight_idx: int | None = None):
        while self._char_inner_layout.count() > 1:
            item = self._char_inner_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._row_tops = []

        if not self._char_order:
            row = QWidget()
            row.setStyleSheet("background: transparent;")
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(24, 30, 24, 30)
            row_layout.setSpacing(0)

            spacer_left = QWidget()
            spacer_left.setFixedWidth(190)
            spacer_left.setStyleSheet("background: transparent;")
            row_layout.addWidget(spacer_left)

            row_layout.addStretch()

            lbl = QLabel(t("tab.personnages.notfound"))
            lbl.setFont(QFont("Segoe UI", 10))
            lbl.setStyleSheet(f"color: {self.GRAY}; background: transparent;")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            row_layout.addWidget(lbl)

            row_layout.addStretch()

            spacer_right = QWidget()
            spacer_right.setFixedWidth(280)
            spacer_right.setStyleSheet("background: transparent;")
            row_layout.addWidget(spacer_right)

            self._char_inner_layout.insertWidget(0, row)
            return

        for i, (hwnd, pseudo) in enumerate(self._char_order):
            self._create_char_row(i, hwnd, pseudo, i == highlight_idx)

        if hasattr(self, "_dradidas_chars_layout"):
            self._rebuild_dradidas_char_list()

        QApplication.instance().processEvents()
        self._update_row_tops()

    def _update_row_tops(self):
        self._row_tops = []
        for i in range(self._char_inner_layout.count()):
            item = self._char_inner_layout.itemAt(i)
            if item and item.widget():
                w = item.widget()
                if w.height() > 1:
                    self._row_tops.append(w.mapTo(self._char_inner, QPoint(0, 0)).y())
                    self._row_height = w.height() + 4

    # ------------------------------------------------------------------
    # Création d'une ligne de personnage
    # ------------------------------------------------------------------

    def _create_char_row(self, idx: int, hwnd: int, pseudo: str, hl: bool = False):
        is_skipped = pseudo in self._char_skip_names
        bg     = "#2a3350" if hl else self.CARD
        border = f"border: 2px solid {self.ACCENT};" if hl else "border: none;"

        row = QFrame()
        row.setStyleSheet(f"""
            QFrame {{
                background-color: {bg};
                border-radius: 6px;
                {border}
            }}
        """)
        row.setCursor(QCursor(Qt.CursorShape.SizeAllCursor))

        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(10, 6, 10, 6)
        row_layout.setSpacing(0)

        # ── Drag handle ──────────────────────────────────────────────
        lbl_handle = QLabel("⠿")
        lbl_handle.setFont(QFont("Segoe UI", 15))
        lbl_handle.setFixedWidth(16)
        lbl_handle.setStyleSheet(
            f"color: {self.ACCENT if hl else self.GRAY}; background: transparent; border: none;"
        )
        lbl_handle.setCursor(QCursor(Qt.CursorShape.SizeAllCursor))

        # ── Numéro ───────────────────────────────────────────────────
        lbl_idx = QLabel(str(idx + 1))
        lbl_idx.setFont(QFont("Segoe UI", 9))
        lbl_idx.setFixedWidth(20)
        lbl_idx.setStyleSheet(f"color: {self.GRAY}; background: transparent; border: none;")

        # ── Nom + sous-label ─────────────────────────────────────────
        name_col = QWidget()
        name_col.setStyleSheet("background: transparent;")
        name_col.setFixedWidth(280)
        name_col.setFixedHeight(36)
        name_col_layout = QVBoxLayout(name_col)
        name_col_layout.setContentsMargins(0, 0, 0, 0)
        name_col_layout.setSpacing(0)

        text_color = self.ACCENT if hl else (self.RED if is_skipped else self.TEXT)
        lbl_pseudo = QLabel(pseudo)
        lbl_pseudo.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        lbl_pseudo.setStyleSheet(
            f"color: {text_color}; background: transparent; border: none;"
            + ("text-decoration: line-through;" if is_skipped else "")
        )
        name_col_layout.addWidget(lbl_pseudo)

        if pseudo == self._char_main:
            lbl_sub = QLabel("⭐  " + t("tab.personnages.tag.principal"))
            lbl_sub.setFont(QFont("Segoe UI", 8))
            lbl_sub.setStyleSheet(f"color: {self.ACCENT}; background: transparent; border: none;")
            name_col_layout.addWidget(lbl_sub)
        elif is_skipped:
            lbl_sub = QLabel(t("tab.personnages.tag.exclu"))
            lbl_sub.setFont(QFont("Segoe UI", 8))
            lbl_sub.setStyleSheet(f"color: {self.RED}; background: transparent; border: none;")
            name_col_layout.addWidget(lbl_sub)

        # ── Point actif ──────────────────────────────────────────────
        lbl_dot = QLabel("●")
        lbl_dot.setFont(QFont("Segoe UI", 7))

        active_preset_name = self._preset_dropdown_btn.text().replace("  ▾", "").strip() \
            if hasattr(self, "_preset_dropdown_btn") else ""
        presets = load_order_presets()
        active_pseudos = presets.get(active_preset_name, []) \
            if active_preset_name != t("tab.personnages.loadpreset").strip() else []

        dot_color = self.GREEN if (not active_pseudos or pseudo in active_pseudos) else self.ACCENT
        lbl_dot.setStyleSheet(f"color: {dot_color}; background: transparent; border: none;")
        lbl_dot.setContentsMargins(4, 0, 4, 0)

        # ── Zone gauche ───────────────────────────────────────────────
        left_zone = QWidget()
        left_zone.setStyleSheet("background: transparent;")
        left_zone.setFixedWidth(340)
        lz_layout = QHBoxLayout(left_zone)
        lz_layout.setContentsMargins(0, 0, 0, 0)
        lz_layout.setSpacing(0)
        lz_layout.addWidget(lbl_handle)
        lz_layout.addSpacing(8)
        lz_layout.addWidget(lbl_idx)
        lz_layout.addSpacing(4)
        lz_layout.addWidget(lbl_dot)
        lz_layout.addSpacing(4)
        lz_layout.addWidget(name_col)
        row_layout.addWidget(left_zone)

        row_layout.addStretch()

        # ── Boutons AF par type ───────────────────────────────────────
        override = self._char_af_overrides.get(pseudo)
        af_row = QWidget()
        af_row.setStyleSheet("background: transparent;")
        af_row_layout = QHBoxLayout(af_row)
        af_row_layout.setContentsMargins(0, 0, 0, 0)
        af_row_layout.setSpacing(3)

        for type_key, icon in _TYPE_ORDER:
            locally_disabled = (override is not None and override.get(type_key) is False)
            globally_off     = not self.type_vars[type_key].get()
            is_active        = not globally_off and not locally_disabled

            btn = QPushButton(icon)
            btn.setFont(self.S.Bouton.font_type_notifnobold)
            btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            btn.setFlat(True)
            btn.setFixedSize(30, 26)
            self._style_af_char_btn(btn, is_active)
            btn.clicked.connect(
                lambda checked=False, p=pseudo, k=type_key, b=btn:
                self._toggle_char_af_type(p, k, b)
            )
            af_row_layout.addWidget(btn)

        row_layout.addWidget(af_row)

        row_layout.addStretch()

        # ── Actions ───────────────────────────────────────────────────
        actions = QWidget()
        actions.setStyleSheet("background: transparent;")
        actions.setFixedWidth(280)
        al = QHBoxLayout(actions)
        al.setContentsMargins(0, 0, 0, 0)
        al.setSpacing(4)

        main_btn = QPushButton()
        main_btn.setFont(self.S.Bouton.font_petit)
        main_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        main_btn.setFlat(True)
        self._style_main_btn(main_btn, active=(pseudo == self._char_main))
        main_btn.setFixedWidth(60)
        main_btn.clicked.connect(
            lambda checked=False, b=main_btn, p=pseudo: self._toggle_char_main(p, b)
        )
        al.addWidget(main_btn)

        skip_btn = QPushButton()
        skip_btn.setFont(self.S.Bouton.font_petit)
        skip_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        skip_btn.setFlat(True)
        self._style_skip_btn(skip_btn, active=is_skipped)
        skip_btn.clicked.connect(
            lambda checked=False, b=skip_btn, p=pseudo: self._toggle_char_skip(p, b)
        )
        al.addWidget(skip_btn)

        row_layout.addWidget(actions)

        # ── Cibles du drag ───────────────────────────────────────────
        for widget in [row, lbl_handle, lbl_idx, lbl_pseudo, lbl_dot]:
            widget.mousePressEvent = lambda e, i=idx: self._drag_start(i, e)

        self._char_inner_layout.insertWidget(
            self._char_inner_layout.count() - 1, row
        )

    # ------------------------------------------------------------------
    # Drag & drop
    # ------------------------------------------------------------------

    def _drag_start(self, idx: int, event):
        self._drag_idx = idx
        if not self._row_tops:
            self._update_row_tops()
        self._rebuild_char_list(highlight_idx=idx)

        class _DragFilter(QObject):
            def __init__(self, parent):
                super().__init__()
                self._p = parent

            def eventFilter(self, obj, event):
                if event.type() == QEvent.Type.MouseMove:
                    self._p._drag_motion(event)
                elif (event.type() == QEvent.Type.MouseButtonRelease
                      and event.button() == Qt.MouseButton.LeftButton):
                    self._p._drag_end(event)
                return False

        self._drag_filter = _DragFilter(self)
        QApplication.instance().installEventFilter(self._drag_filter)

    def _drag_motion(self, event):
        if self._drag_idx is None or not self._row_tops:
            return
        if len(self._row_tops) != len(self._char_order):
            QApplication.instance().processEvents()
            self._update_row_tops()
        try:
            inner_y = (
                self._char_inner.mapFromGlobal(
                    event.globalPosition().toPoint()
                ).y()
                + self._char_scroll.verticalScrollBar().value()
            )
        except Exception:
            return

        target = self._drag_idx
        for i, top in enumerate(self._row_tops):
            bot = (
                self._row_tops[i + 1]
                if i + 1 < len(self._row_tops)
                else top + self._row_height
            )
            if top <= inner_y < bot:
                target = i
                break

        if target != self._drag_idx:
            self._char_order[self._drag_idx], self._char_order[target] = (
                self._char_order[target],
                self._char_order[self._drag_idx],
            )
            self._drag_idx = target
            self._rebuild_char_list(highlight_idx=target)

    def _drag_end(self, event):
        if hasattr(self, "_drag_filter") and self._drag_filter:
            QApplication.instance().removeEventFilter(self._drag_filter)
            self._drag_filter = None
        if self._drag_idx is not None:
            self._drag_idx = None
            self._preset_dropdown_btn.setText(t("tab.personnages.loadpreset"))
            self._preset_dropdown_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {self.CARD};
                    color: {self.GRAY};
                    border: 1px solid #2e3547;
                    border-radius: 4px;
                    padding: 0px 12px;
                }}
                QPushButton:hover {{ color: {self.TEXT}; border-color: {self.ACCENT}; }}
            """)
            self._rebuild_char_list()

    # ------------------------------------------------------------------
    # Enregistrement de l'ordre
    # ------------------------------------------------------------------

    def _save_order(self):
        if not self._char_order:
            return
        self._preset_dropdown_btn.setText(t("tab.personnages.loadpreset"))
        self._preset_dropdown_btn.setStyleSheet(f"""
            QPushButton {{
                background: {self.CARD};
                color: {self.GRAY};
                border: 1px solid #2e3547;
                border-radius: 4px;
                padding: 0px 12px;
            }}
            QPushButton:hover {{ color: {self.TEXT}; border-color: {self.ACCENT}; }}
        """)
        order = " → ".join(p for _, p in self._char_order)
        self.log_msg(f"Ordre : {order}", "ok")
        hwnds = [h for h, _ in self._char_order]
        self._persist_config()
        print("persist appelé, char_order:", [p for _, p in self._char_order])
        threading.Thread(
            target=reorder_with_ungroup_regroup,
            args=(hwnds, lambda m, t: QTimer.singleShot(0, lambda: self.log_msg(m, t))),
            daemon=True,
        ).start()

    # ------------------------------------------------------------------
    # Boutons skip / main
    # ------------------------------------------------------------------

    def _toggle_char_skip(self, pseudo: str, btn: QPushButton):
        if pseudo in self._char_skip_names:
            self._char_skip_names.discard(pseudo)
            self._style_skip_btn(btn, active=False)
        else:
            self._char_skip_names.add(pseudo)
            self._style_skip_btn(btn, active=True)
        self._persist_config()
        self._rebuild_char_list()

    def _style_skip_btn(self, btn: QPushButton, active: bool):
        if active:
            btn.setText("⊗  " + t("tab.personnages.exclure"))
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: #2d1515;
                    color: {self.RED};
                    border: none;
                    border-radius: 4px;
                    padding: {self.S.Bouton.pady_petit}px {self.S.Bouton.padx_petit}px;
                }}
                QPushButton:hover {{ background-color: #3a1a1a; }}
            """)
        else:
            btn.setText("○  " + t("tab.personnages.exclure"))
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: #252b3b;
                    color: {self.GRAY};
                    border: none;
                    border-radius: 4px;
                    padding: {self.S.Bouton.pady_petit}px {self.S.Bouton.padx_petit}px;
                }}
                QPushButton:hover {{ background-color: #2e3547; }}
            """)

    def _toggle_char_main(self, pseudo: str, btn: QPushButton):
        self._char_main = None if self._char_main == pseudo else pseudo
        self._persist_config()
        self._rebuild_char_list()

    def _style_main_btn(self, btn: QPushButton, active: bool):
        if active:
            btn.setText("★")
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: #252b3b;
                    color: {self.ACCENT};
                    border: none;
                    border-radius: 4px;
                    padding: {self.S.Bouton.pady_petit}px {self.S.Bouton.padx_petit}px;
                }}
                QPushButton:hover {{ background-color: #2e3547; }}
            """)
        else:
            btn.setText("☆")
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: #252b3b;
                    color: {self.GRAY};
                    border: none;
                    border-radius: 4px;
                    padding: {self.S.Bouton.pady_petit}px {self.S.Bouton.padx_petit}px;
                }}
                QPushButton:hover {{ background-color: #2e3547; }}
            """)

    # ------------------------------------------------------------------
    # AutoFocus : toggles globaux
    # ------------------------------------------------------------------

    def _is_type_fully_active(self, type_key: str) -> bool:
        return self.type_vars[type_key].get()

    def _style_global_af_btn(self, btn: QPushButton, state: str = "active"):
        pad = f"{self.S.Bouton.pady_type_notifnobold}px 4px"
        if state == "active":
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: rgba(200, 160, 40, 0.18);
                    color: #c8a028;
                    border: 1px solid rgba(200, 160, 40, 0.45);
                    border-radius: 4px;
                    padding: {pad};
                }}
                QPushButton:hover {{ background-color: rgba(200, 160, 40, 0.28); }}
            """)
        else:
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {self.PANEL};
                    color: {self.GRAY};
                    border: 1px solid {self.GRAY};
                    border-radius: 4px;
                    padding: {pad};
                }}
                QPushButton:hover {{
                    background-color: transparent;
                    border: 1px solid {self.ACCENT};
                }}
            """)

    def _update_global_btn_style(self, type_key: str):
        btn = self.type_btns[type_key]
        state = "active" if self.type_vars[type_key].get() else "all_off"
        self._style_global_af_btn(btn, state)

    def _toggle_type(self, key: str):
        self.type_vars[key].set(not self.type_vars[key].get())
        for overrides in self._char_af_overrides.values():
            overrides.pop(key, None)
        self._char_af_overrides = {p: o for p, o in self._char_af_overrides.items() if o}

        self._update_global_btn_style(key)
        self._persist_config()

        any_active = any(v.get() for v in self.type_vars.values())
        if any_active and not self._running:
            self._start()
        elif not any_active and self._running:
            self._stop()

        self._rebuild_char_list()

    # ------------------------------------------------------------------
    # AutoFocus : toggle par personnage / type
    # ------------------------------------------------------------------

    def _style_af_char_btn(self, btn: QPushButton, is_active: bool):
        if is_active:
            btn.setStyleSheet("""
                QPushButton {
                    background-color: rgba(200, 160, 40, 0.18);
                    color: #c8a028;
                    border: 1px solid rgba(200, 160, 40, 0.45);
                    border-radius: 4px;
                    padding: 2px 4px;
                }
                QPushButton:hover { background-color: rgba(200, 160, 40, 0.28); }
            """)
        else:
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {self.PANEL};
                    color: {self.GRAY};
                    border: 1px solid {self.GRAY};
                    border-radius: 4px;
                    padding: 2px 4px;
                }}
                QPushButton:hover {{
                    background-color: transparent;
                    border: 1px solid {self.ACCENT};
                }}
            """)

    def _toggle_char_af_type(self, pseudo: str, type_key: str, _btn: QPushButton):
        if not self.type_vars[type_key].get():
            return  # globalement off, rien à faire

        override = self._char_af_overrides.get(pseudo)
        locally_disabled = override is not None and override.get(type_key) is False

        if locally_disabled:
            del override[type_key]
            if not override:
                del self._char_af_overrides[pseudo]
        else:
            if override is None:
                override = {}
                self._char_af_overrides[pseudo] = override
            override[type_key] = False

        self._update_global_btn_style(type_key)
        self._persist_config()
        self._rebuild_char_list()

    # ------------------------------------------------------------------
    # Compat : _rebuild_af_char_list
    # ------------------------------------------------------------------

    def _rebuild_af_char_list(self):
        self._rebuild_char_list()

    # ------------------------------------------------------------------
    # Moteur AutoFocus : démarrage / arrêt
    # ------------------------------------------------------------------

    def _start(self):
        if not WIN32_OK or not WINSDK_OK:
            self.log_msg("AutoFocus impossible : dépendances manquantes (pywin32 / winsdk).", "error")
            return
        self._running = True
        self.log_msg("AutoFocus démarré.", "ok")
        threading.Thread(target=self._run_async_loop, daemon=True).start()
        threading.Thread(target=self._watch_windows,  daemon=True).start()

    def _stop(self):
        self._running = False
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
        self.log_msg("AutoFocus arrêté.", "dim")

    def _set_status(self, text: str, color: str):
        pass  # stub — plus d'UI de statut dédiée

    def _run_async_loop(self):
        import ctypes
        ctypes.windll.ole32.CoInitializeEx(None, 0x2)  # COINIT_APARTMENTTHREADED
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._listen())
        except Exception as e:
            QTimer.singleShot(0, lambda: self.log_msg(f"Erreur fatale AF : {e}", "error"))
        finally:
            self._loop.close()
            ctypes.windll.ole32.CoUninitialize()


    # ------------------------------------------------------------------
    # Surveillance des fenêtres (détection automatique + maximize)
    # ------------------------------------------------------------------

    def _watch_windows(self):
        while self._running:
            try:
                from logic import _shortened_titles, TITLE_PATTERN, LOADING_PATTERN, extract_pseudo_from_title
                current: dict[int, str] = {}

                def _cb(hwnd, _):
                    if not win32gui.IsWindowVisible(hwnd):
                        return True
                    try:
                        _, pid = win32process.GetWindowThreadProcessId(hwnd)
                        if not _is_dofus_pid(pid):
                            return True
                    except Exception:
                        return True
                    title = win32gui.GetWindowText(hwnd)
                    if hwnd in _shortened_titles or TITLE_PATTERN.match(title) or LOADING_PATTERN.match(title):
                        current[hwnd] = title
                    return True

                win32gui.EnumWindows(_cb, None)

                if current != self._window_snapshot:
                    new_hwnds  = set(current.keys()) - set(self._window_snapshot.keys())
                    gone_hwnds = set(self._window_snapshot.keys()) - set(current.keys())

                    for hwnd in new_hwnds:
                        try:
                            if self.maximize_on_launch_var.get():
                                win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
                        except Exception:
                            pass

                    for hwnd in gone_hwnds:
                        _shortened_titles.pop(hwnd, None)

                    # Détection loading pattern — toujours actif
                    for hwnd, title in current.items():
                        old_title = self._window_snapshot.get(hwnd)
                        if old_title is not None and title != old_title:
                            if LOADING_PATTERN.match(title):
                                self._preset_needs_reset = True

                    # Titres changés sur hwnds existants (ex: changement de personnage)
                    if self.shorten_title_var.get():
                        for hwnd, title in current.items():
                            old_title = self._window_snapshot.get(hwnd)
                            if old_title is not None and title != old_title:
                                if LOADING_PATTERN.match(title):
                                    _shortened_titles.pop(hwnd, None)
                                else:
                                    pseudo = extract_pseudo_from_title(title)
                                    if pseudo:
                                        _shortened_titles[hwnd] = (pseudo, title)
                                        win32gui.SetWindowText(hwnd, pseudo)

                    self._window_snapshot = current
                    QTimer.singleShot(0, self.refresh_characters)

            except Exception:
                pass
            time.sleep(0.3)

    # ------------------------------------------------------------------
    # Écoute des notifications (moteur principal)
    # ------------------------------------------------------------------

    async def _listen(self):
        listener = winman.UserNotificationListener.current
        access   = await listener.request_access_async()
        if access != winman.UserNotificationListenerAccessStatus.ALLOWED:
            QTimer.singleShot(0, lambda: self.log_msg(
                "Accès notifications refusé ! "
                "Active-les dans Paramètres → Système → Notifications.", "error"))
            QTimer.singleShot(0, self._stop)
            return

        self.log_msg("Accès aux notifications accordé.", "ok")
        seen_ids: set[int] = set()

        event      = asyncio.Event()
        use_events = False
        token      = None

        def on_notif_changed(sender, args):
            try:
                if self._loop and self._loop.is_running():
                    self._loop.call_soon_threadsafe(event.set)
            except Exception:
                pass

        try:
            token = listener.add_notification_changed(on_notif_changed)
            use_events = True
            self.log_msg("Mode event-driven actif (détection instantanée).", "ok")
        except Exception:
            self.log_msg("Mode polling actif (0.3 s).", "dim")

        try:
            while self._running:
                if use_events:
                    try:
                        await asyncio.wait_for(event.wait(), timeout=30.0)
                    except asyncio.TimeoutError:
                        pass
                    except asyncio.CancelledError:
                        break
                    event.clear()
                else:
                    try:
                        await asyncio.sleep(0.3)
                    except asyncio.CancelledError:
                        break

                try:
                    notifications = await listener.get_notifications_async(
                        winnot.NotificationKinds.TOAST)
                    new_notifs = [n for n in notifications if n.id not in seen_ids]

                    if new_notifs:
                        self._n_notifs += len(new_notifs)

                    for notif in new_notifs:
                        seen_ids.add(notif.id)

                        if self.remove_notif_var.get():
                            try:
                                listener.remove_notification(notif.id)
                            except Exception:
                                pass
                        try:
                            binding = notif.notification.visual.get_binding(
                                winnot.KnownNotificationBindings.toast_generic)
                            if binding is None:
                                continue

                            elements = [e.text for e in binding.get_text_elements()]
                            if not elements:
                                continue

                            notif_title = elements[0]
                            notif_body  = elements[1] if len(elements) > 1 else ""

                            pseudo = extract_pseudo_from_title(notif_title)
                            if not pseudo:
                                continue

                            matched_type  = None
                            matched_emoji = "🔔"
                            for type_key, patterns, emoji in NOTIF_TYPES:
                                if any(p.search(notif_body) for p in patterns):
                                    matched_type  = type_key
                                    matched_emoji = emoji
                                    break

                            if matched_type is None:
                                continue

                            if not self.type_vars[matched_type].get():
                                continue

                            if self._char_af_overrides:
                                _ov = self._char_af_overrides.get(pseudo)
                                if _ov is not None and _ov.get(matched_type) is False:
                                    continue

                            # ── Dradidas ──────────────────────────────────────
                            if matched_type == "combat" and self._dradidas_manager.has_active_skips():
                                _skip, _left = self._dradidas_manager.should_skip_combat(pseudo)
                                if _skip:
                                    _tours = "tour" if _left <= 1 else "tours"
                                    QTimer.singleShot(0, lambda p=pseudo, l=_left, t=_tours: self.log_msg(
                                        f"🌿 [DRADIDAS] {p} — tour ignoré ({l} {t} restant{'s' if l > 1 else ''})",
                                        "dim"))
                                    if hasattr(self, "_refresh_dradidas_badges"):
                                        QTimer.singleShot(0, self._refresh_dradidas_badges)
                                    continue

                            self._n_matches += 1
                            QTimer.singleShot(0, lambda me=matched_emoji, mt=matched_type, p=pseudo, b=notif_body:
                                self.log_msg(f"{me} [{mt.upper()}] {p} — {b}", "info"))

                            if WIN32_OK:
                                try:
                                    _fg = win32gui.GetForegroundWindow()
                                    if _fg:
                                        self._prev_hwnd = _fg
                                except Exception:
                                    pass

                            ok, detail = focus_dofus_window(pseudo)
                            if ok:
                                self._n_focus += 1
                                QTimer.singleShot(0, lambda d=detail: self.log_msg(f"  ✓ Focus : {d}", "ok"))
                            else:
                                QTimer.singleShot(0, lambda d=detail: self.log_msg(f"  ✗ {d}", "error"))

                        except Exception as e:
                            QTimer.singleShot(0, lambda ex=e: self.log_msg(
                                f"[debug] Exception notif : {ex}", "error"))

                    if len(seen_ids) > 500:
                        seen_ids.clear()

                except Exception as e:
                    QTimer.singleShot(0, lambda ex=e: self.log_msg(f"Erreur lecture : {ex}", "error"))

        finally:
            try:
                listener.remove_notification_changed(token)
            except Exception:
                pass
