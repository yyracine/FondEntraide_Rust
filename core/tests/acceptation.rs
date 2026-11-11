//! Tests d'acceptation du §5.2 de `docs/historique/PLAN_MIGRATION_RUST.md`.
//!
//! Chaque test travaille sur une **copie** de `cotisations_v2.db` : la base
//! migrée n'est jamais modifiée. Si elle manque, lancer `python migrer_v2.py`.

use std::path::PathBuf;

use chrono::{Datelike, NaiveDate};
use fonds_core::{db, erreur::Erreur, membres, noeuds, sauvegardes, tarifs, ventilation};
use rusqlite::{params, Connection};

struct Base {
    _dir: tempfile::TempDir,
    chemin: PathBuf,
}

fn base() -> Base {
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
    Base { _dir: dir, chemin }
}

fn ouvrir(b: &Base) -> Connection {
    db::ouvrir(&b.chemin).expect("ouverture de la base migrée")
}

fn jour(a: i32, m: u32, j: u32) -> NaiveDate {
    NaiveDate::from_ymd_opt(a, m, j).expect("date valide")
}

fn premiere_famille(con: &Connection) -> i64 {
    con.query_row("SELECT id FROM familles ORDER BY id LIMIT 1", [], |l| {
        l.get(0)
    })
    .unwrap()
}

fn creer_membre(
    con: &Connection,
    famille_id: i64,
    nom: &str,
    entree: Option<&str>,
    sortie: Option<&str>,
) -> i64 {
    con.execute(
        "INSERT INTO membres (famille_id, nom, prenom, statut, date_entree, date_sortie)
         VALUES (?1, ?2, 'Test', 'actif', ?3, ?4)",
        params![famille_id, nom, entree, sortie],
    )
    .unwrap();
    con.last_insert_rowid()
}

/// Crée un exercice et matérialise ses échéances, mois par mois.
fn creer_exercice(
    con: &Connection,
    libelle: &str,
    debut: NaiveDate,
    fin: NaiveDate,
    montant: i64,
) -> rusqlite::Result<i64> {
    con.execute(
        "INSERT INTO exercices (libelle, date_debut, date_fin, montant_mensuel)
         VALUES (?1, ?2, ?3, ?4)",
        params![libelle, debut.to_string(), fin.to_string(), montant],
    )?;
    let id = con.last_insert_rowid();

    let (mut annee, mut mois) = (debut.year(), debut.month());
    while (annee, mois) <= (fin.year(), fin.month()) {
        let premier = NaiveDate::from_ymd_opt(annee, mois, 1).unwrap();
        let date = if premier < debut { debut } else { premier };
        con.execute(
            "INSERT INTO echeances (exercice_id, annee, mois, date_echeance, montant_du)
             VALUES (?1, ?2, ?3, ?4, ?5)",
            params![id, annee, mois, date.to_string(), montant],
        )?;
        mois += 1;
        if mois == 13 {
            mois = 1;
            annee += 1;
        }
    }
    Ok(id)
}

// ------------------------------------------------------------------
//  1. Les goldens de l'historique survivent-ils à la réécriture ?
// ------------------------------------------------------------------
#[test]
fn les_goldens_de_l_historique_sont_preserves() {
    let b = base();
    let con = ouvrir(&b);

    let compte = |table: &str| -> i64 {
        con.query_row(&format!("SELECT COUNT(*) FROM {table}"), [], |l| l.get(0))
            .unwrap()
    };
    assert_eq!(compte("clans"), 7);
    assert_eq!(compte("grandes_familles"), 46);
    assert_eq!(compte("lignees"), 46);
    assert_eq!(compte("familles"), 391);
    assert_eq!(compte("membres"), 599);
    assert_eq!(compte("paiements"), 227);
    assert_eq!(compte("affectations"), 1_805);

    let total: i64 = con
        .query_row("SELECT SUM(montant) FROM affectations", [], |l| l.get(0))
        .unwrap();
    assert_eq!(total, 1_807_000, "le total historique doit être intact");

    let incoherents: i64 = con
        .query_row("SELECT COUNT(*) FROM v_paiements_incoherents", [], |l| {
            l.get(0)
        })
        .unwrap();
    assert_eq!(incoherents, 0);
}

