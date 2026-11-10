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
