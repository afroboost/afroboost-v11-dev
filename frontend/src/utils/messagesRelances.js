/**
 * V588 — CAMPAGNES → PROSPECTION → MESSAGES & RELANCES. LECTURE SEULE, FONCTIONS PURES.
 *
 * CE FICHIER NE DÉCIDE RIEN, IL LIT. Les vérités viennent toutes du serveur :
 *   - l'ACTION de campagne (`prospect_campaign_actions`) : textes approuvés
 *     `message_j0/j3/j7`, `sent_at`, échéances `j3_due_at`/`j7_due_at`,
 *     `j3_sent_at`/`j7_sent_at`, annulations `jX_annule_le` + motif, `replied_at`,
 *     rebond `bounce_type` ;
 *   - la CAMPAGNE : objets approuvés `subject_j0/j3/j7` ;
 *   - la CONVERSATION (`GET /prospect-inbound`) : réponses reçues, état commercial
 *     (dont « refus »), dernière réponse envoyée par Afroboost ;
 *   - la FICHE prospect : son statut.
 * Rien n'est recopié ni stocké : l'écran recalcule à chaque lecture.
 *
 * ⚠️ LES TEXTES SONT CEUX DE L'ACTION, JAMAIS CEUX DE LA FICHE. La fiche prospect
 * porte aussi `j3_message`/`j7_message` : ce sont des brouillons NON approuvés.
 * Le moteur P3-R2 n'envoie que `message_j3`/`message_j7` de l'action (empreinte).
 *
 * LES RÈGLES SUIVENT CELLES DU MOTEUR (`p3r2_garde_relance`), sans les remplacer :
 * une réponse, un refus, un rebond permanent, une exclusion ou une reprise en main
 * humaine arrêtent les relances ; le J+7 n'est possible que 4 jours après un J+3
 * réellement parti. L'écran n'envoie rien et n'active rien.
 */

export const ETATS = {
  A_ENVOYER: 'a_envoyer',
  PREVU: 'prevu',
  EN_RETARD: 'en_retard',
  ENVOYE: 'envoye',
  REPONDU: 'repondu',
  STOPPE: 'stoppe',
  REBOND: 'rebond',
  REFUS: 'refus',
  MANUEL: 'manuel',
  SANS_OBJET: 'sans_objet',
};

export const LIBELLES_ETAT = {
  a_envoyer: 'À envoyer',
  prevu: 'Prévu',
  en_retard: 'En retard',
  envoye: 'Envoyé',
  repondu: 'Répondu',
  stoppe: 'Stoppé',
  rebond: 'Rebond',
  refus: 'Refus',
  manuel: 'À faire manuellement',
  sans_objet: '—',
};

export const SUIVI_MANUEL_INDISPONIBLE = 'Suivi manuel non encore disponible';

export const FILTRES = [
  { id: 'tous', libelle: 'Tous' },
  { id: 'a_envoyer', libelle: 'À envoyer' },
  { id: 'en_retard', libelle: 'J+3 en retard' },
  { id: 'envoyes', libelle: 'Envoyés' },
  { id: 'repondus', libelle: 'Répondus' },
  { id: 'stoppes', libelle: 'Stoppés' },
  { id: 'manuel', libelle: 'Manuel' },
];

export const FILTRES_CANAL = [
  { id: 'tous', libelle: 'Tous canaux' },
  { id: 'email', libelle: 'E-mail' },
  { id: 'whatsapp', libelle: 'WhatsApp' },
  { id: 'dm', libelle: 'Instagram / DM' },
  { id: 'autre', libelle: 'Autres' },
];

/* Le seul canal que le moteur sait envoyer (`P3S3D_CANAUX_AUTOMATISABLES`). */
const CANAL_AUTO = 'email';
/* `P3R2_ECART_J3_J7_JOURS` — le J+7 attend 4 jours après un J+3 PARTI. */
const ECART_J3_J7_JOURS = 4;
const JOUR_MS = 86400000;

const LIBELLES_CANAL = {
  email: 'E-mail', whatsapp: 'WhatsApp', instagram: 'Instagram', facebook: 'Facebook',
  tiktok: 'TikTok', formulaire: 'Formulaire', telephone: 'Téléphone', visite: 'Visite',
  aucun: 'Aucun canal',
};

const LIBELLES_STATUT_PROSPECT = {
  a_contacter: 'À contacter', contacte: 'Contacté', repondu: 'Répondu', interesse: 'Intéressé',
  partenaire: 'Partenaire', refus: 'Refus', exclu: 'Exclu', pause: 'En pause',
};

