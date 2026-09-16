/**
 * OFFRES AIMANTS — la logique pure du parcours de conversion.
 * Catalogue = les vraies offres hiver de production (mêmes champs que /api/offers).
 */
import {
  familleOffre, FAMILLE, regrouperOffres, ficheOffre, badgeOffre, economieOffre, infoCompacteLimitee,
  prixAffiche, libelleSeances, libellePaiement, libelleEngagement, visiteurEstConnecte, libelleDepuis,
  mensuelDeReference, promesseCourte, coutParSeance, estMeilleurPrix,
} from '../offresAimants';

const essai = { id: 'o-essai', name: "🎁 Cours d'essai GRATUIT", price: 0, offer_type: 'single_class', pack_sessions: 1, stock: -1, position: 0 };
const fond = { id: 'o-fond', name: 'Fondateurs', price: 59, offer_type: 'subscription', pack_sessions: 8, stock: 50, places_restantes: 47, position: 1, billing_mode: 'mensuel_auto', countdown_enabled: true, countdown_date: '2026-09-30', countdown_time: '23:59', description: 'Tarif de lancement réservé aux 50 premiers inscrits. Prélevé chaque mois.' };
const s1 = { id: 'o-s1', name: 'Saison hiver — 8 mois', price: 549, offer_type: 'subscription', pack_sessions: 64, stock: -1, position: 2, billing_mode: 'unique', duree_mois: 8 };
const s2 = { id: 'o-s2', name: 'Saison hiver — 2 paiements', price: 299, offer_type: 'subscription', pack_sessions: 8, stock: -1, position: 3, billing_mode: 'saison_2x' };
const mensuel = { id: 'o-men', name: 'Mensuel Liberté', price: 89, offer_type: 'subscription', pack_sessions: 8, stock: -1, position: 4, billing_mode: 'mensuel_auto' };
const flex = { id: 'o-flex', name: 'Flex 4', price: 49, offer_type: 'subscription', pack_sessions: 4, stock: -1, position: 5, billing_mode: 'mensuel_auto' };
const etu = { id: 'o-etu', name: 'Étudiant', price: 69, offer_type: 'subscription', pack_sessions: 8, stock: -1, position: 6, billing_mode: 'mensuel_auto' };
const unite = { id: 'o-unite', name: "Cours à l'unité", price: 30, offer_type: 'single_class', pack_sessions: 1, stock: -1, position: 1 };
const carte = { id: 'o-carte', name: 'Carte membre association', price: 100, offer_type: 'membership', pack_sessions: 0, duree_mois: 12, creates_membership: true, stock: -1, position: 9 };
const tshirt = { id: 'o-tee', name: 'T-shirt', price: 59.99, isProduct: true, offer_type: 'product' };
// Les positions sont VOLONTAIREMENT en désordre dans la liste d'entrée.
const CATALOGUE = [unite, tshirt, essai, etu, flex, carte, mensuel, s2, s1, fond];

describe('familles lues sur les champs, jamais sur un nom', () => {
  test('chaque offre tombe dans sa famille', () => {
    expect(familleOffre(fond)).toBe(FAMILLE.LANCEMENT);
    expect(familleOffre(s1)).toBe(FAMILLE.SAISON_1X);
    expect(familleOffre(s2)).toBe(FAMILLE.SAISON_2X);
    expect(familleOffre(mensuel)).toBe(FAMILLE.MENSUEL);
    expect(familleOffre(flex)).toBe(FAMILLE.MENSUEL);
    expect(familleOffre(unite)).toBe(FAMILLE.UNITE);
    expect(familleOffre(essai)).toBe(FAMILLE.OFFERT);
    expect(familleOffre(carte)).toBe(FAMILLE.MEMBRE);
    expect(familleOffre(tshirt)).toBe(FAMILLE.PRODUIT);
  });
  test('une offre limitée par la date seule (stock illimité) est un lancement', () => {
    expect(familleOffre({ ...mensuel, countdown_enabled: true, countdown_date: '2026-10-01' })).toBe(FAMILLE.LANCEMENT);
  });
  test('un nom « Fondateurs » sans stock ni date n’est PAS un lancement', () => {
    expect(familleOffre({ ...fond, stock: -1, countdown_enabled: false })).toBe(FAMILLE.MENSUEL);
  });
});

