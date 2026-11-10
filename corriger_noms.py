"""
corriger_noms.py — Réparer les noms « parasites » hérités de l'import Excel.

Concerne les membres dont le NOM est vide, un séparateur (« / », « - », …) ou
commence par un séparateur : l'Excel s'en servait pour dire « même famille que
la ligne du dessus ». Le nom est alors repris du parent (ou, s'il n'y a pas de
parent exploitable, du membre précédent de la même famille).

Utilisation :

    python corriger_noms.py                     # SIMULATION : affiche, n'écrit rien
    python corriger_noms.py --base demo/xxx.db  # simulation sur une copie
    python corriger_noms.py --appliquer         # écrit dans cotisations.db

Par défaut rien n'est modifié : on examine d'abord ce que le script ferait.

Sécurité : sauvegarde automatique avant écriture, enregistrement des valeurs
d'origine dans la colonne `notes` (préfixe « [nom d'origine: …] ») et
vérification du nombre de lignes avant/après. Aucun nom à corriger = aucune
écriture.

Lancement autonome : python corriger_noms.py
"""
import argparse
import datetime
import re
import sqlite3
import sys
from pathlib import Path

BASE = Path(__file__).parent
BASE_PAR_DEFAUT = BASE / "cotisations.db"
DOSSIER_SAUVEGARDES = BASE / "sauvegardes"

# Un nom « parasite » : vide, fait uniquement de séparateurs, ou commençant
# par un séparateur. On ne touche PAS aux noms normaux.
RE_PARASITE_TOTAL = re.compile(r"^[\s/\\\-–—.,;:*+'’·|_]*$")
RE_PARASITE_TETE = re.compile(r"^[\s/\\\-–—.,;:*+'’·|_]+")
RE_PRENOM_VALIDE = re.compile(r"^[^\W\d_][\w'’\- .]*$", re.UNICODE)


def nom_est_parasite(nom):
    """Vrai si le nom est vide, purement séparateur, ou commence par un séparateur."""
    if nom is None:
        return True
    n = str(nom).strip()
    if RE_PARASITE_TOTAL.match(n):
        return True
    return bool(RE_PARASITE_TETE.match(n)) and not n[0].isalnum()


def nom_exploitable(nom):
    """Un nom peut-il servir de modèle à ses enfants ?"""
    if nom_est_parasite(nom):
        return False
    n = RE_PARASITE_TETE.sub("", str(nom)).strip()
    return bool(n) and n[0].isalpha()


def nom_depuis_prenom(prenom):
    """Pour « / APPIA SEWA » : le prénom contenait en fait le nom de famille."""
    if not prenom:
        return None
    mots = str(prenom).split()
    if len(mots) >= 2 and mots[0][:1].isalpha():
        return mots[0]
    return None


def nom_apres_separateur(nom_actuel):
    """« /APPIA » -> APPIA. Un seul mot suffit ici : c'est le champ nom."""
    if not nom_actuel:
        return None
    reste = RE_PARASITE_TETE.sub("", str(nom_actuel)).strip()
    if not reste or not reste[0].isalpha():
        return None
    return reste.split()[0]


def nom_du_parent(con_id, infos):
    """Remonte la chaine des parents pour trouver un vrai nom de famille.

    « Mariam » (seul prénom, pas de nom) ne peut pas servir de nom de famille :
    on cherche alors un nom exploitable chez ses propres ancetres, puis on
    revient sur le prénom de l'enfant (« / APPIA SEWA » -> APPIA).
    """
    vus = set()
    courant = infos.get(con_id)
    while courant is not None and courant["id"] not in vus:
        vus.add(courant["id"])
        n = RE_PARASITE_TETE.sub("", (courant["nom"] or "")).strip()
        if nom_exploitable(n):
            return n
        # le parent n'a pas de nom : cherche dans son prénom, puis chez ses parents
        n2 = nom_depuis_prenom(courant["prenom"])
        if n2:
            return n2
        courant = infos.get(courant["parent_id"])
    return None


