"""
core/update.py
Vérification ET application des mises à jour via les releases GitHub.

Logique réseau/version 100% pure : PyQt n'est utilisé nulle part ici
(seule la bibliothèque standard : urllib, json, re, threading, hashlib,
zipfile, subprocess). ui/UI_UpdatePopup.py se charge de marshaler les
résultats vers le thread principal Qt.

Deux phases distinctes, appelables indépendamment :

1. CHECK (fetch_latest_release / check_for_update / check_for_update_async)
   Une requête GET en lecture seule vers l'API publique GitHub. Aucune
   donnée envoyée, aucune télémétrie, pas de clé API.

2. APPLY (download_and_verify_asset / launch_update_and_exit)
   Optionnelle : si l'utilisateur clique sur "Mettre à jour maintenant",
   on télécharge l'asset correspondant au mode de build (onefile/onedir),
   on vérifie son intégrité (SHA256 depuis SHASUMS.txt publié sur la
   release), puis on délègue le remplacement effectif à Dracoon-updater.exe (voir
   update_launcher.py), qui tourne en dehors du process principal pour
   pouvoir remplacer les fichiers une fois Dracoon fermé.

L'utilisateur peut toujours refuser l'auto-update et cliquer sur "Ouvrir
GitHub" pour télécharger/installer lui-même (voir ui/UI_UpdatePopup.py) —
les deux chemins restent disponibles.

Pour repasser Dracoon en version 100% hors-ligne, il suffit de :
  1. supprimer ce fichier
  2. supprimer ui/UI_UpdatePopup.py
  3. retirer les deux lignes d'intégration dans Main.py (voir notes
     d'intégration fournies avec ce fichier)
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from pathlib import Path

try:
    from core.config import APP_VERSION, APP_GITHUB, APP_UPDATE_MODE
except Exception:
    # Permet d'importer/tester ce module isolément.
    # APP_UPDATE_MODE doit être fixé au build ("onefile" ou "onedir") --
    # voir README_UPDATER.md, section 5.
    APP_VERSION = "0.0.0"
    APP_GITHUB = ""
    APP_UPDATE_MODE = "onefile"

logger = logging.getLogger("dracoon.update")
logger.addHandler(logging.NullHandler())


def _ensure_fallback_handler(log_path: str | None = None) -> None:
    """
    Optionnel : à appeler une seule fois au démarrage (ex. dans
    _init_update_checker) si tu veux être SÛR que les logs de ce module
    atterrissent quelque part, même si Main.py ne configure pas encore
    de logging global. Idempotent (n'ajoute pas de handler en double).
    """
    if any(isinstance(h, logging.FileHandler) for h in logger.handlers):
        return
    path = log_path or os.path.join(tempfile.gettempdir(), "dracoon_update_debug.log")
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(threadName)s %(message)s"
    ))
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    logger.info("Logging de secours initialisé -> %s", path)


REQUEST_TIMEOUT = 5           # secondes — on ne bloque jamais longtemps l'utilisateur
DOWNLOAD_TIMEOUT = 15         # secondes — un peu plus large, on télécharge un fichier
DOWNLOAD_CHUNK_SIZE = 1024 * 256
USER_AGENT = "Dracoon-UpdateChecker"

# Noms fixes des assets attendus sur chaque release (voir
# README_UPDATER.md pour le détail du processus de publication).
ONEFILE_ASSET_NAME = "Dracoon.exe"
ONEDIR_UPDATE_ASSET_NAME = "Dracoon-update.zip"
INSTALLER_ASSET_NAME = "Dracoon-installer.exe"  # jamais utilisé pour une mise à jour, référence seulement
SHASUMS_ASSET_NAME = "SHASUMS.txt"


class UpdateCheckError(Exception):
    """Levée quand la vérification échoue (réseau, timeout, repo/release introuvable, JSON invalide)."""


class UpdateApplyError(UpdateCheckError):
    """
    Levée quand le téléchargement/la vérification/le lancement de la mise
    à jour échoue. Hérite de UpdateCheckError pour que le code appelant
    puisse choisir de tout catcher avec un seul `except UpdateCheckError`
    s'il ne distingue pas les deux phases.
    """

class UpdateShasumsMissingError(UpdateApplyError):
    """
    Levée quand SHASUMS.txt n'est pas publié sur la release, ou n'a pas
    d'entrée pour l'asset demandé. Aucun téléchargement de l'asset
    principal n'est effectué dans ce cas — voir download_and_verify_asset().
    """


class UpdateShasumsMismatchError(UpdateApplyError):
    """
    Levée quand le SHA256 calculé ne correspond pas à celui attendu dans
    SHASUMS.txt. Le fichier téléchargé est supprimé avant que
    l'exception ne soit levée.
    """    


class UpdateCancelledError(UpdateApplyError):
    """
    Levée quand l'utilisateur annule la mise à jour en cours (via le
    cancel_event passé à launch_update_async / launch_update_and_exit).
    Ce n'est PAS une erreur au sens propre : l'appelant UI ne doit pas
    afficher de QMessageBox d'erreur pour ce cas, juste réinitialiser
    l'état de la popup. Le fichier téléchargé (le cas échéant) est
    supprimé avant que l'exception ne soit levée.
    """


@dataclass
class UpdateInfo:
    current_version: str
    latest_version: str
    is_newer: bool
    release_url: str
    changelog: str
    published_at: str | None
    assets: list[dict] = field(default_factory=list)

    def find_asset(self, name: str) -> dict | None:
        """Retourne le dict {'name', 'url'} de l'asset demandé, ou None."""
        for a in self.assets:
            if a.get("name") == name:
                return a
        return None


