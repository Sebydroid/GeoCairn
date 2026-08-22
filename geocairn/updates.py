"""Recherche d'une version plus récente publiée sur GitHub.

Les livraisons sont déposées dans les « releases » du dépôt, chacune portant
une étiquette de version (`v1.1.0`) et l'installeur Windows en pièce jointe.
Interroger l'API publique de GitHub suffit donc à savoir si le logiciel installé
est dépassé :

    https://api.github.com/repos/<dépôt>/releases/latest

Le service est **gratuit et sans clé d'accès** ; il tolère soixante appels par
heure et par adresse IP, largement de quoi vérifier une fois par jour. Aucune
donnée n'est envoyée : la requête ne dit rien de l'utilisateur ni de ses traces.

Le module ne connaît ni Qt ni l'interface : il rend un objet `Version` ou lève
`UpdateError`. C'est [ui/update_checker.py](ui/update_checker.py) qui l'appelle
depuis un fil de fond, et la fenêtre principale qui décide quoi en montrer.

Le téléchargement n'est **pas** fait par le logiciel : l'adresse est ouverte
dans le navigateur, qui sait reprendre une coupure et où l'utilisateur voit ce
qu'il récupère. Un programme qui se remplace lui-même pendant qu'il tourne est
une source d'ennuis sans commune mesure avec le gain.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass

from . import APP_SLUG, APP_VERSION

#: Compte et dépôt GitHub d'où viennent les versions publiées.
DEPOT = "Sebydroid/GeoCairn"

API_DERNIERE_VERSION = f"https://api.github.com/repos/{DEPOT}/releases/latest"

#: Page des versions, montrée quand la publication ne porte pas d'installeur.
PAGE_VERSIONS = f"https://github.com/{DEPOT}/releases"

#: Court : la recherche a lieu au démarrage, elle ne doit jamais faire attendre.
TIMEOUT_S = 10

#: Reconnaît l'installeur parmi les fichiers joints à la publication. Le nom
#: est celui que produit build.py : « GeoCairn-1.1.0-installation.exe ».
MOTIF_INSTALLEUR = re.compile(r"-installation\.exe$", re.IGNORECASE)


class UpdateError(RuntimeError):
    """La liste des versions n'a pas pu être consultée."""


@dataclass(frozen=True)
class Version:
    """Une version publiée sur GitHub."""

    #: Numéro sans le « v » de l'étiquette : « 1.1.0 ».
    numero: str
    #: Titre donné à la publication, à défaut le numéro.
    titre: str
    #: Texte de la publication (nouveautés), tel qu'écrit, éventuellement vide.
    notes: str
    #: Page de la publication sur GitHub.
    page: str
    #: Adresse à ouvrir pour récupérer le programme : l'installeur s'il est
    #: joint, la page de la publication sinon.
    telechargement: str


# ------------------------------------------------------- numéros de version


def normaliser(version: str) -> str:
    """Numéro nu, sans le « v » que porte l'étiquette Git."""
    return (version or "").strip().lstrip("vV").strip()


def _numeros(version: str) -> tuple[int, ...]:
    """Les nombres du numéro : « 1.2.3-beta » donne (1, 2, 3).

    Un morceau qui n'est pas un nombre vaut zéro plutôt que de faire échouer la
    comparaison : une étiquette mal formée ne doit pas empêcher le démarrage.
    """
    corps = version.partition("-")[0].partition("+")[0]
    return tuple(int(m) if m.isdigit() else 0 for m in corps.split("."))


def _est_preliminaire(version: str) -> bool:
    """Vrai pour « 1.2.0-beta.1 » : une version d'essai, pas une définitive."""
    return "-" in version


def est_un_numero(version: str) -> bool:
    """Vrai si l'étiquette ressemble à un numéro de version.

    Garde-fou contre une étiquette fantaisiste (« livraison-du-jeudi ») qui
    serait sinon comparée à zéro, donc jugée plus ancienne que tout.
    """
    nu = normaliser(version)
    return bool(nu) and nu.partition("-")[0].partition(".")[0].isdigit()


def plus_recente(proposee: str, installee: str) -> bool:
    """Vrai si `proposee` est postérieure à `installee`."""
    a, b = normaliser(proposee), normaliser(installee)
    if not est_un_numero(a):
        return False

    na, nb = _numeros(a), _numeros(b)
    taille = max(len(na), len(nb))
    na += (0,) * (taille - len(na))
    nb += (0,) * (taille - len(nb))
    if na != nb:
        return na > nb

    # Numéros égaux : « 1.1.0 » l'emporte sur « 1.1.0-beta », et rien
    # n'emporte sur une version définitive de même numéro.
    return _est_preliminaire(b) and not _est_preliminaire(a)


# ------------------------------------------------------- appel à l'API GitHub


def _default_fetch(url: str) -> bytes:
    requete = urllib.request.Request(
        url,
        headers={
            "User-Agent": f"{APP_SLUG}/{APP_VERSION}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(requete, timeout=TIMEOUT_S) as reponse:
        return reponse.read()


def derniere_version(fetch=None) -> Version:
    """Dernière version publiée sur GitHub.

    Lève `UpdateError` dès que la réponse n'est pas exploitable : réseau coupé,
    dépôt sans publication, quota dépassé, contenu inattendu. `fetch` permet
    d'injecter un transport de test.
    """
    recuperer = fetch or _default_fetch
    try:
        contenu = recuperer(API_DERNIERE_VERSION)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise UpdateError(
                "Aucune version n'est encore publiée sur GitHub."
            ) from exc
        if exc.code == 403:
            raise UpdateError(
                "GitHub limite temporairement les recherches (trop d'appels "
                "depuis cette connexion). Réessayez plus tard."
            ) from exc
        raise UpdateError(f"GitHub a répondu HTTP {exc.code}.") from exc
    except OSError as exc:
        raise UpdateError(f"GitHub est injoignable : {exc}") from exc

    return lire_publication(contenu)


def lire_publication(contenu: bytes | str) -> Version:
    """Traduit la réponse de l'API en `Version`."""
    try:
        donnees = json.loads(contenu)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise UpdateError(f"Réponse illisible de GitHub : {exc}") from exc
    if not isinstance(donnees, dict):
        raise UpdateError("Réponse inattendue de GitHub.")

    numero = normaliser(donnees.get("tag_name") or "")
    if not est_un_numero(numero):
        raise UpdateError(
            f"La dernière publication ne porte pas de numéro de version "
            f"reconnaissable ({donnees.get('tag_name') or 'étiquette absente'})."
        )

    page = donnees.get("html_url") or PAGE_VERSIONS
    return Version(
        numero=numero,
        titre=(donnees.get("name") or "").strip() or numero,
        notes=(donnees.get("body") or "").strip(),
        page=page,
        telechargement=installeur(donnees.get("assets"), page),
    )


def installeur(fichiers, repli: str = PAGE_VERSIONS) -> str:
    """Adresse de l'installeur joint à la publication, ou `repli` à défaut.

    Une publication peut n'avoir que ses sources — c'est le cas tant que
    l'installeur n'a pas été téléversé. Mieux vaut alors ouvrir la page de la
    publication qu'un lien mort.
    """
    for fichier in fichiers or []:
        if not isinstance(fichier, dict):
            continue
        adresse = fichier.get("browser_download_url")
        if adresse and MOTIF_INSTALLEUR.search(fichier.get("name") or ""):
            return adresse
    return repli
