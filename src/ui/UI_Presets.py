"""
UI_Presets.py
Mixin gérant la zone de presets d'ordre de personnages.

Méthodes fournies :
  - _build_preset_zone
  - _toggle_preset_dropdown
  - _rebuild_preset_menu
  - _build_preset_menu_row
  - _open_preset_popup
  - _apply_preset
  - _delete_preset
  - _reset_preset_btn
  - _save_order
"""

import threading

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QPushButton,
    QLabel, QDialog, QLineEdit, QFrame,
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QCursor
from distro import name

from core.i18n import t
from core.preset import load_order_presets, save_order_preset, delete_order_preset, apply_order_preset
from core.windows import reorder_with_ungroup_regroup


class PresetsMixin:
    """
    Mixin autonome pour la gestion des presets d'ordre de personnages.

    Dépendances attendues sur self (fournies par App / TabPersonnagesMixin) :
      - self.BG, self.CARD, self.PANEL, self.TEXT, self.GRAY, self.ACCENT, self.RED
      - self.S.Bouton.font_principal, self.S.Bouton.font_petit
      - self.S.Bouton.pady_principal, self.S.Bouton.padx_principal
      - self._char_order   (list[tuple[hwnd, pseudo]])
      - self._rebuild_char_list()
      - self._persist_config()
      - self.log_msg(msg, tag)
    """

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
        self._preset_menu.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint
        )
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
            lbl.setStyleSheet(
                f"color: {self.GRAY}; background: transparent; padding: 8px 14px;"
            )
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
        lbl_del.setStyleSheet(
            f"color: {self.GRAY}; background: transparent; border-radius: 3px;"
        )
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
            lbl_del.setStyleSheet(
                f"color: {self.TEXT}; background: transparent; border-radius: 3px;"
            )

        def _leave(e):
            row.setStyleSheet("background: transparent;")
            lbl_del.setStyleSheet(
                f"color: {self.GRAY}; background: transparent; border-radius: 3px;"
            )

        def _mouse_move(e):
            if e.position().x() >= del_x_start:
                lbl_del.setStyleSheet(
                    f"color: {self.RED}; background: #3a1a1a; border-radius: 3px;"
                )
            else:
                lbl_del.setStyleSheet(
                    f"color: {self.TEXT}; background: transparent; border-radius: 3px;"
                )

        row.enterEvent = _enter
        row.leaveEvent = _leave
        row.mouseMoveEvent = _mouse_move
        row.setMouseTracking(True)

        return row

    # ------------------------------------------------------------------
    # Popup "Nom du preset"
    # ------------------------------------------------------------------

    def _open_preset_popup(self):
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
        self._set_preset_btn_active(name)
        self._rebuild_char_list()

    def _delete_preset(self, name: str):
        delete_order_preset(name)
        self._rebuild_preset_menu()
        # Remettre le label par défaut si c'était le preset affiché
        if name in self._preset_dropdown_btn.text():
            self._reset_preset_btn()

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
        
    def _set_preset_btn_active(self, name: str):
        """Style du dropdown quand un preset est sélectionné."""
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
    # ------------------------------------------------------------------
    # Enregistrement de l'ordre
    # ------------------------------------------------------------------

    def _save_order(self):
        if not self._char_order:
            return
        self._reset_preset_btn()
        order = " → ".join(p for _, p in self._char_order)
        self.log_msg(f"Ordre : {order}", "ok")
        hwnds = [h for h, _ in self._char_order]
        self._persist_config()
        threading.Thread(
            target=reorder_with_ungroup_regroup,
            args=(hwnds, lambda m, t: QTimer.singleShot(0, lambda: self.log_msg(m, t))),
            daemon=True,
        ).start()
