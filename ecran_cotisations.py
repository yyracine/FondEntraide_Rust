"""
ecran_cotisations.py — Étape 6 : saisie des COTISATIONS.

Principe : on choisit une année, puis un membre (filtré par clan →
grande famille → lignée → famille), et l'on coche les mois réglés.
Un versement peut couvrir plusieurs mois : un seul enregistrement
dans `paiements`, une ligne par mois dans `affectations`.

Lancement autonome : python ecran_cotisations.py
"""
import datetime
import os
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

import cotisations as C
import db
import exports as X
import recus as R
from ui_commun import CadreDefilant

try:                                  # calendrier intégré (pas de popup)
    from tkcalendar import Calendar
    CALENDRIER = True
except ImportError:                   # repli : simple champ texte
    Calendar = None
    CALENDRIER = False


class EcranCotisations(ttk.Frame):
    def __init__(self, parent, con, etat):
        super().__init__(parent, padding=12)
        self.con = con
        self.etat = etat
        self.membre_id = None
        self.cases = {}          # {mois: BooleanVar}
        self.membres_affiches = []
        self._en_peuplement = False

        self._construire()
        self.recharger_annees()

    # ================================================================
    #  Interface
    # ================================================================
    def _construire(self):
        self.columnconfigure(0, weight=3)
        self.columnconfigure(1, weight=2)
        self.rowconfigure(2, weight=1)

        entete = ttk.Frame(self)
        entete.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        ttk.Label(entete, text="Étape 6 — Les cotisations",
                  font=("Segoe UI", 16, "bold"),
                  foreground="#1f4e5f").pack(side="left")
        self.lbl_annee_total = ttk.Label(entete, text="", font=("Segoe UI", 10))
        self.lbl_annee_total.pack(side="right")

        # --- filtres -------------------------------------------------
        barre = ttk.LabelFrame(self, text="Sélection", padding=8)
        barre.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        for i in range(6):
            barre.columnconfigure(i, weight=1 if i else 0)

        ttk.Label(barre, text="Année :").grid(row=0, column=0, sticky="w")
        self.var_annee = tk.StringVar()
        # "normal" = liste proposée MAIS saisie libre : on peut taper 2028,
        # 2029, … ou toute année passée non listée.
        self.cmb_annee = ttk.Combobox(barre, textvariable=self.var_annee,
                                      state="normal", width=8)
        self.cmb_annee.grid(row=1, column=0, sticky="w", padx=(0, 10))
        self.cmb_annee.bind("<<ComboboxSelected>>", self._sur_annee)
        self.cmb_annee.bind("<Return>", self._sur_annee)
        self.cmb_annee.bind("<FocusOut>", self._sur_annee)

        ttk.Label(barre, text="Clan").grid(row=0, column=1, sticky="w")
        self.var_clan = tk.StringVar()
        self.cmb_clan = ttk.Combobox(barre, textvariable=self.var_clan,
                                     state="readonly", width=18)
        self.cmb_clan.grid(row=1, column=1, sticky="ew", padx=(0, 6))
        self.cmb_clan.bind("<<ComboboxSelected>>", self._sur_clan)

        ttk.Label(barre, text="Grande famille").grid(row=0, column=2, sticky="w")
        self.var_gf = tk.StringVar()
        self.cmb_gf = ttk.Combobox(barre, textvariable=self.var_gf,
                                   state="readonly", width=18)
        self.cmb_gf.grid(row=1, column=2, sticky="ew", padx=(0, 6))
        self.cmb_gf.bind("<<ComboboxSelected>>", self._sur_gf)

        ttk.Label(barre, text="Lignée").grid(row=0, column=3, sticky="w")
        self.var_lg = tk.StringVar()
        self.cmb_lg = ttk.Combobox(barre, textvariable=self.var_lg,
                                   state="readonly", width=18)
        self.cmb_lg.grid(row=1, column=3, sticky="ew", padx=(0, 6))
        self.cmb_lg.bind("<<ComboboxSelected>>", self._sur_lg)

        ttk.Label(barre, text="Famille").grid(row=0, column=4, sticky="w")
        self.var_fa = tk.StringVar()
        self.cmb_fa = ttk.Combobox(barre, textvariable=self.var_fa,
                                   state="readonly", width=18)
        self.cmb_fa.grid(row=1, column=4, sticky="ew", padx=(0, 6))
        self.cmb_fa.bind("<<ComboboxSelected>>", self._sur_fa)

        ttk.Button(barre, text="Tout afficher", width=13,
                   command=self._tout_afficher).grid(row=1, column=5, sticky="w")

        # --- liste des membres ---------------------------------------
        bloc_liste = ttk.LabelFrame(self, text="Membres", padding=8)
        bloc_liste.grid(row=2, column=0, sticky="nsew", padx=(0, 10))
        bloc_liste.columnconfigure(0, weight=1)
        bloc_liste.rowconfigure(0, weight=1)

        self.table = ttk.Treeview(
            bloc_liste,
            columns=("nom", "famille", "mois", "verse"),
            show="headings", selectmode="browse")
        for cle, lib, larg, anc in (
                ("nom", "Membre", 190, "w"),
                ("famille", "Famille", 165, "w"),
                ("mois", "Mois payés", 90, "center"),
                ("verse", "Versé", 90, "e")):
            self.table.heading(cle, text=lib)
            self.table.column(cle, width=larg, anchor=anc)
        self.table.grid(row=0, column=0, sticky="nsew")
        sy = ttk.Scrollbar(bloc_liste, orient="vertical", command=self.table.yview)
        sy.grid(row=0, column=1, sticky="ns")
        self.table.configure(yscrollcommand=sy.set)
        self.table.bind("<<TreeviewSelect>>", self._sur_membre)
        self.lbl_vide = ttk.Label(bloc_liste, text="Aucun membre.",
                                  foreground="#8a8a8a")

        # --- fiche de cotisation -------------------------------------
        bloc_fiche = ttk.LabelFrame(self, text="Cotisation du membre", padding=4)
        bloc_fiche.grid(row=2, column=1, sticky="nsew")
        bloc_fiche.rowconfigure(0, weight=1)
        bloc_fiche.columnconfigure(0, weight=1)
        defilant = CadreDefilant(bloc_fiche)
        defilant.grid(row=0, column=0, sticky="nsew")
        f = ttk.Frame(defilant.contenu, padding=8)
        f.grid(row=0, column=0, sticky="nsew")
        f.columnconfigure(0, weight=1)

        self.lbl_membre = ttk.Label(f, text="— aucun membre sélectionné —",
                                    font=("Segoe UI", 11, "bold"),
                                    foreground="#1f4e5f")
        self.lbl_membre.grid(row=0, column=0, sticky="w", pady=(0, 6))

        self.lbl_situation = ttk.Label(f, text="", justify="left")
        self.lbl_situation.grid(row=1, column=0, sticky="w", pady=(0, 6))

        # bandeau des arriérés (toutes années confondues)
        self.lbl_arrieres = ttk.Label(f, text="", justify="left",
                                      wraplength=340,
                                      foreground="#8a4b00")
        self.lbl_arrieres.grid(row=2, column=0, sticky="w", pady=(0, 8))

        # grille des 12 mois
        cadre_mois = ttk.LabelFrame(f, text="Mois à régler", padding=8)
        cadre_mois.grid(row=3, column=0, sticky="ew", pady=(0, 10))
        for i in range(3):
            cadre_mois.columnconfigure(i, weight=1)
        for i, nom in enumerate(C.MOIS_NOMS):
            var = tk.BooleanVar()
            case = ttk.Checkbutton(cadre_mois, text=nom, variable=var,
                                   command=self._maj_montant)
            case.grid(row=i % 4, column=i // 4, sticky="w", pady=2)
            self.cases[i + 1] = var

        raccourcis = ttk.Frame(cadre_mois)
        raccourcis.grid(row=0, column=3, rowspan=4, sticky="nw", padx=(10, 0))
        ttk.Button(raccourcis, text="Tous", width=9,
                   command=lambda: self._cocher(None)).pack(pady=1)
        ttk.Button(raccourcis, text="Aucun", width=9,
                   command=lambda: self._cocher([])).pack(pady=1)
        ttk.Button(raccourcis, text="1er trim.", width=9,
                   command=lambda: self._cocher([1, 2, 3])).pack(pady=1)
        ttk.Button(raccourcis, text="Impayés", width=9,
                   command=self._cocher_impayes).pack(pady=1)

        # saisie du versement
        ttk.Label(f, text="Montant (FCFA)").grid(row=4, column=0, sticky="w")
        self.var_montant = tk.StringVar()
        self.ent_montant = ttk.Entry(f, textvariable=self.var_montant)
        self.ent_montant.grid(row=5, column=0, sticky="ew", pady=(0, 6))

        ttk.Label(f, text="Date du versement").grid(row=6, column=0, sticky="w")
        self.var_date = tk.StringVar(
            value=datetime.date.today().strftime("%d/%m/%Y"))
        ligne_date = ttk.Frame(f)
        ligne_date.grid(row=7, column=0, sticky="ew", pady=(0, 4))
        ligne_date.columnconfigure(0, weight=1)
        self.ent_date = ttk.Entry(ligne_date, textvariable=self.var_date,
                                  justify="left")
        self.ent_date.grid(row=0, column=0, sticky="ew")
        self.ent_date.bind("<KeyRelease>", self._verifier_date)
        ttk.Button(ligne_date, text="Aujourd'hui", width=13,
                   command=self.date_aujourdhui).grid(row=0, column=1,
                                                      padx=(6, 0))

        self.lbl_calendrier = ttk.Label(f, text="Date de saisie", foreground="#8a8a8a")
        self.lbl_calendrier.grid(row=8, column=0, sticky="w", pady=(0, 4))

        if CALENDRIER:
            # Calendrier INTÉGRÉ (et non en fenêtre flottante) : la navigation
            # mois/année reste utilisable, contrairement au popup de
            # DateEntry qui se referme à chaque clic sous Windows.
            cadre_cal = ttk.Frame(f)
            cadre_cal.grid(row=9, column=0, sticky="ew", pady=(0, 8))
            self.calendrier = Calendar(
                cadre_cal, locale="fr_FR", date_pattern="dd/mm/yyyy",
                selectmode="day", showweeknumbers=False,
                showothermonthdays=False,
                background="#ffffff", foreground="#1f2d33",
                headersbackground="#1f4e5f", headersforeground="white",
                normalbackground="#ffffff", normalforeground="#1f2d33",
                weekendbackground="#f2f6f8", weekendforeground="#1f2d33",
                othermonthbackground="#f7f7f7",
                othermonthforeground="#bdbdbd",
                bordercolor="#c8d3d8", borderwidth=1,
                font=("Segoe UI", 9))
            self.calendrier.pack(fill="x")
            self.calendrier.selection_set(datetime.date.today())
            self.calendrier.bind("<<CalendarSelected>>", self._sur_calendrier)
        else:
            self.calendrier = None

        ttk.Label(f, text="Mode").grid(row=10, column=0, sticky="w")
        self.var_mode = tk.StringVar(value="Espèces")
        self.cmb_mode = ttk.Combobox(f, textvariable=self.var_mode,
                                     state="readonly",
                                     values=[lib for _, lib in C.MODES])
        self.cmb_mode.grid(row=11, column=0, sticky="ew", pady=(0, 6))

        self.btn_enregistrer = ttk.Button(f, text="Enregistrer le versement",
                                          command=self.enregistrer)
        self.btn_enregistrer.grid(row=12, column=0, sticky="ew", pady=(6, 3))

        # historique
        self.bloc_hist = ttk.LabelFrame(f, text="Versements enregistrés", padding=6)
        self.bloc_hist.grid(row=13, column=0, sticky="ew", pady=(8, 0))
        self.bloc_hist.columnconfigure(0, weight=1)
        self.hist = ttk.Treeview(self.bloc_hist,
                                 columns=("date", "montant", "mois", "mode"),
                                 show="headings", height=4)
        for cle, lib, larg in (("date", "Date", 85), ("montant", "Montant", 80),
                               ("mois", "Mois", 130), ("mode", "Mode", 85)):
            self.hist.heading(cle, text=lib)
            self.hist.column(cle, width=larg,
                             anchor="w" if cle == "mois" else "center")
        self.hist.grid(row=0, column=0, sticky="ew")
        self.btn_suppr_vers = ttk.Button(self.bloc_hist,
                                         text="Supprimer ce versement",
                                         command=self.supprimer_versement)
        self.btn_suppr_vers.grid(row=1, column=0, sticky="ew", pady=(6, 0))

        self.btn_recu = ttk.Button(self.bloc_hist,
                                   text="Reçu (aperçu PDF)…",
                                   command=self.apercu_recu)
        self.btn_recu.grid(row=2, column=0, sticky="ew", pady=(4, 0))

        self._maj_boutons()

    # ================================================================
    #  Listes déroulantes en cascade
    # ================================================================
    def recharger_annees(self):
        annees = C.annees_disponibles(self.con)
        self.cmb_annee["values"] = [str(a) for a in annees]
        if self.var_annee.get() not in self.cmb_annee["values"]:
            self.var_annee.set(str(annees[0]))
        self.recharger_clans()

    def recharger_clans(self):
        self.clans = [(r["id"], r["nom"]) for r in self.con.execute(
            "SELECT id, nom FROM clans ORDER BY nom COLLATE NOCASE")]
        self.cmb_clan["values"] = ["— Tous —"] + [n for _, n in self.clans]
        if self.var_clan.get() not in self.cmb_clan["values"]:
            self.var_clan.set("— Tous —")
        self._remplir_gf()

    def _remplir_gf(self):
        clan_id = self._id_par_nom(self.clans, self.var_clan.get())
        sql = "SELECT id, nom FROM grandes_familles"
        params = []
        if clan_id is not None:
            sql += " WHERE clan_id = ?"
            params.append(clan_id)
        sql += " ORDER BY nom COLLATE NOCASE"
        self.gfs = [(r["id"], r["nom"]) for r in self.con.execute(sql, params)]
        self.cmb_gf["values"] = ["— Toutes —"] + [n for _, n in self.gfs]
        self.var_gf.set("— Toutes —")
        self._remplir_lg()

    def _remplir_lg(self):
        gf_id = self._id_par_nom(self.gfs, self.var_gf.get())
        sql = "SELECT id, nom FROM lignees"
        params = []
        if gf_id is not None:
            sql += " WHERE grande_famille_id = ?"
            params.append(gf_id)
        sql += " ORDER BY nom COLLATE NOCASE"
        self.lgs = [(r["id"], r["nom"]) for r in self.con.execute(sql, params)]
        self.cmb_lg["values"] = ["— Toutes —"] + [n for _, n in self.lgs]
        self.var_lg.set("— Toutes —")
        self._remplir_fa()

    def _remplir_fa(self):
        lg_id = self._id_par_nom(self.lgs, self.var_lg.get())
        sql = "SELECT id, nom FROM familles"
        params = []
        if lg_id is not None:
            sql += " WHERE lignee_id = ?"
            params.append(lg_id)
        sql += " ORDER BY IFNULL(ordre,9999), nom COLLATE NOCASE"
        self.fas = [(r["id"], r["nom"]) for r in self.con.execute(sql, params)]
        self.cmb_fa["values"] = ["— Toutes —"] + [n for _, n in self.fas]
        self.var_fa.set("— Toutes —")
        self.recharger_membres()

    @staticmethod
    def _id_par_nom(liste, nom):
        for i, n in liste:
            if n == nom:
                return i
        return None

    # ================================================================
    #  Événements de filtre
    # ================================================================
    def _annee_saisie(self):
        """Année choisie, ou None si la saisie n'est pas une année valide."""
        try:
            annee = int(self.var_annee.get().strip())
        except (TypeError, ValueError):
            return None
        return annee if C.annee_valide(annee) else None

    def _sur_annee(self, _e=None):
        annee = self._annee_saisie()
        if annee is None:
            self.etat.info("Année invalide : saisissez une année entre 2000 "
                           "et 2100 (ex. 2028).")
            return
        # l'année saisie hors liste devient une option de la liste
        valeurs = list(self.cmb_annee["values"])
        if str(annee) not in valeurs:
            valeurs.append(str(annee))
            valeurs.sort(key=lambda v: -int(v))
            self.cmb_annee["values"] = valeurs
        self.membre_id = None
        self.recharger_membres()
        self._afficher_membre(None)

    def _sur_clan(self, _e=None):
        self._remplir_gf()

    def _sur_gf(self, _e=None):
        self._remplir_lg()

    def _sur_lg(self, _e=None):
        self._remplir_fa()

    def _sur_fa(self, _e=None):
        self.recharger_membres()

    def _tout_afficher(self):
        self.var_clan.set("— Tous —"); self._remplir_gf()
        self.var_gf.set("— Toutes —"); self._remplir_lg()
        self.var_lg.set("— Toutes —"); self._remplir_fa()
        self.recharger_membres()

    # ================================================================
    #  Membres
    # ================================================================
    def recharger_membres(self):
        self.table.delete(*self.table.get_children())
        annee = self._annee_saisie()
        if annee is None:
            return

        fa_id = self._id_par_nom(self.fas, self.var_fa.get())
        lg_id = self._id_par_nom(self.lgs, self.var_lg.get())
        gf_id = self._id_par_nom(self.gfs, self.var_gf.get())
        clan_id = self._id_par_nom(self.clans, self.var_clan.get())

        sql = """
            SELECT m.id, m.nom, m.prenom, f.nom AS famille
            FROM membres m
            JOIN familles f ON f.id = m.famille_id
            JOIN lignees l ON l.id = f.lignee_id
            JOIN grandes_familles gf ON gf.id = l.grande_famille_id
            JOIN clans c ON c.id = gf.clan_id
            WHERE m.statut = 'actif'
        """
        params = []
        if fa_id is not None:
            sql += " AND m.famille_id = ?"; params.append(fa_id)
        elif lg_id is not None:
            sql += " AND f.lignee_id = ?"; params.append(lg_id)
        elif gf_id is not None:
            sql += " AND l.grande_famille_id = ?"; params.append(gf_id)
        elif clan_id is not None:
            sql += " AND gf.clan_id = ?"; params.append(clan_id)
        sql += " ORDER BY f.nom COLLATE NOCASE, m.nom COLLATE NOCASE"

        self.membres_affiches = self.con.execute(sql, params).fetchall()
        for m in self.membres_affiches:
            sit = C.situation(self.con, m["id"], annee)
            echus = sit["mois_echus"] or 1      # evite « 0/0 »
            self.table.insert(
                "", "end", iid=str(m["id"]),
                values=(f"{m['nom']} {m['prenom'] or ''}".strip(),
                        m["famille"],
                        f"{sit['nb_mois']}/{echus}",
                        f"{int(sit['verse']):,}".replace(",", " ")))

        nb = len(self.membres_affiches)
        total = sum(C.situation(self.con, m["id"], annee)["verse"]
                    for m in self.membres_affiches)
        self.lbl_annee_total.config(
            text=f"{annee} — {nb} membre(s) affiché(s) · "
                 f"{int(total):,} FCFA".replace(",", " "))
        if nb == 0:
            self.lbl_vide.place(relx=0.5, rely=0.4, anchor="center")
        else:
            self.lbl_vide.place_forget()

        if self.membre_id and self.table.exists(str(self.membre_id)):
            self.table.selection_set(str(self.membre_id))
        else:
            self.membre_id = None
            self._afficher_membre(None)

    def _sur_membre(self, _e=None):
        sel = self.table.selection()
        if not sel:
            return
        self.membre_id = int(sel[0])
        self._afficher_membre(self.membre_id)

    # ================================================================
    #  Fiche du membre
    # ================================================================
    def _afficher_membre(self, membre_id):
        self._en_peuplement = True
        try:
            for var in self.cases.values():
                var.set(False)
            self.hist.delete(*self.hist.get_children())

            if membre_id is None:
                self.lbl_membre.config(text="— aucun membre sélectionné —")
                self.lbl_situation.config(text="")
                self.lbl_arrieres.config(text="")
                self.var_montant.set("")
                self._maj_boutons()
                return

            annee = self._annee_saisie()
            if annee is None:
                self.lbl_membre.config(text="Année invalide.")
                self._maj_boutons()
                return
            m = self.con.execute(
                "SELECT nom, prenom FROM membres WHERE id = ?",
                (membre_id,)).fetchone()
            sit = C.situation(self.con, membre_id, annee)

            self.lbl_membre.config(
                text=f"{m['nom']} {m['prenom'] or ''}".strip())
            exercice = C.libelle_exercice(self.con, annee)
            if exercice:
                self.lbl_annee_total.config(
                    text=f"{exercice} · {len(self.membres_affiches)} "
                         f"membre(s)")
            impayes = C.mois_impayes(self.con, membre_id, annee)
            texte = (f"Année {annee} · cotisation {int(sit['montant_mensuel'])} "
                     f"FCFA/mois\n"
                     f"Payés : {sit['nb_mois']}/"
                     f"{sit['mois_echus'] or '—'} · Versé : "
                     f"{int(sit['verse'])} FCFA\n"
                     f"Attendu : {int(sit['attendu'])} · Reste : "
                     f"{int(sit['solde'])} FCFA\n")
            if impayes:
                texte += ("Mois en retard : "
                          + ", ".join(C.MOIS_NOMS[i - 1] for i in impayes))
            else:
                texte += "À jour pour cette année."
            self.lbl_situation.config(text=texte)

            # bandeau des arriérés des AUTRES années
            arr = {a: mo for a, mo in
                   C.arrieres_membre(self.con, membre_id).items()
                   if a != annee}
            if arr:
                morceaux = [f"{a} : {len(mo)} mois" for a, mo in
                            sorted(arr.items())]
                total = C.total_arrieres(self.con, membre_id)
                self.lbl_arrieres.config(
                    text="⚠ Arriérés à régler : "
                         + " · ".join(morceaux)
                         + "\nTotal dû, toutes années confondues : "
                         + f"{int(total)} FCFA.\n"
                         + "Choisissez l'année concernée dans la liste "
                           "« Année » ci-dessus pour la régulariser.")
            else:
                self.lbl_arrieres.config(text="")

            for v in C.versements_membre(self.con, membre_id, annee):
                self.hist.insert("", "end", iid=str(v["id"]),
                                 values=(C.date_fr(v["date_paiement"]),
                                         f"{int(v['montant_total']):,}"
                                         .replace(",", " "),
                                         C.mois_en_lettres(v["mois"]),
                                         v["mode"]))
            self._maj_boutons()
        finally:
            self._en_peuplement = False

    # ================================================================
    #  Cases à cocher
    # ================================================================
    def _cocher(self, mois):
        if self.membre_id is None:
            return
        annee = self._annee_saisie()
        if annee is None:
            return
        payes = C.mois_payes(self.con, self.membre_id, annee)
        mensuel = C.situation(self.con, self.membre_id, annee)["montant_mensuel"]
        for m, var in self.cases.items():
            deja_paye = payes.get(m, 0) >= mensuel
            if mois is None:
                var.set(not deja_paye)
            else:
                var.set(m in mois and not deja_paye)
        self._maj_montant()

    def _cocher_impayes(self):
        if self.membre_id is None:
            return
        annee = self._annee_saisie()
        if annee is None:
            return
        impayes = C.mois_impayes(self.con, self.membre_id, annee)
        for m, var in self.cases.items():
            var.set(m in impayes)
        self._maj_montant()

    def _maj_montant(self):
        """Met à jour le montant proposé à partir des mois cochés."""
        if self._en_peuplement:
            return
        if self.membre_id is None:
            return
        annee = self._annee_saisie()
        if annee is None:
            return
        mensuel = C.situation(self.con, self.membre_id, annee)["montant_mensuel"]
        nb = sum(1 for v in self.cases.values() if v.get())
        self.var_montant.set(str(int(mensuel * nb)) if nb else "")

    # ================================================================
    #  Actions
    # ================================================================
    def _date_saisie(self):
        """Renvoie la date au format ISO (AAAA-MM-JJ) ou None si invalide."""
        txt = self.var_date.get().strip()
        for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
            try:
                return datetime.datetime.strptime(txt, fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue
        return None

    def date_aujourdhui(self):
        """Remet la date du jour dans le champ et dans le calendrier."""
        aujourdhui = datetime.date.today()
        self.var_date.set(aujourdhui.strftime("%d/%m/%Y"))
        if CALENDRIER and self.calendrier is not None:
            self.calendrier.selection_set(aujourdhui)
        self.lbl_calendrier.config(text="Date de saisie", foreground="#8a8a8a")

    def _sur_calendrier(self, _e=None):
        """Un jour a été choisi dans le calendrier -> on remplit le champ."""
        try:
            d = self.calendrier.selection_get()
        except Exception:
            return
        self.var_date.set(d.strftime("%d/%m/%Y"))
        self.lbl_calendrier.config(text="Date de saisie", foreground="#8a8a8a")

    def _verifier_date(self, _e=None):
        """Prévient si le texte saisi n'est pas une date valide, et cale le
        calendrier sur la date tapée."""
        txt = self.var_date.get().strip()
        for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
            try:
                d = datetime.datetime.strptime(txt, fmt)
                self.lbl_calendrier.config(text="Date de saisie",
                                           foreground="#8a8a8a")
                if CALENDRIER and self.calendrier is not None:
                    self.calendrier.selection_set(d.date())
                return
            except ValueError:
                continue
        self.lbl_calendrier.config(
            text="Date non reconnue — choisissez dans le calendrier."
                 if txt else "Date de saisie",
            foreground="#b00020" if txt else "#8a8a8a")

    def _maj_boutons(self):
        actif = self.membre_id is not None
        self.btn_enregistrer.state(["!disabled"] if actif else ["disabled"])
        self.btn_suppr_vers.state(["!disabled"] if actif else ["disabled"])
        self.btn_recu.state(["!disabled"] if actif else ["disabled"])

    def enregistrer(self):
        if self.membre_id is None:
            messagebox.showinfo("Aucun membre",
                                "Sélectionnez d'abord un membre dans la liste.")
            return
        annee = self._annee_saisie()
        if annee is None:
            messagebox.showerror("Année invalide",
                                 "Saisissez une année entre 2000 et 2100.")
            return

        mois = sorted(m for m, v in self.cases.items() if v.get())
        if not mois:
            messagebox.showinfo("Aucun mois",
                                "Cochez au moins un mois à régler.")
            return

        date_txt = self._date_saisie()
        if date_txt is None:
            messagebox.showerror(
                "Date invalide",
                "Saisissez la date au format JJ/MM/AAAA "
                "(ex. 31/12/2025) ou choisissez-la dans le calendrier.")
            return

        mode = next((cle for cle, lib in C.MODES if lib == self.var_mode.get()),
                    "especes")
        try:
            paiement_id = C.enregistrer_versement(
                self.con, self.membre_id, annee, mois, date_txt,
                montant_total=self.var_montant.get().strip() or None,
                mode=mode)
        except db.ErreurSaisie as e:
            messagebox.showerror("Enregistrement refusé", str(e))
            return

        nb = len(mois)
        self.etat.info(f"Versement enregistré : {nb} mois "
                       f"({C.mois_en_lettres(','.join(map(str, mois)))}) pour "
                       f"{self.lbl_membre.cget('text')}.")
        mid = self.membre_id
        self.recharger_membres()
        self.membre_id = mid
        if self.table.exists(str(mid)):
            self.table.selection_set(str(mid))
        self._afficher_membre(mid)
        if self.hist.exists(str(paiement_id)):
            self.hist.selection_set(str(paiement_id))

        # Reçu : on le propose immédiatement après l'enregistrement.
        if messagebox.askyesno(
                "Versement enregistré",
                "Versement enregistré.\n\nÉditer le reçu de ce paiement "
                "(aperçu PDF puis impression) ?"):
            self.apercu_recu()

    # ================================================================
    #  Reçu de versement : aperçu PDF puis impression
    # ================================================================
    def _versement_selectionne(self):
        """Id du versement à justifier (sélection, sinon le dernier)."""
        sel = self.hist.selection()
        if sel:
            return int(sel[0])
        enfants = self.hist.get_children()
        if enfants:
            return int(enfants[0])
        return None

    def apercu_recu(self):
        """Génère le reçu en PDF et l'ouvre dans la visionneuse."""
        if self.membre_id is None:
            messagebox.showinfo("Aucun membre",
                                "Sélectionnez d'abord un membre.")
            return
        paiement_id = self._versement_selectionne()
        if paiement_id is None:
            messagebox.showinfo(
                "Aucun versement",
                "Ce membre n'a aucun versement enregistré : enregistrez-en "
                "un avant d'éditer un reçu.")
            return
        try:
            d = R.donnees_recu(self.con, paiement_id)
        except db.ErreurSaisie as e:
            messagebox.showerror("Reçu impossible", str(e))
            return
        chemin = X.chemin_temporaire("recu_%s" % d["numero"].replace("/", "-"))
        try:
            X.recu_pdf(chemin, d)
        except X.ErreurExport as e:
            messagebox.showerror("Reçu impossible", str(e))
            return
        self.etat.info("Reçu %s — aperçu PDF" % d["numero"])
        try:
            os.startfile(chemin)
        except (AttributeError, OSError) as e:
            messagebox.showerror(
                "Aperçu",
                "Impossible d'ouvrir le PDF : aucun lecteur associé.\n"
                f"Fichier : {chemin}\n\n{e}")
            return
        self._proposer_impression(d, chemin)

    def _proposer_impression(self, d, chemin):
        """Demande s'il faut imprimer et/ou enregistrer une copie."""
        rep = messagebox.askyesnocancel(
            "Reçu %s" % d["numero"],
            "L'aperçu du reçu est ouvert.\n\n"
            "Oui  = imprimer le reçu\n"
            "Non  = enregistrer une copie dans un dossier\n"
            "Annuler = fermer l'aperçu, ne rien faire",
            parent=self)
        if rep is None:
            return
        if rep:
            try:
                X.imprimer(chemin)
            except X.ErreurExport as e:
                messagebox.showerror("Impression", str(e), parent=self)
                return
            self.etat.info("Reçu %s envoyé à l'imprimante." % d["numero"])
            return
        dossier = filedialog.askdirectory(
            parent=self, title="Dossier où enregistrer le reçu",
            mustexist=True)
        if not dossier:
            return
        cible = os.path.join(dossier, "recu_%s.pdf" % d["numero"])
        try:
            with open(chemin, "rb") as src, open(cible, "wb") as dst:
                dst.write(src.read())
        except OSError as e:
            messagebox.showerror("Enregistrement",
                                 f"Copie impossible : {e}", parent=self)
            return
        self.etat.info("Reçu %s enregistré : %s" % (d["numero"], cible))

    def supprimer_versement(self):
        sel = self.hist.selection()
        if not sel:
            messagebox.showinfo("Aucune sélection",
                                "Sélectionnez un versement dans la liste "
                                "du bas.")
            return
        if not messagebox.askyesno(
                "Confirmer", "Supprimer ce versement et tous ses mois ?"):
            return
        C.supprimer_versement(self.con, int(sel[0]))
        self.etat.info("Versement supprimé.")
        mid = self.membre_id
        self.recharger_membres()
        self.membre_id = mid
        if mid and self.table.exists(str(mid)):
            self.table.selection_set(str(mid))
        self._afficher_membre(mid)


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
    root.title("Test — Cotisations")
    root.geometry("1180x780")
    con = db.initialiser()
    etat = _Etat(root)
    etat.pack(side="bottom", fill="x")
    EcranCotisations(root, con, etat).pack(fill="both", expand=True)
    root.mainloop()
    con.close()
