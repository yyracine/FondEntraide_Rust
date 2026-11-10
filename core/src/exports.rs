//! Export CSV des listes affichées (décision D10).
//!
//! Le CSV est construit à partir des lignes **déjà affichées** dans
//! l'interface : le fichier ne peut pas diverger de l'écran. Deux détails
//! comptent pour Excel et LibreOffice en français :
//! - séparateur point-virgule, sinon tout atterrit dans une seule colonne ;
//! - BOM UTF-8 en tête et fins de ligne CRLF, sinon les accents sont abîmés.
//!
//! Les montants partent en entiers nus, sans séparateur de milliers : un
//! « 1 807 000 » serait lu comme du texte et ne s'additionnerait pas.
//!
//! Un champ qui commence par `=`, `+`, `@`, une tabulation ou un retour
//! chariot est préfixé d'une apostrophe : Excel et LibreOffice le liraient
//! sinon comme une formule (injection de formule). `-` n'est neutralisé que
//! s'il n'ouvre pas un nombre, pour que `-3000` reste un montant.

use std::fs;
use std::path::{Path, PathBuf};

use crate::erreur::Erreur;

/// Fichier écrit, tel que l'interface le confirme.
#[derive(Debug, Clone, PartialEq, Eq, serde::Serialize)]
pub struct Export {
    pub chemin: String,
    pub lignes: usize,
}

/// Dossier des exports : à côté de la base, comme les sauvegardes.
pub fn dossier(base: &Path) -> PathBuf {
    base.parent()
        .unwrap_or_else(|| Path::new("."))
        .join("exports")
}

/// Contenu complet du fichier : en-tête puis lignes, BOM et CRLF compris.
pub fn csv(colonnes: &[String], lignes: &[Vec<String>]) -> String {
    let mut sortie = String::from("\u{feff}");
    sortie.push_str(&ligne_csv(colonnes));
    for ligne in lignes {
        sortie.push_str(&ligne_csv(ligne));
    }
    sortie
}

fn ligne_csv(champs: &[String]) -> String {
    let mut ligne = String::new();
    for (index, champ) in champs.iter().enumerate() {
        if index > 0 {
            ligne.push(';');
        }
        ligne.push_str(&champ_csv(champ));
    }
    ligne.push_str("\r\n");
    ligne
}

/// Vrai si un tableur interpréterait le champ comme une formule.
fn commence_par_formule(champ: &str) -> bool {
    let mut caracteres = champ.chars();
    match caracteres.next() {
        Some('=') | Some('+') | Some('@') | Some('\t') | Some('\r') => true,
        Some('-') => !caracteres.all(|c| c.is_ascii_digit() || c == '.' || c == ','),
        _ => false,
    }
}

/// Un champ n'est mis entre guillemets que s'il le faut, et ses guillemets
/// sont doublés — la règle CSV ordinaire. Les formules sont neutralisées par
/// une apostrophe en tête, marqueur de texte ignoré à l'affichage par Excel
/// comme par LibreOffice.
fn champ_csv(champ: &str) -> String {
    let valeur = if commence_par_formule(champ) {
        format!("'{champ}")
    } else {
        champ.to_string()
    };
    let a_proteger = valeur.contains(';')
        || valeur.contains('"')
        || valeur.contains('\n')
        || valeur.contains('\r');
    if a_proteger {
        format!("\"{}\"", valeur.replace('"', "\"\""))
    } else {
        valeur
    }
}

