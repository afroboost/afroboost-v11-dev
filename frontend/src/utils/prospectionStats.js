/**
 * V595 — PROSPECTION : Vue d'ensemble + Résultats. FONCTIONS PURES, LECTURE SEULE.
 *
 * AUCUN CHIFFRE INVENTÉ. Tout se recalcule à chaque lecture depuis :
 *   - les fiches `GET /partner-prospects` (statut, ville, catégorie, vague, canal, dates) ;
 *   - les rendez-vous `GET /calendar-events` de type `appointment` liés à une fiche ;
 *   - les compteurs de conversations `GET /prospect-inbound`.
 * Rien n'est stocké, rien n'est écrit.
 *
 * TROIS CHAMPS N'EXISTENT PAS EN BASE ET SONT DÉDUITS, SANS DEVINER :
 *   - NICHE : la lettre de la vague « GV 10-2026 — X … » quand elle existe, sinon la
 *     catégorie (écoles → D, festivals/organisateurs → C, étudiants/associations → B,
 *     commerces/bars/restaurants/fitness/influenceurs → A). E et F n'existent QUE par
 *     leur vague : aucune catégorie ne permet de dire « entreprise » ou « santé ».
 *   - PAYS : « France » si la ville ou la vague le dit, OU si la ville principale est une
 *     ville française connue (6 festivals 2027 sont notés « Paris », « Besançon »… sans
 *     « (France) »). Sinon Suisse — liste vérifiée sur les 398 fiches le 09/10/2026.
 *     ⚠️ « (FR) » veut dire canton de Fribourg, jamais France.
 *   - CANAL : `preferred_channel` est du texte libre (« Visite / DM », « E-mail (…) / WhatsApp ») ;
 *     on retient le PREMIER canal cité, celui par lequel on commence.
 *
 * LES ÉTAPES DE L'ENTONNOIR sont lues sur la fiche :
 *   contacté = statut ≠ « à contacter » ou premier envoi daté ;
 *   réponse  = statut répondu / intéressé / refusé, ou `replied_at` ;
 *   intéressé = statut « intéressé » ;
 *   CHAQUE ÉTAPE EST STRICTE, rien n'est déduit d'une autre : une fiche rattachée à un
 *   partenaire par un autre chemin (Akoko Tresses, encore « à contacter ») compte en
 *   « accepté » sans être comptée « contactée » ni « intéressée ».
 *   rendez-vous = au moins un rendez-vous réel (non annulé) dans le calendrier ;
 *   accepté  = statut « accepte » de la fiche (V595d) — JAMAIS `partner_id` seul : un
 *              partenaire créé pour préparer un lien / QR (niveau « Découverte ») n'est
 *              pas un accord commercial. Ce statut n'existe pas encore : 0 aujourd'hui ;
 *   refusé   = statut « refusé » ;
 *   RÉPONSE inclut tous ceux qui ont répondu, même refusés ensuite (une fois chacun) ;
 *   sans réponse = contacté sans réponse.
 */

// V598 : six niches D'ORIGINE seulement — repli d'affichage et clés historiques. La liste
// réelle (renommages, niches ajoutées) vient du serveur : hooks/useNichesProspection.
export const NICHES = [
  { id: 'A', libelle: 'Partenaires locaux' },
  { id: 'B', libelle: 'Étudiants / associations' },
  { id: 'C', libelle: 'Festivals' },
  { id: 'D', libelle: 'Écoles de danse' },
  { id: 'E', libelle: 'Entreprises' },
  { id: 'F', libelle: 'Santé / mamans' },
];

export const CANAUX = [
  { id: 'email', libelle: 'E-mail' },
  { id: 'instagram', libelle: 'Instagram' },
  { id: 'formulaire', libelle: 'Formulaire' },
  { id: 'telephone', libelle: 'Téléphone' },
  { id: 'visite', libelle: 'Visite' },
  { id: 'autre', libelle: 'Autres (WhatsApp, LinkedIn, Facebook…)' },
  { id: 'a_trouver', libelle: 'Canal à trouver' },
];

export const PERIODES = [
  { id: '7j', libelle: '7 jours', jours: 7 },
  { id: '30j', libelle: '30 jours', jours: 30 },
  { id: '3m', libelle: '3 mois', jours: 92 },
  { id: 'tout', libelle: 'Tout', jours: null },
];

const CATEGORIE_NICHE = {
  ecole_danse: 'D',
  festival: 'C', organisateur_evenement: 'C',
  communaute_etudiante: 'B', association: 'B',
  restaurant: 'A', bar: 'A', commerce: 'A', fitness: 'A', influenceur: 'A',
};

function txt(v) { return typeof v === 'string' ? v.trim() : ''; }

export function nicheDe(p) {
  const vague = txt((p || {}).wave);
  const m = vague.match(/^GV\b.*?—\s*([A-F])\b/);
  if (m) return m[1];
  if (/festival/i.test(vague)) return 'C';
  return CATEGORIE_NICHE[txt((p || {}).category)] || null;
}

