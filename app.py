"""
app.py — Application de saisie de la hiérarchie du Fonds d'Entraide.

Étape 1 : saisie des CLANS.
Les étapes suivantes (grandes familles, lignées, familles, membres) seront
ajoutées progressivement, chacune dans son fichier d'écran.

Lancement : python app.py
"""
import tkinter as tk
from pathlib import Path
from tkinter import ttk, messagebox

import db
from liste_pdf_mixin import BoutonListePDF
from ui_commun import CadreDefilant
from ecran_grandes_familles import EcranGrandesFamilles
from ecran_lignees import EcranLignees
from ecran_familles import EcranFamilles
from ecran_membres import EcranMembres
from ecran_cotisations import EcranCotisations
from ecran_parametres import EcranParametres
from ecran_tableau_bord import EcranTableauBord
import parametres as P
import theme

# Couleurs de repli : la palette de theme.py (DESIGN.md) fait foi.
COULEUR_FOND = theme.CLAIR["fond"]
COULEUR_ENTETE = theme.CLAIR["entete"]
COULEUR_ACCENT = theme.CLAIR["accent"]


class BarreEtat(ttk.Frame):
    """Bandeau d'information en bas de fenêtre."""

    def __init__(self, parent):
        super().__init__(parent, relief="sunken", padding=(8, 4))
        self.var = tk.StringVar()
        ttk.Label(self, textvariable=self.var).pack(side="left")

    def info(self, texte):
        self.var.set(texte)


