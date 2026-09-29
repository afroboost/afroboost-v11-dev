/**
 * CO-1 — Contacts et Campagnes rouverts aux coachs partenaires.
 *
 * CoachDashboard.js (9 000+ lignes) et CampaignModal.js ne se montent pas ici :
 * le banc prouve la RÈGLE pure (utils/co1OngletsCoach.js) et, sur la SOURCE,
 * que le tableau de bord l'applique partout où l'onglet est décidé, que les
 * réglages plateforme (ai-config, ai-logs, numéro WhatsApp officiel) ne sont
 * plus touchés par un partenaire, et que le super-admin garde son comportement.
 * Les gardes serveur sont prouvées par tests/test_co1_onglets_coach.py.
 */
const fs = require('fs');
const path = require('path');
const {
  ongletsAutorises, ongletValide, canalCampagneAutorise, ONGLET_PAR_DEFAUT,
} = require('../../utils/co1OngletsCoach');

const RACINE = path.join(__dirname, '..', '..', '..', '..');
const lire = (p) => fs.readFileSync(path.join(RACINE, p), 'utf8');

function sansCommentaires(src) {
  return src
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/\{\/\*[\s\S]*?\*\/\}/g, '')
    .replace(/(^|[^:])\/\/.*$/gm, '$1');
}

const DASH = sansCommentaires(lire('frontend/src/components/CoachDashboard.js'));
const MODAL = sansCommentaires(lire('frontend/src/components/coach/CampaignModal.js'));
const CRM = sansCommentaires(lire('frontend/src/components/coach/CRMSection.js'));

// Corps d'une fonction fléchée `const nom = async (...) => { ... }` (accolades équilibrées).
function corps(src, debut) {
  const i = src.indexOf(debut);
  if (i < 0) return '';
  const j = src.indexOf('{', src.indexOf('=>', i));
  let n = 0;
  for (let k = j; k < src.length; k += 1) {
    if (src[k] === '{') n += 1;
    else if (src[k] === '}') { n -= 1; if (n === 0) return src.slice(i, k + 1); }
  }
  return '';
}

describe('règle pure des onglets', () => {
  test('partenaire : Contacts et Campagnes présents, plus Boutique et Stripe', () => {
    const p = ongletsAutorises(false);
    ['contacts', 'campaigns', 'reservations', 'boutique', 'stripe'].forEach((o) => expect(p).toContain(o));
  });

  test('super-admin : inchangé (pas de Boutique ni de Stripe partenaire)', () => {
    const a = ongletsAutorises(true);
    expect(a).toEqual(['reservations', 'offers', 'codes', 'contacts', 'campaigns',
      'prospection', 'conversations', 'corbeille']);
  });

  test('onglet restauré hors liste -> repli sur Réservations', () => {
    expect(ongletValide('boutique', true)).toBe(ONGLET_PAR_DEFAUT);
    expect(ongletValide('inexistant', false)).toBe('reservations');
    expect(ongletValide('', false)).toBe('reservations');
    expect(ongletValide(null, true)).toBe('reservations');
    expect(ongletValide('campaigns', false)).toBe('campaigns');
    expect(ongletValide('contacts', false)).toBe('contacts');
    expect(ongletValide('concept', false)).toBe('offers'); // migration v36 conservée
  });

  test('WhatsApp (numéro officiel) jamais proposé au partenaire', () => {
    expect(canalCampagneAutorise('whatsapp', false)).toBe(false);
    expect(canalCampagneAutorise('email', false)).toBe(true);
    expect(canalCampagneAutorise('internal', false)).toBe(true);
    expect(canalCampagneAutorise('whatsapp', true)).toBe(true);
  });
});

