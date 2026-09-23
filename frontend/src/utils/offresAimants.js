/**
 * OFFRES AIMANTS — la logique PURE du parcours de conversion visiteur.
 *
 * La vitrine ne doit plus montrer 7+ formules d'un coup : trois « aimants »
 * (lancement, saison 8 mois, mensuel de référence), un accès « toutes les
 * offres », et une fiche détail par offre. Tout ce qui est décidé ici est LU
 * sur les documents d'offre servis par /api/offers (billing_mode, duree_mois,
 * stock, places_restantes, countdown_*, pack_sessions) — jamais sur un nom.
 *
 * Miroir volontaire des règles serveur de la landing (`_m1_famille`,
 * `_m1_economie`, `_m1_paiement`…, api/server.py) : la carte visiteur et la
 * page /cours-essai-gratuit-neuchatel disent la même chose.
 */

export const FAMILLE = {
  LANCEMENT: 'lancement',
  SAISON_1X: 'saison_1x',
  SAISON_2X: 'saison_2x',
  MENSUEL: 'mensuel',
  UNITE: 'unite',
  OFFERT: 'offert',
  MEMBRE: 'membre',
  PRODUIT: 'produit',
};

export const SAISON_MOIS = 8;
export const SAISON_2X_ECHEANCES = 2;
export const SAISON_2X_INTERVALLE_MOIS = 4;
const DUREE_DROITS_DEFAUT_MOIS = 2;

const RANG = { lancement: 0, saison_1x: 1, saison_2x: 2, mensuel: 3, unite: 4, membre: 5, produit: 6, offert: 7 };

const BADGES = {
  lancement: 'Offre lancement',
  saison_1x: 'Meilleur prix',
  saison_2x: 'Saison en 2 fois',
  mensuel: 'Le plus flexible',
  offert: 'Premier cours offert',
};

export const nombre = (v, defaut = 0) => {
  const n = parseFloat(v);
  return Number.isFinite(n) ? n : defaut;
};

export const prixUnitaire = (o) => {
  if (!o) return 0;
  return (o.progressive_pricing && o.active_price != null) ? nombre(o.active_price) : nombre(o.price);
};

export const prixFormate = (n) => {
  const v = nombre(n);
  return Number.isInteger(v) ? String(v) : v.toFixed(2).replace(/0$/, '');
};

// V527: une offre RÉCURRENTE (abonnement Stripe) — l'e-mail est demandé AVANT le
// checkout pour empêcher un second abonnement à la même offre (garde 409 serveur).
export const estRecurrente = (o) => modeFacturation(o) !== 'unique';

const modeFacturation = (o) => {
  const m = String((o && o.billing_mode) || 'unique').trim();
  return (m === 'mensuel_auto' || m === 'saison_2x') ? m : 'unique';
};

const dureeMois = (o) => {
  const d = parseInt(o && o.duree_mois, 10);
  return (Number.isFinite(d) && d >= 1 && d <= 24) ? d : null;
};

export const estLimitee = (o) => {
  if (!o) return false;
  const s = o.stock;
  const stockFini = typeof s === 'number' && Number.isFinite(s) && s >= 0;
  return stockFini || !!(o.countdown_enabled && o.countdown_date);
};

export const familleOffre = (o) => {
  if (!o) return FAMILLE.UNITE;
  if (o.isProduct || o.isPhysicalProduct || o.offer_type === 'product') return FAMILLE.PRODUIT;
  if (o.offer_type === 'membership') return FAMILLE.MEMBRE;
  const prix = prixUnitaire(o);
  if (prix <= 0) return FAMILLE.OFFERT;
  if (estLimitee(o)) return FAMILLE.LANCEMENT;
  const mode = modeFacturation(o);
  const duree = dureeMois(o) || 0;
  if (mode === 'unique' && duree >= SAISON_MOIS) return FAMILLE.SAISON_1X;
  if (mode === 'saison_2x') return FAMILLE.SAISON_2X;
  if (mode === 'mensuel_auto') return FAMILLE.MENSUEL;
  return FAMILLE.UNITE;
};

/** Le mensuel de référence : le plus cher des mensuels (hors offre limitée). */
export const mensuelDeReference = (offres) => {
  const mensuels = (offres || []).filter((o) => familleOffre(o) === FAMILLE.MENSUEL);
  if (!mensuels.length) return null;
  return mensuels.reduce((a, b) => (prixUnitaire(b) > prixUnitaire(a) ? b : a));
};

