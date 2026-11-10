//! Cœur métier du Fonds d'Entraide.
//!
//! Ce crate ne connaît ni Tauri ni l'interface : il ne manipule que des types
//! du domaine et une base SQLite au schéma v2 (`schema_v2.sql`). C'est ce qui
//! permet de tester l'argent (`cargo test`) sans lancer de fenêtre.
//!
//! Règles appliquées ici, conformes aux décisions D1–D3 du plan :
//! - une échéance est un mois civil d'un exercice (D1) ;
//! - les montants sont des entiers de FCFA (D2) ;
//! - un versement se ventile en cascade sur les échéances **échues** impayées,
//!   sans dépasser le reste dû, et tout reliquat est refusé (D3).

#![forbid(unsafe_code)]

pub mod db;
pub mod domaine;
pub mod erreur;
pub mod hierarchie;
pub mod membres;
pub mod noeuds;
pub mod recus;
pub mod ventilation;

// Réexporté pour que la coquille Tauri n'ait pas à dépendre de rusqlite
// dans une version potentiellement différente.
pub use rusqlite;

pub use domaine::{EcheanceImpayee, Paiement, Solde, Ventilation};
pub use erreur::Erreur;
