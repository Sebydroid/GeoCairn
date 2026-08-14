"""Tests du rangement, de la sauvegarde et de l'export (Jalon 4)."""

from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest
from PyQt6.QtCore import QMimeData, QPointF, Qt
from PyQt6.QtGui import QDropEvent
from PyQt6.QtWidgets import QMessageBox

from geocairn.app import create_app
from geocairn.gpx import GPX_NS
from geocairn.ui.main_window import MainWindow
from geocairn.ui.tree_panel import (
    COL_NAME,
    KIND_FOLDER,
    KIND_TRACK,
    ROLE_ID,
    ROLE_KIND,
    TreePanel,
    folder_of,
    is_self_or_descendant,
)

NS = {"gpx": GPX_NS}


@pytest.fixture(scope="session")
def qapp():
    app = create_app(["geocairn-tests"])
    yield app
    app.processEvents()


@pytest.fixture
def panel(qapp, db):
    widget = TreePanel(db)
    widget.resize(320, 700)
    widget.show()
    yield widget
    widget.close()


@pytest.fixture
def window(qapp, db):
    """Une fenêtre par test, chacune avec son moteur web.

    ATTENTION : ce fichier est à la limite de ce que QtWebEngine supporte dans
    un même processus. Quelques tests de plus qui demandent cette fixture, et
    la suite entière meurt — sans message, et plusieurs fichiers plus loin, ce
    qui rend la cause introuvable. Pour de nouveaux tests, préférer une fenêtre
    partagée par le fichier, comme dans `test_export_altitude.py` ou
    `test_robustesse.py`.
    """
    win = MainWindow(db=db)
    yield win
    win.close()


@pytest.fixture
def silence_dialogs(monkeypatch):
    """Neutralise les boîtes de dialogue et enregistre ce qui aurait été montré."""
    shown: list[tuple[str, str]] = []

    def record(kind):
        def handler(_parent, title, text, *args, **kwargs):
            shown.append((title, text))
            return QMessageBox.StandardButton.Yes
        return handler

    for name in ("warning", "information", "critical", "question", "about"):
        monkeypatch.setattr(QMessageBox, name, staticmethod(record(name)))
    return shown


def item_labels(panel: TreePanel, item=None) -> list[str]:
    parent = item if item is not None else panel.tree.topLevelItem(0)
    return [parent.child(i).text(COL_NAME) for i in range(parent.childCount())]


# ------------------------------------------------------ dossiers : création


def test_creation_de_dossier_a_la_racine(panel, db):
    folder_id = panel.create_folder("Alpes")

    assert folder_id is not None
    assert [f.name for f in db.list_folders()] == ["Alpes"]
    assert item_labels(panel) == ["Alpes"]
    assert panel.current_selection() == (KIND_FOLDER, folder_id)


def test_creation_de_sous_dossier_dans_la_selection(panel, db):
    parent = panel.create_folder("Alpes")
    child = panel.create_folder("2026")

    assert db.get_folder(child).parent_id == parent
    parent_item = panel.find_item(KIND_FOLDER, parent)
    assert item_labels(panel, parent_item) == ["2026"]


def test_dossier_en_double_refuse_avec_message(panel, db, silence_dialogs):
    panel.create_folder("Alpes")
    panel.select_folder(None)

    assert panel.create_folder("Alpes") is None
    assert len(db.list_folders()) == 1
    assert any("déjà" in text for _titre, text in silence_dialogs)


def test_nom_de_dossier_vide_refuse(panel, db, silence_dialogs):
    assert panel.create_folder("   ") is None
    assert db.list_folders() == []


# --------------------------------------------- dossiers : renommer, supprimer


def test_renommage_de_dossier(panel, db):
    folder_id = panel.create_folder("Alpe")

    assert panel.rename_selected("Alpes") is True
    assert db.get_folder(folder_id).name == "Alpes"
    assert item_labels(panel) == ["Alpes"]


