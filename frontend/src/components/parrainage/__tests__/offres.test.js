/**
 * V534b — L'OFFRE DU PASS DUO EST CHOISIE PAR LE PARTICIPANT : le banc du front.
 *
 * CE QU'IL PROUVE
 *   1. création : une offre → encart sans sélecteur ; trois offres sans
 *      recommandée → bouton désactivé tant que rien n'est choisi ; recommandée
 *      présélectionnée mais modifiable ; `POST /pass` reçoit `offer_id` ;
 *   2. pass existant : « Offre actuelle » + note ; « Changer d'offre » → sheet
 *      → « Choisir cette offre » → PATCH avec `version` ; 409 `conflit_version`
 *      → UN seul rechargement de /me et le message ; 409 `pass_non_modifiable`
 *      → le `detail` du serveur ; `used` → le texte EXACT ; expiré/annulé → pas
 *      de lien ;
 *   3. invitation : bloc OFFRE, « Cette offre me convient » déplie le
 *      formulaire ; « Voir les autres offres » → PATCH public avec `version`
 *      puis le formulaire ; une seule offre → pas de « Voir les autres offres » ;
 *   4. historique « Offre modifiée : A → B » (history[] ou offer_history[]) ;
 *   5. aucun `offer_id` rendu dans le DOM (assert sur textContent) ;
 *   6. CoursesManager : cases sur les offres, payante désactivée avec la note,
 *      recommandée désélectionnable, PUT partiel, avertissement sans offre ;
 *   7. cockpit : les deux cartes de plus.
 *
 * axios est mocké : aucun réseau.
 */
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import axios from 'axios';
import PassDuoCard from '../PassDuoCard';
import InvitationDuo from '../InvitationDuo';
import CentreParrainage from '../CentreParrainage';
import CoursesManager, { offreAutorisablePassDuo, basculerOffreDuo, NOTE_OFFRE_PAYANTE, AVERT_AUCUNE_OFFRE } from '../../dashboard/CoursesManager';
import { SectionParrainage } from '../../analytics/AnalyticsCockpit';
import {
  libelleOffre, offreDuPass, offrePreselectionnee, lignesHistorique, changerOffre, messageRefusOffre, lireRefus,
  TEXTE_OFFRE_UTILISEE, TEXTE_OFFRE_CONFLIT, NOTE_OFFRE_PASS, _resetParrainagePourTest,
} from '../../../utils/parrainage';

global.IS_REACT_ACT_ENVIRONMENT = true;

jest.mock('axios', () => ({
  __esModule: true,
  default: { get: jest.fn(), post: jest.fn(), put: jest.fn(), patch: jest.fn(), delete: jest.fn() },
}));
jest.mock('qrcode.react', () => ({
  QRCodeSVG: (p) => <svg data-testid="qr-svg" data-value={p.value} />,
  QRCodeCanvas: (p) => <canvas data-testid="qr-canvas" data-value={p.value} />,
}));
jest.mock('../../../utils/spordateHandoff', () => ({
  __esModule: true, prechargerSpordate: jest.fn(), entrerDansSpordate: jest.fn(),
}));

let conteneur, racine;
beforeEach(() => {
  conteneur = document.createElement('div');
  document.body.appendChild(conteneur);
  jest.clearAllMocks();
  axios.get.mockReset(); axios.post.mockReset(); axios.patch.mockReset(); axios.put.mockReset();
  window.localStorage.clear();
  _resetParrainagePourTest();
});
afterEach(() => {
  if (racine) act(() => racine.unmount());
  racine = null;
  conteneur.remove();
});

const par = (id) => conteneur.querySelector(`[data-testid="${id}"]`);
const tous = (id) => conteneur.querySelectorAll(`[data-testid="${id}"]`);
async function monter(element) {
  await act(async () => { racine = createRoot(conteneur); racine.render(element); });
  await act(async () => { await Promise.resolve(); await Promise.resolve(); await Promise.resolve(); });
}
const attendre = () => act(async () => { await Promise.resolve(); await Promise.resolve(); await Promise.resolve(); });

// ── Données ─────────────────────────────────────────────────────────────────
const COURSE = { id: 'c1', name: 'Afroboost Dimanche', time: '18:30', locationName: 'Bord du Lac, Auvernier' };
const OCC = '2026-09-27T18:30:00';
const OFF_A = { id: 'of-aaa111', name: 'Essai découverte', benefit: '1 séance offerte', price: 0, sessions: 1, validity: '1 mois', conditions: null, recommended: false };
const OFF_B = { id: 'of-bbb222', name: 'Pack bienvenue', benefit: '2 séances offertes', price: 0, sessions: 2, validity: null, conditions: 'Réservé aux nouveaux membres', recommended: false };
const OFF_C = { id: 'of-ccc333', name: 'Séance duo', benefit: '1 séance offerte', price: 0, sessions: 1, validity: '2 semaines', conditions: null, recommended: false };
const ID_TECHNIQUES = [OFF_A.id, OFF_B.id, OFF_C.id];
const coursAvec = (offers, default_offer_id) => ({ ...COURSE, occurrences: [OCC], offers, default_offer_id: default_offer_id || null });
const CONFIG_1 = { enabled: true, courses: [coursAvec([OFF_A])] };
const CONFIG_3 = { enabled: true, courses: [coursAvec([OFF_A, OFF_B, OFF_C])] };
const CONFIG_3_RECO = { enabled: true, courses: [coursAvec([OFF_A, { ...OFF_B, recommended: true }, OFF_C], OFF_B.id)] };

