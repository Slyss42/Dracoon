"""
UI_Avatar.py
Mixin gérant les boutons avatar et la popup de personnalisation d'icône.

Méthodes fournies :
  - _make_avatar_btn
  - _style_avatar_btn
  - _open_icon_popup
"""

import os as _os

from PyQt6.QtWidgets import (
    QWidget, QPushButton, QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QScrollArea, QGridLayout,
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import (
    QFont, QCursor, QIcon, QPixmap,
    QPainter, QColor, QBrush, QPen, QPainterPath,
)

from core.i18n import t
from core.config import CHAR_ICON_COLORS, CHAR_ICON_PORTRAITS, portraits_dir
from core.icons import set_window_icon, _restore_original_icon


class AvatarMixin:
    """
    Mixin autonome pour la personnalisation des avatars de personnages.

    Dépendances attendues sur self (fournies par App / TabPersonnagesMixin) :
      - self.BG, self.CARD, self.PANEL, self.TEXT, self.GRAY, self.ACCENT, self.RED
      - self.S.Bouton.font_petit
      - self._char_icons  (dict[pseudo, {"color": str|None, "portrait": str|None}])
      - self._persist_config()
    """

    # ------------------------------------------------------------------
    # Bouton avatar dans la ligne de personnage
    # ------------------------------------------------------------------

    def _make_avatar_btn(self, hwnd: int, pseudo: str) -> QWidget:
        cfg      = self._char_icons.get(pseudo, {})
        color    = cfg.get("color")
        portrait = cfg.get("portrait")

        SIZE = 32
        btn = QPushButton()
        btn.setFixedSize(SIZE, SIZE)
        btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn.setToolTip("✏  Personnaliser l'icône")
        btn.setFlat(True)
        self._style_avatar_btn(btn, color, portrait, SIZE)

        # Charger le portrait si défini
        if portrait:
            portrait_path = portraits_dir() + f"/{portrait}.png"
            if _os.path.exists(portrait_path):
                btn.setIcon(QIcon(portrait_path))
                btn.setIconSize(QSize(SIZE - 6, SIZE - 6))
        else:
            btn.setIcon(QIcon())  # vider l'icône si aucun portrait

        btn.clicked.connect(
            lambda checked=False, h=hwnd, p=pseudo, b=btn:
            self._open_icon_popup(h, p, b)
        )
        return btn

    def _style_avatar_btn(self, btn: QPushButton, color: str | None,
                           portrait: str | None, size: int = 32):
        """Met à jour le style CSS du bouton avatar."""
        if color:
            border_color = f"#{color}"
        else:
            border_color = self.GRAY

        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                border-radius: {size // 2}px;
                border: 2px solid {border_color};
            }}
            QPushButton:hover {{
                border: 2px solid {self.ACCENT};
            }}
        """)
        if portrait:
            portrait_path = portraits_dir() + f"/{portrait}.png"
            if _os.path.exists(portrait_path):
                btn.setIcon(QIcon(portrait_path))
                btn.setIconSize(QSize(size - 6, size - 6))
        else:
            btn.setIcon(QIcon())
        # Texte = initiale du pseudo si pas de portrait
        if not portrait:
            initial = pseudo[0].upper() if (pseudo := btn.toolTip()) else "?"  # noqa: F841
            # on récupère le pseudo depuis le parent — on met juste ✏ au hover
            btn.setText("")
        else:
            btn.setText("")

    # ------------------------------------------------------------------
    # Popup de personnalisation d'icône
    # ------------------------------------------------------------------

    def _open_icon_popup(self, hwnd: int, pseudo: str, avatar_btn: QPushButton):
        """Popup de personnalisation style FocusRétro."""
        cfg          = self._char_icons.get(pseudo, {})
        sel_color    = [cfg.get("color")]    # liste pour capturer par ref
        sel_portrait = [cfg.get("portrait")]

        dlg = QDialog(self)
        dlg.setWindowTitle(f"{pseudo}  —  Personnaliser")
        dlg.setModal(True)
        dlg.setFixedWidth(420)
        dlg.setStyleSheet(f"""
            QDialog {{
                background-color: {self.PANEL};
            }}
            QLabel {{
                background: transparent;
            }}
        """)

        dlg_layout = QVBoxLayout(dlg)
        dlg_layout.setContentsMargins(20, 18, 20, 18)
        dlg_layout.setSpacing(14)

        # ── Titre ────────────────────────────────────────────────────
        lbl_title = QLabel(f"{pseudo}  —  Personnaliser")
        lbl_title.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        lbl_title.setStyleSheet(f"color: {self.TEXT};")
        dlg_layout.addWidget(lbl_title)

        # ── Section Couleur ──────────────────────────────────────────
        lbl_color = QLabel("Couleur")
        lbl_color.setFont(QFont("Segoe UI", 10))
        lbl_color.setStyleSheet(f"color: {self.GRAY};")
        dlg_layout.addWidget(lbl_color)

        color_row = QWidget()
        color_row.setStyleSheet("background: transparent;")
        color_layout = QHBoxLayout(color_row)
        color_layout.setContentsMargins(0, 0, 0, 0)
        color_layout.setSpacing(6)

        color_btns: list[QPushButton] = []

        def _select_color(hex_val, btns):
            sel_color[0] = hex_val
            for b in btns:
                b.setProperty("selected", False)
                b.setStyleSheet(b.property("base_style"))
            # Retrouver le bon bouton
            for b in btns:
                if b.property("color_val") == hex_val:
                    b.setStyleSheet(
                        b.property("base_style") +
                        f" border: 2px solid {self.TEXT};"
                    )
            _update_preview()

        for hex_val in CHAR_ICON_COLORS:
            cb = QPushButton()
            cb.setFixedSize(28, 28)
            cb.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            cb.setFlat(True)

            if hex_val is None:
                # Bouton "X" = aucune couleur
                base_style = f"""
                    QPushButton {{
                        background-color: {self.CARD};
                        border-radius: 14px;
                        border: 2px solid {self.GRAY};
                        color: {self.GRAY};
                        font-size: 16px;
                        font-weight: bold;
                        padding: 0px;
                        margin: 0px;
                        qproperty-iconSize: 0px;
                    }}
                    QPushButton:hover {{ border-color: {self.TEXT}; color: {self.TEXT}; }}
                """
                cb.setText("✕")
            else:
                base_style = f"""
                    QPushButton {{
                        background-color: #{hex_val};
                        border-radius: 14px;
                        border: 2px solid transparent;
                    }}
                    QPushButton:hover {{ border-color: {self.TEXT}; opacity: 0.9; }}
                """

            cb.setProperty("base_style", base_style)
            cb.setProperty("color_val", hex_val)
            cb.setStyleSheet(base_style)

            if sel_color[0] == hex_val:
                cb.setStyleSheet(base_style + f" border: 2px solid {self.TEXT};")

            cb.clicked.connect(
                lambda checked=False, v=hex_val, bl=color_btns: _select_color(v, bl)
            )
            color_layout.addWidget(cb)
            color_btns.append(cb)

        color_layout.addStretch()
        dlg_layout.addWidget(color_row)

        # ── Section Portrait ─────────────────────────────────────────
        lbl_portrait = QLabel("Icône")
        lbl_portrait.setFont(QFont("Segoe UI", 10))
        lbl_portrait.setStyleSheet(f"color: {self.GRAY};")
        dlg_layout.addWidget(lbl_portrait)

        portrait_scroll = QScrollArea()
        portrait_scroll.setWidgetResizable(True)
        portrait_scroll.setFixedHeight(130)
        portrait_scroll.setStyleSheet(f"""
            QScrollArea {{ background: transparent; border: none; }}
            QScrollBar:vertical {{ width: 4px; background: {self.PANEL}; }}
            QScrollBar::handle:vertical {{ background: {self.GRAY}; border-radius: 2px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """)

        portrait_inner = QWidget()
        portrait_inner.setStyleSheet("background: transparent;")
        portrait_grid = QGridLayout(portrait_inner)
        portrait_grid.setContentsMargins(0, 0, 0, 0)
        portrait_grid.setSpacing(6)
        portrait_scroll.setWidget(portrait_inner)

        portrait_btns: list[QPushButton] = []
        COLS = 9

        def _select_portrait(name, btns):
            sel_portrait[0] = name
            for b in btns:
                b.setProperty("selected", False)
                b.setStyleSheet(b.property("base_style"))
            for b in btns:
                if b.property("portrait_val") == name:
                    b.setStyleSheet(
                        b.property("base_style") +
                        f" border: 2px solid {self.ACCENT};"
                    )
            _update_preview()

        for i, name in enumerate(CHAR_ICON_PORTRAITS):
            if name == "dofus_icon":
                continue
            pb = QPushButton()
            pb.setFixedSize(36, 36)
            pb.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            pb.setFlat(True)

            if name is None:
                base = f"""
                    QPushButton {{
                        background-color: {self.CARD};
                        border-radius: 18px;
                        border: 2px solid {self.GRAY};
                        color: {self.GRAY};
                        font-size: 16px;
                        font-weight: bold;
                        padding: 0px;
                        margin: 0px;
                        qproperty-iconSize: 0px;
                    }}
                    QPushButton:hover {{ border-color: {self.TEXT}; color: {self.TEXT}; }}
                """
                pb.setText("✕")
            else:
                # Charger le portrait si disponible
                portrait_path = portraits_dir() + f"/{name}.png"
                if _os.path.exists(portrait_path):
                    icon = QIcon(portrait_path)
                    pb.setIcon(icon)
                    pb.setIconSize(pb.size() - QSize(4, 4))
                    base = f"""
                        QPushButton {{
                            background-color: {self.CARD};
                            border-radius: 18px;
                            border: 2px solid transparent;
                        }}
                        QPushButton:hover {{ border-color: {self.ACCENT}; }}
                    """
                else:
                    # Fallback : initiales
                    base = f"""
                        QPushButton {{
                            background-color: {self.CARD};
                            border-radius: 18px;
                            border: 2px solid {self.GRAY};
                            color: {self.GRAY};
                            font-size: 8px;
                        }}
                        QPushButton:hover {{ border-color: {self.ACCENT}; }}
                    """
                    pb.setText(name[:3])

            pb.setProperty("base_style", base)
            pb.setProperty("portrait_val", name)
            pb.setStyleSheet(base)

            if sel_portrait[0] == name:
                pb.setStyleSheet(base + f" border: 2px solid {self.ACCENT};")

            pb.clicked.connect(
                lambda checked=False, n=name, bl=portrait_btns: _select_portrait(n, bl)
            )
            portrait_grid.addWidget(pb, i // COLS, i % COLS)
            portrait_btns.append(pb)

        dlg_layout.addWidget(portrait_scroll)

        # ── Prévisualisation ─────────────────────────────────────────
        preview_row = QWidget()
        preview_row.setStyleSheet("background: transparent;")
        prev_layout = QHBoxLayout(preview_row)
        prev_layout.setContentsMargins(0, 0, 0, 0)
        prev_layout.setSpacing(10)

        prev_layout.addStretch()

        lbl_prev_label = QLabel("Aperçu :")
        lbl_prev_label.setFont(QFont("Segoe UI", 10))
        lbl_prev_label.setStyleSheet(f"color: {self.GRAY};")
        prev_layout.addWidget(lbl_prev_label)

        lbl_preview = QLabel()
        lbl_preview.setFixedSize(36, 36)
        lbl_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        prev_layout.addWidget(lbl_preview)
        prev_layout.addStretch()
        dlg_layout.addWidget(preview_row)

        def _update_preview():
            """Redessine le disque de prévisualisation."""
            SIZE = 64  # haute résolution pour éviter le flou
            px = QPixmap(SIZE, SIZE)
            px.fill(Qt.GlobalColor.transparent)
            painter = QPainter(px)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

            # Fond : couleur ou CARD si aucune couleur
            if sel_color[0]:
                c = QColor(f"#{sel_color[0]}")
            else:
                c = QColor(self.CARD)
            painter.setBrush(QBrush(c))
            painter.setPen(QPen(Qt.GlobalColor.transparent))
            painter.drawEllipse(2, 2, SIZE - 4, SIZE - 4)

            # Portrait par-dessus si disponible (clipé dans le cercle)
            if sel_portrait[0]:
                pp = _os.path.join(portraits_dir(), f"{sel_portrait[0]}.png")
                if _os.path.exists(pp):
                    portrait_px = QPixmap(pp).scaled(
                        SIZE - 4, SIZE - 4,
                        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                        Qt.TransformationMode.SmoothTransformation
                    )
                    path = QPainterPath()
                    path.addEllipse(2, 2, SIZE - 4, SIZE - 4)
                    painter.setClipPath(path)
                    painter.drawPixmap(2, 2, portrait_px)
                    painter.setClipping(False)

            painter.end()
            # Redimensionner proprement à 36x36 pour l'affichage
            lbl_preview.setPixmap(px.scaled(
                36, 36,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            ))

        _update_preview()

        # ── Boutons OK / Annuler ─────────────────────────────────────
        btn_row = QWidget()
        btn_row.setStyleSheet("background: transparent;")
        btn_row_layout = QHBoxLayout(btn_row)
        btn_row_layout.setContentsMargins(0, 0, 0, 0)
        btn_row_layout.setSpacing(8)
        btn_row_layout.addStretch()

        btn_reset = QPushButton("Réinitialiser")
        btn_reset.setFont(self.S.Bouton.font_petit)
        btn_reset.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_reset.setFlat(True)
        btn_reset.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {self.GRAY};
                border: 1px solid #2e3547;
                border-radius: 4px;
                padding: 5px 14px;
            }}
            QPushButton:hover {{ color: {self.RED}; border-color: {self.RED}; }}
        """)

        def _do_reset():
            self._char_icons.pop(pseudo, None)
            self._persist_config()
            _restore_original_icon(hwnd)
            self._style_avatar_btn(avatar_btn, None, None)
            dlg.accept()

        btn_reset.clicked.connect(_do_reset)
        btn_row_layout.addWidget(btn_reset)

        btn_cancel = QPushButton("Annuler")
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
        btn_row_layout.addWidget(btn_cancel)

        btn_ok = QPushButton("Appliquer")
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

        def _do_apply():
            c = sel_color[0]
            p = sel_portrait[0]
            if c is None and p is None:
                self._char_icons.pop(pseudo, None)
            else:
                self._char_icons[pseudo] = {"color": c, "portrait": p}
            self._persist_config()
            # Appliquer immédiatement à la fenêtre
            set_window_icon(hwnd, c, p)
            # Rafraîchir l'avatar dans la liste
            self._style_avatar_btn(avatar_btn, c, p)
            dlg.accept()

        btn_ok.clicked.connect(_do_apply)
        btn_row_layout.addWidget(btn_ok)
        dlg_layout.addWidget(btn_row)

        dlg.adjustSize()
        # Centrer sur la fenêtre principale
        rx = self.x() + (self.width()  - dlg.width())  // 2
        ry = self.y() + (self.height() - dlg.height()) // 2
        dlg.move(rx, ry)
        dlg.exec()