describe('les 3 aimants', () => {
  const g = regrouperOffres(CATALOGUE);
  test('lancement, saison (2 offres sous UNE carte), mensuel de référence — dans cet ordre', () => {
    expect(g.aimants.map((a) => a.cle)).toEqual(['lancement', 'saison', 'mensuel']);
    expect(g.aimants[0].offre.id).toBe('o-fond');
    expect(g.aimants[1].offres.map((o) => o.id)).toEqual(['o-s1', 'o-s2']);
    expect(g.aimants[2].offre.id).toBe('o-men');
  });
  test('la carte saison dit « Dès 549 CHF » (le moins cher des totaux), sans fusionner les offres', () => {
    expect(libelleDepuis(g.aimants[1])).toBe('Dès 549 CHF');
    expect(g.aimants[1].offres[0]).toBe(s1);
    expect(g.aimants[1].offres[1]).toBe(s2);
  });
  test('le mensuel de référence est le plus cher des mensuels (89, pas Flex 49 ni Étudiant 69)', () => {
    expect(mensuelDeReference(CATALOGUE).id).toBe('o-men');
  });
  test('« toutes les offres » : ordre commercial, produits exclus, essai en dernier', () => {
    expect(g.autres.map((o) => o.id)).toEqual(['o-fond', 'o-s1', 'o-s2', 'o-men', 'o-flex', 'o-etu', 'o-unite', 'o-carte', 'o-essai']);
  });
  test('sans aucun aimant (catalogue unité + essai) : liste vide → la vitrine garde son carrousel', () => {
    expect(regrouperOffres([unite, essai]).aimants).toEqual([]);
  });
  test('seule la saison 2× existe : la carte saison tient quand même, « Dès 598 CHF »', () => {
    const g2 = regrouperOffres([s2, mensuel]);
    expect(g2.aimants.map((a) => a.cle)).toEqual(['saison', 'mensuel']);
    expect(libelleDepuis(g2.aimants[0])).toBe('Dès 598 CHF');
  });
});

describe('badges', () => {
  const ref = mensuelDeReference(CATALOGUE);
  test('OFFRE LANCEMENT / MEILLEUR PRIX / SAISON EN 2 FOIS / LE PLUS FLEXIBLE / ÉTUDIANT, rien sur Flex', () => {
    expect(badgeOffre(fond, ref)).toBe('Offre lancement');
    expect(badgeOffre(s1, ref)).toBe('Meilleur prix'); // sans liste : règle historique
    // V526: face au catalogue, « Meilleur prix » n'est vrai que si la saison a le
    // coût par séance le plus bas — Fondateurs (59/8 = 7.38) bat la saison (549/64 = 8.58).
    expect(coutParSeance(fond)).toBeCloseTo(7.375, 3);
    expect(coutParSeance(s1)).toBeCloseTo(8.578, 3);
    expect(coutParSeance(s2)).toBeCloseTo(9.344, 3); // 299 / (8 × 4)
    expect(coutParSeance(flex)).toBeCloseTo(12.25, 3);
    expect(estMeilleurPrix(fond, CATALOGUE)).toBe(true);
    expect(estMeilleurPrix(s1, CATALOGUE)).toBe(false);
    expect(badgeOffre(s1, ref, CATALOGUE)).toBe('Saison complète');
    const sansFondateurs = CATALOGUE.filter((o) => o !== fond);
    expect(estMeilleurPrix(s1, sansFondateurs)).toBe(true); // 8.58 < Étudiant 8.63
    expect(badgeOffre(s1, ref, sansFondateurs)).toBe('Meilleur prix');
    expect(regrouperOffres(CATALOGUE).aimants.find((a) => a.cle === 'saison').badge).toBe('Saison complète');
    expect(regrouperOffres(sansFondateurs).aimants.find((a) => a.cle === 'saison').badge).toBe('Meilleur prix');
    expect(badgeOffre(s2, ref)).toBe('Saison en 2 fois');
    expect(badgeOffre(mensuel, ref)).toBe('Le plus flexible');
    expect(badgeOffre(etu, ref)).toBe('Étudiant');
    expect(badgeOffre(flex, ref)).toBe('');
    expect(badgeOffre(unite, ref)).toBe('');
  });
});

describe('économie réelle (8 × mensuel de référence = 712)', () => {
  const ref = mensuelDeReference(CATALOGUE);
  test('8 mois 1× → 163 ; 2 × 299 → 114 ; jamais sur un mensuel', () => {
    expect(economieOffre(s1, ref)).toBe(163);
    expect(economieOffre(s2, ref)).toBe(114);
    expect(economieOffre(mensuel, ref)).toBeNull();
    expect(economieOffre(fond, ref)).toBeNull();
  });
  test('sans mensuel de référence : aucune économie inventée', () => {
    expect(economieOffre(s1, null)).toBeNull();
  });
  test('un « saison » plus cher que 8 mensuels n’affiche rien', () => {
    expect(economieOffre({ ...s1, price: 800 }, ref)).toBeNull();
  });
});

