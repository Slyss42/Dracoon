from core.config import KEYBOARD_OK, WIN32_OK
import keyboard

if WIN32_OK:
    import win32con
    import win32api

import queue
import threading

_action_queue: "queue.SimpleQueue" = queue.SimpleQueue()

def _action_worker():
    """Thread dédié qui exécute les callbacks de raccourcis sans bloquer keyboard."""
    while True:
        fn = _action_queue.get()
        try:
            fn()
        except Exception:
            pass

_worker_thread = threading.Thread(target=_action_worker, daemon=True)
_worker_thread.start()

def enqueue_action(fn):
    """Poste fn dans la queue ; exécuté par _worker_thread, hors thread keyboard."""
    _action_queue.put(fn)
    
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