# ---------------------------------------------------------------------------
# Parsing / comparaison de versions
# ---------------------------------------------------------------------------

def _parse_owner_repo(github_url: str) -> tuple[str, str]:
    """
    Extrait (owner, repo) depuis une URL GitHub.
    Fonctionne avec https://github.com/owner/repo, .../repo/, .../repo/releases, etc.
    """
    match = re.search(r"github\.com/([^/]+)/([^/]+)", github_url or "")
    if not match:
        raise UpdateCheckError(f"Impossible d'extraire owner/repo depuis : {github_url!r}")
    owner, repo = match.group(1), match.group(2)
    if repo.endswith(".git"):
        repo = repo[:-4]
    return owner, repo


def parse_version(version: str) -> tuple[int, ...]:
    """
    Convertit une chaîne de version en tuple d'entiers comparables.
        'v3.1.0'   -> (3, 1, 0)
        '3.0.6'    -> (3, 0, 6)
        '3.2-beta' -> (3, 2)   (suffixe non numérique ignoré pour la comparaison)
    """
    cleaned = (version or "").strip()
    if cleaned[:1] in ("v", "V"):
        cleaned = cleaned[1:]
    cleaned = re.split(r"[-+]", cleaned, maxsplit=1)[0]

    parts = []
    for chunk in cleaned.split("."):
        digits = re.match(r"\d+", chunk)
        parts.append(int(digits.group()) if digits else 0)
    return tuple(parts) if parts else (0,)


def is_version_newer(latest: str, current: str) -> bool:
    """True si `latest` est strictement plus récente que `current`."""
    v_latest, v_current = parse_version(latest), parse_version(current)
    length = max(len(v_latest), len(v_current))
    v_latest += (0,) * (length - len(v_latest))
    v_current += (0,) * (length - len(v_current))
    return v_latest > v_current


# ---------------------------------------------------------------------------
# Phase 1 — CHECK : appel réseau en lecture seule, sans authentification
# ---------------------------------------------------------------------------

def fetch_latest_release(owner: str, repo: str, timeout: int = REQUEST_TIMEOUT) -> dict:
    """
    Interroge https://api.github.com/repos/{owner}/{repo}/releases/latest

    C'est un endpoint public : aucun token nécessaire pour un repo public.
    Lève UpdateCheckError en cas d'échec (réseau, timeout, 404, JSON invalide).
    """
    url = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": USER_AGENT,
        },
    )
    logger.debug("GET %s", url)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            logger.warning("Release introuvable (404) pour %s/%s", owner, repo)
            raise UpdateCheckError("Aucune release publiée sur le dépôt GitHub.") from e
        logger.warning("Erreur HTTP %s lors de la vérification (%s/%s)", e.code, owner, repo)
        raise UpdateCheckError(f"Erreur HTTP {e.code} lors de la vérification.") from e
    except urllib.error.URLError as e:
        logger.warning("Impossible de contacter GitHub : %s", e)
        raise UpdateCheckError("Impossible de contacter GitHub (pas de connexion internet ?).") from e
    except Exception as e:
        logger.exception("Erreur inattendue lors de la vérification")
        raise UpdateCheckError(f"Erreur inattendue lors de la vérification : {e}") from e

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error("Réponse GitHub illisible (JSON invalide)")
        raise UpdateCheckError("Réponse GitHub illisible (JSON invalide).") from e

    logger.debug("Release reçue : tag=%s assets=%d", data.get("tag_name"), len(data.get("assets", [])))
    return data


