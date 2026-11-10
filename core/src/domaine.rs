use chrono::NaiveDate;
use serde::Serialize;

/// Part d'un versement affectée à une échéance précise.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct Ventilation {
    pub echeance_id: i64,
    pub annee: i32,
    pub mois: u32,
    pub montant: i64,
}

/// Versement enregistré : un reçu, une date, une ventilation.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct Paiement {
    pub id: i64,
    pub numero_recu: String,
    pub montant_total: i64,
    pub affectations: Vec<Ventilation>,
}

/// Versement déjà enregistré, tel que la fiche du membre le relit : date, reçu,
/// mode et mois couverts.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct PaiementHistorique {
    pub id: i64,
    pub date_paiement: String,
    pub montant_total: i64,
    pub mode: String,
    pub numero_recu: Option<String>,
    pub affectations: Vec<Ventilation>,
}

/// Répartition **prévisionnelle** d'un versement : ce que les échéances échues
/// absorberaient, et la part qui resterait sans imputation. Aucune écriture.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct PlanVentilation {
    pub affectations: Vec<Ventilation>,
    /// Somme réellement imputée sur des mois échus.
    pub ventile: i64,
    /// Part du montant qu'aucun mois échu ne peut absorber.
    pub reliquat: i64,
}

/// Solde d'un membre sur un exercice (lecture de `v_solde_membre_exercice`).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Solde {
    pub exercice_id: i64,
    pub mois_dus: i64,
    pub du: i64,
    pub paye: i64,
    pub reste: i64,
    pub mois_a_jour: i64,
}

/// Échéance encore due par un membre, avec son reste à payer.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct EcheanceImpayee {
    pub echeance_id: i64,
    pub annee: i32,
    pub mois: u32,
    pub date_echeance: NaiveDate,
    pub reste: i64,
}

/// Un mois de la grille de la fiche : ce qui est dû, ce qui est payé, et l'état
/// de l'échéance. `assujetti = false` signale un mois hors période d'adhésion
/// (avant l'entrée ou après la sortie) : la grille garde ses douze cases.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct MoisMembre {
    pub echeance_id: i64,
    pub annee: i32,
    pub mois: u32,
    pub date_echeance: String,
    pub du: i64,
    pub paye: i64,
    pub reste: i64,
    /// La date d'échéance est atteinte à la date de référence demandée.
    pub echue: bool,
    pub assujetti: bool,
}
