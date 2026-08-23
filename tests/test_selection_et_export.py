"""Sélection multiple et mémoire du dossier d'export.

Ce que ces tests protègent : le moment où l'utilisateur retient plusieurs
traces puis déclenche une action qui n'en traite qu'une. Sans garde-fou, le
logiciel en choisissait une au hasard de l'élément courant et laissait croire
que toute la sélection avait été traitée — et le clic droit détruisait au
passage la sélection qu'on venait de faire.

Et le geste le plus répétitif du logiciel : exporter une trace, en repartant
chaque fois d'un dossier technique d'AppData.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PyQt6.QtCore import QStandardPaths

from geocairn.app import create_app
from geocairn.models import Point
from geocairn.ui.main_window import CLE_DOSSIER_EXPORT, MainWindow
from geocairn.ui.tree_panel import KIND_TRACK

RACINE = Path(__file__).resolve().parent.parent

#: Libellés des actions du clic droit qui ne traitent qu'un seul élément.
MONO_TRACE = [
    "Couleur",
    "Modifier la trace",
    "Inverser le sens",
    "Calculer l'altitude (IGN)",
    "Décimer la trace…",
    "Dupliquer la trace",
    "Fusionner avec…",
    "Exporter en GPX…",
]

#: Celles qui savent traiter toute la sélection et doivent rester actionnables.
MULTIPLES = ["Afficher", "Masquer", "Copier", "Couper"]


@pytest.fixture(scope="session")
def qapp():
    application = create_app(["geocairn-tests"])
    yield application
    application.processEvents()


@pytest.fixture
def fenetre(db, qapp):
    window = MainWindow(db=db)
    yield window
    window.close()


@pytest.fixture
def deux_traces(fenetre):
    """Deux traces enregistrées, l'arborescence à jour."""
    points = [Point(48.930, 1.440), Point(48.931, 1.442), Point(48.932, 1.441)]
    premiere = fenetre.db.create_track("Sentier des crêtes", points=points)
    seconde = fenetre.db.create_track("Tour du lac", points=points)
    fenetre.tree_panel.refresh()
    return premiere, seconde


def retenir(panel, *track_ids) -> None:
    """Met les traces désignées en surbrillance, et elles seules."""
    panel.tree.clearSelection()
    for track_id in track_ids:
        item = panel.find_item(KIND_TRACK, track_id)
        assert item is not None, f"trace {track_id} absente de l'arborescence"
        item.setSelected(True)
        panel.tree.setCurrentItem(item)
    # setCurrentItem sélectionne aussi : on rétablit la sélection voulue.
    panel.tree.clearSelection()
    for track_id in track_ids:
        panel.find_item(KIND_TRACK, track_id).setSelected(True)


def libelles(menu) -> dict:
    """Libellé -> actionnable, pour toutes les entrées d'un menu."""
    return {
        action.text().split("\t")[0]: action.isEnabled()
        for action in menu.actions()
        if action.text()
    }


# ------------------------------------------------------- le verrou lui-même


def test_une_seule_trace_retenue_est_designee(fenetre, deux_traces):
    premiere, _seconde = deux_traces
    retenir(fenetre.tree_panel, premiere)

    assert fenetre.tree_panel.selected_track() == premiere
    assert fenetre.tree_panel.selection_unique() is True


def test_deux_traces_retenues_n_en_designent_aucune(fenetre, deux_traces):
    retenir(fenetre.tree_panel, *deux_traces)

    assert fenetre.tree_panel.selected_track() is None
    assert fenetre.tree_panel.selection_unique() is False


def test_un_dossier_n_est_pas_une_trace(fenetre):
    dossier = fenetre.db.create_folder("Vacances")
    fenetre.tree_panel.refresh()
    item = fenetre.tree_panel.find_item("folder", dossier)
    fenetre.tree_panel.tree.clearSelection()
    item.setSelected(True)

    assert fenetre.tree_panel.selected_track() is None
    # Un seul élément retenu : les actions du dossier restent actionnables.
    assert fenetre.tree_panel.selection_unique() is True


def test_sans_selection_aucune_trace_n_est_designee(fenetre, deux_traces):
    fenetre.tree_panel.tree.clearSelection()
    assert fenetre.tree_panel.selected_track() is None


# ---------------------------------------------- barre d'outils et menu Fichier


def test_exporter_est_grise_des_qu_il_y_a_plusieurs_traces(fenetre, deux_traces):
    premiere, _seconde = deux_traces

    retenir(fenetre.tree_panel, premiere)
    assert fenetre.action_export.isEnabled() is True

    retenir(fenetre.tree_panel, *deux_traces)
    assert fenetre.action_export.isEnabled() is False
    assert "une seule trace" in fenetre.action_export.toolTip().lower()


