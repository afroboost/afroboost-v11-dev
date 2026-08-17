/**
 * Les moments de rappel, definis UNE fois pour toutes.
 *
 * Ces valeurs decrivent exactement ce que le serveur accepte
 * (`n1b2_valider_regles`, api/server.py). Un `<select>` ferme rend
 * litteralement impossible l'envoi d'une valeur arbitraire — c'est la raison
 * d'etre de ce fichier : deux ecrans qui proposeraient des listes divergentes
 * finiraient par proposer un delai que le serveur refuse.
 */

export const MAX_REGLES = 2;
export const ECART_MIN = 60;          // meme seuil que N1B3B2_ECART_MIN cote serveur

// Les quatre delais admis par le serveur, et rien d'autre.
export const DELAIS = [
  { minutes: 60, label: '1 h avant le cours' },
  { minutes: 180, label: '3 h avant le cours' },
  { minutes: 1440, label: '24 h avant — la veille' },
  { minutes: 2880, label: '48 h avant — l’avant-veille' }
];

export const deuxChiffres = (n) => (n < 10 ? `0${n}` : `${n}`);

// Heures fixes possibles le jour du cours. Le serveur n'accepte que :00 et :30
// (la cadence du cron est de 30 min) — proposer la minute libre serait mentir.
export const HEURES_JOUR_MEME = (() => {
  const _liste = [];
  for (let _h = 0; _h < 24; _h += 1) {
    _liste.push({ heure: _h, minute: 0, label: `${deuxChiffres(_h)}:00` });
    _liste.push({ heure: _h, minute: 30, label: `${deuxChiffres(_h)}:30` });
  }
  return _liste;
})();

export const JOUR_MEME_DEFAUT = { type: 'same_day', heure: 7, minute: 0 };

/** Valeur du `<select>` de moment, pour une regle donnee. */
export const valeurMoment = (regle) => (
  regle.type === 'same_day' ? 'same_day' : `rel:${regle.minutes}`
);

/**
 * Cle d'idempotence — COPIE FIDELE de `n1b2_cle` (api/server.py).
 * Elle ne sert ici qu'a detecter le doublon exact avec la meme definition que
 * le serveur : deux regles de meme cle s'ecraseraient en base.
 */
export const cleDe = (regle) => {
  if (regle.type === 'same_day') {
    return `same_day:${deuxChiffres(regle.heure)}:${deuxChiffres(regle.minute)}`;
  }
  return regle.minutes === 60 ? 'defaut' : `relative:${regle.minutes}m`;
};

/**
 * Refus previsible, dit avant d'appeler le serveur. Chaine vide = rien a
 * signaler. On ne duplique QUE les deux regles calculables sans le planning.
 */
export const refusDeConfig = (regles) => {
  if (regles.length === 0) return 'Garde au moins un rappel.';
  const _cles = regles.map(cleDe);
  if (new Set(_cles).size !== _cles.length) {
    return 'Ces deux rappels sont identiques — choisis deux moments différents.';
  }
  const _fixes = regles
    .filter((r) => r.type === 'same_day')
    .map((r) => r.heure * 60 + r.minute)
    .sort((a, b) => a - b);
  for (let i = 0; i + 1 < _fixes.length; i += 1) {
    if (_fixes[i + 1] - _fixes[i] < ECART_MIN) {
      return 'Deux rappels le jour même à moins d’une heure d’écart — espace-les davantage.';
    }
  }
  return '';
};

/** Libelle lisible d'un cours : « Mercredi 18:30 — Danse Afro ». */
export const JOURS_FR = ['Dimanche', 'Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi'];

export const libelleCours = (c) => {
  if (!c) return '';
  const _nom = (c.name || 'Cours sans nom').trim();
  const _h = c.time ? ` ${c.time}` : '';
  if (c.date) return `${c.date}${_h} — ${_nom}`;
  const _j = (typeof c.weekday === 'number' && JOURS_FR[c.weekday]) || 'Récurrent';
  return `${_j}${_h} — ${_nom}`;
};
