"""
ecran_lignees.py — Étape 3 : saisie des LIGNÉES.

Une lignée appartient obligatoirement à une grande famille.

Lancement autonome : python ecran_lignees.py
"""
import tkinter as tk
from tkinter import ttk

import db
from ecran_base import EcranHierarchique


class EcranLignees(EcranHierarchique):
    NIVEAU = "lignee"
    TITRE = "Étape 3 — Les lignées"
    LABEL_PARENT = "Grande famille"
    ARTICLE_PARENT = "une grande famille"
    TEXTE_AIDE = ("Une lignée appartient à une seule grande famille.\n"
                  "Son nom doit être unique dans cette grande famille.")
    TEXTE_VIDE = ("Aucune lignée enregistrée.\n"
                  "Choisissez une grande famille parente puis « Nouveau ».")

    COLONNES = (
        ("grande_famille", "Grande famille (parent)", 190, "w"),
        ("clan", "Clan", 150, "w"),
        ("nom", "Lignée", 200, "w"),
        ("familles", "Familles", 80, "center"),
    )

    CHAMPS = (
        ("description", "Description", "text"),
    )

    def requete_liste(self):
        return ("""
            SELECT t.id, t.nom, t.description, t.grande_famille_id,
                   gf.nom AS grande_famille, c.nom AS clan,
                   (SELECT COUNT(*) FROM familles fa
                     WHERE fa.lignee_id = t.id) AS familles
            FROM lignees t
            JOIN grandes_familles gf ON gf.id = t.grande_famille_id
            JOIN clans c ON c.id = gf.clan_id
            __FILTRE__
            ORDER BY c.nom COLLATE NOCASE, gf.nom COLLATE NOCASE,
                     t.nom COLLATE NOCASE
        """, [])

    def valeurs_ligne(self, row):
        return (row["grande_famille"], row["clan"], row["nom"], row["familles"])

    def charger_champs(self, row):
        self.widgets["description"][0].delete("1.0", "end")
        self.widgets["description"][0].insert("1.0", row["description"] or "")

    def lire_champs(self):
        return {"description":
                self.widgets["description"][0].get("1.0", "end").strip() or None}


if __name__ == "__main__":
    class _Etat(ttk.Frame):
        def __init__(self, p):
            super().__init__(p, relief="sunken", padding=(8, 4))
            self.var = tk.StringVar()
            ttk.Label(self, textvariable=self.var).pack(side="left")

        def info(self, t):
            self.var.set(t)

    root = tk.Tk()
    # icone de l'application (relation.ico)
    try:
        from app import appliquer_icone
        appliquer_icone(root)
    except Exception:
        pass
    root.title("Test — Lignées")
    root.geometry("1080x660")
    con = db.initialiser()
    etat = _Etat(root)
    etat.pack(side="bottom", fill="x")
    EcranLignees(root, con, etat).pack(fill="both", expand=True)
    root.mainloop()
    con.close()
