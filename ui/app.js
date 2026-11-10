const { invoke } = window.__TAURI__.core;

const etat = {
  clan: null,
  grandeFamille: null,
  lignee: null,
  famille: null,
  exercices: [],
  exercice: null,
  // Vue complète : le tableau affiche toute la base au lieu d'une famille.
  vueComplete: false,
  // Vrai quand cette fenêtre tourne sur la base de démonstration.
  demo: false,
  // Listes affichées : elles servent à l'export CSV, qui doit reproduire
  // exactement l'écran, filtre compris.
  clans: [],
  grandesFamilles: [],
  lignees: [],
  familles: [],
};

const MOIS = [
  "janvier",
  "février",
  "mars",
  "avril",
  "mai",
  "juin",
  "juillet",
  "août",
  "septembre",
  "octobre",
  "novembre",
  "décembre",
];

const MODES = {
  especes: "espèces",
  mobile_money: "mobile money",
  virement: "virement",
  cheque: "chèque",
  autre: "autre",
};

const nf = new Intl.NumberFormat("fr-FR");
const $ = (id) => document.getElementById(id);
const fcf = (montant) => `${nf.format(montant)} F`;
const pluriel = (n, mot) => `${nf.format(n)} ${mot}${n > 1 ? "s" : ""}`;

let ligneSelectionnee = null;
let membreCourant = null;
// Un versement vient d'être enregistré dans cette feuille : le bouton reste
// désarmé tant que l'utilisateur n'a pas saisi un nouveau montant.
let enregistre = false;
// Exercice choisi dans la feuille, indépendant des puces du tableau.
let exerciceFeuille = null;

/* ------------------------------- erreurs ------------------------------- */
let minuterieInfo = null;

function afficherErreur(texte) {
  const bandeau = $("bandeau");
  bandeau.textContent = String(texte);
  bandeau.hidden = false;
  bandeau.classList.remove("succes");
  clearTimeout(minuterieInfo);
}

/** Confirmation discrète : le bandeau se referme tout seul. */
function afficherInfo(texte) {
  const bandeau = $("bandeau");
  bandeau.textContent = String(texte);
  bandeau.hidden = false;
  bandeau.classList.add("succes");
  clearTimeout(minuterieInfo);
  minuterieInfo = setTimeout(() => {
    bandeau.hidden = true;
    bandeau.classList.remove("succes");
  }, 8000);
}

function effacerErreur() {
  const bandeau = $("bandeau");
  bandeau.hidden = true;
  bandeau.classList.remove("succes");
  clearTimeout(minuterieInfo);
}

/* ------------------------------- outils -------------------------------- */
function vide(conteneur, texte) {
  conteneur.replaceChildren();
  const p = document.createElement("p");
  p.className = "vide";
  p.textContent = texte;
  conteneur.append(p);
}

function ligne(nom, detail, action, id) {
  const bouton = document.createElement("button");
  bouton.type = "button";
  bouton.className = "ligne";
  // L'identifiant permet de retrouver la ligne après un rechargement.
  if (id !== undefined && id !== null) bouton.dataset.id = String(id);
  const titre = document.createElement("span");
  titre.className = "ligne-nom";
  titre.textContent = nom;
  bouton.append(titre);
  if (detail) {
    const petit = document.createElement("span");
    petit.className = "ligne-detail";
    petit.textContent = detail;
    bouton.append(petit);
  }
  bouton.addEventListener("click", () => action(bouton));
  return bouton;
}

function puce(texte, actif, action) {
  const bouton = document.createElement("button");
  bouton.type = "button";
  bouton.className = actif ? "puce actif" : "puce";
  bouton.textContent = texte;
  bouton.addEventListener("click", () => action());
  return bouton;
}

function remplir(idListe, elements, texteVide) {
  const conteneur = $(idListe);
  conteneur.replaceChildren();
  if (elements.length === 0) {
    vide(conteneur, texteVide);
    return;
  }
  for (const element of elements) conteneur.append(element);
}

function marquerActif(bouton) {
  const parent = bouton.parentElement;
  for (const autre of parent.querySelectorAll(".ligne.actif")) {
    autre.classList.remove("actif");
  }
  bouton.classList.add("actif");
}

/** Descend automatiquement les niveaux qui n'ont qu'un seul enfant. */
function unique(idListe) {
  const elements = $(idListe).querySelectorAll(".ligne");
  return elements.length === 1 ? elements[0] : null;
}

/**
 * Fil d'Ariane étiqueté par niveau. Deux niveaux consécutifs qui portent le
 * même nom sont fusionnés (« GF/Lignée · YAOCRE APPIA »).
 */
function fil() {
  const niveaux = [
    { etiquette: "Clan", valeur: etat.clan },
    { etiquette: "GF", valeur: etat.grandeFamille },
    { etiquette: "Lignée", valeur: etat.lignee },
    { etiquette: "Famille", valeur: etat.famille },
  ].filter((niveau) => niveau.valeur);

  const morceaux = [];
  for (const niveau of niveaux) {
    const dernier = morceaux[morceaux.length - 1];
    if (dernier && dernier.nom === niveau.valeur.nom) {
      dernier.etiquettes.push(niveau.etiquette);
    } else {
      morceaux.push({ nom: niveau.valeur.nom, etiquettes: [niveau.etiquette] });
    }
  }
  return morceaux.map((m) => `${m.etiquettes.join("/")} · ${m.nom}`).join("   ›   ");
}

/* ---------------------------- vue complète ----------------------------- */
function majLibelleVue() {
  // Le bouton reste toujours visible : la vue complète se quitte en cliquant
  // un clan ou une famille dans les colonnes.
  $("voir-tous").hidden = false;
  $("th-parent").textContent = etat.vueComplete ? "Chemin" : "Parent";
}

function quitterVueComplete() {
  if (!etat.vueComplete) return;
  etat.vueComplete = false;
  majLibelleVue();
}

