"""
recus.py — Reçus de paiement : numérotation, montant en lettres, données.

Ce module ne touche pas à l'interface : il prépare les données du reçu
(fichier PDF produit par `exports.recu_pdf`) à partir de la base.

Numérotation : `RECU-<année paiement>-<numéro>` (ex. RECU-2026-000147).
Le numéro est **stable** : il est stocké dans la table `parametres`
(clé `recu_numeros`) et n'est jamais réattribué, même si un versement est
supprimé ensuite. Le compteur ne fait que monter.
"""
import datetime
import json

import cotisations as C
import db
import parametres as P

CLE_NUMEROS = "recu_numeros"

UNITES = ("zéro", "un", "deux", "trois", "quatre", "cinq", "six", "sept",
          "huit", "neuf", "dix", "onze", "douze", "treize", "quatorze",
          "quinze", "seize", "dix-sept", "dix-huit", "dix-neuf")
DIZAINES = ("", "", "vingt", "trente", "quarante", "cinquante", "soixante",
            "soixante", "quatre-vingt", "quatre-vingt")


def _centaines(n):
    """0 à 999 en lettres."""
    if n == 0:
        return ""
    if n < 20:
        return UNITES[n]
    if n < 100:
        d, u = divmod(n, 10)
        if d in (7, 9):                     # 70-79 (soixante-dix…) et
            base = DIZAINES[d]              # 90-99 (quatre-vingt-dix…)
            reste = u + 10
            if reste == 10:
                return base + "-dix"
            if reste == 11:
                return base + " et onze"
            return base + "-" + UNITES[reste]
        if d == 8 and u == 0:               # 80
            return "quatre-vingts"
        base = DIZAINES[d]
        if u == 1 and d != 8:               # vingt et un, trente et un…
            return base + " et un"
        if u == 0:
            return base
        return base + "-" + UNITES[u]
    c, reste = divmod(n, 100)
    tete = "cent" if c == 1 else UNITES[c] + " cent"
    if reste == 0:
        return tete + ("s" if c > 1 else "")
    return tete + " " + _centaines(reste)


def montant_en_lettres(montant, devise="francs CFA"):
    """« 4500 » -> « quatre mille cinq cents francs CFA »."""
    try:
        valeur = float(montant)
    except (TypeError, ValueError):
        return ""
    entier = int(round(valeur))
    centimes = int(round((valeur - entier) * 100))
    if entier == 0:
        mots = "zéro"
    else:
        mots = _entier_en_lettres(entier)
    texte = mots + " " + devise
    if centimes:
        texte += " et %s centimes" % _entier_en_lettres(centimes)
    return texte[0].upper() + texte[1:]


def _entier_en_lettres(n):
    """Nombre entier positif en lettres (français)."""
    if n == 0:
        return "zéro"
    morceaux = []
    milliards, reste = divmod(n, 10 ** 9)
    millions, reste = divmod(reste, 10 ** 6)
    milliers, reste = divmod(reste, 1000)
    if milliards:
        morceaux.append(_centaines(milliards) +
                        (" milliard" if milliards == 1 else " milliards"))
    if millions:
        morceaux.append(_centaines(millions) +
                        (" million" if millions == 1 else " millions"))
    if milliers:
        if milliers == 1:
            morceaux.append("mille")
        else:
            morceaux.append(_centaines(milliers) + " mille")
    if reste:
        morceaux.append(_centaines(reste))
    return " ".join(morceaux)


