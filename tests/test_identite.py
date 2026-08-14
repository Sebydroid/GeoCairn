"""Nom, logo et reprise des données de l'ancien nom.

Le logiciel s'est appelé Carto avant de devenir Géo Cairn. Un renommage touche
des dizaines de fichiers et laisse volontiers deux orthographes derrière lui :
ces tests fixent la règle — le nom accentué pour ce qui s'affiche, le nom nu
pour ce qui sert de chemin — et vérifient qu'une installation existante
retrouve ses traces.
"""

from __future__ import annotations

import re
import struct
from pathlib import Path

import pytest

from geocairn import APP_NAME, APP_SLUG, config

RACINE = Path(__file__).resolve().parent.parent
ICONE = RACINE / "geocairn" / "resources" / "geocairn.ico"


# ------------------------------------------------------------------ le nom


def test_les_deux_formes_du_nom():
    assert APP_NAME == "Géo Cairn"
    assert APP_SLUG == "GeoCairn"


def test_le_nom_technique_ne_sert_que_de_chemin():
    """Sans accent ni espace : c'est toute sa raison d'être."""
    assert APP_SLUG.isascii()
    assert " " not in APP_SLUG


@pytest.mark.parametrize(
    "chemin, attendus",
    [
        # Le dossier de données, le mutex et l'exécutable prennent le nom nu…
        ("geocairn/mutex.py", ['MUTEX_NAME = "GeoCairn.Application.Running"']),
        ("geocairn.spec", ['name="GeoCairn"', 'icon="geocairn/resources/geocairn.ico"']),
        # …le nom affiché, lui, ne s'écrit qu'à un seul endroit.
        ("geocairn/ui/main_window.py", ["APP_NAME"]),
    ],
)
def test_le_nom_est_ecrit_au_bon_endroit(chemin, attendus):
    contenu = (RACINE / chemin).read_text(encoding="utf-8")
    for attendu in attendus:
        assert attendu in contenu, f"{chemin} : {attendu} manquant"


