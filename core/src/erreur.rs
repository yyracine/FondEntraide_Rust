use thiserror::Error;

/// Erreurs métier du cœur. Aucune erreur SQLite brute ne doit atteindre
/// l'interface : les commandes Tauri les convertissent en `{ code, message }`.
#[derive(Debug, Error)]
pub enum Erreur {
    #[error("montant invalide : {0} F")]
    MontantInvalide(i64),

    #[error("membre inconnu : {0}")]
    MembreInconnu(i64),

    #[error("exercice inconnu : {0}")]
    ExerciceInconnu(i64),

    #[error("versement inconnu : {0}")]
    PaiementInconnu(i64),

    #[error("aucune échéance échue à régler sur cet exercice")]
    AucuneEcheance,

    #[error("{0} F ne peuvent pas être affectés : {1} F resteraient non ventilés")]
    Reliquat(i64, i64),

    #[error("date illisible en base : {0}")]
    DateInvalide(String),

    #[error("date attendue au format AAAA-MM-JJ : {0}")]
    DateMalFormee(String),

    #[error("{0} est obligatoire")]
    ChampRequis(&'static str),

    #[error("{0}")]
    ChampIncoherent(String),

    #[error("famille inconnue : {0}")]
    FamilleInconnue(i64),

    #[error("statut inconnu : {0}")]
    StatutInvalide(String),

    #[error("sexe attendu M ou F : {0}")]
    SexeInvalide(String),

    #[error("le parent doit appartenir à la même famille que le membre")]
    ParentHorsFamille,

    #[error("parent invalide : {0}")]
    ParentInvalide(String),

    #[error("suppression impossible : {0}")]
    SuppressionRefusee(String),

    #[error("{0} inconnu : {1}")]
    NoeudInconnu(&'static str, i64),

    #[error("un nœud de ce nom existe déjà : {0}")]
    NomDejaPris(String),

    #[error("le tarif doit être supérieur à zéro")]
    TarifInvalide,

    #[error(
        "paiement incohérent après écriture : montant total différent de la somme des affectations"
    )]
    Incoherence,

    #[error("schéma incompatible : version {trouve} trouvée, {attendu} attendue")]
    SchemaIncompatible { trouve: i64, attendu: i64 },

    #[error("base de données : {0}")]
    Sql(#[from] rusqlite::Error),
}