// ------------------------------------------------------------------
//  2. P01 : un exercice décalé crédite avril→novembre, et refuse
//     décembre→mars tant qu'ils ne sont pas échus.
// ------------------------------------------------------------------
#[test]
fn exercice_decale_credite_les_bons_mois() {
    let b = base();
    let mut con = ouvrir(&b);
    let famille = premiere_famille(&con);
    let exercice = creer_exercice(
        &con,
        "Exercice 2031-2032",
        jour(2031, 4, 1),
        jour(2032, 3, 31),
        1_000,
    )
    .expect("exercice créé");

    let membre = creer_membre(&con, famille, "ZZDECALE", Some("2030-12-01"), None);
    let paiement = ventilation::ventiler(
        &mut con,
        membre,
        exercice,
        8_000,
        jour(2031, 11, 10),
        "especes",
    )
    .expect("8 000 F = 8 mois échus");

    let mois: Vec<(i32, u32)> = paiement
        .affectations
        .iter()
        .map(|v| (v.annee, v.mois))
        .collect();
    assert_eq!(
        mois,
        vec![
            (2031, 4),
            (2031, 5),
            (2031, 6),
            (2031, 7),
            (2031, 8),
            (2031, 9),
            (2031, 10),
            (2031, 11)
        ],
        "les 8 premiers mois doivent être avril→novembre, pas janvier→août"
    );

    let autre = creer_membre(&con, famille, "ZZDECALE2", Some("2030-12-01"), None);
    match ventilation::ventiler(
        &mut con,
        autre,
        exercice,
        12_000,
        jour(2031, 11, 10),
        "especes",
    ) {
        Err(Erreur::Reliquat(total, reste)) => {
            assert_eq!((total, reste), (12_000, 4_000), "décembre→mars non échus");
        }
        autre_resultat => panic!("attendu Reliquat, obtenu {autre_resultat:?}"),
    }
}

// ------------------------------------------------------------------
//  3. Un mois civil ne peut pas appartenir à deux exercices.
// ------------------------------------------------------------------
#[test]
fn un_mois_ne_peut_appartenir_a_deux_exercices() {
    let b = base();
    let con = ouvrir(&b);
    // 2026 est déjà couvert par l'exercice civil migré.
    let resultat = creer_exercice(
        &con,
        "Chevauchement",
        jour(2026, 7, 1),
        jour(2027, 6, 30),
        1_000,
    );
    assert!(
        resultat.is_err(),
        "rattacher juillet 2026 à un second exercice doit être refusé"
    );
}

// ------------------------------------------------------------------
//  4. Mois partiel, puis solde.
// ------------------------------------------------------------------
#[test]
fn mois_partiel_puis_solde() {
    let b = base();
    let mut con = ouvrir(&b);
    let famille = premiere_famille(&con);
    let exercice = creer_exercice(
        &con,
        "Exercice 2030",
        jour(2030, 1, 1),
        jour(2030, 12, 31),
        1_000,
    )
    .expect("exercice créé");
    let membre = creer_membre(&con, famille, "ZZPARTIEL", Some("2030-01-01"), None);

    let premier = ventilation::ventiler(
        &mut con,
        membre,
        exercice,
        600,
        jour(2030, 11, 10),
        "especes",
    )
    .expect("600 F acceptés");
    assert_eq!(premier.affectations.len(), 1);
    assert_eq!(premier.affectations[0].montant, 600);

    let solde = ventilation::solde(&con, membre, exercice)
        .unwrap()
        .expect("membre assujetti");
    assert_eq!(
        (solde.paye, solde.reste, solde.mois_a_jour),
        (600, 11_400, 0)
    );

    let second = ventilation::ventiler(
        &mut con,
        membre,
        exercice,
        400,
        jour(2030, 11, 10),
        "especes",
    )
    .expect("le complément solde le mois");
    assert_eq!(second.affectations[0].montant, 400);

    let solde = ventilation::solde(&con, membre, exercice).unwrap().unwrap();
    assert_eq!(
        (solde.paye, solde.reste, solde.mois_a_jour),
        (1_000, 11_000, 1)
    );
}

// ------------------------------------------------------------------
//  5. D4 : numéros stables, jamais réattribués.
// ------------------------------------------------------------------
#[test]
fn numeros_de_recu_stables_et_jamais_reutilises() {
    let b = base();
    let mut con = ouvrir(&b);
    let famille = premiere_famille(&con);
    let exercice = creer_exercice(
        &con,
        "Exercice 2033",
        jour(2033, 1, 1),
        jour(2033, 12, 31),
        1_000,
    )
    .expect("exercice créé");
    let membre = creer_membre(&con, famille, "ZZRECU", Some("2033-01-01"), None);

    let premier = ventilation::ventiler(
        &mut con,
        membre,
        exercice,
        1_000,
        jour(2033, 11, 10),
        "especes",
    )
    .expect("paiement accepté");
    assert_eq!(premier.numero_recu, "RECU-2033-000001");

    // Deux impressions du même reçu portent le même numéro : il est en base.
    let relu: String = con
        .query_row(
            "SELECT numero_recu FROM paiements WHERE id = ?1",
            params![premier.id],
            |l| l.get(0),
        )
        .unwrap();
    assert_eq!(relu, premier.numero_recu);

    con.execute("DELETE FROM paiements WHERE id = ?1", params![premier.id])
        .expect("suppression du versement");

    let second = ventilation::ventiler(
        &mut con,
        membre,
        exercice,
        1_000,
        jour(2033, 11, 10),
        "especes",
    )
    .expect("nouveau paiement accepté");
    assert_eq!(
        second.numero_recu, "RECU-2033-000002",
        "le numéro du paiement supprimé ne doit pas être réutilisé"
    );
}

