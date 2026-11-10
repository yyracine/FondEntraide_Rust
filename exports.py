"""
exports.py — Export du tableau de bord en CSV et en PDF.

Aucune dépendance obligatoire :
  - CSV  : module `csv` de la bibliothèque standard, encodage UTF-8 avec BOM
           pour qu'Excel ouvre correctement les accents.
  - PDF  : `reportlab` si installé ; sinon on retombe sur le « PDF virtuel »
           de Windows (Microsoft Print to PDF) qui produit le même résultat.
           Si aucun des deux n'existe, une erreur claire est levée.

Le contenu exporté est décrit par un  objet `Document` :
  - titre, sous-titre
  - une liste de blocs : titre + en-têtes + lignes
On peut donc exporter :
  - un seul tableau (le sous-onglet affiché),
  - ou le tableau de bord complet (les 5 sous-onglets).
"""
import csv
import datetime
import os
import tempfile

# Couleurs du rapport (identiques au thème clair de l'application)
BLEU = "#1f4e5f"
GRIS = "#55606a"
LIGNE = "#c9d4d8"
FOND_ENTETE = "#e8eff1"


class ErreurExport(Exception):
    """Problème empêchant l'écriture du fichier (message affichable)."""


# ---------------------------------------------------------------------
#  Description d'un document
# ---------------------------------------------------------------------
class Bloc:
    """Un tableau : titre + en-têtes + lignes (liste de listes)."""

    def __init__(self, titre, entetes, lignes, pied=None):
        self.titre = titre
        self.entetes = list(entetes)
        self.lignes = [list(l) for l in lignes]
        self.pied = list(pied) if pied else None


class Document:
    def __init__(self, titre, sous_titre="", blocs=None):
        self.titre = titre
        self.sous_titre = sous_titre
        self.blocs = blocs or []

    def ajouter(self, bloc):
        self.blocs.append(bloc)
        return self


# ---------------------------------------------------------------------
#  CSV
# ---------------------------------------------------------------------
def _valeur_csv(v):
    """Un champ vide reste vide ; les nombres deviennent de vrais nombres.

    On retire les espaces de milliers et le symbole %, et la virgule
    décimale devient un point : Excel additionne alors les cellules au
    lieu de les lire comme du texte.
    """
    if v is None:
        return ""
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, (int, float)):
        return v
    s = str(v).strip()
    if not s:
        return ""
    pct = s.endswith("%")
    if pct:
        s = s[:-1].strip()
    s2 = s.replace(" ", "").replace("\u202f", "").replace(",", ".")
    try:
        n = float(s2)
    except ValueError:
        return v
    if pct:
        return round(n / 100, 4)
    return int(n) if n == int(n) else n


def ecrire_csv(doc, chemin, separateur=";"):
    """Écrit le document en CSV (un bloc = une section).

    Le séparateur « ; » est celui qu'attend Excel en configuration
    française ; les nombres restent sans séparateur de milliers pour
    pouvoir être additionnés dans le tableur.
    """
    try:
        with open(chemin, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, delimiter=separateur,
                           quoting=csv.QUOTE_MINIMAL)
            def ecrire(cells):
                """Écrit une ligne : les nombres restent numériques."""
                propre = []
                for v in cells:
                    if (isinstance(v, float) and not isinstance(v, bool)):
                        v = format(v, ".15g")
                    propre.append(v)
                w.writerow(propre)

            w.writerow([doc.titre])
            if doc.sous_titre:
                w.writerow([doc.sous_titre])
            w.writerow([])
            for i, b in enumerate(doc.blocs):
                if i:
                    w.writerow([])
                w.writerow([b.titre])
                w.writerow(b.entetes)
                for ligne in b.lignes:
                    ecrire([_valeur_csv(v) for v in ligne])
                if b.pied:
                    ecrire([_valeur_csv(v) for v in b.pied])
    except OSError as e:
        raise ErreurExport(f"Impossible d'écrire « {chemin} » : {e}") from e
    return chemin


# ---------------------------------------------------------------------
#  PDF — reportlab
# ---------------------------------------------------------------------
def reportlab_disponible():
    try:
        import reportlab  # noqa: F401
    except Exception:
        return False
    return True


def _chaine(v):
    return "" if v is None else str(v)