// V526: « Meilleur prix » n'est plus décrété par la famille : il est CALCULÉ.
// Coût par SÉANCE d'une offre payante (prix d'UN paiement / séances ouvertes par ce
// paiement — pack × 4 mois pour la saison en 2 fois) ; null si rien à comparer.
export const coutParSeance = (o) => {
  if (!o) return null;
  const p = prixUnitaire(o);
  const n = parseInt(o.pack_sessions, 10);
  if (!(p > 0) || !(Number.isFinite(n) && n > 0)) return null;
  const f = familleOffre(o);
  if (f === FAMILLE.PRODUIT || f === FAMILLE.MEMBRE) return null;
  return p / (f === FAMILLE.SAISON_2X ? n * SAISON_2X_INTERVALLE_MOIS : n);
};

/** Vrai si `o` a le coût par séance le plus bas parmi TOUTES les offres affichées. */
export const estMeilleurPrix = (o, offres) => {
  const mien = coutParSeance(o);
  if (mien == null) return false;
  return (offres || []).every((x) => {
    const c = coutParSeance(x);
    return c == null || c >= mien - 0.005;
  });
};

const BADGE_SAISON_SINON = 'Saison complète';

export const badgeOffre = (o, mensuelRef, offres) => {
  const f = familleOffre(o);
  if (f === FAMILLE.MENSUEL) {
    if (/tudiant/i.test(String(o.name || ''))) return 'Étudiant';
    return (mensuelRef && o && mensuelRef.id === o.id) ? BADGES.mensuel : '';
  }
  if (f === FAMILLE.SAISON_1X) {
    // V526: badge factuel — « Meilleur prix » seulement si c'est vrai face aux autres formules
    return (offres == null || estMeilleurPrix(o, offres)) ? BADGES.saison_1x : BADGE_SAISON_SINON;
  }
  return BADGES[f] || '';
};

/** Économie RÉELLE sur la saison par rapport au mensuel de référence, sinon null. */
export const economieOffre = (o, mensuelRef) => {
  if (!mensuelRef || !o) return null;
  const f = familleOffre(o);
  const ref = prixUnitaire(mensuelRef) * SAISON_MOIS;
  let total;
  if (f === FAMILLE.SAISON_1X) total = prixUnitaire(o);
  else if (f === FAMILLE.SAISON_2X) total = prixUnitaire(o) * SAISON_2X_ECHEANCES;
  else return null;
  const eco = Math.round((ref - total) * 100) / 100;
  return eco > 0 ? eco : null;
};

const seancesPack = (o) => {
  const n = parseInt(o && o.pack_sessions, 10);
  return Number.isFinite(n) && n > 0 ? n : 0;
};

export const libelleSeances = (o) => {
  const n = seancesPack(o);
  const f = familleOffre(o);
  if (n <= 0) return '';
  if (f === FAMILLE.MENSUEL || (f === FAMILLE.LANCEMENT && modeFacturation(o) === 'mensuel_auto')) {
    return `jusqu’à ${n} séances / mois`;
  }
  if (f === FAMILLE.SAISON_2X) return `jusqu’à ${n} séances / mois (${n * SAISON_2X_INTERVALLE_MOIS} par échéance)`;
  if (f === FAMILLE.SAISON_1X) {
    const d = dureeMois(o) || SAISON_MOIS;
    return `${n} séances sur la saison (env. ${Math.round(n / d)} / mois)`;
  }
  return `${n} séance${n > 1 ? 's' : ''}`;
};

export const libellePaiement = (o) => {
  const mode = modeFacturation(o);
  const f = familleOffre(o);
  if (mode === 'mensuel_auto') return 'Prélèvement automatique chaque mois (carte)';
  // V537 : le délai vient de l'OFFRE (V536 : 1 ou 2 mois), pas de la constante
  // historique — la fiche disait « 4 mois plus tard » sur une offre réglée à 2.
  // Le délai individuel d'un membre, lui, s'affiche dans son espace et au
  // checkout : ici on énonce la règle générale de l'offre, celle qui est vraie
  // pour qui n'a pas de réglage particulier.
  if (mode === 'saison_2x') {
    const n = parseInt(o && o.installment_interval_months, 10);
    const mois = (n === 1 || n === 2) ? n : SAISON_2X_INTERVALLE_MOIS;
    return `2 paiements : à l’inscription, puis ${mois} mois plus tard`;
  }
  if (f === FAMILLE.SAISON_1X) return '1 paiement (carte ou TWINT)';
  if (f === FAMILLE.OFFERT) return 'Offert';
  return 'Paiement unique (carte ou TWINT)';
};

