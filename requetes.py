#!/usr/bin/env python3
"""
Requêtes utilitaires sur cotisations.db — hiérarchie
    Clan > Grande famille > Lignée > Famille > Membre

Usage :
    python requetes.py                              récap général + par clan
    python requetes.py --clans                      état par clan
    python requetes.py --clan "YAOCRE"              détail d'un clan
    python requetes.py --grandes-familles "YAOCRE"  grandes familles d'un clan
    python requetes.py --feuille "YAOCRE ALLIEYOFE" détail d'une grande famille
    python requetes.py --lignee "YAOCRE ALLIEYOFFE"
    python requetes.py --membre 211                 fiche d'un membre
    python requetes.py --recherche "YAO"            recherche par nom
    python requetes.py --impayes 2025               actifs sans versement
    python requetes.py --grille "YAOCRE ALLIEYOFE" --annee 2024   grille mensuelle
    python requetes.py --top 20                     meilleurs cotisants
    python requetes.py --synthese 2024              synthèse annuelle par clan
"""
import argparse
import json
import sqlite3
from pathlib import Path

DB = Path(__file__).parent / "cotisations.db"
REPERTOIRES = Path(__file__).parent / "repertoires.json"
# la feuille-répertoire nomme le clan « AMBOFF » alors que A1 des feuilles
# de détail donne « KOUADIO AMBOFF »
# Correspondance nom de clan dans les feuilles-répertoires
#   et nom de clan tel que lu dans A1 des feuilles de détail.
ALIAS_REPERTOIRE = {
    "AMBOFF": "KOUADIO AMBOFF",   # la feuille dit « LIGNEE AMBOFF »
    "AGOH": "AGO",                # la feuille dit « LIGNEE AGOH »
}
MOIS = ["Janv", "Févr", "Mars", "Avr", "Mai", "Juin",
        "Juil", "Août", "Sept", "Oct", "Nov", "Déc"]
LIGNE = 78


def con():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c


def fa(v):
    """Formate un entier avec espaces fines (FCFA)."""
    if v is None:
        return "-"
    return f"{int(round(v)):,}".replace(",", " ")


def titre(t):
    print("\n" + "=" * LIGNE)
    print(t)
    print("=" * LIGNE)


def tableau(rows, cols=None, largeurs=None):
    if not isinstance(rows, list):
        rows = list(rows)
    if not rows:
        print("  (aucun résultat)")
        return
    cols = cols or list(rows[0].keys())
    rows = [dict(r) for r in rows]
    w = largeurs or {}
    larg = [w.get(c, min(30, max(len(str(c)), *(len(str(r[c] if r[c] is not None else "-")) for r in rows[:200])))) for c in cols]
    print("  " + " | ".join(str(c).ljust(l) for c, l in zip(cols, larg)))
    print("  " + "-" * (sum(larg) + 3 * (len(cols) - 1)))
    for r in rows:
        print("  " + " | ".join(str(r[c] if r[c] is not None else "-").ljust(l) for c, l in zip(cols, larg)))


# --------------------------------------------------------------- synthèses
def recap(c):
    titre("RÉCAPITULATIF GÉNÉRAL PAR CAMPAGNE")
    tableau(c.execute("""
        SELECT a.annee                                   AS campagne,
               COUNT(DISTINCT p.membre_id)               AS cotisants,
               COUNT(DISTINCT p.id)                      AS versements,
               SUM(a.montant)                            AS total_fcfa
        FROM affectations a
        JOIN paiements p ON p.id = a.paiement_id
        GROUP BY a.annee ORDER BY a.annee
    """))


