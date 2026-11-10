use chrono::{Datelike, NaiveDate};
use rusqlite::{params, Connection};

use crate::domaine::{EcheanceImpayee, Paiement, Solde, Ventilation};
use crate::erreur::Erreur;
use crate::recus;

/// Échéances **échues** et encore impayées d'un membre sur un exercice,
/// de la plus ancienne à la plus récente.
///
/// « Échue » = sa date est atteinte à la date du versement. C'est la règle qui
/// manquait à la v1 : sur un exercice 01/04 → 31/03, régler 8 mois doit
/// créditer avril→novembre, jamais janvier→mars de l'année suivante.
pub fn echeances_impayees(
    con: &Connection,
    membre_id: i64,
    exercice_id: i64,
    date_paiement: NaiveDate,
) -> Result<Vec<EcheanceImpayee>, Erreur> {
    let mut stmt = con.prepare(
        "SELECT e.id, e.annee, e.mois, e.date_echeance,
                e.montant_du - IFNULL(pay.paye, 0) AS reste
           FROM echeances e
           JOIN membres m
             ON m.id = ?1
            AND m.statut = 'actif'
            AND (m.date_entree IS NULL OR date(m.date_entree) <= date(e.date_echeance))
            AND (m.date_sortie IS NULL OR date(m.date_sortie) >= date(e.date_echeance))
           LEFT JOIN (SELECT a.echeance_id AS echeance_id,
                             SUM(a.montant)  AS paye
                        FROM affectations a
                        JOIN paiements p ON p.id = a.paiement_id
                       WHERE p.membre_id = ?1
                       GROUP BY a.echeance_id) pay
             ON pay.echeance_id = e.id
          WHERE e.exercice_id = ?2
            AND date(e.date_echeance) <= date(?3)
            AND e.montant_du - IFNULL(pay.paye, 0) > 0
          ORDER BY e.annee, e.mois",
    )?;

    let lignes = stmt.query_map(
        params![membre_id, exercice_id, date_paiement.to_string()],
        |l| {
            let date: String = l.get(3)?;
            Ok((
                l.get::<_, i64>(0)?,
                l.get::<_, i32>(1)?,
                l.get::<_, u32>(2)?,
                date,
                l.get::<_, i64>(4)?,
            ))
        },
    )?;

    let mut resultat = Vec::new();
    for ligne in lignes {
        let (echeance_id, annee, mois, date, reste) = ligne?;
        let date_echeance = NaiveDate::parse_from_str(&date, "%Y-%m-%d")
            .map_err(|_| Erreur::DateInvalide(date.clone()))?;
        resultat.push(EcheanceImpayee {
            echeance_id,
            annee,
            mois,
            date_echeance,
            reste,
        });
    }
    Ok(resultat)
}

/// Solde d'un membre sur un exercice, ou `None` s'il n'y est pas assujetti
/// (statut non actif, ou bornes d'entrée/sortie hors période).
pub fn solde(con: &Connection, membre_id: i64, exercice_id: i64) -> Result<Option<Solde>, Erreur> {
    let mut stmt = con.prepare(
        "SELECT mois_dus, du, paye, reste, mois_a_jour
           FROM v_solde_membre_exercice
          WHERE membre_id = ?1 AND exercice_id = ?2",
    )?;
    let mut lignes = stmt.query(params![membre_id, exercice_id])?;
    match lignes.next()? {
        Some(l) => Ok(Some(Solde {
            exercice_id,
            mois_dus: l.get(0)?,
            du: l.get(1)?,
            paye: l.get(2)?,
            reste: l.get(3)?,
            mois_a_jour: l.get(4)?,
        })),
        None => Ok(None),
    }
}

/// Enregistre un versement : ventilation en cascade, écriture du paiement,
/// numéro de reçu et contrôle d'incohérence, **dans une seule transaction**.
///
/// Refus possibles (aucune écriture) :
/// - `Reliquat` : le montant dépasse le total des échéances échues impayées ;
/// - `AucuneEcheance` : tout est déjà réglé, ou rien n'est encore échu.
pub fn ventiler(
    con: &mut Connection,
    membre_id: i64,
    exercice_id: i64,
    total: i64,
    date_paiement: NaiveDate,
    mode: &str,
) -> Result<Paiement, Erreur> {
    if total <= 0 {
        return Err(Erreur::MontantInvalide(total));
    }

    let tx = con.transaction()?;

    let membre_existe: bool = tx.query_row(
        "SELECT EXISTS (SELECT 1 FROM membres WHERE id = ?1)",
        params![membre_id],
        |l| l.get(0),
    )?;
    if !membre_existe {
        return Err(Erreur::MembreInconnu(membre_id));
    }

    let exercice_existe: bool = tx.query_row(
        "SELECT EXISTS (SELECT 1 FROM exercices WHERE id = ?1)",
        params![exercice_id],
        |l| l.get(0),
    )?;
    if !exercice_existe {
        return Err(Erreur::ExerciceInconnu(exercice_id));
    }

    let impayees = echeances_impayees(&tx, membre_id, exercice_id, date_paiement)?;
    if impayees.is_empty() {
        return Err(Erreur::AucuneEcheance);
    }

    let mut reste = total;
    let mut plan: Vec<Ventilation> = Vec::new();
    for echeance in &impayees {
        if reste == 0 {
            break;
        }
        let part = echeance.reste.min(reste);
        if part > 0 {
            plan.push(Ventilation {
                echeance_id: echeance.echeance_id,
                annee: echeance.annee,
                mois: echeance.mois,
                montant: part,
            });
            reste -= part;
        }
    }
    if reste > 0 {
        return Err(Erreur::Reliquat(total, reste));
    }

    tx.execute(
        "INSERT INTO paiements (membre_id, date_paiement, montant_total, mode)
         VALUES (?1, ?2, ?3, ?4)",
        params![membre_id, date_paiement.to_string(), total, mode],
    )?;
    let paiement_id = tx.last_insert_rowid();

    let numero = recus::numero_suivant(&tx, date_paiement.year())?;
    tx.execute(
        "UPDATE paiements SET numero_recu = ?1 WHERE id = ?2",
        params![numero, paiement_id],
    )?;

    for part in &plan {
        tx.execute(
            "INSERT INTO affectations (paiement_id, echeance_id, montant)
             VALUES (?1, ?2, ?3)",
            params![paiement_id, part.echeance_id, part.montant],
        )?;
    }

    // GARDE-FOU : l'invariant doit tenir avant de valider la transaction.
    let incoherents: i64 =
        tx.query_row("SELECT COUNT(*) FROM v_paiements_incoherents", [], |l| {
            l.get(0)
        })?;
    if incoherents > 0 {
        return Err(Erreur::Incoherence);
    }

    tx.commit()?;
    Ok(Paiement {
        id: paiement_id,
        numero_recu: numero,
        montant_total: total,
        affectations: plan,
    })
}
