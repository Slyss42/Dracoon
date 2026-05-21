import asyncio
import threading
import tkinter as tk
import webbrowser
from tkinter import scrolledtext
from datetime import datetime

from logic import (
    LOADING_PATTERN, WIN32_OK, WINSDK_OK, KEYBOARD_OK, TRAY_OK,
    ICON_PATH, TITLE_PATTERN, NOTIF_TYPES,
    APP_VERSION, APP_GITHUB, APP_TWITTER, APP_LEGAL,
    get_dofus_windows, focus_window, focus_dofus_window,
    list_dofus_windows, is_dofus_foreground,
    reorder_with_ungroup_regroup,
    _load_config, _save_config, _build_config,
    _unhook_all, _release_modifier_keys,
    _encode_af_overrides, _decode_af_overrides,
    extract_pseudo_from_title, _is_dofus_pid,
)
import json
import os

try:
    import win32gui, win32con, win32api, win32process
except Exception:
    pass

try:
    import winsdk.windows.ui.notifications.management as winman
    import winsdk.windows.ui.notifications as winnot
except Exception:
    pass

try:
    import keyboard
except Exception:
    pass

try:
    import pystray
    from PIL import Image, ImageDraw
except Exception:
    pass


# ══════════════════════════════════════════════════════════════════════════════
# STYLES
# ══════════════════════════════════════════════════════════════════════════════

class UIStyles:
    class Titre:
        font      = ("Segoe UI", 14, "bold")
        padx      = 16

    class OngletActif:
        font      = ("Segoe UI", 11, "bold")

    class Bouton:
        font_standard         = ("Segoe UI", 11)
        padx_standard         = 18
        pady_standard         = 9

        font_principal        = ("Segoe UI", 11, "bold")
        padx_principal        = 16
        pady_principal        = 7

        font_type_notif       = ("Segoe UI", 11, "bold")
        padx_type_notif       = 10
        pady_type_notif       = 4

        font_type_notifnobold = ("Segoe UI", 11)
        padx_type_notifnobold = 10
        pady_type_notifnobold = 4

        font_petit            = ("Segoe UI", 11)
        padx_petit            = 12
        pady_petit            = 5

    class EnTete:
        font       = ("Segoe UI", 12, "bold")
        pady_titre = (14, 2)
        pady_sous  = (0, 10)

    class Info:
        font = ("Segoe UI", 11)


# ══════════════════════════════════════════════════════════════════════════════
# APPLICATION
# ══════════════════════════════════════════════════════════════════════════════

