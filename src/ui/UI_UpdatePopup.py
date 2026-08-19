"""
ui/UI_UpdatePopup.py
Mixin UI : lance la vérification de mise à jour et affiche la popup
d'annonce le cas échéant. Toute la logique réseau/version/téléchargement
vit dans core/update.py — ce fichier ne fait que construire l'UI et
marshaler les résultats vers le thread principal Qt.

Deux façons de mettre à jour, proposées à l'utilisateur dans la popup :
  - "Mettre à jour maintenant" : télécharge le package correspondant au
    mode de build (onefile/onedir), vérifie son SHA256, puis ferme et
    relance Dracoon automatiquement. C'est l'option recommandée.
  - "Ouvrir GitHub" : ouvre la page de release dans le navigateur, pour
    les utilisateurs qui préfèrent télécharger/installer eux-mêmes.

Pour repasser Dracoon en version 100% hors-ligne : supprime ce fichier
et core/update.py, puis retire UpdatePopupMixin des bases de App ainsi
que les deux appels d'intégration dans Main.py.
"""

import sys
import threading

from PyQt6.QtCore import Qt, QObject, QUrl, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QCursor, QDesktopServices
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QMessageBox, QWidget, QApplication, QProgressBar,
)

from core.update import (
    check_for_update_async,
    launch_update_async,
    UpdateInfo,
    UpdateShasumsMissingError,
    UpdateShasumsMismatchError,
    UpdateCancelledError,
)
from core.i18n import t


class _UpdateSignals(QObject):
    """Pont thread-safe entre les threads réseau (core.update) et le thread Qt."""
    result = pyqtSignal(object)          # UpdateInfo (phase check)
    error = pyqtSignal(object)           # Exception (phase check)
    apply_done = pyqtSignal()            # phase apply réussie -> fermer l'app
    apply_error = pyqtSignal(object)     # Exception (phase apply)
    apply_progress = pyqtSignal(str, int)  # (stage, percent) — percent=-1 si indéterminé
    apply_cancelled = pyqtSignal()       # phase apply annulée par l'utilisateur


