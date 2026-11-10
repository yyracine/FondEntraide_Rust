#!/usr/bin/env python3
"""
migrer_v2.py — migration ponctuelle de la base v1 (schema.sql) vers la base v2
(schema_v2.sql), conforme aux décisions D1–D10 de PLAN_MIGRATION_RUST.md.

Principes
---------
1. La source est ouverte en LECTURE SEULE et n'est jamais modifiée ; son
   empreinte SHA-256 est vérifiée après coup.
2. La cible est écrite dans un fichier temporaire, vérifiée, puis renommée :
   en cas d'écart sur un seul golden, rien n'est publié.
3. Les montants ne sont jamais recalculés : ils sont recopiés à l'identique
   (les deux affectations de 2 000 F du paiement 105 restent à 2 000 F).
4. Toute la migration est une seule transaction.

Usage
-----
    python migrer_v2.py
    python migrer_v2.py --source cotisations.db --sortie cotisations_v2.db
    python migrer_v2.py --garder-temporaire     # laisse le .tmp pour enquête

Codes de sortie : 0 = succès, 2 = écart détecté / migration refusée.
"""
import argparse
import datetime
import hashlib
import json
import os
import sqlite3
import sys
from pathlib import Path

BASE = Path(__file__).parent
SOURCE_DEFAUT = BASE / "cotisations.db"
SORTIE_DEFAUT = BASE / "cotisations_v2.db"
SCHEMA_V2 = BASE / "schema_v2.sql"

# Goldens de référence — cf. PLAN_MIGRATION_RUST.md § 5.1
ATTENDU = {
    "clans": 7,
    "grandes_familles": 46,
    "lignees": 46,
    "familles": 391,
    "membres": 599,
    "paiements": 227,
    "affectations": 1805,
}
TOTAL_ATTENDU = 1_807_000
PAR_ANNEES_ATTENDU = {2024: 1_453_000, 2025: 338_000, 2026: 16_000}


# ---------------------------------------------------------------------
#  Utilitaires
# ---------------------------------------------------------------------
def empreinte(chemin):
    h = hashlib.sha256()
    with open(chemin, "rb") as f:
        for bloc in iter(lambda: f.read(65536), b""):
            h.update(bloc)
    return h.hexdigest()


def colonnes(con, table):
    return [r[1] for r in con.execute("PRAGMA table_info(%s)" % table)]


