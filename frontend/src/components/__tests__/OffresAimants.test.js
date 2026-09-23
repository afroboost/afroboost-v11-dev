/**
 * OFFRES AIMANTS — le rendu du parcours visiteur : 3 cartes, « toutes les
 * offres », fiche détail, choix 1× / 2× de la saison, un seul CTA qui délègue
 * au point d'entrée existant (`onChoisir` = handleSelectOffer).
 */
import React from 'react';
import { createRoot } from 'react-dom/client';
import OffresAimants from '../OffresAimants';


global.IS_REACT_ACT_ENVIRONMENT = true;
const act = React.act;

const analyser = (url) => {
  if (!url) return null;
  if (/\.mp4$/i.test(url)) return { type: 'video', url };
  return { type: 'image', url };
};
// Le bouton Mobile Money réel décide seul (drapeau de l'offre) ; ici on vérifie
// que la fiche le monte avec l'offre, et lui rend `null` sans le drapeau.
jest.mock('../PawaPayOfferButton', () => ({ offer }) => (offer && offer.mobile_money_enabled ? <span data-testid="mobile-money" /> : null));

// Fondateurs : comme en production, un .png dans le champ « vidéo », rien d'autre.
const fond = { id: 'o-fond', name: 'Fondateurs', price: 59, offer_type: 'subscription', pack_sessions: 8, stock: 50, places_restantes: 47, position: 1, billing_mode: 'mensuel_auto', countdown_enabled: true, countdown_date: '2026-09-30', countdown_time: '23:59', description: 'Tarif de lancement réservé aux 50 premiers inscrits.', videoUrl: 'https://x/couverture.png', video_aspect_ratio: '16:9' };
// Saison : vidéo + miniature dédiée → la carte montre la miniature, la fiche la vidéo.
const s1 = { id: 'o-s1', name: 'Saison hiver — 8 mois', price: 549, offer_type: 'subscription', pack_sessions: 64, stock: -1, position: 2, billing_mode: 'unique', duree_mois: 8, videoUrl: 'https://x/saison.mp4', thumbnail: 'https://x/mini-saison.jpg' };
const s2 = { id: 'o-s2', name: 'Saison hiver — 2 paiements', price: 299, offer_type: 'subscription', pack_sessions: 8, stock: -1, position: 3, billing_mode: 'saison_2x' };
const mensuel = { id: 'o-men', name: 'Mensuel Liberté', price: 89, offer_type: 'subscription', pack_sessions: 8, stock: -1, position: 4, billing_mode: 'mensuel_auto', videoUrl: 'https://x/v.mp4', video_aspect_ratio: '9:16', mobile_money_enabled: true };
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
  // V526: avec Fondateurs ouverte (7.38 CHF/séance), la saison (8.58) n'est PAS le meilleur prix
  expect(texte('aimant-saison')).toMatch(/Saison complète/);
  expect(texte('aimant-saison')).not.toMatch(/Meilleur prix/);
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
  // Hiérarchie : groupes titrés, vignette par ligne, prix à droite.
  expect(['lancement', 'saison', 'mensuel', 'unite', 'membre', 'offert'].map((g) => !!par(`groupe-${g}`))).toEqual([true, true, true, true, true, true]);
  expect(par('ligne-offre-o-fond').querySelector('img').getAttribute('src')).toBe('https://x/couverture.png');
  expect(par('ligne-offre-o-s1').textContent).toMatch(/Économie : 163 CHF/);
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
  expect(par('mobile-money')).toBeNull();                 // drapeau absent → pas de Mobile Money
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

test('vidéo 9:16 dans la fiche : REMPLIT un cadre portrait (cover, 4:5), fond flouté ; « Agrandir » = format réel 9:16 en contain ; Mobile Money si activé', async () => {
  await monter();
  await cliquer(par('aimant-mensuel'));
  const lecteur = par('fiche-lecteur');
  expect(lecteur.getAttribute('data-ratio')).toBe('9:16');
  expect(lecteur.style.aspectRatio).toBe('4 / 5');
  const video = lecteur.querySelector('video');
  expect(video.style.objectFit).toBe('cover');
  expect(video.hasAttribute('controls')).toBe(true);
  expect(lecteur.querySelector('[data-testid=fond-flou]')).not.toBeNull();
  expect(par('mobile-money')).not.toBeNull();
  await cliquer(par('fiche-agrandir'));
  const grand = par('media-agrandi');
  expect(grand.getAttribute('data-ratio')).toBe('9:16');
  const v = grand.querySelector('video');
  expect(v.style.objectFit).toBe('contain');
  expect(v.style.aspectRatio).toBe('9 / 16');
  await cliquer(par('media-agrandi-fermer'));
  expect(par('media-agrandi')).toBeNull();
});

