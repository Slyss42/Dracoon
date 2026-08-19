import ctypes
import time
import sys
from core.i18n import t

# Récupération des dépendances et constantes depuis config.py
from core.config import (
    _shell32, WIN32_OK, UNGROUP_OK, _IID_PS, _PROPERTYKEY, _PROPVARIANT,
    VT_LPWSTR, VT_EMPTY, TITLE_PATTERN, LOADING_PATTERN, _DOFUS_GROUP_ID,
    shortened_titles, _is_dofus_pid, _PKEY_AUMI,
)

if WIN32_OK:
    import win32gui
    import win32process
    import win32con
    import win32api

# --- Déblocage du focus-stealing Windows (remplace l'astuce "Alt") -------
_SPI_GETFOREGROUNDLOCKTIMEOUT = 0x2000
_SPI_SETFOREGROUNDLOCKTIMEOUT = 0x2001
_SPIF_UPDATEINIFILE = 0x01
_SPIF_SENDCHANGE = 0x02

_original_fg_lock_timeout: int | None = None

def unlock_foreground_switching(persist: bool = False) -> bool:
    """
    Désactive la protection anti-vol-de-focus de Windows (ForegroundLockTimeout)
    afin que SetForegroundWindow fonctionne directement, sans simuler de touche
    (Alt, etc.) et sans passer par AttachThreadInput.

    À appeler UNE SEULE FOIS, le plus tôt possible au démarrage de l'appli
    (juste après window.show(), pendant qu'elle est encore au premier plan) :
    c'est le seul moment où Windows garantit que l'appel réussit. Un échec
    n'est pas bloquant : le fallback AttachThreadInput (_attach_and_set_foreground)
    prend le relais automatiquement, sans jamais recourir à Alt.

    persist=False (par défaut) : ne modifie rien dans le registre, seulement
    le réglage vivant de la session Windows en cours (SPIF_SENDCHANGE). C'est
    donc un réglage global à la session (pas propre à ce process) tant que
    restore_foreground_lock() n'est pas appelée — pensez à l'appeler à la
    fermeture de l'appli.
    persist=True : écrit aussi la valeur dans le registre (persiste après
    un redémarrage) — à éviter sauf besoin explicite.
    """
    global _original_fg_lock_timeout
    if not WIN32_OK:
        return False
    try:
        current = ctypes.c_uint(0)
        ctypes.windll.user32.SystemParametersInfoW(
            _SPI_GETFOREGROUNDLOCKTIMEOUT, 0, ctypes.byref(current), 0)
        _original_fg_lock_timeout = current.value
    except Exception:
        _original_fg_lock_timeout = None
    flags = _SPIF_SENDCHANGE | (_SPIF_UPDATEINIFILE if persist else 0)
    try:
        ok = ctypes.windll.user32.SystemParametersInfoW(
            _SPI_SETFOREGROUNDLOCKTIMEOUT, 0, ctypes.c_void_p(0), flags)
        return bool(ok)
    except Exception:
        return False

def restore_foreground_lock() -> bool:
    """
    Remet ForegroundLockTimeout à sa valeur d'avant unlock_foreground_switching().
    À appeler à la fermeture de l'appli (dans _quit()), sinon le réglage reste
    à 0 pour le reste de la session Windows, même après que l'appli ait quitté.
    """
    global _original_fg_lock_timeout
    if not WIN32_OK or _original_fg_lock_timeout is None:
        return False
    try:
        ok = ctypes.windll.user32.SystemParametersInfoW(
            _SPI_SETFOREGROUNDLOCKTIMEOUT, 0,
            ctypes.c_void_p(_original_fg_lock_timeout), _SPIF_SENDCHANGE)
        _original_fg_lock_timeout = None
        return bool(ok)
    except Exception:
        return False

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
        Release(pstore.value)
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
    if hwnd is not None and hwnd in shortened_titles:
        return shortened_titles[hwnd][0]
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
    # Ne simule plus Alt : une fois unlock_foreground_switching() appelée au
    # démarrage, ForegroundLockTimeout=0 suffit à autoriser cet appel direct.
    try:
        win32gui.SetForegroundWindow(hwnd)
        return True
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
        if hwnd in shortened_titles:
            return True
        title = win32gui.GetWindowText(hwnd)
        return bool(TITLE_PATTERN.match(title) or LOADING_PATTERN.match(title))
    except Exception:
        return False
    
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
    
def apply_shorten_titles(enabled: bool):
    if not WIN32_OK:
        return
    def cb(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return True
        title = win32gui.GetWindowText(hwnd)
        cached = shortened_titles.get(hwnd)
        pseudo = cached[0] if cached else extract_pseudo_from_title(title)
        if not pseudo:
            return True  # loading pattern → on touche pas
        if enabled:
            shortened_titles[hwnd] = (pseudo, title)  # mémorise pseudo + titre original
            win32gui.SetWindowText(hwnd, pseudo)
        else:
            shortened_titles.pop(hwnd, None)
            original = cached[1] if cached else f"{pseudo} - Dofus Retro"
            win32gui.SetWindowText(hwnd, original)
        return True
    win32gui.EnumWindows(cb, None)