function pass(status, extra) {
  return Object.assign({
    id: `p-${status}`, status, status_label: status, course: COURSE, occurrence: OCC,
    share_token: 'TOK123', invite_url: 'https://afroboost.com/duo/TOK123', whatsapp_text: 'x', invitee: null, tickets: [],
    blocked_reason: null, created_at: '2026-09-18T10:00:00Z', unlocked_at: null, expires_at: OCC,
    offer: OFF_A, offers: [OFF_A, OFF_B, OFF_C], version: 3, offer_history: [],
  }, extra || {});
}
const propsCarte = (p, extra) => ({
  config: CONFIG_3, passes: p ? [p] : [], passAffiche: p, initialeParrain: 'B', urlEspace: '/espace/AFR-1',
  onCreer: jest.fn(), onAnnuler: jest.fn(), onConfirmer: jest.fn(), onChoisir: jest.fn(), onChangerOffre: jest.fn(),
  occupe: false, erreur: '', ...(extra || {}),
});
const sansIdTechnique = (texte) => ID_TECHNIQUES.forEach((id) => expect(texte).not.toContain(id));

// ═══ 0. Helpers purs ══════════════════════════════════════════════════════════
describe('utils/parrainage — helpers V534b', () => {
  test('libelleOffre : « Offerte » si prix 0 ou absent, sinon le prix', () => {
    expect(libelleOffre({ price: 0 })).toBe('Offerte');
    expect(libelleOffre({})).toBe('Offerte');
    expect(libelleOffre({ price: 30 })).toBe('30 CHF');
    expect(libelleOffre({ price: 12.5 })).toBe('12.50 CHF');
  });
  test('offreDuPass : `offer` d\'abord, sinon `offer_snapshot` mis au format, sinon null', () => {
    expect(offreDuPass(pass('locked')).name).toBe('Essai découverte');
    const p = pass('locked', { offer: null, offer_snapshot: { id: 'x', name: 'Ancien', sessions: 2, price: 0 } });
    expect(offreDuPass(p)).toMatchObject({ name: 'Ancien', benefit: '2 séances offertes' });
    expect(offreDuPass(pass('locked', { offer: null, offer_snapshot: null }))).toBeNull();
    expect(offreDuPass(null)).toBeNull();
  });
  test('offrePreselectionnee : une seule → elle ; recommandée → elle ; plusieurs sans reco → null', () => {
    expect(offrePreselectionnee([OFF_A])).toBe(OFF_A.id);
    expect(offrePreselectionnee([OFF_A, OFF_B, OFF_C])).toBeNull();
    expect(offrePreselectionnee([OFF_A, OFF_B, OFF_C], OFF_C.id)).toBe(OFF_C.id);
    expect(offrePreselectionnee([OFF_A, { ...OFF_B, recommended: true }])).toBe(OFF_B.id);
  });
  test('lignesHistorique : history[] `offer_changed` tel quel, sinon depuis offer_history[] (récents d\'abord)', () => {
    const h = [{ at: '2026-09-18T10:00:00Z', type: 'pass_created', label: 'Pass Duo créé.' }];
    const p = pass('locked', { offer_history: [{ from_name: 'Essai découverte', to_name: 'Pack bienvenue', changed_at: '2026-09-19T10:00:00Z', changed_by: 'sponsor' }] });
    const lignes = lignesHistorique(h, [p]);
    expect(lignes[0].label).toBe('Offre modifiée : Essai découverte → Pack bienvenue');
    expect(lignes[1].label).toBe('Pass Duo créé.');
    const serveur = [{ at: '2026-09-19T10:00:00Z', type: 'offer_changed', label: 'Offre modifiée : A → B' }];
    expect(lignesHistorique(serveur, [p]).length).toBe(1);
    expect(lignesHistorique([{ at: '2026-09-19', type: 'offer_changed', from_name: 'A', to_name: 'B' }], [])[0].label).toBe('Offre modifiée : A → B');
  });
  test('changerOffre : PATCH /pass/{cible}/offer {offer_id, version} avec les en-têtes', async () => {
    axios.patch.mockResolvedValue({ data: {} });
    await changerOffre({ passId: 'p1', offerId: OFF_B.id, version: 3, headers: { 'X-Subscriber-Token': 'dev-1' } });
    expect(axios.patch).toHaveBeenCalledWith(expect.stringMatching(/\/referral\/pass\/p1\/offer$/), { offer_id: OFF_B.id, version: 3 }, expect.objectContaining({ headers: { 'X-Subscriber-Token': 'dev-1' } }));
    await changerOffre({ token: 'TOK 1', offerId: OFF_B.id, version: 2 });
    expect(axios.patch.mock.calls[1][0]).toMatch(/\/referral\/pass\/TOK%201\/offer$/);
    expect(axios.patch.mock.calls[1][2].headers).toEqual({});
  });
  test('messageRefusOffre / lireRefus : pass_non_modifiable → detail du serveur ; used sans detail → texte exact', () => {
    const r = lireRefus({ response: { status: 409, headers: { 'x-refus-raison': 'pass_non_modifiable' }, data: { detail: 'Message du serveur' } } });
    expect(r).toEqual({ status: 409, raison: 'pass_non_modifiable', detail: 'Message du serveur' });
    expect(messageRefusOffre(r)).toBe('Message du serveur');
    expect(messageRefusOffre({ status: 409, raison: 'pass_non_modifiable', detail: '' }, 'used')).toBe(TEXTE_OFFRE_UTILISEE);
    expect(messageRefusOffre({ status: 409, raison: 'pass_deja_rejoint' })).toContain('seul le parrain');
    expect(messageRefusOffre({ status: 400, raison: 'offre_payante' })).toContain('plus disponible');
  });
});