def test_renommage_en_doublon_refuse(panel, db, silence_dialogs):
    panel.create_folder("Alpes")
    panel.select_folder(None)  # sinon « Jura » serait créé dans « Alpes »
    jura = panel.create_folder("Jura")

    assert panel.rename_selected("Alpes") is False
    assert db.get_folder(jura).name == "Jura"


def test_suppression_de_dossier_avec_son_contenu(panel, db, sample_points):
    folder_id = panel.create_folder("Alpes")
    track_id = db.create_track("Trace", folder_id=folder_id, points=sample_points)
    panel.refresh()
    panel.select_folder(folder_id)

    assert panel.delete_selected(confirm=False) is True
    assert db.get_folder(folder_id) is None
    assert db.get_track(track_id) is None
    assert item_labels(panel) == []


def test_suppression_de_trace(panel, db, sample_points):
    track_id = db.create_track("Trace", points=sample_points)
    panel.refresh()
    panel.select_track(track_id)

    assert panel.delete_selected(confirm=False) is True
    assert db.get_track(track_id) is None
    assert item_labels(panel) == []


def test_renommage_de_trace(panel, db, sample_points):
    track_id = db.create_track("Sans nom", points=sample_points)
    panel.refresh()
    panel.select_track(track_id)

    assert panel.rename_selected("Boucle du lac") is True
    assert db.get_track(track_id).name == "Boucle du lac"
    assert item_labels(panel) == ["Boucle du lac"]


# ------------------------------------------------------- glisser-déposer


def test_dossier_parent_d_un_item(panel, db, sample_points):
    folder_id = panel.create_folder("Alpes")
    track_id = db.create_track("Trace", folder_id=folder_id, points=sample_points)
    panel.refresh()

    assert folder_of(panel.find_item(KIND_TRACK, track_id)) == folder_id
    assert folder_of(panel.find_item(KIND_FOLDER, folder_id)) == folder_id
    assert folder_of(panel.tree.topLevelItem(0)) is None  # racine
    assert folder_of(None) is None


def test_deplacement_de_trace_vers_un_dossier(panel, db, sample_points):
    folder_id = panel.create_folder("Alpes")
    track_id = db.create_track("Trace", points=sample_points)
    panel.refresh()

    assert panel.move_track(track_id, folder_id) is True

    assert db.get_track(track_id).folder_id == folder_id
    assert item_labels(panel) == ["Alpes"]
    parent_item = panel.find_item(KIND_FOLDER, folder_id)
    assert item_labels(panel, parent_item) == ["Trace"]


def test_deplacement_vers_la_racine(panel, db, sample_points):
    folder_id = panel.create_folder("Alpes")
    track_id = db.create_track("Trace", folder_id=folder_id, points=sample_points)
    panel.refresh()

    assert panel.move_track(track_id, None) is True
    assert db.get_track(track_id).folder_id is None


def test_deplacement_sans_effet_si_meme_dossier(panel, db, sample_points):
    track_id = db.create_track("Trace", points=sample_points)
    panel.refresh()

    assert panel.move_track(track_id, None) is False