/// Écrit le fichier `exports/<nom>_<instant>.csv` et renvoie son chemin.
///
/// `nom` vient de l'interface : il est limité à des caractères sûrs, ce qui
/// interdit toute traversée de chemin. Deux exports dans la même seconde
/// reçoivent un suffixe `_2`, `_3`… : rien ne s'écrase.
pub fn ecrire(
    base: &Path,
    nom: &str,
    colonnes: &[String],
    lignes: &[Vec<String>],
    instant: &str,
) -> Result<Export, Erreur> {
    let nom_valide = !nom.is_empty()
        && nom
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-');
    if !nom_valide {
        return Err(Erreur::ExportEchoue(format!(
            "nom de fichier invalide : {nom}"
        )));
    }

    let dossier = dossier(base);
    fs::create_dir_all(&dossier)
        .map_err(|e| Erreur::ExportEchoue(format!("dossier impossible : {e}")))?;

    let mut cible = dossier.join(format!("{nom}_{instant}.csv"));
    let mut suffixe = 2;
    while cible.exists() {
        cible = dossier.join(format!("{nom}_{instant}_{suffixe}.csv"));
        suffixe += 1;
    }

    fs::write(&cible, csv(colonnes, lignes))
        .map_err(|e| Erreur::ExportEchoue(format!("écriture impossible : {e}")))?;

    Ok(Export {
        chemin: cible.to_string_lossy().to_string(),
        lignes: lignes.len(),
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn texte(valeur: &str) -> String {
        valeur.to_string()
    }

    #[test]
    fn un_champ_avec_separateur_ou_guillemet_est_protege() {
        let contenu = csv(
            &[texte("Nom"), texte("Note")],
            &[vec![texte("A;B"), texte("dit \"oui\"")]],
        );
        assert!(contenu.starts_with('\u{feff}'), "le BOM ouvre le fichier");
        assert_eq!(
            contenu, "\u{feff}Nom;Note\r\n\"A;B\";\"dit \"\"oui\"\"\"\r\n",
            "point-virgule protégé, guillemets doublés, CRLF"
        );
    }

    #[test]
    fn un_retour_a_la_ligne_dans_un_nom_ne_casse_pas_la_ligne() {
        let contenu = csv(&[texte("Nom")], &[vec![texte("ligne 1\nligne 2")]]);
        assert_eq!(contenu, "\u{feff}Nom\r\n\"ligne 1\nligne 2\"\r\n");
    }

    #[test]
    fn le_fichier_est_ecrit_dans_exports_avec_la_date_dans_le_nom() {
        let racine = std::env::temp_dir().join("fonds-export-test");
        let _ = fs::remove_dir_all(&racine);
        let base = racine.join("cotisations_v2.db");

        let export = ecrire(
            &base,
            "membres",
            &[texte("Nom"), texte("Payé")],
            &[vec![texte("Akesse"), texte("3000")]],
            "2026-11-10_17-30-00",
        )
        .expect("export");

        assert_eq!(export.lignes, 1);
        assert!(export.chemin.ends_with("membres_2026-11-10_17-30-00.csv"));
        let contenu = fs::read_to_string(&export.chemin).expect("lecture");
        assert!(contenu.contains("Akesse;3000"));

        let _ = fs::remove_dir_all(&racine);
    }

    #[test]
    fn une_formule_est_neutralisee_mais_un_montant_negatif_reste_numerique() {
        let contenu = csv(
            &[texte("Nom"), texte("Note")],
            &[
                vec![
                    texte("=HYPERLINK(\"http://exemple\")"),
                    texte("+221 77 000 00 00"),
                ],
                vec![texte("@SUM(A1)"), texte("-3000")],
                vec![texte("-1+2"), texte("déjà du texte")],
            ],
        );
        assert!(
            contenu.contains("'=HYPERLINK"),
            "une formule = est précédée d'une apostrophe : {contenu}"
        );
        assert!(contenu.contains(";'+221 77 000 00 00"), "+ neutralisé");
        assert!(contenu.contains("'@SUM(A1)"), "@ neutralisé");
        assert!(
            contenu.contains(";-3000\r\n"),
            "un montant négatif reste un nombre : {contenu}"
        );
        assert!(
            contenu.contains("'-1+2"),
            "- suivi d'une expression neutralisé"
        );
    }

    #[test]
    fn un_nom_qui_sort_du_dossier_est_refuse() {
        let base = Path::new("cotisations_v2.db");
        for nom in ["../evil", "a/b", "a\\b", "nom avec espace"] {
            assert!(
                matches!(
                    ecrire(base, nom, &[], &[], "2026-11-10_17-30-00"),
                    Err(Erreur::ExportEchoue(_))
                ),
                "nom refusé attendu : {nom}"
            );
        }
    }
}
