//! Test de fumée de l'interface, sans dépendance : un DOM minimal, un pont
//! Tauri simulé, et le vrai `ui/app.js` exécuté dedans.
//!
//! Ce qu'il attrape : une fonction appelée mais non définie (le bug
//! `choisirExercice`), un identifiant absent de `index.html`, un handler qui
//! lève, un en-tête qui ne suit pas l'exercice choisi.
//!
//!     node tests/ui/fumee.mjs

import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const ici = path.dirname(fileURLToPath(import.meta.url));
const racine = path.resolve(ici, "..", "..");
const lire = (...morceaux) => fs.readFileSync(path.join(racine, ...morceaux), "utf8");

/* ------------------------------ DOM minimal ----------------------------- */
const erreurs = [];

class Element {
  constructor(balise) {
    this.balise = balise.toUpperCase();
    this.enfants = [];
    this.parentElement = null;
    this.ecouteurs = new Map();
    this.className = "";
    this._texte = "";
    this.hidden = false;
    this.value = "";
    this.type = "";
    this.colSpan = 1;
    this.dataset = {};
    const liste = () => this.className.split(/\s+/).filter(Boolean);
    this.classList = {
      add: (classe) => {
        if (!liste().includes(classe)) this.className = [...liste(), classe].join(" ");
      },
      remove: (classe) => {
        this.className = liste()
          .filter((c) => c !== classe)
          .join(" ");
      },
      contains: (classe) => liste().includes(classe),
    };
  }

  get children() {
    return this.enfants;
  }

  get firstElementChild() {
    return this.enfants[0] ?? null;
  }

  get textContent() {
    if (this.enfants.length > 0) {
      return this.enfants.map((enfant) => enfant.textContent).join("");
    }
    return this._texte;
  }

  set textContent(valeur) {
    this._texte = String(valeur);
    this.enfants = [];
  }

  append(...noeuds) {
    for (const noeud of noeuds) {
      noeud.parentElement = this;
      this.enfants.push(noeud);
    }
  }

  replaceChildren(...noeuds) {
    this.enfants = [];
    this._texte = "";
    this.append(...noeuds);
  }

  addEventListener(type, action) {
    if (!this.ecouteurs.has(type)) this.ecouteurs.set(type, []);
    this.ecouteurs.get(type).push(action);
  }

  /** Déclenche un événement comme un utilisateur ; exception retenue. */
  declencher(type) {
    for (const action of this.ecouteurs.get(type) ?? []) {
      try {
        const resultat = action(this);
        if (resultat && typeof resultat.then === "function") {
          resultat.catch((e) => erreurs.push(e));
        }
      } catch (e) {
        erreurs.push(e);
      }
    }
  }

  click() {
    this.declencher("click");
  }

  input() {
    this.declencher("input");
  }

  correspond(selecteur) {
    const classes = this.className.split(/\s+/).filter(Boolean);
    return selecteur
      .split(".")
      .filter(Boolean)
      .every((classe) => classes.includes(classe));
  }

  querySelectorAll(selecteur) {
    const trouves = [];
    const parcourir = (noeud) => {
      for (const enfant of noeud.enfants) {
        if (enfant.correspond(selecteur)) trouves.push(enfant);
        parcourir(enfant);
      }
    };
    parcourir(this);
    return trouves;
  }
}

const html = lire("ui", "index.html");
const css = lire("ui", "style.css");
const elements = new Map();
for (const [balise] of html.matchAll(/<[a-zA-Z][^>]*>/g)) {
  const id = balise.match(/\bid="([^"]+)"/)?.[1];
  if (!id) continue;
  const element = new Element("div");
  // L'état initial de `hidden` vient du vrai HTML, pas d'un défaut inventé.
  element.hidden = /\shidden(\s|>|=)/.test(balise);
  elements.set(id, element);
}

// Le CSS ne doit jamais écraser l'attribut `hidden` : c'est ce qui laissait le
// voile affiché au démarrage, bloquant tous les clics (et la saisie du membre).
assert.match(
  css,
  /\[hidden\]\s*\{[^}]*display:\s*none\s*!important/,
  "style.css doit neutraliser [hidden]",
);

const document = {
  createElement: (balise) => new Element(balise),
  getElementById: (id) => elements.get(id) ?? null,
};

