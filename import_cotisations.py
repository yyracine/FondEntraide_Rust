#!/usr/bin/env python3
"""
Peuplement de la base SQLite 'cotisations.db' depuis Test1.xlsx.

Structure lue dans le classeur :
  - Colonnes D..O   = Janv..Déc 2024, Total en P
  - Colonnes Q..AB  = Janv..Déc 2025, Total en AC
  - Colonnes AD..AO = Janv..Déc 2026, Total en AP

Hiérarchie du fichier (indentation colonne A/B/C) :
    Famille            -> ex. "TIGORI Germaine"            (col A)
      Enfant/Penfant   -> ex. "(Penfant 31) XXXX"          (col B ou C)
        APenfant       -> ex. "(APenfant311)"              (col C)

Chaque membre est cotisant : on crée un membre pour CHAQUE ligne nommée,
avec parent_id = membre parent (le plus proche ancêtre "nommé"), et
famille_id = la famille (branche) de rattachement.
"""
import re
import sqlite3
import unicodedata
from pathlib import Path

import openpyxl

BASE = Path(__file__).parent
XLSX = BASE / "Test1.xlsx"
DB = BASE / "cotisations.db"
SQL = BASE / "schema.sql"

MOIS_2024 = list(range(4, 16))    # D..O
MOIS_2025 = list(range(17, 29))   # Q..AB
MOIS_2026 = list(range(30, 42))   # AD..AO

# Libellés manifestement fictifs présents dans le fichier source.
# Ils ne correspondent à aucun membre réel et ne cotisent jamais : on les ignore.
PLACEHOLDER = re.compile(r"^(?:X{2,}|Y{2,}|Z{2,}|AMY|XXX+)$", re.I)

# Les 5 familles. 'motif' = expression régulière sur la clé normalisée,
# car le fichier oscille entre GNANDAKY / GNANDAKI.
FAMILLES = [
    ("GNANDAKY AKOUA",         r"^GNANDAK?Y?\s*AKOUA$"),
    ("GNANDAKY APPIA",         r"^GNANDAK?Y?\s*APPIA$"),
    ("GNANDAKY BOA",           r"^GNANDAK?Y?\s*BOA$"),
    ("PAGNINI N'da Gnankon",   r"^PAGNINI N DA GNANKON$"),
    ("PAGNINI N'da Bomo",      r"^PAGNINI N DA BOMO$"),
]


def nettoie(txt):
    """Corrige les accents cassés du fichier (ex : 'Cath?rine')."""
    if txt is None:
        return None
    s = str(txt).strip()
    if not s:
        return None
    s = re.sub(r"\s+", " ", s)
    return s


def cle(txt):
    """Clé de comparaison insensible aux accents/casse/espaces."""
    if not txt:
        return ""
    s = unicodedata.normalize("NFKD", str(txt))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^A-Za-z0-9]+", " ", s).strip().upper()
    return s


def split_nom(s):
    """'TIGORI Ange Fran?ois' -> ('TIGORI', 'Ange Francois-ish').
    On garde le premier mot comme NOM, le reste comme PRENOM."""
    s = nettoie(s) or ""
    s = s.lstrip("(").strip()
    parts = s.split(" ", 1)
    nom = parts[0].strip()
    prenom = parts[1].strip() if len(parts) > 1 else None
    return nom, prenom


def extrait_ordre(label):
    """Récupère l'ordre dans la fratrie depuis '(Penfant 31)' ou '(Enfant3)'."""
    if not label:
        return None
    m = re.search(r"Enfant\s*(\d+)", label, re.I)
    return int(m.group(1)) if m else None


def est_ligne_total(label):
    return bool(re.match(r"\s*total\b", str(label or ""), re.I))