export function instant(iso) {
  if (!iso) return NaN;
  const t = Date.parse(String(iso));
  return Number.isFinite(t) ? t : NaN;
}

function texte(v) { return typeof v === 'string' ? v.trim() : ''; }

export function libelleCanal(canal) {
  const c = texte(canal).toLowerCase();
  return LIBELLES_CANAL[c] || (c ? c.charAt(0).toUpperCase() + c.slice(1) : '—');
}

export function libelleStatutProspect(statut) {
  const s = texte(statut).toLowerCase();
  return LIBELLES_STATUT_PROSPECT[s] || (s || '—');
}

/** E-mail / WhatsApp / DM (Instagram, Facebook, TikTok) / autre. */
export function familleCanal(canal) {
  const c = texte(canal).toLowerCase();
  if (c === 'email') return 'email';
  if (c === 'whatsapp') return 'whatsapp';
  if (c === 'instagram' || c === 'facebook' || c === 'tiktok' || c === 'dm') return 'dm';
  return 'autre';
}

export function organisationDe(action, conversation) {
  const a = action || {};
  const orgs = Array.isArray(a.organisations) ? a.organisations.filter(Boolean) : [];
  if (orgs.length) return orgs.join(' · ');
  if (typeof a.organisations === 'string' && a.organisations.trim()) return a.organisations.trim();
  return texte((conversation || {}).organisation) || texte(a.recipient_key) || '—';
}

function estRebondPermanent(a) { return texte(a.bounce_type).toLowerCase() === 'permanent'; }
function estRefus(conv) { return !!conv && texte(conv.statut_commercial) === 'refus'; }
function aRepondu(a, conv) { return !!a.replied_at || !!(conv && (conv.nb_messages || 0) > 0); }
function estAutomatique(a) {
  return texte(a.execution_type) === 'AUTO' && texte(a.channel).toLowerCase() === CANAL_AUTO;
}

/** L'étape J0 d'une action. */
export function etapeJ0(action, campagne) {
  const a = action || {};
  const base = {
    etape: 'j0', objet: texte((campagne || {}).subject_j0), message: a.message_j0 || '',
    canal: a.channel || '', date_prevue: null, date_envoi: a.sent_at || null,
    motif: '', retard_jours: 0,
  };
  if (a.sent_at) {
    if (texte(a.bounce_type)) {
      return {
        ...base, etat: ETATS.REBOND,
        motif: estRebondPermanent(a)
          ? 'Rebond permanent : adresse morte, relances annulées'
          : `Rebond temporaire (${texte(a.bounce_type)}) : non bloquant`,
      };
    }
    return { ...base, etat: ETATS.ENVOYE };
  }
  if (texte(a.statut) === 'exclu') return { ...base, etat: ETATS.STOPPE, motif: 'Exclu de la campagne' };
  if (texte(a.statut) === 'bloque' || texte(a.execution_type) === 'BLOQUE') {
    return { ...base, etat: ETATS.STOPPE, motif: texte(a.execution_reason) || 'Aucun canal de contact exploitable' };
  }
  if (!estAutomatique(a)) return { ...base, etat: ETATS.MANUEL, motif: SUIVI_MANUEL_INDISPONIBLE };
  return { ...base, etat: ETATS.A_ENVOYER };
}

/** Échéance RÉELLE d'une relance (le J+7 attend 4 jours après un J+3 parti). */
export function echeanceRelance(action, etape) {
  const a = action || {};
  if (etape === 'j3') return a.j3_due_at || null;
  const j3 = instant(a.j3_sent_at);
  if (!Number.isFinite(j3)) return null;
  const apresJ3 = j3 + ECART_J3_J7_JOURS * JOUR_MS;
  const nominale = instant(a.j7_due_at);
  return new Date(Number.isFinite(nominale) ? Math.max(nominale, apresJ3) : apresJ3).toISOString();
}

