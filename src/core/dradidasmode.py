class DradidasManager:
    """
    Gère les compteurs de Puissance Sylvestre par personnage.

    Usage :
        manager = DradidasManager(turns=3)
        manager.set_sadidas({"Perso1", "Perso2"})

        # Quand le raccourci est pressé sur la fenêtre de "Perso1" :
        manager.trigger("Perso1")

        # Dans le listener d'autofocus, avant chaque notification combat :
        skip, left = manager.should_skip_combat("Perso1")
        if skip:
            # ignorer ce tour de combat
    """

    def __init__(self, turns: int = 3):
        self._sadida_pseudos: set[str] = set()
        self._skip_counts:    dict[str, int] = {}   # pseudo → tours restants
        self._turns = max(1, int(turns))

    # ── Propriétés ────────────────────────────────────────────────────────────

    @property
    def turns(self) -> int:
        return self._turns

    @turns.setter
    def turns(self, value: int):
        self._turns = max(1, int(value))

    @property
    def sadida_pseudos(self) -> set[str]:
        return set(self._sadida_pseudos)

    # ── Configuration ─────────────────────────────────────────────────────────

    def set_sadidas(self, pseudos: set[str]):
        """Met à jour l'ensemble des pseudos Sadida.
        Annule les compteurs des personnages qui ne sont plus Sadida.
        """
        self._sadida_pseudos = set(pseudos)
        for p in list(self._skip_counts.keys()):
            if p not in self._sadida_pseudos:
                del self._skip_counts[p]

    def is_sadida(self, pseudo: str) -> bool:
        return pseudo in self._sadida_pseudos

    # ── Contrôle du compteur ──────────────────────────────────────────────────

    def trigger(self, pseudo: str):
        """Démarre ou remet à zéro le compteur pour ce pseudo.
        Idempotent : si déjà actif, remet exactement à _turns (sans dépasser).
        Ne fait rien si le pseudo n'est pas dans la liste Sadida.
        """
        if pseudo in self._sadida_pseudos:
            self._skip_counts[pseudo] = self._turns

    def should_skip_combat(self, pseudo: str) -> tuple[bool, int]:
        """Appelé par le listener d'autofocus pour chaque notification de combat.

        Retourne (True, tours_restants_après_décrément) si ce tour doit être ignoré.
        Retourne (False, 0) si le compteur est épuisé ou si le pseudo n'est pas Sadida.
        Décrémente le compteur à chaque appel positif.
        """
        remaining = self._skip_counts.get(pseudo, 0)
        if remaining <= 0:
            return False, 0
        new_remaining = remaining - 1
        if new_remaining == 0:
            del self._skip_counts[pseudo]
        else:
            self._skip_counts[pseudo] = new_remaining
        return True, new_remaining

    def get_skip_remaining(self, pseudo: str) -> int:
        """Retourne le nombre de tours restants (0 si inactif)."""
        return self._skip_counts.get(pseudo, 0)

    def cancel(self, pseudo: str):
        """Annule le compteur d'un personnage spécifique."""
        self._skip_counts.pop(pseudo, None)

    def cancel_all(self):
        """Annule tous les compteurs actifs."""
        self._skip_counts.clear()

    def has_active_skips(self) -> bool:
        """True si au moins un personnage a un compteur actif."""
        return bool(self._skip_counts)