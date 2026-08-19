"""
UI_Tab_Outils.py
Onglet « Outils » — modes de jeu activables (Déplacement, Dradidas, ...).

Ce fichier ne contient que la construction et le câblage de l'UI.
La logique de chaque mode vit dans core/movemode.py et core/dradidasmode.py
et n'est pas modifiée ici.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFrame, QLineEdit,
    QScrollArea, QSpinBox,
)
from PyQt6.QtCore import Qt, QEvent, QObject, QMetaObject, pyqtSlot, QTimer
from PyQt6.QtGui import QFont, QCursor, QKeySequence, QKeyEvent

from core.config import KEYBOARD_OK
from core.i18n import t

from core.movemode import MoveModeManager
from core.windows import is_dofus_foreground, extract_pseudo_from_title


class TabOutilsMixin:
    """
    Mixin pour la classe App.
    Fournit : _build_tab_outils — onglet « Outils » regroupant les modes
    activables (Déplacement, Dradidas, ...).
    """

    # ------------------------------------------------------------------
    # Construction de l'onglet
    # ------------------------------------------------------------------

    def _build_tab_outils(self):
        f = QWidget()
        f.setStyleSheet(f"background-color: {self.BG};")
        self._tab_frames["outils"] = f
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

        lbl_titre = QLabel(t("tab.outils.title"))
        lbl_titre.setFont(self.S.EnTete.font)
        lbl_titre.setStyleSheet(f"color: {self.TEXT};")
        top_layout.addWidget(lbl_titre)

        lbl_sub = QLabel(t("tab.outils.description"))
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
        self._outils_layout = QVBoxLayout(inner)
        self._outils_layout.setContentsMargins(16, 4, 16, 16)
        self._outils_layout.setSpacing(6)
        self._outils_layout.addStretch()
        scroll.setWidget(inner)
        layout.addWidget(scroll, stretch=1)

        # --- Initialisation manager + construction des cartes ---
        if not hasattr(self, "_mode_panels"):
            self._mode_panels = {}
            self._mode_arrows = {}
        self._move_overlay = None
        self._move_manager = MoveModeManager(
            cycle_fn        = self._cycle_next,
            is_dofus_fg_fn  = is_dofus_foreground,
            on_state_change = self._on_move_state_change,
        )
        self._build_mode_deplacement()
        self._move_hotkey_ref = None
        QTimer.singleShot(500, self._register_move_hotkey)

        self._build_mode_dradidas()
        self._dradidas_hotkey_ref = None
        QTimer.singleShot(500, self._register_dradidas_hotkey)

    def _build_mode_card(
            self,
            mode_id: str,
            icon: str,
            title: str,
            subtitle: str,
            is_active_fn,        # callable() → bool
            toggle_fn,           # callable() → None
            build_content_fn,    # callable(parent_layout) → None
        ) -> QFrame:
            """
            Crée une carte accordion.
            Retourne le QFrame racine.
            """

            root = QFrame()
            root.setStyleSheet(f"background-color: {self.CARD}; border-radius: 6px;")
            root_layout = QVBoxLayout(root)
            root_layout.setContentsMargins(0, 0, 0, 0)
            root_layout.setSpacing(0)

            # ── Header de la carte ──────────────────────────────────────────
            header = QWidget()
            header.setStyleSheet("background: transparent;")
            header.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            header_layout = QHBoxLayout(header)
            header_layout.setContentsMargins(14, 12, 14, 12)
            header_layout.setSpacing(0)

            # Icône invisible (réservation d'espace supprimée — plus d'icône dupliquée)

            # Texte titre + sous-titre
            info = QWidget()
            info.setStyleSheet("background: transparent;")
            info_layout = QVBoxLayout(info)
            info_layout.setContentsMargins(0, 0, 0, 0)
            info_layout.setSpacing(1)

            # Titre avec icône intégrée
            lbl_title = QLabel(f"{icon}  {title}")
            lbl_title.setFont(self.S.Bouton.font_principal)
            lbl_title.setStyleSheet(f"color: {self.TEXT}; background: transparent;")
            info_layout.addWidget(lbl_title)

            lbl_sub = QLabel(subtitle)
            lbl_sub.setFont(self.S.Info.font)
            lbl_sub.setStyleSheet(f"color: {self.GRAY}; background: transparent;")
            info_layout.addWidget(lbl_sub)

            header_layout.addWidget(info, stretch=1)

            # ── Checkbox permission (QLabel cliquable) ─────────────────────
            # La checkbox n'active/désactive PAS le mode directement.
            # Elle sert de permission : si cochée, le raccourci peut toggler le mode.
            _cb_enabled = [getattr(self, "_move_enabled", True)]   # état mutable dans la closure

            def _cb_text():
                return "☑" if _cb_enabled[0] else "☐"

            def _cb_color():
                return self.ACCENT if _cb_enabled[0] else self.GRAY

            toggle_cb = QLabel(_cb_text())
            toggle_cb.setFont(QFont("Segoe UI", 13))
            toggle_cb.setStyleSheet(f"color: {_cb_color()}; background: transparent; font-size: 18px;")
            toggle_cb.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            toggle_cb.setFixedWidth(22)

            def _on_cb_click(event=None):
                _cb_enabled[0] = not _cb_enabled[0]
                self._move_enabled = _cb_enabled[0]
                self._persist_config()
                toggle_cb.setText(_cb_text())
                toggle_cb.setStyleSheet(f"color: {_cb_color()}; background: transparent;")
                # Si on décoche alors que le mode est actif, on le désactive
                if not _cb_enabled[0] and is_active_fn():
                    toggle_fn()
                    if hasattr(self, "_mode_checkboxes"):
                        self._mode_checkboxes[mode_id] = _cb_enabled
                event.accept()   # stopper la propagation vers le header

            toggle_cb.mousePressEvent = _on_cb_click

            # Stocker la ref à l'état pour _toggle_move_mode
            if not hasattr(self, "_mode_enabled"):
                self._mode_enabled = {}
            self._mode_enabled[mode_id] = _cb_enabled

            header_layout.addWidget(toggle_cb)
            header_layout.addSpacing(12)

            # Flèche déroulement           
            arrow_lbl = QLabel("▸") # au lieu de ▶
            arrow_lbl.setStyleSheet(f"color: {self.GRAY}; background: transparent; font-size: 20pt; font-family: Segoe UI;")
            arrow_lbl.setFixedWidth(40)
            arrow_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            header_layout.addWidget(arrow_lbl)

            root_layout.addWidget(header)

            # ── Panneau déroulant ───────────────────────────────────────────
            panel = QWidget()
            panel.setStyleSheet(f"background-color: #151a27; border-radius: 0px 0px 6px 6px;")
            panel.setVisible(False)
            panel_layout = QVBoxLayout(panel)
            panel_layout.setContentsMargins(16, 14, 16, 16)
            panel_layout.setSpacing(14)

            # Séparateur haut
            sep = QFrame()
            sep.setFixedHeight(1)
            sep.setStyleSheet(f"background-color: {self.CARD};")
            panel_layout.addWidget(sep)

            # Contenu spécifique au mode
            build_content_fn(panel_layout)

            root_layout.addWidget(panel)

            # ── Clic sur le header → dérouler/enrouler ─────────────────────
            def _on_header_click(event):
                if panel.isVisible():
                    panel.setVisible(False)
                    arrow_lbl.setText("▸")
                    arrow_lbl.setStyleSheet(f"color: {self.GRAY}; background: transparent; font-size: 20pt; font-family: Segoe UI;")

                else:
                    panel.setVisible(True)
                    arrow_lbl.setText("▾")
                    arrow_lbl.setStyleSheet(f"color: {self.GRAY}; background: transparent; font-size: 20pt; font-family: Segoe UI;")

                    

            # Stocker refs pour usage externe
            if not hasattr(self, "_mode_panels"):
                self._mode_panels = {}
                self._mode_arrows = {}
            self._mode_panels[mode_id]  = panel
            self._mode_arrows[mode_id]  = arrow_lbl
            # Garder une ref à la checkbox pour rafraîchissement externe
            if not hasattr(self, "_mode_checkboxes"):
                self._mode_checkboxes = {}
            self._mode_checkboxes[mode_id] = toggle_cb

            for w in [header, lbl_title, lbl_sub, arrow_lbl, info]:
                w.mousePressEvent = _on_header_click

            # Insérer avant le stretch
            idx = self._outils_layout.count() - 1
            self._outils_layout.insertWidget(idx, root)
            return root

        # ------------------------------------------------------------------
        # Helper : ligne de paramètre inline (dans le panneau déroulant)
        # ------------------------------------------------------------------

    def _mode_param_label(self, layout: QVBoxLayout, text: str):
        lbl = QLabel(text)
        lbl.setFont(self.S.Info.font)
        lbl.setStyleSheet(f"color: {self.GRAY}; background: transparent;")
        layout.addWidget(lbl)

    def _mode_shortcut_entry(
        self, layout: QVBoxLayout, label: str, current: str | None, which: str
    ) -> QLineEdit:
        """Ligne raccourci compacte pour panneau déroulant."""
        row = QWidget()
        row.setStyleSheet("background: transparent;")
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(8)

        lbl = QLabel(label)
        lbl.setFont(self.S.Info.font)
        lbl.setStyleSheet(f"color: {self.GRAY}; background: transparent;")
        row_layout.addWidget(lbl, stretch=1)

        display = "Aucun" if current is None else current
        color   = self.GRAY if current is None else self.ACCENT

        entry = QLineEdit(display)
        entry.setFont(QFont("Consolas", 10))
        entry.setAlignment(Qt.AlignmentFlag.AlignCenter)
        entry.setFixedWidth(120)
        entry.setStyleSheet(f"""
            QLineEdit {{
                background-color: #252b3b;
                color: {color};
                border: none;
                border-radius: 4px;
                padding: 4px;
            }}
        """)
        if which == "move":
            entry.focusInEvent = lambda e, en=entry: self._start_capture_move(en)
        elif which == "dradidas":
            entry.focusInEvent = lambda e, en=entry: self._start_capture_dradidas(en) 
        else:
            entry.focusInEvent = lambda e, w=which, en=entry: self._start_capture(en, w)
        row_layout.addWidget(entry)

        btn_aucun = QPushButton("Aucun")
        btn_aucun.setFont(self.S.Bouton.font_petit)
        btn_aucun.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_aucun.setFlat(True)
        btn_aucun.setStyleSheet(f"""
            QPushButton {{
                background-color: #252b3b;
                color: {self.GRAY};
                border: none;
                border-radius: 4px;
                padding: 4px 10px;
            }}
            QPushButton:hover {{ color: {self.TEXT}; }}
        """)
        if which == "move":
            btn_aucun.clicked.connect(self._set_no_shortcut_move)
        elif which == "dradidas":
            btn_aucun.clicked.connect(self._set_no_shortcut_dradidas)
        else:
            btn_aucun.clicked.connect(lambda checked=False, w=which: self._set_no_shortcut(w))
        row_layout.addWidget(btn_aucun)

        layout.addWidget(row)
        return entry

    def _mode_toggle_row(
        self, layout: QVBoxLayout, label: str, variable
    ):
        """Ligne toggle (label à gauche, checkbox à droite) pour panneau déroulant."""
        row = QWidget()
        row.setStyleSheet("background: transparent;")
        row.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(8)

        lbl = QLabel(label)
        lbl.setFont(self.S.Info.font)
        lbl.setStyleSheet(f"color: {self.GRAY}; background: transparent;")
        row_layout.addWidget(lbl, stretch=1)

        # Checkbox à droite
        cb = QLabel("☑" if variable.get() else "☐")
        cb.setFont(QFont("Segoe UI", 11))
        cb.setStyleSheet(
            f"color: {self.ACCENT}; background: transparent; font-size: 18px;"
            if variable.get() else
            f"color: {self.GRAY}; background: transparent; font-size: 18px;"
        )
        row_layout.addWidget(cb)

        def _toggle(event=None):
            variable.set(not variable.get())
            cb.setText("☑" if variable.get() else "☐")
            cb.setStyleSheet(
                f"color: {self.ACCENT}; background: transparent; font-size: 18px;"
                if variable.get() else
                f"color: {self.GRAY}; background: transparent; font-size: 18px;"
            )
            self._persist_config()

        for w in [row, cb, lbl]:
            w.mousePressEvent = _toggle

        layout.addWidget(row)

    def _mode_spinbox_row(
        self, layout: QVBoxLayout, label: str,
        min_val: int, max_val: int, current: int,
        unit: str, on_change  # callable(int)
    ) -> QSpinBox:
        """Ligne avec entrée numérique (spinbox) pour panneau déroulant."""
        row = QWidget()
        row.setStyleSheet("background: transparent;")
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(8)

        lbl = QLabel(label)
        lbl.setFont(self.S.Info.font)
        lbl.setStyleSheet(f"color: {self.GRAY}; background: transparent;")
        row_layout.addWidget(lbl, stretch=1)

        spinbox = QSpinBox()
        spinbox.setMinimum(min_val)
        spinbox.setMaximum(max_val)
        spinbox.setValue(current)
        spinbox.setSuffix(f" {unit}")
        spinbox.setFont(QFont("Consolas", 10))
        spinbox.setFixedWidth(90)
        spinbox.setAlignment(Qt.AlignmentFlag.AlignCenter)
        spinbox.setStyleSheet(f"""
            QSpinBox {{
                background-color: #252b3b;
                color: {self.ACCENT};
                border: none;
                border-radius: 4px;
                padding: 4px 6px;
            }}
            QSpinBox::up-button, QSpinBox::down-button {{
                background-color: #1a1f2e;
                border: none;
                width: 16px;
            }}
            QSpinBox::up-button:hover, QSpinBox::down-button:hover {{
                background-color: {self.ACCENT};
            }}
            QSpinBox::up-arrow {{
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-bottom: 5px solid {self.GRAY};
                width: 0; height: 0;
            }}
            QSpinBox::down-arrow {{
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 5px solid {self.GRAY};
                width: 0; height: 0;
            }}
        """)

        def _on_value(val: int):
            on_change(val)
            self._persist_config()

        spinbox.valueChanged.connect(_on_value)
        row_layout.addWidget(spinbox)
        layout.addWidget(row)
        return spinbox

    # ------------------------------------------------------------------
    # Mode Déplacement
    # ------------------------------------------------------------------

    def _build_mode_deplacement(self):

        def _build_content(panel_layout: QVBoxLayout):
            # Raccourci
            self._move_shortcut_entry_mode = self._mode_shortcut_entry(
                panel_layout, t("tab.outils.mode.move.raccourci"), self._shortcut_move, "move"
            )
            # Overlay (label à gauche, checkbox à droite)
            self._mode_toggle_row(
                panel_layout, t("tab.outils.mode.move.overlay"), self.move_overlay_var
            )
            # Délai de cycle — spinbox
            self._move_delay_spinbox = self._mode_spinbox_row(
                panel_layout,
                label     = t("tab.outils.mode.move.ms"),
                min_val   = 90,
                max_val   = 300,
                current   = self._move_cycle_delay_ms,
                unit      = "ms",
                on_change = self._set_move_cycle_delay,
            )

        self._build_mode_card(
            mode_id          = "deplacement",
            icon             = "🏃",
            title            = t("tab.outils.mode.move.title"),
            subtitle         = t("tab.outils.mode.move.description"),
            is_active_fn     = lambda: self._move_manager.is_active,
            toggle_fn        = self._toggle_move_mode,
            build_content_fn = _build_content,
        )

    def _set_move_cycle_delay(self, val: int):
        self._move_cycle_delay_ms = val
        self._move_manager._CYCLE_DELAY_MS = val

    def _set_no_shortcut_move(self):
        """Efface le raccourci du mode déplacement et re-applique les hotkeys."""
        self._shortcut_move = None
        if hasattr(self, "_move_shortcut_entry_mode"):
            self._move_shortcut_entry_mode.setText("Aucun")
            self._move_shortcut_entry_mode.setStyleSheet(f"""
                QLineEdit {{
                    background-color: #252b3b;
                    color: {self.GRAY};
                    border: none;
                    border-radius: 4px;
                    padding: 4px;
                }}
            """)
        self._apply_shortcuts()
        # Plus besoin d'enregistrer le hotkey move — il a été retiré par _apply_shortcuts

    def _toggle_move_mode(self):
        # Vérifier que la checkbox de permission est cochée
        enabled = getattr(self, "_mode_enabled", {}).get("deplacement", [True])
        if not enabled[0]:
            return
        if not is_dofus_foreground():
            return
        self._move_manager.toggle()

    # ------------------------------------------------------------------
    # Surcharges de TabRaccourcisMixin — sans modifier UI_Tab_Raccourcis.py
    # ------------------------------------------------------------------

    def _start_capture_move(self, entry: QLineEdit):
        """Capture de touche dédiée au raccourci du mode déplacement."""
        from PyQt6.QtCore import QEvent, QObject
        from PyQt6.QtGui import QKeySequence, QKeyEvent

        entry.setText("Appuyez…")
        entry.setStyleSheet(f"""
            QLineEdit {{
                background-color: #252b3b;
                color: {self.GRAY};
                border: none;
                border-radius: 4px;
                padding: 4px;
            }}
        """)

        def on_key(event: QKeyEvent):
            mod_keys = {
                Qt.Key.Key_Control, Qt.Key.Key_Shift, Qt.Key.Key_Alt,
                Qt.Key.Key_Meta, Qt.Key.Key_CapsLock,
                Qt.Key.Key_Super_L, Qt.Key.Key_Super_R,
            }
            k = event.key()
            if k in mod_keys:
                return
            mods = []
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier: mods.append("ctrl")
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:   mods.append("shift")
            if event.modifiers() & Qt.KeyboardModifier.AltModifier:     mods.append("alt")
            key_name = QKeySequence(k).toString().lower()
            combo = "+".join(mods + [key_name]) if mods else key_name

            self._shortcut_move = combo
            entry.setText(combo)
            entry.setStyleSheet(f"""
                QLineEdit {{
                    background-color: #252b3b;
                    color: {self.ACCENT};
                    border: none;
                    border-radius: 4px;
                    padding: 4px;
                }}
            """)
            entry.removeEventFilter(self._move_capture_filter)
            self._move_capture_filter = None
            self.setFocus()
            self._apply_shortcuts()
            self._register_move_hotkey()

        class _KeyFilter(QObject):
            def __init__(self, cb):
                super().__init__()
                self._cb = cb
            def eventFilter(self, obj, evt):
                if evt.type() == QEvent.Type.KeyPress:
                    self._cb(evt)
                    return True
                return False

        self._move_capture_filter = _KeyFilter(on_key)
        entry.installEventFilter(self._move_capture_filter)



    def _register_move_hotkey(self):
        """Enregistre (ou retire) le hotkey move indépendamment des autres raccourcis."""
        if not KEYBOARD_OK:
            return
        try:
            import keyboard as _kb
            # Retirer uniquement le hook move s'il existe déjà
            if hasattr(self, "_move_hotkey_ref") and self._move_hotkey_ref:
                try:
                    _kb.remove_hotkey(self._move_hotkey_ref)
                except Exception:
                    pass
                self._move_hotkey_ref = None
            if self._shortcut_move:
                self._move_hotkey_ref = _kb.add_hotkey(
                    self._shortcut_move, self._toggle_move_mode
                )
        except Exception:
            pass

    def _on_move_state_change(self, is_active: bool):
        QMetaObject.invokeMethod(
            self, "_apply_move_state",
            Qt.ConnectionType.QueuedConnection,
        )

    @pyqtSlot()
    def _apply_move_state(self):
        if self._move_manager.is_active:
            self._show_move_overlay()
        else:
            self._flash_move_overlay_off()

    # ------------------------------------------------------------------
    # Overlay flottant
    # ------------------------------------------------------------------

    def _show_move_overlay(self):
        enabled = getattr(self, "_mode_enabled", {}).get("deplacement", [True])
        if not enabled[0]:
            return
        if not self.move_overlay_var.get():
            self._start_overlay_poll()
            return
        if self._move_overlay is None:
            self._build_move_overlay()
        self._move_overlay_label.setText("🏃 Mode déplacement")
        self._move_overlay_label.setStyleSheet(
            f"color: {self.GREEN}; background: transparent; font-weight: bold;")
        self._move_overlay.setStyleSheet("background-color: #0d2918; border-radius: 6px;")
        from PyQt6.QtWidgets import QApplication
        screen = QApplication.primaryScreen().availableGeometry()
        self._move_overlay.move(screen.right() - 230, screen.bottom() - 90)
        self._move_overlay.show()
        self._move_overlay.raise_()
        self._start_overlay_poll()

    def _flash_move_overlay_off(self):
        if not self.move_overlay_var.get() or self._move_overlay is None:
            return
        self._move_overlay_label.setText("🧍 Mode déplacement")
        self._move_overlay_label.setStyleSheet(
            f"color: {self.RED}; background: transparent; font-weight: bold;")
        self._move_overlay.setStyleSheet("background-color: #2d0f0f; border-radius: 6px;")
        self._move_overlay.show()
        QTimer.singleShot(1000, self._hide_move_overlay)

    def _hide_move_overlay(self):
        if self._move_overlay:
            self._move_overlay.hide()

    def _build_move_overlay(self):
        from PyQt6.QtWidgets import QApplication
        ov = QWidget(None, Qt.WindowType.Tool |
                        Qt.WindowType.FramelessWindowHint |
                        Qt.WindowType.WindowStaysOnTopHint)
        ov.setStyleSheet("background-color: #0d2918; border-radius: 6px;")
        ov.setFixedSize(210, 42)
        ov.setWindowOpacity(0.90)

        inner_layout = QHBoxLayout(ov)
        inner_layout.setContentsMargins(14, 8, 14, 8)

        lbl = QLabel("🏃 Mode déplacement")
        lbl.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        lbl.setStyleSheet(f"color: {self.GREEN}; background: transparent;")
        inner_layout.addWidget(lbl)

        ov._drag_pos = None
        def _press(e):
            if e.button() == Qt.MouseButton.LeftButton:
                ov._drag_pos = e.globalPosition().toPoint() - ov.frameGeometry().topLeft()
        def _move(e):
            if ov._drag_pos and e.buttons() == Qt.MouseButton.LeftButton:
                ov.move(e.globalPosition().toPoint() - ov._drag_pos)
        def _release(e):
            ov._drag_pos = None

        ov.mousePressEvent   = _press
        ov.mouseMoveEvent    = _move
        ov.mouseReleaseEvent = _release
        lbl.mousePressEvent   = _press
        lbl.mouseMoveEvent    = _move
        lbl.mouseReleaseEvent = _release

        self._move_overlay       = ov
        self._move_overlay_label = lbl

    def _start_overlay_poll(self):
        if self._move_overlay and self._move_manager.is_active:
            if is_dofus_foreground():
                self._move_overlay.show()
                self._move_overlay.raise_()
            else:
                self._move_overlay.hide()
            QTimer.singleShot(250, self._start_overlay_poll)


    # ------------------------------------------------------------------
    # Mode Dradidas
    # ------------------------------------------------------------------

    def _build_mode_dradidas(self):

        def _build_content(panel_layout: QVBoxLayout):
            # Raccourci
            self._dradidas_shortcut_entry_mode = self._mode_shortcut_entry(
                panel_layout, t("tab.outils.mode.dradidas.raccourci"), self._shortcut_dradidas, "dradidas"
            )

            # Nombre de tours
            self._dradidas_turns_spinbox = self._mode_spinbox_row(
                panel_layout,
                label     = t("tab.outils.mode.dradidas.tours"),
                min_val   = 2,
                max_val   = 4,
                current   = self._dradidas_turns,
                unit      = "tours",
                on_change = self._set_dradidas_turns,
            )

            # En-tête
            lbl_sadidas = QLabel(t("tab.outils.mode.dradidas.personnages"))
            lbl_sadidas.setFont(self.S.Info.font)
            lbl_sadidas.setStyleSheet(f"color: {self.GRAY}; background: transparent;")
            panel_layout.addWidget(lbl_sadidas)

            # Container de la liste
            self._dradidas_chars_container = QWidget()
            self._dradidas_chars_container.setStyleSheet("background: transparent;")
            self._dradidas_chars_layout = QVBoxLayout(self._dradidas_chars_container)
            self._dradidas_chars_layout.setContentsMargins(0, 0, 0, 0)
            self._dradidas_chars_layout.setSpacing(4)
            panel_layout.addWidget(self._dradidas_chars_container)

            self._rebuild_dradidas_char_list()

        self._build_mode_card(
            mode_id          = "dradidas",
            icon             = "🌿",
            title            = t("tab.outils.mode.dradidas.title"),
            subtitle         = t("tab.outils.mode.dradidas.description"),
            is_active_fn     = lambda: False,   # ce mode n'a pas d'état actif/inactif — juste un raccourci
            toggle_fn        = lambda: None,
            build_content_fn = _build_content,
        )

    def _set_dradidas_turns(self, val: int):
        self._dradidas_turns = val
        self._dradidas_manager.turns = val

    def _set_no_shortcut_dradidas(self):
        self._shortcut_dradidas = None
        if hasattr(self, "_dradidas_shortcut_entry_mode"):
            self._dradidas_shortcut_entry_mode.setText("Aucun")
            self._dradidas_shortcut_entry_mode.setStyleSheet(f"""
                QLineEdit {{
                    background-color: #252b3b;
                    color: {self.GRAY};
                    border: none;
                    border-radius: 4px;
                    padding: 4px;
                }}
            """)
        self._apply_shortcuts()
        self._register_dradidas_hotkey()

    def _start_capture_dradidas(self, entry: QLineEdit):
        """Capture de touche dédiée au raccourci du mode Dradidas (Puissance Sylvestre)."""
        entry.setText("Appuyez…")
        entry.setStyleSheet(f"""
            QLineEdit {{
                background-color: #252b3b;
                color: {self.GRAY};
                border: none;
                border-radius: 4px;
                padding: 4px;
            }}
        """)

        def on_key(event: QKeyEvent):
            mod_keys = {
                Qt.Key.Key_Control, Qt.Key.Key_Shift, Qt.Key.Key_Alt,
                Qt.Key.Key_Meta, Qt.Key.Key_CapsLock,
                Qt.Key.Key_Super_L, Qt.Key.Key_Super_R,
            }
            k = event.key()
            if k in mod_keys:
                return
            mods = []
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier: mods.append("ctrl")
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:   mods.append("shift")
            if event.modifiers() & Qt.KeyboardModifier.AltModifier:     mods.append("alt")
            key_name = QKeySequence(k).toString().lower()
            combo = "+".join(mods + [key_name]) if mods else key_name

            self._shortcut_dradidas = combo
            entry.setText(combo)
            entry.setStyleSheet(f"""
                QLineEdit {{
                    background-color: #252b3b;
                    color: {self.ACCENT};
                    border: none;
                    border-radius: 4px;
                    padding: 4px;
                }}
            """)
            entry.removeEventFilter(self._dradidas_capture_filter)
            self._dradidas_capture_filter = None
            self.setFocus()
            self._apply_shortcuts()
            self._register_dradidas_hotkey()

        class _KeyFilter(QObject):
            def __init__(self, cb):
                super().__init__()
                self._cb = cb
            def eventFilter(self, obj, evt):
                if evt.type() == QEvent.Type.KeyPress:
                    self._cb(evt)
                    return True
                return False

        self._dradidas_capture_filter = _KeyFilter(on_key)
        entry.installEventFilter(self._dradidas_capture_filter)

    def _register_dradidas_hotkey(self):
        """Enregistre (ou retire) le hotkey Dradidas indépendamment des autres raccourcis."""
        if not KEYBOARD_OK:
            return
        try:
            import keyboard as _kb
            if hasattr(self, "_dradidas_hotkey_ref") and self._dradidas_hotkey_ref:
                try:
                    _kb.remove_hotkey(self._dradidas_hotkey_ref)
                except Exception:
                    pass
                self._dradidas_hotkey_ref = None
            if self._shortcut_dradidas:
                self._dradidas_hotkey_ref = _kb.add_hotkey(
                    self._shortcut_dradidas, self._trigger_dradidas
                )
        except Exception:
            pass

    def _trigger_dradidas(self):
        """Appelé quand le raccourci Puissance Sylvestre est pressé.
        Lit le pseudo de la fenêtre Dofus active et déclenche le compteur Dradidas.
        """
        enabled = getattr(self, "_mode_enabled", {}).get("dradidas", [True])
        if not enabled[0]:
            return
        if not is_dofus_foreground():
            return
        try:
            import win32gui
            hwnd  = win32gui.GetForegroundWindow()
            title = win32gui.GetWindowText(hwnd)
            pseudo = extract_pseudo_from_title(title, hwnd)
            if pseudo and self._dradidas_manager.is_sadida(pseudo):
                self._dradidas_manager.trigger(pseudo)
                remaining = self._dradidas_manager.get_skip_remaining(pseudo)
                tours = "tour" if remaining <= 1 else "tours"
                self.log_msg(
                    f"🌿 [DRADIDAS] {pseudo} — Puissance Sylvestre activée"
                    f" ({remaining} {tours} ignorés)",
                    "ok"
                )
            elif pseudo:
                self.log_msg(
                    f"🌿 [DRADIDAS] {pseudo} — non marqué comme Sadida", "dim"
                )
        except Exception:
            pass
        
    def _rebuild_dradidas_char_list(self):
        """Reconstruit la liste des personnages détectés avec cases à cocher Sadida."""
        # Vider le container
        for i in reversed(range(self._dradidas_chars_layout.count())):
            w = self._dradidas_chars_layout.itemAt(i).widget()
            if w:
                w.deleteLater()

        if not self._char_order:
            lbl = QLabel(t("tab.outils.mode.dradidas.notfound"))
            lbl.setFont(self.S.Info.font)
            lbl.setStyleSheet(f"color: {self.GRAY}; background: transparent;")
            self._dradidas_chars_layout.addWidget(lbl)
            return

        for _, pseudo in self._char_order:
            self._create_dradidas_char_row(pseudo)

    def _create_dradidas_char_row(self, pseudo: str):
        """Ligne personnage : nom à gauche, case Sadida à droite."""
        is_sadida = self._dradidas_manager.is_sadida(pseudo)

        row = QWidget()
        row.setStyleSheet(f"background-color: {self.CARD}; border-radius: 4px;")
        row.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(10, 6, 10, 6)
        row_layout.setSpacing(8)

        lbl_name = QLabel(pseudo)
        lbl_name.setFont(self.S.Bouton.font_principal)
        lbl_name.setStyleSheet(f"color: {self.TEXT}; background: transparent;")
        row_layout.addWidget(lbl_name, stretch=1)

        # Badge tours restants
        remaining = self._dradidas_manager.get_skip_remaining(pseudo)
        lbl_badge = QLabel(
            f"⏸ {remaining} tour{'s' if remaining > 1 else ''}" if remaining > 0 else ""
        )
        lbl_badge.setFont(self.S.Info.font)
        lbl_badge.setStyleSheet(
            f"color: {self.GREEN}; background: transparent;" if remaining > 0
            else f"color: transparent; background: transparent;"
        )
        row_layout.addWidget(lbl_badge)
        row._badge = lbl_badge  # ref pour _refresh_dradidas_badges

        # Case à cocher Sadida
        cb = QLabel("🌿" if is_sadida else "○")
        cb.setFont(QFont("Segoe UI", 13))
        cb.setStyleSheet(
            f"color: {self.GREEN}; background: transparent;" if is_sadida
            else f"color: {self.GRAY}; background: transparent;"
        )
        row_layout.addWidget(cb)

        def _toggle(event=None, p=pseudo, c=cb):
            if self._dradidas_manager.is_sadida(p):
                new_set = self._dradidas_manager.sadida_pseudos - {p}
            else:
                new_set = self._dradidas_manager.sadida_pseudos | {p}
            self._dradidas_manager.set_sadidas(new_set)
            self._dradidas_turns = self._dradidas_manager.turns
            self._persist_config()
            # Mettre à jour la case visuellement
            is_now = self._dradidas_manager.is_sadida(p)
            c.setText("🌿" if is_now else "○")
            c.setStyleSheet(
                f"color: {self.GREEN}; background: transparent;" if is_now
                else f"color: {self.GRAY}; background: transparent;"
            )

        for w in [row, lbl_name, cb]:
            w.mousePressEvent = _toggle

        self._dradidas_chars_layout.addWidget(row)

    def _refresh_dradidas_badges(self):
        if not hasattr(self, "_dradidas_chars_layout"):
            return
        for i in range(self._dradidas_chars_layout.count()):
            row = self._dradidas_chars_layout.itemAt(i).widget()
            if row is None:
                continue
            badge = getattr(row, "_badge", None)
            if badge is None:
                continue
            # Retrouver le pseudo depuis le label nom (premier QLabel du row)
            lbl_name = row.findChild(QLabel)
            if lbl_name is None:
                continue
            pseudo = lbl_name.text()
            remaining = self._dradidas_manager.get_skip_remaining(pseudo)
            if remaining > 0:
                badge.setText(f"⏸ {remaining} tour{'s' if remaining > 1 else ''}")
                badge.setStyleSheet(f"color: {self.GREEN}; background: transparent;")
            else:
                badge.setText("")
                badge.setStyleSheet("color: transparent; background: transparent;")

