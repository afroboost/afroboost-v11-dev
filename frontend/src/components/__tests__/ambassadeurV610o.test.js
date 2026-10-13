/**
 * V610o — PROGRAMME AMBASSADEUR (écrans) : messages membre / non membre, « Partager et
 * inviter », « Ton impact Afroboost », section coach « Ambassadeurs », page de l'ami.
 * axios et fetch sont mockés : aucun réseau, aucune donnée réelle.
 */
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';

jest.mock('axios', () => ({ get: jest.fn(), post: jest.fn(), put: jest.fn(), create: jest.fn(), interceptors: { request: { use: jest.fn() }, response: { use: jest.fn() } } }));
// eslint-disable-next-line import/first
import axios from 'axios';
// eslint-disable-next-line import/first
import { texteAmbassadeur, titreLisible, villeDuLieu } from '../../utils/invitationCampagne';
// eslint-disable-next-line import/first
import PartagerInviter from '../PartagerInviter';
// eslint-disable-next-line import/first
import ImpactAfroboost, { nouveautes } from '../ImpactAfroboost';
// eslint-disable-next-line import/first
import InviterMesAmis from '../InviterMesAmis';
// eslint-disable-next-line import/first
import MonImpactAfroboost from '../MonImpactAfroboost';
// eslint-disable-next-line import/first
import AmbassadeursCoach, { actionsRecompense } from '../coach/AmbassadeursCoach';
// eslint-disable-next-line import/first
import InvitationPublique from '../InvitationPublique';

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
jest.setTimeout(15000);
let conteneur = null; let racine = null;
function rendre(el) { conteneur = document.createElement('div'); document.body.appendChild(conteneur); racine = createRoot(conteneur); racine.render(el); }
beforeEach(() => {
  jest.spyOn(window.HTMLMediaElement.prototype, 'play').mockImplementation(() => Promise.resolve());
  jest.spyOn(window.HTMLMediaElement.prototype, 'pause').mockImplementation(() => {});
});
afterEach(() => {
  if (racine) act(() => racine.unmount());
  if (conteneur) conteneur.remove();
  racine = null; conteneur = null;
  delete global.fetch; window.localStorage.clear();
  jest.restoreAllMocks(); jest.clearAllMocks();
});
const q = (id) => document.querySelector(`[data-testid="${id}"]`);
async function attendre(fn) { let e; for (let i = 0; i < 200; i += 1) { try { fn(); return; } catch (x) { e = x; } await act(async () => { await new Promise((r) => setTimeout(r, 20)); }); } throw e; }
const json = (corps, ok = true, status = 200) => Promise.resolve({ ok, status, json: () => Promise.resolve(corps) });

const SILENT = {
  type: 'event_paid', title: 'AFROBOOST SILENT — ÉDITION SPÉCIALE', date_label: 'mercredi 28 octobre', time_label: '18:45',
  lieu: 'Chemin des Valangines 97, 2000 Neuchâtel', inviter_display: { prenom: 'Bassi' }, gratuit_membres: true,
  audio_partage_url: '/api/files/a1/afro.mp3', reservation_directe: { offer_id: 'OFF-1' },
  prix_actif: { prix: 25, palier: 'early_bird', libelle: 'Prévente', prochain: { palier: 'standard', prix: 30, a_partir_de: '2026-10-21T16:45:00+00:00' } },
  share_url: 'https://afroboost.com/i/JetonBassi1234567890',
};
const IMPACT = (boosts, extra) => Object.assign({
  progression: { boosts, debloques: boosts >= 3 ? ['pass_ami'] : [], vip: boosts >= 10,
    prochain: boosts < 3 ? { cle: 'pass_ami', seuil: 3, libelle: 'Pass Ami', restant: 3 - boosts }
      : boosts < 5 ? { cle: 'recompense', seuil: 5, libelle: 'Récompense Afroboost', restant: 5 - boosts }
        : boosts < 10 ? { cle: 'vip', seuil: 10, libelle: 'Ambassadeur VIP', restant: 10 - boosts } : null },
  amis: boosts, recents: [], recompenses: [], message_places: '50 PLACES',
}, extra || {});