const VILLES_FRANCE = new Set([
  'paris', 'ivry-sur-seine', 'lyon', 'strasbourg', 'mulhouse', 'colmar', 'illzach', 'sausheim', 'wattwiller',
  'belfort', 'besançon', 'montbéliard', 'audincourt', 'exincourt', 'bart', 'pontarlier', 'morteau', 'dijon',
  'annecy', 'annemasse', 'thonon-les-bains', 'évian-les-bains', 'saint-louis', 'huningue',
]);

export function paysDe(p) {
  if (/france/i.test(`${txt((p || {}).city)} ${txt((p || {}).wave)}`)) return 'France';
  return VILLES_FRANCE.has(villeDe(p).toLowerCase()) ? 'France' : 'Suisse';
}

/** « Lyon (France) — Meyzieu / Bron » → « Lyon » ; « Carouge (GE) & Nyon » → « Carouge ». */
export function villeDe(p) {
  const brut = txt((p || {}).city);
  if (!brut) return '';
  const v = brut.split(/\s*[(/—&,]\s*|\s+-\s+/)[0].trim();
  return v || brut;
}

const MOTIFS_CANAL = [
  ['a_trouver', /à (trouver|identifier|obtenir)|a (trouver|identifier)/i],
  ['email', /e-?mail|courriel/i],
  ['instagram', /instagram|\binsta\b|\bdm\b/i],
  ['formulaire', /formulaire|site institutionnel|appel à projets|candidature/i],
  ['telephone', /t[ée]l[ée]phone|\bt[ée]l\b|\bappel\b/i],
  ['visite', /visite/i],
  ['autre', /whatsapp|linkedin|facebook|tiktok|\bvia\b|\bsite\b/i],
];

export function canalDe(p) {
  const t = txt((p || {}).preferred_channel);
  if (!t) return 'a_trouver';
  // « E-mail (à obtenir) » reste un e-mail à trouver, pas un e-mail utilisable.
  if (/^[^/]*\((à|a) obtenir\)/i.test(t) || /^(à|a) (trouver|identifier)/i.test(t)) return 'a_trouver';
  let meilleur = null;
  MOTIFS_CANAL.forEach(([id, re]) => {
    if (id === 'a_trouver') return;
    const m = re.exec(t);
    if (m && (meilleur === null || m.index < meilleur.index)) meilleur = { id, index: m.index };
  });
  return meilleur ? meilleur.id : 'autre';
}

// Toute fiche passée par une réponse, quel que soit son statut final.
const STATUTS_REPONSE = ['repondu', 'interesse', 'refuse', 'accepte'];

export function dateContact(p) { return (p && (p.first_contact_sent_at || p.first_contact_at || p.last_contact_at)) || null; }

export function etapes(p, rdvParFiche) {
  const s = txt((p || {}).status);
  const accepte = s === 'accepte';
  const contacte = (s && s !== 'a_contacter') || !!dateContact(p);
  const reponse = STATUTS_REPONSE.includes(s) || !!(p && p.replied_at);
  const interesse = s === 'interesse';
  const rdv = !!(rdvParFiche && p && (rdvParFiche[p.id] || rdvParFiche[p.ref]));
  return {
    a_contacter: !contacte, contacte, reponse, interesse, rdv, accepte,
    refuse: s === 'refuse', sans_reponse: contacte && !reponse,
  };
}

function depuisISO(periodeId, maintenant) {
  const per = PERIODES.find((x) => x.id === periodeId);
  if (!per || per.jours === null) return null;
  return new Date((maintenant || Date.now()) - per.jours * 86400000).toISOString();
}

function dansPeriode(iso, depuis) {
  if (depuis === null) return true;
  if (!iso) return false;
  const t = Date.parse(String(iso));
  return Number.isFinite(t) && new Date(t).toISOString() >= depuis;
}

export const COMPTEURS_VIDES = {
  total: 0, a_contacter: 0, contacte: 0, reponse: 0, interesse: 0, rdv: 0,
  accepte: 0, refuse: 0, sans_reponse: 0,
};

/**
 * Compte une liste de fiches. `periode` ≠ 'tout' : chaque étape n'est comptée que si
 * SA date tombe dans la période (création, premier contact, réponse, intérêt,
 * rendez-vous). Une étape SANS date n'entre que dans « Tout » — on ne lui en invente pas.
 */
export function compter(prospects, { rdvParFiche = {}, periode = 'tout', maintenant } = {}) {
  const depuis = depuisISO(periode, maintenant);
  const c = { ...COMPTEURS_VIDES };
  (prospects || []).forEach((p) => {
    const e = etapes(p, rdvParFiche);
    const rdvDate = (rdvParFiche[p.id] || rdvParFiche[p.ref] || null);
    if (dansPeriode(p.created_at, depuis)) c.total += 1;
    if (e.a_contacter && dansPeriode(p.created_at, depuis)) c.a_contacter += 1;
    if (e.contacte && dansPeriode(dateContact(p), depuis)) c.contacte += 1;
    if (e.reponse && dansPeriode(p.replied_at, depuis)) c.reponse += 1;
    if (e.interesse && dansPeriode(p.interested_at, depuis)) c.interesse += 1;
    if (e.rdv && dansPeriode(rdvDate, depuis)) c.rdv += 1;
    if (e.accepte && depuis === null) c.accepte += 1;
    if (e.refuse && depuis === null) c.refuse += 1;
    if (e.sans_reponse && dansPeriode(dateContact(p), depuis)) c.sans_reponse += 1;
  });
  return c;
}

/** Pourcentage arrondi, ou null quand le dénominateur est nul (affiché « — »). */
export function taux(n, d) {
  if (!d) return null;
  return Math.round((n / d) * 1000) / 10;
}

export function tauxDe(c) {
  return {
    reponse: taux(c.reponse, c.contacte),
    interet: taux(c.interesse, c.reponse),
    rdv: taux(c.rdv, c.interesse),
    conversion: taux(c.accepte, c.contacte),
  };
}

/** Regroupe et compte. Rend [{cle, libelle, c}] trié par total décroissant. */
export function grouper(prospects, cleDe, options, libelles) {
  const groupes = new Map();
  (prospects || []).forEach((p) => {
    const cle = cleDe(p) || '';
    if (!groupes.has(cle)) groupes.set(cle, []);
    groupes.get(cle).push(p);
  });
  return Array.from(groupes.entries())
    .map(([cle, liste]) => ({ cle, libelle: (libelles && libelles[cle]) || cle || 'Non renseigné', n: liste.length, c: compter(liste, options) }))
    .sort((a, b) => b.n - a.n || String(a.libelle).localeCompare(String(b.libelle), 'fr'));
}

export const LIBELLES_NICHE = NICHES.reduce((m, n) => ({ ...m, [n.id]: `${n.id} — ${n.libelle}` }), { '': 'Non classé' });

/** V598 — la lettre d'une niche, déduite de son ordre : 1 → A … 26 → Z, 27 → AA. PURE. */
export function lettreNiche(ordre) {
  let n = Math.max(1, Math.round(Number(ordre) || 1));
  let out = '';
  while (n > 0) { const r = (n - 1) % 26; out = String.fromCharCode(65 + r) + out; n = Math.floor((n - 1) / 26); }
  return out;
}

/**
 * V599 — LA NICHE D'UN PROSPECT, lue sur son `niche_id` (l'id stable d'une niche de
 * `prospection_niches`) et rendue comme sa CLÉ (« A »…« F », ou l'id d'une niche
 * créée) — la même clé que les médias, les liens et les libellés. Une fiche pas
 * encore rattachée retombe sur la règle historique (nicheDe). PURE.
 */
export function cleNicheProspect(niches) {
  const parId = (niches || []).reduce((m, n) => ({ ...m, [n.id]: n.cle }), {});
  return (p) => {
    const id = p && p.niche_id;
    if (id) return parId[id] || '';
    return nicheDe(p);
  };
}

/** V598 — { clé: « G — Seniors » } à partir de la liste du serveur (repli : les six d'origine). PURE. */
export function libellesNiches(niches) {
  // V600 : une niche dans la Corbeille reste NOMMÉE (fiches historiques), avec la mention.
  return (niches || []).reduce((m, n) => ({ ...m, [n.cle]: `${lettreNiche(n.ordre)} — ${n.nom}${n.supprimee ? ' (supprimée)' : ''}` }), { '': 'Non classé' });
}
export const LIBELLES_CANAL = CANAUX.reduce((m, n) => ({ ...m, [n.id]: n.libelle }), {});

/** « Campagne » = la vague d'import, seul regroupement qui existe sur TOUTES les fiches. */
export function campagneDe(p) {
  const v = txt((p || {}).wave);
  if (!v) return 'Premières fiches (sans vague)';
  return v.replace(/^GV 10-2026 — [A-F]\s*/, 'Grande vague — ').replace(/^Grande vague — $/, 'Grande vague');
}

/** Les rendez-vous RÉELS par fiche : {prospect_id: date du premier}. Annulés exclus. */
export function rdvParFicheDe(evenements) {
  const m = {};
  (evenements || []).forEach((e) => {
    if (!e || e.event_type !== 'appointment' || e.is_deleted) return;
    if (txt(e.status) === 'annule') return;
    const id = txt(e.prospect_id);
    if (!id) return;
    const d = e.starts_at || e.created_at || null;
    if (!m[id] || (d && d < m[id])) m[id] = d || m[id] || '0';
  });
  return m;
}