def test_modifier_est_grise_des_qu_il_y_a_plusieurs_traces(fenetre, deux_traces):
    premiere, _seconde = deux_traces

    retenir(fenetre.tree_panel, premiere)
    assert fenetre.action_resume.isEnabled() is True

    retenir(fenetre.tree_panel, *deux_traces)
    assert fenetre.action_resume.isEnabled() is False


def test_modifier_reste_actionnable_pendant_une_edition(fenetre, deux_traces):
    """Sinon le bouton enfoncé ne pourrait plus être relevé : on resterait
    prisonnier du mode édition."""
    premiere, _seconde = deux_traces
    assert fenetre.resume_track(premiere) is True

    retenir(fenetre.tree_panel, *deux_traces)

    assert fenetre.edit_mode is True
    assert fenetre.action_resume.isEnabled() is True


def test_l_export_refuse_poliment_une_selection_multiple(
    fenetre, deux_traces, monkeypatch
):
    """Le bouton est grisé, mais le menu Fichier reste atteignable."""
    boites = []
    monkeypatch.setattr(
        "geocairn.ui.main_window.QMessageBox.information",
        lambda _parent, titre, texte: boites.append(titre),
    )
    ouvertures = []
    monkeypatch.setattr(
        "geocairn.ui.main_window.QFileDialog.getSaveFileName",
        lambda *a, **k: ouvertures.append(a) or ("", ""),
    )
    retenir(fenetre.tree_panel, *deux_traces)

    fenetre._export_selected_track()

    assert boites == ["Une seule trace à la fois"]
    assert ouvertures == [], "aucune boîte d'enregistrement ne doit s'ouvrir"


# ------------------------------------------------------- menu du clic droit


def test_le_clic_droit_grise_les_actions_mono_trace(fenetre, deux_traces):
    retenir(fenetre.tree_panel, *deux_traces)
    item = fenetre.tree_panel.find_item(KIND_TRACK, deux_traces[0])

    menu = fenetre.tree_panel.build_context_menu(item)
    etats = libelles(menu)

    for libelle in MONO_TRACE:
        assert libelle in etats, f"« {libelle} » a disparu du menu"
        assert etats[libelle] is False, f"« {libelle} » devrait être grisé"


def test_le_clic_droit_laisse_agir_sur_toute_la_selection(fenetre, deux_traces):
    """Afficher, masquer, copier, supprimer savent traiter plusieurs traces."""
    retenir(fenetre.tree_panel, *deux_traces)
    item = fenetre.tree_panel.find_item(KIND_TRACK, deux_traces[0])

    etats = libelles(fenetre.tree_panel.build_context_menu(item))

    for libelle in MULTIPLES:
        assert etats.get(libelle) is True, f"« {libelle} » ne devrait pas être grisé"
    assert etats["Supprimer la trace"] is True


def test_une_seule_trace_laisse_tout_actionnable(fenetre, deux_traces):
    premiere, _seconde = deux_traces
    retenir(fenetre.tree_panel, premiere)
    item = fenetre.tree_panel.find_item(KIND_TRACK, premiere)

    etats = libelles(fenetre.tree_panel.build_context_menu(item))

    for libelle in MONO_TRACE:
        assert etats[libelle] is True, f"« {libelle} » grisé à tort"


def test_le_clic_droit_ne_detruit_plus_la_selection(fenetre, deux_traces):
    """Le geste même d'ouvrir le menu réduisait la sélection à un élément.

    `setCurrentItem` sélectionne : l'utilisateur perdait les autres traces au
    moment précis où il ouvrait le menu pour agir dessus, et l'action portait
    alors sur une seule sans que rien ne le dise.
    """
    retenir(fenetre.tree_panel, *deux_traces)
    item = fenetre.tree_panel.find_item(KIND_TRACK, deux_traces[0])

    fenetre.tree_panel.build_context_menu(item)

    assert len(fenetre.tree_panel.selected_items()) == 2


def test_le_clic_droit_hors_selection_designe_l_element_vise(fenetre, deux_traces):
    """Viser une trace non retenue bascule bien la sélection sur elle."""
    premiere, seconde = deux_traces
    retenir(fenetre.tree_panel, premiere)

    fenetre.tree_panel.build_context_menu(
        fenetre.tree_panel.find_item(KIND_TRACK, seconde)
    )

    assert fenetre.tree_panel.selected_track() == seconde