/** L'étape J+3 ou J+7 d'une action. `maintenant` = horodatage en ms. */
export function etapeRelance(action, campagne, etape, conversation, maintenant) {
  const a = action || {};
  const base = {
    etape, objet: texte((campagne || {})[`subject_${etape}`]), message: a[`message_${etape}`] || '',
    canal: a.channel || '', date_prevue: null, date_envoi: a[`${etape}_sent_at`] || null,
    motif: '', retard_jours: 0,
  };
  if (!a.sent_at) {
    return { ...base, etat: ETATS.SANS_OBJET,
      motif: estAutomatique(a) ? 'Après le J0' : 'Aucune relance automatique sur ce canal' };
  }
  if (a[`${etape}_sent_at`]) return { ...base, etat: ETATS.ENVOYE };

  const annule = a[`${etape}_annule_le`];
  if (annule) {
    const motifBrut = texte(a[`${etape}_annule_motif`]);
    let etat = ETATS.STOPPE;
    let motif = motifBrut ? `Annulée : ${motifLisible(motifBrut)}` : 'Annulée';
    if (estRefus(conversation)) { etat = ETATS.REFUS; motif = 'Annulée : refus exprimé dans la réponse'; } else if (/reponse/i.test(motifBrut)) { etat = ETATS.REPONDU; motif = 'Annulée : réponse reçue'; } else if (/rebond/i.test(motifBrut)) { etat = ETATS.REBOND; motif = 'Annulée : rebond permanent'; }
    return { ...base, etat, motif, date_annulation: annule };
  }
  if (estRefus(conversation)) return { ...base, etat: ETATS.REFUS, motif: 'Refus exprimé dans la réponse' };
  if (aRepondu(a, conversation)) return { ...base, etat: ETATS.REPONDU, motif: 'Réponse reçue : la conversation prime' };
  if (estRebondPermanent(a)) return { ...base, etat: ETATS.REBOND, motif: 'Rebond permanent' };
  if (a.paused_at || a.interesse_at) return { ...base, etat: ETATS.STOPPE, motif: 'Suivi humain en cours' };
  if (texte(a.statut) === 'exclu') return { ...base, etat: ETATS.STOPPE, motif: 'Exclu de la campagne' };
  if (!estAutomatique(a)) return { ...base, etat: ETATS.MANUEL, motif: SUIVI_MANUEL_INDISPONIBLE };
  if (!texte(base.message)) return { ...base, etat: ETATS.STOPPE, motif: 'Aucun texte approuvé pour cette étape' };

  const echeance = echeanceRelance(a, etape);
  if (!echeance) {
    return { ...base, etat: ETATS.PREVU, motif: `${ECART_J3_J7_JOURS} jours après l'envoi du J+3` };
  }
  const t = instant(echeance);
  if (Number.isFinite(t) && Number.isFinite(maintenant) && t <= maintenant) {
    return { ...base, etat: ETATS.EN_RETARD, date_prevue: echeance,
      retard_jours: Math.floor((maintenant - t) / JOUR_MS),
      motif: 'Non envoyée : les relances sont fermées' };
  }
  return { ...base, etat: ETATS.PREVU, date_prevue: echeance };
}

const ETATS_STOP = [ETATS.REFUS, ETATS.REBOND, ETATS.STOPPE];

/** Une ligne de l'onglet = un destinataire (une action de campagne). */
export function ligneRelance(action, campagne, conversation, prospectsParRef, maintenant) {
  const a = action || {};
  const conv = conversation || null;
  const j0 = etapeJ0(a, campagne);
  const j3 = etapeRelance(a, campagne, 'j3', conv, maintenant);
  const j7 = etapeRelance(a, campagne, 'j7', conv, maintenant);

  const refs = Array.isArray(a.prospect_ids) ? a.prospect_ids : [];
  const fiche = refs.map((r) => (prospectsParRef || {})[r]).find(Boolean) || null;

  let etat;
  let motifArret = '';
  if (estRefus(conv)) { etat = ETATS.REFUS; motifArret = 'Refus exprimé dans la réponse'; } else if (aRepondu(a, conv)) { etat = ETATS.REPONDU; motifArret = 'Réponse reçue : relances arrêtées'; } else if (estRebondPermanent(a)) { etat = ETATS.REBOND; motifArret = 'Rebond permanent : adresse morte'; } else if (j0.etat === ETATS.STOPPE) { etat = ETATS.STOPPE; motifArret = j0.motif; } else if (a.paused_at || a.interesse_at) { etat = ETATS.STOPPE; motifArret = 'Suivi humain en cours'; } else if (j0.etat === ETATS.MANUEL) { etat = ETATS.MANUEL; } else if (j0.etat === ETATS.A_ENVOYER) { etat = ETATS.A_ENVOYER; } else if (j3.etat === ETATS.EN_RETARD || j7.etat === ETATS.EN_RETARD) { etat = ETATS.EN_RETARD; } else if (j3.etat === ETATS.PREVU || j7.etat === ETATS.PREVU) { etat = ETATS.PREVU; } else { etat = ETATS.ENVOYE; }

  let prochaineAction = '—';
  let prochaineDate = null;
  if (etat === ETATS.REFUS) prochaineAction = 'Aucune relance (refus)';
  else if (etat === ETATS.REPONDU) {
    prochaineAction = conv && texte(conv.statut_commercial) === 'a_repondre'
      ? 'Répondre (Conversations partenaires)' : 'Suivre la conversation';
  } else if (etat === ETATS.REBOND || etat === ETATS.STOPPE) prochaineAction = 'Aucune';
  else if (etat === ETATS.MANUEL) prochaineAction = `Contact manuel : ${libelleCanal(a.channel)}`;
  else if (etat === ETATS.A_ENVOYER) prochaineAction = 'Envoi du J0';
  else if (etat === ETATS.EN_RETARD) {
    const e = j3.etat === ETATS.EN_RETARD ? j3 : j7;
    prochaineAction = `${e.etape === 'j3' ? 'J+3' : 'J+7'} en retard (relances fermées)`;
    prochaineDate = e.date_prevue;
  } else if (etat === ETATS.PREVU) {
    const e = j3.etat === ETATS.PREVU ? j3 : j7;
    prochaineAction = `${e.etape === 'j3' ? 'J+3' : 'J+7'} prévu`;
    prochaineDate = e.date_prevue;
  } else prochaineAction = 'Attendre une réponse';

  const recus = (conv && Array.isArray(conv.messages_recus)) ? conv.messages_recus : [];
  const premiereReponse = a.replied_at
    || recus.map((m) => m && m.received_at).filter(Boolean).sort()[0] || null;

  return {
    id: a.id,
    action: a,
    conversation: conv,
    organisation: organisationDe(a, conv),
    reference: texte(a.recipient_key),
    canal: a.channel || '',
    famille: familleCanal(a.channel),
    statutProspect: fiche ? fiche.status : '',
    j0, j3, j7,
    etat,
    motifArret,
    prochaineAction,
    prochaineDate,
    reponseLe: premiereReponse,
    statutCommercial: conv ? texte(conv.statut_commercial) : '',
  };
}

