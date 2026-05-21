"""
UI_Tab_Infos.py
Onglet « Info » — à propos, liens, mentions légales, réinitialisation.
"""

import webbrowser

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFrame,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QCursor

from logic import APP_VERSION, APP_GITHUB, APP_TWITTER, _unhook_all, t


class TabInfosMixin:
    """
    Mixin pour la classe App.
    Fournit : _build_tab_info, _reset_config.
    """

    # ------------------------------------------------------------------
    # Construction de l'onglet
    # ------------------------------------------------------------------

    def _build_tab_info(self):
        f = QWidget()
        f.setStyleSheet(f"background-color: {self.BG};")
        self._tab_frames["info"] = f
        self._content.addWidget(f)

        layout = QVBoxLayout(f)
        layout.setContentsMargins(0, 10, 0, 10)
        layout.setSpacing(0)

        # --- En-tête ---
        top = QWidget()
        top.setStyleSheet("background: transparent;")
        top_layout = QVBoxLayout(top)
        top_layout.setContentsMargins(16, 12, 16, 12)
        top_layout.setSpacing(2)

        lbl_titre = QLabel(t("tab.info.title"))
        lbl_titre.setFont(self.S.EnTete.font)
        lbl_titre.setStyleSheet(f"color: {self.TEXT};")
        top_layout.addWidget(lbl_titre)

        lbl_sub = QLabel(t("tab.info.description"))
        lbl_sub.setFont(self.S.Info.font)
        lbl_sub.setStyleSheet(f"color: {self.GRAY};")
        top_layout.addWidget(lbl_sub)
        layout.addWidget(top)

        # --- Helper carte générique ---
        def _card(pady_top=4, pady_bot=2) -> tuple[QFrame, QVBoxLayout]:
            container = QWidget()
            container.setStyleSheet("background: transparent;")
            cl = QHBoxLayout(container)
            cl.setContentsMargins(16, pady_top, 16, pady_bot)
            card = QFrame()
            card.setStyleSheet(f"background-color: {self.CARD}; border-radius: 4px;")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(16, 12, 16, 12)
            card_layout.setSpacing(6)
            cl.addWidget(card)
            layout.addWidget(container)
            return card, card_layout

        # --- Version ---
        _card_ver, cl_ver = _card()
        row_ver = QWidget()
        row_ver.setStyleSheet("background: transparent;")
        row_ver_layout = QHBoxLayout(row_ver)
        row_ver_layout.setContentsMargins(0, 0, 0, 0)

        lbl_ver_label = QLabel(t("tab.info.version"))
        lbl_ver_label.setFont(self.S.Info.font)
        lbl_ver_label.setStyleSheet(f"color: {self.GRAY}; background: transparent;")
        row_ver_layout.addWidget(lbl_ver_label)
        row_ver_layout.addStretch()

        lbl_ver_val = QLabel(APP_VERSION)
        lbl_ver_val.setFont(self.S.Bouton.font_principal)
        lbl_ver_val.setStyleSheet(f"color: {self.ACCENT}; background: transparent;")
        row_ver_layout.addWidget(lbl_ver_val)
        cl_ver.addWidget(row_ver)

        # --- Liens ---
        _card_links, cl_links = _card()

        lbl_liens = QLabel(t("tab.info.liens"))
        lbl_liens.setFont(self.S.Info.font)
        lbl_liens.setStyleSheet(f"color: {self.GRAY}; background: transparent;")
        cl_links.addWidget(lbl_liens)

        def _link_row(icon: str, label: str, url: str):
            row = QWidget()
            row.setStyleSheet("background: transparent;")
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 2, 0, 2)
            row_layout.setSpacing(6)

            lbl_icon = QLabel(icon)
            lbl_icon.setFont(self.S.Info.font)
            lbl_icon.setStyleSheet(f"color: {self.GRAY}; background: transparent;")
            row_layout.addWidget(lbl_icon)

            lbl_url = QLabel(label)
            lbl_url.setFont(self.S.Info.font)
            lbl_url.setStyleSheet(f"color: {self.BLUE}; background: transparent;")
            lbl_url.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            lbl_url.mousePressEvent = lambda e, u=url: webbrowser.open(u)
            lbl_url.enterEvent = lambda e: lbl_url.setStyleSheet(f"color: {self.ACCENT}; background: transparent;")
            lbl_url.leaveEvent = lambda e: lbl_url.setStyleSheet(f"color: {self.BLUE}; background: transparent;")
            row_layout.addWidget(lbl_url)
            row_layout.addStretch()
            cl_links.addWidget(row)

        _link_row("⌨", t("link.github"), APP_GITHUB)
        _link_row("🐦", t("link.twitter"), APP_TWITTER)

        # --- Mentions légales ---
        _card_legal, cl_legal = _card()

        lbl_legal_titre = QLabel(t("tab.info.legal.title"))
        lbl_legal_titre.setFont(self.S.Info.font)
        lbl_legal_titre.setStyleSheet(f"color: {self.GRAY}; background: transparent;")
        cl_legal.addWidget(lbl_legal_titre) 

        lbl_legal_body = QLabel(t("tab.info.legal.text"))
        lbl_legal_body.setFont(self.S.Info.font)
        lbl_legal_body.setStyleSheet(f"color: {self.TEXT}; background: transparent;")
        lbl_legal_body.setWordWrap(True)
        cl_legal.addWidget(lbl_legal_body)

        # --- Réinitialiser ---
        _card_reset, cl_reset = _card(pady_bot=16)

        lbl_reset_titre = QLabel(t("tab.info.reset.title"))
        lbl_reset_titre.setFont(self.S.Info.font)
        lbl_reset_titre.setStyleSheet(f"color: {self.GRAY}; background: transparent;")
        cl_reset.addWidget(lbl_reset_titre)

        lbl_reset_body = QLabel(t("tab.info.reset.text"))
        lbl_reset_body.setFont(self.S.Info.font)
        lbl_reset_body.setStyleSheet(f"color: {self.GRAY}; background: transparent;")
        lbl_reset_body.setWordWrap(True)
        cl_reset.addWidget(lbl_reset_body)

        btn_reset = QPushButton("🗑  " + t("tab.info.reset.bouton"))
        btn_reset.setFont(self.S.Bouton.font_petit)
        btn_reset.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_reset.setFlat(True)
        btn_reset.setStyleSheet(f"""
            QPushButton {{
                background-color: #2d1515;
                color: {self.RED};
                border: none;
                border-radius: 4px;
                padding: {self.S.Bouton.pady_petit}px {self.S.Bouton.padx_petit}px;
            }}
            QPushButton:hover {{ background-color: #3a1a1a; }}
        """)
        btn_reset.clicked.connect(self._reset_config)
        cl_reset.addWidget(btn_reset, alignment=Qt.AlignmentFlag.AlignLeft)

        layout.addStretch()
