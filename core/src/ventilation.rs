use chrono::{Datelike, NaiveDate};
use rusqlite::{params, Connection};

use crate::domaine::{
    EcheanceImpayee, MoisMembre, Paiement, PaiementHistorique, PlanVentilation, Solde, Ventilation,
};
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

/// Variante de [`ventiler`] qui reçoit la date en ISO (`AAAA-MM-JJ`), pour
/// que la coquille Tauri n'ait pas à manipuler `chrono`.
pub fn ventiler_iso(
    con: &mut Connection,
    membre_id: i64,
    exercice_id: i64,
    total: i64,
    date_paiement: &str,
    mode: &str,
) -> Result<Paiement, Erreur> {
    let date = NaiveDate::parse_from_str(date_paiement, "%Y-%m-%d")
        .map_err(|_| Erreur::DateInvalide(date_paiement.to_string()))?;
    ventiler(con, membre_id, exercice_id, total, date, mode)
}

/// Cascade : chaque franc va au mois échu le plus ancien encore impayé.
///
/// Ne touche à rien : sert à montrer à l'utilisateur, avant validation, quels
/// mois et quelles années son versement va couvrir, et quelle part dépasserait
/// le dû (au lieu de le lui refuser après coup).
pub fn plan_ventilation(
    con: &Connection,
    membre_id: i64,
    exercice_id: i64,
    total: i64,
    date_paiement: NaiveDate,
) -> Result<PlanVentilation, Erreur> {
    if total <= 0 {
        return Err(Erreur::MontantInvalide(total));
    }

    let impayees = echeances_impayees(con, membre_id, exercice_id, date_paiement)?;
    if impayees.is_empty() {
        return Err(Erreur::AucuneEcheance);
    }

    let mut reste = total;
    let mut affectations: Vec<Ventilation> = Vec::new();
    for echeance in &impayees {
        if reste == 0 {
            break;
        }
        let part = echeance.reste.min(reste);
        if part > 0 {
            affectations.push(Ventilation {
                echeance_id: echeance.echeance_id,
                annee: echeance.annee,
                mois: echeance.mois,
                montant: part,
            });
            reste -= part;
        }
    }

    Ok(PlanVentilation {
        ventile: total - reste,
        reliquat: reste,
        affectations,
    })
}

/// Variante de [`plan_ventilation`] qui reçoit la date en ISO (`AAAA-MM-JJ`).
pub fn plan_ventilation_iso(
    con: &Connection,
    membre_id: i64,
    exercice_id: i64,
    total: i64,
    date_paiement: &str,
) -> Result<PlanVentilation, Erreur> {
    let date = NaiveDate::parse_from_str(date_paiement, "%Y-%m-%d")
        .map_err(|_| Erreur::DateInvalide(date_paiement.to_string()))?;
    plan_ventilation(con, membre_id, exercice_id, total, date)
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

    let plan = plan_ventilation(&tx, membre_id, exercice_id, total, date_paiement)?;
    if plan.reliquat > 0 {
        return Err(Erreur::Reliquat(total, plan.reliquat));
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

    for part in &plan.affectations {
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
        affectations: plan.affectations,
    })
}

/// Versements d'un membre, du plus récent au plus ancien, avec les mois que
/// chacun a couverts. Une seule requête : on ne relit pas les affectations
/// paiement par paiement.
pub fn historique_paiements(
    con: &Connection,
    membre_id: i64,
) -> Result<Vec<PaiementHistorique>, Erreur> {
    let mut stmt = con.prepare(
        "SELECT p.id, p.date_paiement, p.montant_total, p.mode, p.numero_recu,
                a.montant, e.annee, e.mois
           FROM paiements p
           LEFT JOIN affectations a ON a.paiement_id = p.id
           LEFT JOIN echeances e    ON e.id = a.echeance_id
          WHERE p.membre_id = ?1
          ORDER BY date(p.date_paiement) DESC, p.id DESC, e.annee, e.mois",
    )?;

    let lignes = stmt.query_map(params![membre_id], |l| {
        Ok((
            PaiementHistorique {
                id: l.get(0)?,
                date_paiement: l.get(1)?,
                montant_total: l.get(2)?,
                mode: l.get(3)?,
                numero_recu: l.get(4)?,
                affectations: Vec::new(),
            },
            l.get::<_, Option<i64>>(5)?,
            l.get::<_, Option<i32>>(6)?,
            l.get::<_, Option<u32>>(7)?,
        ))
    })?;

    let mut resultat: Vec<PaiementHistorique> = Vec::new();
    for ligne in lignes {
        let (paiement, montant, annee, mois) = ligne?;
        let nouveau = resultat.last().map(|p| p.id) != Some(paiement.id);
        if nouveau {
            resultat.push(paiement);
        }
        if let (Some(montant), Some(annee), Some(mois)) = (montant, annee, mois) {
            if let Some(courant) = resultat.last_mut() {
                courant.affectations.push(Ventilation {
                    // L'échéance n'est pas nécessaire à l'affichage de la fiche.
                    echeance_id: 0,
                    annee,
                    mois,
                    montant,
                });
            }
        }
    }
    Ok(resultat)
}