def _pdf_reportlab(doc, chemin):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (Paragraph, SimpleDocTemplate, Spacer,
                                    Table, TableStyle)

    # Toutes les colonnes ne tiennent pas en portrait : paysage.
    pagesize = landscape(A4)
    marge = 12 * mm

    styles = getSampleStyleSheet()
    # Style « Normal » en base : le style Title de reportlab ajoute un
    # retrait de 12 points qui décalait le titre du tableau.
    st_titre = ParagraphStyle("t", parent=styles["Normal"], fontSize=17,
                              fontName="Helvetica-Bold", leading=21,
                              textColor=colors.HexColor(BLEU),
                              spaceAfter=2, alignment=0)
    st_sous = ParagraphStyle("s", parent=styles["Normal"], fontSize=9.5,
                             textColor=colors.HexColor(GRIS), spaceAfter=8)
    st_bloc = ParagraphStyle("b", parent=styles["Heading2"], fontSize=12,
                             textColor=colors.HexColor(BLEU),
                             spaceBefore=10, spaceAfter=4)
    st_cell = ParagraphStyle("c", parent=styles["Normal"], fontSize=7.2,
                             leading=8.6)
    st_cell_d = ParagraphStyle("cd", parent=st_cell, alignment=2)
    st_ent = ParagraphStyle("e", parent=st_cell, fontName="Helvetica-Bold",
                            textColor=colors.HexColor(BLEU))
    st_ent_d = ParagraphStyle("ed", parent=st_ent, alignment=2)

    largeur_utile = pagesize[0] - 2 * marge

    def tableau(bloc):
        entetes = bloc.entetes
        nb = max(1, len(entetes))
        # Les colonnes numériques sont alignées à droite.
        def est_num(i):
            for ligne in bloc.lignes:
                if i < len(ligne):
                    v = ligne[i]
                    if isinstance(v, (int, float)):
                        return True
                    s = _chaine(v)
                    if s and (s[0].isdigit() or s[0] in "+-"):
                        return True
                    if s:
                        return False
            return False

        num = [est_num(i) for i in range(nb)]
        # Largeur : la première colonne (libellé) prend plus de place.
        poids = [2.6 if i == 0 else (2.0 if i == 1 else 1.0)
                 for i in range(nb)]
        total_poids = sum(poids)
        largeurs = [largeur_utile * p / total_poids for p in poids]

        donnees = [[Paragraph(_chaine(c),
                              st_ent_d if num[i] else st_ent)
                    for i, c in enumerate(entetes)]]
        for ligne in bloc.lignes:
            cel = []
            for i in range(nb):
                v = ligne[i] if i < len(ligne) else ""
                cel.append(Paragraph(_chaine(v),
                                     st_cell_d if num[i] else st_cell))
            donnees.append(cel)
        if bloc.pied:
            cel = []
            for i in range(nb):
                v = bloc.pied[i] if i < len(bloc.pied) else ""
                cel.append(Paragraph(_chaine(v),
                                     st_cell_d if num[i] else st_cell))
            donnees.append(cel)

        t = Table(donnees, colWidths=largeurs, repeatRows=1)
        t.hAlign = "LEFT"
        cmds = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(FOND_ENTETE)),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor(LIGNE)),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("LEFTPADDING", (0, 0), (-1, -1), 3),
            ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ]
        if bloc.pied:
            cmds.append(("BACKGROUND", (0, len(donnees) - 1), (-1, -1),
                         colors.HexColor("#f4f7f8")))
        t.setStyle(TableStyle(cmds))
        return t

    def pied_de_page(canvas, _doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(colors.HexColor(GRIS))
        canvas.drawString(marge, 7 * mm,
                          "Fond d'Entraide — édité le "
                          + datetime.datetime.now().strftime("%d/%m/%Y %H:%M"))
        canvas.drawRightString(pagesize[0] - marge, 7 * mm,
                               "Page %d" % canvas.getPageNumber())
        canvas.restoreState()

    histoire = [Paragraph(doc.titre, st_titre)]
    if doc.sous_titre:
        histoire.append(Paragraph(doc.sous_titre, st_sous))
    for b in doc.blocs:
        histoire.append(Paragraph(b.titre, st_bloc))
        histoire.append(tableau(b))
        histoire.append(Spacer(1, 4))

    try:
        pdf = SimpleDocTemplate(chemin, pagesize=pagesize,
                                leftMargin=marge, rightMargin=marge,
                                topMargin=12 * mm, bottomMargin=14 * mm,
                                title=doc.titre, author="Fond d'Entraide")
        pdf.build(histoire, onFirstPage=pied_de_page,
                  onLaterPages=pied_de_page)
    except Exception as e:
        raise ErreurExport(f"Échec de la création du PDF : {e}") from e
    return chemin


# ---------------------------------------------------------------------
#  PDF — solution de repli portable (aucune dépendance)
# ---------------------------------------------------------------------
def _echapper(t):
    return (str(t).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;"))


def _pdf_minimal(doc, chemin):
    """Génère un PDF paysage A4 avec la police Helvetica, sans dépendance.

    Pagination automatique : on mesure la hauteur de chaque bloc et on
    ouvre une nouvelle page quand ça déborde.
    """
    largeur_page, hauteur_page = 842, 595          # A4 paysage en points
    marge = 34
    bas = 34
    utile = largeur_page - 2 * marge
    # Taille de police réduite quand le tableau a beaucoup de colonnes.
    nb_col_max = max([len(b.entetes) for b in doc.blocs] or [2])
    taille = 7.5 if nb_col_max <= 6 else (6.5 if nb_col_max <= 10 else 5.6)
    interligne = taille * 1.9

    # La police Helvetica n'est pas proportionnelle : ~0,5 em par caractère.
    def largeur_txt(t):
        return len(str(t)) * taille * 0.52

    def colonnes(bloc):
        nb = max(1, len(bloc.entetes))
        poids = [2.6 if i == 0 else (2.0 if i == 1 else 1.0)
                 for i in range(nb)]
        s = sum(poids)
        return [utile * p / s for p in poids]

    def est_num(bloc, i):
        for ligne in bloc.lignes:
            if i < len(ligne):
                v = ligne[i]
                if isinstance(v, (int, float)):
                    return True
                sx = _chaine(v)
                if sx and (sx[0].isdigit() or sx[0] in "+-"):
                    return True
                if sx:
                    return False
        return False

    pages = []      # chaque page : liste d'opérations de dessin
    ops = []

    def nouvelle_page():
        nonlocal ops
        if ops:
            pages.append(ops)
        ops = []

    def texte(x, y, t, taille_=None, gras=False, gris=False, droite=False):
        t = _chaine(t)
        if not t:
            return
        f = "F2" if gras else "F1"
        t = t.encode("cp1252", "replace").decode("cp1252")
        coul = "0.33 0.38 0.42 rg" if gris else "0 0 0 rg"
        x_ = x - largeur_txt(t) if droite else x
        ops.append("BT /%s %.2f Tf %s %.2f %.2f Td (%s) Tj ET"
                   % (f, taille_ or taille, coul, x_, y,
                      t.replace("\\", "\\\\").replace("(", "\\(")
                       .replace(")", "\\)")))

    def trait(x1, y1, x2, y2, gris=0.79):
        ops.append("%.2f %.2f %.2f RG %.2f w %.2f %.2f m %.2f %.2f l S"
                   % (gris, gris, gris, 0.4, x1, y1, x2, y2))

    def rectangle(x, y, w, h, rgb):
        ops.append("%s rg %.2f %.2f %.2f %.2f re f" % (rgb, x, y, w, h))

    y = hauteur_page - marge

    def place(h_necessaire):
        nonlocal y
        if y - h_necessaire < bas:
            nouvelle_page()
            y = hauteur_page - marge

    # ---- titre ----
    taille_titre = 16
    ops.append("BT /F2 %.2f Tf 0.12 0.31 0.37 rg %.2f %.2f Td (%s) Tj ET"
               % (taille_titre, marge, y - taille_titre,
                  _echapper(doc.titre).replace("(", "\\(")
                  .replace(")", "\\)")))
    y -= taille_titre + 10
    if doc.sous_titre:
        ops.append("BT /F1 8.5 Tf 0.33 0.38 0.42 rg %.2f %.2f Td (%s) Tj ET"
                   % (marge, y - 8,
                      _echapper(doc.sous_titre).replace("(", "\\(")
                      .replace(")", "\\)")))
        y -= 16
    y -= 4

    for b in doc.blocs:
        hauteur = interligne * (len(b.lignes) + (1 if b.pied else 0)) + 26
        place(min(hauteur, hauteur_page - 2 * marge))
        # titre du bloc
        ops.append("BT /F2 10.5 Tf 0.12 0.31 0.37 rg %.2f %.2f Td (%s) Tj ET"
                   % (marge, y - 10,
                      _echapper(b.titre).replace("(", "\\(")
                      .replace(")", "\\)")))
        y -= 16

        largs = colonnes(b)
        nb = len(b.entetes)
        # en-tête
        place(interligne * 2)
        rectangle(marge, y - interligne + 2, utile, interligne - 1,
                  "0.91 0.94 0.95")
        x = marge
        for i, c in enumerate(b.entetes):
            droit = i > 0
            texte(x + largs[i] - 2 if droit else x + 2,
                  y - taille - 1, str(c), gras=True, droite=droit)
            x += largs[i]
        trait(marge, y - interligne + 1, marge + utile, y - interligne + 1)
        y -= interligne

        lignes = b.lignes + ([b.pied] if b.pied else [])
        for k, ligne in enumerate(lignes):
            if y - interligne < bas:
                nouvelle_page()
                y = hauteur_page - marge
                # on réaffiche l'en-tête sur la nouvelle page
                rectangle(marge, y - interligne + 2, utile,
                          interligne - 1, "0.91 0.94 0.95")
                x = marge
                for i, c in enumerate(b.entetes):
                    droit = i > 0
                    texte(x + largs[i] - 2 if droit else x + 2,
                          y - taille - 1, str(c), gras=True, droite=droit)
                    x += largs[i]
                trait(marge, y - interligne + 1, marge + utile,
                      y - interligne + 1)
                y -= interligne
            x = marge
            gras = b.pied is not None and k == len(lignes) - 1
            for i in range(nb):
                v = ligne[i] if i < len(ligne) else ""
                droit = i > 0
                texte(x + largs[i] - 2 if droit else x + 2,
                      y - taille - 1, v, gras=gras, droite=droit)
                x += largs[i]
            trait(marge, y - interligne + 1, marge + utile,
                  y - interligne + 1, gris=0.88)
            y -= interligne
        y -= 10

    if ops:
        pages.append(ops)
    if not pages:
        pages = [[]]

    # ---- assemblage du fichier PDF ----
    objets = []          # contenu brut de chaque objet

    def ajouter(contenu):
        objets.append(contenu)
        return len(objets)          # numéro de l'objet (1-based)

    # On réserve d'abord les numéros : 1=Catalogue, 2=Pages, 3=F1, 4=F2
    objets.append("")   # 1 catalogue (rempli après)
    objets.append("")   # 2 pages
    objets.append("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica "
                  "/Encoding /WinAnsiEncoding >>")                 # 3
    objets.append("<< /Type /Font /Subtype /Type1 /BaseFont "
                  "/Helvetica-Bold /Encoding /WinAnsiEncoding >>")  # 4

    # pages : 5 = première page, puis 2 objets par page (contenu, page)
    numeros_pages = []
    for i, ops_page in enumerate(pages):
        corps = "\n".join(ops_page)
        # filigrane : date + numéro de page
        corps += ("\nBT /F1 7.5 Tf 0.33 0.38 0.42 rg %.2f 20 Td "
                  "(Fond d'Entraide - page %d/%d) Tj ET"
                  % (marge, i + 1, len(pages)))
        flux = corps.encode("cp1252", "replace")
        n_contenu = ajouter(
            b"<< /Length %d >>\nstream\n" % len(flux)
            + flux + b"\nendstream")
        n_page = ajouter(
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %d %d] "
            "/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> "
            "/Contents %d 0 R >>" % (largeur_page, hauteur_page, n_contenu))
        numeros_pages.append(n_page)

    objets[1] = ("<< /Type /Pages /Count %d /Kids [%s] >>"
                 % (len(numeros_pages),
                    " ".join("%d 0 R" % n for n in numeros_pages)))
    objets[0] = "<< /Type /Catalog /Pages 2 0 R >>"

    sortie = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    decalages = []
    for i, contenu in enumerate(objets, start=1):
        decalages.append(len(sortie))
        if isinstance(contenu, str):
            contenu = contenu.encode("cp1252", "replace")
        sortie += b"%d 0 obj\n" % i + contenu + b"\nendobj\n"
    pos_xref = len(sortie)
    sortie += b"xref\n0 %d\n" % (len(objets) + 1)
    sortie += b"0000000000 65535 f \n"
    for d in decalages:
        sortie += b"%010d 00000 n \n" % d
    sortie += (b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n"
               % (len(objets) + 1, pos_xref))

    try:
        with open(chemin, "wb") as f:
            f.write(bytes(sortie))
    except OSError as e:
        raise ErreurExport(f"Impossible d'écrire « {chemin} » : {e}") from e
    return chemin


def ecrire_pdf(doc, chemin, moteur="auto"):
    """Écrit le document en PDF.

    moteur : "auto" (reportlab si présent, sinon le moteur minimal),
             "reportlab", "minimal".
    """
    if moteur in ("auto", "reportlab") and reportlab_disponible():
        return _pdf_reportlab(doc, chemin)
    if moteur == "reportlab":
        raise ErreurExport(
            "reportlab n'est pas installé (pip install reportlab).")
    return _pdf_minimal(doc, chemin)


# ---------------------------------------------------------------------
#  Impression
# ---------------------------------------------------------------------
def imprimer(chemin_pdf):
    """Envoie le PDF à l'imprimante par défaut de Windows.

    Utilise l'association système : ouvre le PDF avec le lecteur par défaut
    et lui demande l'impression. Renvoie True si la demande est partie.
    """
    if not os.path.exists(chemin_pdf):
        raise ErreurExport("Le PDF à imprimer n'existe pas.")
    try:
        os.startfile(chemin_pdf, "print")   # Windows : verbe « print »
        return True
    except (AttributeError, OSError):
        pass
    try:                                    # repli : ouvrir le document
        os.startfile(chemin_pdf)
        return True
    except (AttributeError, OSError) as e:
        raise ErreurExport(
            "Impossible de lancer l'impression : aucun lecteur PDF "
            f"associé ({e}).") from e


def chemin_temporaire(nom="tableau_de_bord", ext=".pdf"):
    dossier = tempfile.gettempdir()
    horo = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    return os.path.join(dossier, f"{nom}_{horo}{ext}")


# =====================================================================
#  Reçu de paiement de cotisation
# =====================================================================
def recu_pdf(chemin, donnees, moteur="auto"):
    """Génère le PDF d'un reçu de versement.

    `donnees` est un dictionnaire :
      numero      : n° de reçu (str)
      date        : date du paiement au format JJ/MM/AAAA
      membre      : nom complet du membre
      telephone   : téléphone (ou "")
      clan, famille, grande_famille, lignee : hiérarchie
      exercice    : année de l'exercice
      mois        : liste des mois réglés (libellés courts, ex. ["Jan","Fév"])
      montant     : montant total (float ou int)
      montant_total_lettres : montant en toutes lettres (ou "")
      mode        : libellé du mode de paiement
      en_toutes_lettres : booléen — écrire le montant en lettres
      association : nom de l'association / en-tête (ou "")
      siege       : adresse / ville (ou "")
      saisi_par   : nom du caissier (ou "")
    """
    if moteur in ("auto", "reportlab") and reportlab_disponible():
        return _recu_reportlab(chemin, donnees)
    if moteur == "reportlab":
        raise ErreurExport(
            "reportlab n'est pas installé (pip install reportlab).")
    return _recu_minimal(chemin, donnees)


def format_montant(montant):
    """« 3000.0 » -> « 3 000 » (affichage français, sans décimale inutile)."""
    try:
        valeur = float(montant)
    except (TypeError, ValueError):
        return str(montant)
    if valeur == int(valeur):
        return f"{int(valeur):,}".replace(",", " ")
    return f"{valeur:,.2f}".replace(",", " ").replace(".", ",")


def _recu_reportlab(chemin, d):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (Paragraph, SimpleDocTemplate, Spacer,
                                    Table, TableStyle)

    pagesize = landscape(A4)
    marge = 14 * mm
    width, _height = pagesize

    styles = getSampleStyleSheet()
    entete = ParagraphStyle("e", parent=styles["Normal"], fontSize=12,
                            fontName="Helvetica-Bold",
                            textColor=colors.HexColor(BLEU), alignment=1)
    centre = ParagraphStyle("c", parent=styles["Normal"], fontSize=9,
                            alignment=1)
    gros = ParagraphStyle("g", parent=styles["Normal"], fontSize=15,
                          fontName="Helvetica-Bold",
                          textColor=colors.HexColor(BLEU), alignment=1,
                          spaceBefore=6, spaceAfter=2)
    champ = ParagraphStyle("ch", parent=styles["Normal"], fontSize=10,
                           leading=13)
    ligne = ParagraphStyle("li", parent=styles["Normal"], fontSize=10,
                           leading=13)

    hist = [Paragraph(d.get("association") or "FOND D'ENTRAIDE", entete)]
    if d.get("siege"):
        hist.append(Paragraph(d["siege"], centre))
    hist.append(Spacer(1, 4))
    hist.append(Paragraph("REÇU DE PAIEMENT DE COTISATION", gros))
    hist.append(Paragraph("N° %s" % d.get("numero", ""), centre))
    hist.append(Spacer(1, 6))

    montant_lettres = d.get("montant_total_lettres") or ""
    cadre = Table(
        [[Paragraph("REÇU DE %s" % str(d["membre"]).upper(), ligne)],
         [Paragraph(montant_lettres, champ)]],
        colWidths=[width - 2 * marge])
    cadre.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 1.2, colors.HexColor(BLEU)),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#f4f7f8")),
    ]))
    hist.append(cadre)
    hist.append(Spacer(1, 6))

    cols_d = [58 * mm, 46 * mm, 58 * mm, width - 2 * marge - 162 * mm]
    recap = Table(
        [[Paragraph("ÉLÉMENT", ligne), Paragraph("DÉTAIL", ligne),
          Paragraph("ÉLÉMENT", ligne), Paragraph("DÉTAIL", ligne)],
         [Paragraph("Membre", champ), Paragraph(d["membre"], champ),
          Paragraph("Exercice", champ), Paragraph(str(d["exercice"]), champ)],
         [Paragraph("Clan", champ),
          Paragraph(str(d.get("clan", "")), champ),
          Paragraph("Grande famille", champ),
          Paragraph(str(d.get("grande_famille", "")), champ)],
         [Paragraph("Lignée", champ), Paragraph(str(d.get("lignee", "")), champ),
          Paragraph("Famille", champ), Paragraph(str(d.get("famille", "")), champ)],
         [Paragraph("Mode de paiement", champ),
          Paragraph(str(d.get("mode", "")), champ),
          Paragraph("Date", champ), Paragraph(str(d.get("date", "")), champ)],
         [Paragraph("Mois réglés", champ),
          Paragraph(", ".join(d["mois"]) or "—", champ),
          Paragraph("Montant total", champ),
          Paragraph("%s FCFA" % format_montant(d["montant"]), champ)]],
        colWidths=cols_d)
    recap.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor(LIGNE)),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(FOND_ENTETE)),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    hist.append(recap)
    hist.append(Spacer(1, 14))

    sig = Table(
        [[Paragraph("Le membre", champ),
          Paragraph("Le caissier / %s" % (d.get("saisi_par") or "la caisse"),
                    champ)],
         [Paragraph("", champ), Paragraph("", champ)],
         [Paragraph("", champ), Paragraph("", champ)]],
        colWidths=[(width - 2 * marge) / 2.0] * 2)
    sig.setStyle(TableStyle([
        ("LINEBELOW", (0, 1), (-1, -1), 0.6, colors.HexColor(GRIS)),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
    ]))
    hist.append(sig)

    def pied(c, _doc):
        c.saveState()
        c.setFont("Helvetica", 7.5)
        c.setFillColor(colors.HexColor(GRIS))
        c.drawString(marge, 6 * mm,
                     "Reçu N° %s — généré le %s" % (
                         d.get("numero", ""),
                         datetime.datetime.now().strftime("%d/%m/%Y %H:%M")))
        c.restoreState()

    try:
        pdf = SimpleDocTemplate(chemin, pagesize=pagesize,
                                leftMargin=marge, rightMargin=marge,
                                topMargin=12 * mm, bottomMargin=12 * mm,
                                title="Reçu N° %s" % d.get("numero", ""),
                                author="Fond d'Entraide")
        pdf.build(hist, onFirstPage=pied)
    except Exception as e:
        raise ErreurExport(f"Échec de la création du reçu : {e}") from e
    return chemin