def deposer(panel, source_item, cible_item) -> QDropEvent:
    """Simule un vrai QDropEvent de `source_item` sur `cible_item`."""
    panel.tree.setCurrentItem(source_item)
    event = QDropEvent(
        QPointF(panel.tree.visualItemRect(cible_item).center()),
        Qt.DropAction.MoveAction,
        QMimeData(),
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    panel.tree.dropEvent(event)
    return event


def test_depot_reel_sur_un_dossier(panel, db, sample_points):
    """Simule un vrai QDropEvent, comme le fait le glisser-déposer de Qt."""
    folder_id = panel.create_folder("Alpes")
    track_id = db.create_track("Trace", points=sample_points)
    panel.refresh()

    deposer(
        panel,
        panel.find_item(KIND_TRACK, track_id),
        panel.find_item(KIND_FOLDER, folder_id),
    )

    assert db.get_track(track_id).folder_id == folder_id


def test_element_visible_a_sa_nouvelle_place_apres_depot(panel, db, sample_points):
    """Régression : la trace doit apparaître immédiatement dans le dossier."""
    folder_id = panel.create_folder("Alpes")
    track_id = db.create_track("Trace", points=sample_points)
    panel.refresh()

    deposer(
        panel,
        panel.find_item(KIND_TRACK, track_id),
        panel.find_item(KIND_FOLDER, folder_id),
    )

    item = panel.find_item(KIND_TRACK, track_id)
    assert item is not None, "la trace a disparu de l'arborescence"
    assert folder_of(item) == folder_id
    assert item_labels(panel, panel.find_item(KIND_FOLDER, folder_id)) == [
        "Trace"
    ]


def simuler_nettoyage_qt(panel, event) -> None:
    """Reproduit ce que fait Qt une fois dropEvent terminé.

    QAbstractItemView.startDrag() supprime les lignes sélectionnées lorsque
    l'action retenue est MoveAction. Comme l'arbre a déjà été reconstruit
    depuis la base, cette suppression frappe l'élément fraîchement replacé.
    """
    if event.dropAction() != Qt.DropAction.MoveAction:
        return
    for index in panel.tree.selectedIndexes():
        panel.tree.model().removeRow(index.row(), index.parent())


def test_le_depot_ne_laisse_pas_qt_supprimer_la_ligne(panel, db, sample_points):
    """Régression : c'est ce qui vidait l'affichage après un déplacement."""
    folder_id = panel.create_folder("Alpes")
    track_id = db.create_track("Trace", points=sample_points)
    panel.refresh()

    event = deposer(
        panel,
        panel.find_item(KIND_TRACK, track_id),
        panel.find_item(KIND_FOLDER, folder_id),
    )
    simuler_nettoyage_qt(panel, event)

    assert panel.find_item(KIND_TRACK, track_id) is not None, (
        "la trace a été effacée par le nettoyage de Qt après le dépôt"
    )
    assert event.isAccepted() is True
    assert event.dropAction() != Qt.DropAction.MoveAction


def test_dossier_visible_a_sa_nouvelle_place_apres_depot(panel, db):
    """Régression : même symptôme pour un dossier déplacé."""
    alpes = panel.create_folder("Alpes")
    panel.select_folder(None)
    jura = panel.create_folder("Jura")

    event = deposer(
        panel,
        panel.find_item(KIND_FOLDER, jura),
        panel.find_item(KIND_FOLDER, alpes),
    )

    assert event.dropAction() != Qt.DropAction.MoveAction
    item = panel.find_item(KIND_FOLDER, jura)
    assert item is not None, "le dossier a disparu de l'arborescence"
    assert item.parent() is panel.find_item(KIND_FOLDER, alpes)


def test_un_dossier_peut_etre_glisse(panel, db):
    folder_id = panel.create_folder("Alpes")
    item = panel.find_item(KIND_FOLDER, folder_id)

    assert bool(item.flags() & Qt.ItemFlag.ItemIsDragEnabled)


def test_une_trace_peut_etre_glissee(panel, db, sample_points):
    track_id = db.create_track("Trace", points=sample_points)
    panel.refresh()
    item = panel.find_item(KIND_TRACK, track_id)

    assert bool(item.flags() & Qt.ItemFlag.ItemIsDragEnabled)


# ------------------------------------------- glisser-déposer des dossiers


def test_deplacement_de_dossier_dans_un_autre(panel, db):
    alpes = panel.create_folder("Alpes")
    panel.select_folder(None)
    jura = panel.create_folder("Jura")

    assert panel.move_folder(jura, alpes) is True

    assert db.get_folder(jura).parent_id == alpes
    assert item_labels(panel) == ["Alpes"]
    assert item_labels(panel, panel.find_item(KIND_FOLDER, alpes)) == ["Jura"]


def test_dossier_deplace_emporte_son_contenu(panel, db, sample_points):
    alpes = panel.create_folder("Alpes")
    sous = panel.create_folder("2026")
    track_id = db.create_track("Trace", folder_id=sous, points=sample_points)
    panel.select_folder(None)
    jura = panel.create_folder("Jura")

    panel.move_folder(alpes, jura)

    assert db.get_folder(alpes).parent_id == jura
    assert db.get_folder(sous).parent_id == alpes  # inchangé
    assert db.get_track(track_id).folder_id == sous


def test_remontee_d_un_dossier_a_la_racine(panel, db):
    alpes = panel.create_folder("Alpes")
    sous = panel.create_folder("2026")

    assert panel.move_folder(sous, None) is True
    assert db.get_folder(sous).parent_id is None


def test_dossier_ne_peut_pas_aller_dans_lui_meme(panel, db, silence_dialogs):
    alpes = panel.create_folder("Alpes")

    assert panel.move_folder(alpes, alpes) is False
    assert db.get_folder(alpes).parent_id is None


def test_dossier_ne_peut_pas_aller_dans_son_sous_dossier(panel, db, silence_dialogs):
    """Sinon la branche entière disparaîtrait de l'arborescence."""
    alpes = panel.create_folder("Alpes")
    sous = panel.create_folder("2026")

    assert panel.move_folder(alpes, sous) is False
    assert db.get_folder(alpes).parent_id is None
    assert db.get_folder(sous).parent_id == alpes
    assert any("sous-dossier" in text for _titre, text in silence_dialogs)


def test_deplacement_refuse_si_le_nom_est_deja_pris(panel, db, silence_dialogs):
    alpes = panel.create_folder("Alpes")
    panel.create_folder("2026")
    panel.select_folder(None)
    jura = panel.create_folder("Jura")
    doublon = panel.create_folder("2026")  # dans Jura

    assert panel.move_folder(doublon, alpes) is False
    assert db.get_folder(doublon).parent_id == jura


def test_detection_d_ascendance_dans_l_arbre(panel, db):
    alpes = panel.create_folder("Alpes")
    sous = panel.create_folder("2026")
    panel.select_folder(None)
    jura = panel.create_folder("Jura")

    item_alpes = panel.find_item(KIND_FOLDER, alpes)
    item_sous = panel.find_item(KIND_FOLDER, sous)
    item_jura = panel.find_item(KIND_FOLDER, jura)

    assert is_self_or_descendant(item_alpes, item_alpes) is True
    assert is_self_or_descendant(item_sous, item_alpes) is True
    assert is_self_or_descendant(item_jura, item_alpes) is False
    assert is_self_or_descendant(None, item_alpes) is False


def test_depot_reel_d_un_dossier(panel, db):
    """Simule un vrai QDropEvent sur un dossier cible."""
    alpes = panel.create_folder("Alpes")
    panel.select_folder(None)
    jura = panel.create_folder("Jura")

    deposer(
        panel,
        panel.find_item(KIND_FOLDER, jura),
        panel.find_item(KIND_FOLDER, alpes),
    )

    assert db.get_folder(jura).parent_id == alpes


def test_depot_d_un_dossier_sur_sa_descendance_ignore(panel, db):
    """Le dépôt est refusé au niveau de la vue, sans même toucher la base."""
    alpes = panel.create_folder("Alpes")
    sous = panel.create_folder("2026")
    panel.find_item(KIND_FOLDER, alpes).setExpanded(True)

    event = deposer(
        panel,
        panel.find_item(KIND_FOLDER, alpes),
        panel.find_item(KIND_FOLDER, sous),
    )

    assert event.isAccepted() is False
    assert db.get_folder(alpes).parent_id is None


# ------------------------------------------------ sauvegarde du brouillon


def test_sauvegarde_du_brouillon_en_base(window, db):
    window.set_edit_mode(True)
    window.add_draft_point(48.930, 1.440)
    window.add_draft_point(48.931, 1.442)
    window.add_draft_point(48.932, 1.441)

    track_id = window.save_draft("Boucle de Bueil")

    assert track_id is not None
    track = db.get_track(track_id, with_points=True)
    assert track.name == "Boucle de Bueil"
    assert [p.as_tuple() for p in track.points] == [
        (48.930, 1.440),
        (48.931, 1.442),
        (48.932, 1.441),
    ]


def test_sauvegarde_vide_le_brouillon(window):
    window.add_draft_point(48.930, 1.440)
    window.add_draft_point(48.931, 1.442)

    window.save_draft("Trace")

    assert window.draft.is_empty
    assert window.action_save.isEnabled() is False


def test_trace_enregistree_apparait_et_est_selectionnee(window):
    window.add_draft_point(48.930, 1.440)
    window.add_draft_point(48.931, 1.442)

    track_id = window.save_draft("Ma trace")

    assert item_labels(window.tree_panel) == ["Ma trace"]
    assert window.tree_panel.current_selection() == (KIND_TRACK, track_id)


def test_sauvegarde_dans_le_dossier_selectionne(window, db):
    folder_id = window.tree_panel.create_folder("Alpes")
    window.add_draft_point(48.930, 1.440)
    window.add_draft_point(48.931, 1.442)

    track_id = window.save_draft("Trace")

    assert db.get_track(track_id).folder_id == folder_id


def test_sauvegarde_refusee_sous_deux_points(window, db, silence_dialogs):
    window.add_draft_point(48.930, 1.440)

    assert window.save_draft("Trop courte") is None
    assert db.list_tracks(None) == []
    assert any("deux points" in text for _titre, text in silence_dialogs)


def test_action_enregistrer_activee_a_partir_de_deux_points(window):
    assert window.action_save.isEnabled() is False

    window.add_draft_point(48.930, 1.440)
    assert window.action_save.isEnabled() is False

    window.add_draft_point(48.931, 1.442)
    assert window.action_save.isEnabled() is True


def test_deux_traces_peuvent_porter_le_meme_nom(window, db):
    """Contrairement aux dossiers, les noms de traces ne sont pas uniques."""
    for _ in range(2):
        window.add_draft_point(48.930, 1.440)
        window.add_draft_point(48.931, 1.442)
        window.save_draft("Même nom")

    assert len(db.list_tracks(None)) == 2


# ------------------------------------------------------------- export GPX


def test_export_d_une_trace_enregistree(window, db, tmp_path, sample_points):
    track_id = db.create_track("Rallye V1", points=sample_points)
    cible = tmp_path / "export.gpx"

    resultat = window.export_track(track_id, str(cible))

    assert resultat == str(cible)
    assert cible.exists()
    relu = ET.parse(cible).getroot()
    assert relu.find("gpx:trk/gpx:name", NS).text == "Rallye V1"
    assert len(relu.findall("gpx:trk/gpx:trkseg/gpx:trkpt", NS)) == 4


def test_export_declenche_par_l_arborescence(window, db, sample_points):
    """Le clic droit « Exporter en GPX » passe par le signal du panneau."""
    track_id = db.create_track("Trace", points=sample_points)
    window.tree_panel.refresh()

    recu = []
    # On remplace le destinataire réel, sinon une vraie boîte « Enregistrer
    # sous » s'ouvrirait et bloquerait le test.
    window.tree_panel.export_requested.disconnect(window.export_track)
    window.tree_panel.export_requested.connect(recu.append)

    window.tree_panel.select_track(track_id)
    window.tree_panel._request_export()

    assert recu == [track_id]


def test_export_d_une_trace_vide_refuse(window, db, tmp_path, silence_dialogs):
    track_id = db.create_track("Vide", points=[])

    assert window.export_track(track_id, str(tmp_path / "x.gpx")) is None
    assert not (tmp_path / "x.gpx").exists()


def test_export_boucle_complete(window, db, tmp_path):
    """Saisie sur carte, enregistrement, puis export : le tout doit concorder."""
    window.set_edit_mode(True)
    coords = [(48.930, 1.440), (48.931, 1.442), (48.932, 1.441)]
    for lat, lon in coords:
        window.add_draft_point(lat, lon)
    track_id = window.save_draft("Aller-retour")

    cible = tmp_path / "aller-retour.gpx"
    window.export_track(track_id, str(cible))

    relu = ET.parse(cible).getroot()
    exportes = [
        (round(float(p.get("lat")), 3), round(float(p.get("lon")), 3))
        for p in relu.findall("gpx:trk/gpx:trkseg/gpx:trkpt", NS)
    ]
    assert exportes == coords
