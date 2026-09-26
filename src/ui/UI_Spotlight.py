"""
UI_Spotlight.py
Palette de commande (type Spotlight) — recherche rapide pour naviguer
dans Dracoon ou déclencher des actions sans passer par un raccourci dédié.
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLayout, QLineEdit, QListWidget,
    QListWidgetItem, QPushButton, QSizePolicy, QWidget, QLabel,
    QGraphicsOpacityEffect,
)
from PyQt6.QtCore import (
    Qt, QEvent, QPoint, QRect, QRectF, QSize, QTimer,
    QPropertyAnimation, QEasingCurve,
)
from PyQt6.QtGui import QFont, QColor, QBrush, QCursor, QPainterPath, QRegion

from core.i18n import t
from UI_Spotlight_Commands import (
    build_commands,
    command_matches,
    sort_by_recency,
    mark_command_used,
    group_by_category,
)

# Nombre d'actions affichées quand le champ de recherche est vide (juste un
# aperçu des actions les plus récemment utilisées — la liste complète existe
# déjà ailleurs dans l'app, et reste accessible via le bouton "Toutes les
# actions").
DEFAULT_VISIBLE_COUNT = 3

# Hauteur maximale (px) de la zone de résultats. En dessous de ce nombre de
# lignes, la zone rétrécit pour coller au contenu ; au-delà, elle se fige à
# cette hauteur et devient scrollable.
MAX_RESULTS_HEIGHT = 280

# Mode "Toutes les commandes" (chips visibles) : la zone de résultats s'adapte
# au contenu, entre un plancher et un plafond.
#   - contenu plus petit que MIN  -> la zone garde MIN (évite que le dialogue
#     "saute" quand on passe d'un chip à l'autre) ;
#   - contenu plus grand que MAX  -> la zone se fige à MAX et devient
#     scrollable (barre verticale).
# Mettre MIN à 0 pour une hauteur strictement collée au contenu.
MIN_RESULTS_HEIGHT_ALL = 0
MAX_RESULTS_HEIGHT_ALL = 400

# Clé de catégorie spéciale pour le chip "Tout" (vue groupée avec en-têtes,
# par opposition aux chips de catégorie qui filtrent sur une seule d'entre
# elles — voir _set_category_filter).
ALL_CATEGORIES = "all"


def _is_dofus_window(hwnd) -> bool:
    """Vérifie que `hwnd` est toujours une fenêtre Dofus valide. Utilisé
    avant de restaurer le focus à la fermeture du Spotlight : sans ce
    garde-fou, en dev (script lancé depuis une console, sans Dofus au
    premier plan), c'est la console elle-même qui serait mémorisée comme
    'fenêtre précédente' puis re-forcée au premier plan à la fermeture.
    Si le projet expose déjà un équivalent dans core.windows, il est
    préférable de l'utiliser à la place de cette vérification locale."""
    try:
        import win32gui
        if not hwnd or not win32gui.IsWindow(hwnd):
            return False
        return "dofus" in win32gui.GetWindowText(hwnd).lower()
    except Exception:
        return False


def _force_foreground(hwnd):
    """Force le focus clavier OS vers `hwnd`, même si une autre fenêtre (le jeu)
    le détient actuellement. SetForegroundWindow seul est refusé par Windows si
    l'appelant n'est pas déjà au premier plan — on contourne via AttachThreadInput."""
    try:
        import win32gui, win32process, win32con
        import ctypes

        fg_hwnd = win32gui.GetForegroundWindow()
        if fg_hwnd == hwnd:
            return

        fg_thread, _ = win32process.GetWindowThreadProcessId(fg_hwnd)
        cur_thread = ctypes.windll.kernel32.GetCurrentThreadId()

        attached = False
        if fg_thread and fg_thread != cur_thread:
            attached = bool(ctypes.windll.user32.AttachThreadInput(fg_thread, cur_thread, True))

        win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
        win32gui.SetForegroundWindow(hwnd)

        if attached:
            ctypes.windll.user32.AttachThreadInput(fg_thread, cur_thread, False)
    except Exception:
        pass