def main():
    wb = openpyxl.load_workbook(XLSX, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))

    if DB.exists():
        DB.unlink()
    con = sqlite3.connect(DB)
    con.executescript(SQL.read_text(encoding="utf-8"))
    cur = con.cursor()

    # ---------------- Hiérarchie haute ----------------
    cur.execute("INSERT INTO clans (nom, description) VALUES (?,?)",
                ("KOUADIO AMBOFF", "Clan fondateur"))
    clan_id = cur.lastrowid

    cur.execute("INSERT INTO grandes_familles (clan_id, nom, description) VALUES (?,?,?)",
                (clan_id, "AMBOFF MIAN BLA", "Grande famille "))
    gf_id = cur.lastrowid

    cur.execute("INSERT INTO lignees (grande_famille_id, nom, description) VALUES (?,?,?)",
                (gf_id, "MIAN BLAH", "Lignée des descendants de Mian Blah"))
    lig_id = cur.lastrowid

    familles_ids = []   # [(regex, id), ...]
    for i, (nom, motif) in enumerate(FAMILLES, start=1):
        cur.execute("INSERT INTO familles (lignee_id, nom, ordre) VALUES (?,?,?)",
                    (lig_id, nom, i))
        familles_ids.append((re.compile(motif), cur.lastrowid))

    # ---------------- Campagnes ----------------
    campagnes = {}
    for annee in (2024, 2025, 2026):
        statut = "ouverte" if annee == 2026 else "fermee"
        cur.execute(
            "INSERT INTO campagnes (libelle, annee, montant_mensuel, devise, statut) "
            "VALUES (?,?,?,?,?)",
            (f"Campagne {annee}", annee, 1000, "FCFA", statut))
        campagnes[annee] = (cur.lastrowid, statut)

    # ---------------- Lecture de l'arbre ----------------
    famille_courante = None      # id de la famille active
    pile = []                    # pile de (niveau, membre_id, label)
    membres_crees = 0
    paiements_crees = 0

    for excel_row, row in enumerate(rows, start=1):
        if excel_row < 5:
            continue

        cell_a = nettoie(row[0]) if len(row) > 0 else None
        cell_b = nettoie(row[1]) if len(row) > 1 else None
        cell_c = nettoie(row[2]) if len(row) > 2 else None

        label = cell_a or cell_b or cell_c
        if not label:
            continue

        # --- Changement de famille ---
        if cell_a and not est_ligne_total(cell_a):
            k = cle(cell_a)
            for motif, fid in familles_ids:
                if motif.match(k):
                    famille_courante = fid
                    pile = []
                    break

        # --- Ligne TOTAL : on ignore, les totaux sont recalculés ---
        if est_ligne_total(label):
            continue

        if famille_courante is None:
            continue

        # --- Niveau dans l'arbre : c'est la colonne remplie qui l'indique ---
        if cell_a:
            niveau = 1     # chef de famille
        elif cell_b:
            niveau = 2     # enfant / petit-enfant
        else:
            niveau = 3     # arrière-petit-enfant

        # Le parent est le membre du niveau juste au-dessus
        parent_id = None
        for lvl, mid, _ in reversed(pile):
            if lvl < niveau:
                parent_id = mid
                break

        # Nettoyage du libellé -> nom / prénom
        brut = label.lstrip("(").rstrip(")").strip()
        # '(Penfant 31) XXXX' -> on retire le marqueur pour un nom propre
        brut = re.sub(r"^\(?(?:A?Penfant\s*\d+|A?P?[Ee]nfant\s*\d+)\)?\s*",
                      "", brut, flags=re.I).strip()

        # Un descendant SANS NOM PROPRE (ex. '(APenfant111)' seul) n'est pas
        # un membre : on l'ignore complètement (ni membre, ni cotisation).
        if not brut:
            continue

        nom, prenom = split_nom(brut)

        # Placeholders du fichier (XXXX, YYYYY, ZZZZZ, AMY...) : ne sont pas de
        # vrais membres. On les ignore d'emblée -> import idempotent.
        if PLACEHOLDER.match(nom) or (prenom and PLACEHOLDER.match(prenom)):
            continue

        ordre = extrait_ordre(label)

        cur.execute(
            "INSERT INTO membres (famille_id, parent_id, nom, prenom, ordre_fratrie, statut, notes) "
            "VALUES (?,?,?,?,?,?,?)",
            (famille_courante, parent_id, nom, prenom, ordre,
             "actif", f"importé ligne {excel_row}"))
        membre_id = cur.lastrowid
        membres_crees += 1

        # Met à jour la pile (on dépile tout ce qui est >= niveau)
        pile = [(l, i, lab) for (l, i, lab) in pile if l < niveau]
        pile.append((niveau, membre_id, label))

        # ---------------- Cotisations ----------------
        for annee, cols in ((2024, MOIS_2024), (2025, MOIS_2025), (2026, MOIS_2026)):
            # On ne remplit 2026 que si le fichier contient quelque chose
            payes = []
            for idx, col in enumerate(cols, start=1):
                if col - 1 < len(row):
                    v = row[col - 1]
                    if isinstance(v, (int, float)) and v > 0:
                        payes.append((idx, float(v)))
            if not payes:
                continue

            total = sum(m for _, m in payes)
            campagne_id, statut = campagnes[annee]
            # date de paiement : on prend le mois du DERNIER mois payé
            dernier_mois = max(m for m, _ in payes)
            date_paiement = f"{annee}-{dernier_mois:02d}-28"

            cur.execute(
                "INSERT INTO paiements (membre_id, campagne_id, date_paiement, montant_total, "
                "mode, saisi_par, observation) VALUES (?,?,?,?,?,?,?)",
                (membre_id, campagne_id, date_paiement, total, "especes", "import_excel",
                 f"{len(payes)} mois réglés en une fois"))
            paiement_id = cur.lastrowid
            paiements_crees += 1

            for mois, montant in payes:
                cur.execute(
                    "INSERT INTO affectations (paiement_id, annee, mois, montant) VALUES (?,?,?,?)",
                    (paiement_id, annee, mois, montant))

    con.commit()

    # ---------------- Bilan ----------------
    print("=" * 60)
    print(f"Base créée : {DB}")
    print(f"Membres importés   : {membres_crees}")
    print(f"Paiements importés : {paiements_crees}")
    for lib, sql in [
        ("Familles", "SELECT COUNT(*) FROM familles"),
        ("Affectations (mois)", "SELECT COUNT(*) FROM affectations"),
        ("Total versé 2024", "SELECT SUM(montant_total) FROM paiements p JOIN campagnes c ON c.id=p.campagne_id WHERE c.annee=2024"),
        ("Total versé 2025", "SELECT SUM(montant_total) FROM paiements p JOIN campagnes c ON c.id=p.campagne_id WHERE c.annee=2025"),
        ("Total versé 2026", "SELECT IFNULL(SUM(montant_total),0) FROM paiements p JOIN campagnes c ON c.id=p.campagne_id WHERE c.annee=2026"),
    ]:
        cur.execute(sql)
        print(f"  {lib:22s}: {cur.fetchone()[0]}")
    print("=" * 60)
    con.close()


if __name__ == "__main__":
    main()
