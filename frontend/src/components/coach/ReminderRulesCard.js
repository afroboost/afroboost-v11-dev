/**
 * ReminderRulesCard.js — N1B-3C : le coach regle ses rappels avant cours.
 *
 * POURQUOI UN COMPOSANT AUTONOME
 * `ReservationTab.js` est purement presentatif (toute la logique vit dans
 * CoachDashboard). Brancher un fetch dedans casserait ce contrat ; poser la
 * logique dans CoachDashboard.js ajouterait ~120 lignes a un fichier de 7 200.
 * Cette section est donc un composant ferme : il possede son etat, son appel
 * reseau et sa validation, et s'insere en une ligne au-dessus de la liste.
 *
 * UN SEUL ENDROIT
 * C'est le SEUL point de reglage des rappels dans l'application : aucune entree
 * dans l'onglet Gestion, aucune copie ailleurs. Un second exemplaire de cet
 * ecran ferait diverger deux sources pour la meme valeur en base.
 *
 * CONTRAT SERVEUR (N1B-3B2)
 *   GET  /api/coach/reminder-rules  -> { rules: [...], par_defaut: bool }
 *   PUT  /api/coach/reminder-rules  <- { rules: [...] }
 *                                   -> { success, rules, avertissements: [] }
 *                                   -> 400 { detail } si la config est refusee
 * Une regle est SOIT { type:'relative', minutes:60|180|1440|2880 },
 * SOIT { type:'same_day', heure:0..23, minute:0|30 }. Deux au maximum.
 *
 * LA VALIDATION EST DOUBLEE, PAS DEPLACEE
 * Le serveur reste seul juge — il refuse en 400 quoi qu'il arrive. Ce qui suit
 * n'est qu'un garde-fou d'ecran : il evite au coach d'aller chercher un refus
 * serveur pour une faute qu'on peut lui dire tout de suite. Les deux regles
 * reproduites ici sont exactement celles du serveur (doublon exact, et deux
 * `same_day` a moins de 60 min). Les COLLISIONS avec de vrais cours, elles, ne
 * sont PAS reproduites : elles demandent le planning, donc seul le serveur peut
 * les calculer — il les renvoie dans `avertissements`, et on les affiche.
 */