/** « Akesse » se cherche aussi « akéssé » : on ignore casse et accents. */
function sansAccents(texte) {
  return String(texte ?? "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
}

function filtrerMembres(membres, recherche) {
  const terme = sansAccents(recherche);
  if (!terme) return membres;
  return membres.filter((m) =>
    sansAccents(`${m.nom} ${m.prenom ?? ""}`).includes(terme),
  );
}

async function basculerVueComplete() {
  etat.vueComplete = true;
  majLibelleVue();
  await chargerMembres();
  $("fil").textContent = "Toute la base";
  $("titre-membres").textContent = "Tous les membres";
}

function statut(texte) {
  const badge = document.createElement("span");
  const actif = texte === "actif";
  badge.className = actif ? "badge" : "badge inactif";
  badge.textContent = texte;
  return badge;
}

function cellule(texte, classe) {
  const td = document.createElement("td");
  td.textContent = texte ?? "—";
  if (classe) td.className = classe;
  return td;
}

function celluleBadge(texte) {
  const td = document.createElement("td");
  td.append(statut(texte));
  return td;
}

/* ------------------------------ compteurs ------------------------------ */
function compteur(valeur, libelle) {
  const boite = document.createElement("div");
  boite.className = "compteur";
  const v = document.createElement("span");
  v.className = "compteur-valeur";
  v.textContent = valeur;
  const l = document.createElement("span");
  l.className = "compteur-libelle";
  l.textContent = libelle;
  boite.append(v, l);
  return boite;
}

async function chargerResume() {
  const r = await invoke("resume");
  $("compteurs").replaceChildren(
    compteur(nf.format(r.clans), "clans"),
    compteur(nf.format(r.familles), "familles"),
    compteur(nf.format(r.membres), "membres"),
    compteur(fcf(r.encaisse), "encaissé total"),
  );
}

/* ------------------------------ exercices ------------------------------ */
/** « 2026 » pour une année civile, sinon le libellé complet. */
function nomExercice(exercice) {
  if (!exercice) return "tous exercices";
  const civile =
    exercice.date_debut.endsWith("-01-01") && exercice.date_fin.endsWith("-12-31");
  return civile ? String(exercice.annee) : exercice.libelle;
}

function dessinerAnnees() {
  const puces = [puce("Tous", etat.exercice === null, () => choisirExercice(null))];
  for (const exercice of etat.exercices) {
    puces.push(
      puce(nomExercice(exercice), etat.exercice?.id === exercice.id, () =>
        choisirExercice(exercice),
      ),
    );
  }
  $("annees").replaceChildren(...puces);
}

function majEntetes() {
  const suffixe = etat.exercice ? ` ${nomExercice(etat.exercice)}` : "";
  $("th-paye").textContent = `Payé${suffixe}`;
  $("th-reste").textContent = `Reste${suffixe}`;
  $("th-arrieres").textContent = `Arriérés${suffixe}`;
}

async function choisirExercice(exercice) {
  etat.exercice = exercice;
  dessinerAnnees();
  majEntetes();
  // En vue complète, il n'y a pas de famille : changer d'exercice doit
  // recharger la liste entière, pas la vider.
  if (etat.famille || etat.vueComplete) await chargerMembres();
  else afficherMembres([]);
}

async function chargerExercices() {
  etat.exercices = await invoke("exercices");
  etat.exercice = etat.exercices.find((e) => e.courant) ?? null;
  dessinerAnnees();
  majEntetes();
}

/* --------------------------- tarif de l'exercice ----------------------- */
function moisLisible(annee, mois) {
  return `${MOIS[mois - 1]} ${annee}`;
}

/**
 * Mois d'effet proposé : le suivant, borné à la période de l'exercice. Un
 * changement décidé en mars prend effet en avril, jamais sur le mois en cours.
 */
function moisSuivantDans(exercice) {
  const d = new Date();
  let annee = d.getFullYear();
  let mois = d.getMonth() + 2;
  if (mois > 12) {
    mois = 1;
    annee += 1;
  }
  let cle = `${annee}-${String(mois).padStart(2, "0")}`;
  const debut = exercice?.date_debut?.slice(0, 7);
  const fin = exercice?.date_fin?.slice(0, 7);
  if (debut && cle < debut) cle = debut;
  if (fin && cle > fin) cle = fin;
  return cle;
}

/** Réarme le bouton dès qu'une valeur change (nouveau tarif ou nouveau mois). */
function armerTarif() {
  $("appliquer-tarif").disabled = false;
  $("appliquer-tarif").textContent = "Appliquer le tarif";
}

function ouvrirTarif() {
  armerTarif();
  const exercice = exercicePourPaiement();
  if (!exercice) {
    afficherErreur("Aucun exercice disponible pour changer le tarif.");
    return;
  }
  effacerErreur();
  $("tarif-titre").textContent = `Tarif de ${nomExercice(exercice)}`;
  $("annuler-tarif").textContent = "Fermer";
  $("tarif-actuel").textContent =
    `Tarif en vigueur : ${fcf(exercice.montant_mensuel ?? 0)} par mois`;
  $("tarif-montant").value = String(exercice.montant_mensuel ?? "");
  $("tarif-mois").value = moisSuivantDans(exercice);
  $("tarif-note").textContent =
    "Les mois antérieurs gardent leur montant, même impayés ; les mois déjà réglés ne changent pas. « Fermer » n'annule pas un tarif déjà appliqué.";
  $("voile-tarif").hidden = false;
  $("tarif-montant").focus?.();
}

async function rafraichirApresTarif() {
  await chargerMembres();
  await chargerResume();
  if (membreFiche) await rafraichirSoldesFiche();
  if (membreCourant) {
    const exercice = exerciceDuPaiement();
    const aJour = await invoke("membre", {
      membreId: membreCourant.id,
      exerciceId: exercice ? exercice.id : null,
    });
    if (aJour) {
      membreCourant = { ...membreCourant, ...aJour };
      majSoldes(membreCourant);
    }
  }
}

async function appliquerTarif() {
  const exercice = exercicePourPaiement();
  if (!exercice) return;

  const montant = Number($("tarif-montant").value);
  const mois = $("tarif-mois").value;
  if (!Number.isInteger(montant) || montant <= 0) {
    $("tarif-note").textContent = "Le tarif doit être un entier supérieur à zéro.";
    return;
  }
  if (!/^\d{4}-\d{2}$/.test(mois)) {
    $("tarif-note").textContent = "Choisissez le mois d'effet.";
    return;
  }

  const bouton = $("appliquer-tarif");
  bouton.disabled = true;
  try {
    const resultat = await invoke("changer_tarif", {
      exerciceId: exercice.id,
      montant,
      dateEffet: `${mois}-01`,
    });

    // Le tarif en vigueur suit, sans recharger les puces (cela remettrait
    // l'exercice courant à la place de celui que l'utilisateur a choisi).
    for (const e of etat.exercices) {
      if (e.id === exercice.id) e.montant_mensuel = resultat.montant;
    }
    if (etat.exercice && etat.exercice.id === exercice.id) {
      etat.exercice.montant_mensuel = resultat.montant;
    }

    $("tarif-actuel").textContent =
      `Tarif en vigueur : ${fcf(resultat.montant)} par mois`;
    $("tarif-note").textContent =
      `À partir de ${moisLisible(resultat.annee_effet, resultat.mois_effet)} : ` +
      `${pluriel(resultat.modifies, "mois")} à ${fcf(resultat.montant)}` +
      (resultat.conserves > 0
        ? ` · ${pluriel(resultat.conserves, "mois")} conservé${resultat.conserves > 1 ? "s" : ""}`
        : "") +
      ". Enregistré : fermer cet écran ne défait pas ce changement.";

    // Le tarif est écrit : le bouton reste désarmé tant que rien ne change,
    // sinon on croit pouvoir annuler une modification déjà enregistrée.
    bouton.disabled = true;
    bouton.textContent = "Tarif appliqué";
    effacerErreur();
    await rafraichirApresTarif();
  } catch (erreur) {
    bouton.disabled = false;
    $("tarif-note").textContent = String(erreur);
  }
}

$("changer-tarif").addEventListener("click", () => ouvrirTarif());
$("tarif-montant").addEventListener("input", armerTarif);
$("tarif-mois").addEventListener("input", armerTarif);
$("fermer-tarif").addEventListener("click", () => {
  $("voile-tarif").hidden = true;
});
$("annuler-tarif").addEventListener("click", () => {
  $("voile-tarif").hidden = true;
});
$("appliquer-tarif").addEventListener("click", () => {
  appliquerTarif().catch((e) => afficherErreur(e));
});

/* ------------------------------ navigation ----------------------------- */
function reinitialiserApres(niveau) {
  if (niveau === "clan") {
    etat.grandeFamille = null;
    etat.lignee = null;
    etat.famille = null;
    vide($("liste-gf"), "Sélectionnez un clan");
    vide($("liste-lignees"), "Sélectionnez une grande famille");
    vide($("liste-familles"), "Sélectionnez une lignée");
  }
  if (niveau === "grandeFamille") {
    etat.lignee = null;
    etat.famille = null;
    vide($("liste-lignees"), "Sélectionnez une grande famille");
    vide($("liste-familles"), "Sélectionnez une lignée");
  }
  if (niveau === "lignee") {
    etat.famille = null;
    vide($("liste-familles"), "Sélectionnez une lignée");
  }
  quitterVueComplete();
  $("recherche").value = "";
  afficherMembres([]);
  $("fil").textContent = fil();
  $("titre-membres").textContent = etat.famille ? etat.famille.nom : "Membres";
}

async function choisirClan(bouton, clan) {
  marquerActif(bouton);
  etat.clan = clan;
  reinitialiserApres("clan");

  const familles = await invoke("grandes_familles", { clanId: clan.id });
  etat.grandesFamilles = familles;
  remplir(
    "liste-gf",
    familles.map((gf) => ligne(gf.nom, "", (b) => choisirGrandeFamille(b, gf), gf.id)),
    "Aucune grande famille",
  );

  const seul = unique("liste-gf");
  if (seul) await choisirGrandeFamille(seul, familles[0]);
}

async function choisirGrandeFamille(bouton, gf) {
  marquerActif(bouton);
  etat.grandeFamille = gf;
  reinitialiserApres("grandeFamille");

  const lignees = await invoke("lignees", { grandeFamilleId: gf.id });
  etat.lignees = lignees;
  remplir(
    "liste-lignees",
    lignees.map((l) => ligne(l.nom, "", (b) => choisirLignee(b, l), l.id)),
    "Aucune lignée",
  );

  const seule = unique("liste-lignees");
  if (seule) await choisirLignee(seule, lignees[0]);
}

async function choisirLignee(bouton, lignee) {
  marquerActif(bouton);
  etat.lignee = lignee;
  reinitialiserApres("lignee");

  const familles = await invoke("familles", { ligneeId: lignee.id });
  etat.familles = familles;

  // Deux familles homonymes dans la même lignée : on les distingue par leur
  // identifiant et leur effectif.
  const occurrences = new Map();
  for (const f of familles) {
    occurrences.set(f.nom, (occurrences.get(f.nom) ?? 0) + 1);
  }

  remplir(
    "liste-familles",
    familles.map((f) => {
      const detail = pluriel(f.membres, "membre");
      const suffixe = occurrences.get(f.nom) > 1 ? ` · #${f.id}` : "";
      return ligne(f.nom, detail + suffixe, (b) => choisirFamille(b, f), f.id);
    }),
    "Aucune famille",
  );

  const seule = unique("liste-familles");
  if (seule) await choisirFamille(seule, familles[0]);
}

async function choisirFamille(bouton, famille) {
  marquerActif(bouton);
  etat.famille = famille;
  reinitialiserApres("famille");
  await chargerMembres();
}

/* --------------------- écrire la hiérarchie ---------------------------- */
const NOEUDS = {
  clan: {
    libelle: "clan",
    courant: () => etat.clan,
    parent: () => null,
    parentLibelle: null,
  },
  grande_famille: {
    libelle: "grande famille",
    courant: () => etat.grandeFamille,
    parent: () => etat.clan,
    parentLibelle: "un clan",
  },
  lignee: {
    libelle: "lignée",
    courant: () => etat.lignee,
    parent: () => etat.grandeFamille,
    parentLibelle: "une grande famille",
  },
  famille: {
    libelle: "famille",
    courant: () => etat.famille,
    parent: () => etat.lignee,
    parentLibelle: "une lignée",
  },
};

async function chargerClans() {
  const clans = await invoke("clans");
  etat.clans = clans;
  remplir(
    "liste-clans",
    clans.map((c) => ligne(c.nom, c.description ?? "", (b) => choisirClan(b, c), c.id)),
    "Aucun clan",
  );
  return clans;
}

async function chargerGrandesFamilles(clanId) {
  const liste = await invoke("grandes_familles", { clanId });
  etat.grandesFamilles = liste;
  remplir(
    "liste-gf",
    liste.map((gf) => ligne(gf.nom, "", (b) => choisirGrandeFamille(b, gf), gf.id)),
    "Aucune grande famille",
  );
  return liste;
}

async function chargerLignees(grandeFamilleId) {
  const liste = await invoke("lignees", { grandeFamilleId });
  etat.lignees = liste;
  remplir(
    "liste-lignees",
    liste.map((l) => ligne(l.nom, "", (b) => choisirLignee(b, l), l.id)),
    "Aucune lignée",
  );
  return liste;
}

async function chargerFamilles(ligneeId) {
  const liste = await invoke("familles", { ligneeId });
  etat.familles = liste;
  const occurrences = new Map();
  for (const f of liste) {
    occurrences.set(f.nom, (occurrences.get(f.nom) ?? 0) + 1);
  }
  remplir(
    "liste-familles",
    liste.map((f) => {
      const suffixe = occurrences.get(f.nom) > 1 ? ` · #${f.id}` : "";
      return ligne(
        f.nom,
        pluriel(f.membres, "membre") + suffixe,
        (b) => choisirFamille(b, f),
        f.id,
      );
    }),
    "Aucune famille",
  );
  return liste;
}

function marquerParId(idListe, id) {
  for (const bouton of $(idListe).children) {
    if (id !== null && id !== undefined && bouton.dataset.id === String(id)) {
      bouton.classList.add("actif");
    } else {
      bouton.classList.remove("actif");
    }
  }
}

/**
 * Recharge la chaîne après une écriture, en retrouvant les sélections par
 * identifiant : un nœud renommé reste sélectionné, un nœud supprimé vide les
 * colonnes qui en dépendaient.
 */
async function rechargerHierarchie() {
  // Les compteurs du haut (clans, familles, membres, encaissé) viennent de
  // `resume` : ils doivent suivre toute création, tout renommage et toute
  // suppression, même quand la chaîne s'arrête faute de sélection.
  await chargerResume();

  const clans = await chargerClans();
  const clan = clans.find((c) => c.id === etat.clan?.id) ?? null;
  etat.clan = clan;
  marquerParId("liste-clans", clan?.id);
  if (!clan) {
    reinitialiserApres("clan");
    return;
  }

  const gfs = await chargerGrandesFamilles(clan.id);
  const gf = gfs.find((g) => g.id === etat.grandeFamille?.id) ?? null;
  etat.grandeFamille = gf;
  marquerParId("liste-gf", gf?.id);
  if (!gf) {
    reinitialiserApres("grandeFamille");
    return;
  }

  const lignees = await chargerLignees(gf.id);
  const lignee = lignees.find((l) => l.id === etat.lignee?.id) ?? null;
  etat.lignee = lignee;
  marquerParId("liste-lignees", lignee?.id);
  if (!lignee) {
    reinitialiserApres("lignee");
    return;
  }

  const familles = await chargerFamilles(lignee.id);
  const famille = familles.find((f) => f.id === etat.famille?.id) ?? null;
  etat.famille = famille;
  marquerParId("liste-familles", famille?.id);
  if (!famille) {
    reinitialiserApres("famille");
    return;
  }

  await chargerMembres();
  $("fil").textContent = fil();
  $("titre-membres").textContent = famille.nom;
}

let noeudEdite = null; // { niveau, id } ; id null = création
const suppressionsArmees = new Set();

function fermerNom() {
  $("voile-nom").hidden = true;
  noeudEdite = null;
}

async function ouvrirNom(niveau, creation) {
  effacerErreur();
  const config = NOEUDS[niveau];
  const courant = config.courant();

  if (!creation && !courant) {
    afficherErreur(`Sélectionnez d'abord ${config.libelle} à renommer.`);
    return;
  }
  if (creation && niveau !== "clan" && !config.parent()) {
    afficherErreur(`Sélectionnez d'abord ${config.parentLibelle}.`);
    return;
  }

  noeudEdite = { niveau, id: creation ? null : courant.id };
  $("nom-titre").textContent = creation
    ? `Nouveau ${config.libelle}`
    : `Renommer ${config.libelle}`;
  $("nom-contexte").textContent = creation
    ? (config.parent()?.nom ?? "")
    : (courant.nom ?? "");
  $("nom-champ").value = creation ? "" : (courant.nom ?? "");
  $("nom-note").textContent = "";
  $("voile-nom").hidden = false;
  $("nom-champ").focus?.();
}

async function enregistrerNom() {
  if (!noeudEdite) return;
  const nom = $("nom-champ").value.trim();
  if (!nom) {
    $("nom-note").textContent = "Le nom est obligatoire.";
    return;
  }

  const config = NOEUDS[noeudEdite.niveau];
  try {
    if (noeudEdite.id === null) {
      await invoke("creer_noeud", {
        niveau: noeudEdite.niveau,
        parentId: config.parent()?.id ?? null,
        nom,
      });
    } else {
      await invoke("renommer_noeud", {
        niveau: noeudEdite.niveau,
        id: noeudEdite.id,
        nom,
      });
    }
    fermerNom();
    effacerErreur();
    await rechargerHierarchie();
  } catch (erreur) {
    $("nom-note").textContent = String(erreur);
  }
}

async function supprimerNoeud(niveau, bouton) {
  const courant = NOEUDS[niveau].courant();
  if (!courant) {
    afficherErreur(`Sélectionnez d'abord ${NOEUDS[niveau].libelle} à supprimer.`);
    return;
  }
  if (!suppressionsArmees.has(niveau)) {
    suppressionsArmees.add(niveau);
    bouton.textContent = "✕ ?";
    bouton.classList.add("arme");
    return;
  }

  suppressionsArmees.delete(niveau);
  bouton.textContent = "✕";
  bouton.classList.remove("arme");
  try {
    await invoke("supprimer_noeud", { niveau, id: courant.id });
    effacerErreur();
    await rechargerHierarchie();
  } catch (erreur) {
    afficherErreur(String(erreur));
  }
}

$("fermer-nom").addEventListener("click", fermerNom);
$("annuler-nom").addEventListener("click", fermerNom);
$("enregistrer-nom").addEventListener("click", () => {
  enregistrerNom().catch((e) => afficherErreur(e));
});

for (const [niveau, suffixe] of [
  ["clan", "clan"],
  ["grande_famille", "gf"],
  ["lignee", "lignee"],
  ["famille", "famille"],
]) {
  $(`ajouter-${suffixe}`).addEventListener("click", () => {
    ouvrirNom(niveau, true).catch((e) => afficherErreur(e));
  });
  $(`renommer-${suffixe}`).addEventListener("click", () => {
    ouvrirNom(niveau, false).catch((e) => afficherErreur(e));
  });
  $(`supprimer-${suffixe}`).addEventListener("click", () => {
    supprimerNoeud(niveau, $(`supprimer-${suffixe}`)).catch((e) =>
      afficherErreur(e),
    );
  });
}

/* -------------------------------- membres ------------------------------ */
function afficherMembres(membres) {
  const corps = $("corps-membres");
  corps.replaceChildren();
  ligneSelectionnee = null;
  membresAffiches = membres;

  if (membres.length === 0) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = 8;
    td.className = "vide-table";
    td.textContent =
      etat.vueComplete || etat.famille
        ? "Aucun membre ne correspond à cette recherche."
        : "Sélectionnez un clan, puis descendez jusqu'à une famille pour afficher ses membres.";
    tr.append(td);
    corps.append(tr);
  }

  for (const membre of membres) {
    const tr = document.createElement("tr");
    tr.className = "cliquable";
    tr.append(
      cellule(membre.nom),
      cellule(membre.prenom, membre.prenom ? "" : "doux"),
      celluleBadge(membre.statut),
      cellule(fcf(membre.paye), "numerique"),
      cellule(fcf(membre.reste), membre.reste > 0 ? "numerique" : "numerique doux"),
      cellule(
        fcf(membre.arrieres),
        membre.arrieres > 0 ? "numerique alerte" : "numerique doux",
      ),
      cellule(
        membre.chemin ?? membre.parent,
        membre.chemin || membre.parent ? "" : "doux",
      ),
    );

    // Le bouton de fiche ne doit pas ouvrir la feuille d'encaissement : le clic
    // remonte au <tr> dans un vrai navigateur.
    const caseFiche = document.createElement("td");
    const boutonFiche = document.createElement("button");
    boutonFiche.type = "button";
    boutonFiche.className = "lien";
    boutonFiche.textContent = "Fiche";
    boutonFiche.addEventListener("click", (evenement) => {
      evenement?.stopPropagation?.();
      ouvrirFiche(membre);
    });
    caseFiche.append(boutonFiche);
    tr.append(caseFiche);

    tr.addEventListener("click", () => ouvrirFeuille(membre, tr));
    corps.append(tr);
  }

  if (!etat.famille && !etat.vueComplete) {
    $("compte-membres").textContent = "";
    return;
  }

  const paye = membres.reduce((somme, m) => somme + m.paye, 0);
  const reste = membres.reduce((somme, m) => somme + m.reste, 0);
  const perimetre = etat.exercice
    ? `Exercice ${nomExercice(etat.exercice)}`
    : "Tous exercices";
  $("compte-membres").textContent =
    `${perimetre}   ·   ${pluriel(membres.length, "membre")}` +
    ` affiché${membres.length > 1 ? "s" : ""}` +
    `   ·   payé ${fcf(paye)}   ·   reste ${fcf(reste)}`;
}

