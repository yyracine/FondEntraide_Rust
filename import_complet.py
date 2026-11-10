#!/usr/bin/env python3
"""
Import COMPLET des 46 feuilles du classeur
« FONDS D'ENTRE AIDE Final MAJ 3 Aout 24 (1).xlsx » vers cotisations.db

Hiérarchie lue dans le classeur :
    Clan             <- cellule A1, préfixe "Famille"/"LIGNEE" retiré
    Grande famille   <- nom de la feuille
    Lignée           <- cellule A3 ou A4 ("Descendants  XXX")
    Famille          <- 1er membre nommé après chaque bloc (voir plus bas)
    Membre           <- chaque ligne portant un nom réel (col A, B ou C)

Motif d'une feuille de cotisation :
    lignes 1-4 : titres + en-tête des mois
       D..O  = Janv..Déc 2024   (Total en P)
       Q..AB = Janv..Déc 2025   (Total en AC)
       AD..AO= Janv..Déc 2026   (Total en AP)
    ligne 5+  : l'arbre. Colonne remplie => niveau.
       A = membre / tête de famille      (niveau 1)
       B = enfant                        (niveau 2)
       C = petit-enfant                  (niveau 3)
       "TOTAL xxx" => clôture d'un bloc : le prochain nom en A
                      ouvre une NOUVELLE FAMILLE.

Les libellés de type "(Penfant 21)" / "(APenfant211)" SANS NOM sont ignorés.
Le marqueur "(Enfant4)" est retiré du nom ; le numéro va dans ordre_fratrie.
"""
import re
import sqlite3
import unicodedata
from pathlib import Path

import openpyxl

BASE = Path(__file__).parent
XLSX = Path(r"C:/Users/HP/Documents/Fond Entraide Revise/FONDS D'ENTRE AIDE Final MAJ 3 Aout 24 (1).xlsx")
DB = BASE / "cotisations.db"
SQL = BASE / "schema.sql"

SHEET_RECAP = "TOTAL GENERAL COTISATIONS"
# Feuilles sans colonnes de cotisation : listes de noms, on les ignore.
SHEETS_A_IGNORER = {"AGOH", "KOUADIO AMBOFF", "YAOCRE", "ADJOUA MALA",
                    "TCHOUWA", "KACOUTIE EDJAPA", "ASSOMOU"}

MOIS_2024 = list(range(4, 16))    # D..O
MOIS_2025 = list(range(17, 29))   # Q..AB
MOIS_2026 = list(range(30, 42))   # AD..AO

PLACEHOLDER = re.compile(r"^(?:X{2,}|Y{2,}|Z{2,}|AMY|XXX+)$", re.I)
# Un libellé qui n'est QUE un marqueur : (Penfant 21), (APenfant211), (Enfant1)
RE_MARQUEUR_SEUL = re.compile(r"^\(?\s*A?P?enfant\s*[\d\s]+\)?$", re.I)
RE_MARQUEUR_TETE = re.compile(r"^\(\s*A?P?[Ee]nfant\s*[\d\s]+\)", re.I)
RE_TOTAL = re.compile(r"^\s*total\b", re.I)
RE_PREFIXE_CLAN = re.compile(r"^\s*(?:famille|lign[ée]e)\s+", re.I)

# Separasites utilises dans l'Excel pour dire "meme famille que la ligne
# du dessus" : / \ - . , ; : * + ' etc. (formes pleine largeur incluses).
RE_PARASITES = re.compile(r"^[\s/\\-–—.,;:*+'’·|_]+")


# ----------------------------------------------------------------- utilitaires
def nettoie(txt):
    if txt is None:
        return None
    s = re.sub(r"\s+", " ", str(txt).replace("\u00a0", " ")).strip()
    return s or None


def cle(txt):
    if not txt:
        return ""
    s = unicodedata.normalize("NFKD", str(txt))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^A-Za-z0-9]+", " ", s).strip().upper()


def nom_lignee(ws):
    """Nom de lignée = A3 sinon A4, préfixe 'Descendants' retiré."""
    for r in (3, 4):
        v = nettoie(ws.cell(row=r, column=1).value)
        if not v:
            continue
        v = re.sub(r"^\s*descendants?\s*", "", v, flags=re.I).strip()
        if v:
            return v
    return None


def nom_clan(ws):
    """Clan = A1, préfixe 'Famille'/'LIGNEE' retiré."""
    v = nettoie(ws.cell(row=1, column=1).value)
    if not v:
        return None
    return RE_PREFIXE_CLAN.sub("", v).strip() or None


