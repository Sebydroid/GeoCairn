# Publier Géo Cairn sur GitHub

Deux gestes distincts, à ne pas confondre :

- **publier le code** — une seule fois, au départ ;
- **publier une version** — à chaque livraison, c'est elle que le logiciel
  installé va chercher pour proposer sa mise à jour.

Le dépôt visé est <https://github.com/Sebydroid/GeoCairn>. Cette adresse est
écrite dans [geocairn/updates.py](geocairn/updates.py) (`DEPOT`) : la changer
suppose de la changer là aussi, ce qu'un test vérifie.

---

## 1. Créer le dépôt et pousser le code

### Créer le dépôt

Sur <https://github.com/new> :

| Champ | Valeur |
| --- | --- |
| Repository name | `GeoCairn` |
| Description | Logiciel de gestion de traces GPX pour Windows |
| Visibilité | **Public** (une release privée ne serait pas téléchargeable) |
| Add a README / .gitignore / license | **rien** — ils existent déjà ici |

Cocher l'un des trois derniers ajouterait un commit dans le dépôt neuf, et le
premier `git push` serait refusé pour divergence.

### Pousser le code

Le dépôt local pointe aujourd'hui sur GitLab. Pour garder les deux, GitHub
devient `origin` et GitLab prend son nom :

```bash
git remote rename origin gitlab
git remote add origin https://github.com/Sebydroid/GeoCairn.git
git push -u origin master
```

Pour n'avoir que GitHub, remplacer les deux premières lignes par
`git remote set-url origin https://github.com/Sebydroid/GeoCairn.git`.

GitHub demandera de s'authentifier au premier push : ni le mot de passe du
compte ni une clé ne conviennent en HTTPS — il faut un **jeton d'accès
personnel** (Settings → Developer settings → Personal access tokens → Fine-grained
tokens), avec le droit *Contents: read and write* sur ce seul dépôt. Il tient
lieu de mot de passe et se range dans le gestionnaire d'identifiants Windows,
qui ne le redemandera plus.

En SSH (`git@github.com:Sebydroid/GeoCairn.git`), c'est la clé publique du poste
qu'il faut déposer dans Settings → SSH and GPG keys.

### Vérifier

```bash
git remote -v
git log --oneline -1
```

Puis, sur la page du dépôt : le README doit s'afficher, la licence MIT être
reconnue dans le bandeau de droite, et `venv/`, `dist/`, `build/` ne pas
apparaître.

---

## 2. Publier une version

C'est ce que le logiciel installé va chercher. Cinq étapes.

### a. Monter le numéro de version

Un seul endroit fait foi : `APP_VERSION` dans
[geocairn/\_\_init\_\_.py](geocairn/__init__.py).

```python
APP_VERSION = "0.3"
```

Tout en découle : le numéro affiché dans *À propos*, l'en-tête envoyé à GitHub,
la comparaison avec la dernière version publiée, le nom du fichier produit
(`GeoCairn-0.3-installation.exe`) et l'`AppVersion` de l'installeur —
`build.py` le transmet à Inno Setup par `/DMaVersion=`. Le `#define MaVersion`
d'[installateur.iss](installateur.iss) n'est qu'un repli, pour le cas où `iscc`
serait lancé à la main ; il est tenu aligné par cohérence, rien de plus.

Le numéro s'écrit `MAJEUR.MINEUR` tant qu'on est en `0.x`, et passera à
`MAJEUR.MINEUR.CORRECTIF` à la première version stable. Les deux formes se
comparent correctement : `0.3` vaut `0.3.0`.

### b. Construire et contrôler

```bash
source venv/Scripts/activate
pytest tests/
python build.py --installateur
```

`build.py` lance de lui-même l'autotest de la livraison : il ne produit
l'installeur que si le programme construit démarre, charge sa carte et y dessine
une trace. Le fichier attendu est
`dist-installeur\GeoCairn-1.1.0-installation.exe`.

### c. Étiqueter le commit

```bash
git commit -am "Passe en version 1.1.0"
git tag -a v1.1.0 -m "Version 1.1.0"
git push origin master --tags
```

**L'étiquette porte un `v`, le fichier n'en a pas** : `v1.1.0` et
`GeoCairn-1.1.0-installation.exe`. Le logiciel retire le `v` avant de comparer.

### d. Créer la release sur GitHub

