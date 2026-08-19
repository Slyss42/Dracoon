# Présentation

Dracoon est un outil ayant pour but de faciliter et automatiser la gestion des fenetres de Dofus Rétro en monocompte et en multicompte, tout en restant respectueux des CGU.

Le programme **intègre les fonctionnalités déjà connues** par une grande partie de joueur (tri des comptes selon l'ordre d'initiative, compte suivant/précédent via une touche...) et **ajoute un système d’Auto-Focus**.

Vidéo de présentation :

[![Vidéo de présentation](https://github.com/Slyss42/Dracoon/blob/fd2ad522809b8398c359805ac353bc745ef0a1d7/miniature-pr%C3%A9sentation.png)](https://youtu.be/6R7pPM_5euM)

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

# Pré-requis
* Autorisé les applications à accéder à vos notifications (Paramètre > Confidentialité > Notifications > "activer")  [screen](https://github.com/Slyss42/Dracoon/blob/f2e668830b0f250211360b09da4b0d9b2b68c9e7/.github/activer-notification-autorisation.png)
* Activer les notifications sur vos comptes Dofus (option en jeu > général > notification en arrière plan) [screen](https://github.com/Slyss42/Dracoon/blob/46b5f9711967baa45749e804de905726fff89c6a/activer-notification-ig.png)
* Activer les notifications Windows (Paramètre > Système > Actions et notifications > "activer")

# Recommandations
* Désactiver "autoriser les notifications à émettre des sons" (ou le faire spécifiquement pour Dofus si vous voulez garder le son pour les autres applications). (Paramètre > Système > Actions et notifications) [screen](https://github.com/Slyss42/Dracoon/blob/7fae9b3246307ed8bc5035d0d623450cbc735c73/activer-notification-windows1.png)
* Au même endroit (Paramètre > Système > Actions et notifications), cliquez sur l'application "Dofus 1" et désactivez les bannières de notifications.  Vous pouvez donc désactiver le son des notifications de Dofus à cet endroit (si vous préférez avoir le son des autres notifications) [screen](https://github.com/Slyss42/Dracoon/blob/ce4e21739dc6cbe9c16bf4d05bd57da43d9ef453/activer-notification-windows2.png)
* Dans les paramètres de Dracoon, cocher "Supprimer la bannière dès son apparition"

---
# Installation depuis le code
Prérequis :
* Python 3.10 minimum [(site officiel)](https://www.python.org/downloads/)
* Installer les dépendances : (ouvrir l'invite de commande, copier/coller le texte ci-dessous, puis presser enter)
``` 
pip install pywin32 winsdk keyboard pystray Pillow psutil pyinstaller
```
* Lancement pour test : (ouvrir l'invite de commande aller jusqu'au dossier ou se trouve le script et taper "python Dracoon.pyw"). OU : taper "python" et glisser le UI.py dans l'invite de commande + presser enter
```
C:\CHEMIN\VERS\LE\DOSSIER\SRC>python main.py
```
 
* Build : (passer le .py en .exe)
```
@echo off
set "SRC_PATH=CHEMIN\VERS\LE\DOSSIER"

PyInstaller --onefile --noconsole --clean ^
--name "Dracoon" ^
--distpath "%SRC_PATH%\dist" ^
--workpath "%SRC_PATH%\build" ^
--specpath "%SRC_PATH%" ^
--icon "%SRC_PATH%\src\ressources\icon.ico" ^
--add-data "%SRC_PATH%\src\ressources\icon.ico;ressources" ^
--add-data "%SRC_PATH%\src\ressources\i18n.json;ressources" ^
--add-data "%SRC_PATH%\src\ressources\portraits;portraits" ^
--add-binary "CHEMIN\VERS\UPDATER\Dracoon-updater.exe;." ^
--paths "%SRC_PATH%\src" ^
--paths "%SRC_PATH%\src\ui" ^
--paths "%SRC_PATH%\src\core" ^
--hidden-import win32gui ^
--hidden-import win32con ^
--hidden-import win32api ^
--hidden-import win32process ^
--hidden-import win32com ^
--hidden-import pythoncom ^
--hidden-import winsdk.windows.ui.notifications ^
--hidden-import winsdk.windows.ui.notifications.management ^
--hidden-import winsdk.windows.foundation ^
--hidden-import pystray._win32 ^
--hidden-import PIL ^
--hidden-import PIL.Image ^
--hidden-import PIL.ImageDraw ^
--hidden-import PIL.ImageTk ^
--hidden-import keyboard ^
--hidden-import psutil ^
"%SRC_PATH%\src\Main.py"

```
* Lancer le fichier `.exe` se trouvant dans le dossier "dist"
Vous pouvez librement déplacer le .exe et supprimer tous les autres fichiers sans que cela ait un impact.


---
# Installation rapide
* Télécharger la dernière version dans la section **Releases** (à droite sur Github). Vous pouvez téléchargez uniquement le .exe
* Lancer le fichier `.exe`.

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
# License
MIT License

Copyright (c) 2026 Slyss42

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