class FlowLayout(QLayout):
    """Disposition horizontale qui revient à la ligne quand ça ne tient plus
    (contrairement à QHBoxLayout, qui n'a pas de mode wrap) — utilisée pour
    les chips de filtre par catégorie, dont le nombre/texte varie selon la
    langue et le nombre de catégories. Implémentation standard Qt adaptée à
    PyQt6 (Qt ne fournit pas ce layout en natif)."""

    def __init__(self, parent=None, margin=0, hspacing=6, vspacing=6):
        super().__init__(parent)
        self._hspacing = hspacing
        self._vspacing = vspacing
        self._items = []
        self.setContentsMargins(margin, margin, margin, margin)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index):
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        return size

    def _do_layout(self, rect, test_only):
        left, top, right, bottom = self.getContentsMargins()
        effective = rect.adjusted(left, top, -right, -bottom)
        x, y = effective.x(), effective.y()
        line_height = 0

        for item in self._items:
            hint = item.sizeHint()
            next_x = x + hint.width() + self._hspacing
            if next_x - self._hspacing > effective.right() and line_height > 0:
                x = effective.x()
                y += line_height + self._vspacing
                next_x = x + hint.width() + self._hspacing
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x = next_x
            line_height = max(line_height, hint.height())

        return y + line_height - rect.y() + bottom