/** Toutes les lignes d'une campagne. `conversations` = celles de `/prospect-inbound`. */
export function lignesRelances(actions, campagne, conversations, prospects, maintenant) {
  const parAction = {};
  (conversations || []).forEach((c) => { if (c && c.action_id) parAction[c.action_id] = c; });
  const parRef = {};
  (prospects || []).forEach((p) => { if (p && p.ref) parRef[p.ref] = p; });
  return (actions || []).map((a) => ligneRelance(a, campagne, parAction[a.id], parRef, maintenant));
}

export function compteursRelances(lignes) {
  const L = lignes || [];
  const n = (f) => L.filter(f).length;
  return {
    total: L.length,
    j0Envoyes: n((l) => !!l.action.sent_at),
    j3AVenir: n((l) => l.j3.etat === ETATS.PREVU),
    j3EnRetard: n((l) => l.j3.etat === ETATS.EN_RETARD),
    j7AVenir: n((l) => l.j7.etat === ETATS.PREVU),
    reponses: n((l) => l.etat === ETATS.REPONDU || l.etat === ETATS.REFUS),
    stoppes: n((l) => ETATS_STOP.includes(l.etat)),
    manuel: n((l) => l.etat === ETATS.MANUEL),
  };
}

export function filtrerRelances(lignes, filtre, canal) {
  const f = filtre || 'tous';
  const c = canal || 'tous';
  return (lignes || []).filter((l) => {
    if (c !== 'tous' && l.famille !== c) return false;
    switch (f) {
      case 'a_envoyer': return l.etat === ETATS.A_ENVOYER;
      case 'en_retard': return l.j3.etat === ETATS.EN_RETARD;
      case 'envoyes': return !!l.action.sent_at;
      case 'repondus': return l.etat === ETATS.REPONDU || l.etat === ETATS.REFUS;
      case 'stoppes': return ETATS_STOP.includes(l.etat);
      case 'manuel': return l.etat === ETATS.MANUEL;
      default: return true;
    }
  });
}

/** Ordre d'affichage : ce qui demande de l'attention d'abord, puis l'organisation. */
const RANG = { en_retard: 0, repondu: 1, refus: 2, a_envoyer: 3, prevu: 4, envoye: 5, manuel: 6, rebond: 7, stoppe: 8 };
export function trierRelances(lignes) {
  return [...(lignes || [])].sort((x, y) => {
    const r = (RANG[x.etat] ?? 9) - (RANG[y.etat] ?? 9);
    if (r) return r;
    if (x.etat === ETATS.EN_RETARD && y.etat === ETATS.EN_RETARD) {
      const d = (y.j3.retard_jours || 0) - (x.j3.retard_jours || 0);
      if (d) return d;
    }
    return x.organisation.localeCompare(y.organisation, 'fr');
  });
}