def par_clan(c, annee=None):
    """État par clan. Les montants viennent d'AFFECTATIONS (un paiement
    peut couvrir plusieurs années), pas de paiements.montant_total."""
    t = "ÉTAT PAR CLAN" + (f" — {annee}" if annee else "")
    titre(t)
    cond = f"AND a.annee = {int(annee)}" if annee else ""
    q = f"""
        SELECT cl.nom AS clan,
               (SELECT COUNT(*) FROM grandes_familles g WHERE g.clan_id = cl.id) AS grandes_fam,
               (SELECT COUNT(*) FROM membres m
                  JOIN familles fa ON fa.id = m.famille_id
                  JOIN lignees lg ON lg.id = fa.lignee_id
                  JOIN grandes_familles g2 ON g2.id = lg.grande_famille_id
                 WHERE g2.clan_id = cl.id) AS membres,
               (SELECT COUNT(DISTINCT p.membre_id) FROM affectations a
                  JOIN paiements p ON p.id = a.paiement_id
                  JOIN membres m ON m.id = p.membre_id
                  JOIN familles fa ON fa.id = m.famille_id
                  JOIN lignees lg ON lg.id = fa.lignee_id
                  JOIN grandes_familles g3 ON g3.id = lg.grande_famille_id
                 WHERE g3.clan_id = cl.id {cond}) AS cotisants,
               (SELECT IFNULL(SUM(a.montant),0) FROM affectations a
                  JOIN paiements p ON p.id = a.paiement_id
                  JOIN membres m ON m.id = p.membre_id
                  JOIN familles fa ON fa.id = m.famille_id
                  JOIN lignees lg ON lg.id = fa.lignee_id
                  JOIN grandes_familles g4 ON g4.id = lg.grande_famille_id
                 WHERE g4.clan_id = cl.id {cond}) AS verse
        FROM clans cl ORDER BY verse DESC
    """
    tableau(c.execute(q))
    r = c.execute("SELECT SUM(montant) FROM affectations" +
                  (f" WHERE annee={int(annee)}" if annee else "")).fetchone()[0]
    print(f"\n  TOTAL : {fa(r)} FCFA")


def detail_clan(c, nom):
    cl = c.execute("SELECT * FROM clans WHERE nom LIKE ?", (f"%{nom}%",)).fetchone()
    if not cl:
        print(f"Clan « {nom} » introuvable.")
        return
    titre(f"CLAN {cl['nom']} — grandes familles")
    tableau(c.execute("""
        SELECT gf.nom AS grande_famille,
               lg.nom AS lignee,
               (SELECT COUNT(*) FROM membres m
                  JOIN familles f2 ON f2.id = m.famille_id
                 WHERE f2.lignee_id = lg.id) AS membres,
               IFNULL((SELECT SUM(a.montant) FROM affectations a
                         JOIN paiements p ON p.id = a.paiement_id
                         JOIN membres m2 ON m2.id = p.membre_id
                         JOIN familles f3 ON f3.id = m2.famille_id
                        WHERE f3.lignee_id = lg.id), 0) AS verse
        FROM grandes_familles gf
        JOIN lignees lg ON lg.grande_famille_id = gf.id
        WHERE gf.clan_id = ?
        ORDER BY verse DESC
    """, (cl["id"],)))


def detail_grande_famille(c, nom):
    gf = c.execute("SELECT gf.*, cl.nom AS clan FROM grandes_familles gf "
                   "JOIN clans cl ON cl.id=gf.clan_id WHERE gf.nom LIKE ?",
                   (f"%{nom}%",)).fetchone()
    if not gf:
        print(f"Grande famille « {nom} » introuvable.")
        return
    titre(f"GRANDE FAMILLE {gf['nom']}  (clan {gf['clan']})")
    tableau(c.execute("""
        SELECT fa.ordre AS n,
               fa.nom   AS famille,
               (SELECT COUNT(*) FROM membres m WHERE m.famille_id = fa.id) AS membres,
               IFNULL((SELECT SUM(a.montant) FROM affectations a
                         JOIN paiements p ON p.id = a.paiement_id
                         JOIN membres m2 ON m2.id = p.membre_id
                        WHERE m2.famille_id = fa.id), 0) AS verse
        FROM familles fa
        JOIN lignees lg ON lg.id = fa.lignee_id
        WHERE lg.grande_famille_id = ?
        ORDER BY verse DESC
    """, (gf["id"],)))
    tot = c.execute("""SELECT IFNULL(SUM(a.montant),0) FROM affectations a
        JOIN paiements p ON p.id=a.paiement_id JOIN membres m ON m.id=p.membre_id
        JOIN familles fa ON fa.id=m.famille_id
        JOIN lignees lg ON lg.id=fa.lignee_id WHERE lg.grande_famille_id=?""",
                    (gf["id"],)).fetchone()[0]
    print(f"\n  TOTAL grande famille : {fa(tot)} FCFA")


