import psutil

import os
import sys
import json
import logging
from logging.handlers import RotatingFileHandler
import re
import ctypes
import ctypes.wintypes as wt
from logging.handlers import RotatingFileHandler
import winreg

# ══════════════════════════════════════════════════════════════════════════════
# 1. CONSTANTES ET DÉPENDANCES
# ══════════════════════════════════════════════════════════════════════════════
# ─── Type build ─────────────────────────────────────────────────────────
APP_UPDATE_MODE = "onefile"  # ou "onedir" ou "onefile" — à changer manuellement selon le build (voir README_UPDATER.md §5)
# ─── Onglet Info ─────────────────────────────────────────────────────────
APP_VERSION = "4.0.0"
APP_GITHUB  = "https://github.com/Slyss42/Dracoon"
APP_TWITTER = "https://x.com/Slyss42"

# ─── Logique Raccourcis──────────────────────────────────────────────
_REG_PATH = r"Software\Dracoon"

# ─── Dépendances optionnelles ─────────────────────────────────────────────────
try:
    import win32gui, win32con, win32api, win32process
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
    import psutil
    PSUTIL_OK = True
except Exception:
    psutil = None
    PSUTIL_OK = False

try:
    import pystray
    from PIL import Image, ImageDraw
    TRAY_OK = True
except Exception:
    TRAY_OK = False

# ─── Constantes pour Logique Personnages──────────────────
TITLE_PATTERN   = re.compile(r"^(.+?)\s*-\s*Dofus", re.IGNORECASE)
LOADING_PATTERN = re.compile(r"^Dofus Retro\b",      re.IGNORECASE)
shortened_titles: dict[int, tuple[str, str]] = {}

def _is_dofus_pid(pid: int) -> bool:
    if not PSUTIL_OK:
        return True  # fallback : on ne filtre pas, comportement comme avant
    try:
        return "dofus" in psutil.Process(pid).name().lower()
    except Exception:
        return False

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

# ─── Icônes de classe (barre des tâches par personnage) ──────────────────────
# Couleurs prédéfinies (hex sans #)
CHAR_ICON_COLORS = [
    None,        # aucune (défaut)
    "808080",    # gris
    "e05252",    # rouge
    "e07d52",    # orange
    "f5c842",    # jaune
    "4caf78",    # vert
    "42c5c5",    # cyan
    "4a90d9",    # bleu
    "9b59b6",    # violet
    "e05299",    # rose
]

# Portraits de classe disponibles (noms sans extension)
CHAR_ICON_PORTRAITS = [
    None,           # aucun
    "cra_f", "cra_m",
    "ecaflip_f", "ecaflip_m",
    "eniripsa_f", "eniripsa_m",
    "feca_f", "feca_m",
    "iop_f", "iop_m",
    "osamodas_f", "osamodas_m",
    "pandawa_f", "pandawa_m",
    "enutrof_f", "enutrof_m",
    "sacrieur_f", "sacrieur_m",
    "sadida_f", "sadida_m",
    "sram_f", "sram_m",
    "xelor_f", "xelor_m",
]

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

_TYPE_ORDER = [
    ("combat",  "⚔️"),
    ("mp",      "💬"),
    ("groupe",  "👥"),
    ("echange", "🔄"),
    ("craft",   "🔨"),
    ("defi",    "🏆"),
    ("pvp",     "🛡️"),
]

# ─── Constantes pour Logique Autofocus ────────────────────────────────────────────────────
POLL_INTERVAL = 0.1

NOTIF_TYPES = [
    ("combat", [
        re.compile(r"de jouer",                             re.IGNORECASE),
        re.compile(r"turn to play",                         re.IGNORECASE),
        re.compile(r"Le toca jugar a",                      re.IGNORECASE),
    ], "⚔️"),
    ("echange", [
        re.compile(r"te propose de faire un échange",       re.IGNORECASE),
        re.compile(r"offers a trade",                       re.IGNORECASE),
        re.compile(r"te propone realizar un intercambio",   re.IGNORECASE),
    ], "🔄"),
    ("groupe", [
        re.compile(r"t['']invite .+rejoindre son groupe",  re.IGNORECASE),
        re.compile(r"t['']invite .+rejoindre sa guilde",   re.IGNORECASE),
        re.compile(r"You are invited to join .+'s group",   re.IGNORECASE),
        re.compile(r"invites you to join the .+guild",      re.IGNORECASE),
        re.compile(r"te invita a unirte a su grupo",        re.IGNORECASE),
        re.compile(r"te invita a unirte a su gremio",       re.IGNORECASE),
    ], "👥"),
    ("mp", [
        re.compile(r"^de ",                                 re.IGNORECASE),
        re.compile(r"^from ",                               re.IGNORECASE),
        re.compile(r"^desde ",                              re.IGNORECASE),
    ], "💬"),
    ("defi", [
        re.compile(r"te défie",                             re.IGNORECASE),
        re.compile(r"challenges you",                       re.IGNORECASE),
        re.compile(r"te desafía",                           re.IGNORECASE),
    ], "🏆"),
    ("craft", [
        re.compile(r"fait appel à tes talents d.artisan",   re.IGNORECASE),
        re.compile(r"rejoindre son atelier",                re.IGNORECASE),
        re.compile(r"tous les objets ont été fabriqués",    re.IGNORECASE),
        re.compile(r"is crying out for your skills",        re.IGNORECASE),
        re.compile(r"You are invited to join .+'s workshop",re.IGNORECASE),
        re.compile(r"All items have been created!",         re.IGNORECASE),
        re.compile(r"solicita tus talentos de artesano",    re.IGNORECASE),
        re.compile(r"te invita a pasarte por su taller",    re.IGNORECASE),
        re.compile(r"¡Todos los objetos han sido fabricados!", re.IGNORECASE),
    ], "🔨"),
    ("pvp", [
        re.compile(r"percepteur.+est attaqué en",             re.IGNORECASE),
        re.compile(r"The perceptor .+is attacked in",         re.IGNORECASE),
        re.compile(r"El recaudador .+está siendo atacado en", re.IGNORECASE),
    ], "🛡️"),
]


