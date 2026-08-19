import ctypes
import ctypes.wintypes as wt
import time
import threading
from core.config import TITLE_PATTERN, LOADING_PATTERN, shortened_titles

# ─── Logique Mode Déplacement ─────────────────────────────────────────────────

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
                                hwnd_root in shortened_titles or TITLE_PATTERN.match(title) or LOADING_PATTERN.match(title)
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