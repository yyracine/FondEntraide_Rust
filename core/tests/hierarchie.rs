//! Vérifie les lectures qui alimentent l'interface, sur une copie de la base
//! migrée : chaque écran doit trouver ses données sans requête par ligne.

use std::path::PathBuf;

use chrono::{Datelike, NaiveDate};
use fonds_core::{db, hierarchie, ventilation};
use rusqlite::{params, Connection};

fn base() -> (tempfile::TempDir, Connection) {
    let dir = tempfile::tempdir().expect("dossier temporaire");
    let chemin = dir.path().join("cotisations.db");
    let source = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .expect("racine du projet")
        .join("cotisations_v2.db");
    std::fs::copy(&source, &chemin).unwrap_or_else(|e| {
        panic!(
            "copie de {} impossible ({e}) : lancer `python migrer_v2.py` d'abord",
            source.display()
        )
    });
    (dir, db::ouvrir(&chemin).expect("ouverture"))
}

fn jour(a: i32, m: u32, j: u32) -> NaiveDate {
    NaiveDate::from_ymd_opt(a, m, j).expect("date valide")
}

// L'export « tous les membres » doit voir la base entière, pas une famille.
#[test]
fn tous_les_membres_sortent_avec_leur_chemin() {
    let (_dir, con) = base();
    let membres = hierarchie::tous_membres(&con, None).expect("liste complète");

    let attendus: i64 = con
        .query_row("SELECT COUNT(*) FROM membres", [], |l| l.get(0))
        .unwrap();
    assert_eq!(membres.len() as i64, attendus, "aucun membre oublié");
    assert!(membres.len() > 500, "toute la base : {}", membres.len());
    assert!(
        membres.iter().all(|m| !m.chemin.is_empty()),
        "chaque ligne porte son chemin dans la hiérarchie"
    );
}

fn creer_membre(con: &Connection, famille_id: i64, nom: &str, entree: &str) -> i64 {
    con.execute(
        "INSERT INTO membres (famille_id, nom, prenom, statut, date_entree)
         VALUES (?1, ?2, 'Test', 'actif', ?3)",
        params![famille_id, nom, entree],
    )
    .unwrap();
    con.last_insert_rowid()
}

fn creer_exercice(
    con: &Connection,
    libelle: &str,
    debut: NaiveDate,
    fin: NaiveDate,
    montant: i64,
) -> i64 {
    con.execute(
        "INSERT INTO exercices (libelle, date_debut, date_fin, montant_mensuel)
         VALUES (?1, ?2, ?3, ?4)",
        params![libelle, debut.to_string(), fin.to_string(), montant],
    )
    .unwrap();
    let id = con.last_insert_rowid();

    let (mut annee, mut mois) = (debut.year(), debut.month());
    while (annee, mois) <= (fin.year(), fin.month()) {
        let premier = NaiveDate::from_ymd_opt(annee, mois, 1).unwrap();
        let date = if premier < debut { debut } else { premier };
        con.execute(
            "INSERT INTO echeances (exercice_id, annee, mois, date_echeance, montant_du)
             VALUES (?1, ?2, ?3, ?4, ?5)",
            params![id, annee, mois, date.to_string(), montant],
        )
        .unwrap();
        mois += 1;
        if mois == 13 {
            mois = 1;
            annee += 1;
        }
    }
    id
}

#[test]
fn le_resume_reflete_la_base() {
    let (_dir, con) = base();
    let r = hierarchie::resume(&con).unwrap();
    assert_eq!(r.clans, 7);
    assert_eq!(r.familles, 391);
    assert_eq!(r.membres, 599);
    assert_eq!(r.encaisse, 1_807_000);
}

#[test]
fn les_exercices_sont_listes_du_plus_recent_au_plus_ancien() {
    let (_dir, con) = base();
    let exos = hierarchie::exercices(&con).unwrap();
    assert_eq!(exos.len(), 3);
    assert_eq!(exos[0].annee, 2026);
    assert_eq!(exos[2].annee, 2024);
    assert_eq!(
        exos.iter().filter(|e| e.courant).count(),
        1,
        "un seul exercice contient la date du jour"
    );
    assert!(exos[0].courant, "l'exercice 2026 est le courant en 2026");
}