# ══════════════════════════════════════════════════════════════════════════════
# 2. GESTION DES CHEMINS ET DOSSIERS
# ══════════════════════════════════════════════════════════════════════════════
# # ─── Icône ────────────────────────────────────────────────────────────────────
if getattr(sys, "frozen", False):
    ICON_PATH = os.path.join(sys._MEIPASS, "ressources", "icon.ico")
else:
    ICON_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ressources", "icon.ico")
    
def portraits_dir() -> str:
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, "portraits")
    # Remonte d'un cran (vers src/) puis cherche ressources/portraits
    current_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(os.path.join(current_dir, "..", "..", "ressources", "portraits"))

def log_dir() -> str:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    d = os.path.join(base, "Dracoon")
    os.makedirs(d, exist_ok=True)
    return d

LOG_PATH = os.path.join(log_dir(), "dracoon.log")

def setup_file_logger():
    """Initialise le système de logs."""
    logger = logging.getLogger("Dracoon")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        try:
            handler = RotatingFileHandler(LOG_PATH, maxBytes=1024*1024, backupCount=1, encoding="utf-8")
            formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', '%Y-%m-%d %H:%M:%S')
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        except Exception:
            pass
    return logger

# ══════════════════════════════════════════════════════════════════════════════
# 3. UTILS D'ENCODAGE / DÉCODAGE JSON
# ══════════════════════════════════════════════════════════════════════════════
def _encode_af_overrides(overrides: dict) -> str:
    return json.dumps(overrides, ensure_ascii=False)


def _decode_af_overrides(raw: str) -> dict:
    try:
        return json.loads(raw) if raw else {}
    except Exception:
        return {}

def _encode_char_icons(icons: dict) -> str:
    return json.dumps(icons, ensure_ascii=False)


def _decode_char_icons(raw: str) -> dict:
    try:
        return json.loads(raw) if raw else {}
    except Exception:
        return {}
    
# ══════════════════════════════════════════════════════════════════════════════
# 4. SAUVEGARDE ET CONFIGURATION REGISTRE
# ══════════════════════════════════════════════════════════════════════════════
# ─── LOGIQUE DE PERSISTANCE (REGISTRE WINDOWS) ────────────────────────────────
def build_config(shortcut_next, shortcut_prev, shortcut_back,
                  char_af_overrides=None, shortcut_main=None, char_main=None,
                  welcome_shown=False, char_skip_names=None,
                  remove_notif=False, maximize_on_launch=True,
                  shortcut_move=None,
                  move_overlay=True, move_cycle_delay: int = 95, move_enabled=True,
                  dradidas_enabled=True, dradidas_turns=3, dradidas_sadidas=None, shortcut_dradidas=None, shortcut_ctrl_shift=None, lang="fr",shorten_title=False, char_icons=None,
                  check_update_on_launch=True) -> dict: 
    return {
        "shortcut_next":     shortcut_next,
        "shortcut_prev":     shortcut_prev,
        "shortcut_back":     shortcut_back,
        "shortcut_main":     shortcut_main,
        "shortcut_move":     shortcut_move,
        "char_main":         char_main if char_main is not None else "",
        "char_af_overrides": _encode_af_overrides(char_af_overrides or {}),
        "welcome_shown":     "1" if welcome_shown else "0",
        "char_skip_names":   json.dumps(sorted(char_skip_names), ensure_ascii=False)
                             if char_skip_names else "[]",
        "remove_notif":        "1" if remove_notif else "0",
        "maximize_on_launch":  "1" if maximize_on_launch else "0",
        "move_overlay":        "1" if move_overlay else "0",
        "move_cycle_delay":     str(move_cycle_delay),
        "move_enabled":        "1" if move_enabled else "0",
        "dradidas_enabled":  "1" if dradidas_enabled else "0",
        "dradidas_turns":    str(dradidas_turns),
        "dradidas_sadidas":  json.dumps(sorted(dradidas_sadidas or []), ensure_ascii=False),
        "shortcut_dradidas": shortcut_dradidas,
        "shortcut_ctrl_shift": shortcut_ctrl_shift,
        "lang": lang,
        "shorten_title": "1" if shorten_title else "0",
        "char_icons":    _encode_char_icons(char_icons or {}),
        "check_update_on_launch": "1" if check_update_on_launch else "0",
    }

def load_config() -> dict:
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


def save_config(data: dict):
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