# Présentation

Dracoon est un outil ayant pour but de faciliter et automatiser la gestion des fenetres de Dofus Rétro en monocompte et en multicompte, tout en restant respectueux des CGU.

Le programme **intègre les fonctionnalités déjà connues** par une grande partie de joueur (tri des comptes selon l'ordre d'initiative, compte suivant/précédent via une touche...) et **ajoute un système d’Auto-Focus**.

Vidéo de présentation :

[(https://github.com/Slyss42/Dracoon/blob/4cf59d33ab03a9f8568ab6c3938f918b69737c58/youtube-miniature.png)](https://youtu.be/6R7pPM_5euM)

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

**Mais aussi**
* Pour les personnes en situation de handicap
---

# Installation

1. Télécharger la dernière version dans la section **Releases** (à droite sur Github). Vous pouvez téléchargez uniquement le .exe
2. Lancer le fichier `.exe`.
3. Activer les notifications sur vos comptes Dofus (option en jeu > général > notification en arrière plan) [screen](https://github.com/Slyss42/Dracoon/blob/46b5f9711967baa45749e804de905726fff89c6a/activer-notification-ig.png)
4. Activer les notifications Windows (Paramètre > Système > Actions et notifications > "activer"
5. Désactiver "autoriser les notifications à émettre des sons" (ou le faire spécifiquement pour Dofus si vous voulez garder le son pour les autres applications) [screen](https://github.com/Slyss42/Dracoon/blob/7fae9b3246307ed8bc5035d0d623450cbc735c73/activer-notification-windows1.png)
6. Cliquer sur l'application "Dofus 1" pour désactiver l'affichage des bannières. Vous pouvez donc désactiver le son des notifications de Dofus à cet endroit (si vous préférez avoir le son des autres notifications) [screen](https://github.com/Slyss42/Dracoon/blob/ce4e21739dc6cbe9c16bf4d05bd57da43d9ef453/activer-notification-windows2.png)
 
---

# FAQ

* **En quel langage est écrit Dracoon ? Comment as-tu fais le lodiciel ?**

Tout est développé en Python et réalisé grâce à l'IA.

* **Windows me demande si je fais confiance à le logiciel**

Dracoon permettant de modifier le comportement de votre clavier (touche de raccourcis) il est normal que Windows ajoute une sécurité supplémentaire. Le comportement de Windows est le même sur d'autres outils.

* **L'auto-focus ne fonctionne pas**

Vous pouvez afficher le mode "debug" dans l'onglet d'auto-focus. Ensuite faite un échange entre vos personnages et vérifie si la notification est bien affichée dans les logs. SI ce n'est pas le cas, c'est que les notifications ne sont pas bien activée sur votre ordinateur.

* **Ce programme est-il autorisé par Ankama ?**

Petit rappel de la part d'Ankama concernant les règles fixée autour des outils fan-made : *"L'utilisation d'un logiciel tiers est tolérée UNIQUEMENT s'il ne modifie/n'interagit pas avec les fichiers du jeu ou le jeu en lui-même. Ne s'agissant pas d'un outil officiellement pris en charge par Ankama, nous vous rappelons que nous ne pouvons pas garantir la sécurité du logiciel et que son utilisation peut comporter des risques. En cas d'éventuelles violations de données ou de logs, le joueur sera tenu responsable.Il est également important de distinguer un outil de gestion de fenêtre d'autres outils tiers comme les macros, ces dernières sont strictement interdites.."*

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