// ═══ 1. Création : le choix de l'offre ════════════════════════════════════════
describe('PassDuoCard — création : choisis ton offre', () => {
  beforeEach(() => { axios.get.mockResolvedValue({ data: { required: false } }); }); // ConditionsParticipation

  test('UNE offre → encart « OFFRE — nom / avantage / Offerte » sans sélecteur, bouton actif, offer_id envoyé', async () => {
    const onCreer = jest.fn();
    await monter(<PassDuoCard {...propsCarte(null, { config: CONFIG_1, onCreer })} />);
    expect(par('offre-selecteur')).toBeNull();
    const encart = par('offre-encart-creation');
    expect(encart.textContent).toContain('Offre');
    expect(encart.textContent).toContain('Essai découverte');
    expect(encart.textContent).toContain('1 séance offerte');
    expect(encart.textContent).toContain('Offerte');
    expect(encart.textContent).toContain('Valable 1 mois');
    expect(par('pass-creer').disabled).toBe(false);
    await act(async () => { par('pass-creer').click(); });
    expect(onCreer).toHaveBeenCalledWith('c1', OCC, false, OFF_A.id);
    sansIdTechnique(conteneur.textContent);
  });

  test('TROIS offres sans recommandée → aucune présélection, bouton désactivé tant que rien n\'est choisi', async () => {
    const onCreer = jest.fn();
    await monter(<PassDuoCard {...propsCarte(null, { config: CONFIG_3, onCreer })} />);
    const sel = par('offre-selecteur');
    expect(sel).not.toBeNull();
    expect(sel.textContent).toContain('Choisis ton offre');
    expect(sel.querySelectorAll('input[type="radio"]').length).toBe(3);
    expect(sel.querySelectorAll('input[type="radio"]:checked').length).toBe(0);
    expect(par('pass-creer').disabled).toBe(true);
    await act(async () => { par('pass-creer').click(); });
    expect(onCreer).not.toHaveBeenCalled();
    await act(async () => { par(`offre-carte-${OFF_B.id}`).querySelector('input').click(); });
    expect(par(`offre-carte-${OFF_B.id}`).getAttribute('data-choisie')).toBe('1');
    expect(par('pass-creer').disabled).toBe(false);
    await act(async () => { par('pass-creer').click(); });
    expect(onCreer).toHaveBeenCalledWith('c1', OCC, false, OFF_B.id);
    expect(sel.textContent).toContain('Réservé aux nouveaux membres');
    sansIdTechnique(conteneur.textContent);
  });

  test('recommandée → présélectionnée (badge « Recommandée ») mais modifiable', async () => {
    const onCreer = jest.fn();
    await monter(<PassDuoCard {...propsCarte(null, { config: CONFIG_3_RECO, onCreer })} />);
    expect(par(`offre-carte-${OFF_B.id}`).getAttribute('data-choisie')).toBe('1');
    expect(par(`offre-carte-${OFF_B.id}`).textContent).toContain('Recommandée');
    expect(par('pass-creer').disabled).toBe(false);
    await act(async () => { par(`offre-carte-${OFF_C.id}`).querySelector('input').click(); });
    expect(par(`offre-carte-${OFF_C.id}`).getAttribute('data-choisie')).toBe('1');
    expect(par(`offre-carte-${OFF_B.id}`).getAttribute('data-choisie')).toBe('0');
    await act(async () => { par('pass-creer').click(); });
    expect(onCreer).toHaveBeenCalledWith('c1', OCC, false, OFF_C.id);
  });

  test('Centre : la création envoie offer_id dans POST /pass ; 400 offre_* → message dédié', async () => {
    window.localStorage.setItem('afroboost_subscriber_token', 'dev-1');
    const ME = { enabled: true, sponsor: { first_name: 'Bassi' }, stats: {}, passes: [], invitations: [], history: [] };
    axios.get.mockImplementation((url) => {
      if (String(url).endsWith('/me')) return Promise.resolve({ data: ME });
      if (String(url).indexOf('/terms/') >= 0) return Promise.resolve({ data: { required: false } });
      return Promise.resolve({ data: CONFIG_1 });
    });
    axios.post.mockRejectedValueOnce({ response: { status: 400, data: { detail: 'offre_non_autorisee' } } });
    await monter(<CentreParrainage />);
    await act(async () => { par('pass-creer').click(); });
    await attendre();
    expect(axios.post).toHaveBeenCalledWith(expect.stringMatching(/\/referral\/pass$/), { course_id: 'c1', occurrence: OCC, terms_accepted: false, offer_id: OFF_A.id }, expect.anything());
    expect(par('pass-duo-card').textContent).toContain('Cette offre n’est plus disponible');
  });
});