def nettoie_personne(label):
    """Retire le marqueur (EnfantN) du libelle. Renvoie (nom, prenom, ordre) ou None.

    Un libelle qui commence par "/" ou un autre separateur parasite est
    d'abord debarrasse de ces caracteres : l'Excel s'en sert pour signifier
    "meme famille que la ligne du dessus". Si le libelle ne contient plus
    qu'un seul mot, ce mot est un PRENOM et non un nom : on renvoie un nom
    vide (None) pour que l'appelant herite du nom du parent. C'est ce qui
    evite les noms valant "/" ou "/APPIA".
    """
    s = label.strip()
    ordre = None
    m = re.search(r"\(\s*A?P?[Ee]nfant\s*(\d+)\s*\)", s, re.I)
    if m:
        ordre = int(m.group(1))
        s = RE_MARQUEUR_TETE.sub("", s, count=1).strip()
    s = re.sub(r"^[\(\s]+|[\)\s]+$", "", s)
    # "/APPIA CYNTHIA" -> "APPIA CYNTHIA" ; "/ APPIA SEWA" -> "APPIA SEWA"
    parasite_en_tete = bool(RE_PARASITES.match(s))
    s = RE_PARASITES.sub("", s).strip()
    s = nettoie(s)
    if not s or RE_MARQUEUR_SEUL.match(s):
        return None
    parts = s.split(" ", 1)
    nom = parts[0].strip()
    prenom = parts[1].strip() if len(parts) > 1 else None
    # un seul mot apres un "/" : c'est un prenom, le nom viendra du parent
    if parasite_en_tete and prenom is None:
        return None, nom, ordre
    if not nom or PLACEHOLDER.match(nom) or (prenom and PLACEHOLDER.match(prenom)):
        return None
    return nom, prenom, ordre

def lit_montants(row):
    """Renvoie [(annee, mois, montant), ...] pour une ligne Excel."""
    out = []
    for annee, cols in ((2024, MOIS_2024), (2025, MOIS_2025), (2026, MOIS_2026)):
        for idx, col in enumerate(cols, start=1):
            if col - 1 < len(row):
                v = row[col - 1]
                if isinstance(v, (int, float)) and v > 0:
                    out.append((annee, idx, float(v)))
    return out