# ---------------------------------------------------------------------
#  Numérotation des reçus
# ---------------------------------------------------------------------
def _lire_compteurs(con):
    brut = P.lire_parametre(con, CLE_NUMEROS, "")
    if not brut:
        return {}
    try:
        data = json.loads(brut)
    except (TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _ecrire_compteurs(con, compteurs):
    P.ecrire_parametre(con, CLE_NUMEROS, json.dumps(compteurs))


def numero_existant(con, paiement_id):
    """Numéro de reçu déjà attribué à ce versement, ou None."""
    return P.lire_parametre(con, "recu_paiement_%d" % paiement_id, None)


def attribuer_numero(con, paiement_id, annee):
    """Renvoie le numéro de reçu du versement, en le créant si besoin.

    Le numéro est mémorisé par versement : réimprimer un reçu ne change
    jamais son numéro.
    """
    cle_paiement = "recu_paiement_%d" % paiement_id
    deja = P.lire_parametre(con, cle_paiement, None)
    if deja:
        return deja
    compteurs = _lire_compteurs(con)
    suivant = int(compteurs.get(str(annee), 0)) + 1
    compteurs[str(annee)] = suivant
    numero = "RECU-%s-%06d" % (annee, suivant)
    P.ecrire_parametre(con, cle_paiement, numero)
    _ecrire_compteurs(con, compteurs)
    return numero


def prochain_numero(con, annee):
    """Numéro qui SERA attribué au prochain versement de cette année."""
    compteurs = _lire_compteurs(con)
    return "RECU-%s-%06d" % (annee, int(compteurs.get(str(annee), 0)) + 1)


# ---------------------------------------------------------------------
#  Données du reçu
# ---------------------------------------------------------------------
def _membre_complet(con, membre_id):
    r = con.execute("""
        SELECT m.id, TRIM(m.nom || ' ' || IFNULL(m.prenom, '')) AS membre,
               IFNULL(m.telephone, '') AS telephone,
               f.nom AS famille, l.nom AS lignee,
               gf.nom AS grande_famille, c.nom AS clan
        FROM membres m
        JOIN familles f ON f.id = m.famille_id
        JOIN lignees l ON l.id = f.lignee_id
        JOIN grandes_familles gf ON gf.id = l.grande_famille_id
        JOIN clans c ON c.id = gf.clan_id
        WHERE m.id = ?
    """, (membre_id,)).fetchone()
    if r is None:
        raise db.ErreurSaisie("Membre introuvable dans la base.")
    return r


def donnees_recu(con, paiement_id, en_lettres=True, association=None,
                 siege=None, saisi_par=None):
    """Prépare le dictionnaire attendu par `exports.recu_pdf`."""
    p = con.execute("SELECT * FROM paiements WHERE id = ?",
                    (paiement_id,)).fetchone()
    if p is None:
        raise db.ErreurSaisie("Versement introuvable dans la base.")
    m = _membre_complet(con, p["membre_id"])

    lignes = con.execute("""
        SELECT annee, mois, montant FROM affectations
        WHERE paiement_id = ? ORDER BY annee, mois
    """, (paiement_id,)).fetchall()
    if not lignes:
        raise db.ErreurSaisie("Ce versement n'a aucun mois affecté.")

    annees = sorted({r["annee"] for r in lignes})
    exercice = lignes[0]["annee"]
    mois = [C.MOIS_COURTS[r["mois"] - 1] for r in lignes
            if r["annee"] == exercice]
    if len(annees) > 1:
        # versement couvrant deux exercices : on précise l'année par mois
        mois = ["%s %s" % (C.MOIS_COURTS[r["mois"] - 1], r["annee"])
                for r in lignes]

    mode = dict(C.MODES).get(p["mode"], p["mode"])
    montant = float(p["montant_total"])
    numero = attribuer_numero(con, paiement_id, exercice)
    texte_lettres = ""
    if en_lettres:
        texte_lettres = montant_en_lettres(montant)

    return {
        "numero": numero,
        "date": C.date_fr(p["date_paiement"]),
        "membre": m["membre"],
        "telephone": m["telephone"],
        "clan": m["clan"],
        "grande_famille": m["grande_famille"],
        "lignee": m["lignee"],
        "famille": m["famille"],
        "exercice": exercice,
        "annees": annees,
        "mois": mois,
        "montant": montant,
        "montant_total_lettres": texte_lettres,
        "mode": mode,
        "reference": p["reference"] or "",
        "observation": p["observation"] or "",
        "association": (association or
                        P.lire_parametre(con, "recu_association",
                                         "FOND D'ENTRAIDE")),
        "siege": (siege if siege is not None
                  else P.lire_parametre(con, "recu_siege", "")),
        "saisi_par": (saisi_par if saisi_par is not None
                      else (P.lire_parametre(con, "recu_caissier", "") or "")),
        "paiement_id": paiement_id,
        "date_edition": datetime.datetime.now().strftime("%d/%m/%Y %H:%M"),
    }
