# PLAN - Logiciel de Gestion de Traces GPX

## 1. Contexte et Objectifs

Le projet consiste à développer un logiciel de bureau pour Windows dédié à la création, la gestion et l'édition de traces de randonnée (fichiers GPX). L'objectif est de proposer une alternative moderne et maintenable à d'anciens logiciels comme GeoCairn Explorer, avec un outil facile à utiliser, destiné à un usage personnel et familial.

## 2. Contraintes Techniques et Choix d'Architecture

Pour garantir la pérennité des données, la facilité de développement et un fonctionnement natif sous Windows, l'architecture suivante est retenue :

- **Technologie principale** : Python avec le framework PyQt6 (ou PySide6) pour l'interface graphique de bureau.
- **Gestion de la carte** : Intégration d'une vue cartographique interactive (via QWebEngineView et Leaflet.js ou PyQtMap) supportant le déplacement et le zoom.
- **Couches cartographiques** : Support des tuiles OpenStreetMap, Imagerie Aérienne/Satellite, et cartes IGN (via flux Géoportail ou équivalent, si possible à l'échelle 1:25000).
- **Base de données** : SQLite (fichier local). Le fichier de base de données sera stocké dans le répertoire utilisateur de Windows (`C:\Users\[Nom]\AppData\Local\NomDuLogiciel\`) pour garantir qu'il ne soit jamais supprimé lors d'une mise à jour du logiciel.
- **Déploiement** : Packaging en exécutable Windows (.exe) via PyInstaller pour une installation simple sans pré-requis technique.

## 3. Fonctionnalités Principales (Cahier des Charges)

### Interface
- **Panneau de gauche** : Arborescence (dossiers, sous-dossiers) pour gérer la bibliothèque de traces.
- **Panneau de droite** : Carte interactive plein écran.

### Gestion des traces (Arborescence)
Création de dossiers/sous-dossiers, copie de traces, import et export au format GPX standard.

### Création et Édition sur carte
- Créer une trace en cliquant sur la carte.
- Reprendre une trace (ajouter des points à la fin).
- Annuler le dernier point ajouté.
- Fermer une trace (créer une boucle).
- Modification point par point (déplacement).
- Suppression de points individuels ou par liste.
- Découper une trace en deux (Split).
- Fusionner plusieurs traces (Merge).

### Sécurité des données
Isolation absolue des données utilisateur lors des mises à jour du logiciel.

## 4. Plan de Développement par Jalons

### Jalon 1 : Architecture et Squelette de l'Interface

**Objectif** : Poser les fondations visuelles et techniques.

- Mise en place du projet Python et de l'environnement de développement.
- Création de la fenêtre principale divisée en deux (Panneau arborescence à gauche, Espace carte à droite).
- Création de la base de données SQLite locale dans AppData.
- Définition des tables (Dossiers, Traces, Points GPS).

### Jalon 2 : Intégration de la Carte interactive

**Objectif** : Afficher la carte et se déplacer.

- Intégration du composant cartographique.
- Affichage des tuiles de base (OpenStreetMap).
- Ajout d'un sélecteur pour basculer entre les couches (Classique, Aérienne/Satellite, IGN).

### Jalon 3 : Création de traces basique et interaction carte

**Objectif** : Cliquer sur la carte pour créer une ligne.

- Ajout du bouton "Créer une trace".
- Activation du mode "Édition" : clic gauche ajoute un point sur la carte.
- Reliage des points par une ligne (polyline).
- Implémentation du bouton "Annuler le dernier point" (Ctrl+Z).
- Maintien de la trace "brouillon" en mémoire.

### Jalon 4 : Gestion de l'arborescence et sauvegarde locale

**Objectif** : Ranger, sauvegarder et retrouver ses traces.

- Sauvegarde de la trace créée dans la base de données SQLite.
- Affichage de la trace dans l'arborescence de gauche.
- Création, renommage et suppression de dossiers/sous-dossiers.
- Glisser-déposer (Drag & Drop) pour déplacer les traces entre dossiers.
- Clic droit sur une trace : "Exporter en GPX".

### Jalon 5 : Importation et affichage des traces existantes

**Objectif** : Voir les anciennes traces sur la carte.

- Bouton "Importer une trace GPX" (parsing du fichier XML).
- Ajout de la trace importée dans l'arborescence et la base de données.
- Double-clic sur une trace : la carte zoome automatiquement et affiche le tracé.

### Jalon 6 : Édition avancée des traces

**Objectif** : Manipuler finement les tracés.

- Reprendre une trace existante pour l'étendre.
- Bouton pour fermer la trace (créer une boucle).
- Édition point par point (glisser un point existant pour le repositionner).
- Suppression d'un point précis ou d'une sélection.
- Découpage d'une trace en deux (Split).
- Fusion de deux traces (Merge).
- Fonction "Dupliquer / Copier" une trace.

### Jalon 7 : Finalisation et Déploiement Windows

**Objectif** : Sécuriser les données et packager le logiciel.

- Test de sécurité des données (vérification du dossier AppData).
- Création de l'exécutable Windows (.exe) via PyInstaller.
- Élaboration de la stratégie de mise à jour (remplacement de l'exécutable sans toucher aux données).

---

*Si ce plan convient, nous pouvons commencer à écrire le code pour le Jalon 1 !*