class SpotlightDialog(QDialog):
    def __init__(self, app):
        # Pas de parent Qt ici. Tant que `app` est parent, Windows applique
        # deux comportements automatiques liés à la relation "owner" qu'on
        # ne peut pas contourner depuis Python :
        #   1) au show/activate, l'owner (Dracoon) est remonté dans le
        #      z-order juste sous la fenêtre owned → il repasse devant Dofus,
        #      même s'il n'était que "visible en arrière-plan" (pas minimisé) ;
        #   2) à la fermeture, Windows redonne nativement le focus à l'owner
        #      → ça écrase notre restauration manuelle du focus vers Dofus.
        # D'où le retour aux deux bugs dès qu'on remet `app` comme parent.
        #
        # On passe donc None, et on corrige directement les deux effets de
        # bord que ça causait quand on l'avait fait la première fois :
        #   - le crash (Qt::WA_QuitOnClose actif par défaut sans parent) →
        #     désactivé explicitement juste en dessous, indépendamment du
        #     parent ;
        #   - le bouton "Dracoon" dans la barre des tâches → on utilise
        #     Qt.WindowType.Tool au lieu de Dialog : une fenêtre "Tool"
        #     n'apparaît ni dans la barre des tâches ni dans Alt+Tab, tout
        #     en recevant le focus normalement (comme une palette d'outils).
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_QuitOnClose, False)
        self.app = app

        # Mémoriser la fenêtre qui avait le focus AVANT qu'on le vole (= Dofus)
        # pour pouvoir le lui rendre explicitement à la fermeture.
        try:
            import win32gui
            self._previous_hwnd = win32gui.GetForegroundWindow()
        except Exception:
            self._previous_hwnd = None
        self._skip_focus_restore = False

        self.commands = build_commands(app)
        # Groupes par catégorie calculés une fois pour toutes (les commandes
        # ne changent pas pendant la durée de vie du dialogue) : réutilisés à
        # la fois pour construire les chips et pour remplir la liste quand on
        # clique dessus — voir _set_category_filter.
        self._category_groups = group_by_category(self.commands)

        self._row_map = list(self.commands)  # ligne -> commande (None = en-tête de catégorie)
        self._show_all = False
        self._active_category = ALL_CATEGORIES
        self.setModal(True)
        self.setFixedWidth(700)  # largeur fixe ; la hauteur s'adapte au contenu (voir _resize_results)

        # Note technique : on n'utilise plus WA_TranslucentBackground ni
        # d'ombre portée (QGraphicsDropShadowEffect) sur la fenêtre. Cette
        # combinaison force Windows à recomposer toute la fenêtre (canal
        # alpha complet, API UpdateLayeredWindowIndirect) à chaque
        # redimensionnement — ce qu'on fait souvent ici (clic sur un chip,
        # bascule "toutes les commandes", frappe dans le champ de recherche).
        # Cette API est connue pour échouer ("Paramètre incorrect") sous
        # Windows dans ce genre de scénario : quand ça arrive, Windows garde
        # l'ancienne image affichée alors que le contenu a changé en
        # interne, d'où les bugs observés (affichage figé/plus sélectionnable,
        # catégories qui "disparaissent"). On garde les coins arrondis, mais
        # via un masque de fenêtre (voir resizeEvent) plutôt que par
        # transparence par pixel — ça n'utilise pas cette API et est stable.
        self.setStyleSheet(f"background-color: {app.PANEL};")
        self.setWindowOpacity(0.0)  # fondu à l'ouverture, voir showEvent (opacité globale de
                                     # la fenêtre — ne nécessite pas WA_TranslucentBackground,
                                     # donc ne pose pas le problème décrit ci-dessus)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(6)

        # Conteneur qui porte le fond/la bordure de la "barre de recherche" ;
        # la loupe et le QLineEdit sont posés dessus sans fond propre, pour
        # donner l'impression d'une seule pièce (style Spotlight/Raycast)
        # plutôt qu'un champ de formulaire classique.
        search_wrap = QWidget()
        search_wrap.setStyleSheet(f"""
            QWidget {{
                background-color: {app.CARD};
                border: 1px solid {app.ACCENT};
                border-radius: 10px;
            }}
        """)
        search_wrap_layout = QHBoxLayout(search_wrap)
        search_wrap_layout.setContentsMargins(10, 0, 6, 0)
        search_wrap_layout.setSpacing(6)

        self.entry = QLineEdit()
        self.entry.setPlaceholderText(t("spotlight.search_placeholder"))
        self.entry.setFont(QFont("Segoe UI", 13))
        self.entry.setStyleSheet(f"""
            QLineEdit {{
                background: transparent;
                color: {app.TEXT};
                border: none;
                padding: 8px 0;
            }}
        """)
        self.entry.textChanged.connect(self._filter)
        self.entry.installEventFilter(self)
        search_wrap_layout.addWidget(self.entry, stretch=1)

        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(8)
        top_row.addWidget(search_wrap, stretch=1)

        btn_all = QPushButton(t("spotlight.show_all_actions"))
        btn_all.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_all.setFixedHeight(32)
        btn_all.setFlat(True)
        btn_all.setStyleSheet(f"""
            QPushButton {{
                background-color: {app.CARD};
                color: {app.GRAY};
                border: none;
                border-radius: 6px;
                padding: 0 10px;
                font-size: 10pt;
            }}
            QPushButton:hover {{
                background-color: {app.ACCENT};
                color: #000;
            }}
        """)
        btn_all.clicked.connect(self._toggle_all_results)   # ← nouvelle méthode dispatcher
        top_row.addWidget(btn_all)
        self.btn_all = btn_all   # ← ajouté : pour changer le texte plus tard

        btn_close = QPushButton("✕")
        btn_close.setFixedSize(32, 32)
        btn_close.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_close.setFlat(True)
        btn_close.setStyleSheet(f"""
            QPushButton {{
                background-color: {app.CARD};
                color: {app.GRAY};
                border: none;
                border-radius: 6px;
                font-size: 14pt;
            }}
            QPushButton:hover {{
                background-color: {app.ACCENT};
                color: #000;
            }}
        """)
        btn_close.clicked.connect(self.close)  # Escape et croix suivent le même chemin
        top_row.addWidget(btn_close)

        layout.addLayout(top_row)

        # --- Chips de filtre par catégorie -------------------------------
        # N'apparaissent que dans le mode "Toutes les commandes" (voir
        # _show_all_results), juste sous la barre de recherche. Dès que
        # l'utilisateur tape quoi que ce soit, _filter() les masque et la
        # recherche normale reprend (voir _filter) : chips et résultats
        # groupés disparaissent ensemble, comme demandé.
        self.chips_container = QWidget()
        chips_layout = FlowLayout(self.chips_container, margin=0, hspacing=6, vspacing=6)

        self._chip_buttons = {}
        chip_defs = [(ALL_CATEGORIES, t("spotlight.filter_all"))]
        chip_defs += [(key, label) for key, label, _items in self._category_groups]
        for key, label in chip_defs:
            btn = QPushButton(label)
            btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            btn.setFlat(True)
            btn.setFixedHeight(26)
            btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            btn.clicked.connect(lambda _checked=False, k=key: self._set_category_filter(k))
            chips_layout.addWidget(btn)
            self._chip_buttons[key] = btn
        self._style_chips()
        self.chips_container.setVisible(False)
        # Effet réutilisé pour un léger fondu quand les chips apparaissent
        # (voir _show_all_results) plutôt qu'un affichage instantané et sec.
        self._chips_opacity_effect = QGraphicsOpacityEffect(self.chips_container)
        self._chips_opacity_effect.setOpacity(1.0)
        self.chips_container.setGraphicsEffect(self._chips_opacity_effect)
        layout.addWidget(self.chips_container)

        self.results = QListWidget()
        self.results.setFont(QFont("Segoe UI", 11))
        self.results.setStyleSheet(f"""
            QListWidget {{
                background-color: {app.CARD};
                color: {app.TEXT};
                border: none;
                border-radius: 10px;
                padding: 4px;
                outline: none;
            }}
            QListWidget::item {{
                border-radius: 6px;
                padding: 5px 8px;
                margin: 0px 2px;
            }}
            QListWidget::item:hover {{
                background-color: {app.PANEL};
            }}
            QListWidget::item:selected {{
                background-color: {app.ACCENT};
                color: #000;
            }}
            QScrollBar:vertical {{
                background: transparent;
                width: 10px;
                margin: 4px 2px 4px 0px;
            }}
            QScrollBar::handle:vertical {{
                background: {app.GRAY};
                border-radius: 4px;
                min-height: 24px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {app.ACCENT};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
                border: none;
                background: none;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: none;
            }}
        """)
        self.results.itemActivated.connect(self._select_item)
        layout.addWidget(self.results)

        # Pied de page discret : rappel des raccourcis clavier, comme dans
        # la plupart des command palettes (Spotlight, Raycast, VSCode...).
        hint = QLabel(t("spotlight.hint_navigation"))
        hint.setFont(QFont("Segoe UI", 10))
        hint.setStyleSheet(f"color: {app.GRAY}; background: transparent; padding-top: 2px;")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(hint)

        self._filter("")  # état initial = même logique que champ vide (aperçu récent)
        self._center_on_screen()

        # Filet de sécurité : parfois WM_ACTIVATE n'est pas transmis à Qt
        # (jeu en plein écran exclusif, changement de focus très rapide...),
        # donc on vérifie aussi activement la fenêtre au premier plan.
        self._focus_watchdog = QTimer(self)
        self._focus_watchdog.setInterval(200)
        self._focus_watchdog.timeout.connect(self._check_foreground)
        self._focus_watchdog.start()

    # ------------------------------------------------------------------
    # Vol de focus forcé à l'ouverture, restitution à la fermeture
    # ------------------------------------------------------------------
    def showEvent(self, event):
        super().showEvent(event)
        self.raise_()
        self.activateWindow()
        _force_foreground(int(self.winId()))
        self.entry.setFocus(Qt.FocusReason.ActiveWindowFocusReason)

        # Fondu d'ouverture : la fenêtre part de windowOpacity=0.0 (posé au
        # __init__) et remonte à 1.0. Réf gardée sur self pour ne pas être
        # ramassée par le garbage collector avant la fin de l'animation.
        self._fade_anim = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade_anim.setDuration(120)
        self._fade_anim.setStartValue(0.0)
        self._fade_anim.setEndValue(1.0)
        self._fade_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._fade_anim.start()

    def closeEvent(self, event):
        if hasattr(self, "_focus_watchdog"):
            self._focus_watchdog.stop()
        if self._previous_hwnd and not self._skip_focus_restore and _is_dofus_window(self._previous_hwnd):
            _force_foreground(self._previous_hwnd)
        super().closeEvent(event)

    def changeEvent(self, event):
        """Si la fenêtre Spotlight n'est plus la fenêtre active (l'utilisateur
        a cliqué ailleurs, alt-tab, changé de page sur Dofus...), Escape ne peut
        plus être capté puisque le clavier ne pointe plus vers cette QLineEdit.
        On ferme donc automatiquement l'overlay dans ce cas.
        """
        if event.type() == QEvent.Type.ActivationChange and not self.isActiveWindow():
            # L'utilisateur a déjà changé de focus de lui-même : ne pas le lui
            # reprendre en forçant Dofus au premier plan à la fermeture.
            self._skip_focus_restore = True
            self.close()
        super().changeEvent(event)

    def _check_foreground(self):
        """Filet de sécurité pour le watchdog QTimer : ferme l'overlay si la
        fenêtre au premier plan Windows n'est plus la nôtre, même si Qt n'a
        pas déclenché ActivationChange (arrive avec certains jeux plein écran)."""
        try:
            import win32gui
            if win32gui.GetForegroundWindow() != int(self.winId()):
                self._skip_focus_restore = True
                self.close()
        except Exception:
            pass

    def _center_on_screen(self):
        from PyQt6.QtWidgets import QApplication
        screen = QApplication.primaryScreen().availableGeometry()
        x = screen.center().x() - self.width() // 2
        y = screen.top() + screen.height() // 4
        self.move(x, y)

    def resizeEvent(self, event):
        """Coins arrondis via un masque de fenêtre (SetWindowRgn), et non par
        transparence par pixel (WA_TranslucentBackground) : voir la note dans
        __init__ sur pourquoi cette dernière a été abandonnée."""
        super().resizeEvent(event)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), 14, 14)
        self.setMask(QRegion(path.toFillPolygon().toPolygon()))

    def _filter(self, text: str):
        self._show_all = False  # dès qu'on tape, on repasse en mode normal
        if self.chips_container.isVisible():
            # L'utilisateur se remet à chercher : les chips (et la vue
            # groupée par catégorie qu'ils pilotaient) n'ont plus lieu
            # d'être, la recherche classique reprend la main.
            self.chips_container.setVisible(False)
        q = text.lower().strip()
        if not q:
            # Champ vide : on ne montre qu'un petit aperçu (les actions les
            # plus récemment utilisées) plutôt que la liste complète — celle-ci
            # reste accessible via le bouton "Toutes les actions".
            recent = sort_by_recency(self.commands)
            filtered = recent[:DEFAULT_VISIBLE_COUNT]
            self._refresh(filtered)
        else:
            # Recherche avec tolérance aux fautes de frappe (voir
            # command_matches), résultats triés du plus récent au moins
            # récent.
            matches = [c for c in self.commands if command_matches(q, c)]
            filtered = sort_by_recency(matches)
            empty_message = f"Aucun résultat pour « {text.strip()} »" if not filtered else None
            self._refresh(filtered, empty_message=empty_message)
        self._update_btn_all_label()

    def _update_btn_all_label(self):
        self.btn_all.setText(
            t("spotlight.hide_all_actions") if self._show_all
            else t("spotlight.show_all_actions")
        )

    def _toggle_all_results(self):
        """Clic sur le bouton : bascule entre 'Toutes les actions' et retour
        à la vue normale."""
        if self._show_all:
            self._hide_all_results()
        else:
            self._show_all_results()

    def _hide_all_results(self):
        """Referme la vue 'Toutes les actions' : cache les chips et repasse
        en vue normale (aperçu récent / recherche en cours)."""
        self._filter(self.entry.text())

    def _show_all_results(self):
        """Bouton 'Toutes les actions' : affiche les chips de filtre par
        catégorie sous la recherche, et la liste complète groupée (chip
        'Tout' actif par défaut), en ignorant la recherche en cours."""
        self._show_all = True
        self.entry.blockSignals(True)   # évite de repasser par _filter("")
        self.entry.clear()              # qui masquerait aussitôt les chips
        self.entry.blockSignals(False)
        self.chips_container.setVisible(True)

        # Petit fondu (au lieu d'un affichage instantané) quand les chips
        # apparaissent. Réf gardée sur self, sinon l'animation est ramassée
        # par le garbage collector avant d'avoir joué.
        self._chips_fade = QPropertyAnimation(self._chips_opacity_effect, b"opacity", self)
        self._chips_fade.setDuration(150)
        self._chips_fade.setStartValue(0.0)
        self._chips_fade.setEndValue(1.0)
        self._chips_fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._chips_fade.start()

        self._set_category_filter(ALL_CATEGORIES)
        self.entry.setFocus()
        self._update_btn_all_label()

    def _set_category_filter(self, key: str):
        """Appelée au clic sur un chip : bascule le chip actif et rafraîchit
        la liste en conséquence. 'Tout' réaffiche la vue groupée avec
        en-têtes ; une catégorie précise affiche ses commandes seules, triées
        alphabétiquement (déjà fait par group_by_category), sans en-tête
        puisqu'il n'y a plus qu'un seul groupe à l'écran."""
        self._active_category = key
        self._style_chips()
        if key == ALL_CATEGORIES:
            self._refresh_grouped(self._category_groups)
        else:
            group = next((g for g in self._category_groups if g[0] == key), None)
            self._refresh(group[2] if group else [])
        self.entry.setFocus()

    def _style_chips(self):
        active = f"""
            QPushButton {{
                background-color: {self.app.ACCENT};
                color: #000;
                border: none;
                border-radius: 13px;
                padding: 0 12px;
                font-size: 9pt;
            }}
        """
        inactive = f"""
            QPushButton {{
                background-color: {self.app.CARD};
                color: {self.app.GRAY};
                border: none;
                border-radius: 13px;
                padding: 0 12px;
                font-size: 9pt;
            }}
            QPushButton:hover {{
                background-color: {self.app.ACCENT};
                color: #000;
            }}
        """
        for key, btn in self._chip_buttons.items():
            btn.setStyleSheet(active if key == self._active_category else inactive)

    def _command_label(self, c):
        if "label_fn" in c:
            # Label calculé dynamiquement (ex: "Activer" / "Désactiver"
            # selon l'état courant) — pas de suffixe [ON]/[OFF] en plus,
            # le texte porte déjà l'information.
            return c["label_fn"]()
        return c["label"]

    def _add_command_row(self, c):
        self.results.addItem(QListWidgetItem(self._command_label(c)))
        self._row_map.append(c)

    def _add_category_header(self, label):
        """Ligne d'en-tête de groupe, non sélectionnable : fond distinct de
        celui des lignes de commande (app.PANEL, le fond du dialogue, au
        lieu d'app.CARD) + texte en gras/majuscules dans la couleur accent,
        pour qu'elle se distingue clairement même en un coup d'œil rapide —
        contrairement à un simple séparateur fin, facile à manquer. Utilisée
        uniquement par le chip 'Tout' (_refresh_grouped) : un chip de
        catégorie précise n'affiche qu'un seul groupe, donc pas d'en-tête."""
        item = QListWidgetItem(label.upper())
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
        font = QFont("Segoe UI", 9)
        font.setBold(True)
        font.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 105)
        item.setFont(font)
        item.setBackground(QBrush(QColor(self.app.PANEL)))
        item.setForeground(QBrush(QColor(self.app.ACCENT)))
        self.results.addItem(item)
        self._row_map.append(None)  # marque : ligne non sélectionnable

    def _add_empty_state(self, text):
        """Ligne centrée, grise, italique, non sélectionnable — affichée à
        la place d'une liste vide plutôt que de laisser un silence total."""
        item = QListWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        font = QFont("Segoe UI", 10)
        font.setItalic(True)
        item.setFont(font)
        item.setForeground(QBrush(QColor(self.app.GRAY)))
        self.results.addItem(item)
        self._row_map.append(None)

    def _refresh(self, cmds, empty_message: str | None = None):
        """Rendu à plat : pas de groupement, pas d'en-têtes. Utilisé par la
        recherche, l'aperçu récent par défaut, et un chip de catégorie
        précise — voir _refresh_grouped pour le chip 'Tout'. `empty_message`
        n'est affiché que si `cmds` est vide (ex: recherche sans résultat)."""
        self.results.clear()
        self._row_map = []
        if not cmds:
            self._add_empty_state(empty_message or t("spotlight.no_results"))
        else:
            for c in cmds:
                self._add_command_row(c)
        self._select_first_selectable()
        self._resize_results(len(self._row_map))

    def _refresh_grouped(self, groups):
        """Rendu groupé par catégorie avec en-têtes, pour le chip 'Tout' :
        `groups` = [(category_key, label, [commandes]), ...] tel que renvoyé
        par group_by_category (déjà trié alphabétiquement par groupe)."""
        self.results.clear()
        self._row_map = []
        for _key, label, items in groups:
            if not items:
                continue
            self._add_category_header(label)
            for c in items:
                self._add_command_row(c)
        if not self._row_map:
            self._add_empty_state(t("spotlight.no_results"))
        self._select_first_selectable()
        self._resize_results(len(self._row_map))

    def _select_first_selectable(self):
        for row, entry in enumerate(self._row_map):
            if entry is not None:
                self.results.setCurrentRow(row)
                return
        self.results.setCurrentRow(-1)

    def _content_height(self) -> int:
        """Hauteur réelle du contenu de la liste = somme de la hauteur de
        CHAQUE ligne. Il ne faut pas multiplier la hauteur de la ligne 0 par
        le nombre de lignes : en vue groupée la ligne 0 est un en-tête de
        catégorie (police plus petite) et le calcul sous-estimait la hauteur,
        d'où une liste qui défilait alors que le plafond n'était pas atteint."""
        count = self.results.count()
        if count == 0:
            return self.results.fontMetrics().height() + 14
        return sum(max(self.results.sizeHintForRow(r), 0) for r in range(count)) \
            + self.results.spacing() * (count + 1)

    def _resize_results(self, count: int):
        """Hauteur adaptative de la zone de résultats :
          - elle colle au contenu tant qu'il tient sous le plafond ;
          - au-delà du plafond, elle se fige et une barre verticale apparaît.
        Plafond : MAX_RESULTS_HEIGHT (recherche / aperçu) ou
        MAX_RESULTS_HEIGHT_ALL (mode "Toutes les commandes", avec en plus un
        plancher MIN_RESULTS_HEIGHT_ALL)."""
        # +8 : le padding (4px haut + 4px bas) ajouté sur QListWidget dans
        # sa feuille de style — non compté par frameWidth(), qui ne mesure
        # que la bordure. Sans ça, la liste sous-estime sa hauteur idéale de
        # cette marge et une barre de défilement apparaît inutilement.
        frame = self.results.frameWidth() * 2 + 8
        ideal_height = self._content_height() + frame
        if self._show_all:
            height = max(MIN_RESULTS_HEIGHT_ALL, min(ideal_height, MAX_RESULTS_HEIGHT_ALL))
        else:
            height = min(ideal_height, MAX_RESULTS_HEIGHT)
        self.results.setFixedHeight(height)
        self._fit_to_content()

    def _fit_to_content(self):
        """Ajuste la hauteur du dialogue au contenu, calculée pour la largeur
        RÉELLE (fixe). On n'utilise pas adjustSize() : il calcule la hauteur
        du layout pour la largeur du sizeHint (étroite), pas pour les 700 px
        fixés — les chips (FlowLayout) y passent sur 2 lignes, la hauteur
        réservée est donc trop grande, et l'espace en trop se retrouve dans
        le conteneur des chips (2e ligne vide)."""
        layout = self.layout()
        layout.activate()
        width = self.width()
        self.resize(width, layout.totalHeightForWidth(width))

    def eventFilter(self, obj, event):
        if obj is self.entry and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key == Qt.Key.Key_Escape:
                self.close()
                return True
            elif key == Qt.Key.Key_Down:
                self._move_selection(+1)
                return True
            elif key == Qt.Key.Key_Up:
                self._move_selection(-1)
                return True
            elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                row = self.results.currentRow()
                if row >= 0:
                    self._select_index(row)
                return True
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)

    def _move_selection(self, step: int):
        """Déplace la sélection de `step` lignes en sautant les en-têtes de
        catégorie (non sélectionnables, marquées par None dans _row_map).
        Comportement bloquant aux extrémités (pas de wrap)."""
        row = self.results.currentRow()
        row = 0 if row < 0 else row
        candidate = row + step
        while 0 <= candidate < len(self._row_map) and self._row_map[candidate] is None:
            candidate += step
        if 0 <= candidate < len(self._row_map):
            self.results.setCurrentRow(candidate)

    def _select_item(self, item):
        self._select_index(self.results.row(item))

    def _select_index(self, idx: int):
        if not (0 <= idx < len(self._row_map)):
            return
        cmd = self._row_map[idx]
        if cmd is None:   # ligne d'en-tête de catégorie : rien à exécuter
            return
        mark_command_used(cmd.get("id"))   # pour le tri par récence la prochaine fois
        if cmd.get("type") == "navigate":
            self._skip_focus_restore = True   # on reste sur Dracoon
        self.close()           # → déclenche closeEvent
        cmd["run"]()            # → puis l'action/navigation s'exécute


def open_spotlight(app):
    """Ouvre le Spotlight, ou le referme s'il est déjà ouvert (toggle on/off).

    La référence `app._spotlight_dialog` est remise à None via le signal
    `finished`, qui se déclenche quoi qu'il arrive : sélection d'une commande,
    Escape/croix, ou fermeture automatique (changement de fenêtre détecté par
    changeEvent/_check_foreground). L'état toggle reste donc toujours cohérent,
    même quand l'overlay disparaît tout seul.
    """
    existing = getattr(app, "_spotlight_dialog", None)
    if existing is not None and existing.isVisible():
        existing.close()   # 2e appui = on referme l'overlay déjà ouvert
        return

    dlg = SpotlightDialog(app)
    app._spotlight_dialog = dlg
    dlg.finished.connect(lambda _r=None: setattr(app, "_spotlight_dialog", None))
    dlg.exec()