let minuterie = null;

async function chargerMembres() {
  if (etat.vueComplete) {
    const membres = await invoke("tous_membres", {
      exerciceId: etat.exercice ? etat.exercice.id : null,
    });
    afficherMembres(filtrerMembres(membres, $("recherche").value.trim()));
    $("fil").textContent = "Toute la base";
    return membres;
  }
  if (!etat.famille) {
    afficherMembres([]);
    return null;
  }
  const recherche = $("recherche").value.trim();
  const membres = await invoke("membres", {
    familleId: etat.famille.id,
    recherche: recherche.length > 0 ? recherche : null,
    exerciceId: etat.exercice ? etat.exercice.id : null,
  });
  afficherMembres(membres);
  return membres;
}

$("voir-tous").addEventListener("click", () => {
  basculerVueComplete().catch((e) => afficherErreur(e));
});

$("recherche").addEventListener("input", () => {
  clearTimeout(minuterie);
  minuterie = setTimeout(() => {
    chargerMembres().catch((e) => afficherErreur(e));
  }, 150);
});

/* ------------------------------- fiche --------------------------------- */
let membreFiche = null;

function nomComplet(membre) {
  return membre.prenom ? `${membre.nom} ${membre.prenom}` : membre.nom;
}

async function chargerVersements(membreId) {
  const versements = await invoke("paiements_membre", { membreId });
  const boite = $("fiche-versements");
  boite.replaceChildren();

  if (versements.length === 0) {
    vide(boite, "Aucun versement enregistré pour ce membre.");
    return;
  }

  for (const versement of versements) {
    const bloc = document.createElement("div");
    bloc.className = "versement";

    const tete = document.createElement("div");
    tete.className = "versement-tete";
    const montant = document.createElement("span");
    montant.className = "versement-montant";
    montant.textContent = fcf(versement.montant_total);
    const details = document.createElement("span");
    details.className = "versement-details";
    const jour = (versement.date_paiement ?? "").split("-").reverse().join("/");
    details.textContent = [
      jour,
      versement.numero_recu ?? "sans reçu",
      MODES[versement.mode] ?? versement.mode,
    ].join(" · ");
    tete.append(montant, details);
    bloc.append(tete);

    const mois = document.createElement("p");
    mois.className = "versement-mois";
    mois.textContent = versement.affectations
      .map((part) => `${MOIS[part.mois - 1]} ${part.annee}`)
      .join(", ");
    bloc.append(mois);
    bloc.append(boutonAnnuler(versement));

    boite.append(bloc);
  }
}

