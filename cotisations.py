"""
cotisations.py — Logique métier des cotisations.

Un membre cotise 1 000 FCFA par mois (montant de la campagne).
Un versement réel (`paiements`) peut couvrir PLUSIEURS mois : le détail
mois par mois est stocké dans `affectations`.

Règle de calcul essentielle
---------------------------
Tous les totaux doivent être calculés sur `affectations.annee`, JAMAIS sur
`paiements.campagne_id` : un versement de 5 000 FCFA en 2025 peut très bien
régler décembre 2024 + janvier à avril 2025. C'est l'erreur qui faussait les
premiers imports.
"""
import datetime

import db

MOIS_NOMS = ["Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
             "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"]
MOIS_COURTS = ["Janv", "Févr", "Mars", "Avr", "Mai", "Juin",
               "Juil", "Août", "Sept", "Oct", "Nov", "Déc"]

MODES = [("especes", "Espèces"),
         ("mobile_money", "Mobile Money"),
         ("virement", "Virement"),
         ("cheque", "Chèque"),
         ("autre", "Autre")]


# ---------------------------------------------------------------------
#  Campagnes
# ---------------------------------------------------------------------
def lister_campagnes(con):
    return con.execute(
        "SELECT * FROM campagnes ORDER BY annee DESC").fetchall()


def campagne(con, annee):
    return con.execute("SELECT * FROM campagnes WHERE annee = ?",
                       (annee,)).fetchone()


def creer_campagne(con, annee, montant_mensuel=1000):
    """Crée la campagne d'une année si elle n'existe pas déjà."""
    existante = campagne(con, annee)
    if existante:
        return existante["id"]
    try:
        cur = con.execute(
            "INSERT INTO campagnes (libelle, annee, montant_mensuel) "
            "VALUES (?, ?, ?)",
            (f"Campagne {annee}", annee, montant_mensuel))
        con.commit()
    except Exception as e:
        con.rollback()
        raise db.ErreurSaisie(f"Impossible de créer la campagne {annee} : {e}")
    return cur.lastrowid


ANNEES_DEPUIS = 2024
DEBUT_ANNEES = ANNEES_DEPUIS      # alias lisible
HORIZON = 5                       # années futures proposées au-delà de l'année courante


def annees_disponibles(con, depuis=None, horizon=None):
    """Toutes les années sélectionnables dans l'écran de cotisation.

    On propose :
      - toutes les années déjà présentes en campagne ;
      - toutes les années où des montants ont été affectés ;
      - toutes les années de `depuis` (2024 par défaut) jusqu'à
        `année courante + horizon` (5 ans par défaut).

    L'horizon large couvre les besoins réels : régler des ARRIÉRÉS
    (payer en 2026 une cotisation de 2024) comme ANTICIPER (payer 2028,
    2029, … à l'avance). Le pilote peut élargir encore via les paramètres
    de l'écran.
    """
    depuis = ANNEES_DEPUIS if depuis is None else depuis
    horizon = HORIZON if horizon is None else horizon
    annee_courante = datetime.date.today().year
    annees = {r["annee"] for r in con.execute("SELECT annee FROM campagnes")}
    annees |= {r["annee"] for r in con.execute(
        "SELECT DISTINCT annee FROM affectations")}
    annees |= set(range(depuis, annee_courante + horizon + 1))
    return sorted(annees, reverse=True)


def libelle_exercice(con, annee):
    """Étiquette lisible d'un exercice : « Exercice 2025-2026
    (01/07/2025 → 30/06/2026) », ou None s'il n'y a pas d'exercice."""
    r = con.execute("""SELECT libelle, date_debut, date_fin FROM campagnes
                       WHERE annee = ?""", (annee,)).fetchone()
    if not r:
        return None
    if not r["date_debut"] or not r["date_fin"]:
        return r["libelle"]
    def fr(v):
        try:
            return datetime.datetime.strptime(str(v), "%Y-%m-%d").strftime(
                "%d/%m/%Y")
        except ValueError:
            return str(v)
    return (f"{r['libelle']} ({fr(r['date_debut'])} → "
            f"{fr(r['date_fin'])})")


