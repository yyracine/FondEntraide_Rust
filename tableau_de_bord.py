"""
tableau_de_bord.py — Calculs de synthèse pour le tableau de bord.

Toutes les sommes sont calculées sur `affectations.annee` (l'exercice
concerné), jamais sur `paiements.campagne_id` : un versement fait en 2026
peut régler une cotisation de 2025.

Aucune écriture : ce module ne fait que lire.
"""

import cotisations as C
import parametres as P


def _montant_exercice(con, annee):
    """Montant mensuel de l'exercice, ou le montant par défaut."""
    camp = C.campagne(con, annee)
    if camp is not None:
        return float(camp["montant_mensuel"])
    return P.montant_par_defaut(con)


def _mensualites_attendues(con, annee):
    """Nombre de mois échus sur l'exercice (voir C.mois_echus, source unique)."""
    return C.mois_echus(con, annee)


# ---------------------------------------------------------------------
#  Vue d'ensemble
# ---------------------------------------------------------------------
def vue_ensemble(con, annee):
    """Chiffres clés de l'exercice."""
    mensuel = _montant_exercice(con, annee)
    echeances = _mensualites_attendues(con, annee)

    nb_membres = con.execute(
        "SELECT COUNT(*) FROM membres WHERE statut = 'actif'").fetchone()[0]
    attendu = nb_membres * mensuel * echeances

    encaisse = con.execute(
        "SELECT IFNULL(SUM(montant), 0) FROM affectations WHERE annee = ?",
        (annee,)).fetchone()[0]

    cotisants = con.execute("""
        SELECT COUNT(DISTINCT p.membre_id)
        FROM affectations a JOIN paiements p ON p.id = a.paiement_id
        WHERE a.annee = ?
    """, (annee,)).fetchone()[0]

    nb_versements = con.execute("""
        SELECT COUNT(DISTINCT p.id)
        FROM paiements p
        WHERE EXISTS (SELECT 1 FROM affectations a
                      WHERE a.paiement_id = p.id AND a.annee = ?)
    """, (annee,)).fetchone()[0]

    nb_familles = con.execute("SELECT COUNT(*) FROM familles").fetchone()[0]

    # membres à jour = ceux qui ont réglé tous les mois échus
    a_jour = 0
    if echeances:
        for m in con.execute("SELECT id FROM membres WHERE statut='actif'"):
            s = C.situation(con, m["id"], annee)
            payes = len([1 for mo in range(1, echeances + 1)
                         if s["mois_payes"].get(mo, 0) >= mensuel])
            if payes == echeances:
                a_jour += 1

    return {
        "annee": annee,
        "montant_mensuel": mensuel,
        "echeances": echeances,
        "nb_membres": nb_membres,
        "nb_familles": nb_familles,
        "nb_cotisants": cotisants,
        "nb_versements": nb_versements,
        "attendu": attendu,
        "encaisse": encaisse,
        "reste": max(0, attendu - encaisse),
        "taux": (encaisse / attendu * 100) if attendu else 0.0,
        "a_jour": a_jour,
        "en_retard": max(0, nb_membres - a_jour),
    }


# ---------------------------------------------------------------------
#  Par niveau de la hiérarchie
# ---------------------------------------------------------------------
# Pour chaque niveau : la colonne d'identification, son libellé, et la
# suite de jointures qui remonte d'une famille jusqu'à ce niveau.
_NIVEAUX = {
    "famille": (
        "f.id", "f.nom",
        """FROM familles f""",
    ),
    "lignee": (
        "l.id", "l.nom",
        """FROM familles f
           JOIN lignees l ON l.id = f.lignee_id""",
    ),
    "grande_famille": (
        "gf.id", "gf.nom",
        """FROM familles f
           JOIN lignees l ON l.id = f.lignee_id
           JOIN grandes_familles gf ON gf.id = l.grande_famille_id""",
    ),
    "clan": (
        "cl.id", "cl.nom",
        """FROM familles f
           JOIN lignees l ON l.id = f.lignee_id
           JOIN grandes_familles gf ON gf.id = l.grande_famille_id
           JOIN clans cl ON cl.id = gf.clan_id""",
    ),
}