def _recu_minimal(chemin, d):
    """Reçu PDF généré par le moteur interne (aucune dépendance)."""
    width, height = 842, 595     # A4 paysage
    marge = 36
    utile = width - 2 * marge
    taille = 9
    ligne_h = taille * 2.05
    x = marge
    ops = []

    def echappe(t):
        return (str(t).replace("\\", "\\\\").replace("(", "\\(")
                .replace(")", "\\)").replace(
                    "\u00e9\u00e8\u00ea\u00e0\u00e2\u00e7\u00ee\u00f4\u00fb"
                    , ""))

    def largeur(t, taille_=None):
        """Largeur estimée en points (Helvetica : 0,52 em par caractère,
        les capitales et les accents sont plus larges)."""
        t = str(t)
        moy = 0.0
        for ch in t:
            if ch.isupper():
                moy += 0.66
            elif ch in "il.,:;'!| ":
                moy += 0.28
            else:
                moy += 0.52
        return moy * (taille_ or taille)

    def texte(y, t, taille_=None, gras=False, gris=False, x_=None,
              centrer_sur=None):
        t = str(t)
        plt = x_ if x_ is not None else x
        if centrer_sur is not None:
            # largeur réelle du texte à CETTE taille de police
            plt = centrer_sur - largeur(t, taille_ or taille) / 2.0
        f = "F2" if gras else "F1"
        coul = "0.33 0.38 0.42 rg" if gris else "0 0 0 rg"
        ops.append("BT /%s %.2f Tf %s %.2f %.2f Td (%s) Tj ET"
                   % (f, taille_ or taille, coul, plt, y, echappe(t)))

    def trait(y, x1=None, x2=None):
        xa = x1 if x1 is not None else marge
        xb = x2 if x2 is not None else marge + utile
        ops.append("0.79 0.79 0.79 RG 0.5 w %.2f %.2f m %.2f %.2f l S"
                   % (xa, y, xb, y))

    def cadre(y, h):
        ops.append("0.12 0.31 0.37 RG 1 w %.2f %.2f %.2f %.2f re S"
                   % (marge, y, utile, h))

    y = height - marge
    milieu = marge + utile / 2
    texte(y, d.get("association") or "FOND D'ENTRAIDE", 12, True,
          centrer_sur=milieu)
    y -= 13
    if d.get("siege"):
        texte(y, d["siege"], 8, gris=True, centrer_sur=milieu)
        y -= 13
    y -= 6
    texte(y, "REÇU DE PAIEMENT DE COTISATION", 15, True,
          centrer_sur=milieu)
    y -= 17
    texte(y, "N° %s" % d.get("numero", ""), 10, gris=True,
          centrer_sur=milieu)
    y -= 22

    h = 46
    cadre(y, h)
    texte(y + h - 24, "REÇU DE %s" % str(d["membre"]).upper(), 11, True,
          x_=marge + 12)
    texte(y + h - 44, d.get("montant_total_lettres") or "", 9,
          x_=marge + 12)
    y -= h + 12

    trait(y - 4)
    texte(y - 2, "Date : %s" % d.get("date", ""), 10, x_=marge)
    texte(y - 2, "N° : %s" % d.get("numero", ""), 10, x_=marge + 150)
    y -= 18
    trait(y)

    def champ(lib, val):
        nonlocal y
        texte(y, lib, 9, gras=True, x_=marge + 4)
        texte(y, val, 9, x_=marge + 138)
        y -= ligne_h

    champ("Membre", d["membre"])
    champ("Clan / Grande famille",
          "%s / %s" % (d.get("clan", ""), d.get("grande_famille", "")))
    champ("Lignée / Famille",
          "%s / %s" % (d.get("lignee", ""), d.get("famille", "")))
    champ("Exercice", str(d["exercice"]))
    champ("Mois réglés", ", ".join(d["mois"]) or "—")
    champ("Mode de paiement", d["mode"])
    champ("Montant total",
          d.get("montant_total_lettres") or
          "%s FCFA" % format_montant(d["montant"]))
    trait(y - 4)
    y -= 26

    texte(y, "Le membre", 9, gras=True, x_=marge)
    texte(y, "Le caissier / %s" % (d.get("saisi_par") or "la caisse"), 9,
          gras=True, x_=marge + utile / 2)
    trait(y - 40, marge, marge + utile / 2 - 8)
    trait(y - 40, marge + utile / 2 + 8, marge + utile)

    ops.append("BT /F1 7.5 Tf 0.33 0.38 0.42 rg %.2f 24 Td "
               "(Reçu N° %s - généré le %s) Tj ET"
               % (marge, d.get("numero", ""),
                  datetime.datetime.now().strftime("%d/%m/%Y %H:%M")))

    contenu = "\n".join(ops).encode("cp1252", "replace")
    objets = [
        "", "",
        "<< /Length %d >>\nstream\n" % len(contenu) + contenu.decode(
            "latin-1") + "\nendstream",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %d %d] "
        "/Resources << /Font << /F1 5 0 R /F2 6 0 R >> >> "
        "/Contents 3 0 R >>" % (width, height),
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica "
        "/Encoding /WinAnsiEncoding >>",
        "<< /Type /Font /Subtype /Type1 /BaseFont "
        "/Helvetica-Bold /Encoding /WinAnsiEncoding >>",
        "<< /Type /Pages /Count 1 /Kids [4 0 R] >>",
        "<< /Type /Catalog /Pages 2 0 R >>",
    ]
    # ordre : 1 catalogue, 2 pages, 3 contenu, 4 page, 5 F1, 6 F2
    objets[0] = objets[7]
    objets[1] = objets[6]
    obj_utiles = [objets[0], objets[1], objets[2], objets[3],
                  objets[4], objets[5]]

    sortie = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for i, o in enumerate(obj_utiles, start=1):
        offsets.append(len(sortie))
        if isinstance(o, str):
            o = o.encode("cp1252", "replace")
        sortie += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    pos = len(sortie)
    sortie += b"xref\n0 %d\n" % (len(obj_utiles) + 1)
    sortie += b"0000000000 65535 f \n"
    for off in offsets:
        sortie += b"%010d 00000 n \n" % off
    sortie += (b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n"
               % (len(obj_utiles) + 1, pos))
    try:
        with open(chemin, "wb") as f:
            f.write(bytes(sortie))
    except OSError as e:
        raise ErreurExport(f"Impossible d'écrire « {chemin} » : {e}") from e
    return chemin


