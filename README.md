# Géo Cairn — Gestion de traces GPX

<img src="geocairn/resources/logo.svg" alt="" width="72" align="right">

Application de bureau Windows pour créer, organiser et éditer des traces de
randonnée (GPX). Carte interactive, dessin à la souris, altitude IGN, profil
altimétrique, arborescence de dossiers, import et export GPX. Voir
[PLAN.md](PLAN.md) pour le plan par jalons.

![licence MIT](https://img.shields.io/badge/licence-MIT-blue)
![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)
![Windows](https://img.shields.io/badge/plateforme-Windows-blue)

## Télécharger

L'installeur Windows est joint à chaque version publiée :

**[→ Dernière version](https://github.com/Sebydroid/GeoCairn/releases/latest)**

Récupérer `GeoCairn-<version>-installation.exe` et le lancer. L'installation se
fait dans le profil de l'utilisateur : **aucun droit d'administrateur** n'est
demandé, et chaque compte du poste a ses propres traces.

L'installeur n'est pas signé numériquement — une signature de code coûte
plusieurs centaines d'euros par an. Windows affiche donc un avertissement
SmartScreen au premier lancement : *Informations complémentaires* → *Exécuter
quand même*.

Une fois installé, **le logiciel prévient lui-même quand une nouvelle version
paraît** (voir [Mise à jour automatique](#mise-à-jour-automatique)).

## Nom et identité

Le logiciel s'est d'abord appelé Carto — nom déjà porté par le logiciel qu'il
remplace (Carto Explorer) et par une plateforme cartographique connue.

Le logo reprend le cairn qui balise les sentiers de montagne : un empilement de
pierres laissé par ceux qui sont passés avant, surmonté d'un point de position
qui émet vers les satellites. C'est ce que fait le logiciel — poser des points
qui marquent un itinéraire.

Deux orthographes cohabitent, et ce n'est pas un oubli :

| Forme | Où | Pourquoi |
| --- | --- | --- |
| `Géo Cairn` | titre de fenêtre, menus, installeur, raccourcis, GPX produits | le nom, tel qu'il se lit |
| `GeoCairn` | exécutable, dossiers, mutex, en-tête réseau, paquet Python | un chemin accentué finit toujours par se faire recoder de travers |

Les deux valeurs vivent dans [geocairn/\_\_init\_\_.py](geocairn/__init__.py)
(`APP_NAME` et `APP_SLUG`) ; aucun autre fichier ne doit écrire le nom en dur.

Le dessin de référence est [logo.svg](geocairn/resources/logo.svg).
`python outils/logo.py` en tire `geocairn.ico`, l'icône Windows à sept
résolutions portée par l'exécutable, les raccourcis et la fenêtre. En dessous de
32 pixels, un tracé allégé — deux pierres et une seule onde — prend le relais :
le dessin complet s'y réduirait à une tache. Le fichier `.ico` est versionné,
Pillow n'est donc nécessaire que pour le refaire.

## Installation

```bash
python -m venv venv
source venv/Scripts/activate
pip install -r requirements.txt
```

## Lancement

```bash
python main.py
```

## Tests

```bash
pytest tests/
```

Les tests ne touchent jamais à Internet : le service altimétrique est coupé
d'office, ceux qui le concernent fournissant leur propre transport simulé. Les
scripts `tests/check_*.py` sont des diagnostics à lancer à la main, hors
pytest : ils dépendent du réseau, d'une construction préalable ou de la
machine.

## Organisation du code

| Chemin | Rôle |
| --- | --- |
| `main.py` | Point d'entrée |
| `geocairn/config.py` | Emplacement des données utilisateur (AppData) |
| `geocairn/database.py` | Base SQLite : dossiers, traces, points |
| `geocairn/models.py` | Structures de données (`Folder`, `Track`, `Point`) |
| `geocairn/geo.py` | Distances, longueur d'une trace, rectangle englobant |
| `geocairn/editor.py` | Trace brouillon maintenue en mémoire pendant la saisie |
| `geocairn/gpx.py` | Lecture et écriture du format GPX |
| `geocairn/ui/main_window.py` | Fenêtre principale (arborescence + carte) |
| `geocairn/ui/tree_panel.py` | Panneau de gauche : bibliothèque de traces |
| `geocairn/ui/points_panel.py` | Liste des points de la trace en cours d'édition |
| `geocairn/ui/icons.py` | Ampoules d'affichage, dessinées à la volée |
| `geocairn/ui/toolbar_icons.py` | Icônes de la barre d'outils, dessinées à la volée |
| `geocairn/simplify.py` | Décimation d'une trace (Ramer-Douglas-Peucker) |
| `geocairn.spec` | Recette de construction de l'exécutable Windows |
| `build.py` | Construction, allègement, archive, installeur, contrôle |
| `installateur.iss` | Recette de l'installeur `.exe` (Inno Setup) |
| `outils/installer.ps1` | Installation sans outil supplémentaire |
| `outils/livraison.py` | Règles d'allègement, vérifiées par les tests |
| `geocairn/ui/profile_panel.py` | Profil sous la carte : altitude ou vitesse |
| `geocairn/ui/widgets.py` | Étiquette abrégée, partagée par les panneaux |
| `geocairn/elevation.py` | Altitude des points par le service IGN |
| `geocairn/ui/elevation_fetcher.py` | Altitude en arrière-plan pendant la saisie |
| `geocairn/updates.py` | Recherche d'une nouvelle version sur GitHub |
| `geocairn/ui/update_checker.py` | La même, en arrière-plan, au démarrage |
| `geocairn/mutex.py` | Marque de présence lue par l'installeur |
| `geocairn/ui/map_view.py` | Carte Leaflet dans un `QWebEngineView` |
| `geocairn/resources/map.html` | Carte : couches, évènements, pont JS ↔ Python |
| `geocairn/resources/leaflet/` | Leaflet 1.9.4 embarqué (fonctionnement hors ligne) |
| `geocairn/resources/logo.svg` | Dessin de référence du logo |
| `geocairn/resources/geocairn.ico` | Icône Windows, sept résolutions |
| `outils/logo.py` | Dessin du logo et fabrication du `.ico` |

## Livraison Windows

### Construire

```bash
python build.py                  # le programme, dans dist/GeoCairn/
python build.py --archive        # + archive ZIP prête à distribuer
python build.py --installateur   # + installeur .exe (voir plus bas)
python build.py --console        # variante gardant une console, pour diagnostiquer
```

Le script enchaîne la construction et un **contrôle de la livraison** : il lance
le programme produit avec `--autotest`, qui vérifie que les ressources
embarquées sont présentes, que la carte se charge, **qu'une trace s'y dessine**
et que la base s'ouvre au bon endroit. Une livraison incomplète est ainsi
détectée à la construction, et non chez l'utilisateur. La même commande sert
après coup :

```bash
GeoCairn.exe --autotest        # contrôler une livraison déjà installée
```

Le mode « un dossier » est retenu plutôt que le fichier unique : le moteur de
carte embarque son propre processus de rendu et des centaines de mégaoctets de
ressources, qu'un fichier unique devrait extraire à chaque lancement.

**La construction dépend de ce qui traîne sur le `PATH`.** PyInstaller y cherche
les dépendances des bibliothèques natives — et non dans l'environnement virtuel,
même si la commande en vient. Sur une machine où Anaconda est installé, il
embarquait ainsi ses bibliothèques ICU, que Qt trouvait alors dans le dossier de
l'application et qui l'empêchaient de démarrer. `build.py` restreint donc le
`PATH` au système et à l'environnement virtuel du projet, ce qui règle le
problème à la source ; [geocairn.spec](geocairn.spec) garde un filtre en second rideau,
au cas où la construction serait lancée autrement.

### Taille de la livraison

329 Mo, dont **195 Mo pour le seul moteur de rendu de la carte** : c'est
Chromium, embarqué par Qt WebEngine. Cette part est incompressible tant que la
carte reste interactive.

La recette écarte ce qui ne sert jamais, soit 184 Mo :

| Écarté | Gain |
| --- | --- |
| Outils de développement web de Chromium (panneaux d'inspection) | 83 Mo |
| Traductions autres que français et anglais | 52 Mo |
| Modules Qt sans rapport (3D, contrôles Quick, multimédia, PDF…) | 47 Mo |

L'archive ZIP compressée pèse **139 Mo**. Une économie supplémentaire de 20 Mo
serait possible en retirant `opengl32sw.dll`, le rendu logiciel de secours ;
elle n'a pas été faite, car la carte resterait blanche sur un poste dépourvu de
pilote graphique correct.

### Installer

**Sans rien à installer d'autre** : décompresser `GeoCairn-<version>.zip`, puis
double-cliquer sur `Installer.bat`. Le programme est copié dans le profil de
l'utilisateur (`%LOCALAPPDATA%\Programs\GeoCairn`), avec raccourcis au menu
Démarrer et sur le Bureau, et une entrée dans « Applications et
fonctionnalités ». Aucun droit d'administrateur n'est demandé.
`Desinstaller.bat` fait l'inverse, et **demande** avant de toucher aux traces.

**Installeur `.exe` classique** : `python build.py --installateur` produit
`dist-installeur\GeoCairn-<version>-installation.exe` (92 Mo — mieux compressé que
l'archive ZIP). Il faut pour cela Inno Setup, outil gratuit à installer une
seule fois :

```bash
winget install JRSoftware.InnoSetup
```

Sans lui, la construction le signale et se poursuit : l'archive et son
`Installer.bat` restent utilisables. Inno Setup s'installe indifféremment pour
la machine ou pour le seul utilisateur — winget choisit le second, dans
`AppData` : les deux emplacements sont explorés, et le registre sert de dernier
recours.

`python tests/check_installateur.py` vérifie l'installeur produit de bout en
bout : installation silencieuse dans un dossier temporaire, autotest du
programme installé, désinstallation, puis contrôle que plus rien ne subsiste.

### Mise à jour automatique

**Le logiciel installé va voir tout seul s'il existe une version plus récente.**
Trois secondes après l'ouverture de la fenêtre, il interroge l'API publique de
GitHub — sans clé d'accès, et sans rien envoyer de l'utilisateur ni de ses
traces :

    https://api.github.com/repos/Sebydroid/GeoCairn/releases/latest

S'il y a du neuf, une boîte annonce le numéro de la nouvelle version et ses
nouveautés, et propose trois choses : **Télécharger**, **Plus tard**, ou
**Ignorer cette version** — cette dernière ne revient alors plus au lancement
suivant. *Aide → Rechercher les mises à jour…* force une recherche à tout moment.

La discrétion est la règle :

- **une fois par jour au plus** ; la date est notée dans la bibliothèque de
  l'utilisateur ;
- **rien ne s'affiche** s'il n'y a pas de nouveauté, ou si GitHub ne répond
  pas : un lancement hors connexion se passe exactement comme les autres ;
- l'appel part **dans un fil séparé**, avec un délai maximal de dix secondes :
  un service lent ne retarde jamais l'affichage de la fenêtre ;
- **depuis les sources, la recherche automatique ne part pas** — il n'y aurait
  pas d'installeur à proposer, on met à jour avec `git pull`. Le menu, lui,
  fonctionne partout.
- `GEOCAIRN_SANS_MAJ=1` débranche la recherche automatique.

Le téléchargement est confié au **navigateur** : il sait reprendre une coupure,
et l'utilisateur voit ce qu'il récupère. Le logiciel ne se remplace jamais
lui-même pendant qu'il tourne — un programme qui fait cela est une source
d'ennuis sans commune mesure avec le gain.

**Le programme ouvert au moment d'installer** est le piège classique : Windows
retient les fichiers d'un programme qui tourne, et l'installation s'arrêterait à
mi-chemin en laissant un mélange de deux versions. Trois gardes-fous se
complètent : la boîte qui suit le téléchargement le rappelle et propose de
fermer Géo Cairn tout de suite ; l'installeur s'en aperçoit tout seul grâce à la
marque de présence posée par le programme (`AppMutex`, voir
[geocairn/mutex.py](geocairn/mutex.py)) et propose de le fermer ; et le script
`installer.ps1` de la voie ZIP refuse d'installer par-dessus un programme
ouvert, avant toute suppression.

La procédure de publication d'une version est dans
[PUBLICATION.md](PUBLICATION.md).

### Mettre à jour à la main

Il n'y a rien à installer pour utiliser le logiciel : copier le dossier `GeoCairn`
où l'on veut et lancer `GeoCairn.exe` suffit aussi.

**Mettre à jour, c'est remplacer ce dossier.** Les traces n'y sont pas : elles
vivent dans `AppData` (voir ci-dessous), que la mise à jour ne touche jamais. La
marche à suivre :

1. fermer Géo Cairn ;
2. supprimer l'ancien dossier `GeoCairn`, ou le renommer pour pouvoir revenir en
   arrière ;
3. y déposer le nouveau ;
4. relancer `GeoCairn.exe`.

La base est **mise à niveau automatiquement** si le nouveau logiciel attend un
format plus récent : colonnes ajoutées, données conservées. L'opération se fait à
la première ouverture, sans rien demander. Deux tests reconstituent ce
scénario — une mise à jour qui efface le dossier d'installation, et une base
ancienne ouverte par la version du jour.

## Sécurité des données

La base SQLite est stockée hors du répertoire d'installation, dans
`C:\Users\[Nom]\AppData\Local\GeoCairn\geocairn.db`. Elle est mise à niveau
automatiquement quand le schéma évolue, sans perte de données.

Cela vaut aussi pour la version compilée : l'emplacement est déterminé par le
compte Windows, jamais par l'endroit d'où le programme s'exécute. Des tests le
vérifient dans les deux cas, en simulant l'exécutable installé.

**Sauvegarder ses traces**, c'est copier ce seul fichier `geocairn.db` — ou
exporter les traces en GPX, format lisible par n'importe quel autre logiciel. Une mise à jour du logiciel
(remplacement de l'exécutable) ne peut donc pas effacer les traces.
La variable d'environnement `GEOCAIRN_DATA_DIR` permet de surcharger cet
emplacement (utilisée par les tests).

**Une installation venant de l'époque « Carto »** retrouve ses traces toute
seule : au premier lancement, si `...\AppData\Local\GeoCairn\geocairn.db`
n'existe pas encore et que `...\AppData\Local\Carto\carto.db` est là, la base
est recopiée sous le nouveau nom. Une copie, et non un déplacement : l'ancien
dossier reste en place comme filet.

## Avancement

- **Jalon 1 — Architecture et squelette** : fait.
  Fenêtre en deux panneaux, base SQLite dans AppData, tables dossiers / traces /
  points GPS.
- **Jalon 2 — Carte interactive** : fait.
  Leaflet embarqué, déplacement et zoom, cinq fonds de carte (OpenStreetMap,
  Aérienne/Satellite, IGN Plan, IGN Carte topographique, Photos aériennes IGN),
  pont bidirectionnel JavaScript ↔ Python (clic, déplacement, changement de
  couche).
  `python tests/check_tiles.py` vérifie que les cinq flux répondent.

  *Réserve* : le SCAN 25 de l'IGN (1:25000) n'est plus diffusé librement sur la
  Géoplateforme et exige désormais une licence payante. La couche « IGN Carte
  topographique » (gratuite) le remplace ; son ajout restera possible plus tard
  si une clé est fournie.
- **Jalon 3 — Création de traces et interaction carte** : fait.
  Bouton « Créer une trace » (mode saisie, curseur en croix), chaque clic gauche
  ajoute un point, les points sont reliés par une polyligne, annulation du
  dernier point (Ctrl+Z), effacement du brouillon, longueur cumulée affichée en
  temps réel. Le brouillon est conservé en mémoire même après la sortie du mode
  saisie.
- **Jalon 4 — Arborescence et sauvegarde locale** : fait.
  Enregistrement du brouillon en base (`Ctrl+S`), création / renommage /
  suppression de dossiers et sous-dossiers, glisser-déposer d'une trace vers un
  dossier, menu contextuel au clic droit, export GPX 1.1.
- **Jalon 5 — Import et affichage des traces existantes** : fait.
  Import d'un ou plusieurs fichiers GPX (`Ctrl+I`), double-clic sur une trace
  pour l'afficher et cadrer la carte dessus, repères de départ et d'arrivée.
- **Jalon 6 — Édition avancée des traces** : fait.
  Reprise d'une trace pour la prolonger, fermeture en boucle, déplacement d'un
  point à la souris, suppression d'un point ou d'une sélection, découpage en
  deux, fusion de deux traces, duplication.
- **Interface** : affichage simultané de plusieurs traces, ampoules d'affichage
  dans l'arborescence, couleur et transparence par trace, barre d'outils
  allégée de ses doublons.
- **Jalon 7 — Finalisation et déploiement Windows** : fait.
  Exécutable `.exe` construit par PyInstaller, autotest de la livraison,
  isolation des données vérifiée y compris en version compilée, stratégie de
  mise à jour documentée et testée.

## Utilisation

### Créer et enregistrer une trace

1. Cliquer sur **Créer une trace** dans la barre d'outils (ou `Ctrl+N`).
2. Cliquer sur la carte pour poser les points ; ils se relient au fur et à
   mesure, le départ est marqué en vert.
3. `Ctrl+Z` annule le dernier point (le raccourci fonctionne aussi lorsque la
   carte a le focus).
4. Le nombre de points et la longueur cumulée s'affichent en bas à droite.
5. **Enregistrer la trace** (`Ctrl+S`) la range dans le dossier sélectionné à
   gauche. Il faut au moins deux points.

### Ranger ses traces

- **Nouveau dossier** crée un sous-dossier dans la sélection courante. Deux
  dossiers de même nom ne peuvent pas coexister au même niveau.
- Le **clic droit** ouvre un menu : renommer, supprimer, exporter en GPX.
- Traces **et** dossiers se **glissent-déposent**. Un dossier ne peut pas être
  déposé dans lui-même ni dans l'un de ses sous-dossiers : le dépôt est refusé
  dès le survol.
- Deux traces d'un même dossier ne peuvent pas porter le même nom : la nouvelle
  venue est suffixée (`Rallye 2`). Un renommage vers un nom déjà pris est refusé
  avec un message, plutôt que renommé dans le dos de l'utilisateur.
- L'arborescence se manipule comme un explorateur de fichiers : **F2** renomme,
  **Suppr** supprime après confirmation, **Ctrl** et **Maj** étendent la
  sélection, et **Ctrl+C / Ctrl+X / Ctrl+V** copient, coupent et collent. Copier
  un dossier recopie tout son contenu ; si le nom est déjà pris à l'arrivée, la
  copie est renommée.
- Le glisser-déposer emporte **toute la sélection**. Un élément déjà contenu
  dans un dossier lui aussi sélectionné reste à sa place : le dossier l'emmène.
- Supprimer un dossier supprime aussi son contenu, après confirmation.

### Afficher les traces

Plusieurs traces peuvent être affichées en même temps, chacune avec sa couleur.

- L'**ampoule**, juste à gauche du logo de la trace ou du dossier, allume ou
  éteint l'affichage. Sur un dossier, elle agit sur toutes les traces qu'il
  contient, sous-dossiers compris ; elle est à demi allumée quand une partie
  seulement est visible.
- Le **clic droit** propose *Afficher*, *Afficher seulement ceci*, *Masquer* et
  *Zoom sur la trace* (ou sur le dossier, qui cadre alors l'ensemble). Zoomer
  affiche la trace si elle était masquée.
- **Double-cliquer** sur une trace l'affiche et cadre la carte dessus.
- Le menu **Couleur** (clic droit sur une trace) propose huit teintes et un
  sous-menu **Transparence** en pourcentage — 0 % pour une trace opaque, ou une
  valeur libre jusqu'à 95 %. La couleur choisie teinte aussi le nom dans
  l'arborescence.

Chaque trace porte un repère vert au départ et rouge à l'arrivée, et son nom
apparaît en infobulle au survol. Le brouillon en cours de saisie reste en rouge
vif, distinct des traces enregistrées.

Les traces affichées sont **mémorisées** : elles sont réaffichées au prochain
lancement, avec leur couleur et leur transparence.

### Modifier une trace existante

**Modifier la trace** (barre d'outils ou clic droit) reprend la trace
sélectionnée : ses points passent en édition, la carte se cadre dessus et le
panneau du bas les liste un par un.

- **Prolonger** : cliquer sur la carte, en dehors du tracé, ajoute des points à
  la suite.
- **Insérer un point** : cliquer sur le tracé lui-même l'ajoute à cet endroit,
  entre les deux points du segment visé.
- **Déplacer un point** : le glisser à la souris.
- **Sélectionner un point** : le cliquer sur la carte, ou cliquer sa ligne dans
  le panneau ; il apparaît en jaune des deux côtés.
- **Supprimer** : clic droit sur un point de la carte puis *Supprimer*, ou
  sélection multiple dans le panneau puis **Supprimer**.

Le panneau liste le numéro, les coordonnées, l'altitude et la distance parcourue
depuis le départ, point par point. Il reste rempli **hors mode édition** : sélectionner une trace dans l'arborescence
affiche ses points en consultation, les boutons de modification étant inactifs
tant qu'elle n'est pas reprise.

**Inverser le sens** (clic droit sur une trace) retourne l'ordre des points.
Le sens de parcours est visible sur la carte : des flèches jalonnent chaque
trace affichée, du départ vers l'arrivée.

## Altitude et profil

### D'où vient l'altitude ?

Une trace dessinée à la main n'a aucune altitude, et tous les GPX n'en portent
pas.

**Pendant le dessin, l'altitude est récupérée automatiquement** : chaque point
posé — ou déplacé — interroge l'IGN en arrière-plan, sans bloquer l'interface.
Un point déplacé perd son ancienne altitude en attendant celle de son nouvel
emplacement.

**Sans connexion, rien ne s'interrompt** : l'échec est signalé dans la barre
d'état, et après trois tentatives infructueuses la récupération automatique se
met en veille au lieu de solliciter un service absent. Le dessin, le
déplacement de points et l'enregistrement restent pleinement utilisables.
`python tests/check_hors_ligne.py` le vérifie en détournant le service vers une
adresse injoignable.

**Calculer l'altitude (IGN)** (clic droit sur une trace) traite d'un coup une
trace entière. Les deux chemins interrogent le service de calcul altimétrique
de la Géoplateforme, qui s'appuie sur le RGE ALTI de l'IGN :

    https://data.geopf.fr/altimetrie/1.0/calcul/alti/rest/elevation.json

Ce service est **gratuit et sans clé d'accès**. Il n'y a donc **aucun MNT à
télécharger** : le RGE ALTI complet pèse des dizaines de gigaoctets, pour un
résultat équivalent. En contrepartie, le calcul demande une connexion à
Internet et se limite au territoire français ; hors couverture, les altitudes
restent vides.

Mesuré sur un parcours réel du projet : 255 points en 2 secondes, avec un écart
moyen de 2,6 m par rapport à l'altitude enregistrée dans le fichier GPX.
`python tests/check_altimetrie.py` refait cette vérification.

L'altitude du fichier n'est jamais écrasée : les deux sources coexistent et se
comparent. Dans la liste des points, une altitude calculée est signalée par
« ~ ».

### Le profil

Sous la carte, le profil de la trace sélectionnée. L'axe des abscisses porte la
distance parcourue. Trois grandeurs se cochent, **seules ou ensemble** :

- **Altitude du fichier** — celle enregistrée dans le GPX ;
- **Altitude IGN** — celle calculée par le service ;
- **Vitesse** — déduite des horodatages du fichier, en km/h.

Les grandeurs de même unité partagent une échelle : les deux altitudes se
superposent donc directement, en mètres à gauche, tandis que la vitesse prend
l'axe de droite en km/h. Une légende rappelle les couleurs.

Les grandeurs absentes de la trace sont grisées, l'infobulle expliquant ce qui
manque. Survoler le profil affiche la distance et toutes les valeurs à cet
endroit.

Sous le tracé, les chiffres clés : **distance totale**, **dénivelés cumulés
positif et négatif**, **vitesse maximale** et **vitesse moyenne**. Cette
dernière rapporte la distance au temps total : les arrêts comptent.

La **molette** zoome sur l'axe des distances, autour du curseur ; l'échelle
verticale s'ajuste à la portion visible. Un **double-clic** revient à la vue
d'ensemble.

### Les trois vues sont liées

Carte, liste des points et profil désignent toujours les mêmes points.
Sélectionner dans l'une met en évidence dans les deux autres, et la carte se
centre dessus — en édition comme en consultation. La sélection multiple dans la
liste (Ctrl ou Maj) se répercute elle aussi sur la carte et sur le profil.
- **Fermer la boucle** ramène le tracé à son point de départ.
- **Découper ici** coupe la trace en deux au point sélectionné. Le point de
  coupure appartient aux deux moitiés, qui restent donc jointives. La seconde
  moitié devient une trace « (suite) ». Le découpage n'agit que sur une trace
  déjà enregistrée.
- **Enregistrer** (`Ctrl+S`) écrit directement dans la trace reprise, sans rien
  demander ; une trace neuve demande son nom. L'enregistrement referme les modes
  *Créer* et *Modifier*.

Pendant une modification, la trace concernée porte un **crayon** dans
l'arborescence, et c'est le bouton *Modifier la trace* qui apparaît enfoncé.
Le relever quitte la modification.

**Fusionner avec…** (clic droit) ajoute une autre trace à la suite de celle
sélectionnée ; les deux traces d'origine sont remplacées par la fusion.
**Dupliquer la trace** en crée une copie indépendante dans le même dossier,
suffixée `-copie` pour qu'on ne la confonde pas avec l'originale.

### Alléger une trace trop dense

Un enregistreur GPS pose un point par seconde : une sortie de trois heures en
compte des milliers, difficiles à retoucher. **Décimer la trace…** (clic droit)
rappelle le nombre de points actuel et demande combien en garder, puis crée une
copie allégée suffixée `-décimé`. L'originale n'est pas touchée.

Le tri n'est pas fait au hasard ni un point sur deux : chaque point reçoit un
poids — l'aire du triangle qu'il forme avec ses voisins — et seuls les plus
lourds sont conservés. Les longues lignes droites fondent, les virages restent,
et le compte demandé est respecté exactement. Le départ et l'arrivée ne sont
jamais retirés.

### Importer et exporter

- **Importer un GPX** (`Ctrl+I`) accepte plusieurs fichiers d'un coup et les
  range dans le dossier sélectionné. Un fichier contenant plusieurs `<trk>`
  donne autant de traces. Les fichiers illisibles sont signalés sans
  interrompre l'import des autres.
- Clic droit sur une trace → **Exporter en GPX…**, ou menu *Fichier*. Le fichier
  produit est du GPX 1.1 standard, relisible par les autres logiciels de
  randonnée.
- Le format GPX n'accepte qu'une altitude par point. Quand la trace en porte
  deux — celle de son fichier d'origine et celle calculée par l'IGN —, le
  logiciel demande laquelle écrire avant d'ouvrir la boîte d'enregistrement.
  S'il n'y en a qu'une, il ne demande rien et l'écrit.

**Points d'intérêt non gérés.** Un GPX ne contenant que des `<wpt>` (relevé de
points remarquables, sans itinéraire) n'a rien à importer : Géo Cairn l'explique
au lieu d'échouer en silence. Le stockage des points d'intérêt n'est pas au plan.

## Note technique

`QApplication` doit toujours recevoir un `argv[0]` non vide : QtWebEngine
(Chromium) interrompt brutalement le processus dans le cas contraire. Un test de
régression couvre ce point (`tests/test_ui.py`).

## Contribuer

Les remarques et les rapports de panne sont bienvenus dans les
[issues](https://github.com/Sebydroid/GeoCairn/issues). Pour une proposition de
code : `pytest tests/` doit passer, les messages de commit sont en français et
commencent par un verbe d'action, et le code suit les conventions des fichiers
voisins — noms français, commentaires qui expliquent *pourquoi* plutôt que
*quoi*.

## Licence

[MIT](LICENSE) — libre de réutilisation, y compris commerciale, en gardant la
mention de copyright.

Le logiciel embarque **Leaflet** (BSD 2 clauses) et s'appuie sur **PyQt6**,
diffusé sous GPL v3 : une redistribution du programme *compilé* emporte donc
les obligations de la GPL v3 pour cette part. Les fonds de carte viennent
d'OpenStreetMap (ODbL) et de la Géoplateforme de l'IGN ; ils ne sont pas
redistribués avec le logiciel. Le détail est en fin de [LICENSE](LICENSE).