export const libelleEngagement = (o) => {
  const mode = modeFacturation(o);
  const f = familleOffre(o);
  if (mode === 'mensuel_auto') return 'Sans engagement — résiliable à tout moment, accès jusqu’à la fin du mois payé';
  if (f === FAMILLE.SAISON_1X || f === FAMILLE.SAISON_2X) return `Saison de ${SAISON_MOIS} mois`;
  if (f === FAMILLE.OFFERT) return 'Aucun';
  const d = dureeMois(o);
  if (f === FAMILLE.MEMBRE) return `Adhésion de ${d || 12} mois`;
  return `Aucun — valable ${d || DUREE_DROITS_DEFAUT_MOIS} mois`;
};

export const libelleDuree = (o) => {
  const mode = modeFacturation(o);
  const f = familleOffre(o);
  // V527: quota mensuel — pas de report des séances non utilisées (règle validée le 16/09/2026)
  if (mode === 'mensuel_auto') return '1 mois, renouvelé automatiquement. Les séances sont valables pendant la période mensuelle en cours et ne sont pas reportées au mois suivant.';
  if (f === FAMILLE.SAISON_1X || f === FAMILLE.SAISON_2X) return `${SAISON_MOIS} mois`;
  if (f === FAMILLE.OFFERT) return '1 séance';
  const d = dureeMois(o);
  return `${d || DUREE_DROITS_DEFAUT_MOIS} mois`;
};

/**
 * V542 — LE MODE DE PAIEMENT, EN TROIS MOTS. `libellePaiement` est la phrase
 * complète de la FICHE (« Prélèvement automatique chaque mois (carte) ») : dans une
 * carte, elle prend deux lignes et noie le reste. Ici on ne garde que ce qui
 * DIFFÉRENCIE une formule d'une autre. Aucune donnée nouvelle : même source, même
 * `modeFacturation`, seulement plus court.
 */
export const libellePaiementCourt = (o) => {
  const mode = modeFacturation(o);
  const f = familleOffre(o);
  if (mode === 'mensuel_auto') return 'Chaque mois';
  if (mode === 'saison_2x') return 'En 2 paiements';
  if (f === FAMILLE.SAISON_1X) return 'En 1 paiement';
  if (f === FAMILLE.OFFERT) return 'Offert';
  return 'Paiement unique';
};

/**
 * V542 — POURQUOI CELLE-CI PLUTÔT QU'UNE AUTRE, en une ligne.
 *
 * C'est la seule chose que les trois cartes ne disaient pas, et c'est précisément
 * ce qu'on demande à un visiteur de trancher. Rien n'est inventé ici : l'économie
 * est CALCULÉE face au mensuel de référence (`economieOffre`, déjà utilisée par la
 * fiche), et le reste vient de `libelleEngagement` / `libellePourQui`, qui existent
 * depuis V526. Une formule dont on ne sait rien de particulier ne reçoit aucune
 * phrase — mieux vaut une carte plus courte qu'une promesse fabriquée.
 */
export const libelleAvantage = (o, mensuelRef) => {
  if (!o) return '';
  const f = familleOffre(o);
  const eco = economieOffre(o, mensuelRef);
  // Le montant reste CALCULÉ (`economieOffre`) : seule l'unité manquait, alors
  // que la même phrase dans la fiche (`economie`, plus bas) la portait déjà.
  if (eco) return `Économie de ${prixFormate(eco)} CHF sur la saison`;
  // ⚠️ L'ORDRE EST LE FOND DU SUJET. Fondateurs est AUSSI un prélèvement mensuel :
  // s'il passait par la branche « sans engagement », les deux cartes mensuelles
  // diraient la même phrase et on n'aurait rien différencié du tout. Ce qui
  // distingue Fondateurs, c'est à QUI il s'adresse, pas sa fréquence.
  if (f === FAMILLE.LANCEMENT) return libellePourQui(o);
  if (modeFacturation(o) === 'mensuel_auto') return 'Sans engagement, résiliable à tout moment';
  if (f === FAMILLE.SAISON_1X || f === FAMILLE.SAISON_2X) return `Saison complète de ${SAISON_MOIS} mois`;
  return '';
};