/** État d'un mois de la grille : payé, partiel, impayé, à venir, hors période. */
function etatMois(mois) {
  if (!mois.assujetti) return "hors";
  if (mois.reste === 0) return "paye";
  if (mois.paye > 0) return "partiel";
  return mois.echue ? "impaye" : "avenir";
}

/**
 * Grille des douze mois : l'état de chaque échéance de l'exercice, d'un coup
 * d'œil. Les montants affichés sont les restes, jamais les dus.
 */
async function chargerGrille(membre) {
  const boite = $("fiche-grille");
  boite.replaceChildren();
  const exercice = exercicePourPaiement();
  if (!membre || !exercice) return;

  const mois = await invoke("grille_membre", {
    membreId: membre.id,
    exerciceId: exercice.id,
    dateReference: aujourdhui(),
  });

  for (const m of mois) {
    const etat = etatMois(m);
    const caseMois = document.createElement("div");
    caseMois.className = `case-mois ${etat}`;
    caseMois.title =
      `${MOIS[m.mois - 1]} ${m.annee} · dû ${fcf(m.du)} · payé ${fcf(m.paye)}`;

    const nom = document.createElement("span");
    nom.className = "case-nom";
    nom.textContent = MOIS[m.mois - 1].slice(0, 3);
    const montant = document.createElement("span");
    montant.className = "case-montant";
    montant.textContent =
      etat === "hors" ? "—" : m.reste === 0 ? "payé" : fcf(m.reste);
    caseMois.append(nom, montant);
    boite.append(caseMois);
  }
}

function ouvrirFiche(membre) {
  membreFiche = membre;
  $("fiche-titre").textContent = nomComplet(membre);
  $("fiche-chemin").textContent = membre.chemin ?? fil();
  majSoldesFiche(membre);
  $("fiche-versements").replaceChildren();
  $("fiche-grille").replaceChildren();
  $("voile-fiche").hidden = false;
  chargerVersements(membre.id).catch((e) => afficherErreur(e));
  chargerGrille(membre).catch((e) => afficherErreur(e));
}

function fermerFiche() {
  $("voile-fiche").hidden = true;
  $("fiche-grille").replaceChildren();
  membreFiche = null;
}

/* ----------------------- écrire la fiche d'un membre ------------------- */
let membreEdite = null; // null : création
let familleEditee = null;
let suppressionArmee = false;

function fermerFormulaire() {
  $("voile-membre").hidden = true;
  membreEdite = null;
  familleEditee = null;
  suppressionArmee = false;
  $("supprimer-membre").textContent = "Supprimer le membre";
  $("supprimer-membre").classList.remove("arme");
}

function optionTexte(valeur, libelle) {
  const option = document.createElement("option");
  option.value = valeur;
  option.textContent = libelle;
  return option;
}

/**
 * Ouvre le formulaire : `membreId = null` crée un membre dans la famille
 * affichée, sinon on relit la fiche complète (téléphone, dates, notes) que
 * le tableau ne porte pas.
 */
async function ouvrirFormulaireMembre(membreId) {
  effacerErreur();
  suppressionArmee = false;
  $("m-note").textContent = "";
  $("supprimer-membre").textContent = "Supprimer le membre";
  $("supprimer-membre").classList.remove("arme");

  // La fiche arrive en camelCase (serde `rename_all`), comme elle est envoyée.
  const detail = membreId
    ? await invoke("membre_edition", { membreId })
    : { familleId: etat.famille?.id ?? null, statut: "actif" };

  if (!detail.familleId) {
    afficherErreur("Sélectionnez d'abord une famille pour créer un membre.");
    return;
  }

  membreEdite = membreId ?? null;
  familleEditee = detail.familleId;
  $("membre-titre").textContent = membreId ? "Modifier le membre" : "Nouveau membre";
  $("membre-famille").textContent = etat.famille?.nom ?? "";

  $("m-nom").value = detail.nom ?? "";
  $("m-prenom").value = detail.prenom ?? "";
  $("m-telephone").value = detail.telephone ?? "";
  $("m-sexe").value = detail.sexe ?? "";
  $("m-statut").value = detail.statut ?? "actif";
  $("m-ordre").value = detail.ordreFratrie ?? "";
  $("m-entree").value = detail.dateEntree ?? "";
  $("m-sortie").value = detail.dateSortie ?? "";
  $("m-notes").value = detail.notes ?? "";
  $("supprimer-membre").hidden = !membreId;

  const parent = $("m-parent");
  parent.replaceChildren(optionTexte("", "— aucun —"));
  const candidats = await invoke("parents_candidats", {
    familleId: detail.familleId,
    exclure: membreId ?? null,
  });
  for (const candidat of candidats) {
    parent.append(optionTexte(String(candidat.id), candidat.nom));
  }
  parent.value = detail.parentId ? String(detail.parentId) : "";

  $("voile-membre").hidden = false;
  $("m-nom").focus?.();
}

async function enregistrerMembre() {
  if (!familleEditee) return;
  const nom = $("m-nom").value.trim();
  if (!nom) {
    $("m-note").textContent = "Le nom est obligatoire.";
    return;
  }

  const texte = (id) => {
    const valeur = $(id).value.trim();
    return valeur.length > 0 ? valeur : null;
  };
  const nombre = (id) => (texte(id) ? Number($(id).value) : null);

  const fiche = {
    id: membreEdite,
    familleId: familleEditee,
    parentId: texte("m-parent") ? Number($("m-parent").value) : null,
    nom,
    prenom: texte("m-prenom"),
    telephone: texte("m-telephone"),
    sexe: texte("m-sexe"),
    ordreFratrie: nombre("m-ordre"),
    statut: texte("m-statut"),
    dateEntree: texte("m-entree"),
    dateSortie: texte("m-sortie"),
    notes: texte("m-notes"),
  };

  $("m-note").textContent = "";
  try {
    const id = await invoke("enregistrer_membre", { fiche });
    effacerErreur();
    fermerFormulaire();
    await chargerMembres();
    await chargerResume();
    if (membreFiche && membreFiche.id === id) await rafraichirSoldesFiche();
  } catch (erreur) {
    $("m-note").textContent = String(erreur);
  }
}

async function supprimerMembre() {
  if (!membreEdite) return;
  const bouton = $("supprimer-membre");
  if (!suppressionArmee) {
    suppressionArmee = true;
    bouton.textContent = "Confirmer la suppression";
    bouton.classList.add("arme");
    return;
  }

  $("m-note").textContent = "";
  try {
    await invoke("supprimer_membre", { membreId: membreEdite });
    effacerErreur();
    fermerFormulaire();
    if (membreFiche) fermerFiche();
    await chargerMembres();
    await chargerResume();
  } catch (erreur) {
    $("m-note").textContent = String(erreur);
  }
}

$("nouveau-membre").addEventListener("click", () => {
  ouvrirFormulaireMembre(null).catch((e) => afficherErreur(e));
});

$("modifier-membre").addEventListener("click", () => {
  if (membreFiche) {
    ouvrirFormulaireMembre(membreFiche.id).catch((e) => afficherErreur(e));
  }
});

$("fermer-membre").addEventListener("click", fermerFormulaire);
$("annuler-membre").addEventListener("click", fermerFormulaire);
$("enregistrer-membre").addEventListener("click", () => {
  enregistrerMembre().catch((e) => afficherErreur(e));
});
$("supprimer-membre").addEventListener("click", () => {
  supprimerMembre().catch((e) => afficherErreur(e));
});