Sur <https://github.com/Sebydroid/GeoCairn/releases/new> :

| Champ | Valeur |
| --- | --- |
| Choose a tag | `v1.1.0` (celle qui vient d'être poussée) |
| Release title | `Géo Cairn 1.1.0` |
| Describe this release | les nouveautés, une par ligne, en commençant par `-` |
| Attach binaries | **`GeoCairn-1.1.0-installation.exe`**, glissé dans la zone |
| Set as the latest release | coché |
| Set as a pre-release | décoché |

Trois points comptent pour la mise à jour automatique :

1. **la release doit être « latest »** — c'est cette seule publication que le
   logiciel interroge ; une pré-version est ignorée par GitHub dans ce calcul ;
2. **l'installeur doit être joint** — le nom doit se terminer par
   `-installation.exe`, c'est à cela qu'il est reconnu parmi les fichiers ;
   sans lui, le logiciel ouvre la page de la release et l'utilisateur se
   débrouille ;
3. **le texte de la release est montré à l'utilisateur** dans la boîte de mise à
   jour, tronqué à douze lignes : les nouveautés d'abord, les détails ensuite.

Publier une **pré-version** (case *pre-release* cochée) est le moyen de faire
essayer une version à quelques personnes sans la proposer à tout le monde.

### e. Vérifier que la mise à jour est vue

Sur un poste où une version antérieure est installée, lancer Géo Cairn : la
boîte doit apparaître dans les secondes qui suivent. Sans attendre le
lendemain, *Aide → Rechercher les mises à jour…* force la recherche.

Depuis les sources, la même commande répond aussi :

```bash
python -c "from geocairn.updates import derniere_version; print(derniere_version())"
```

---

## Ce que fait le logiciel installé

Au démarrage, trois secondes après l'ouverture de la fenêtre, la version
compilée interroge l'API publique de GitHub — sans clé d'accès, sans rien
envoyer de l'utilisateur ni de ses traces :

    https://api.github.com/repos/Sebydroid/GeoCairn/releases/latest

- **une fois par jour au plus** : la date de la dernière recherche est notée
  dans la bibliothèque de l'utilisateur ;
- **rien n'est affiché** s'il n'y a pas de nouveauté, ou si GitHub ne répond
  pas — un lancement hors connexion se passe exactement comme les autres ;
- **la version écartée** par le bouton *Ignorer cette version* ne revient pas
  au lancement suivant. Le menu *Aide* permet d'y revenir quand on veut ;
- **depuis les sources, la recherche automatique ne part pas** : il n'y aurait
  pas d'installeur à proposer. Le menu, lui, fonctionne partout.

Le téléchargement est confié au **navigateur** : il sait reprendre une coupure,
et l'utilisateur voit ce qu'il récupère. Le logiciel ne se remplace jamais
lui-même pendant qu'il tourne.

`GEOCAIRN_SANS_MAJ=1` débranche la recherche automatique — pour un poste sans
accès à Internet, ou une salle où l'on ne veut pas de cette boîte.

### Le programme ouvert pendant l'installation

C'est le piège classique : Windows retient les fichiers d'un programme qui
tourne, et l'installation s'arrêterait à mi-chemin en laissant un mélange de
deux versions. Trois gardes-fous se complètent :

1. la boîte qui suit le téléchargement **le rappelle** et propose de fermer
   Géo Cairn tout de suite ;
2. le programme pose une **marque de présence** (`geocairn/mutex.py`) que
   l'installeur interroge (`AppMutex` dans `installateur.iss`) : il s'aperçoit
   donc tout seul que le logiciel tourne et propose de le fermer
   (`CloseApplications=yes`) ;
3. le script `outils/installer.ps1`, pour la voie ZIP, **refuse** d'installer
   par-dessus un programme ouvert — avant toute suppression.

Les traces ne sont pas concernées : elles vivent dans
`%LOCALAPPDATA%\GeoCairn`, que ni l'installation ni la désinstallation ne
touchent.

---

## Rappel : ce que le dépôt ne contient pas

`.gitignore` écarte `venv/`, `build/`, `dist/`, `dist-installeur/`,
`GPX exemples/` et les bases `*.db`. Les livraisons pèsent 330 Mo : elles n'ont
rien à faire dans l'historique Git, c'est le rôle des releases. Vérifier avant
le premier push :

```bash
git status --short
```
