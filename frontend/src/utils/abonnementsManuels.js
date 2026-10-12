// V617 — ABONNEMENTS MANUELS : règles pures de l'écran « Codes promo ».
//
// Le serveur reste juge (un seul abonnement actuel, historique jamais modifié) ;
// ces fonctions évitent seulement d'ENVOYER ce que le coach n'a pas touché, rangent
// les articles autorisés par nature, et rendent lisibles les refus du serveur.

const _norm = (v) => {
  if (v === undefined || v === null) return '';
  if (Array.isArray(v)) return JSON.stringify([...v].map(String).sort());
  if (typeof v === 'number') return String(v);
  if (typeof v === 'boolean') return v ? '1' : '0';
  const s = String(v).trim();
  return s !== '' && !Number.isNaN(Number(s)) && /^-?\d+(\.\d+)?$/.test(s) ? String(Number(s)) : s;
};

/** Les seuls champs dont la valeur a réellement changé par rapport au code d'origine. */
export function champsModifies(updates, original) {
  const o = original || {};
  const sortie = {};
  Object.keys(updates || {}).forEach((k) => {
    const avant = k === 'used' ? (o.usedCount ?? o.used) : o[k];
    if (_norm(updates[k]) !== _norm(avant)) sortie[k] = updates[k];
  });
  return sortie;
}

export const SUIVI_VIDE = {
  montant_total: '', plusieurs_fois: false, nb_paiements: 2, paiement_actuel: 1,
  prochaine_echeance: '', note_interne: '',
};

/** Suivi du serveur (abonnement actuel) -> valeurs du formulaire. */
export function suiviVersFormulaire(suivi) {
  const s = suivi || {};
  return {
    montant_total: s.montant_total ?? '',
    plusieurs_fois: !!s.plusieurs_fois,
    nb_paiements: s.nb_paiements || 2,
    paiement_actuel: s.paiement_actuel || 1,
    prochaine_echeance: s.prochaine_echeance || '',
    note_interne: s.note_interne || '',
  };
}

/** Formulaire -> charge utile pour le serveur ; `null` si rien n'est renseigné. */
export function suiviPourEnvoi(form) {
  const f = form || {};
  const total = String(f.montant_total ?? '').trim();
  const note = String(f.note_interne || '').trim();
  const ech = String(f.prochaine_echeance || '').trim();
  if (!total && !note && !ech && !f.plusieurs_fois) return null;
  const sortie = {};
  if (total) sortie.montant_total = parseFloat(total);
  if (f.plusieurs_fois) {
    sortie.plusieurs_fois = true;
    sortie.nb_paiements = parseInt(f.nb_paiements, 10) || 2;
    sortie.paiement_actuel = parseInt(f.paiement_actuel, 10) || 1;
  }
  if (ech) sortie.prochaine_echeance = ech;
  if (note) sortie.note_interne = note;
  return sortie;
}

/** Reste à payer affiché (le serveur le recalcule de son côté, jamais stocké).
 *  V617d : seulement si le total ET l'encaissé sont connus — sinon `null` (« — »),
 *  jamais un 0 ni un « total = encaissé » inventés. */
export function resteAPayer(total, encaisse) {
  const t = parseFloat(total);
  const e = parseFloat(encaisse);
  if (Number.isNaN(t) || Number.isNaN(e)) return null;
  return Math.max(0, Math.round((t - e) * 100) / 100);
}

/**
 * V617d — le bloc « Suivi du paiement » : visible pour TOUT abonnement éditable,
 * ancien ou nouveau, qu'un suivi existe déjà ou non.
 *  - création avec bénéficiaire -> visible, éditable ;
 *  - édition d'un code qui porte au moins un abonnement (`v617_abonnement`) -> visible ;
 *    éditable seulement si le serveur a désigné UN abonnement actuel (motif `unique`) ;
 *  - code promo simple (aucun abonnement, aucun bénéficiaire) -> pas de bloc.
 * Ne lit que ce qui est déjà chargé : ouvrir une fiche n'écrit rien.
 */