def ouvrir_lecture_seule(chemin):
    con = sqlite3.connect("file:%s?mode=ro" % Path(chemin).as_posix(), uri=True)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def normaliser_date(valeur):
    """ISO reste ISO ; JJ/MM/AAAA et JJ-MM-AAAA sont convertis ; sinon None."""
    if valeur is None:
        return None
    texte = str(valeur).strip()
    if not texte:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.datetime.strptime(texte, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def mois_de_periode(debut, fin):
    """Tous les (année, mois) touchés par [debut, fin], bornes incluses."""
    a, m = debut.year, debut.month
    courant = None
    while (a, m) <= (fin.year, fin.month):
        if (a, m) != courant:
            yield a, m
            courant = (a, m)
        m += 1
        if m == 13:
            a, m = a + 1, 1


def copier_table(src, dst, table, renommer=None):
    """Copie les colonnes communes à la source et à la cible."""
    renommer = renommer or {}
    dispo = set(colonnes(dst, table))
    paires = []
    for c in colonnes(src, table):
        cible = renommer.get(c, c)
        if cible in dispo:
            paires.append((c, cible))
    if not paires:
        return 0
    sql = "INSERT INTO %s (%s) VALUES (%s)" % (
        table,
        ", ".join(d for _, d in paires),
        ", ".join("?" * len(paires)),
    )
    n = 0
    for ligne in src.execute(
            "SELECT %s FROM %s" % (", ".join(s for s, _ in paires), table)):
        dst.execute(sql, tuple(ligne))
        n += 1
    return n


# ---------------------------------------------------------------------
#  État de la source (avant migration)
# ---------------------------------------------------------------------
def mesurer_source(con):
    etat = {}
    for table in ATTENDU:
        etat[table] = con.execute(
            "SELECT COUNT(*) FROM %s" % table).fetchone()[0]
    etat["total"] = con.execute(
        "SELECT IFNULL(SUM(montant), 0) FROM affectations").fetchone()[0]
    etat["total_paiements"] = con.execute(
        "SELECT IFNULL(SUM(montant_total), 0) FROM paiements").fetchone()[0]
    etat["par_annee"] = {
        r["annee"]: r["total"]
        for r in con.execute(
            "SELECT annee, SUM(montant) AS total FROM affectations "
            "GROUP BY annee")
    }
    etat["fractionnaires"] = (
        con.execute("SELECT COUNT(*) FROM affectations "
                    "WHERE montant <> CAST(montant AS INTEGER)").fetchone()[0]
        + con.execute("SELECT COUNT(*) FROM paiements "
                      "WHERE montant_total <> CAST(montant_total AS INTEGER)"
                      ).fetchone()[0]
    )
    etat["multi_annees"] = con.execute(
        "SELECT COUNT(*) FROM (SELECT paiement_id FROM affectations "
        "GROUP BY paiement_id HAVING COUNT(DISTINCT annee) > 1)").fetchone()[0]

    # ce que la cible DOIT contenir, calculé depuis la source elle-même
    etat["campagnes"] = con.execute(
        "SELECT COUNT(*) FROM campagnes").fetchone()[0]
    etat["mois_attendus"] = 0
    for c in con.execute("SELECT annee, date_debut, date_fin FROM campagnes"):
        debut = normaliser_date(c["date_debut"])
        fin = normaliser_date(c["date_fin"])
        if not debut or not fin:
            debut = "%04d-01-01" % c["annee"]
            fin = "%04d-12-31" % c["annee"]
        etat["mois_attendus"] += sum(
            1 for _ in mois_de_periode(datetime.date.fromisoformat(debut),
                                       datetime.date.fromisoformat(fin)))
    return etat


def depassements_source(con):
    """{(membre_id, annee, mois)} des mois réglés au-delà de leur dû."""
    mensuel = {
        r["annee"]: r["montant_mensuel"]
        for r in con.execute("SELECT annee, montant_mensuel FROM campagnes")
    }
    totaux = con.execute("""
        SELECT p.membre_id AS membre_id, a.annee AS annee, a.mois AS mois,
               SUM(a.montant) AS total
          FROM affectations a
          JOIN paiements p ON p.id = a.paiement_id
         GROUP BY p.membre_id, a.annee, a.mois
    """).fetchall()
    return {
        (r["membre_id"], r["annee"], r["mois"])
        for r in totaux
        if r["total"] > mensuel.get(r["annee"], 1000)
    }


# ---------------------------------------------------------------------
#  Migration
# ---------------------------------------------------------------------
def migrer(src, dst, sha_source):
    rapport = {}

    # --- 1. hiérarchie : identifiants conservés -----------------------
    rapport["clans"] = copier_table(src, dst, "clans",
                                    {"created_at": "cree_le"})
    rapport["grandes_familles"] = copier_table(
        src, dst, "grandes_familles", {"created_at": "cree_le"})
    rapport["lignees"] = copier_table(
        src, dst, "lignees", {"created_at": "cree_le"})
    rapport["familles"] = copier_table(
        src, dst, "familles", {"created_at": "cree_le"})
    rapport["membres"] = copier_table(
        src, dst, "membres", {"created_at": "cree_le"})

    # --- 2. exercices (ex-campagnes) ---------------------------------
    # Un exercice est défini par sa PÉRIODE. Si la v1 porte des bornes,
    # on les reprend ; sinon on considère l'année civile.
    rapport["exercices"] = 0
    rapport["echeances"] = 0
    echeance_par_mois = {}
    for c in src.execute("SELECT * FROM campagnes ORDER BY annee"):
        debut = normaliser_date(c["date_debut"])
        fin = normaliser_date(c["date_fin"])
        if not debut or not fin:
            debut = "%04d-01-01" % c["annee"]
            fin = "%04d-12-31" % c["annee"]
        libelle = c["libelle"] or ("Exercice %s" % c["annee"])
        dst.execute("""
            INSERT INTO exercices (id, libelle, date_debut, date_fin,
                                   montant_mensuel, devise, statut, cree_le)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (c["id"], libelle, debut, fin, int(c["montant_mensuel"]),
              c["devise"] or "XOF", c["statut"] or "ouverte",
              c["created_at"] if "created_at" in c.keys() else None))
        rapport["exercices"] += 1

        d = datetime.date.fromisoformat(debut)
        f = datetime.date.fromisoformat(fin)
        for annee, mois in mois_de_periode(d, f):
            premier = datetime.date(annee, mois, 1)
            date_echeance = max(premier, d)      # jamais avant le début
            dst.execute("""
                INSERT INTO echeances (exercice_id, annee, mois,
                                       date_echeance, montant_du)
                VALUES (?, ?, ?, ?, ?)
            """, (c["id"], annee, mois, date_echeance.isoformat(),
                  int(c["montant_mensuel"])))
            echeance_par_mois[(annee, mois)] = dst.execute(
                "SELECT last_insert_rowid()").fetchone()[0]
            rapport["echeances"] += 1

    # --- 3. paiements ------------------------------------------------
    numeros = {}
    try:
        for r in src.execute("SELECT cle, valeur FROM parametres "
                             "WHERE cle LIKE 'recu_paiement_%'"):
            try:
                numeros[int(r["cle"].rsplit("_", 1)[1])] = r["valeur"]
            except (ValueError, IndexError):
                continue
    except sqlite3.Error:
        pass       # base sans table parametres : rien à reprendre

    rapport["paiements"] = 0
    dates_reparees = []
    for p in src.execute("SELECT * FROM paiements ORDER BY id"):
        date_iso = normaliser_date(p["date_paiement"])
        if date_iso is None:
            raise SystemExit(
                "Date de paiement illisible sur le paiement %s : %r"
                % (p["id"], p["date_paiement"]))
        if date_iso != str(p["date_paiement"]):
            dates_reparees.append((p["id"], p["date_paiement"], date_iso))
        dst.execute("""
            INSERT INTO paiements (id, membre_id, date_paiement,
                                   montant_total, mode, reference,
                                   observation, saisi_par, numero_recu, cree_le)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (p["id"], p["membre_id"], date_iso, int(p["montant_total"]),
              p["mode"] or "especes", p["reference"], p["observation"],
              p["saisi_par"], numeros.get(p["id"]),
              p["created_at"] if "created_at" in p.keys() else None))
        rapport["paiements"] += 1

    # --- 4. affectations : (annee, mois) -> echeance_id --------------
    rapport["affectations"] = 0
    orphelines = []
    for a in src.execute("SELECT * FROM affectations ORDER BY id"):
        eid = echeance_par_mois.get((a["annee"], a["mois"]))
        if eid is None:
            orphelines.append((a["id"], a["annee"], a["mois"]))
            continue
        dst.execute("""
            INSERT INTO affectations (id, paiement_id, echeance_id, montant)
            VALUES (?, ?, ?, ?)
        """, (a["id"], a["paiement_id"], eid, int(a["montant"])))
        rapport["affectations"] += 1
    if orphelines:
        raise SystemExit(
            "Affectations sans échéance correspondante : %r" % orphelines[:10])

    # --- 5. compteurs de reçus ---------------------------------------
    compteurs = {}
    try:
        brut = src.execute("SELECT valeur FROM parametres "
                           "WHERE cle = 'recu_numeros'").fetchone()
        if brut:
            compteurs = json.loads(brut["valeur"])
    except (sqlite3.Error, ValueError, TypeError):
        compteurs = {}
    for annee, dernier in compteurs.items():
        try:
            dst.execute("INSERT OR REPLACE INTO sequences (nom, annee, dernier) "
                        "VALUES ('recu', ?, ?)", (int(annee), int(dernier)))
        except (TypeError, ValueError):
            continue
    # sécurité : le compteur ne peut pas être inférieur à un numéro émis
    for numero in numeros.values():
        try:
            _, annee, rang = numero.split("-")
            dst.execute("""
                INSERT INTO sequences (nom, annee, dernier) VALUES ('recu', ?, ?)
                ON CONFLICT(nom, annee) DO UPDATE
                SET dernier = MAX(dernier, excluded.dernier)
            """, (int(annee), int(rang)))
        except (ValueError, AttributeError):
            continue

    # --- 6. métadonnées ----------------------------------------------
    for cle, valeur in (
            ("schema_version", "2"),
            ("migre_le", datetime.datetime.now().isoformat(timespec="seconds")),
            ("source", "cotisations.db"),
            ("source_sha256", sha_source),
    ):
        dst.execute("INSERT OR REPLACE INTO meta (cle, valeur) VALUES (?, ?)",
                    (cle, valeur))

    rapport["dates_reparees"] = dates_reparees
    return rapport


# ---------------------------------------------------------------------
#  Vérification de la cible
# ---------------------------------------------------------------------
def verifier(dst, attendus, depassements_attendus):
    ecarts = []

    def controler(nom, obtenu, attendu):
        if obtenu != attendu:
            ecarts.append("%s : obtenu %r, attendu %r" % (nom, obtenu, attendu))

    for table, n in ATTENDU.items():
        controler("nombre de %s" % table,
                  dst.execute("SELECT COUNT(*) FROM %s" % table).fetchone()[0], n)
    controler("nombre d'exercices",
              dst.execute("SELECT COUNT(*) FROM exercices").fetchone()[0],
              attendus["campagnes"])
    controler("nombre d'échéances",
              dst.execute("SELECT COUNT(*) FROM echeances").fetchone()[0],
              attendus["mois_attendus"])

    controler("total des affectations",
              dst.execute("SELECT SUM(montant) FROM affectations").fetchone()[0],
              TOTAL_ATTENDU)
    controler("total des paiements",
              dst.execute("SELECT SUM(montant_total) FROM paiements").fetchone()[0],
              TOTAL_ATTENDU)
    for annee, total in PAR_ANNEES_ATTENDU.items():
        obtenu = dst.execute("""
            SELECT IFNULL(SUM(a.montant), 0)
              FROM affectations a
              JOIN echeances e ON e.id = a.echeance_id
             WHERE e.annee = ?
        """, (annee,)).fetchone()[0]
        controler("total %d" % annee, obtenu, total)

    controler("paiements multi-exercices", dst.execute("""
        SELECT COUNT(*) FROM (
            SELECT a.paiement_id
              FROM affectations a
              JOIN echeances e ON e.id = a.echeance_id
             GROUP BY a.paiement_id
            HAVING COUNT(DISTINCT e.exercice_id) > 1)
    """).fetchone()[0], attendus["multi_annees"])

    controler("intégrité", dst.execute("PRAGMA integrity_check").fetchone()[0],
              "ok")
    controler("clés étrangères",
              len(dst.execute("PRAGMA foreign_key_check").fetchall()), 0)
    controler("paiements incohérents",
              dst.execute("SELECT COUNT(*) FROM v_paiements_incoherents"
                          ).fetchone()[0], 0)

    obtenus = {(r["membre_id"], r["annee"], r["mois"])
               for r in dst.execute("SELECT membre_id, annee, mois "
                                    "FROM v_affectations_depassement")}
    controler("dépassements (liste)", obtenus, depassements_attendus)

    # le compteur de reçus doit couvrir tous les numéros déjà attribués
    for p in dst.execute("SELECT numero_recu FROM paiements "
                         "WHERE numero_recu IS NOT NULL"):
        _, annee, rang = p["numero_recu"].split("-")
        dernier = dst.execute("SELECT dernier FROM sequences "
                              "WHERE nom='recu' AND annee=?", (int(annee),)
                              ).fetchone()
        if dernier is None or dernier[0] < int(rang):
            ecarts.append("compteur de reçus incohérent pour %s"
                          % p["numero_recu"])
            break

    return ecarts


# ---------------------------------------------------------------------
#  Programme
# ---------------------------------------------------------------------
def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--source", default=str(SOURCE_DEFAUT))
    ap.add_argument("--sortie", default=str(SORTIE_DEFAUT))
    ap.add_argument("--schema", default=str(SCHEMA_V2))
    ap.add_argument("--garder-temporaire", action="store_true")
    args = ap.parse_args(argv)

    source = Path(args.source)
    sortie = Path(args.sortie)
    temporaire = sortie.with_suffix(sortie.suffix + ".tmp")

    if not source.exists():
        print("Source introuvable : %s" % source)
        return 2
    if source.resolve() == sortie.resolve():
        print("La sortie doit être un fichier différent de la source.")
        return 2
    if temporaire.exists():
        temporaire.unlink()

    sha_avant = empreinte(source)
    src = ouvrir_lecture_seule(source)
    attendus = mesurer_source(src)
    depassements = depassements_source(src)

    # Un montant fractionnaire ne peut pas être recopié en entier : le
    # tronquer déplacerait de l'argent. On refuse plutôt que d'arrondir.
    if attendus["fractionnaires"]:
        print("Refus : %d montant(s) non entier(s) en base — conversion "
              "impossible sans perte." % attendus["fractionnaires"])
        return 2

    print("== source ==")
    print("  %s  (%s)" % (source.name, sha_avant[:16] + "…"))
    print("  " + " · ".join("%s %d" % (t, attendus[t]) for t in ATTENDU))
    print("  total %s FCFA · %s" % (
        format(attendus["total"], ",").replace(",", " "),
        " · ".join("%d : %s" % (a, format(v, ",").replace(",", " "))
                   for a, v in sorted(attendus["par_annee"].items()))))
    print("  dépassements connus : %d" % len(depassements))

    dst = sqlite3.connect(temporaire)
    dst.row_factory = sqlite3.Row
    dst.execute("PRAGMA foreign_keys = ON")
    try:
        dst.executescript(Path(args.schema).read_text(encoding="utf-8"))
        dst.execute("BEGIN")
        rapport = migrer(src, dst, sha_avant)
        ecarts = verifier(dst, attendus, depassements)
        if ecarts:
            dst.rollback()
            print("\n== MIGRATION REFUSÉE ==")
            for e in ecarts:
                print("  - " + e)
            return 2
        dst.commit()
    except SystemExit as e:
        dst.rollback()
        print("\n== MIGRATION REFUSÉE ==\n  %s" % e)
        return 2
    except Exception as e:                             # noqa: BLE001
        dst.rollback()
        print("\n== MIGRATION REFUSÉE ==\n  %s: %s" % (type(e).__name__, e))
        return 2
    finally:
        dst.close()

    # vérification finale sur le fichier écrit, puis publication atomique
    controle = sqlite3.connect("file:%s?mode=ro" % temporaire.as_posix(),
                              uri=True)
    integrite = controle.execute("PRAGMA integrity_check").fetchone()[0]
    controle.close()
    if integrite != "ok":
        print("\n== MIGRATION REFUSÉE ==\n  intégrité du fichier : %s"
              % integrite)
        return 2
    os.replace(temporaire, sortie)

    sha_apres = empreinte(source)
    print("\n== cible ==")
    print("  %s" % sortie)
    print("  exercices %d · échéances %d · paiements %d · affectations %d"
          % (rapport["exercices"], rapport["echeances"], rapport["paiements"],
             rapport["affectations"]))
    print("  dates normalisées : %d" % len(rapport["dates_reparees"]))
    print("\n== source intacte ==")
    print("  %s" % ("OUI (SHA-256 identique)" if sha_apres == sha_avant
                    else "NON — ARRÊT"))
    return 0 if sha_apres == sha_avant else 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
