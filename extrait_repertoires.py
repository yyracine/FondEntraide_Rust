#!/usr/bin/env python3
"""
Extrait les valeurs des 7 feuilles-répertoires du classeur Excel
(LIGNEE <CLAN>) et les enregistre dans « repertoires.json ».

Ces feuilles sont des tableaux agrégés par lignée. Le récapitulatif
« TOTAL GENERAL COTISATIONS » pointe vers elles (ex : =+'AGOH'!AB8).
Elles servent de référence pour l'audit (option --audit de requetes.py).

Usage : python extrait_repertoires.py
"""
import json
import re
from pathlib import Path

import openpyxl

BASE = Path(__file__).parent
XLSX = Path(r"C:/Users/HP/Documents/Fond Entraide Revise/FONDS D'ENTRE AIDE Final MAJ 3 Aout 24 (1).xlsx")
OUT = BASE / "repertoires.json"

# feuilles-répertoires : lignes agrégées par lignée
REPERTOIRES = ["KOUADIO AMBOFF", "YAOCRE", "ADJOUA MALA", "AGOH",
               "TCHOUWA", "KACOUTIE EDJAPA", "ASSOMOU"]

# colonnes de total annuel : 2024=P(16), 2025=AC(29), 2026=AP(42)
COL_TOTAL = {2024: 16, 2025: 29, 2026: 42}


def main():
    wb = openpyxl.load_workbook(XLSX, data_only=True)
    data = {}

    for nom in REPERTOIRES:
        if nom not in wb.sheetnames:
            print(f"  ! feuille {nom!r} absente")
            continue
        ws = wb[nom]

        # nom de clan depuis A1 : "LIGNEE AGOH" -> "AGOH"
        a1 = str(ws.cell(1, 1).value or "").strip()
        clan = re.sub(r"^\s*(?:lign[ée]e|famille)\s+", "", a1, flags=re.I).strip()

        # ligne TOTAL de la feuille
        ligne_total = None
        for r in range(1, ws.max_row + 1):
            if str(ws.cell(r, 1).value or "").upper().startswith("TOTAL"):
                ligne_total = r

        valeurs = {}
        for annee, col in COL_TOTAL.items():
            v = ws.cell(ligne_total, col).value if ligne_total else None
            valeurs[str(annee)] = float(v) if isinstance(v, (int, float)) else 0.0

        # détail par grande famille listée dans le répertoire
        detail = []
        for r in range(3, (ligne_total or ws.max_row)):
            lib = ws.cell(r, 1).value
            if not lib or str(lib).upper().startswith("TOTAL"):
                continue
            row = {"grande_famille": str(lib).strip()}
            for annee, col in COL_TOTAL.items():
                v = ws.cell(r, col).value
                row[str(annee)] = float(v) if isinstance(v, (int, float)) else 0.0
            detail.append(row)

        data[clan] = {
            "feuille": nom,
            "ligne_total": ligne_total,
            "totaux": valeurs,
            "detail": detail,
        }

    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Écrit {OUT.name}")
    print(f"{'CLAN':<18} {'2024':>10} {'2025':>10} {'2026':>8}  lignes")
    for clan, d in data.items():
        t = d["totaux"]
        print(f"{clan:<18} {int(t['2024']):>10,} {int(t['2025']):>10,}"
              f" {int(t['2026']):>8,}  {len(d['detail'])}".replace(",", " "))


if __name__ == "__main__":
    main()