test('image 16:9 dans la fiche : cadre 16:9 rempli (cover) ; agrandie = image entière (contain)', async () => {
  await monter();
  await cliquer(par('aimant-lancement'));
  const cadre = par('fiche-image');
  expect(cadre.style.aspectRatio).toBe('16 / 9');
  expect(cadre.querySelector('img').style.objectFit).toBe('cover');
  await cliquer(par('fiche-agrandir'));
  expect(par('media-agrandi').querySelector('img').style.objectFit).toBe('contain');
});

test('MINIATURES : image du champ vidéo (Fondateurs) et miniature dédiée (Saison) REMPLISSENT la carte ; vidéo sans image = vidéo qui remplit la zone', async () => {
  await monter();
  const vF = par('aimant-lancement').querySelector('[data-testid=vignette-image]');
  expect(vF).not.toBeNull();
  expect(vF.getAttribute('src')).toBe('https://x/couverture.png');
  expect(vF.style.objectFit).toBe('cover');
  const vS = par('aimant-saison').querySelector('[data-testid=vignette-image]');
  expect(vS.getAttribute('src')).toBe('https://x/mini-saison.jpg');     // miniature dédiée prioritaire sur la vidéo
  const vM = par('aimant-mensuel').querySelector('[data-testid=vignette-video]');
  expect(vM.querySelector('video').style.objectFit).toBe('cover');
  // Trois offres, trois médias DIFFÉRENTS : aucun repli, aucune source partagée.
  const sources = [vF.getAttribute('src'), vS.getAttribute('src'), vM.querySelector('video').getAttribute('src')];
  expect(new Set(sources).size).toBe(3);
  expect(document.querySelectorAll('[data-testid=vignette-repli]')).toHaveLength(0);
  // Fiche Fondateurs : l'image, pas un <video> vide.
  await cliquer(par('aimant-lancement'));
  expect(par('fiche-image')).not.toBeNull();
  expect(par('fiche-lecteur')).toBeNull();
  // Fiche Saison : la vidéo, avec la miniature en poster.
  await cliquer(par('panneau-fermer'));
  await cliquer(par('aimant-saison'));
  expect(par('fiche-lecteur').querySelector('video').getAttribute('poster')).toBe('https://x/mini-saison.jpg');
});

test('média indisponible : repli sobre, jamais une zone vide cassée', async () => {
  await monter({ offres: [{ ...fond, videoUrl: '' }, s1, mensuel] });
  expect(par('aimant-lancement').querySelector('[data-testid=vignette-repli]')).not.toBeNull();
  await cliquer(par('aimant-lancement'));
  expect(par('fiche-repli')).not.toBeNull();
});

