import ctypes
import ctypes.wintypes as wt
import json
import logging
import os
import re
import sys
import time
import winreg
from logging.handlers import RotatingFileHandler


# ══════════════════════════════════════════════════════════════════════════════
# 1. CONSTANTES ET DÉPENDANCES
# ══════════════════════════════════════════════════════════════════════════════

# ─── Icône ────────────────────────────────────────────────────────────────────
if getattr(sys, "frozen", False):
    ICON_PATH = os.path.join(sys._MEIPASS, "icon.ico")
else:
    ICON_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico")

# ─── Fichier de log ───────────────────────────────────────────────────────────
def _log_dir() -> str:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    d = os.path.join(base, "Dracoon")
    try:
        os.makedirs(d, exist_ok=True)
    except Exception:
        pass
    return d

LOG_PATH = os.path.join(_log_dir(), "dracoon.log")

def setup_file_logger() -> logging.Logger:
    logger = logging.getLogger("dracoon")
    if logger.handlers:
        return logger
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    try:
        h = RotatingFileHandler(LOG_PATH, maxBytes=5 * 1024 * 1024,
                                backupCount=3, encoding="utf-8")
        h.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)s [%(threadName)s] %(message)s"))
        logger.addHandler(h)
    except Exception:
        pass
    return logger

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

# ─── Constantes pour Logique Raccourcis──────────────────────────────────────────────

_REG_PATH = r"Software\DofusRetro"

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

# ─── Constantes pour Onflet Info ─────────────────────────────────────────────────────────

APP_VERSION = "2.0.6"
APP_GITHUB  = "https://github.com/Slyss42/Dracoon"
APP_TWITTER = "https://x.com/Slyss42"
APP_LEGAL   = (
    "Dofus Retro est une marque déposée de Ankama et ce projet n'y est pas affilié. L'utilisation d'un logiciel tiers est tolérée uniquement s'il ne modifie pas les fichiers du jeu et n'interagit pas directement avec celui-ci, comme un simple outil de gestion de fenêtres. Ce logiciel est fourni à titre personnel, sans aucune garantie, et n'est pas officiellement pris en charge par Ankama. Par conséquent, son utilisation se fait sous l'entière responsabilité de l'utilisateur : Ankama ne peut garantir la sécurité de l'outil et toute violation éventuelle de données ou de logs reste à la charge du joueur. Enfin, il est important de noter que les outils de type macros ou automatisation restent strictement interdits.\n"
)

# ══════════════════════════════════════════════════════════════════════════════
# 2. LOGIQUE
# ══════════════════════════════════════════════════════════════════════════════

def set_window_app_id(hwnd: int, app_id: str | None) -> bool:
    if not UNGROUP_OK:
        return False
    pstore = ctypes.c_void_p()
    Release = None
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
        return hr == 0
    except Exception:
        return False
    finally:
        if Release is not None and pstore.value:
            try:
                Release(pstore.value)
            except Exception:
                pass


def reorder_with_ungroup_regroup(hwnds: list[int], log_fn=None):
    # 1. Dégrouper
    for i, hwnd in enumerate(hwnds):
        ok = set_window_app_id(hwnd, f"DofusRetro.Char.{hwnd}")
        if log_fn:
            log_fn(f"  Ungroup hwnd={hwnd} → {'OK' if ok else 'ÉCHEC'}", "debug")
    time.sleep(0.3)
    # 2. Z-order silencieux
    SWP = 0x0010 | 0x0002 | 0x0001
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
        if not win32gui.IsWindowVisible(hwnd):
            return True
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            if not _is_dofus_pid(pid):
                return True
        except Exception:
            return True
        t = win32gui.GetWindowText(hwnd)
        p = extract_pseudo_from_title(t)
        if p:
            result.append((hwnd, p))
        elif LOADING_PATTERN.match(t):
            result.append((hwnd, "[Chargement…]"))
        return True
    win32gui.EnumWindows(cb, None)
    return result