describe('V610o — messages de l’Afroboosteur', () => {
  test('17 — MEMBRE : « Ma place est offerte » = la SIENNE ; 50 PLACES ; jamais l’ami gratuit', () => {
    const t = texteAmbassadeur(SILENT, { nature: 'membre', messagePlaces: '50 PLACES' });
    expect(t).toBe([
      '🔥 Je vais à Afroboost Silent !', '',
      'Ma place est offerte grâce à mon abonnement Afroboost et j’aimerais que tu viennes vivre l’expérience avec moi 🎧💜', '',
      '📅 Mercredi 28 octobre · 18h45', '📍 Neuchâtel', '', '🔥 50 PLACES', '', 'Plus tu réserves tôt, moins c’est cher.', '',
      'Viens vivre l’expérience avec moi 👇', 'https://afroboost.com/i/JetonBassi1234567890'].join('\n'));
    expect(t).not.toMatch(/gratuit pour toi|offerte pour toi|ta place est offerte/i);
  });
  test('18 — NON MEMBRE (billet payé)', () => {
    const t = texteAmbassadeur(SILENT, { nature: 'stripe', messagePlaces: '50 PLACES' });
    expect(t).toBe([
      '🔥 Je deviens Afroboosteur !', '', 'Je vais à Afroboost Silent — Édition Spéciale 🎧', '',
      '📅 Mercredi 28 octobre · 18h45', '📍 Neuchâtel', '', '🔥 50 PLACES', '', 'Plus tu réserves tôt, moins c’est cher.', '',
      'Viens vivre l’expérience avec moi 💜👇', 'https://afroboost.com/i/JetonBassi1234567890'].join('\n'));
  });
  test('« plus tu réserves tôt » seulement si un palier plus cher suit ; message 50 PLACES configurable (vide = absent)', () => {
    const t = texteAmbassadeur({ ...SILENT, prix_actif: { prix: 40, palier: 'last_minute' } }, { nature: 'stripe', messagePlaces: '' });
    expect(t).not.toMatch(/Plus tu réserves tôt/);
    expect(t).not.toMatch(/PLACES/);
  });
  test('titre et ville lisibles', () => {
    expect(titreLisible('AFROBOOST SILENT — ÉDITION SPÉCIALE')).toBe('Afroboost Silent — Édition Spéciale');
    expect(titreLisible('Soirée Festival')).toBe('Soirée Festival');
    expect(villeDuLieu('Chemin des Valangines 97, 2000 Neuchâtel')).toBe('Neuchâtel');
    expect(villeDuLieu('Salle A')).toBe('Salle A');
  });
});

describe('V610o — « Partager et inviter »', () => {
  test('16 — un bouton, puis WhatsApp (en premier), SMS, Copier, Autrement ; suivi seulement à l’ouverture d’un canal', async () => {
    global.fetch = jest.fn(() => json({}));
    const ouvrir = jest.spyOn(window, 'open').mockImplementation(() => null);
    await act(async () => { rendre(<PartagerInviter jeton="JetonBassi1234567890" lien={SILENT.share_url} texte="MSG" />); });
    expect(q('partager-canaux')).toBeNull();
    await act(async () => { q('inviter-partager').click(); });
    expect(global.fetch).not.toHaveBeenCalled();                    // ouvrir la liste ne compte rien
    const canaux = [...q('partager-canaux').querySelectorAll('button')].map((b) => b.dataset.testid);
    expect(canaux).toEqual(['inviter-whatsapp', 'inviter-sms', 'inviter-copier', 'inviter-autrement']);
    await act(async () => { q('inviter-whatsapp').click(); });
    expect(String(ouvrir.mock.calls[0][0])).toBe('https://wa.me/?text=MSG');
    expect(JSON.parse(global.fetch.mock.calls[0][1].body).evenement).toBe('partage_whatsapp_declenche');
    expect(document.body.textContent).not.toMatch(/envoy[ée]/i);
  });
});