def par_niveau(con, annee, niveau="clan"):
    """Agrégat par clan / grande famille / lignée / famille.

    On part des familles puis on remonte : le nombre de membres et les
    montants restent exacts à chaque niveau.
    """
    if niveau not in _NIVEAUX:
        raise ValueError(f"niveau inconnu : {niveau}")
    cle, nom, source = _NIVEAUX[niveau]

    return con.execute(f"""
        SELECT {cle} AS id, {nom} AS libelle,
               COUNT(DISTINCT m.id)          AS nb_membres,
               IFNULL(SUM(a.montant), 0)     AS encaisse,
               COUNT(DISTINCT p.membre_id)   AS nb_cotisants
        {source}
        LEFT JOIN membres m
               ON m.famille_id = f.id AND m.statut = 'actif'
        LEFT JOIN paiements p ON p.membre_id = m.id
        LEFT JOIN affectations a ON a.paiement_id = p.id AND a.annee = ?
        GROUP BY {cle}
        ORDER BY encaisse DESC, libelle COLLATE NOCASE
    """, (annee,)).fetchall()


# ---------------------------------------------------------------------
#  Membres en retard
# ---------------------------------------------------------------------
def membres_en_retard(con, annee):
    """Liste des membres actifs n'ayant pas réglé tous les mois échus."""
    mensuel = _montant_exercice(con, annee)
    echeances = _mensualites_attendues(con, annee)
    if not echeances:
        return []

    resultat = []
    for m in con.execute("""
        SELECT m.id, m.nom, m.prenom, f.nom AS famille, cl.nom AS clan
        FROM membres m
        JOIN familles f ON f.id = m.famille_id
        JOIN lignees l ON l.id = f.lignee_id
        JOIN grandes_familles gf ON gf.id = l.grande_famille_id
        JOIN clans cl ON cl.id = gf.clan_id
        WHERE m.statut = 'actif'
        ORDER BY cl.nom COLLATE NOCASE, f.nom COLLATE NOCASE,
                 m.nom COLLATE NOCASE
    """):
        s = C.situation(con, m["id"], annee)
        payes = [mo for mo in range(1, echeances + 1)
                 if s["mois_payes"].get(mo, 0) >= mensuel]
        manquants = echeances - len(payes)
        if manquants <= 0:
            continue
        du = manquants * mensuel
        # mois en retard, en clair
        mois_du = [C.MOIS_COURTS[mo - 1] for mo in range(1, echeances + 1)
                   if s["mois_payes"].get(mo, 0) < mensuel]
        resultat.append({
            "membre_id": m["id"],
            "membre": f"{m['nom']} {m['prenom'] or ''}".strip(),
            "famille": m["famille"],
            "clan": m["clan"],
            "mois_payes": len(payes),
            "mois_echus": echeances,
            "mois_manquants": manquants,
            "du": du,
            "mois_en_clair": ", ".join(mois_du),
        })
    resultat.sort(key=lambda r: (-r["du"], r["membre"]))
    return resultat


# ---------------------------------------------------------------------
#  Détail mensuel (grille 12 mois par famille)
# ---------------------------------------------------------------------
def grille_mensuelle(con, annee, famille_id=None):
    """Liste des membres avec, pour chaque mois, le montant réglé."""
    mensuel = _montant_exercice(con, annee)
    sql = """
        SELECT m.id, m.nom, m.prenom, f.nom AS famille
        FROM membres m JOIN familles f ON f.id = m.famille_id
        WHERE m.statut = 'actif'
    """
    params = []
    if famille_id is not None:
        sql += " AND m.famille_id = ?"
        params.append(famille_id)
    sql += " ORDER BY f.nom COLLATE NOCASE, m.nom COLLATE NOCASE"

    lignes = []
    for m in con.execute(sql, params):
        payes = C.mois_payes(con, m["id"], annee)
        mois = [payes.get(mo, 0) for mo in range(1, 13)]
        lignes.append({
            "membre": f"{m['nom']} {m['prenom'] or ''}".strip(),
            "famille": m["famille"],
            "mois": mois,
            "total": sum(mois),
            "complet": all(v >= mensuel for v in mois) if mensuel else False,
        })
    return lignes