def check_for_update(current_version: str | None = None,
                      github_url: str | None = None,
                      timeout: int = REQUEST_TIMEOUT) -> UpdateInfo:
    """
    Vérifie s'il existe une version plus récente que `current_version`
    (par défaut APP_VERSION) sur le dépôt `github_url` (par défaut APP_GITHUB).

    Retourne toujours un UpdateInfo (avec is_newer=False si déjà à jour).
    Lève UpdateCheckError en cas d'échec de la requête.
    """
    current_version = current_version or APP_VERSION
    owner, repo = _parse_owner_repo(github_url or APP_GITHUB)
    logger.info("Vérification de mise à jour : %s/%s (version actuelle=%s)", owner, repo, current_version)
    data = fetch_latest_release(owner, repo, timeout=timeout)

    tag = data.get("tag_name", "") or ""
    assets = [
        {"name": a.get("name", ""), "url": a.get("browser_download_url", ""), "size": a.get("size", 0)}
        for a in data.get("assets", [])
    ]
    logger.info(
        "Résultat vérification : latest=%s is_newer=%s assets=%s",
        tag, is_version_newer(tag, current_version), [a["name"] for a in assets],
    )

    return UpdateInfo(
        current_version=current_version,
        latest_version=tag,
        is_newer=is_version_newer(tag, current_version),
        release_url=data.get("html_url") or github_url or APP_GITHUB,
        changelog=data.get("body", "") or "",
        published_at=data.get("published_at"),
        assets=assets,
    )


def check_for_update_async(on_result, on_error=None,
                            current_version: str | None = None,
                            github_url: str | None = None,
                            timeout: int = REQUEST_TIMEOUT) -> threading.Thread:
    """
    Lance check_for_update() dans un thread daemon pour ne jamais bloquer
    le démarrage ou l'UI, même si GitHub met du temps à répondre ou si
    l'utilisateur est hors ligne.

    ATTENTION : `on_result` et `on_error` sont appelés depuis le thread
    d'arrière-plan, PAS depuis le thread principal Qt. Ne touche aucun
    widget directement dans ces callbacks — passe par un signal Qt
    thread-safe (c'est ce que fait ui/UI_UpdatePopup.py).
    """
    def _worker():
        try:
            info = check_for_update(current_version, github_url, timeout)
            on_result(info)
        except Exception as e:
            if on_error:
                on_error(e)

    thread = threading.Thread(target=_worker, daemon=True, name="Dracoon-UpdateCheck")
    thread.start()
    return thread


# ---------------------------------------------------------------------------
# Phase 2 — APPLY : téléchargement, vérification SHA256, lancement d'Dracoon-updater.exe
# ---------------------------------------------------------------------------

ProgressCallback = "Callable[[str, int], None]"  # (stage, percent) — percent=-1 si indéterminé


