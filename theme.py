"""
theme.py — Apparence claire / sombre de l'application.

Le thème s'applique à trois niveaux :
  1. les couleurs de base (fond, texte, en-têtes) ;
  2. les styles ttk (Treeview, Notebook, Entry, Combobox…) ;
  3. les couleurs écrites en dur dans les écrans (foreground=...).

Pour le point 3, on enregistre chaque couleur demandée dans une palette et
on journalise (widget, option, couleur-claire). Au changement de thème, on
rejoue ces couleurs avec leur équivalent sombre. Cela évite de réécrire
les 8 écrans.

Le choix est mémorisé dans la table `parametres` (clé « theme »).
"""
import tkinter as tk
from tkinter import ttk

import parametres as P

CLE = "theme"

# Thème appliqué tant que l'utilisateur n'a rien choisi : la palette
# DESIGN.md (sombre). Le choix explicite reste mémorisé en base et prime.
THEME_PAR_DEFAUT = "sombre"

# ---------------------------------------------------------------------
#  Palettes
# ---------------------------------------------------------------------
CLAIR = {
    "nom": "clair",
    "fond": "#F3F3F3",
    "fond_alt": "#FFFFFF",
    "fond_zone": "#FFFFFF",
    "bordure": "#C8C8C8",
    "texte": "#1F1F1F",
    "texte_doux": "#4A4A4A",
    "texte_faible": "#6E6E6E",
    "accent": "#007ACC",
    "accent_hover": "#005A9E",
    "entete": "#007ACC",
    "entete_texte": "#FFFFFF",
    "entete_second": "#D6E9F8",
    "ligne_paire": "#FFFFFF",
    "ligne_impaire": "#F3F3F3",
    "selection": "#CCE4F7",
    "selection_texte": "#1F1F1F",
    "ok": "#107C10",
    "alerte": "#8A6D00",
    "danger": "#C42B1C",
    "bandeau": "#E8E8E8",
    "total": "#EFEFEF",
}

SOMBRE = {
    "nom": "sombre",
    # --- palette DESIGN.md (thème sombre type VS Code) ----------------
    "fond": "#1E1E1E",          # Background
    "fond_alt": "#252526",      # Surface (cartes)
    "fond_zone": "#333333",     # Surface élevée (activity bar, inputs)
    "bordure": "#474747",       # Bordure
    "texte": "#D4D4D4",         # Texte principal
    "texte_doux": "#B0B0B0",    # intermédiaire (non prévu par la palette)
    "texte_faible": "#808080",  # Texte secondaire
    "accent": "#007ACC",        # Accent
    "accent_hover": "#005A9E",  # Accent hover
    # --- rôles dérivés de la palette ---------------------------------
    "entete": "#007ACC",        # bandeaux / en-têtes de tableau
    "entete_texte": "#FFFFFF",
    "entete_second": "#B9DCF5",
    "ligne_paire": "#1E1E1E",
    "ligne_impaire": "#252526",
    "selection": "#094771",     # sélection (accent assombri, reste lisible)
    "selection_texte": "#FFFFFF",
    "ok": "#4EC9B0",
    "alerte": "#DCDCAA",
    "danger": "#F14C4C",
    "bandeau": "#252526",
    "total": "#333333",
}

# Couleurs claires écrites en dur dans les écrans -> équivalent sombre
CORRESPONDANCES = {
    # bandeaux / titres -> accent
    "#1f4e5f": SOMBRE["entete"],
    "#2e7d8f": SOMBRE["accent"],
    # textes secondaires
    "#55606a": SOMBRE["texte_doux"],
    "#5a6a72": SOMBRE["texte_doux"],
    "#8a8a8a": SOMBRE["texte_faible"],
    # rôles fonctionnels (on garde leur sens)
    "#8a4b00": SOMBRE["alerte"],
    "#b00020": SOMBRE["danger"],
    "#1f7a3f": SOMBRE["ok"],
    # fonds
    "#1f2d33": SOMBRE["texte"],
    "#f4f6f8": SOMBRE["fond"],
    "#ffffff": SOMBRE["fond_alt"],
    "#f2f6f8": SOMBRE["ligne_impaire"],
    "#f7f7f7": SOMBRE["ligne_impaire"],
    "#e8eff1": SOMBRE["bandeau"],
    "#f4f7f8": SOMBRE["total"],
    "#b8d8e0": SOMBRE["entete_second"],
    "#c8d2d8": SOMBRE["bordure"],
    "#cfe3e8": SOMBRE["selection"],
}

