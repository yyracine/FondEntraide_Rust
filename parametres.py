"""
parametres.py — Réglages de l'application et gestion des sauvegardes.

Contenu
-------
1. Paramètres persistants (montant de cotisation, devise, horizon des années)
   stockés dans une petit table `parametres` créée au besoin : ainsi un
   réglage survit à la fermeture sans dépendre du format du fichier.
2. Montant de cotisation par année (table `campagnes` déjà existante).
3. Sauvegarde, restauration et purge de la base.

Sauvegarde tournante à la fermeture
-----------------------------------
Deux sauvegardes seulement sont conservées : celle du jour (n) et celle de
la veille (n-1). Si l'application est fermée plusieurs fois le même jour,
la sauvegarde du jour est écrasée — ce qui évite d'accumuler des dizaines
de fichiers identiques.
"""
import datetime
import sqlite3
from pathlib import Path

import db

BASE_DIR = Path(__file__).parent
DOSSIER_SAUVEGARDES = BASE_DIR / "sauvegardes"
PREFIXE = "familles_"

DEVISE = "FCFA"


# ---------------------------------------------------------------------
#  Table des paramètres (créée au besoin, sans modifier schema.sql)
# ---------------------------------------------------------------------
def _assurer_table(con):
    con.execute("""
        CREATE TABLE IF NOT EXISTS parametres (
            cle     TEXT PRIMARY KEY,
            valeur  TEXT NOT NULL,
            maj_le  TEXT NOT NULL
        )
    """)
    con.commit()


def lire_parametre(con, cle, defaut=None):
    _assurer_table(con)
    r = con.execute("SELECT valeur FROM parametres WHERE cle = ?",
                    (cle,)).fetchone()
    return r["valeur"] if r else defaut


def ecrire_parametre(con, cle, valeur):
    _assurer_table(con)
    con.execute("""
        INSERT INTO parametres (cle, valeur, maj_le) VALUES (?, ?, ?)
        ON CONFLICT(cle) DO UPDATE SET valeur = excluded.valeur,
                                       maj_le = excluded.maj_le
    """, (cle, str(valeur), datetime.datetime.now().isoformat(timespec="seconds")))
    con.commit()


def tous_les_parametres(con):
    _assurer_table(con)
    return {r["cle"]: r["valeur"] for r in
            con.execute("SELECT cle, valeur FROM parametres")}


# ---------------------------------------------------------------------
#  Montant de cotisation
# ---------------------------------------------------------------------
def montant_par_defaut(con):
    """Montant mensuel de référence : le paramètre s'il existe, sinon le
    montant de la dernière campagne, sinon 1 000 FCFA."""
    val = lire_parametre(con, "montant_mensuel")
    if val is not None:
        try:
            return float(val)
        except ValueError:
            pass
    r = con.execute("SELECT montant_mensuel FROM campagnes "
                    "ORDER BY annee DESC LIMIT 1").fetchone()
    return float(r["montant_mensuel"]) if r else 1000.0


def definir_montant(con, montant, annee=None, appliquer_existantes=False):
    """Enregistre le montant de cotisation.

    montant            : montant mensuel en FCFA (> 0)
    annee              : année concernée ; None = montant par défaut
    appliquer_existantes : si vrai, met aussi à jour les campagnes existantes
    """
    try:
        montant = float(montant)
    except (TypeError, ValueError):
        raise db.ErreurSaisie("Le montant doit être un nombre.")
    if montant <= 0:
        raise db.ErreurSaisie("Le montant doit être supérieur à zéro.")
    if montant > 10_000_000:
        raise db.ErreurSaisie("Le montant paraît invraisemblable (maximum "
                              "10 000 000 FCFA).")

    ecrire_parametre(con, "montant_mensuel", int(montant)
                     if montant == int(montant) else montant)
    ecrire_parametre(con, "devise", DEVISE)

    if annee is not None:
        r = con.execute("SELECT id FROM campagnes WHERE annee = ?",
                        (annee,)).fetchone()
        if r:
            con.execute("UPDATE campagnes SET montant_mensuel = ? WHERE id = ?",
                        (montant, r["id"]))
        else:
            con.execute(
                "INSERT INTO campagnes (libelle, annee, montant_mensuel, "
                "devise, statut, created_at) VALUES (?, ?, ?, ?, 'ouverte', ?)",
                (f"Campagne {annee}", annee, montant, DEVISE,
                 datetime.datetime.now().isoformat(timespec="seconds")))
        con.commit()

    if appliquer_existantes:
        con.execute("UPDATE campagnes SET montant_mensuel = ?", (montant,))
        con.commit()
    return montant