// ═══ 2. Pass existant : offre actuelle + changer d'offre ══════════════════════
describe('PassDuoCard — pass existant : « Changer d\'offre »', () => {
  test('« Offre actuelle » + note + lien discret ; aucun offer_id dans le texte', async () => {
    await monter(<PassDuoCard {...propsCarte(pass('waiting'))} />);
    const bloc = par('offre-actuelle');
    expect(bloc.textContent).toContain('Offre actuelle');
    expect(bloc.textContent).toContain('Essai découverte');
    expect(bloc.textContent).toContain('1 séance offerte');
    expect(bloc.textContent).toContain(NOTE_OFFRE_PASS);
    expect(NOTE_OFFRE_PASS).toBe('Ton ami la reçoit à son inscription ; ta place vient de ton forfait.');
    expect(par('offre-changer')).not.toBeNull();
    expect(par('offre-sheet')).toBeNull();
    sansIdTechnique(conteneur.textContent);
  });

  test('« Changer d\'offre » → sheet (cartes, offre actuelle présélectionnée, « Choisir » inactif) → PATCH avec version → sheet fermé', async () => {
    const onChangerOffre = jest.fn().mockResolvedValue({ ok: true });
    await monter(<PassDuoCard {...propsCarte(pass('waiting'), { onChangerOffre })} />);
    await act(async () => { par('offre-changer').click(); });
    expect(par('offre-sheet')).not.toBeNull();
    expect(par('offre-selecteur').querySelectorAll('input[type="radio"]').length).toBe(3);
    expect(par(`offre-carte-${OFF_A.id}`).getAttribute('data-choisie')).toBe('1');
    expect(par(`offre-carte-${OFF_A.id}`).textContent).toContain('Offre actuelle');
    expect(par('offre-choisir').disabled).toBe(true); // même offre : rien à changer
    await act(async () => { par(`offre-carte-${OFF_B.id}`).querySelector('input').click(); });
    expect(par('offre-choisir').disabled).toBe(false);
    await act(async () => { par('offre-choisir').click(); });
    await attendre();
    expect(onChangerOffre).toHaveBeenCalledWith('p-waiting', OFF_B.id, 3);
    expect(par('offre-sheet')).toBeNull();
    sansIdTechnique(conteneur.textContent);
    const confirmSpy = jest.spyOn(window, 'confirm');
    expect(confirmSpy).not.toHaveBeenCalled();
    confirmSpy.mockRestore();
  });

  test('refus (pass_non_modifiable) → le detail du serveur dans le sheet, qui reste ouvert', async () => {
    const onChangerOffre = jest.fn().mockResolvedValue({ ok: false, message: 'Une présence est déjà validée.' });
    await monter(<PassDuoCard {...propsCarte(pass('unlocked'), { onChangerOffre })} />);
    await act(async () => { par('offre-changer').click(); });
    await act(async () => { par(`offre-carte-${OFF_C.id}`).querySelector('input').click(); });
    await act(async () => { par('offre-choisir').click(); });
    await attendre();
    expect(par('offre-sheet')).not.toBeNull();
    expect(par('offre-sheet-erreur').textContent).toBe('Une présence est déjà validée.');
  });

  test('conflit de version → le sheet se réaffiche avec le message et le NOUVEAU catalogue', async () => {
    const onChangerOffre = jest.fn().mockResolvedValue({ ok: false, conflit: true, message: TEXTE_OFFRE_CONFLIT });
    const p = pass('locked');
    const { rerender } = { rerender: null };
    await monter(<PassDuoCard {...propsCarte(p, { onChangerOffre })} />);
    await act(async () => { par('offre-changer').click(); });
    await act(async () => { par(`offre-carte-${OFF_B.id}`).querySelector('input').click(); });
    await act(async () => { par('offre-choisir').click(); });
    await attendre();
    expect(par('offre-sheet-message').textContent).toBe("L'offre a changé entre-temps, revoici les offres");
    expect(par('offre-sheet-erreur')).toBeNull();
    // Le parent a rechargé : le pass a maintenant l'offre C et la version 4
    const p2 = pass('locked', { offer: OFF_C, version: 4 });
    await act(async () => { racine.render(<PassDuoCard {...propsCarte(p2, { onChangerOffre })} />); });
    expect(par(`offre-carte-${OFF_C.id}`).textContent).toContain('Offre actuelle');
    expect(rerender).toBeNull();
  });

  test('used → le lien reste visible et affiche le texte EXACT, sans appel', async () => {
    const onChangerOffre = jest.fn();
    await monter(<PassDuoCard {...propsCarte(pass('used'), { onChangerOffre })} />);
    expect(par('offre-changer')).not.toBeNull();
    await act(async () => { par('offre-changer').click(); });
    expect(par('offre-sheet')).toBeNull();
    expect(onChangerOffre).not.toHaveBeenCalled();
    expect(par('offre-utilisee').textContent).toBe('Cette offre a déjà été utilisée. Tu peux choisir une autre offre pour une prochaine réservation si elle est disponible.');
    expect(TEXTE_OFFRE_UTILISEE).toBe('Cette offre a déjà été utilisée. Tu peux choisir une autre offre pour une prochaine réservation si elle est disponible.');
  });

  test('expired / cancelled → offre affichée, pas de lien « Changer d\'offre »', async () => {
    await monter(<PassDuoCard {...propsCarte(pass('expired'))} />);
    expect(par('offre-actuelle')).not.toBeNull();
    expect(par('offre-changer')).toBeNull();
    act(() => racine.unmount()); racine = null;
    await monter(<PassDuoCard {...propsCarte(pass('cancelled'))} />);
    expect(par('offre-changer')).toBeNull();
  });

  test('pass sans offre (serveur antérieur) → ni encart ni lien, rien ne casse', async () => {
    await monter(<PassDuoCard {...propsCarte(pass('waiting', { offer: null, offers: undefined, offer_snapshot: null }))} />);
    expect(par('offre-actuelle')).toBeNull();
    expect(par('offre-changer')).toBeNull();
    expect(par('chip-waiting')).not.toBeNull();
  });
});