describe('V610o — « Ton impact Afroboost »', () => {
  test('8 — 2 / 3 Boosts, « Encore 1 ami pour débloquer : Pass Ami », 2 amis, bouton Partager', async () => {
    const partager = jest.fn();
    await act(async () => { rendre(<ImpactAfroboost impact={IMPACT(2)} onPartager={partager} />); });
    expect(q('impact-compteur').textContent).toContain('2 / 3 Boosts');
    expect(q('impact-prochain').textContent).toContain('Encore 1 ami pour débloquer');
    expect(q('impact-prochain').textContent).toContain('Pass Ami');
    expect(q('impact-amis').textContent).toBe('2 amis ont rejoint grâce à toi');
    await act(async () => { q('impact-partager').click(); });
    expect(partager).toHaveBeenCalled();
  });
  test('9 — cumul : 3 / 5 -> Récompense ; 5 / 10 -> VIP ; 10 -> VIP, plus de palier suivant', async () => {
    await act(async () => { rendre(<ImpactAfroboost impact={IMPACT(3)} />); });
    expect(q('impact-compteur').textContent).toContain('3 / 5 Boosts');
    act(() => racine.unmount()); conteneur.remove();
    await act(async () => { rendre(<ImpactAfroboost impact={IMPACT(5)} />); });
    expect(q('impact-compteur').textContent).toContain('5 / 10 Boosts');
    act(() => racine.unmount()); conteneur.remove();
    await act(async () => { rendre(<ImpactAfroboost impact={IMPACT(10)} />); });
    expect(q('impact-compteur').textContent).toContain('10 Boosts');
    expect(q('impact-vip')).toBeTruthy();
    expect(q('impact-prochain')).toBeNull();
  });
  test('24/25 — « +1 Boost ! » et palier débloqué : affichés UNE fois (mémoire locale)', async () => {
    const imp = IMPACT(3, { recents: [{ id: 'boost:r1', prenom: 'Sophie', at: '2026-10-13T10:00:00' }],
      recompenses: [{ palier: 'pass_ami', libelle: 'Pass Ami', etat: 'disponible', etat_libelle: 'Disponible' }] });
    await act(async () => { rendre(<ImpactAfroboost impact={imp} />); });
    expect(q('impact-plus-un').textContent).toContain('+1 Boost !');
    expect(q('impact-plus-un').textContent).toContain('Sophie vient de rejoindre Afroboost grâce à ton invitation.');
    expect(q('impact-palier-pass_ami').textContent).toContain('Ton Pass Ami est débloqué !');
    expect(nouveautes(imp, JSON.parse(window.localStorage.getItem('af_boost_vu')))).toEqual({ boosts: [], paliers: [] });
    act(() => racine.unmount()); conteneur.remove();
    await act(async () => { rendre(<ImpactAfroboost impact={imp} />); });
    expect(q('impact-plus-un')).toBeNull();
  });
  test('15 — confirmation Stripe : l’impact de l’ACHETEUR via la session payée (0 / 3), jamais via le lien public', async () => {
    global.fetch = jest.fn((url) => {
      const u = String(url);
      if (u.includes('/api/ambassadeur/impact/session/cs_test_ABC123456')) return json(IMPACT(0));
      if (u.includes('/api/invitation/publique/')) return json(SILENT);
      return json({});
    });
    const relais = { jeton: 'JetonSophie1234567890', share_url: 'https://afroboost.com/i/JetonSophie1234567890', nature: 'stripe' };
    await act(async () => { rendre(<InviterMesAmis relaisInitial={relais} impactCs="cs_test_ABC123456" />); });
    await attendre(() => expect(q('impact-afroboost-confirmation')).toBeTruthy());
    expect(q('impact-compteur').textContent).toContain('0 / 3 Boosts');
    expect(global.fetch.mock.calls.some((c) => /mon-impact/.test(String(c[0])))).toBe(false);
  });
  test('espace : rien sans participation ; sinon le bloc + « Partager et inviter » ouvre SON lien', async () => {
    global.fetch = jest.fn((url, opts) => {
      const u = String(url);
      if (u.includes('/api/ambassadeur/mon-impact')) return json(IMPACT(2, { ambassadeur: true, lien: { jeton: 'JetonMia12345678901234', share_url: 'https://afroboost.com/i/JetonMia12345678901234', nature: 'membre' } }));
      if (u.includes('/api/invitation/publique/')) return json(SILENT);
      return json({});
    });
    await act(async () => { rendre(<MonImpactAfroboost accessCode="AFR-M1" jetonEspace="tok" slug="" />); });
    await attendre(() => expect(q('mon-impact')).toBeTruthy());
    const [, opts] = global.fetch.mock.calls[0];
    expect(opts.headers['x-espace-token']).toBe('tok');
    await act(async () => { q('impact-partager').click(); });
    await attendre(() => expect(q('inviter-lien').textContent).toContain('JetonMia12345678901234'));
    act(() => racine.unmount()); conteneur.remove();
    global.fetch = jest.fn(() => json({ ambassadeur: false }));
    await act(async () => { rendre(<MonImpactAfroboost accessCode="AFR-M1" jetonEspace="tok" slug="" />); });
    await act(async () => { await new Promise((r) => setTimeout(r, 30)); });
    expect(q('mon-impact')).toBeNull();
  });
});