// ------------------------------------------------------------------
//  6. D9 : suppressions protégées.
// ------------------------------------------------------------------
#[test]
fn suppressions_protegees() {
    let b = base();
    let mut con = ouvrir(&b);
    let famille = premiere_famille(&con);
    let exercice = creer_exercice(
        &con,
        "Exercice 2034",
        jour(2034, 1, 1),
        jour(2034, 12, 31),
        1_000,
    )
    .expect("exercice créé");
    let membre = creer_membre(&con, famille, "ZZSUPPR", Some("2034-01-01"), None);

    ventilation::ventiler(
        &mut con,
        membre,
        exercice,
        1_000,
        jour(2034, 11, 10),
        "especes",
    )
    .expect("paiement accepté");

    assert!(
        con.execute("DELETE FROM membres WHERE id = ?1", params![membre])
            .is_err(),
        "un membre ayant des paiements ne peut pas être supprimé"
    );
    assert!(
        con.execute("DELETE FROM exercices WHERE id = ?1", params![exercice])
            .is_err(),
        "un exercice dont une échéance est réglée ne peut pas être supprimé"
    );
}

// ------------------------------------------------------------------
//  7. P05 : un parent hors de la famille est refusé, avec un message clair.
// ------------------------------------------------------------------
#[test]
fn parent_hors_de_la_famille_refuse() {
    let b = base();
    let con = ouvrir(&b);

    let mut stmt = con
        .prepare("SELECT id FROM familles ORDER BY id LIMIT 2")
        .unwrap();
    let familles: Vec<i64> = stmt
        .query_map([], |l| l.get(0))
        .unwrap()
        .map(|r| r.unwrap())
        .collect();
    drop(stmt);
    assert_eq!(familles.len(), 2);

    let pere = creer_membre(&con, familles[0], "ZZPERE", None, None);
    let enfant = creer_membre(&con, familles[1], "ZZENFANT", None, None);

    match con.execute(
        "UPDATE membres SET parent_id = ?1 WHERE id = ?2",
        params![pere, enfant],
    ) {
        Err(rusqlite::Error::SqliteFailure(_, Some(message))) => {
            assert!(
                message.contains("même famille"),
                "message inattendu : {message}"
            );
        }
        autre => panic!("un parent d'une autre famille doit être refusé : {autre:?}"),
    }
}

// ------------------------------------------------------------------
//  8. D7 : la date de sortie borne les échéances dues.
// ------------------------------------------------------------------
#[test]
fn date_de_sortie_borne_les_echeances_dues() {
    let b = base();
    let con = ouvrir(&b);
    let famille = premiere_famille(&con);
    let exercice = creer_exercice(
        &con,
        "Exercice 2035",
        jour(2035, 1, 1),
        jour(2035, 12, 31),
        1_000,
    )
    .expect("exercice créé");
    let membre = creer_membre(
        &con,
        famille,
        "ZZSORTI",
        Some("2035-01-01"),
        Some("2035-06-30"),
    );

    let solde = ventilation::solde(&con, membre, exercice)
        .unwrap()
        .expect("membre assujetti sur la période");
    assert_eq!(solde.mois_dus, 6, "janvier→juin seulement");
    assert_eq!(solde.du, 6_000);
}

// ------------------------------------------------------------------
//  9. L'autodiagnostic de démarrage ne signale que l'historique connu.
// ------------------------------------------------------------------
#[test]
fn autodiagnostic_ne_signale_que_les_depassements_historiques() {
    let b = base();
    let con = ouvrir(&b);
    let alertes = db::autodiagnostic(&con).expect("diagnostic");
    assert_eq!(alertes.len(), 1, "alertes inattendues : {alertes:?}");
    assert!(alertes[0].contains("au-delà du dû"), "{alertes:?}");
}

/// La répartition prévisionnelle annonce ce que le versement couvrirait, sans
/// écrire une seule ligne : c'est ce que la feuille affiche pendant la frappe.
#[test]
fn le_plan_annonce_les_mois_et_le_reliquat_sans_ecrire() {
    let b = base();
    let con = ouvrir(&b);
    let membre = creer_membre(
        &con,
        premiere_famille(&con),
        "Plan",
        Some("2027-01-01"),
        None,
    );
    // 2027 : les exercices 2024 à 2026 existent déjà dans la base, et leurs
    // bornes sont uniques.
    let exercice = creer_exercice(
        &con,
        "Plan 2027",
        jour(2027, 1, 1),
        jour(2027, 12, 31),
        1_000,
    )
    .expect("exercice de test");

    // Au 15 juillet 2027, sept mois sont échus : janvier → juillet.
    let date = jour(2027, 7, 15);
    let plan = ventilation::plan_ventilation(&con, membre, exercice, 5_500, date).unwrap();
    assert_eq!(
        plan.affectations.len(),
        6,
        "janvier à mai pleins, puis 500 F sur juin"
    );
    assert_eq!(plan.affectations[0].mois, 1);
    assert_eq!(plan.affectations[5].mois, 6);
    assert_eq!(plan.affectations[5].montant, 500);
    assert_eq!(plan.ventile, 5_500);
    assert_eq!(plan.reliquat, 0);

    // 9 000 F pour 7 000 F dus : 2 000 F resteraient sans imputation.
    let trop = ventilation::plan_ventilation(&con, membre, exercice, 9_000, date).unwrap();
    assert_eq!(trop.ventile, 7_000);
    assert_eq!(trop.reliquat, 2_000);

    // Rien n'a été écrit.
    let paiements: i64 = con
        .query_row(
            "SELECT COUNT(*) FROM paiements WHERE membre_id = ?1",
            params![membre],
            |l| l.get(0),
        )
        .unwrap();
    assert_eq!(paiements, 0, "le plan n'écrit aucun paiement");

    // Aucun mois échu : le cœur refuse de planifier.
    let rien = ventilation::plan_ventilation(&con, membre, exercice, 1_000, jour(2026, 12, 31));
    assert!(matches!(rien, Err(Erreur::AucuneEcheance)));
}