# =====================================================================
#  Listes d'onglets (Clans, Grandes familles, Lignées, Familles, Membres)
# =====================================================================
def _texte_largeur(t, taille, gras=False):
    """Largeur estimée d'un texte en points (police Helvetica)."""
    total = 0.0
    for ch in str(t):
        if ch.isupper():
            total += 0.70 if gras else 0.66
        elif ch in "il.,:;'!| ":
            total += 0.28
        else:
            total += 0.54 if gras else 0.52
    return total * taille


def _colonnes_adaptees(entetes, lignes, utile):
    """Répartit la largeur utile selon le contenu réel des colonnes.

    On part de la largeur du plus long contenu, en tenant compte de la
    proportion de cellules vides : une colonne vide aux trois quarts n'a
    pas besoin de la largeur d'un seul nom long. La première colonne
    (libellé) garde un peu de marge.
    """
    nb = len(entetes)
    poids = []
    for i, e in enumerate(entetes):
        largeur_max = _texte_largeur(e, 8, gras=True)
        largeur_moy = 0.0
        remplis = 0
        for ligne in lignes[:400]:
            if i < len(ligne):
                v = _chaine(ligne[i])
                if v:
                    remplis += 1
                    largeur_moy += _texte_largeur(v, 7.2)
                    largeur_max = max(largeur_max, _texte_largeur(v, 7.2))
        if remplis:
            largeur_moy /= remplis
        # largeur utile = moyenne + un peu de place pour les valeurs longues
        poids.append(max((largeur_moy + largeur_max) / 2.0 + 10, 30.0))
    # une petite prime à la première colonne (souvent un libellé)
    if nb > 1:
        poids[0] *= 1.15
    somme = sum(poids) or 1.0
    return [utile * p / somme for p in poids]


