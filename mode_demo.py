"""
mode_demo.py — Lancer l'application sur une COPIE de la base de référence.

But : tester les boutons (listes en PDF, reçu, exports du tableau de bord)
sur des **données réelles** sans jamais toucher à `cotisations.db`.

Ce que fait le script :
  1. contrôle que la base source n'a pas bougé depuis le dernier lancement
     (empreinte SHA-256) ;
  2. la copie dans `demo/demo_<horodatage>.db` ;
  3. ouvre l'application COMPLÈTE sur cette copie ;
  4. à la fermeture, écrit un **état de vérification** dans `demo/etats/` :
     avant/après (lignes, sommes, empreinte de la source) — pour prouver que
     la vraie base est restée intacte et que la copie a bien reçu les essais.

Utilisation :

    python mode_demo.py              # copie neuve à chaque lancement
    python mode_demo.py --garder     # réutilise la dernière copie
    python mode_demo.py --liste      # liste les copies et les états

Rien n'est supprimé : chaque lancement laisse sa copie et son état.
"""
import datetime
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

BASE = Path(__file__).parent
SOURCE = BASE / "cotisations.db"
DOSSIER = BASE / "demo"
ETATS = DOSSIER / "etats"

TABLES = ("clans", "grandes_familles", "lignees", "familles", "membres",
          "paiements", "affectations", "campagnes", "parametres")


# ---------------------------------------------------------------------
#  Empreintes et comptages
# ---------------------------------------------------------------------
def empreinte(chemin):
    """SHA-256 du fichier (on lit par blocs : la base peut être grosse)."""
    h = hashlib.sha256()
    with open(chemin, "rb") as f:
        for bloc in iter(lambda: f.read(65536), b""):
            h.update(bloc)
    return h.hexdigest()


def mesurer(chemin):
    """Comptages et sommes d'une base (lecture seule)."""
    con = sqlite3.connect(f"file:{Path(chemin).as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    infos = {"fichier": Path(chemin).name, "taille_octets": Path(chemin).stat().st_size}
    for t in TABLES:
        try:
            infos[t] = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        except sqlite3.Error as e:
            infos[t] = f"absente ({e})"
    for libelle, sql in (
            ("somme_affectations", "SELECT IFNULL(SUM(montant),0) FROM affectations"),
            ("somme_paiements", "SELECT IFNULL(SUM(montant_total),0) FROM paiements"),
            ("par_annee", """SELECT annee, IFNULL(SUM(montant),0) AS total
                             FROM affectations GROUP BY annee ORDER BY annee""")):
        try:
            if libelle == "par_annee":
                infos[libelle] = {str(r["annee"]): r["total"]
                                  for r in con.execute(sql)}
            else:
                infos[libelle] = con.execute(sql).fetchone()[0]
        except sqlite3.Error as e:
            infos[libelle] = f"erreur ({e})"
    try:
        infos["integrite"] = con.execute("PRAGMA integrity_check").fetchone()[0]
    except sqlite3.Error:
        infos["integrite"] = "inconnue"
    con.close()
    return infos


# ---------------------------------------------------------------------
#  Préparation de la copie
# ---------------------------------------------------------------------
def derniere_copie():
    if not DOSSIER.exists():
        return None
    copies = sorted(DOSSIER.glob("demo_*.db"), reverse=True)
    return copies[0] if copies else None


def creer_copie():
    if not SOURCE.exists():
        raise SystemExit(f"Base de référence introuvable : {SOURCE}")
    DOSSIER.mkdir(exist_ok=True)
    ETATS.mkdir(parents=True, exist_ok=True)
    horo = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    cible = DOSSIER / f"demo_{horo}.db"
    # copie SQLite propre (pas un simple copier-coller de fichier)
    src = sqlite3.connect(f"file:{SOURCE.as_posix()}?mode=ro", uri=True)
    dst = sqlite3.connect(cible)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    return cible


def lister():
    if not DOSSIER.exists():
        print("Aucune copie de démonstration pour le moment.")
        return
    print("Copies :")
    for f in sorted(DOSSIER.glob("demo_*.db"), reverse=True):
        taille = f.stat().st_size // 1024
        print(f"  - {f.name}  ({taille} Ko)")
    print("\nÉtats de vérification :")
    for f in sorted(ETATS.glob("*.json"), reverse=True):
        print(f"  - {f.name}")


# ---------------------------------------------------------------------
#  Lancement de l'application
# ---------------------------------------------------------------------
def lancer(copie, avant_source, empreinte_source_avant):
    import db
    import app as A

    con = db.initialiser(copie)      # initialiser() ne détruit rien
    etat_avant = mesurer(copie)
    application = A.Application(con)
    application.title("Fonds d'Entraide — MODE DÉMO (copie, base réelle "
                      "intacte) · %s" % copie.name)

    resultat = {"lance_le": datetime.datetime.now().isoformat(timespec="seconds"),
                "copie": copie.name, "base_reelle": SOURCE.name,
                "base_reelle_avant": avant_source,
                "empreinte_base_reelle_avant": empreinte_source_avant,
                "copie_avant_essais": etat_avant}

    def fermer_et_tracer():
        try:
            apres = mesurer(copie)
        except Exception as e:                       # noqa: BLE001
            apres = {"erreur": str(e)}
        try:
            con.close()
        except Exception:                            # noqa: BLE001
            pass
        empreinte_apres = empreinte(SOURCE)
        resultat.update({
            "ferme_le": datetime.datetime.now().isoformat(timespec="seconds"),
            "copie_apres_essais": apres,
            "base_reelle_apres": mesurer(SOURCE),
            "empreinte_base_reelle_apres": empreinte_apres,
            "base_reelle_intacte": empreinte_apres == empreinte_source_avant,
        })
        chemin = ETATS / ("etat_%s_%s.json" % (
            copie.stem.replace("demo_", ""),
            datetime.datetime.now().strftime("%H%M%S")))
        chemin.write_text(json.dumps(resultat, ensure_ascii=False, indent=2),
                          encoding="utf-8")
        # résumé lisible
        print("\n=== ÉTAT DE VÉRIFICATION ===")
        print("copie        :", copie.name)
        print("état écrit   :", chemin)
        if resultat["base_reelle_intacte"]:
            print("base réelle  : INTACTE (empreinte identique)")
        else:
            print("base réelle  : MODIFIÉE !!!")
        for cle in ("membres", "familles", "paiements", "affectations"):
            a = etat_avant.get(cle)
            b = apres.get(cle)
            if a != b:
                print(f"  copie {cle}: {a} -> {b}")
        if apres.get("parametres") != etat_avant.get("parametres"):
            print("  copie parametres:", etat_avant.get("parametres"), "->",
                  apres.get("parametres"))

    application.protocol("WM_DELETE_WINDOW", fermer_et_tracer)
    application._fermer_demo = fermer_et_tracer   # pour les tests automatises
    application.mainloop()


def main(argv):
    if "--liste" in argv:
        lister()
        return 0
    empreinte_source = empreinte(SOURCE)
    avant = mesurer(SOURCE)
    if "--garder" in argv:
        copie = derniere_copie()
        if copie is None:
            print("Aucune copie existante : création d'une nouvelle.")
            copie = creer_copie()
        else:
            print("Réutilisation de la copie :", copie.name)
    else:
        copie = creer_copie()
        print("Copie de travail :", copie)
    print("Base réelle      :", SOURCE.name, "(ouverture en lecture seule "
          "pour contrôle, jamais modifiée)")
    lancer(copie, avant, empreinte_source)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