describe('libellés lus sur le document', () => {
  test('prix et unité', () => {
    expect(prixAffiche(fond)).toEqual({ montant: '59 CHF', unite: '/ mois' });
    expect(prixAffiche(s1)).toEqual({ montant: '549 CHF', unite: '/ saison' });
    expect(prixAffiche(s2)).toEqual({ montant: '2 × 299 CHF', unite: '' });
    expect(prixAffiche(carte)).toEqual({ montant: '100 CHF', unite: '/ an' });
    expect(prixAffiche(unite)).toEqual({ montant: '30 CHF', unite: '' });
    expect(prixAffiche(essai)).toEqual({ montant: 'Offert', unite: '' });
    expect(prixAffiche({ ...unite, price: 19.5 })).toEqual({ montant: '19.5 CHF', unite: '' });
  });
  test('séances', () => {
    expect(libelleSeances(fond)).toBe('jusqu’à 8 séances / mois');
    expect(libelleSeances(s1)).toBe('64 séances sur la saison (env. 8 / mois)');
    expect(libelleSeances(s2)).toBe('jusqu’à 8 séances / mois (32 par échéance)');
    expect(libelleSeances(unite)).toBe('1 séance');
    expect(libelleSeances(carte)).toBe('');
  });
  test('paiement et engagement', () => {
    expect(libellePaiement(mensuel)).toMatch(/Prélèvement automatique chaque mois/);
    expect(libellePaiement(s2)).toMatch(/2 paiements/);
    expect(libellePaiement(s1)).toBe('1 paiement (carte ou TWINT)');
    expect(libelleEngagement(mensuel)).toMatch(/résiliable/);
    expect(libelleEngagement(s1)).toBe('Saison de 8 mois');
    expect(libelleEngagement(carte)).toBe('Adhésion de 12 mois');
  });
  test('info compacte de l’offre limitée : places réelles + date, jamais un compteur', () => {
    expect(infoCompacteLimitee(fond)).toBe('47 places restantes · offre jusqu’au 30/09');
    expect(infoCompacteLimitee({ ...fond, places_restantes: 1 })).toBe('1 place restante · offre jusqu’au 30/09');
    expect(infoCompacteLimitee({ ...fond, places_restantes: undefined, countdown_enabled: false })).toBe('50 places maximum');
    expect(infoCompacteLimitee(mensuel)).toBe('');
  });
  test('promesse courte = première phrase', () => {
    expect(promesseCourte(fond)).toBe('Tarif de lancement réservé aux 50 premiers inscrits.');
    expect(promesseCourte({ description: '' })).toBe('');
  });
});

describe('fiche détail', () => {
  const ref = mensuelDeReference(CATALOGUE);
  test('Étudiant : badge, prix, mensuel, justificatif requis, pour qui', () => {
    const f = ficheOffre(etu, ref);
    expect(f.badge).toBe('Étudiant');
    expect(f.prix).toEqual({ montant: '69 CHF', unite: '/ mois' });
    expect(f.inclus).toContain('jusqu’à 8 séances / mois');
    expect(f.conditions).toContain('Justificatif étudiant requis');
    // V527: quota mensuel, pas de report
    expect(f.duree).toBe('1 mois, renouvelé automatiquement. Les séances sont valables pendant la période mensuelle en cours et ne sont pas reportées au mois suivant.');
    expect(f.pourQui).toBe('Étudiant·e, avec justificatif');
    expect(f.economie).toBe('');
    expect(f.gratuit).toBe(false);
  });
  test('Fondateurs : 50 places maximum + date dans les conditions, info compacte', () => {
    const f = ficheOffre(fond, ref);
    expect(f.conditions).toEqual(['50 places maximum', 'Jusqu’au 30/09']);
    expect(f.limitee).toBe('47 places restantes · offre jusqu’au 30/09');
  });
  test('Saison 8 mois 1× : économie réelle affichée', () => {
    expect(ficheOffre(s1, ref).economie).toBe('Tu économises 163 CHF par rapport au mensuel');
  });
  test('Carte membre : adhésion incluse, aucune séance', () => {
    const f = ficheOffre(carte, ref);
    expect(f.inclus).toContain('Carte membre de l’association incluse');
    expect(f.seances).toBe('');
  });
  test('essai : gratuit', () => {
    expect(ficheOffre(essai, ref).gratuit).toBe(true);
    expect(ficheOffre(null, ref)).toBeNull();
  });
});

describe('visiteur connecté ou non (décision d’affichage)', () => {
  const avec = (cles) => (k) => (cles.includes(k) ? 'x' : null);
  test('anonyme → parcours conversion', () => { expect(visiteurEstConnecte(avec([]))).toBe(false); });
  test('coach, admin persistant, abonné (jeton), espace → expérience communautaire', () => {
    expect(visiteurEstConnecte(avec(['afroboost_coach_user']))).toBe(true);
    expect(visiteurEstConnecte(avec(['afroboost_admin_persist']))).toBe(true);
    expect(visiteurEstConnecte(avec(['afroboost_subscriber_token']))).toBe(true);
    expect(visiteurEstConnecte(avec(['afroboost_espace_token']))).toBe(true);
  });
  test('une identité de chat seule ne suffit pas', () => {
    expect(visiteurEstConnecte(avec(['afroboost_identity']))).toBe(false);
  });
});