// ═══ 3. Centre : PATCH réel, conflit → UN rechargement de /me ═════════════════
describe('CentreParrainage — changement d\'offre porté par le parent', () => {
  const ME = () => ({
    enabled: true, sponsor: { first_name: 'Bassi', code: 'AFR-1' }, stats: { invited: 1, joined: 0, unlocked: 0 },
    passes: [pass('waiting')], invitations: [{ id: 'inv-1', pass_id: 'p-waiting', channel: 'copy', created_at: '2026-09-18T10:00:00Z' }],
    history: [{ at: '2026-09-18T10:00:00Z', type: 'pass_created', label: 'Pass Duo créé.' }],
  });
  const monterCentre = async (me) => {
    window.localStorage.setItem('afroboost_subscriber_token', 'dev-1');
    axios.get.mockImplementation((url) => (String(url).endsWith('/me') ? Promise.resolve({ data: me || ME() }) : Promise.resolve({ data: CONFIG_3 })));
    await monter(<CentreParrainage />);
  };
  const appelsMe = () => axios.get.mock.calls.filter((c) => String(c[0]).endsWith('/me')).length;

  test('PATCH /pass/{id}/offer {offer_id, version} avec enteteParrain() ; état local depuis le PassDTO renvoyé ; /me UNE fois', async () => {
    await monterCentre();
    axios.patch.mockResolvedValueOnce({ data: pass('waiting', { offer: OFF_B, version: 4, offer_history: [{ from_name: 'Essai découverte', to_name: 'Pack bienvenue', changed_at: '2026-09-20T10:00:00Z', changed_by: 'sponsor' }] }) });
    await act(async () => { par('offre-changer').click(); });
    await act(async () => { par(`offre-carte-${OFF_B.id}`).querySelector('input').click(); });
    await act(async () => { par('offre-choisir').click(); });
    await attendre();
    expect(axios.patch).toHaveBeenCalledTimes(1);
    expect(axios.patch.mock.calls[0][0]).toMatch(/\/referral\/pass\/p-waiting\/offer$/);
    expect(axios.patch.mock.calls[0][1]).toEqual({ offer_id: OFF_B.id, version: 3 });
    expect(axios.patch.mock.calls[0][2].headers).toEqual({ 'X-Subscriber-Token': 'dev-1' });
    expect(par('offre-sheet')).toBeNull();
    expect(par('offre-actuelle').textContent).toContain('Pack bienvenue');
    expect(par('historique').textContent).toContain('Offre modifiée : Essai découverte → Pack bienvenue');
    expect(par('mes-invitations').textContent).toContain('Pack bienvenue');
    expect(appelsMe()).toBe(1);
    sansIdTechnique(conteneur.textContent);
  });

  test('409 conflit_version → /me rechargé UNE seule fois, sheet réaffiché avec le message et la nouvelle version', async () => {
    await monterCentre();
    axios.patch.mockRejectedValueOnce({ response: { status: 409, headers: { 'x-refus-raison': 'conflit_version' }, data: { detail: 'conflit_version' } } });
    const meApres = ME(); meApres.passes = [pass('waiting', { offer: OFF_C, version: 5 })];
    axios.get.mockImplementation((url) => (String(url).endsWith('/me') ? Promise.resolve({ data: meApres }) : Promise.resolve({ data: CONFIG_3 })));
    await act(async () => { par('offre-changer').click(); });
    await act(async () => { par(`offre-carte-${OFF_B.id}`).querySelector('input').click(); });
    await act(async () => { par('offre-choisir').click(); });
    await attendre(); await attendre();
    expect(appelsMe()).toBe(2); // 1 au montage + 1 rechargement, jamais plus
    expect(par('offre-sheet')).not.toBeNull();
    expect(par('offre-sheet-message').textContent).toBe(TEXTE_OFFRE_CONFLIT);
    expect(par(`offre-carte-${OFF_C.id}`).textContent).toContain('Offre actuelle');
    // Nouvelle tentative : la version rechargée (5) part cette fois
    axios.patch.mockResolvedValueOnce({ data: pass('waiting', { offer: OFF_B, version: 6 }) });
    await act(async () => { par(`offre-carte-${OFF_B.id}`).querySelector('input').click(); });
    await act(async () => { par('offre-choisir').click(); });
    await attendre();
    expect(axios.patch.mock.calls[1][1]).toEqual({ offer_id: OFF_B.id, version: 5 });
    expect(appelsMe()).toBe(2);
    expect(par('offre-sheet')).toBeNull();
  });

  test('409 pass_non_modifiable → le detail du serveur, aucun rechargement', async () => {
    await monterCentre();
    axios.patch.mockRejectedValueOnce({ response: { status: 409, headers: { 'x-refus-raison': 'pass_non_modifiable' }, data: { detail: 'Une présence est déjà validée pour ce Pass.' } } });
    await act(async () => { par('offre-changer').click(); });
    await act(async () => { par(`offre-carte-${OFF_B.id}`).querySelector('input').click(); });
    await act(async () => { par('offre-choisir').click(); });
    await attendre();
    expect(par('offre-sheet-erreur').textContent).toBe('Une présence est déjà validée pour ce Pass.');
    expect(appelsMe()).toBe(1);
  });
});

