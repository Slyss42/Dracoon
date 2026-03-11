# Présentation

Dracoon est un outil développé 100% par l'IA en **Python**. Cet outil pour but de faciliter et automatiser la gestion des fenetres de Dofus Rétro en monocompte et en multicompte, tout en restant respectueux des CGU.

Le programme **intègre les fonctionnalités déjà connues** par une grande partie de joueur (tri des comptes selon l'ordre d'initiative, compte suivant/précédent via une touche...) et **ajoute un système d’Auto-Focus**.

Comme tous les autres outils non-officiels et respectant les CGU, cet outil est toléré par Ankama.

---

# Cas d’utilisation

**Monocompte**

* jouer sur un seul compte tout en faisant autre chose à côté. Le programme effectuera le changement de fenetre lorsque vous êtes demandé

**Multicompte**
* échanges entre comptes
* création de groupes
* navigation rapide entre les personnages
* lorsque l’ordre d’initiative change régulièrement
* éviter de devoir réorganiser les fenêtres manuellement

---

# Installation

1. Télécharger la dernière version dans la section **Releases**.
2. Lancer le fichier `.exe`.
3. Activer les notifications sur vos comptes Dofus (option en jeu > général > notification en arrière plan)

![image alt](https://github.com/Slyss42/Dracoon/blob/870bcb80c08f91d18c7bfe1a981e38dc6da308d1/activer-notification-ig.png)

---

# Amélioration

Je suis **ouvert aux retours et aux suggestions d’amélioration** :

* si certaines fonctionnalités ne fonctionnent pas correctement
* si le système n’est pas assez rapide
* si vous avez des idées d’amélioration
* si le système n'est pas intuitif

N’hésitez pas à **ouvrir une issue ou proposer des améliorations sur twitter @Slyss42**.

---
# Fonctionnement technique de l'auto-focus

Plusieurs proposition d'auto-focus existent/ont existés, mais elles reposent souvent sur  la **lecture de paquets réseau** : plus rapide,  mais interdit par les CGU (et parfois difficile à maintenir). Égalament, ces outils contiennent parfois des macros, elles-aussi interditent par les CGU.

L'auto-focus de Dracoon repose uniquement sur l’analyse des **notifications du jeu**. Voici le fonctionnement global :
* Windows stocke les notifications dans un fichier se trouvant sur votre ordinateur
* Dès qu'il est activé, Dracoon lit ce fichier en boucle et vérifie si il y a une nouvelle notification
* Si le texte de la notification est connu de Dracoon ("de joeur" pour les combat, "te propose de faire un échange" pour les échange,...) alors, Dracoon regarde le titre de la notification (correspondant au personnage qui recoit la notification et donc, l'action)
* Si le compte existe, Dracoon se charge de mettre ce compte au premier plan


L’objectif est donc d’avoir un outil **simple, automatisé et respectueux des CGU**.

---

# Amélioration

Je suis **ouvert aux retours et aux suggestions d’amélioration** :

* si certaines fonctionnalités ne fonctionnent pas correctement
* si le système n’est pas assez rapide
* si vous avez des idées d’amélioration
* si le système n'est pas intuitif

N’hésitez pas à **ouvrir une issue ou proposer des améliorations sur twitter @Slyss42**.

---

# FAQ

**Windows me demande si je fais confiance à le logiciel**
Dracoon permettant de modifier le comportement de votre clavier (touche de raccourcis) il est normal que Windows ajoute une sécurité supplémentaire. Le comportement de Windows est le même sur d'autres outils.

**L'auto-focus ne fonctionne pas**

---

# Rappel concernant ce genre d'outils

Petit rappel de la part d'Ankama concernant les règles fixée autour des outils fan-made :

*"L'utilisation d'un logiciel tiers est tolérée UNIQUEMENT s'il ne modifie/n'interagit pas avec les fichiers du jeu ou le jeu en lui-même.*

*Ne s'agissant pas d'un outil officiellement pris en charge par Ankama, nous vous rappelons que nous ne pouvons pas garantir la sécurité du logiciel et que son utilisation peut comporter des risques. En cas d'éventuelles violations de données ou de logs, le joueur sera tenu responsable.*

*Il est également important de distinguer un outil de gestion de fenêtre d'autres outils tiers comme les macros, ces dernières sont strictement interdites.."*





