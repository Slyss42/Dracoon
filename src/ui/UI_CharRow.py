"""
UI_CharRow.py
Mixin gérant la création des lignes de personnages et le drag & drop.

Méthodes fournies :
  - _create_char_row
  - _drag_start
  - _drag_motion
  - _drag_end
  - _toggle_char_skip
  - _style_skip_btn
  - _toggle_char_main
  - _style_main_btn
"""

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QFrame,
    QPushButton, QLabel, QApplication,
)
from PyQt6.QtCore import Qt, QPoint, QEvent, QObject
from PyQt6.QtGui import QFont, QCursor

from core.i18n import t
from core.preset import load_order_presets

from core.config import _TYPE_ORDER

class CharRowMixin:
    """
    Mixin autonome pour la construction des lignes de personnages
    et la gestion du drag & drop.

    Dépendances attendues sur self (fournies par App / TabPersonnagesMixin) :
      - self.BG, self.CARD, self.PANEL, self.TEXT, self.GRAY,
        self.ACCENT, self.RED, self.GREEN
      - self.S.Bouton.font_petit, self.S.Bouton.font_type_notifnobold
      - self.S.Bouton.pady_petit, self.S.Bouton.padx_petit
      - self._char_order        (list[tuple[hwnd, pseudo]])
      - self._char_skip_names   (set[str])
      - self._char_main         (str | None)
      - self._char_af_overrides (dict)
      - self._char_inner        (QWidget — conteneur scrollable)
      - self._char_inner_layout (QVBoxLayout)
      - self._char_scroll       (QScrollArea)
      - self._row_tops          (list[int])
      - self._row_height        (int)
      - self._drag_idx          (int | None)
      - self._preset_dropdown_btn (QPushButton)
      - self._make_avatar_btn(hwnd, pseudo) → QWidget   [depuis AvatarMixin]
      - self._style_af_char_btn(btn, active)             [depuis AutoFocusMixin]
      - self._toggle_char_af_type(pseudo, type_key, btn) [depuis AutoFocusMixin]
      - self._rebuild_char_list(highlight_idx=None)
      - self._update_row_tops()
      - self._persist_config()
    """

    # ------------------------------------------------------------------
    # Construction d'une ligne de personnage
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

        # ── Avatar rond ───────────────────────────────────────────────
        lz_layout.addSpacing(6)
        avatar_btn = self._make_avatar_btn(hwnd, pseudo)
        lz_layout.addWidget(avatar_btn)
        lz_layout.addSpacing(6)
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
            self._reset_preset_btn()
            self._rebuild_char_list()

    # ------------------------------------------------------------------
    # Boutons Exclure / Principal
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