/// La fiche relit les versements d'un membre : du plus récent au plus ancien,
/// avec leur reçu et les mois qu'ils ont couverts, en une seule requête.
#[test]
fn l_historique_liste_les_versements_du_plus_recent_au_plus_ancien() {
    let b = base();
    let mut con = ouvrir(&b);
    let membre = creer_membre(
        &con,
        premiere_famille(&con),
        "Historique",
        Some("2027-01-01"),
        None,
    );
    let exercice = creer_exercice(
        &con,
        "Historique 2027",
        jour(2027, 1, 1),
        jour(2027, 12, 31),
        1_000,
    )
    .expect("exercice de test");

    let premier = ventilation::ventiler(
        &mut con,
        membre,
        exercice,
        2_000,
        jour(2027, 3, 10),
        "especes",
    )
    .expect("mars réglé");
    let second = ventilation::ventiler(
        &mut con,
        membre,
        exercice,
        1_000,
        jour(2027, 4, 10),
        "mobile_money",
    )
    .expect("avril réglé");

    let liste = ventilation::historique_paiements(&con, membre).unwrap();
    assert_eq!(liste.len(), 2, "un bloc par versement");
    assert_eq!(liste[0].id, second.id, "le plus récent en tête");
    assert_eq!(liste[1].id, premier.id);
    assert_eq!(liste[1].montant_total, 2_000);
    assert_eq!(liste[1].mode, "especes");
    assert_eq!(
        liste[1].affectations.len(),
        2,
        "les deux mois couverts sont listés"
    );
    assert_eq!(liste[1].affectations[0].mois, 1);
    assert_eq!(liste[1].affectations[1].mois, 2);
    assert!(
        liste[1].numero_recu.is_some(),
        "chaque versement a son reçu"
    );
    assert_ne!(
        liste[0].numero_recu, liste[1].numero_recu,
        "deux reçus, deux numéros"
    );

    // Un membre sans versement ne doit pas produire de bloc vide.
    let autre = creer_membre(
        &con,
        premiere_famille(&con),
        "SansVersement",
        Some("2027-01-01"),
        None,
    );
    assert!(ventilation::historique_paiements(&con, autre)
        .unwrap()
        .is_empty());
}

/// Annuler un versement libère ses mois, sans jamais rendre son numéro de
/// reçu : le compteur ne redescend pas (D9).
#[test]
fn un_versement_supprime_libere_ses_mois_sans_rendre_son_recu() {
    let b = base();
    let mut con = ouvrir(&b);
    let membre = creer_membre(
        &con,
        premiere_famille(&con),
        "Annulation",
        Some("2027-01-01"),
        None,
    );
    let exercice = creer_exercice(
        &con,
        "Annulation 2027",
        jour(2027, 1, 1),
        jour(2027, 12, 31),
        1_000,
    )
    .expect("exercice de test");

    let paiement = ventilation::ventiler(
        &mut con,
        membre,
        exercice,
        3_000,
        jour(2027, 4, 10),
        "especes",
    )
    .expect("janvier à mars réglés");
    let numero = paiement.numero_recu.clone();
    // Le solde porte sur tout l'exercice : 12 000 F dus, 3 000 F versés.
    let avant = ventilation::solde(&con, membre, exercice).unwrap().unwrap();
    assert_eq!((avant.paye, avant.reste), (3_000, 9_000));

    ventilation::supprimer_paiement(&mut con, paiement.id).expect("annulation");

    let affectations: i64 = con
        .query_row(
            "SELECT COUNT(*) FROM affectations WHERE paiement_id = ?1",
            params![paiement.id],
            |l| l.get(0),
        )
        .unwrap();
    assert_eq!(affectations, 0, "aucune affectation ne survit au versement");
    let apres = ventilation::solde(&con, membre, exercice).unwrap().unwrap();
    assert_eq!(
        (apres.paye, apres.reste),
        (0, 12_000),
        "l'annulation remet l'exercice entier à payer"
    );

    // Le versement suivant prend le numéro d'après, jamais celui du supprimé.
    let suivant = ventilation::ventiler(
        &mut con,
        membre,
        exercice,
        1_000,
        jour(2027, 4, 11),
        "especes",
    )
    .expect("nouveau versement");
    assert_ne!(
        suivant.numero_recu, numero,
        "un reçu supprimé ne revient pas"
    );
    assert_eq!(suivant.numero_recu, "RECU-2027-000002");

    // Un identifiant inconnu est refusé proprement, sans rien casser.
    assert!(matches!(
        ventilation::supprimer_paiement(&mut con, 999_999),
        Err(Erreur::PaiementInconnu(_))
    ));
}