/* --------------------------- pont Tauri simulé -------------------------- */
const appels = [];
const reponses = {
  resume: { clans: 7, familles: 391, membres: 599, encaisse: 1_807_000 },
  previsualiser: {
    ventile: 2_000,
    reliquat: 3_000,
    affectations: [
      { echeance_id: 1, annee: 2026, mois: 1, montant: 1_000 },
      { echeance_id: 2, annee: 2026, mois: 2, montant: 1_000 },
    ],
  },
  enregistrer_paiement: {
    id: 900,
    numero_recu: "RECU-2026-000001",
    montant_total: 2_000,
    affectations: [
      { echeance_id: 1, annee: 2026, mois: 1, montant: 1_000 },
      { echeance_id: 2, annee: 2026, mois: 2, montant: 1_000 },
    ],
  },
  supprimer_paiement: null,
  paiements_membre: [
    {
      id: 901,
      date_paiement: "2026-11-10",
      montant_total: 2_000,
      mode: "especes",
      numero_recu: "RECU-2026-000001",
      affectations: [
        { echeance_id: 1, annee: 2026, mois: 1, montant: 1_000 },
        { echeance_id: 2, annee: 2026, mois: 2, montant: 1_000 },
      ],
    },
    {
      id: 900,
      date_paiement: "2026-10-05",
      montant_total: 1_000,
      mode: "mobile_money",
      numero_recu: "RECU-2026-000002",
      affectations: [{ echeance_id: 3, annee: 2026, mois: 3, montant: 1_000 }],
    },
  ],
  // Réponse réelle de la commande : serde la sérialise en camelCase.
  creer_noeud: 999,
  renommer_noeud: null,
  supprimer_noeud: null,
  membre_edition: {
    id: 180,
    familleId: 180,
    parentId: null,
    nom: "Akesse",
    prenom: "Comoé",
    telephone: "07 00 00 00 00",
    sexe: "M",
    ordreFratrie: null,
    statut: "actif",
    dateEntree: "2020-01-01",
    dateSortie: null,
    notes: null,
  },
  parents_candidats: [{ id: 181, nom: "Akesse Aya" }],
  enregistrer_membre: 181,
  supprimer_membre: null,
  // Grille des 12 mois : janvier à mars soldés, le reste en attente.
  grille_membre: Array.from({ length: 12 }, (_, i) => ({
    echeance_id: i + 1,
    annee: 2026,
    mois: i + 1,
    date_echeance: `2026-${String(i + 1).padStart(2, "0")}-28`,
    du: 1_000,
    paye: i < 3 ? 1_000 : 0,
    reste: i < 3 ? 0 : 1_000,
    echue: i < 3,
    assujetti: true,
  })),
  rechercher_membres: [
    {
      id: 180,
      nom: "Akesse",
      prenom: "Comoé",
      statut: "actif",
      ordre_fratrie: null,
      parent: null,
      du: 12_000,
      paye: 3_000,
      reste: 9_000,
      arrieres: 8_000,
      chemin: "YAOCRE › Akesse Comoé",
    },
  ],
  membre: {
    id: 180,
    nom: "Akesse",
    prenom: "Comoé",
    statut: "actif",
    ordre_fratrie: null,
    parent: null,
    du: 12_000,
    paye: 5_000,
    reste: 7_000,
    arrieres: 6_000,
  },
  exercices: [
    { id: 1, libelle: "Campagne 2026", date_debut: "2026-01-01", date_fin: "2026-12-31", montant_mensuel: 1_000, annee: 2026, statut: "ouverte", courant: true },
    { id: 2, libelle: "Campagne 2025", date_debut: "2025-01-01", date_fin: "2025-12-31", montant_mensuel: 1_000, annee: 2025, statut: "fermee", courant: false },
    { id: 3, libelle: "Campagne 2024", date_debut: "2024-01-01", date_fin: "2024-12-31", montant_mensuel: 1_000, annee: 2024, statut: "fermee", courant: false },
  ],
  changer_tarif: {
    montant: 1_500,
    annee_effet: 2026,
    mois_effet: 4,
    modifies: 8,
    conserves: 1,
  },
  sauvegardes: [
    { nom: "cotisations_2026-11-10_16-27-10.db", chemin: "C:\\tmp\\sauvegardes\\a.db", octets: 200_704 },
    { nom: "cotisations_2026-11-01_09-00-00.db", chemin: "C:\\tmp\\sauvegardes\\b.db", octets: 198_656 },
  ],
  sauvegarder_base: {
    nom: "cotisations_2026-11-10_16-00-00.db",
    chemin: "C:\\tmp\\sauvegardes\\c.db",
    octets: 200_704,
  },
  restaurer_base: {
    nom: "cotisations_2026-11-10_16-00-00.db",
    chemin: "C:\\tmp\\sauvegardes\\c.db",
    octets: 200_704,
  },
  purger_base: {
    copie: {
      nom: "cotisations_2026-11-10_18-00-00.db",
      chemin: "C:\\tmp\\sauvegardes\\p.db",
      octets: 200_704,
    },
    bilan: {
      paiements: 227,
      affectations: 1805,
      membres: 0,
      familles: 0,
      lignees: 0,
      grandesFamilles: 0,
      clans: 0,
    },
  },
  exporter_csv: {
    chemin: "C:\\tmp\\exports\\membres_2026-11-10_17-30-00.csv",
    lignes: 1,
  },
  tous_membres: [
    {
      id: 180,
      nom: "Akesse",
      prenom: "Comoé",
      statut: "actif",
      ordre_fratrie: null,
      parent: null,
      du: 12_000,
      paye: 3_000,
      reste: 9_000,
      arrieres: 8_000,
      chemin: "YAOCRE › YAOCRE APPIA › Akesse Comoé",
    },
  ],
  mode_demo: false,
  lancer_demo: null,
  lire_aide: ({ doc }) =>
    `<!doctype html><html><body><h1>${doc === "guide" ? "Guide du caissier" : "Encaisser en 6 gestes"}</h1></body></html>`,
  clans: [{ id: 2, nom: "YAOCRE", description: null }],
  grandes_familles: [{ id: 7, nom: "YAOCRE APPIA", clan_id: 2 }],
  lignees: [{ id: 18, nom: "YAOCRE APPIA", grande_famille_id: 7 }],
  familles: [{ id: 180, nom: "Akesse Comoé", lignee_id: 18, ordre: null, membres: 1 }],
  membres: [
    {
      id: 180,
      nom: "Akesse",
      prenom: "Comoé",
      statut: "actif",
      ordre_fratrie: null,
      parent: null,
      du: 12_000,
      paye: 3_000,
      reste: 9_000,
      arrieres: 8_000,
    },
  ],
};