def annee_valide(annee):
    """Garde-fou : une année de cotisation plausible."""
    try:
        annee = int(annee)
    except (TypeError, ValueError):
        return False
    return 2000 <= annee <= 2100


def arrieres_membre(con, membre_id, jusqua=None):
    """Dictionnaire {année: [mois impayés]} pour toutes les années passées.

    C'est la vue dont on a besoin pour payer des arriérés : on voit en un
    coup d'œil tout ce qui reste dû, exercice par exercice.
    """
    limite = jusqua or datetime.date.today().year
    resultat = {}
    for annee in sorted(annees_disponibles(con)):
        if annee > limite:
            continue
        impayes = mois_impayes(con, membre_id, annee)
        if impayes:
            resultat[annee] = impayes
    return resultat


def total_arrieres(con, membre_id):
    """Montant total restant dû, toutes années passées confondues."""
    total = 0
    for annee, mois in arrieres_membre(con, membre_id).items():
        camp = campagne(con, annee)
        mensuel = camp["montant_mensuel"] if camp else 1000
        payes = mois_payes(con, membre_id, annee)
        for m in mois:
            total += max(0, mensuel - payes.get(m, 0))
    return total


# ---------------------------------------------------------------------
#  Situation d'un membre
# ---------------------------------------------------------------------
def mois_payes(con, membre_id, annee):
    """Dictionnaire {mois: montant} des mois réglés pour ce membre et cette
    année. Calculé sur les affectations."""
    return {r["mois"]: r["montant"] for r in con.execute("""
        SELECT a.mois, SUM(a.montant) AS montant
        FROM affectations a
        JOIN paiements p ON p.id = a.paiement_id
        WHERE p.membre_id = ? AND a.annee = ?
        GROUP BY a.mois
    """, (membre_id, annee))}


def mois_echus(con, annee):
    """Nombre de mois réellement échus sur l'exercice.

    Année passée : 12. Année en cours : le mois courant. Année future : 0.
    Un exercice décalé (date_debut / date_fin) est ramené à ses bornes.
    """
    aujourdhui = datetime.date.today()
    camp = campagne(con, annee)
    debut = fin = None
    if camp is not None:
        # sqlite3.Row n'a pas de .get() : on teste les clés explicitement
        try:
            dd, df = camp["date_debut"], camp["date_fin"]
        except (IndexError, KeyError):
            dd = df = None
        if dd and df:
            try:
                debut = datetime.datetime.strptime(
                    str(dd), "%Y-%m-%d").date()
                fin = datetime.datetime.strptime(
                    str(df), "%Y-%m-%d").date()
            except ValueError:
                debut = fin = None
    if debut is None:
        debut = datetime.date(annee, 1, 1)
        fin = datetime.date(annee, 12, 31)
    if aujourdhui < debut:
        return 0
    borne = min(aujourdhui, fin)
    return (borne.year - debut.year) * 12 + (borne.month - debut.month) + 1


def situation(con, membre_id, annee):
    """Renvoie un dictionnaire décrivant la situation d'un membre :
    montant mensuel, mois payés, total versé, attendu, solde."""
    camp = campagne(con, annee)
    mensuel = camp["montant_mensuel"] if camp else 1000
    payes = mois_payes(con, membre_id, annee)
    verse = sum(payes.values())
    echus = mois_echus(con, annee)
    attendu = mensuel * echus
    return {
        "membre_id": membre_id,
        "annee": annee,
        "montant_mensuel": mensuel,
        "mois_payes": payes,
        "nb_mois": len(payes),
        "mois_echus": echus,
        "verse": verse,
        "attendu": attendu,
        "solde": attendu - verse,
        "complet": bool(payes) and echus > 0 and len(
            [m for m in payes if m <= echus and payes[m] >= mensuel]) == echus,
    }


