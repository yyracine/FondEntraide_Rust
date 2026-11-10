"""
ui_commun.py — Composants d'interface partagés par les écrans de saisie.
"""
import tkinter as tk
from tkinter import ttk


class CadreDefilant(ttk.Frame):
    """Cadre qui ajoute une barre de defilement verticale si son contenu
    depasse la hauteur disponible. Evite qu'un bouton en bas du formulaire
    devienne inaccessible quand la fenetre est petite."""

    def __init__(self, parent, **kw):
        super().__init__(parent, **kw)
        self.canvas = tk.Canvas(self, highlightthickness=0, borderwidth=0)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.barre = ttk.Scrollbar(self, orient="vertical",
                                   command=self.canvas.yview)
        self.contenu = ttk.Frame(self.canvas)
        self._fenetre = self.canvas.create_window((0, 0), window=self.contenu,
                                                  anchor="nw")
        self.canvas.configure(yscrollcommand=self._sur_scroll)
        self.contenu.bind("<Configure>", self._sur_contenu)
        self.canvas.bind("<Configure>", self._sur_canvas)
        self.canvas.bind("<Enter>", self._activer_molette)
        self.canvas.bind("<Leave>", self._desactiver_molette)

    def _sur_scroll(self, debut, fin):
        if float(debut) <= 0.0 and float(fin) >= 1.0:
            self.barre.pack_forget()
        else:
            self.barre.pack(side="right", fill="y")
        self.barre.set(debut, fin)

    def _sur_contenu(self, _e=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _sur_canvas(self, e):
        self.canvas.itemconfigure(self._fenetre, width=e.width)

    def _activer_molette(self, _e=None):
        self.canvas.bind_all("<MouseWheel>", self._molette)

    def _desactiver_molette(self, _e=None):
        self.canvas.unbind_all("<MouseWheel>")

    def _molette(self, e):
        if self.barre.winfo_ismapped():
            self.canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
