import ctypes
import ctypes.wintypes as wt
import json
import logging
import os
import re
import sys
import time
import threading
import webbrowser
import winreg
from datetime import datetime
import psutil
import time


# ══════════════════════════════════════════════════════════════════════════════
# 1. CONSTANTES ET DÉPENDANCES
# ══════════════════════════════════════════════════════════════════════════════

# ─── Icône ────────────────────────────────────────────────────────────────────
import sys as _sys
if getattr(_sys, "frozen", False):
    ICON_PATH = os.path.join(_sys._MEIPASS, "icon.ico")
    #_log_path = os.path.join(os.path.dirname(_sys.executable), "dracoon.log")  # +
    #_sys.stderr = open(_log_path, "w", buffering=1, encoding="utf-8")
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
_shortened_titles: dict[int, tuple[str, str]] = {}

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

APP_VERSION = "3.0.0"
APP_GITHUB  = "https://github.com/Slyss42/Dracoon"
APP_TWITTER = "https://x.com/Slyss42"

# ─── i18n ─────────────────────────────────────────────────────────────────────

_translations: dict = {}

def load_translations(lang: str = "fr"):
    global _translations
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "i18n.json")
    with open(path, encoding="utf-8") as f:
        all_langs = json.load(f)
    _translations = all_langs.get(lang, all_langs.get("fr", {}))

def t(key: str) -> str:
    return _translations.get(key, key)

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


def extract_pseudo_from_title(title: str, hwnd: int = None) -> str | None:
    if hwnd is not None and hwnd in _shortened_titles:
        return _shortened_titles[hwnd][0]
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
        title = win32gui.GetWindowText(hwnd)
        p = extract_pseudo_from_title(title, hwnd)  # ← hwnd en plus
        if p:
            result.append((hwnd, p))
        elif LOADING_PATTERN.match(title):
            result.append((hwnd, t("tab.personnages.loading")))
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
            title = win32gui.GetWindowText(hwnd)
            if "dofus" in title.lower():
                result.append(title)
        return True
    win32gui.EnumWindows(cb, None)
    return result


def is_dofus_foreground() -> bool:
    if not WIN32_OK:
        return False
    try:
        hwnd = win32gui.GetForegroundWindow()
        if hwnd in _shortened_titles:
            return True
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
                  remove_notif=False, maximize_on_launch=True,
                  shortcut_move=None,
                  move_overlay=True, move_cycle_delay: int = 95, move_enabled=True,
                  dradidas_enabled=True, dradidas_turns=3, dradidas_sadidas=None, shortcut_dradidas=None, shortcut_ctrl_shift=None, lang="fr",shorten_title=False) -> dict: 
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
        title = win32gui.GetWindowText(hwnd)
        p = extract_pseudo_from_title(title, hwnd)  # ← hwnd en plus
        if p and p.lower() == pseudo.lower():
            found.append((hwnd, title))
        return True
    win32gui.EnumWindows(cb, None)
    if not found:
        return False, f"Aucune fenêtre « {pseudo} » trouvée"
    return focus_window(found[0][0])


def _encode_af_overrides(overrides: dict) -> str:
    return json.dumps(overrides, ensure_ascii=False)


def _decode_af_overrides(raw: str) -> dict:
    try:
        return json.loads(raw) if raw else {}
    except Exception:
        return {}


# ─── Presets d'ordre des personnages ──────────────────────────────────────────

_PRESET_KEY = "order_presets"


def load_order_presets() -> dict[str, list[str]]:
    """Retourne {nom: [pseudo, ...]} depuis le registre."""
    cfg = _load_config()
    raw = cfg.get(_PRESET_KEY, "") or ""
    try:
        return json.loads(raw) if raw else {}
    except Exception:
        return {}


def save_order_preset(name: str, pseudos: list[str]):
    """Ajoute ou écrase un preset et persiste."""
    presets = load_order_presets()
    presets[name] = pseudos
    _save_config({_PRESET_KEY: json.dumps(presets, ensure_ascii=False)})


def delete_order_preset(name: str):
    """Supprime un preset et persiste."""
    presets = load_order_presets()
    presets.pop(name, None)
    _save_config({_PRESET_KEY: json.dumps(presets, ensure_ascii=False)})


def apply_order_preset(preset_pseudos: list[str],
                       current_order: list[tuple[int, str]]) -> list[tuple[int, str]]:
    """
    Retourne un nouvel ordre :
      1. Personnages du preset dans l'ordre défini (s'ils sont connectés)
      2. Personnages connectés absents du preset, dans leur ordre actuel
    """
    pseudo_to_hwnd = {p: h for h, p in current_order}
    result = []
    seen = set()
    for pseudo in preset_pseudos:
        if pseudo in pseudo_to_hwnd:
            result.append((pseudo_to_hwnd[pseudo], pseudo))
            seen.add(pseudo)
    for hwnd, pseudo in current_order:
        if pseudo not in seen:
            result.append((hwnd, pseudo))
    return result