/// La grille de la fiche : douze cases, avec soldé, partiel, échu et à venir.
#[test]
fn la_grille_des_douze_mois_distingue_paye_partiel_et_impaye() {
    let b = base();
    let mut con = ouvrir(&b);
    let exercice = creer_exercice(
        &con,
        "Grille 2027",
        jour(2027, 1, 1),
        jour(2027, 12, 31),
        1_000,
    )
    .expect("exercice de test");
    let membre = creer_membre(
        &con,
        premiere_famille(&con),
        "Grille",
        Some("2027-01-01"),
        None,
    );

    ventilation::ventiler(
        &mut con,
        membre,
        exercice,
        1_500,
        jour(2027, 3, 15),
        "especes",
    )
    .expect("janvier et février");

    let grille =
        ventilation::grille_membre(&con, membre, exercice, "2027-03-20").expect("grille du membre");
    assert_eq!(grille.len(), 12, "un exercice complet a douze cases");
    assert_eq!(
        (
            grille[0].mois,
            grille[0].du,
            grille[0].paye,
            grille[0].reste
        ),
        (1, 1_000, 1_000, 0),
        "janvier est soldé"
    );
    assert_eq!(
        (grille[1].paye, grille[1].reste),
        (500, 500),
        "février est partiel"
    );
    assert_eq!(
        (grille[2].paye, grille[2].reste, grille[2].echue),
        (0, 1_000, true),
        "mars est échu et impayé"
    );
    assert!(!grille[3].echue, "avril n'est pas encore échu au 20 mars");
    assert!(!grille[11].echue, "décembre est à venir");

    // Un membre entré en juillet garde douze cases, dont six hors période.
    let tardif = creer_membre(
        &con,
        premiere_famille(&con),
        "Tardif",
        Some("2027-07-01"),
        None,
    );
    let grille = ventilation::grille_membre(&con, tardif, exercice, "2027-03-20")
        .expect("grille du membre entré en juillet");
    assert_eq!(grille.len(), 12);
    assert!(!grille[0].assujetti, "janvier précède l'entrée");
    assert_eq!((grille[0].du, grille[0].reste), (0, 0));
    assert!(grille[6].assujetti, "juillet est dans la période");
}

// ------------------------------------------------------------------
//  9. Gestion des membres : création, modification, suppression.
// ------------------------------------------------------------------
fn fiche(famille: i64, nom: &str) -> membres::FicheMembre {
    membres::FicheMembre {
        id: None,
        famille_id: famille,
        parent_id: None,
        nom: nom.to_string(),
        prenom: Some("Essai".to_string()),
        telephone: Some("07 00 00 00 00".to_string()),
        sexe: Some("M".to_string()),
        ordre_fratrie: Some(2),
        statut: "actif".to_string(),
        date_entree: Some("2035-01-01".to_string()),
        date_sortie: None,
        notes: None,
    }
}

#[test]
fn un_membre_cree_puis_modifie_garde_ses_champs() {
    let b = base();
    let mut con = ouvrir(&b);
    let famille = premiere_famille(&con);

    let id = membres::enregistrer(&mut con, &fiche(famille, "ZZCRÉÉ")).expect("création");
    let relu = membres::edition(&con, id).expect("relecture");
    assert_eq!(relu.nom, "ZZCRÉÉ");
    assert_eq!(relu.prenom.as_deref(), Some("Essai"));
    assert_eq!(relu.telephone.as_deref(), Some("07 00 00 00 00"));
    assert_eq!(relu.ordre_fratrie, Some(2));

    let mut modifiee = relu.clone();
    modifiee.id = Some(id);
    modifiee.prenom = Some("Corrigé".to_string());
    modifiee.statut = "inactif".to_string();
    modifiee.telephone = None;
    membres::enregistrer(&mut con, &modifiee).expect("modification");

    let relu = membres::edition(&con, id).expect("relecture après modification");
    assert_eq!(relu.prenom.as_deref(), Some("Corrigé"));
    assert_eq!(relu.statut, "inactif");
    assert_eq!(relu.telephone, None, "un champ vidé le reste");

    // Le nom vide est refusé, comme une date hors format ISO.
    let mut sans_nom = fiche(famille, "   ");
    sans_nom.id = None;
    assert!(matches!(
        membres::enregistrer(&mut con, &sans_nom),
        Err(Erreur::ChampRequis(_))
    ));
    let mut date_fausse = fiche(famille, "ZZDATE");
    date_fausse.id = None;
    date_fausse.date_entree = Some("01/01/2035".to_string());
    assert!(matches!(
        membres::enregistrer(&mut con, &date_fausse),
        Err(Erreur::DateMalFormee(_))
    ));
}