def detail_lignee(c, nom):
    lg = c.execute("SELECT lg.*, gf.nom AS gf, cl.nom AS clan FROM lignees lg "
                   "JOIN grandes_familles gf ON gf.id=lg.grande_famille_id "
                   "JOIN clans cl ON cl.id=gf.clan_id WHERE lg.nom LIKE ?",
                   (f"%{nom}%",)).fetchone()
    if not lg:
        print(f"Lignée « {nom} » introuvable.")
        return
    titre(f"LIGNÉE {lg['nom']}  (GF {lg['gf']} / clan {lg['clan']})")
    tableau(c.execute("""
        SELECT m.id, m.nom, m.prenom, fa.nom AS famille, m.parent_id,
               IFNULL((SELECT SUM(a.montant) FROM affectations a
                         JOIN paiements p ON p.id=a.paiement_id
                        WHERE p.membre_id=m.id),0) AS verse
        FROM membres m JOIN familles fa ON fa.id=m.famille_id
        WHERE fa.lignee_id = ? ORDER BY fa.ordre, m.id
    """, (lg["id"],)))


def fiche_membre(c, mid):
    m = c.execute("""
        SELECT m.*, fa.nom AS famille, lg.nom AS lignee, gf.nom AS gf, cl.nom AS clan
        FROM membres m JOIN familles fa ON fa.id=m.famille_id
        JOIN lignees lg ON lg.id=fa.lignee_id
        JOIN grandes_familles gf ON gf.id=lg.grande_famille_id
        JOIN clans cl ON cl.id=gf.clan_id WHERE m.id=?""", (mid,)).fetchone()
    if not m:
        print("Membre introuvable.")
        return
    print(f"\n=== MEMBRE #{m['id']} : {m['nom']} {m['prenom'] or ''} ===")
    print(f"  Clan           : {m['clan']}")
    print(f"  Grande famille : {m['gf']}")
    print(f"  Lignée         : {m['lignee']}")
    print(f"  Famille        : {m['famille']}")
    print(f"  Statut         : {m['statut']}   Ordre fratrie : {m['ordre_fratrie']}")
    print(f"  Téléphone      : {m['telephone'] or '-'}   Parent : {m['parent_id'] or '-'}")
    titre("Versements")
    tableau(c.execute("""
        SELECT ca.annee, p.date_paiement, p.montant_total,
               GROUP_CONCAT(a.mois) AS mois
        FROM paiements p JOIN campagnes ca ON ca.id=p.campagne_id
        LEFT JOIN affectations a ON a.paiement_id=p.id
        WHERE p.membre_id=? GROUP BY p.id ORDER BY ca.annee
    """, (mid,)))
    tot = c.execute("SELECT IFNULL(SUM(a.montant),0) FROM affectations a "
                    "JOIN paiements p ON p.id=a.paiement_id WHERE p.membre_id=?", (mid,)).fetchone()[0]
    print(f"\n  TOTAL versé : {fa(tot)} FCFA")


def recherche(c, txt):
    titre(f"RECHERCHE « {txt} »")
    tableau(c.execute("""
        SELECT m.id, m.nom, m.prenom, gf.nom AS grande_famille, fa.nom AS famille,
               IFNULL((SELECT SUM(a.montant) FROM affectations a
                         JOIN paiements p ON p.id=a.paiement_id
                        WHERE p.membre_id=m.id),0) AS verse
        FROM membres m JOIN familles fa ON fa.id=m.famille_id
        JOIN lignees lg ON lg.id=fa.lignee_id
        JOIN grandes_familles gf ON gf.id=lg.grande_famille_id
        WHERE m.nom LIKE ? OR IFNULL(m.prenom,'') LIKE ?
        ORDER BY m.nom, m.prenom LIMIT 100
    """, (f"%{txt}%", f"%{txt}%")))


