"""Tests de la couche de données : dossiers, traces, points."""

from __future__ import annotations

import pytest

from carto.database import (
    SCHEMA_VERSION,
    Database,
    DuplicateNameError,
    NotFoundError,
)
from carto.models import DEFAULT_TRACK_OPACITY, Point

# --------------------------------------------------------------------- schéma


def test_schema_cree_et_versionne(db):
    tables = {
        row["name"]
        for row in db.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert {"folders", "tracks", "points", "meta"} <= tables
    assert db.schema_version == SCHEMA_VERSION


def test_base_persistante_entre_deux_ouvertures(db, sample_points):
    track_id = db.create_track("Rallye", points=sample_points)
    path = db.path
    db.close()

    with Database(path) as reopened:
        track = reopened.get_track(track_id, with_points=True)
        assert track is not None
        assert track.name == "Rallye"
        assert len(track.points) == len(sample_points)


# ------------------------------------------------------------------ migration

SCHEMA_V1 = """
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE folders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    parent_id INTEGER REFERENCES folders(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE UNIQUE INDEX idx_folders_unique ON folders(IFNULL(parent_id, -1), name);
CREATE TABLE tracks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    folder_id INTEGER REFERENCES folders(id) ON DELETE CASCADE,
    color TEXT NOT NULL DEFAULT '#1f5fbf',
    description TEXT NOT NULL DEFAULT '',
    is_loop INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE points (
    track_id INTEGER NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
    seq INTEGER NOT NULL, lat REAL NOT NULL, lon REAL NOT NULL,
    ele REAL, time TEXT, PRIMARY KEY (track_id, seq)
) WITHOUT ROWID;
INSERT INTO meta(key, value) VALUES ('schema_version', '1');
"""


def creer_base_v1(path):
    """Reconstitue une base telle que la créait la version précédente."""
    import sqlite3

    conn = sqlite3.connect(str(path))
    conn.executescript(SCHEMA_V1)
    conn.execute("INSERT INTO folders(id, name) VALUES (1, 'Rallye 2016')")
    conn.execute(
        "INSERT INTO tracks(id, name, folder_id, color) "
        "VALUES (1, 'Ancienne trace', 1, '#e6194b')"
    )
    conn.executemany(
        "INSERT INTO points(track_id, seq, lat, lon) VALUES (1, ?, ?, ?)",
        [(0, 48.93, 1.44), (1, 48.94, 1.45)],
    )
    conn.commit()
    conn.close()


def test_migration_depuis_le_schema_precedent(tmp_path):
    """Une base existante doit être mise à niveau sans perdre de données."""
    chemin = tmp_path / "ancienne.db"
    creer_base_v1(chemin)

    with Database(chemin) as db:
        assert db.schema_version == SCHEMA_VERSION

        folder = db.get_folder(1)
        assert folder is not None and folder.name == "Rallye 2016"

        track = db.get_track(1, with_points=True)
        assert track.name == "Ancienne trace"
        assert track.color == "#e6194b"  # la couleur choisie est conservée
        assert len(track.points) == 2
        # La colonne apparue depuis prend sa valeur par défaut.
        assert track.opacity == pytest.approx(DEFAULT_TRACK_OPACITY)


def test_migration_idempotente(tmp_path):
    chemin = tmp_path / "ancienne.db"
    creer_base_v1(chemin)

    for _ in range(3):
        with Database(chemin) as db:
            assert db.schema_version == SCHEMA_VERSION
            assert db.get_track(1).name == "Ancienne trace"

    with Database(chemin) as db:
        colonnes = [r["name"] for r in db.conn.execute("PRAGMA table_info(tracks)")]
        assert colonnes.count("opacity") == 1


# --------------------------------------------------------- couleur et opacité


def test_style_par_defaut(db, sample_points):
    track_id = db.create_track("Trace", points=sample_points)
    track = db.get_track(track_id)

    assert track.color == "#1f5fbf"
    assert track.opacity == pytest.approx(DEFAULT_TRACK_OPACITY)


def test_changement_de_couleur(db, sample_points):
    track_id = db.create_track("Trace", points=sample_points)

    db.set_track_style(track_id, color="#ff8800")

    assert db.get_track(track_id).color == "#ff8800"
    assert db.get_track(track_id).opacity == pytest.approx(DEFAULT_TRACK_OPACITY)


def test_changement_de_transparence(db, sample_points):
    track_id = db.create_track("Trace", points=sample_points)

    db.set_track_style(track_id, opacity=0.4)

    assert db.get_track(track_id).opacity == pytest.approx(0.4)
    assert db.get_track(track_id).color == "#1f5fbf"  # inchangée


def test_transparence_bornee(db, sample_points):
    """Une trace totalement transparente serait introuvable sur la carte."""
    track_id = db.create_track("Trace", points=sample_points)

    db.set_track_style(track_id, opacity=0.0)
    assert db.get_track(track_id).opacity == pytest.approx(0.05)

    db.set_track_style(track_id, opacity=5.0)
    assert db.get_track(track_id).opacity == pytest.approx(1.0)


def test_style_d_une_trace_inexistante(db):
    with pytest.raises(NotFoundError):
        db.set_track_style(999, color="#000000")


def test_le_style_suit_la_duplication(db, sample_points):
    track_id = db.create_track("Trace", points=sample_points)
    db.set_track_style(track_id, color="#ff8800", opacity=0.35)

    copie = db.duplicate_track(track_id)

    assert db.get_track(copie).color == "#ff8800"
    assert db.get_track(copie).opacity == pytest.approx(0.35)


# ------------------------------------------------------------------- dossiers


def test_creation_dossier_et_sous_dossier(db):
    parent = db.create_folder("Randonnées")
    child = db.create_folder("2026", parent_id=parent)

    assert [f.name for f in db.list_folders()] == ["Randonnées"]
    assert [f.name for f in db.list_folders(parent)] == ["2026"]
    assert db.get_folder(child).parent_id == parent


def test_dossiers_uniques_a_la_racine(db):
    db.create_folder("Vosges")
    with pytest.raises(DuplicateNameError):
        db.create_folder("Vosges")
    assert len(db.list_folders()) == 1


def test_dossiers_uniques_dans_un_meme_parent(db):
    parent = db.create_folder("Alpes")
    db.create_folder("Été", parent_id=parent)
    with pytest.raises(DuplicateNameError):
        db.create_folder("Été", parent_id=parent)


def test_meme_nom_autorise_dans_deux_parents_differents(db):
    a = db.create_folder("Alpes")
    b = db.create_folder("Jura")
    db.create_folder("2026", parent_id=a)
    db.create_folder("2026", parent_id=b)  # ne doit pas lever

    assert len(db.list_folders(a)) == 1
    assert len(db.list_folders(b)) == 1


def test_renommage_refuse_un_doublon(db):
    db.create_folder("Alpes")
    jura = db.create_folder("Jura")
    with pytest.raises(DuplicateNameError):
        db.rename_folder(jura, "Alpes")
    assert db.get_folder(jura).name == "Jura"


def test_nom_de_dossier_vide_refuse(db):
    with pytest.raises(ValueError):
        db.create_folder("   ")


def test_parent_inexistant_refuse(db):
    with pytest.raises(NotFoundError):
        db.create_folder("Orphelin", parent_id=999)


def test_suppression_dossier_en_cascade(db, sample_points):
    parent = db.create_folder("Alpes")
    child = db.create_folder("2026", parent_id=parent)
    track_id = db.create_track("Trace", folder_id=child, points=sample_points)

    db.delete_folder(parent)

    assert db.get_folder(child) is None
    assert db.get_track(track_id) is None
    assert db.count_points(track_id) == 0


# --------------------------------------------------------------------- traces


def test_creation_trace_avec_points(db, sample_points):
    folder = db.create_folder("Rallyes")
    track_id = db.create_track("Rallye V1", folder_id=folder, points=sample_points)

    track = db.get_track(track_id, with_points=True)
    assert track.name == "Rallye V1"
    assert track.folder_id == folder
    assert track.point_count == 4
    assert track.points[0].lat == pytest.approx(48.9300)
    assert track.points[-1].lon == pytest.approx(1.4390)


def test_ordre_des_points_conserve(db, sample_points):
    track_id = db.create_track("Ordre", points=sample_points)
    stored = db.get_points(track_id)
    assert [p.as_tuple() for p in stored] == [p.as_tuple() for p in sample_points]


def test_ajout_de_points_a_la_fin(db, sample_points):
    """Reprise de trace : les nouveaux points s'ajoutent après les anciens."""
    track_id = db.create_track("Reprise", points=sample_points)
    extra = [Point(48.9340, 1.4370), Point(48.9350, 1.4360)]

    db.append_points(track_id, extra)

    points = db.get_points(track_id)
    assert len(points) == 6
    assert points[4].as_tuple() == extra[0].as_tuple()
    assert points[5].as_tuple() == extra[1].as_tuple()


def test_remplacement_des_points(db, sample_points):
    track_id = db.create_track("Edition", points=sample_points)
    db.replace_points(track_id, sample_points[:2])
    assert db.count_points(track_id) == 2


def test_append_sur_trace_inexistante(db):
    with pytest.raises(NotFoundError):
        db.append_points(999, [Point(1.0, 2.0)])


def test_liste_des_traces_par_dossier(db, sample_points):
    folder = db.create_folder("Alpes")
    db.create_track("Dans le dossier", folder_id=folder, points=sample_points)
    db.create_track("À la racine", points=sample_points)

    assert [t.name for t in db.list_tracks(folder)] == ["Dans le dossier"]
    assert [t.name for t in db.list_tracks(None)] == ["À la racine"]


def test_deplacement_de_trace(db, sample_points):
    a = db.create_folder("Alpes")
    b = db.create_folder("Jura")
    track_id = db.create_track("Trace", folder_id=a, points=sample_points)

    db.move_track(track_id, b)

    assert db.list_tracks(a) == []
    assert [t.id for t in db.list_tracks(b)] == [track_id]


def test_suppression_trace_supprime_ses_points(db, sample_points):
    track_id = db.create_track("Trace", points=sample_points)
    db.delete_track(track_id)
    assert db.get_track(track_id) is None
    assert db.count_points(track_id) == 0


# --------------------------------------------------------- fermeture en boucle


def test_fermeture_de_trace_cree_la_boucle(db, sample_points):
    track_id = db.create_track("Boucle", points=sample_points)

    assert db.close_track(track_id) is True

    points = db.get_points(track_id)
    assert len(points) == len(sample_points) + 1
    assert points[0].as_tuple() == points[-1].as_tuple()
    assert db.get_track(track_id).is_loop is True


def test_fermeture_idempotente(db, sample_points):
    """Fermer une trace déjà fermée n'ajoute pas de point en double."""
    track_id = db.create_track("Boucle", points=sample_points)
    db.close_track(track_id)
    n_after_first = db.count_points(track_id)

    assert db.close_track(track_id) is False
    assert db.count_points(track_id) == n_after_first


def test_fermeture_refusee_si_moins_de_trois_points(db):
    track_id = db.create_track("Trop court", points=[Point(48.0, 1.0), Point(48.1, 1.1)])
    assert db.close_track(track_id) is False
    assert db.get_track(track_id).is_loop is False
    assert db.count_points(track_id) == 2