#[test]
fn le_parent_est_borne_a_la_famille_et_sans_cycle() {
    let b = base();
    let mut con = ouvrir(&b);

    let mut stmt = con
        .prepare("SELECT id FROM familles ORDER BY id LIMIT 2")
        .unwrap();
    let familles: Vec<i64> = stmt
        .query_map([], |l| l.get(0))
        .unwrap()
        .map(|r| r.unwrap())
        .collect();
    drop(stmt);

    let pere = membres::enregistrer(&mut con, &fiche(familles[0], "ZZPÈRE")).expect("père");
    let mut fils = fiche(familles[0], "ZZFILS");
    fils.parent_id = Some(pere);
    let fils = membres::enregistrer(&mut con, &fils).expect("fils");

    // Un parent d'une autre famille est refusé avant d'atteindre SQLite.
    let mut etranger = fiche(familles[1], "ZZÉTRANGER");
    etranger.parent_id = Some(pere);
    assert!(matches!(
        membres::enregistrer(&mut con, &etranger),
        Err(Erreur::ParentHorsFamille)
    ));

    // Faire du fils le parent du père formerait une boucle.
    let mut boucle = membres::edition(&con, pere).unwrap();
    boucle.parent_id = Some(fils);
    assert!(matches!(
        membres::enregistrer(&mut con, &boucle),
        Err(Erreur::ParentInvalide(_))
    ));

    // Les candidats ne proposent jamais le membre lui-même.
    let candidats = membres::candidats_parent(&con, familles[0], Some(pere)).unwrap();
    assert!(candidats.iter().all(|c| c.id != pere));
    assert!(candidats.iter().any(|c| c.id == fils));
}

#[test]
fn la_suppression_protege_descendants_et_versements() {
    let b = base();
    let mut con = ouvrir(&b);
    let famille = premiere_famille(&con);

    let pere = membres::enregistrer(&mut con, &fiche(famille, "ZZSUPPÈRE")).expect("père");
    let mut enfant = fiche(famille, "ZZENFANT");
    enfant.parent_id = Some(pere);
    let enfant = membres::enregistrer(&mut con, &enfant).expect("enfant");

    match membres::supprimer(&mut con, pere) {
        Err(Erreur::SuppressionRefusee(message)) => assert!(message.contains("descendant")),
        autre => panic!("un membre avec descendant doit être protégé : {autre:?}"),
    }

    let exercice = creer_exercice(
        &con,
        "Suppression 2036",
        jour(2036, 1, 1),
        jour(2036, 12, 31),
        1_000,
    )
    .expect("exercice");
    let payeur = membres::enregistrer(&mut con, &fiche(famille, "ZZPAYEUR")).expect("payeur");
    ventilation::ventiler(
        &mut con,
        payeur,
        exercice,
        1_000,
        jour(2036, 2, 10),
        "especes",
    )
    .expect("versement");
    assert!(matches!(
        membres::supprimer(&mut con, payeur),
        Err(Erreur::SuppressionRefusee(_))
    ));

    // Sans descendant ni versement, la suppression passe.
    membres::supprimer(&mut con, enfant).expect("suppression de l'enfant");
    assert!(matches!(
        membres::edition(&con, enfant),
        Err(Erreur::MembreInconnu(_))
    ));
}

// ------------------------------------------------------------------
// 10. Hiérarchie : créer, renommer, supprimer sans casser la chaîne.
// ------------------------------------------------------------------
#[test]
fn la_hierarchie_se_cree_se_renomme_et_se_protege() {
    let b = base();
    let mut con = ouvrir(&b);

    let clan = noeuds::creer(&mut con, noeuds::Niveau::Clan, None, "ZZCLAN").expect("clan");
    let gf = noeuds::creer(&mut con, noeuds::Niveau::GrandeFamille, Some(clan), "ZZGF")
        .expect("grande famille");
    let lignee =
        noeuds::creer(&mut con, noeuds::Niveau::Lignee, Some(gf), "ZZLIGNEE").expect("lignée");
    let famille = noeuds::creer(&mut con, noeuds::Niveau::Famille, Some(lignee), "ZZFAMILLE")
        .expect("famille");

    // Doublon chez le même parent refusé (sans tenir compte de la casse),
    // et parent obligatoire pour un niveau qui en dépend.
    assert!(matches!(
        noeuds::creer(&mut con, noeuds::Niveau::Clan, None, "zzclan"),
        Err(Erreur::NomDejaPris(_))
    ));
    assert!(matches!(
        noeuds::creer(&mut con, noeuds::Niveau::Famille, None, "ZZORPHELINE"),
        Err(Erreur::ChampRequis(_))
    ));

    noeuds::renommer(&mut con, noeuds::Niveau::Clan, clan, "ZZCLAN2").expect("renommage");
    let nom: String = con
        .query_row("SELECT nom FROM clans WHERE id = ?1", params![clan], |l| {
            l.get(0)
        })
        .unwrap();
    assert_eq!(nom, "ZZCLAN2");

    // Une famille habitée ne se supprime pas, un clan peuplé non plus.
    let habitant = membres::enregistrer(&mut con, &fiche(famille, "ZZHABITANT"))
        .expect("membre dans la famille");
    assert!(matches!(
        noeuds::supprimer(&mut con, noeuds::Niveau::Famille, famille),
        Err(Erreur::SuppressionRefusee(_))
    ));
    assert!(matches!(
        noeuds::supprimer(&mut con, noeuds::Niveau::Clan, clan),
        Err(Erreur::SuppressionRefusee(_))
    ));

    // Vide, la chaîne se supprime du bas vers le haut.
    membres::supprimer(&mut con, habitant).expect("membre retiré");
    noeuds::supprimer(&mut con, noeuds::Niveau::Famille, famille).expect("famille");
    noeuds::supprimer(&mut con, noeuds::Niveau::Lignee, lignee).expect("lignée");
    noeuds::supprimer(&mut con, noeuds::Niveau::GrandeFamille, gf).expect("grande famille");
    noeuds::supprimer(&mut con, noeuds::Niveau::Clan, clan).expect("clan");
}