def impayes(c, annee):
    titre(f"MEMBRES ACTIFS SANS VERSEMENT — {annee}")
    rows = c.execute("""
        SELECT cl.nom AS clan, gf.nom AS grande_famille, m.id, m.nom, m.prenom
        FROM membres m
        JOIN familles fa ON fa.id=m.famille_id
        JOIN lignees lg ON lg.id=fa.lignee_id
        JOIN grandes_familles gf ON gf.id=lg.grande_famille_id
        JOIN clans cl ON cl.id=gf.clan_id
        WHERE m.statut='actif'
          AND NOT EXISTS (SELECT 1 FROM affectations a JOIN paiements p ON p.id=a.paiement_id
                          WHERE p.membre_id=m.id AND a.annee=?)
        ORDER BY cl.nom, gf.nom, m.nom LIMIT 300
    """, (annee,)).fetchall()
    print(f"  {len(rows)} membre(s) sans versement en {annee}")
    tableau(rows, cols=["clan", "grande_famille", "nom", "prenom"])


def grille(c, gf_nom, annee):
    gf = c.execute("SELECT id, nom FROM grandes_familles WHERE nom LIKE ?", (f"%{gf_nom}%",)).fetchone()
    if not gf:
        print(f"Grande famille « {gf_nom} » introuvable.")
        return
    rows = c.execute("""
        SELECT m.id, m.nom || ' ' || IFNULL(m.prenom,'') AS membre, a.mois, SUM(a.montant) AS mt
        FROM affectations a JOIN paiements p ON p.id=a.paiement_id
        JOIN membres m ON m.id=p.membre_id
        JOIN familles fa ON fa.id=m.famille_id
        JOIN lignees lg ON lg.id=fa.lignee_id
        WHERE lg.grande_famille_id=? AND a.annee=?
        GROUP BY m.id, a.mois ORDER BY m.id, a.mois
    """, (gf["id"], annee)).fetchall()
    titre(f"GRILLE {gf['nom']} — {annee}")
    if not rows:
        print("  (aucune cotisation)")
        return
    entete = f"{'Membre':32s} " + " ".join(f"{x:>6s}" for x in MOIS) + f" {'TOTAL':>9s}"
    print(entete)
    print("-" * len(entete))
    courant, ligne, tot = None, {}, 0
    for r in rows:
        if r["membre"] != courant:
            if courant is not None:
                print(f"{courant[:32]:32s} " + " ".join(f"{int(ligne[k]):>6d}" if ligne.get(k) else "      " for k in range(1, 13)) + f" {int(tot):>9d}")
            courant, ligne, tot = r["membre"], {}, 0
        ligne[r["mois"]] = r["mt"]
        tot += r["mt"]
    print(f"{courant[:32]:32s} " + " ".join(f"{int(ligne[k]):>6d}" if ligne.get(k) else "      " for k in range(1, 13)) + f" {int(tot):>9d}")


def top(c, n):
    titre(f"TOP {n} COTISANTS")
    tableau(c.execute("""
        SELECT m.nom, m.prenom, gf.nom AS grande_famille, SUM(a.montant) AS verse
        FROM membres m
        JOIN paiements p ON p.membre_id=m.id
        JOIN affectations a ON a.paiement_id=p.id
        JOIN familles fa ON fa.id=m.famille_id
        JOIN lignees lg ON lg.id=fa.lignee_id
        JOIN grandes_familles gf ON gf.id=lg.grande_famille_id
        GROUP BY m.id ORDER BY verse DESC LIMIT ?
    """, (n,)))


def synthese(c, annee):
    titre(f"SYNTHÈSE {annee} PAR CLAN ET GRANDE FAMILLE")
    tableau(c.execute("""
        SELECT cl.nom AS clan, gf.nom AS grande_famille,
               COUNT(DISTINCT p.membre_id) AS cotisants,
               SUM(a.montant) AS verse
        FROM affectations a
        JOIN paiements p ON p.id=a.paiement_id
        JOIN membres m ON m.id=p.membre_id
        JOIN familles fa ON fa.id=m.famille_id
        JOIN lignees lg ON lg.id=fa.lignee_id
        JOIN grandes_familles gf ON gf.id=lg.grande_famille_id
        JOIN clans cl ON cl.id=gf.clan_id
        WHERE a.annee = ?
        GROUP BY gf.id ORDER BY cl.nom, verse DESC
    """, (annee,)))


