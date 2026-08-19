"""
UI_Tab_Infos.py
Onglet « Info » — à propos, liens, mentions légales, réinitialisation.
"""

import webbrowser
import os

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFrame,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QCursor, QFont

from core.config import APP_VERSION, APP_GITHUB, APP_TWITTER, LOG_PATH
from core.shortcuts import _unhook_all
from core.i18n import t

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

        # Bouton à deux états, au même emplacement :
        #   - pas de MAJ connue -> "Vérifier" (déclenche une vérification manuelle)
        #   - MAJ connue        -> badge "MAJ disponible" (ouvre la popup de MAJ)
        # Un seul widget, un seul état visible à la fois : l'un remplace l'autre.
        self._lbl_version_update = QPushButton("")
        self._lbl_version_update.setFont(self.S.Bouton.font_petit)
        self._lbl_version_update.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._lbl_version_update.setFlat(True)
        self._lbl_version_update.clicked.connect(self._on_version_button_clicked)
        row_ver_layout.addWidget(self._lbl_version_update)
        row_ver_layout.addSpacing(10)

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

        # --- Fichier de log ---
        _card_log, cl_log = _card()

        lbl_log_titre = QLabel(t("tab.info.log.title"))
        lbl_log_titre.setFont(self.S.Info.font)
        lbl_log_titre.setStyleSheet(f"color: {self.GRAY}; background: transparent;")
        cl_log.addWidget(lbl_log_titre)

        lbl_log_path = QLabel(LOG_PATH)
        lbl_log_path.setFont(QFont("Consolas", 10))
        lbl_log_path.setStyleSheet(f"color: {self.TEXT}; background: transparent;")
        lbl_log_path.setWordWrap(True)
        cl_log.addWidget(lbl_log_path)

        btn_log = QPushButton("📂  " + t("tab.info.log.bouton"))
        btn_log.setFont(self.S.Bouton.font_petit)
        btn_log.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_log.setFlat(True)
        btn_log.setStyleSheet(f"""
            QPushButton {{
                background-color: #252b3b;
                color: {self.ACCENT};
                border: none;
                border-radius: 4px;
                padding: {self.S.Bouton.pady_petit}px {self.S.Bouton.padx_petit}px;
            }}
            QPushButton:hover {{ background-color: #2e3550; }}
        """)
        btn_log.clicked.connect(lambda: os.startfile(os.path.dirname(LOG_PATH)))
        cl_log.addWidget(btn_log, alignment=Qt.AlignmentFlag.AlignLeft)

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

        # Si une MAJ était déjà connue avant que cet onglet ne soit construit
        # (l'onglet Info n'est buildé qu'à la première visite), on synchronise
        # tout de suite le bouton qu'on vient de créer.
        self._sync_version_button()

    # ------------------------------------------------------------------
    # Bouton "Vérifier" / "MAJ disponible" (2 états du même widget)
    # ------------------------------------------------------------------

    def _sync_version_button(self):
        """
        Met le bouton dans le bon état selon self._last_update_info.
        À appeler chaque fois que cet état change (résultat de vérif,
        MAJ ignorée, etc.) — c'est le pendant, pour ce bouton, de
        _refresh_update_indicator() côté badge du header.
        """
        btn = getattr(self, "_lbl_version_update", None)
        if btn is None:
            return

        if getattr(self, "_update_check_running", False):
            self._style_version_button_checking()
            return

        info = getattr(self, "_last_update_info", None)
        if info is not None:
            self._style_version_button_available()
        else:
            self._style_version_button_idle()

    def _style_version_button_idle(self):
        btn = self._lbl_version_update
        btn.setText(t("tab.info.update.check_now"))
        btn.setEnabled(True)
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {self.CARD};
                color: {self.GRAY};
                border: 1px solid {self.GRAY};
                border-radius: 12px;
                padding: 4px 12px;
            }}
            QPushButton:hover {{ border-color: {self.ACCENT}; color: {self.ACCENT}; }}
        """)

    def _style_version_button_checking(self):
        btn = self._lbl_version_update
        btn.setText(t("tab.info.update.checking"))
        btn.setEnabled(False)
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {self.CARD};
                color: {self.GRAY};
                border: 1px solid {self.GRAY};
                border-radius: 12px;
                padding: 4px 12px;
            }}
        """)

    def _style_version_button_available(self):
        btn = self._lbl_version_update
        btn.setText(t("update.badge"))
        btn.setEnabled(True)
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {self.CARD};
                color: {self.ACCENT};
                border: 1px solid {self.ACCENT};
                border-radius: 12px;
                padding: 4px 12px;
            }}
            QPushButton:hover {{ background-color: {self.ACCENT}; color: {self.BG}; }}
        """)

    def _on_version_button_clicked(self):
        info = getattr(self, "_last_update_info", None)
        if info is not None:
            self._show_update_popup(info)
        else:
            self._check_for_updates(silent=False)
