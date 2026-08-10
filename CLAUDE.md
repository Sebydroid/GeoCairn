# Instructions pour Claude (Claude Code)

## Procédure de Fin de Session

Après avoir terminé toutes tes tâches sur ce projet, tu DOIS :

### 1. Commit Git Obligatoire

Faire un commit Git qui résume les tâches effectuées durant la session.

**Format du commit :**
- Commencer par un verbe d'action (ex: "Ajoute", "Crée", "Implémente", "Modifie")
- Suivi d'un bref descriptif clair

### 2. Lancement de l'Application

Après le commit, lancer systématiquement le logiciel pour permettre l'évaluation du résultat.

**Commande de lancement :**
```bash
# Activer l'environnement virtuel si nécessaire
source venv/Scripts/activate

# Lancer l'application
python main.py
```

## Tests Automatiques OBLIGATOIRES

⚠️ **IMPORTANT** : Lorsque tu déploies une fonctionnalité ou que tu corriges une erreur, tu DOIS créer des tests qui te permettent de constater par toi-même si cela a fonctionné.

### Tests à Implémenter

Pour chaque nouvelle fonctionnalité, crée des tests dans le dossier `tests/` :

1. **Tests unitaires** pour les fonctions critiques
2. **Tests d'intégration** pour vérifier les interactions
3. **Tests de régression** pour éviter les réintroductions de bugs

### Exécution des Tests

Avant de considérer une fonctionnalité comme terminée :
1. Lance les tests existants : `pytest tests/`
2. Vérifie que tous les tests passent
3. Si un test échoue, corrige le problème avant de continuer

### Fonctionnalités à Tester Prioritairement

- **Création de traces** : Vérifier que les points sont correctement ajoutés
- **Sauvegarde de traces** : Vérifier que les traces sont enregistrées dans la BDD
- **Fermeture de traces** : Vérifier que la boucle est correctement créée
- **Arborescence** : Vérifier qu'il n'y a pas de doublons
- **Création de dossiers** : Vérifier que les dossiers sont uniques
- Exemple : `Ajoute l'architecture et le squelette de l'interface (Jalon 1)`

**Contenu du commit :**
- Tous les fichiers créés ou modifiés durant la session
- Le message de commit doit être en français
- Doit refléter ce qui a été réellement accompli

### 2. Lancement de l'Application

Après le commit, lancer systématiquement le logiciel pour permettre l'évaluation du résultat.

**Commande de lancement :**
```bash
# Activer l'environnement virtuel si nécessaire
source venv/Scripts/activate

# Lancer l'application
python main.py
```

**Important :**
- L'application doit être lancée à la fin de chaque session de travail
- Elle doit rester ouverte suffisamment longtemps pour que le résultat puisse être observé
- Attendre que l'application soit pleinement fonctionnelle avant de terminer

---

## Contexte du Projet

Projet : Carto - Logiciel de Gestion de Traces GPX
Objectif : Application de bureau Windows pour créer et gérer des traces de randonnée
Architecture : Python + PyQt6 + SQLite + WebEngine (carte interactive)

Voir [PLAN.md](PLAN.md) pour le plan de développement par jalons.
