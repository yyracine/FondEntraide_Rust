//! Coquille Tauri : aucune règle métier ici, seulement l'ouverture de la base
//! et des commandes qui délèguent au crate `fonds-core`.

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::path::PathBuf;
use std::sync::Mutex;

use fonds_core::rusqlite::Connection;
use fonds_core::{db, domaine, hierarchie, ventilation};

/// État partagé : une connexion, ou l'erreur qui empêche de l'ouvrir (affichée
/// dans l'interface plutôt que de faire tomber la fenêtre).
struct Etat {
    base: Result<Mutex<Connection>, String>,
}

impl Etat {
    fn ouvrir() -> Self {
        let chemin = chemin_base();
        let base = match db::ouvrir(&chemin) {
            Ok(con) => Ok(Mutex::new(con)),
            Err(erreur) => Err(format!(
                "Base introuvable ou illisible : {} — {erreur}",
                chemin.display()
            )),
        };
        Etat { base }
    }

    fn avec<T>(
        &self,
        requete: impl FnOnce(&Connection) -> Result<T, fonds_core::Erreur>,
    ) -> Result<T, String> {
        let verrou = self.base.as_ref().map_err(|e| e.clone())?;
        let con = verrou
            .lock()
            .map_err(|_| "verrou de base empoisonné".to_string())?;
        requete(&con).map_err(|e| e.to_string())
    }
}

/// Ordre de recherche de la base :
/// 1. variable d'environnement `FONDS_DB` (tests, base partagée) ;
/// 2. fichier posé à côté de l'exécutable (installation) ;
/// 3. racine du projet (développement).
fn chemin_base() -> PathBuf {
    if let Some(chemin) = std::env::var_os("FONDS_DB") {
        return PathBuf::from(chemin);
    }

    if let Ok(exe) = std::env::current_exe() {
        if let Some(dossier) = exe.parent() {
            let candidat = dossier.join("cotisations_v2.db");
            if candidat.exists() {
                return candidat;
            }
        }
    }

    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .map(|racine| racine.join("cotisations_v2.db"))
        .unwrap_or_else(|| PathBuf::from("cotisations_v2.db"))
}

#[tauri::command]
fn resume(etat: tauri::State<Etat>) -> Result<hierarchie::Resume, String> {
    etat.avec(hierarchie::resume)
}

#[tauri::command]
fn clans(etat: tauri::State<Etat>) -> Result<Vec<hierarchie::Clan>, String> {
    etat.avec(hierarchie::clans)
}

#[tauri::command]
fn grandes_familles(
    etat: tauri::State<Etat>,
    clan_id: i64,
) -> Result<Vec<hierarchie::GrandeFamille>, String> {
    etat.avec(|con| hierarchie::grandes_familles(con, clan_id))
}

#[tauri::command]
fn lignees(
    etat: tauri::State<Etat>,
    grande_famille_id: i64,
) -> Result<Vec<hierarchie::Lignee>, String> {
    etat.avec(|con| hierarchie::lignees(con, grande_famille_id))
}

#[tauri::command]
fn familles(etat: tauri::State<Etat>, lignee_id: i64) -> Result<Vec<hierarchie::Famille>, String> {
    etat.avec(|con| hierarchie::familles(con, lignee_id))
}

#[tauri::command]
fn exercices(etat: tauri::State<Etat>) -> Result<Vec<hierarchie::Exercice>, String> {
    etat.avec(hierarchie::exercices)
}

/// Enregistre un versement : la ventilation, le numéro de reçu et le contrôle
/// d'incohérence sont faits par `ventilation::ventiler_iso`, dans une seule
/// transaction. Ici, on ne fait que tenir le verrou d'écriture.
#[tauri::command]
fn enregistrer_paiement(
    etat: tauri::State<Etat>,
    membre_id: i64,
    exercice_id: i64,
    montant: i64,
    date_paiement: String,
    mode: String,
) -> Result<domaine::Paiement, String> {
    let verrou = etat.base.as_ref().map_err(|e| e.clone())?;
    let mut con = verrou
        .lock()
        .map_err(|_| "verrou de base empoisonné".to_string())?;
    ventilation::ventiler_iso(
        &mut con,
        membre_id,
        exercice_id,
        montant,
        &date_paiement,
        &mode,
    )
    .map_err(|e| e.to_string())
}

/// Répartition prévisionnelle : quels mois, quelles années, et quelle part
/// resterait sans imputation. Lecture seule, appelée à chaque frappe.
#[tauri::command]
fn previsualiser(
    etat: tauri::State<Etat>,
    membre_id: i64,
    exercice_id: i64,
    montant: i64,
    date_paiement: String,
) -> Result<domaine::PlanVentilation, String> {
    etat.avec(|con| {
        ventilation::plan_ventilation_iso(con, membre_id, exercice_id, montant, &date_paiement)
    })
}

/// Recherche par nom ou prénom dans toute la base : encaisser ne doit pas
/// obliger à descendre clan → grande famille → lignée → famille.
#[tauri::command]
fn rechercher_membres(
    etat: tauri::State<Etat>,
    recherche: String,
    exercice_id: Option<i64>,
) -> Result<Vec<hierarchie::MembreTrouve>, String> {
    etat.avec(|con| {
        hierarchie::rechercher_membres(con, None, Some(recherche.as_str()), exercice_id, None, 25)
    })
}

/// Soldes d'un membre précis, pour rafraîchir la feuille après un versement
/// même quand le membre a été trouvé par la recherche.
#[tauri::command]
fn membre(
    etat: tauri::State<Etat>,
    membre_id: i64,
    exercice_id: Option<i64>,
) -> Result<Option<hierarchie::MembreResume>, String> {
    etat.avec(|con| hierarchie::membre(con, membre_id, exercice_id, None))
}

#[tauri::command]
fn membres(
    etat: tauri::State<Etat>,
    famille_id: i64,
    recherche: Option<String>,
    exercice_id: Option<i64>,
    date_reference: Option<String>,
) -> Result<Vec<hierarchie::MembreResume>, String> {
    etat.avec(|con| {
        hierarchie::membres(
            con,
            famille_id,
            recherche.as_deref(),
            exercice_id,
            date_reference.as_deref(),
        )
    })
}

fn main() {
    let etat = Etat::ouvrir();

    tauri::Builder::default()
        .manage(etat)
        .invoke_handler(tauri::generate_handler![
            resume,
            exercices,
            enregistrer_paiement,
            previsualiser,
            rechercher_membres,
            membre,
            clans,
            grandes_familles,
            lignees,
            familles,
            membres
        ])
        .run(tauri::generate_context!())
        .expect("échec du lancement de Tauri");
}