class App(tk.Tk):
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

    NO_SHORTCUT = None

    # ══════════════════════════════════════════════════════════════════════
    # INIT
    # ══════════════════════════════════════════════════════════════════════

    def __init__(self):
        super().__init__()
        self.title("Dracoon - Gestionnaire de fenêtres Dofus Rétro")
        self.configure(bg=self.BG)
        self.resizable(True, True)
        self.geometry("740x810")
        self.minsize(500, 460)

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
        self._window_snapshot: dict[int, str] = {}  # hwnd → titre, pour détecter les changements

        raw_next = cfg.get("shortcut_next", "ctrl+right")
        raw_prev = cfg.get("shortcut_prev", "ctrl+left")
        raw_back = cfg.get("shortcut_back", None)
        raw_main = cfg.get("shortcut_main", None)
        self._shortcut_next: str | None = raw_next
        self._shortcut_prev: str | None = raw_prev
        self._shortcut_back: str | None = raw_back
        self._shortcut_main: str | None = raw_main

        _raw_main = cfg.get("char_main", "") or None
        self._char_main: str | None = _raw_main

        self._char_af_overrides: dict[str, dict[str, bool]] = _decode_af_overrides(
            cfg.get("char_af_overrides", "")
        )

        self._prev_hwnd: int | None = None

        _raw_skip = cfg.get("char_skip_names", "[]") or "[]"
        try:
            self._char_skip_names: set[str] = set(json.loads(_raw_skip))
        except Exception:
            self._char_skip_names: set[str] = set()

        self._welcome_shown: bool = cfg.get("welcome_shown", "0") == "1"

        self.remove_notif_var       = tk.BooleanVar(value=cfg.get("remove_notif",       "1") == "1")
        self.maximize_on_launch_var = tk.BooleanVar(value=cfg.get("maximize_on_launch", "1") == "1")

        self._build_ui()

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

        self.protocol("WM_DELETE_WINDOW", self._quit)
        self.bind("<B1-Motion>",       self._drag_motion)
        self.bind("<ButtonRelease-1>", self._drag_end)

        if KEYBOARD_OK:
            self._apply_shortcuts(silent=True)

        self.refresh_characters()

        if not self._welcome_shown:
            self.after(200, self._show_welcome_popup)

    # ══════════════════════════════════════════════════════════════════════
    # QUIT
    # ══════════════════════════════════════════════════════════════════════

    def _quit(self):
        self._persist_config()
        _unhook_all()
        _release_modifier_keys()
        self._running = False
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._tray_icon:
            try:
                self._tray_icon.stop()
            except Exception:
                pass
        self.destroy()
        os._exit(0)

    # ══════════════════════════════════════════════════════════════════════
    # POPUP DE BIENVENUE
    # ══════════════════════════════════════════════════════════════════════

    def _show_welcome_popup(self):
        TIMER_SECONDS = 30

        popup = tk.Toplevel(self)
        popup.title("Bienvenue dans Dracoon")
        popup.configure(bg=self.BG)
        popup.resizable(False, False)
        popup.grab_set()
        popup.focus_force()

        self.update_idletasks()
        pw, ph = 580, 560
        rx = self.winfo_rootx() + (self.winfo_width()  - pw) // 2
        ry = self.winfo_rooty() + (self.winfo_height() - ph) // 2
        popup.geometry(f"{pw}x{ph}+{rx}+{ry}")

        FONT_TITRE   = ("Segoe UI", 14, "bold")
        FONT_SECTION = ("Segoe UI", 12, "bold")
        FONT_BODY    = ("Segoe UI", 11)
        FONT_BTN     = ("Segoe UI", 12, "bold")
        WRAPLENGTH   = 500

        pad = tk.Frame(popup, bg=self.BG, padx=28, pady=22)
        pad.pack(fill="both", expand=True)

        tk.Label(pad, text="Bienvenue dans Dracoon",
                 bg=self.BG, fg=self.ACCENT,
                 font=FONT_TITRE).pack(anchor="w", pady=(0, 16))

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
                           fg=self.BLUE, font=FONT_BODY, cursor="hand2")
            lbl.pack(side="left")
            lbl.bind("<Button-1>", lambda e, u=url: webbrowser.open(u))
            lbl.bind("<Enter>",    lambda e: lbl.config(fg=self.ACCENT))
            lbl.bind("<Leave>",    lambda e: lbl.config(fg=self.BLUE))

        _link(card_links, "⌨", APP_GITHUB)
        _link(card_links, "🐦", APP_TWITTER)

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

        tk.Checkbutton(pad, text="Ne plus afficher ce message",
                       variable=dont_show_var,
                       bg=self.BG, fg=self.GRAY,
                       selectcolor=self.CARD,
                       activebackground=self.BG, activeforeground=self.TEXT,
                       font=FONT_BODY).pack(anchor="w")

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

        def _on_close_attempt():
            if close_btn["state"] == "normal":
                _close()

        popup.protocol("WM_DELETE_WINDOW", _on_close_attempt)

    # ══════════════════════════════════════════════════════════════════════
    # TRAY
    # ══════════════════════════════════════════════════════════════════════

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

        try:
            from PIL import Image as _PilImg, ImageTk as _PilImgTk
            _raw = _PilImg.open(ICON_PATH).convert("RGBA").resize((32, 32), _PilImg.LANCZOS)
            self._header_icon = _PilImgTk.PhotoImage(_raw)
            tk.Label(header, image=self._header_icon,
                     bg=self.PANEL).pack(side="left", padx=(16, 4))
        except Exception:
            pass

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
                            ("parametres",  "Paramètres"),
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
        self._build_tab_parametres()
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

        top = tk.Frame(f, bg=self.BG, pady=12)
        top.pack(side="top", fill="x", padx=16)

        left = tk.Frame(top, bg=self.BG)
        left.pack(side="left", fill="x", expand=True)
        tk.Label(left, text="Ordre d'initiative", bg=self.BG,
                 fg=self.TEXT, font=self.S.EnTete.font).pack(anchor="w")
        tk.Label(left, text="Drag & drop pour réordonner", bg=self.BG,
                 fg=self.GRAY, font=self.S.Info.font).pack(anchor="w")

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
        win_map   = {h: p for h, p in windows}
        known     = set(win_map.keys())
        new_order = [(h, win_map[h]) for h, _ in self._char_order if h in known]
        existing  = {h for h, _ in new_order}
        for h, p in windows:
            if h not in existing:
                new_order.append((h, p))
        self._char_order = new_order
        self._rebuild_char_list()
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

        self.after(10, self._update_row_tops)

    def _update_row_tops(self):
        self._row_tops = []
        for w in self._char_inner.winfo_children():
            if w.winfo_exists() and w.winfo_height() > 1:
                self._row_tops.append(w.winfo_y())
                self._row_height = w.winfo_height() + 6
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

        skip_btn = tk.Button(
            row, relief="flat", cursor="hand2",
            font=self.S.Bouton.font_petit,
            padx=self.S.Bouton.padx_petit, pady=self.S.Bouton.pady_petit,
        )
        
        self._style_skip_btn(skip_btn, active=(pseudo in self._char_skip_names))
        skip_btn.config(command=lambda b=skip_btn, p=pseudo: self._toggle_char_skip(p, b))
        skip_btn.pack(side="right", padx=(0, 4))

        main_btn = tk.Button(
            row, relief="flat", cursor="hand2",
            font=self.S.Bouton.font_petit,
            padx=self.S.Bouton.padx_petit, pady=self.S.Bouton.pady_petit,
        )
        
        self._style_main_btn(main_btn, active=(pseudo == self._char_main))
        main_btn.config(command=lambda b=main_btn, p=pseudo: self._toggle_char_main(p, b))
        main_btn.pack(side="right", padx=(0, 2))

        drag_targets = [row] + [w for w in row.winfo_children()
                                if w is not skip_btn and w is not main_btn]
        for w in drag_targets:
            w.bind("<ButtonPress-1>", lambda e, i=idx: self._drag_start(i, e))

    def _drag_start(self, idx: int, event):
        self._drag_idx = idx
        if not self._row_tops:
            self._update_row_tops()
        self._rebuild_char_list(highlight_idx=idx)

    def _drag_motion(self, event):
        if self._drag_idx is None or not self._row_tops:
            return
        try:
            inner_y = (event.y_root
                       - self._char_inner.winfo_rooty()
                       + self._char_canvas.canvasy(0))
        except Exception:
            return

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
        mapping = {
            "next": ("_shortcut_next", "_next_entry"),
            "prev": ("_shortcut_prev", "_prev_entry"),
            "main": ("_shortcut_main", "_main_entry"),
            "back": ("_shortcut_back", "_back_entry"),
        }
        attr, entry_attr = mapping[which]
        setattr(self, attr, self.NO_SHORTCUT)
        entry = getattr(self, entry_attr)
        entry.delete(0, "end")
        entry.insert(0, "Aucun")
        entry.config(fg=self.GRAY)
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
                if which == "next":   self._shortcut_next = combo
                elif which == "prev": self._shortcut_prev = combo
                elif which == "main": self._shortcut_main = combo
                else:                 self._shortcut_back = combo
                entry.unbind("<KeyPress>")
                self.focus()
                self._apply_shortcuts()
            return "break"

        entry.bind("<KeyPress>", on_key)

    def _apply_shortcuts(self, silent: bool = False):
        if not KEYBOARD_OK:
            return
        try:
            _unhook_all()
            if self._shortcut_next: keyboard.add_hotkey(self._shortcut_next, self._focus_next)
            if self._shortcut_prev: keyboard.add_hotkey(self._shortcut_prev, self._focus_prev)
            if self._shortcut_back: keyboard.add_hotkey(self._shortcut_back, self._focus_back)
            if self._shortcut_main: keyboard.add_hotkey(self._shortcut_main, self._focus_main)
            self._persist_config()
        except Exception:
            pass

    def _focus_main(self):
        if not is_dofus_foreground() or not self._char_main:
            return
        if WIN32_OK:
            try:
                fg = win32gui.GetForegroundWindow()
                if fg:
                    self._prev_hwnd = fg
            except Exception:
                pass
        focus_dofus_window(self._char_main)

    def _focus_next(self):
        if not is_dofus_foreground():
            return

        hwnd = win32gui.GetForegroundWindow()
        title = win32gui.GetWindowText(hwnd)

        if TITLE_PATTERN.match(title):
            # état stable → immédiat
            self._cycle(+1)
        else:
            # loading → exécuté dans la boucle UI
            self.after(0, lambda: self._cycle(+1))

    def _focus_prev(self):
        if not is_dofus_foreground():
            return

        hwnd = win32gui.GetForegroundWindow()
        title = win32gui.GetWindowText(hwnd)

        if TITLE_PATTERN.match(title):
            # état stable → immédiat
            self._cycle(-1)
        else:
            # loading → exécuté dans la boucle UI
            self.after(0, lambda: self._cycle(-1))        

    def _focus_back(self):
        if not is_dofus_foreground():
            return
        if self._prev_hwnd and WIN32_OK:
            try:
                if win32gui.IsWindow(self._prev_hwnd):
                    focus_window(self._prev_hwnd)
                    return
            except Exception:
                pass
        self._cycle(-1)

    # ── Persistance centralisée ───────────────────────────────────────────────

    def _cycle(self, direction: int):
        if not self._char_order:
            self.refresh_characters()
        if not self._char_order:
            return

        cycle_order = [(i, h, p) for i, (h, p) in enumerate(self._char_order)
                       if p not in self._char_skip_names]
        if not cycle_order:
            cycle_order = [(i, h, p) for i, (h, p) in enumerate(self._char_order)]

        fg = win32gui.GetForegroundWindow() if WIN32_OK else None
        if fg:
            self._prev_hwnd = fg

        cur_pos = next((pos for pos, (_, h, _) in enumerate(cycle_order) if h == fg), None)
        new_pos = 0 if cur_pos is None else (cur_pos + direction) % len(cycle_order)
        focus_window(cycle_order[new_pos][1])

    def _persist_config(self):
        _save_config(_build_config(
            self._shortcut_next, self._shortcut_prev, self._shortcut_back,
            self._char_af_overrides, self._shortcut_main, self._char_main,
            self._welcome_shown, self._char_skip_names,
            self.remove_notif_var.get(),
            self.maximize_on_launch_var.get(),
        ))

    # ── Gestion des exclusions de roulement ───────────────────────────────────

    def _toggle_char_skip(self, pseudo: str, btn: tk.Button):
        if pseudo in self._char_skip_names:
            self._char_skip_names.discard(pseudo)
            self._style_skip_btn(btn, active=False)
        else:
            self._char_skip_names.add(pseudo)
            self._style_skip_btn(btn, active=True)
        self._persist_config()

    def _style_skip_btn(self, btn: tk.Button, active: bool):
        if active:
            btn.config(text="⊗  Exclure des raccourcis", bg="#2d1515",
                       fg=self.RED, activebackground="#2d1515", activeforeground=self.RED)
        else:
            btn.config(text="○  Exclure des raccourcis", bg="#252b3b",
                       fg=self.GRAY, activebackground="#252b3b", activeforeground=self.GRAY)

    def _toggle_char_main(self, pseudo: str, btn: tk.Button):
        self._char_main = None if self._char_main == pseudo else pseudo
        self._persist_config()
        self._rebuild_char_list()

    def _style_main_btn(self, btn: tk.Button, active: bool):
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

        top = tk.Frame(f, bg=self.BG, pady=12)
        top.pack(fill="x", padx=16)
        tk.Label(top, text="Switch automatique de fenêtre", bg=self.BG,
                 fg=self.TEXT, font=self.S.EnTete.font).pack(anchor="w")
        tk.Label(top, text="Choisissez quand passer la fenêtre au premier plan",
                 bg=self.BG, fg=self.GRAY, font=self.S.Info.font).pack(anchor="w")

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

        ROW1 = [("combat",  "⚔  Combat"), ("echange", "🔄  Échange"),
                ("groupe",  "👥  Groupe"), ("craft",   "🔨  Craft")]
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

        f_opt = tk.Frame(f, bg=self.BG)
        f_opt.pack(fill="x", padx=16, pady=(10, 0))

        tk.Frame(f, bg=self.CARD, height=1).pack(fill="x", padx=16, pady=(10, 0))


        per_top = tk.Frame(f, bg=self.BG, pady=8)
        per_top.pack(fill="x", padx=16)
        tk.Label(per_top, text="Personnalisation par personnage",
                 bg=self.BG, fg=self.TEXT, font=self.S.EnTete.font).pack(side="left")

        tk.Label(f, text="Cliquez sur une icône pour désactiver ce type pour ce personnage uniquement",
                 bg=self.BG, fg=self.GRAY, font=self.S.Info.font).pack(anchor="w", padx=16)

        self._af_chars_container = tk.Frame(f, bg=self.BG)
        self._af_chars_container.pack(fill="x", padx=16, pady=(4, 0))

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

        self._stats_outer = tk.Frame(f, bg=self.BG)
        stats = tk.Frame(self._stats_outer, bg=self.BG, pady=8)
        stats.pack(fill="x", padx=16)
        self.lbl_notifs  = self._stat(stats, "Notifications lues", "0")
        self.lbl_matches = self._stat(stats, "Patterns trouvés",   "0")
        self.lbl_focus   = self._stat(stats, "Focus réussis",      "0")
        self.lbl_last    = self._stat(stats, "Dernier joueur",     "—")

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
        if not self.type_vars[type_key].get():
            return False
        for overrides in self._char_af_overrides.values():
            if overrides.get(type_key) is False:
                return False
        return True

    def _update_global_btn_style(self, type_key: str):
        btn = self.type_btns[type_key]
        if self._is_type_fully_active(type_key):
            btn.config(bg=self.ACCENT, fg=self.BG,
                       activebackground=self.ACCENT, activeforeground=self.BG)
        else:
            btn.config(bg=self.CARD, fg=self.GRAY,
                       activebackground=self.CARD, activeforeground=self.GRAY)

    def _toggle_type(self, key: str):
        fully_active = self._is_type_fully_active(key)
        if fully_active:
            self.type_vars[key].set(False)
            for overrides in self._char_af_overrides.values():
                overrides.pop(key, None)
            self._char_af_overrides = {p: o for p, o in self._char_af_overrides.items() if o}
        else:
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

        if hasattr(self, "_af_chars_container"):
            self._rebuild_af_char_list()

    # ── AutoFocus per-personnage ──────────────────────────────────────────


    def _rebuild_af_char_list(self):
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
        override = self._char_af_overrides.get(pseudo)

        card = tk.Frame(self._af_chars_container, bg=self.CARD, padx=10, pady=5)
        card.pack(fill="x", pady=2)

        tk.Label(card, text=pseudo, bg=self.CARD,
                 fg=self.TEXT, font=self.S.Bouton.font_principal,
                 anchor="w").pack(side="left", padx=(0, 10))

        btn_frame = tk.Frame(card, bg=self.CARD)
        btn_frame.pack(side="right")

        TYPE_ICONS = [("combat", "⚔"), ("echange", "🔄"), ("groupe", "👥"), ("craft", "🔨"),
                      ("mp", "💬"), ("defi", "🏆"), ("pvp", "🛡")]
        for type_key, icon in TYPE_ICONS:
            locally_disabled = (override is not None and override.get(type_key) is False)
            is_active = self.type_vars[type_key].get() and not locally_disabled

            btn = tk.Button(btn_frame, text=icon,
                            font=self.S.Bouton.font_type_notifnobold,
                            padx=5, pady=2, relief="flat", cursor="hand2")
            self._style_af_char_btn(btn, is_active)
            btn.config(command=lambda p=pseudo, k=type_key, b=btn:
                       self._toggle_char_af_type(p, k, b))
            btn.pack(side="left", padx=1)

    def _style_af_char_btn(self, btn: tk.Button, is_active: bool):
        fg = self.ACCENT if is_active else self.GRAY
        btn.config(bg="#252b3b", fg=fg,
                   activebackground="#252b3b", activeforeground=fg)

    def _toggle_char_af_type(self, pseudo: str, type_key: str, _btn: tk.Button):
        override = self._char_af_overrides.get(pseudo)
        locally_disabled = (override is not None and override.get(type_key) is False)
        is_active = self.type_vars[type_key].get() and not locally_disabled

        if is_active:
            if override is None:
                override = {}
                self._char_af_overrides[pseudo] = override
            override[type_key] = False
        elif locally_disabled:
            del override[type_key]
            if not override:
                del self._char_af_overrides[pseudo]

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

    def _watch_windows(self):
        """Thread de surveillance : détecte toute modification des fenêtres Dofus
        (ouverture, fermeture, changement de titre) et rafraîchit automatiquement."""
        import time
        while self._running:
            try:
                current = {}
                def cb(hwnd, _):
                    if not win32gui.IsWindowVisible(hwnd):
                        return True
                    try:
                        _, pid = win32process.GetWindowThreadProcessId(hwnd)
                        if not _is_dofus_pid(pid):
                            return True
                    except Exception:
                        return True
                    current[hwnd] = win32gui.GetWindowText(hwnd)
                    return True
                win32gui.EnumWindows(cb, None)
                if current != self._window_snapshot:
                    # Détecter les nouveaux hwnds
                    new_hwnds = set(current.keys()) - set(self._window_snapshot.keys())
                    for hwnd in new_hwnds:
                        try:
                            if self.maximize_on_launch_var.get():
                                win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
                        except Exception:
                            pass
                    self._window_snapshot = current
                    self.after(0, self.refresh_characters)
            except Exception:
                pass
            time.sleep(0.3)

    def _start(self):
        if not WIN32_OK or not WINSDK_OK:
            self.log_msg("Impossible : dépendances manquantes.", "error")
            return
        self._running = True
        self._set_status("AutoFocus actif", self.GREEN)
        self.log_msg("Écoute démarrée.", "ok")
        threading.Thread(target=self._run_async_loop, daemon=True).start()
        threading.Thread(target=self._watch_windows,  daemon=True).start()

    def _stop(self):
        self._running = False
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
        self._set_status("AutoFocus inactif", self.GRAY)
        self.log_msg("Écoute arrêtée.", "dim")

    def _set_status(self, text: str, color: str):
        pass

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
                        pass
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
                        # ── Suppression bannière conditionnelle ───────────────
                        if self.remove_notif_var.get():
                            try:
                                listener.remove_notification(notif.id)
                            except Exception:
                                pass
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

                            if not self.type_vars[matched_type].get():
                                self.after(0, self.log_msg,
                                    f"[{matched_type}] ignoré (désactivé global) — {pseudo}", "dim")
                                continue

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
                pass

    # ══════════════════════════════════════════════════════════════════════
    # ONGLET PARAMETRES
    # ══════════════════════════════════════════════════════════════════════

    def _build_tab_parametres(self):
        f = tk.Frame(self._content, bg=self.BG)
        self._tab_frames["parametres"] = f

        top = tk.Frame(f, bg=self.BG, pady=12)
        top.pack(fill="x", padx=16)
        tk.Label(top, text="Paramètres", bg=self.BG,
                fg=self.TEXT, font=self.S.EnTete.font).pack(anchor="w")
        tk.Label(top, text="Configuration générale de l'application",
                bg=self.BG, fg=self.GRAY, font=self.S.Info.font).pack(anchor="w")

        def _param_row(parent, label, sublabel, variable):
            card = tk.Frame(parent, bg=self.CARD, padx=14, pady=12, cursor="hand2")
            card.pack(fill="x", padx=16, pady=4)
            info = tk.Frame(card, bg=self.CARD, cursor="hand2")
            info.pack(side="left", fill="x", expand=True)
            tk.Label(info, text=label, bg=self.CARD,
                    fg=self.TEXT, font=self.S.Bouton.font_principal, cursor="hand2").pack(anchor="w")
            if sublabel:
                tk.Label(info, text=sublabel, bg=self.CARD,
                        fg=self.GRAY, font=self.S.Info.font, cursor="hand2").pack(anchor="w")

            cb_lbl = tk.Label(card, font=("Segoe UI", 18), bg=self.CARD, cursor="hand2")
            cb_lbl.pack(side="right")

            def _refresh():
                cb_lbl.config(text="☑" if variable.get() else "☐",
                            fg=self.ACCENT if variable.get() else self.GRAY)

            def _toggle(e):
                variable.set(not variable.get())
                _refresh()
                return "break"

            _refresh()
            for w in [card, info, cb_lbl] + list(info.winfo_children()):
                w.bind("<Button-1>", _toggle)

        _param_row(f,
                "Supprimer la bannière dès son apparition",
                "Libère la zone de clic en bas à droite immédiatement",
                self.remove_notif_var)
        
        _param_row(f,
           "Agrandir les fenêtres Dofus au lancement",
           "Nécessite de lancer Dracoon avant les comptes",
           self.maximize_on_launch_var)

    # ══════════════════════════════════════════════════════════════════════
    # ONGLET INFO
    # ══════════════════════════════════════════════════════════════════════

    def _build_tab_info(self):
        f = tk.Frame(self._content, bg=self.BG)
        self._tab_frames["info"] = f

        top = tk.Frame(f, bg=self.BG, pady=12)
        top.pack(fill="x", padx=16)
        tk.Label(top, text="À propos", bg=self.BG,
                 fg=self.TEXT, font=self.S.EnTete.font).pack(anchor="w")
        tk.Label(top, text="Informations sur l'application et mentions légales",
                 bg=self.BG, fg=self.GRAY, font=self.S.Info.font).pack(anchor="w")

        card_ver = tk.Frame(f, bg=self.CARD, padx=16, pady=12)
        card_ver.pack(fill="x", padx=16, pady=(4, 2))
        row_ver = tk.Frame(card_ver, bg=self.CARD)
        row_ver.pack(fill="x")
        tk.Label(row_ver, text="Version", bg=self.CARD,
                 fg=self.GRAY, font=self.S.Info.font).pack(side="left")
        tk.Label(row_ver, text=APP_VERSION, bg=self.CARD,
                 fg=self.ACCENT, font=self.S.Bouton.font_principal).pack(side="right")

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
                           fg=self.BLUE, font=self.S.Info.font, cursor="hand2")
            lbl.pack(side="left")
            lbl.bind("<Button-1>", lambda e, u=url: webbrowser.open(u))
            lbl.bind("<Enter>",    lambda e: lbl.config(fg=self.ACCENT))
            lbl.bind("<Leave>",    lambda e: lbl.config(fg=self.BLUE))

        _link_row(card_links, "⌨", "GitHub : https://github.com/Slyss42/Dracoon", APP_GITHUB)
        _link_row(card_links, "🐦", "Twitter/X : https://x.com/Slyss42", APP_TWITTER)

        card_legal = tk.Frame(f, bg=self.CARD, padx=16, pady=12)
        card_legal.pack(fill="x", padx=16, pady=2)
        tk.Label(card_legal, text="Mentions légales", bg=self.CARD,
                 fg=self.GRAY, font=self.S.Info.font).pack(anchor="w", pady=(0, 6))
        tk.Label(card_legal, text=APP_LEGAL, bg=self.CARD,
                 fg=self.TEXT, font=self.S.Info.font,
                 justify="left", wraplength=620).pack(anchor="w")

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
        self._shortcut_next     = None
        self._shortcut_prev     = None
        self._shortcut_back     = None
        self._shortcut_main     = None
        self._char_main         = None
        self._char_skip_names   = set()
        self._char_af_overrides = {}
        self._welcome_shown     = False

        _unhook_all()
        self._persist_config()
        self._rebuild_char_list()

        for entry in [self._next_entry, self._prev_entry,
                      self._back_entry, self._main_entry]:
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