def _try_set_foreground(hwnd: int) -> bool:
    try:
        win32api.keybd_event(win32con.VK_MENU, 0, 0, 0)
        try:
            win32gui.SetForegroundWindow(hwnd)
            return True
        finally:
            win32api.keybd_event(win32con.VK_MENU, 0, win32con.KEYEVENTF_KEYUP, 0)
    except Exception:
        return False


def _attach_and_set_foreground(hwnd: int) -> bool:
    # Fallback when SetForegroundWindow is silently denied by Windows focus-stealing
    # prevention: temporarily attach our input queue to the current foreground thread.
    try:
        user32   = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        fg = win32gui.GetForegroundWindow()
        if not fg:
            return False
        fg_tid     = win32process.GetWindowThreadProcessId(fg)[0]
        target_tid = win32process.GetWindowThreadProcessId(hwnd)[0]
        cur_tid    = kernel32.GetCurrentThreadId()
        attached_fg = attached_target = False
        try:
            if fg_tid and fg_tid != cur_tid:
                attached_fg = bool(user32.AttachThreadInput(cur_tid, fg_tid, True))
            if target_tid and target_tid != cur_tid and target_tid != fg_tid:
                attached_target = bool(user32.AttachThreadInput(cur_tid, target_tid, True))
            user32.BringWindowToTop(hwnd)
            try:
                win32gui.SetForegroundWindow(hwnd)
                return True
            except Exception:
                return False
        finally:
            if attached_fg:
                user32.AttachThreadInput(cur_tid, fg_tid, False)
            if attached_target:
                user32.AttachThreadInput(cur_tid, target_tid, False)
    except Exception:
        return False


def focus_window(hwnd: int) -> tuple[bool, str]:
    try:
        title = win32gui.GetWindowText(hwnd)
        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        if _try_set_foreground(hwnd):
            return True, title
        if _attach_and_set_foreground(hwnd):
            return True, title
        return False, f"focus refusé par Windows (hwnd={hwnd})"
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
    if not WIN32_OK:
        return False
    try:
        hwnd = win32gui.GetForegroundWindow()
        title = win32gui.GetWindowText(hwnd)
        return bool(TITLE_PATTERN.match(title) or LOADING_PATTERN.match(title))
    except Exception:
        return False


def _release_modifier_keys():
    if not WIN32_OK:
        return
    for vk in (win32con.VK_MENU, win32con.VK_CONTROL,
               win32con.VK_LMENU, win32con.VK_RMENU,
               win32con.VK_LCONTROL, win32con.VK_RCONTROL):
        try:
            win32api.keybd_event(vk, 0, win32con.KEYEVENTF_KEYUP, 0)
        except Exception:
            pass


# ─── Logique Raccourcis : sauvegarde dans le registre ─────────────────────────

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
                  char_af_overrides=None, shortcut_main=None, char_main=None,
                  welcome_shown=False, char_skip_names=None,
                  remove_notif=False, maximize_on_launch=True) -> dict:    
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
        "remove_notif":        "1" if remove_notif else "0",
        "maximize_on_launch":  "1" if maximize_on_launch else "0",                     
    }


# ─── Logique Autofocus ─────────────────────────────────────────────────────────

def focus_dofus_window(pseudo: str) -> tuple[bool, str]:
    found = []
    def cb(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return True
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            if not _is_dofus_pid(pid):
                return True
        except Exception:
            return True
        t = win32gui.GetWindowText(hwnd)
        if re.match(rf"^{re.escape(pseudo)}\s*-\s*Dofus Retro\b", t, re.IGNORECASE):
            found.append((hwnd, t))
        return True
    win32gui.EnumWindows(cb, None)
    if not found:
        return False, f"Aucune fenêtre « {pseudo} - Dofus Retro… » trouvée"
    return focus_window(found[0][0])


def _encode_af_overrides(overrides: dict) -> str:
    return json.dumps(overrides, ensure_ascii=False)


def _decode_af_overrides(raw: str) -> dict:
    try:
        return json.loads(raw) if raw else {}
    except Exception:
        return {}
