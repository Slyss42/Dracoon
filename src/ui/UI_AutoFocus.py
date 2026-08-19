"""
UI_AutoFocus.py
Mixin gérant la partie UI du moteur AutoFocus.

Méthodes fournies :
  - _is_type_fully_active
  - _style_global_af_btn
  - _update_global_btn_style
  - _toggle_type
  - _style_af_char_btn
  - _toggle_char_af_type
  - _rebuild_af_char_list
"""

from PyQt6.QtWidgets import QPushButton

from core.autofocus import AutoFocusCoreMixin

class AutoFocusMixin(AutoFocusCoreMixin):
    """
    Mixin autonome pour le moteur AutoFocus.
    La logique pure (démarrage, écoute, surveillance fenêtres) est dans AutoFocusCoreMixin.

    Dépendances attendues sur self (fournies par App / TabPersonnagesMixin) :
      - self.BG, self.PANEL, self.GRAY, self.ACCENT, self.RED
      - self.S.Bouton.pady_type_notifnobold
      - self.type_vars   (dict[str, _BoolVar])
      - self.type_btns   (dict[str, QPushButton])
      - self._char_af_overrides (dict)
      - self._char_icons        (dict)
      - self._char_order        (list[tuple[hwnd, pseudo]])
      - self._window_snapshot   (dict[int, str])
      - self._preset_needs_reset (bool)
      - self._running   (bool)
      - self._loop      (asyncio.AbstractEventLoop | None)
      - self._n_notifs, self._n_matches, self._n_focus  (int)
      - self._dradidas_manager
      - self.maximize_on_launch_var, self.shorten_title_var,
        self.remove_notif_var, self.debug_var   (_BoolVar)
      - self.log_msg(msg, tag)
      - self._persist_config()
      - self._rebuild_char_list()
      - self.refresh_characters()
    """

    # ------------------------------------------------------------------
    # Toggles globaux AutoFocus
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
    # Toggle AutoFocus par personnage / type
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