const invoke = async (commande, args) => {
  appels.push({ commande, args });
  if (!(commande in reponses)) throw new Error(`commande inconnue : ${commande}`);
  const reponse = reponses[commande];
  return typeof reponse === "function" ? reponse(args) : reponse;
};

process.on("unhandledRejection", (e) => erreurs.push(e));

/* ---------------------------- exécution réelle -------------------------- */
let impressions = 0;

const contexte = {
  window: {
    __TAURI__: { core: { invoke } },
    // WebView2 expose window.print() : on le remplace par un compteur.
    print: () => {
      impressions += 1;
    },
  },
  document,
  Intl,
  console,
  setTimeout,
  clearTimeout,
};
vm.createContext(contexte);
vm.runInContext(lire("ui", "app.js"), contexte, { filename: "ui/app.js" });

const attendre = async (ms = 30) => {
  await new Promise((r) => setTimeout(r, ms));
  await new Promise((r) => setTimeout(r, 0));
};

await attendre();

/* -------------------------------- contrôles ----------------------------- */
const $ = (id) => elements.get(id);
const fcf = (n) => `${new Intl.NumberFormat("fr-FR").format(n)} F`;
const jetons = () => $("annees").children.map((c) => c.textContent);
const actif = () => $("annees").children.find((c) => c.classList.contains("actif"))?.textContent;
const dernierAppel = (commande) => appels.filter((a) => a.commande === commande).pop();

assert.equal($("voile").hidden, true, "la feuille est fermée au démarrage");
assert.equal($("liste-clans").children.length, 1, "un clan affiché");
assert.deepEqual(jetons(), ["Tous", "2026", "2025", "2024"], "quatre puces d'exercice");
assert.equal(actif(), "2026", "l'exercice courant est sélectionné par défaut");
assert.equal($("th-paye").textContent, "Payé 2026", "l'en-tête porte l'année");
assert.equal($("fil").textContent, "", "aucun fil d'Ariane avant sélection");
assert.equal($("menu-plus").hidden, true, "le menu Plus est fermé au départ");
assert.equal($("bandeau").hidden, true, "pas de bandeau de démonstration");
assert.equal($("voir-tous").hidden, false, "« Voir tous » est visible au départ");

// 1. clic sur le clan : la chaîne à enfant unique doit descendre jusqu'aux membres
$("liste-clans").children[0].click();
await attendre();

assert.ok(
  appels.some((a) => a.commande === "grandes_familles") &&
    appels.some((a) => a.commande === "lignees") &&
    appels.some((a) => a.commande === "familles"),
  "la descente automatique interroge chaque niveau",
);
assert.equal(dernierAppel("membres")?.args.exerciceId, 1, "membres interrogés sur 2026");
assert.equal($("titre-membres").textContent, "Akesse Comoé");
assert.match($("fil").textContent, /Clan · YAOCRE/);
assert.match($("fil").textContent, /GF\/Lignée · YAOCRE APPIA/);
assert.match($("fil").textContent, /Famille · Akesse Comoé/);

const ligne = $("corps-membres").children[0];
assert.equal(ligne.children[0].textContent, "Akesse");
assert.equal(ligne.children[1].textContent, "Comoé");
assert.equal(ligne.children[3].textContent, fcf(3_000), "payé");
assert.equal(ligne.children[4].textContent, fcf(9_000), "reste");
assert.equal(ligne.children[5].textContent, fcf(8_000), "arriérés");
assert.match($("compte-membres").textContent, /Exercice 2026/);

// 1 bis. export CSV : il reprend exactement la liste affichée
$("ouvrir-plus").click();
assert.equal($("menu-plus").hidden, false, "le menu Plus s'ouvre");
$("exporter-membres").click();
await attendre();
assert.equal($("menu-plus").hidden, true, "le menu se referme après l'action");

const exporte = dernierAppel("exporter_csv");
assert.ok(exporte, "l'export part au cœur");
assert.equal(exporte.args.nom, "membres");
// Les tableaux naissent dans le contexte VM : on les recopie avant de
// comparer, sinon deepStrictEqual voit deux prototypes différents.
assert.deepEqual(Array.from(exporte.args.colonnes), [
  "Nom",
  "Prénom",
  "Statut",
  "Payé 2026",
  "Reste 2026",
  "Arriérés 2026",
  "Parent",
]);
assert.deepEqual(
  Array.from(exporte.args.lignes, (ligne) => Array.from(ligne)),
  [["Akesse", "Comoé", "actif", "3000", "9000", "8000", ""]],
  "mêmes valeurs que le tableau, montants nus",
);
assert.equal($("bandeau").hidden, false, "le chemin de l'export est affiché");
assert.match($("bandeau").textContent, /membres_2026-11-10_17-30-00\.csv/);
assert.ok($("bandeau").classList.contains("succes"), "le bandeau est en mode confirmation");