def _http_download(url: str, dest: Path, expected_size: int = 0, timeout: int = DOWNLOAD_TIMEOUT,
                    on_progress=None, stage: str = "download",
                    cancel_event: threading.Event | None = None) -> None:
    """
    on_progress(stage: str, percent: int) est appelé à intervalles réguliers
    pendant le téléchargement. percent vaut -1 si la taille totale est
    inconnue (barre indéterminée côté UI). Le callback n'est appelé que
    lorsque le pourcentage change, pour ne pas spammer le thread Qt.

    cancel_event : si fourni et positionné (set()) pendant le téléchargement,
    la boucle s'arrête au chunk suivant, le fichier partiel est supprimé et
    UpdateCancelledError est levée.
    """
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    tmp_dest = dest.with_suffix(dest.suffix + ".part")
    last_percent = -2  # valeur impossible pour forcer le premier appel
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp, open(tmp_dest, "wb") as f:
            total = expected_size or int(resp.headers.get("Content-Length") or 0)
            written = 0
            while True:
                if cancel_event is not None and cancel_event.is_set():
                    raise UpdateCancelledError("Téléchargement annulé par l'utilisateur.")
                chunk = resp.read(DOWNLOAD_CHUNK_SIZE)
                if not chunk:
                    break
                f.write(chunk)
                written += len(chunk)
                if on_progress is not None:
                    percent = int(written * 100 / total) if total else -1
                    if percent != last_percent:
                        last_percent = percent
                        on_progress(stage, percent)
        if on_progress is not None and last_percent != 100 and expected_size:
            on_progress(stage, 100)
        if expected_size and written != expected_size:
            raise UpdateApplyError(
                f"Taille du fichier téléchargé incorrecte pour {dest.name} "
                f"(attendu {expected_size}, reçu {written})"
            )
        tmp_dest.replace(dest)
    except UpdateCancelledError:
        _safe_unlink(tmp_dest)
        raise
    except urllib.error.URLError as e:
        _safe_unlink(tmp_dest)
        raise UpdateApplyError(f"Échec du téléchargement de {url} : {e}") from e
    except Exception:
        _safe_unlink(tmp_dest)
        raise


def _safe_unlink(path: Path) -> None:
    try:
        if path.exists():
            path.unlink()
    except OSError:
        pass


def _sha256_of_file(path: Path, on_progress=None, stage: str = "verify",
                     cancel_event: threading.Event | None = None) -> str:
    total = path.stat().st_size
    written = 0
    last_percent = -2
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(DOWNLOAD_CHUNK_SIZE), b""):
            if cancel_event is not None and cancel_event.is_set():
                raise UpdateCancelledError("Vérification annulée par l'utilisateur.")
            h.update(chunk)
            written += len(chunk)
            if on_progress is not None and total:
                percent = int(written * 100 / total)
                if percent != last_percent:
                    last_percent = percent
                    on_progress(stage, percent)
    if on_progress is not None and total and last_percent != 100:
        on_progress(stage, 100)
    return h.hexdigest()


def _parse_shasums(text: str) -> dict[str, str]:
    result = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 1)
        if len(parts) != 2:
            continue
        digest, fname = parts
        result[fname.strip()] = digest.strip().lower()
    return result


