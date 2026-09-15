/**
 * OFFRES AIMANTS — le rendu du parcours visiteur : 3 cartes, « toutes les
 * offres », fiche détail, choix 1× / 2× de la saison, un seul CTA qui délègue
 * au point d'entrée existant (`onChoisir` = handleSelectOffer).
 */
import React from 'react';
import { createRoot } from 'react-dom/client';
import OffresAimants from '../OffresAimants';

jest.mock('../PawaPayOfferButton', () => () => <span data-testid="mobile-money" />);

global.IS_REACT_ACT_ENVIRONMENT = true;
const act = React.act;

const analyser = (url) => {
  if (!url) return null;
  if (/\.mp4$/i.test(url)) return { type: 'video', url };
  return { type: 'image', url };
};

const fond = { id: 'o-fond', name: 'Fondateurs', price: 59, offer_type: 'subscription', pack_sessions: 8, stock: 50, places_restantes: 47, position: 1, billing_mode: 'mensuel_auto', countdown_enabled: true, countdown_date: '2026-09-30', countdown_time: '23:59', description: 'Tarif de lancement réservé aux 50 premiers inscrits.', images: ['https://x/f.jpg'] };
const s1 = { id: 'o-s1', name: 'Saison hiver — 8 mois', price: 549, offer_type: 'subscription', pack_sessions: 64, stock: -1, position: 2, billing_mode: 'unique', duree_mois: 8 };
const s2 = { id: 'o-s2', name: 'Saison hiver — 2 paiements', price: 299, offer_type: 'subscription', pack_sessions: 8, stock: -1, position: 3, billing_mode: 'saison_2x' };
const mensuel = { id: 'o-men', name: 'Mensuel Liberté', price: 89, offer_type: 'subscription', pack_sessions: 8, stock: -1, position: 4, billing_mode: 'mensuel_auto', videoUrl: 'https://x/v.mp4', video_aspect_ratio: '9:16' };
const flex = { id: 'o-flex', name: 'Flex 4', price: 49, offer_type: 'subscription', pack_sessions: 4, stock: -1, position: 5, billing_mode: 'mensuel_auto' };
const etu = { id: 'o-etu', name: 'Étudiant', price: 69, offer_type: 'subscription', pack_sessions: 8, stock: -1, position: 6, billing_mode: 'mensuel_auto', description: 'Tarif réservé aux étudiants.' };
const unite = { id: 'o-unite', name: "Cours à l'unité", price: 30, offer_type: 'single_class', pack_sessions: 1, stock: -1, position: 1 };
const carte = { id: 'o-carte', name: 'Carte membre association', price: 100, offer_type: 'membership', pack_sessions: 0, duree_mois: 12, creates_membership: true, stock: -1, position: 9 };
const essai = { id: 'o-essai', name: "Cours d'essai", price: 0, offer_type: 'single_class', pack_sessions: 1, stock: -1, position: 0 };
const OFFRES = [unite, essai, etu, flex, carte, mensuel, s2, s1, fond];

let conteneur = null;
let racine = null;
let choisis = [];

async function monter(props = {}) {
  choisis = [];
  conteneur = document.createElement('div');
  document.body.appendChild(conteneur);
  racine = createRoot(conteneur);
  await act(async () => {
    racine.render(<OffresAimants offres={OFFRES} analyserMedia={analyser} onChoisir={(o) => choisis.push(o)} {...props} />);
  });
  await act(async () => {});
}
async function rerendre(props = {}) {
  await act(async () => {
    racine.render(<OffresAimants offres={OFFRES} analyserMedia={analyser} onChoisir={(o) => choisis.push(o)} {...props} />);
  });
}
async function demonter() {
  if (racine) await act(async () => { racine.unmount(); });
  if (conteneur) conteneur.remove();
  racine = null; conteneur = null;
}
afterEach(async () => { await demonter(); document.body.style.removeProperty('overflow'); window.history.replaceState({}, '', '/'); });

