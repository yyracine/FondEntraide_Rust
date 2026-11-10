"""
ecran_tableau_bord.py — Onglet Tableau de bord.

Affiche, pour l'exercice choisi :
  - les chiffres clés (attendu, encaissé, taux, à jour, en retard)
  - une répartition par clan / grande famille / lignée / famille
  - la liste des membres en retard, avec le montant dû
  - éventuellement la grille mensuelle d'une famille

Aucune donnée n'est modifiée ici : l'écran est en lecture seule.

Lancement autonome : python ecran_tableau_bord.py
"""
import datetime
import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import cotisations as C
import db
import exports as X
import tableau_de_bord as T


def _f(n):
    """Nombre formaté : 12 000"""
    try:
        return f"{int(round(float(n))):,}".replace(",", " ")
    except (TypeError, ValueError):
        return "0"


def _pct(n):
    return f"{n:.1f} %".replace(".", ",")


class EcranTableauBord(ttk.Frame):
    def __init__(self, parent, con, etat):
        super().__init__(parent, padding=8)
        self.con = con
        self.etat = etat
        self._annee_choisie = False
        self._construire()
        self.recharger_annees()
        # le theme peut changer : on rejoue les couleurs des tags
        import theme
        g = theme.gestionnaire()
        if g is not None:
            g.observer(lambda _pal: self._habiller_tags())

    # ================================================================
    #  Interface
    # ================================================================
    def _construire(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        # ---- barre de sélection + chiffres clés ----
        haut = ttk.Frame(self)
        haut.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        haut.columnconfigure(3, weight=1)

        ttk.Label(haut, text="Tableau de bord",
                  font=("Segoe UI", 15, "bold"),
                  foreground="#1f4e5f").grid(row=0, column=0, sticky="w",
                                             padx=(0, 16))
        ttk.Label(haut, text="Exercice :").grid(row=0, column=1, sticky="e")
        self.var_annee = tk.StringVar()
        self.cmb_annee = ttk.Combobox(haut, textvariable=self.var_annee,
                                      state="readonly", width=8)
        self.cmb_annee.grid(row=0, column=2, sticky="w", padx=(6, 12))
        self.cmb_annee.bind("<<ComboboxSelected>>", self._sur_annee)

        self.lbl_exercice = ttk.Label(haut, text="", foreground="#55606a")
        self.lbl_exercice.grid(row=0, column=3, sticky="w")

        ttk.Button(haut, text="Rafraîchir", width=11,
                   command=self.recharger).grid(row=0, column=4, sticky="e")
        ttk.Button(haut, text="Exporter CSV", width=13,
                   command=self.exporter_csv).grid(row=0, column=5,
                                                   padx=(4, 0))
        ttk.Button(haut, text="Imprimer PDF", width=13,
                   command=self.imprimer_pdf).grid(row=0, column=6,
                                                   padx=(4, 0))
        ttk.Button(haut, text="PDF…", width=7,
                   command=self.exporter_pdf).grid(row=0, column=7,
                                                   padx=(4, 0))

        # ---- cartes de synthèse ----
        cartes = ttk.Frame(self)
        cartes.grid(row=1, column=0, sticky="ew", pady=(0, 6))
        for i in range(5):
            cartes.columnconfigure(i, weight=1, uniform="carte")

        self.cartes = {}
        for i, (cle, titre) in enumerate([
                ("encaisse", "Encaissé"),
                ("attendu", "Attendu"),
                ("taux", "Taux de recouvrement"),
                ("a_jour", "Membres à jour"),
                ("en_retard", "Membres en retard")]):
            f = ttk.Frame(cartes, relief="solid", borderwidth=1, padding=6)
            f.grid(row=0, column=i, sticky="ew",
                   padx=(0 if i == 0 else 4, 0))
            ttk.Label(f, text=titre, foreground="#55606a").pack(anchor="w")
            val = ttk.Label(f, text="—", font=("Segoe UI", 14, "bold"),
                            foreground="#1f4e5f")
            val.pack(anchor="w")
            self.cartes[cle] = val

        # ---- notebook de détails ----
        self.onglets = ttk.Notebook(self)
        self.onglets.grid(row=2, column=0, sticky="nsew")

        # onglet répartition
        self.page_rep = ttk.Frame(self.onglets, padding=6)
        self.onglets.add(self.page_rep, text="  Répartition  ")
        self.page_rep.columnconfigure(0, weight=1)
        self.page_rep.rowconfigure(1, weight=1)

        barre = ttk.Frame(self.page_rep)
        barre.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        ttk.Label(barre, text="Niveau :").pack(side="left")
        self.var_niveau = tk.StringVar(value="Clan")
        cmb = ttk.Combobox(barre, textvariable=self.var_niveau, width=18,
                           state="readonly",
                           values=["Clan", "Grande famille", "Lignée",
                                   "Famille"])
        cmb.pack(side="left", padx=(6, 0))
        cmb.bind("<<ComboboxSelected>>", self._sur_niveau)

        cadre = ttk.Frame(self.page_rep)
        cadre.grid(row=1, column=0, sticky="nsew")
        cadre.columnconfigure(0, weight=1)
        cadre.rowconfigure(0, weight=1)

        self.tab_rep = ttk.Treeview(
            cadre, columns=("libelle", "membres", "cotisants", "encaisse",
                            "part"),
            show="headings", selectmode="browse")
        for cle, lib, larg, anc in (
                ("libelle", "Libellé", 250, "w"),
                ("membres", "Membres", 90, "center"),
                ("cotisants", "Cotisants", 90, "center"),
                ("encaisse", "Encaissé (FCFA)", 140, "e"),
                ("part", "Part", 80, "e")):
            self.tab_rep.heading(cle, text=lib)
            self.tab_rep.column(cle, width=larg, anchor=anc)
        self.tab_rep.grid(row=0, column=0, sticky="nsew")
        sy = ttk.Scrollbar(cadre, orient="vertical", command=self.tab_rep.yview)
        sy.grid(row=0, column=1, sticky="ns")
        self.tab_rep.configure(yscrollcommand=sy.set)

        # onglet retards
        self.page_ret = ttk.Frame(self.onglets, padding=6)
        self.onglets.add(self.page_ret, text="  Membres en retard  ")
        self.page_ret.columnconfigure(0, weight=1)
        self.page_ret.rowconfigure(1, weight=1)

        self.lbl_ret = ttk.Label(self.page_ret, text="", foreground="#8a4b00")
        self.lbl_ret.grid(row=0, column=0, sticky="w", pady=(0, 4))

        cadre2 = ttk.Frame(self.page_ret)
        cadre2.grid(row=1, column=0, sticky="nsew")
        cadre2.columnconfigure(0, weight=1)
        cadre2.rowconfigure(0, weight=1)

        self.tab_ret = ttk.Treeview(
            cadre2, columns=("membre", "famille", "clan", "mois", "du"),
            show="headings", selectmode="browse")
        for cle, lib, larg, anc in (
                ("membre", "Membre", 200, "w"),
                ("famille", "Famille", 170, "w"),
                ("clan", "Clan", 170, "w"),
                ("mois", "Mois payés / échus", 130, "center"),
                ("du", "Reste dû (FCFA)", 130, "e")):
            self.tab_ret.heading(cle, text=lib)
            self.tab_ret.column(cle, width=larg, anchor=anc)
        self.tab_ret.grid(row=0, column=0, sticky="nsew")
        sy2 = ttk.Scrollbar(cadre2, orient="vertical",
                            command=self.tab_ret.yview)
        sy2.grid(row=0, column=1, sticky="ns")
        self.tab_ret.configure(yscrollcommand=sy2.set)

        # onglet grille mensuelle
        self.page_gr = ttk.Frame(self.onglets, padding=6)
        self.onglets.add(self.page_gr, text="  Grille mensuelle  ")
        self.page_gr.columnconfigure(0, weight=1)
        self.page_gr.rowconfigure(1, weight=1)

        self.lbl_gr = ttk.Label(self.page_gr, text="", foreground="#55606a")
        self.lbl_gr.grid(row=0, column=0, sticky="w", pady=(0, 4))

        cadre3 = ttk.Frame(self.page_gr)
        cadre3.grid(row=1, column=0, sticky="nsew")
        cadre3.columnconfigure(0, weight=1)
        cadre3.rowconfigure(0, weight=1)

        cols = ("membre", "famille") + tuple(C.MOIS_COURTS) + ("total",)
        self.tab_gr = ttk.Treeview(cadre3, columns=cols, show="headings")
        for cle, lib, larg, anc in (
                [("membre", "Membre", 170, "w"), ("famille", "Famille", 150, "w")]
                + [(m, m[:3], 50, "center") for m in C.MOIS_COURTS]
                + [("total", "Total", 85, "e")]):
            self.tab_gr.heading(cle, text=lib)
            self.tab_gr.column(cle, width=larg, anchor=anc,
                               stretch=(cle in ("membre", "famille")))
        self.tab_gr.grid(row=0, column=0, sticky="nsew")
        sx = ttk.Scrollbar(cadre3, orient="horizontal",
                           command=self.tab_gr.xview)
        sx.grid(row=1, column=0, sticky="ew")
        self.tab_gr.configure(xscrollcommand=sx.set)
        sy3 = ttk.Scrollbar(cadre3, orient="vertical", command=self.tab_gr.yview)
        sy3.grid(row=0, column=1, sticky="ns")
        self.tab_gr.configure(yscrollcommand=sy3.set)

        # ---- onglet : montants cotises par annee, tous les niveaux ----
        self.page_mnt = ttk.Frame(self.onglets, padding=6)
        self.onglets.add(self.page_mnt, text="  Montants par année  ")
        self.page_mnt.columnconfigure(0, weight=1)
        self.page_mnt.rowconfigure(1, weight=1)

        self.lbl_mnt = ttk.Label(
            self.page_mnt,
            text="Montant cotisé par niveau et par année.",
            foreground="#55606a")
        self.lbl_mnt.grid(row=0, column=0, sticky="w", pady=(0, 4))

        cadre4 = ttk.Frame(self.page_mnt)
        cadre4.grid(row=1, column=0, sticky="nsew")
        cadre4.columnconfigure(0, weight=1)
        cadre4.rowconfigure(0, weight=1)

        self.tab_mnt = ttk.Treeview(cadre4, show="headings", selectmode="browse")
        self.tab_mnt.grid(row=0, column=0, sticky="nsew")
        sy4 = ttk.Scrollbar(cadre4, orient="vertical",
                            command=self.tab_mnt.yview)
        sy4.grid(row=0, column=1, sticky="ns")
        self.tab_mnt.configure(yscrollcommand=sy4.set)
        sx4 = ttk.Scrollbar(cadre4, orient="horizontal",
                            command=self.tab_mnt.xview)
        sx4.grid(row=1, column=0, sticky="ew")
        self.tab_mnt.configure(xscrollcommand=sx4.set)

        # ---- onglet : montant cotise par membre, par annee ----
        self.page_mbr = ttk.Frame(self.onglets, padding=6)
        self.onglets.add(self.page_mbr, text="  Par membre / an  ")
        self.page_mbr.columnconfigure(0, weight=1)
        self.page_mbr.rowconfigure(1, weight=1)

        self.lbl_mbr = ttk.Label(self.page_mbr, text="", foreground="#55606a")
        self.lbl_mbr.grid(row=0, column=0, sticky="w", pady=(0, 4))

        cadre5 = ttk.Frame(self.page_mbr)
        cadre5.grid(row=1, column=0, sticky="nsew")
        cadre5.columnconfigure(0, weight=1)
        cadre5.rowconfigure(0, weight=1)

        self.tab_mbr = ttk.Treeview(cadre5, show="headings",
                                    selectmode="browse")
        self.tab_mbr.grid(row=0, column=0, sticky="nsew")
        sy5 = ttk.Scrollbar(cadre5, orient="vertical",
                            command=self.tab_mbr.yview)
        sy5.grid(row=0, column=1, sticky="ns")
        self.tab_mbr.configure(yscrollcommand=sy5.set)
        sx5 = ttk.Scrollbar(cadre5, orient="horizontal",
                            command=self.tab_mbr.xview)
        sx5.grid(row=1, column=0, sticky="ew")
        self.tab_mbr.configure(xscrollcommand=sx5.set)

    # ================================================================
    #  Rechargement
    # ================================================================
    def recharger_annees(self):
        annees = [str(a) for a in C.annees_disponibles(self.con)]
        self.cmb_annee["values"] = annees
        # Au premier affichage, on choisit une année parlante. Ensuite on
        # respecte le choix de l'utilisateur.
        if not self._annee_choisie:
            self.var_annee.set(self._annee_par_defaut(annees))
            self._annee_choisie = True
        elif self.var_annee.get() not in annees:
            self.var_annee.set(self._annee_par_defaut(annees))
        self.recharger()

    def _annee_par_defaut(self, annees):
        """Année sélectionnée à l'ouverture.

        On privilégie un exercice où il se passe quelque chose : d'abord
        une année ayant des cotisations, puis l'année courante, sinon la
        première de la liste. Éviter d'ouvrir sur une année future vide.
        """
        if not annees:
            return ""
        with_data = [r["annee"] for r in C.totaux_par_annee(self.con)]
        courante = datetime.date.today().year
        # 1. l'année courante si elle contient déjà des cotisations
        if courante in with_data:
            return str(courante)
        # 2. sinon la dernière année où il y a des cotisations
        if with_data:
            return str(with_data[0])
        # 3. sinon l'année courante (même vide)
        if str(courante) in annees:
            return str(courante)
        return annees[0]

    def _annee(self):
        try:
            return int(self.var_annee.get())
        except (TypeError, ValueError):
            return None

    def _sur_annee(self, _e=None):
        self._annee_choisie = True
        self.recharger()

    def _sur_niveau(self, _e=None):
        self._remplir_repartition()

    def recharger(self):
        annee = self._annee()
        if annee is None:
            return

        v = T.vue_ensemble(self.con, annee)
        libelle = C.libelle_exercice(self.con, annee)
        self.lbl_exercice.config(
            text=libelle or f"Exercice {annee} (année civile)")

        self.cartes["encaisse"].config(text=_f(v["encaisse"]) + " F")
        self.cartes["attendu"].config(text=_f(v["attendu"]) + " F")
        self.cartes["taux"].config(
            text=_pct(v["taux"]),
            foreground=("#1f7a3f" if v["taux"] >= 80
                        else "#b06b00" if v["taux"] >= 40 else "#b00020"))
        self.cartes["a_jour"].config(
            text=f"{v['a_jour']} / {v['nb_membres']}",
            foreground="#1f7a3f")
        self.cartes["en_retard"].config(
            text=str(v["en_retard"]),
            foreground="#b00020" if v["en_retard"] else "#1f7a3f")

        self._remplir_repartition()
        self._remplir_retards(annee)
        self._remplir_grille(annee)
        self._remplir_montants()
        self._remplir_membres()

        if v["echeances"] == 0:
            self.lbl_ret.config(
                text="Exercice non commencé : aucune échéance due.")
        self.etat.info(
            f"Exercice {annee} : {_f(v['encaisse'])} FCFA encaissés sur "
            f"{_f(v['attendu'])} attendus ({_pct(v['taux'])}).")

    # ================================================================
    #  Export CSV / PDF / impression
    # ================================================================
    def _sous_onglet_courant(self):
        """Clé du sous-onglet affiché (utilisée par l'export simple)."""
        try:
            i = self.onglets.index(self.onglets.select())
        except tk.TclError:
            return "repartition"
        return ("repartition", "retards", "grille", "montants",
                "membres")[i]

    def _doc_tableau(self, cle):
        """Construit le bloc exportable d'un sous-onglet."""
        arbre = {"repartition": self.tab_rep, "retards": self.tab_ret,
                 "grille": self.tab_gr, "montants": self.tab_mnt,
                 "membres": self.tab_mbr}.get(cle)
        if arbre is None:
            return None
        entetes = [arbre.heading(c)["text"] for c in arbre["columns"]]
        lignes = [list(arbre.item(i, "values"))
                  for i in arbre.get_children()]
        libelles = {"repartition": "Répartition", "retards":
                    "Membres en retard", "grille": "Grille mensuelle",
                    "montants": "Montants par niveau et par année",
                    "membres": "Montants par membre et par année"}
        return X.Bloc(libelles.get(cle, cle), entetes, lignes)

    def _doc_complet(self):
        """Document complet : chiffres clés + les 5 tableaux."""
        annee = self._annee()
        v = T.vue_ensemble(self.con, annee) if annee else {}
        doc = X.Document(
            "Tableau de bord — Fond d'Entraide",
            "%s · édité le %s" % (
                self.lbl_exercice.cget("text") or f"Exercice {annee}",
                datetime.datetime.now().strftime("%d/%m/%Y %H:%M")))
        if v:
            doc.ajouter(X.Bloc(
                "Chiffres clés", ["Indicateur", "Valeur"], [
                    ["Encaissé (FCFA)", _f(v["encaisse"])],
                    ["Attendu (FCFA)", _f(v["attendu"])],
                    ["Taux de recouvrement", _pct(v["taux"])],
                    ["Membres à jour", f"{v['a_jour']} / {v['nb_membres']}"],
                    ["Membres en retard", str(v["en_retard"])],
                    ["Membres / familles",
                     f"{v['nb_membres']} / {v['nb_familles']}"],
                    ["Versements enregistrés", str(v["nb_versements"])]]))
        for cle in ("repartition", "retards", "grille", "montants",
                    "membres"):
            b = self._doc_tableau(cle)
            if b is not None:
                doc.ajouter(b)
        return doc

    def _doc_simple(self, cle, quoi):
        """Petit document d'un seul sous-onglet, ou None si vide."""
        bloc = self._doc_tableau(cle)
        if bloc is None or not bloc.lignes:
            messagebox.showinfo(
                quoi, "Ce tableau est vide : rien à exporter.", parent=self)
            return None
        return X.Document(
            "%s — Fond d'Entraide" % bloc.titre,
            "%s · édité le %s" % (
                self.lbl_exercice.cget("text"),
                datetime.datetime.now().strftime("%d/%m/%Y %H:%M")),
            [bloc])

    def _etendue(self):
        """Demande si l'on exporte le sous-onglet ou tout le tableau.

        True = tout, False = sous-onglet courant, None = annuler.
        """
        return messagebox.askyesnocancel(
            "Étendue de l'export",
            "Exporter tout le tableau de bord ?\n\n"
            "Oui  = tous les tableaux + chiffres clés\n"
            "Non  = seulement le sous-onglet affiché\n"
            "Annuler = ne rien faire", parent=self)

    def _demander_dossier(self, quoi):
        """Choisit le dossier de destination (le nom est imposé)."""
        return filedialog.askdirectory(
            parent=self, title="Dossier où enregistrer l'export " + quoi,
            mustexist=True)

    def _nom_export(self, complet):
        """Nom imposé : exercice, portée (complet ou sous-onglet), heure."""
        annee = self._annee() or "sans_exercice"
        portee = "complet" if complet else self._sous_onglet_courant()
        return "tableau_de_bord_%s_%s_%s" % (
            annee, portee,
            datetime.datetime.now().strftime("%Y%m%d_%H%M"))

    def _chemin_export(self, complet, ext, quoi):
        dossier = self._demander_dossier(quoi)
        if not dossier:
            return ""
        return os.path.join(dossier, self._nom_export(complet) + ext)

    def exporter_csv(self):
        choix = self._etendue()
        if choix is None:
            return
        doc = self._doc_complet() if choix else self._doc_simple(
            self._sous_onglet_courant(), "Export CSV")
        if doc is None:
            return
        chemin = self._chemin_export(choix, ".csv", "CSV")
        if not chemin:
            return
        try:
            X.ecrire_csv(doc, chemin)
        except X.ErreurExport as e:
            messagebox.showerror("Export CSV", str(e), parent=self)
            return
        self._apres_export("CSV", chemin)

    def ecrire_pdf_auto(self, chemin, doc):
        """Écrit le PDF : reportlab si présent, sinon moteur interne."""
        X.ecrire_pdf(doc, chemin, "auto")

    def exporter_pdf(self):
        choix = self._etendue()
        if choix is None:
            return
        doc = self._doc_complet() if choix else self._doc_simple(
            self._sous_onglet_courant(), "Export PDF")
        if doc is None:
            return
        chemin = self._chemin_export(choix, ".pdf", "PDF")
        if not chemin:
            return
        try:
            self.ecrire_pdf_auto(chemin, doc)
        except X.ErreurExport as e:
            messagebox.showerror("Export PDF", str(e), parent=self)
            return
        self._apres_export("PDF", chemin)

    def imprimer_pdf(self):
        """Crée le PDF complet puis l'envoie à l'imprimante."""
        doc = self._doc_complet()
        chemin = X.chemin_temporaire(
            "tableau_de_bord_%s" % (self._annee() or "sans_exercice"))
        try:
            self.ecrire_pdf_auto(chemin, doc)
        except X.ErreurExport as e:
            messagebox.showerror("Impression", str(e), parent=self)
            return
        if not messagebox.askyesno(
                "Impression",
                "Envoyer le tableau de bord complet à l'imprimante ?\n\n"
                f"Document : {os.path.basename(chemin)}", parent=self):
            return
        try:
            X.imprimer(chemin)
        except X.ErreurExport as e:
            messagebox.showerror("Impression", str(e), parent=self)
            return
        self.etat.info("Impression lancée : " + os.path.basename(chemin))

    def _apres_export(self, quoi, chemin):
        self.etat.info(f"Export {quoi} : {chemin}")
        if messagebox.askyesno(
                "Export terminé",
                f"Fichier {quoi} créé :\n{chemin}\n\n"
                "Voulez-vous l'ouvrir maintenant ?", parent=self):
            try:
                os.startfile(chemin)
            except (AttributeError, OSError):
                messagebox.showinfo(
                    "Export", f"Ouvrez le fichier manuellement :\n{chemin}",
                    parent=self)

    def _remplir_repartition(self):
        annee = self._annee()
        if annee is None:
            return
        niveaux = {"Clan": "clan", "Grande famille": "grande_famille",
                   "Lignée": "lignee", "Famille": "famille"}
        lignes = T.par_niveau(self.con, annee,
                              niveaux.get(self.var_niveau.get(), "clan"))
        total = sum(r["encaisse"] for r in lignes) or 1

        self.tab_rep.delete(*self.tab_rep.get_children())
        for r in lignes:
            part = r["encaisse"] / total * 100
            self.tab_rep.insert("", "end", values=(
                r["libelle"], r["nb_membres"], r["nb_cotisants"],
                _f(r["encaisse"]), _pct(part)))

    def _remplir_retards(self, annee):
        self.tab_ret.delete(*self.tab_ret.get_children())
        retards = T.membres_en_retard(self.con, annee)
        for r in retards:
            self.tab_ret.insert("", "end", values=(
                r["membre"], r["famille"], r["clan"],
                "%d / %d" % (r["mois_payes"], r["mois_echus"]),
                _f(r["du"])))
        if retards:
            du = sum(r["du"] for r in retards)
            self.lbl_ret.config(
                text=f"{len(retards)} membre(s) en retard · "
                     f"{_f(du)} FCFA à recouvrer", foreground="#8a4b00")
        else:
            self.lbl_ret.config(
                text="Aucun membre en retard : tout le monde est à jour."
                if T.vue_ensemble(self.con, annee)["echeances"] else
                "Aucune échéance pour cet exercice.",
                foreground="#1f7a3f")

    def _remplir_grille(self, annee):
        self.tab_gr.delete(*self.tab_gr.get_children())
        grille = T.grille_mensuelle(self.con, annee)
        for r in grille:
            vals = [r["membre"], r["famille"]]
            vals += [(_f(m) if m else "·") for m in r["mois"]]
            vals.append(_f(r["total"]))
            self.tab_gr.insert("", "end", values=vals)
        v = T.vue_ensemble(self.con, annee)
        self.lbl_gr.config(
            text=f"{len(grille)} membre(s) · cotisation "
                 f"{_f(v['montant_mensuel'])} FCFA/mois · "
                 f"« · » = mois non réglé")


    # ----------------------------------------------------------------
    #  Montants cotises par niveau et par annee
    # ----------------------------------------------------------------
    def _habiller_tags(self):
        """Couleurs des lignes d'entete / total, alignees sur la palette."""
        import theme
        g = theme.gestionnaire()
        pal = g.palette if g is not None else theme.CLAIR
        self.tab_mnt.tag_configure("entete", background=pal["bandeau"],
                                   foreground=pal["texte"],
                                   font=("Segoe UI", 9, "bold"))
        self.tab_mnt.tag_configure("total", background=pal["total"],
                                   foreground=pal["texte"],
                                   font=("Segoe UI", 9, "bold"))

    def _remplir_montants(self):
        niveaux = [("Clan", "clan"), ("Grande famille", "grande_famille"),
                   ("Lignée", "lignee"), ("Famille", "famille")]
        annees_globale = set()
        blocs = []
        for titre, code in niveaux:
            annees, lignes = T.montants_par_niveau(self.con, code)
            annees_globale.update(annees)
            blocs.append((titre, lignes))

        annees = sorted(annees_globale)

        colonnes = (["libelle", "nb_membres"]
                    + ["a%d" % a for a in annees] + ["total"])
        self.tab_mnt.configure(columns=colonnes)
        self.tab_mnt.heading("libelle", text="Libellé")
        self.tab_mnt.column("libelle", width=230, anchor="w")
        self.tab_mnt.heading("nb_membres", text="Membres")
        self.tab_mnt.column("nb_membres", width=75, anchor="center")
        for a in annees:
            self.tab_mnt.heading("a%d" % a, text=str(a))
            self.tab_mnt.column("a%d" % a, width=110, anchor="e")
        self.tab_mnt.heading("total", text="Total")
        self.tab_mnt.column("total", width=120, anchor="e")

        self.tab_mnt.delete(*self.tab_mnt.get_children())
        if not annees:
            self.lbl_mnt.config(
                text="Aucune cotisation enregistrée pour le moment.")
            return

        self._habiller_tags()

        for titre, lignes in blocs:
            self.tab_mnt.insert(
                "", "end", tags=("entete",),
                values=["— %s —" % titre, ""]
                + [""] * (len(annees) + 1))
            for r in lignes:
                vals = [r["libelle"], r["nb_membres"]]
                vals += [_f(r["par_annee"].get(a, 0)) for a in annees]
                vals.append(_f(r["total"]))
                self.tab_mnt.insert("", "end", values=vals)
            tot = ["Total %s" % titre.lower(), ""]
            tot += [_f(sum(r["par_annee"].get(a, 0) for r in lignes))
                    for a in annees]
            tot.append(_f(sum(r["total"] for r in lignes)))
            self.tab_mnt.insert("", "end", tags=("total",), values=tot)

        self.lbl_mnt.config(
            text="Montants en FCFA · annees : "
                 + ", ".join(str(a) for a in annees))

    # ----------------------------------------------------------------
    #  Montant cotise par membre, par annee
    # ----------------------------------------------------------------
    def _remplir_membres(self):
        annees_filtre = self._annee()
        _, lignes = T.montant_par_membre(self.con, annees_filtre)
        annees = sorted({a for r in lignes for a in r["par_annee"]})

        colonnes = (["membre", "famille", "clan"]
                    + ["a%d" % a for a in annees] + ["total", "moyenne"])
        self.tab_mbr.configure(columns=colonnes)
        for cle, lib, larg, anc in (
                ("membre", "Membre", 190, "w"),
                ("famille", "Famille", 160, "w"),
                ("clan", "Clan", 160, "w")):
            self.tab_mbr.heading(cle, text=lib)
            self.tab_mbr.column(cle, width=larg, anchor=anc)
        for a in annees:
            self.tab_mbr.heading("a%d" % a, text=str(a))
            self.tab_mbr.column("a%d" % a, width=100, anchor="e")
        self.tab_mbr.heading("total", text="Total")
        self.tab_mbr.column("total", width=110, anchor="e")
        self.tab_mbr.heading("moyenne", text="Moyenne/an")
        self.tab_mbr.column("moyenne", width=105, anchor="e")

        self.tab_mbr.delete(*self.tab_mbr.get_children())
        for r in lignes:
            vals = [r["membre"], r["famille"], r["clan"]]
            vals += [_f(r["par_annee"].get(a, 0)) for a in annees]
            vals.append(_f(r["total"]))
            vals.append(_f(r["total"] / len(annees)) if annees else "0")
            self.tab_mbr.insert("", "end", values=vals)

        if lignes:
            total = sum(r["total"] for r in lignes)
            self.lbl_mbr.config(
                text="%d membre(s) · total %s FCFA · années : %s"
                     % (len(lignes), _f(total),
                        ", ".join(str(a) for a in annees)))
        else:
            self.lbl_mbr.config(text="Aucune cotisation enregistrée.")


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
    root.title("Test — Tableau de bord")
    root.geometry("1100x760")
    con = db.initialiser()
    etat = _Etat(root)
    etat.pack(side="bottom", fill="x")
    EcranTableauBord(root, con, etat).pack(fill="both", expand=True)
    root.mainloop()
    con.close()
