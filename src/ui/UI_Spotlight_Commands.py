"""
UI_Spotlight_Commands.py
"""

import difflib
import threading
import time

from PyQt6.QtCore import QTimer, QSettings

from core.i18n import t
from core.preset import load_order_presets, apply_order_preset
from core.windows import reorder_with_ungroup_regroup

# ----------------------------------------------------------------------
# Historique d'utilisation (persisté dans le registre, comme le reste
# de la config — voir core/config.py). On garde un couple id -> timestamp
# de dernière exécution pour chaque commande, afin de pouvoir trier le
# Spotlight du plus récent au moins récent et ne montrer par défaut
# qu'un tout petit nombre d'actions (voir DEFAULT_VISIBLE_COUNT dans
# UI_Spotlight.py).
# ----------------------------------------------------------------------
_HISTORY_SETTINGS = QSettings("Dracoon", "Spotlight")


def mark_command_used(cmd_id: str) -> None:
    """A appeler juste avant d'exécuter une commande : enregistre l'instant
    présent comme dernière utilisation de `cmd_id`."""
    if not cmd_id:
        return
    _HISTORY_SETTINGS.setValue(f"recent/{cmd_id}", time.time())


def get_last_used(cmd_id: str) -> float:
    """Timestamp (epoch) de dernière utilisation de `cmd_id`, ou 0.0 si la
    commande n'a jamais été lancée depuis le Spotlight."""
    if not cmd_id:
        return 0.0
    try:
        return float(_HISTORY_SETTINGS.value(f"recent/{cmd_id}", 0.0))
    except (TypeError, ValueError):
        return 0.0


def sort_by_recency(commands):
    """Trie une liste de commandes du plus récemment utilisé au moins
    récent. Les commandes jamais utilisées (timestamp 0) restent en fin
    de liste, dans leur ordre d'origine (tri stable)."""
    return sorted(commands, key=lambda c: get_last_used(c.get("id")), reverse=True)


# ----------------------------------------------------------------------
# Catégories (utilisées uniquement par le mode "Toutes les commandes" du
# Spotlight — la recherche et l'aperçu par défaut restent triés par
# récence, voir sort_by_recency). L'ordre de CATEGORY_ORDER fixe l'ordre
# d'affichage des groupes, indépendamment de l'ordre de build_commands().
# ----------------------------------------------------------------------
CATEGORY_ORDER = ["navigation","actions", "presets"]

CATEGORY_LABEL_KEYS = {
    "navigation": "spotlight.cat.navigation",
    "presets": "spotlight.cat.presets",
    "actions": "spotlight.cat.actions",

}


def group_by_category(commands):
    """Regroupe `commands` par catégorie pour l'affichage "Toutes les
    commandes". Renvoie une liste de tuples (category_key, label,
    [commandes triées alphabétiquement par label affiché]).

    Contrairement à l'aperçu par défaut / la recherche (triés par
    récence via sort_by_recency), ici on trie par ordre alphabétique à
    l'intérieur de chaque groupe : l'utilisateur parcourt la liste
    complète pour trouver une commande, pas pour relancer la dernière
    utilisée, donc la récence n'apporte rien et un ordre stable et
    prévisible aide davantage.

    Une catégorie absente de CATEGORY_ORDER (nouvelle commande sans
    catégorie assignée, oubli...) est regroupée sous "actions" par
    défaut plutôt que d'être silencieusement omise."""
    buckets = {key: [] for key in CATEGORY_ORDER}
    for cmd in commands:
        key = cmd.get("category") or "actions"
        buckets.setdefault(key, [])
        buckets[key].append(cmd)

    def _display_label(c):
        return c["label_fn"]() if "label_fn" in c else c["label"]

    groups = []
    seen = set()
    for key in list(CATEGORY_ORDER) + [k for k in buckets if k not in CATEGORY_ORDER]:
        if key in seen or not buckets.get(key):
            continue
        seen.add(key)
        label = t(CATEGORY_LABEL_KEYS.get(key, key))
        items = sorted(buckets[key], key=lambda c: _display_label(c).lower())
        groups.append((key, label, items))
    return groups


# ----------------------------------------------------------------------
# Recherche avec tolérance aux fautes de frappe
# ----------------------------------------------------------------------
FUZZY_THRESHOLD = 0.6  # 0 = tout matche, 1 = correspondance exacte requise


def _fuzzy_ratio(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b).ratio()