def _couper_texte(t, largeur, taille):
    """Tronque un texte trop long pour sa colonne (avec « … »)."""
    t = str(t)
    if _texte_largeur(t, taille) <= largeur - 6:
        return t
    while t and _texte_largeur(t + "…", taille) > largeur - 6:
        t = t[:-1]
    return t + "…"


def liste_pdf(chemin, titre, entetes, lignes, sous_titre="",
              pied=None, orientation="auto", moteur="auto"):
    """Écrit une liste (un seul tableau) en PDF, une ligne par élément.

    orientation : "auto" choisit le paysage dès 5 colonnes ou quand le
                  contenu est large ; "portrait" / "paysage" forcent.
    pied        : ligne de total optionnelle (liste de valeurs).
    """
    if moteur in ("auto", "reportlab") and reportlab_disponible():
        try:
            return _liste_reportlab(chemin, titre, entetes, lignes,
                                    sous_titre, pied, orientation)
        except Exception as e:
            if moteur == "reportlab":
                raise ErreurExport(
                    f"Échec de la création du PDF : {e}") from e
    return _liste_minimal(chemin, titre, entetes, lignes, sous_titre,
                          pied, orientation)


def _choisir_orientation(orientation, entetes, lignes):
    """Portrait ou paysage selon le nombre et la largeur des colonnes.

    Le portrait A4 laisse environ 500 points utiles ; au-delà, on passe en
    paysage (700 points). Cinq colonnes ou plus partent directement en
    paysage : c'est plus lisible pour des listes de membres.
    """
    if orientation in ("portrait", "paysage"):
        return orientation
    if len(entetes) >= 5:
        return "paysage"
    estime = 0.0
    for i in range(len(entetes)):
        largeur_col = _texte_largeur(entetes[i], 7.6, gras=True)
        for r in lignes[:300]:
            if i < len(r):
                largeur_col = max(largeur_col, _texte_largeur(r[i], 7.4))
        estime += largeur_col + 16          # marge interne + filet
    return "paysage" if estime > 500 else "portrait"