import React, { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import axios from 'axios';
import SvgIcon from '../SvgIcon';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';
const API = `${BACKEND_URL}/api`;

const MAX_REGLES = 2;
const ECART_MIN = 60;               // meme seuil que N1B3B2_ECART_MIN cote serveur

// Les quatre delais admis par le serveur, et rien d'autre : un `<select>` ferme
// rend litteralement impossible l'envoi d'une valeur arbitraire.
const DELAIS = [
  { minutes: 60, label: '1 h avant le cours' },
  { minutes: 180, label: '3 h avant le cours' },
  { minutes: 1440, label: '24 h avant — la veille' },
  { minutes: 2880, label: '48 h avant — l’avant-veille' }
];

const deuxChiffres = (n) => (n < 10 ? `0${n}` : `${n}`);

// Heures fixes possibles le jour du cours. Le serveur n'accepte que :00 et :30
// (la cadence du cron est de 30 min) — proposer la minute libre serait mentir.
const HEURES_JOUR_MEME = (() => {
  const _liste = [];
  for (let _h = 0; _h < 24; _h += 1) {
    _liste.push({ heure: _h, minute: 0, label: `${deuxChiffres(_h)}:00` });
    _liste.push({ heure: _h, minute: 30, label: `${deuxChiffres(_h)}:30` });
  }
  return _liste;
})();

const JOUR_MEME_DEFAUT = { type: 'same_day', heure: 7, minute: 0 };

/** Valeur du `<select>` de moment, pour une regle donnee. */
const valeurMoment = (regle) => (
  regle.type === 'same_day' ? 'same_day' : `rel:${regle.minutes}`
);

/**
 * Cle d'idempotence — COPIE FIDELE de `n1b2_cle` (api/server.py).
 * Elle ne sert ici qu'a detecter le doublon exact avec la meme definition que
 * le serveur : deux regles de meme cle s'ecraseraient en base.
 */
const cleDe = (regle) => {
  if (regle.type === 'same_day') {
    return `same_day:${deuxChiffres(regle.heure)}:${deuxChiffres(regle.minute)}`;
  }
  return regle.minutes === 60 ? 'defaut' : `relative:${regle.minutes}m`;
};

const memeConfig = (a, b) => JSON.stringify(a) === JSON.stringify(b);

const ReminderRulesCard = ({ coachEmail }) => {
  const [regles, setRegles] = useState([]);
  const [enregistrees, setEnregistrees] = useState([]);   // dernier etat connu du serveur
  const [parDefaut, setParDefaut] = useState(false);
  const [chargement, setChargement] = useState(true);
  const [indisponible, setIndisponible] = useState('');
  const [envoi, setEnvoi] = useState(false);
  const [erreur, setErreur] = useState('');
  const [avertissements, setAvertissements] = useState([]);
  const [confirme, setConfirme] = useState(false);

  const monte = useRef(true);
  const minuteur = useRef(null);

  const entetes = useMemo(() => (
    { headers: { 'X-User-Email': coachEmail || '' } }
  ), [coachEmail]);

  // `monte` est REARME a chaque montage, pas seulement pose au premier. React
  // tourne en <StrictMode> (src/index.js) : en developpement il monte, demonte
  // puis REMONTE le composant. Un drapeau seulement remis a false au demontage
  // resterait faux pour de bon, et l'enregistrement paraitrait sans effet —
  // la reponse du serveur arriverait bien, mais serait ignoree.
  useEffect(() => {
    monte.current = true;
    return () => {
      monte.current = false;
      if (minuteur.current) clearTimeout(minuteur.current);
    };
  }, []);

  useEffect(() => {
    let annule = false;
    (async () => {
      try {
        const res = await axios.get(`${API}/coach/reminder-rules`, entetes);
        if (annule) return;
        const _lues = Array.isArray(res.data?.rules) ? res.data.rules : [];
        setRegles(_lues);
        setEnregistrees(_lues);
        setParDefaut(Boolean(res.data?.par_defaut));
      } catch (e) {
        if (annule) return;
        // Le reglage n'est pas encore servi (route absente) ou la session n'est
        // pas reconnue : on le DIT, et on n'affiche pas un editeur qui ne
        // saurait rien enregistrer.
        setIndisponible(
          e?.response?.status === 401 || e?.response?.status === 403
            ? 'Reconnecte-toi pour régler tes rappels.'
            : 'Réglage des rappels indisponible pour le moment.'
        );
      } finally {
        if (!annule) setChargement(false);
      }
    })();
    return () => { annule = true; };
  }, [entetes]);

  /**
   * Refus previsible, dit avant d'appeler le serveur. Chaine vide = rien a
   * signaler. On ne duplique QUE les deux regles calculables sans le planning.
   */
  const refus = useMemo(() => {
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
  }, [regles]);

  const modifie = !memeConfig(regles, enregistrees);

  // Toute retouche invalide la confirmation precedente : afficher « Enregistré »
  // au-dessus d'une valeur qui ne l'est plus serait un mensonge.
  const majRegles = useCallback((suivantes) => {
    setRegles(suivantes);
    setConfirme(false);
    setErreur('');
    setAvertissements([]);
  }, []);

  const changerMoment = (index, valeur) => {
    const _suivantes = regles.slice();
    if (valeur === 'same_day') {
      _suivantes[index] = { ...JOUR_MEME_DEFAUT };
    } else {
      _suivantes[index] = { type: 'relative', minutes: parseInt(valeur.slice(4), 10) };
    }
    majRegles(_suivantes);
  };

  const changerHeure = (index, valeur) => {
    const [_h, _m] = valeur.split(':').map((x) => parseInt(x, 10));
    const _suivantes = regles.slice();
    _suivantes[index] = { type: 'same_day', heure: _h, minute: _m };
    majRegles(_suivantes);
  };

  const ajouter = () => {
    // Second rappel propose a 24 h : c'est le moment le plus eloigne de la
    // valeur par defaut (1 h), donc celui qui a le moins de chances d'entrer en
    // collision avec elle.
    const _defaut = regles.some((r) => r.type === 'relative' && r.minutes === 1440)
      ? { ...JOUR_MEME_DEFAUT }
      : { type: 'relative', minutes: 1440 };
    majRegles(regles.concat([_defaut]));
  };

  const retirer = (index) => majRegles(regles.filter((_, i) => i !== index));

  const enregistrer = async () => {
    if (refus || envoi) return;
    setEnvoi(true);
    setErreur('');
    setAvertissements([]);
    try {
      const res = await axios.put(`${API}/coach/reminder-rules`, { rules: regles }, entetes);
      if (!monte.current) return;
      const _validees = Array.isArray(res.data?.rules) ? res.data.rules : regles;
      setRegles(_validees);
      setEnregistrees(_validees);
      setParDefaut(false);
      setAvertissements(Array.isArray(res.data?.avertissements) ? res.data.avertissements : []);
      setConfirme(true);
      if (minuteur.current) clearTimeout(minuteur.current);
      minuteur.current = setTimeout(() => { if (monte.current) setConfirme(false); }, 4000);
    } catch (e) {
      if (!monte.current) return;
      const _detail = e?.response?.data?.detail;
      setErreur(typeof _detail === 'string' && _detail
        ? _detail
        : 'Enregistrement impossible. Réessaie dans un instant.');
    } finally {
      if (monte.current) setEnvoi(false);
    }
  };

  const styleChamp = {
    colorScheme: 'dark',        // sans quoi le menu natif s'ouvre en clair sur fond sombre
    backgroundColor: 'rgba(0,0,0,0.45)'
  };
  const classeChamp = 'rounded-lg border border-white/10 text-white text-xs sm:text-sm '
    + 'px-2 py-2 focus:outline-none focus:border-white/30 min-w-0';

  return (
    <div className="card-gradient rounded-xl p-4">
      {/* En-tete : titre, puis la phrase qui dit la limite de deux moments. */}
      <div className="flex items-center gap-2 flex-wrap">
        <SvgIcon name="bell" size={16} style={{ color: 'var(--primary-color, #D91CD2)' }} />
        <h2 className="font-semibold text-white text-base sm:text-lg">Rappels avant cours</h2>
        {!chargement && !indisponible && parDefaut && (
          <span
            className="text-[10px] uppercase tracking-wide px-2 py-0.5 rounded-full"
            style={{
              color: 'var(--primary-color, #D91CD2)',
              backgroundColor: 'rgba(var(--primary-rgb, 217, 28, 210), 0.12)'
            }}
          >
            par défaut
          </span>
        )}
      </div>
      <p className="text-white/50 text-xs mt-1">
        Choisis jusqu&rsquo;à 2 moments pour rappeler automatiquement tes participants.
      </p>

      {chargement && (
        <p className="text-white/40 text-xs mt-3 flex items-center gap-2">
          <SvgIcon name="loader" size={14} className="animate-spin" /> Chargement&hellip;
        </p>
      )}

      {!chargement && indisponible && (
        <p className="text-white/40 text-xs mt-3">{indisponible}</p>
      )}

      {!chargement && !indisponible && (
        <>
          {/* Un rappel par ligne. Sur mobile les champs occupent la largeur ;
              le seul champ secondaire (l'heure fixe) passe a la ligne si besoin
              plutot que de comprimer le champ principal.
              `max-w-md` (448 px) borne la ligne sur grand ecran : sans lui,
              `flex-1` etirait le menu « 1 h avant le cours » sur 1 222 px
              (mesure a 1280 px de large), soit une barre presque vide. Le cap
              est SANS effet sous 448 px, donc le mobile reste pleine largeur —
              inutile d'y ajouter un point de rupture. */}
          <div className="mt-3 space-y-2">
            {regles.map((regle, index) => (
              <div key={index} className="flex items-center gap-2 max-w-md">
                <div className="flex flex-1 flex-wrap items-center gap-2 min-w-0">
                  <select
                    value={valeurMoment(regle)}
                    onChange={(e) => changerMoment(index, e.target.value)}
                    className={`${classeChamp} flex-1`}
                    style={styleChamp}
                    aria-label={`Moment du rappel ${index + 1}`}
                    data-testid={`reminder-moment-${index}`}
                  >
                    {DELAIS.map((d) => (
                      <option key={d.minutes} value={`rel:${d.minutes}`}>{d.label}</option>
                    ))}
                    <option value="same_day">Le jour même à&hellip;</option>
                  </select>

                  {regle.type === 'same_day' && (
                    <select
                      value={`${regle.heure}:${regle.minute}`}
                      onChange={(e) => changerHeure(index, e.target.value)}
                      className={`${classeChamp} w-[88px]`}
                      style={styleChamp}
                      aria-label={`Heure du rappel ${index + 1}`}
                      data-testid={`reminder-heure-${index}`}
                    >
                      {HEURES_JOUR_MEME.map((h) => (
                        <option key={h.label} value={`${h.heure}:${h.minute}`}>{h.label}</option>
                      ))}
                    </select>
                  )}
                </div>

                {/* Le premier rappel n'est pas retirable : le serveur refuse une
                    configuration vide, un bouton qui menerait a un 400 serait
                    un piege. */}
                {regles.length > 1 && (
                  <button
                    type="button"
                    onClick={() => retirer(index)}
                    className="text-white/40 hover:text-white/80 p-2 rounded-lg shrink-0"
                    aria-label={`Retirer le rappel ${index + 1}`}
                    data-testid={`reminder-retirer-${index}`}
                  >
                    <SvgIcon name="x" size={14} />
                  </button>
                )}
              </div>
            ))}
          </div>

          {regles.length < MAX_REGLES && (
            <button
              type="button"
              onClick={ajouter}
              className="mt-2 text-xs flex items-center gap-1.5 hover:opacity-80"
              style={{ color: 'var(--primary-color, #D91CD2)' }}
              data-testid="reminder-ajouter"
            >
              <SvgIcon name="plusCircle" size={14} /> Ajouter un second rappel
            </button>
          )}

          {/* Refus previsible : dit sous les champs, sans attendre le serveur. */}
          {refus && (
            <p className="text-amber-300/90 text-xs mt-2 flex items-start gap-1.5">
              <SvgIcon name="warning" size={13} style={{ marginTop: '2px' }} /> {refus}
            </p>
          )}

          <div className="mt-3 flex items-center gap-3 flex-wrap">
            <button
              type="button"
              onClick={enregistrer}
              disabled={!modifie || !!refus || envoi}
              className="btn-primary px-3 py-2 rounded-lg text-xs sm:text-sm flex items-center gap-2"
              data-testid="reminder-enregistrer"
            >
              {envoi && <SvgIcon name="loader" size={14} className="animate-spin" />}
              {envoi ? 'Enregistrement…' : 'Enregistrer'}
            </button>

            {confirme && !modifie && (
              <span className="text-emerald-300/90 text-xs flex items-center gap-1.5">
                <SvgIcon name="check" size={14} /> Enregistré
              </span>
            )}
          </div>

          {erreur && (
            <p className="text-red-300/90 text-xs mt-2" data-testid="reminder-erreur">{erreur}</p>
          )}

          {/* Avertissements de collision : calcules par le serveur sur les vrais
              cours du coach. Ils n'empechent pas l'enregistrement — la config
              peut etre la bonne pour les autres cours — mais ils doivent se
              voir, sinon le coach croit a deux rappels la ou il n'y en aura
              qu'un. */}
          {avertissements.length > 0 && (
            <ul className="mt-2 space-y-1" data-testid="reminder-avertissements">
              {avertissements.map((a, i) => (
                <li key={i} className="text-amber-300/90 text-xs flex items-start gap-1.5">
                  <SvgIcon name="warning" size={13} style={{ marginTop: '2px' }} /> {a}
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  );
};

export default memo(ReminderRulesCard);