// 1 ter. liste complète : toutes les familles, avec le chemin de chacun
$("exporter-tous").click();
await attendre();

assert.equal(
  dernierAppel("tous_membres")?.args.exerciceId,
  1,
  "la liste complète suit l'exercice choisi",
);
const complet = dernierAppel("exporter_csv");
assert.equal(complet.args.nom, "membres-tous");
assert.deepEqual(Array.from(complet.args.colonnes), [
  "Chemin",
  "Nom",
  "Prénom",
  "Statut",
  "Payé 2026",
  "Reste 2026",
  "Arriérés 2026",
  "Parent",
]);
assert.deepEqual(Array.from(complet.args.lignes[0]), [
  "YAOCRE › YAOCRE APPIA › Akesse Comoé",
  "Akesse",
  "Comoé",
  "actif",
  "3000",
  "9000",
  "8000",
  "",
]);

// 2. puce 2024 : l'en-tête et la requête doivent suivre
$("annees").children[3].click();
await attendre();

assert.equal(actif(), "2024");
assert.equal($("th-paye").textContent, "Payé 2024");
assert.equal($("th-arrieres").textContent, "Arriérés 2024");
assert.equal(dernierAppel("membres")?.args.exerciceId, 3, "membres interrogés sur 2024");
assert.match($("compte-membres").textContent, /Exercice 2024/);

// 3. puce « Tous » : retour au cumul, sans année dans l'en-tête
$("annees").children[0].click();
await attendre();

assert.equal(actif(), "Tous");
assert.equal($("th-paye").textContent, "Payé");
assert.equal(dernierAppel("membres")?.args.exerciceId, null, "aucun filtre d'exercice");
assert.match($("compte-membres").textContent, /Tous exercices/);

// 4. encaissement : la feuille s'ouvre au clic sur une ligne, le versement
//    part sur l'exercice courant et le reçu s'affiche.
$("corps-membres").children[0].click();
await attendre();

assert.equal($("voile").hidden, false, "la feuille de cotisation s'ouvre");
assert.equal($("feuille-titre").textContent, "Akesse Comoé");
assert.match($("feuille-perimetre").textContent, /Exercice 2026/);
assert.equal($("montant").value, "", "champ montant vide à l'ouverture");
assert.match($("date-paiement").value, /^\d{4}-\d{2}-\d{2}$/, "date préremplie");

// Le sélecteur d'année de la feuille : le versement ne dépend plus de l'année
// choisie dans le tableau.
assert.equal($("annees-feuille").children.length, 3, "une puce par exercice");
assert.equal(
  $("annees-feuille").children.find((c) => c.classList.contains("actif"))?.textContent,
  "2026",
  "l'exercice courant est proposé par défaut",
);

$("annees-feuille").children[2].click(); // 2024
await attendre();
assert.match($("feuille-perimetre").textContent, /Exercice 2024/);
assert.equal(dernierAppel("membre")?.args.exerciceId, 3, "soldes relus sur 2024");

$("annees-feuille").children[0].click(); // retour à 2026
await attendre();
assert.match($("feuille-perimetre").textContent, /Exercice 2026/);
assert.equal(dernierAppel("membre")?.args.exerciceId, 1);

// La répartition suit la frappe : mois, année et part non imputable annoncés
// avant validation.
$("montant").value = "5000";
$("montant").input();
await attendre();

