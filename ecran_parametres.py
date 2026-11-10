"""
ecran_parametres.py — Onglet Paramètres.

Trois sections :
  1. Montant de la cotisation (par défaut et par année)
  2. Sauvegarde et restauration de la base
  3. Purge de la base (avec confirmation forte)

Lancement autonome : python ecran_parametres.py
"""
import datetime
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from pathlib import Path

import db
import parametres as P
from ui_commun import CadreDefilant


class EcranParametres(ttk.Frame):
    def __init__(self, parent, con, etat, sur_restauration=None):
        super().__init__(parent, padding=10)
        self.con = con
        self.etat = etat
        self.sur_restauration = sur_restauration   # rappel pour rafraîchir
        self._construire()
        self.recharger()

    # ================================================================
    #  Interface
    # ================================================================
    def _construire(self):
        entete = ttk.Frame(self)
        entete.pack(fill="x", pady=(0, 8))
        ttk.Label(entete, text="Paramètres", font=("Segoe UI", 16, "bold"),
                  foreground="#1f4e5f").pack(side="left")
        self.lbl_etat_base = ttk.Label(entete, text="", foreground="#55606a")
        self.lbl_etat_base.pack(side="right")

        defilant = CadreDefilant(self)
        defilant.pack(fill="both", expand=True)
        f = defilant.contenu
        f.columnconfigure(0, weight=1)

        # ---------- 1. montant de la cotisation --------------------
        b1 = ttk.LabelFrame(f, text=" 1. Montant de la cotisation ",
                            padding=10)
        b1.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        b1.columnconfigure(1, weight=1)

        ttk.Label(b1, text="Montant mensuel par membre :").grid(
            row=0, column=0, sticky="w")
        cadre_m = ttk.Frame(b1)
        cadre_m.grid(row=0, column=1, sticky="w", padx=(8, 0))
        self.var_montant = tk.StringVar()
        self.ent_montant = ttk.Entry(cadre_m, textvariable=self.var_montant,
                                    width=12)
        self.ent_montant.pack(side="left")
        ttk.Label(cadre_m, text="FCFA").pack(side="left", padx=(6, 0))

        ttk.Label(b1, text="Année concernée :").grid(row=1, column=0,
                                                    sticky="w", pady=(8, 0))
        cadre_a = ttk.Frame(b1)
        cadre_a.grid(row=1, column=1, sticky="w", padx=(8, 0), pady=(8, 0))
        self.var_annee = tk.StringVar(value="Toutes les années")
        # "normal" : liste proposée ET saisie libre d'une année (2024, 2028…)
        self.cmb_annee = ttk.Combobox(cadre_a, textvariable=self.var_annee,
                                      state="normal", width=18)
        self.cmb_annee.pack(side="left")
        ttk.Button(cadre_a, text="Appliquer",
                   command=self.appliquer_montant).pack(side="left", padx=(8, 0))

        ttk.Label(cadre_a, text="(ou tapez une année : 2024, 2028…)",
                  foreground="#8a8a8a").pack(side="left", padx=(10, 0))

        self.var_appliquer_tout = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            b1, text="Appliquer aussi aux campagnes déjà créées",
            variable=self.var_appliquer_tout).grid(
            row=2, column=1, sticky="w", padx=(8, 0), pady=(6, 0))

        self.lbl_montant_info = ttk.Label(b1, text="", foreground="#55606a",
                                          wraplength=560, justify="left")
        self.lbl_montant_info.grid(row=3, column=0, columnspan=2, sticky="w",
                                   pady=(8, 0))

        ttk.Label(b1, text="Exercices ouverts :").grid(
            row=4, column=0, columnspan=2, sticky="w", pady=(10, 4))
        self.tab_campagnes = ttk.Treeview(
            b1, columns=("libelle", "annee", "periode", "montant", "mois"),
            show="headings", height=4)
        for cle, lib, larg, anc in (("libelle", "Exercice", 190, "w"),
                                    ("annee", "Rattachement", 95, "center"),
                                    ("periode", "Période", 200, "w"),
                                    ("montant", "Montant / mois", 110, "e"),
                                    ("mois", "Mois saisis", 85, "center")):
            self.tab_campagnes.heading(cle, text=lib)
            self.tab_campagnes.column(cle, width=larg, anchor=anc)
        self.tab_campagnes.grid(row=5, column=0, columnspan=2, sticky="ew")

        # ---- ouverture d'un exercice libre ----
        b1b = ttk.LabelFrame(f, text=" Ouvrir un exercice ", padding=10)
        b1b.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        for i in (1, 3, 5):
            b1b.columnconfigure(i, weight=1)

        ttk.Label(b1b, text="Libellé :").grid(row=0, column=0, sticky="w")
        self.var_ex_libelle = tk.StringVar()
        ttk.Entry(b1b, textvariable=self.var_ex_libelle).grid(
            row=0, column=1, columnspan=3, sticky="ew", padx=(6, 0))

        ttk.Label(b1b, text="Début :").grid(row=1, column=0, sticky="w",
                                            pady=(6, 0))
        self.var_ex_debut = tk.StringVar(
            value=datetime.date.today().replace(month=1, day=1).strftime("%d/%m/%Y"))
        e1 = ttk.Entry(b1b, textvariable=self.var_ex_debut, width=14)
        e1.grid(row=1, column=1, sticky="w", padx=(6, 0), pady=(6, 0))
        ttk.Label(b1b, text="Fin :").grid(row=1, column=2, sticky="e",
                                          pady=(6, 0))
        self.var_ex_fin = tk.StringVar(
            value=datetime.date.today().replace(month=12, day=31).strftime("%d/%m/%Y"))
        e2 = ttk.Entry(b1b, textvariable=self.var_ex_fin, width=14)
        e2.grid(row=1, column=3, sticky="w", padx=(6, 0), pady=(6, 0))

        ttk.Label(b1b, text="Montant :").grid(row=1, column=4, sticky="e",
                                              pady=(6, 0))
        self.var_ex_montant = tk.StringVar()
        ttk.Entry(b1b, textvariable=self.var_ex_montant, width=10).grid(
            row=1, column=5, sticky="w", padx=(6, 0), pady=(6, 0))
        ttk.Label(b1b, text="FCFA").grid(row=1, column=6, sticky="w",
                                         padx=(4, 0), pady=(6, 0))

        barre_ex = ttk.Frame(b1b)
        barre_ex.grid(row=2, column=0, columnspan=7, sticky="w", pady=(8, 0))
        ttk.Button(barre_ex, text="Ouvrir / mettre à jour", width=24,
                   command=self.ouvrir_exercice).pack(side="left")
        ttk.Button(barre_ex, text="Année civile", width=14,
                   command=self.exercice_annee_civile).pack(side="left",
                                                              padx=(8, 0))
        ttk.Button(barre_ex, text="Supprimer l'exercice sélectionné",
                   width=32,
                   command=self.supprimer_exercice).pack(side="left",
                                                          padx=(8, 0))
        ttk.Label(b1b, text="Aucune limite d'année : la période est libre "
                            "(ex. 01/07/2025 → 30/06/2026). Le rattachement "
                            "se fait sur l'année de début.",
                  foreground="#8a8a8a", wraplength=620,
                  justify="left").grid(row=3, column=0, columnspan=7,
                                       sticky="w", pady=(8, 0))

        # ---------- 2. sauvegarde --------------------------------
        b2 = ttk.LabelFrame(f, text=" 2. Sauvegarde de la base ", padding=10)
        b2.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        b2.columnconfigure(0, weight=1)

        info = ("Une sauvegarde automatique est faite à chaque fermeture de "
                "l'application. Seules les deux dernières sont conservées : "
                "celle du jour (n) et celle de la veille (n-1).")
        ttk.Label(b2, text=info, wraplength=620, justify="left",
                  foreground="#55606a").grid(row=0, column=0, sticky="w")

        self.tab_sauvegardes = ttk.Treeview(
            b2, columns=("date", "taille", "fichier"), show="headings",
            height=3)
        for cle, lib, larg, anc in (("date", "Date", 110, "center"),
                                    ("taille", "Taille", 100, "e"),
                                    ("fichier", "Fichier", 260, "w")):
            self.tab_sauvegardes.heading(cle, text=lib)
            self.tab_sauvegardes.column(cle, width=larg, anchor=anc)
        self.tab_sauvegardes.grid(row=1, column=0, sticky="ew", pady=(8, 6))

        barre = ttk.Frame(b2)
        barre.grid(row=2, column=0, sticky="w")
        ttk.Button(barre, text="Sauvegarder maintenant", width=24,
                   command=self.sauvegarder_maintenant).pack(side="left")
        ttk.Button(barre, text="Enregistrer une copie…", width=22,
                   command=self.copier_ailleurs).pack(side="left", padx=(8, 0))
        ttk.Button(barre, text="Restaurer…", width=14,
                   command=self.restaurer).pack(side="left", padx=(8, 0))
        ttk.Button(barre, text="Importer une base…", width=20,
                   command=self.importer).pack(side="left", padx=(8, 0))
        ttk.Button(barre, text="Ouvrir le dossier", width=17,
                   command=self.ouvrir_dossier).pack(side="left", padx=(8, 0))

        # ---------- 3. purge -------------------------------------
        b3 = ttk.LabelFrame(f, text=" 3. Purge de la base ", padding=10)
        b3.grid(row=3, column=0, sticky="ew")
        b3.columnconfigure(0, weight=1)
        ttk.Label(b3, text="Opération irréversible : une sauvegarde est faite "
                           "automatiquement avant toute purge.",
                  foreground="#8a4b00", wraplength=620,
                  justify="left").grid(row=0, column=0, sticky="w")

        barre3 = ttk.Frame(b3)
        barre3.grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Button(barre3, text="Vider la hiérarchie et les membres",
                   width=34,
                   command=lambda: self.purger("hierarchie")).pack(side="left")
        ttk.Button(barre3, text="Tout vider (sauf réglages)", width=28,
                   command=lambda: self.purger("donnees")).pack(
            side="left", padx=(8, 0))
        ttk.Button(barre3, text="Réinitialisation totale",
                   style="Danger.TButton", width=24,
                   command=lambda: self.purger("tout")).pack(side="left",
                                                             padx=(8, 0))

    # ================================================================
    #  Rechargement
    # ================================================================
    def recharger(self):
        montant = P.montant_par_defaut(self.con)
        affiche = int(montant) if montant == int(montant) else montant
        self.var_montant.set(str(affiche))

        annees = [str(a) for a in P.annees_pour_montant(self.con)]
        # on garde l'année déjà saisie si elle sort de la liste
        courante = self.var_annee.get().strip()
        valeurs = annees[:]
        if courante and courante != "Toutes les années" and courante not in valeurs:
            if P.annee_montant_valide(courante):
                valeurs.append(courante)
        # tri numérique sûr (la liste ne contient que des années)
        valeurs = sorted({v for v in valeurs if P.annee_montant_valide(v)},
                         key=int, reverse=True)
        self.cmb_annee["values"] = ["Toutes les années"] + valeurs
        if courante not in valeurs:
            self.var_annee.set("Toutes les années")

        self.tab_campagnes.delete(*self.tab_campagnes.get_children())
        for c in P.lister_exercices(self.con):
            m = c["montant_mensuel"]
            self.tab_campagnes.insert(
                "", "end", iid=str(c["annee"]),
                values=(c["libelle"], c["annee"],
                        P.periode_lisible(c["date_debut"], c["date_fin"]),
                        f"{int(m) if m == int(m) else m} FCFA",
                        c["nb_mois"]))
        if not self.tab_campagnes.get_children():
            self.lbl_montant_info.config(
                text="Aucune campagne enregistrée : le montant ci-dessus sera "
                     "appliqué à la première cotisation de chaque année.")
        else:
            self.lbl_montant_info.config(
                text="Le montant en vigueur est utilisé pour chaque nouvelle "
                     "année. Une année déjà cotisée garde son montant, sauf si "
                     "vous cochez « Appliquer aussi aux campagnes déjà "
                     "créées ».")

        self.tab_sauvegardes.delete(*self.tab_sauvegardes.get_children())
        for s in P.lister_sauvegardes():
            ko = s["taille"] / 1024
            self.tab_sauvegardes.insert(
                "", "end", iid=str(s["chemin"]),
                values=(s["date"].strftime("%d/%m/%Y"),
                        f"{ko:.0f} Ko", s["chemin"].name))

        e = P.etat_base(self.con)
        self.lbl_etat_base.config(
            text=f"{e['membres']} membre(s) · {e['familles']} famille(s) · "
                 f"{int(e['total_cotise']):,} FCFA cotisés · "
                 f"{e['taille']/1024:.0f} Ko".replace(",", " "))

    # ================================================================
    #  Montant
    # ================================================================
    def appliquer_montant(self):
        texte = self.var_montant.get().strip().replace(" ", "").replace(",", ".")
        choix = self.var_annee.get().strip()
        if choix in ("", "Toutes les années"):
            annee = None
        else:
            if not P.annee_montant_valide(choix):
                messagebox.showerror(
                    "Année invalide",
                    "Saisissez une année entre 2000 et 2100, ou choisissez "
                    "« Toutes les années ».")
                return
            annee = int(choix)
        try:
            P.definir_montant(self.con, texte, annee=annee,
                              appliquer_existantes=self.var_appliquer_tout.get())
        except db.ErreurSaisie as e:
            messagebox.showerror("Montant refusé", str(e))
            return
        where = "toutes les années" if annee is None else f"l'année {annee}"
        self.etat.info(f"Montant de cotisation enregistré pour {where}.")
        messagebox.showinfo(
            "Montant enregistré",
            f"La cotisation mensuelle est désormais de "
            f"{self.var_montant.get().strip()} FCFA pour {where}.\n\n"
            f"Les cotisations déjà enregistrées ne sont pas recalculées.")
        self.recharger()

    # ================================================================
    #  Exercices
    # ================================================================
    @staticmethod
    def _iso(texte):
        """« 01/07/2025 » ou « 2025-07-01 » -> « 2025-07-01 » (ou None)."""
        for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
            try:
                return datetime.datetime.strptime(texte.strip(), fmt).strftime(
                    "%Y-%m-%d")
            except ValueError:
                continue
        return None

    def ouvrir_exercice(self):
        debut = self._iso(self.var_ex_debut.get())
        fin = self._iso(self.var_ex_fin.get())
        if debut is None or fin is None:
            messagebox.showerror(
                "Dates invalides",
                "Saisissez les dates au format JJ/MM/AAAA "
                "(ex. 01/07/2025).")
            return
        try:
            action = P.ouvrir_exercice(
                self.con, self.var_ex_libelle.get(), debut, fin,
                self.var_ex_montant.get().strip()
                or self.var_montant.get().strip())
        except db.ErreurSaisie as e:
            # un exercice existe déjà pour cette année : proposer le
            # remplacement explicite plutôt que d'écraser en silence
            message = str(e)
            if "existe déjà" in message and messagebox.askyesno(
                    "Exercice déjà existant",
                    f"{message}\n\nRemplacer cet exercice ?",
                    icon="warning"):
                try:
                    action = P.ouvrir_exercice(
                        self.con, self.var_ex_libelle.get(), debut, fin,
                        self.var_ex_montant.get().strip()
                        or self.var_montant.get().strip(),
                        remplacer=True)
                except db.ErreurSaisie as e2:
                    messagebox.showerror("Exercice refusé", str(e2))
                    return
            else:
                messagebox.showerror("Exercice refusé", message)
                return
        self.etat.info(f"Exercice {action} : {debut} → {fin}")
        messagebox.showinfo(
            "Exercice enregistré",
            f"L'exercice « {self.var_ex_libelle.get().strip() or 'sans nom'} » "
            f"a été {action}.\n\n"
            f"Période : {debut} → {fin}\n\n"
            f"Il est désormais proposé dans l'onglet Cotisations.")
        self.recharger()

    def exercice_annee_civile(self):
        """Pré-remplit le formulaire pour l'année civile en cours."""
        a = datetime.date.today().year
        self.var_ex_libelle.set(f"Exercice {a}")
        self.var_ex_debut.set(f"01/01/{a}")
        self.var_ex_fin.set(f"31/12/{a}")
        self.var_ex_montant.set(self.var_montant.get())

    def supprimer_exercice(self):
        sel = self.tab_campagnes.selection()
        if not sel:
            messagebox.showinfo("Aucune sélection",
                                "Sélectionnez un exercice dans la liste.")
            return
        annee = int(sel[0])
        if not messagebox.askyesno(
                "Supprimer l'exercice",
                f"Supprimer l'exercice rattaché à {annee} ?\n\n"
                "Possible seulement s'il ne contient aucune cotisation.",
                icon="warning"):
            return
        try:
            P.supprimer_exercice(self.con, annee)
        except db.ErreurSaisie as e:
            messagebox.showerror("Suppression refusée", str(e))
            return
        self.etat.info(f"Exercice {annee} supprimé.")
        self.recharger()

    # ================================================================
    #  Sauvegarde
    # ================================================================
    def sauvegarder_maintenant(self):
        try:
            chemin = P.sauvegarder(self.con)
        except Exception as e:
            messagebox.showerror("Sauvegarde impossible", str(e))
            return
        self.etat.info(f"Sauvegarde enregistrée : {chemin.name}")
        messagebox.showinfo("Sauvegarde faite",
                            f"Base sauvegardée dans :\n{chemin}\n\n"
                            f"Les deux sauvegardes les plus récentes sont "
                            f"conservées.")
        self.recharger()

    def copier_ailleurs(self):
        horo = datetime.datetime.now().strftime("%Y%m%d_%H%M")
        chemin = filedialog.asksaveasfilename(
            title="Enregistrer une copie de la base",
            defaultextension=".db",
            initialfile=f"fonds_entraide_{horo}.db",
            filetypes=[("Base SQLite", "*.db"), ("Tous les fichiers", "*.*")])
        if not chemin:
            return
        try:
            import sqlite3
            dest = sqlite3.connect(chemin)
            self.con.commit()
            self.con.backup(dest)
            dest.close()
        except Exception as e:
            messagebox.showerror("Copie impossible", str(e))
            return
        self.etat.info(f"Copie enregistrée : {Path(chemin).name}")
        messagebox.showinfo("Copie enregistrée", f"Fichier :\n{chemin}")

    def restaurer(self):
        sel = self.tab_sauvegardes.selection()
        sauvegardes = {str(s["chemin"]): s for s in P.lister_sauvegardes()}
        if sel:
            chemin = sel[0]
            date_s = sauvegardes[chemin]["date"].strftime("%d/%m/%Y")
        else:
            chemin = filedialog.askopenfilename(
                title="Choisir une sauvegarde à restaurer",
                initialdir=str(P.DOSSIER_SAUVEGARDES),
                filetypes=[("Base SQLite", "*.db"), ("Tous les fichiers", "*.*")])
            if not chemin:
                return
            date_s = Path(chemin).name

        if not messagebox.askyesno(
                "Restaurer la base",
                f"Remplacer TOUTES les données actuelles par le contenu de :\n"
                f"{date_s} ?\n\nUne copie de sécurité de la base actuelle sera "
                f"faite avant.", icon="warning"):
            return
        try:
            P.restaurer(chemin, con=self.con)
        except db.ErreurSaisie as e:
            messagebox.showerror("Restauration refusée", str(e))
            return
        self.etat.info("Base restaurée.")
        messagebox.showinfo("Base restaurée",
                            "Les données ont été remplacées.\n\n"
                            "Pensez à redémarrer l'application si vous "
                            "constatez un affichage incohérent.")
        self.recharger()
        if self.sur_restauration:
            self.sur_restauration()

    def importer(self):
        chemin = filedialog.askopenfilename(
            title="Importer une base du Fonds d'Entraide",
            filetypes=[("Base SQLite", "*.db"), ("Tous les fichiers", "*.*")])
        if not chemin:
            return
        if not messagebox.askyesno(
                "Importer",
                f"Importer la base :\n{chemin}\n\n"
                f"Cette opération REMPLACE toutes les données actuelles.\n"
                f"Une copie de sécurité sera faite avant.", icon="warning"):
            return
        try:
            P.importer(chemin, con=self.con)
        except db.ErreurSaisie as e:
            messagebox.showerror("Import refusé", str(e))
            return
        self.etat.info(f"Base importée : {Path(chemin).name}")
        messagebox.showinfo("Import terminé",
                            "La base a été remplacée par le fichier importé.")
        self.recharger()
        if self.sur_restauration:
            self.sur_restauration()

    def ouvrir_dossier(self):
        P.DOSSIER_SAUVEGARDES.mkdir(parents=True, exist_ok=True)
        try:
            import subprocess
            subprocess.Popen(["explorer", str(P.DOSSIER_SAUVEGARDES)])
        except Exception as e:
            messagebox.showerror("Ouverture impossible", str(e))

    # ================================================================
    #  Purge
    # ================================================================
    def purger(self, niveau):
        textes = {
            "hierarchie": ("Vider la hiérarchie et les membres",
                           "Tous les clans, grandes familles, lignées, "
                           "familles, membres, cotisations et versements "
                           "seront effacés. Les réglages sont conservés."),
            "donnees": ("Tout vider (sauf réglages)",
                        "Toutes les données — hiérarchie, membres et "
                        "cotisations — seront effacées. Les réglages "
                        "(montant de cotisation) sont conservés."),
            "tout": ("Réinitialisation totale",
                     "ABSOLUMENT TOUT sera effacé, y compris les réglages "
                     "(montant de la cotisation)."),
        }
        titre, detail = textes[niveau]
        e = P.etat_base(self.con)
        if not messagebox.askyesno(
                titre,
                f"{detail}\n\nCette action est IRRÉVERSIBLE.\n\n"
                f"Contenu actuel : {e['clans']} clan(s), {e['familles']} "
                f"famille(s), {e['membres']} membre(s), {e['paiements']} "
                f"versement(s).\n\nContinuer ?", icon="warning"):
            return

        # double confirmation pour la réinitialisation totale
        if niveau == "tout":
            reponse = messagebox.askstring(
                "Confirmation",
                "Pour confirmer la réinitialisation totale, tapez EFFACER :")
            if (reponse or "").strip().upper() != "EFFACER":
                messagebox.showinfo("Annulé", "La purge a été annulée.")
                return

        try:
            P.sauvegarder(self.con)          # filet de sécurité
        except Exception:
            if not messagebox.askyesno(
                    "Sauvegarde impossible",
                    "La sauvegarde de sécurité a échoué. Poursuivre la purge "
                    "malgré tout ?", icon="warning"):
                return
        try:
            compte = P.purger(self.con, niveau)
        except db.ErreurSaisie as e:
            messagebox.showerror("Purge impossible", str(e))
            return

        total = sum(compte.values())
        self.etat.info(f"Purge effectuée : {total} ligne(s) supprimée(s).")
        messagebox.showinfo("Purge terminée",
                            f"{total} ligne(s) supprimée(s).\n\n"
                            f"Une sauvegarde a été faite avant la purge.")
        self.recharger()
        if self.sur_restauration:
            self.sur_restauration()


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
    root.title("Test — Paramètres")
    root.geometry("1060x800")
    con = db.initialiser()
    etat = _Etat(root)
    etat.pack(side="bottom", fill="x")
    EcranParametres(root, con, etat).pack(fill="both", expand=True)
    root.mainloop()
    con.close()