// ═══ 4. Invitation publique : bloc OFFRE ══════════════════════════════════════
describe('InvitationDuo — l\'ami choisit', () => {
  const PUB = (extra) => ({ status: 'waiting', sponsor_first_name: 'Bassi', course: COURSE, occurrence: OCC, expired: false, offer: OFF_A, offers: [OFF_A, OFF_B, OFF_C], version: 2, ...(extra || {}) });

  test('bloc OFFRE entre la séance et le formulaire ; formulaire replié ; « Cette offre me convient » le déplie', async () => {
    axios.get.mockResolvedValue({ data: PUB() });
    await monter(<InvitationDuo token="TOK123" />);
    const bloc = par('invitation-offre');
    expect(bloc.textContent).toContain('Offre');
    expect(bloc.textContent).toContain('Essai découverte');
    expect(bloc.textContent).toContain('1 séance offerte');
    expect(bloc.textContent).toContain('Offerte');
    expect(par('invitation-form')).toBeNull();
    expect(par('offre-convient')).not.toBeNull();
    expect(par('offre-voir-autres')).not.toBeNull();
    // ordre : séance, puis offre, puis (après) le formulaire
    expect(par('invitation-seance').compareDocumentPosition(bloc) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    await act(async () => { par('offre-convient').click(); });
    expect(par('invitation-form')).not.toBeNull();
    expect(par('invitation-consent').checked).toBe(false);
    expect(axios.patch).not.toHaveBeenCalled();
    sansIdTechnique(conteneur.textContent);
  });

  test('« Voir les autres offres » → sheet → PATCH public /pass/{token}/offer {offer_id, version} → puis le formulaire', async () => {
    axios.get.mockResolvedValue({ data: PUB() });
    axios.patch.mockResolvedValueOnce({ data: { offer: OFF_C, offers: [OFF_A, OFF_B, OFF_C], version: 3, status: 'waiting' } });
    await monter(<InvitationDuo token="TOK123" />);
    await act(async () => { par('offre-voir-autres').click(); });
    expect(par('offre-sheet')).not.toBeNull();
    expect(par('offre-sheet').textContent).toContain('Choisis ton offre');
    await act(async () => { par(`offre-carte-${OFF_C.id}`).querySelector('input').click(); });
    await act(async () => { par('offre-choisir').click(); });
    await attendre();
    expect(axios.patch).toHaveBeenCalledTimes(1);
    expect(axios.patch.mock.calls[0][0]).toMatch(/\/referral\/pass\/TOK123\/offer$/);
    expect(axios.patch.mock.calls[0][1]).toEqual({ offer_id: OFF_C.id, version: 2 });
    expect(axios.patch.mock.calls[0][2].headers).toEqual({}); // public : aucun en-tête d'identité
    expect(par('offre-sheet')).toBeNull();
    expect(par('invitation-offre').textContent).toContain('Séance duo');
    expect(par('invitation-form')).not.toBeNull();
    expect(axios.get).toHaveBeenCalledTimes(1); // pas de rechargement
    sansIdTechnique(conteneur.textContent);
  });

  test('conflit de version côté public → UN rechargement de GET /pass/{token}, message, sheet toujours ouvert', async () => {
    axios.get.mockResolvedValueOnce({ data: PUB() }).mockResolvedValueOnce({ data: PUB({ offer: OFF_B, version: 4 }) });
    axios.patch.mockRejectedValueOnce({ response: { status: 409, headers: { 'x-refus-raison': 'conflit_version' } } });
    await monter(<InvitationDuo token="TOK123" />);
    await act(async () => { par('offre-voir-autres').click(); });
    await act(async () => { par(`offre-carte-${OFF_C.id}`).querySelector('input').click(); });
    await act(async () => { par('offre-choisir').click(); });
    await attendre(); await attendre();
    expect(axios.get).toHaveBeenCalledTimes(2);
    expect(par('offre-sheet-message').textContent).toBe(TEXTE_OFFRE_CONFLIT);
    expect(par(`offre-carte-${OFF_B.id}`).textContent).toContain('Offre actuelle');
    expect(par('invitation-form')).toBeNull();
  });

  test('409 pass_deja_rejoint → message précis dans le sheet', async () => {
    axios.get.mockResolvedValue({ data: PUB() });
    axios.patch.mockRejectedValueOnce({ response: { status: 409, headers: { 'x-refus-raison': 'pass_deja_rejoint' } } });
    await monter(<InvitationDuo token="TOK123" />);
    await act(async () => { par('offre-voir-autres').click(); });
    await act(async () => { par(`offre-carte-${OFF_B.id}`).querySelector('input').click(); });
    await act(async () => { par('offre-choisir').click(); });
    await attendre();
    expect(par('offre-sheet-erreur').textContent).toContain('seul le parrain');
  });

  test('UNE seule offre autorisée → pas de « Voir les autres offres »', async () => {
    axios.get.mockResolvedValue({ data: PUB({ offers: [OFF_A] }) });
    await monter(<InvitationDuo token="TOK123" />);
    expect(par('offre-convient')).not.toBeNull();
    expect(par('offre-voir-autres')).toBeNull();
  });

  test('déjà rejoint → l\'offre s\'affiche sans boutons, formulaire direct (plus de changement côté ami)', async () => {
    axios.get.mockResolvedValue({ data: PUB({ status: 'friend_registered' }) });
    await monter(<InvitationDuo token="TOK123" />);
    expect(par('invitation-offre')).not.toBeNull();
    expect(par('offre-convient')).toBeNull();
    expect(par('offre-voir-autres')).toBeNull();
    expect(par('invitation-form')).not.toBeNull();
    expect(par('invitation-deja-rejoint')).not.toBeNull();
  });

  test('sans `offer` (serveur antérieur) → formulaire direct, comme V534', async () => {
    axios.get.mockResolvedValue({ data: PUB({ offer: undefined, offers: undefined, version: undefined }) });
    await monter(<InvitationDuo token="TOK123" />);
    expect(par('invitation-offre')).toBeNull();
    expect(par('invitation-form')).not.toBeNull();
  });

  test('succès après join → « Ton offre » affichée par son nom ; aucun offer_id dans le DOM', async () => {
    axios.get.mockResolvedValue({ data: PUB() });
    await monter(<InvitationDuo token="TOK123" />);
    await act(async () => { par('offre-convient').click(); });
    const saisir = (id, v) => act(async () => {
      const el = par(id);
      Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set.call(el, v);
      el.dispatchEvent(new Event('input', { bubbles: true }));
    });
    await saisir('invitation-prenom', 'Aminata'); await saisir('invitation-email', 'aminata@example.com'); await saisir('invitation-whatsapp', '0790000000');
    await act(async () => { par('invitation-consent').click(); });
    axios.post.mockResolvedValueOnce({ data: { status: 'unlocked', tickets: [], blocked_reason: null, offer: OFF_A } });
    await act(async () => { par('invitation-rejoindre').click(); });
    await attendre();
    expect(par('invitation-succes')).not.toBeNull();
    expect(par('offre-recue').textContent).toContain('Essai découverte');
    expect(axios.post.mock.calls[0][1]).not.toHaveProperty('offer_id'); // le choix est déjà parti par le PATCH
    sansIdTechnique(conteneur.textContent);
  });
});

// ═══ 5. CoursesManager : offres autorisées ═══════════════════════════════════
describe('CoursesManager — offres autorisées du Pass Duo', () => {
  const OFFRES_COACH = [
    { id: 'o-gratuite', name: 'Essai découverte', price: 0, visible: true },
    { id: 'o-payante', name: 'Cours à l’unité', price: 30, visible: true },
    { id: 'o-gratuite2', name: 'Pack bienvenue', price: '0', visible: true },
    { id: 'o-archivee', name: 'Ancienne', price: 0, archived: true },
  ];
  const monterCM = async (course) => {
    const courses = [course];
    const setCourses = jest.fn();
    const updateCourse = jest.fn();
    await monter(<CoursesManager courses={courses} setCourses={setCourses} newCourse={{}} setNewCourse={jest.fn()} updateCourse={updateCourse}
                                openAudioModal={jest.fn()} hideAudioButton lang="fr" t={(k) => k} coachEmail="c@x" offers={OFFRES_COACH} />);
    return { setCourses, updateCourse };
  };
  const COURS = { id: 'c1', name: 'Afroboost Dimanche', weekday: 0, time: '18:30', duo_enabled: true, duo_offer_ids: [], duo_default_offer_id: null, visible: true };

  test('helpers : autorisable = prix 0 et non archivée ; basculer ajoute/retire et nettoie la recommandée', () => {
    expect(offreAutorisablePassDuo(OFFRES_COACH[0])).toBe(true);
    expect(offreAutorisablePassDuo(OFFRES_COACH[1])).toBe(false);
    expect(offreAutorisablePassDuo(OFFRES_COACH[2])).toBe(true);
    expect(offreAutorisablePassDuo(OFFRES_COACH[3])).toBe(false);
    expect(basculerOffreDuo({ duo_offer_ids: [] }, 'a')).toEqual({ duo_offer_ids: ['a'], duo_default_offer_id: null });
    expect(basculerOffreDuo({ duo_offer_ids: ['a', 'b'], duo_default_offer_id: 'a' }, 'a')).toEqual({ duo_offer_ids: ['b'], duo_default_offer_id: null });
    expect(basculerOffreDuo({ duo_offer_ids: ['a'], duo_default_offer_id: 'a' }, 'b')).toEqual({ duo_offer_ids: ['a', 'b'], duo_default_offer_id: 'a' });
  });

  test('Pass Duo OFF → pas de bloc ; ON → cases, payante désactivée avec la note, archivée absente, avertissement sans offre', async () => {
    await monterCM({ ...COURS, duo_enabled: false });
    expect(par('course-duo-offres-c1')).toBeNull();
    act(() => racine.unmount()); racine = null;
    await monterCM(COURS);
    const bloc = par('course-duo-offres-c1');
    expect(bloc.textContent).toContain('Offres autorisées');
    expect(par('course-duo-offre-case-c1-o-gratuite').disabled).toBe(false);
    expect(par('course-duo-offre-case-c1-o-payante').disabled).toBe(true);
    expect(par('course-duo-offre-c1-o-payante').textContent).toContain(NOTE_OFFRE_PAYANTE);
    expect(NOTE_OFFRE_PAYANTE).toBe('Pass Duo V1 : offres offertes uniquement');
    expect(par('course-duo-offre-c1-o-archivee')).toBeNull();
    expect(par('course-duo-avert-c1').textContent).toContain(AVERT_AUCUNE_OFFRE);
    expect(AVERT_AUCUNE_OFFRE).toBe('Coche au moins une offre, sinon ce cours n’apparaîtra pas dans le Pass Duo');
    expect(tous('course-duo-offre-reco-c1-o-gratuite').length).toBe(0); // pas cochée → pas de radio
  });

  test('cocher → PUT partiel {…course, duo_offer_ids} ; cochée + recommandée → duo_default_offer_id ; recliquer désélectionne', async () => {
    const { updateCourse, setCourses } = await monterCM(COURS);
    await act(async () => { par('course-duo-offre-case-c1-o-gratuite').click(); });
    expect(updateCourse).toHaveBeenCalledWith(expect.objectContaining({ id: 'c1', duo_offer_ids: ['o-gratuite'], duo_default_offer_id: null }));
    expect(setCourses).toHaveBeenCalled();
    act(() => racine.unmount()); racine = null;
    const { updateCourse: u2 } = await monterCM({ ...COURS, duo_offer_ids: ['o-gratuite', 'o-gratuite2'] });
    expect(par('course-duo-avert-c1')).toBeNull();
    expect(par('course-duo-offre-reco-c1-o-gratuite').checked).toBe(false);
    await act(async () => { par('course-duo-offre-reco-c1-o-gratuite').click(); });
    expect(u2).toHaveBeenLastCalledWith(expect.objectContaining({ duo_offer_ids: ['o-gratuite', 'o-gratuite2'], duo_default_offer_id: 'o-gratuite' }));
    act(() => racine.unmount()); racine = null;
    const { updateCourse: u3 } = await monterCM({ ...COURS, duo_offer_ids: ['o-gratuite', 'o-gratuite2'], duo_default_offer_id: 'o-gratuite' });
    expect(par('course-duo-offre-reco-c1-o-gratuite').checked).toBe(true);
    await act(async () => { par('course-duo-offre-reco-c1-o-gratuite').click(); });
    expect(u3).toHaveBeenLastCalledWith(expect.objectContaining({ duo_default_offer_id: null }));
    await act(async () => { par('course-duo-offre-case-c1-o-gratuite').click(); });
    expect(u3).toHaveBeenLastCalledWith(expect.objectContaining({ duo_offer_ids: ['o-gratuite2'], duo_default_offer_id: null }));
  });
});

// ═══ 6. Cockpit : deux cartes de plus ════════════════════════════════════════
describe('AnalyticsCockpit — KPI offre', () => {
  test('« Changements d\'offre » et « Offre la plus choisie » (par son nom, jamais son id)', async () => {
    axios.get.mockResolvedValue({ data: { kpi: { passes_crees: 3, changements_offre: 4, offre_la_plus_choisie: { offer_id: 'of-zzz999', name: 'Essai découverte', n: 2 } }, par_canal: {} } });
    await monter(<SectionParrainage periode="mois" du="" au="" coachId="" courseId="" />);
    expect(par('kpi-parrainage-changements-offre').textContent).toContain('4');
    expect(par('kpi-parrainage-changements-offre').textContent).toContain("Changements d'offre");
    expect(par('kpi-parrainage-offre-choisie').textContent).toContain('2');
    expect(par('kpi-parrainage-offre-choisie').textContent).toContain('Essai découverte');
    expect(conteneur.textContent).not.toContain('of-zzz999');
    expect(axios.get).toHaveBeenCalledTimes(1);
  });
  test('sans KPI offre → « — » et « Aucune encore », rien ne casse', async () => {
    axios.get.mockResolvedValue({ data: { kpi: { passes_crees: 0 }, par_canal: {} } });
    await monter(<SectionParrainage periode="mois" du="" au="" coachId="" courseId="" />);
    expect(par('kpi-parrainage-changements-offre').textContent).toContain('—');
    expect(par('kpi-parrainage-offre-choisie').textContent).toContain('Aucune encore');
  });
});