def _liste_reportlab(chemin, titre, entetes, lignes, sous_titre, pied,
                     orientation):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (Paragraph, SimpleDocTemplate,
                                    Table, TableStyle)

    pagesize = landscape(A4) if _choisir_orientation(
        orientation, entetes, lignes) == "paysage" else A4
    marge = 12 * mm
    utile = pagesize[0] - 2 * marge

    styles = getSampleStyleSheet()
    st_titre = ParagraphStyle("t", parent=styles["Normal"], fontSize=15,
                              fontName="Helvetica-Bold", leading=19,
                              textColor=colors.HexColor(BLEU),
                              spaceAfter=2, alignment=0)
    st_sous = ParagraphStyle("s", parent=styles["Normal"], fontSize=9,
                             textColor=colors.HexColor(GRIS), spaceAfter=8)
    st_cell = ParagraphStyle("c", parent=styles["Normal"], fontSize=7.4,
                             leading=9)
    st_cell_d = ParagraphStyle("cd", parent=st_cell, alignment=2)
    st_cell_c = ParagraphStyle("cc", parent=st_cell, alignment=1)
    st_ent = ParagraphStyle("e", parent=st_cell, fontName="Helvetica-Bold",
                            fontSize=7.6, textColor=colors.HexColor(BLEU))

    def est_num(i):
        for r in lignes:
            if i < len(r):
                v = r[i]
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    return True
                s = _chaine(v)
                if s and (s[0].isdigit() or s[0] in "+-"):
                    return True
                if s:
                    return False
        return False

    # colonnes courtes (nombres, ordre, statut) centrées, autres à gauche
    def courte(i):
        if not lignes:
            return False
        longueurs = [len(_chaine(r[i])) for r in lignes
                     if i < len(r) and _chaine(r[i])]
        if not longueurs:
            return True
        return max(longueurs) <= 12 and (sum(longueurs) / len(longueurs)) <= 9

    largeurs = _colonnes_adaptees(entetes, lignes, utile)
    donnees = [[Paragraph(_chaine(c), st_ent) for c in entetes]]
    for r in lignes:
        cel = []
        for i in range(len(entetes)):
            v = r[i] if i < len(r) else ""
            st = st_cell_d if est_num(i) else (st_cell_c if courte(i)
                                               else st_cell)
            cel.append(Paragraph(_chaine(v), st))
        donnees.append(cel)
    if pied:
        cel = []
        for i in range(len(entetes)):
            v = pied[i] if i < len(pied) else ""
            st = st_cell_d if est_num(i) else (st_cell_c if courte(i)
                                               else st_cell)
            cel.append(Paragraph("<b>%s</b>" % _chaine(v), st))
        donnees.append(cel)

    t = Table(donnees, colWidths=largeurs, repeatRows=1)
    t.hAlign = "LEFT"
    cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(FOND_ENTETE)),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor(LIGNE)),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1),
         [colors.white, colors.HexColor("#fbfcfc")]),
    ]
    if pied:
        cmds.append(("BACKGROUND", (0, len(donnees) - 1), (-1, -1),
                     colors.HexColor("#f4f7f8")))
    t.setStyle(TableStyle(cmds))

    hist = [Paragraph(titre, st_titre)]
    if sous_titre:
        hist.append(Paragraph(sous_titre, st_sous))
    hist.append(t)

    def page(c, doc_):
        c.saveState()
        c.setFont("Helvetica", 7.5)
        c.setFillColor(colors.HexColor(GRIS))
        c.drawString(marge, 7 * mm,
                     "Fond d'Entraide — %s" %
                     datetime.datetime.now().strftime("%d/%m/%Y %H:%M"))
        c.drawRightString(pagesize[0] - marge, 7 * mm,
                          "Page %d" % c.getPageNumber())
        c.restoreState()

    try:
        pdf = SimpleDocTemplate(chemin, pagesize=pagesize,
                                leftMargin=marge, rightMargin=marge,
                                topMargin=12 * mm, bottomMargin=14 * mm,
                                title=titre, author="Fond d'Entraide")
        pdf.build(hist, onFirstPage=page, onLaterPages=page)
    except Exception as e:
        raise ErreurExport(
            f"Échec de la création du PDF (« {titre} ») : {e}") from e
    return chemin


