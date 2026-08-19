import ctypes
import os
import ctypes
import io
import tempfile
from PIL import Image, ImageDraw  


# On récupère ce dont on a besoin depuis notre fichier de configuration centralisé
from core.config import WIN32_OK, portraits_dir
if WIN32_OK:
    import win32gui
    import win32process
    import win32api

_original_icons: dict[int, int] = {}  # hwnd → hicon sauvegardé avant toute modification

def _save_original_icon(hwnd: int) -> None:
    """Appelé une seule fois par hwnd, au premier set_window_icon."""
    if hwnd in _original_icons:
        return
    hicon = ctypes.windll.user32.SendMessageW(hwnd, 0x007F, 1, 0)  # WM_GETICON ICON_BIG
    if not hicon:
        hicon = ctypes.windll.user32.SendMessageW(hwnd, 0x007F, 0, 0)  # ICON_SMALL
    if not hicon:
        hicon = ctypes.windll.user32.GetClassLongPtrW(hwnd, -14)        # GCL_HICON
    if hicon:
        _original_icons[hwnd] = hicon

def _restore_original_icon(hwnd: int) -> bool:
    """Remet l'icône sauvegardée. Retourne False si rien n'avait été sauvegardé."""
    if not WIN32_OK:
        return False
    try:
        hicon = _original_icons.pop(hwnd, None)
        if hicon:
            win32gui.SendMessage(hwnd, 0x0080, 0, hicon)
            win32gui.SendMessage(hwnd, 0x0080, 1, hicon)
            return True
        return False
    except Exception:
        return False

def restore_all_original_icons() -> None:
    """Remet toutes les icônes originales — appelé à la fermeture de Dracoon."""
    for hwnd in list(_original_icons.keys()):
        _restore_original_icon(hwnd)


def set_window_icon(hwnd: int, color_hex: str | None, portrait: str | None) -> bool:
    if not WIN32_OK:
        return False
    if color_hex is None and portrait is None:
        return _restore_original_icon(hwnd)
    try:

        _save_original_icon(hwnd)  # ← sauvegarde avant toute modification

        SIZE = 48
        img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # ── Anneau coloré (contour seulement, pas de fond plein) ──────
        if color_hex:
            r = int(color_hex[0:2], 16)
            g = int(color_hex[2:4], 16)
            b = int(color_hex[4:6], 16)
            BORDER = 4
            draw.ellipse([0, 0, SIZE - 1, SIZE - 1],
                         outline=(r, g, b, 255), width=BORDER)

        # ── Portrait clipé dans le cercle ────────────────────────────
        if portrait:
            portrait_path = os.path.join(portraits_dir(), f"{portrait}.png")
            if os.path.exists(portrait_path):
                try:
                    overlay = Image.open(portrait_path).convert("RGBA")
                    inner = SIZE - 8
                    overlay = overlay.resize((inner, inner), Image.LANCZOS)
                    mask = Image.new("L", (inner, inner), 0)
                    ImageDraw.Draw(mask).ellipse([0, 0, inner - 1, inner - 1], fill=255)
                    img.paste(overlay, (4, 4), mask)
                except Exception:
                    pass
        elif not color_hex:
            return _restore_original_icon(hwnd)

        # ── Sauvegarder en .ico et appliquer ────────────────────────
        buf = io.BytesIO()
        img.save(buf, format="ICO", sizes=[(48, 48), (32, 32), (16, 16)])
        buf.seek(0)

        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".ico") as tmp:
                tmp.write(buf.read())
                tmp_path = tmp.name
            hicon = ctypes.windll.user32.LoadImageW(
                None, tmp_path, 1, 0, 0, 0x00000010 | 0x00000040
            )
            if hicon:
                win32gui.SendMessage(hwnd, 0x0080, 0, hicon)
                win32gui.SendMessage(hwnd, 0x0080, 1, hicon)
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass

        return bool(hicon)
    except Exception:
        return False