/**
 * Annulation en deux temps : un clic arme le bouton, le second supprime.
 * Pas de `confirm()` système : la confirmation reste dans la fiche.
 */
function boutonAnnuler(versement) {
  const pied = document.createElement("div");
  pied.className = "versement-pied";

  const bouton = document.createElement("button");
  bouton.type = "button";
  bouton.className = "lien danger";
  bouton.textContent = "Annuler";
  let arme = false;

  bouton.addEventListener("click", async (evenement) => {
    evenement?.stopPropagation?.();
    if (!arme) {
      arme = true;
      bouton.textContent = "Confirmer l'annulation";
      bouton.classList.add("arme");
      return;
    }

    const idMembre = membreFiche?.id;
    bouton.disabled = true;
    try {
      await invoke("supprimer_paiement", { paiementId: versement.id });
      if (idMembre) {
        await chargerVersements(idMembre);
        await rafraichirSoldesFiche();
      }
    } catch (erreur) {
      afficherErreur(erreur);
      bouton.disabled = false;
    }
  });

  pied.append(bouton);
  return pied;
}

/** Après une annulation, les soldes de la fiche et du tableau doivent suivre. */
async function rafraichirSoldesFiche() {
  if (!membreFiche) return;
  const aJour = await invoke("membre", {
    membreId: membreFiche.id,
    exerciceId: etat.exercice ? etat.exercice.id : null,
  });
  if (aJour) {
    membreFiche = { ...membreFiche, ...aJour };
    $("fiche-titre").textContent = nomComplet(membreFiche);
    majSoldesFiche(membreFiche);
    await chargerGrille(membreFiche);
    if (membreCourant && membreCourant.id === membreFiche.id) {
      membreCourant = { ...membreCourant, ...aJour };
      majSoldes(membreCourant);

      // Le reçu affiché dans la feuille correspond à un versement qui vient
      // d'être annulé : il ne doit pas rester à l'écran, et le bouton doit se
      // réarmer puisqu'il n'y a plus rien d'enregistré.
      viderRecu();
      $("repartition").hidden = true;
      $("repartition").replaceChildren();
      enregistre = false;
      armerBouton();
      $("note").textContent =
        membreCourant.reste > 0
          ? "La ventilation suit l'ordre des mois échus : le plus ancien d'abord."
          : "Ce membre est à jour sur cet exercice.";
    }
  }
  await chargerMembres();
  await chargerResume();
}

/* --------------------------- recherche globale -------------------------- */
let minuterieGlobale = null;

function effacerResultats() {
  $("resultats-membres").hidden = true;
  $("resultats-membres").replaceChildren();
}

/**
 * Encaisser sans parcourir la hiérarchie : on tape un nom, on clique le bon
 * membre (situé par son chemin) et la feuille s'ouvre directement.
 */
async function chercherMembre() {
  const texte = $("recherche-membre").value.trim();
  if (texte.length < 2) {
    effacerResultats();
    return;
  }

  const exercice = exercicePourPaiement();
  const trouves = await invoke("rechercher_membres", {
    recherche: texte,
    exerciceId: exercice ? exercice.id : null,
  });

  const boite = $("resultats-membres");
  boite.replaceChildren();
  if (trouves.length === 0) {
    const vide = document.createElement("p");
    vide.className = "vide";
    vide.textContent = "Aucun membre ne porte ce nom.";
    boite.append(vide);
  } else {
    for (const trouve of trouves) {
      const nom = trouve.prenom ? `${trouve.nom} ${trouve.prenom}` : trouve.nom;
      boite.append(
        ligne(nom, `${trouve.chemin} · reste ${fcf(trouve.reste)}`, () =>
          choisirPourCotisation(trouve),
        ),
      );
    }
  }
  boite.hidden = false;
}

function choisirPourCotisation(trouve) {
  $("recherche-membre").value = "";
  effacerResultats();
  ouvrirFeuille(trouve, null);
}

$("recherche-membre").addEventListener("input", () => {
  clearTimeout(minuterieGlobale);
  minuterieGlobale = setTimeout(() => {
    chercherMembre().catch((e) => afficherErreur(e));
  }, 150);
});

/* ------------------------------ cotisation ----------------------------- */
/** Année locale au format ISO, pour préremplir la date du versement. */
function aujourdhui() {
  const d = new Date();
  const mois = String(d.getMonth() + 1).padStart(2, "0");
  const jour = String(d.getDate()).padStart(2, "0");
  return `${d.getFullYear()}-${mois}-${jour}`;
}

/**
 * Un versement doit toujours viser un exercice : celui sélectionné dans les
 * puces, sinon l'exercice en cours. En mode « Tous », on ne peut pas deviner
 * l'année d'un encaissement, donc on retombe sur l'exercice courant.
 */
function exercicePourPaiement() {
  if (etat.exercice) return etat.exercice;
  return etat.exercices.find((e) => e.courant) ?? etat.exercices[0] ?? null;
}

/** L'exercice choisi **dans la feuille** prime sur celui du tableau. */
function exerciceDuPaiement() {
  return exerciceFeuille ?? exercicePourPaiement();
}

function dessinerAnneesFeuille() {
  $("annees-feuille").replaceChildren(
    ...etat.exercices.map((exercice) =>
      puce(nomExercice(exercice), exerciceFeuille?.id === exercice.id, () =>
        choisirExerciceFeuille(exercice),
      ),
    ),
  );
}

function majPerimetre() {
  const exercice = exerciceDuPaiement();
  if (!membreCourant || !exercice) {
    $("feuille-perimetre").textContent = "Aucun exercice disponible";
    return;
  }
  $("feuille-perimetre").textContent =
    `Exercice ${nomExercice(exercice)} · ` +
    `${pluriel(membreCourant.du, "franc")} dus sur le périmètre`;
}

/**
 * Changer d'année dans la feuille change le périmètre du versement : on relit
 * les soldes de cet exercice au lieu de garder ceux de l'année précédente.
 */
async function choisirExerciceFeuille(exercice) {
  if (!membreCourant || exerciceFeuille?.id === exercice.id) return;
  exerciceFeuille = exercice;
  dessinerAnneesFeuille();

  enregistre = false;
  $("montant").value = "";
  viderRecu();
  $("repartition").hidden = true;
  $("repartition").replaceChildren();
  armerBouton();

  const aJour = await invoke("membre", {
    membreId: membreCourant.id,
    exerciceId: exercice.id,
  });
  if (aJour) {
    membreCourant = { ...membreCourant, ...aJour };
    majSoldes(membreCourant);
  }
  majPerimetre();
  $("note").textContent =
    membreCourant.reste > 0
      ? "La ventilation suit l'ordre des mois échus : le plus ancien d'abord."
      : "Ce membre est à jour sur cet exercice.";
}

function blocSolde(libelle, valeur, alerte) {
  const boite = document.createElement("div");
  boite.className = "solde";
  const v = document.createElement("span");
  v.className = alerte ? "solde-valeur alerte" : "solde-valeur";
  v.textContent = fcf(valeur);
  const l = document.createElement("span");
  l.className = "solde-libelle";
  l.textContent = libelle;
  boite.append(v, l);
  return boite;
}

/**
 * Le bouton d'encaissement ne doit jamais rester armé sur un montant déjà
 * enregistré : sans cela, un second clic renvoie un reliquat au lieu de
 * proposer un nouveau versement.
 */
function armerBouton() {
  const bouton = $("encaisser");
  const montant = Number($("montant").value);
  const saisi = Number.isInteger(montant) && montant > 0;
  bouton.disabled = enregistre && !saisi;
  bouton.textContent =
    enregistre && !saisi ? "Versement enregistré" : "Enregistrer le versement";
}

function dessinerSoldes(idListe, membre) {
  $(idListe).replaceChildren(
    blocSolde("Payé", membre.paye, false),
    blocSolde("Reste", membre.reste, false),
    blocSolde("Arriérés", membre.arrieres, membre.arrieres > 0),
  );
}

function majSoldes(membre) {
  dessinerSoldes("feuille-soldes", membre);
}

function majSoldesFiche(membre) {
  dessinerSoldes("fiche-soldes", membre);
}

function ouvrirFeuille(membre, ligneTableau) {
  membreCourant = membre;

  if (ligneSelectionnee) ligneSelectionnee.classList.remove("selection");
  // Une feuille ouverte depuis la recherche n'a pas de ligne de tableau.
  ligneSelectionnee = ligneTableau ?? null;
  ligneTableau?.classList.add("selection");

  exerciceFeuille = exercicePourPaiement();
  dessinerAnneesFeuille();

  const nom = membre.prenom ? `${membre.nom} ${membre.prenom}` : membre.nom;
  $("feuille-titre").textContent = nom;
  majPerimetre();
  $("feuille-chemin").textContent = membre.chemin ?? fil();

  majSoldes(membre);

  enregistre = false;
  $("montant").value = "";
  armerBouton();
  $("date-paiement").value = aujourdhui();
  $("mode").value = "especes";
  $("note").textContent =
    membre.reste > 0
      ? "La ventilation suit l'ordre des mois échus : le plus ancien d'abord."
      : "Ce membre est à jour sur cet exercice.";

  $("repartition").hidden = true;
  $("repartition").replaceChildren();
  viderRecu();
  $("voile").hidden = false;
  $("montant").focus?.();
}

function fermerFeuille() {
  $("voile").hidden = true;
  $("repartition").hidden = true;
  enregistre = false;
  armerBouton();
  membreCourant = null;
  exerciceFeuille = null;
  if (ligneSelectionnee) {
    ligneSelectionnee.classList.remove("selection");
    ligneSelectionnee = null;
  }
}

