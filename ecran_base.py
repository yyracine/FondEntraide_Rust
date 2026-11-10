"""
ecran_base.py — Squelette commun aux écrans de saisie hiérarchique.

Chaque niveau (grande famille, lignée, famille, membre) fonctionne de la même
façon :
    - une liste à gauche, filtrée par le nœud parent ;
    - un formulaire à droite, dont le parent est choisi dans une liste
      déroulante limitée aux parents existants ;
    - les boutons Enregistrer / Annuler / Nouveau / Modifier / Supprimer.

Les sous-classes décrivent seulement :
    NIVEAU          clé dans db.NIVEAUX
    TITRE           titre de l'écran
    COLONNES        liste de (clé, libellé, largeur, ancrage)
    CHAMPS          liste de champs spécifiques au niveau (au-delà du nom)
    requete_liste() requête SQL alimentant la liste
"""
import tkinter as tk
from tkinter import ttk, messagebox

import db
from liste_pdf_mixin import BoutonListePDF
from ui_commun import CadreDefilant

# Bandeau des tableaux : couleur de la palette sombre DESIGN.md
# (elle est rejouee par theme.Gestionnaire.CORRESPONDANCES).
COULEUR_ENTETE = "#007ACC"


class EcranHierarchique(BoutonListePDF, ttk.Frame):
    """Écran générique de saisie d'un niveau de la hiérarchie."""

    NIVEAU = None
    TITRE = ""
    COLONNES = ()
    CHAMPS = ()
    LABEL_PARENT = "Parent"
    ARTICLE_PARENT = "le parent"
    TEXTE_AIDE = ""
    TEXTE_VIDE = ""

    def __init__(self, parent, con, etat):
        super().__init__(parent, padding=12)
        self.con = con
        self.etat = etat
        self.id_selection = None
        self.en_edition = False
        self.filtre_id = None          # parent servant de filtre sur la liste
        self.parents = []

        self._construire()
        self.recharger_parents()

    # ================================================================
    #  Construction de l'interface
    # ================================================================
    def _construire(self):
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=0, minsize=340)
        self.rowconfigure(2, weight=1)

        # --- en-tête -------------------------------------------------
        entete = ttk.Frame(self)
        entete.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        ttk.Label(entete, text=self.TITRE, font=("Segoe UI", 16, "bold"),
                  foreground=COULEUR_ENTETE).pack(side="left")
        self.lbl_total = ttk.Label(entete, text="", font=("Segoe UI", 10))
        self.lbl_total.pack(side="right")

        # --- filtre par parent ---------------------------------------
        bloc_filtre = ttk.LabelFrame(self, text=f"Filtrer par {self.LABEL_PARENT.lower()}",
                                     padding=8)
        bloc_filtre.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        self.var_filtre = tk.StringVar(value="— Tous —")
        self.cmb_filtre = ttk.Combobox(bloc_filtre, textvariable=self.var_filtre,
                                       state="readonly", width=42)
        self.cmb_filtre.pack(side="left")
        self.cmb_filtre.bind("<<ComboboxSelected>>", self._sur_filtre)
        ttk.Button(bloc_filtre, text="Tous", width=8,
                   command=self._effacer_filtre).pack(side="left", padx=(8, 0))
        # Export de la liste affichée (respecte le filtre par parent).
        self.bouton_liste_pdf(bloc_filtre, side="right")

        # --- liste ---------------------------------------------------
        bloc_liste = ttk.LabelFrame(self, text=f"{self.TITRE.split('— ')[-1]} enregistrées",
                                    padding=8)
        bloc_liste.grid(row=2, column=0, sticky="nsew", padx=(0, 10))
        bloc_liste.columnconfigure(0, weight=1)
        bloc_liste.rowconfigure(0, weight=1)

        cles = [c[0] for c in self.COLONNES]
        self.table = ttk.Treeview(bloc_liste, columns=cles, show="headings",
                                  selectmode="browse")
        for cle, lib, larg, anc in self.COLONNES:
            self.table.heading(cle, text=lib)
            self.table.column(cle, width=larg, anchor=anc)
        self.table.grid(row=0, column=0, sticky="nsew")
        sy = ttk.Scrollbar(bloc_liste, orient="vertical", command=self.table.yview)
        sy.grid(row=0, column=1, sticky="ns")
        self.table.configure(yscrollcommand=sy.set)
        self.table.bind("<<TreeviewSelect>>", self._sur_selection)
        self.table.bind("<Double-1>", lambda e: self.passer_en_edition())

        self.lbl_vide = ttk.Label(bloc_liste, text=self.TEXTE_VIDE,
                                  justify="center", foreground="#8a8a8a")

        # --- formulaire (défilant) -----------------------------------
        bloc_fiche = ttk.LabelFrame(self, text="Fiche", padding=4)
        bloc_fiche.grid(row=2, column=1, sticky="nsew")
        bloc_fiche.rowconfigure(0, weight=1)
        bloc_fiche.columnconfigure(0, weight=1)

        defilant = CadreDefilant(bloc_fiche)
        defilant.grid(row=0, column=0, sticky="nsew")
        f = ttk.Frame(defilant.contenu, padding=8)
        f.grid(row=0, column=0, sticky="nsew")
        f.columnconfigure(0, weight=1)
        self.form = f

        ligne = 0
        # parent obligatoire
        ttk.Label(f, text=f"{self.LABEL_PARENT} *").grid(
            row=ligne, column=0, sticky="w"); ligne += 1
        self.var_parent = tk.StringVar()
        self.cmb_parent = ttk.Combobox(f, textvariable=self.var_parent,
                                       state="readonly", width=30)
        self.cmb_parent.grid(row=ligne, column=0, sticky="ew", pady=(0, 6))
        ligne += 1

        # nom
        ttk.Label(f, text="Nom *").grid(row=ligne, column=0, sticky="w"); ligne += 1
        self.var_nom = tk.StringVar()
        self.ent_nom = ttk.Entry(f, textvariable=self.var_nom, width=30)
        self.ent_nom.grid(row=ligne, column=0, sticky="ew", pady=(0, 6))
        self.ent_nom.bind("<Return>", lambda e: self.enregistrer())
        ligne += 1

        # champs spécifiques
        # CHAMPS_EN_LIGNE = True place les champs courts sur deux colonnes
        # (utile quand un niveau a beaucoup de champs, comme le membre),
        # les champs "text" occupant toujours toute la largeur.
        self.widgets = {}
        deux_colonnes = getattr(self, "CHAMPS_EN_LIGNE", False)
        f.columnconfigure(1, weight=1)
        col = 0
        for cle, libelle, type_champ in self.CHAMPS:
            if type_champ == "text" or not deux_colonnes:
                ttk.Label(f, text=libelle).grid(row=ligne, column=0,
                                               columnspan=2, sticky="w")
                ligne += 1
                if type_champ == "text":
                    w = tk.Text(f, height=3, width=30, wrap="word")
                elif type_champ == "combo":
                    w = ttk.Combobox(f, state="readonly", width=30)
                else:
                    w = ttk.Entry(f, width=30)
                w.grid(row=ligne, column=0, columnspan=2, sticky="ew",
                       pady=(0, 6))
                ligne += 1
            else:
                # deux champs courts cote a cote
                colonne = col % 2
                ttk.Label(f, text=libelle).grid(row=ligne + 0, column=colonne,
                                               sticky="w")
                if type_champ == "combo":
                    w = ttk.Combobox(f, state="readonly", width=14)
                else:
                    w = ttk.Entry(f, width=14)
                w.grid(row=ligne + 1, column=colonne, sticky="ew",
                       padx=(0, 6) if colonne == 0 else (0, 0), pady=(0, 8))
                col += 1
                if col % 2 == 0:
                    ligne += 2
            self.widgets[cle] = (w, type_champ)
        if deux_colonnes and col % 2:
            ligne += 2

        if self.TEXTE_AIDE:
            ttk.Label(f, text=self.TEXTE_AIDE, foreground="#5a6a72",
                      justify="left").grid(row=ligne, column=0, sticky="w",
                                           pady=(0, 10))
            ligne += 1

        # boutons
        z = ttk.Frame(f)
        z.grid(row=ligne, column=0, sticky="ew")
        z.columnconfigure(0, weight=1)
        z.columnconfigure(1, weight=1)
        self.btn_valider = ttk.Button(z, text="Enregistrer", command=self.enregistrer)
        self.btn_valider.grid(row=0, column=0, sticky="ew", padx=(0, 4), pady=3)
        self.btn_annuler = ttk.Button(z, text="Annuler", command=self.annuler)
        self.btn_annuler.grid(row=0, column=1, sticky="ew", padx=(4, 0), pady=3)
        self.btn_nouveau = ttk.Button(z, text="Nouveau", command=self.nouveau)
        self.btn_nouveau.grid(row=1, column=0, columnspan=2, sticky="ew", pady=3)
        self.btn_modifier = ttk.Button(z, text="Modifier",
                                       command=self.passer_en_edition)
        self.btn_modifier.grid(row=2, column=0, sticky="ew", padx=(0, 4), pady=3)
        self.btn_supprimer = ttk.Button(z, text="Supprimer", command=self.supprimer)
        self.btn_supprimer.grid(row=2, column=1, sticky="ew", padx=(4, 0), pady=3)

    # ================================================================
    #  À surcharger par les sous-classes
    # ================================================================
    def requete_liste(self):
        """Retourne (sql, params) alimentant la liste."""
        raise NotImplementedError

    def valeurs_ligne(self, row):
        """Retourne le tuple de valeurs affiché pour une ligne."""
        return tuple(row[c[0]] for c in self.COLONNES)

    def charger_champs(self, row):
        """Remplit les champs spécifiques depuis une ligne."""
        pass

    def lire_champs(self):
        """Retourne un dict des champs spécifiques saisis."""
        return {}

    @property
    def LISTE_TITRE(self):
        """Titre utilisé dans le PDF de la liste (dérivé du TITRE)."""
        return self.TITRE or "Liste"

    def libelle_parent(self, row):
        return ""

    # ================================================================
    #  Parents
    # ================================================================
    def recharger_parents(self):
        self.parents = db.parents_disponibles(self.con, self.NIVEAU)
        libelles = ["— Tous —"] + [n for _, n in self.parents]
        self.cmb_filtre["values"] = libelles
        if self.var_filtre.get() not in libelles:
            self.var_filtre.set(libelles[0])
        self.cmb_parent["values"] = [n for _, n in self.parents]
        self._maj_boutons()

    def parent_id_par_nom(self, nom):
        for i, n in self.parents:
            if n == nom:
                return i
        return None

    def nom_parent_par_id(self, id_):
        for i, n in self.parents:
            if i == id_:
                return n
        return ""

    # ================================================================
    #  Liste
    # ================================================================
    def recharger(self, garder_id=None):
        self.table.delete(*self.table.get_children())
        sql, params = self.requete_liste()
        params = list(params)
        if self.filtre_id is not None:
            sql = sql.replace("__FILTRE__", "WHERE " + self.requete_liste_filtre())
            params = [self.filtre_id] + params
        else:
            sql = sql.replace("__FILTRE__", "")
        rows = self.con.execute(sql, params).fetchall()
        for r in rows:
            self.table.insert("", "end", iid=str(r["id"]),
                              values=self.valeurs_ligne(r))

        total = self.con.execute(
            f"SELECT COUNT(*) FROM {db.NIVEAUX[self.NIVEAU]['table']}"
        ).fetchone()[0]
        self.lbl_total.config(text=f"{total} au total")
        if not rows:
            self.lbl_vide.place(relx=0.5, rely=0.35, anchor="center")
        else:
            self.lbl_vide.place_forget()

        if garder_id is not None and self.table.exists(str(garder_id)):
            self.table.selection_set(str(garder_id))
            self.table.see(str(garder_id))
        else:
            self.id_selection = None
            self._maj_boutons()

    def requete_liste_filtre(self):
        return f"{db.NIVEAUX[self.NIVEAU]['parent_col']} = ?"

    def _sur_filtre(self, _e=None):
        nom = self.var_filtre.get()
        self.filtre_id = None if nom.startswith("—") else self.parent_id_par_nom(nom)
        self.recharger()

    def _effacer_filtre(self):
        self.var_filtre.set("— Tous —")
        self.filtre_id = None
        self.recharger()

    # ================================================================
    #  Sélection
    # ================================================================
    def _sur_selection(self, _e=None):
        sel = self.table.selection()
        if not sel:
            return
        self.id_selection = int(sel[0])
        self.en_edition = False
        self.btn_valider.config(text="Enregistrer")
        self._charger_fiche(self.id_selection)
        self._maj_boutons()

    def _charger_fiche(self, id_):
        row = self._lire_une(id_)
        if not row:
            return
        self.var_nom.set(row["nom"])
        parent_id = row[db.NIVEAUX[self.NIVEAU]["parent_col"]]
        self.var_parent.set(self.nom_parent_par_id(parent_id))
        self.charger_champs(row)

    def _lire_une(self, id_):
        """Relit une ligne par son identifiant, indépendamment du filtre."""
        sql, params = self.requete_liste()
        sql = sql.replace("__FILTRE__", "").split("ORDER BY")[0].rstrip()
        return self.con.execute(
            f"{sql} WHERE t.id = ?", list(params) + [id_]
        ).fetchone()

    def _maj_boutons(self):
        actif = self.id_selection is not None
        self.btn_modifier.state(["!disabled"] if actif else ["disabled"])
        self.btn_supprimer.state(["!disabled"] if actif else ["disabled"])
        self.btn_annuler.state(["!disabled"] if self.en_edition else ["disabled"])
        self.btn_nouveau.state(["!disabled"] if self.parents else ["disabled"])

    def _vider(self):
        self.var_nom.set("")
        self.var_parent.set("")
        for cle, (w, t) in self.widgets.items():
            if t == "text":
                w.delete("1.0", "end")
            else:
                w.delete(0, "end")

    # ================================================================
    #  Actions
    # ================================================================
    def nouveau(self):
        if not self.parents:
            messagebox.showwarning(
                "Aucun parent",
                f"Créez d'abord {self.ARTICLE_PARENT} : "
                f"le rattachement est obligatoire.")
            return
        self.en_edition = True
        self.id_selection = None
        self.table.selection_remove(*self.table.selection())
        self._vider()
        if self.filtre_id is not None:
            self.var_parent.set(self.nom_parent_par_id(self.filtre_id))
        self.btn_valider.config(text="Enregistrer")
        self.ent_nom.focus_set()
        self._maj_boutons()
        self.etat.info(f"Nouveau : choisissez {self.ARTICLE_PARENT}, "
                       f"saisissez le nom, puis Enregistrer.")

    def passer_en_edition(self):
        if self.id_selection is None:
            messagebox.showinfo("Aucune sélection",
                                "Sélectionnez d'abord une ligne dans la liste.")
            return
        self._charger_fiche(self.id_selection)
        self.en_edition = True
        self.btn_valider.config(text="Mettre à jour")
        self.ent_nom.focus_set()
        self.ent_nom.selection_range(0, "end")
        self._maj_boutons()

    def annuler(self):
        self.en_edition = False
        if self.id_selection is not None:
            self._charger_fiche(self.id_selection)
        else:
            self._vider()
        self.btn_valider.config(text="Enregistrer")
        self._maj_boutons()
        self.etat.info("Saisie annulée.")

    def enregistrer(self):
        nom = self.var_nom.get()
        parent_id = self.parent_id_par_nom(self.var_parent.get())
        try:
            # lire_champs() peut lever ErreurSaisie (ex. ordre non numérique)
            # il doit donc être DANS le bloc try pour être intercepté.
            extras = self.lire_champs()
            if self.en_edition and self.id_selection is None:
                nouveau_id = db.ajouter(self.con, self.NIVEAU, nom,
                                        parent_id=parent_id, **extras)
                message = f"« {db.nettoyer_nom(nom)} » créé."
            elif self.id_selection is not None:
                db.modifier(self.con, self.NIVEAU, self.id_selection, nom, **extras)
                col = db.NIVEAUX[self.NIVEAU]["parent_col"]
                self.con.execute(
                    f"UPDATE {db.NIVEAUX[self.NIVEAU]['table']} SET {col} = ? "
                    f"WHERE id = ?", (parent_id, self.id_selection))
                self.con.commit()
                nouveau_id = self.id_selection
                message = f"« {db.nettoyer_nom(nom)} » mis à jour."
            else:
                messagebox.showinfo("Rien à enregistrer",
                                    "Cliquez sur « Nouveau » ou sélectionnez "
                                    "une ligne à modifier.")
                return
        except db.ErreurSaisie as e:
            messagebox.showerror("Saisie refusée", str(e))
            return

        self.en_edition = False
        self.btn_valider.config(text="Enregistrer")
        self.recharger(garder_id=nouveau_id)
        self.etat.info(message)

    def supprimer(self):
        if self.id_selection is None:
            return
        nom = self.var_nom.get().strip()
        if not messagebox.askyesno("Confirmer la suppression",
                                   f"Supprimer « {nom} » ?"):
            return
        try:
            db.supprimer(self.con, self.NIVEAU, self.id_selection)
        except db.ErreurSaisie as e:
            messagebox.showwarning("Suppression refusée", str(e))
            return
        self.id_selection = None
        self._vider()
        self.recharger()
        self.etat.info(f"« {nom} » supprimé.")
