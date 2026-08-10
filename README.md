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
| `carto/ui/map_view.py` | Carte Leaflet dans un `QWebEngineView` |
| `carto/resources/map.html` | Carte : couches, évènements, pont JS ↔ Python |
| `carto/resources/leaflet/` | Leaflet 1.9.4 embarqué (fonctionnement hors ligne) |

## Sécurité des données

La base SQLite est stockée hors du répertoire d'installation, dans
`C:\Users\[Nom]\AppData\Local\Carto\carto.db`. Elle est mise à niveau
automatiquement quand le schéma évolue, sans perte de données. Une mise à jour du logiciel
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
- Jalon 7 : à venir (packaging `.exe`).

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
- Supprimer un dossier supprime aussi son contenu, après confirmation.

### Afficher les traces

Plusieurs traces peuvent être affichées en même temps, chacune avec sa couleur.

- L'**ampoule** à gauche de chaque ligne allume ou éteint l'affichage. Sur un
  dossier, elle agit sur toutes les traces qu'il contient, sous-dossiers
  compris ; elle est à demi allumée quand une partie seulement est visible.
- Le **clic droit** propose *Afficher*, *Afficher seulement ceci*, *Masquer* et
  *Zoom sur la trace* (ou sur le dossier, qui cadre alors l'ensemble). Zoomer
  affiche la trace si elle était masquée.
- **Double-cliquer** sur une trace l'affiche et cadre la carte dessus.
- Le menu **Couleur** (clic droit sur une trace) propose huit teintes, et
  *Couleur et transparence…* ouvre le sélecteur complet, canal alpha compris.
  La couleur choisie teinte aussi le nom dans l'arborescence.

Chaque trace porte un repère vert au départ et rouge à l'arrivée, et son nom
apparaît en infobulle au survol. Le brouillon en cours de saisie reste en rouge
vif, distinct des traces enregistrées.

L'affichage est un état de session : au prochain lancement, aucune trace n'est
affichée. Couleur et transparence, elles, sont enregistrées avec la trace.

### Modifier une trace existante

**Modifier la trace** (barre d'outils ou clic droit) reprend la trace
sélectionnée : ses points passent en édition, la carte se cadre dessus et le
panneau du bas les liste un par un.

- **Prolonger** : cliquer sur la carte ajoute des points à la suite.
- **Déplacer un point** : le glisser à la souris.
- **Sélectionner un point** : le cliquer sur la carte, ou cliquer sa ligne dans
  le panneau ; il apparaît en jaune.
- **Supprimer** : clic droit sur un point de la carte, ou sélection multiple
  dans le panneau puis **Supprimer**.
- **Fermer la boucle** ramène le tracé à son point de départ.
- **Découper ici** coupe la trace en deux au point sélectionné. Le point de
  coupure appartient aux deux moitiés, qui restent donc jointives. La seconde
  moitié devient une trace « (suite) ». Le découpage n'agit que sur une trace
  déjà enregistrée.
- **Enregistrer** (`Ctrl+S`) met à jour la trace reprise — sans créer de
  doublon — et permet au passage de la renommer.

**Fusionner avec…** (clic droit) ajoute une autre trace à la suite de celle
sélectionnée ; les deux traces d'origine sont remplacées par la fusion.
**Dupliquer la trace** en crée une copie indépendante, dans le même dossier.

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
