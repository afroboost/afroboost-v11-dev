// V546 — LE LIEN PRIVÉ D'UNE OFFRE (`/?offre=<id>`) DANS LE NAVIGATEUR DU COACH.
//
// CE QUI A ÉTÉ MESURÉ EN PRODUCTION LE 23/09/2026
// ===========================================================================
// Offre réelle « Membres — 8 mois » (`ba530ae4-934c-46b1-8bc5-4999448f1e86`,
// `link_only: true`) :
//
//   GET /api/offers                       -> 10 offres, 0 privée
//   GET /api/offers?offre=ba530ae4-...    -> 11 offres, la privée incluse
//       => le SERVEUR est sain, le contrat V537 tient.
//
//   https://afroboost.com/?visitor=true&offre=ba530ae4-...   (session anonyme)
//       -> { fiche: true, nom: "Membres — 8 mois ", cta: true }
//       -> clic sur le CTA : l'étape V535 « mode de paiement » s'ouvre
//          (399,98 CHF / 2 × 199,99 CHF) => la chaîne complète est saine.
//
//   https://afroboost.com/?offre=ba530ae4-...                (session coach)
//       -> { dashboard: true, fiche: false, aimants: false, controleur: false }
//       => LA VITRINE N'EST JAMAIS MONTÉE.
//
// POURQUOI. `if (coachMode && !isVisitorMode)` rend `CoachDashboard` et SORT.
// Les deux lecteurs du lien profond (l'effet de `OffresAimants` et celui de
// `OffersSliderAutoPlay`) vivent dans la vitrine : non montée, personne ne lit
// `?offre=`. Or le bouton « Copier le lien privé » est DANS le tableau de bord
// (`OfferCard.js`) : la première personne à ouvrir ce lien est toujours celle
// qui vient de le copier.
//
// CE FICHIER teste la LOGIQUE, sur le source livré — même convention que
// `deepLinkOffre.test.js`. Le comportement réel est mesuré en navigateur.

import fs from 'fs';
import path from 'path';

const APP = fs.readFileSync(path.join(__dirname, '..', '..', 'App.js'), 'utf8');

/** Le CODE seul : commentaires de ligne et de bloc retirés — sinon ce fichier
 *  se piégerait lui-même, les commentaires du correctif citant ses propres
 *  expressions pour les EXPLIQUER. */
const code = (() => {
  const sans = APP.replace(/\/\*[\s\S]*?\*\//g, '');
  return sans.split('\n').filter((l) => !l.trim().startsWith('//')).join('\n');
})();

describe('V546 — le lien privé rouvre la vitrine pour le propriétaire', () => {
  test('la présence de `?offre=` dans l’URL est lue par le helper V537 existant', () => {
    // Aucun nouveau lecteur d'URL : on réutilise `v537ParamOffreDuLien`, qui
    // valide déjà la forme de l'identifiant (6 à 64 caractères, sans `/`).
    expect(code).toContain("const v546LienOffreDansUrl = !!((v537ParamOffreDuLien().params || {}).offre);");
  });

  test('un lien profond d’offre vaut « Vue Visiteur » — et rien de neuf n’est inventé', () => {
    expect(code).toMatch(
      /const isVisitorMode = urlParams\.get\('visitor'\) === 'true' \|\| isSuperAdminSlugInUrl\s*\n?\s*\|\| \(coachMode && v546LienOffreDansUrl\);/);
  });

  test('la condition est BORNÉE à `coachMode` — un visiteur anonyme n’est pas touché', () => {
    // Sans cette borne, « Retour au dashboard » (rendu sous `isVisitorMode`)
    // surgirait chez n'importe quel visiteur ouvrant un lien d'offre.
    const ligne = code.split('\n').find((l) => l.includes('coachMode && v546LienOffreDansUrl'));
    expect(ligne).toBeTruthy();
    expect(ligne).toContain('coachMode &&');
  });

  test('la sortie vers CoachDashboard est CONSERVÉE — on cesse seulement de la déclencher', () => {
    expect(code).toContain('if (coachMode && !isVisitorMode) {');
    expect(code).toContain('return <CoachDashboard');
  });
});

describe('V546 — la garde « offre privée » reste entière', () => {
  test('l’identifiant du lien part toujours au serveur, qui seul rouvre l’offre', () => {
    expect(code).toContain('axios.get(`${API}/offers`, v537ParamOffreDuLien())');
  });

  test('la forme de l’identifiant reste validée — aucune énumération possible', () => {
    expect(code).toMatch(/\/\^\[A-Za-z0-9-\]\{6,64\}\$\/\.test\(id\)/);
  });

  test('la page d’accueil ne décide JAMAIS elle-même qu’une offre est privée', () => {
    // `link_only` n'est lu nulle part dans App.js : le catalogue public est
    // celui que le serveur a servi, ni plus ni moins. Le jour où un filtre
    // `link_only` apparaîtrait ici, il masquerait l'offre que le lien vient
    // précisément d'ouvrir.
    expect(code).not.toContain('link_only');
  });

  test('le lien seul n’ouvre toujours aucun paiement', () => {
    expect(code).toMatch(/if \(v449Reserver && typeof onSelectOffer === 'function'\)/);
  });
});