const apercu = dernierAppel("previsualiser");
assert.ok(apercu, "la répartition est demandée au cœur");
assert.equal(apercu.args.montant, 5_000);
assert.equal($("repartition").hidden, false, "la répartition s'affiche");
assert.match($("repartition").textContent, /Imputé sur l'exercice 2026/);
assert.match($("repartition").textContent, /janvier 2026/);
assert.match($("repartition").textContent, /février 2026/);
assert.ok(
  $("repartition").textContent.includes(`${fcf(3_000)} ne peuvent pas être imputés`),
  "le reliquat est annoncé avant validation",
);

$("montant").value = "2000";
$("mode").value = "especes";
$("encaisser").click();
await attendre();

const versement = dernierAppel("enregistrer_paiement");
assert.ok(versement, "la commande d'écriture est appelée");
assert.equal(versement.args.membreId, 180);
assert.equal(versement.args.montant, 2_000);
assert.equal(versement.args.mode, "especes");
assert.match(versement.args.datePaiement, /^\d{4}-\d{2}-\d{2}$/);
assert.equal(
  versement.args.exerciceId,
  1,
  "en mode Tous, le paiement vise l'exercice courant",
);

assert.equal($("repartition").hidden, true, "la répartition laisse place au reçu");
assert.equal($("recu").hidden, false, "le reçu s'affiche");

// Le bouton ne doit pas rester armé sur un montant déjà encaissé : c'était la
// cause du second enregistrement refusé par un « reliquat ».
assert.equal($("encaisser").disabled, true, "bouton désarmé après enregistrement");
assert.equal($("encaisser").textContent, "Versement enregistré");
assert.equal($("montant").value, "", "le montant est vidé après enregistrement");

// Le reçu affiché porte le bon numéro, les bons mois, le bon montant.
assert.match($("recu").textContent, /RECU-2026-000001/);
assert.match($("recu").textContent, /janvier 2026/);
assert.match($("recu").textContent, /février 2026/);

// La feuille d'impression reprend le reçu à l'identique, et le bouton
// déclenche bien l'impression du WebView.
assert.match($("impression").textContent, /RECU-2026-000001/);
assert.match($("impression").textContent, /Akesse Comoé/);
assert.match($("impression").textContent, /janvier 2026/);
assert.ok(
  $("impression").textContent.includes(fcf(2_000)),
  "le montant imprimé est celui du reçu",
);

const imprimer = $("recu").children[2];
assert.equal(imprimer.textContent, "Imprimer le reçu");
imprimer.click();
assert.equal(impressions, 1, "window.print est appelé une fois");

// Une nouvelle saisie réarme le bouton et efface le reçu comme sa feuille
// d'impression : on ne doit pas pouvoir imprimer un versement déjà réglé.
$("montant").value = "1000";
$("montant").input();
await attendre();
assert.equal($("encaisser").disabled, false, "le bouton se réarme sur une saisie");
assert.equal($("encaisser").textContent, "Enregistrer le versement");
assert.equal($("recu").hidden, true, "le reçu précédent s'efface");
assert.equal($("recu").textContent, "", "le reçu précédent est vidé");
assert.equal($("impression").textContent, "", "la feuille d'impression est vidée");
assert.equal($("note").textContent, "");

// 5. fermeture
$("fermer-feuille").click();
assert.equal($("voile").hidden, true, "la feuille se ferme");

// 6. montant invalide : refus avant tout appel
$("corps-membres").children[0].click();
await attendre();
const avant = appels.length;
$("montant").value = "12.5";
$("encaisser").click();
await attendre();
assert.equal(appels.length, avant, "aucun appel pour un montant non entier");
assert.match($("note").textContent, /Montant invalide/);
$("fermer-feuille").click();

// 7. recherche globale : encaisser sans passer par les clans
$("recherche-membre").value = "akesse";
$("recherche-membre").input();
await attendre(250);

assert.equal($("resultats-membres").hidden, false, "les résultats s'affichent");
assert.equal($("resultats-membres").children.length, 1);
assert.match($("resultats-membres").textContent, /YAOCRE/);

const recherche = dernierAppel("rechercher_membres");
assert.ok(recherche, "la recherche globale interroge le cœur");
assert.equal(recherche.args.recherche, "akesse");
assert.equal(recherche.args.exerciceId, 1, "la recherche vise l'exercice courant");

$("resultats-membres").children[0].click();
await attendre();

assert.equal($("voile").hidden, false, "la feuille s'ouvre depuis la recherche");
assert.equal($("feuille-titre").textContent, "Akesse Comoé");
assert.match($("feuille-chemin").textContent, /YAOCRE/);
assert.equal($("resultats-membres").hidden, true, "la liste se referme");
assert.equal($("recherche-membre").value, "", "le champ se vide après le choix");

$("fermer-feuille").click();

// 8. fiche membre : l'historique des versements, depuis le tableau
const boutonFiche = $("corps-membres").children[0].children[7].children[0];
boutonFiche.click();
await attendre();

assert.equal($("voile-fiche").hidden, false, "la fiche s'ouvre");
assert.equal($("fiche-titre").textContent, "Akesse Comoé");
assert.match($("fiche-chemin").textContent, /Akesse Comoé/);
assert.equal(dernierAppel("paiements_membre")?.args.membreId, 180);
assert.match($("fiche-versements").textContent, /RECU-2026-000001/);
assert.match($("fiche-versements").textContent, /10\/11\/2026/);
assert.match($("fiche-versements").textContent, /janvier 2026/);
assert.match($("fiche-versements").textContent, /espèces/);
assert.ok(
  $("fiche-soldes").textContent.includes(fcf(9_000)),
  "les soldes de la fiche sont ceux du membre",
);
assert.equal(
  $("voile").hidden,
  true,
  "la fiche ne doit pas ouvrir la feuille d'encaissement",
);

// Grille des 12 mois : trois mois soldés, les suivants encore dus, et la
// date de référence transmise pour juger les échéances.
assert.equal($("fiche-grille").children.length, 12, "douze cases");
assert.equal($("fiche-grille").children[0].className, "case-mois paye");
assert.equal($("fiche-grille").children[0].children[1].textContent, "payé");
assert.equal($("fiche-grille").children[5].className, "case-mois avenir");
assert.equal(
  $("fiche-grille").children[5].children[1].textContent,
  fcf(1_000),
  "un mois à venir affiche son reste",
);
assert.equal(dernierAppel("grille_membre")?.args.membreId, 180);
assert.match(
  dernierAppel("grille_membre")?.args.dateReference,
  /^\d{4}-\d{2}-\d{2}$/,
);

// Annulation en deux temps : le premier clic arme, le second supprime.
const annuler = $("fiche-versements").children[0].children[2].children[0];
assert.equal(annuler.textContent, "Annuler");

annuler.click();
await attendre();
assert.equal(annuler.textContent, "Confirmer l'annulation");
assert.equal(
  dernierAppel("supprimer_paiement"),
  undefined,
  "aucune suppression sans confirmation",
);

annuler.click();
await attendre();
assert.equal(dernierAppel("supprimer_paiement")?.args.paiementId, 901);
assert.equal(
  dernierAppel("paiements_membre")?.args.membreId,
  180,
  "l'historique est relu après l'annulation",
);

$("fermer-fiche").click();
assert.equal($("voile-fiche").hidden, true, "la fiche se ferme");

// 8b. annuler un versement alors que la feuille est ouverte : le reçu affiché
//     ne doit pas survivre à la suppression.
$("corps-membres").children[0].click();
await attendre();
$("montant").value = "1000";
$("montant").input();
await attendre();
$("encaisser").click();
await attendre();
assert.equal($("recu").hidden, false, "un reçu est affiché avant l'annulation");

$("ouvrir-historique").click();
await attendre();
assert.equal($("voile-fiche").hidden, false, "l'historique s'ouvre depuis la feuille");

const annulerBis = $("fiche-versements").children[0].children[2].children[0];
annulerBis.click();
await attendre();
annulerBis.click();
await attendre();

assert.equal($("recu").hidden, true, "le reçu d'un versement annulé disparaît");
assert.equal($("encaisser").disabled, false, "le bouton se réarme");
assert.equal($("encaisser").textContent, "Enregistrer le versement");
assert.equal(
  $("impression").textContent,
  "",
  "la feuille d'impression ne garde pas un reçu annulé",
);

$("fermer-fiche").click();
$("fermer-feuille").click();

// 10. gestion des membres : création, puis modification et suppression.
$("nouveau-membre").click();
await attendre();

assert.equal($("voile-membre").hidden, false, "le formulaire s'ouvre");
assert.equal($("supprimer-membre").hidden, true, "rien à supprimer à la création");
assert.equal($("m-parent").children.length, 2, "les parents de la famille sont proposés");
assert.equal(
  dernierAppel("parents_candidats")?.args.familleId,
  180,
  "la famille réellement envoyée n'est jamais undefined",
);

$("m-nom").value = "Nouveau";
$("enregistrer-membre").click();
await attendre();

const creation = dernierAppel("enregistrer_membre");
assert.equal(creation?.args.fiche.nom, "Nouveau");
assert.equal(creation?.args.fiche.familleId, 180);
assert.equal(creation?.args.fiche.statut, "actif");
assert.equal(creation?.args.fiche.id, null, "aucun identifiant à la création");
assert.equal($("voile-membre").hidden, true, "le formulaire se referme");

$("corps-membres").children[0].children[7].children[0].click();
await attendre();
$("modifier-membre").click();
await attendre();

assert.equal($("voile-membre").hidden, false);
assert.equal($("m-nom").value, "Akesse");
assert.equal($("m-telephone").value, "07 00 00 00 00");
assert.equal($("m-entree").value, "2020-01-01", "la date d'entrée est relue");
assert.equal($("m-prenom").value, "Comoé");
assert.equal($("supprimer-membre").hidden, false);

$("supprimer-membre").click();
assert.equal(dernierAppel("supprimer_membre"), undefined, "suppression en deux temps");
$("supprimer-membre").click();
await attendre();

assert.equal(dernierAppel("supprimer_membre")?.args.membreId, 180);
assert.equal($("voile-membre").hidden, true);

// 11. hiérarchie : créer, renommer et supprimer un nœud.
$("ajouter-clan").click();
await attendre();

assert.equal($("voile-nom").hidden, false, "le formulaire de nom s'ouvre");
assert.equal($("nom-titre").textContent, "Nouveau clan");

$("nom-champ").value = "NOUVEAU CLAN";
$("enregistrer-nom").click();
await attendre();

const creationNoeud = dernierAppel("creer_noeud");
assert.equal(creationNoeud?.args.niveau, "clan");

const apresCreation = appels.findIndex((a) => a.commande === "creer_noeud");
assert.ok(
  appels.slice(apresCreation).some((a) => a.commande === "resume"),
  "les compteurs sont relus après une création",
);
assert.equal(creationNoeud?.args.nom, "NOUVEAU CLAN");
assert.equal(creationNoeud?.args.parentId, null, "un clan n'a pas de parent");
assert.equal($("voile-nom").hidden, true);

// Renommer la famille sélectionnée : le nom courant est prérempli.
$("renommer-famille").click();
await attendre();
assert.equal($("voile-nom").hidden, false);
assert.equal($("nom-champ").value, "Akesse Comoé");

$("nom-champ").value = "Akesse Comoé 2";
$("enregistrer-nom").click();
await attendre();

const renommage = dernierAppel("renommer_noeud");
assert.equal(renommage?.args.niveau, "famille");
assert.equal(renommage?.args.id, 180);
assert.equal(renommage?.args.nom, "Akesse Comoé 2");

// Suppression en deux temps sur le bouton de colonne.
$("supprimer-clan").click();
assert.equal(dernierAppel("supprimer_noeud"), undefined, "un clic n'efface rien");
assert.equal($("supprimer-clan").textContent, "✕ ?");

$("supprimer-clan").click();
await attendre();
assert.equal(dernierAppel("supprimer_noeud")?.args.niveau, "clan");
assert.equal(dernierAppel("supprimer_noeud")?.args.id, 2);

const indexSuppression = appels.findLastIndex((a) => a.commande === "supprimer_noeud");
assert.ok(
  appels.slice(indexSuppression + 1).some((a) => a.commande === "resume"),
  "les compteurs sont relus après une suppression",
);
assert.equal($("supprimer-clan").textContent, "✕");

// 12. tarif : le changement prend effet au mois choisi.
$("changer-tarif").click();
await attendre();

assert.equal($("voile-tarif").hidden, false, "le tarif s'ouvre");
assert.equal($("tarif-montant").value, "1000", "le tarif en vigueur est prérempli");
assert.match($("tarif-mois").value, /^\d{4}-\d{2}$/, "un mois d'effet est proposé");

$("tarif-montant").value = "1500";
$("tarif-mois").value = "2026-04";
$("appliquer-tarif").click();
await attendre();

const tarif = dernierAppel("changer_tarif");
assert.equal(tarif?.args.exerciceId, 1);
assert.equal(tarif?.args.montant, 1_500);
assert.equal(tarif?.args.dateEffet, "2026-04-01", "le mois d'effet part au premier jour");
assert.match($("tarif-note").textContent, /avril 2026/);
assert.match($("tarif-note").textContent, /8 mois/);
assert.match($("tarif-actuel").textContent, /1[\s\u202f]500 F/);
assert.equal($("appliquer-tarif").disabled, true, "le bouton est désarmé après application");
assert.equal($("appliquer-tarif").textContent, "Tarif appliqué");
assert.equal($("annuler-tarif").textContent, "Fermer", "fermer n'annonce pas une annulation");

// Une nouvelle valeur réarme le bouton.
$("tarif-montant").value = "1600";
$("tarif-montant").input();
assert.equal($("appliquer-tarif").disabled, false);
assert.equal($("appliquer-tarif").textContent, "Appliquer le tarif");

// 13. sauvegardes : liste, restauration en deux clics, copie à la demande.
$("ouvrir-sauvegarde").click();
await attendre();

assert.equal($("voile-sauvegarde").hidden, false, "l'écran des sauvegardes s'ouvre");
assert.equal($("liste-sauvegardes").children.length, 2, "deux copies listées");
assert.match(
  $("liste-sauvegardes").children[0].textContent,
  /10 novembre 2026 à 16:27/,
  "le nom de fichier devient une date lisible",
);
assert.match(
  $("liste-sauvegardes").children[0].textContent,
  /la plus récente/,
  "la copie du jour est repérée",
);


const rangee = $("liste-sauvegardes").children[1];
const restaurer = rangee.querySelectorAll(".restaurer")[0];
restaurer.click();
assert.equal(dernierAppel("restaurer_base"), undefined, "un clic n'écrase pas la base");
assert.equal(restaurer.textContent, "Confirmer");

restaurer.click();
await attendre();

assert.equal(
  dernierAppel("restaurer_base")?.args.nom,
  "cotisations_2026-11-01_09-00-00.db",
  "la copie choisie part à la restauration",
);
assert.match($("sauvegarde-note").textContent, /Base restaurée depuis/);
assert.match($("sauvegarde-note").textContent, /cotisations_2026-11-10_16-00-00\.db/);

const indexRestauration = appels.findLastIndex((a) => a.commande === "restaurer_base");
assert.ok(
  appels.slice(indexRestauration + 1).some((a) => a.commande === "exercices"),
  "les exercices sont relus après restauration",
);
assert.ok(
  appels.slice(indexRestauration + 1).some((a) => a.commande === "resume"),
  "les compteurs sont relus après restauration",
);

$("sauvegarder-base").click();
await attendre();

assert.ok(dernierAppel("sauvegarder_base"), "la copie part à la demande");
assert.match($("sauvegarde-note").textContent, /cotisations_2026-11-10_16-00-00\.db/);
assert.equal($("sauvegarder-base").disabled, false, "le bouton revient après la copie");
assert.equal($("sauvegarder-base").textContent, "Sauvegarder maintenant");

// 13 bis. purge : deux clics, copie de sécurité annoncée, données relues
$("purge-cotisations").click();
assert.equal(dernierAppel("purger_base"), undefined, "un clic n'efface rien");
assert.equal($("purge-cotisations").textContent, "Confirmer…");

$("purge-cotisations").click();
await attendre();

assert.equal(dernierAppel("purger_base")?.args.portee, "cotisations");
assert.match($("sauvegarde-note").textContent, /Effacé : 227 versements/);
assert.match($("sauvegarde-note").textContent, /cotisations_2026-11-10_18-00-00\.db/);
assert.equal($("purge-cotisations").textContent, "Effacer les cotisations");

const indexPurge = appels.findLastIndex((a) => a.commande === "purger_base");
assert.ok(
  appels.slice(indexPurge + 1).some((a) => a.commande === "resume"),
  "les compteurs sont relus après la purge",
);
assert.ok(
  appels.slice(indexPurge + 1).some((a) => a.commande === "exercices"),
  "les exercices sont relus après la purge",
);

// 13 ter. démonstration : une seconde fenêtre, la base réelle reste ouverte
$("ouvrir-demo").click();
await attendre();
assert.ok(dernierAppel("lancer_demo"), "la démonstration est lancée");
assert.match($("sauvegarde-note").textContent, /nouvelle fenêtre/);

// 13 quater. aide : les documents embarqués s'affichent dans l'application
$("ouvrir-aide").click();
assert.equal($("voile-aide").hidden, false, "l'écran d'aide s'ouvre");
assert.equal($("aide-page").hidden, true, "aucun document au départ");
$("lire-guide").click();
await attendre();
assert.equal(dernierAppel("lire_aide")?.args.doc, "guide");
assert.match($("aide-page").srcdoc, /Guide du caissier/, "le guide est rendu");
assert.equal($("aide-page").hidden, false);
assert.equal($("imprimer-aide").hidden, false, "le bouton d'impression apparaît");
assert.match($("aide-fil").textContent, /Guide d'utilisation/);

$("lire-aide-memoire").click();
await attendre();
assert.equal(dernierAppel("lire_aide")?.args.doc, "aide-memoire");
assert.match($("aide-page").srcdoc, /Encaisser en 6 gestes/);

$("fermer-aide").click();
assert.equal($("voile-aide").hidden, true, "l'écran se referme");
assert.equal($("aide-page").srcdoc, "", "le document est déchargé");
assert.equal($("imprimer-aide").hidden, true);

// 14. impression de la liste affichée : même feuille que le reçu, avec un
//     en-tête daté et une ligne de totaux.
$("ouvrir-plus").click();
$("imprimer-membres").click();
await attendre();

assert.equal(impressions, 2, "window.print est appelé pour la liste");
assert.match($("impression").textContent, /Liste des membres/);
assert.match($("impression").textContent, /Akesse/);
assert.match($("impression").textContent, /Total payé/);
assert.ok(
  $("impression").textContent.includes(fcf(3_000)),
  "le total payé est celui du tableau",
);
assert.ok(
  $("impression").textContent.includes(fcf(9_000)),
  "le reste à payer est imprimé",
);

const jour = new Date();
const attendu =
  `${String(jour.getDate()).padStart(2, "0")}/` +
  `${String(jour.getMonth() + 1).padStart(2, "0")}/${jour.getFullYear()}`;
assert.ok(
  $("impression").textContent.includes(`imprimé le ${attendu}`),
  "la date d'impression est celle du jour",
);

// 15. vue complète : toute la base dans le tableau, avec le chemin
$("voir-tous").click();
await attendre();

assert.equal(dernierAppel("tous_membres")?.args.exerciceId, 1);
assert.equal($("titre-membres").textContent, "Tous les membres");
assert.equal($("th-parent").textContent, "Chemin");
assert.equal($("fil").textContent, "Toute la base");
assert.equal($("voir-tous").hidden, false, "« Voir tous » reste visible");
assert.equal($("corps-membres").children.length, 1);
assert.equal(
  $("corps-membres").children[0].children[6].textContent,
  "YAOCRE › YAOCRE APPIA › Akesse Comoé",
  "la colonne Parent devient le chemin complet",
);
assert.match($("compte-membres").textContent, /Exercice 2026/);

// changer d'exercice en vue complète recharge la liste au lieu de la vider
$("annees").children[0].click();
await attendre();
assert.equal(dernierAppel("tous_membres")?.args.exerciceId, null, "puce Tous → null");
assert.equal($("corps-membres").children.length, 1, "la liste complète reste affichée");

// la recherche filtre toute la base, pas seulement la famille affichée
$("recherche").value = "zzz";
$("recherche").input();
await attendre(250);
assert.equal(
  $("corps-membres").children[0].children[0].textContent,
  "Aucun membre ne correspond à cette recherche.",
);

$("recherche").value = "akes";
$("recherche").input();
await attendre(250);
assert.equal($("corps-membres").children.length, 1, "la recherche retrouve le membre");

// retour au tableau familial par la colonne des clans
$("liste-clans").children[0].click();
await attendre();
assert.equal($("titre-membres").textContent, "Akesse Comoé");
assert.equal($("th-parent").textContent, "Parent");
assert.equal($("voir-tous").hidden, false, "le bouton réapparaît hors vue complète");

// 9. aucun handler n'a levé
assert.deepEqual(
  erreurs.map((e) => String(e)),
  [],
  "aucune erreur dans les handlers",
);

console.log("fumee UI : OK");
console.log(`  ${appels.length} appels Tauri simulés`);
console.log(`  puces : ${jetons().join(" · ")}`);
console.log("  scénario : clan → descendue → exercices → feuille → reçu → refus");