export function etatSuiviPaiement({ isBatchMode, editingCode, fiche, beneficiaires } = {}) {
  if (isBatchMode) return { visible: false };
  if (!editingCode) {
    return (beneficiaires || []).length > 0 ? { visible: true, editable: true, message: '' } : { visible: false };
  }
  const abo = (fiche || {}).v617_abonnement;
  if (!abo) {
    return (beneficiaires || []).length > 0 ? { visible: true, editable: true, message: '' } : { visible: false };
  }
  if (abo.motif === 'unique' && abo.id) return { visible: true, editable: true, message: '' };
  if (abo.motif === 'plusieurs') {
    return { visible: true, editable: false, message: 'Plusieurs abonnements actuels détectés. '
      + "Aucune modification ne sera enregistrée tant que ce doublon n'aura pas été résolu." };
  }
  if (abo.motif === 'aucun') {
    return { visible: true, editable: false, message: "Aucun abonnement actuel : l'historique reste en lecture seule. "
      + 'Créez un nouvel abonnement pour ce client.' };
  }
  return { visible: true, editable: false, message: "Cet abonnement appartient à un autre coach : suivi non modifiable." };
}

const _jour = (d) => {
  const x = d || new Date();
  return `${x.getFullYear()}-${String(x.getMonth() + 1).padStart(2, '0')}-${String(x.getDate()).padStart(2, '0')}`;
};
const _estProduit = (o) => !!(o && (o.isProduct || (o.category
  && ['tshirt', 'shoes', 'supplement', 'accessory', 'audio', 'video'].includes(o.category))));

/**
 * Range les articles autorisables en 4 rubriques et retire ce qui n'est plus
 * utilisable. Un élément DÉJÀ sélectionné reste toujours visible, avec son badge
 * (« Archivé », « Masqué », « Terminé ») : l'historique n'est jamais effacé.
 * Les offres masquées sont souvent volontairement RÉSERVÉES aux membres : elles
 * restent accessibles par l'option `afficherInternes`, jamais supprimées.
 */
export function classerArticles({ courses = [], offers = [], selection = [], afficherInternes = false, aujourdhui } = {}) {
  const jour = aujourdhui || _jour();
  const choisis = new Set((selection || []).map(String));
  const coursParId = {};
  (courses || []).forEach((c) => { if (c && c.id) coursParId[String(c.id)] = c; });
  const rubriques = { cours: [], evenements: [], offres: [], articles: [] };
  const masques = { total: 0 };
  const garder = (item, badge, interne) => {
    const sel = choisis.has(String(item.id));
    if (badge && !sel && !(interne && afficherInternes)) { masques.total += 1; return null; }
    return { id: item.id, nom: item.name || item.title || item.id, badge: badge || null, selectionne: sel };
  };
  (courses || []).forEach((c) => {
    if (!c || !c.id) return;
    const ponctuel = !!c.date && (c.weekday === undefined || c.weekday === null || c.weekday === '');
    let badge = null; let interne = false;
    if (c.archived) badge = 'Archivé';
    else if (ponctuel && String(c.date).slice(0, 10) < jour) badge = 'Terminé';
    else if (c.visible === false) { badge = 'Masqué'; interne = true; }
    const r = garder(c, badge, interne);
    if (r) (ponctuel ? rubriques.evenements : rubriques.cours).push(r);
  });
  (offers || []).forEach((o) => {
    if (!o || !o.id) return;
    const evenement = o.offer_type === 'event';
    let badge = null; let interne = false;
    if (o.archived) badge = 'Archivée';
    else if (evenement) {
      const dates = (o.linked_course_ids || []).map((id) => coursParId[String(id)])
        .filter((c) => c && c.date).map((c) => String(c.date).slice(0, 10));
      if (dates.length && dates.every((d) => d < jour)) badge = 'Terminé';
    }
    if (!badge && o.visible === false) { badge = 'Réservée / interne'; interne = true; }
    const r = garder(o, badge, interne);
    if (!r) return;
    if (_estProduit(o)) rubriques.articles.push(r);
    else if (evenement) rubriques.evenements.push(r);
    else rubriques.offres.push(r);
  });
  return { ...rubriques, masques: masques.total };
}

/** Message lisible d'un refus serveur (le détail V617 est un objet). */
export function messageServeur(err) {
  const d = err?.response?.data?.detail;
  if (d && typeof d === 'object') return d.message || JSON.stringify(d);
  return d || err?.message || 'Erreur inconnue';
}

/** Le type V617 d'un refus 409, s'il y en a un. */
export function typeRefus(err) {
  const d = err?.response?.data?.detail;
  return err?.response?.status === 409 && d && typeof d === 'object' ? d.type : null;
}
