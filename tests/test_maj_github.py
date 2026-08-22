"""Recherche d'une nouvelle version sur GitHub.

Ce que ces tests protègent : la seule fonctionnalité du logiciel qui parle à un
service extérieur au démarrage. Elle doit être invisible quand tout va bien, et
plus encore quand tout va mal — GitHub muet, quota dépassé, réponse
fantaisiste. Un plantage au lancement pour cause de mise à jour serait le
comble.

Aucun test ne touche au réseau : chacun fournit son propre transport.
"""

from __future__ import annotations

import json
import urllib.error
from pathlib import Path

import pytest

from geocairn import APP_VERSION, updates
from geocairn.updates import (
    DEPOT,
    PAGE_VERSIONS,
    UpdateError,
    Version,
    derniere_version,
    installeur,
    lire_publication,
    plus_recente,
)

RACINE = Path(__file__).resolve().parent.parent


def publication(tag="v1.1.0", assets=None, **reste) -> bytes:
    """Une réponse de l'API GitHub, réduite aux champs que le logiciel lit."""
    donnees = {
        "tag_name": tag,
        "name": f"Géo Cairn {tag}",
        "body": "- Correction du profil\n- Nouvelle icône",
        "html_url": f"https://github.com/{DEPOT}/releases/tag/{tag}",
        "assets": assets if assets is not None else [
            {
                "name": f"GeoCairn-{tag.lstrip('v')}-installation.exe",
                "browser_download_url":
                    f"https://github.com/{DEPOT}/releases/download/{tag}/"
                    f"GeoCairn-{tag.lstrip('v')}-installation.exe",
            }
        ],
    }
    donnees.update(reste)
    return json.dumps(donnees).encode("utf-8")


def transport(contenu: bytes):
    """Un `fetch` qui rend toujours la même réponse."""
    return lambda _url: contenu


# ------------------------------------------------------ comparaison de versions


@pytest.mark.parametrize(
    "proposee, installee, attendu",
    [
        ("1.1.0", "1.0.0", True),
        ("1.0.1", "1.0.0", True),
        ("2.0.0", "1.9.9", True),
        ("1.0.0", "1.0.0", False),
        ("1.0.0", "1.1.0", False),
        ("0.9.0", "1.0.0", False),
        # Le « v » de l'étiquette Git ne doit pas fausser la comparaison.
        ("v1.1.0", "1.0.0", True),
        ("v1.0.0", "1.0.0", False),
        # Nombres à plus d'un chiffre : une comparaison de texte se tromperait.
        ("1.10.0", "1.9.0", True),
        ("1.2.0", "1.10.0", False),
        # Longueurs différentes : « 1.1 » vaut « 1.1.0 ».
        ("1.1", "1.1.0", False),
        ("1.1.1", "1.1", True),
        # Une version d'essai passe avant la définitive de même numéro.
        ("1.1.0-beta", "1.1.0", False),
        ("1.1.0", "1.1.0-beta", True),
        ("1.1.0-beta.2", "1.0.0", True),
    ],
)
def test_comparaison_des_numeros(proposee, installee, attendu):
    assert plus_recente(proposee, installee) is attendu


def test_une_etiquette_fantaisiste_n_est_jamais_jugee_plus_recente():
    """« livraison-du-jeudi » vaudrait zéro, donc paraîtrait plus ancienne.

    Sans ce garde-fou, une étiquette sans numéro serait comparée à (0, 0, 0) :
    inoffensif ici, mais l'inverse — une étiquette lue comme énorme — ne l'est
    pas. Le refus est explicite plutôt que dépendant du hasard de l'analyse.
    """
    for etiquette in ("", "livraison", "derniere", "v", None):
        assert plus_recente(etiquette, "1.0.0") is False


# ---------------------------------------------------- lecture de la réponse


def test_lecture_d_une_publication():
    version = lire_publication(publication())

    assert isinstance(version, Version)
    assert version.numero == "1.1.0"           # sans le « v »
    assert version.titre == "Géo Cairn v1.1.0"
    assert "Correction du profil" in version.notes
    assert version.page.endswith("/releases/tag/v1.1.0")
    assert version.telechargement.endswith("GeoCairn-1.1.0-installation.exe")


