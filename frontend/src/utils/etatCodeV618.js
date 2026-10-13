// V618f — L'ÉTAT MÉTIER D'UN CODE, UNE SEULE RÈGLE POUR L'ÉCRAN ET L'EXPORT.
//
// Avant : l'export CSV écrivait « Actif : Oui » dès que l'interrupteur `active` était vrai,
// même pour un code expiré depuis des mois, et le bouton « Lien » (accès à l'espace) restait
// proposé sur ces codes. Désormais l'état se lit dans ce que le SERVEUR a tranché :
//   `code.v532.classement` — actuel / historique / a_verifier (LOT A + règle canonique V618 :
//                             quand un code porte des abonnements, c'est l'abonnement ACTUEL de
//                             la personne qui décide, plus la seule date de la fiche) ;
//   `code.v618.etat`        — actuel / historique / conflit.
// Repli (étiquettes absentes) : interrupteur actif ET date non dépassée.
//
// Fonctions PURES : aucune lecture réseau, aucun effet.

export const ETAT_ACTIF = 'ACTIF';
export const ETAT_EXPIRE = 'EXPIRÉ';
export const ETAT_HISTORIQUE = 'HISTORIQUE';
export const ETAT_CONFLIT = 'CONFLIT';

// Même lecture que PromoCodesTab (V200) : ISO, ou JJ.MM.AAAA (fin de journée).
export function lireDateCode(valeur) {
  if (!valeur) return null;
  try {
    let d = new Date(valeur);
    if (isNaN(d.getTime()) && typeof valeur === 'string') {
      const m = valeur.match(/^(\d{1,2})\.(\d{1,2})\.(\d{4})$/);
      if (m) d = new Date(parseInt(m[3], 10), parseInt(m[2], 10) - 1, parseInt(m[1], 10), 23, 59, 59, 999);
    }
    return isNaN(d.getTime()) ? null : d;
  } catch (e) {
    return null;
  }
}

// Expiré ssi le JOUR de fin est strictement antérieur à aujourd'hui (V200).
export function dateCodeExpiree(valeur, maintenant) {
  const d = lireDateCode(valeur);
  if (!d) return false;
  const now = maintenant || new Date();
  const fin = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const jour = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  return fin < jour;
}

// La fin à AFFICHER : celle de l'abonnement actuel quand le serveur l'a désigné, sinon la fiche.
export function finAfficheeCode(code) {
  const c = code || {};
  const v = c.v532 || {};
  // La fin d'un abonnement est écrite « AAAA-MM-JJT23:59:59+00:00 » (fin de journée) : affichée
  // telle quelle à l'heure suisse, elle tomberait le LENDEMAIN. On garde le jour seul.
  if (v.classement === 'actuel' && v.expire_le) {
    const m = String(v.expire_le).match(/^(\d{4}-\d{2}-\d{2})T/);
    return m ? m[1] : v.expire_le;
  }
  return c.expiresAt || null;
}

export function etatMetierCode(code, maintenant) {
  const c = code || {};
  const v532 = c.v532 || {};
  const v618 = (c.v618 && c.v618.etat) || '';
  if (v618 === 'conflit' || v532.classement === 'a_verifier') return ETAT_CONFLIT;
  if (v532.classement === 'actuel') return ETAT_ACTIF;
  if (!v532.classement && c.active && !dateCodeExpiree(c.expiresAt, maintenant)) return ETAT_ACTIF;
  if (dateCodeExpiree(finAfficheeCode(c), maintenant)) return ETAT_EXPIRE;
  return ETAT_HISTORIQUE;
}

// Le bouton « Lien » (accès à l'espace membre) n'est proposé QUE pour un accès actuel.
export function lienEspaceProposable(code, maintenant) {
  return !!(code && code.active) && etatMetierCode(code, maintenant) === ETAT_ACTIF;
}