export const libellePourQui = (o) => {
  const f = familleOffre(o);
  if (f === FAMILLE.LANCEMENT) return 'Les premiers inscrits de la saison';
  if (f === FAMILLE.SAISON_1X) return 'Tu es décidé·e pour toute la saison';
  if (f === FAMILLE.SAISON_2X) return 'La saison, sans tout payer d’un coup';
  if (f === FAMILLE.MENSUEL) {
    if (/tudiant/i.test(String(o.name || ''))) return 'Étudiant·e, avec justificatif';
    const n = seancesPack(o);
    return (n > 0 && n <= 4) ? 'Une fois par semaine' : 'Tu veux rester libre chaque mois';
  }
  if (f === FAMILLE.MEMBRE) return 'Tu veux soutenir l’association et profiter des avantages membres';
  if (f === FAMILLE.OFFERT) return 'Pour découvrir';
  return 'Pour revenir une fois, sans formule';
};

export const conditionsOffre = (o) => {
  const c = [];
  const f = familleOffre(o);
  if (/tudiant/i.test(String((o && o.name) || ''))) c.push('Justificatif étudiant requis');
  if (f === FAMILLE.LANCEMENT) {
    const s = o.stock;
    if (typeof s === 'number' && s >= 0) c.push(`${s} places maximum`);
    if (o.countdown_enabled && o.countdown_date) c.push(`Jusqu’au ${dateCourte(o.countdown_date)}`);
  }
  if (o && o.requires_active_membership) c.push('Réservé aux membres actifs');
  return c;
};

export const dateCourte = (iso) => {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(iso || ''));
  if (!m) return '';
  return `${m[3]}/${m[2]}`;
};

/** « 47 places restantes · offre jusqu’au 30/09 » — compact, jamais un gros compteur. */
export const infoCompacteLimitee = (o) => {
  if (!o) return '';
  const parts = [];
  if (typeof o.places_restantes === 'number' && Number.isFinite(o.places_restantes)) {
    const p = o.places_restantes;
    parts.push(`${p} place${p > 1 ? 's' : ''} restante${p > 1 ? 's' : ''}`);
  } else if (typeof o.stock === 'number' && o.stock >= 0) {
    parts.push(`${o.stock} places maximum`);
  }
  if (o.countdown_enabled && o.countdown_date) parts.push(`offre jusqu’au ${dateCourte(o.countdown_date)}`);
  return parts.join(' · ');
};

/** Le prix et son unité, comme sur la landing. */
export const prixAffiche = (o) => {
  const f = familleOffre(o);
  const prix = prixUnitaire(o);
  if (prix <= 0) return { montant: 'Offert', unite: '' };
  if (f === FAMILLE.SAISON_2X) return { montant: `2 × ${prixFormate(prix)} CHF`, unite: '' };
  if (f === FAMILLE.SAISON_1X) return { montant: `${prixFormate(prix)} CHF`, unite: '/ saison' };
  if (modeFacturation(o) === 'mensuel_auto') return { montant: `${prixFormate(prix)} CHF`, unite: '/ mois' };
  if (f === FAMILLE.MEMBRE) return { montant: `${prixFormate(prix)} CHF`, unite: '/ an' };
  return { montant: `${prixFormate(prix)} CHF`, unite: '' };
};

/** La première phrase de la description = la promesse courte. */
export const promesseCourte = (o) => {
  const d = String((o && o.description) || '').replace(/\s+/g, ' ').trim();
  if (!d) return '';
  const m = /^(.{10,160}?[.!?])(\s|$)/.exec(d);
  return m ? m[1] : (d.length > 160 ? d.slice(0, 157) + '…' : d);
};

/** Les lignes « ce qui est inclus » d'une fiche — lues sur le document. */
export const inclusOffre = (o) => {
  const l = [];
  const s = libelleSeances(o);
  if (s) l.push(s);
  const f = familleOffre(o);
  if (f === FAMILLE.OFFERT) l.push('Ton premier cours, offert');
  if (o && o.creates_membership) l.push('Carte membre de l’association incluse');
  if (o && o.member_discount_pct > 0) l.push(`${o.member_discount_pct} % de remise pour les membres`);
  if (o && o.max_participants != null) l.push(`${o.max_participants} places par séance`);
  return l;
};

/**
 * La fiche complète d'une offre : tout ce que la modale affiche, dans l'ordre
 * demandé (badge, nom, prix, promesse, inclus, séances, durée, paiement,
 * engagement, conditions, pour qui, avantage réel).
 */
