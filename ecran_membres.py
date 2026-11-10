"""
ecran_membres.py — Étape 5 : saisie des MEMBRES.

Un membre appartient obligatoirement à une famille. Son parent généalogique
(appelé « parent » ci-dessous) est FACULTATIF mais, s'il existe, il doit
appartenir à la même famille : règle garantie par des triggers SQL et
rappelée ici par la liste déroulante, qui ne propose que les membres de la
famille choisie.

Lancement autonome : python ecran_membres.py
"""
import re
import tkinter as tk
from tkinter import ttk, messagebox

import db
from ecran_base import EcranHierarchique

STATUTS = ["actif", "inactif", "decede", "parti", "suspendu"]


class EcranMembres(EcranHierarchique):
    NIVEAU = "membre"
    TITRE = "Étape 5 — Les membres"
    LABEL_PARENT = "Famille"
    ARTICLE_PARENT = "une famille"
    TEXTE_AIDE = ("Un membre appartient à une seule famille.\n"
                  "Le parent, facultatif, doit être membre de cette même "
                  "famille (garanti par la base).")
    TEXTE_VIDE = ("Aucun membre enregistré.\n"
                  "Choisissez une famille parente puis « Nouveau ».")

    COLONNES = (
        ("famille", "Famille (parent)", 150, "w"),
        ("nom", "Nom", 140, "w"),
        ("prenom", "Prénom", 120, "w"),
        ("telephone", "Téléphone", 100, "w"),
        ("grande_famille", "Grande famille", 165, "w"),
        ("parent", "Parent", 135, "w"),
        ("statut", "Statut", 70, "center"),
    )

    CHAMPS_EN_LIGNE = True

    CHAMPS = (
        ("prenom", "Prénom", "entry"),
        ("telephone", "Téléphone", "entry"),
        ("sexe", "Sexe", "combo"),
        ("ordre_fratrie", "Fratrie (1 = aîné)", "entry"),
        ("statut", "Statut", "combo"),
        ("lien_parent", "Parent (même famille)", "combo"),
        ("notes", "Notes", "text"),
    )

    # ================================================================
    def _construire(self):
        super()._construire()
        self.widgets["notes"][0].configure(height=2)
        # marges internes reduites pour tenir sans defilement
        self.form.configure(padding=2)
        # valeurs des listes déroulantes
        self.widgets["sexe"][0]["values"] = ("—", "M", "F")
        self.widgets["statut"][0]["values"] = STATUTS
        self.widgets["statut"][0].set("actif")
        # la famille choisie détermine les parents proposés
        self.cmb_parent.bind("<<ComboboxSelected>>", self._sur_famille_choisie)
        self.ent_nom.bind("<Return>", lambda e: self.enregistrer())

    # ================================================================
    #  Parents possibles = membres de la famille sélectionnée
    # ================================================================
    def _membres_de_famille(self, famille_id, exclure=None):
        if famille_id is None:
            return []
        sql = ("SELECT id, nom, prenom FROM membres WHERE famille_id = ?")
        params = [famille_id]
        if exclure is not None:
            sql += " AND id <> ?"
            params.append(exclure)
        sql += " ORDER BY nom COLLATE NOCASE, prenom COLLATE NOCASE"
        return [(r["id"], f"{r['nom']} {r['prenom'] or ''}".strip())
                for r in self.con.execute(sql, params)]

    def _sur_famille_choisie(self, _e=None):
        """Recharge la liste des parents quand on change de famille."""
        fid = self.parent_id_par_nom(self.var_parent.get())
        exclus = self.id_selection if self.en_edition else None
        # un membre ne peut pas descendre de lui-même ni de ses descendants
        interdits = set()
        if exclus is not None:
            interdits = self._descendants(exclus) | {exclus}
        propose = [lib for i, lib in self._membres_de_famille(fid)
                   if i not in interdits]
        combo_parent = self.widgets["lien_parent"][0]
        combo_parent["values"] = ["— aucun —"] + propose
        if combo_parent.get() not in combo_parent["values"]:
            combo_parent.set("— aucun —")

    def _descendants(self, membre_id):
        """Tous les descendants d'un membre (pour interdire les cycles)."""
        vus = set()
        pile = [membre_id]
        while pile:
            courant = pile.pop()
            for (enfant,) in self.con.execute(
                    "SELECT id FROM membres WHERE parent_id = ?", (courant,)):
                if enfant not in vus:
                    vus.add(enfant)
                    pile.append(enfant)
        return vus

    # ================================================================
    #  Liste
    # ================================================================
    def requete_liste(self):
        return ("""
            SELECT t.id, t.nom, t.prenom, t.telephone, t.ordre_fratrie,
                   t.statut, t.sexe, t.notes, t.parent_id, t.famille_id,
                   f.nom AS famille, gf.nom AS grande_famille,
                   (SELECT p.nom || ' ' || IFNULL(p.prenom, '')
                      FROM membres p WHERE p.id = t.parent_id) AS parent
            FROM membres t
            JOIN familles f ON f.id = t.famille_id
            JOIN lignees l ON l.id = f.lignee_id
            JOIN grandes_familles gf ON gf.id = l.grande_famille_id
            __FILTRE__
            ORDER BY f.nom COLLATE NOCASE, t.nom COLLATE NOCASE,
                     IFNULL(t.ordre_fratrie, 9999)
        """, [])

    def valeurs_ligne(self, row):
        return (row["famille"], row["nom"], row["prenom"] or "",
                row["telephone"] or "", row["grande_famille"] or "",
                (row["parent"] or "").strip(), row["statut"])

    def charger_champs(self, row):
        w = self.widgets
        for cle in ("prenom", "telephone", "ordre_fratrie"):
            w[cle][0].delete(0, "end")
            w[cle][0].insert(0, row[cle] if row[cle] is not None else "")
        w["sexe"][0].set(row["sexe"] or "—")
        w["statut"][0].set(row["statut"] or "actif")
        w["notes"][0].delete("1.0", "end")
        w["notes"][0].insert("1.0", row["notes"] or "")

        # parents proposés : ceux de la famille du membre
        self._sur_famille_choisie()
        combo = w["lien_parent"][0]
        if row["parent_id"] is None:
            combo.set("— aucun —")
        else:
            for i, lib in self._membres_de_famille(row["famille_id"],
                                                   exclure=row["id"]):
                if i == row["parent_id"]:
                    combo.set(lib)
                    break
            else:
                combo.set(self.valeurs_ligne(row)[5] or "— aucun —")

    def lire_champs(self):
        w = self.widgets
        tel = w["telephone"][0].get().strip() or None
        if tel and not re.fullmatch(r"[0-9 +().-]{6,25}", tel):
            raise db.ErreurSaisie(
                "Le téléphone contient des caractères inattendus "
                "(chiffres, espaces, +, -, parenthèses uniquement).")

        brut = w["ordre_fratrie"][0].get().strip()
        fratrie = None
        if brut:
            try:
                fratrie = int(brut)
            except ValueError:
                raise db.ErreurSaisie(
                    "L'ordre de fratrie doit être un nombre entier "
                    "(ou rester vide).")
            if fratrie < 1:
                raise db.ErreurSaisie("L'ordre de fratrie commence à 1.")

        sexe = w["sexe"][0].get()
        parent_lib = w["lien_parent"][0].get()
        parent_id = None
        if not parent_lib.startswith("—"):
            fid = self.parent_id_par_nom(self.var_parent.get())
            for i, lib in self._membres_de_famille(fid):
                if lib == parent_lib:
                    parent_id = i
                    break

        return {
            "prenom": w["prenom"][0].get().strip() or None,
            "telephone": tel,
            "ordre_fratrie": fratrie,
            "sexe": sexe if sexe in ("M", "F") else None,
            "lien_parent_id": parent_id,
            "statut": w["statut"][0].get() or "actif",
            "notes": w["notes"][0].get("1.0", "end").strip() or None,
        }

    # ================================================================
    #  Surcharges
    # ================================================================
    def nouveau(self):
        super().nouveau()
        self.widgets["sexe"][0].set("—")
        self.widgets["statut"][0].set("actif")
        self._sur_famille_choisie()

    def _vider(self):
        super()._vider()
        for cle, (w, t) in self.widgets.items():
            if t == "combo":
                w.set("—")
        self.widgets["statut"][0].set("actif")
        self.widgets["lien_parent"][0]["values"] = ["— aucun —"]
        self.widgets["lien_parent"][0].set("— aucun —")

    def passer_en_edition(self):
        """On recale la liste des parents APRÈS être passé en édition :
        `_charger_fiche` la recalcule sans exclure les descendants, car
        `en_edition` vaut encore False à ce moment-là."""
        super().passer_en_edition()
        if self.id_selection is not None:
            courant = self.widgets["lien_parent"][0].get()
            self._sur_famille_choisie()      # exclut le membre et ses descendants
            self.widgets["lien_parent"][0].set(courant)

    def enregistrer(self):
        """Un membre déjà enregistré peut changer de famille : on prévient
        que ses liens de parenté seront rompus."""
        if self.en_edition and self.id_selection is not None:
            ancienne = self.con.execute(
                "SELECT famille_id FROM membres WHERE id = ?",
                (self.id_selection,)).fetchone()[0]
            nouvelle = self.parent_id_par_nom(self.var_parent.get())
            if ancienne != nouvelle:
                parent_id = self.lire_champs()["lien_parent_id"]
                if parent_id is None:
                    if not messagebox.askyesno(
                            "Changement de famille",
                            "Ce membre change de famille et perdra son lien "
                            "de parenté actuel (le parent doit être dans la "
                            "même famille).\n\nContinuer ?"):
                        return
                    # on détache le parent avant de déplacer
                    self.con.execute(
                        "UPDATE membres SET parent_id = NULL WHERE id = ?",
                        (self.id_selection,))
                    self.con.commit()
                    self.widgets["lien_parent"][0].set("— aucun —")
        super().enregistrer()

    def supprimer(self):
        if self.id_selection is None:
            return
        nb_enfants = self.con.execute(
            "SELECT COUNT(*) FROM membres WHERE parent_id = ?",
            (self.id_selection,)).fetchone()[0]
        nb_paiements = self.con.execute(
            "SELECT COUNT(*) FROM paiements WHERE membre_id = ?",
            (self.id_selection,)).fetchone()[0]
        if nb_enfants or nb_paiements:
            details = []
            if nb_enfants:
                details.append(f"{nb_enfants} descendant"
                               f"{'s' if nb_enfants > 1 else ''}")
            if nb_paiements:
                details.append(f"{nb_paiements} paiement"
                               f"{'s' if nb_paiements > 1 else ''}")
            messagebox.showwarning(
                "Suppression refusée",
                "Ce membre a " + " et ".join(details) + " :\n"
                "il ne peut pas être supprimé.\n\n"
                "Détachez d'abord ses descendants, ou changez son statut "
                "en « inactif » / « parti » pour conserver l'historique.")
            return
        super().supprimer()


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
    root.title("Test — Membres")
    root.geometry("1180x680")
    con = db.initialiser()
    etat = _Etat(root)
    etat.pack(side="bottom", fill="x")
    EcranMembres(root, con, etat).pack(fill="both", expand=True)
    root.mainloop()
    con.close()
