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
| `carto/ui/map_view.py` | Carte Leaflet dans un `QWebEngineView` |
| `carto/resources/map.html` | Carte : couches, évènements, pont JS ↔ Python |
| `carto/resources/leaflet/` | Leaflet 1.9.4 embarqué (fonctionnement hors ligne) |

## Sécurité des données

La base SQLite est stockée hors du répertoire d'installation, dans
`C:\Users\[Nom]\AppData\Local\Carto\carto.db`. Une mise à jour du logiciel
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
- Jalons 6 et 7 : à venir (édition avancée, packaging `.exe`).

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

### Consulter une trace

Double-cliquer sur une trace l'affiche en bleu et cadre la carte dessus, avec un
repère vert au départ et rouge à l'arrivée. La barre d'état indique le nombre de
points et la distance. Le brouillon en cours de saisie (rouge) reste visible :
les deux couleurs permettent de ne pas les confondre.

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