class EcranClans(BoutonListePDF, ttk.Frame):
    """
    Étape 1 — Saisie des clans.

    Un clan est le sommet de la hiérarchie : il n'a pas de parent.
    Son nom doit être unique dans toute la base.
    """

    NIVEAU = "clan"
    LISTE_TITRE = "Étape 1 — Les clans"

    def __init__(self, parent, con, etat):
        super().__init__(parent, padding=12)
        self.con = con
        self.etat = etat
        self.id_selection = None
        self.en_edition = False

        self._construire()
        self.recharger()

    # ----------------------------------------------------------------
    #  Interface
    # ----------------------------------------------------------------
    def _construire(self):
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=0, minsize=340)
        self.rowconfigure(1, weight=1)

        entete = ttk.Frame(self)
        entete.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        ttk.Label(
            entete,
            text="Étape 1 — Les clans",
            font=("Segoe UI", 16, "bold"),
            foreground=COULEUR_ENTETE,
        ).pack(side="left")
        self.btn_liste_pdf = ttk.Button(entete, text="Liste en PDF…",
                                        width=16,
                                        command=self.exporter_liste_pdf)
        self.btn_liste_pdf.pack(side="right", padx=(8, 0))
        self.lbl_total = ttk.Label(entete, text="", font=("Segoe UI", 10))
        self.lbl_total.pack(side="right")

        # --- liste des clans -----------------------------------------
        bloc_liste = ttk.LabelFrame(self, text="Clans enregistrés", padding=8)
        bloc_liste.grid(row=1, column=0, sticky="nsew", padx=(0, 10))
        bloc_liste.columnconfigure(0, weight=1)
        bloc_liste.rowconfigure(0, weight=1)

        colonnes = ("nom", "gf", "desc")
        self.table = ttk.Treeview(
            bloc_liste, columns=colonnes, show="headings", selectmode="browse"
        )
        self.table.heading("nom", text="Clan")
        self.table.heading("gf", text="Grandes familles")
        self.table.heading("desc", text="Description")
        self.table.column("nom", width=200)
        self.table.column("gf", width=120, anchor="center")
        self.table.column("desc", width=240)
        self.table.grid(row=0, column=0, sticky="nsew")

        sy = ttk.Scrollbar(bloc_liste, orient="vertical", command=self.table.yview)
        sy.grid(row=0, column=1, sticky="ns")
        self.table.configure(yscrollcommand=sy.set)
        self.table.bind("<<TreeviewSelect>>", self._sur_selection)
        self.table.bind("<Double-1>", lambda e: self.passer_en_edition())

        self.lbl_vide = ttk.Label(
            bloc_liste,
            text="Aucun clan enregistré.\n"
                 "Commencez par « Nouveau clan » à droite.",
            justify="center",
            foreground="#8a8a8a",
        )

        # --- formulaire ----------------------------------------------
        bloc_fiche = ttk.LabelFrame(self, text="Fiche du clan", padding=4)
        bloc_fiche.grid(row=1, column=1, sticky="nsew")
        bloc_fiche.rowconfigure(0, weight=1)
        bloc_fiche.columnconfigure(0, weight=1)
        defilant = CadreDefilant(bloc_fiche)
        defilant.grid(row=0, column=0, sticky="nsew")
        bloc_form = ttk.Frame(defilant.contenu, padding=8)
        bloc_form.grid(row=0, column=0, sticky="nsew")
        bloc_form.columnconfigure(0, weight=1)

        ttk.Label(bloc_form, text="Nom du clan *").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 2)
        )
        self.var_nom = tk.StringVar()
        self.ent_nom = ttk.Entry(bloc_form, textvariable=self.var_nom, width=30)
        self.ent_nom.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 10))

        ttk.Label(bloc_form, text="Description").grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(0, 2)
        )
        self.txt_desc = tk.Text(bloc_form, height=5, width=30, wrap="word")
        self.txt_desc.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(0, 12))

        self.lbl_aide = ttk.Label(
            bloc_form,
            text="Un clan est le sommet de la hiérarchie.\n"
                 "Son nom doit être unique dans la base.",
            foreground="#5a6a72",
            justify="left",
        )
        self.lbl_aide.grid(row=4, column=0, columnspan=2, sticky="w", pady=(0, 12))

        zone_boutons = ttk.Frame(bloc_form)
        zone_boutons.grid(row=5, column=0, columnspan=2, sticky="ew")
        for i in range(2):
            zone_boutons.columnconfigure(i, weight=1)

        self.btn_valider = ttk.Button(
            zone_boutons, text="Enregistrer", command=self.enregistrer
        )
        self.btn_valider.grid(row=0, column=0, sticky="ew", padx=(0, 4), pady=3)

        self.btn_annuler = ttk.Button(
            zone_boutons, text="Annuler", command=self.annuler
        )
        self.btn_annuler.grid(row=0, column=1, sticky="ew", padx=(4, 0), pady=3)

        self.btn_nouveau = ttk.Button(
            zone_boutons, text="Nouveau clan", command=self.nouveau
        )
        self.btn_nouveau.grid(row=1, column=0, sticky="ew", padx=(0, 4), pady=3)

        self.btn_modifier = ttk.Button(
            zone_boutons, text="Modifier", command=self.passer_en_edition
        )
        self.btn_modifier.grid(row=1, column=1, sticky="ew", padx=(4, 0), pady=3)

        self.btn_supprimer = ttk.Button(
            zone_boutons, text="Supprimer", command=self.supprimer
        )
        self.btn_supprimer.grid(row=2, column=0, columnspan=2, sticky="ew", pady=3)

        self.ent_nom.bind("<Return>", lambda e: self.enregistrer())

    # ----------------------------------------------------------------
    #  Données
    # ----------------------------------------------------------------
    def recharger(self, garder_id=None):
        self.table.delete(*self.table.get_children())
        lignes = db.lister(self.con, self.NIVEAU)
        for id_, nom, nb in lignes:
            desc = self.con.execute(
                "SELECT description FROM clans WHERE id = ?", (id_,)
            ).fetchone()
            desc = (desc["description"] or "").replace("\n", " ") if desc else ""
            self.table.insert("", "end", iid=str(id_), values=(nom, nb, desc))

        total = len(lignes)
        self.lbl_total.config(
            text=f"{total} clan{'s' if total > 1 else ''} enregistré"
                 f"{'s' if total > 1 else ''}"
        )
        if total == 0:
            self.lbl_vide.place(relx=0.5, rely=0.4, anchor="center")
        else:
            self.lbl_vide.place_forget()

        if garder_id is not None and self.table.exists(str(garder_id)):
            self.table.selection_set(str(garder_id))
            self.table.see(str(garder_id))
        else:
            self.id_selection = None
            self._maj_boutons()

    def _sur_selection(self, _evt=None):
        """Un clic sur une ligne quitte le mode création et charge la fiche."""
        sel = self.table.selection()
        if not sel:
            return
        self.id_selection = int(sel[0])
        self.en_edition = False
        self.btn_valider.config(text="Enregistrer")
        self._charger_fiche(self.id_selection)
        self._maj_boutons()

    def _charger_fiche(self, id_):
        row = self.con.execute(
            "SELECT nom, description FROM clans WHERE id = ?", (id_,)
        ).fetchone()
        self.var_nom.set(row["nom"])
        self.txt_desc.delete("1.0", "end")
        self.txt_desc.insert("1.0", row["description"] or "")

    def _maj_boutons(self):
        actif = self.id_selection is not None
        self.btn_modifier.state(["!disabled"] if actif else ["disabled"])
        self.btn_supprimer.state(["!disabled"] if actif else ["disabled"])
        self.btn_annuler.state(["!disabled"] if self.en_edition else ["disabled"])

    def _vider(self):
        self.var_nom.set("")
        self.txt_desc.delete("1.0", "end")

    # ----------------------------------------------------------------
    #  Actions
    # ----------------------------------------------------------------
    def nouveau(self):
        self.en_edition = False
        self.id_selection = None
        self.table.selection_remove(*self.table.selection())
        self._vider()
        self.en_edition = True
        self.btn_valider.config(text="Enregistrer")
        self.ent_nom.focus_set()
        self._maj_boutons()
        self.etat.info("Nouveau clan : saisissez son nom puis Enregistrer.")

    def passer_en_edition(self):
        if self.id_selection is None:
            messagebox.showinfo(
                "Aucune sélection", "Sélectionnez d'abord un clan dans la liste."
            )
            return
        self._charger_fiche(self.id_selection)
        self.en_edition = True
        self.btn_valider.config(text="Mettre à jour")
        self.ent_nom.focus_set()
        self.ent_nom.selection_range(0, "end")
        self._maj_boutons()
        self.etat.info("Modification du clan sélectionné.")

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
        try:
            if self.en_edition and self.id_selection is None:
                nouveau_id = db.ajouter(self.con, self.NIVEAU, nom, description=desc)
                message = f"Clan « {db.nettoyer_nom(nom)} » créé."
            elif self.id_selection is not None:
                db.modifier(self.con, self.NIVEAU, self.id_selection, nom,
                            description=desc)
                nouveau_id = self.id_selection
                message = f"Clan « {db.nettoyer_nom(nom)} » mis à jour."
            else:
                messagebox.showinfo(
                    "Rien à enregistrer",
                    "Cliquez sur « Nouveau clan » ou sélectionnez un clan à modifier.",
                )
                return
        except db.ErreurSaisie as e:
            messagebox.showerror("Saisie refusée", str(e))
            self.ent_nom.focus_set()
            return

        self.en_edition = False
        self.btn_valider.config(text="Enregistrer")
        self.recharger(garder_id=nouveau_id)
        self.etat.info(message)

    def supprimer(self):
        if self.id_selection is None:
            return
        nom = self.var_nom.get().strip()
        if not messagebox.askyesno(
            "Confirmer la suppression",
            f"Supprimer définitivement le clan « {nom} » ?",
        ):
            return
        try:
            db.supprimer(self.con, self.NIVEAU, self.id_selection)
        except db.ErreurSaisie as e:
            messagebox.showwarning("Suppression refusée", str(e))
            return
        self.id_selection = None
        self._vider()
        self.recharger()
        self.etat.info(f"Clan « {nom} » supprimé.")

    # ----------------------------------------------------------------
    def focus_initial(self):
        self.ent_nom.focus_set()