def mois_impayes(con, membre_id, annee, jusqua=None):
    """Liste des mois non réglés (ou partiellement) jusqu'au mois courant."""
    sit = situation(con, membre_id, annee)
    limite = jusqua or (12 if annee < datetime.date.today().year
                        else datetime.date.today().month)
    payes = sit["mois_payes"]
    return [m for m in range(1, limite + 1)
            if payes.get(m, 0) < sit["montant_mensuel"]]


# ---------------------------------------------------------------------
#  Enregistrer un versement
# ---------------------------------------------------------------------
def verifier_date(valeur):
    """Renvoie la date au format ISO (AAAA-MM-JJ) ou leve ErreurSaisie.

    Accepte AAAA-MM-JJ, JJ/MM/AAAA et JJ-MM-AAAA.
    """
    if isinstance(valeur, (datetime.date, datetime.datetime)):
        return valeur.strftime("%Y-%m-%d")
    texte = str(valeur).strip()
    if not texte:
        raise db.ErreurSaisie("La date du versement est obligatoire.")
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.datetime.strptime(texte, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    raise db.ErreurSaisie(
        "Date invalide : %r. Utilisez le format JJ/MM/AAAA "
        "(par exemple 31/12/2026)." % (texte,))


def enregistrer_versement(con, membre_id, annee, mois_coches, date_paiement,
                          montant_total=None, mode="especes",
                          reference=None, observation=None):
    """
    Enregistre un versement qui couvre les mois listés dans `mois_coches`
    (numéros de 1 à 12).

    - Si `montant_total` est None, il est calculé : nb_mois × montant mensuel.
    - Un seul paiement est créé, avec une affectation par mois.
    - Les mois déjà payés sont refusés pour éviter un double comptage.
    """
    if not mois_coches:
        raise db.ErreurSaisie("Cochez au moins un mois à régler.")

    # -- validations : message clair plutot qu'une erreur SQLite brute --
    echus = mois_echus(con, annee)
    hors = sorted({m for m in mois_coches
                   if not isinstance(m, int) or not 1 <= m <= 12})
    if hors:
        raise db.ErreurSaisie(
            "Mois invalide : %s. Les mois vont de 1 (janvier) à 12 "
            "(décembre)." % ", ".join(str(m) for m in hors))
    futures = sorted(m for m in mois_coches if echus and m > echus)
    if futures:
        raise db.ErreurSaisie(
            "Ces mois ne sont pas encore échus pour %s : %s. "
            "Seuls les %d premiers mois peuvent être réglés."
            % (annee, ", ".join(MOIS_NOMS[m - 1] for m in futures), echus))
    if con.execute("SELECT 1 FROM membres WHERE id = ?",
                   (membre_id,)).fetchone() is None:
        raise db.ErreurSaisie("Ce membre n'existe pas (identifiant %r)."
                              % (membre_id,))
    if date_paiement is not None:
        date_paiement = verifier_date(date_paiement)

    camp = campagne(con, annee)
    if camp is None:
        creer_campagne(con, annee)
        camp = campagne(con, annee)
    mensuel = camp["montant_mensuel"]

    # refus des doublons
    deja = mois_payes(con, membre_id, annee)
    conflits = [m for m in mois_coches
                if deja.get(m, 0) >= mensuel]
    if conflits:
        noms = ", ".join(MOIS_NOMS[m - 1] for m in sorted(conflits))
        raise db.ErreurSaisie(
            f"{noms} : déjà réglé(s) pour ce membre. "
            f"Décochez-les ou corrigez le versement existant.")

    if montant_total in (None, ""):
        montant_total = mensuel * len(mois_coches)
    try:
        montant_total = float(montant_total)
    except (TypeError, ValueError):
        raise db.ErreurSaisie("Le montant doit être un nombre.")

    if montant_total <= 0:
        raise db.ErreurSaisie("Le montant doit être supérieur à zéro.")

    # répartition du montant sur les mois cochés
    part = round(montant_total / len(mois_coches), 2)
    try:
        cur = con.execute("""
            INSERT INTO paiements
                (membre_id, campagne_id, date_paiement, montant_total,
                 mode, reference, observation)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (membre_id, camp["id"], str(date_paiement), montant_total,
              mode, reference, observation))
        paiement_id = cur.lastrowid
        for m in mois_coches:
            con.execute(
                "INSERT INTO affectations (paiement_id, annee, mois, montant) "
                "VALUES (?, ?, ?, ?)", (paiement_id, annee, m, part))
        con.commit()
    except Exception as e:
        con.rollback()
        raise db.ErreurSaisie(f"Enregistrement impossible : {e}")

    return paiement_id


def supprimer_versement(con, paiement_id):
    """Supprime un versement et ses affectations."""
    con.execute("DELETE FROM affectations WHERE paiement_id = ?", (paiement_id,))
    con.execute("DELETE FROM paiements WHERE id = ?", (paiement_id,))
    con.commit()


def versements_membre(con, membre_id, annee=None):
    """Historique des versements d'un membre."""
    sql = """
        SELECT p.id, p.date_paiement, p.montant_total, p.mode, p.reference,
               p.observation,
               (SELECT GROUP_CONCAT(a.mois)
                  FROM affectations a WHERE a.paiement_id = p.id) AS mois,
               (SELECT MIN(a.annee) FROM affectations a
                  WHERE a.paiement_id = p.id) AS premiere_annee
        FROM paiements p
        WHERE p.membre_id = ?
    """
    params = [membre_id]
    if annee is not None:
        sql += """ AND EXISTS (SELECT 1 FROM affectations a
                                WHERE a.paiement_id = p.id AND a.annee = ?)"""
        params.append(annee)
    sql += " ORDER BY p.date_paiement DESC, p.id DESC"
    return con.execute(sql, params).fetchall()


def date_fr(valeur):
    """« 2024-12-31 » -> « 31/12/2024 ». Renvoie la valeur telle quelle si
    elle n'est pas reconnue (affichage, jamais de perte d'information)."""
    if not valeur:
        return ""
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.datetime.strptime(str(valeur), fmt).strftime(
                "%d/%m/%Y")
        except ValueError:
            continue
    return str(valeur)


def mois_en_lettres(mois_csv):
    """« 1,2,3 » -> « Janv, Févr, Mars »."""
    if not mois_csv:
        return ""
    return ", ".join(MOIS_COURTS[int(m) - 1]
                     for m in sorted({int(x) for x in mois_csv.split(",")}))


# ---------------------------------------------------------------------
#  Statistiques globales (calculées sur les affectations)
# ---------------------------------------------------------------------
def totaux_par_annee(con):
    return con.execute("""
        SELECT annee, COUNT(*) AS nb_mois, SUM(montant) AS total
        FROM affectations GROUP BY annee ORDER BY annee DESC
    """).fetchall()


def totaux_par_famille(con, annee):
    return con.execute("""
        SELECT cl.nom AS clan, gf.nom AS grande_famille,
               f.nom AS famille, COUNT(DISTINCT p.membre_id) AS cotisants,
               SUM(a.montant) AS total
        FROM affectations a
        JOIN paiements p ON p.id = a.paiement_id
        JOIN membres m ON m.id = p.membre_id
        JOIN familles f ON f.id = m.famille_id
        JOIN lignees l ON l.id = f.lignee_id
        JOIN grandes_familles gf ON gf.id = l.grande_famille_id
        JOIN clans cl ON cl.id = gf.clan_id
        WHERE a.annee = ?
        GROUP BY f.id
        ORDER BY cl.nom, gf.nom, f.nom
    """, (annee,)).fetchall()
