import asyncio
import ctypes
import ctypes.wintypes as wt
import json
import os
import re
import sys
import threading
import time
import tkinter as tk
import webbrowser
import winreg
from tkinter import scrolledtext
from datetime import datetime


# ══════════════════════════════════════════════════════════════════════════════
# 1. INFORMATIONS GÉNÉRALES
# ══════════════════════════════════════════════════════════════════════════════

APP_VERSION = "2.0.0"
APP_GITHUB  = "https://github.com/Slyss42/Dracoon"
APP_TWITTER = "https://x.com/Slyss42"
APP_LEGAL   = (
    "Dofus Retro est une marque déposée de Ankama et ce projet n'y est pas affilié. L'utilisation d'un logiciel tiers est tolérée uniquement s'il ne modifie pas les fichiers du jeu et n'interagit pas directement avec celui-ci, comme un simple outil de gestion de fenêtres. Ce logiciel est fourni à titre personnel, sans aucune garantie, et n'est pas officiellement pris en charge par Ankama. Par conséquent, son utilisation se fait sous l'entière responsabilité de l'utilisateur : Ankama ne peut garantir la sécurité de l'outil et toute violation éventuelle de données ou de logs reste à la charge du joueur. Enfin, il est important de noter que les outils de type macros ou automatisation restent strictement interdits.\n"
)


# ══════════════════════════════════════════════════════════════════════════════
# 2. BASES DU PROGRAMME
# ══════════════════════════════════════════════════════════════════════════════

# ─── Icône ────────────────────────────────────────────────────────────────────
import sys as _sys
if getattr(_sys, "frozen", False):
    ICON_PATH = os.path.join(_sys._MEIPASS, "icon.ico")
else:
    ICON_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico")



# ─── Dépendances optionnelles ─────────────────────────────────────────────────
try:
    import win32gui, win32con, win32api
    WIN32_OK = True
except Exception:
    WIN32_OK = False

try:
    import winsdk.windows.ui.notifications.management as winman
    import winsdk.windows.ui.notifications as winnot
    WINSDK_OK = True
except Exception:
    WINSDK_OK = False

try:
    import keyboard
    KEYBOARD_OK = True
except Exception:
    KEYBOARD_OK = False

try:
    import pystray
    from PIL import Image, ImageDraw
    TRAY_OK = True
except Exception:
    TRAY_OK = False


# ══════════════════════════════════════════════════════════════════════════════
# 3. TECHNIQUE — PAR ONGLET
# ══════════════════════════════════════════════════════════════════════════════

# ─── TECHNIQUE : Onglet Personnages : tri et réorganisation des fenêtres ────────────────
TITLE_PATTERN = re.compile(r"^(.+?)\s*-\s*Dofus", re.IGNORECASE)

class _GUID(ctypes.Structure):
    _fields_ = [("Data1", ctypes.c_ulong), ("Data2", ctypes.c_ushort),
                ("Data3", ctypes.c_ushort), ("Data4", ctypes.c_ubyte * 8)]

class _PROPERTYKEY(ctypes.Structure):
    _fields_ = [("fmtid", _GUID), ("pid", ctypes.c_ulong)]

class _PROPVARIANT(ctypes.Structure):
    _fields_ = [("vt",   ctypes.c_ushort), ("pad1", ctypes.c_ushort),
                ("pad2", ctypes.c_ushort), ("pad3", ctypes.c_ushort),
                ("ptr",  ctypes.c_void_p)]

VT_LPWSTR, VT_EMPTY = 31, 0
_DOFUS_GROUP_ID = "DofusRetro.SharedGroup"

_PKEY_AUMI = _PROPERTYKEY()
_PKEY_AUMI.fmtid.Data1 = 0x9F4C2855; _PKEY_AUMI.fmtid.Data2 = 0x9F79
_PKEY_AUMI.fmtid.Data3 = 0x4B39
for _i, _b in enumerate([0xA8,0xD0,0xE1,0xD4,0x2D,0xE1,0xD5,0xF3]):
    _PKEY_AUMI.fmtid.Data4[_i] = _b
_PKEY_AUMI.pid = 5

_IID_PS = _GUID()
_IID_PS.Data1 = 0x886D8EEB; _IID_PS.Data2 = 0x8CF2; _IID_PS.Data3 = 0x4446
for _i, _b in enumerate([0x8D,0x02,0xCD,0xBA,0x1D,0xBD,0xCF,0x99]):
    _IID_PS.Data4[_i] = _b

try:
    _shell32 = ctypes.windll.shell32
    _shell32.SHGetPropertyStoreForWindow.restype  = ctypes.HRESULT
    _shell32.SHGetPropertyStoreForWindow.argtypes = [
        wt.HWND, ctypes.POINTER(_GUID), ctypes.POINTER(ctypes.c_void_p)]
    UNGROUP_OK = True
except Exception:
    UNGROUP_OK = False



def set_window_app_id(hwnd: int, app_id: str | None) -> bool:
    if not UNGROUP_OK:
        return False
    pstore = ctypes.c_void_p()
    try:
        hr = _shell32.SHGetPropertyStoreForWindow(
            hwnd, ctypes.byref(_IID_PS), ctypes.byref(pstore))
        if hr != 0 or not pstore.value:
            return False
        vtbl = ctypes.cast(
            ctypes.cast(pstore.value, ctypes.POINTER(ctypes.c_void_p))[0],
            ctypes.POINTER(ctypes.c_void_p))

        Release  = ctypes.WINFUNCTYPE(ctypes.c_ulong,  ctypes.c_void_p)(vtbl[2])
        SetValue = ctypes.WINFUNCTYPE(ctypes.HRESULT,  ctypes.c_void_p,
                       ctypes.POINTER(_PROPERTYKEY), ctypes.POINTER(_PROPVARIANT))(vtbl[6])
        Commit   = ctypes.WINFUNCTYPE(ctypes.HRESULT,  ctypes.c_void_p)(vtbl[7])

        pv = _PROPVARIANT()
        if app_id:
            buf = ctypes.create_unicode_buffer(app_id)
            pv.vt = VT_LPWSTR
            pv.ptr = ctypes.cast(buf, ctypes.c_void_p).value
        else:
            pv.vt = VT_EMPTY

        hr = SetValue(pstore.value, ctypes.byref(_PKEY_AUMI), ctypes.byref(pv))
        if hr == 0:
            Commit(pstore.value)
        Release(pstore.value)
        return hr == 0
    except Exception:
        return False


def reorder_with_ungroup_regroup(hwnds: list[int], log_fn=None):
    # 1. Dégrouper
    for i, hwnd in enumerate(hwnds):
        ok = set_window_app_id(hwnd, f"DofusRetro.Char.{hwnd}")
        if log_fn:
            log_fn(f"  Ungroup hwnd={hwnd} → {'OK' if ok else 'ÉCHEC'}", "debug")
    time.sleep(0.3)
    # 2. Z-order silencieux
    SWP = 0x0010 | 0x0002 | 0x0001   # NOACTIVATE | NOMOVE | NOSIZE
    for i in range(len(hwnds) - 1):
        try:
            ctypes.windll.user32.SetWindowPos(hwnds[i], hwnds[i+1], 0, 0, 0, 0, SWP)
            time.sleep(0.05)
        except Exception:
            pass
    time.sleep(0.2)
    # 3. Regrouper
    for hwnd in hwnds:
        ok = set_window_app_id(hwnd, _DOFUS_GROUP_ID)
        if log_fn:
            log_fn(f"  Regroup hwnd={hwnd} → {'OK' if ok else 'ÉCHEC'}", "debug")
    if log_fn:
        log_fn("  Terminé.", "ok")


def extract_pseudo_from_title(title: str) -> str | None:
    m = TITLE_PATTERN.match(title)
    return m.group(1).strip() if m else None