# =====================================================================
#  Montants cotisés, tous niveaux × toutes années
# =====================================================================
def montants_par_niveau(con, niveau="clan"):
    """Montant cotisé par niveau, avec une ligne par année.

    Renvoie (annees, lignes) où :
      annees  = liste ordonnée des années présentes
      lignes  = [{id, libelle, par_annee: {annee: montant}, total, ...}]

    Le montant d'un niveau est la somme des affectations de l'année pour
    tous les membres appartenant à ce niveau, plus les membres et les
    familles qui y sont rattachés (même s'ils n'ont rien versé).
    """
    if niveau not in _NIVEAUX:
        raise ValueError(f"niveau inconnu : {niveau}")
    cle, nom, source = _NIVEAUX[niveau]

    # tous les membres actifs, avec leur année et montant
    detail = con.execute(f"""
        SELECT {cle} AS id, {nom} AS libelle, a.annee AS annee,
               IFNULL(SUM(a.montant), 0) AS montant
        {source}
        LEFT JOIN membres m ON m.famille_id = f.id AND m.statut = 'actif'
        LEFT JOIN paiements p ON p.membre_id = m.id
        LEFT JOIN affectations a ON a.paiement_id = p.id
        WHERE a.annee IS NOT NULL
        GROUP BY {cle}, a.annee
    """).fetchall()

    # effectifs et familles, indépendamment des paiements
    effectifs = con.execute(f"""
        SELECT {cle} AS id, {nom} AS libelle,
               COUNT(DISTINCT m.id) AS nb_membres,
               COUNT(DISTINCT f.id) AS nb_familles
        {source}
        LEFT JOIN membres m ON m.famille_id = f.id AND m.statut = 'actif'
        GROUP BY {cle}
    """).fetchall()

    annees = sorted({r["annee"] for r in detail})

    lignes = {}
    for r in effectifs:
        lignes[r["id"]] = {
            "id": r["id"], "libelle": r["libelle"],
            "nb_membres": r["nb_membres"], "nb_familles": r["nb_familles"],
            "par_annee": {}, "total": 0,
        }
    for r in detail:
        if r["id"] not in lignes:
            lignes[r["id"]] = {
                "id": r["id"], "libelle": r["libelle"],
                "nb_membres": 0, "nb_familles": 0,
                "par_annee": {}, "total": 0,
            }
        lignes[r["id"]]["par_annee"][r["annee"]] = r["montant"]
        lignes[r["id"]]["total"] += r["montant"]

    resultat = sorted(lignes.values(),
                      key=lambda x: (-x["total"], x["libelle"].upper()))
    return annees, resultat


def montant_par_membre(con, annee=None):
    """Montant cotisé par membre et par année.

    Renvoie (annees, lignes) avec lignes = [{membre, famille, clan,
    par_annee, total}]. Si annee est fourni, seules les années jusqu'à
    celle-ci sont conservées.
    """
    sql = """
        SELECT m.id AS id,
               TRIM(m.nom || ' ' || IFNULL(m.prenom, '')) AS membre,
               f.nom AS famille, cl.nom AS clan,
               a.annee AS annee,
               IFNULL(SUM(a.montant), 0) AS montant
        FROM membres m
        JOIN familles f ON f.id = m.famille_id
        JOIN lignees l ON l.id = f.lignee_id
        JOIN grandes_familles gf ON gf.id = l.grande_famille_id
        JOIN clans cl ON cl.id = gf.clan_id
        LEFT JOIN paiements p ON p.membre_id = m.id
        LEFT JOIN affectations a ON a.paiement_id = p.id
        WHERE m.statut = 'actif' AND a.annee IS NOT NULL
        {filtre}
        GROUP BY m.id, a.annee
        ORDER BY cl.nom COLLATE NOCASE, f.nom COLLATE NOCASE,
                 m.nom COLLATE NOCASE
    """.format(filtre="AND a.annee <= ?" if annee is not None else "")
    params = (annee,) if annee is not None else ()
    detail = con.execute(sql, params).fetchall()

    annees = sorted({r["annee"] for r in detail})

    infos = con.execute("""
        SELECT m.id AS id,
               TRIM(m.nom || ' ' || IFNULL(m.prenom, '')) AS membre,
               f.nom AS famille, cl.nom AS clan
        FROM membres m
        JOIN familles f ON f.id = m.famille_id
        JOIN lignees l ON l.id = f.lignee_id
        JOIN grandes_familles gf ON gf.id = l.grande_famille_id
        JOIN clans cl ON cl.id = gf.clan_id
        WHERE m.statut = 'actif'
        ORDER BY cl.nom COLLATE NOCASE, f.nom COLLATE NOCASE,
                 m.nom COLLATE NOCASE
    """).fetchall()

    lignes = {r["id"]: {"id": r["id"], "membre": r["membre"],
                        "famille": r["famille"], "clan": r["clan"],
                        "par_annee": {}, "total": 0}
              for r in infos}
    for r in detail:
        l = lignes[r["id"]]
        l["par_annee"][r["annee"]] = r["montant"]
        l["total"] += r["montant"]

    resultat = sorted(lignes.values(),
                      key=lambda x: (-x["total"], x["membre"].upper()))
    return annees, resultat