def test_les_actions_mono_trace_n_emettent_rien_en_selection_multiple(
    fenetre, deux_traces
):
    """Garde-fou de dernier ressort, pour les chemins qui évitent les menus."""
    recus = []
    fenetre.tree_panel.duplicate_requested.connect(recus.append)
    retenir(fenetre.tree_panel, *deux_traces)

    fenetre.tree_panel._emit_for_track(fenetre.tree_panel.duplicate_requested)
    assert recus == []

    retenir(fenetre.tree_panel, deux_traces[0])
    fenetre.tree_panel._emit_for_track(fenetre.tree_panel.duplicate_requested)
    assert recus == [deux_traces[0]]


# ------------------------------------------------ mémoire du dossier d'export


def test_le_dossier_d_export_est_retenu(fenetre, deux_traces, tmp_path, monkeypatch):
    premiere, _seconde = deux_traces
    destination = tmp_path / "Randonnées"
    destination.mkdir()
    choisi = destination / "sentier.gpx"

    monkeypatch.setattr(
        "geocairn.ui.main_window.QFileDialog.getSaveFileName",
        lambda *a, **k: (str(choisi), "Fichiers GPX (*.gpx)"),
    )

    assert fenetre.export_track(premiere, elevation="auto") is not None
    assert fenetre.db.get_meta(CLE_DOSSIER_EXPORT) == str(destination)


def test_l_export_suivant_repart_du_dossier_retenu(
    fenetre, deux_traces, tmp_path, monkeypatch
):
    premiere, seconde = deux_traces
    destination = tmp_path / "Randonnées"
    destination.mkdir()
    fenetre.db.set_meta(CLE_DOSSIER_EXPORT, str(destination))

    proposes = []

    def boite(_parent, _titre, chemin, _filtre):
        proposes.append(chemin)
        return (str(destination / "autre.gpx"), "")

    monkeypatch.setattr(
        "geocairn.ui.main_window.QFileDialog.getSaveFileName", boite
    )

    fenetre.export_track(seconde, elevation="auto")

    assert len(proposes) == 1
    propose = Path(proposes[0])
    assert propose.parent == destination
    # Le nom du fichier reste celui de la trace.
    assert "Tour du lac" in propose.name or "Tour" in propose.name


def test_le_premier_export_part_des_documents(fenetre):
    """Aucun dossier retenu : les Documents, et non le dossier du processus."""
    assert fenetre.db.get_meta(CLE_DOSSIER_EXPORT) == ""

    propose = Path(fenetre._chemin_export_propose("Sentier"))

    documents = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.DocumentsLocation
    )
    if documents:
        assert propose.parent == Path(documents)


def test_un_dossier_disparu_est_ignore(fenetre, tmp_path):
    """Clé USB retirée, partage déconnecté : la boîte ne doit pas s'ouvrir
    sur du vide."""
    fenetre.db.set_meta(CLE_DOSSIER_EXPORT, str(tmp_path / "jamais-cree"))

    propose = Path(fenetre._chemin_export_propose("Sentier"))

    assert propose.parent != tmp_path / "jamais-cree"


def test_un_export_pilote_ne_touche_pas_a_la_memoire(
    fenetre, deux_traces, tmp_path
):
    """Un export avec chemin imposé (tests, automatisation) n'est pas un choix
    de l'utilisateur : il ne doit pas déplacer son dossier habituel."""
    premiere, _seconde = deux_traces
    fenetre.db.set_meta(CLE_DOSSIER_EXPORT, str(tmp_path))

    fenetre.export_track(
        premiere, path=str(tmp_path / "ailleurs" / "t.gpx"), elevation="auto"
    )

    assert fenetre.db.get_meta(CLE_DOSSIER_EXPORT) == str(tmp_path)


def test_la_memoire_survit_a_la_fermeture(fenetre, tmp_path):
    """Le réglage suit la bibliothèque : il est rangé en base, pas en mémoire."""
    fenetre.db.set_meta(CLE_DOSSIER_EXPORT, str(tmp_path))
    assert fenetre._chemin_export_propose("Sentier").startswith(str(tmp_path))


# ----------------------------------------------------------------- à propos


def test_la_dedicace_est_dans_la_boite_a_propos():
    source = (RACINE / "geocairn" / "ui" / "main_window.py").read_text(
        encoding="utf-8"
    )
    assert "Ce logiciel a été créé pour l'anniversaire de mon Papa." in source


def test_la_boite_a_propos_montre_la_dedicace(fenetre, monkeypatch):
    textes = []
    monkeypatch.setattr(
        "geocairn.ui.main_window.QMessageBox.about",
        lambda _parent, _titre, texte: textes.append(texte),
    )

    fenetre._show_about()

    assert len(textes) == 1
    assert "anniversaire de mon Papa" in textes[0]