/**
 * Ce que le versement en cours de saisie va couvrir : les mois, leur année, et
 * la part qui déborderait du dû (annoncée avant validation, pas après).
 */
function afficherApercu(plan) {
  const boite = $("repartition");
  boite.replaceChildren();

  const exercice = exerciceDuPaiement();
  const titre = document.createElement("p");
  titre.className = "repartition-titre";
  titre.textContent =
    `Imputé sur l'exercice ${nomExercice(exercice)} · ` +
    `${fcf(plan.ventile)} de ${fcf(membreCourant.du)} dus` +
    (plan.affectations.length === 0 ? " · aucun mois échu" : "");
  boite.append(titre);

  const date = $("date-paiement").value;
  const anneePaie = Number(date.slice(0, 4));
  const moisPaie = Number(date.slice(5, 7));

  if (plan.affectations.length > 0) {
    const liste = document.createElement("ul");
    for (const part of plan.affectations) {
      const li = document.createElement("li");
      const arriere =
        part.annee < anneePaie || (part.annee === anneePaie && part.mois < moisPaie);
      if (arriere) li.className = "arriere";
      li.textContent = `${MOIS[part.mois - 1]} ${part.annee} · ${fcf(part.montant)}`;
      liste.append(li);
    }
    boite.append(liste);
  }

  if (plan.reliquat > 0) {
    const reste = document.createElement("p");
    reste.className = "repartition-reliquat";
    reste.textContent =
      `${fcf(plan.reliquat)} ne peuvent pas être imputés : ` +
      "aucun mois échu ne reste à régler sur cet exercice. Baissez le montant ou choisissez l'année concernée.";
    boite.append(reste);
  }

  boite.hidden = false;
}

async function rafraichirApercu() {
  const boite = $("repartition");
  const exercice = exerciceDuPaiement();
  const montant = Number($("montant").value);

  if (!membreCourant || !exercice || !Number.isInteger(montant) || montant <= 0) {
    boite.hidden = true;
    boite.replaceChildren();
    return;
  }

  try {
    const plan = await invoke("previsualiser", {
      membreId: membreCourant.id,
      exerciceId: exercice.id,
      montant,
      datePaiement: $("date-paiement").value,
    });
    afficherApercu(plan);
  } catch (erreur) {
    boite.replaceChildren();
    const message = document.createElement("p");
    message.className = "repartition-reliquat";
    message.textContent = String(erreur);
    boite.append(message);
    boite.hidden = false;
  }
}

/**
 * Feuille d'impression : `@media print` ne laisse visible que ce bloc, qui
 * reprend le reçu à l'identique (même numéro, même montant, mêmes mois).
 */
function remplirImpression(paiement) {
  const boite = $("impression");
  boite.replaceChildren();

  const entete = document.createElement("div");
  entete.className = "impression-entete";
  const titre = document.createElement("h1");
  titre.textContent = "Fonds d'Entraide";
  const sousTitre = document.createElement("p");
  sousTitre.textContent = "Reçu de cotisation";
  entete.append(titre, sousTitre);

  const membre = document.createElement("p");
  membre.className = "impression-membre";
  membre.textContent = membreCourant ? nomComplet(membreCourant) : "";
  const chemin = document.createElement("p");
  chemin.className = "impression-chemin";
  chemin.textContent = $("feuille-chemin").textContent;

  const numero = document.createElement("p");
  numero.className = "impression-numero";
  numero.textContent = paiement.numero_recu;

  const date = ($("date-paiement").value || "").split("-").reverse().join("/");
  const mode = $("mode").value;
  const infos = document.createElement("p");
  infos.className = "impression-infos";
  infos.textContent = `${date} · ${MODES[mode] ?? mode} · ${fcf(paiement.montant_total)}`;

  const liste = document.createElement("ul");
  for (const part of paiement.affectations) {
    const li = document.createElement("li");
    li.textContent = `${MOIS[part.mois - 1]} ${part.annee} — ${fcf(part.montant)}`;
    liste.append(li);
  }

  const total = document.createElement("p");
  total.className = "impression-total";
  total.textContent = `Total : ${fcf(paiement.montant_total)}`;

  boite.append(entete, membre, chemin, numero, infos, liste, total);
}

/** Ouvre la boîte d'impression de WebView2 sur la feuille `#impression`. */
function imprimerRecu() {
  window.print?.();
}

function afficherRecu(paiement) {
  const boite = $("recu");
  boite.replaceChildren();

  const numero = document.createElement("p");
  numero.className = "recu-numero";
  numero.textContent = `${paiement.numero_recu} · ${fcf(paiement.montant_total)}`;
  boite.append(numero);

  const liste = document.createElement("ul");
  for (const part of paiement.affectations) {
    const li = document.createElement("li");
    li.textContent = `${MOIS[part.mois - 1]} ${part.annee} — ${fcf(part.montant)}`;
    liste.append(li);
  }
  boite.append(liste);

  const imprimer = document.createElement("button");
  imprimer.type = "button";
  imprimer.className = "secondaire imprimer";
  imprimer.textContent = "Imprimer le reçu";
  imprimer.addEventListener("click", () => imprimerRecu());
  boite.append(imprimer);

  remplirImpression(paiement);
  boite.hidden = false;
}

/** Efface reçu et feuille d'impression : ils ne doivent pas survivre à
 *  l'annulation du versement ou à une nouvelle saisie. */
function viderRecu() {
  $("recu").hidden = true;
  $("recu").replaceChildren();
  $("impression").replaceChildren();
}

async function encaisser() {
  if (!membreCourant) return;

  const exercice = exerciceDuPaiement();
  const montant = Number($("montant").value);
  if (!Number.isInteger(montant) || montant <= 0) {
    $("note").textContent = "Montant invalide : un nombre entier de francs, supérieur à zéro.";
    return;
  }
  if (!exercice) {
    $("note").textContent = "Aucun exercice ouvert : impossible d'imputer le versement.";
    return;
  }

  const bouton = $("encaisser");
  bouton.disabled = true;
  bouton.textContent = "Enregistrement…";
  try {
    const paiement = await invoke("enregistrer_paiement", {
      membreId: membreCourant.id,
      exerciceId: exercice.id,
      montant,
      datePaiement: $("date-paiement").value,
      mode: $("mode").value,
    });
    afficherRecu(paiement);
    enregistre = true;
    $("montant").value = "";
    $("note").textContent = "";
    $("repartition").hidden = true;
    $("repartition").replaceChildren();

    // Les soldes doivent suivre l'encaissement. On relit le membre lui-même :
    // la feuille peut avoir été ouverte par la recherche, donc hors de la
    // famille actuellement affichée.
    const id = membreCourant.id;
    await chargerMembres();
    const aJour = await invoke("membre", {
      membreId: id,
      exerciceId: exercice.id,
    });
    if (aJour) {
      membreCourant = { ...membreCourant, ...aJour };
      majSoldes(membreCourant);
    }
    await chargerResume();
  } catch (erreur) {
    $("note").textContent = String(erreur);
  } finally {
    // `armerBouton` et non `disabled = false` : après un succès, le bouton doit
    // rester désarmé jusqu'à la prochaine saisie.
    armerBouton();
  }
}

for (const id of ["montant", "date-paiement"]) {
  $(id).addEventListener("input", () => {
    if (id === "montant") {
      // Nouvelle saisie = nouveau versement : le reçu précédent s'efface et le
      // bouton se réarme.
      enregistre = false;
      viderRecu();
    }
    armerBouton();
    rafraichirApercu().catch((e) => afficherErreur(e));
  });
  $(id).addEventListener("change", () => {
    armerBouton();
    rafraichirApercu().catch((e) => afficherErreur(e));
  });
}

$("fermer-fiche").addEventListener("click", fermerFiche);
$("voile-fiche").addEventListener("click", (evenement) => {
  if (evenement.target === $("voile-fiche")) fermerFiche();
});
$("ouvrir-historique").addEventListener("click", () => {
  if (membreCourant) ouvrirFiche(membreCourant);
});
$("fermer-feuille").addEventListener("click", fermerFeuille);
$("encaisser").addEventListener("click", () => {
  encaisser().catch((e) => afficherErreur(e));
});
$("voile").addEventListener("click", (evenement) => {
  if (evenement.target === $("voile")) fermerFeuille();
});

/* ------------------------- sauvegardes de la base ---------------------- */
let restaurationArmee = null;

/** « 10 novembre 2026 à 15:19 » pour `cotisations_2026-11-10_15-19-00.db`. */
function dateSauvegarde(nom) {
  const m = nom.match(/^cotisations_(\d{4})-(\d{2})-(\d{2})_(\d{2})-(\d{2})-(\d{2})/);
  if (!m) return nom;
  const [, annee, mois, jour, heure, minute] = m;
  return `${Number(jour)} ${MOIS[Number(mois) - 1]} ${annee} à ${heure}:${minute}`;
}

function tailleLisible(octets) {
  if (!octets || octets < 1024) return `${octets ?? 0} o`;
  return `${nf.format(Math.round(octets / 1024))} Ko`;
}

