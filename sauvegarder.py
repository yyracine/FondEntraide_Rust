"""Sauvegarde datée et vérifiée de la base de référence du Fonds d'Entraide.

    python sauvegarder.py                  # cotisations.db
    python sauvegarder.py familles.db      # une autre base, en plus

La copie passe par l'API `backup` de SQLite, pas par `copy` : elle reste
cohérente même si une autre connexion écrit pendant l'opération. La source est
ouverte en LECTURE SEULE et n'est jamais modifiée.

La copie est ensuite vérifiée : intégrité, nombre de lignes de chaque table et
total des montants, comparés à la source. Un fichier `.sha256` l'accompagne.

Restauration (application fermée, base de travail remplacée) :

    cp sauvegardes/cotisations_AAAA-MM-JJ.db cotisations.db
    rm -f cotisations.db-wal cotisations.db-shm
    python migrer_v2.py

Les sauvegardes vivent dans `sauvegardes/`, exclu de git : elles contiennent
les données nominatives des membres et ne doivent pas être publiées.
"""

from __future__ import annotations

import hashlib
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

RACINE = Path(__file__).resolve().parent
DOSSIER = RACINE / "sauvegardes"
DEFAUT = "cotisations.db"


def empreinte(chemin: Path) -> str:
    """SHA-256 du fichier, lu par blocs."""
    h = hashlib.sha256()
    with open(chemin, "rb") as flux:
        for bloc in iter(lambda: flux.read(1 << 20), b""):
            h.update(bloc)
    return h.hexdigest()


def ouvrir_lecture(chemin: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{chemin.as_posix()}?mode=ro", uri=True)


def tables(con: sqlite3.Connection) -> list[str]:
    return [
        r[0]
        for r in con.execute(
            "SELECT name FROM sqlite_master "
            " WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
    ]


def compter(con: sqlite3.Connection, table: str) -> int:
    return con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def cible_libre(source: Path) -> Path:
    date = datetime.now().strftime("%Y-%m-%d")
    cible = DOSSIER / f"{source.stem}_{date}.db"
    suffixe = 2
    while cible.exists():
        cible = DOSSIER / f"{source.stem}_{date}_{suffixe}.db"
        suffixe += 1
    return cible


def sauvegarder(nom: str) -> bool:
    source = RACINE / nom
    if not source.exists():
        print(f"  {nom} : absente, ignorée")
        return True

    DOSSIER.mkdir(exist_ok=True)
    cible = cible_libre(source)

    src = ouvrir_lecture(source)
    dst = sqlite3.connect(cible)
    try:
        src.backup(dst)  # cohérent même sous écriture concurrente
        dst.commit()
    finally:
        dst.close()
        src.close()

    # Vérification indépendante, sur une nouvelle connexion en lecture seule.
    a = ouvrir_lecture(source)
    b = ouvrir_lecture(cible)
    try:
        integrite = b.execute("PRAGMA integrity_check").fetchone()[0]
        liste = tables(a)
        ecarts = []
        for table in liste:
            avant, apres = compter(a, table), compter(b, table)
            if avant != apres:
                ecarts.append((table, avant, apres))

        montants = None
        if "affectations" in liste:
            montants = (
                a.execute("SELECT IFNULL(SUM(montant), 0) FROM affectations").fetchone()[0],
                b.execute("SELECT IFNULL(SUM(montant), 0) FROM affectations").fetchone()[0],
            )

        print(f"\n  {nom} -> {cible.name}")
        print(f"    tables          : {', '.join(f'{t} {compter(b, t)}' for t in liste)}")
        if montants is not None:
            print(f"    total affecté   : {montants[0]} F (source) / {montants[1]} F (copie)")
        print(f"    intégrité       : {integrite}")
        print(f"    taille          : {cible.stat().st_size / 1024:.0f} Ko")
        print(f"    SHA-256 source  : {empreinte(source)[:16]}…")
        print(f"    SHA-256 copie   : {empreinte(cible)}")

        probleme = integrite != "ok" or ecarts or (montants is not None and montants[0] != montants[1])
        if probleme:
            if ecarts:
                print(f"    ÉCARTS          : {ecarts}")
            cible.unlink(missing_ok=True)
            print("    copie refusée et supprimée : elle ne reproduit pas la source")
            return False

        sidecar = cible.with_suffix(cible.suffix + ".sha256")
        # newline="\n" : sinon Python écrit CRLF sous Windows et `sha256sum -c`
        # lit un \r parasite à la fin du nom de fichier.
        sidecar.write_text(
            f"{empreinte(cible)}  {cible.name}\n", encoding="utf-8", newline="\n"
        )
        return True
    finally:
        b.close()
        a.close()


def main(argv: list[str]) -> int:
    noms = argv[1:] or [DEFAUT]
    print("== sauvegarde de la base ==")
    for nom in noms:
        if not sauvegarder(nom):
            return 2
    print("\n  contenu de sauvegardes/ :")
    for fichier in sorted(DOSSIER.glob("*")):
        print(f"    {fichier.name:<40} {fichier.stat().st_size / 1024:>8.0f} Ko")
    print("\n  restauration : copier la sauvegarde sur la base, puis python migrer_v2.py")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
