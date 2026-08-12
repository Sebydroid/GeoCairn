# Carto — Gestion de traces GPX

Application de bureau Windows pour créer, organiser et éditer des traces de
randonnée (GPX). Voir [PLAN.md](PLAN.md) pour le plan par jalons.

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

## Organisation du code

| Chemin | Rôle |
| --- | --- |
| `main.py` | Point d'entrée |
| `carto/config.py` | Emplacement des données utilisateur (AppData) |
| `carto/database.py` | Base SQLite : dossiers, traces, points |
| `carto/models.py` | Structures de données (`Folder`, `Track`, `Point`) |
| `carto/geo.py` | Distances, longueur d'une trace, rectangle englobant |
| `carto/editor.py` | Trace brouillon maintenue en mémoire pendant la saisie |
| `carto/gpx.py` | Lecture et écriture du format GPX |
| `carto/ui/main_window.py` | Fenêtre principale (arborescence + carte) |
| `carto/ui/tree_panel.py` | Panneau de gauche : bibliothèque de traces |
| `carto/ui/points_panel.py` | Liste des points de la trace en cours d'édition |
| `carto/ui/icons.py` | Ampoules d'affichage, dessinées à la volée |
| `carto/ui/toolbar_icons.py` | Icônes de la barre d'outils, dessinées à la volée |
| `carto/simplify.py` | Décimation d'une trace (Ramer-Douglas-Peucker) |
| `carto.spec` | Recette de construction de l'exécutable Windows |
| `build.py` | Construction, allègement, archive, installeur, contrôle |
| `installateur.iss` | Recette de l'installeur `.exe` (Inno Setup) |
| `outils/installer.ps1` | Installation sans outil supplémentaire |
| `carto/ui/profile_panel.py` | Profil sous la carte : altitude ou vitesse |
| `carto/ui/widgets.py` | Étiquette abrégée, partagée par les panneaux |
| `carto/elevation.py` | Altitude des points par le service IGN |
| `carto/ui/elevation_fetcher.py` | Altitude en arrière-plan pendant la saisie |
| `carto/ui/map_view.py` | Carte Leaflet dans un `QWebEngineView` |
| `carto/resources/map.html` | Carte : couches, évènements, pont JS ↔ Python |
| `carto/resources/leaflet/` | Leaflet 1.9.4 embarqué (fonctionnement hors ligne) |

## Livraison Windows

### Construire

```bash
python build.py                  # le programme, dans dist/Carto/
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
Carto.exe --autotest        # contrôler une livraison déjà installée
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
problème à la source ; [carto.spec](carto.spec) garde un filtre en second rideau,
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

**Sans rien à installer d'autre** : décompresser `Carto-1.0.0.zip`, puis
double-cliquer sur `Installer.bat`. Le programme est copié dans le profil de
l'utilisateur (`%LOCALAPPDATA%\Programs\Carto`), avec raccourcis au menu
Démarrer et sur le Bureau, et une entrée dans « Applications et
fonctionnalités ». Aucun droit d'administrateur n'est demandé.
`Desinstaller.bat` fait l'inverse, et **demande** avant de toucher aux traces.

**Installeur `.exe` classique** : `python build.py --installateur` produit
`dist-installeur\Carto-1.0.0-installation.exe`. Il faut pour cela Inno Setup,
outil gratuit à installer une seule fois :

```bash
winget install JRSoftware.InnoSetup
```

Sans lui, la construction le signale et se poursuit : l'archive et son
`Installer.bat` restent utilisables.

### Mettre à jour

Il n'y a rien à installer pour utiliser le logiciel : copier le dossier `Carto`
où l'on veut et lancer `Carto.exe` suffit aussi.

**Mettre à jour, c'est remplacer ce dossier.** Les traces n'y sont pas : elles
vivent dans `AppData` (voir ci-dessous), que la mise à jour ne touche jamais. La
marche à suivre :

1. fermer Carto ;
2. supprimer l'ancien dossier `Carto`, ou le renommer pour pouvoir revenir en
   arrière ;
3. y déposer le nouveau ;
4. relancer `Carto.exe`.

La base est **mise à niveau automatiquement** si le nouveau logiciel attend un
format plus récent : colonnes ajoutées, données conservées. L'opération se fait à
la première ouverture, sans rien demander. Deux tests reconstituent ce
scénario — une mise à jour qui efface le dossier d'installation, et une base
ancienne ouverte par la version du jour.

## Sécurité des données

La base SQLite est stockée hors du répertoire d'installation, dans
`C:\Users\[Nom]\AppData\Local\Carto\carto.db`. Elle est mise à niveau
automatiquement quand le schéma évolue, sans perte de données.

Cela vaut aussi pour la version compilée : l'emplacement est déterminé par le
compte Windows, jamais par l'endroit d'où le programme s'exécute. Des tests le
vérifient dans les deux cas, en simulant l'exécutable installé.

**Sauvegarder ses traces**, c'est copier ce seul fichier `carto.db` — ou
exporter les traces en GPX, format lisible par n'importe quel autre logiciel. Une mise à jour du logiciel
(remplacement de l'exécutable) ne peut donc pas effacer les traces.
La variable d'environnement `CARTO_DATA_DIR` permet de surcharger cet
emplacement (utilisée par les tests).

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

Le tri n'est pas fait au hasard ni un point sur deux : l'algorithme de
Ramer-Douglas-Peucker écarte les points qui s'écartent peu de la ligne joignant
leurs voisins. Les longues lignes droites fondent, les virages restent. Le
compte obtenu est donc **approchant** et non exact.

### Importer et exporter

- **Importer un GPX** (`Ctrl+I`) accepte plusieurs fichiers d'un coup et les
  range dans le dossier sélectionné. Un fichier contenant plusieurs `<trk>`
  donne autant de traces. Les fichiers illisibles sont signalés sans
  interrompre l'import des autres.
- Clic droit sur une trace → **Exporter en GPX…**, ou menu *Fichier*. Le fichier
  produit est du GPX 1.1 standard, relisible par les autres logiciels de
  randonnée.

**Points d'intérêt non gérés.** Un GPX ne contenant que des `<wpt>` (relevé de
points remarquables, sans itinéraire) n'a rien à importer : Carto l'explique au
lieu d'échouer en silence. Le stockage des points d'intérêt n'est pas au plan.

## Note technique

`QApplication` doit toujours recevoir un `argv[0]` non vide : QtWebEngine
(Chromium) interrompt brutalement le processus dans le cas contraire. Un test de
régression couvre ce point (`tests/test_ui.py`).