export const ficheOffre = (o, mensuelRef, offres) => {
  if (!o) return null;
  const eco = economieOffre(o, mensuelRef);
  return {
    id: o.id,
    famille: familleOffre(o),
    badge: badgeOffre(o, mensuelRef, offres), // V526: badge saison calculé face aux autres formules
    nom: o.name || '',
    prix: prixAffiche(o),
    promesse: promesseCourte(o),
    inclus: inclusOffre(o),
    seances: libelleSeances(o),
    duree: libelleDuree(o),
    paiement: libellePaiement(o),
    engagement: libelleEngagement(o),
    conditions: conditionsOffre(o),
    pourQui: libellePourQui(o),
    economie: eco ? `Tu économises ${prixFormate(eco)} CHF par rapport au mensuel` : '',
    limitee: infoCompacteLimitee(o),
    gratuit: prixUnitaire(o) <= 0,
  };
};

/**
 * Le regroupement de la vitrine :
 *  - aimants : lancement, saison (8 mois 1× ET 2× sous UNE carte), mensuel de
 *    référence — chacun présent seulement s'il existe ;
 *  - autres : toutes les offres de service (aimants compris, dans l'ordre
 *    commercial), pour le panneau « Voir toutes les offres ».
 * Aucune fusion de données : la carte « saison » garde ses deux offres réelles.
 */
export const regrouperOffres = (offres) => {
  const services = (offres || []).filter((o) => o && familleOffre(o) !== FAMILLE.PRODUIT);
  const mensuelRef = mensuelDeReference(services);
  const lancement = services.filter((o) => familleOffre(o) === FAMILLE.LANCEMENT)
    .sort((a, b) => nombre(a.position, 999) - nombre(b.position, 999))[0] || null;
  const saison1x = services.filter((o) => familleOffre(o) === FAMILLE.SAISON_1X)
    .sort((a, b) => prixUnitaire(a) - prixUnitaire(b))[0] || null;
  const saison2x = services.filter((o) => familleOffre(o) === FAMILLE.SAISON_2X)
    .sort((a, b) => prixUnitaire(a) - prixUnitaire(b))[0] || null;
  const aimants = [];
  if (lancement) aimants.push({ cle: 'lancement', offre: lancement, offres: [lancement] });
  if (saison1x || saison2x) {
    const choix = [saison1x, saison2x].filter(Boolean);
    const depuis = Math.min(...choix.map((o) => (familleOffre(o) === FAMILLE.SAISON_2X ? prixUnitaire(o) * SAISON_2X_ECHEANCES : prixUnitaire(o))));
    // V526: le badge de la carte saison est calculé, jamais décrété
    const badgeSaison = (choix.some((o) => estMeilleurPrix(o, services))) ? BADGES.saison_1x : BADGE_SAISON_SINON;
    aimants.push({ cle: 'saison', offre: saison1x || saison2x, offres: choix, depuis, badge: badgeSaison });
  }
  if (mensuelRef) aimants.push({ cle: 'mensuel', offre: mensuelRef, offres: [mensuelRef] });
  const ordre = (o) => [RANG[familleOffre(o)] != null ? RANG[familleOffre(o)] : 9,
    (mensuelRef && o.id === mensuelRef.id) ? 0 : 1, nombre(o.position, 999)];
  const autres = services.slice().sort((a, b) => {
    const x = ordre(a); const y = ordre(b);
    for (let i = 0; i < x.length; i += 1) if (x[i] !== y[i]) return x[i] - y[i];
    return String(a.name || '').localeCompare(String(b.name || ''));
  });
  return { aimants, autres, mensuelRef };
};

/**
 * Un visiteur est « connecté » s'il a une identité de coach, un jeton d'abonné
 * ou une session d'espace. Décision d'AFFICHAGE seulement (parcours conversion
 * contre expérience communautaire) — aucun droit n'en dépend.
 */
export const visiteurEstConnecte = (lire) => {
  const get = typeof lire === 'function' ? lire : (k) => {
    try { return window.localStorage.getItem(k); } catch (e) { return null; }
  };
  if (get('afroboost_coach_user')) return true;
  if (get('afroboost_admin_persist')) return true;
  if (get('afroboost_subscriber_token')) return true;
  if (get('afroboost_espace_token')) return true;
  return false;
};

/** Le libellé « Dès X CHF » de la carte saison. */
export const libelleDepuis = (aimant) => {
  if (!aimant || aimant.cle !== 'saison') return '';
  return `Dès ${prixFormate(aimant.depuis)} CHF`;
};