def test_l_installeur_est_reconnu_parmi_les_fichiers_joints():
    """GitHub joint d'office les archives des sources : il ne faut pas les
    proposer à la place du programme."""
    fichiers = [
        {"name": "Source code (zip)", "browser_download_url": "https://x/src.zip"},
        {"name": "GeoCairn-1.1.0.zip", "browser_download_url": "https://x/prog.zip"},
        {
            "name": "GeoCairn-1.1.0-installation.exe",
            "browser_download_url": "https://x/setup.exe",
        },
    ]
    assert installeur(fichiers) == "https://x/setup.exe"


def test_sans_installeur_joint_c_est_la_page_qui_est_proposee():
    """Une publication peut n'avoir que ses sources : mieux vaut la page
    qu'un lien mort."""
    version = lire_publication(publication(assets=[]))
    assert version.telechargement == version.page

    assert installeur(None) == PAGE_VERSIONS
    assert installeur([{"name": "notes.txt"}]) == PAGE_VERSIONS


def test_une_publication_sans_numero_est_refusee():
    with pytest.raises(UpdateError, match="numéro de version"):
        lire_publication(publication(tag="livraison-du-jeudi"))


def test_une_reponse_illisible_est_refusee():
    for contenu in (b"", b"<html>404</html>", b"[]"):
        with pytest.raises(UpdateError):
            lire_publication(contenu)


def test_les_champs_absents_ne_font_pas_tomber_la_lecture():
    """L'API ne garantit ni titre ni texte : un `null` est possible partout."""
    version = lire_publication(
        json.dumps({"tag_name": "v2.0.0", "name": None, "body": None}).encode()
    )
    assert version.numero == "2.0.0"
    assert version.titre == "2.0.0"          # le numéro, à défaut de titre
    assert version.notes == ""
    assert version.telechargement == PAGE_VERSIONS


# ------------------------------------------------------------ pannes réseau


def test_le_reseau_coupe_donne_une_erreur_explicite():
    def injoignable(_url):
        raise OSError("nom de domaine introuvable")

    with pytest.raises(UpdateError, match="injoignable"):
        derniere_version(fetch=injoignable)


def test_un_depot_sans_publication_le_dit():
    """Le cas du premier jour : le dépôt existe, la première release non."""
    def absent(url):
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)

    with pytest.raises(UpdateError, match="Aucune version"):
        derniere_version(fetch=absent)


def test_le_quota_depasse_est_explique():
    def refuse(url):
        raise urllib.error.HTTPError(url, 403, "rate limit exceeded", {}, None)

    with pytest.raises(UpdateError, match="limite"):
        derniere_version(fetch=refuse)


def test_toute_autre_reponse_http_est_signalee():
    def panne(url):
        raise urllib.error.HTTPError(url, 500, "Server Error", {}, None)

    with pytest.raises(UpdateError, match="HTTP 500"):
        derniere_version(fetch=panne)


def test_l_appel_porte_l_identite_du_logiciel_et_va_au_bon_depot():
    """Sans en-tête `User-Agent`, GitHub refuse la requête (HTTP 403)."""
    vues = {}

    def espion(url):
        vues["url"] = url
        return publication()

    derniere_version(fetch=espion)
    assert vues["url"] == f"https://api.github.com/repos/{DEPOT}/releases/latest"

    source = (RACINE / "geocairn" / "updates.py").read_text(encoding="utf-8")
    assert "User-Agent" in source
    assert "TIMEOUT_S" in source, "un appel sans délai maximal bloquerait au démarrage"


# ------------------------------------------------- recherche en arrière-plan


@pytest.fixture
def attendre_qt(qapp):
    """Fait tourner la boucle Qt jusqu'à ce qu'une condition soit vraie."""
    from PyQt6.QtCore import QEventLoop, QTimer

    def attendre(condition, timeout_ms=5000):
        boucle = QEventLoop()
        ecoule = {"ms": 0}
        minuteur = QTimer()

        def battement():
            ecoule["ms"] += 20
            if condition() or ecoule["ms"] >= timeout_ms:
                boucle.quit()

        minuteur.timeout.connect(battement)
        minuteur.start(20)
        boucle.exec()
        minuteur.stop()
        return condition()

    return attendre


@pytest.fixture(scope="session")
def qapp():
    from geocairn.app import create_app

    application = create_app(["geocairn-tests"])
    yield application
    application.processEvents()


