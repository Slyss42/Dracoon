"""
UI_Tab_Raccourcis.py
Onglet « Raccourcis » — capture et gestion des hotkeys globaux.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFrame, QLineEdit,
)
from PyQt6.QtCore import Qt, QEvent, QObject, QMetaObject, pyqtSlot
from PyQt6.QtGui import QFont, QCursor, QKeySequence, QKeyEvent

from logic import KEYBOARD_OK, WIN32_OK, _unhook_all, CtrlShiftManager, t

try:
    import win32gui
except Exception:
    pass

try:
    import keyboard
except Exception:
    pass


class TabRaccourcisMixin:
    """
    Mixin pour la classe App.
    Fournit : _build_tab_raccourcis, _shortcut_row, capture de touche,
              _apply_shortcuts, _focus_next/prev/back/main, _cycle.
    """

    # ------------------------------------------------------------------
    # Construction de l'onglet
    # ------------------------------------------------------------------

    def _build_tab_raccourcis(self):
        f = QWidget()
        f.setStyleSheet(f"background-color: {self.BG};")
        self._tab_frames["raccourcis"] = f
        self._content.addWidget(f)

        layout = QVBoxLayout(f)
        layout.setContentsMargins(0, 10, 0, 10)
        layout.setSpacing(0)

        lbl_titre = QLabel(t("tab.raccourcis.title"))
        lbl_titre.setFont(self.S.EnTete.font)
        lbl_titre.setStyleSheet(f"color: {self.TEXT}; background: transparent;")
        lbl_titre.setContentsMargins(16, self.S.EnTete.pady_titre[0], 16, self.S.EnTete.pady_titre[1])
        layout.addWidget(lbl_titre)

        lbl_sub = QLabel(t("tab.raccourcis.description"))
        lbl_sub.setFont(self.S.Info.font)
        lbl_sub.setStyleSheet(f"color: {self.GRAY}; background: transparent;")
        lbl_sub.setContentsMargins(16, self.S.EnTete.pady_sous[0], 16, self.S.EnTete.pady_sous[1])
        layout.addWidget(lbl_sub)

        self._next_entry = self._shortcut_row(
            layout, "▶  " + t("tab.raccourcis.next.title"),
            t("tab.raccourcis.next.description"),
            self._shortcut_next, "next")
        self._prev_entry = self._shortcut_row(
            layout, "◀  " + t("tab.raccourcis.previous.title"),
            t("tab.raccourcis.previous.description"),
            self._shortcut_prev, "prev")
        self._back_entry = self._shortcut_row(
            layout, "↩  " + t("tab.raccourcis.back.title"),
            t("tab.raccourcis.back.description"),
            self._shortcut_back, "back")
        self._main_entry = self._shortcut_row(
            layout, "★  " + t("tab.raccourcis.main.title"),
            t("tab.raccourcis.main.description"),
            self._shortcut_main, "main")

        # --- Séparateur ---
        sep_container = QWidget()
        sep_container.setStyleSheet("background: transparent;")
        sep_layout = QHBoxLayout(sep_container)
        sep_layout.setContentsMargins(16, 8, 16, 4)
        sep_line = QFrame()
        sep_line.setFrameShape(QFrame.Shape.HLine)
        sep_line.setFixedHeight(1)
        sep_line.setStyleSheet(f"background-color: {self.GRAY}; border: none;")
        sep_layout.addWidget(sep_line)
        layout.addWidget(sep_container)

        #lbl_modif = QLabel("Modificateurs")
        #lbl_modif.setFont(self.S.Info.font)
        #lbl_modif.setStyleSheet(f"color: {self.GRAY}; background: transparent;")
        #lbl_modif.setContentsMargins(16, 0, 16, 4)
        #layout.addWidget(lbl_modif)

        self._ctrl_shift_entry = self._shortcut_row(
            layout, "⇧  " + t("tab.raccourcis.ctrlshift.title"),
            t("tab.raccourcis.ctrlshift.description"),
            self._shortcut_ctrl_shift, "ctrl_shift")

        if not KEYBOARD_OK:
            warn = QFrame()
            warn.setStyleSheet("background-color: #2a1a1a; border-radius: 4px;")
            warn_layout = QVBoxLayout(warn)
            warn_layout.setContentsMargins(12, 10, 12, 10)
            warn_layout.setSpacing(4)

            lbl_warn_titre = QLabel("⚠  Module 'keyboard' non chargé")
            lbl_warn_titre.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            lbl_warn_titre.setStyleSheet("color: %s; background: transparent;" % self.RED)
            warn_layout.addWidget(lbl_warn_titre)

            lbl_warn_sub = QLabel("pip install keyboard  (nécessite droits admin pour les hotkeys globaux)")
            lbl_warn_sub.setFont(QFont("Consolas", 9))
            lbl_warn_sub.setStyleSheet(f"color: {self.GRAY}; background: transparent;")
            warn_layout.addWidget(lbl_warn_sub)

            warn_container = QWidget()
            warn_container.setStyleSheet("background: transparent;")
            wc_layout = QHBoxLayout(warn_container)
            wc_layout.setContentsMargins(16, 8, 16, 8)
            wc_layout.addWidget(warn)
            layout.addWidget(warn_container)

        layout.addStretch()

    # ------------------------------------------------------------------
    # Ligne de raccourci générique
    # ------------------------------------------------------------------

    def _shortcut_row(self, parent_layout: QVBoxLayout, title: str, subtitle: str,
                      current: str | None, which: str) -> QLineEdit:
        card = QFrame()
        card.setStyleSheet(f"background-color: {self.CARD}; border-radius: 4px;")
        card_layout = QHBoxLayout(card)
        card_layout.setContentsMargins(14, 12, 14, 12)
        card_layout.setSpacing(0)

        info = QWidget()
        info.setStyleSheet("background: transparent;")
        info_layout = QVBoxLayout(info)
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(2)

        lbl_title = QLabel(title)
        lbl_title.setFont(self.S.Bouton.font_principal)
        lbl_title.setStyleSheet(f"color: {self.TEXT}; background: transparent;")
        info_layout.addWidget(lbl_title)

        lbl_sub = QLabel(subtitle)
        lbl_sub.setFont(self.S.Info.font)
        lbl_sub.setStyleSheet(f"color: {self.GRAY}; background: transparent;")
        info_layout.addWidget(lbl_sub)

        card_layout.addWidget(info, stretch=1)

        right = QWidget()
        right.setStyleSheet("background: transparent;")
        right_layout = QHBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(4)

        display = t("no.shortcut") if current is None else current
        color   = self.GRAY if current is None else self.ACCENT

        entry = QLineEdit(display)
        entry.setFont(QFont("Consolas", 11))
        entry.setAlignment(Qt.AlignmentFlag.AlignCenter)
        entry.setFixedWidth(130)
        entry.setStyleSheet(f"""
            QLineEdit {{
                background-color: #252b3b;
                color: {color};
                border: none;
                border-radius: 4px;
                padding: 5px;
            }}
        """)
        entry.focusInEvent = lambda e, w=which, en=entry: self._start_capture(en, w)
        right_layout.addWidget(entry)

        btn_aucun = QPushButton(t("no.shortcut"))
        btn_aucun.setFont(self.S.Bouton.font_petit)
        btn_aucun.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_aucun.setFlat(True)
        btn_aucun.setStyleSheet(f"""
            QPushButton {{
                background-color: #252b3b;
                color: {self.GRAY};
                border: none;
                border-radius: 4px;
                padding: {self.S.Bouton.pady_petit}px {self.S.Bouton.padx_petit}px;
            }}
            QPushButton:hover {{ color: {self.TEXT}; }}
        """)
        btn_aucun.clicked.connect(lambda checked=False, w=which: self._set_no_shortcut(w))
        right_layout.addWidget(btn_aucun)

        card_layout.addWidget(right)

        container = QWidget()
        container.setStyleSheet("background: transparent;")
        c_layout = QHBoxLayout(container)
        c_layout.setContentsMargins(16, 4, 16, 4)
        c_layout.addWidget(card)

        parent_layout.addWidget(container)
        return entry

    # ------------------------------------------------------------------
    # Effacement d'un raccourci
    # ------------------------------------------------------------------

    def _set_no_shortcut(self, which: str):
        mapping = {
            "next":       ("_shortcut_next",       "_next_entry"),
            "prev":       ("_shortcut_prev",       "_prev_entry"),
            "main":       ("_shortcut_main",       "_main_entry"),
            "back":       ("_shortcut_back",       "_back_entry"),
            "ctrl_shift": ("_shortcut_ctrl_shift", "_ctrl_shift_entry"),
        }
        attr, entry_attr = mapping[which]
        setattr(self, attr, self.NO_SHORTCUT)
        entry: QLineEdit = getattr(self, entry_attr)
        entry.setText(t("no.shortcut"))
        entry.setStyleSheet(entry.styleSheet().replace(
            f"color: {self.ACCENT}", f"color: {self.GRAY}"
        ))
        self._apply_shortcuts()

    # ------------------------------------------------------------------
    # Capture de touche
    # ------------------------------------------------------------------

    def _start_capture(self, entry: QLineEdit, which: str):
        entry.setText("Appuyez…")
        entry.setStyleSheet(entry.styleSheet().replace(
            f"color: {self.ACCENT}", f"color: {self.GRAY}"
        ))

        def on_key(event: QKeyEvent):
            mods = []
            mod_keys = {
                Qt.Key.Key_Control, Qt.Key.Key_Shift, Qt.Key.Key_Alt,
                Qt.Key.Key_Meta, Qt.Key.Key_CapsLock,
                Qt.Key.Key_Super_L, Qt.Key.Key_Super_R,
            }
            key = event.key()
            if key in mod_keys:
                return

            modifiers = event.modifiers()
            if modifiers & Qt.KeyboardModifier.ControlModifier: mods.append("ctrl")
            if modifiers & Qt.KeyboardModifier.ShiftModifier:   mods.append("shift")
            if modifiers & Qt.KeyboardModifier.AltModifier:     mods.append("alt")

            key_name_map = {
                Qt.Key.Key_Left:       "left",
                Qt.Key.Key_Right:      "right",
                Qt.Key.Key_Up:         "up",
                Qt.Key.Key_Down:       "down",
                Qt.Key.Key_Home:       "home",
                Qt.Key.Key_End:        "end",
                Qt.Key.Key_PageUp:     "page up",
                Qt.Key.Key_PageDown:   "page down",
                Qt.Key.Key_Insert:     "insert",
                Qt.Key.Key_F1:  "f1",  Qt.Key.Key_F2:  "f2",  Qt.Key.Key_F3:  "f3",
                Qt.Key.Key_F4:  "f4",  Qt.Key.Key_F5:  "f5",  Qt.Key.Key_F6:  "f6",
                Qt.Key.Key_F7:  "f7",  Qt.Key.Key_F8:  "f8",  Qt.Key.Key_F9:  "f9",
                Qt.Key.Key_F10: "f10", Qt.Key.Key_F11: "f11", Qt.Key.Key_F12: "f12",
            }

            key_name = key_name_map.get(key)
            if key_name is None:
                key_name = QKeySequence(key).toString().lower()
                if not key_name:
                    return  # touche non reconnue → on ignore

            combo = "+".join(mods + [key_name]) if mods else key_name

            entry.setText(combo)
            entry.setStyleSheet(entry.styleSheet().replace(
                f"color: {self.GRAY}", f"color: {self.ACCENT}"
            ))

            if which == "next":        self._shortcut_next = combo
            elif which == "prev":       self._shortcut_prev = combo
            elif which == "main":       self._shortcut_main = combo
            elif which == "ctrl_shift": self._shortcut_ctrl_shift = combo
            else:                       self._shortcut_back = combo

            entry.removeEventFilter(self._capture_filter)
            self._capture_filter = None
            self.setFocus()
            self._apply_shortcuts()

        class _KeyFilter(QObject):
            def __init__(self, callback):
                super().__init__()
                self._cb = callback
            def eventFilter(self, obj, event):
                if event.type() == QEvent.Type.KeyPress:
                    self._cb(event)
                    return True
                return False

        self._capture_filter = _KeyFilter(on_key)
        entry.installEventFilter(self._capture_filter)

    # ------------------------------------------------------------------
    # Application des hotkeys
    # ------------------------------------------------------------------

    def _apply_shortcuts(self, silent: bool = False):
        if not KEYBOARD_OK:
            return
        try:
            _unhook_all()
            if self._shortcut_next:       keyboard.add_hotkey(self._shortcut_next,       self._focus_next)
            if self._shortcut_prev:       keyboard.add_hotkey(self._shortcut_prev,       self._focus_prev)
            if self._shortcut_back:       keyboard.add_hotkey(self._shortcut_back,       self._focus_back)
            if self._shortcut_main:       keyboard.add_hotkey(self._shortcut_main,       self._focus_main)
            if self._shortcut_ctrl_shift: keyboard.add_hotkey(self._shortcut_ctrl_shift, self._toggle_ctrl_shift)
            self._persist_config()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Actions de focus
    # ------------------------------------------------------------------

    def _toggle_ctrl_shift(self):
        from logic import is_dofus_foreground
        self._ctrl_shift_manager.toggle(is_dofus_foreground)

    def _focus_main(self):
        from logic import is_dofus_foreground, focus_dofus_window
        if not is_dofus_foreground() or not self._char_main:
            return
        if WIN32_OK:
            try:
                fg = win32gui.GetForegroundWindow()
                if fg:
                    self._prev_hwnd = fg
            except Exception:
                pass
        focus_dofus_window(self._char_main)

    def _focus_next(self):
        from logic import is_dofus_foreground
        if not is_dofus_foreground():
            return
        QMetaObject.invokeMethod(self, "_cycle_next", Qt.ConnectionType.QueuedConnection)

    def _focus_prev(self):
        from logic import is_dofus_foreground
        if not is_dofus_foreground():
            return
        QMetaObject.invokeMethod(self, "_cycle_prev", Qt.ConnectionType.QueuedConnection)

    @pyqtSlot()
    def _cycle_next(self):
        self._cycle(+1)

    @pyqtSlot()
    def _cycle_prev(self):
        self._cycle(-1)

    def _focus_back(self):
        from logic import is_dofus_foreground, focus_window
        if not is_dofus_foreground():
            return
        if self._prev_hwnd and WIN32_OK:
            try:
                if win32gui.IsWindow(self._prev_hwnd):
                    focus_window(self._prev_hwnd)
                    return
            except Exception:
                pass
        self._cycle(-1)

    def _cycle(self, direction: int):
        if not self._char_order:
            self.refresh_characters()
        if not self._char_order:
            return

        cycle_order = [(i, h, p) for i, (h, p) in enumerate(self._char_order)
                       if p not in self._char_skip_names]
        if not cycle_order:
            cycle_order = [(i, h, p) for i, (h, p) in enumerate(self._char_order)]

        from logic import focus_window
        fg = win32gui.GetForegroundWindow() if WIN32_OK else None
        if fg:
            self._prev_hwnd = fg

        cur_pos = next((pos for pos, (_, h, _) in enumerate(cycle_order) if h == fg), None)
        new_pos = 0 if cur_pos is None else (cur_pos + direction) % len(cycle_order)
        focus_window(cycle_order[new_pos][1])
        self._ctrl_shift_manager.reapply()

