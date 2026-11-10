"""
ecran_grandes_familles.py — Étape 2 : saisie des GRANDES FAMILLES.

Une grande famille appartient obligatoirement à un clan (lien de dépendance
garanti à trois niveaux : liste filtrée, bouton désactivé, contrôle SQL).

Lancement autonome pour tester : python ecran_grandes_familles.py
"""
import tkinter as tk
from tkinter import ttk, messagebox

import db
from liste_pdf_mixin import BoutonListePDF
from ui_commun import CadreDefilant

# Bandeau des tableaux : couleur de la palette sombre DESIGN.md
# (elle est rejouee par theme.Gestionnaire.CORRESPONDANCES).
COULEUR_ENTETE = "#007ACC"


class EcranGrandesFamilles(BoutonListePDF, ttk.Frame):
    NIVEAU = "grande_famille"
    PARENT = "clan"
    LISTE_TITRE = "Étape 2 — Les grandes familles"

    def __init__(self, parent, con, etat):
        super().__init__(parent, padding=12)
        self.con = con
        self.etat = etat
        self.id_selection = None
        self.en_edition = False
        self.clan_filtre = None

        self._construire()
        self.recharger_clans()

    # ----------------------------------------------------------------
    def _construire(self):
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=0, minsize=340)
        self.rowconfigure(2, weight=1)

        # en-tête
        entete = ttk.Frame(self)
        entete.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        ttk.Label(entete, text="Étape 2 — Les grandes familles",
                  font=("Segoe UI", 16, "bold"),
                  foreground=COULEUR_ENTETE).pack(side="left")
        self.lbl_total = ttk.Label(entete, text="", font=("Segoe UI", 10))
        self.lbl_total.pack(side="right")

        # filtre par clan (le parent)
        bloc_filtre = ttk.LabelFrame(self, text="Filtrer par clan parent", padding=8)
        bloc_filtre.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        self.var_filtre = tk.StringVar(value="— Tous les clans —")
        self.cmb_filtre = ttk.Combobox(bloc_filtre, textvariable=self.var_filtre,
                                       state="readonly", width=40)
        self.cmb_filtre.pack(side="left")
        self.cmb_filtre.bind("<<ComboboxSelected>>", self._sur_filtre)
        ttk.Button(bloc_filtre, text="Tous", width=8,
                   command=self._effacer_filtre).pack(side="left", padx=(8, 0))
        self.bouton_liste_pdf(bloc_filtre, side="right")

        # tableau
        bloc_liste = ttk.LabelFrame(self, text="Grandes familles enregistrées",
                                    padding=8)
        bloc_liste.grid(row=2, column=0, sticky="nsew", padx=(0, 10))
        bloc_liste.columnconfigure(0, weight=1)
        bloc_liste.rowconfigure(0, weight=1)

        colonnes = ("clan", "nom", "lignees", "desc")
        self.table = ttk.Treeview(bloc_liste, columns=colonnes, show="headings",
                                  selectmode="browse")
        for cle, lib, larg in (("clan", "Clan (parent)", 190),
                               ("nom", "Grande famille", 200),
                               ("lignees", "Lignées", 80),
                               ("desc", "Description", 200)):
            self.table.heading(cle, text=lib)
            self.table.column(cle, width=larg,
                              anchor="center" if cle == "lignees" else "w")
        self.table.grid(row=0, column=0, sticky="nsew")
        sy = ttk.Scrollbar(bloc_liste, orient="vertical", command=self.table.yview)
        sy.grid(row=0, column=1, sticky="ns")
        self.table.configure(yscrollcommand=sy.set)
        self.table.bind("<<TreeviewSelect>>", self._sur_selection)
        self.table.bind("<Double-1>", lambda e: self.passer_en_edition())

        self.lbl_vide = ttk.Label(
            bloc_liste,
            text="Aucune grande famille enregistrée.\n"
                 "Choisissez un clan parent puis « Nouvelle ».",
            justify="center", foreground="#8a8a8a")

        # formulaire
        bloc_fiche = ttk.LabelFrame(self, text="Fiche de la grande famille",
                                    padding=4)
        bloc_fiche.grid(row=2, column=1, sticky="nsew")
        bloc_fiche.rowconfigure(0, weight=1)
        bloc_fiche.columnconfigure(0, weight=1)

        defilant = CadreDefilant(bloc_fiche)
        defilant.grid(row=0, column=0, sticky="nsew")
        bloc_form = ttk.Frame(defilant.contenu, padding=8)
        bloc_form.grid(row=0, column=0, sticky="nsew")
        bloc_form.columnconfigure(0, weight=1)

        ttk.Label(bloc_form, text="Clan parent *").grid(row=0, column=0, sticky="w")
        self.var_clan = tk.StringVar()
        self.cmb_clan = ttk.Combobox(bloc_form, textvariable=self.var_clan,
                                     state="readonly", width=30)
        self.cmb_clan.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        self.cmb_clan.bind("<<ComboboxSelected>>", self._sur_clan_form)

        ttk.Label(bloc_form, text="Nom de la grande famille *").grid(
            row=2, column=0, sticky="w")
        self.var_nom = tk.StringVar()
        self.ent_nom = ttk.Entry(bloc_form, textvariable=self.var_nom, width=30)
        self.ent_nom.grid(row=3, column=0, sticky="ew", pady=(0, 10))

        ttk.Label(bloc_form, text="Description").grid(row=4, column=0, sticky="w")
        self.txt_desc = tk.Text(bloc_form, height=3, width=30, wrap="word")
        self.txt_desc.grid(row=5, column=0, sticky="ew", pady=(0, 10))

        self.lbl_aide = ttk.Label(
            bloc_form,
            text="Une grande famille appartient à un seul clan.\n"
                 "Son nom doit être unique dans ce clan.",
            foreground="#5a6a72", justify="left")
        self.lbl_aide.grid(row=6, column=0, sticky="w", pady=(0, 10))

        # la zone de boutons est ancree en bas : elle reste visible
        # meme si la fenetre est reduite
        z = ttk.Frame(bloc_form)
        z.grid(row=7, column=0, sticky="ew")
        z.columnconfigure(0, weight=1)
        z.columnconfigure(1, weight=1)
        self.btn_valider = ttk.Button(z, text="Enregistrer", command=self.enregistrer)
        self.btn_valider.grid(row=0, column=0, sticky="ew", padx=(0, 4), pady=3)
        self.btn_annuler = ttk.Button(z, text="Annuler", command=self.annuler)
        self.btn_annuler.grid(row=0, column=1, sticky="ew", padx=(4, 0), pady=3)
        self.btn_nouveau = ttk.Button(z, text="Nouvelle grande famille",
                                      command=self.nouveau)
        self.btn_nouveau.grid(row=1, column=0, columnspan=2, sticky="ew", pady=3)
        self.btn_modifier = ttk.Button(z, text="Modifier",
                                       command=self.passer_en_edition)
        self.btn_modifier.grid(row=2, column=0, sticky="ew", padx=(0, 4), pady=3)
        self.btn_supprimer = ttk.Button(z, text="Supprimer", command=self.supprimer)
        self.btn_supprimer.grid(row=2, column=1, sticky="ew", padx=(4, 0), pady=3)

        self.ent_nom.bind("<Return>", lambda e: self.enregistrer())

    # ----------------------------------------------------------------
    #  Listes de référence
    # ----------------------------------------------------------------
    def recharger_clans(self):
        """Alimente la liste des clans parents et le filtre."""
        self.clans = db.parents_disponibles(self.con, self.NIVEAU)
        libelles = ["— Tous les clans —"] + [nom for _, nom in self.clans]
        self.cmb_filtre["values"] = libelles
        if self.var_filtre.get() not in libelles:
            self.var_filtre.set(libelles[0])
        self.cmb_clan["values"] = [nom for _, nom in self.clans]
        self._maj_boutons()

    def _clan_id_par_nom(self, nom):
        for id_, n in self.clans:
            if n == nom:
                return id_
        return None

    def _nom_clan(self, id_):
        for i, n in self.clans:
            if i == id_:
                return n
        return ""

    # ----------------------------------------------------------------
    #  Données
    # ----------------------------------------------------------------
    def recharger(self, garder_id=None):
        self.table.delete(*self.table.get_children())
        sql = """
            SELECT gf.id, gf.nom, gf.description, c.nom AS clan,
                   (SELECT COUNT(*) FROM lignees l
                     WHERE l.grande_famille_id = gf.id) AS nb
            FROM grandes_familles gf
            JOIN clans c ON c.id = gf.clan_id
        """
        params = []
        if self.clan_filtre is not None:
            sql += " WHERE gf.clan_id = ?"
            params.append(self.clan_filtre)
        sql += " ORDER BY c.nom COLLATE NOCASE, gf.nom COLLATE NOCASE"

        lignes = self.con.execute(sql, params).fetchall()
        for r in lignes:
            desc = (r["description"] or "").replace("\n", " ")
            self.table.insert("", "end", iid=str(r["id"]),
                              values=(r["clan"], r["nom"], r["nb"], desc))

        total = self.con.execute("SELECT COUNT(*) FROM grandes_familles").fetchone()[0]
        self.lbl_total.config(text=f"{total} grande{'s' if total > 1 else ''} "
                                   f"famille{'s' if total > 1 else ''} au total")

        if not lignes:
            self.lbl_vide.place(relx=0.5, rely=0.35, anchor="center")
        else:
            self.lbl_vide.place_forget()

        if garder_id is not None and self.table.exists(str(garder_id)):
            self.table.selection_set(str(garder_id))
            self.table.see(str(garder_id))
        else:
            self.id_selection = None
            self._maj_boutons()

    def _sur_filtre(self, _e=None):
        nom = self.var_filtre.get()
        if nom.startswith("—"):
            self.clan_filtre = None
        else:
            self.clan_filtre = self._clan_id_par_nom(nom)
        self.recharger()

    def _effacer_filtre(self):
        self.var_filtre.set("— Tous les clans —")
        self.clan_filtre = None
        self.recharger()

    def _sur_clan_form(self, _e=None):
        """Pré-remplit le nom du clan choisi dans la fiche."""
        self._maj_boutons()

    def _sur_selection(self, _e=None):
        """Un clic sur une ligne sélectionne TOUJOURS cette ligne : on quitte
        le mode création et on charge la fiche. Sinon le formulaire resterait
        vide alors qu'une ligne est sélectionnée, et l'utilisateur croirait
        ne rien pouvoir modifier."""
        sel = self.table.selection()
        if not sel:
            return
        self.id_selection = int(sel[0])
        self.en_edition = False
        self.btn_valider.config(text="Enregistrer")
        self._charger_fiche(self.id_selection)
        self._maj_boutons()

    def _charger_fiche(self, id_):
        r = self.con.execute("""
            SELECT gf.nom, gf.description, c.nom AS clan
            FROM grandes_familles gf JOIN clans c ON c.id = gf.clan_id
            WHERE gf.id = ?""", (id_,)).fetchone()
        self.var_nom.set(r["nom"])
        self.var_clan.set(r["clan"])
        self.txt_desc.delete("1.0", "end")
        self.txt_desc.insert("1.0", r["description"] or "")

    def _maj_boutons(self):
        actif = self.id_selection is not None
        self.btn_modifier.state(["!disabled"] if actif else ["disabled"])
        self.btn_supprimer.state(["!disabled"] if actif else ["disabled"])
        self.btn_annuler.state(["!disabled"] if self.en_edition else ["disabled"])
        # pas de clan dans la base -> pas de création possible
        self.btn_nouveau.state(["!disabled"] if self.clans else ["disabled"])

    def _vider(self):
        self.var_nom.set("")
        self.var_clan.set("")
        self.txt_desc.delete("1.0", "end")

    # ----------------------------------------------------------------
    #  Actions
    # ----------------------------------------------------------------
    def nouveau(self):
        if not self.clans:
            messagebox.showwarning(
                "Aucun clan",
                "Créez d'abord un clan : une grande famille doit "
                "obligatoirement appartenir à un clan.")
            return
        self.en_edition = True
        self.id_selection = None
        self.table.selection_remove(*self.table.selection())
        self._vider()
        if self.clan_filtre is not None:
            self.var_clan.set(self._nom_clan(self.clan_filtre))
        self.btn_valider.config(text="Enregistrer")
        self.ent_nom.focus_set()
        self._maj_boutons()
        self.etat.info("Nouvelle grande famille : choisissez le clan parent, "
                       "saisissez le nom, puis Enregistrer.")

    def passer_en_edition(self):
        if self.id_selection is None:
            messagebox.showinfo("Aucune sélection",
                                "Sélectionnez d'abord une grande famille "
                                "dans la liste.")
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
        desc = self.txt_desc.get("1.0", "end").strip() or None
        clan_id = self._clan_id_par_nom(self.var_clan.get())
        try:
            if self.en_edition and self.id_selection is None:
                nouveau_id = db.ajouter(self.con, self.NIVEAU, nom,
                                        parent_id=clan_id, description=desc)
                message = f"Grande famille « {db.nettoyer_nom(nom)} » créée."
            elif self.id_selection is not None:
                # le clan parent reste modifiable : on le met à jour aussi
                db.modifier(self.con, self.NIVEAU, self.id_selection, nom,
                            description=desc)
                self.con.execute("UPDATE grandes_familles SET clan_id = ? "
                                 "WHERE id = ?", (clan_id, self.id_selection))
                self.con.commit()
                nouveau_id = self.id_selection
                message = f"Grande famille « {db.nettoyer_nom(nom)} » mise à jour."
            else:
                messagebox.showinfo("Rien à enregistrer",
                                    "Cliquez sur « Nouvelle grande famille » "
                                    "ou sélectionnez-en une à modifier.")
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
                                   f"Supprimer la grande famille « {nom} » ?"):
            return
        try:
            db.supprimer(self.con, self.NIVEAU, self.id_selection)
        except db.ErreurSaisie as e:
            messagebox.showwarning("Suppression refusée", str(e))
            return
        self.id_selection = None
        self._vider()
        self.recharger()
        self.etat.info(f"Grande famille « {nom} » supprimée.")


# ---------------------------------------------------------------------
#  Lancement autonome (test de l'écran seul)
# ---------------------------------------------------------------------
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
    root.title("Test — Grandes familles")
    root.geometry("1060x620")
    con = db.initialiser()
    etat = _Etat(root)
    etat.pack(side="bottom", fill="x")
    ecran = EcranGrandesFamilles(root, con, etat)
    ecran.pack(fill="both", expand=True)
    root.mainloop()
    con.close()
