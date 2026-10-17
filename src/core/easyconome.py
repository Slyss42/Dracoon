"""
core/easyconome.py
Challenge Économe : catalogue des sorts + état (qui a lancé quel sort, pour chaque compte).

Logique pure : aucun import Qt / Win32 / config (testable sans interface).
Tous les appels doivent venir du thread GUI ; le manager de ui/UI_Easyconome.py ramène les
commandes venant d'autres threads (raccourcis clavier) vers lui.

Icônes attendues dans src/ressources/spells/ (dossier unique) :
    cra1.png, cra2.png, sram10.png, common1.png, ...   <classe|common><numéro>.png
Sans aucune icône reconnue, un catalogue de placeholders est généré (26 sorts de classe + 6 communs = 32).
"""
from __future__ import annotations

import json
import os
import sys
import re
from typing import Callable, Iterable


# ==============================================================================
# 1. CATALOGUE DES SORTS
# ==============================================================================

# Identifiants alignés sur les portraits (ressources/portraits/<classe>_<f|m>.png)
CLASSES: dict[str, str] = {
    "cra": "Crâ",
    "ecaflip": "Ecaflip",
    "eniripsa": "Eniripsa",
    "enutrof": "Enutrof",
    "feca": "Féca",
    "iop": "Iop",
    "osamodas": "Osamodas",
    "pandawa": "Pandawa",
    "sacrieur": "Sacrieur",
    "sadida": "Sadida",
    "sram": "Sram",
    "xelor": "Xélor",
}
COMMON = "common"

PLACEHOLDER_OWN = 26
PLACEHOLDER_COMMON = 6


def resources_dir() -> str:
    """Même convention que ICON_PATH dans core/config.py (…/ressources/…)."""
    if getattr(sys, "frozen", False):
        base = os.path.join(sys._MEIPASS, "ressources")
    else:
        base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ressources")
    return os.path.abspath(os.path.join(base, "spells"))


def class_from_portrait(portrait: str | None) -> str | None:
    """'cra_f' / 'cra_m' / 'portraits/cra_f.png' -> 'cra'.
    None si pas de portrait ou si ce n'est pas un portrait de classe (ex. 'dofus_icon')."""
    if not portrait:
        return None
    name = os.path.splitext(os.path.basename(str(portrait).replace("\\", "/")))[0].strip().lower()
    cid, sep, gender = name.rpartition("_")
    if not sep or gender not in ("f", "m"):
        return None
    return cid if cid in CLASSES else None


def spell_folder(spell_id: str) -> str:
    """'iop_03' -> 'iop', 'common_02' -> 'common'."""
    return spell_id.rsplit("_", 1)[0]


class SpellCatalog:
    def __init__(self, root: str | None = None) -> None:
        self.root = root or resources_dir()
        self.has_files = False
        self._own: dict[str, list[str]] = {}
        self._common: list[str] = []
        self._paths: dict[str, str] = {}      # id du sort -> chemin du fichier
        self._load()


    def _load(self) -> None:
        if self._scan_flat():                    # des PNG <classe><numéro>.png ont été trouvés
            self.has_files = True
            return

        self.has_files = False                   # aucun fichier : catalogue de placeholders
        self._common = [f"common_{i:02d}" for i in range(1, PLACEHOLDER_COMMON + 1)]
        for cid in CLASSES:
            self._own[cid] = [f"{cid}_{i:02d}" for i in range(1, PLACEHOLDER_OWN + 1)]

    def _scan_flat(self) -> bool:
        """Dossier unique : cra1.png, cra2.png, sram10.png, common1.png…
        Les fichiers qui ne correspondent pas à <classe|common><numéro>.png sont ignorés."""
        pattern = re.compile(r"^([a-z]+?)(\d+)\.png$", re.IGNORECASE)
        try:
            names = os.listdir(self.root)
        except OSError:
            return False

        found: dict[str, dict[int, str]] = {}
        for name in names:
            m = pattern.match(name)
            if not m:
                continue
            group = m.group(1).lower()
            if group != COMMON and group not in CLASSES:
                continue
            found.setdefault(group, {})[int(m.group(2))] = os.path.join(self.root, name)

        if not found:
            return False

        for group, by_num in found.items():
            ids: list[str] = []
            for num in sorted(by_num):               # ordre numérique : 2 avant 10
                sid = f"{group}_{num:02d}"           # même format d'id qu'avant (cra_07)
                self._paths[sid] = by_num[num]
                ids.append(sid)
            if group == COMMON:
                self._common = ids
            else:
                self._own[group] = ids
        for cid in CLASSES:
            self._own.setdefault(cid, [])
        return True       

    # ------------------------------------------------------------------
    def spells_for(self, class_id: str) -> list[str]:
        """Ordre par défaut : sorts de classe puis sorts communs."""
        return list(self._own.get(class_id, [])) + list(self._common)

    @property
    def common(self) -> list[str]:
        """Identifiants des sorts communs (copie)."""
        return list(self._common)

    @property
    def max_spells(self) -> int:
        return max((len(o) + len(self._common) for o in self._own.values()), default=0)

    def icon_path(self, spell_id: str) -> str | None:
        return self._paths.get(spell_id)