def etudier(con):
    """Renvoie la liste des corrections {id, avant_nom, apres_nom, source}."""
    con.row_factory = sqlite3.Row
    lignes = con.execute("""
        SELECT m.id, m.nom, m.prenom, m.parent_id, m.famille_id, m.ordre_fratrie
        FROM membres m
        ORDER BY m.famille_id, IFNULL(m.ordre_fratrie, 9999), m.id
    """).fetchall()
    infos = {r["id"]: r for r in lignes}

    corrections = []
    dernier_nom_famille = {}     # famille_id -> dernier nom exploitable vu

    for r in lignes:
        nouveau = None
        source = None
        if nom_est_parasite(r["nom"]):
            # 1) le prénom contient « NOM Prénoms » : le plus fiable, car
            #    c'est le nom que la personne porte elle-même
            n = nom_depuis_prenom(r["prenom"])
            if n:
                nouveau, source = n, "prénom de la personne"
            # 2) le nom actuel contient des mots apres le separateur
            #    (« /APPIA » -> APPIA)
            if nouveau is None:
                n = nom_apres_separateur(r["nom"])
                if n:
                    nouveau, source = n, "nom après le séparateur"
            # 3) sinon, nom de famille trouve chez le parent ou plus haut
            if nouveau is None and r["parent_id"] is not None:
                n = nom_du_parent(r["parent_id"], infos)
                if n:
                    nouveau, source = n, "nom du parent"
            # 4) dernier nom exploitable de la famille
            if nouveau is None:
                n = dernier_nom_famille.get(r["famille_id"])
                if n:
                    nouveau, source = n, "membre précédent de la famille"

        if nouveau and nouveau != (r["nom"] or "").strip():
            corrections.append({
                "id": r["id"],
                "avant_nom": r["nom"],
                "avant_prenom": r["prenom"],
                "apres_nom": nouveau,
                "source": source,
            })

        if nom_exploitable(r["nom"]):
            dernier_nom_famille[r["famille_id"]] = (
                RE_PARASITE_TETE.sub("", r["nom"]).strip())

    return corrections


def afficher(corrections):
    if not corrections:
        print("Aucun nom à corriger : rien à faire.")
        return
    print(f"{len(corrections)} membre(s) à corriger :\n")
    entete = f"{'id':>5}  {'nom actuel':<18} {'prénom actuel':<22} -> {'nom corrigé':<18} source"
    print(entete)
    print("-" * len(entete))
    for c in corrections:
        avant = repr(c["avant_nom"]) if c["avant_nom"] is not None else "(vide)"
        print(f"{c['id']:>5}  {avant:<18} {(c['avant_prenom'] or ''):<22} -> "
              f"{c['apres_nom']:<18} {c['source']}")


def appliquer(con, corrections, sauvegarder=True):
    """Écrit les corrections. Renvoie le chemin de la sauvegarde (ou None)."""
    if not corrections:
        return None
    chemin_sauv = None
    if sauvegarder:
        DOSSIER_SAUVEGARDES.mkdir(exist_ok=True)
        horo = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        chemin_sauv = DOSSIER_SAUVEGARDES / f"avant_correction_noms_{horo}.db"
        dest = sqlite3.connect(chemin_sauv)
        try:
            con.commit()
            con.backup(dest)
        finally:
            dest.close()

    avant_n = con.execute("SELECT COUNT(*) FROM membres").fetchone()[0]
    with con:
        for c in corrections:
            note = f"[nom d'origine: {c['avant_nom']!r}]"
            con.execute(
                "UPDATE membres SET nom = ?, notes = "
                "CASE WHEN notes IS NULL OR TRIM(notes) = '' THEN ? "
                "     ELSE notes || ' ' || ? END WHERE id = ?",
                (c["apres_nom"], note, note, c["id"]))
    apres_n = con.execute("SELECT COUNT(*) FROM membres").fetchone()[0]
    assert avant_n == apres_n, f"nombre de membres modifié : {avant_n} -> {apres_n}"
    restants = con.execute(
        "SELECT COUNT(*) FROM membres WHERE nom IS NULL OR TRIM(nom) = ''"
    ).fetchone()[0]
    print(f"\n{len(corrections)} nom(s) corrigé(s). Membres : {avant_n} -> {apres_n} "
          f"(inchangé). Noms restés vides : {restants}.")
    if chemin_sauv:
        print("Sauvegarde :", chemin_sauv)
    return chemin_sauv


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Corrige les noms parasites (/ , vide, …) hérités de l'import.")
    ap.add_argument("--base", default=str(BASE_PAR_DEFAUT),
                    help="base à examiner (défaut : cotisations.db)")
    ap.add_argument("--appliquer", action="store_true",
                    help="écrit réellement les corrections (sinon simulation)")
    ap.add_argument("--sans-sauvegarde", action="store_true",
                    help="ne pas créer de copie de sécurité avant écriture")
    args = ap.parse_args(argv)

    chemin = Path(args.base)
    if not chemin.exists():
        raise SystemExit(f"Base introuvable : {chemin}")

    con = sqlite3.connect(chemin)
    try:
        corrections = etudier(con)
        print(f"Base examinée : {chemin}")
        afficher(corrections)
        if not args.appliquer:
            if corrections:
                print("\nSIMULATION : aucune écriture. "
                      "Relancer avec --appliquer pour corriger.")
            return 0
        appliquer(con, corrections, sauvegarder=not args.sans_sauvegarde)
        return 0
    finally:
        con.close()


if __name__ == "__main__":
    sys.exit(main())