describe('V610o — coach : Ambassadeurs', () => {
  const LISTE = { total: 1, paliers: [], ambassadeurs: [{ id: 'abc123def456abc123def456', prenom: 'Mia', contact: { email: 'mia@test.example', whatsapp: '' },
    partages: 7, convertis: 5, revoques: 1, progression: { boosts: 5, vip: false, prochain: { cle: 'vip', seuil: 10, libelle: 'Ambassadeur VIP', restant: 5 } },
    recompenses: [{ id: 'X|e|pass_ami', palier: 'pass_ami', libelle: 'Pass Ami', etat: 'disponible', etat_libelle: 'Disponible' },
      { id: 'X|e|recompense', palier: 'recompense', libelle: 'Récompense Afroboost', etat: 'a_remettre', etat_libelle: 'À remettre' }] }] };
  test('10/11 — repliée par défaut (aucun appel) ; ouverte : liste, recherche, détail, « Marquer remise »', async () => {
    axios.get.mockImplementation((url) => {
      if (String(url).endsWith('/api/ambassadeur/coach')) return Promise.resolve({ data: LISTE });
      return Promise.resolve({ data: { id: 'abc', filleuls: [{ prenom: 'Sophie', evenement: 'AFROBOOST SILENT', date: '2026-10-28T18:45:00',
        reservation_confirmee: true, montant: 25, boost: true, annule_ou_rembourse: false }], recompenses: LISTE.ambassadeurs[0].recompenses } });
    });
    axios.post.mockResolvedValue({ data: { id: 'X|e|recompense', etat: 'remise', etat_libelle: 'Remise' } });
    await act(async () => { rendre(<AmbassadeursCoach />); });
    expect(axios.get).not.toHaveBeenCalled();
    await act(async () => { q('ambassadeurs-ouvrir').click(); });
    await attendre(() => expect(q('ambassadeur-abc123def456abc123def456')).toBeTruthy());
    expect(q('ambassadeur-boosts').textContent).toBe('5 Boosts');
    expect(document.body.textContent).toContain('Encore 5 → Ambassadeur VIP');
    await act(async () => { q('ambassadeur-abc123def456abc123def456').click(); });
    await attendre(() => expect(q('amb-filleul')).toBeTruthy());
    expect(q('amb-filleul').textContent).toContain('Sophie');
    expect(q('amb-filleul').textContent).toContain('Boost attribué');
    await act(async () => { q('amb-action-recompense-remise').click(); });
    expect(axios.post.mock.calls[0][1]).toEqual({ id: 'X|e|recompense', etat: 'remise' });
  });
  test('actions : Pass Ami utilisé / disponible, Récompense remise / à remettre, VIP aucune', () => {
    expect(actionsRecompense({ palier: 'pass_ami', etat: 'disponible' })[0].etat).toBe('utilise');
    expect(actionsRecompense({ palier: 'recompense', etat: 'remise' })[0].etat).toBe('a_remettre');
    expect(actionsRecompense({ palier: 'vip', etat: 'actif' })).toEqual([]);
  });
});

describe('V610o — page de l’ami', () => {
  test('20/27 — « Bassi t’invite à Afroboost Silent » + « Viens avec tes amis » ; aucun compteur de places', async () => {
    global.fetch = jest.fn(() => json(SILENT));
    await act(async () => { rendre(<InvitationPublique token="JetonBassi1234567890" />); });
    await attendre(() => expect(q('inv-pub-inviteur')).toBeTruthy());
    expect(q('inv-pub-inviteur').textContent).toBe('Bassi t\'invite à Afroboost Silent');
    expect(q('inv-pub-groupe').textContent).toContain('Viens avec tes amis');
    expect(document.body.textContent).not.toMatch(/places restantes|plus que \d+ places|50 places/i);
  });
  test('essai : en-tête inchangé', async () => {
    global.fetch = jest.fn(() => json({ type: 'trial', title: 'Ton premier cours', inviter_display: { prenom: 'Bassi' } }));
    await act(async () => { rendre(<InvitationPublique token="JetonBassi1234567890" />); });
    await attendre(() => expect(q('inv-pub-inviteur')).toBeTruthy());
    expect(q('inv-pub-inviteur').textContent).toBe('Bassi t\'invite');
    expect(q('inv-pub-groupe')).toBeNull();
  });
});