// ------------------------------------------------------------------
// 11. Tarif : changement en cours d'année, au mois choisi.
// ------------------------------------------------------------------
#[test]
fn un_tarif_change_en_cours_d_annee_ne_vaut_que_pour_les_mois_suivants() {
    let b = base();
    let mut con = ouvrir(&b);
    let famille = premiere_famille(&con);
    let membre = creer_membre(&con, famille, "ZZTARIF", Some("2037-01-01"), None);
    let exercice = creer_exercice(
        &con,
        "Tarif 2037",
        jour(2037, 1, 1),
        jour(2037, 12, 31),
        1_000,
    )
    .expect("exercice");

    // Janvier et février réglés à l'ancien tarif, le 15 mars.
    ventilation::ventiler(
        &mut con,
        membre,
        exercice,
        2_000,
        jour(2037, 3, 15),
        "especes",
    )
    .expect("janvier et février");

    let change = tarifs::changer(&mut con, exercice, 1_500, "2037-04-01").expect("changement");
    assert_eq!((change.annee_effet, change.mois_effet), (2037, 4));
    assert_eq!(change.modifies, 9, "avril à décembre");
    assert_eq!(change.conserves, 3, "janvier à mars gardent 1 000");

    let grille =
        ventilation::grille_membre(&con, membre, exercice, "2037-03-20").expect("grille du membre");
    assert_eq!(grille[0].du, 1_000, "janvier garde l'ancien tarif");
    assert_eq!(grille[2].du, 1_000, "mars, pourtant impayé, garde 1 000");
    assert_eq!(grille[3].du, 1_500, "avril prend le nouveau tarif");
    assert_eq!(grille[11].du, 1_500);

    let solde = ventilation::solde(&con, membre, exercice).unwrap().unwrap();
    assert_eq!(solde.du, 3_000 + 9 * 1_500);
    assert_eq!(solde.paye, 2_000);
    assert_eq!(solde.reste, 1_000 + 9 * 1_500);

    // Tout régler, puis changer encore : aucun mois réglé ne bouge.
    ventilation::ventiler(
        &mut con,
        membre,
        exercice,
        solde.reste,
        jour(2037, 12, 31),
        "especes",
    )
    .expect("solde complet");
    let apres =
        tarifs::changer(&mut con, exercice, 2_000, "2037-04-01").expect("second changement");
    assert_eq!(apres.modifies, 0, "aucun mois déjà réglé ne change");
    assert_eq!(apres.conserves, 12, "les douze mois restent à leur montant");
    let grille = ventilation::grille_membre(&con, membre, exercice, "2037-12-31")
        .expect("grille après second changement");
    assert!(grille.iter().all(|m| m.du <= 1_500));

    // Le mois d'effet doit appartenir à l'exercice, et le tarif être positif.
    assert!(matches!(
        tarifs::changer(&mut con, exercice, 1_000, "2038-01-01"),
        Err(Erreur::ChampIncoherent(_))
    ));
    assert!(matches!(
        tarifs::changer(&mut con, exercice, 0, "2037-06-01"),
        Err(Erreur::TarifInvalide)
    ));
}

// ------------------------------------------------------------------
//  13. Sauvegarde : la copie relue remet la base dans son état, et l'état
//      courant est sauvegardé avant d'être écrasé.
// ------------------------------------------------------------------
#[test]
fn sauvegarde_puis_restauration_revient_a_l_etat_de_la_copie() {
    let b = base();
    let mut con = ouvrir(&b);
    let famille = premiere_famille(&con);
    creer_membre(&con, famille, "ZZSAUVE", None, None);

    let copie = sauvegardes::sauvegarder(&con, &b.chemin).expect("sauvegarde");
    assert!(copie.nom.starts_with("cotisations_"));
    assert!(std::path::Path::new(&copie.chemin).is_file());
    assert!(copie.octets > 0);

    // Une écriture après la copie doit disparaître à la restauration.
    creer_membre(&con, famille, "ZZAPRES", None, None);
    let apres: i64 = con
        .query_row(
            "SELECT COUNT(*) FROM membres WHERE nom = 'ZZAPRES'",
            [],
            |l| l.get(0),
        )
        .unwrap();
    assert_eq!(apres, 1);

    let secours = sauvegardes::restaurer(&mut con, std::path::Path::new(&copie.chemin), &b.chemin)
        .expect("restauration");
    assert!(
        std::path::Path::new(&secours.chemin).is_file(),
        "l'état courant est sauvegardé avant d'être écrasé"
    );

    let garde: i64 = con
        .query_row(
            "SELECT COUNT(*) FROM membres WHERE nom = 'ZZSAUVE'",
            [],
            |l| l.get(0),
        )
        .unwrap();
    assert_eq!(garde, 1, "le membre d'avant la copie est revenu");
    let efface: i64 = con
        .query_row(
            "SELECT COUNT(*) FROM membres WHERE nom = 'ZZAPRES'",
            [],
            |l| l.get(0),
        )
        .unwrap();
    assert_eq!(efface, 0, "l'écriture d'après la copie a disparu");

    // La liste retrouve les deux copies, la plus récente d'abord.
    let liste = sauvegardes::lister(&b.chemin).expect("liste");
    assert!(liste.iter().any(|s| s.nom == copie.nom));
    assert!(liste.iter().any(|s| s.nom == secours.nom));
    assert!(
        liste.windows(2).all(|paire| paire[0].nom >= paire[1].nom),
        "la plus récente d'abord"
    );
}

