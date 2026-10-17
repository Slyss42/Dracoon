"""
UI_Easyconome.py
Overlay du challenge Économe (1 sort max par combat et par personnage).

  EasyconomeManager  : le seul objet que Main.py connaît (voir INTEGRATION.md)
  Overlay         : fenêtre toujours au premier plan, qui ne vole jamais le focus au jeu
  SpellGrid       : grille peinte à la main (clic = lancé, glisser-déposer en mode édition)
  TabBar          : un onglet par compte Dofus connecté
  compute_layout  : toute la disposition responsive (ligne / pile / colonne), en Python pur
  IconCache       : chaque icône (normale / grisée) construite UNE fois, jamais au rendu
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Callable, Iterable, NamedTuple

from PyQt6.QtCore import QEvent, QObject, QPoint, QPointF, QRect, QRectF, Qt, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtGui import (
    QColor, QFont, QFontMetrics, QGuiApplication, QImage, QPainter, QPainterPath, QPen, QPixmap,
)
from PyQt6.QtWidgets import QApplication, QLabel, QMenu, QPushButton, QWidget

from core.easyconome import CLASSES, COMMON, EasyconomeState, SpellCatalog, spell_folder


# ==============================================================================
# 1. THÈME ET TRADUCTIONS
# ==============================================================================

_FALLBACK = {
    "BG": "#0f1117", "PANEL": "#171b26", "CARD": "#1d2230", "ACCENT": "#e8a33a",
    "GREEN": "#4caf78", "RED": "#e05252", "GRAY": "#8b93a7", "TEXT": "#e5e7eb",
}


def color(name: str) -> QColor:
    """Couleur du Palette de Dracoon (ui/theme.py) ; valeur de secours si indisponible."""
    try:
        from ui.theme import Palette
        c = QColor(str(getattr(Palette, name)))
        if c.isValid():
            return c
    except Exception:
        pass
    return QColor(_FALLBACK[name])


@lru_cache(maxsize=None)
def tr(key: str, default: str) -> str:
    """t(key) de core/i18n ; retombe sur `default` si la clé n'existe pas encore dans i18n.json."""
    try:
        from core.i18n import t
        v = t(key)
        return default if (not v or v == key) else v
    except Exception:
        return default


def class_name(cid: str) -> str:
    """Nom traduit d'une classe (clé easyconome.class.<id>) ; nom français de CLASSES en secours."""
    return tr(f"easyconome.class.{cid}", CLASSES.get(cid, cid))


# ==============================================================================
# 2. CACHE D'ICÔNES
# ==============================================================================

_PLACEHOLDER_COLORS = {
    "cra": "#84cc16", "ecaflip": "#ef4444", "eniripsa": "#ec4899", "enutrof": "#eab308",
    "feca": "#3b82f6", "iop": "#f97316", "osamodas": "#22c55e", "pandawa": "#f59e0b",
    "sacrieur": "#dc2626", "sadida": "#10b981", "sram": "#a855f7", "xelor": "#06b6d4",
}


