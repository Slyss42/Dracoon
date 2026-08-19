"""
reg_migration.py

Migration unique des paramètres du registre Windows :
    HKCU\\Software\\DofusRetro  ->  HKCU\\Software\\Dracoon

Usage dans main.py :

    from reg_migration import migrate_registry_if_needed
    migrate_registry_if_needed()

La migration ne s'exécute qu'une seule fois : un marqueur est écrit dans la
nouvelle clé une fois la copie terminée. Aux lancements suivants, le coût
est celui d'une seule lecture de registre (négligeable, de l'ordre de la
microseconde) — pas de copie, pas de parcours de clés.
"""

import winreg
import logging

logger = logging.getLogger(__name__)

OLD_KEY_PATH = r"Software\DofusRetro"
NEW_KEY_PATH = r"Software\Dracoon"
MIGRATION_MARKER = "MigratedFromDofusRetro"
ROOT = winreg.HKEY_CURRENT_USER


def _copy_key_recursive(src_key: winreg.HKEYType, dst_key: winreg.HKEYType) -> None:
    """Copie récursivement toutes les valeurs et sous-clés de src_key vers dst_key."""

    # 1. Copier les valeurs de la clé courante
    index = 0
    while True:
        try:
            name, value, value_type = winreg.EnumValue(src_key, index)
        except OSError:
            break
        winreg.SetValueEx(dst_key, name, 0, value_type, value)
        index += 1

    # 2. Copier récursivement les sous-clés
    index = 0
    while True:
        try:
            subkey_name = winreg.EnumKey(src_key, index)
        except OSError:
            break

        with winreg.OpenKey(src_key, subkey_name) as src_subkey:
            dst_subkey = winreg.CreateKey(dst_key, subkey_name)
            try:
                _copy_key_recursive(src_subkey, dst_subkey)
            finally:
                winreg.CloseKey(dst_subkey)

        index += 1

def _delete_key_recursive(root, key_path: str) -> None:
    """Supprime récursivement une clé de registre et toutes ses sous-clés."""
    try:
        with winreg.OpenKey(
            root,
            key_path,
            0,
            winreg.KEY_READ | winreg.KEY_WRITE
        ) as key:
            while True:
                try:
                    subkey_name = winreg.EnumKey(key, 0)
                except OSError:
                    break

                _delete_key_recursive(
                    key,
                    subkey_name
                )

        winreg.DeleteKey(root, key_path)

    except FileNotFoundError:
        pass

def _is_already_migrated() -> bool:
    """Vérifie la présence du marqueur dans la nouvelle clé (une seule lecture)."""
    try:
        with winreg.OpenKey(ROOT, NEW_KEY_PATH) as new_key:
            winreg.QueryValueEx(new_key, MIGRATION_MARKER)
            return True
    except OSError:
        # Soit la clé n'existe pas, soit le marqueur n'existe pas
        return False


def migrate_registry_if_needed(logger: logging.Logger | None = None) -> None:
    """
    Point d'entrée à appeler au démarrage de l'application.

    - Si la migration a déjà été faite : une seule lecture registre, puis retour
      immédiat (coût négligeable).
    - Sinon : copie récursive de l'ancienne clé vers la nouvelle, puis écriture
      du marqueur pour ne plus jamais refaire la copie.
    - Si l'ancienne clé n'existe pas (nouvelle installation) : on écrit juste
      le marqueur pour éviter de retester à chaque démarrage.

    :param logger: logger applicatif à utiliser (ex: celui de setup_file_logger()).
                   Si None, utilise le logger par défaut du module (console uniquement,
                   tant qu'aucun handler fichier n'est configuré côté appli).
    """
    log = logger or logging.getLogger(__name__)

    if _is_already_migrated():
        return

    try:
        old_key_exists = True
        try:
            old_key = winreg.OpenKey(ROOT, OLD_KEY_PATH)
        except OSError:
            old_key_exists = False
            old_key = None

        # Crée (ou ouvre) la nouvelle clé
        new_key = winreg.CreateKey(ROOT, NEW_KEY_PATH)

        try:
            if old_key_exists:
                log.info("Migration registre : %s -> %s", OLD_KEY_PATH, NEW_KEY_PATH)
                _copy_key_recursive(old_key, new_key)
                log.info("Migration registre terminée avec succès.")
            else:
                log.info(
                    "Aucune ancienne clé %s trouvée, pas de migration nécessaire.",
                    OLD_KEY_PATH,
                )

            # Ferme l'ancienne clé avant de pouvoir la supprimer
            if old_key is not None:
                winreg.CloseKey(old_key)
                old_key = None

            # Suppression de l'ancienne clé uniquement après migration réussie
            if old_key_exists:
                log.info("Suppression de l'ancienne clé : %s", OLD_KEY_PATH)
                _delete_key_recursive(ROOT, OLD_KEY_PATH)
                log.info("Ancienne clé supprimée avec succès.")

            # Marqueur écrit après la migration réussie
            winreg.SetValueEx(new_key, MIGRATION_MARKER, 0, winreg.REG_DWORD, 1)

        finally:
            winreg.CloseKey(new_key)
            if old_key is not None:
                winreg.CloseKey(old_key)

    except Exception:
        # On ne doit jamais empêcher le lancement de l'appli pour un souci
        # de migration de registre. On log et on continue.
        log.exception("Échec de la migration du registre DofusRetro -> Dracoon")




if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    migrate_registry_if_needed()
    print("Migration terminée (ou déjà faite / non nécessaire).")