def command_matches(query: str, cmd: dict) -> bool:
    """True si `cmd` correspond à `query`, en tolérant les petites fautes
    de frappe / approximations (ex: 'racourci' matche 'raccourci').
    On teste d'abord une simple sous-chaîne (rapide, précis), puis on
    retombe sur une comparaison floue mot à mot si rien n'a matché."""
    q = query.lower().strip()
    if not q:
        return True

    label = cmd["label"].lower()
    keywords = [kw.lower() for kw in cmd.get("keywords", [])]
    candidates = [label, *keywords, *label.split()]

    # 1. Correspondance directe (sous-chaîne)
    if any(q in c for c in candidates):
        return True

    # 2. Tolérance floue : la requête entière contre chaque candidat...
    if any(_fuzzy_ratio(q, c) >= FUZZY_THRESHOLD for c in candidates):
        return True

    # ...puis mot par mot, pour les requêtes à plusieurs mots
    for qword in q.split():
        if len(qword) < 3:
            continue
        if any(_fuzzy_ratio(qword, c) >= FUZZY_THRESHOLD for c in candidates):
            return True

    return False

def _navigate(app, key):
    app._ensure_visible()
    app._switch_tab(key)


def _apply_preset(app, preset_name):
    """Charge un preset d'ordre et l'applique IMMÉDIATEMENT aux personnages
    connectés (ordre logique + réorganisation physique des fenêtres).
    Contrairement au dropdown de l'onglet Personnages, le Spotlight applique
    l'ordre directement, sans passer par le bouton 'Enregistrer l'ordre'."""
    presets = load_order_presets()
    pseudos = presets.get(preset_name)
    if pseudos is None:
        return
    app._char_order = apply_order_preset(pseudos, app._char_order)
    if hasattr(app, "refresh_characters"):
        app.refresh_characters()
    if hasattr(app, "_persist_config"):
        app._persist_config()

    hwnds = [h for h, _ in app._char_order]
    threading.Thread(
        target=reorder_with_ungroup_regroup,
        args=(
            hwnds,
            lambda m, t: QTimer.singleShot(0, lambda: app.log_msg(m, t)) if hasattr(app, "log_msg") else None,
        ),
        daemon=True,
    ).start()


def _toggle_move_mode(app):
    """Bascule le mode Déplacement (on ↔ off), en contournant la checkbox
    de permission via force=True."""
    app._toggle_move_mode(force=True)

def _set_all_autofocus(app, active: bool):
    """Active ou désactive TOUS les types d'AutoFocus, pour TOUS les
    personnages, en mémoire uniquement (aucun appel à _persist_config).
    Bascule aussi le moteur global (_running) en conséquence, pour que
    l'état soit visible immédiatement (boutons par type + démarrage/arrêt
    réel de la boucle d'écoute), sans jamais toucher au registre."""
    for key, var in app.type_vars.items():
        var.set(active)
        if hasattr(app, "_update_global_btn_style"):
            app._update_global_btn_style(key)

    if active and not app._running:
        app._start()
    elif not active and app._running:
        app._stop()

    if hasattr(app, "_rebuild_char_list"):
        app._rebuild_char_list()