/* Les motifs sont écrits SANS accents en base (« reponse recue ») : on les rend lisibles. */
const MOTIFS_LISIBLES = { 'reponse recue': 'réponse reçue', 'rebond permanent': 'rebond permanent' };
export function motifLisible(motif) {
  const m = texte(motif);
  return MOTIFS_LISIBLES[m.toLowerCase()] || m;
}

/** Le nom humain d'une campagne (jamais son identifiant si un nom existe). */
export function nomCampagne(campagne) {
  const c = campagne || {};
  return texte(c.name) || texte(c.nom) || texte(c.label) || texte(c.id) || '—';
}

function libEtape(etape) { return etape === 'j3' ? 'J+3' : etape === 'j7' ? 'J+7' : 'J0'; }

/**
 * La chronologie d'UN destinataire, à partir des seules données existantes.
 * `notes` = celles de `GET /prospect-inbound/{id}/notes` (facultatives).
 */
export function chronologie(ligne, notes) {
  const l = ligne || {};
  const a = l.action || {};
  const conv = l.conversation;
  const ev = [];
  const ajouter = (quand, titre, detail, genre) => { if (quand) ev.push({ quand, titre, detail: detail || '', genre: genre || 'info' }); };

  if (a.sent_at) {
    ajouter(a.sent_at, `J0 envoyé (${libelleCanal(a.channel)})`, l.j0 && l.j0.objet, 'envoi');
    if (a.provider_message_id) ajouter(a.sent_at, 'Accepté par Resend', '', 'info');
  }
  if (a.bounced_at || texte(a.bounce_type)) {
    ajouter(a.bounced_at || a.updated_at, `Rebond ${texte(a.bounce_type) || ''}`.trim(),
      estRebondPermanent(a) ? 'Adresse morte : relances annulées' : 'Temporaire : non bloquant', 'stop');
  }
  ['j3', 'j7'].forEach((etape) => {
    const e = l[etape] || {};
    if (e.date_prevue) ajouter(e.date_prevue, `${libEtape(etape)} prévu`, '', 'info');
    if (e.etat === ETATS.EN_RETARD) {
      ajouter(e.date_prevue, `${libEtape(etape)} en retard (${e.retard_jours} j)`, 'Non envoyé : relances fermées', 'retard');
    }
    if (a[`${etape}_sent_at`]) ajouter(a[`${etape}_sent_at`], `${libEtape(etape)} envoyé`, e.objet, 'envoi');
    if (a[`${etape}_annule_le`]) {
      ajouter(a[`${etape}_annule_le`], `${libEtape(etape)} annulé`, motifLisible(a[`${etape}_annule_motif`]), 'stop');
    }
  });
  const recus = conv && Array.isArray(conv.messages_recus) ? conv.messages_recus : [];
  recus.forEach((m) => { if (m) ajouter(m.received_at, 'Réponse reçue', texte(m.subject), 'reponse'); });
  if (conv && conv.derniere_reponse_afroboost && conv.derniere_reponse_afroboost.sent_at) {
    ajouter(conv.derniere_reponse_afroboost.sent_at, 'Réponse envoyée par Afroboost',
      texte(conv.derniere_reponse_afroboost.objet), 'envoi');
  }
  if (a.paused_at) ajouter(a.paused_at, 'Mis en pause', '', 'stop');
  if (a.interesse_at) ajouter(a.interesse_at, 'Marqué intéressé', '', 'info');

  const annulees = new Set((notes || []).map((n) => n && n.corrige_note_id).filter(Boolean));
  (notes || []).forEach((n) => {
    if (!n || annulees.has(n.id)) return;
    const type = texte(n.type) === 'prospect_reply' ? 'réponse' : (texte(n.type) || 'note');
    ajouter(n.occurred_at || n.created_at, `Note (${type})`, texte(n.texte).slice(0, 280), 'note');
  });

  /* Tri stable : à date égale, l'ordre d'insertion (envoyé → accepté → …) est gardé. */
  return ev
    .map((e, i) => ({ ...e, i, t: instant(e.quand) }))
    .filter((e) => Number.isFinite(e.t))
    .sort((x, y) => (x.t - y.t) || (x.i - y.i))
    .map(({ i, t, ...e }) => e);
}

export function dateCourte(iso) {
  const t = instant(iso);
  if (!Number.isFinite(t)) return '—';
  const d = new Date(t);
  const p = (x) => String(x).padStart(2, '0');
  return `${p(d.getDate())}/${p(d.getMonth() + 1)}/${d.getFullYear()}`;
}