describe('CoachDashboard applique la règle', () => {
  test('plus aucun filtre qui retire Contacts/Campagnes au partenaire', () => {
    expect(DASH).not.toMatch(/ADMIN_ONLY_TAB_IDS/);
    expect(DASH).not.toMatch(/ADMIN_ONLY_TABS/);
    expect(DASH).not.toMatch(/isPartnerOnly/);
  });

  test('la barre d\'onglets est dérivée de la liste autorisée', () => {
    expect(DASH).toMatch(/import \{[^}]*ongletsAutorises[^}]*\} from "\.\.\/utils\/co1OngletsCoach"/);
    expect(DASH).toMatch(/\.filter\(t => co1Ids\.includes\(t\.id\)\)/);
  });

  test('restauration localStorage validée + garde de rendu', () => {
    expect(DASH).toMatch(/ongletValide\(localStorage\.getItem\(COACH_TAB_KEY\), isSuperAdmin\)/);
    expect(DASH).toMatch(/const tab = ongletValide\(tabBrut, isSuperAdmin\)/);
  });

  test('partenaire sans crédits : CampaignManager rendu (bandeau), jamais CreditsGate pleine page', () => {
    expect(DASH).not.toMatch(/testId="credits-lock-campaigns"/);
    expect(DASH).not.toMatch(/tab === "campaigns" && !hasCreditsFor\('campaign'\)/);
    expect(DASH).toMatch(/tab === "campaigns" && \(/);
    expect(DASH).toMatch(/hasInsufficientCredits=\{hasInsufficientCredits \|\| !hasCreditsFor\('campaign'\)\}/);
    // Conversations garde son verrou (hors périmètre).
    expect(DASH).toMatch(/testId="credits-lock-conversations"/);
  });

  test('partenaire : aucun GET /ai-config, GET /ai-logs, PUT /ai-config', () => {
    const effet = DASH.slice(DASH.indexOf('if (tab === "campaigns") {\n      loadCampaigns'));
    expect(effet.slice(0, 400)).toMatch(/if \(isSuperAdmin\) \{\s*loadAIConfig\(\);\s*loadAILogs\(\);\s*\}/);
    const auto = DASH.slice(DASH.indexOf('const isAiConfigLoaded'), DASH.indexOf('}, [aiConfig'));
    expect(auto).toMatch(/if \(!isSuperAdmin\) return;/);
    expect(DASH).toMatch(/if \(newCampaign\.mediaUrl && isSuperAdmin\)/);
    expect(corps(DASH, 'const loadAIConfig')).toMatch(/if \(!isSuperAdmin\) return;/);
    expect(corps(DASH, 'const loadAILogs')).toMatch(/if \(!isSuperAdmin\) return;/);
    expect(corps(DASH, 'const handleClearAILogs')).toMatch(/if \(!isSuperAdmin\) return;/);
  });

  test('super-admin : chargement IA et auto-sauvegarde conservés', () => {
    expect(DASH).toMatch(/await axios\.put\(`\$\{API\}\/ai-config`, aiConfig\)/);
    expect(DASH).toMatch(/axios\.get\(`\$\{API\}\/ai-config`\)/);
    expect(DASH).toMatch(/axios\.get\(`\$\{API\}\/ai-logs`\)/);
  });

  test('GET /users : la réponse cloisonnée par le serveur n\'est plus jetée', () => {
    expect(DASH).toMatch(/appliquer\('Utilisateurs', usr, \(r\) => setUsers\(r\.data\)\)/);
    expect(DASH).not.toMatch(/setUsers\(isSuperAdmin \? r\.data : \[\]\)/);
  });

  test('Campagnes : un refus de session est dit (SectionErreur), jamais une liste vide muette', () => {
    expect(DASH).toMatch(/import \{ SectionErreur \} from "\.\/ui\/EtatChargement"/);
    expect(DASH).toMatch(/setCo1CampagnesMotif\(classerEchec\(err\)\)/);
    expect(DASH).toMatch(/<SectionErreur motif=\{co1CampagnesMotif\}/);
  });
});

describe('CampaignModal : numéro officiel jamais proposé au partenaire', () => {
  test('le canal WhatsApp est filtré par la règle', () => {
    expect(MODAL).toMatch(/\.filter\(ch => canalCampagneAutorise\(ch\.key, isSuperAdmin\)\)/);
  });

  test('le sélecteur d\'expéditeur (numéro Afroboost) n\'existe que pour le super-admin', () => {
    expect(MODAL).toMatch(/\{isSuperAdmin && newCampaign\.channels\?\.whatsapp && \(/);
  });

  test('un canal WhatsApp hérité (édition) est retiré sans boucle', () => {
    expect(MODAL).toMatch(/if \(isSuperAdmin \|\| !waActif\) return;/);
    expect(MODAL).toMatch(/prev\.channels\?\.whatsapp \? \{ \.\.\.prev, channels: \{ \.\.\.prev\.channels, whatsapp: false \} \} : prev/);
  });

  test('le partenaire voit pourquoi', () => {
    expect(MODAL).toMatch(/\{!isSuperAdmin && \(/);
    expect(MODAL).toMatch(/MESSAGE_WHATSAPP_PARTENAIRE/);
  });
});

describe('CRMSection : le prompt IA global n\'est plus proposé au partenaire', () => {
  test('SystemPromptBlock réservé au super-admin', () => {
    expect(CRM).toMatch(/\{isSuperAdmin && <SystemPromptBlock /);
  });
});