def download_and_verify_asset(info: UpdateInfo, asset_name: str, work_dir: Path, on_progress=None,
                               cancel_event: threading.Event | None = None) -> Path:
    """
    Télécharge l'asset `asset_name` de la release (déjà connu via un
    check_for_update() préalable -- pas de nouvel appel à l'API GitHub) et
    vérifie son SHA256 contre SHASUMS.txt (lui-même un asset de la release).

    on_progress(stage, percent) est appelé pendant le téléchargement du
    package ("download") puis pendant le calcul du hash ("verify").
    percent va de 0 à 100, ou vaut -1 si indéterminé (taille inconnue).

    cancel_event : si positionné à tout moment pendant le téléchargement
    de SHASUMS.txt, du package, ou pendant le calcul du hash,
    UpdateCancelledError est levée et le fichier partiel/téléchargé est
    supprimé.

    Comportement STRICT (fail-closed) :
    - Si SHASUMS.txt n'est pas publié sur la release, ou n'a pas d'entrée
      pour asset_name -> UpdateShasumsMissingError. Dans le premier cas,
      RIEN n'est téléchargé (vérifié avant le gros fichier).
    - Si le hash ne correspond pas -> UpdateShasumsMismatchError, le
      fichier téléchargé est supprimé.
    """
    asset = info.find_asset(asset_name)
    if asset is None:
        raise UpdateApplyError(
            f"Release {info.latest_version} : aucun asset nommé '{asset_name}' — "
            f"la publication de cette release est peut-être incomplète."
        )

    shasums_asset = info.find_asset(SHASUMS_ASSET_NAME)
    if shasums_asset is None:
        logger.warning(
            "Aucun %s trouvé sur la release %s : mise à jour refusée (vérification stricte).",
            SHASUMS_ASSET_NAME, info.latest_version,
        )
        raise UpdateShasumsMissingError(
            f"{SHASUMS_ASSET_NAME} absent de la release {info.latest_version} — "
            f"mise à jour automatique désactivée par sécurité."
        )

    work_dir.mkdir(parents=True, exist_ok=True)

    shasums_path = work_dir / SHASUMS_ASSET_NAME
    _http_download(shasums_asset["url"], shasums_path, cancel_event=cancel_event)  # petit fichier, pas de progression nécessaire
    expected_hashes = _parse_shasums(shasums_path.read_text(encoding="utf-8", errors="replace"))
    expected = expected_hashes.get(asset_name)

    if expected is None:
        raise UpdateShasumsMissingError(
            f"{SHASUMS_ASSET_NAME} ne contient pas d'entrée pour {asset_name} — abandon par sécurité"
        )

    package_path = work_dir / asset_name
    logger.info("Téléchargement de %s (%d octets)...", asset_name, asset.get("size", 0))
    _http_download(asset["url"], package_path, asset.get("size", 0), on_progress=on_progress, stage="download",
                    cancel_event=cancel_event)

    if on_progress is not None:
        on_progress("verify", -1)  # le hash d'un petit fichier est quasi instantané, mais on prévient l'UI
    actual = _sha256_of_file(package_path, on_progress=on_progress, stage="verify", cancel_event=cancel_event)
    if actual.lower() != expected:
        _safe_unlink(package_path)
        raise UpdateShasumsMismatchError(
            f"Hash SHA256 invalide pour {asset_name} "
            f"(attendu {expected}, calculé {actual}) — fichier potentiellement corrompu ou altéré"
        )

    logger.info("Intégrité vérifiée (SHA256 OK) pour %s", asset_name)
    return package_path


def _extract_update_exe(work_dir: Path) -> Path:
    """
    Récupère Dracoon-updater.exe depuis l'emplacement où le build l'a embarqué :
    - onefile : extrait depuis sys._MEIPASS (bundle PyInstaller de Dracoon.exe)
    - onedir  : copié depuis le dossier de l'exécutable courant

    Retourne le chemin de Dracoon-updater.exe copié dans work_dir (indépendant du
    process appelant, jamais verrouillé pendant l'opération).
    """
    dest = work_dir / "Dracoon-updater.exe"

    if hasattr(sys, "_MEIPASS"):
        source = Path(sys._MEIPASS) / "Dracoon-updater.exe"
    else:
        source = Path(sys.executable).parent / "Dracoon-updater.exe"

    if not source.exists():
        raise UpdateApplyError(f"Dracoon-updater.exe introuvable à l'emplacement attendu : {source}")

    shutil.copy2(source, dest)
    return dest