test('V530 — « Voir toutes les offres » est une action SECONDAIRE rattachée à la grille : pleine largeur, contour de marque, pas une carte', async () => {
  await monter();
  const b = par('voir-toutes-les-offres');
  expect(b.style.width).toBe('100%');
  // jsdom refuse `border`/`background` contenant rgba(var()) (le navigateur les accepte) :
  // la couleur de marque se vérifie sur le SOURCE du bouton, le rendu sur le DOM.
  const src = require('fs').readFileSync(require.resolve('../OffresAimants'), 'utf8');
  const bloc = src.slice(src.indexOf('data-testid="voir-toutes-les-offres"'), src.indexOf('Voir toutes les offres', src.indexOf('data-testid="voir-toutes-les-offres"')));
  expect(bloc).toContain('border: `1px solid rgba(${RGB}'); // contour couleur de marque
  expect(bloc).toContain('background: `rgba(${RGB}'); // fond léger de marque, pas le dégradé d'une carte
  expect(bloc).not.toMatch(/#[0-9a-fA-F]{6}/); // aucun hex codé en dur
  expect((b.getAttribute('style') || '')).not.toContain('linear-gradient');
  expect(b.textContent.trim()).toBe('Voir toutes les offres');
  expect(b.querySelectorAll('svg').length).toBe(2); // grille + flèche en SVG, aucun emoji
  expect(b.previousElementSibling).toBe(par('grille-aimants')); // juste sous la grille
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

test('✂️ la fiche et la carte jouent l’extrait découpé : tête au début, retour au début après la fin', async () => {
  await monter({ offres: [fond, s1, { ...mensuel, thumbnail: '', video_trim_start: 2, video_trim_end: 17 }] });
  const carte = par('aimant-mensuel').querySelector('video');
  carte.play = () => Promise.resolve();
  carte.currentTime = 0; await act(async () => { carte.dispatchEvent(new Event('loadedmetadata')); });
  expect(carte.currentTime).toBe(2);
  carte.currentTime = 17.5; await act(async () => { carte.dispatchEvent(new Event('timeupdate')); });
  expect(carte.currentTime).toBe(2);                       // boucle sur l'extrait
  await cliquer(par('aimant-mensuel'));
  const v = par('fiche-lecteur').querySelector('video');
  expect(v.getAttribute('data-trim')).toBe('2-17');
  const pause = jest.fn(); v.pause = pause;
  v.currentTime = 0; await act(async () => { v.dispatchEvent(new Event('loadedmetadata')); });
  expect(v.currentTime).toBe(2);
  v.currentTime = 17; await act(async () => { v.dispatchEvent(new Event('timeupdate')); });
  expect(pause).toHaveBeenCalled();                        // fin de l'extrait : pause, retour au début
  expect(v.currentTime).toBe(2);
});

// V525 : le compteur (composant OfferCountdown existant d'App.js, passé en prop)
// est monté sur la carte Fondateurs ET dans sa fiche — jamais sur les autres.
test('V525 — la prop Countdown est rendue sur la carte de lancement et dans sa fiche, nulle part ailleurs', async () => {
  const Countdown = ({ offer }) => <span data-testid="countdown-stub" data-offre={offer.id} />;
  await monter({ Countdown });
  const stubs = conteneur.querySelectorAll('[data-testid="countdown-stub"]');
  expect(stubs.length).toBe(1);
  expect(stubs[0].getAttribute('data-offre')).toBe('o-fond');
  expect(conteneur.querySelector('[data-testid="aimant-lancement"] [data-testid="countdown-stub"]')).not.toBeNull();
  await act(async () => { conteneur.querySelector('[data-testid="aimant-lancement"]').click(); });
  const fiche = document.querySelector('[data-testid="fiche-offre"]');
  expect(fiche.querySelector('[data-testid="countdown-stub"]').getAttribute('data-offre')).toBe('o-fond');
  await act(async () => { conteneur.querySelector('[data-testid="aimant-lancement"]').click(); });
  // Sans la prop : aucun compteur, rien ne casse.
  await rerendre({});
  expect(document.querySelectorAll('[data-testid="countdown-stub"]').length).toBe(0);
});

test('V526/V530 — le bloc CTA de la fiche est COLLANT en bas (position sticky) sur mobile ET desktop', async () => {
  const largeur = window.innerWidth;
  Object.defineProperty(window, 'innerWidth', { configurable: true, writable: true, value: 390 });
  await monter();
  await act(async () => { conteneur.querySelector('[data-testid="aimant-mensuel"]').click(); });
  const bloc = document.querySelector('[data-testid="fiche-cta-bloc"]');
  expect(bloc).not.toBeNull();
  expect(bloc.style.position).toBe('sticky');
  expect(bloc.style.bottom).toBe('0px');
  expect(bloc.querySelector('[data-testid="fiche-cta"]')).not.toBeNull(); // le bouton reste DANS le bloc
  await act(async () => { bloc.querySelector('[data-testid="fiche-cta"]').click(); });
  expect(choisis.map((o) => o.id)).toEqual(['o-men']); // et il fonctionne (onChoisir)
  Object.defineProperty(window, 'innerWidth', { configurable: true, writable: true, value: 1280 });
  await monter();
  await act(async () => { conteneur.querySelector('[data-testid="aimant-mensuel"]').click(); });
  const blocDesktop = document.querySelector('[data-testid="fiche-cta-bloc"]');
  expect(blocDesktop.style.position).toBe('sticky'); // V530 : desktop aussi (CTA à y=1088 pour 900 px avant)
  expect(blocDesktop.style.bottom).toBe('0px');
  Object.defineProperty(window, 'innerWidth', { configurable: true, writable: true, value: largeur });
});

/* ══════════════ V542 — contrôleur seul + cartes comparatives ══════════════ */

test('V542 — `cartes={false}` : aucune carte rendue, mais le panneau complet répond au signal', async () => {
  await monter({ cartes: false, ouvrirToutesSignal: 0 });
  // Rien à l'écran : le parcours connecté garde SON carrousel, pas un doublon.
  expect(conteneur.querySelectorAll('[data-testid^="aimant-"]')).toHaveLength(0);
  expect(conteneur.querySelector('[data-testid="offres-aimants"]')).toBeNull();
  expect(conteneur.querySelector('[data-testid="voir-toutes-les-offres"]')).toBeNull();
  expect(conteneur.querySelector('[data-testid="offres-controleur"]')).not.toBeNull();
  expect(document.querySelector('[data-testid="toutes-les-offres"]')).toBeNull();

  // …mais le signal — celui de « Voir toutes les offres » de la colonne d'accueil —
  // rouvre bien le panneau historique. C'est EXACTEMENT la régression corrigée.
  await rerendre({ cartes: false, ouvrirToutesSignal: 1 });
  await act(async () => {});
  const panneau = document.querySelector('[data-testid="toutes-les-offres"]');
  expect(panneau).not.toBeNull();
  const liste = document.querySelector('[data-testid="liste-toutes-offres"]');
  expect(liste.textContent).toContain('Flex 4');           // une offre SECONDAIRE
  expect(liste.textContent).toContain('Fondateurs');       // et les aimants aussi
  expect(liste.textContent).not.toContain('T-shirt');      // jamais un produit
});

test('V542 — le contrôleur seul ouvre la fiche détail d’une offre secondaire', async () => {
  await monter({ cartes: false, ouvrirToutesSignal: 0 });
  await rerendre({ cartes: false, ouvrirToutesSignal: 1 });
  await act(async () => {});
  const lignes = [...document.querySelectorAll('[data-testid="liste-toutes-offres"] button')];
  const cible = lignes.find((b) => /Flex 4/.test(b.textContent));
  expect(cible).toBeTruthy();
  await act(async () => { cible.dispatchEvent(new MouseEvent('click', { bubbles: true })); });
  const fiche = document.querySelector('[data-testid="fiche-offre"]') || document.body;
  expect(fiche.textContent).toContain('Flex 4');
});

test('V542 — un catalogue SANS aimant : plus de carte, mais le catalogue reste ouvrable', async () => {
  // La garde historique (`return null` sans aimant) ne doit fermer que la présentation.
  await demonter();
  conteneur = document.createElement('div');
  document.body.appendChild(conteneur);
  racine = createRoot(conteneur);
  await act(async () => {
    racine.render(<OffresAimants offres={[unite, essai]} analyserMedia={analyser} onChoisir={() => {}} cartes={false} ouvrirToutesSignal={1} />);
  });
  await act(async () => {});
  expect(document.querySelector('[data-testid="toutes-les-offres"]')).not.toBeNull();
});

test('V542 — les 3 cartes disent enfin POURQUOI les choisir (données réelles, rien d’inventé)', async () => {
  await monter();
  const lire = (cle) => conteneur.querySelector(`[data-testid="details-aimant-${cle}"]`).textContent;

  // Fondateurs : mensuel, séances réelles, et à qui il s'adresse.
  expect(lire('lancement')).toContain('8 séances / mois');
  expect(lire('lancement')).toContain('Chaque mois');
  expect(lire('lancement')).toContain('premiers inscrits');

  // Saison : l'économie est CALCULÉE face au mensuel (89 × 8 = 712 → 549 = 163 CHF).
  expect(lire('saison')).toContain('Économie');
  expect(lire('saison')).toContain('163');

  // Mensuel : sa différence, c'est la liberté — pas un prix.
  expect(lire('mensuel')).toContain('Chaque mois');
  expect(lire('mensuel')).toContain('Sans engagement');

  // Hiérarchie tenue : 4 lignes maximum par carte, le reste vit dans la fiche.
  for (const cle of ['lancement', 'saison', 'mensuel']) {
    const n = conteneur.querySelectorAll(`[data-testid="details-aimant-${cle}"] > span`).length;
    expect(n).toBeGreaterThanOrEqual(2);
    expect(n).toBeLessThanOrEqual(4);
  }
  // Et toujours le même point d'entrée : « Voir l'offre ».
  expect(conteneur.querySelector('[data-testid="aimant-mensuel"]').textContent).toContain('Voir l’offre');
});
