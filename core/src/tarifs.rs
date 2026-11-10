//! Changement du tarif d'un exercice en cours d'année.
//!
//! Règle retenue avec l'adhérent : le nouveau montant prend effet au **mois**
//! choisi. Les échéances des mois antérieurs gardent leur montant, même
//! impayées ; celles du mois d'effet et des suivants prennent le nouveau
//! montant, sauf si elles sont déjà entièrement réglées — un reçu remis doit
//! rester juste.

use chrono::{Datelike, NaiveDate};
use rusqlite::{params, Connection, OptionalExtension};
use serde::Serialize;

use crate::erreur::Erreur;

/// Ce que le changement a réellement modifié, pour l'afficher dans l'écran.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct TarifChange {
    pub montant: i64,
    pub annee_effet: i32,
    pub mois_effet: u32,
    /// Échéances passées au nouveau montant.
    pub modifies: i64,
    /// Échéances laissées telles quelles (mois antérieurs ou déjà réglés).
    pub conserves: i64,
}

/// Clé comparable d'un mois : `202604` pour avril 2026.
fn cle_mois(date: &str) -> Result<i32, Erreur> {
    let jour = NaiveDate::parse_from_str(date, "%Y-%m-%d")
        .map_err(|_| Erreur::DateMalFormee(date.to_string()))?;
    Ok(jour.year() * 100 + jour.month() as i32)
}

/// Applique un nouveau tarif à partir du mois de `date_effet`.
pub fn changer(
    con: &mut Connection,
    exercice_id: i64,
    montant: i64,
    date_effet: &str,
) -> Result<TarifChange, Erreur> {
    if montant <= 0 {
        return Err(Erreur::TarifInvalide);
    }
    let effet = NaiveDate::parse_from_str(date_effet, "%Y-%m-%d")
        .map_err(|_| Erreur::DateMalFormee(date_effet.to_string()))?;
    let cle = effet.year() * 100 + effet.month() as i32;

    let tx = con.transaction()?;

    let bornes: Option<(String, String)> = tx
        .query_row(
            "SELECT date_debut, date_fin FROM exercices WHERE id = ?1",
            params![exercice_id],
            |l| Ok((l.get(0)?, l.get(1)?)),
        )
        .optional()?;
    let Some((debut, fin)) = bornes else {
        return Err(Erreur::ExerciceInconnu(exercice_id));
    };
    if cle < cle_mois(&debut)? || cle > cle_mois(&fin)? {
        return Err(Erreur::ChampIncoherent(
            "le mois d'effet doit appartenir à l'exercice".to_string(),
        ));
    }

    // Toutes les échéances de l'exercice : celles qui restent à l'ancien tarif
    // (mois antérieurs, ou mois réglés) sont comptées pour l'affichage.
    let total: i64 = tx.query_row(
        "SELECT COUNT(*) FROM echeances WHERE exercice_id = ?1",
        params![exercice_id],
        |l| l.get(0),
    )?;

    // Une échéance entièrement réglée garde son montant (reçu déjà remis), et
    // une baisse de tarif ne doit jamais passer sous ce qui est déjà payé.
    let modifies = tx.execute(
        "UPDATE echeances
            SET montant_du = ?2
          WHERE exercice_id = ?1
            AND annee * 100 + mois >= ?3
            AND montant_du > IFNULL((SELECT SUM(a.montant)
                                       FROM affectations a
                                      WHERE a.echeance_id = echeances.id), 0)
            AND ?2 >= IFNULL((SELECT SUM(a.montant)
                                FROM affectations a
                               WHERE a.echeance_id = echeances.id), 0)",
        params![exercice_id, montant, cle],
    )? as i64;

    // Le tarif de l'exercice suit : les échéances créées plus tard partiront
    // du nouveau montant, et l'écran affiche le tarif en vigueur.
    tx.execute(
        "UPDATE exercices SET montant_mensuel = ?2 WHERE id = ?1",
        params![exercice_id, montant],
    )?;
    tx.commit()?;

    Ok(TarifChange {
        montant,
        annee_effet: effet.year(),
        mois_effet: effet.month(),
        modifies,
        conserves: total - modifies,
    })
}