function ligneSauvegarde(sauvegarde, recente) {
  const rangee = document.createElement("div");
  rangee.className = "sauvegarde";
  if (recente) rangee.classList.add("recente");

  const texte = document.createElement("div");
  texte.className = "sauvegarde-texte";
  const nom = document.createElement("span");
  nom.className = "sauvegarde-nom";
  nom.textContent = dateSauvegarde(sauvegarde.nom);
  const detail = document.createElement("span");
  detail.className = "sauvegarde-detail";
  detail.textContent =
    `${sauvegarde.nom} · ${tailleLisible(sauvegarde.octets)}` +
    (recente ? " · la plus récente" : "");
  texte.append(nom, detail);

  const restaurer = document.createElement("button");
  restaurer.type = "button";
  restaurer.className = "secondaire restaurer";
  restaurer.textContent = "Restaurer";
  restaurer.addEventListener("click", () => {
    // Deux clics : une restauration remplace le contenu de la base courante.
    if (restaurationArmee !== sauvegarde.nom) {
      for (const autre of $("liste-sauvegardes").querySelectorAll(".restaurer")) {
        autre.textContent = "Restaurer";
        autre.classList.remove("arme");
      }
      restaurationArmee = sauvegarde.nom;
      restaurer.textContent = "Confirmer";
      restaurer.classList.add("arme");
      $("sauvegarde-note").textContent =
        `Restaurer la copie du ${dateSauvegarde(sauvegarde.nom)} ? L'état actuel est d'abord ` +
        "sauvegardé, puis tout ce qui a été saisi depuis cette copie disparaît.";
      return;
    }
    restaurationArmee = null;
    restaurerSauvegarde(sauvegarde.nom);
  });

  rangee.append(texte, restaurer);
  return rangee;
}

async function chargerSauvegardes() {
  const liste = await invoke("sauvegardes");
  const conteneur = $("liste-sauvegardes");
  conteneur.replaceChildren();
  if (liste.length === 0) {
    vide(conteneur, "Aucune sauvegarde pour l'instant.");
    return;
  }
  for (const [index, sauvegarde] of liste.entries()) {
    conteneur.append(ligneSauvegarde(sauvegarde, index === 0));
  }
}

async function ouvrirSauvegardes() {
  effacerErreur();
  restaurationArmee = null;
  desarmerPurges();
  $("sauvegarder-base").disabled = false;
  $("sauvegarder-base").textContent = "Sauvegarder maintenant";
  $("sauvegarde-note").textContent =
    "Seules les cinq copies de l'application sont conservées : à chaque nouvelle " +
    "sauvegarde, la plus ancienne est effacée. Les archives laissées dans ce dossier " +
    "par l'ancienne version ne sont ni listées ni supprimées.";
  $("voile-sauvegarde").hidden = false;
  try {
    await chargerSauvegardes();
  } catch (erreur) {
    $("sauvegarde-note").textContent = String(erreur);
  }
}

async function sauvegarderMaintenant() {
  const bouton = $("sauvegarder-base");
  bouton.disabled = true;
  bouton.textContent = "Sauvegarde…";
  try {
    const faite = await invoke("sauvegarder_base");
    $("sauvegarde-note").textContent =
      `Copie enregistrée : ${faite.nom} — ${dateSauvegarde(faite.nom)} (${tailleLisible(faite.octets)}).`;
    await chargerSauvegardes();
  } catch (erreur) {
    $("sauvegarde-note").textContent = String(erreur);
  } finally {
    bouton.disabled = false;
    bouton.textContent = "Sauvegarder maintenant";
  }
}

/** Après une restauration, rien de ce qui est affiché ne doit survivre. */
async function rechargerTout() {
  fermerFeuille();
  fermerFiche();
  fermerFormulaire();
  viderRecu();
  membreCourant = null;
  ligneSelectionnee = null;
  quitterVueComplete();
  $("recherche").value = "";
  await chargerExercices();
  await rechargerHierarchie();
}

async function restaurerSauvegarde(nom) {
  $("sauvegarde-note").textContent = `Restauration de ${nom}…`;
  try {
    const secours = await invoke("restaurer_base", { nom });
    await rechargerTout();
    $("sauvegarde-note").textContent =
      `Base restaurée depuis ${nom}. L'état précédent est conservé dans ${secours.nom}.`;
  } catch (erreur) {
    $("sauvegarde-note").textContent = String(erreur);
  }
  await chargerSauvegardes().catch(() => {});
}

/* --------------------------------- purge -------------------------------- */
let purgeArmee = null;

const PURGES = {
  cotisations: {
    id: "purge-cotisations",
    libelle: "Effacer les cotisations",
    question: "Effacer tous les versements ? Toutes les échéances redeviendront dues.",
  },
  hierarchie: {
    id: "purge-hierarchie",
    libelle: "Effacer membres et hiérarchie",
    question:
      "Effacer les membres, les familles et les clans, avec leurs versements ?",
  },
  tout: {
    id: "purge-tout",
    libelle: "Tout effacer",
    question: "Tout effacer : membres, hiérarchie et versements ?",
  },
};

function desarmerPurges() {
  purgeArmee = null;
  for (const reglage of Object.values(PURGES)) {
    $(reglage.id).textContent = reglage.libelle;
    $(reglage.id).classList.remove("arme");
  }
}

/** « Effacé : 227 versements, 1 805 affectations. » — on dit ce qui est parti. */
function resumePurge(bilan) {
  const morceaux = [];
  const ajouter = (nombre, singulier, plurielMot) => {
    if (nombre > 0) morceaux.push(`${nombre} ${nombre > 1 ? plurielMot : singulier}`);
  };
  ajouter(bilan.paiements, "versement", "versements");
  ajouter(bilan.affectations, "affectation", "affectations");
  ajouter(bilan.membres, "membre", "membres");
  ajouter(bilan.familles, "famille", "familles");
  ajouter(bilan.lignees, "lignée", "lignées");
  ajouter(bilan.grandesFamilles, "grande famille", "grandes familles");
  ajouter(bilan.clans, "clan", "clans");
  return morceaux.length === 0 ? "Rien à effacer." : `Effacé : ${morceaux.join(", ")}.`;
}

async function purgerBase(portee) {
  const reglage = PURGES[portee];
  if (!reglage) return;
  const bouton = $(reglage.id);

  // Deux clics : la première fois on annonce, la seconde on efface.
  if (purgeArmee !== portee) {
    desarmerPurges();
    purgeArmee = portee;
    bouton.textContent = "Confirmer…";
    bouton.classList.add("arme");
    $("sauvegarde-note").textContent =
      `${reglage.question} Cliquez à nouveau pour confirmer : une copie de sécurité ` +
      "est prise juste avant.";
    return;
  }

  desarmerPurges();
  bouton.disabled = true;
  try {
    const faite = await invoke("purger_base", { portee });
    await rechargerTout();
    const resume = resumePurge(faite.bilan);
    $("sauvegarde-note").textContent = `${resume} Copie de sécurité : ${faite.copie.nom}.`;
    afficherInfo(`${resume} Copie de sécurité : ${faite.copie.nom}.`);
  } catch (erreur) {
    $("sauvegarde-note").textContent = String(erreur);
  } finally {
    bouton.disabled = false;
    desarmerPurges();
    await chargerSauvegardes().catch(() => {});
  }
}

for (const portee of Object.keys(PURGES)) {
  $(PURGES[portee].id).addEventListener("click", () => {
    purgerBase(portee).catch((e) => afficherErreur(e));
  });
}

/* ------------------------------ démonstration --------------------------- */
async function ouvrirDemonstration() {
  try {
    await invoke("lancer_demo");
    $("sauvegarde-note").textContent =
      "Démonstration ouverte dans une nouvelle fenêtre. La base réelle reste " +
      "ouverte ici, intacte.";
  } catch (erreur) {
    $("sauvegarde-note").textContent = String(erreur);
  }
}

$("ouvrir-demo").addEventListener("click", () => {
  ouvrirDemonstration().catch((e) => afficherErreur(e));
});

/* ---------------------------------- aide -------------------------------- */
/**
 * Affiche un document embarqué dans l'écran d'aide. Le HTML vient du binaire
 * (`lire_aide`) : une iframe le rend telle quelle, sans réseau ni fichier.
 */
async function afficherAide(doc) {
  try {
    const html = await invoke("lire_aide", { doc });
    const page = $("aide-page");
    page.srcdoc = html;
    page.hidden = false;
    $("imprimer-aide").hidden = false;
    $("aide-fil").textContent =
      doc === "guide" ? "Guide d'utilisation" : "Aide-mémoire — une page";
    $("aide-note").textContent = "";
  } catch (erreur) {
    $("aide-note").textContent = String(erreur);
  }
}

function fermerAide() {
  $("voile-aide").hidden = true;
  $("aide-page").srcdoc = "";
  $("aide-page").hidden = true;
  $("imprimer-aide").hidden = true;
  $("aide-fil").textContent = "Choisissez un document";
}

/** Imprime le document affiché, pas la fenêtre principale. */
function imprimerAide() {
  $("aide-page").contentWindow?.print?.();
}

$("ouvrir-aide").addEventListener("click", () => {
  $("aide-note").textContent = "";
  $("voile-aide").hidden = false;
});
for (const id of ["fermer-aide", "annuler-aide"]) {
  $(id).addEventListener("click", fermerAide);
}
$("voile-aide").addEventListener("click", (evenement) => {
  if (evenement.target === $("voile-aide")) fermerAide();
});
$("lire-aide-memoire").addEventListener("click", () => {
  afficherAide("aide-memoire").catch((e) => afficherErreur(e));
});
$("lire-guide").addEventListener("click", () => {
  afficherAide("guide").catch((e) => afficherErreur(e));
});
$("imprimer-aide").addEventListener("click", imprimerAide);

