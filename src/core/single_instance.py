"""
single_instance.py — Instance unique pour Dracoon (Windows)
=============================================================

Utilise un mutex nommé Windows (objet noyau natif) pour garantir qu'une
seule instance de Dracoon tourne à la fois. Aucune écriture réseau,
aucune mémoire partagée : le mutex est géré entièrement par le noyau
Windows, et libéré automatiquement par l'OS si le process crash.

Nécessite pywin32 (déjà utilisé ailleurs dans Dracoon via win32gui).

Utilisation dans Main.py :

    from single_instance import acquire_single_instance

    if not acquire_single_instance(window_title="Dracoon"):
        sys.exit(0)  # une instance tourne déjà, elle a été remise au premier plan

    # ... lancer l'app Qt normalement ...
    # (garder une référence globale au mutex pour qu'il ne soit pas
    #  libéré par le garbage collector avant la fin du process)
"""

import ctypes
import logging
import win32event
import win32api
import win32gui
import win32con
import win32process
import winerror

_MUTEX_NAME = r"Dracoon_SingleInstance_Mutex"

# Même logger que le reste de l'app (voir core/config.py::setup_file_logger).
# logging.getLogger(...) renvoie toujours la même instance pour un nom donné,
# donc pas besoin de le passer en paramètre : tant que setup_file_logger()
# a été appelée une fois quelque part (avec ou après cet appel), les
# handlers sont déjà en place et les messages partent dans dracoon.log.
_logger = logging.getLogger("Dracoon")

# Référence globale : garder le handle vivant tant que l'app tourne,
# sinon le mutex est libéré dès que la variable locale sort de portée.
_mutex_handle = None


def acquire_single_instance(window_title: str = "Dracoon") -> bool:
    """Tente de devenir l'instance principale de Dracoon.

    Retourne True si c'est la seule instance (on peut continuer le
    lancement). Retourne False si une instance tourne déjà : sa fenêtre
    est remise au premier plan et l'appelant doit quitter immédiatement.
    """
    global _mutex_handle

    _mutex_handle = win32event.CreateMutex(None, False, _MUTEX_NAME)
    already_running = (win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS)

    if already_running:
        _logger.warning("single_instance: tentative de lancement bloquée (mutex '%s' déjà détenu)", _MUTEX_NAME)
        _bring_existing_window_to_front(window_title)
        return False

    return True


def _bring_existing_window_to_front(window_title: str) -> None:
    # Seule la marque en début de titre ("Dracoon") est stable : le reste
    # ("Dracoon - Dofus Rétro Window Manager") est un sous-titre traduit qui
    # change selon la langue active. Une correspondance exacte via
    # FindWindow() échoue donc dès que la langue courante diffère de celle
    # utilisée au moment où window_title a été construit. On ne garde que
    # le préfixe avant " - " et on cherche par préfixe sur tous les
    # top-level windows.
    prefix = window_title.split(" - ", 1)[0].strip()
    hwnd = _find_window_by_prefix(prefix)
    if not hwnd:
        _logger.warning(
            "single_instance: mutex détecté mais aucune fenêtre commençant par '%s' introuvable "
            "(instance en cours de démarrage ?) — fermeture silencieuse.",
            prefix,
        )
        return  # fenêtre pas trouvée, on ne bloque pas pour autant

    # SW_RESTORE couvre à la fois le cas "minimisé" et le cas "caché
    # dans le tray" (la fenêtre n'a alors pas WS_VISIBLE) : dans les
    # deux cas elle réapparaît normalement à l'écran.
    if not win32gui.IsWindowVisible(hwnd) or win32gui.IsIconic(hwnd):
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)

    ok = win32gui.SetForegroundWindow(hwnd)
    if not ok:
        ok = _force_foreground(hwnd)

    if ok:
        _logger.info("single_instance: fenêtre existante remise au premier plan (hwnd=%s)", hwnd)
    else:
        _logger.warning(
            "single_instance: échec de la remise au premier plan (hwnd=%s), "
            "même après AttachThreadInput — la fenêtre a été restaurée mais "
            "reste probablement derrière les autres.", hwnd
        )


def _find_window_by_prefix(prefix: str):
    """
    Renvoie le handle de la première fenêtre de premier niveau dont le
    titre commence par `prefix`, ou None si aucune ne correspond.

    On énumère plutôt que d'utiliser FindWindow() (correspondance exacte
    uniquement) car le titre complet inclut un sous-titre traduit qui
    varie selon la langue active — voir _bring_existing_window_to_front().
    On n'exclut pas les fenêtres invisibles : une instance réduite dans le
    tray n'a pas WS_VISIBLE mais doit quand même être trouvée.
    """
    matches: list[int] = []

    def _on_window(hwnd, _extra):
        title = win32gui.GetWindowText(hwnd)
        if title.startswith(prefix):
            matches.append(hwnd)
        return True  # continuer l'énumération

    win32gui.EnumWindows(_on_window, None)
    return matches[0] if matches else None


def _force_foreground(hwnd) -> bool:
    """Contournement de la restriction anti-vol-de-focus de Windows.

    SetForegroundWindow échoue silencieusement si notre process n'a pas
    reçu d'input récent. En attachant temporairement notre thread à celui
    qui détient actuellement le focus, Windows nous laisse passer.
    Cf. https://learn.microsoft.com/windows/win32/api/winuser/nf-winuser-setforegroundwindow
    """
    user32 = ctypes.windll.user32
    current_thread = win32api.GetCurrentThreadId()
    fg_hwnd = win32gui.GetForegroundWindow()
    fg_thread, _ = win32process.GetWindowThreadProcessId(fg_hwnd) if fg_hwnd else (0, 0)

    attached = False
    try:
        if fg_thread and fg_thread != current_thread:
            attached = bool(user32.AttachThreadInput(current_thread, fg_thread, True))

        win32gui.SetForegroundWindow(hwnd)
        return win32gui.GetForegroundWindow() == hwnd
    except Exception:
        _logger.exception("single_instance: erreur pendant AttachThreadInput (hwnd=%s)", hwnd)
        return False
    finally:
        if attached:
            user32.AttachThreadInput(current_thread, fg_thread, False)


if __name__ == "__main__":
    if not acquire_single_instance():
        print("Une instance de Dracoon tourne déjà. Fermeture.")
    else:
        print("Instance principale active.")
        input("Appuie sur Entrée pour quitter...\n")