class IconCache:
    def __init__(self, catalog: SpellCatalog) -> None:
        self.catalog = catalog
        self.size = 40
        self.dpr = 1.0
        self._normal: dict[str, QPixmap] = {}
        self._used: dict[str, QPixmap] = {}
        self._src: dict[str, QPixmap | None] = {}     # images d'origine, lues une seule fois

    def configure(self, size: int, dpr: float) -> None:
        """À appeler avant de peindre ; ne fait rien tant que taille et densité ne changent pas."""
        if size != self.size or abs(dpr - self.dpr) > 1e-6:
            self.size, self.dpr = size, dpr
            self._normal.clear()
            self._used.clear()

    def get(self, spell_id: str, used: bool) -> QPixmap:
        store = self._used if used else self._normal
        pm = store.get(spell_id)
        if pm is None:
            self._build(spell_id)
            pm = store[spell_id]
        return pm

    def warm(self, spell_ids) -> None:
        """Pré-construit les icônes (appelé hors combat, quand un compte apparaît)."""
        for s in spell_ids:
            if s not in self._normal:
                self._build(s)

    # ------------------------------------------------------------------
    def _build(self, spell_id: str) -> None:
        px = max(1, int(round(self.size * self.dpr)))
        normal = self._from_file(spell_id, px) or self._placeholder(spell_id, px)
        used = self._make_used(normal, px)
        normal.setDevicePixelRatio(self.dpr)       # après tout dessin : on peint en pixels physiques
        used.setDevicePixelRatio(self.dpr)
        self._normal[spell_id] = normal
        self._used[spell_id] = used

    def _from_file(self, spell_id: str, px: int) -> QPixmap | None:
        if spell_id not in self._src:
            path = self.catalog.icon_path(spell_id)
            src = QPixmap(path) if path and os.path.isfile(path) else None
            self._src[spell_id] = None if (src is None or src.isNull()) else src
        src = self._src[spell_id]
        if src is None:
            return None
        src = src.scaled(px, px, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        out = QPixmap(px, px)
        out.fill(Qt.GlobalColor.transparent)
        p = QPainter(out)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        clip = QPainterPath()
        r = 6 * self.dpr
        clip.addRoundedRect(QRectF(0, 0, px, px), r, r)
        p.setClipPath(clip)
        p.drawPixmap((px - src.width()) // 2, (px - src.height()) // 2, src)
        p.end()
        return out

    def _placeholder(self, spell_id: str, px: int) -> QPixmap:
        folder = spell_folder(spell_id)
        _, _, num = spell_id.rpartition("_")
        try:
            n = int(num)
        except ValueError:
            n = 0
        if folder == COMMON:
            color, label = QColor("#475569"), f"C{n}"
        else:
            color = QColor(_PLACEHOLDER_COLORS.get(folder, "#64748b")).darker(100 + (n % 4) * 14)
            label = str(n)
        pm = QPixmap(px, px)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(color)
        p.drawRoundedRect(QRectF(1, 1, px - 2, px - 2), 6 * self.dpr, 6 * self.dpr)
        f = QFont()
        f.setBold(True)
        f.setPixelSize(max(8, int(px * 0.38)))
        p.setFont(f)
        p.setPen(QColor("white"))
        p.drawText(QRect(0, 0, px, px), Qt.AlignmentFlag.AlignCenter, label)
        p.end()
        return pm

    def _make_used(self, normal: QPixmap, px: int) -> QPixmap:
        """Icône désaturée + voile sombre + coche. Calculée une fois, jamais au rendu."""
        img = normal.toImage().convertToFormat(QImage.Format.Format_ARGB32)
        alpha = img.convertToFormat(QImage.Format.Format_Alpha8)
        gray = img.convertToFormat(QImage.Format.Format_Grayscale8).convertToFormat(QImage.Format.Format_ARGB32)
        gray.setAlphaChannel(alpha)
        used = QPixmap.fromImage(gray)

        p = QPainter(used)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceAtop)
        p.fillRect(used.rect(), QColor(16, 16, 20, 150))
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        pen = QPen(QColor("#4ade80"), max(2.0, px * 0.085))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.drawLine(QPointF(.27 * px, .52 * px), QPointF(.44 * px, .69 * px))
        p.drawLine(QPointF(.44 * px, .69 * px), QPointF(.75 * px, .33 * px))
        p.end()
        return used


# ==============================================================================
# 3. GÉOMÉTRIE RESPONSIVE
#    Pur Python (aucun widget) : toute la disposition se calcule ici, à partir de
#    (colonnes, taille d'icône, nombre d'onglets). L'overlay ne fait qu'appliquer le résultat.
# ==============================================================================
#
#  Un SEUL réglage : la TAILLE de la fenêtre (poignées sur les bords, elle suit le curseur au pixel
#  près). Le reste est calculé : on essaie toutes les grilles possibles (1 colonne, 2 colonnes, …) et on
#  garde celle dont les icônes sont les plus grandes ; à taille égale, celle qui laisse le moins de cases
#  vides, puis celle qui change le moins par rapport à l'instant d'avant (pas de scintillement).
#  Le nombre de colonnes / lignes ne bloque donc jamais la taille de la fenêtre.
#  Les noms de mode ci-dessous ne dépendent que de la LARGEUR de la fenêtre :
#
#   colonnes nombreuses  →  mode « ligne »   [titre][onglets........][boutons]   (1 seule bande d'en-tête)
#                                            [ icônes sur 1 ou 2 lignes ........................ ]
#   colonnes moyennes    →  mode « pile »    [titre.................][boutons]
#                                            [onglets, repartis sur 1..n lignes]
#                                            [ grille d'icônes ]
#   colonnes très peu    →  mode « colonne » [boutons]            (titre masqué)
#                                            [onglets empilés, 1 par ligne, version compacte]
#                                            [ grille étroite ]
#
#  Si une dimension a du jeu une fois les icônes au maximum, l'excédent est réparti ENTRE les icônes
#  (plafonné par STRETCH_MAX), puis la grille est centrée.

GAP = 4                      # espace minimal entre deux icônes
STRETCH_MAX = 0.5            # espace vertical en plus, au maximum, entre deux icônes (× taille d'icône)
PAD = 10                     # marge gauche / droite / bas
PAD_TOP = 8
SP = 6                       # espace entre blocs (en-tête / onglets / grille)
EDGE = 7                     # épaisseur de la zone de redimensionnement sur le bord
CORNER = 14                  # côté de la zone de coin (largeur + hauteur en même temps) : plus grande que EDGE
TILE_MIN, TILE_MAX, TILE_DEFAULT = 20, 96, 40   # bornes de l'icône (calculée seule) · taille « naturelle » au 1er lancement
DEFAULT_COLS = 7
RESET_CONFIRM_MS = 2500
REORDER_ENABLED = False      # glisser-déposer pour trier les sorts : codé et testé, désactivé pour l'instant

BTN_W, BTN_H, BTN_GAP, N_BTNS = 26, 24, 4, 3
BTNS_W = N_BTNS * BTN_W + (N_BTNS - 1) * BTN_GAP      # 86
TITLE_W, TITLE_H = 84, 20
HDR_H = 28
TAB_H, TAB_H_COMPACT, TAB_GAP = 40, 26, 3
MIN_TAB_W, MAX_TAB_W = 76, 110
MIN_INNER_W = BTNS_W + 8                              # jamais plus étroit que la rangée de boutons
PICK_MIN_W, PICK_MIN_H, PICK_MAX_H = 70, 22, 34       # sélecteur de classe


class Rect(NamedTuple):
    x: int
    y: int
    w: int
    h: int


_NO_RECT = Rect(0, 0, 0, 0)


class Layout(NamedTuple):
    cols: int
    rows: int
    tile: int
    width: int                  # taille de la fenêtre entière
    height: int
    mode: str                   # "ligne" | "pile" | "colonne"
    compact_tabs: bool
    show_title: bool
    title: Rect                 # tous les Rect sont en coordonnées de la fenêtre
    buttons: tuple              # N_BTNS Rect : reset, réduire, fermer
    tabs: tuple                 # un Rect par compte
    tabs_box: Rect              # boîte englobant tous les onglets
    grid: Rect                  # zone du widget SpellGrid
    cells_x: int                # décalage des icônes dans la zone de la grille (centrage si la zone est plus grande)
    cells_y: int
    step_x: float               # distance entre deux colonnes / deux lignes (taille d'icône + espace étiré)
    step_y: float


def picker_cols(width: int) -> int:
    """Colonnes du sélecteur de classe : diviseurs de 12 pour des lignes toutes pleines."""
    for pk in (12, 6, 4, 3, 2, 1):
        if (width - (pk - 1) * GAP) // pk >= PICK_MIN_W:
            return pk
    return 1


def picker_title_h(width: int) -> int:
    return 18 if width >= 300 else 36 if width >= 150 else 50      # le titre passe sur 2-3 lignes


def picker_height(width: int) -> int:
    """Hauteur minimale du sélecteur : la zone de la grille ne doit jamais être plus basse."""
    rows = -(-len(CLASSES) // picker_cols(width))
    return picker_title_h(width) + rows * PICK_MIN_H + (rows - 1) * GAP


def picker_rects(width: int, height: int) -> list:
    pk = picker_cols(width)
    rows = -(-len(CLASSES) // pk)
    th = picker_title_h(width)
    cw = (width - (pk - 1) * GAP) // pk
    ch = max(PICK_MIN_H, min(PICK_MAX_H, (height - th - (rows - 1) * GAP) // rows))
    return [Rect((i % pk) * (cw + GAP), th + (i // pk) * (ch + GAP), cw, ch) for i in range(len(CLASSES))]


def _layout_for(cols: int, n_spells: int, n_tabs: int, collapsed: bool = False,
                want_w: int | None = None, want_h: int | None = None) -> Layout:
    """Disposition pour un nombre de colonnes DONNÉ (brique de compute_layout).

    want_w / want_h : taille voulue de la fenêtre entière (None = taille naturelle, icônes de TILE_DEFAULT).
    La fenêtre a EXACTEMENT cette taille (sauf sous le minimum : icônes de TILE_MIN). La taille d'icône est
    la plus grande qui fait tenir toute la grille dans la zone disponible (largeur ET hauteur) ; l'excédent
    éventuel s'ajoute entre les icônes (plafonné par STRETCH_MAX), puis la grille est centrée."""
    n = max(1, n_spells)
    cols = max(1, min(int(cols), n))
    rows = -(-n // cols)
    min_gw = cols * TILE_MIN + (cols - 1) * GAP                        # grille la plus petite acceptable
    nat_gw = cols * TILE_DEFAULT + (cols - 1) * GAP
    iw = max(nat_gw if want_w is None else want_w - 2 * PAD, min_gw, MIN_INNER_W)   # largeur utile (hors marges)
    k = max(0, n_tabs)
    x0, y = PAD, PAD_TOP
    btn_x = x0 + iw - BTNS_W

    # --- une seule bande (titre + onglets + boutons) si la largeur le permet ----------------
    merged = k > 0 and iw >= TITLE_W + BTNS_W + 2 * SP + k * MIN_TAB_W + (k - 1) * TAB_GAP

    tabs: list[Rect] = []
    compact = False
    if merged:
        mode, show_title = "ligne", True
        title = Rect(x0, y + (TAB_H - TITLE_H) // 2, TITLE_W, TITLE_H)
        by = y + (TAB_H - BTN_H) // 2
        avail = iw - TITLE_W - BTNS_W - 2 * SP
        tw = min(MAX_TAB_W, (avail - (k - 1) * TAB_GAP) // k)
        tx = x0 + TITLE_W + SP
        tabs = [Rect(tx + i * (tw + TAB_GAP), y, tw, TAB_H) for i in range(k)]
        y += TAB_H
    else:
        show_title = iw >= TITLE_W + BTNS_W + SP
        title = Rect(x0, y + (HDR_H - TITLE_H) // 2, TITLE_W, TITLE_H)
        by = y + (HDR_H - BTN_H) // 2
        y += HDR_H
        mode = "pile"
        if k:
            fit = (iw + TAB_GAP) // (MIN_TAB_W + TAB_GAP)              # onglets de largeur correcte par ligne
            compact = fit < 2
            if compact:                                                # colonne étroite : 1 onglet par ligne
                mode = "colonne"
                per_row, th, tw = 1, TAB_H_COMPACT, iw
            else:                                                      # lignes équilibrées (3+2 plutôt que 4+1)
                n_rows = -(-k // min(k, fit))
                per_row = -(-k // n_rows)
                th = TAB_H
                tw = min(MAX_TAB_W, (iw - (per_row - 1) * TAB_GAP) // per_row)
            for i in range(k):
                r, c = divmod(i, per_row)
                tabs.append(Rect(x0 + c * (tw + TAB_GAP), y + SP + r * (th + TAB_GAP), tw, th))
            n_rows = -(-k // per_row)
            y += SP + n_rows * th + (n_rows - 1) * TAB_GAP
        elif iw < TITLE_W + BTNS_W + SP:
            mode = "colonne"

    buttons = tuple(Rect(btn_x + i * (BTN_W + BTN_GAP), by, BTN_W, BTN_H) for i in range(N_BTNS))

    # --- grille : la taille d'icône est déduite de l'espace disponible -----------------------
    tile_w = (iw - (cols - 1) * GAP) // cols
    if collapsed:
        tile = max(TILE_MIN, min(TILE_MAX, tile_w))
        gh = gh_icons = 0
        grid = Rect(x0, y, iw, 0)
    else:
        y += SP
        min_gh = max(rows * TILE_MIN + (rows - 1) * GAP, picker_height(iw))     # le sélecteur de classe doit tenir
        gh_want = rows * TILE_DEFAULT + (rows - 1) * GAP if want_h is None else want_h - PAD - y
        gh = max(gh_want, min_gh)
        tile_h = (gh - (rows - 1) * GAP) // rows
        tile = max(TILE_MIN, min(TILE_MAX, tile_w, tile_h))                     # la plus grande qui tient
        extra = int(tile * STRETCH_MAX)                                         # jeu max ajouté entre 2 icônes
        used_h = rows * tile + (rows - 1) * GAP
        gh_icons = used_h + min(gh - used_h, (rows - 1) * extra)
        grid = Rect(x0, y, iw, gh)
        y += gh
    used_w = cols * tile + (cols - 1) * GAP
    iw_icons = used_w + min(iw - used_w, (cols - 1) * int(tile * STRETCH_MAX))

    box = _NO_RECT
    if tabs:
        left, top = min(t.x for t in tabs), min(t.y for t in tabs)
        right, bottom = max(t.x + t.w for t in tabs), max(t.y + t.h for t in tabs)
        box = Rect(left, top, right - left, bottom - top)

    return Layout(cols, rows, tile, iw + 2 * PAD, y + PAD, mode, compact, show_title, title, buttons,
                  tuple(tabs), box, grid, (iw - iw_icons) // 2, (gh - gh_icons) // 2,
                  (iw_icons - tile) / (cols - 1) if cols > 1 else float(tile + GAP),
                  (gh_icons - tile) / (rows - 1) if rows > 1 else float(tile + GAP))


def compute_layout(n_spells: int, n_tabs: int, collapsed: bool = False,
                   want_w: int | None = None, want_h: int | None = None, prefer: int | None = None) -> Layout:
    """Disposition complète à partir de la SEULE taille de fenêtre voulue.

    On essaie chaque nombre de colonnes et on garde la grille aux icônes les plus grandes. À égalité :
    le moins de cases vides, puis la valeur la plus proche de `prefer` (la précédente : stabilité).
    Seules les grilles qui tiennent (icônes ≥ TILE_MIN) sont candidates ; si aucune ne tient (fenêtre
    minuscule), on prend celle qui oblige la fenêtre à grandir le moins."""
    n = max(1, n_spells)
    if collapsed:                                       # grille cachée : 1 colonne, aucune contrainte de largeur
        return _layout_for(1, n, n_tabs, True, want_w, None)
    if want_w is None or want_h is None:                # 1er lancement : taille naturelle (DEFAULT_COLS colonnes)
        base = _layout_for(min(DEFAULT_COLS, n), n, n_tabs, False, want_w, want_h)
        want_w, want_h = base.width, base.height

    best_key, best = None, None
    for c in range(1, n + 1):
        lay = _layout_for(c, n, n_tabs, False, want_w, want_h)
        grew = max(0, lay.width - want_w) + max(0, lay.height - want_h)     # 0 = la grille tient sans forcer
        empty = lay.rows * c - n
        key = (grew > 0, grew, -lay.tile, empty, abs(c - (prefer or c)))
        if best_key is None or key < best_key:
            best_key, best = key, lay
    return best


# ==============================================================================
# 4. GRILLE DES SORTS
# ==============================================================================

class SpellGrid(QWidget):
    def __init__(self, state: EasyconomeState, cache: IconCache, overlay, tile: int) -> None:
        super().__init__(overlay)
        self.state, self.cache, self.overlay = state, cache, overlay
        self.cols, self.rows, self.tile, self.cells_x, self.cells_y = DEFAULT_COLS, 1, tile, 0, 0
        self.step_x = self.step_y = float(tile + GAP)
        self.edit_mode = False
        self._press_idx = -1
        self._press_pseudo: str | None = None
        self._press_pos = QPoint()
        self._dragging = False
        self._cursor = QPoint()
        self._drop_idx = -1
        self._hover_class = -1                       # case survolée dans le sélecteur de classe
        self._accent = color("ACCENT")
        self._gray = color("GRAY")
        self._text = color("TEXT")
        self.setMouseTracking(True)

        for ev in (state.cast_changed, state.order_changed, state.roster_changed):
            ev.connect(lambda *_: self.update())
        state.active_changed.connect(self._on_active_changed)

    # ------------------------------------------------------------------
    def set_layout(self, lay: Layout) -> None:
        self.cols, self.rows, self.tile = lay.cols, lay.rows, lay.tile
        self.cells_x, self.cells_y = lay.cells_x, lay.cells_y
        self.step_x, self.step_y = lay.step_x, lay.step_y
        self.setGeometry(*lay.grid)
        self.update()

    def set_edit_mode(self, on: bool) -> None:
        self.edit_mode = on
        self._refresh_cursor()
        self._cancel_drag()
        self.update()

    def _refresh_cursor(self) -> None:
        open_hand = self.edit_mode and REORDER_ENABLED
        self.setCursor(Qt.CursorShape.OpenHandCursor if open_hand else Qt.CursorShape.ArrowCursor)

    def _on_active_changed(self) -> None:
        self._cancel_drag()
        self._hover_class = -1
        self._refresh_cursor()
        self.update()

    def leaveEvent(self, e) -> None:
        if self._hover_class != -1:
            self._hover_class = -1
            self.update()

    def _cancel_drag(self) -> None:
        self._press_idx, self._dragging = -1, False

    # ------------------------------------------------------------------
    # Géométrie
    # ------------------------------------------------------------------
    def _cell(self, idx: int) -> QRect:
        r, c = divmod(idx, self.cols)
        return QRect(self.cells_x + round(c * self.step_x), self.cells_y + round(r * self.step_y),
                     self.tile, self.tile)

    def _index_at(self, pos: QPoint, n: int, strict: bool) -> int:
        """strict : l'icône exactement sous `pos` (-1 sinon) ; sinon : l'icône la plus proche."""
        if strict:
            return next((i for i in range(n) if self._cell(i).contains(pos)), -1)
        best, best_d = -1, None
        for i in range(n):
            c = self._cell(i).center()
            d = (c.x() - pos.x()) ** 2 + (c.y() - pos.y()) ** 2
            if best_d is None or d < best_d:
                best, best_d = i, d
        return best

    def _picker_rects(self) -> list:
        return [QRect(*r) for r in picker_rects(self.width(), self.height())]

    def _class_at(self, pos: QPoint) -> int:
        for i, r in enumerate(self._picker_rects()):
            if r.contains(pos):
                return i
        return -1

    # ------------------------------------------------------------------
    # Rendu
    # ------------------------------------------------------------------
    def _paint_class_picker(self, p: QPainter, pseudo: str) -> None:
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        f = QFont()
        f.setBold(True)
        f.setPixelSize(12)
        p.setFont(f)
        p.setPen(self._text)
        msg = tr("easyconome.pick_class", "Quelle est la classe de {pseudo} ?").format(pseudo=pseudo)
        p.drawText(QRect(0, 0, self.width(), picker_title_h(self.width())),
                   Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, msg)
        f.setBold(False)
        p.setFont(f)
        for i, (r, name) in enumerate(zip(self._picker_rects(), (class_name(c) for c in CLASSES))):
            hover = i == self._hover_class
            p.setPen(QPen(self._accent, 1.5) if hover else Qt.PenStyle.NoPen)
            p.setBrush(QColor(self._accent.red(), self._accent.green(), self._accent.blue(), 70)
                       if hover else QColor(255, 255, 255, 18))
            p.drawRoundedRect(QRectF(r).adjusted(.5, .5, -.5, -.5), 6, 6)
            p.setPen(self._text)
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, name)

    def paintEvent(self, e) -> None:
        p = QPainter(self)
        ch = self.state.active_char()
        if ch is None:
            p.setPen(self._gray)
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                       tr("easyconome.no_account", "Aucun compte Dofus détecté"))
            return
        if ch.class_id is None:
            self._paint_class_picker(p, ch.pseudo)
            return

        order = list(ch.order)
        if not order:                                            # tout est masqué : on l'explique
            p.setPen(self._gray)
            p.drawText(self.rect().adjusted(6, 6, -6, -6),
                       Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                       tr("easyconome.grid_empty", "Aucun sort affiché\nClic droit : choisir les sorts"))
            return

        self.cache.configure(self.tile, self.devicePixelRatioF())
        dragged = None
        if self._dragging:                                       # aperçu en direct du nouvel ordre
            dragged = order.pop(self._press_idx)
            order.insert(self._drop_idx, dragged)

        clip = e.rect()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        for idx, spell in enumerate(order):
            rect = self._cell(idx)
            if not rect.intersects(clip):
                continue
            if spell == dragged:
                p.setPen(QPen(self._accent, 2, Qt.PenStyle.DashLine))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 6, 6)
                continue
            p.drawPixmap(rect.topLeft(), self.cache.get(spell, spell in ch.cast))
            if self.edit_mode and REORDER_ENABLED:               # contour discret : "déplaçable"
                p.setPen(QPen(QColor(255, 255, 255, 60), 1))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRoundedRect(rect.adjusted(0, 0, -1, -1), 6, 6)

        if dragged:
            p.setOpacity(0.85)
            p.drawPixmap(self._cursor - QPoint(self.tile // 2, self.tile // 2),
                         self.cache.get(dragged, dragged in ch.cast))

    # ------------------------------------------------------------------
    # Souris (la molette est gérée par l'overlay : elle remonte jusqu'à lui)
    # ------------------------------------------------------------------
    def mousePressEvent(self, e) -> None:
        ch = self.state.active_char()
        if ch is None:
            return
        if e.button() == Qt.MouseButton.RightButton:             # palette des sorts affichés (sauf sélecteur de classe)
            if ch.class_id is not None:
                self.overlay.show_spells_palette(ch.pseudo, e.globalPosition().toPoint())
            return
        if e.button() != Qt.MouseButton.LeftButton:
            return
        pos = e.position().toPoint()
        if ch.class_id is None:                                  # sélecteur de classe affiché
            i = self._class_at(pos)
            if i >= 0:
                self._hover_class = -1
                self.state.set_class(ch.pseudo, list(CLASSES)[i])
                self._refresh_cursor()
            return
        self._press_idx = self._index_at(pos, len(ch.order), True)
        self._press_pseudo = ch.pseudo
        self._press_pos = pos
        if self.edit_mode and REORDER_ENABLED and self._press_idx >= 0:
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, e) -> None:
        ch = self.state.active_char()
        if ch is not None and ch.class_id is None:               # survol des cases du sélecteur
            i = self._class_at(e.position().toPoint())
            if i != self._hover_class:
                self._hover_class = i
                self.setCursor(Qt.CursorShape.PointingHandCursor if i >= 0 else Qt.CursorShape.ArrowCursor)
                self.update()
            return
        if self._press_idx < 0 or ch is None or ch.pseudo != self._press_pseudo:
            return
        pos = e.position().toPoint()
        if not self._dragging and self.edit_mode and REORDER_ENABLED \
                and (pos - self._press_pos).manhattanLength() > 6:
            self._dragging = True
        if self._dragging:
            self._cursor = pos
            self._drop_idx = self._index_at(pos, len(ch.order), False)
            self.update()

    def mouseReleaseEvent(self, e) -> None:
        if e.button() != Qt.MouseButton.LeftButton:
            return
        ch = self.state.active_char()
        if ch is not None and ch.pseudo == self._press_pseudo and self._press_idx >= 0:
            if self._dragging:
                if self._drop_idx != self._press_idx:
                    self.state.move_spell(ch.pseudo, self._press_idx, self._drop_idx)
            elif self._index_at(e.position().toPoint(), len(ch.order), True) == self._press_idx:
                self.state.toggle(ch.pseudo, ch.order[self._press_idx])
        self._cancel_drag()
        self._refresh_cursor()
        self.update()


# ==============================================================================
# 4 bis. ONGLETS (UN PAR COMPTE) : leurs positions viennent du Layout
# ==============================================================================

class TabBar(QWidget):
    def __init__(self, state: EasyconomeState, overlay) -> None:
        super().__init__(overlay)
        self.state, self.overlay = state, overlay
        self._rects: tuple = ()                     # relatifs à ce widget
        self.setMouseTracking(True)
        self._accent = color("ACCENT")
        self._text = color("TEXT")
        self._gray = color("GRAY")
        for ev in (state.roster_changed, state.cast_changed):
            ev.connect(lambda *_: self.update())
        state.active_changed.connect(self.update)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_layout(self, lay: Layout) -> None:
        box = lay.tabs_box
        self._rects = tuple(Rect(t.x - box.x, t.y - box.y, t.w, t.h) for t in lay.tabs)
        self.setVisible(bool(lay.tabs))
        if lay.tabs:
            self.setGeometry(*box)
        self.update()

    def _index_at(self, pos: QPoint) -> int:
        for i, r in enumerate(self._rects):
            if QRect(*r).contains(pos) and i < len(self.state.roster):
                return i
        return -1

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        f_name, f_sub = QFont(), QFont()
        f_name.setBold(True)
        f_name.setPixelSize(12)
        f_sub.setPixelSize(11)
        fm, fm_sub = QFontMetrics(f_name), QFontMetrics(f_sub)

        for pseudo, rr in zip(self.state.roster, self._rects):
            ch = self.state.chars[pseudo]
            r = QRect(*rr)
            active = pseudo == self.state.active
            fill = QColor(self._accent)
            fill.setAlpha(55 if active else 0)
            p.setPen(QPen(self._accent, 1.5) if active else Qt.PenStyle.NoPen)
            p.setBrush(fill if active else QColor(255, 255, 255, 14))
            p.drawRoundedRect(QRectF(r).adjusted(.5, .5, -.5, -.5), 6, 6)

            if ch.class_id:
                sub = class_name(ch.class_id) + ("" if ch.class_auto else " ▾") + f" · {len(ch.cast)}"
                n_hidden = len(self.state.hidden_spells(pseudo))
                if n_hidden:
                    sub += f" (−{n_hidden})"                    # sorts masqués pour ce compte
                sub_pen = self._accent if (active and ch.cast) else self._gray
            else:
                sub = tr("easyconome.class_unknown", "Classe ?") + " ▾"
                sub_pen = self._accent                          # attire l'œil : il faut choisir une classe

            if r.height() >= TAB_H:                             # onglet à deux lignes : pseudo / classe
                p.setFont(f_name)
                p.setPen(self._text)
                name = fm.elidedText(pseudo, Qt.TextElideMode.ElideRight, r.width() - 8)
                p.drawText(QRect(r.left() + 4, r.top() + 3, r.width() - 8, 16),
                           Qt.AlignmentFlag.AlignCenter, name)
                p.setFont(f_sub)
                p.setPen(sub_pen)
                sub = fm_sub.elidedText(sub, Qt.TextElideMode.ElideRight, r.width() - 6)
                p.drawText(QRect(r.left(), r.top() + 21, r.width(), 15), Qt.AlignmentFlag.AlignCenter, sub)
            else:                                               # onglet compact : tout sur une ligne
                sub_w = fm_sub.horizontalAdvance(sub)
                if r.width() - 12 - sub_w - 6 < 40 and ch.class_id:    # trop juste : on garde le compteur seul
                    sub = f"· {len(ch.cast)}"
                    sub_w = fm_sub.horizontalAdvance(sub)
                show_sub = r.width() - 12 - sub_w - 6 >= 40            # sinon : le pseudo seul, lisible
                name_w = r.width() - 12 - (sub_w + 6 if show_sub else 0)
                p.setFont(f_name)
                p.setPen(self._text)
                p.drawText(QRect(r.left() + 6, r.top(), name_w, r.height()),
                           Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                           fm.elidedText(pseudo, Qt.TextElideMode.ElideRight, name_w))
                if show_sub:
                    p.setFont(f_sub)
                    p.setPen(sub_pen)
                    p.drawText(QRect(r.right() - 6 - sub_w, r.top(), sub_w, r.height()),
                               Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, sub)

    def mouseMoveEvent(self, e) -> None:
        i = self._index_at(e.position().toPoint())
        tip = ""
        if i >= 0:
            pseudo = self.state.roster[i]
            tip = pseudo
            if not self.state.chars[pseudo].class_auto:
                tip += "\n" + tr("easyconome.tab_hint", "Clic sur la classe (ou clic droit) pour la changer")
            tip += "\n" + tr("easyconome.spells_hint", "Clic droit dans la grille : choisir les sorts affichés")
            n_hidden = len(self.state.hidden_spells(pseudo))
            if n_hidden:
                tip += " " + tr("easyconome.spells_hidden", "({n} masqué(s))").format(n=n_hidden)
        self.setToolTip(tip)

    def mousePressEvent(self, e) -> None:
        i = self._index_at(e.position().toPoint())
        if i < 0:
            return
        pseudo = self.state.roster[i]
        r = self._rects[i]
        ch = self.state.chars[pseudo]
        if e.button() == Qt.MouseButton.LeftButton:
            self.state.set_active(pseudo)
            # classe inconnue : n'importe quel clic ouvre le menu ; sinon clic sur la ligne de la classe
            # (onglet compact : une seule ligne, donc seulement clic droit)
            two_lines = r.h >= TAB_H
            if not ch.class_auto and (ch.class_id is None or (two_lines and e.position().y() - r.y >= r.h / 2)):
                self.overlay.show_class_menu(pseudo, e.globalPosition().toPoint())
        elif e.button() == Qt.MouseButton.RightButton and not ch.class_auto:
            self.overlay.show_class_menu(pseudo, e.globalPosition().toPoint())


# ==============================================================================
# 4 ter. PALETTE DES SORTS AFFICHÉS (clic droit dans la grille)
# ==============================================================================

PAL_TILE, PAL_GAP, PAL_PAD, PAL_COLS_MAX, PAL_MIN_W = 36, 4, 10, 8, 210
PAL_LINE_H, PAL_SECTION_GAP = 16, 10


def _spell_num(spell_id: str) -> tuple:
    _, _, num = spell_id.rpartition("_")
    return (int(num) if num.isdigit() else 0, spell_id)


class SpellPalette(QWidget):
    """Panneau flottant : toutes les icônes (classe + communs) d'un compte ; un clic masque / affiche.
    Il reste ouvert tant qu'on ne clique pas ailleurs (Échap le ferme aussi) : on règle plusieurs sorts d'affilée."""

    def __init__(self, state: EasyconomeState, cache: IconCache, overlay, pseudo: str,
                 sections: list[tuple[str, list[str]]]) -> None:
        super().__init__(overlay, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self.state, self.cache, self.pseudo, self.sections = state, cache, pseudo, sections
        self._bg = color("PANEL")
        self._bg.setAlpha(245)
        self._accent, self._gray, self._text = color("ACCENT"), color("GRAY"), color("TEXT")
        self._title_font = QFont(self.font())
        self._title_font.setBold(True)
        self._link_font = QFont(self.font())
        self._link_font.setPixelSize(11)
        self._hover: tuple[str, int] | None = None
        self._titles: list[tuple[QRect, str, list[str]]] = []      # (zone, texte, sorts de la section)
        self._links: list[tuple[QRect, str, list[str], bool]] = [] # (zone, texte, sorts, masquer ?)
        self._cells: list[tuple[QRect, str]] = []
        self._build()

    def _hidden(self) -> set:
        return set(self.state.hidden_spells(self.pseudo))

    def _build(self) -> None:
        fm = QFontMetrics(self._link_font)
        cols = max(1, min(PAL_COLS_MAX, max(len(ids) for _, ids in self.sections)))
        grid_w = cols * PAL_TILE + (cols - 1) * PAL_GAP
        width = max(grid_w, PAL_MIN_W) + 2 * PAL_PAD
        y = PAL_PAD
        for k, (title, ids) in enumerate(self.sections):
            if k:
                y += PAL_SECTION_GAP
            self._titles.append((QRect(PAL_PAD, y, width - 2 * PAL_PAD, PAL_LINE_H), title, ids))
            y += PAL_LINE_H
            x = PAL_PAD
            for label, hide in ((tr("easyconome.pal_show_all", "Tout afficher"), False),
                                (tr("easyconome.pal_hide_all", "Tout masquer"), True)):
                w = fm.horizontalAdvance(label) + 4
                self._links.append((QRect(x, y, w, PAL_LINE_H), label, ids, hide))
                x += w + 12
            y += PAL_LINE_H + 2
            for i, sid in enumerate(ids):
                r, c = divmod(i, cols)
                self._cells.append((QRect(PAL_PAD + c * (PAL_TILE + PAL_GAP), y + r * (PAL_TILE + PAL_GAP),
                                          PAL_TILE, PAL_TILE), sid))
            y += -(-len(ids) // cols) * (PAL_TILE + PAL_GAP) - PAL_GAP
        self.setFixedSize(width, y + PAL_PAD)

    def _hit(self, pos: QPoint) -> tuple[str, int] | None:
        for i, (r, *_rest) in enumerate(self._links):
            if r.contains(pos):
                return ("link", i)
        for i, (r, _sid) in enumerate(self._cells):
            if r.contains(pos):
                return ("cell", i)
        return None

    # ------------------------------------------------------------------
    def paintEvent(self, e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.cache.configure(PAL_TILE, self.devicePixelRatioF())
        hidden = self._hidden()

        p.setPen(QPen(self._gray, 1))
        p.setBrush(self._bg)
        p.drawRoundedRect(QRectF(self.rect()).adjusted(.5, .5, -.5, -.5), 8, 8)

        for r, text, ids in self._titles:
            shown = sum(1 for s in ids if s not in hidden)
            p.setFont(self._title_font)
            p.setPen(self._text)
            p.drawText(r, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                       QFontMetrics(self._title_font).elidedText(f"{text} · {shown}/{len(ids)}",
                                                                 Qt.TextElideMode.ElideRight, r.width()))
        p.setFont(self._link_font)
        for i, (r, label, _ids, _hide) in enumerate(self._links):
            f = QFont(self._link_font)
            f.setUnderline(self._hover == ("link", i))
            p.setFont(f)
            p.setPen(self._accent)
            p.drawText(r, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, label)

        for i, (r, sid) in enumerate(self._cells):
            pm = self.cache.get(sid, False)
            if sid in hidden:
                p.setOpacity(0.22)
                p.drawPixmap(r.topLeft(), pm)
                p.setOpacity(1.0)
                p.setPen(QPen(QColor(255, 255, 255, 50), 1, Qt.PenStyle.DashLine))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRoundedRect(r.adjusted(0, 0, -1, -1), 6, 6)
            else:
                p.drawPixmap(r.topLeft(), pm)
            if self._hover == ("cell", i):
                p.setPen(QPen(self._accent, 2))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRoundedRect(r.adjusted(1, 1, -1, -1), 6, 6)

    # ------------------------------------------------------------------
    def mouseMoveEvent(self, e) -> None:
        hit = self._hit(e.position().toPoint())
        if hit != self._hover:
            self._hover = hit
            self.setCursor(Qt.CursorShape.PointingHandCursor if hit else Qt.CursorShape.ArrowCursor)
            self.update()

    def leaveEvent(self, e) -> None:
        if self._hover is not None:
            self._hover = None
            self.update()

    def mousePressEvent(self, e) -> None:
        if e.button() != Qt.MouseButton.LeftButton:
            return
        hit = self._hit(e.position().toPoint())
        if hit is None:
            return
        kind, i = hit
        if kind == "link":
            _r, _label, ids, hide = self._links[i]
            self.state.set_hidden(self.pseudo, ids, hide)
        else:
            sid = self._cells[i][1]
            self.state.set_hidden(self.pseudo, [sid], sid not in self._hidden())
        self.update()


# ==============================================================================
# 5. OVERLAY
#    Pas de QLayout : les enfants sont placés d'après le Layout calculé ci-dessus.
# ==============================================================================

EDGE_L, EDGE_R, EDGE_T, EDGE_B = 1, 2, 4, 8
_EDGE_CURSORS = {
    EDGE_L: Qt.CursorShape.SizeHorCursor, EDGE_R: Qt.CursorShape.SizeHorCursor,
    EDGE_T: Qt.CursorShape.SizeVerCursor, EDGE_B: Qt.CursorShape.SizeVerCursor,
    EDGE_L | EDGE_T: Qt.CursorShape.SizeFDiagCursor, EDGE_R | EDGE_B: Qt.CursorShape.SizeFDiagCursor,
    EDGE_R | EDGE_T: Qt.CursorShape.SizeBDiagCursor, EDGE_L | EDGE_B: Qt.CursorShape.SizeBDiagCursor,
}


class Overlay(QWidget):
    def __init__(self, state: EasyconomeState, cache: IconCache, on_close=None) -> None:
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.Tool | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)    # n'active jamais la fenêtre
        self.state, self.cache, self._on_close = state, cache, on_close
        self._pal_cache = IconCache(state.catalog)          # la palette a sa propre taille d'icône

        self.collapsed = bool(state.setting("collapsed", False))
        self.tile = TILE_DEFAULT                                          # recalculée par chaque disposition
        cols = state.setting("cols", DEFAULT_COLS)
        self.cols = cols if isinstance(cols, int) and cols >= 1 else DEFAULT_COLS
        w, h = state.setting("w"), state.setting("h")                     # taille voulue (None = naturelle)
        self.want_w = w if isinstance(w, int) and w > 0 else None
        self.want_h = h if isinstance(h, int) and h > 0 else None
        self._layout: Layout | None = None
        self._rz = None                                                   # redimensionnement en cours
        self.setMouseTracking(True)

        self._bg = color("PANEL")
        self._bg.setAlpha(240)
        self._accent = color("ACCENT")
        accent, text, gray = self._accent.name(), color("TEXT").name(), color("GRAY").name()
        panel = color("PANEL").name()
        self.setStyleSheet(
            f"QLabel{{color:{text};font-size:12px;}}"
            f"QPushButton{{color:{text};background:rgba(255,255,255,18);border:none;border-radius:5px;"
            f"min-width:26px;max-width:26px;min-height:24px;max-height:24px;font-size:14px;padding:0;}}"
            f"QPushButton:hover{{background:rgba(255,255,255,40);}}"
            f"QPushButton:checked{{background:{accent};color:#000;}}"
            f"QMenu{{background:{panel};color:{text};border:1px solid {gray};}}"
            f"QMenu::item{{padding:4px 18px;}}QMenu::item:selected{{background:{accent};color:#000;}}"
            f"QMenu::item:disabled{{color:{gray};}}")

        hint = tr("easyconome.drag_hint",
                  "Glisser pour déplacer · bords = taille (les icônes s'adaptent seules)")
        self.title = QLabel(tr("easyconome.title", "Easyconome"), self)
        self.title.setStyleSheet("font-weight:bold;")
        self.title.setToolTip(hint)
        self.btn_reset = self._button("↺", tr("easyconome.reset", "Nouveau combat : remet tous les sorts à zéro"))
        self.btn_col = self._button("–", tr("easyconome.collapse", "Réduire / agrandir"))
        self.btn_close = self._button("×", tr("easyconome.close", "Fermer Easyconome (les sorts cochés sont oubliés)"))
        self._buttons = (self.btn_reset, self.btn_col, self.btn_close)

        self.tabs = TabBar(state, self)
        self.grid = SpellGrid(state, cache, self, self.tile)

        self._reset_armed = False
        self._reset_timer = QTimer(self)
        self._reset_timer.setSingleShot(True)
        self._reset_timer.timeout.connect(self._disarm_reset)

        self.btn_reset.clicked.connect(self._on_reset_clicked)
        self.btn_col.clicked.connect(self._toggle_collapsed)
        self.btn_close.clicked.connect(lambda: self._on_close and self._on_close())

        state.roster_changed.connect(lambda *_: self._relayout())         # un compte arrive / part

        self._relayout()
        self.setWindowOpacity(0.85)
        self._restore_position()
        self._update_edge_cursor(0)

    def _button(self, glyph: str, tip: str) -> QPushButton:
        b = QPushButton(glyph, self)
        b.setToolTip(tip)
        b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        return b

    # ------------------------------------------------------------------
    # Disposition
    # ------------------------------------------------------------------
    def _max_width(self) -> int:
        scr = self.screen() or QGuiApplication.primaryScreen()
        return scr.availableGeometry().width() if scr else 1920

    def _max_height(self) -> int:
        scr = self.screen() or QGuiApplication.primaryScreen()
        return scr.availableGeometry().height() if scr else 1080

    def _compute(self) -> Layout:
        w = None if self.want_w is None else min(self.want_w, self._max_width())
        h = None if (self.want_h is None or self.collapsed) else min(self.want_h, self._max_height())
        return compute_layout(self.state.n_spells_needed(), len(self.state.roster), self.collapsed, w, h, self.cols)

    def _relayout(self, lay: Layout | None = None,
                  anchor_right: int | None = None, anchor_bottom: int | None = None) -> None:
        """Applique la disposition (calculée ici si `lay` est None). anchor_* : bord de la fenêtre
        qui doit rester en place (poignée gauche / haute tirée : la fenêtre s'agrandit vers l'autre côté)."""
        if lay is None:
            lay = self._compute()
        self.cols, self.tile = lay.cols, lay.tile            # grille et taille d'icône : TOUJOURS déduites de la fenêtre
        if lay == self._layout and anchor_right is None and anchor_bottom is None:
            return
        self._layout = lay
        x = anchor_right - lay.width if anchor_right is not None else self.x()
        y = anchor_bottom - lay.height if anchor_bottom is not None else self.y()
        self.setGeometry(x, y, lay.width, lay.height)
        self._place(lay)

    def _place(self, lay: Layout) -> None:
        self.title.setGeometry(*lay.title)
        self.title.setVisible(lay.show_title)
        for btn, r in zip(self._buttons, lay.buttons):
            btn.setGeometry(*r)
        self.btn_col.setText("+" if self.collapsed else "–")
        self.tabs.set_layout(lay)
        self.grid.set_layout(lay)
        self.grid.setVisible(not self.collapsed)
        self.update()

    # ------------------------------------------------------------------
    # En-tête
    # ------------------------------------------------------------------
    def _on_reset_clicked(self) -> None:
        """Deux clics rapprochés : un clic de trop en plein combat ne doit pas tout effacer."""
        if self._reset_armed:
            self._disarm_reset()
            self.state.reset_all()
            return
        self._reset_armed = True
        self.btn_reset.setText("?")
        self.btn_reset.setStyleSheet(f"background:{color('RED').name()};color:#fff;")
        self.btn_reset.setToolTip(tr("easyconome.reset_confirm", "Clique encore pour confirmer"))
        self._reset_timer.start(RESET_CONFIRM_MS)

    def _disarm_reset(self) -> None:
        self._reset_armed = False
        self.btn_reset.setText("↺")
        self.btn_reset.setStyleSheet("")
        self.btn_reset.setToolTip(tr("easyconome.reset", "Nouveau combat : remet tous les sorts à zéro"))

    def _toggle_collapsed(self) -> None:
        self.collapsed = not self.collapsed
        self.state.set_setting("collapsed", self.collapsed)
        self._relayout()

    def warm(self) -> None:
        """Pré-construit les icônes des comptes connectés (hors combat, pas au premier clic)."""
        self.cache.configure(self.tile, self.devicePixelRatioF())
        for ch in self.state.online_chars():
            if ch.class_id:
                self.cache.warm(ch.order)

    # ------------------------------------------------------------------
    # Classe choisie à la main
    # ------------------------------------------------------------------
    def show_class_menu(self, pseudo: str, global_pos: QPoint) -> None:
        ch = self.state.chars.get(pseudo)
        if ch is None or ch.class_auto:                  # classe détectée : rien à choisir
            return
        menu = QMenu(self)
        menu.addAction(tr("easyconome.class_of", "Classe de {pseudo}").format(pseudo=pseudo)).setEnabled(False)
        menu.addSeparator()
        for cid in CLASSES:
            menu.addAction(class_name(cid)).triggered.connect(
                lambda _=False, c=cid: self.state.set_class(pseudo, c))
        menu.exec(global_pos)

    # ------------------------------------------------------------------
    # Sorts affichés / masqués (clic droit dans la grille)
    # ------------------------------------------------------------------
    def show_spells_palette(self, pseudo: str, global_pos: QPoint) -> None:
        ch = self.state.chars.get(pseudo)
        if ch is None or ch.class_id is None:            # jamais sur le sélecteur de classe
            return
        common = list(self.state.catalog.common)
        common_set = set(common)
        # tous les sorts du compte = visibles + masqués (la grille vide reste donc réglable)
        own = sorted((s for s in set(ch.order) | set(self.state.hidden_spells(pseudo)) if s not in common_set),
                     key=_spell_num)
        sections = []
        if own:
            sections.append((f"{tr('easyconome.pal_class', 'Sorts de la classe')} · "
                             f"{class_name(ch.class_id)}", own))
        if common:
            sections.append((tr("easyconome.pal_common", "Sorts communs"), common))
        if not sections:
            return
        pal = SpellPalette(self.state, self._pal_cache, self, pseudo, sections)
        scr = QGuiApplication.screenAt(global_pos) or QGuiApplication.primaryScreen()
        if scr is not None:                              # reste entièrement à l'écran
            geo = scr.availableGeometry()
            x = max(geo.left(), min(global_pos.x(), geo.right() - pal.width() + 1))
            y = max(geo.top(), min(global_pos.y(), geo.bottom() - pal.height() + 1))
        else:
            x, y = global_pos.x(), global_pos.y()
        pal.move(x, y)
        pal.show()

    # ------------------------------------------------------------------
    # Position
    # ------------------------------------------------------------------
    def _restore_position(self) -> None:
        x, y = self.state.setting("x"), self.state.setting("y")
        pos = QPoint(x, y) if isinstance(x, int) and isinstance(y, int) else QPoint(80, 80)
        if QGuiApplication.screenAt(pos) is None:                 # écran débranché : on recale
            screen = QGuiApplication.primaryScreen()
            pos = screen.availableGeometry().topLeft() + QPoint(80, 80) if screen else QPoint(80, 80)
        self.move(pos)

    def moveEvent(self, e) -> None:
        super().moveEvent(e)
        if self.isVisible():                                       # pas de sauvegarde pendant l'init
            self.state.set_setting("x", self.x())
            self.state.set_setting("y", self.y())

    # ------------------------------------------------------------------
    # Souris : déplacer (fond de la fenêtre), redimensionner (bords), zoomer (molette)
    # ------------------------------------------------------------------
    def _edges_at(self, pos: QPoint) -> int:
        x, y, w, h = pos.x(), pos.y(), self.width(), self.height()
        edges = 0
        if x < EDGE:
            edges |= EDGE_L
        elif x >= w - EDGE:
            edges |= EDGE_R
        if not self.collapsed:                                     # réduit : la hauteur n'est pas réglable
            if y < EDGE:
                edges |= EDGE_T
            elif y >= h - EDGE:
                edges |= EDGE_B
            # coins : zone élargie, sinon il faudrait viser pile les deux bords à la fois
            cx = EDGE_L if x < CORNER else EDGE_R if x >= w - CORNER else 0
            cy = EDGE_T if y < CORNER else EDGE_B if y >= h - CORNER else 0
            if cx and cy:
                edges = cx | cy
        return edges

    def _update_edge_cursor(self, edges: int) -> None:
        self.setCursor(_EDGE_CURSORS.get(edges, Qt.CursorShape.SizeAllCursor))

    def mousePressEvent(self, e) -> None:
        if e.button() != Qt.MouseButton.LeftButton:
            return
        edges = self._edges_at(e.position().toPoint())
        if edges:
            self._rz = (edges, e.globalPosition().toPoint(), self.geometry())
            return
        handle = self.windowHandle()                               # déplacement natif (fluide)
        if handle is not None:
            handle.startSystemMove()

    def mouseMoveEvent(self, e) -> None:
        if self._rz is None:
            self._update_edge_cursor(self._edges_at(e.position().toPoint()))
            return
        edges, start, geo = self._rz
        d = e.globalPosition().toPoint() - start
        drag_w = bool(edges & (EDGE_L | EDGE_R))
        drag_h = bool(edges & (EDGE_T | EDGE_B)) and not self.collapsed
        # La fenêtre prend EXACTEMENT la taille demandée par la souris (au minimum près) ; colonnes,
        # lignes et taille d'icône sont recalculées en direct à chaque mouvement.
        if drag_w:
            self.want_w = geo.width() + (d.x() if edges & EDGE_R else -d.x())
        if drag_h:
            self.want_h = geo.height() + (d.y() if edges & EDGE_B else -d.y())
        self._relayout(anchor_right=geo.x() + geo.width() if edges & EDGE_L else None,
                       anchor_bottom=geo.y() + geo.height() if edges & EDGE_T else None)

    def mouseReleaseEvent(self, e) -> None:
        if self._rz is not None:
            self._rz = None
            self.want_w = self.width()                             # on mémorise la taille obtenue
            if not self.collapsed:
                self.want_h = self.height()
            self.state.set_setting("w", self.want_w)
            self.state.set_setting("h", self.want_h)
            self._update_edge_cursor(self._edges_at(e.position().toPoint()))

    def enterEvent(self, e) -> None:
        self.setWindowOpacity(1.0)

    def leaveEvent(self, e) -> None:
        self.setWindowOpacity(0.85)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(self._bg)
        p.setPen(QPen(QColor(255, 255, 255, 45), 1.5))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 10, 10)


# ==============================================================================
# 6. MANAGER (point d'entrée pour Main.py)
# ==============================================================================

POLL_MS = 200
SAVE_DEBOUNCE_MS = 400
COMMANDS = ("toggle", "start", "stop", "reset", "next", "prev")

try:
    import win32gui

    def _foreground_hwnd() -> int:
        return win32gui.GetForegroundWindow()
except Exception:                                  # hors Windows / pywin32 absent
    def _foreground_hwnd() -> int:
        return 0


class EasyconomeManager(QObject):
    _cmd = pyqtSignal(str)

    def __init__(self,
                 get_roster: Callable[[], Iterable[tuple[int, str]]],
                 class_of: Callable[[str], str | None],
                 data: dict,
                 on_persist: Callable[[], None],
                 visible_when: Callable[[], bool] | None = None,
                 catalog: SpellCatalog | None = None,
                 parent: QObject | None = None) -> None:
        """
        get_roster : () -> [(hwnd, pseudo), …]   ex. lambda: self._char_order
        class_of   : pseudo -> classe détectée ou None   (via self._char_icons[pseudo]["portrait"])
        data       : dict mémorisé = core.easyconome.decode_data(cfg.get("easyconome_data")).
                     Modifié EN PLACE : à écrire dans le registre avec encode_data(data).
        on_persist : appelé (débouncé) quand `data` change ; chez Dracoon : self._persist_config
        """
        super().__init__(parent)
        self.catalog = catalog or SpellCatalog()
        self.state = EasyconomeState(self.catalog, data)
        self.cache = IconCache(self.catalog)
        self._get_roster, self._class_of, self._on_persist = get_roster, class_of, on_persist
        self._visible_when = visible_when      # () -> bool ; None = toujours visible
        self._overlay: Overlay | None = None
        self._running = False
        self._last_sig = None
        self._last_fg = 0

        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(SAVE_DEBOUNCE_MS)      # une seule écriture après un geste
        self._save_timer.timeout.connect(self._flush)
        self.state.dirty.connect(self._save_timer.start)

        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(POLL_MS)
        self._poll_timer.timeout.connect(self._poll)

        self._cmd.connect(self._on_cmd)                       # file d'attente inter-threads

    # ------------------------------------------------------------------
    # Cycle de vie : l'outil se lance et se ferme comme movemode / dradidas
    # ------------------------------------------------------------------
    @property
    def running(self) -> bool:
        return self._running

    def start(self) -> None:
        """Lance l'outil : récupère les comptes ouverts et affiche l'overlay."""
        if self._running:
            return
        self._running = True
        if self._overlay is None:
            self._overlay = Overlay(self.state, self.cache, on_close=self.stop)
        self._poll(force=True)
        self._poll_timer.start()
        self._apply_visibility()

    def stop(self) -> None:
        """Ferme l'outil : les comptes et sorts lancés sont oubliés ; classes et position sont gardées."""
        if not self._running:
            return
        self._running = False
        self._poll_timer.stop()
        self._last_fg = 0
        self.state.end_session()
        if self._overlay is not None:
            self._overlay.hide()
        self._save_timer.stop()
        self._flush()                                        # la mémoire pseudo -> classe est écrite tout de suite

    def toggle(self) -> None:
        self.stop() if self._running else self.start()

    def _flush(self) -> None:
        try:
            self._on_persist()
        except Exception:
            pass

    def post(self, cmd: str) -> None:
        """Peut être appelé depuis N'IMPORTE quel thread (raccourcis, tray, hook souris…)."""
        if cmd in COMMANDS:
            self._cmd.emit(cmd)

    @pyqtSlot(str)
    def _on_cmd(self, cmd: str) -> None:
        if cmd == "toggle":
            self.toggle()
        elif cmd == "start":
            self.start()
        elif cmd == "stop":
            self.stop()
        elif not self._running or self._overlay is None:
            return                                           # les autres commandes n'ont de sens que lancé
        elif cmd == "reset":
            self.state.reset_all()
        elif cmd == "next":
            self.state.step_active(1)
        elif cmd == "prev":
            self.state.step_active(-1)

    def shutdown(self) -> None:
        """À appeler dans App._quit() : coupe les timers et masque l'overlay.
        (L'écriture des données se fait déjà via _persist_config() dans _quit.)"""
        self._running = False
        self._poll_timer.stop()
        self._save_timer.stop()
        if self._overlay is not None:
            self._overlay.hide()

    def _should_show(self) -> bool:
        """Overlay visible seulement si `visible_when()` est vrai (Dofus au premier plan).
        On le garde aussi tant qu'un menu de l'overlay (choix de classe) est ouvert :
        ce menu prend le focus, et masquer l'overlay le fermerait."""
        if self._visible_when is None:
            return True
        try:
            if QApplication.activePopupWidget() is not None:
                return True
            return bool(self._visible_when())
        except Exception:
            return True

    def _apply_visibility(self) -> None:
        ov = self._overlay
        if ov is None or not self._running:
            return
        want = self._should_show()
        if want and not ov.isVisible():
            ov.show()
        elif not want and ov.isVisible():
            ov.hide()
    
    # ------------------------------------------------------------------
    def _poll(self, force: bool = False) -> None:
        self._apply_visibility()
        if force:
            self._last_sig = None
        try:
            roster = [(int(h), str(p)) for h, p in list(self._get_roster())]
        except Exception:                                    # liste modifiée par un autre thread : on réessaie
            return                                           # au prochain tick (200 ms)

        classes = tuple(self._class_of(p) for _, p in roster)
        sig = (tuple(roster), classes)
        if sig != self._last_sig:
            self._last_sig = sig
            self.state.sync_roster(roster, self._class_of)
            if self._overlay is not None:
                QTimer.singleShot(0, self._overlay.warm)

        fg = _foreground_hwnd()
        if fg != self._last_fg:                              # on ne réagit qu'à un CHANGEMENT de fenêtre :
            self._last_fg = fg                               # un clic manuel sur un onglet reste respecté
            ch = self.state.by_hwnd(fg)
            if ch is not None:
                self.state.set_active(ch.pseudo)