def launch_update_and_exit(info: UpdateInfo,
                            mode: str | None = None,
                            current_exe_path: Path | None = None,
                            current_dir: Path | None = None,
                            on_progress=None,
                            cancel_event: threading.Event | None = None) -> None:
    """
    Orchestre toute la phase APPLY : télécharge l'asset correspondant au
    mode de build, vérifie son intégrité, extrait Dracoon-updater.exe, puis le
    lance en sous-processus détaché avec les arguments nécessaires.

    on_progress(stage, percent) est relayé depuis download_and_verify_asset
    ("download"/"verify") et reçoit en plus un appel ("launch", -1) juste
    avant de démarrer Dracoon-updater.exe.

    cancel_event : vérifié pendant le téléchargement/la vérification (voir
    download_and_verify_asset), PUIS une dernière fois juste avant le
    lancement de Dracoon-updater.exe -- c'est le point de non-retour : une
    fois le sous-processus lancé, l'annulation n'est plus possible et
    cancel_event n'est plus consulté.

    N'appelle PAS sys.exit() elle-même -- c'est à l'appelant (le callback
    UI, après confirmation que le lancement a réussi) de fermer
    proprement l'application pour libérer le PID attendu par Dracoon-updater.exe.

    Lève UpdateApplyError si une étape échoue, ou UpdateCancelledError si
    l'utilisateur a annulé -- dans les deux cas l'application ne doit PAS
    se fermer, l'utilisateur reste sur la version actuelle.
    """
    mode = mode or APP_UPDATE_MODE
    if mode not in ("onefile", "onedir"):
        raise ValueError("mode doit être 'onefile' ou 'onedir'")

    current_exe_path = current_exe_path or Path(sys.executable)
    asset_name = ONEFILE_ASSET_NAME if mode == "onefile" else ONEDIR_UPDATE_ASSET_NAME

    work_dir = Path(tempfile.gettempdir()) / "DracoonUpdate" / f"run_{int(time.time())}"
    work_dir.mkdir(parents=True, exist_ok=True)

    package_path = download_and_verify_asset(info, asset_name, work_dir, on_progress=on_progress,
                                               cancel_event=cancel_event)

    # Dernier point de contrôle avant le point de non-retour : une fois
    # Dracoon-updater.exe lancé (Popen ci-dessous), on ne peut plus annuler.
    if cancel_event is not None and cancel_event.is_set():
        raise UpdateCancelledError("Mise à jour annulée par l'utilisateur avant le lancement de l'updater.")

    if on_progress is not None:
        on_progress("launch", -1)

    updater_exe = _extract_update_exe(work_dir)

    target = str(current_exe_path if mode == "onefile" else (current_dir or current_exe_path.parent))

    args = [
        str(updater_exe),
        "--pid", str(os.getpid()),
        "--mode", mode,
        "--target", target,
        "--package", str(package_path),
        "--new-version", info.latest_version.lstrip("vV"),
        "--log", str(work_dir / "update.log"),
    ]

    logger.info("Lancement de l'updater : %s", " ".join(args))

    creationflags = 0
    if os.name == "nt":
        DETACHED_PROCESS = 0x00000008
        CREATE_NEW_PROCESS_GROUP = 0x00000200
        creationflags = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP

    try:
        subprocess.Popen(args, creationflags=creationflags, close_fds=True)
    except OSError as e:
        raise UpdateApplyError(f"Impossible de lancer Dracoon-updater.exe : {e}") from e


def launch_update_async(info: UpdateInfo, on_done, on_error, on_progress=None,
                         mode: str | None = None,
                         current_exe_path: Path | None = None,
                         current_dir: Path | None = None,
                         cancel_event: threading.Event | None = None,
                         on_cancelled=None) -> tuple[threading.Thread, threading.Event]:
    """
    Équivalent de check_for_update_async pour la phase APPLY : lance
    launch_update_and_exit() dans un thread daemon pour ne pas geler l'UI
    pendant le téléchargement. `on_done` est appelé sans argument en cas
    de succès (l'appelant doit alors fermer l'application), `on_error`
    est appelé avec l'exception en cas d'échec (hors annulation),
    `on_progress(stage, percent)` est appelé à chaque changement de
    progression.

    cancel_event : threading.Event optionnel. Si non fourni, un nouvel
    Event est créé et retourné (voir valeur de retour) -- l'appelant UI
    n'a alors qu'à faire `.set()` dessus pour demander l'annulation.
    Positionner cet event avant que le sous-processus updater ne soit
    lancé interrompt proprement le téléchargement/la vérification ; une
    fois l'updater lancé, l'annulation n'a plus d'effet.

    on_cancelled : callback optionnel, appelé sans argument si la mise à
    jour a été annulée (au lieu de on_error). Si non fourni, l'annulation
    est simplement ignorée silencieusement (pas d'appel à on_error).

    Retourne (thread, cancel_event) : garde une référence à cancel_event
    côté appelant pour pouvoir annuler plus tard.

    Mêmes précautions que check_for_update_async : callbacks exécutés
    hors du thread principal Qt, à faire remonter via un signal.
    """
    cancel_event = cancel_event or threading.Event()

    def _worker():
        try:
            launch_update_and_exit(info, mode, current_exe_path, current_dir,
                                    on_progress=on_progress, cancel_event=cancel_event)
            on_done()
        except UpdateCancelledError:
            if on_cancelled is not None:
                on_cancelled()
        except Exception as e:
            on_error(e)

    thread = threading.Thread(target=_worker, daemon=True, name="Dracoon-UpdateApply")
    thread.start()
    return thread, cancel_event
