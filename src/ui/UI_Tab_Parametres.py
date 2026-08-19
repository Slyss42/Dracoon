"""
UI_Tab_Parametres.py
Onglet « Paramètres » — options générales de l'application.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QFrame, QScrollArea,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QCursor

from core.shortcuts import _unhook_all
from core.config import _REG_PATH, build_config
from core.i18n import t

from core.windows import apply_shorten_titles

import winreg

try:
    import keyboard
except Exception:
    pass



class TabParametresMixin:
    """
    Mixin pour la classe App.
    Fournit : _build_tab_parametres, _reset_config.
    """

    # ------------------------------------------------------------------
    # Construction de l'onglet
    # ------------------------------------------------------------------

    def _build_tab_parametres(self):
        f = QWidget()
        f.setStyleSheet(f"background-color: {self.BG};")
        self._tab_frames["parametres"] = f
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

        lbl_titre = QLabel(t("tab.parametres.title"))
        lbl_titre.setFont(self.S.EnTete.font)
        lbl_titre.setStyleSheet(f"color: {self.TEXT};")
        top_layout.addWidget(lbl_titre)

        lbl_sub = QLabel(t("tab.parametres.description"))
        lbl_sub.setFont(self.S.Info.font)
        lbl_sub.setStyleSheet(f"color: {self.GRAY};")
        top_layout.addWidget(lbl_sub)

        layout.addWidget(top)

        # --- Zone scrollable des modes ---
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"""
            QScrollArea {{ background-color: {self.BG}; border: none; }}
            QScrollBar:vertical {{ width: 6px; background: {self.PANEL}; }}
            QScrollBar::handle:vertical {{ background: {self.GRAY}; border-radius: 3px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """)
        inner = QWidget()
        inner.setStyleSheet(f"background-color: {self.BG};")
        self._modes_layout = QVBoxLayout(inner)
        self._modes_layout.setContentsMargins(16, 4, 16, 16)
        self._modes_layout.setSpacing(6)
        self._modes_layout.addStretch()
        scroll.setWidget(inner)
        layout.addWidget(scroll, stretch=1)

        

        # --- Helper ligne de paramètre ---
        def _param_row(label: str, sublabel: str, variable, on_change=None):
            container = QWidget()
            container.setStyleSheet("background: transparent;")
            c_layout = QHBoxLayout(container)
            c_layout.setContentsMargins(0, 4, 0, 4)

            card = QFrame()
            card.setStyleSheet(f"background-color: {self.CARD}; border-radius: 4px;")
            card.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            card_layout = QHBoxLayout(card)
            card_layout.setContentsMargins(14, 12, 14, 12)
            card_layout.setSpacing(0)

            info = QWidget()
            info.setStyleSheet("background: transparent;")
            info.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            info_layout = QVBoxLayout(info)
            info_layout.setContentsMargins(0, 0, 0, 0)
            info_layout.setSpacing(2)

            lbl_main = QLabel(label)
            lbl_main.setFont(self.S.Bouton.font_principal)
            lbl_main.setStyleSheet(f"color: {self.TEXT}; background: transparent;")
            info_layout.addWidget(lbl_main)

            if sublabel:
                lbl_sl = QLabel(sublabel)
                lbl_sl.setFont(self.S.Info.font)
                lbl_sl.setStyleSheet(f"color: {self.GRAY}; background: transparent;")
                info_layout.addWidget(lbl_sl)

            card_layout.addWidget(info, stretch=1)

            # Checkbox visuelle (droite)
            cb_lbl = QLabel()
            cb_lbl.setFont(self.S.Bouton.font_principal.__class__("Segoe UI", 18))
            cb_lbl.setStyleSheet("background: transparent;")
            cb_lbl.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            card_layout.addWidget(cb_lbl)

            def _refresh():
                cb_lbl.setText("☑" if variable.get() else "☐")
                cb_lbl.setStyleSheet(
                    f"color: {self.ACCENT}; background: transparent; font-size: 18px;"
                    if variable.get() else
                    f"color: {self.GRAY}; background: transparent; font-size: 18px;"
                )

            def _toggle(event, _on_change=on_change):
                variable.set(not variable.get())
                _refresh()
                self._persist_config()
                if _on_change:
                    _on_change(variable.get())

            _refresh()

            for w in [card, info, cb_lbl, lbl_main] + ([lbl_sl] if sublabel else []):
                w.mousePressEvent = _toggle

            c_layout.addWidget(card)
            self._modes_layout.insertWidget(self._modes_layout.count() - 1, container)

        _param_row(
            t("tab.parametres.banner.title"),
            t("tab.parametres.banner.description"),
            self.remove_notif_var,
        )
        _param_row(
            t("tab.parametres.maximize.title"),
            t("tab.parametres.maximize.description"),
            self.maximize_on_launch_var,
        )

        _param_row(
            t("tab.parametres.short.title"),
            t("tab.parametres.short.description"),
            self.shorten_title_var,
            on_change=apply_shorten_titles,
        )

        _param_row(
            t("tab.parametres.update_check.title"),
            t("tab.parametres.update_check.description"),
            self.check_update_on_launch_var,
            on_change=self._on_update_check_toggle,
        )

    # ------------------------------------------------------------------
    # Réinitialisation
    # ------------------------------------------------------------------

    def _reset_config(self):
        # ── Nettoyage registre ────────────────────────────────────────────────
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REG_PATH,
                                 access=winreg.KEY_WRITE)
            with key:
                for name in build_config(None, None, None).keys():
                    try:
                        winreg.DeleteValue(key, name)
                    except FileNotFoundError:
                        pass
        except FileNotFoundError:
            pass
        # ── Reste de ton code existant ────────────────────────────────────────
        self._shortcut_next     = None
        self._shortcut_prev     = None
        self._shortcut_back     = None
        self._shortcut_main     = None
        self._char_main         = None
        self._char_skip_names   = set()
        self._char_af_overrides = {}
        self._welcome_shown     = False

        _unhook_all()
        self._persist_config()
        self._rebuild_char_list()

        for entry in [
            getattr(self, '_next_entry', None),
            getattr(self, '_prev_entry', None),
            getattr(self, '_back_entry', None),
            getattr(self, '_main_entry', None),
        ]:
            if entry is None:
                continue
            try:
                entry.setText("Aucun")
                entry.setStyleSheet(entry.styleSheet().replace(
                    f"color: {self.ACCENT}", f"color: {self.GRAY}"
                ))
            except Exception:
                pass

        self.log_msg("Paramètres réinitialisés.", "ok")