/// Supprime un versement et libère les mois qu'il couvrait.
///
/// Décision D9 : l'annulation est permise (une erreur de saisie doit pouvoir
/// se corriger), mais le **numéro de reçu reste consommé** — `sequences`
/// n'est jamais décrémenté, donc un reçu supprimé ne peut pas être réattribué
/// à un autre versement.
pub fn supprimer_paiement(con: &mut Connection, paiement_id: i64) -> Result<(), Erreur> {
    let tx = con.transaction()?;

    let existe: bool = tx.query_row(
        "SELECT EXISTS (SELECT 1 FROM paiements WHERE id = ?1)",
        params![paiement_id],
        |l| l.get(0),
    )?;
    if !existe {
        return Err(Erreur::PaiementInconnu(paiement_id));
    }

    // Suppression explicite des affectations : on ne dépend pas du réglage
    // `foreign_keys` de la connexion pour libérer les échéances.
    tx.execute(
        "DELETE FROM affectations WHERE paiement_id = ?1",
        params![paiement_id],
    )?;
    tx.execute("DELETE FROM paiements WHERE id = ?1", params![paiement_id])?;

    // Le contrôle reste actif après suppression : aucun versement ne doit
    // sortir incohérent de la transaction.
    let incoherents: i64 =
        tx.query_row("SELECT COUNT(*) FROM v_paiements_incoherents", [], |l| {
            l.get(0)
        })?;
    if incoherents > 0 {
        return Err(Erreur::Incoherence);
    }

    tx.commit()?;
    Ok(())
}

/// Grille des échéances d'un membre sur un exercice, dans l'ordre des mois.
///
/// Toujours les douze cases d'un exercice complet : un mois hors période
/// d'adhésion est renvoyé avec `assujetti = false` et des montants nuls, plutôt
/// que supprimé. `date_reference` est la date à laquelle on juge l'échéance
/// échue (elle est injectée pour que les tests ne dépendent pas du jour réel).
pub fn grille_membre(
    con: &Connection,
    membre_id: i64,
    exercice_id: i64,
    date_reference: &str,
) -> Result<Vec<MoisMembre>, Erreur> {
    let reference = NaiveDate::parse_from_str(date_reference, "%Y-%m-%d")
        .map_err(|_| Erreur::DateInvalide(date_reference.to_string()))?;

    let mut stmt = con.prepare(
        "SELECT e.id, e.annee, e.mois, e.date_echeance, e.montant_du,
                CASE WHEN m.id IS NULL THEN 0 ELSE 1 END AS assujetti,
                IFNULL(pay.paye, 0) AS paye
           FROM echeances e
           LEFT JOIN membres m
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
          ORDER BY e.annee, e.mois",
    )?;

    let lignes = stmt.query_map(params![membre_id, exercice_id], |l| {
        let assujetti: i64 = l.get(5)?;
        let montant_du: i64 = l.get(4)?;
        let paye: i64 = l.get(6)?;
        let date_echeance: String = l.get(3)?;
        let (du, paye) = if assujetti == 1 {
            (montant_du, paye)
        } else {
            (0, 0)
        };
        Ok(MoisMembre {
            echeance_id: l.get(0)?,
            annee: l.get(1)?,
            mois: l.get(2)?,
            date_echeance,
            du,
            paye,
            reste: (du - paye).max(0),
            // Rempli après la collecte : la closure de `query_map` ne peut
            // renvoyer qu'une erreur rusqlite, pas une `Erreur` du domaine.
            echue: false,
            assujetti: assujetti == 1,
        })
    })?;

    let mut resultat = Vec::new();
    for ligne in lignes {
        let mut mois = ligne?;
        let jour_echeance = NaiveDate::parse_from_str(&mois.date_echeance, "%Y-%m-%d")
            .map_err(|_| Erreur::DateInvalide(mois.date_echeance.clone()))?;
        mois.echue = jour_echeance <= reference;
        resultat.push(mois);
    }
    Ok(resultat)
}
