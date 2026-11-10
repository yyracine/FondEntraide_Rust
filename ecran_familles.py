"""
ecran_familles.py — Étape 4 : saisie des FAMILLES.

Une famille appartient obligatoirement à une lignée.

Lancement autonome : python ecran_familles.py
"""
import tkinter as tk
from tkinter import ttk

import db
from ecran_base import EcranHierarchique


class EcranFamilles(EcranHierarchique):
    NIVEAU = "famille"
    TITRE = "Étape 4 — Les familles"
    LABEL_PARENT = "Lignée"
    ARTICLE_PARENT = "une lignée"
    TEXTE_AIDE = ("Une famille appartient à une seule lignée.\n"
                  "Son nom doit être unique dans cette lignée.\n"
                  "L'ordre sert à ranger les familles dans la lignée.")
    TEXTE_VIDE = ("Aucune famille enregistrée.\n"
                  "Choisissez une lignée parente puis « Nouveau ».")

    COLONNES = (
        ("lignee", "Lignée (parent)", 180, "w"),
        ("grande_famille", "Grande famille", 165, "w"),
        ("nom", "Famille", 190, "w"),
        ("ordre", "Ordre", 60, "center"),
        ("membres", "Membres", 75, "center"),
    )

    CHAMPS = (
        ("ordre", "Ordre d'affichage (nombre)", "entry"),
        ("description", "Description", "text"),
    )

    def requete_liste(self):
        return ("""
            SELECT t.id, t.nom, t.description, t.ordre, t.lignee_id,
                   l.nom AS lignee, gf.nom AS grande_famille,
                   (SELECT COUNT(*) FROM membres m
                     WHERE m.famille_id = t.id) AS membres
            FROM familles t
            JOIN lignees l ON l.id = t.lignee_id
            JOIN grandes_familles gf ON gf.id = l.grande_famille_id
            __FILTRE__
            ORDER BY gf.nom COLLATE NOCASE, l.nom COLLATE NOCASE,
                     IFNULL(t.ordre, 9999), t.nom COLLATE NOCASE
        """, [])

    def valeurs_ligne(self, row):
        return (row["lignee"], row["grande_famille"], row["nom"],
                "" if row["ordre"] is None else row["ordre"], row["membres"])

    def charger_champs(self, row):
        ent_ordre = self.widgets["ordre"][0]
        ent_ordre.delete(0, "end")
        if row["ordre"] is not None:
            ent_ordre.insert(0, str(row["ordre"]))
        self.widgets["description"][0].delete("1.0", "end")
        self.widgets["description"][0].insert("1.0", row["description"] or "")

    def lire_champs(self):
        brut = self.widgets["ordre"][0].get().strip()
        ordre = None
        if brut:
            try:
                ordre = int(brut)
            except ValueError:
                raise db.ErreurSaisie(
                    "L'ordre d'affichage doit être un nombre entier "
                    "(ou rester vide).")
        return {
            "ordre": ordre,
            "description": self.widgets["description"][0]
                           .get("1.0", "end").strip() or None,
        }


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
    root.title("Test — Familles")
    root.geometry("1080x660")
    con = db.initialiser()
    etat = _Etat(root)
    etat.pack(side="bottom", fill="x")
    EcranFamilles(root, con, etat).pack(fill="both", expand=True)
    root.mainloop()
    con.close()