# --------------------------------------------------------------------- import
def main():
    wb = openpyxl.load_workbook(XLSX, data_only=True)

    if DB.exists():
        DB.unlink()
    con = sqlite3.connect(DB)
    con.executescript(SQL.read_text(encoding="utf-8"))
    cur = con.cursor()

    # campagnes
    campagnes = {}
    for annee in (2024, 2025, 2026):
        cur.execute("INSERT INTO campagnes (libelle,annee,montant_mensuel,devise,statut)"
                    " VALUES (?,?,?,?,?)",
                    (f"Campagne {annee}", annee, 1000, "FCFA",
                     "ouverte" if annee == 2026 else "fermee"))
        campagnes[annee] = cur.lastrowid

    clans, gf, lig = {}, {}, {}
    tot_membres = tot_paiements = 0
    rapport = []

    feuilles = [s for s in wb.sheetnames if s != SHEET_RECAP]
    for nom_feuille in feuilles:
        ws = wb[nom_feuille]

        # feuille-répertoire : pas de grille de mois
        if nom_feuille in SHEETS_A_IGNORER:
            rapport.append((nom_feuille, "IGNOREE (répertoire)", 0, 0, 0))
            continue

        clan_nom = nom_clan(ws) or "INCONNU"
        lignee_nom = nom_lignee(ws) or nom_feuille

        # --- Clan
        if clan_nom not in clans:
            cur.execute("INSERT INTO clans (nom) VALUES (?)", (clan_nom,))
            clans[clan_nom] = cur.lastrowid
        clan_id = clans[clan_nom]

        # --- Grande famille (nom de feuille)
        gkey = (clan_id, nom_feuille.strip())
        if gkey not in gf:
            cur.execute("INSERT INTO grandes_familles (clan_id, nom) VALUES (?,?)",
                        (clan_id, nom_feuille.strip()))
            gf[gkey] = cur.lastrowid
        gf_id = gf[gkey]

        # --- Lignée
        lkey = (gf_id, lignee_nom)
        if lkey not in lig:
            cur.execute("INSERT INTO lignees (grande_famille_id, nom) VALUES (?,?)",
                        (gf_id, lignee_nom))
            lig[lkey] = cur.lastrowid
        lig_id = lig[lkey]

        # --- Familles de la lignée
        ordre_famille = 0
        famille_courante = None      # id dans la table familles
        dernier_membre = None        # dernier membre "niveau 1" = parent potentiel
        apres_total = True           # au début, un nom en A ouvre une famille

        rows = list(ws.iter_rows(values_only=True))
        nb_m = nb_p = total_fcfa = 0

        for i, row in enumerate(rows, start=1):
            if i <= 4:
                continue
            a = nettoie(row[0]) if len(row) > 0 else None
            b = nettoie(row[1]) if len(row) > 1 else None
            c = nettoie(row[2]) if len(row) > 2 else None
            label = a or b or c
            if not label:
                continue
            if RE_TOTAL.match(label):
                apres_total = True
                continue

            who = nettoie_personne(label)
            if not who:
                continue                     # (Penfant 21) seul -> ignoré
            nom, prenom, ordre = who

            niveau = 1 if a else (2 if b else 3)

            # --- Nouvelle famille si nom en A juste après un TOTAL
            if niveau == 1 and apres_total:
                ordre_famille += 1
                cur.execute("INSERT INTO familles (lignee_id, nom, ordre) VALUES (?,?,?)",
                            (lig_id, f"{nom} {prenom or ''}".strip(), ordre_famille))
                famille_courante = cur.lastrowid
                dernier_membre = None
                apres_total = False

            if famille_courante is None:      # sécurité
                continue

            # parent = dernier membre de niveau 1 (pour les niveaux 2/3)
            parent_id = dernier_membre if niveau > 1 else None

            cur.execute(
                "INSERT INTO membres (famille_id, parent_id, nom, prenom,"
                " ordre_fratrie, statut, notes) VALUES (?,?,?,?,?,?,?)",
                (famille_courante, parent_id, nom, prenom, ordre,
                 "actif", f"F{nom_feuille.strip()} L{i}"))
            mid = cur.lastrowid
            nb_m += 1
            if niveau == 1:
                dernier_membre = mid

            # --- cotisations
            payes = lit_montants(row)
            if payes:
                total = sum(m for _, _, m in payes)
                total_fcfa += total
                dernier_mois = max(mm for _, mm, _ in payes)
                annee_ref = max(y for y, _, _ in payes)
                cur.execute(
                    "INSERT INTO paiements (membre_id, campagne_id, date_paiement,"
                    " montant_total, mode, saisi_par, observation)"
                    " VALUES (?,?,?,?,?,?,?)",
                    (mid, campagnes[annee_ref], f"{annee_ref}-{dernier_mois:02d}-28",
                     total, "especes", "import_excel", f"{len(payes)} mois en bloc"))
                pid = cur.lastrowid
                nb_p += 1
                for annee, mois, montant in payes:
                    cur.execute("INSERT INTO affectations (paiement_id,annee,mois,montant)"
                                " VALUES (?,?,?,?)", (pid, annee, mois, montant))

        rapport.append((nom_feuille, "OK", nb_m, nb_p, int(total_fcfa)))
        tot_membres += nb_m
        tot_paiements += nb_p

    con.commit()

    # ------------------------------------------------------------ rapport
    print("=" * 92)
    print(f"{'FEUILLE':<32} {'ÉTAT':<20} {'MEMBRES':>8} {'PAIEM.':>7} {'TOTAL FCFA':>12}")
    print("-" * 92)
    for nom, etat, nm, np_, tt in rapport:
        print(f"{nom[:32]:<32} {etat[:20]:<20} {nm:>8} {np_:>7} {tt:>12,}".replace(",", " "))
    print("-" * 92)
    print(f"{'TOTAL GÉNÉRAL':<32} {'':<20} {tot_membres:>8} {tot_paiements:>7}"
          f" {sum(r[4] for r in rapport):>12,}".replace(",", " "))
    print("=" * 92)

    cur.execute("SELECT SUM(montant_total) FROM paiements")
    print("Somme des paiements en base :", int(cur.fetchone()[0] or 0))
    for lbl, sql in [
        ("Clans", "SELECT COUNT(*) FROM clans"),
        ("Grandes familles", "SELECT COUNT(*) FROM grandes_familles"),
        ("Lignées", "SELECT COUNT(*) FROM lignees"),
        ("Familles", "SELECT COUNT(*) FROM familles"),
        ("Membres", "SELECT COUNT(*) FROM membres"),
        ("Affectations", "SELECT COUNT(*) FROM affectations"),
    ]:
        cur.execute(sql)
        print(f"  {lbl:18s}: {cur.fetchone()[0]}")
    con.close()


if __name__ == "__main__":
    main()