def build_commands(app):
    commands = []

    # --- Afficher Dracoon (premier plan, tray ou non) ---
    commands.append({
        "id": "show_window",
        "label": t("spotlight.cmd.show_window"),
        "type": "action",
        "run": lambda: app._ensure_visible(),
        "keywords": ["dracoon", "afficher", "show", "fenetre", "premier plan"],
        "category": "navigation",
    })

    # --- Navigation vers les onglets ---
    # for key, ikey, keywords in [
    #     ("personnages", "spotlight.cmd.tab_personnages", ["perso", "personnages", "characters", "comptes"]),
    #     ("raccourcis",  "spotlight.cmd.tab_raccourcis",  ["raccourcis", "hotkeys", "touches"]),
    #     ("outils",      "spotlight.cmd.tab_outils",      ["outils", "tools", "modes"]),
    #     ("parametres",  "spotlight.cmd.tab_parametres",  ["parametres", "settings", "options"]),
    #     ("info",        "spotlight.cmd.tab_info",        ["info", "infos", "about", "a propos"]),
    # ]:
    #     commands.append({
    #         "id": f"nav_{key}",
    #         "label": t(ikey),
    #         "type": "navigate",
    #         "run": (lambda k=key: _navigate(app, k)),
    #         "keywords": keywords,
    #         "category": "navigation",
    #     })

    # --- Mode Déplacement : toggle, texte dynamique selon l'état courant ---
    commands.append({
        "id": "move_toggle",
        "label": t("spotlight.cmd.move_deactivate"),  # fallback recherche
        "label_fn": lambda: (
            t("spotlight.cmd.move_deactivate") if app._move_manager.is_active
            else t("spotlight.cmd.move_activate")
        ),
        "type": "action",
        "run": lambda: _toggle_move_mode(app),
        "get_state": lambda: app._move_manager.is_active,
        "keywords": ["deplacement", "move", "marche", "activer", "desactiver"],
        "category": "actions",
    })

    # --- Mode Dradidas : déclenche l'effet directement, contourne la checkbox ---
    commands.append({
        "id": "dradidas_activate",
        "label": t("spotlight.cmd.dradidas_activate"),
        "type": "action",
        "run": lambda: app._trigger_dradidas(force=True),
        "keywords": ["dradidas", "sylvestre", "sadida", "activer"],
        "category": "actions",
    })

    # --- Presets de team (une commande par preset existant) ---
    for preset_name in load_order_presets().keys():
        commands.append({
            "id": f"preset_{preset_name}",
            "label": f"{t('spotlight.cmd.preset_load')} : {preset_name}",
            "type": "action",
            "run": (lambda p=preset_name: _apply_preset(app, p)),
            "keywords": ["preset", "team", "ordre", preset_name.lower()],
            "category": "presets",
        })

    # --- Autofocus : toggle unique, texte dynamique selon l'état courant ---
    commands.append({
        "id": "autofocus_toggle",
        "label": t("spotlight.cmd.autofocus_off"),  # fallback (recherche uniquement, jamais affiché tel quel)
        "label_fn": lambda: (
            t("spotlight.cmd.autofocus_off") if app._running
            else t("spotlight.cmd.autofocus_on")
        ),
        "type": "action",
        "run": lambda: _set_all_autofocus(app, not app._running),
        "get_state": lambda: app._running,
        "keywords": ["autofocus", "focus", "activer", "desactiver", "toggle", "on", "off"],
        "category": "actions",
    })

    # --- Ctrl+Maj (maintien simulé) : toggle, texte dynamique selon l'état
    # courant. On appelle directement _toggle_ctrl_shift (celle du raccourci
    # clavier) plutôt que de dupliquer sa logique : ça fonctionne même sans
    # raccourci configuré pour ctrl_shift, puisqu'on ne passe jamais par
    # keyboard.add_hotkey. Le Spotlight se ferme avant l'exécution de "run"
    # (voir _select_index) : le focus est donc déjà revenu sur la fenêtre
    # Dofus précédente au moment de l'appel, donc la vérification interne
    # is_dofus_foreground() de _toggle_ctrl_shift passe normalement, et le
    # maintien cible bien cette fenêtre (comme avec le raccourci clavier).
    commands.append({
        "id": "ctrl_shift_toggle",
        "label": t("spotlight.cmd.ctrlshift_deactivate"),  # fallback recherche
        "label_fn": lambda: (
            t("spotlight.cmd.ctrlshift_deactivate") if app._ctrl_shift_manager.is_active
            else t("spotlight.cmd.ctrlshift_activate")
        ),
        "type": "action",
        "run": lambda: app._toggle_ctrl_shift(),
        "get_state": lambda: app._ctrl_shift_manager.is_active,
        "keywords": ["ctrl", "shift", "maj", "maintien", "activer", "desactiver"],
        "category": "actions",
    })

    # --- Personnage principal : focus direct sur app._char_main, réutilise
    # _focus_main du raccourci clavier — même raisonnement que ci-dessus
    # (focus déjà restauré sur Dofus avant l'appel). Ne fait rien si aucun
    # personnage principal n'a été choisi (comportement hérité, silencieux).
    commands.append({
        "id": "focus_main",
        "label": t("spotlight.cmd.focus_main"),
        "type": "action",
        "run": lambda: app._focus_main(),
        "keywords": ["principal", "main", "perso principal"],
        "category": "navigation",
    })

    # --- Retour direct : dernière fenêtre Dofus focus avant le switch en
    # cours (app._prev_hwnd), réutilise _focus_back du raccourci clavier —
    # retombe sur un cycle -1 si aucune fenêtre précédente valide (hérité).
    commands.append({
        "id": "focus_back",
        "label": t("spotlight.cmd.focus_back"),
        "type": "action",
        "run": lambda: app._focus_back(),
        "keywords": ["retour", "back", "precedent", "dernier"],
        "category": "navigation",
    })

    return commands