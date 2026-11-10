"""
liste_pdf_mixin.py — Bouton « Liste en PDF » des onglets 1 à 5.

Chaque écran de la hiérarchie (Clans, Grandes familles, Lignées, Familles,
Membres) possède une liste. Ce module fournit une seule méthode commune :
`exporter_liste_pdf()` qui imprime **exactement ce qui est affiché** dans la
liste de l'onglet :

  - colonnes et en-têtes de la vue (ordre, libellés, valeurs formatées) ;
  - filtrage par parent actif (ex. un clan → ses seules grandes familles) ;
  - ligne de total en bas quand elle a un sens (nombres).

Le PDF est déposé dans un dossier choisi par l'utilisateur, puis proposé à
l'ouverture. Aucune donnée de la base n'est modifiée.
"""
import datetime
import os
from tkinter import filedialog, messagebox, ttk

import exports as X


class BoutonListePDF:
    """À mélanger dans un `ttk.Frame` possédant `self.table` (Treeview).

    Attributs attendus : self.table, self.etat, et pour le titre :
    LISTE_TITRE (ou self.TITRE), et facultativement self.var_filtre.
    """

    LISTE_TITRE = "Liste"

    # ------------------------------------------------------------------
    def bouton_liste_pdf(self, parent, **place):
        """Crée le bouton (largeur fixe), le place et le renvoie.

        Le placement est laissé à l'appelant : `place` est transmis tel quel
        à `pack`, le gestionnaire utilisé par les barres de filtre.
        """
        self.btn_liste_pdf = ttk.Button(
            parent, text="Liste en PDF…", width=16,
            command=self.exporter_liste_pdf)
        self.btn_liste_pdf.pack(**place)
        return self.btn_liste_pdf

    # ------------------------------------------------------------------
    def _entetes_liste(self):
        return [self.table.heading(c)["text"] for c in self.table["columns"]]

    def _lignes_liste(self):
        return [list(self.table.item(i, "values"))
                for i in self.table.get_children()]

    def _contexte_liste(self):
        """Sous-titre : filtre actif + date d'édition."""
        morceaux = []
        try:
            filtre = self.var_filtre.get()
        except Exception:
            filtre = ""
        if filtre and not str(filtre).startswith("—"):
            morceaux.append("Filtre : %s" % filtre)
        morceaux.append("édité le %s" %
                        datetime.datetime.now().strftime("%d/%m/%Y %H:%M"))
        return " · ".join(morceaux)

    def _pied_liste(self, entetes, lignes):
        """Ligne de total si au moins une colonne est numérique."""
        if not lignes:
            return None
        pied = []
        numerique = False
        for i, lib in enumerate(entetes):
            total = 0.0
            compte = 0
            for ligne in lignes:
                if i >= len(ligne):
                    continue
                v = str(ligne[i]).replace(" ", "").replace("\u202f", "")
                v = v.replace(",", ".")
                try:
                    total += float(v)
                    compte += 1
                except ValueError:
                    compte = -1
                    break
            if compte == len(lignes) and compte > 0 and i > 0:
                numerique = True
                pied.append(X.format_montant(total)
                            if total == int(total) else
                            ("%s" % X.format_montant(total)))
            else:
                pied.append("Total" if i == 0 else "")
        return pied if numerique else None

    # ------------------------------------------------------------------
    def exporter_liste_pdf(self):
        titre = getattr(self, "LISTE_TITRE", None) or getattr(
            self, "TITRE", "Liste")
        entetes = self._entetes_liste()
        lignes = self._lignes_liste()
        if not lignes:
            messagebox.showinfo(
                "Liste en PDF",
                "La liste de cet onglet est vide : rien à éditer.",
                parent=self)
            return
        dossier = filedialog.askdirectory(
            parent=self, title="Dossier où enregistrer la liste en PDF",
            mustexist=True)
        if not dossier:
            return
        nom = "%s_%s.pdf" % (
            _nom_fichier(titre),
            datetime.datetime.now().strftime("%Y%m%d_%H%M"))
        chemin = os.path.join(dossier, nom)
        try:
            X.liste_pdf(chemin, titre, entetes, lignes,
                        sous_titre=self._contexte_liste(),
                        pied=self._pied_liste(entetes, lignes))
        except X.ErreurExport as e:
            messagebox.showerror("Liste en PDF", str(e), parent=self)
            return
        self.etat.info("%s : %d ligne(s) exportée(s) → %s"
                       % (titre, len(lignes), chemin))
        if messagebox.askyesno(
                "Liste en PDF",
                "Fichier créé :\n%s\n\n%d ligne(s).\n\n"
                "Voulez-vous l'ouvrir maintenant ?" % (chemin, len(lignes)),
                parent=self):
            try:
                os.startfile(chemin)
            except (AttributeError, OSError):
                messagebox.showinfo(
                    "Liste en PDF",
                    "Ouvrez le fichier manuellement :\n%s" % chemin,
                    parent=self)


def _nom_fichier(titre):
    """« Étape 2 — Les grandes familles » -> « liste_grandes_familles »."""
    import re
    base = titre.split("—")[-1].strip().lower()
    for vide in ("les ", "la ", "le ", "l'"):
        if base.startswith(vide):
            base = base[len(vide):]
    base = (base.replace("é", "e").replace("è", "e").replace("ê", "e")
            .replace("à", "a").replace("â", "a").replace("ç", "c")
            .replace("î", "i").replace("ï", "i").replace("ô", "o")
            .replace("û", "u").replace("ù", "u"))
    base = re.sub(r"[^a-z0-9]+", "_", base).strip("_")
    return "liste_" + (base or "elements")