// ------------------------------------------------------------------
//  14. D9 : une copie abîmée, un schéma v1 ou un nom hors du dossier sont
//      refusés avant toute écriture.
// ------------------------------------------------------------------
#[test]
fn une_copie_abimee_est_refusee_sans_toucher_a_la_base() {
    let b = base();
    let mut con = ouvrir(&b);
    let famille = premiere_famille(&con);
    creer_membre(&con, famille, "ZZINTACT", None, None);

    let dossier = sauvegardes::dossier(&b.chemin);
    std::fs::create_dir_all(&dossier).expect("dossier des sauvegardes");

    // Fichier qui n'est pas une base du tout.
    let illisible = dossier.join("cotisations_abimee.db");
    std::fs::write(&illisible, b"ceci n'est pas une base").expect("écriture du faux");

    // Base valide, mais d'ancien schéma (v1) : c'est le cas de la sauvegarde
    // Python `sauvegardes/cotisations_2026-11-10.db`.
    let ancienne = dossier.join("cotisations_v1.db");
    {
        let v1 = Connection::open(&ancienne).expect("base v1");
        v1.execute_batch("PRAGMA user_version = 1; CREATE TABLE marqueur (x INTEGER);")
            .expect("schéma v1");
    }

    for chemin in [&illisible, &ancienne] {
        match sauvegardes::restaurer(&mut con, chemin, &b.chemin) {
            Err(Erreur::RestaurationRefusee(_)) => {}
            autre => panic!(
                "copie refusée attendue pour {} : {autre:?}",
                chemin.display()
            ),
        }
    }

    let membres: i64 = con
        .query_row("SELECT COUNT(*) FROM membres", [], |l| l.get(0))
        .unwrap();
    assert!(membres > 0, "la base vivante est intacte");

    // Le nom vient de l'interface : aucune traversée de chemin acceptée.
    for nom in [
        "../cotisations.db",
        "..\\cotisations.db",
        "absente.db",
        "x.txt",
    ] {
        assert!(
            matches!(
                sauvegardes::chemin_de(&b.chemin, nom),
                Err(Erreur::RestaurationRefusee(_))
            ),
            "nom refusé attendu : {nom}"
        );
    }
}

// ------------------------------------------------------------------
//  15. Le dossier ne grossit pas sans fin : seules les cinq copies les plus
//      récentes restent, et rien d'autre n'est effacé.
// ------------------------------------------------------------------
#[test]
fn les_copies_au_dela_de_cinq_sont_effacees() {
    let b = base();
    let con = ouvrir(&b);

    // Une copie déposée par un autre outil ne doit jamais être touchée.
    let dossier = sauvegardes::dossier(&b.chemin);
    std::fs::create_dir_all(&dossier).expect("dossier");
    let etranger = dossier.join("avant_correction_noms_20261109_134410.db");
    std::fs::write(&etranger, b"pas une base, mais pas a nous").expect("dépôt");

    let mut creees = Vec::new();
    for _ in 0..7 {
        // Un écart réel entre les fichiers : le tri se fait sur la date.
        std::thread::sleep(std::time::Duration::from_millis(5));
        creees.push(sauvegardes::sauvegarder(&con, &b.chemin).unwrap().nom);
    }

    let effacees = sauvegardes::purger(&b.chemin).expect("purge");
    assert_eq!(effacees, 2, "les deux copies au-delà des cinq");
    assert!(etranger.is_file(), "le fichier étranger est intact");

    let restantes: Vec<String> = sauvegardes::lister(&b.chemin)
        .unwrap()
        .into_iter()
        .map(|s| s.nom)
        .collect();
    assert_eq!(restantes.len(), 5, "l'écran ne voit que les cinq copies");
    for vieille in &creees[..2] {
        assert!(
            !restantes.contains(vieille),
            "la plus ancienne est partie : {vieille}"
        );
    }
    for recente in &creees[2..] {
        assert!(
            restantes.contains(recente),
            "les cinq dernières restent : {recente}"
        );
    }
}