# ─── Logique Mode Déplacement ─────────────────────────────────────────────────

import ctypes.wintypes as wt

WH_MOUSE_LL    = 14
WM_LBUTTONDOWN = 0x0201
LLMHF_INJECTED = 0x00000001


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("pt",          wt.POINT),
        ("mouseData",   wt.DWORD),
        ("flags",       wt.DWORD),
        ("time",        wt.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class MoveModeManager:
    """
    Gère le mode déplacement :
      • Hook souris bas niveau (WH_MOUSE_LL) — aucune dépendance UI.
      • À chaque clic gauche sur une fenêtre Dofus, appelle cycle_fn après
        un délai configurable.
      • Notifie l'UI via on_state_change(is_active: bool) à chaque toggle.
    """

    _CYCLE_DELAY_MS = 95   # délai (ms) avant de cycler après le clic
    _COOLDOWN_MS    = 96   # cooldown minimum (ms) entre deux cycles

    def __init__(self, cycle_fn, is_dofus_fg_fn, on_state_change=None):
        self._cycle_fn        = cycle_fn
        self._is_dofus_fg     = is_dofus_fg_fn
        self._on_state_change = on_state_change
        self._active          = False
        self._last_ts         = 0.0
        self._hook            = None
        self._proc            = None
        self._start_hook()

    def toggle(self):
        self._active = not self._active
        if self._on_state_change:
            self._on_state_change(self._active)

    @property
    def is_active(self) -> bool:
        return self._active

    def _start_hook(self):
        threading.Thread(
            target=self._hook_loop, daemon=True, name="MoveModeHook"
        ).start()

    def _hook_loop(self):
        LowLevelMouseProc = ctypes.WINFUNCTYPE(
            ctypes.c_int, ctypes.c_int, wt.WPARAM,
            ctypes.POINTER(MSLLHOOKSTRUCT),
        )

        def _callback(nCode, wParam, lParam):
            if nCode >= 0 and wParam == WM_LBUTTONDOWN:
                if not (lParam.contents.flags & LLMHF_INJECTED):
                    if self._active:
                        # Vérifier la fenêtre SOUS le curseur (pas le foreground)
                        # pour éviter d'intercepter les clics sur la barre des tâches
                        try:
                            pt = lParam.contents.pt
                            hwnd_under = ctypes.windll.user32.WindowFromPoint(pt)
                            # Remonter jusqu'à la fenêtre racine
                            hwnd_root = ctypes.windll.user32.GetAncestor(hwnd_under, 2)  # GA_ROOT
                            title_buf = ctypes.create_unicode_buffer(256)
                            ctypes.windll.user32.GetWindowTextW(hwnd_root, title_buf, 256)
                            title = title_buf.value
                            is_dofus = bool(
                                TITLE_PATTERN.match(title) or LOADING_PATTERN.match(title)
                            )
                        except Exception:
                            is_dofus = False

                        if is_dofus:
                            now = time.monotonic()
                            if now - self._last_ts >= (self._COOLDOWN_MS / 1000.0):
                                self._last_ts = now
                                threading.Timer(
                                    self._CYCLE_DELAY_MS / 1000.0,
                                    self._cycle_fn
                                ).start()
            return ctypes.windll.user32.CallNextHookEx(
                self._hook, nCode, wParam, lParam)

        self._proc = LowLevelMouseProc(_callback)
        self._hook = ctypes.windll.user32.SetWindowsHookExW(
            WH_MOUSE_LL, self._proc, None, 0)

        msg = wt.MSG()
        while ctypes.windll.user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            ctypes.windll.user32.TranslateMessage(ctypes.byref(msg))
            ctypes.windll.user32.DispatchMessageW(ctypes.byref(msg))

        if self._hook:
            ctypes.windll.user32.UnhookWindowsHookEx(self._hook)
            self._hook = None

class DradidasManager:
    """
    Gère les compteurs de Puissance Sylvestre par personnage.

    Usage :
        manager = DradidasManager(turns=3)
        manager.set_sadidas({"Perso1", "Perso2"})

        # Quand le raccourci est pressé sur la fenêtre de "Perso1" :
        manager.trigger("Perso1")

        # Dans le listener d'autofocus, avant chaque notification combat :
        skip, left = manager.should_skip_combat("Perso1")
        if skip:
            # ignorer ce tour de combat
    """

    def __init__(self, turns: int = 3):
        self._sadida_pseudos: set[str] = set()
        self._skip_counts:    dict[str, int] = {}   # pseudo → tours restants
        self._turns = max(1, int(turns))

    # ── Propriétés ────────────────────────────────────────────────────────────

    @property
    def turns(self) -> int:
        return self._turns

    @turns.setter
    def turns(self, value: int):
        self._turns = max(1, int(value))

    @property
    def sadida_pseudos(self) -> set[str]:
        return set(self._sadida_pseudos)

    # ── Configuration ─────────────────────────────────────────────────────────

    def set_sadidas(self, pseudos: set[str]):
        """Met à jour l'ensemble des pseudos Sadida.
        Annule les compteurs des personnages qui ne sont plus Sadida.
        """
        self._sadida_pseudos = set(pseudos)
        for p in list(self._skip_counts.keys()):
            if p not in self._sadida_pseudos:
                del self._skip_counts[p]

    def is_sadida(self, pseudo: str) -> bool:
        return pseudo in self._sadida_pseudos

    # ── Contrôle du compteur ──────────────────────────────────────────────────

    def trigger(self, pseudo: str):
        """Démarre ou remet à zéro le compteur pour ce pseudo.
        Idempotent : si déjà actif, remet exactement à _turns (sans dépasser).
        Ne fait rien si le pseudo n'est pas dans la liste Sadida.
        """
        if pseudo in self._sadida_pseudos:
            self._skip_counts[pseudo] = self._turns

    def should_skip_combat(self, pseudo: str) -> tuple[bool, int]:
        """Appelé par le listener d'autofocus pour chaque notification de combat.

        Retourne (True, tours_restants_après_décrément) si ce tour doit être ignoré.
        Retourne (False, 0) si le compteur est épuisé ou si le pseudo n'est pas Sadida.
        Décrémente le compteur à chaque appel positif.
        """
        remaining = self._skip_counts.get(pseudo, 0)
        if remaining <= 0:
            return False, 0
        new_remaining = remaining - 1
        if new_remaining == 0:
            del self._skip_counts[pseudo]
        else:
            self._skip_counts[pseudo] = new_remaining
        return True, new_remaining

    def get_skip_remaining(self, pseudo: str) -> int:
        """Retourne le nombre de tours restants (0 si inactif)."""
        return self._skip_counts.get(pseudo, 0)

    def cancel(self, pseudo: str):
        """Annule le compteur d'un personnage spécifique."""
        self._skip_counts.pop(pseudo, None)

    def cancel_all(self):
        """Annule tous les compteurs actifs."""
        self._skip_counts.clear()

    def has_active_skips(self) -> bool:
        """True si au moins un personnage a un compteur actif."""
        return bool(self._skip_counts)


# ─── Logique Ctrl+Shift simulé ───────────────────────────────────────────────

class CtrlShiftManager:
    """
    Simule le maintien de Ctrl+Shift en mode toggle.
    • toggle(is_dofus_fg_fn) : active ou désactive — ne fait rien si Dofus
      n'est pas au premier plan lors du premier appui.
    • reapply() : relâche et ré-appuie sur la nouvelle fenêtre active ;
      à appeler juste après chaque changement de focus (next/prev/back/main).
    • release() : force le relâchement (fermeture de l'app).
    """

    def __init__(self):
        self._active = False

    @property
    def is_active(self) -> bool:
        return self._active

    def toggle(self, is_dofus_fg_fn) -> bool:
        """Retourne le nouvel état."""
        if not self._active and not is_dofus_fg_fn():
            return False
        self._active = not self._active
        if self._active:
            keyboard.press('ctrl')
            keyboard.press('shift')
        else:
            keyboard.release('shift')
            keyboard.release('ctrl')
        return self._active

    def reapply(self):
        """Relâche et ré-appuie pour cibler la nouvelle fenêtre active."""
        if not self._active:
            return
        keyboard.release('shift')
        keyboard.release('ctrl')
        keyboard.press('ctrl')
        keyboard.press('shift')

    def release(self):
        """Force le relâchement (ex. à la fermeture de l'app)."""
        if self._active:
            keyboard.release('shift')
            keyboard.release('ctrl')
            self._active = False

# ─── Logique shorten_title ─────────────────────────────────────────────────
def apply_shorten_titles(enabled: bool):
    """Renomme les fenêtres Dofus Rétro pour n'afficher que le pseudo dans la barre des tâches.
    Les fenêtres en loading pattern (ex: 'Dofus Retro') sont ignorées.
    """
    if not WIN32_OK:
        return
    def cb(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return True
        title = win32gui.GetWindowText(hwnd)
        cached = _shortened_titles.get(hwnd)
        pseudo = cached[0] if cached else extract_pseudo_from_title(title)
        if not pseudo:
            return True  # loading pattern → on touche pas
        if enabled:
            _shortened_titles[hwnd] = (pseudo, title)  # mémorise pseudo + titre original
            win32gui.SetWindowText(hwnd, pseudo)
        else:
            _shortened_titles.pop(hwnd, None)
            original = cached[1] if cached else f"{pseudo} - Dofus Retro"
            win32gui.SetWindowText(hwnd, original)
        return True
    win32gui.EnumWindows(cb, None)