#[test]
fn chaque_niveau_se_descend_jusqu_aux_membres() {
    let (_dir, con) = base();
    let clans = hierarchie::clans(&con).unwrap();
    assert_eq!(clans.len(), 7);

    let mut trouve = false;
    for clan in &clans {
        for gf in hierarchie::grandes_familles(&con, clan.id).unwrap() {
            for lignee in hierarchie::lignees(&con, gf.id).unwrap() {
                for famille in hierarchie::familles(&con, lignee.id).unwrap() {
                    let membres = hierarchie::membres(&con, famille.id, None, None, None).unwrap();
                    if !membres.is_empty() {
                        assert!(!membres[0].nom.is_empty());
                        trouve = true;
                    }
                }
            }
        }
    }
    assert!(trouve, "au moins une famille doit contenir des membres");
}

#[test]
fn la_recherche_filtre_sur_le_nom_ou_le_prenom() {
    let (_dir, con) = base();

    // première famille non vide
    let mut famille_id = None;
    'externe: for clan in hierarchie::clans(&con).unwrap() {
        for gf in hierarchie::grandes_familles(&con, clan.id).unwrap() {
            for lignee in hierarchie::lignees(&con, gf.id).unwrap() {
                for famille in hierarchie::familles(&con, lignee.id).unwrap() {
                    if !hierarchie::membres(&con, famille.id, None, None, None)
                        .unwrap()
                        .is_empty()
                    {
                        famille_id = Some(famille.id);
                        break 'externe;
                    }
                }
            }
        }
    }
    let famille_id = famille_id.expect("famille peuplée");

    let tous = hierarchie::membres(&con, famille_id, None, None, None).unwrap();
    let cible = tous[0].nom.clone();
    let filtre = hierarchie::membres(&con, famille_id, Some(&cible), None, None).unwrap();

    assert!(!filtre.is_empty(), "la recherche doit retrouver {cible}");
    assert!(filtre.len() <= tous.len());
    let aiguille = cible.to_lowercase();
    for membre in &filtre {
        let dans_nom = membre.nom.to_lowercase().contains(&aiguille);
        let dans_prenom = membre
            .prenom
            .as_deref()
            .map(|p| p.to_lowercase().contains(&aiguille))
            .unwrap_or(false);
        assert!(
            dans_nom || dans_prenom,
            "{} ne correspond pas à {cible}",
            membre.nom
        );
    }
}

#[test]
fn les_montants_sont_filtres_par_exercice() {
    let (_dir, mut con) = base();
    let famille = con
        .query_row("SELECT id FROM familles ORDER BY id LIMIT 1", [], |l| {
            l.get(0)
        })
        .unwrap();
    let exercice = creer_exercice(
        &con,
        "Exercice 2036",
        jour(2036, 1, 1),
        jour(2036, 12, 31),
        1_000,
    );
    let membre = creer_membre(&con, famille, "ZZSOLDE", "2036-01-01");
    ventilation::ventiler(
        &mut con,
        membre,
        exercice,
        3_000,
        jour(2036, 11, 10),
        "especes",
    )
    .expect("3 mois réglés");

    let liste = hierarchie::membres(
        &con,
        famille,
        Some("ZZSOLDE"),
        Some(exercice),
        Some("2036-11-10"),
    )
    .unwrap();
    let m = liste.iter().find(|m| m.id == membre).expect("membre listé");
    assert_eq!(
        (m.du, m.paye, m.reste, m.arrieres),
        (12_000, 3_000, 9_000, 8_000),
        "11 mois échus, 3 payés : 8 000 F d'arriérés sur l'exercice 2036"
    );

    // au 5 janvier, seul janvier est échu — et il est payé
    let liste = hierarchie::membres(
        &con,
        famille,
        Some("ZZSOLDE"),
        Some(exercice),
        Some("2036-01-05"),
    )
    .unwrap();
    assert_eq!(liste[0].arrieres, 0);

    // un exercice antérieur ne doit rien contenir pour ce membre entré en 2036
    let ex2026 = con
        .query_row(
            "SELECT id FROM exercices WHERE date_debut LIKE '2026%'",
            [],
            |l| l.get::<_, i64>(0),
        )
        .unwrap();
    let liste = hierarchie::membres(
        &con,
        famille,
        Some("ZZSOLDE"),
        Some(ex2026),
        Some("2036-11-10"),
    )
    .unwrap();
    assert_eq!(
        (liste[0].du, liste[0].paye, liste[0].reste),
        (0, 0, 0),
        "aucune échéance 2026 : le membre entre en 2036"
    );

    // sans filtre, les trois exercices s'additionnent : 2036 seulement ici
    let liste =
        hierarchie::membres(&con, famille, Some("ZZSOLDE"), None, Some("2036-11-10")).unwrap();
    assert_eq!(liste[0].du, 12_000);
}

