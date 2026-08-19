"""
core_autofocus.py
Moteur AutoFocus (logique pure, sans UI).

Méthodes fournies :
  - _set_status
  - _start
  - _stop
  - _run_async_loop
  - _watch_windows
  - _listen
"""

import asyncio
import threading
import time

from PyQt6.QtCore import QTimer

from core.config import WIN32_OK, WINSDK_OK, NOTIF_TYPES, _is_dofus_pid, TITLE_PATTERN, LOADING_PATTERN, shortened_titles
from core.windows import focus_dofus_window, list_dofus_windows, extract_pseudo_from_title
from core.icons import set_window_icon, _restore_original_icon
try:
    import win32gui, win32process, win32con
except Exception:
    pass

try:
    import winsdk.windows.ui.notifications.management as winman
    import winsdk.windows.ui.notifications as winnot
except Exception:
    pass


class AutoFocusCoreMixin:
    """
    Mixin contenant le moteur AutoFocus (logique pure).

    Dépendances attendues sur self (fournies par App / TabPersonnagesMixin) :
      - self.RED
      - self.type_vars            (dict[str, _BoolVar])
      - self._char_af_overrides   (dict)
      - self._char_icons          (dict)
      - self._char_order          (list[tuple[hwnd, pseudo]])
      - self._window_snapshot     (dict[int, str])
      - self._preset_needs_reset  (bool)
      - self._running             (bool)
      - self._loop                (asyncio.AbstractEventLoop | None)
      - self._n_notifs, self._n_matches, self._n_focus  (int)
      - self._dradidas_manager
      - self.maximize_on_launch_var, self.shorten_title_var,
        self.remove_notif_var, self.debug_var   (_BoolVar)
      - self.log_msg(msg, tag)
      - self.refresh_characters()
    """

    # ------------------------------------------------------------------
    # Statut (stub — plus d'UI dédiée)
    # ------------------------------------------------------------------

    def _set_status(self, text: str, color: str):
        pass  # stub — plus d'UI de statut dédiée

    # ------------------------------------------------------------------
    # Moteur AutoFocus : démarrage / arrêt
    # ------------------------------------------------------------------

    def _start(self):
        if not WIN32_OK or not WINSDK_OK:
            self.log_msg("AutoFocus impossible : dépendances manquantes (pywin32 / winsdk).", "error")
            return
        self._running = True
        self.log_msg("AutoFocus démarré.", "ok")
        threading.Thread(target=self._run_async_loop, daemon=True).start()
        threading.Thread(target=self._watch_windows,  daemon=True).start()

    def _stop(self):
        self._running = False
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
        self.log_msg("AutoFocus arrêté.", "dim")

    def _run_async_loop(self):
        import ctypes
        ctypes.windll.ole32.CoInitializeEx(None, 0x2)  # COINIT_APARTMENTTHREADED
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._listen())
        except Exception as e:
            QTimer.singleShot(0, lambda ex=e: self.log_msg(f"Erreur fatale AF : {ex}", "error"))
            self._running = False
            QTimer.singleShot(0, lambda: self._set_status("Erreur — relancez AF", self.RED))
        finally:
            self._loop.close()
            ctypes.windll.ole32.CoUninitialize()

    # ------------------------------------------------------------------
    # Surveillance des fenêtres (détection automatique + maximize)
    # ------------------------------------------------------------------

    def _watch_windows(self):
        while self._running:
            try:
                current: dict[int, str] = {}

                def _cb(hwnd, _):
                    if not win32gui.IsWindowVisible(hwnd):
                        return True
                    try:
                        _, pid = win32process.GetWindowThreadProcessId(hwnd)
                        if not _is_dofus_pid(pid):
                            return True
                    except Exception:
                        return True
                    title = win32gui.GetWindowText(hwnd)
                    if hwnd in shortened_titles or TITLE_PATTERN.match(title) or LOADING_PATTERN.match(title):
                        current[hwnd] = title
                    return True

                win32gui.EnumWindows(_cb, None)

                if current != self._window_snapshot:
                    new_hwnds  = set(current.keys()) - set(self._window_snapshot.keys())
                    gone_hwnds = set(self._window_snapshot.keys()) - set(current.keys())

                    for hwnd in new_hwnds:
                        try:
                            if self.maximize_on_launch_var.get():
                                win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
                        except Exception as e:
                            self.log_msg(f"[watch_windows] maximize échoué hwnd={hwnd} : {e}", "debug")
                        try:
                            title = current.get(hwnd, "")
                            pseudo = (shortened_titles.get(hwnd, (None,))[0]
                                      or extract_pseudo_from_title(title))
                            if pseudo and pseudo in self._char_icons:
                                cfg_icon = self._char_icons[pseudo]
                                set_window_icon(hwnd,
                                                cfg_icon.get("color"),
                                                cfg_icon.get("portrait"))
                        except Exception as e:
                            self.log_msg(f"[watch_windows] icône échouée hwnd={hwnd} : {e}", "debug")

                    for hwnd in gone_hwnds:
                        shortened_titles.pop(hwnd, None)

                    # Détection loading pattern — toujours actif
                    for hwnd, title in current.items():
                        old_title = self._window_snapshot.get(hwnd)
                        if old_title is not None and title != old_title:
                            if LOADING_PATTERN.match(title):
                                self._preset_needs_reset = True

                    # Titres changés sur hwnds existants (ex: changement de personnage)
                    for hwnd, title in current.items():
                        old_title = self._window_snapshot.get(hwnd)
                        if old_title is None or title == old_title:
                            continue

                        # ── Icône : restaurer puis réappliquer selon le nouveau pseudo ──
                        try:
                            if LOADING_PATTERN.match(title):
                                # Chargement → icône de base
                                _restore_original_icon(hwnd)
                            else:
                                # Pseudo final (avec ou sans suffixe Dofus)
                                new_pseudo = extract_pseudo_from_title(title) or title.strip()
                                if new_pseudo and new_pseudo in self._char_icons:
                                    cfg_icon = self._char_icons[new_pseudo]
                                    set_window_icon(hwnd,
                                                    cfg_icon.get("color"),
                                                    cfg_icon.get("portrait"))
                                else:
                                    _restore_original_icon(hwnd)
                        except Exception as e:
                             self.log_msg(f"[watch_windows] maj icône hwnd={hwnd} : {e}", "debug")

                        if self.shorten_title_var.get():
                            if LOADING_PATTERN.match(title):
                                shortened_titles.pop(hwnd, None)
                            else:
                                pseudo = extract_pseudo_from_title(title)
                                if pseudo:
                                    shortened_titles[hwnd] = (pseudo, title)
                                    win32gui.SetWindowText(hwnd, pseudo)

                    self._window_snapshot = current
                    QTimer.singleShot(0, self.refresh_characters)

            except Exception as e:
                self.log_msg(f"[watch_windows] Erreur : {e}", "warn")

            # ── Surveillance Focus Assist (changement d'état) ──
            try:
                import winreg
                _key = winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\CloudStore\Store\DefaultAccount"
                    r"\Current\default$windows.data.notifications.quiethourssettings"
                    r"\windows.data.notifications.quiethourssettings"
                )
                _data, _ = winreg.QueryValueEx(_key, "Data")
                winreg.CloseKey(_key)
                _mode = _data[1] if len(_data) > 1 else 0
            except Exception:
                _mode = -1  # illisible

            if not hasattr(self, "_fa_mode_last"):
                self._fa_mode_last = _mode  # init silencieuse au premier tour

            if _mode != self._fa_mode_last:
                _FA_LABELS = {0: "OFF", 1: "Priorité uniquement", 2: "Alarmes seulement", -1: "illisible"}
                prev = _FA_LABELS.get(self._fa_mode_last, str(self._fa_mode_last))
                curr = _FA_LABELS.get(_mode, str(_mode))
                tag  = "warn" if _mode not in (0, -1) else "ok"
                self.log_msg(f"Focus Assist changé : {prev} → {curr}", tag)
                self._fa_mode_last = _mode
            time.sleep(0.3)

    # ------------------------------------------------------------------
    # Écoute des notifications (moteur principal)
    # ------------------------------------------------------------------

    async def _listen(self):
        import winreg

        # ════════════════════════════════════════════════════════════════════
        # 1) PARAMÈTRE 1/4 : AUTORISATION D'ACCÈS DES APPS AUX NOTIFICATIONS
        # ════════════════════════════════════════════════════════════════════
        listener = winman.UserNotificationListener.current
        access = await listener.request_access_async()

        if access == winman.UserNotificationListenerAccessStatus.ALLOWED:
            self.log_msg("✅ Paramètre 1/4 : Autorisation d'accès aux notifications accordée à l'application.", "ok")
            app_access_ok = True
        else:
            self.log_msg("❌ Paramètre 1/4 : L'accès des applications aux notifications est REFUSÉ / BLOQUÉ.", "error")
            app_access_ok = False

        # ════════════════════════════════════════════════════════════════════
        # DIAGNOSTIC DES AUTRES PARAMÈTRES (S'EXÉCUTE DANS TOUS LES CAS)
        # ════════════════════════════════════════════════════════════════════
        try:
            # 2) PARAMÈTRE 2/4 : NOTIFICATIONS GLOBALES DE WINDOWS
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\PushNotifications") as key:
                    toast_enabled, _ = winreg.QueryValueEx(key, "ToastEnabled")
                if toast_enabled == 0:
                    self.log_msg("❌ Paramètre 2/4 : Les notifications Windows générales sont DÉSACTIVÉES.", "error")
                else:
                    self.log_msg("✅ Paramètre 2/4 : Les notifications Windows globales sont activées.", "ok")
            except (FileNotFoundError, OSError):
                self.log_msg("✅ Paramètre 2/4 : Les notifications Windows globales sont activées (par défaut).", "ok")

            # 3) PARAMÈTRE 3/4 : AUTORISATION SPÉCIFIQUE À DOFUS
            try:
                notif_base = r"Software\Microsoft\Windows\CurrentVersion\Notifications\Settings"
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, notif_base) as base_key:
                    i = 0
                    dofus_entries = []
                    while True:
                        try:
                            subkey_name = winreg.EnumKey(base_key, i)
                            if "dofus" in subkey_name.lower():
                                dofus_entries.append(subkey_name)
                            i += 1
                        except OSError:
                            break

                if not dofus_entries:
                    self.log_msg("⚠️ Paramètre 3/4 : Notifications Dofus : aucune entrée trouvée dans le registre (le jeu n'a pas encore émis de toast).", "warn")
                else:
                    for aumid in dofus_entries:
                        try:
                            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, f"{notif_base}\\{aumid}") as sub:
                                enabled, _ = winreg.QueryValueEx(sub, "Enabled")
                            if enabled == 0:
                                self.log_msg(f"❌ Paramètre 3/4 : Notifications DÉSACTIVÉES spécifiquement pour : {aumid}", "error")
                            else:
                                self.log_msg(f"✅ Paramètre 3/4 : Notifications activées pour : {aumid}", "ok")
                        except FileNotFoundError:
                            self.log_msg(f"✅ Paramètre 3/4 : Notifications activées par défaut pour : {aumid}", "ok")
            except Exception as e:
                self.log_msg(f"Diagnostic (Notifs Dofus) : Erreur registre — {e}", "warn")

            # 4) PARAMÈTRE 4/4 : MODE CONCENTRATION / NE PAS DÉRANGER (W10 & W11)
            focus_active = False
            fa_label = "OFF"

            try:
                # Test de la clé principale FocusAssist
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\FocusAssist") as key:
                    focus_mode, _ = winreg.QueryValueEx(key, "FocusAssistMode")
                if focus_mode != 0:
                    focus_active = True
                    _LABELS = {1: "Priorité uniquement", 2: "Alarmes seulement"}
                    fa_label = _LABELS.get(focus_mode, f"Inconnu ({focus_mode})")
            except (FileNotFoundError, OSError):
                # Si absent (ex: Windows 11 propre), test du flag "Ne pas déranger"
                try:
                    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Notifications\Settings") as key:
                        dnd_val, _ = winreg.QueryValueEx(key, "NOC_GLOBAL_SETTING_DND")
                    if dnd_val == 1:
                        focus_active = True
                        fa_label = "Ne pas déranger"
                except (FileNotFoundError, OSError):
                    pass  # Clés absentes = Mode concentration désactivé par défaut

            if focus_active:
                # Mis en ROUGE ("error") car c'est synonyme de bug
                self.log_msg(f"❌ Paramètre 4/4 : Mode Concentration / Ne Pas Déranger est ACTIF : {fa_label} (Les notifications vont bugger !)", "error")
            else:
                self.log_msg("✅ Paramètre 4/4 : Mode Concentration / Ne Pas Déranger : OFF (Normal)", "ok")

        except Exception as e:
            self.log_msg(f"Diagnostic : Erreur générale — {e}", "warn")

        # ════════════════════════════════════════════════════════════════════
        # FIN DU DIAGNOSTIC & ARRÊT SI LE PARAMÈTRE 1 EST BLOQUANT
        # ════════════════════════════════════════════════════════════════════
        if not app_access_ok:
            QTimer.singleShot(0, lambda: self.log_msg(
                "Moteur arrêté : L'application n'a pas les droits nécessaires. "
                "Activez-les dans vos Paramètres Windows.", "error"))
            QTimer.singleShot(0, self._stop)
            return

        seen_ids: set[int] = set()
        seen_order: list[int] = []

        event      = asyncio.Event()
        use_events = False
        token      = None

        def on_notif_changed(sender, args):
            try:
                if self._loop and self._loop.is_running():
                    self._loop.call_soon_threadsafe(event.set)
            except Exception:
                pass

        try:
            token = listener.add_notification_changed(on_notif_changed)
            use_events = True
            self.log_msg("Mode event-driven actif (détection instantanée).", "ok")
        except Exception:
            self.log_msg("Mode polling actif (0.3 s).", "dim")

        try:
            while self._running:
                if use_events:
                    try:
                        await asyncio.wait_for(event.wait(), timeout=30.0)
                    except asyncio.TimeoutError:
                        pass
                    except asyncio.CancelledError:
                        break
                    event.clear()
                else:
                    try:
                        await asyncio.sleep(0.3)
                    except asyncio.CancelledError:
                        break

                try:
                    notifications = await listener.get_notifications_async(
                        winnot.NotificationKinds.TOAST)
                    new_notifs = [n for n in notifications if n.id not in seen_ids]

                    if new_notifs:
                        self._n_notifs += len(new_notifs)

                    for notif in new_notifs:
                        seen_ids.add(notif.id)
                        seen_order.append(notif.id)

                        if self.remove_notif_var.get():
                            try:
                                listener.remove_notification(notif.id)
                            except Exception:
                                pass
                        try:
                            binding = notif.notification.visual.get_binding(
                                winnot.KnownNotificationBindings.toast_generic)
                            if binding is None:
                                continue

                            elements = [e.text for e in binding.get_text_elements()]
                            if not elements:
                                continue

                            notif_title = elements[0]
                            notif_body  = elements[1] if len(elements) > 1 else ""

                            pseudo = extract_pseudo_from_title(notif_title)
                            if not pseudo:
                                continue

                            matched_type  = None
                            matched_emoji = "🔔"
                            for type_key, patterns, emoji in NOTIF_TYPES:
                                if any(p.search(notif_body) for p in patterns):
                                    matched_type  = type_key
                                    matched_emoji = emoji
                                    break

                            if matched_type is None:
                                continue

                            if not self.type_vars[matched_type].get():
                                continue

                            if self._char_af_overrides:
                                _ov = self._char_af_overrides.get(pseudo)
                                if _ov is not None and _ov.get(matched_type) is False:
                                    continue

                            # ── Dradidas ──────────────────────────────────────
                            if matched_type == "combat" and self._dradidas_manager.has_active_skips():
                                _skip, _left = self._dradidas_manager.should_skip_combat(pseudo)
                                if _skip:
                                    _tours = "tour" if _left <= 1 else "tours"
                                    QTimer.singleShot(0, lambda p=pseudo, l=_left, t=_tours: self.log_msg(
                                        f"🌿 [DRADIDAS] {p} — tour ignoré ({l} {t} restant{'s' if l > 1 else ''})",
                                        "dim"))
                                    if hasattr(self, "_refresh_dradidas_badges"):
                                        QTimer.singleShot(0, self._refresh_dradidas_badges)
                                    continue

                            self._n_matches += 1
                            QTimer.singleShot(0, lambda me=matched_emoji, mt=matched_type, p=pseudo, b=notif_body:
                                self.log_msg(f"{me} [{mt.upper()}] {p} — {b}", "info"))

                            if WIN32_OK:
                                try:
                                    _fg = win32gui.GetForegroundWindow()
                                    if _fg:
                                        self._prev_hwnd = _fg
                                except Exception:
                                    pass

                            ok, detail = focus_dofus_window(pseudo)
                            if ok:
                                self._n_focus += 1
                                QTimer.singleShot(0, lambda d=detail: self.log_msg(f"  ✓ Focus : {d}", "ok"))
                            else:
                                QTimer.singleShot(0, lambda d=detail: self.log_msg(f"  ✗ {d}", "error"))
                                if self.debug_var.get():
                                    wins = list_dofus_windows()
                                    for w in wins:
                                        QTimer.singleShot(0, lambda ww=w: self.log_msg(
                                            f"    Fenêtre dispo : {repr(ww)}", "debug"))

                        except Exception as e:
                            QTimer.singleShot(0, lambda ex=e: self.log_msg(
                                f"[debug] Exception notif : {ex}", "error"))

                    if len(seen_order) > 500:
                        drop = seen_order[:-250]
                        seen_order = seen_order[-250:]
                        seen_ids.difference_update(drop)

                except Exception as e:
                    QTimer.singleShot(0, lambda ex=e: self.log_msg(f"Erreur lecture : {ex}", "error"))

        finally:
            try:
                listener.remove_notification_changed(token)
            except Exception:
                pass