def test_une_version_plus_recente_remonte_au_fil_de_l_interface(attendre_qt):
    from geocairn.ui.update_checker import UpdateChecker

    recus = []
    chercheur = UpdateChecker("1.0.0", fetch=transport(publication("v1.1.0")))
    chercheur.terminee.connect(recus.append)

    assert chercheur.check() is True
    assert attendre_qt(lambda: bool(recus))
    assert recus[0].numero == "1.1.0"


def test_un_logiciel_a_jour_ne_remonte_rien(attendre_qt):
    from geocairn.ui.update_checker import UpdateChecker

    recus = []
    chercheur = UpdateChecker("1.1.0", fetch=transport(publication("v1.1.0")))
    chercheur.terminee.connect(recus.append)
    chercheur.check()

    assert attendre_qt(lambda: bool(recus))
    assert recus[0] is None


def test_une_panne_reseau_ne_leve_aucune_exception(attendre_qt):
    """Le fil de fond ne doit rien laisser échapper : une exception qui remonte
    d'un QRunnable emporte le processus."""
    from geocairn.ui.update_checker import UpdateChecker

    def catastrophe(_url):
        raise ValueError("panne inattendue")

    echecs = []
    chercheur = UpdateChecker("1.0.0", fetch=catastrophe)
    chercheur.echouee.connect(echecs.append)
    chercheur.check()

    assert attendre_qt(lambda: bool(echecs))
    assert "panne inattendue" in echecs[0]


def test_une_seule_recherche_a_la_fois(attendre_qt):
    from geocairn.ui.update_checker import UpdateChecker

    chercheur = UpdateChecker("1.0.0", fetch=transport(publication()))
    assert chercheur.check() is True
    assert chercheur.check() is False, "une recherche est déjà en vol"

    chercheur.wait()
    attendre_qt(lambda: not chercheur._en_vol)
    assert chercheur.check() is True


# ------------------------------------------------------ réglages mémorisés


def test_les_reglages_survivent_a_la_fermeture(db):
    from geocairn.database import Database

    db.set_meta("maj_version_ignoree", "1.4.0")
    chemin = Path(db.conn.execute("PRAGMA database_list").fetchone()["file"])
    db.close()

    with Database(chemin) as relue:
        assert relue.get_meta("maj_version_ignoree") == "1.4.0"
        assert relue.get_meta("reglage_inconnu") == ""
        assert relue.get_meta("reglage_inconnu", "repli") == "repli"


def test_un_reglage_reecrit_remplace_le_precedent(db):
    db.set_meta("maj_derniere_recherche", "2026-01-01")
    db.set_meta("maj_derniere_recherche", "2026-01-02")
    assert db.get_meta("maj_derniere_recherche") == "2026-01-02"


# ------------------------------------------------------------- la fenêtre


@pytest.fixture
def fenetre(db, qapp):
    from geocairn.ui.main_window import MainWindow

    window = MainWindow(db=db)
    yield window
    window.close()


def test_le_menu_aide_propose_la_recherche(fenetre):
    assert fenetre.action_check_updates.text() == "Rechercher les &mises à jour…"


def test_la_recherche_automatique_ne_part_pas_depuis_les_sources(fenetre):
    """Il n'y aurait pas d'installeur à proposer : on met à jour avec git."""
    assert fenetre.rechercher_mise_a_jour_au_demarrage() is False


def test_la_recherche_automatique_n_a_lieu_qu_une_fois_par_jour(fenetre, monkeypatch):
    monkeypatch.setattr("geocairn.ui.main_window.is_frozen", lambda: True)
    monkeypatch.delenv("GEOCAIRN_SANS_MAJ", raising=False)
    parties = []
    monkeypatch.setattr(fenetre.update_checker, "check", lambda: parties.append(1) or True)

    assert fenetre.rechercher_mise_a_jour_au_demarrage() is True
    # La date se note à la réception de la réponse, pas au départ.
    fenetre._on_update_result(None)
    assert fenetre.rechercher_mise_a_jour_au_demarrage() is False
    assert len(parties) == 1


def test_la_recherche_automatique_se_debranche(fenetre, monkeypatch):
    monkeypatch.setattr("geocairn.ui.main_window.is_frozen", lambda: True)
    monkeypatch.setenv("GEOCAIRN_SANS_MAJ", "1")
    assert fenetre.rechercher_mise_a_jour_au_demarrage() is False