class UpdatePopupMixin:
    """
    Mixin à ajouter aux bases de la classe App, aux côtés des autres
    mixins d'onglets. Fournit :

        self._init_update_checker()          -> à appeler une fois dans App.__init__
        self._check_for_updates(silent=True)  -> lance une vérification
        self._show_update_popup(info)         -> popup "nouvelle version"

    Attributs optionnels lus s'ils existent déjà sur self (sinon valeurs
    par défaut ci-dessous) :
        self._update_check_enabled   (bool) — vérif. auto au démarrage
        self._update_ignored_version (str|None) — version à ne plus proposer
    """

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def _init_update_checker(self):
        self._update_signals = _UpdateSignals()
        self._update_signals.result.connect(self._on_update_check_result)
        self._update_signals.error.connect(self._on_update_check_error)
        self._update_signals.apply_done.connect(self._on_update_apply_done)
        self._update_signals.apply_error.connect(self._on_update_apply_error)
        self._update_signals.apply_progress.connect(self._on_update_apply_progress)
        self._update_signals.apply_cancelled.connect(self._on_update_apply_cancelled)

        self._update_check_running = False
        self._update_check_silent = True
        self._update_apply_running = False
        self._update_cancel_event = None

        if hasattr(self, "check_update_on_launch_var"):
            # Paramètre persistant de l'onglet Paramètres (voir
            # UI_Tab_Parametres.py) : source de vérité si présent.
            self._update_check_enabled = self.check_update_on_launch_var.get()
        elif not hasattr(self, "_update_check_enabled"):
            self._update_check_enabled = True
        if not hasattr(self, "_update_ignored_version"):
            self._update_ignored_version = None
        if not hasattr(self, "_last_update_info"):
            self._last_update_info = None

    def _on_update_check_toggle(self, enabled: bool):
        """
        Callback de la case "Vérifier les mises à jour au lancement"
        (onglet Paramètres). Ne coupe QUE la vérification automatique au
        démarrage : une vérification manuelle (bouton de l'onglet Info)
        reste toujours possible — voir _check_for_updates() ci-dessous,
        qui n'applique ce flag que si silent=True.
        """
        self._update_check_enabled = enabled

    # ------------------------------------------------------------------
    # Lancement de la vérification
    # ------------------------------------------------------------------

    def _check_for_updates(self, silent: bool = True):
        """
        silent=True  : appel automatique au démarrage. Ne dérange
                       jamais l'utilisateur (pas de popup si à jour,
                       pas de popup en cas d'erreur réseau).
        silent=False : appel manuel (bouton "Vérifier les mises à
                       jour"). Affiche toujours un retour visuel.
        """
        if silent and not self._update_check_enabled:
            return
        if self._update_check_running:
            return

        self._update_check_running = True
        self._update_check_silent = silent

        if hasattr(self, "_sync_version_button"):
            self._sync_version_button()

        check_for_update_async(
            on_result=lambda info: self._update_signals.result.emit(info),
            on_error=lambda err: self._update_signals.error.emit(err),
        )

    # ------------------------------------------------------------------
    # Callbacks phase CHECK (ré-exécutés sur le thread principal Qt)
    # ------------------------------------------------------------------

    def _on_update_check_result(self, info: UpdateInfo):
        self._update_check_running = False
        silent = self._update_check_silent

        self._last_update_info = info if info.is_newer else None
        self._refresh_update_indicator()

        if not info.is_newer:
            if not silent:
                QMessageBox.information(
                    self,
                    t("update.title"),
                    t("update.up_to_date").format(version=info.current_version),
                )
            return

        if silent and info.latest_version == self._update_ignored_version:
            return  # l'utilisateur a déjà choisi d'ignorer cette version

        self._show_update_popup(info)

    def _on_update_check_error(self, error: Exception):
        self._update_check_running = False
        silent = self._update_check_silent

        if hasattr(self, "_sync_version_button"):
            self._sync_version_button()

        try:
            self.log_msg(f"Vérification de mise à jour échouée : {error}", "warn")
        except Exception:
            pass

        if not silent:
            QMessageBox.warning(
                self, t("update.title"), t("update.error").format(error=str(error))
            )

    # ------------------------------------------------------------------
    # Callbacks phase APPLY (téléchargement + lancement de update.exe)
    # ------------------------------------------------------------------

    def _on_update_apply_progress(self, stage: str, percent: int):
        bar = getattr(self, "_update_progress_bar", None)
        lbl = getattr(self, "_update_lbl_status", None)

        if stage == "download":
            if lbl is not None:
                lbl.setText(t("update.stage_downloading").format(percent=max(percent, 0)))
            if bar is not None:
                if percent < 0:
                    bar.setRange(0, 0)  # indéterminé
                else:
                    bar.setRange(0, 100)
                    bar.setValue(percent)
        elif stage == "verify":
            if lbl is not None:
                lbl.setText(t("update.stage_verify"))
            if bar is not None:
                bar.setRange(0, 0)  # vérification quasi instantanée, pas la peine d'afficher un %
        elif stage == "launch":
            if lbl is not None:
                lbl.setText(t("update.stage_launchupdater"))
            if bar is not None:
                bar.setRange(0, 0)

    def _on_update_apply_done(self):
        # Le téléchargement/vérification a réussi et update.exe est lancé
        # en sous-processus détaché : il attend maintenant que ce PID se
        # termine. On ferme proprement l'application pour le libérer.
        try:
            self.log_msg("Mise à jour téléchargée, redémarrage pour l'appliquer...", "info")
        except Exception:
            pass
        self._update_cancel_event = None
        QApplication.instance().quit()

    def _on_update_apply_cancelled(self):
        self._update_apply_running = False
        self._update_cancel_event = None
        try:
            self.log_msg("Mise à jour annulée par l'utilisateur.", "info")
        except Exception:
            pass

        lbl = getattr(self, "_update_lbl_status", None)
        bar = getattr(self, "_update_progress_bar", None)
        lnk_skip = getattr(self, "_update_lnk_skip", None)
        btn_apply = getattr(self, "_update_btn_apply", None)
        btn_later = getattr(self, "_update_btn_later", None)
        btn_github = getattr(self, "_update_btn_github", None)
        btn_cancel = getattr(self, "_update_btn_cancel", None)

        if bar is not None:
            bar.setVisible(False)
        if lbl is not None:
            lbl.setVisible(False)
        if lnk_skip is not None:
            lnk_skip.setEnabled(True)
        if btn_cancel is not None:
            btn_cancel.setVisible(False)

        for btn, restore_text_key in (
            (btn_apply, "update.apply_now"),
            (btn_later, "update.later"),
            (btn_github, "update.github"),
        ):
            if btn is not None:
                btn.setEnabled(True)
                btn.setVisible(True)
                btn.setText(t(restore_text_key))

    def _on_update_apply_error(self, error: Exception):
        self._update_apply_running = False
        self._update_cancel_event = None
        try:
            self.log_msg(f"Échec de la mise à jour automatique : {error}", "warn")
        except Exception:
            pass

        lbl = getattr(self, "_update_lbl_status", None)
        bar = getattr(self, "_update_progress_bar", None)
        lnk_skip = getattr(self, "_update_lnk_skip", None)
        btn_apply = getattr(self, "_update_btn_apply", None)
        btn_later = getattr(self, "_update_btn_later", None)
        btn_github = getattr(self, "_update_btn_github", None)
        btn_cancel = getattr(self, "_update_btn_cancel", None)

        if bar is not None:
            bar.setVisible(False)
        if lnk_skip is not None:
            lnk_skip.setEnabled(True)
        if btn_cancel is not None:
            btn_cancel.setVisible(False)

        # Dans tous les cas (erreur connue affichée inline, ou erreur
        # générique affichée en popup), on réaffiche les 3 boutons de
        # base dans leur état/texte initial.
        for btn, restore_text_key in (
            (btn_apply, "update.apply_now"),
            (btn_later, "update.later"),
            (btn_github, "update.github"),
        ):
            if btn is not None:
                btn.setEnabled(True)
                btn.setVisible(True)
                btn.setText(t(restore_text_key))

        if isinstance(error, UpdateShasumsMissingError):
            # SHASUMS.txt absent (ou sans entrée pour l'asset) : on informe
            # via le label inline, sans popup.
            if lbl is not None:
                lbl.setText(t("update.shasums_missing"))
                lbl.setVisible(True)
            return

        if isinstance(error, UpdateShasumsMismatchError):
            # Hash différent : on informe via le label inline, sans popup.
            # L'utilisateur peut relancer une mise à jour normalement avec
            # "Mettre à jour maintenant".
            if lbl is not None:
                lbl.setText(t("update.hash_mismatch"))
                lbl.setVisible(True)
            return

        # Cas générique (réseau, asset absent, etc.) : popup d'erreur.
        if lbl is not None:
            lbl.setVisible(False)

        QMessageBox.warning(
            self, t("update.title"), t("update.apply_error").format(error=str(error))
        )

    # ------------------------------------------------------------------
    # Indicateurs persistants (badge header + onglet Info)
    # ------------------------------------------------------------------

    def _refresh_update_indicator(self):
        """
        Met à jour le badge du header et le bouton de l'onglet Info selon
        self._last_update_info. Utilise hasattr() car ces widgets/méthodes
        peuvent ne pas encore exister (onglet Info pas encore construit, ou
        appel avant _build_ui côté header — normalement jamais le cas).
        """
        info = getattr(self, "_last_update_info", None)

        if hasattr(self, "_update_badge"):
            self._update_badge.setVisible(info is not None)
            if info is not None:
                self._update_badge.setText(t("update.badge"))

        # Le bouton "Vérifier" / "MAJ disponible" de l'onglet Info gère
        # lui-même son style (idle/checking/available) — voir
        # TabInfosMixin._sync_version_button() dans UI_Tab_Infos.py.
        if hasattr(self, "_sync_version_button"):
            self._sync_version_button()

    # ------------------------------------------------------------------
    # Popup "nouvelle version disponible"
    # ------------------------------------------------------------------

    def _show_update_popup(self, info: UpdateInfo):
        popup = QDialog(self)
        popup.setWindowFlags(
            Qt.WindowType.Dialog | Qt.WindowType.WindowTitleHint | Qt.WindowType.WindowCloseButtonHint
        )
        popup.setWindowTitle(t("update.title"))
        popup.setStyleSheet(f"background-color: {self.BG}; color: {self.TEXT};")
        popup.setMinimumSize(560, 460)
        popup.setWindowModality(Qt.WindowModality.ApplicationModal)

        FONT_TITRE = QFont("Segoe UI", 16, QFont.Weight.Bold)
        FONT_BODY = QFont("Segoe UI", 10)
        FONT_SMALL = QFont("Segoe UI", 9)
        FONT_BTN = QFont("Segoe UI", 11, QFont.Weight.Bold)

        root = QVBoxLayout(popup)
        root.setContentsMargins(26, 22, 26, 18)
        root.setSpacing(10)

        # ── Titre ────────────────────────────────────────────────────────
        lbl_title = QLabel("🚀 " + t("update.available"))
        lbl_title.setFont(FONT_TITRE)
        lbl_title.setStyleSheet(f"color: {self.ACCENT}; background: transparent;")
        root.addWidget(lbl_title)

        # ── Ligne de version ─────────────────────────────────────────────
        lbl_versions = QLabel(
            t("update.version.line").format(current=info.current_version, latest=info.latest_version)
        )
        lbl_versions.setFont(FONT_BODY)
        lbl_versions.setStyleSheet(f"color: {self.GRAY}; background: transparent;")
        root.addWidget(lbl_versions)

        # ── Changelog ────────────────────────────────────────────────────
        lbl_changelog_title = QLabel(t("update.changelog"))
        lbl_changelog_title.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        lbl_changelog_title.setStyleSheet(
            f"color: {self.TEXT}; background: transparent; letter-spacing: 1px;"
        )
        root.addWidget(lbl_changelog_title)

        txt_changelog = QTextEdit()
        txt_changelog.setReadOnly(True)
        txt_changelog.setPlainText(info.changelog.strip() or t("update.no_changelog"))
        txt_changelog.setStyleSheet(f"""
            QTextEdit {{
                background-color: {self.CARD};
                color: {self.TEXT};
                border: 1px solid {self.GRAY};
                border-radius: 6px;
                font-family: "Segoe UI";
                font-size: 10pt;
                padding: 8px;
            }}
        """)
        root.addWidget(txt_changelog, stretch=1)

        # ── Statut + progression de la mise à jour automatique (masqués par défaut) ──
        lbl_status = QLabel("")
        lbl_status.setFont(FONT_SMALL)
        lbl_status.setStyleSheet(f"color: {self.ACCENT}; background: transparent;")
        lbl_status.setVisible(False)
        root.addWidget(lbl_status)
        self._update_lbl_status = lbl_status

        progress_bar = QProgressBar()
        progress_bar.setTextVisible(False)
        progress_bar.setFixedHeight(6)
        progress_bar.setRange(0, 100)
        progress_bar.setValue(0)
        progress_bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: {self.CARD};
                border: none;
                border-radius: 3px;
            }}
            QProgressBar::chunk {{
                background-color: {self.ACCENT};
                border-radius: 3px;
            }}
        """)
        progress_bar.setVisible(False)
        root.addWidget(progress_bar)
        self._update_progress_bar = progress_bar

        # ── Boutons ──────────────────────────────────────────────────────
        btn_row = QWidget()
        btn_row.setStyleSheet("background: transparent;")
        btn_layout = QHBoxLayout(btn_row)
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_layout.setSpacing(10)

        btn_later = QPushButton(t("update.later"))
        btn_later.setFont(FONT_BTN)
        btn_later.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_later.setStyleSheet(f"""
            QPushButton {{
                background-color: {self.PANEL};
                color: {self.TEXT};
                border: 1px solid {self.GRAY};
                border-radius: 5px;
                padding: {self.S.Bouton.pady_principal}px {self.S.Bouton.padx_principal}px;
            }}
            QPushButton:hover {{ border-color: {self.ACCENT}; }}
            QPushButton:disabled {{ color: {self.GRAY}; }}
        """)

        btn_github = QPushButton(t("update.github"))
        btn_github.setFont(FONT_BTN)
        btn_github.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_github.setStyleSheet(f"""
            QPushButton {{
                background-color: {self.PANEL};
                color: {self.TEXT};
                border: 1px solid {self.GRAY};
                border-radius: 5px;
                padding: {self.S.Bouton.pady_principal}px {self.S.Bouton.padx_principal}px;
            }}
            QPushButton:hover {{ border-color: {self.ACCENT}; }}
            QPushButton:disabled {{ color: {self.GRAY}; }}
        """)

        btn_apply = QPushButton(t("update.apply_now"))
        btn_apply.setFont(FONT_BTN)
        btn_apply.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_apply.setStyleSheet(f"""
            QPushButton {{
                background-color: {self.ACCENT};
                color: {self.BG};
                border: none;
                border-radius: 5px;
                padding: {self.S.Bouton.pady_principal}px {self.S.Bouton.padx_principal}px;
            }}
            QPushButton:hover {{ background-color: #e0952a; }}
            QPushButton:disabled {{ background-color: {self.PANEL}; color: {self.GRAY}; }}
        """)

        btn_cancel = QPushButton(t("update.cancel_button"))
        btn_cancel.setFont(FONT_BTN)
        btn_cancel.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_cancel.setStyleSheet(f"""
            QPushButton {{
                background-color: {self.PANEL};
                color: {self.TEXT};
                border: 1px solid #c0392b;
                border-radius: 5px;
                padding: {self.S.Bouton.pady_principal}px {self.S.Bouton.padx_principal}px;
            }}
            QPushButton:hover {{ border-color: #e74c3c; color: #e74c3c; }}
            QPushButton:disabled {{ color: {self.GRAY}; border-color: {self.GRAY}; }}
        """)
        btn_cancel.setVisible(False)

        # Gardés sur self au cas où d'autres méthodes du mixin voudraient
        # y accéder plus tard.
        self._update_btn_later = btn_later
        self._update_btn_github = btn_github
        self._update_btn_apply = btn_apply
        self._update_btn_cancel = btn_cancel

        def _close():
            popup.accept()

        def _open_github():
            QDesktopServices.openUrl(QUrl(info.release_url))
            popup.accept()

        def _skip_version():
            # Action immédiate et autonome : on retient la version à ignorer
            # et on ferme la popup, sans dépendre d'un second clic ailleurs.
            self._update_ignored_version = info.latest_version
            if hasattr(self, "_persist_config"):
                try:
                    self._persist_config()
                except Exception:
                    pass
            popup.accept()

        def _apply_now():
            if self._update_apply_running:
                return
            self._update_apply_running = True

            btn_apply.setVisible(False)
            btn_later.setVisible(False)
            btn_github.setEnabled(False)
            lnk_skip.setEnabled(False)
            btn_cancel.setVisible(True)
            btn_cancel.setEnabled(True)
            lbl_status.setText(t("update.stage_launchdownload"))
            lbl_status.setVisible(True)
            progress_bar.setRange(0, 100)
            progress_bar.setValue(0)
            progress_bar.setVisible(True)

            # On ne popup.accept() PAS tout de suite : on garde la fenêtre
            # ouverte pour montrer la progression et pouvoir réafficher une
            # erreur dedans si le téléchargement échoue. La fermeture réelle
            # de l'app se fait dans _on_update_apply_done (hors de ce popup).
            self._update_popup_ref = popup  # évite le garbage-collect prématuré

            _, cancel_event = launch_update_async(
                info,
                on_done=lambda: self._update_signals.apply_done.emit(),
                on_error=lambda err: self._update_signals.apply_error.emit(err),
                on_progress=lambda stage, percent: self._update_signals.apply_progress.emit(stage, percent),
                on_cancelled=lambda: self._update_signals.apply_cancelled.emit(),
            )
            self._update_cancel_event = cancel_event

        def _cancel_apply():
            if self._update_cancel_event is not None:
                self._update_cancel_event.set()
            btn_cancel.setEnabled(False)
            lbl_status.setText(t("update.cancelling"))

        btn_later.clicked.connect(_close)
        btn_github.clicked.connect(_open_github)
        btn_apply.clicked.connect(_apply_now)
        btn_cancel.clicked.connect(_cancel_apply)

        btn_layout.addWidget(btn_later)
        btn_layout.addWidget(btn_github)
        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(btn_apply, stretch=1)
        root.addWidget(btn_row)

        # ── Lien "ignorer cette version" ─────────────────────────────────
        # Sous les boutons principaux, discret (pas de bordure ni de fond),
        # agit immédiatement au clic — plus besoin de cocher puis de
        # cliquer sur un autre bouton pour que ça prenne effet.
        skip_row = QWidget()
        skip_row.setStyleSheet("background: transparent;")
        skip_layout = QHBoxLayout(skip_row)
        skip_layout.setContentsMargins(0, 4, 0, 0)

        lnk_skip = QPushButton(t("update.skip_version"))
        lnk_skip.setFont(FONT_SMALL)
        lnk_skip.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        lnk_skip.setFlat(True)
        lnk_skip.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {self.GRAY};
                border: none;
                padding: 2px 0px;
                text-decoration: underline;
            }}
            QPushButton:hover {{ color: {self.ACCENT}; }}
            QPushButton:disabled {{ color: {self.GRAY}; }}
        """)
        lnk_skip.clicked.connect(_skip_version)
        skip_layout.addWidget(lnk_skip)
        skip_layout.addStretch()
        root.addWidget(skip_row)

        self._update_lnk_skip = lnk_skip

        def _center_popup():
            pw, ph = popup.width(), popup.height()
            rx = self.x() + (self.width() - pw) // 2
            ry = self.y() + (self.height() - ph) // 2
            popup.move(rx, ry)

        popup.open()
        QTimer.singleShot(0, _center_popup)