ICO = "relation.ico"


def appliquer_icone(fenetre, chemin=None):
    """Remplace l'icone Tk par defaut (plume rouge) par relation.ico.

    Windows : iconbitmap (le .ico contient 16, 20, 24, 32, 40, 48, 64,
    128 et 256 px). Repli portable via PhotoImage. Ne leve jamais :
    une icone absente ne doit pas empecher le demarrage.
    """
    fichier = Path(chemin) if chemin else Path(__file__).with_name(ICO)
    if not fichier.exists():
        print(f"Icone introuvable : {fichier}")
        return False
    try:
        fenetre.iconbitmap(default=str(fichier))
        return True
    except tk.TclError:
        pass
    try:
        image = tk.PhotoImage(file=str(fichier))
        fenetre.iconphoto(True, image)
        fenetre._icone_tk = image      # garder une reference (sinon GC)
        return True
    except tk.TclError as e:
        print(f"Icone non appliquee : {e}")
        return False

def icone_autonome(racine):
    """A appeler dans les blocs `if __name__ == "__main__"` des ecrans."""
    appliquer_icone(racine)


class Application(tk.Tk):
    def __init__(self, con, icone=None):
        super().__init__()
        self.con = con
        appliquer_icone(self, icone)
        self.title("Fonds d'Entraide — Saisie de la hiérarchie")
        # la fenetre s'adapte a la taille reelle de l'ecran :
        # sur un 1366x768 elle ne debordera pas sous la barre des taches
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        largeur = min(1060, sw - 60)
        hauteur = min(800, sh - 80)
        self.geometry(f"{largeur}x{hauteur}+30+20")
        self.minsize(780, 480)
        self.configure(bg=COULEUR_FOND)

        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TButton", padding=6)
        style.configure("Treeview", rowheight=24)
        # bouton de purge : rouge pour signaler le danger
        style.configure("Danger.TButton", foreground="#b00020")

        # bandeau de titre
        bandeau = tk.Frame(self, bg=COULEUR_ENTETE, height=46)
        bandeau.pack(fill="x")
        bandeau.pack_propagate(False)
        tk.Label(
            bandeau,
            text="FONDS D'ENTRAIDE  ·  Saisie de la hiérarchie",
            bg=COULEUR_ENTETE,
            fg="white",
            font=("Segoe UI", 13, "bold"),
        ).pack(side="left", padx=16)
        self.lbl_etape = tk.Label(
            bandeau,
            text="Étape 1 / 6",
            bg=COULEUR_ENTETE,
            fg="#b8d8e0",
            font=("Segoe UI", 10),
        )
        self.lbl_etape.pack(side="right", padx=(0, 16))

        # bascule clair / sombre
        self._bandeau = bandeau
        self.btn_theme = tk.Button(
            bandeau,
            text="\u263e  Mode sombre",
            command=self.basculer_theme,
            relief="flat",
            bd=0,
            cursor="hand2",
            font=("Segoe UI", 9),
            padx=10,
            pady=2,
        )
        self.btn_theme.pack(side="right", padx=(0, 12))

        self.etat = BarreEtat(self)
        self.etat.pack(side="bottom", fill="x")

        self.conteneur = ttk.Frame(self)
        self.conteneur.pack(fill="both", expand=True)

        self.onglets = ttk.Notebook(self.conteneur)
        self.onglets.pack(fill="both", expand=True, padx=6, pady=6)

        self.ecran = EcranClans(self.onglets, con, self.etat)
        self.onglets.add(self.ecran, text="  1. Clans  ")

        self.ecran_gf = EcranGrandesFamilles(self.onglets, con, self.etat)
        self.onglets.add(self.ecran_gf, text="  2. Grandes familles  ")

        self.ecran_lg = EcranLignees(self.onglets, con, self.etat)
        self.onglets.add(self.ecran_lg, text="  3. Lignées  ")

        self.ecran_fa = EcranFamilles(self.onglets, con, self.etat)
        self.onglets.add(self.ecran_fa, text="  4. Familles  ")

        self.ecran_me = EcranMembres(self.onglets, con, self.etat)
        self.onglets.add(self.ecran_me, text="  5. Membres  ")

        self.ecran_co = EcranCotisations(self.onglets, con, self.etat)
        self.onglets.add(self.ecran_co, text="  6. Cotisations  ")

        self.ecran_tb = EcranTableauBord(self.onglets, con, self.etat)
        self.onglets.add(self.ecran_tb, text="  7. Tableau de bord  ")

        self.ecran_pa = EcranParametres(self.onglets, con, self.etat,
                                        sur_restauration=self.tout_recharger)
        self.onglets.add(self.ecran_pa, text="  8. Paramètres  ")

        self.onglets.bind("<<NotebookTabChanged>>", self._sur_changement_onglet)

        # ---- thème clair / sombre ----
        self.theme = theme.Gestionnaire(self)
        theme.definir_gestionnaire(self.theme)
        self.theme.suivre_cadre(self.conteneur)
        self.theme.suivre_cadre(self)
        self.theme.charger(con)
        self._habiller_calendriers()
        self._noter_couleurs()
        self.theme.recenser_tk(self)
        self.theme.appliquer()
        self._maj_bouton_theme()

        self.ecran.focus_initial()

        # menu d'aide : diagnostic de mise en page
        barre_menu = tk.Menu(self)
        aide = tk.Menu(barre_menu, tearoff=0)
        aide.add_command(label="Diagnostic de mise en page",
                         command=self.diagnostic)
        aide.add_separator()
        aide.add_command(label="Basculer clair / sombre  (Ctrl+D)",
                         command=self.basculer_theme)
        barre_menu.add_cascade(label="Aide", menu=aide)
        self.config(menu=barre_menu)

        self.etat.info(
            "Prêt. Étapes : 1 Clans, 2 Grandes familles, 3 Lignées, 4 Familles, 5 Membres."
        )

        # sauvegarde automatique à la fermeture
        self._sauvegarde_faite = False
        self.protocol("WM_DELETE_WINDOW", self.fermer)
        self.bind_all("<Control-d>", lambda _e: self.basculer_theme())

    # ------------------------------------------------------------------
    #  Thème clair / sombre
    # ------------------------------------------------------------------
    def _habiller_calendriers(self):
        """Recolore les calendriers des écrans qui en possèdent un."""
        self._calendriers = []
        for ecran in (self.ecran_co,):
            cal = getattr(ecran, "calendrier", None)
            if cal is not None:
                self._calendriers.append(cal)
                self.theme.suivre_calendrier(cal)
            else:
                for nom in ("cal", "calendrier", "_cal"):
                    cal = getattr(ecran, nom, None)
                    if cal is not None:
                        self._calendriers.append(cal)
                        self.theme.suivre_calendrier(cal)
                        break

    def _noter_couleurs(self):
        """Recense les couleurs écrites en dur dans tous les écrans."""
        def parcourir(widget):
            for option in ("foreground", "bg", "background"):
                try:
                    valeur = widget.cget(option)
                except (tk.TclError, AttributeError):
                    continue
                if isinstance(valeur, str) and valeur.startswith("#"):
                    self.theme.enregistrer(widget, option, valeur)
            for enfant in widget.winfo_children():
                parcourir(enfant)

        parcourir(self)

    def _maj_bouton_theme(self):
        clair = not self.theme.sombre
        self.btn_theme.config(
            text="\u263e  Mode sombre" if clair else "\u2600  Mode clair")
        if hasattr(self, "_bandeau"):
            try:
                bandeau_bg = self.theme.couleur("entete")
                self._bandeau.configure(bg=bandeau_bg)
                for enfant in self._bandeau.winfo_children():
                    if isinstance(enfant, tk.Label):
                        enfant.configure(bg=bandeau_bg)
            except tk.TclError:
                pass
        try:
            self.btn_theme.configure(
                bg=self.theme.couleur("entete"),
                fg=self.theme.couleur("entete_second"),
                activebackground=self.theme.couleur("accent"),
                activeforeground=self.theme.couleur("entete_texte"))
        except tk.TclError:
            pass

    def basculer_theme(self):
        nom = self.theme.basculer()
        self._maj_bouton_theme()
        self.theme.enregistrer_choix(self.con)
        self.etat.info("Thème %s activé." %
                       ("sombre" if nom == "sombre" else "clair"))

    # ------------------------------------------------------------------
    #  Rechargement global (après restauration ou purge)
    # ------------------------------------------------------------------
    def tout_recharger(self):
        """Relit la base et remet tous les écrans à jour."""
        for ecran in (self.ecran, self.ecran_gf, self.ecran_lg,
                      self.ecran_fa, self.ecran_me):
            try:
                ecran.recharger_parents()
                ecran.recharger()
            except Exception:
                pass
        for ecran in (self.ecran_co, self.ecran_tb, self.ecran_pa):
            try:
                if ecran is self.ecran_pa:
                    ecran.recharger()
                else:
                    ecran.recharger_annees()
            except Exception:
                pass
        self.etat.info("Données rechargées.")

    # ------------------------------------------------------------------
    #  Fermeture : sauvegarde automatique (n et n-1 conservées)
    # ------------------------------------------------------------------
    def fermer(self):
        if self._sauvegarde_faite:
            self.destroy()
            return
        self._sauvegarde_faite = True
        try:
            chemin = P.sauvegarder(self.con)
            self.con.close()
            print(f"Sauvegarde automatique : {chemin}")
        except Exception as e:
            print(f"Sauvegarde automatique impossible : {e}")
        self.destroy()

    @staticmethod
    def _dans_cadre_defilant(widget):
        """Vrai si le widget est dans un canevas défilant : il reste
        atteignable même s'il dépasse la fenêtre."""
        parent = widget.master
        while parent is not None:
            if parent.winfo_class() == "Canvas":
                return True
            parent = parent.master
        return False

    def diagnostic(self):
        """Affiche la position reelle de chaque bouton : permet de verifier
        qu'aucun n'est hors fenetre."""
        ecran = self.onglets.nametowidget(self.onglets.select())
        W, H = self.winfo_width(), self.winfo_height()
        lignes = [f"Fenêtre : {W} x {H}", ""]
        boutons = []

        def walk(w):
            for c in w.winfo_children():
                if c.winfo_class() == "TButton":
                    # position DANS SON CONTENEUR (indépendante du défilement) :
                    # si le bouton est dans un cadre défilant, le défilement suffit
                    x = c.winfo_rootx() - self.winfo_rootx()
                    y = c.winfo_rooty() - self.winfo_rooty()
                    dedans = (x >= 0 and y >= 0
                              and x + c.winfo_width() <= W
                              and y + c.winfo_height() <= H)
                    defilant = self._dans_cadre_defilant(c)
                    boutons.append((c.cget("text"), x, y,
                                    c.winfo_width(), c.winfo_height(),
                                    dedans or defilant, defilant))
                walk(c)
        walk(ecran)

        if not boutons:
            lignes.append("Aucun bouton détecté sur cet onglet.")
        for t, x, y, w, h, dedans, defilant in boutons:
            if dedans and not defilant:
                etat = "OK "
            elif defilant:
                etat = "DEFILANT"
            else:
                etat = "HORS"
            lignes.append(f"{etat:9s} {t:26s} x={x:4d} y={y:4d}  {w}x{h}")
        hors = [b for b in boutons if not b[5]]
        lignes.append("")
        lignes.append("Tous les boutons sont accessibles."
                      if not hors
                      else f"{len(hors)} bouton(s) inaccessibles : agrandissez "
                           f"la fenêtre.")
        messagebox.showinfo("Diagnostic de mise en page", chr(10).join(lignes))

    def _sur_changement_onglet(self, _evt=None):
        """Chaque onglet relit ses listes de parents : un clan créé
        à l'étape 1 doit apparaître immédiatement à l'étape 2."""
        courant = self.onglets.index(self.onglets.select())
        if courant == 0:
            self.ecran.recharger()
            self.lbl_etape.config(text="Étape 1 / 6")
        elif courant == 1:
            self.ecran_gf.recharger_clans()
            self.ecran_gf.recharger(garder_id=self.ecran_gf.id_selection)
            self.lbl_etape.config(text="Étape 2 / 6")
        elif courant == 2:
            self.ecran_lg.recharger_parents()
            self.ecran_lg.recharger(garder_id=self.ecran_lg.id_selection)
            self.lbl_etape.config(text="Étape 3 / 6")
        elif courant == 3:
            self.ecran_fa.recharger_parents()
            self.ecran_fa.recharger(garder_id=self.ecran_fa.id_selection)
            self.lbl_etape.config(text="Étape 4 / 6")
        elif courant == 4:
            self.ecran_me.recharger_parents()
            self.ecran_me.recharger(garder_id=self.ecran_me.id_selection)
            self.lbl_etape.config(text="Étape 5 / 6")
        elif courant == 5:
            self.ecran_co.recharger_annees()
            self.lbl_etape.config(text="Étape 6 / 6")
        elif courant == 6:
            self.ecran_tb.recharger_annees()
            self.lbl_etape.config(text="Tableau de bord")
        elif courant == 7:
            self.ecran_pa.recharger()
            self.lbl_etape.config(text="Paramètres")


def main():
    con = db.initialiser()
    app = Application(con)
    try:
        app.mainloop()
    finally:
        con.close()


if __name__ == "__main__":
    main()