def _liste_minimal(chemin, titre, entetes, lignes, sous_titre, pied,
                   orientation):
    """Version sans dépendance : paysage A4, texte tronqué aux colonnes."""
    paysage = _choisir_orientation(orientation, entetes, lignes) == "paysage"
    largeur_page, hauteur_page = (842, 595) if paysage else (595, 842)
    marge = 30
    bas = 30
    utile = largeur_page - 2 * marge
    nb = max(1, len(entetes))
    taille = 8.0 if nb <= 5 else (7.0 if nb <= 7 else 6.2)
    interligne = taille * 2.1
    largeurs = _colonnes_adaptees(entetes, lignes, utile)

    pages = []
    ops = []
    y = hauteur_page - marge

    def nouvelle_page():
        nonlocal ops, y
        if ops:
            pages.append(ops)
        ops = []
        y = hauteur_page - marge
        entete()

    def ecrit(x, yy, t, gras=False, taille_=None):
        t = str(t)
        if not t:
            return
        f = "F2" if gras else "F1"
        ops.append("BT /%s %.2f Tf 0 0 0 rg %.2f %.2f Td (%s) Tj ET"
                   % (f, taille_ or taille, x, yy,
                      t.replace("\\", "\\\\").replace("(", "\\(")
                       .replace(")", "\\)")))

    def trait(yy, gris="0.82"):
        ops.append("%s %s %s RG 0.4 w %.2f %.2f m %.2f %.2f l S"
                   % (gris, gris, gris, marge, yy, marge + utile, yy))

    def entete():
        nonlocal y
        ops.append("0.91 0.94 0.95 rg %.2f %.2f %.2f %.2f re f"
                   % (marge, y - interligne + 1, utile, interligne))
        x = marge
        for i, e in enumerate(entetes):
            ecrit(x + 3, y - taille - 1,
                  _couper_texte(e, largeurs[i], taille), gras=True)
            x += largeurs[i]
        trait(y - interligne + 1, "0.65")
        y -= interligne

    # titre + sous-titre
    ops.append("BT /F2 15 Tf 0.12 0.31 0.37 rg %.2f %.2f Td (%s) Tj ET"
               % (marge, y - 15, titre.replace("(", "\\(").replace(")", "\\)")))
    y -= 22
    if sous_titre:
        ops.append("BT /F1 8.5 Tf 0.33 0.38 0.42 rg %.2f %.2f Td (%s) Tj ET"
                   % (marge, y - 8, sous_titre.replace("(", "\\(")
                      .replace(")", "\\)")))
        y -= 14
    y -= 6
    entete()

    corps = list(lignes) + ([pied] if pied else [])
    for k, ligne in enumerate(corps):
        if y - interligne < bas:
            nouvelle_page()
        x = marge
        gras = pied is not None and k == len(corps) - 1
        for i in range(nb):
            v = ligne[i] if i < len(ligne) else ""
            ecrit(x + 3, y - taille - 1,
                  _couper_texte(v, largeurs[i], taille), gras=gras)
            x += largeurs[i]
        trait(y - interligne + 1)
        y -= interligne

    # pied de page sur chaque page
    for i, ops_page in enumerate(pages if ops in pages else pages + [ops]):
        ops_page.append(
            "BT /F1 7.5 Tf 0.33 0.38 0.42 rg %.2f 16 Td "
            "(Fond d'Entraide - page %d/%d) Tj ET"
            % (marge, i + 1, max(1, len(pages) + (1 if ops else 0))))

    toutes = pages if ops in pages else pages + [ops]
    if not toutes:
        toutes = [[]]

    objets = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica "
        "/Encoding /WinAnsiEncoding >>",
        "<< /Type /Font /Subtype /Type1 /BaseFont "
        "/Helvetica-Bold /Encoding /WinAnsiEncoding >>",
    ]
    numeros = []
    for ops_page in toutes:
        flux = "\n".join(ops_page).encode("cp1252", "replace")
        objets.append("<< /Length %d >>\nstream\n" % len(flux)
                      + flux.decode("latin-1") + "\nendstream")
        n_contenu = len(objets)
        objets.append(
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %d %d] "
            "/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> "
            "/Contents %d 0 R >>" % (largeur_page, hauteur_page, n_contenu))
        numeros.append(len(objets))
    objets[1] = ("<< /Type /Pages /Count %d /Kids [%s] >>"
                 % (len(numeros), " ".join("%d 0 R" % n for n in numeros)))

    sortie = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for i, o in enumerate(objets, start=1):
        offsets.append(len(sortie))
        if isinstance(o, str):
            o = o.encode("cp1252", "replace")
        sortie += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    pos = len(sortie)
    sortie += b"xref\n0 %d\n" % (len(objets) + 1)
    sortie += b"0000000000 65535 f \n"
    for off in offsets:
        sortie += b"%010d 00000 n \n" % off
    sortie += (b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n"
               % (len(objets) + 1, pos))
    try:
        with open(chemin, "wb") as f:
            f.write(bytes(sortie))
    except OSError as e:
        raise ErreurExport(f"Impossible d'écrire « {chemin} » : {e}") from e
    return chemin
