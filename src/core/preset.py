from core.config import load_config, save_config
import json

# ─── Presets d'ordre des personnages ──────────────────────────────────────────

_PRESET_KEY = "order_presets"


def load_order_presets() -> dict[str, list[str]]:
    """Retourne {nom: [pseudo, ...]} depuis le registre."""
    cfg = load_config()
    raw = cfg.get(_PRESET_KEY, "") or ""
    try:
        return json.loads(raw) if raw else {}
    except Exception:
        return {}


def save_order_preset(name: str, pseudos: list[str]):
    """Ajoute ou écrase un preset et persiste."""
    presets = load_order_presets()
    presets[name] = pseudos
    save_config({_PRESET_KEY: json.dumps(presets, ensure_ascii=False)})


def delete_order_preset(name: str):
    """Supprime un preset et persiste."""
    presets = load_order_presets()
    presets.pop(name, None)
    save_config({_PRESET_KEY: json.dumps(presets, ensure_ascii=False)})


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