def test_une_version_ignoree_ne_revient_pas_au_demarrage(fenetre, monkeypatch):
    proposees = []
    monkeypatch.setattr(fenetre, "_proposer_la_mise_a_jour", proposees.append)
    version = lire_publication(publication("v9.9.9"))

    fenetre.db.set_meta("maj_version_ignoree", "9.9.9")
    fenetre._maj_silencieuse = True
    fenetre._on_update_result(version)
    assert proposees == []

    # …mais une recherche demandée par le menu répond quand même.
    fenetre._maj_silencieuse = False
    fenetre._on_update_result(version)
    assert proposees == [version]


def test_une_version_plus_recente_que_l_ignoree_est_proposee(fenetre, monkeypatch):
    proposees = []
    monkeypatch.setattr(fenetre, "_proposer_la_mise_a_jour", proposees.append)
    fenetre.db.set_meta("maj_version_ignoree", "9.9.8")
    fenetre._maj_silencieuse = True

    fenetre._on_update_result(lire_publication(publication("v9.9.9")))
    assert len(proposees) == 1


def test_un_echec_au_demarrage_reste_muet(fenetre, monkeypatch):
    """Ni boîte, ni date notée : le prochain lancement retentera."""
    boites = []
    monkeypatch.setattr(
        "geocairn.ui.main_window.QMessageBox.warning",
        lambda *args, **kwargs: boites.append(args),
    )
    fenetre._maj_silencieuse = True
    fenetre._on_update_failed("GitHub est injoignable")

    assert boites == []
    assert fenetre.db.get_meta("maj_derniere_recherche") == ""


def test_un_echec_demande_par_le_menu_est_annonce(fenetre, monkeypatch):
    boites = []
    monkeypatch.setattr(
        "geocairn.ui.main_window.QMessageBox.warning",
        lambda *args, **kwargs: boites.append(args),
    )
    fenetre._maj_silencieuse = False
    fenetre._on_update_failed("GitHub est injoignable")

    assert len(boites) == 1


def test_le_telechargement_passe_par_le_navigateur(fenetre, monkeypatch):
    """Le logiciel ne se remplace pas lui-même pendant qu'il tourne."""
    ouvertes = []
    monkeypatch.setattr(
        "geocairn.ui.main_window.QDesktopServices.openUrl",
        lambda url: ouvertes.append(url.toString()) or True,
    )
    monkeypatch.setattr(
        "geocairn.ui.main_window.QMessageBox.exec", lambda self: 0
    )
    version = lire_publication(publication("v1.1.0"))

    assert fenetre.telecharger_la_mise_a_jour(version) is True
    assert ouvertes == [version.telechargement]


def test_le_rappel_de_fermer_le_logiciel_est_bien_la():
    """Le piège de la mise à jour lancée fenêtre ouverte : Windows retient les
    fichiers du programme, et l'installation s'arrête à mi-chemin."""
    source = (RACINE / "geocairn" / "ui" / "main_window.py").read_text(
        encoding="utf-8"
    )
    assert "Fermez {APP_NAME} avant de lancer l'installation" in source
    assert "Fermer {APP_NAME} maintenant" in source
    # L'installeur s'en aperçoit tout seul : les deux gardes-fous se complètent.
    assert "AppMutex" in (RACINE / "installateur.iss").read_text(
        encoding="utf-8-sig"
    )


def test_une_reponse_tardive_ne_touche_pas_une_base_fermee(fenetre):
    """La recherche peut aboutir après la fermeture de la fenêtre : une
    exception dans ce slot Qt ferait avorter le processus."""
    fenetre.close()
    assert fenetre.db.closed

    fenetre._on_update_result(lire_publication(publication("v9.9.9")))
    fenetre._on_update_failed("trop tard")


# --------------------------------------------------------- cohérence du dépôt


def test_le_depot_est_le_meme_partout():
    """L'adresse est écrite dans le code et dans la documentation : si l'une
    dérive, la recherche de mise à jour interroge un dépôt fantôme."""
    assert DEPOT == "Sebydroid/GeoCairn"
    for fichier in ("README.md", "PUBLICATION.md"):
        texte = (RACINE / fichier).read_text(encoding="utf-8")
        assert f"github.com/{DEPOT}" in texte, f"{fichier} cite un autre dépôt"


def test_la_version_du_logiciel_est_un_numero_comparable():
    """APP_VERSION sert de référence à toutes les comparaisons."""
    assert updates.est_un_numero(APP_VERSION)
    assert plus_recente(APP_VERSION, APP_VERSION) is False