def test_plus_aucune_trace_de_l_ancien_nom_dans_le_code():
    """Un import ou un chemin oublié ne se verrait qu'au lancement.

    Le mot est cherché seul : « cartographique » reste du français, et non un
    reste de l'ancien nom.
    """
    ancien_nom = re.compile(r"\bcarto\b", re.IGNORECASE)
    suspects = []
    for source in RACINE.glob("geocairn/**/*.py"):
        # config.py cite l'ancien nom à dessein : c'est lui qui va y rechercher
        # les traces d'une installation précédente.
        if source.name == "config.py":
            continue
        for numero, ligne in enumerate(
            source.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if ancien_nom.search(ligne):
                suspects.append(f"{source.relative_to(RACINE)}:{numero}  {ligne.strip()}")
    assert not suspects, "\n".join(suspects)


def test_l_installeur_est_lisible_par_inno_setup():
    """Sans marque UTF-8, Inno Setup lit le fichier en ANSI et casse l'accent."""
    brut = (RACINE / "installateur.iss").read_bytes()
    assert brut.startswith(b"\xef\xbb\xbf"), "installateur.iss doit garder son BOM"

    texte = brut.decode("utf-8-sig")
    assert '#define MonNom "Géo Cairn"' in texte
    assert '#define MonIdentifiant "GeoCairn"' in texte
    # Les chemins et le nom du fichier produit passent par l'identifiant.
    assert "DefaultDirName={localappdata}\\Programs\\{#MonIdentifiant}" in texte
    assert "OutputBaseFilename={#MonIdentifiant}-{#MaVersion}-installation" in texte


# ---------------------------------------------------------------- le logo


def test_l_icone_accompagne_les_sources():
    assert ICONE.is_file(), "geocairn.ico doit être versionnée avec le code"


def test_l_icone_porte_toutes_les_resolutions():
    """Windows pioche la taille qu'il lui faut ; il faut donc les fournir.

    L'en-tête d'un fichier .ico se lit sans Pillow : deux entiers courts pour
    l'entête, puis seize octets par image, dont les deux premiers donnent les
    côtés — zéro valant 256.
    """
    brut = ICONE.read_bytes()
    reserve, type_fichier, nombre = struct.unpack("<HHH", brut[:6])
    assert (reserve, type_fichier) == (0, 1), "ce n'est pas une icône Windows"

    tailles = set()
    for index in range(nombre):
        debut = 6 + index * 16
        largeur, hauteur = brut[debut], brut[debut + 1]
        tailles.add((largeur or 256, hauteur or 256))

    for cote in (16, 24, 32, 48, 64, 128, 256):
        assert (cote, cote) in tailles, f"résolution {cote} manquante"


def test_le_dessin_de_reference_accompagne_l_icone():
    """Le SVG est la source ; sans lui, toute retouche repart de zéro."""
    svg = (RACINE / "geocairn" / "resources" / "logo.svg").read_text(encoding="utf-8")
    assert 'viewBox="0 0 64 64"' in svg
    assert "Géo Cairn" in svg


def test_la_fenetre_porte_l_icone():
    """Elle habille la barre des tâches, les boîtes de dialogue et l'alt-tab."""
    from geocairn.app import create_app, icone

    application = create_app(["geocairn-tests"])

    assert not icone().isNull()
    assert not application.windowIcon().isNull()


def test_qt_ne_fabrique_pas_de_chemin_accentue():
    """Le cache du moteur de carte se range sous le nom technique.

    Qt compose ses dossiers de travail avec le nom de l'organisation et celui
    de l'application. Renseigner le nom affiché dans le second faisait écrire
    Chromium dans « ...\\GeoCairn\\Géo Cairn\\cache ». Le nom lisible a son
    propre réglage, `applicationDisplayName`.
    """
    from geocairn.app import create_app

    application = create_app(["geocairn-tests"])

    assert application.applicationName() == APP_SLUG
    assert application.organizationName() == APP_SLUG
    assert application.applicationDisplayName() == APP_NAME


# --------------------------------------------- reprise des données Carto


def test_les_traces_de_l_epoque_carto_sont_reprises(tmp_path):
    ancien = tmp_path / "Carto"
    ancien.mkdir()
    (ancien / "carto.db").write_bytes(b"des traces")
    nouveau = tmp_path / "GeoCairn"
    nouveau.mkdir()

    assert config.reprendre_donnees_heritees(ancien, nouveau) is True
    assert (nouveau / "geocairn.db").read_bytes() == b"des traces"
    # L'ancienne base reste en place : la reprise est une copie, pas un
    # déménagement, pour qu'un incident ne coûte rien.
    assert (ancien / "carto.db").is_file()


def test_les_fichiers_annexes_de_sqlite_suivent_la_base(tmp_path):
    """Un programme fermé brutalement laisse ses dernières traces dans le -wal."""
    ancien = tmp_path / "Carto"
    ancien.mkdir()
    (ancien / "carto.db").write_bytes(b"base")
    (ancien / "carto.db-wal").write_bytes(b"dernieres traces")
    (ancien / "carto.db-shm").write_bytes(b"index")
    nouveau = tmp_path / "GeoCairn"
    nouveau.mkdir()

    assert config.reprendre_donnees_heritees(ancien, nouveau) is True
    assert (nouveau / "geocairn.db-wal").read_bytes() == b"dernieres traces"
    assert (nouveau / "geocairn.db-shm").read_bytes() == b"index"


def test_une_base_deja_en_place_n_est_jamais_ecrasee(tmp_path):
    """La reprise est tentée à chaque lancement : elle doit être sans effet."""
    ancien = tmp_path / "Carto"
    ancien.mkdir()
    (ancien / "carto.db").write_bytes(b"anciennes traces")
    nouveau = tmp_path / "GeoCairn"
    nouveau.mkdir()
    (nouveau / "geocairn.db").write_bytes(b"traces du jour")

    assert config.reprendre_donnees_heritees(ancien, nouveau) is False
    assert (nouveau / "geocairn.db").read_bytes() == b"traces du jour"


def test_sans_installation_precedente_il_ne_se_passe_rien(tmp_path):
    nouveau = tmp_path / "GeoCairn"
    nouveau.mkdir()

    assert config.reprendre_donnees_heritees(tmp_path / "Carto", nouveau) is False
    assert not (nouveau / "geocairn.db").exists()


def test_la_reprise_a_lieu_au_premier_lancement(monkeypatch, tmp_path):
    """Bout en bout : `data_dir()` doit ramener les traces sans rien demander."""
    monkeypatch.delenv(config.ENV_DATA_DIR, raising=False)
    local = tmp_path / "AppData" / "Local"
    (local / "Carto").mkdir(parents=True)
    (local / "Carto" / "carto.db").write_bytes(b"traces d'avant")
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    monkeypatch.setenv("XDG_DATA_HOME", str(local))

    dossier = config.data_dir()

    assert dossier == local / APP_SLUG
    assert (dossier / "geocairn.db").read_bytes() == b"traces d'avant"


def test_un_echec_de_reprise_ne_bloque_pas_le_demarrage(monkeypatch, tmp_path):
    """Mieux vaut une bibliothèque vide qu'un programme qui refuse de s'ouvrir."""
    ancien = tmp_path / "Carto"
    ancien.mkdir()
    (ancien / "carto.db").write_bytes(b"traces")
    nouveau = tmp_path / "GeoCairn"
    nouveau.mkdir()

    def refuser(*_args, **_kwargs):
        raise OSError("disque plein")

    monkeypatch.setattr("geocairn.config.shutil.copy2", refuser)

    assert config.reprendre_donnees_heritees(ancien, nouveau) is False
