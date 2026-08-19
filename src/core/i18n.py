import json
import os
import sys

_translations: dict = {}

def load_translations(lang: str = "fr"):
    """Charge le fichier de traduction i18n.json depuis les ressources."""
    global _translations
    # Gestion du chemin selon si l'application est compilée ou en dev
    if getattr(sys, "frozen", False):
        base_path = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
        # Si i18n.json est resté à la racine des ressources hors du package
        json_path = os.path.join(base_path, "ressources", "i18n.json")
    else:
        # Chemin dev : core/i18n.py -> src/core -> src/ressources/i18n.json
        current_dir = os.path.dirname(os.path.abspath(__file__))
        json_path = os.path.abspath(os.path.join(current_dir, "..", "ressources", "i18n.json"))

    try:
        if os.path.exists(json_path):
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                _translations = data.get(lang, data.get("fr", {}))
        else:
            _translations = {}
    except Exception:
        _translations = {}

def t(key: str) -> str:
    """Retourne la traduction associée à la clé."""
    return _translations.get(key, key)