const par = (id) => document.querySelector(`[data-testid="${id}"]`);
const texte = (id) => (par(id) ? par(id).textContent : '');
async function cliquer(el) {
  await act(async () => { el.dispatchEvent(new MouseEvent('click', { bubbles: true })); });
}

test('la vitrine ne montre que 3 cartes : Fondateurs, Saison 8 mois, Mensuel Liberté — pas 7', async () => {
  await monter();
  expect(texte('aimant-lancement')).toMatch(/Fondateurs/);
  expect(texte('aimant-lancement')).toMatch(/59 CHF/);
  expect(texte('aimant-lancement')).toMatch(/Offre lancement/);
  expect(texte('aimant-limitee')).toBe('47 places restantes · offre jusqu’au 30/09');
  expect(texte('aimant-saison')).toMatch(/Saison 8 mois/);
  expect(texte('aimant-saison')).toMatch(/Dès 549 CHF/);
  expect(texte('aimant-saison')).toMatch(/Meilleur prix/);
  expect(texte('aimant-mensuel')).toMatch(/Mensuel Liberté/);
  expect(texte('aimant-mensuel')).toMatch(/89 CHF/);
  expect(texte('aimant-mensuel')).toMatch(/Le plus flexible/);
  const bloc = texte('offres-aimants');
  expect(bloc).not.toMatch(/Étudiant|Flex 4|Cours d'essai|Carte membre/);
  // Aucun gros compteur sur la carte : rien qui ressemble à « 00h 00m 00s ».
  expect(bloc).not.toMatch(/\d+h \d+m \d+s/);
  expect(document.querySelectorAll('[data-testid^="aimant-"]:not([data-testid="aimant-limitee"])')).toHaveLength(3);
});

test('« Voir toutes les offres » ouvre la liste complète, ordonnée, produits exclus', async () => {
  await monter();
  await cliquer(par('voir-toutes-les-offres'));
  const lignes = Array.from(document.querySelectorAll('[data-testid^="ligne-offre-"]')).map((b) => b.textContent);
  expect(lignes).toHaveLength(9);
  expect(lignes[0]).toMatch(/^Fondateurs/);
  expect(lignes.some((n) => /Étudiant/.test(n) && /69 CHF/.test(n))).toBe(true);
  expect(lignes.some((n) => /Flex 4/.test(n) && /49 CHF/.test(n))).toBe(true);
  expect(lignes.some((n) => /Cours à l'unité/.test(n) && /30 CHF/.test(n))).toBe(true);
  expect(lignes.some((n) => /Carte membre/.test(n) && /100 CHF/.test(n))).toBe(true);
  expect(lignes[lignes.length - 1]).toMatch(/Cours d'essai/);
  expect(document.body.style.overflow).toBe('hidden');
  await cliquer(par('panneau-fermer'));
  expect(par('toutes-les-offres')).toBeNull();
  expect(document.body.style.overflow).toBe('');
});

test('la fiche Étudiant : badge, prix, promesse, inclus, justificatif, CTA → onChoisir(offre)', async () => {
  await monter();
  await cliquer(par('voir-toutes-les-offres'));
  await cliquer(par('ligne-offre-o-etu'));
  expect(par('toutes-les-offres')).toBeNull();
  const fiche = par('fiche-offre');
  expect(texte('fiche-nom')).toBe('Étudiant');
  expect(texte('fiche-prix')).toMatch(/69 CHF/);
  expect(fiche.textContent).toMatch(/Tarif réservé aux étudiants\./);
  expect(texte('fiche-inclus')).toMatch(/jusqu’à 8 séances \/ mois/);
  expect(fiche.textContent).toMatch(/Justificatif étudiant requis/);
  expect(fiche.textContent).toMatch(/Prélèvement automatique chaque mois/);
  expect(fiche.textContent).toMatch(/Étudiant·e, avec justificatif/);
  expect(par('mobile-money')).not.toBeNull();
  expect(texte('fiche-cta')).toBe('Choisir cette formule');
  await cliquer(par('fiche-cta'));
  expect(choisis).toHaveLength(1);
  expect(choisis[0].id).toBe('o-etu');
  expect(par('fiche-offre')).toBeNull();
});

test('la carte Saison ouvre le choix 1× / 2× ; chaque choix part avec SON offre réelle', async () => {
  await monter();
  await cliquer(par('aimant-saison'));
  const choix = texte('fiche-choix-saison');
  expect(choix).toMatch(/549 CHF/);
  expect(choix).toMatch(/Paiement en une fois/);
  expect(choix).toMatch(/2 × 299 CHF/);
  expect(choix).toMatch(/Paiement en deux fois/);
  expect(choix).toMatch(/Tu économises 163 CHF par rapport au mensuel/);
  expect(choix).toMatch(/Tu économises 114 CHF par rapport au mensuel/);
  expect(texte('fiche-prix')).toBe('Dès 549 CHF');
  // Par défaut : la 1× (meilleur prix).
  await cliquer(par('fiche-cta'));
  expect(choisis[0].id).toBe('o-s1');
  // Puis la 2×.
  await cliquer(par('aimant-saison'));
  const radio2 = par('choix-saison-o-s2').querySelector('input');
  await act(async () => { radio2.click(); });
  await cliquer(par('fiche-cta'));
  expect(choisis[1].id).toBe('o-s2');
});

test('la fiche Fondateurs garde le stock réel et la vraie date (compact, pas de gros compteur)', async () => {
  await monter();
  await cliquer(par('aimant-lancement'));
  expect(texte('fiche-limitee')).toBe('47 places restantes · offre jusqu’au 30/09');
  expect(par('fiche-offre').textContent).toMatch(/50 places maximum/);
  expect(par('fiche-offre').textContent).not.toMatch(/\d+h \d+m \d+s/);
});

test('vidéo 9:16 dans la fiche : lecteur en contain, ratio respecté, jamais en cover', async () => {
  await monter();
  await cliquer(par('aimant-mensuel'));
  const lecteur = par('fiche-lecteur');
  expect(lecteur.getAttribute('data-ratio')).toBe('9:16');
  const video = lecteur.querySelector('video');
  expect(video.style.objectFit).toBe('contain');
  expect(video.style.aspectRatio).toBe('9 / 16');
  expect(video.hasAttribute('controls')).toBe(true);
});

test('le signal « Offres » de la barre ouvre la liste', async () => {
  await monter({ ouvrirToutesSignal: 0 });
  expect(par('toutes-les-offres')).toBeNull();
  await rerendre({ ouvrirToutesSignal: 1 });
  expect(par('toutes-les-offres')).not.toBeNull();
});

test('lien profond ?offre=<id> ouvre la fiche ; &reserver=1 sur une offre gratuite ouvre le formulaire (onChoisir), jamais un paiement', async () => {
  window.history.replaceState({}, '', '/?offre=o-etu');
  await monter();
  expect(texte('fiche-nom')).toBe('Étudiant');
  await demonter();
  window.history.replaceState({}, '', '/?offre=o-essai&reserver=1');
  await monter();
  expect(choisis).toHaveLength(1);
  expect(choisis[0].id).toBe('o-essai');
  expect(par('fiche-offre')).toBeNull();
  await demonter();
  window.history.replaceState({}, '', '/?offre=o-s1&reserver=1');
  await monter();
  expect(choisis).toHaveLength(0);              // payant : jamais tout seul
  expect(texte('fiche-nom')).toMatch(/Saison hiver — 8 mois/);
});

test('sans aucun aimant, le bloc ne se rend pas (la vitrine garde son carrousel)', async () => {
  await monter({ offres: [unite, essai] });
  expect(conteneur.firstChild).toBeNull();
});

test('Échap ferme la fiche', async () => {
  await monter();
  await cliquer(par('aimant-mensuel'));
  expect(par('fiche-offre')).not.toBeNull();
  await act(async () => { document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' })); });
  expect(par('fiche-offre')).toBeNull();
});