# couleurs du calendrier (tkcalendar)
CAL_CLAIR = {
    "background": "#ffffff", "foreground": "#1f2d33",
    "headersbackground": "#1f4e5f", "headersforeground": "white",
    "normalbackground": "#ffffff", "normalforeground": "#1f2d33",
    "weekendbackground": "#f2f6f8", "weekendforeground": "#1f2d33",
    "othermonthbackground": "#f7f7f7", "othermonthforeground": "#bdbdbd",
    "selectbackground": "#2e7d8f", "selectforeground": "white",
    "bordercolor": "#c8d2d8",
}
CAL_SOMBRE = {
    "background": "#1E1E1E", "foreground": "#D4D4D4",
    "headersbackground": "#007ACC", "headersforeground": "#FFFFFF",
    "normalbackground": "#1E1E1E", "normalforeground": "#D4D4D4",
    "weekendbackground": "#252526", "weekendforeground": "#D4D4D4",
    "othermonthbackground": "#252526", "othermonthforeground": "#808080",
    "selectbackground": "#007ACC", "selectforeground": "#FFFFFF",
    "bordercolor": "#474747",
}


# ---------------------------------------------------------------------
#  Gestionnaire de thème
# ---------------------------------------------------------------------
class Gestionnaire:
    """Applique et commute le thème de toute la fenêtre."""

    def __init__(self, racine):
        self.racine = racine
        self.palette = SOMBRE
        # (widget, option, couleur-claire) pour rejouer les couleurs
        self._journal = []
        self._vues = []          # widgets tk.Text / tk.Listbox à recolorer
        self._calendriers = []   # réglages à réappliquer (tkcalendar)
        self._cadres_tk = []     # conteneurs Tk purs à recolorer
        self._tk_widgets = []    # Canvas / Text / Listbox à recolorer
        self._observateurs = []  # fonctions rappelées après application
        self.style = ttk.Style(racine)

    # -- accesseurs ---------------------------------------------------
    @property
    def sombre(self):
        return self.palette["nom"] == "sombre"

    def couleur(self, cle):
        return self.palette[cle]

    # -- enregistrement des couleurs en dur --------------------------
    def enregistrer(self, widget, option, valeur):
        """Note une couleur écrite en dur pour pouvoir la rejouer."""
        self._journal.append((widget, option, valeur))

    def suivre_cadre(self, widget):
        """Recolore un tk.Frame (conteneur Tk, hors styles ttk)."""
        self._cadres_tk.append(widget)

    def suivre_widget(self, widget):
        """Recolore un Canvas / Text / Listbox (widget Tk classique)."""
        self._tk_widgets.append(widget)

    def recenser_tk(self, racine):
        """Parcourt l'arbre et note tous les widgets Tk classiques.

        Les widgets ttk suivent les styles ; les autres (tk.Canvas,
        tk.Text, tk.Listbox, tk.Frame…) gardent sinon leur couleur
        blanche par défaut, d'où des zones claires en mode sombre.
        """
        def parcourir(widget):
            if isinstance(widget, (tk.Canvas, tk.Text, tk.Listbox,
                                   tk.Frame, tk.Toplevel, tk.Label,
                                   tk.Button)):
                if not isinstance(widget, ttk.Widget):
                    if widget not in self._tk_widgets:
                        self._tk_widgets.append(widget)
            for enfant in widget.winfo_children():
                parcourir(enfant)

        parcourir(racine)

    def observer(self, fonction):
        """Enregistre une fonction rappelée à chaque changement de thème."""
        self._observateurs.append(fonction)

    def suivre_calendrier(self, widget):
        """Recolore un widget tkcalendar.Calendar à chaque changement."""
        self._calendriers.append(widget)

    # -- bascule ------------------------------------------------------
    def basculer(self):
        self.palette = SOMBRE if not self.sombre else CLAIR
        self.appliquer()
        return self.palette["nom"]

    def charger(self, con):
        """Relit le thème mémorisé dans la base (défaut : sombre)."""
        try:
            valeur = P.lire_parametre(con, CLE, THEME_PAR_DEFAUT)
        except Exception:
            valeur = THEME_PAR_DEFAUT
        valeur = (valeur or THEME_PAR_DEFAUT).strip().lower()
        self.palette = CLAIR if valeur == "clair" else SOMBRE
        return self.palette["nom"]

    def enregistrer_choix(self, con):
        try:
            P.ecrire_parametre(con, CLE, self.palette["nom"])
        except Exception:
            pass

    # -- application --------------------------------------------------
    def appliquer(self):
        pal = self.palette
        s = self.style

        try:
            s.theme_use("clam")
        except tk.TclError:
            pass

        # couleurs générales clam
        s.configure(".", background=pal["fond"], foreground=pal["texte"],
                    fieldbackground=pal["fond_zone"],
                    bordercolor=pal["bordure"],
                    lightcolor=pal["bordure"], darkcolor=pal["bordure"],
                    troughcolor=pal["fond_alt"],
                    selectbackground=pal["selection"],
                    selectforeground=pal["selection_texte"])
        s.configure("TFrame", background=pal["fond"])
        s.configure("TLabel", background=pal["fond"], foreground=pal["texte"])
        s.configure("TLabelframe", background=pal["fond"],
                    foreground=pal["texte"], bordercolor=pal["bordure"])
        s.configure("TLabelframe.Label", background=pal["fond"],
                    foreground=pal["accent"], font=("Segoe UI", 9, "bold"))
        s.configure("TButton", padding=(10, 5), background=pal["fond_zone"],
                    foreground=pal["texte"], bordercolor=pal["bordure"],
                    focusthickness=0, relief="flat")
        s.map("TButton",
              background=[("disabled", pal["fond_alt"]),
                          ("pressed", pal["accent_hover"]),
                          ("active", pal["accent"])],
              foreground=[("disabled", pal["texte_faible"]),
                          ("active", pal["entete_texte"])])
        s.configure("Danger.TButton", foreground=pal["danger"])
        s.map("Danger.TButton", foreground=[("active", pal["danger"])])
        s.configure("TCheckbutton", background=pal["fond"],
                    foreground=pal["texte"])
        s.map("TCheckbutton", background=[("active", pal["fond"])])
        s.configure("TRadiobutton", background=pal["fond"],
                    foreground=pal["texte"])
        s.map("TRadiobutton", background=[("active", pal["fond"])])
        s.configure("TEntry", fieldbackground=pal["fond_zone"],
                    foreground=pal["texte"], insertcolor=pal["texte"],
                    bordercolor=pal["bordure"], lightcolor=pal["bordure"],
                    darkcolor=pal["bordure"], padding=(4, 3))
        s.map("TEntry",
              fieldbackground=[("readonly", pal["fond_alt"]),
                               ("focus", pal["fond_zone"])],
              bordercolor=[("focus", pal["accent"])])
        s.configure("TCombobox", fieldbackground=pal["fond_zone"],
                    background=pal["fond_alt"], foreground=pal["texte"],
                    arrowcolor=pal["texte"], bordercolor=pal["bordure"])
        s.map("TCombobox",
              fieldbackground=[("readonly", pal["fond_zone"])],
              foreground=[("readonly", pal["texte"])])
        # liste déroulante du combobox (élément Tk classique)
        self.racine.option_add("*TCombobox*Listbox.background",
                               pal["fond_zone"])
        self.racine.option_add("*TCombobox*Listbox.foreground", pal["texte"])
        self.racine.option_add("*TCombobox*Listbox.selectBackground",
                               pal["selection"])
        self.racine.option_add("*TCombobox*Listbox.selectForeground",
                               pal["selection_texte"])

        s.configure("TNotebook", background=pal["fond"],
                    bordercolor=pal["bordure"], tabmargins=(2, 4, 2, 0))
        s.configure("TNotebook.Tab", background=pal["fond_alt"],
                    foreground=pal["texte_faible"], padding=(14, 7),
                    bordercolor=pal["bordure"])
        s.map("TNotebook.Tab",
              background=[("selected", pal["accent"]),
                          ("active", pal["fond_zone"])],
              foreground=[("selected", pal["entete_texte"]),
                          ("active", pal["texte"])],
              expand=[("selected", (0, 0, 0, 0))])

        s.configure("TSeparator", background=pal["bordure"])
        s.configure("TScrollbar", background=pal["fond_alt"],
                    troughcolor=pal["fond"], bordercolor=pal["bordure"],
                    arrowcolor=pal["texte_doux"])
        s.map("TScrollbar", background=[("active", pal["selection"])])
        s.configure("TPanedwindow", background=pal["fond"])

        s.configure("Treeview", background=pal["ligne_paire"],
                    fieldbackground=pal["ligne_paire"],
                    foreground=pal["texte"],
                    bordercolor=pal["bordure"], rowheight=24)
        s.map("Treeview",
              background=[("selected", pal["selection"])],
              foreground=[("selected", pal["selection_texte"])])
        s.configure("Treeview.Heading", background=pal["entete"],
                    foreground=pal["entete_texte"],
                    bordercolor=pal["bordure"], relief="flat",
                    padding=(6, 5), font=("Segoe UI", 9, "bold"))
        s.map("Treeview.Heading",
              background=[("active", pal["accent_hover"])],
              foreground=[("active", pal["entete_texte"])])

        # fenêtre, menu
        self.racine.configure(bg=pal["fond"])
        # les conteneurs Tk purs (tk.Frame) ne suivent pas les styles ttk :
        # on les recolore explicitement
        for widget in self._cadres_tk:
            try:
                if not widget.winfo_exists():
                    continue
            except (tk.TclError, AttributeError):
                continue
            try:
                # tk.Tk, tk.Frame, tk.Toplevel acceptent -bg ;
                # un ttk.Frame non (il faut passer par le style)
                widget.configure(bg=pal["fond"])
            except tk.TclError:
                pass
        try:
            self.racine.option_add("*Menu.background", pal["fond_alt"])
            self.racine.option_add("*Menu.foreground", pal["texte"])
            self.racine.option_add("*Menu.activeBackground", pal["selection"])
            self.racine.option_add("*Menu.activeForeground", pal["texte"])
        except tk.TclError:
            pass

        # couleurs écrites en dur
        # (la racine et les conteneurs suivis sont déjà traités ci-dessus :
        #  on ne les rejoue pas, sinon leur ancienne couleur claire revient)
        cadres = set(id(w) for w in self._cadres_tk)
        for widget, option, valeur in self._journal:
            if id(widget) in cadres:
                continue
            try:
                if not widget.winfo_exists():
                    continue
            except (tk.TclError, AttributeError):
                continue
            nouvelle = valeur
            if self.sombre:
                nouvelle = CORRESPONDANCES.get(str(valeur).lower(), valeur)
            try:
                widget.configure(**{option: nouvelle})
            except tk.TclError:
                pass

        # widgets Tk classiques (hors style ttk) : Canvas, Text, Listbox…
        for widget in self._tk_widgets:
            try:
                if not widget.winfo_exists():
                    continue
            except (tk.TclError, AttributeError):
                continue
            try:
                if isinstance(widget, tk.Canvas):
                    widget.configure(bg=pal["fond"],
                                     highlightbackground=pal["fond"],
                                     highlightcolor=pal["fond"])
                else:
                    widget.configure(bg=pal["fond_zone"], fg=pal["texte"],
                                     insertbackground=pal["texte"],
                                     selectbackground=pal["selection"],
                                     selectforeground=pal["texte"],
                                     highlightbackground=pal["bordure"])
            except tk.TclError:
                pass

        # zones de texte / listes enregistrees explicitement
        for widget in self._vues:
            try:
                if not widget.winfo_exists():
                    continue
                if isinstance(widget, tk.Text):
                    widget.configure(bg=pal["fond_zone"], fg=pal["texte"],
                                     insertbackground=pal["texte"],
                                     selectbackground=pal["selection"])
                else:
                    widget.configure(bg=pal["fond_zone"], fg=pal["texte"],
                                     selectbackground=pal["selection"])
            except tk.TclError:
                pass

        # calendriers
        for cal in self._calendriers:
            self.recolorer_calendrier(cal)

        # observateurs
        for fonction in self._observateurs:
            try:
                fonction(self.palette)
            except Exception:
                pass

    def recolorer_calendrier(self, cal, annee=None, mois=None):
        """Applique les couleurs au calendrier en gardant la page vue."""
        reglages = dict(CAL_SOMBRE if self.sombre else CAL_CLAIR)
        try:
            if annee is None or mois is None:
                annee, mois = cal.get_displayed_month()
            cal.configure(**reglages)
            cal._style_configure(**reglages) if hasattr(
                cal, "_style_configure") else None
            cal.selection_clear()
            if annee is not None and mois is not None:
                cal.navigate(annee + mois // 12, mois % 12 + 1)
        except Exception:
            pass


# ---------------------------------------------------------------------
#  Aides pour les écrans : couleur et tags de table
# ---------------------------------------------------------------------
_gestionnaire = None


def definir_gestionnaire(g):
    global _gestionnaire
    _gestionnaire = g


def gestionnaire():
    return _gestionnaire


def teinte(widget, option, valeur):
    """Configure une couleur écrite en dur, et la note pour le thème.

    À utiliser à la place de widget.config(foreground="#1f4e5f")."""
    try:
        widget.configure(**{option: valeur})
    except tk.TclError:
        return
    if _gestionnaire is not None:
        _gestionnaire.enregistrer(widget, option, valeur)


def suivre(racine):
    """Mémorise les Treeview existants pour recolorer leurs tags."""
    for enfant in racine.winfo_children():
        suivre(enfant)