#[test]
fn les_familles_annoncent_leur_nombre_de_membres() {
    let (_dir, con) = base();
    let lignee = con
        .query_row("SELECT id FROM lignees ORDER BY id LIMIT 1", [], |l| {
            l.get(0)
        })
        .unwrap();

    con.execute(
        "INSERT INTO familles (lignee_id, nom) VALUES (?1, 'ZZFAMILLE')",
        params![lignee],
    )
    .unwrap();
    let famille = con.last_insert_rowid();

    let liste = hierarchie::familles(&con, lignee).unwrap();
    let vide = liste.iter().find(|f| f.id == famille).unwrap();
    assert_eq!(vide.membres, 0);

    creer_membre(&con, famille, "ZZUN", "2036-01-01");
    let liste = hierarchie::familles(&con, lignee).unwrap();
    let peuplee = liste.iter().find(|f| f.id == famille).unwrap();
    assert_eq!(peuplee.membres, 1);
}

/// Encaisser doit pouvoir se faire par le nom seul : la recherche globale
/// retrouve un membre sans connaître son clan, sa lignée ni sa famille, et
/// l'isole exactement quand on demande son identifiant.
#[test]
fn la_recherche_globale_trouve_un_membre_sans_navigation() {
    let (_dir, con) = base();

    let famille = con
        .query_row(
            "SELECT id FROM familles WHERE id IN (SELECT famille_id FROM membres)
              ORDER BY id LIMIT 1",
            [],
            |l| l.get::<_, i64>(0),
        )
        .unwrap();
    let reference = hierarchie::membres(&con, famille, None, None, None)
        .unwrap()
        .into_iter()
        .next()
        .expect("famille peuplée");

    let trouves =
        hierarchie::rechercher_membres(&con, None, Some(&reference.nom), None, None, 50).unwrap();
    let trouve = trouves
        .iter()
        .find(|t| t.membre.id == reference.id)
        .expect("le membre doit être retrouvé par son nom");
    assert!(
        trouve.chemin.split('›').count() >= 2,
        "le chemin doit situer le membre : {}",
        trouve.chemin
    );
    assert!(
        trouve.chemin.to_lowercase().contains("›"),
        "séparateur attendu : {}",
        trouve.chemin
    );
    assert_eq!(
        (trouve.membre.du, trouve.membre.paye),
        (reference.du, reference.paye),
        "la recherche ramène les mêmes soldes que la navigation"
    );

    // L'identifiant isole un seul membre (rafraîchissement après versement).
    let seul = hierarchie::membre(&con, reference.id, None, None)
        .unwrap()
        .expect("membre connu");
    assert_eq!(seul.id, reference.id);

    // Recherche insensible à la casse, limitée en nombre.
    let minuscules = hierarchie::rechercher_membres(
        &con,
        None,
        Some(&reference.nom.to_uppercase()),
        None,
        None,
        3,
    )
    .unwrap();
    assert!(minuscules.len() <= 3, "la limite est respectée");
    assert!(!minuscules.is_empty(), "la casse ne doit pas gêner");

    // Un nom absent ne ramène rien.
    assert!(
        hierarchie::rechercher_membres(&con, None, Some("ZZINTROUVABLE"), None, None, 25)
            .unwrap()
            .is_empty()
    );
}