# ---------------------------------------------------------------------
#  Exercices : périodes ouvertes librement (date de début / date de fin)
# ---------------------------------------------------------------------
def lister_exercices(con):
    """Exercices enregistrés, avec leurs bornes et leur montant.
    Un exercice « classique » couvre une année civile ; un exercice libre
    peut couvrir n'importe quelle période (juillet 2025 → juin 2026…)."""
    return con.execute("""
        SELECT c.id, c.libelle, c.annee, c.montant_mensuel, c.devise,
               c.date_debut, c.date_fin, c.statut,
               (SELECT COUNT(*) FROM affectations a WHERE a.annee = c.annee)
                   AS nb_mois
        FROM campagnes c
        ORDER BY IFNULL(c.date_debut, c.annee || '-01-01') DESC
    """).fetchall()


def _mois_entre(debut, fin):
    """Nombre de mois civils touchés par la période (bornes incluses)."""
    m = (fin.year - debut.year) * 12 + (fin.month - debut.month) + 1
    return max(1, m)


def ouvrir_exercice(con, libelle, date_debut, date_fin, montant,
                    annee=None, statut="ouverte", remplacer=False):
    """Ouvre (ou met à jour) un exercice.

    Le stockage reste compatible avec l'existant : la table `campagnes`
    possède une colonne `annee` UNIQUE et les affectations sont indexées
    par `annee`. Un exercice porte donc l'ÉTIQUETTE de son année de début,
    tandis que `date_debut` / `date_fin` décrivent la période réelle.
    """
    import datetime as _dt

    for valeur, nom in ((date_debut, "date de début"), (date_fin, "date de fin")):
        try:
            _dt.datetime.strptime(str(valeur), "%Y-%m-%d")
        except ValueError:
            raise db.ErreurSaisie(f"La {nom} doit être au format AAAA-MM-JJ.")
    d = _dt.datetime.strptime(str(date_debut), "%Y-%m-%d").date()
    f = _dt.datetime.strptime(str(date_fin), "%Y-%m-%d").date()
    if f < d:
        raise db.ErreurSaisie("La date de fin doit suivre la date de début.")

    try:
        montant = float(str(montant).replace(" ", "").replace(",", "."))
    except (TypeError, ValueError):
        raise db.ErreurSaisie("Le montant doit être un nombre.")
    if montant <= 0:
        raise db.ErreurSaisie("Le montant doit être supérieur à zéro.")

    libelle = (libelle or "").strip()
    if not libelle:
        libelle = f"Exercice {d.year}"

    etiquette = annee or d.year
    if not annee_montant_valide(etiquette):
        raise db.ErreurSaisie("L'année de rattachement est invalide.")

    r = con.execute("""SELECT id, libelle, date_debut, date_fin,
                              montant_mensuel
                       FROM campagnes WHERE annee = ?""",
                    (etiquette,)).fetchone()

    # Un exercice existe déjà pour cette année : on ne l'écrase JAMAIS
    # silencieusement. Soit la période est identique (mise à jour normale),
    # soit il faut une confirmation explicite (remplacer=True).
    if r and not remplacer:
        meme_periode = (str(r["date_debut"]) == str(d)
                        and str(r["date_fin"]) == str(f))
        if not meme_periode:
            raise db.ErreurSaisie(
                f"Un exercice existe déjà pour l'année {etiquette} :\n"
                f"    « {r['libelle']} » du "
                f"{periode_lisible(r['date_debut'], r['date_fin'])}\n\n"
                f"Une seule période par année est possible. "
                f"Confirmez le remplacement pour changer la période, "
                f"ou choisissez une autre année de rattachement.")

    try:
        if r:
            con.execute("""
                UPDATE campagnes SET libelle = ?, montant_mensuel = ?,
                       date_debut = ?, date_fin = ?, statut = ?
                WHERE id = ?
            """, (libelle, montant, str(d), str(f), statut, r["id"]))
            action = "modifie"
        else:
            con.execute("""
                INSERT INTO campagnes (libelle, annee, montant_mensuel, devise,
                                       date_debut, date_fin, statut, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (libelle, etiquette, montant, DEVISE, str(d), str(f), statut,
                  _dt.datetime.now().isoformat(timespec="seconds")))
            action = "cree"
        con.commit()
    except sqlite3.IntegrityError as e:
        con.rollback()
        raise db.ErreurSaisie(
            f"Cet exercice entre en conflit avec un autre "
            f"(une période ne peut être enregistrée deux fois sous la même "
            f"année) : {e}")
    return action


def supprimer_exercice(con, annee):
    """Supprime un exercice, uniquement s'il ne contient aucune cotisation."""
    n = con.execute("SELECT COUNT(*) FROM affectations WHERE annee = ?",
                    (annee,)).fetchone()[0]
    if n:
        raise db.ErreurSaisie(
            f"Impossible : {n} mois de cotisation sont enregistrés sur "
            f"l'exercice {annee}. Videz d'abord ces versements.")
    con.execute("DELETE FROM campagnes WHERE annee = ?", (annee,))
    con.commit()


def exercice_couvrant(con, date_iso):
    """Exercice dont la période contient cette date (ou None)."""
    return con.execute("""
        SELECT * FROM campagnes
        WHERE date_debut IS NOT NULL AND date_fin IS NOT NULL
          AND date(?) BETWEEN date(date_debut) AND date(date_fin)
        ORDER BY date_debut DESC LIMIT 1
    """, (str(date_iso),)).fetchone()


def periode_lisible(debut, fin):
    """« 2025-07-01 » / « 2026-06-30 » -> « 01/07/2025 → 30/06/2026 »."""
    import datetime as _dt

    def fr(v):
        if not v:
            return "—"
        try:
            return _dt.datetime.strptime(str(v), "%Y-%m-%d").strftime("%d/%m/%Y")
        except ValueError:
            return str(v)

    if not debut and not fin:
        return "année civile"
    return f"{fr(debut)} → {fr(fin)}"


def annees_pour_montant(con, depuis=2024, horizon=5):
    """Années sélectionnables pour définir un montant de cotisation.

    Même logique que `cotisations.annees_disponibles` : les années passées
    (pour corriger un montant), celles déjà en campagne, et les années
    futures (pour fixer un montant à l'avance).
    """
    annee_courante = datetime.date.today().year
    annees = {r["annee"] for r in con.execute("SELECT annee FROM campagnes")}
    try:
        annees |= {r["annee"] for r in con.execute(
            "SELECT DISTINCT annee FROM affectations")}
    except sqlite3.Error:
        pass
    annees |= set(range(depuis, annee_courante + horizon + 1))
    return sorted(annees, reverse=True)


def annee_montant_valide(annee):
    try:
        annee = int(annee)
    except (TypeError, ValueError):
        return False
    return 2000 <= annee <= 2100


def campagnes_avec_montant(con):
    return con.execute(
        "SELECT annee, montant_mensuel, devise, statut, "
        "  (SELECT COUNT(*) FROM affectations a WHERE a.annee = campagnes.annee)"
        "  AS nb_mois "
        "FROM campagnes ORDER BY annee DESC").fetchall()


# ---------------------------------------------------------------------
#  Sauvegardes
# ---------------------------------------------------------------------
def _nom_fichier(date):
    return f"{PREFIXE}{date.strftime('%Y%m%d')}.db"


def lister_sauvegardes(dossier=None):
    """Sauvegardes présentes, de la plus récente à la plus ancienne."""
    d = Path(dossier) if dossier else DOSSIER_SAUVEGARDES
    if not d.exists():
        return []
    fichiers = sorted(d.glob(f"{PREFIXE}*.db"), reverse=True)
    resultat = []
    for f in fichiers:
        try:
            date_txt = f.stem[len(PREFIXE):]
            date = datetime.datetime.strptime(date_txt, "%Y%m%d").date()
        except ValueError:
            continue
        resultat.append({
            "chemin": f,
            "date": date,
            "taille": f.stat().st_size,
            "modifie": datetime.datetime.fromtimestamp(f.stat().st_mtime),
        })
    return resultat


def sauvegarder(con, dossier=None, date=None):
    """Copie cohérente de la base (via l'API backup de SQLite).

    Ne conserve que les deux sauvegardes les plus récentes (n et n-1).
    Retourne le chemin du fichier écrit.
    """
    d = Path(dossier) if dossier else DOSSIER_SAUVEGARDES
    d.mkdir(parents=True, exist_ok=True)
    jour = date or datetime.date.today()
    cible = d / _nom_fichier(jour)

    dest = sqlite3.connect(cible)
    try:
        con.commit()
        con.backup(dest)          # copie atomique, même base ouverte
    finally:
        dest.close()

    # ne garder que les deux plus récentes
    fichiers = sorted(d.glob(f"{PREFIXE}*.db"), reverse=True)
    for vieux in fichiers[2:]:
        try:
            vieux.unlink()
        except OSError:
            pass
    return cible


def restaurer(chemin, con=None, sauvegarder_avant=True, dossier=None):
    """Restaure une sauvegarde dans la base vivante.

    Par sécurité, la base actuelle est d'abord sauvegardée dans
    `sauvegardes/avant_restauration_<horodatage>.db`.
    """
    source = Path(chemin)
    if not source.exists():
        raise db.ErreurSaisie(f"Sauvegarde introuvable : {source}")

    # vérifie que le fichier est bien une base SQLite lisible
    try:
        essai = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
        integrite = essai.execute("PRAGMA integrity_check").fetchone()[0]
        tables = {r[0] for r in essai.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        essai.close()
    except sqlite3.Error as e:
        raise db.ErreurSaisie(f"Fichier illisible ou corrompu : {e}")
    if integrite != "ok":
        raise db.ErreurSaisie(f"Sauvegarde corrompue (intégrité : {integrite}).")
    if "clans" not in tables or "membres" not in tables:
        raise db.ErreurSaisie("Ce fichier n'est pas une base du Fonds "
                              "d'Entraide (tables manquantes).")

    if sauvegarder_avant:
        d = Path(dossier) if dossier else DOSSIER_SAUVEGARDES
        d.mkdir(parents=True, exist_ok=True)
        horo = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        try:
            con.commit()
            copie = sqlite3.connect(d / f"avant_restauration_{horo}.db")
            con.backup(copie)
            copie.close()
        except sqlite3.Error:
            pass

    # On restaure dans la base réellement ouverte (et non dans un chemin
    # fixe) : la connexion garde son descripteur de fichier.
    cible = source
    if con is not None:
        con.commit()
        src = sqlite3.connect(cible)
        try:
            src.backup(con)       # ecrase le contenu de la base ouverte
        finally:
            src.close()
        con.commit()
    else:
        dest = sqlite3.connect(db.DB_PATH)
        try:
            src = sqlite3.connect(cible)
            try:
                src.backup(dest)
            finally:
                src.close()
        finally:
            dest.close()
    return True


def importer(chemin, con=None, sauvegarder_avant=True, dossier=None):
    """Importe une base externe : même opération qu'une restauration, mais
    le fichier peut venir de n'importe où (clé USB, autre poste)."""
    return restaurer(chemin, con=con, sauvegarder_avant=sauvegarder_avant,
                     dossier=dossier)


def _vider_membres(con):
    """Supprime tous les membres en commencant par les feuilles.

    Le trigger trg_membre_suppr_avec_enfants refuse la suppression d'un
    membre ayant des descendants. Un DELETE massif les rencontre dans un
    ordre arbitraire et echoue ; on procede donc par niveaux de
    profondeur, des plus jeunes vers les plus anciens.
    """
    while True:
        cur = con.execute("""
            DELETE FROM membres
            WHERE id NOT IN (SELECT DISTINCT parent_id FROM membres
                             WHERE parent_id IS NOT NULL)
        """)
        if cur.rowcount == 0:
            break


def purger(con, niveau="donnees"):
    """Vide la base.

    niveau = "donnees"      : efface cotisations + membres + familles + …
    niveau = "hierarchie"   : efface seulement la hiérarchie et les membres
                              (conserve les paramètres)
    niveau = "tout"         : efface absolument tout, paramètres compris

    Retourne le nombre de lignes supprimées par table.
    """
    ordre = ["affectations", "paiements", "membres", "familles", "lignees",
             "grandes_familles", "clans", "campagnes"]
    if niveau == "hierarchie":
        ordre = ["affectations", "paiements", "membres", "familles", "lignees",
                 "grandes_familles", "clans"]

    compte = {}
    # on désactive les clés étrangères le temps de la purge en respectant
    # l'ordre descendant, puis on remet les compteurs à zéro
    con.execute("PRAGMA foreign_keys = OFF")
    try:
        for table in ordre:
            n = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            if table == "membres":
                # Le trigger trg_membre_suppr_avec_enfants interdit de
                # supprimer un membre qui a encore des descendants. Un
                # DELETE global les touche dans un ordre quelconque et
                # echoue. On retire donc les membres feuille par feuille,
                # niveau de profondeur apres niveau de profondeur.
                _vider_membres(con)
            else:
                con.execute(f"DELETE FROM {table}")
            compte[table] = n
        if niveau == "tout":
            con.execute("DELETE FROM parametres")
            con.execute("DELETE FROM sqlite_sequence")
        else:
            for table in ordre:
                con.execute("DELETE FROM sqlite_sequence WHERE name = ?",
                            (table,))
        con.commit()
    except sqlite3.Error as e:
        con.rollback()
        raise db.ErreurSaisie(f"Purge impossible : {e}")
    finally:
        con.execute("PRAGMA foreign_keys = ON")
    con.execute("VACUUM")
    return compte


def etat_base(con):
    """Chiffres de synthèse affichés dans l'onglet Paramètres."""
    tables = ["clans", "grandes_familles", "lignees", "familles", "membres",
              "campagnes", "paiements", "affectations"]
    compte = {}
    for t in tables:
        try:
            compte[t] = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        except sqlite3.Error:
            compte[t] = 0
    compte["taille"] = db.DB_PATH.stat().st_size if db.DB_PATH.exists() else 0
    try:
        compte["total_cotise"] = con.execute(
            "SELECT IFNULL(SUM(montant), 0) FROM affectations").fetchone()[0]
    except sqlite3.Error:
        compte["total_cotise"] = 0
    return compte
