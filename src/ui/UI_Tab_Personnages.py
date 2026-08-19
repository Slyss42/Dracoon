"""
UI_Tab_Personnages.py
Onglet « Personnages » — orchestrateur léger.

La logique est répartie dans 4 mixins autonomes :
  - UI_Presets.py    → PresetsMixin    (zone presets, dropdown, _save_order)
  - UI_Avatar.py     → AvatarMixin     (bouton avatar, popup personnalisation)
  - UI_CharRow.py    → CharRowMixin    (lignes de personnages, drag & drop)
  - UI_AutoFocus.py  → AutoFocusMixin  (moteur AutoFocus complet)
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QScrollArea, QApplication,
)
from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtGui import QFont, QCursor

from core.config import WIN32_OK, _TYPE_ORDER
from core.windows import get_dofus_windows
from core.i18n import t

from UI_Presets    import PresetsMixin
from UI_Avatar     import AvatarMixin
from UI_CharRow    import CharRowMixin
from UI_AutoFocus  import AutoFocusMixin


class TabPersonnagesMixin(PresetsMixin, AvatarMixin, CharRowMixin, AutoFocusMixin):
    """
    Orchestrateur de l'onglet Personnages.

    Fournit directement :
      - log_msg
      - _build_tab_personnages
      - _build_col_header_with_af
      - _build_legend + _get_type_labels
      - refresh_characters
      - _rebuild_char_list + _update_row_tops

    Tout le reste est délégué aux mixins parents.
    """

    # ------------------------------------------------------------------
    # Construction de l'onglet
    # ------------------------------------------------------------------

    def _build_tab_personnages(self):
        from ui.theme import BoolVar

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

        # ── Initialisation type_vars avant _build_col_header_with_af ─
        self.type_vars: dict = {}
        self.type_btns: dict = {}
        for key, _ in _TYPE_ORDER:
            self.type_vars[key] = BoolVar(True)

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

        # ── Compteurs internes pour _listen ──────────────────────────
        self._n_notifs  = getattr(self, "_n_notifs",  0)
        self._n_matches = getattr(self, "_n_matches", 0)
        self._n_focus   = getattr(self, "_n_focus",   0)

    # ------------------------------------------------------------------
    # En-tête colonnes + boutons AF globaux
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