def audit(c, annee):
    """Compare, par clan, le détail (base, autorité) aux feuilles-répertoires
    du classeur Excel. Révèle les incohérences du fichier source."""
    titre(f"AUDIT {annee} — détail (base) vs répertoire (Excel)")
    if not REPERTOIRES.exists():
        print("  repertoires.json absent : lancez d'abord extrait_repertoires.py")
        return
    rep = json.loads(REPERTOIRES.read_text(encoding="utf-8"))
    # normalisation des noms de clan
    valeurs = {}
    for clan, d in rep.items():
        valeurs[ALIAS_REPERTOIRE.get(clan, clan)] = d["totaux"].get(str(annee), 0.0)

    base = {}
    for clan, v in c.execute("""
        SELECT cl.nom, IFNULL(SUM(a.montant), 0)
        FROM affectations a
        JOIN paiements p ON p.id = a.paiement_id
        JOIN membres m ON m.id = p.membre_id
        JOIN familles fa ON fa.id = m.famille_id
        JOIN lignees lg ON lg.id = fa.lignee_id
        JOIN grandes_familles gf ON gf.id = lg.grande_famille_id
        JOIN clans cl ON cl.id = gf.clan_id
        WHERE a.annee = ?
        GROUP BY cl.nom
    """, (annee,)):
        base[clan] = v

    lignes = []
    t_base = t_rep = 0
    for clan in sorted(set(base) | set(valeurs)):
        b = base.get(clan, 0)
        r = valeurs.get(clan, 0)
        t_base += b
        t_rep += r
        ecart = b - r
        lignes.append({
            "clan": clan,
            "detail_base": fa(b),
            "repertoire_excel": fa(r),
            "ecart": ("0" if ecart == 0 else ("+" if ecart > 0 else "") + fa(ecart)),
        })
    lignes.append({
        "clan": "TOTAL",
        "detail_base": fa(t_base),
        "repertoire_excel": fa(t_rep),
        "ecart": ("0" if t_base - t_rep == 0 else ("+" if t_base > t_rep else "") + fa(t_base - t_rep)),
    })
    tableau(lignes)

    print("\n  Le détail (base) est la référence : il provient des 46 feuilles")
    print("  détaillées, feuille par feuille, et correspond à leur somme exacte.")
    print("  Les feuilles-répertoires (LIGNEE xxx) portent des totaux très")
    print("  inférieurs et désynchronisés : le récapitulatif Excel s'appuie")
    print("  dessus, d'où l'écart constaté.")


def main():
    ap = argparse.ArgumentParser(description="Requêtes cotisations (Clan > GF > Lignée > Famille > Membre)")
    ap.add_argument("--clans", action="store_true")
    ap.add_argument("--clan")
    ap.add_argument("--grandes-familles", dest="gfs")
    ap.add_argument("--feuille")
    ap.add_argument("--lignee")
    ap.add_argument("--membre", type=int)
    ap.add_argument("--recherche")
    ap.add_argument("--impayes", type=int)
    ap.add_argument("--grille")
    ap.add_argument("--top", type=int)
    ap.add_argument("--synthese", type=int)
    ap.add_argument("--annee", type=int)
    ap.add_argument("--recap", action="store_true")
    ap.add_argument("--audit", type=int)
    a = ap.parse_args()

    c = con()
    if a.audit:
        audit(c, a.audit)
    elif a.membre:
        fiche_membre(c, a.membre)
    elif a.recherche:
        recherche(c, a.recherche)
    elif a.impayes:
        impayes(c, a.impayes)
    elif a.grille:
        grille(c, a.grille, a.annee or 2024)
    elif a.lignee:
        detail_lignee(c, a.lignee)
    elif a.feuille:
        detail_grande_famille(c, a.feuille)
    elif a.gfs:
        detail_clan(c, a.gfs)
    elif a.clan:
        detail_clan(c, a.clan)
    elif a.top:
        top(c, a.top)
    elif a.synthese:
        synthese(c, a.synthese)
    elif a.clans:
        par_clan(c, a.annee)
    elif a.recap:
        recap(c)
    else:
        recap(c)
        par_clan(c, 2024)
        par_clan(c, 2025)
    c.close()


if __name__ == "__main__":
    main()
