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
    { id: 1, libelle: "Campagne 2026", date_debut: "2026-01-01", date_fin: "2026-12-31", annee: 2026, statut: "ouverte", courant: true },
    { id: 2, libelle: "Campagne 2025", date_debut: "2025-01-01", date_fin: "2025-12-31", annee: 2025, statut: "fermee", courant: false },
    { id: 3, libelle: "Campagne 2024", date_debut: "2024-01-01", date_fin: "2024-12-31", annee: 2024, statut: "fermee", courant: false },
  ],
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
  return reponses[commande];
};

process.on("unhandledRejection", (e) => erreurs.push(e));

/* ---------------------------- exécution réelle -------------------------- */
const contexte = {
  window: { __TAURI__: { core: { invoke } } },
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

// Une nouvelle saisie le réarme explicitement.
$("montant").value = "1000";
$("montant").input();
await attendre();
assert.equal($("encaisser").disabled, false, "le bouton se réarme sur une saisie");
assert.equal($("encaisser").textContent, "Enregistrer le versement");
assert.equal($("recu").hidden, true, "le reçu précédent s'efface");
assert.match($("recu").textContent, /RECU-2026-000001/);
assert.match($("recu").textContent, /janvier 2026/);
assert.match($("recu").textContent, /février 2026/);
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

// 8. aucun handler n'a levé
assert.deepEqual(
  erreurs.map((e) => String(e)),
  [],
  "aucune erreur dans les handlers",
);

console.log("fumee UI : OK");
console.log(`  ${appels.length} appels Tauri simulés`);
console.log(`  puces : ${jetons().join(" · ")}`);
console.log("  scénario : clan → descendue → exercices → feuille → reçu → refus");