def get_dofus_windows() -> list[tuple[int, str]]:
    result = []
    def cb(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            t = win32gui.GetWindowText(hwnd)
            p = extract_pseudo_from_title(t)
            if p:
                result.append((hwnd, p))
        return True
    win32gui.EnumWindows(cb, None)
    return result


def focus_window(hwnd: int) -> tuple[bool, str]:
    try:
        title = win32gui.GetWindowText(hwnd)
        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        # VK_MENU (Alt) est nécessaire pour forcer SetForegroundWindow depuis un autre process.
        # Le try/finally garantit que la touche est toujours relâchée, même en cas d'exception,
        # pour éviter qu'Alt reste "collé" au clavier.
        win32api.keybd_event(win32con.VK_MENU, 0, 0, 0)
        try:
            win32gui.SetForegroundWindow(hwnd)
            win32gui.BringWindowToTop(hwnd)
            # Laisser Windows finaliser le changement de focus avant de
            # relâcher Alt, sinon le focus peut revenir à la fenêtre d'origine.
            time.sleep(0.03)
        finally:
            win32api.keybd_event(win32con.VK_MENU, 0, win32con.KEYEVENTF_KEYUP, 0)
        return True, title
    except Exception as e:
        return False, str(e)


def list_dofus_windows() -> list[str]:
    result = []
    def cb(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            t = win32gui.GetWindowText(hwnd)
            if "dofus" in t.lower():
                result.append(t)
        return True
    win32gui.EnumWindows(cb, None)
    return result


def is_dofus_foreground() -> bool:
    """Retourne True si la fenêtre active est une fenêtre Dofus Rétro."""
    if not WIN32_OK:
        return False
    try:
        hwnd = win32gui.GetForegroundWindow()
        title = win32gui.GetWindowText(hwnd)
        return bool(TITLE_PATTERN.match(title))
    except Exception:
        return False


def _release_modifier_keys():
    """Force le relâchement de Ctrl et Alt pour éviter les touches collées à la fermeture."""
    if not WIN32_OK:
        return
    for vk in (win32con.VK_MENU, win32con.VK_CONTROL,
               win32con.VK_LMENU, win32con.VK_RMENU,
               win32con.VK_LCONTROL, win32con.VK_RCONTROL):
        try:
            win32api.keybd_event(vk, 0, win32con.KEYEVENTF_KEYUP, 0)
        except Exception:
            pass


# ─── TECHNIQUE : Onglet Raccourcis : sauvegarde des touches dans le registre ──────────────

_REG_PATH = r"Software\DofusRetro"


def _load_config() -> dict:
    result = {}
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REG_PATH)
        with key:
            i = 0
            while True:
                try:
                    name, value, _ = winreg.EnumValue(key, i)
                    result[name] = value if value != "" else None
                    i += 1
                except OSError:
                    break
    except FileNotFoundError:
        pass
    return result


def _save_config(data: dict):
    try:
        key = winreg.CreateKeyEx(
            winreg.HKEY_CURRENT_USER, _REG_PATH,
            access=winreg.KEY_WRITE)
        with key:
            for name, value in data.items():
                winreg.SetValueEx(key, name, 0, winreg.REG_SZ,
                                  "" if value is None else str(value))
    except Exception:
        pass


def _unhook_all():
    """Retire tous les hotkeys keyboard proprement."""
    if not KEYBOARD_OK:
        return
    for attr in ("unhook_all_hotkeys", "remove_all_hotkeys", "clear_all_hotkeys"):
        if hasattr(keyboard, attr):
            try:
                getattr(keyboard, attr)()
                return
            except Exception:
                pass
    try:
        keyboard.unhook_all()
    except Exception:
        pass


def _build_config(shortcut_next, shortcut_prev, shortcut_back,
                  char_af_overrides: dict | None = None,
                  shortcut_main=None, char_main=None,
                  welcome_shown: bool = False,
                  char_skip_names: set | None = None) -> dict:
    """Construit le dictionnaire de configuration à persister dans le registre."""
    return {
        "shortcut_next":     shortcut_next,
        "shortcut_prev":     shortcut_prev,
        "shortcut_back":     shortcut_back,
        "shortcut_main":     shortcut_main,
        "char_main":         char_main if char_main is not None else "",
        "char_af_overrides": _encode_af_overrides(char_af_overrides or {}),
        "welcome_shown":     "1" if welcome_shown else "0",
        "char_skip_names":   json.dumps(sorted(char_skip_names), ensure_ascii=False)
                             if char_skip_names else "[]",
    }

# ─── TECHNIQUE : Onglet Autofocus : (Notifications)                  ──────────────
POLL_INTERVAL = 0.1

# ══════════════════════════════════════════════════════════════════════════════
# PATTERNS DE NOTIFICATIONS
# ══════════════════════════════════════════════════════════════════════════════
# Structure : (clé, [pattern_1, pattern_2, ...], emoji)
#
# Chaque entrée regroupe TOUS les patterns d'une même action (toutes langues).
# Pour qu'une notification corresponde à un type, il suffit qu'AU MOINS UN
# des patterns de la liste matche le corps de la notification.
#
# ── Comment ajouter une langue (ex. anglais) ───────────────────────────────
# Il suffit d'ajouter le pattern anglais dans la liste du type concerné.
# Les lignes EN sont déjà présentes en commentaire ci-dessous — il suffit
# de les décommenter et d'y saisir le texte exact de la notification anglaise.
# ══════════════════════════════════════════════════════════════════════════════

NOTIF_TYPES = [
    # ── Combat : invitation à jouer (tour par tour) ──────────────────────────
    ("combat", [
        re.compile(r"de jouer",                             re.IGNORECASE),  # FR
        re.compile(r"turn to play",                         re.IGNORECASE),  # EN
        re.compile(r"Le toca jugar a",                      re.IGNORECASE),  # ES
    ], "⚔️"),

    # ── Échange : proposition d'échange ──────────────────────────────────────
    ("echange", [
        re.compile(r"te propose de faire un échange",       re.IGNORECASE),  # FR
        re.compile(r"offers a trade",                       re.IGNORECASE),  # EN
        re.compile(r"te propone realizar un intercambio",   re.IGNORECASE),  # ES
    ], "🔄"),

    # ── Groupe : invitation à rejoindre un groupe ou une guilde ──────────────
    ("groupe", [
        re.compile(r"t['']invite .+rejoindre son groupe",  re.IGNORECASE),  # FR groupe
        re.compile(r"t['']invite .+rejoindre sa guilde",   re.IGNORECASE),  # FR guilde
        re.compile(r"You are invited to join .+'s group",   re.IGNORECASE),  # EN groupe
        re.compile(r"invites you to join the .+guild",   re.IGNORECASE),  # EN groupe
        re.compile(r"te invita a unirte a su grupo",   re.IGNORECASE),  # ES groupe
        re.compile(r"te invita a unirte a su gremio",   re.IGNORECASE),  # ES groupe
    ], "👥"),

    # ── MP : message privé ────────────────────────────────────────────────────
    ("mp", [
        re.compile(r"^de ",                                 re.IGNORECASE),  # FR
        re.compile(r"^from ",                               re.IGNORECASE),  # FR
        re.compile(r"^desde ",                               re.IGNORECASE),  # FR
    ], "💬"),

    # ── Défi : invitation à un duel ───────────────────────────────────────────
    ("defi", [
        re.compile(r"te défie",                             re.IGNORECASE),  # FR
        re.compile(r"challenges you",                       re.IGNORECASE),  # EN
        re.compile(r"te desafía",                           re.IGNORECASE),  # ES
    ], "🏆"),

    # ── Craft : atelier / artisan / fabrication terminée ─────────────────────
    ("craft", [
        re.compile(r"fait appel à tes talents d.artisan",   re.IGNORECASE),  # FR artisan
        re.compile(r"rejoindre son atelier",                re.IGNORECASE),  # FR atelier
        re.compile(r"tous les objets ont été fabriqués",    re.IGNORECASE),  # FR fabrication

        re.compile(r"is crying out for your skills",            re.IGNORECASE), # EN artisan
        re.compile(r"You are invited to join .+'s workshop",   re.IGNORECASE),  # EN groupe
        re.compile(r"All items have been created!",             re.IGNORECASE),  # EN fabrication

        re.compile(r"solicita tus talentos de artesano",        re.IGNORECASE), # ES artisan
        re.compile(r"te invita a pasarte por su taller",        re.IGNORECASE),  # ES atelier
        re.compile(r"¡Todos los objetos han sido fabricados!",  re.IGNORECASE),  # ES fabrication
    ], "🔨"),

    # ── PVP : percepteur attaqué ──────────────────────────────────────────────
    ("pvp", [
        re.compile(r"percepteur.+est attaqué en",             re.IGNORECASE),  # FR
        re.compile(r"The perceptor .+is attacked in",         re.IGNORECASE),  # EN
        re.compile(r"El recaudador .+está siendo atacado en", re.IGNORECASE),  # ES
    ], "🛡️"),
]

def focus_dofus_window(pseudo: str) -> tuple[bool, str]:
    found = []
    def cb(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return True
        t = win32gui.GetWindowText(hwnd)
        if re.match(rf"^{re.escape(pseudo)}\s*-\s*Dofus", t, re.IGNORECASE):
            found.append((hwnd, t))
        return True
    win32gui.EnumWindows(cb, None)
    if not found:
        return False, f"Aucune fenêtre « {pseudo} - Dofus… » trouvée"
    return focus_window(found[0][0])


def _encode_af_overrides(overrides: dict) -> str:
    """Sérialise les surcharges autofocus par personnage → JSON (stockage registre)."""
    return json.dumps(overrides, ensure_ascii=False)


def _decode_af_overrides(raw: str) -> dict:
    """Désérialise les surcharges autofocus depuis le registre.
    Retourne {} si absent ou invalide → chemin rapide garanti au démarrage.
    """
    try:
        return json.loads(raw) if raw else {}
    except Exception:
        return {}



# ══════════════════════════════════════════════════════════════════════════════
# 4. UI
# ══════════════════════════════════════════════════════════════════════════════

# ─── Styles de texte ──────────────────────────────────────────────────────────
class UIStyles:
    class Titre:
        font      = ("Segoe UI", 14, "bold")
        padx      = 16

    class OngletActif:
        font      = ("Segoe UI", 11, "bold")

    class Bouton:
        font_standard   = ("Segoe UI", 11)
        padx_standard   = 18
        pady_standard   = 9

        font_principal  = ("Segoe UI", 11, "bold")
        padx_principal  = 16
        pady_principal  = 7

        font_type_notif = ("Segoe UI", 11, "bold")
        padx_type_notif = 10
        pady_type_notif = 4

        font_type_notifnobold = ("Segoe UI", 11)
        padx_type_notifnobold = 10
        pady_type_notifnobold = 4

        font_petit      = ("Segoe UI", 11)
        padx_petit      = 12
        pady_petit      = 5

    class EnTete:
        font           = ("Segoe UI", 12, "bold")
        pady_titre     = (14, 2)   # (haut, bas) du titre
        pady_sous      = (0, 10)   # (haut, bas) du sous-titre

    class Info:
        font = ("Segoe UI", 11)


# ─── Application principale ───────────────────────────────────────────────────
class App(tk.Tk):
    # Couleurs
    BG        = "#0f1117"
    PANEL     = "#181c26"
    CARD      = "#1a1f2e"
    ACCENT    = "#f5a623"
    GREEN     = "#4caf78"
    RED       = "#e05252"
    BLUE      = "#4a90d9"
    GRAY      = "#6b7280"
    TEXT      = "#e8e8e8"
    FONT_MONO = ("Consolas", 10)
    FONT_UI   = ("Segoe UI", 10)

    # Référence aux styles de texte
    S         = UIStyles

    TYPE_COLORS = {
        "combat":  "#e05252",
        "echange": "#f5a623",
        "groupe":  "#4caf78",
        "mp":      "#4a90d9",
        "defi":    "#c97bdb",
        "craft":   "#e8a040",
        "pvp":     "#e05252",
    }

    # Valeur sentinelle pour "aucun raccourci"
    NO_SHORTCUT = None

    def __init__(self):
        super().__init__()
        self.title("Dracoon - Gestionnaire de fenêtres Dofus Rétro")
        self.configure(bg=self.BG)
        self.resizable(True, True)
        self.geometry("740x810")
        self.minsize(500, 460)

        # Charger la config
        cfg = _load_config()

        self._running       = False
        self._loop          = None
        self._n_notifs      = 0
        self._n_matches     = 0
        self._n_focus       = 0
        self._char_order: list[tuple[int, str]] = []
        self._drag_idx      = None
        self._row_tops: list[int] = []
        self._row_height    = 48
        self._tray_icon     = None
        self._tray_thread   = None

        # Raccourcis chargés depuis le registre
        raw_next = cfg.get("shortcut_next", "ctrl+right")
        raw_prev = cfg.get("shortcut_prev", "ctrl+left")
        raw_back = cfg.get("shortcut_back", None)
        raw_main = cfg.get("shortcut_main", None)
        self._shortcut_next: str | None = raw_next
        self._shortcut_prev: str | None = raw_prev
        self._shortcut_back: str | None = raw_back
        self._shortcut_main: str | None = raw_main

        # Personnage principal — un seul possible, persisté dans le registre.
        # La touche de raccourci "main" le focus directement, même s'il est exclu du roulement.
        _raw_main = cfg.get("char_main", "") or None
        self._char_main: str | None = _raw_main

        # Surcharges autofocus par personnage — chargées depuis le registre.
        # Vide = aucune surcharge → chemin rapide dans _listen() (pas de lookup par perso).
        # Structure : pseudo → {"combat": bool, "echange": bool, "groupe": bool,
        #                        "mp": bool, "defi": bool, "craft": bool, "pvp": bool}
        self._char_af_overrides: dict[str, dict[str, bool]] = _decode_af_overrides(
            cfg.get("char_af_overrides", "")
        )

        # Fenêtre précédente (pour le raccourci "retour direct")
        self._prev_hwnd: int | None = None

        # Pseudos exclus du roulement next/prev — persisté dans le registre.
        _raw_skip = cfg.get("char_skip_names", "[]") or "[]"
        try:
            self._char_skip_names: set[str] = set(json.loads(_raw_skip))
        except Exception:
            self._char_skip_names: set[str] = set()

        # Popup de bienvenue — affichée une seule fois, sauf si l'utilisateur la réactive
        self._welcome_shown: bool = cfg.get("welcome_shown", "0") == "1"

        self._build_ui()

        # Icône de la fenêtre (barre de titre + barre des tâches)
        try:
            _ico = tk.PhotoImage(file=ICON_PATH)
            self.iconphoto(True, _ico)
            self._app_icon = _ico
        except Exception:
            pass

        if not WIN32_OK:
            self.log_msg("pywin32 manquant → pip install pywin32", "error")
        if not WINSDK_OK:
            self.log_msg("winsdk manquant → pip install winsdk", "error")
        if not KEYBOARD_OK:
            self.log_msg("keyboard non chargé → pip install keyboard", "warn")
        if not TRAY_OK:
            self.log_msg("pystray/pillow manquants → pip install pystray pillow", "warn")
        if WIN32_OK and WINSDK_OK:
            self.log_msg("Prêt — AutoFocus démarré automatiquement.", "ok")
            self._start()

        # Quitter proprement : fermer = quitter (pas de tray ici)
        self.protocol("WM_DELETE_WINDOW", self._quit)

        # Raccourcis drag globaux (survivent aux rebuilds)
        self.bind("<B1-Motion>",       self._drag_motion)
        self.bind("<ButtonRelease-1>", self._drag_end)

        # Appliquer les raccourcis sauvegardés
        if KEYBOARD_OK:
            self._apply_shortcuts(silent=True)

        self.refresh_characters()

        # Afficher la popup de bienvenue si pas encore vue
        if not self._welcome_shown:
            self.after(200, self._show_welcome_popup)

    # ══════════════════════════════════════════════════════════════════════
    # QUIT PROPRE
    # ══════════════════════════════════════════════════════════════════════

    def _quit(self):
        """Fermeture totale du script."""
        # Sauvegarder config
        self._persist_config()
        # Retirer les hotkeys et forcer le relâchement des modificateurs (évite Ctrl/Alt collés)
        _unhook_all()
        _release_modifier_keys()
        # Arrêter la boucle async
        self._running = False
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
        # Arrêter le tray
        if self._tray_icon:
            try:
                self._tray_icon.stop()
            except Exception:
                pass
        self.destroy()
        os._exit(0)   # force la terminaison même si des threads traînent

    # ══════════════════════════════════════════════════════════════════════
    # POPUP DE BIENVENUE
    # ══════════════════════════════════════════════════════════════════════

    def _show_welcome_popup(self):
        """Affiche la fenêtre de bienvenue et d'avertissement de sécurité.
        Modale : bloque l'interaction avec la fenêtre principale jusqu'à fermeture.
        Le bouton de fermeture est verrouillé 30 secondes pour s'assurer que le message est lu.
        La case 'Ne plus afficher' persiste dans le registre via _persist_config.
        """
        TIMER_SECONDS = 30   # durée de verrouillage du bouton

        popup = tk.Toplevel(self)
        popup.title("Bienvenue dans Dracoon")
        popup.configure(bg=self.BG)
        popup.resizable(False, False)
        popup.grab_set()   # modale
        popup.focus_force()

        # ── Centrer sur la fenêtre principale ─────────────────────────────
        self.update_idletasks()
        pw, ph = 580, 560
        rx = self.winfo_rootx() + (self.winfo_width()  - pw) // 2
        ry = self.winfo_rooty() + (self.winfo_height() - ph) // 2
        popup.geometry(f"{pw}x{ph}+{rx}+{ry}")

        # Polices internes à la popup (légèrement plus grandes que les styles globaux)
        FONT_TITRE   = ("Segoe UI", 14, "bold")
        FONT_SECTION = ("Segoe UI", 12, "bold")
        FONT_BODY    = ("Segoe UI", 11)
        FONT_BTN     = ("Segoe UI", 12, "bold")
        WRAPLENGTH   = 500

        pad = tk.Frame(popup, bg=self.BG, padx=28, pady=22)
        pad.pack(fill="both", expand=True)

        # ── Titre ─────────────────────────────────────────────────────────
        tk.Label(pad, text="Bienvenue dans Dracoon",
                 bg=self.BG, fg=self.ACCENT,
                 font=FONT_TITRE).pack(anchor="w", pady=(0, 16))

        # ── Bloc liens officiels ──────────────────────────────────────────
        card_links = tk.Frame(pad, bg=self.CARD, padx=18, pady=14)
        card_links.pack(fill="x", pady=(0, 10))

        tk.Label(card_links,
                 text="Il n'existe aucun site internet lié à Dracoon.",
                 bg=self.CARD, fg=self.TEXT,
                 font=FONT_BODY,
                 justify="left", wraplength=WRAPLENGTH).pack(anchor="w", pady=(0, 10))

        tk.Label(card_links, text="Seuls liens officiels :",
                 bg=self.CARD, fg=self.GRAY,
                 font=FONT_BODY).pack(anchor="w")

        def _link(parent, icon: str, url: str):
            row = tk.Frame(parent, bg=self.CARD)
            row.pack(anchor="w", pady=3)
            tk.Label(row, text=icon, bg=self.CARD,
                     fg=self.GRAY, font=FONT_BODY).pack(side="left", padx=(0, 8))
            lbl = tk.Label(row, text=url, bg=self.CARD,
                           fg=self.BLUE, font=FONT_BODY,
                           cursor="hand2")
            lbl.pack(side="left")
            lbl.bind("<Button-1>", lambda e, u=url: webbrowser.open(u))
            lbl.bind("<Enter>",    lambda e: lbl.config(fg=self.ACCENT))
            lbl.bind("<Leave>",    lambda e: lbl.config(fg=self.BLUE))

        _link(card_links, "⌨", APP_GITHUB)
        _link(card_links, "🐦", APP_TWITTER)

        # ── Bloc avertissement malware ────────────────────────────────────
        card_warn = tk.Frame(pad, bg="#2a1a1a", padx=18, pady=14)
        card_warn.pack(fill="x", pady=(0, 16))

        tk.Label(card_warn, text="⚠  Avertissement de sécurité",
                 bg="#2a1a1a", fg=self.RED,
                 font=FONT_SECTION).pack(anchor="w", pady=(0, 10))

        tk.Label(card_warn,
                 text=(
                     "Si vous n'avez pas téléchargé ce programme depuis les deux liens "
                     "ci-dessus, ou si vous avez obtenu votre lien depuis un site internet, "
                     "vous avez probablement téléchargé un malware.\n\n"
                     "Changez immédiatement l'ensemble de vos mots de passe "
                     "ainsi que vos données sensibles."
                 ),
                 bg="#2a1a1a", fg=self.TEXT,
                 font=FONT_BODY,
                 justify="left", wraplength=WRAPLENGTH).pack(anchor="w")

        # ── Bouton "J'ai compris" (verrouillé TIMER_SECONDS secondes) ─────
        dont_show_var = tk.BooleanVar(value=False)

        def _close():
            if dont_show_var.get():
                self._welcome_shown = True
                self._persist_config()
            popup.destroy()

        close_btn = tk.Button(pad, text=f"J'ai compris ({TIMER_SECONDS})",
                              bg=self.GRAY, fg=self.BG,
                              relief="flat", cursor="arrow",
                              font=FONT_BTN,
                              padx=self.S.Bouton.padx_principal,
                              pady=self.S.Bouton.pady_principal,
                              activebackground=self.GRAY, activeforeground=self.BG,
                              state="disabled",
                              disabledforeground=self.PANEL)
        close_btn.pack(fill="x", pady=(0, 6))

        # ── Case "Ne plus afficher" ────────────────────────────────────────
        tk.Checkbutton(pad, text="Ne plus afficher ce message",
                       variable=dont_show_var,
                       bg=self.BG, fg=self.GRAY,
                       selectcolor=self.CARD,
                       activebackground=self.BG, activeforeground=self.TEXT,
                       font=FONT_BODY).pack(anchor="w")

        # ── Décompte : met à jour le bouton chaque seconde ─────────────────
        def _countdown(remaining: int):
            if remaining > 0:
                close_btn.config(text=f"J'ai compris ({remaining})")
                popup.after(1000, _countdown, remaining - 1)
            else:
                close_btn.config(
                    text="J'ai compris",
                    bg=self.ACCENT, fg=self.BG,
                    activebackground=self.ACCENT, activeforeground=self.BG,
                    cursor="hand2", state="normal",
                    command=_close,
                )

        popup.after(1000, _countdown, TIMER_SECONDS - 1)

        # La croix de fermeture ne fait rien tant que le bouton est verrouillé
        def _on_close_attempt():
            if close_btn["state"] == "normal":
                _close()

        popup.protocol("WM_DELETE_WINDOW", _on_close_attempt)

    def _make_tray_image(self):
        try:
            img = Image.open(ICON_PATH).convert("RGBA").resize((64, 64), Image.LANCZOS)
            return img
        except Exception:
            pass
        size = 64
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        d   = ImageDraw.Draw(img)
        d.ellipse([2, 2, size-2, size-2], fill=self.ACCENT)
        d.ellipse([8, 8, size-8, size-8], fill="#0f1117")
        d.text((16, 18), "DR", fill=self.ACCENT)
        return img

    def _on_header_close(self):
        """Le bouton ⊟ de l'en-tête minimise dans le tray si dispo, sinon quitte."""
        if TRAY_OK:
            self._minimize_to_tray()
        else:
            self._quit()

    def _minimize_to_tray(self):
        if self._tray_thread and self._tray_thread.is_alive():
            self.withdraw()
            return
        self.withdraw()
        menu = pystray.Menu(
            pystray.MenuItem("Afficher", self._tray_show, default=True),
            pystray.MenuItem("Quitter",  self._tray_quit),
        )
        self._tray_icon = pystray.Icon(
            "Dracoon", self._make_tray_image(), "Dracoon", menu)
        self._tray_thread = threading.Thread(target=self._tray_icon.run, daemon=True)
        self._tray_thread.start()

    def _tray_show(self, icon=None, item=None):
        if self._tray_icon:
            self._tray_icon.stop()
            self._tray_icon = None
        self.after(0, self.deiconify)
        self.after(50, self.lift)

    def _tray_quit(self, icon=None, item=None):
        if self._tray_icon:
            self._tray_icon.stop()
            self._tray_icon = None
        self.after(0, self._quit)

    # ══════════════════════════════════════════════════════════════════════
    # UI PRINCIPALE
    # ══════════════════════════════════════════════════════════════════════

    def _build_ui(self):
        header = tk.Frame(self, bg=self.PANEL, pady=10)
        header.pack(fill="x")

        # ── Logo à gauche du titre ────────────────────────────────────────
        try:
            from PIL import Image as _PilImg, ImageTk as _PilImgTk
            _raw = _PilImg.open(ICON_PATH).convert("RGBA").resize((32, 32), _PilImg.LANCZOS)
            self._header_icon = _PilImgTk.PhotoImage(_raw)
            tk.Label(header, image=self._header_icon,
                     bg=self.PANEL).pack(side="left", padx=(16, 4))
        except Exception:
            pass   # icon.png absent → rien à gauche

        tk.Label(header, text="DRACOON", bg=self.PANEL,
                 fg=self.ACCENT,
                 font=self.S.Titre.font).pack(side="left", padx=(0, self.S.Titre.padx))

        tk.Button(header, text="⊟", bg=self.PANEL, fg=self.ACCENT,
                  font=("Segoe UI", 18, "bold"), relief="flat", cursor="hand2",
                  activebackground=self.CARD, activeforeground=self.ACCENT,
                  command=self._on_header_close).pack(side="right", padx=(4, 14))

        tab_bar = tk.Frame(self, bg=self.PANEL)
        tab_bar.pack(fill="x")

        self._tab_btns:   dict[str, tk.Button] = {}
        self._tab_frames: dict[str, tk.Frame]  = {}

        for key, label in [("personnages", "Personnages"),
                            ("raccourcis",  "Raccourcis"),
                            ("autofocus",   "AutoFocus"),
                            ("info",        "Info")]:
            btn = tk.Button(tab_bar, text=label,
                            bg=self.PANEL, fg=self.GRAY,
                            font=self.S.Bouton.font_standard, relief="flat", cursor="hand2",
                            padx=self.S.Bouton.padx_standard, pady=self.S.Bouton.pady_standard,
                            activebackground=self.BG, activeforeground=self.ACCENT,
                            command=lambda k=key: self._switch_tab(k))
            btn.pack(side="left")
            self._tab_btns[key] = btn

        self._content = tk.Frame(self, bg=self.BG)
        self._content.pack(fill="both", expand=True)

        self._build_tab_personnages()
        self._build_tab_raccourcis()
        self._build_tab_autofocus()
        self._build_tab_info()
        self._switch_tab("personnages")

    def _switch_tab(self, key: str):
        for k, f in self._tab_frames.items():
            f.place_forget()
        for k, btn in self._tab_btns.items():
            active = k == key
            btn.config(
                fg=self.ACCENT if active else self.GRAY,
                bg=self.BG     if active else self.PANEL,
                font=self.S.OngletActif.font if active else self.S.Bouton.font_standard,
            )
        self._tab_frames[key].place(relx=0, rely=0, relwidth=1, relheight=1)

    # ══════════════════════════════════════════════════════════════════════
    # ONGLET PERSONNAGES
    # ══════════════════════════════════════════════════════════════════════

    def _build_tab_personnages(self):
        f = tk.Frame(self._content, bg=self.BG)
        self._tab_frames["personnages"] = f

        # ── En-tête
        top = tk.Frame(f, bg=self.BG, pady=12)
        top.pack(side="top", fill="x", padx=16)

        left = tk.Frame(top, bg=self.BG)
        left.pack(side="left", fill="x", expand=True)
        tk.Label(left, text="Ordre d'initiative", bg=self.BG,
                 fg=self.TEXT, font=self.S.EnTete.font).pack(anchor="w")
        tk.Label(left, text="Drag & drop pour réordonner", bg=self.BG,
                 fg=self.GRAY, font=self.S.Info.font).pack(anchor="w")

        tk.Button(top, text="↻  Actualiser", bg=self.PANEL, fg=self.TEXT,
                  relief="flat", cursor="hand2",
                  font=self.S.Bouton.font_petit,
                  padx=self.S.Bouton.padx_petit, pady=self.S.Bouton.pady_petit,
                  command=self.refresh_characters).pack(side="right")

        # ── Pied de page — packés AVANT le canvas pour toujours être visible
        bottom = tk.Frame(f, bg=self.BG, pady=8)
        bottom.pack(side="bottom", fill="x", padx=16)

        tk.Button(bottom, text="Enregistrer l'ordre",
                  bg=self.ACCENT, fg=self.BG,
                  relief="flat", cursor="hand2",
                  font=self.S.Bouton.font_principal,
                  padx=self.S.Bouton.padx_principal, pady=self.S.Bouton.pady_principal,
                  command=self._save_order).pack(side="right")

        tk.Label(bottom, text="Dégrouper → réordonner → regrouper",
                 bg=self.BG, fg=self.GRAY, font=self.S.Info.font).pack(side="left")

        # ── Liste scrollable (prend l'espace restant)
        cf = tk.Frame(f, bg=self.BG)
        cf.pack(side="top", fill="both", expand=True, padx=16)

        self._char_canvas = tk.Canvas(cf, bg=self.BG, highlightthickness=0)
        sb = tk.Scrollbar(cf, orient="vertical", command=self._char_canvas.yview)
        self._char_canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self._char_canvas.pack(side="left", fill="both", expand=True)

        self._char_inner = tk.Frame(self._char_canvas, bg=self.BG)
        self._char_win   = self._char_canvas.create_window(
            (0, 0), window=self._char_inner, anchor="nw")

        self._char_inner.bind("<Configure>",
            lambda e: self._char_canvas.configure(
                scrollregion=self._char_canvas.bbox("all")))
        self._char_canvas.bind("<Configure>",
            lambda e: self._char_canvas.itemconfig(self._char_win, width=e.width))
        self._char_canvas.bind("<MouseWheel>",
            lambda e: self._char_canvas.yview_scroll(-1*(e.delta//120), "units"))

    def refresh_characters(self):
        if not WIN32_OK:
            return
        windows   = get_dofus_windows()
        win_map   = {h: p for h, p in windows}   # hwnd → pseudo actuel
        known     = set(win_map.keys())
        # Conserver l'ordre existant ET mettre à jour le pseudo si le titre a changé
        new_order = [(h, win_map[h]) for h, _ in self._char_order if h in known]
        existing  = {h for h, _ in new_order}
        for h, p in windows:
            if h not in existing:
                new_order.append((h, p))
        self._char_order = new_order
        self._rebuild_char_list()
        # Mettre à jour la liste per-personnage dans l'onglet AutoFocus
        if hasattr(self, "_af_chars_container"):
            self._rebuild_af_char_list()

    def _rebuild_char_list(self, highlight_idx: int | None = None):
        for w in self._char_inner.winfo_children():
            w.destroy()
        self._row_tops = []

        if not self._char_order:
            tk.Label(self._char_inner,
                     text="Aucune fenêtre Dofus Rétro détectée",
                     bg=self.BG, fg=self.GRAY,
                     font=("Segoe UI", 10)).pack(pady=30)
            return

        for i, (hwnd, pseudo) in enumerate(self._char_order):
            self._create_char_row(i, hwnd, pseudo, i == highlight_idx)

        # Mettre à jour les positions après rendu
        self.after(10, self._update_row_tops)

    def _update_row_tops(self):
        """Mémorise les tops des rows en coordonnées canvas pour le drag."""
        self._row_tops = []
        for w in self._char_inner.winfo_children():
            if w.winfo_exists() and w.winfo_height() > 1:
                self._row_tops.append(w.winfo_y())
                self._row_height = w.winfo_height() + 6   # height + pady
        if self._row_tops:
            pass   # OK

    def _create_char_row(self, idx: int, hwnd: int, pseudo: str, hl: bool = False):
        bg = "#2a3350" if hl else self.CARD

        row = tk.Frame(self._char_inner, bg=bg, pady=10, padx=14,
                       highlightthickness=2 if hl else 0,
                       highlightbackground=self.ACCENT,
                       cursor="fleur")
        row.pack(fill="x", pady=3)

        tk.Label(row, text="⠿", bg=bg,
                 fg=self.ACCENT if hl else self.GRAY,
                 font=("Segoe UI", 15), cursor="fleur").pack(side="left", padx=(0, 8))

        tk.Label(row, text=str(idx + 1), bg=bg,
                 fg=self.GRAY, font=("Segoe UI", 10), width=2).pack(side="left", padx=(0, 6))

        tk.Label(row, text=pseudo, bg=bg,
                 fg=self.ACCENT if hl else self.TEXT,
                 font=("Segoe UI", 11, "bold")).pack(side="left")

        tk.Label(row, text="●", bg=bg, fg=self.GREEN,
                 font=("Segoe UI", 9)).pack(side="left", padx=6)

        # ── Pill "Exclure des raccourcis" (UI pure — logique dans _toggle_char_skip) ──
        skip_btn = tk.Button(
            row, relief="flat", cursor="hand2",
            font=self.S.Bouton.font_petit,
            padx=self.S.Bouton.padx_petit, pady=self.S.Bouton.pady_petit,
        )
        self._style_skip_btn(skip_btn, active=(pseudo in self._char_skip_names))
        skip_btn.config(command=lambda b=skip_btn, p=pseudo: self._toggle_char_skip(p, b))
        skip_btn.pack(side="right", padx=(0, 4))

        # ── Étoile "Personnage principal" — à droite du bouton d'exclusion ──
        main_btn = tk.Button(
            row, relief="flat", cursor="hand2",
            font=self.S.Bouton.font_petit,
            padx=self.S.Bouton.padx_petit, pady=self.S.Bouton.pady_petit,
        )
        self._style_main_btn(main_btn, active=(pseudo == self._char_main))
        main_btn.config(command=lambda b=main_btn, p=pseudo: self._toggle_char_main(p, b))
        main_btn.pack(side="right", padx=(0, 2))

        # Bind du début de drag sur la row et ses enfants (sauf les deux pills)
        drag_targets = [row] + [w for w in row.winfo_children()
                                if w is not skip_btn and w is not main_btn]
        for w in drag_targets:
            w.bind("<ButtonPress-1>", lambda e, i=idx: self._drag_start(i, e))

    def _drag_start(self, idx: int, event):
        self._drag_idx = idx
        # S'assurer que les tops sont à jour
        if not self._row_tops:
            self._update_row_tops()
        self._rebuild_char_list(highlight_idx=idx)

    def _drag_motion(self, event):
        """Bindé sur self (root) — survit aux rebuilds."""
        if self._drag_idx is None or not self._row_tops:
            return

        # Convertir y écran → y dans le frame interne
        try:
            inner_y = (event.y_root
                       - self._char_inner.winfo_rooty()
                       + self._char_canvas.canvasy(0))
        except Exception:
            return

        # Trouver l'index cible à partir des tops mémorisés
        target = self._drag_idx
        for i, top in enumerate(self._row_tops):
            bot = self._row_tops[i+1] if i+1 < len(self._row_tops) else top + self._row_height
            if top <= inner_y < bot:
                target = i
                break

        if target != self._drag_idx:
            self._char_order[self._drag_idx], self._char_order[target] = \
                self._char_order[target], self._char_order[self._drag_idx]
            self._drag_idx = target
            self._rebuild_char_list(highlight_idx=target)

    def _drag_end(self, event):
        if self._drag_idx is not None:
            self._drag_idx = None
            self._rebuild_char_list()

    def _save_order(self):
        if not self._char_order:
            return
        order = " → ".join(p for _, p in self._char_order)
        self.log_msg(f"Ordre : {order}", "ok")
        hwnds = [h for h, _ in self._char_order]
        threading.Thread(
            target=reorder_with_ungroup_regroup,
            args=(hwnds, lambda m, t: self.after(0, self.log_msg, m, t)),
            daemon=True
        ).start()
        # Mettre à jour l'ordre dans l'onglet AutoFocus
        if hasattr(self, "_af_chars_container"):
            self._rebuild_af_char_list()

    # ══════════════════════════════════════════════════════════════════════
    # ONGLET RACCOURCIS
    # ══════════════════════════════════════════════════════════════════════

    def _build_tab_raccourcis(self):
        f = tk.Frame(self._content, bg=self.BG)
        self._tab_frames["raccourcis"] = f

        tk.Label(f, text="Raccourcis clavier", bg=self.BG,
                 fg=self.TEXT, font=self.S.EnTete.font).pack(
                     anchor="w", padx=16, pady=self.S.EnTete.pady_titre)
        tk.Label(f, text="Agit uniquement sur les fenêtres Dofus Rétro · sauvegardé automatiquement",
                 bg=self.BG, fg=self.GRAY, font=self.S.Info.font).pack(
                     anchor="w", padx=16, pady=self.S.EnTete.pady_sous)

        self._next_entry = self._shortcut_row(
            f, "▶  Fenêtre suivante",
            "Passe au personnage suivant (exclut les fenêtres marquées)",
            self._shortcut_next, "next")

        self._prev_entry = self._shortcut_row(
            f, "◀  Fenêtre précédente",
            "Revient au personnage précédent (exclut les fenêtres marquées)",
            self._shortcut_prev, "prev")

        self._back_entry = self._shortcut_row(
            f, "↩  Retour direct",
            "Revient à la dernière fenêtre active (idéal après un échange)",
            self._shortcut_back, "back")

        self._main_entry = self._shortcut_row(
            f, "★  Personnage principal",
            "Focus direct sur le personnage principal",
            self._shortcut_main, "main")

        if not KEYBOARD_OK:
            warn = tk.Frame(f, bg="#2a1a1a", padx=12, pady=10)
            warn.pack(fill="x", padx=16, pady=8)
            tk.Label(warn, text="⚠  Module 'keyboard' non chargé",
                     bg="#2a1a1a", fg=self.RED,
                     font=("Segoe UI", 10, "bold")).pack(anchor="w")
            tk.Label(warn,
                     text="pip install keyboard  (nécessite droits admin pour les hotkeys globaux)",
                     bg="#2a1a1a", fg=self.GRAY,
                     font=("Consolas", 9)).pack(anchor="w")

    def _shortcut_row(self, parent, title: str, subtitle: str,
                      current: str | None, which: str) -> tk.Entry:
        card = tk.Frame(parent, bg=self.CARD, padx=14, pady=12)
        card.pack(fill="x", padx=16, pady=4)

        info = tk.Frame(card, bg=self.CARD)
        info.pack(side="left", fill="x", expand=True)
        tk.Label(info, text=title, bg=self.CARD,
                 fg=self.TEXT, font=self.S.Bouton.font_principal).pack(anchor="w")
        tk.Label(info, text=subtitle, bg=self.CARD,
                 fg=self.GRAY, font=self.S.Info.font).pack(anchor="w")

        right = tk.Frame(card, bg=self.CARD)
        right.pack(side="right")

        # Bouton "Aucun"
        tk.Button(right, text="Aucun", bg="#252b3b", fg=self.GRAY,
                  relief="flat", cursor="hand2",
                  font=self.S.Bouton.font_petit,
                  padx=self.S.Bouton.padx_petit, pady=self.S.Bouton.pady_petit,
                  command=lambda w=which: self._set_no_shortcut(w)
                  ).pack(side="right", padx=(4, 0))

        display = "Aucun" if current is None else current
        color   = self.GRAY if current is None else self.ACCENT

        entry = tk.Entry(right, bg="#252b3b", fg=color,
                         font=("Consolas", 11), relief="flat",
                         insertbackground=self.ACCENT,
                         justify="center", width=14)
        entry.insert(0, display)
        entry.pack(side="right", ipady=5)
        entry.bind("<FocusIn>", lambda e, w=which, en=entry: self._start_capture(en, w))
        return entry

    def _set_no_shortcut(self, which: str):
        if which == "next":
            self._shortcut_next = self.NO_SHORTCUT
            self._next_entry.delete(0, "end")
            self._next_entry.insert(0, "Aucun")
            self._next_entry.config(fg=self.GRAY)
        elif which == "prev":
            self._shortcut_prev = self.NO_SHORTCUT
            self._prev_entry.delete(0, "end")
            self._prev_entry.insert(0, "Aucun")
            self._prev_entry.config(fg=self.GRAY)
        elif which == "main":
            self._shortcut_main = self.NO_SHORTCUT
            self._main_entry.delete(0, "end")
            self._main_entry.insert(0, "Aucun")
            self._main_entry.config(fg=self.GRAY)
        else:
            self._shortcut_back = self.NO_SHORTCUT
            self._back_entry.delete(0, "end")
            self._back_entry.insert(0, "Aucun")
            self._back_entry.config(fg=self.GRAY)
        # Application immédiate — pas besoin de cliquer sur "Appliquer"
        self._apply_shortcuts()

    def _start_capture(self, entry: tk.Entry, which: str):
        entry.delete(0, "end")
        entry.insert(0, "Appuyez…")
        entry.config(fg=self.GRAY)

        def on_key(event):
            mods = []
            if event.state & 0x4:     mods.append("ctrl")
            if event.state & 0x1:     mods.append("shift")
            if event.state & 0x20000: mods.append("alt")

            key  = event.keysym.lower()
            skip = {"control_l","control_r","shift_l","shift_r",
                    "alt_l","alt_r","super_l","super_r","caps_lock"}
            if key not in skip:
                combo = "+".join(mods + [key]) if mods else key
                entry.delete(0, "end")
                entry.insert(0, combo)
                entry.config(fg=self.ACCENT)
                if which == "next":
                    self._shortcut_next = combo
                elif which == "prev":
                    self._shortcut_prev = combo
                elif which == "main":
                    self._shortcut_main = combo
                else:
                    self._shortcut_back = combo
                entry.unbind("<KeyPress>")
                self.focus()
                # Application immédiate — pas besoin de cliquer sur "Appliquer"
                self._apply_shortcuts()
            return "break"  # empêche l'insertion naturelle de la touche dans le Entry

        entry.bind("<KeyPress>", on_key)

    def _apply_shortcuts(self, silent: bool = False):
        if not KEYBOARD_OK:
            return
        try:
            _unhook_all()
            if self._shortcut_next:
                keyboard.add_hotkey(self._shortcut_next, self._focus_next)
            if self._shortcut_prev:
                keyboard.add_hotkey(self._shortcut_prev, self._focus_prev)
            if self._shortcut_back:
                keyboard.add_hotkey(self._shortcut_back, self._focus_back)
            if self._shortcut_main:
                keyboard.add_hotkey(self._shortcut_main, self._focus_main)
            self._persist_config()
        except Exception:
            pass

    def _focus_main(self):
        """Focus direct sur le personnage principal.
        Prioritaire sur l'exclusion du roulement : le perso principal est toujours atteignable.
        """
        if not is_dofus_foreground():
            return
        if not self._char_main:
            return
        def _do():
            if WIN32_OK:
                try:
                    fg = win32gui.GetForegroundWindow()
                    if fg:
                        self._prev_hwnd = fg
                except Exception:
                    pass
            focus_dofus_window(self._char_main)
        threading.Thread(target=_do, daemon=True).start()

    def _focus_next(self):
        if is_dofus_foreground():
            threading.Thread(target=self._cycle, args=(+1,), daemon=True).start()

    def _focus_prev(self):
        if is_dofus_foreground():
            threading.Thread(target=self._cycle, args=(-1,), daemon=True).start()

    def _focus_back(self):
        """Retour direct à la fenêtre active avant le dernier switch."""
        if not is_dofus_foreground():
            return
        def _do():
            if self._prev_hwnd and WIN32_OK:
                try:
                    if win32gui.IsWindow(self._prev_hwnd):
                        focus_window(self._prev_hwnd)
                        return
                except Exception:
                    pass
            self._cycle(-1)
        threading.Thread(target=_do, daemon=True).start()

    def _cycle(self, direction: int):
        if not self._char_order:
            self.refresh_characters()
        if not self._char_order:
            return

        # Construire la liste de roulement (exclure les pseudos marqués)
        cycle_order = [(i, h, p) for i, (h, p) in enumerate(self._char_order)
                       if p not in self._char_skip_names]
        if not cycle_order:
            cycle_order = [(i, h, p) for i, (h, p) in enumerate(self._char_order)]

        fg  = win32gui.GetForegroundWindow() if WIN32_OK else None

        # Mémoriser la fenêtre courante avant de changer
        if fg:
            self._prev_hwnd = fg

        # Trouver la position courante dans cycle_order
        cur_pos = next((pos for pos, (_, h, _) in enumerate(cycle_order) if h == fg), None)
        if cur_pos is None:
            new_pos = 0
        else:
            new_pos = (cur_pos + direction) % len(cycle_order)

        focus_window(cycle_order[new_pos][1])

    # ── Persistance centralisée ───────────────────────────────────────────────

    def _persist_config(self):
        """Point unique de sauvegarde de la configuration dans le registre."""
        _save_config(_build_config(
            self._shortcut_next,
            self._shortcut_prev,
            self._shortcut_back,
            self._char_af_overrides,
            self._shortcut_main,
            self._char_main,
            self._welcome_shown,
            self._char_skip_names,
        ))

    # ── Gestion des exclusions de roulement ───────────────────────────────────

    def _toggle_char_skip(self, pseudo: str, btn: tk.Button):
        """Bascule l'exclusion du roulement pour un personnage et met à jour le bouton."""
        if pseudo in self._char_skip_names:
            self._char_skip_names.discard(pseudo)
            self._style_skip_btn(btn, active=False)
        else:
            self._char_skip_names.add(pseudo)
            self._style_skip_btn(btn, active=True)
        self._persist_config()

    def _style_skip_btn(self, btn: tk.Button, active: bool):
        """Applique le style actif/inactif au bouton d'exclusion."""
        if active:
            btn.config(text="⊗  Exclure des raccourcis", bg="#2d1515",
                       fg=self.RED, activebackground="#2d1515", activeforeground=self.RED)
        else:
            btn.config(text="○  Exclure des raccourcis", bg="#252b3b",
                       fg=self.GRAY, activebackground="#252b3b", activeforeground=self.GRAY)

    def _toggle_char_main(self, pseudo: str, btn: tk.Button):
        """Définit ou retire le statut de personnage principal.
        Un seul principal possible : cliquer sur un autre transfère l'étoile.
        Cliquer sur l'étoile active la retire (plus de principal).
        Reconstruit la liste pour mettre à jour toutes les étoiles.
        """
        if self._char_main == pseudo:
            # Déjà principal → retirer
            self._char_main = None
        else:
            # Nouveau principal → remplace l'ancien sans reconstruct partiel
            self._char_main = pseudo
        self._persist_config()
        # Rebuild pour mettre à jour l'étoile de l'ancien principal (si existant)
        self._rebuild_char_list()

    def _style_main_btn(self, btn: tk.Button, active: bool):
        """Applique le style actif/inactif au bouton étoile du personnage principal."""
        if active:
            btn.config(text="★", bg="#252b3b",
                       fg=self.ACCENT, activebackground="#252b3b", activeforeground=self.ACCENT)
        else:
            btn.config(text="☆", bg="#252b3b",
                       fg=self.GRAY, activebackground="#252b3b", activeforeground=self.GRAY)

    # ══════════════════════════════════════════════════════════════════════
    # ONGLET AUTOFOCUS
    # ══════════════════════════════════════════════════════════════════════

    def _build_tab_autofocus(self):
        f = tk.Frame(self._content, bg=self.BG)
        self._tab_frames["autofocus"] = f

        # ── En-tête ───────────────────────────────────────────────────────
        top = tk.Frame(f, bg=self.BG, pady=12)
        top.pack(fill="x", padx=16)
        tk.Label(top, text="Switch automatique de fenêtre", bg=self.BG,
                 fg=self.TEXT, font=self.S.EnTete.font).pack(anchor="w")
        tk.Label(top, text="Choisissez quand passer la fenêtre au premier plan",
                 bg=self.BG, fg=self.GRAY, font=self.S.Info.font).pack(anchor="w")

        # ── Boutons de type globaux (défaut pour tous les persos sans surcharge) ──
        ff = tk.Frame(f, bg=self.BG, pady=4)
        ff.pack(fill="x", padx=16)

        tk.Label(ff, text="Paramètres globaux",
                 bg=self.BG, fg=self.TEXT, font=self.S.EnTete.font).pack(anchor="w")
        tk.Label(ff, text="S'appliquent à tous les personnages",
                 bg=self.BG, fg=self.GRAY, font=self.S.Info.font).pack(anchor="w", pady=(0, 6))

        btn_row1 = tk.Frame(ff, bg=self.BG)
        btn_row1.pack(anchor="w", pady=(0, 3))
        btn_row2 = tk.Frame(ff, bg=self.BG)
        btn_row2.pack(anchor="w")

        self.type_vars: dict[str, tk.BooleanVar] = {}
        self.type_btns: dict[str, tk.Button]     = {}

        # Ligne 1 : combat, échange, groupe, craft
        ROW1 = [("combat",  "⚔  Combat"), ("echange", "🔄  Échange"),
                ("groupe",  "👥  Groupe"), ("craft",   "🔨  Craft")]
        # Ligne 2 : mp, défi, pvp
        ROW2 = [("mp",      "💬  MP"),    ("defi",    "🏆  Défi"),
                ("pvp",     "🛡  PVP")]

        for row_frame, entries in [(btn_row1, ROW1), (btn_row2, ROW2)]:
            for key, label in entries:
                var = tk.BooleanVar(value=True)
                self.type_vars[key] = var
                btn = tk.Button(row_frame, text=label,
                                bg=self.ACCENT, fg=self.BG,
                                font=self.S.Bouton.font_type_notif,
                                relief="flat", cursor="hand2",
                                padx=self.S.Bouton.padx_type_notifnobold,
                                pady=self.S.Bouton.pady_type_notifnobold,
                                command=lambda k=key: self._toggle_type(k))
                btn.pack(side="left", padx=3)
                self.type_btns[key] = btn

        # ── Séparateur ────────────────────────────────────────────────────
        tk.Frame(f, bg=self.CARD, height=1).pack(fill="x", padx=16, pady=(10, 0))

        # ── Personnalisation par personnage ───────────────────────────────
        per_top = tk.Frame(f, bg=self.BG, pady=8)
        per_top.pack(fill="x", padx=16)

        tk.Label(per_top, text="Personnalisation par personnage",
                 bg=self.BG, fg=self.TEXT, font=self.S.EnTete.font).pack(side="left")
        tk.Button(per_top, text="↻  Actualiser", bg=self.PANEL, fg=self.TEXT,
                  relief="flat", cursor="hand2",
                  font=self.S.Bouton.font_petit,
                  padx=self.S.Bouton.padx_petit, pady=self.S.Bouton.pady_petit,
                  command=self.refresh_characters).pack(side="right")

        tk.Label(f, text="Cliquez sur une icône pour désactiver ce type pour ce personnage uniquement",
                 bg=self.BG, fg=self.GRAY, font=self.S.Info.font).pack(anchor="w", padx=16)

        # Container des cartes per-personnage (scrollable si nécessaire)
        self._af_chars_container = tk.Frame(f, bg=self.BG)
        self._af_chars_container.pack(fill="x", padx=16, pady=(4, 0))

        # ── Mode debug (contrôle aussi logs + stats) ──────────────────────
        ctrl = tk.Frame(f, bg=self.BG, pady=6)
        ctrl.pack(fill="x", padx=16)

        self.debug_var    = tk.BooleanVar(value=False)
        self.show_log_var = tk.BooleanVar(value=False)

        tk.Checkbutton(ctrl, text="Mode debug",
                       variable=self.debug_var,
                       bg=self.BG, fg=self.GRAY, selectcolor=self.CARD,
                       activebackground=self.BG, activeforeground=self.TEXT,
                       font=self.S.Info.font,
                       command=self._toggle_debug).pack(side="left")

        # ── Tuiles stats (masquées par défaut, visibles en mode debug) ────
        self._stats_outer = tk.Frame(f, bg=self.BG)

        stats = tk.Frame(self._stats_outer, bg=self.BG, pady=8)
        stats.pack(fill="x", padx=16)
        self.lbl_notifs  = self._stat(stats, "Notifications lues", "0")
        self.lbl_matches = self._stat(stats, "Patterns trouvés",   "0")
        self.lbl_focus   = self._stat(stats, "Focus réussis",      "0")
        self.lbl_last    = self._stat(stats, "Dernier joueur",     "—")

        # ── Zone log (masquée par défaut) ─────────────────────────────────
        self._log_outer = tk.Frame(f, bg=self.BG)

        log_header = tk.Frame(self._log_outer, bg=self.BG)
        log_header.pack(fill="x", pady=(2, 0))
        tk.Label(log_header, text="Journal d'activité", bg=self.BG,
                 fg=self.GRAY, font=self.S.Info.font).pack(side="left")
        tk.Button(log_header, text="vider", bg=self.BG, fg=self.GRAY,
                  relief="flat", cursor="hand2",
                  font=self.S.Info.font, padx=4, pady=0,
                  activeforeground=self.ACCENT,
                  command=self._clear_log).pack(side="right")

        self.log = scrolledtext.ScrolledText(
            self._log_outer, bg=self.CARD, fg=self.TEXT,
            font=self.FONT_MONO, bd=0, relief="flat",
            state="disabled", wrap="word")
        self.log.pack(fill="both", expand=True)

        for tag, color in [("info", self.TEXT), ("ok", self.GREEN),
                            ("warn", self.ACCENT), ("error", self.RED),
                            ("dim", self.GRAY), ("debug", self.BLUE),
                            ("time", "#555e78")]:
            self.log.tag_config(tag, foreground=color)
        for key, color in self.TYPE_COLORS.items():
            self.log.tag_config(f"type_{key}", foreground=color)

    def _toggle_debug(self):
        """Active/désactive le mode debug : affiche/masque stats + journal."""
        on = self.debug_var.get()
        self.show_log_var.set(on)
        if on:
            self._stats_outer.pack(fill="x", padx=0, pady=0)
            self._log_outer.pack(fill="both", expand=True, padx=16, pady=(4, 6))
        else:
            self._stats_outer.pack_forget()
            self._log_outer.pack_forget()

    def _toggle_log(self):
        if self.show_log_var.get():
            self._log_outer.pack(fill="both", expand=True, padx=16, pady=(4, 6))
        else:
            self._log_outer.pack_forget()

    def _stat(self, parent, label: str, value: str) -> tk.Label:
        frame = tk.Frame(parent, bg=self.CARD, padx=10, pady=6)
        frame.pack(side="left", expand=True, fill="x", padx=4)
        tk.Label(frame, text=label, bg=self.CARD,
                 fg=self.GRAY, font=self.S.Info.font).pack(anchor="w")
        lbl = tk.Label(frame, text=value, bg=self.CARD,
                       fg=self.TEXT, font=("Segoe UI", 13, "bold"))
        lbl.pack(anchor="w")
        return lbl

    def _is_type_fully_active(self, type_key: str) -> bool:
        """Retourne True si type_vars est ON et aucun personnage n'a ce type désactivé localement.
        Détermine la couleur du bouton global (jaune = tous actifs, gris = au moins un inactif).
        """
        if not self.type_vars[type_key].get():
            return False
        for pseudo, overrides in self._char_af_overrides.items():
            if overrides.get(type_key) is False:
                return False
        return True

    def _update_global_btn_style(self, type_key: str):
        """Met à jour l'apparence du bouton global selon _is_type_fully_active."""
        btn = self.type_btns[type_key]
        if self._is_type_fully_active(type_key):
            btn.config(bg=self.ACCENT, fg=self.BG,
                       activebackground=self.ACCENT, activeforeground=self.BG)
        else:
            btn.config(bg=self.CARD, fg=self.GRAY,
                       activebackground=self.CARD, activeforeground=self.GRAY)

    def _toggle_type(self, key: str):
        """Bascule le type global.

        Règle liée global ↔ per-perso :
        • Bouton global jaune (tous actifs) → désactive globalement (type_vars False),
          les surcharges per-perso pour ce type sont supprimées (devenues inutiles).
        • Bouton global gris (au moins un inactif, ou global OFF) → réactive TOUT :
          type_vars True + toutes surcharges per-perso pour ce type effacées.
        """
        fully_active = self._is_type_fully_active(key)

        if fully_active:
            # Tout était actif → désactiver globalement
            self.type_vars[key].set(False)
            # Nettoyer les éventuelles surcharges per-perso pour ce type
            for overrides in self._char_af_overrides.values():
                overrides.pop(key, None)
            # Retirer les entrées vides
            self._char_af_overrides = {p: o for p, o in self._char_af_overrides.items() if o}
        else:
            # Au moins un inactif → tout réactiver (efface toutes les surcharges pour ce type)
            self.type_vars[key].set(True)
            for overrides in list(self._char_af_overrides.values()):
                overrides.pop(key, None)
            self._char_af_overrides = {p: o for p, o in self._char_af_overrides.items() if o}

        self._update_global_btn_style(key)
        self._persist_config()

        any_active = any(v.get() for v in self.type_vars.values())
        if any_active and not self._running:
            self._start()
        elif not any_active and self._running:
            self._stop()

        # Synchroniser les icônes per-personnage
        if hasattr(self, "_af_chars_container"):
            self._rebuild_af_char_list()

    # ── AutoFocus per-personnage ──────────────────────────────────────────

    def _rebuild_af_char_list(self):
        """Reconstruit les cartes de personnalisation per-personnage (onglet AutoFocus)."""
        for w in self._af_chars_container.winfo_children():
            w.destroy()

        if not self._char_order:
            tk.Label(self._af_chars_container,
                     text="Aucun personnage détecté — actualisez l'onglet Personnages",
                     bg=self.BG, fg=self.GRAY, font=self.S.Info.font).pack(anchor="w", pady=4)
            return

        for _, pseudo in self._char_order:
            self._create_af_char_row(pseudo)

    def _create_af_char_row(self, pseudo: str):
        """Crée une carte de personnalisation autofocus pour un personnage.

        Deux états pour chaque icône :
          • Icône jaune (ACCENT) = actif pour ce perso (suit le global ON, ou pas de surcharge)
          • Icône gris  (GRAY)   = désactivé localement pour ce perso
        Fond du bouton toujours #252b3b. Pas d'élément conditionnel → layout stable.
        """
        override = self._char_af_overrides.get(pseudo)  # dict {type_key: False} ou None

        card = tk.Frame(self._af_chars_container, bg=self.CARD, padx=10, pady=5)
        card.pack(fill="x", pady=2)

        # ── Nom du personnage (pas de width fixe → pas de coupure) ────────
        tk.Label(card, text=pseudo, bg=self.CARD,
                 fg=self.TEXT, font=self.S.Bouton.font_principal,
                 anchor="w").pack(side="left", padx=(0, 10))

        # ── 4 icônes toujours présentes, fond fixe, icône jaune/gris ──────
        btn_frame = tk.Frame(card, bg=self.CARD)
        btn_frame.pack(side="right")

        TYPE_ICONS = [("combat", "⚔"), ("echange", "🔄"), ("groupe", "👥"), ("craft", "🔨"),
                      ("mp", "💬"), ("defi", "🏆"), ("pvp", "🛡")]
        for type_key, icon in TYPE_ICONS:
            locally_disabled = (override is not None and override.get(type_key) is False)
            global_active    = self.type_vars[type_key].get()
            # Actif = global ON et pas désactivé localement
            is_active = global_active and not locally_disabled

            btn = tk.Button(btn_frame, text=icon,
                            font=self.S.Bouton.font_type_notifnobold,
                            padx=5, pady=2,
                            relief="flat", cursor="hand2")
            self._style_af_char_btn(btn, is_active)
            btn.config(command=lambda p=pseudo, k=type_key, b=btn:
                       self._toggle_char_af_type(p, k, b))
            btn.pack(side="left", padx=1)

    def _style_af_char_btn(self, btn: tk.Button, is_active: bool):
        """Style d'une icône per-personnage.

        Fond toujours #252b3b.
        is_active=True  → icône jaune (ACCENT)
        is_active=False → icône gris  (GRAY)
        """
        fg = self.ACCENT if is_active else self.GRAY
        btn.config(bg="#252b3b", fg=fg,
                   activebackground="#252b3b", activeforeground=fg)

    def _toggle_char_af_type(self, pseudo: str, type_key: str, _btn: tk.Button):
        """Bascule un type de notification pour un personnage spécifique.

        Logique liée :
        • Icône jaune (is_active=True)  → désactiver localement (stocke False).
          type_vars reste True ; le bouton global passe en gris (plus "tous actifs").
        • Icône gris  (is_active=False) → retirer la surcharge locale si elle existe.
          Si le global est OFF, cliquer n'a aucun effet (l'état vient du global).
          Si tous les persos sont à nouveau actifs, le bouton global repasse en jaune.
        Le dict de surcharge ne stocke que les types désactivés (valeur False).
        """
        override = self._char_af_overrides.get(pseudo)
        locally_disabled = (override is not None and override.get(type_key) is False)
        global_active    = self.type_vars[type_key].get()
        is_active        = global_active and not locally_disabled

        if is_active:
            # Actif → désactiver localement
            if override is None:
                override = {}
                self._char_af_overrides[pseudo] = override
            override[type_key] = False
        elif locally_disabled:
            # Désactivé localement (global ON) → retirer la surcharge
            del override[type_key]
            if not override:
                del self._char_af_overrides[pseudo]
        # else : global OFF → rien à faire (ne pas stocker de surcharge inutile)

        # Mettre à jour le bouton global (pas de changement de type_vars)
        self._update_global_btn_style(type_key)
        self._persist_config()
        self._rebuild_af_char_list()

    def log_msg(self, msg: str, tag: str = "info"):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log.configure(state="normal")
        self.log.insert("end", f"[{ts}] ", "time")
        self.log.insert("end", msg + "\n", tag)
        self.log.see("end")
        self.log.configure(state="disabled")

    def _clear_log(self):
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    # ── Logique AutoFocus ─────────────────────────────────────────────────────

    def _start(self):
        if not WIN32_OK or not WINSDK_OK:
            self.log_msg("Impossible : dépendances manquantes.", "error")
            return
        self._running = True
        self._set_status("AutoFocus actif", self.GREEN)
        self.log_msg("Écoute démarrée.", "ok")
        threading.Thread(target=self._run_async_loop, daemon=True).start()

    def _stop(self):
        self._running = False
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
        self._set_status("AutoFocus inactif", self.GRAY)
        self.log_msg("Écoute arrêtée.", "dim")

    def _set_status(self, text: str, color: str):
        pass  # pastille et label supprimés

    def _run_async_loop(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._listen())
        except Exception as e:
            self.after(0, self.log_msg, f"Erreur fatale : {e}", "error")
        finally:
            self._loop.close()

    async def _listen(self):
        listener = winman.UserNotificationListener.current
        access   = await listener.request_access_async()
        if access != winman.UserNotificationListenerAccessStatus.ALLOWED:
            self.after(0, self.log_msg,
                "Accès notifications refusé ! "
                "Active-les dans Paramètres → Système → Notifications.", "error")
            self.after(0, self._stop)
            return

        self.after(0, self.log_msg, "Accès aux notifications accordé.", "ok")
        seen_ids: set[int] = set()

        # ── Mode event-driven, avec fallback polling automatique ─────────
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
            self.after(0, self.log_msg,
                "Mode event-driven actif (détection instantanée).", "ok")
        except Exception:
            self.after(0, self.log_msg,
                "Mode polling actif (0.3 s) — event-driven non supporté sur ce système.", "dim")

        try:
            while self._running:
                if use_events:
                    try:
                        await asyncio.wait_for(event.wait(), timeout=30.0)
                    except asyncio.TimeoutError:
                        pass   # pas de notif depuis 30 s, on reboucle
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
                        self.after(0, self.lbl_notifs.config, {"text": str(self._n_notifs)})

                    for notif in new_notifs:
                        seen_ids.add(notif.id)
                        try:
                            binding = notif.notification.visual.get_binding(
                                winnot.KnownNotificationBindings.toast_generic)
                            if binding is None:
                                continue

                            elements = [e.text for e in binding.get_text_elements()]

                            if self.debug_var.get():
                                self.after(0, self.log_msg,
                                    f"[debug] titre={repr(elements[0] if elements else '?')} "
                                    f"corps={repr(elements[1] if len(elements)>1 else '?')}",
                                    "debug")

                            if not elements:
                                continue

                            notif_title = elements[0]
                            notif_body  = elements[1] if len(elements) > 1 else ""

                            pseudo = extract_pseudo_from_title(notif_title)
                            if not pseudo:
                                if self.debug_var.get():
                                    self.after(0, self.log_msg,
                                        f"[debug] Titre non reconnu : {repr(notif_title)}", "debug")
                                continue

                            matched_type  = None
                            matched_emoji = "🔔"
                            for type_key, patterns, emoji in NOTIF_TYPES:
                                if any(p.search(notif_body) for p in patterns):
                                    matched_type  = type_key
                                    matched_emoji = emoji
                                    break

                            if matched_type is None:
                                if self.debug_var.get():
                                    self.after(0, self.log_msg,
                                        f"[debug] Type inconnu : {repr(notif_body)}", "debug")
                                continue

                            # ── Vérification autofocus ────────────────────────────────
                            # 1. type_vars[type] False = globalement désactivé pour TOUS.
                            if not self.type_vars[matched_type].get():
                                self.after(0, self.log_msg,
                                    f"[{matched_type}] ignoré (désactivé global) — {pseudo}", "dim")
                                continue

                            # 2. Surcharge per-personnage (chemin rapide si dict vide).
                            if self._char_af_overrides:
                                _ov = self._char_af_overrides.get(pseudo)
                                if _ov is not None and _ov.get(matched_type) is False:
                                    self.after(0, self.log_msg,
                                        f"[{matched_type}] ignoré (désactivé pour {pseudo})", "dim")
                                    continue

                            self._n_matches += 1
                            self.after(0, self.lbl_matches.config, {"text": str(self._n_matches)})
                            self.after(0, self.lbl_last.config,    {"text": pseudo})
                            self.after(0, self.log_msg,
                                f"{matched_emoji} [{matched_type.upper()}] {pseudo} — {notif_body}",
                                f"type_{matched_type}")

                            # Mémoriser la fenêtre courante avant le switch auto
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
                                self.after(0, self.lbl_focus.config, {"text": str(self._n_focus)})
                                self.after(0, self.log_msg, f"  ✓ Focus : {detail}", "ok")
                            else:
                                self.after(0, self.log_msg, f"  ✗ {detail}", "error")
                                wins = list_dofus_windows()
                                for w in wins:
                                    self.after(0, self.log_msg,
                                        f"    Fenêtre dispo : {repr(w)}", "debug")

                        except Exception as e:
                            if self.debug_var.get():
                                self.after(0, self.log_msg,
                                    f"[debug] Exception notif : {e}", "debug")

                    if len(seen_ids) > 500:
                        seen_ids.clear()

                except Exception as e:
                    self.after(0, self.log_msg, f"Erreur de lecture : {e}", "error")
        finally:
            try:
                listener.remove_notification_changed(token)
            except Exception:
                pass  # token déjà invalide si la boucle a été arrêtée brutalement

    # ══════════════════════════════════════════════════════════════════════
    # ONGLET INFO
    # ══════════════════════════════════════════════════════════════════════

    def _build_tab_info(self):
        f = tk.Frame(self._content, bg=self.BG)
        self._tab_frames["info"] = f

        # ── En-tête ───────────────────────────────────────────────────────
        top = tk.Frame(f, bg=self.BG, pady=12)
        top.pack(fill="x", padx=16)
        tk.Label(top, text="À propos", bg=self.BG,
                 fg=self.TEXT, font=self.S.EnTete.font).pack(anchor="w")
        tk.Label(top, text="Informations sur l'application et mentions légales",
                 bg=self.BG, fg=self.GRAY, font=self.S.Info.font).pack(anchor="w")

        # ── Carte version ─────────────────────────────────────────────────
        card_ver = tk.Frame(f, bg=self.CARD, padx=16, pady=12)
        card_ver.pack(fill="x", padx=16, pady=(4, 2))

        row_ver = tk.Frame(card_ver, bg=self.CARD)
        row_ver.pack(fill="x")
        tk.Label(row_ver, text="Version", bg=self.CARD,
                 fg=self.GRAY, font=self.S.Info.font).pack(side="left")
        tk.Label(row_ver, text=APP_VERSION, bg=self.CARD,
                 fg=self.ACCENT, font=self.S.Bouton.font_principal).pack(side="right")

        # ── Carte liens ───────────────────────────────────────────────────
        card_links = tk.Frame(f, bg=self.CARD, padx=16, pady=12)
        card_links.pack(fill="x", padx=16, pady=2)

        tk.Label(card_links, text="Liens", bg=self.CARD,
                 fg=self.GRAY, font=self.S.Info.font).pack(anchor="w", pady=(0, 8))

        def _link_row(parent, icon: str, label: str, url: str):
            row = tk.Frame(parent, bg=self.CARD)
            row.pack(fill="x", pady=2)
            tk.Label(row, text=icon, bg=self.CARD,
                     fg=self.GRAY, font=self.S.Info.font).pack(side="left", padx=(0, 6))
            lbl = tk.Label(row, text=label, bg=self.CARD,
                           fg=self.BLUE, font=self.S.Info.font,
                           cursor="hand2")
            lbl.pack(side="left")
            lbl.bind("<Button-1>", lambda e, u=url: webbrowser.open(u))
            lbl.bind("<Enter>",    lambda e: lbl.config(fg=self.ACCENT))
            lbl.bind("<Leave>",    lambda e: lbl.config(fg=self.BLUE))

        _link_row(card_links, "⌨", "GitHub : https://github.com/Slyss42/Dracoon", APP_GITHUB)
        _link_row(card_links, "🐦", "Twitter/X : https://x.com/Slyss42",  APP_TWITTER)

        # ── Carte mentions légales ────────────────────────────────────────
        card_legal = tk.Frame(f, bg=self.CARD, padx=16, pady=12)
        card_legal.pack(fill="x", padx=16, pady=2)

        tk.Label(card_legal, text="Mentions légales", bg=self.CARD,
                 fg=self.GRAY, font=self.S.Info.font).pack(anchor="w", pady=(0, 6))
        tk.Label(card_legal, text=APP_LEGAL, bg=self.CARD,
                 fg=self.TEXT, font=self.S.Info.font,
                 justify="left", wraplength=620).pack(anchor="w")

        # ── Carte réinitialisation ─────────────────────────────────────────
        card_reset = tk.Frame(f, bg=self.CARD, padx=16, pady=12)
        card_reset.pack(fill="x", padx=16, pady=(2, 16))

        tk.Label(card_reset, text="Réinitialiser les paramètres", bg=self.CARD,
                 fg=self.GRAY, font=self.S.Info.font).pack(anchor="w", pady=(0, 6))
        tk.Label(card_reset,
                 text="Efface les raccourcis, le personnage principal, les exclusions "
                      "et réaffiche le message de bienvenue au prochain lancement.",
                 bg=self.CARD, fg=self.GRAY, font=self.S.Info.font,
                 justify="left", wraplength=620).pack(anchor="w", pady=(0, 8))
        tk.Button(card_reset, text="🗑  Réinitialiser",
                  bg="#2d1515", fg=self.RED,
                  relief="flat", cursor="hand2",
                  font=self.S.Bouton.font_petit,
                  padx=self.S.Bouton.padx_petit, pady=self.S.Bouton.pady_petit,
                  activebackground="#2d1515", activeforeground=self.RED,
                  command=self._reset_config).pack(anchor="w")

    def _reset_config(self):
        """Réinitialise l'ensemble de la configuration dans le registre et en mémoire.
        Supprime : raccourcis clavier, personnage principal, exclusions du roulement,
        surcharges autofocus per-perso, et flag 'bienvenue déjà affiché'.
        Le message de bienvenue réapparaîtra au prochain lancement.
        """
        # Remettre à zéro en mémoire
        self._shortcut_next    = None
        self._shortcut_prev    = None
        self._shortcut_back    = None
        self._shortcut_main    = None
        self._char_main        = None
        self._char_skip_names  = set()
        self._char_af_overrides = {}
        self._welcome_shown    = False

        # Désactiver les hotkeys actifs
        _unhook_all()

        # Persister l'état vide dans le registre
        self._persist_config()

        # Reconstruire la liste des personnages pour effacer les étoiles et exclusions
        self._rebuild_char_list()

        # Mettre à jour les entrées de l'onglet Raccourcis si déjà construites
        for attr, entry in [("_next_entry", self._next_entry),
                            ("_prev_entry", self._prev_entry),
                            ("_back_entry", self._back_entry),
                            ("_main_entry", self._main_entry)]:
            try:
                entry.delete(0, "end")
                entry.insert(0, "Aucun")
                entry.config(fg=self.GRAY)
            except Exception:
                pass

        self.log_msg("Paramètres réinitialisés.", "ok")


# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    app = App()
    app.mainloop()