# ==============================================================================
# 2. ÉTAT DU CHALLENGE
# ==============================================================================

# Données mémorisées entre deux lancements (une seule clé de registre, JSON, comme char_icons) :
#   "classes" : {pseudo: classe}                  <- le SEUL état gardé quand l'outil est fermé
#   "orders"  : {pseudo: {classe: [sorts]}}       <- ordre personnalisé des sorts (fonction future)
#   "hidden"  : {pseudo: [sorts]}                 <- sorts masqués pour ce compte (ex. sorts communs non appris)
#   "ui"      : {"x", "y", "tile", "collapsed"}   <- position / taille de l'overlay
# Les sorts lancés ne sont JAMAIS sauvegardés.

def normalize_data(data: dict) -> dict:
    """Remet `data` dans la forme attendue, EN PLACE (l'appelant garde la même référence)."""
    classes = data.get("classes")
    data["classes"] = ({str(p): c for p, c in classes.items() if c in CLASSES}
                       if isinstance(classes, dict) else {})
    orders = data.get("orders")
    clean: dict[str, dict[str, list[str]]] = {}
    if isinstance(orders, dict):
        for pseudo, per_class in orders.items():
            if isinstance(per_class, dict):
                kept = {c: [str(s) for s in lst] for c, lst in per_class.items()
                        if c in CLASSES and isinstance(lst, list)}
                if kept:
                    clean[str(pseudo)] = kept
    data["orders"] = clean
    hidden = data.get("hidden")
    data["hidden"] = ({str(p): sorted({str(s) for s in lst})
                       for p, lst in hidden.items() if isinstance(lst, list) and lst}
                      if isinstance(hidden, dict) else {})
    if not isinstance(data.get("ui"), dict):
        data["ui"] = {}
    return data


def decode_data(raw: str | None) -> dict:
    """Valeur de registre -> dict valide. Tolère None, vide, JSON invalide ou de mauvais type."""
    try:
        data = json.loads(raw) if raw else {}
    except (TypeError, ValueError):
        data = {}
    return normalize_data(data if isinstance(data, dict) else {})


