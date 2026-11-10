"""
apercu_tableau_bord.py — Lancer le tableau de bord SEUL, sur une base choisie.

Sert à vérifier l'onglet 7 et ses exports (CSV / PDF / impression) sur des
données réelles sans passer par les 8 onglets de `app.py`.

Utilisation :

    python apercu_tableau_bord.py
        -> ouvre cotisations.db (la base de référence : 599 membres)

    python apercu_tableau_bord.py familles.db
        -> ouvre la base de saisie

    python apercu_tableau_bord.py --liste
        -> affiche les bases .db du dossier

La base passée en argument est ouverte en LECTURE SEULE : aucune écriture,
aucune modification de schéma. Les exports écrivent leurs fichiers ailleurs
(dossier choisi dans la boîte de dialogue, ou dossier temporaire pour
l'impression), jamais dans la base.
"""
import sys
from pathlib import Path

import tkinter as tk
from tkinter import ttk

import db
import ecran_tableau_bord as E


class BarreEtat(ttk.Frame):
    """Petite barre d'état, comme celle de l'application complète."""

    def __init__(self, parent):
        super().__init__(parent, relief="sunken", padding=(8, 4))
        self.var = tk.StringVar(value="Prêt.")
        ttk.Label(self, textvariable=self.var).pack(side="left")

    def info(self, texte):
        self.var.set(texte)


def bases_disponibles():
    dossier = Path(__file__).parent
    return sorted(p.name for p in dossier.glob("*.db"))


def ouvrir_lecture_seule(chemin):
    """Connexion en lecture seule — le tableau de bord ne modifie rien."""
    fichier = Path(chemin)
    if not fichier.exists():
        raise SystemExit(f"Base introuvable : {fichier}")
    try:
        con = db.connecter_lecture_seule(fichier)
    except AttributeError:
        # db.py sans le mode lecture seule : connexion normale en repli.
        con = db.connecter(str(fichier))
    return con


def main(argv):
    if "--liste" in argv:
        print("Bases .db du dossier :")
        for nom in bases_disponibles():
            print("  -", nom)
        return 0

    choix = [a for a in argv if not a.startswith("-")]
    base = choix[0] if choix else "cotisations.db"
    fichier = Path(base)
    if not fichier.is_absolute():
        fichier = Path(__file__).parent / fichier

    con = ouvrir_lecture_seule(fichier)

    root = tk.Tk()
    # icone de l'application (relation.ico)
    try:
        from app import appliquer_icone
        appliquer_icone(root)
    except Exception:
        pass
    root.title("Aperçu — Tableau de bord (lecture seule) · %s" % fichier.name)
    root.geometry("1250x780")

    barre = BarreEtat(root)
    barre.pack(side="bottom", fill="x")

    ecran = E.EcranTableauBord(root, con, barre)
    ecran.pack(fill="both", expand=True)

    nb = con.execute("SELECT COUNT(*) FROM membres").fetchone()[0]
    barre.info("%s · %d membre(s) · base ouverte en lecture seule"
               % (fichier.name, nb))

    root.mainloop()
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
