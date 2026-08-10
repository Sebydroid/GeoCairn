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
- Jalons 3 à 7 : à venir.

## Note technique

`QApplication` doit toujours recevoir un `argv[0]` non vide : QtWebEngine
(Chromium) interrompt brutalement le processus dans le cas contraire. Un test de
régression couvre ce point (`tests/test_ui.py`).