def encode_data(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


class Event:
    """Mini signal : connect(fn) / emit(*args). Pas de dépendance Qt."""
    __slots__ = ("_subs",)

    def __init__(self) -> None:
        self._subs: list[Callable] = []

    def connect(self, fn: Callable) -> Callable:
        self._subs.append(fn)
        return fn

    def emit(self, *args) -> None:
        for fn in tuple(self._subs):
            fn(*args)


class Character:
    __slots__ = ("pseudo", "hwnd", "class_id", "class_auto", "online", "order", "order_for", "cast")

    def __init__(self, pseudo: str) -> None:
        self.pseudo = pseudo
        self.hwnd = 0
        self.class_id: str | None = None
        self.class_auto = False        # True = classe déduite du portrait de la barre des tâches
        self.online = False            # fenêtre présente dans Dracoon en ce moment
        self.order: list[str] = []     # ordre d'affichage des sorts (personnalisable), sorts masqués exclus
        self.order_for: str | None = None   # classe pour laquelle `order` a été construit
        self.cast: set[str] = set()    # sorts déjà lancés ce combat


class EasyconomeState:
    def __init__(self, catalog: SpellCatalog, data: dict | None = None) -> None:
        """
        data : dict mémorisé (voir decode_data). Modifié EN PLACE : l'appelant (Main.py) garde
               la même référence et l'écrit dans le registre quand `dirty` est émis.
        """
        self.catalog = catalog
        self.data = normalize_data(data if data is not None else {})
        self.chars: dict[str, Character] = {}
        self.roster: list[str] = []            # pseudos en ligne, dans l'ordre de Dracoon
        self.active: str | None = None

        self.roster_changed = Event()
        self.active_changed = Event()
        self.cast_changed = Event()            # (pseudo)
        self.order_changed = Event()           # (pseudo)
        self.dirty = Event()                   # `data` a changé : à sauvegarder (le manager débounce)

    # ------------------------------------------------------------------
    # Données mémorisées
    # ------------------------------------------------------------------
    def setting(self, key: str, default=None):
        return self.data["ui"].get(key, default)

    def set_setting(self, key: str, value) -> None:
        if self.data["ui"].get(key) != value:
            self.data["ui"][key] = value
            self.dirty.emit()

    def _remember_class(self, pseudo: str, class_id: str) -> None:
        if self.data["classes"].get(pseudo) != class_id:
            self.data["classes"][pseudo] = class_id
            self.dirty.emit()

    def _persist_order(self, ch: Character) -> None:
        if ch.class_id:
            self.data["orders"].setdefault(ch.pseudo, {})[ch.class_id] = list(ch.order)
            self.dirty.emit()

    # ------------------------------------------------------------------
    # Classe et ordre des sorts
    # ------------------------------------------------------------------
    def _apply_order(self, ch: Character) -> None:
        ch.order_for = ch.class_id
        if ch.class_id is None:
            ch.order = []
            return
        default = self.catalog.spells_for(ch.class_id)
        known = set(default)
        saved = self.data["orders"].get(ch.pseudo, {}).get(ch.class_id, [])
        kept = [s for s in dict.fromkeys(saved) if s in known]       # dédoublonné, sorts inconnus retirés
        kept_set = set(kept)
        ch.order = kept + [s for s in default if s not in kept_set]  # nouveaux sorts ajoutés à la fin
        hidden = set(self.data["hidden"].get(ch.pseudo, ()))
        if hidden:
            ch.order = [s for s in ch.order if s not in hidden]      # sorts masqués pour CE compte
        ch.cast &= set(ch.order)                                     # un sort masqué ne compte plus comme lancé

    def _resolve_class(self, ch: Character, detected: str | None) -> bool:
        """
        Classe du compte : portrait de la barre des tâches en priorité, sinon celle mémorisée
        (choisie à la main lors d'un lancement précédent). La classe connue est mémorisée
        dans les deux cas. True si quelque chose a changé.
        """
        if detected in CLASSES:
            new_class, new_auto = detected, True
            self._remember_class(ch.pseudo, detected)
        else:
            saved = self.data["classes"].get(ch.pseudo)
            new_class, new_auto = (saved if saved in CLASSES else None), False
        if (ch.class_id, ch.class_auto) == (new_class, new_auto) and ch.order_for == new_class:
            return False
        if ch.class_id != new_class:
            ch.cast.clear()                                  # les sorts ne sont plus les mêmes
        ch.class_id, ch.class_auto = new_class, new_auto
        self._apply_order(ch)
        return True

    def set_class(self, pseudo: str, class_id: str) -> bool:
        """Choix manuel. Ignoré si la classe vient du portrait (source de vérité)."""
        ch = self.chars.get(pseudo)
        if ch is None or ch.class_auto or class_id not in CLASSES:
            return False
        self._remember_class(pseudo, class_id)
        self._resolve_class(ch, None)
        self.roster_changed.emit()
        self.cast_changed.emit(pseudo)
        return True

    # ------------------------------------------------------------------
    # Sorts masqués (par compte)
    # ------------------------------------------------------------------
    def hidden_spells(self, pseudo: str) -> set[str]:
        return set(self.data["hidden"].get(pseudo, ()))

    def set_hidden(self, pseudo: str, spell_ids: Iterable[str], hidden: bool) -> None:
        """Masque (hidden=True) ou ré-affiche (False) des sorts pour UN compte. Mémorisé."""
        cur = self.hidden_spells(pseudo)
        ids = {str(s) for s in spell_ids}
        new = (cur | ids) if hidden else (cur - ids)
        if new == cur:
            return
        if new:
            self.data["hidden"][pseudo] = sorted(new)
        else:
            self.data["hidden"].pop(pseudo, None)
        self.dirty.emit()
        ch = self.chars.get(pseudo)
        if ch is not None:
            self._apply_order(ch)
            self.order_changed.emit(pseudo)
            self.cast_changed.emit(pseudo)
            self.roster_changed.emit()          # déclenche le recalcul de la disposition de l'overlay

    def n_spells_needed(self) -> int:
        """Nombre de cases à prévoir dans la grille (pour dimensionner l'overlay).
        Stable d'un onglet à l'autre : c'est le maximum sur tous les comptes en ligne."""
        online = self.online_chars()
        if not online or any(c.class_id is None for c in online):
            return self.catalog.max_spells       # sélecteur de classe affiché : on garde la place maximale
        return max(1, max(len(c.order) for c in online))

    def move_spell(self, pseudo: str, src: int, dst: int) -> None:
        ch = self.chars.get(pseudo)
        if ch is None or not (0 <= src < len(ch.order)) or not (0 <= dst < len(ch.order)) or src == dst:
            return
        ch.order.insert(dst, ch.order.pop(src))
        self._persist_order(ch)
        self.order_changed.emit(pseudo)

    # ------------------------------------------------------------------
    # Comptes connectés
    # ------------------------------------------------------------------
    def sync_roster(self, entries: Iterable[tuple[int, str]],
                    class_of: Callable[[str], str | None] = lambda p: None) -> bool:
        """
        entries  : [(hwnd, pseudo), …] dans l'ordre voulu pour les onglets.
        class_of : pseudo -> classe détectée via le portrait, ou None.

        Un compte qui disparaît est marqué hors-ligne MAIS garde ses sorts cochés
        (reconnexion auto, crash du client…). Il n'est oublié qu'au "nouveau combat".
        """
        changed = False
        seen: list[str] = []
        for hwnd, pseudo in entries:
            if not pseudo or pseudo in seen:
                continue
            seen.append(pseudo)
            ch = self.chars.get(pseudo)
            if ch is None:
                ch = self.chars[pseudo] = Character(pseudo)
                changed = True
            ch.hwnd = hwnd
            if not ch.online:
                ch.online = True
                changed = True
            if self._resolve_class(ch, class_of(pseudo)):
                changed = True

        for pseudo, ch in self.chars.items():
            if ch.online and pseudo not in seen:
                ch.online = False
                changed = True

        if seen != self.roster:
            self.roster = seen
            changed = True

        if changed:
            self.roster_changed.emit()
        if self.active not in self.roster:
            self._set_active(self.roster[0] if self.roster else None)
        return changed

    # ------------------------------------------------------------------
    # Perso actif
    # ------------------------------------------------------------------
    def active_char(self) -> Character | None:
        return self.chars.get(self.active) if self.active else None

    def online_chars(self) -> list[Character]:
        return [self.chars[p] for p in self.roster]

    def by_hwnd(self, hwnd: int) -> Character | None:
        if hwnd:
            for ch in self.online_chars():
                if ch.hwnd == hwnd:
                    return ch
        return None

    def _set_active(self, pseudo: str | None) -> None:
        if pseudo != self.active:
            self.active = pseudo
            self.active_changed.emit()

    def set_active(self, pseudo: str) -> None:
        if pseudo in self.roster:
            self._set_active(pseudo)

    def step_active(self, delta: int) -> None:
        if not self.roster:
            return
        i = self.roster.index(self.active) if self.active in self.roster else -1
        self._set_active(self.roster[(i + delta) % len(self.roster)])

    # ------------------------------------------------------------------
    # Sorts lancés
    # ------------------------------------------------------------------
    def toggle(self, pseudo: str, spell_id: str) -> None:
        ch = self.chars.get(pseudo)
        if ch is None or spell_id not in ch.order:
            return
        ch.cast.symmetric_difference_update({spell_id})
        self.cast_changed.emit(pseudo)

    def reset_char(self, pseudo: str) -> None:
        ch = self.chars.get(pseudo)
        if ch is not None and ch.cast:
            ch.cast.clear()
            self.cast_changed.emit(pseudo)

    def reset_all(self) -> None:
        """Nouveau combat : tout à zéro, et on oublie les comptes déconnectés."""
        gone = [p for p, c in self.chars.items() if not c.online]
        for p in gone:
            del self.chars[p]
        for ch in self.chars.values():
            if ch.cast:
                ch.cast.clear()
                self.cast_changed.emit(ch.pseudo)
        if gone:
            self.roster_changed.emit()

    def end_session(self) -> None:
        """Fermeture de l'outil : on oublie comptes et sorts lancés. Seul `data` survit (classes, position)."""
        self.chars.clear()
        self.roster = []
        self.roster_changed.emit()
        if self.active is not None:
            self.active = None
            self.active_changed.emit()

    def total_cast(self) -> int:
        return sum(len(c.cast) for c in self.chars.values())