$("ouvrir-sauvegarde").addEventListener("click", () => {
  ouvrirSauvegardes().catch((e) => afficherErreur(e));
});
$("sauvegarder-base").addEventListener("click", () => {
  sauvegarderMaintenant().catch((e) => afficherErreur(e));
});
for (const id of ["fermer-sauvegarde", "annuler-sauvegarde"]) {
  $(id).addEventListener("click", () => {
    $("voile-sauvegarde").hidden = true;
    restaurationArmee = null;
    desarmerPurges();
  });
}
$("voile-sauvegarde").addEventListener("click", (evenement) => {
  if (evenement.target === $("voile-sauvegarde")) {
    $("voile-sauvegarde").hidden = true;
    restaurationArmee = null;
    desarmerPurges();
  }
});

/* ------------------------------ exports CSV ---------------------------- */
let membresAffiches = [];

/** Montant nu : un « 1 807 000 » serait du texte pour Excel. */
const montantCsv = (valeur) => String(valeur ?? 0);

/** « 2026 », ou « (tous exercices) » quand le tableau additionne les années. */
function suffixeExercice() {
  return etat.exercice ? ` ${nomExercice(etat.exercice)}` : " (tous exercices)";
}

/** Écrit une liste affichée en CSV et donne son chemin dans le bandeau. */
async function exporterCsv(nom, colonnes, lignes) {
  if (lignes.length === 0) {
    afficherErreur("Cette liste est vide : il n'y a rien à exporter.");
    return;
  }
  try {
    const fait = await invoke("exporter_csv", { nom, colonnes, lignes });
    afficherInfo(
      `${pluriel(fait.lignes, "ligne")} exportée${fait.lignes > 1 ? "s" : ""} : ${fait.chemin}`,
    );
  } catch (erreur) {
    afficherErreur(erreur);
  }
}

function exporterMembres() {
  const suffixe = suffixeExercice();
  const colonnes = [
    "Nom",
    "Prénom",
    "Statut",
    `Payé${suffixe}`,
    `Reste${suffixe}`,
    `Arriérés${suffixe}`,
    etat.vueComplete ? "Chemin" : "Parent",
  ];
  const lignes = membresAffiches.map((m) => [
    m.nom,
    m.prenom ?? "",
    m.statut,
    montantCsv(m.paye),
    montantCsv(m.reste),
    montantCsv(m.arrieres),
    m.chemin ?? m.parent ?? "",
  ]);
  return exporterCsv("membres", colonnes, lignes);
}

/** Liste complète : toutes les familles, avec le chemin de chaque membre. */
async function exporterTousLesMembres() {
  const suffixe = suffixeExercice();
  const membres = await invoke("tous_membres", {
    exerciceId: etat.exercice ? etat.exercice.id : null,
  });
  const colonnes = [
    "Chemin",
    "Nom",
    "Prénom",
    "Statut",
    `Payé${suffixe}`,
    `Reste${suffixe}`,
    `Arriérés${suffixe}`,
    "Parent",
  ];
  const lignes = membres.map((m) => [
    m.chemin,
    m.nom,
    m.prenom ?? "",
    m.statut,
    montantCsv(m.paye),
    montantCsv(m.reste),
    montantCsv(m.arrieres),
    m.parent ?? "",
  ]);
  return exporterCsv("membres-tous", colonnes, lignes);
}

/**
 * Feuille d'impression d'une liste : même mécanisme que le reçu, `@media print`
 * ne laisse visible que `#impression`. Ce qui est imprimé est ce qui est
 * affiché : famille sélectionnée, recherche et exercice compris.
 */
function imprimerListeMembres() {
  if (membresAffiches.length === 0) {
    afficherErreur("Aucun membre affiché : choisissez une famille avant d'imprimer.");
    return;
  }

  const boite = $("impression");
  boite.replaceChildren();

  const entete = document.createElement("div");
  entete.className = "impression-entete";
  const titre = document.createElement("h1");
  titre.textContent = "Fonds d'Entraide";
  const sousTitre = document.createElement("p");
  sousTitre.textContent = "Liste des membres";
  entete.append(titre, sousTitre);

  const famille = document.createElement("p");
  famille.className = "impression-membre";
  famille.textContent = etat.famille ? etat.famille.nom : "Tous les membres";
  const chemin = document.createElement("p");
  chemin.className = "impression-chemin";
  chemin.textContent = fil();

  const exercice = etat.exercice
    ? `Exercice ${nomExercice(etat.exercice)}`
    : "Tous exercices";
  const jour = aujourdhui().split("-").reverse().join("/");
  const infos = document.createElement("p");
  infos.className = "impression-infos";
  infos.textContent =
    `${exercice} · ${pluriel(membresAffiches.length, "membre")}` +
    ` affiché${membresAffiches.length > 1 ? "s" : ""} · imprimé le ${jour}`;

  const table = document.createElement("table");
  table.className = "impression-table";
  const thead = document.createElement("thead");
  const tete = document.createElement("tr");
  for (const [texte, classe] of [
    ["Nom", ""],
    ["Prénom", ""],
    ["Statut", ""],
    ["Payé", "droite"],
    ["Reste", "droite"],
    ["Arriérés", "droite"],
    [etat.vueComplete ? "Chemin" : "Parent", ""],
  ]) {
    const th = document.createElement("th");
    th.textContent = texte;
    if (classe) th.className = classe;
    tete.append(th);
  }
  thead.append(tete);

  const corps = document.createElement("tbody");
  for (const membre of membresAffiches) {
    const tr = document.createElement("tr");
    tr.append(
      cellule(membre.nom),
      cellule(membre.prenom),
      cellule(membre.statut),
      cellule(fcf(membre.paye), "droite"),
      cellule(fcf(membre.reste), "droite"),
      cellule(fcf(membre.arrieres), "droite"),
      cellule(membre.chemin ?? membre.parent),
    );
    corps.append(tr);
  }
  table.append(thead, corps);

  const paye = membresAffiches.reduce((somme, m) => somme + m.paye, 0);
  const reste = membresAffiches.reduce((somme, m) => somme + m.reste, 0);
  const arrieres = membresAffiches.reduce((somme, m) => somme + m.arrieres, 0);
  const total = document.createElement("p");
  total.className = "impression-total";
  total.textContent =
    `Total payé ${fcf(paye)} · reste ${fcf(reste)} · arriérés ${fcf(arrieres)}`;

  boite.append(entete, famille, chemin, infos, table, total);
  window.print?.();
}

function exporterClans() {
  return exporterCsv(
    "clans",
    ["ID", "Nom", "Description"],
    etat.clans.map((c) => [montantCsv(c.id), c.nom, c.description ?? ""]),
  );
}

function exporterGrandesFamilles() {
  return exporterCsv(
    "grandes-familles",
    ["ID", "Nom", "Clan"],
    etat.grandesFamilles.map((g) => [montantCsv(g.id), g.nom, etat.clan?.nom ?? ""]),
  );
}

function exporterLignees() {
  return exporterCsv(
    "lignees",
    ["ID", "Nom", "Grande famille"],
    etat.lignees.map((l) => [montantCsv(l.id), l.nom, etat.grandeFamille?.nom ?? ""]),
  );
}

function exporterFamilles() {
  return exporterCsv(
    "familles",
    ["ID", "Nom", "Membres"],
    etat.familles.map((f) => [montantCsv(f.id), f.nom, montantCsv(f.membres)]),
  );
}

/* ---------------------------- menu « Plus » ----------------------------- */
function fermerMenuPlus() {
  $("menu-plus").hidden = true;
  $("ouvrir-plus").classList.remove("actif");
}

$("ouvrir-plus").addEventListener("click", (evenement) => {
  evenement?.stopPropagation?.();
  const ouvert = $("menu-plus").hidden;
  $("menu-plus").hidden = !ouvert;
  if (ouvert) $("ouvrir-plus").classList.add("actif");
  else $("ouvrir-plus").classList.remove("actif");
});

for (const [id, action] of [
  ["exporter-membres", exporterMembres],
  ["exporter-tous", exporterTousLesMembres],
  ["imprimer-membres", () => imprimerListeMembres()],
]) {
  $(id).addEventListener("click", () => {
    fermerMenuPlus();
    Promise.resolve(action()).catch((e) => afficherErreur(e));
  });
}

// Les colonnes de la hiérarchie gardent leur bouton ⤓ direct.
for (const [id, action] of [
  ["exporter-clans", exporterClans],
  ["exporter-gf", exporterGrandesFamilles],
  ["exporter-lignees", exporterLignees],
  ["exporter-familles", exporterFamilles],
]) {
  $(id).addEventListener("click", () => {
    action().catch((e) => afficherErreur(e));
  });
}

/* -------------------------------- départ ------------------------------- */
async function demarrer() {
  try {
    effacerErreur();
    // La démonstration se voit tout de suite : aucune capture d'écran ne doit
    // faire passer ces montants fictifs pour les vrais.
    etat.demo = await invoke("mode_demo");
    if (etat.demo) {
      $("bandeau").hidden = false;
      $("bandeau").textContent =
        "Base de démonstration : membres et montants sont fictifs. Vos données " +
        "réelles ne sont pas ouvertes.";
      // Inutile de relancer une démonstration depuis la démonstration.
      $("ouvrir-demo").hidden = true;
    }
    await chargerResume();
    await chargerExercices();
    // Passer par chargerClans garde etat.clans rempli : l'export « clans »
    // et la vue complète s'appuient dessus.
    await chargerClans();
    vide($("liste-gf"), "Sélectionnez un clan");
    vide($("liste-lignees"), "Sélectionnez une grande famille");
    vide($("liste-familles"), "Sélectionnez une lignée");
    afficherMembres([]);
  } catch (erreur) {
    afficherErreur(erreur);
  }
}

demarrer();
