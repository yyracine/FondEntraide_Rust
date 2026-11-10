"""
db.py — Accès à la base et règles communes à tous les écrans de saisie.
"""
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "familles.db"
SCHEMA = BASE_DIR / "schema.sql"


class ErreurSaisie(Exception):
    """Erreur métier destinée à être affichée à l'utilisateur."""


def connecter(db_path=None):
    con = sqlite3.connect(db_path or DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def connecter_lecture_seule(db_path):
    """Ouvre une base sans aucun droit d'écriture.

    Utilisé par l'aperçu du tableau de bord : on peut consulter et
    exporter la base de référence sans risque de la modifier (SQLite refuse alors
    toute écriture, y compris par accident).
    """
    chemin = Path(db_path).resolve().as_uri() + "?mode=ro"
    con = sqlite3.connect(chemin, uri=True)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def initialiser(db_path=None):
    """Crée les tables et les vues si nécessaire. Retourne la connexion."""
    chemin = db_path or DB_PATH
    con = connecter(chemin)
    con.executescript(SCHEMA.read_text(encoding="utf-8"))
    con.commit()
    return con


# ---------------------------------------------------------------------
#  Niveaux de la hiérarchie : table, clé du parent, libellé affiché
# ---------------------------------------------------------------------
NIVEAUX = {
    "clan": {
        "table": "clans",
        "parent_table": None,
        "parent_col": None,
        "singulier": "Clan",
        "pluriel": "Clans",
        "article": "Ce clan",
    },
    "grande_famille": {
        "table": "grandes_familles",
        "parent_table": "clans",
        "parent_col": "clan_id",
        "singulier": "Grande famille",
        "pluriel": "Grandes familles",
        "article": "Cette grande famille",
    },
    "lignee": {
        "table": "lignees",
        "parent_table": "grandes_familles",
        "parent_col": "grande_famille_id",
        "singulier": "Lignée",
        "pluriel": "Lignées",
        "article": "Cette lignée",
    },
    "famille": {
        "table": "familles",
        "parent_table": "lignees",
        "parent_col": "lignee_id",
        "singulier": "Famille",
        "pluriel": "Familles",
        "article": "Cette famille",
    },
    "membre": {
        "table": "membres",
        "parent_table": "familles",
        "parent_col": "famille_id",
        "singulier": "Membre",
        "pluriel": "Membres",
        "article": "Ce membre",
    },
}


def nettoyer_nom(valeur):
    """Normalise un libellé saisi : espaces multiples et bords retirés."""
    if valeur is None:
        return ""
    return " ".join(str(valeur).split())


def exiger_nom(valeur, libelle="Le nom"):
    nom = nettoyer_nom(valeur)
    if not nom:
        raise ErreurSaisie(f"{libelle} est obligatoire.")
    if len(nom) > 120:
        raise ErreurSaisie(f"{libelle} ne doit pas dépasser 120 caractères.")
    return nom


def parents_disponibles(con, niveau):
    """
    Retourne la liste (id, libellé) des nœuds parents possibles
    pour un niveau donné. Vide pour le niveau « clan ».
    """
    cfg = NIVEAUX[niveau]
    if cfg["parent_table"] is None:
        return []
    return [
        (r["id"], r["nom"])
        for r in con.execute(
            f"SELECT id, nom FROM {cfg['parent_table']} ORDER BY nom COLLATE NOCASE"
        )
    ]


def nom_parent(con, niveau, parent_id):
    """Libellé du parent d'un nœud, pour l'affichage hiérarchique."""
    cfg = NIVEAUX[niveau]
    if cfg["parent_table"] is None or parent_id is None:
        return ""
    row = con.execute(
        f"SELECT nom FROM {cfg['parent_table']} WHERE id = ?", (parent_id,)
    ).fetchone()
    return row["nom"] if row else ""


def lister(con, niveau, parent_id=None):
    """
    Retourne (id, nom, nb_enfants) pour chaque nœud du niveau,
    filtré sur son parent. nb_enfants = descendants directs.
    """
    cfg = NIVEAUX[niveau]
    table = cfg["table"]
    enfant = None
    for n, c in NIVEAUX.items():
        if c["parent_col"] and c["parent_table"] == table:
            enfant = c
            break

    sql = f"SELECT id, nom FROM {table}"
    params = []
    if cfg["parent_col"]:
        sql += f" WHERE {cfg['parent_col']} = ?"
        params.append(parent_id)
    sql += " ORDER BY nom COLLATE NOCASE"
    lignes = con.execute(sql, params).fetchall()

    if enfant is None:
        return [(r["id"], r["nom"], None) for r in lignes]

    compteur = {
        r["p"]: r["n"]
        for r in con.execute(
            f"SELECT {enfant['parent_col']} AS p, COUNT(*) AS n "
            f"FROM {enfant['table']} GROUP BY {enfant['parent_col']}"
        )
    }
    return [(r["id"], r["nom"], compteur.get(r["id"], 0)) for r in lignes]


def ajouter(con, niveau, nom, parent_id=None, **autres):
    """Insère un nœud après validation. Lève ErreurSaisie en cas de conflit.

    `parent_id` désigne TOUJOURS le nœud parent dans la hiérarchie
    (clan → grande famille → lignée → famille → membre).
    Pour un membre, le lien généalogique s'appelle `lien_parent_id` afin
    d'éviter toute confusion.
    """
    if "lien_parent_id" in autres:
        autres["parent_id"] = autres.pop("lien_parent_id")
    cfg = NIVEAUX[niveau]
    nom = exiger_nom(nom, f"Le nom du {cfg['singulier'].lower()}")
    cols, vals = ["nom"], [nom]
    if cfg["parent_col"]:
        if parent_id is None:
            raise ErreurSaisie(
                f"Choisissez d'abord le parent (un {cfg['singulier']} "
                f"appartient obligatoirement à un nœud supérieur)."
            )
        cols.append(cfg["parent_col"])
        vals.append(parent_id)
    for k, v in autres.items():
        cols.append(k)
        vals.append(v)

    placeholders = ", ".join("?" * len(cols))
    try:
        cur = con.execute(
            f"INSERT INTO {cfg['table']} ({', '.join(cols)}) VALUES ({placeholders})",
            vals,
        )
        con.commit()
    except sqlite3.IntegrityError as e:
        con.rollback()
        if "UNIQUE" in str(e).upper():
            raise ErreurSaisie(
                f"{cfg['article']} « {nom} » existe déjà sous ce même parent."
            ) from e
        raise ErreurSaisie(str(e)) from e
    return cur.lastrowid


def modifier(con, niveau, id_, nom, **autres):
    """Modifie un nœud. Voir `ajouter` pour `lien_parent_id`."""
    if "lien_parent_id" in autres:
        autres["parent_id"] = autres.pop("lien_parent_id")
    cfg = NIVEAUX[niveau]
    nom = exiger_nom(nom, f"Le nom du {cfg['singulier'].lower()}")
    sets, vals = ["nom = ?"], [nom]
    for k, v in autres.items():
        sets.append(f"{k} = ?")
        vals.append(v)
    vals.append(id_)
    try:
        con.execute(
            f"UPDATE {cfg['table']} SET {', '.join(sets)} WHERE id = ?", vals
        )
        con.commit()
    except sqlite3.IntegrityError as e:
        con.rollback()
        if "UNIQUE" in str(e).upper():
            raise ErreurSaisie(
                f"{cfg['article']} « {nom} » existe déjà sous ce même parent."
            ) from e
        raise ErreurSaisie(str(e)) from e


def _ordre_descendant(con, ids):
    """Trie des membres pour qu'aucun parent ne soit supprimé avant
    ses enfants (contrainte parent_id ON DELETE RESTRICT)."""
    profondeur = {}

    def calculer(mid, vus=None):
        if mid in profondeur:
            return profondeur[mid]
        vus = vus or set()
        if mid in vus:
            return 0
        row = con.execute("SELECT parent_id FROM membres WHERE id = ?", (mid,)).fetchone()
        if not row or row[0] is None:
            profondeur[mid] = 0
        else:
            profondeur[mid] = 1 + calculer(row[0], vus | {mid})
        return profondeur[mid]

    for i in ids:
        calculer(i)
    return sorted(ids, key=lambda i: profondeur.get(i, 0), reverse=True)


def supprimer(con, niveau, id_, force=False):
    """
    Supprime un nœud. Refusé s'il a des descendants, sauf si force=True
    (suppression en chaîne de tout le sous-arbre).
    """
    cfg = NIVEAUX[niveau]
    table = cfg["table"]

    # niveau enfant direct
    enfant = None
    for n, c in NIVEAUX.items():
        if c["parent_col"] and c["parent_table"] == table:
            enfant = c
            break

    if enfant is not None:
        nb = con.execute(
            f"SELECT COUNT(*) FROM {enfant['table']} WHERE {enfant['parent_col']} = ?",
            (id_,),
        ).fetchone()[0]
        if nb and not force:
            raise ErreurSaisie(
                f"{cfg['article']} contient {nb} "
                f"{(enfant['singulier'] if nb == 1 else enfant['pluriel']).lower()}. "
                f"Supprimez-les d'abord, ou utilisez la suppression en chaîne."
            )
        if nb and force:
            ids = [r[0] for r in con.execute(
                f"SELECT id FROM {enfant['table']} WHERE {enfant['parent_col']} = ?",
                (id_,),
            ).fetchall()]
            if n == "membre":
                # les membres sont liés entre eux par parent_id :
                # on supprime du plus profond au plus haut
                ids = _ordre_descendant(con, ids)
            for child_id in ids:
                supprimer(con, n, child_id, force=True)

    try:
        con.execute(f"DELETE FROM {table} WHERE id = ?", (id_,))
        con.commit()
    except sqlite3.IntegrityError as e:
        con.rollback()
        raise ErreurSaisie(
            "Suppression impossible : cet élément est encore référencé "
            f"({e})."
        ) from e
