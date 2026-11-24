import React, { useState, useMemo, useCallback } from 'react';
import axios from 'axios';
import SvgIcon from '../SvgIcon';
import { libelleCours } from './reminderMoments';

/**
 * V673 — MESSAGE EXCEPTIONNEL JOINT AUX RAPPELS AVANT COURS.
 *
 * Exemple : « Coach Bassi est absent ce mercredi, Marie assure le cours. »
 * Le coach l'ecrit pour les cours COCHES dans la carte des rappels, et pour
 * une PERIODE de seances (du ... au ...). Le rappel habituel part a son heure
 * habituelle et porte ce message ; hors periode, il repart comme d'habitude.
 *
 * Ce composant ne touche NI l'activation NI les regles des rappels : il parle
 * a sa propre route (`/reminder-message`). L'etat local ne suit que ce que le
 * SERVEUR a confirme — meme discipline que la carte qui l'accueille.
 */

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';
const API = `${BACKEND_URL}/api`;
export const MAX_CARACTERES = 600;

const JOURS = ['dimanche', 'lundi', 'mardi', 'mercredi', 'jeudi', 'vendredi', 'samedi'];
const MOIS = ['janvier', 'février', 'mars', 'avril', 'mai', 'juin', 'juillet',
  'août', 'septembre', 'octobre', 'novembre', 'décembre'];

/** Date du jour en Suisse, « AAAA-MM-JJ ». PURE (sauf l'horloge passee). */
export const aujourdhuiZurich = (maintenant = new Date()) => {
  try {
    return new Intl.DateTimeFormat('en-CA', {
      timeZone: 'Europe/Zurich', year: 'numeric', month: '2-digit', day: '2-digit'
    }).format(maintenant);
  } catch (e) {
    return maintenant.toISOString().slice(0, 10);
  }
};

const versDate = (iso) => {
  const [a, m, j] = String(iso || '').split('-').map((x) => parseInt(x, 10));
  if (!a || !m || !j) return null;
  return new Date(Date.UTC(a, m - 1, j));
};
const versIso = (d) => d.toISOString().slice(0, 10);

/** Prochaine seance d'un cours, a partir d'aujourd'hui (convention JS : dim = 0). */
export const prochaineSeance = (cours, aujourdhui) => {
  if (!cours) return aujourdhui;
  if (cours.date && String(cours.date) >= aujourdhui) return String(cours.date).slice(0, 10);
  const _wd = parseInt(cours.weekday, 10);
  const _base = versDate(aujourdhui);
  if (Number.isNaN(_wd) || !_base) return aujourdhui;
  const _ecart = (_wd - _base.getUTCDay() + 7) % 7;
  return versIso(new Date(_base.getTime() + _ecart * 86400000));
};

/** « mercredi 25 novembre » */
export const dateLisible = (iso) => {
  const d = versDate(iso);
  if (!d) return '';
  return `${JOURS[d.getUTCDay()]} ${d.getUTCDate()} ${MOIS[d.getUTCMonth()]}`;
};

export const periodeLisible = (m) => {
  if (!m || !m.du) return '';
  return (!m.au || m.au === m.du)
    ? dateLisible(m.du)
    : `du ${dateLisible(m.du)} au ${dateLisible(m.au)}`;
};

/**
 * V673d — dates REELLES des seances d'un cours entre `du` et `au` (inclus).
 * null = inconnu (ni `date` ni `weekday`) : le serveur tranche alors seul.
 * Jours annules (`dates_annulees`) exclus, comme le moteur des rappels.
 */
export const seancesDansPeriode = (cours, du, au) => {
  const _d1 = versDate(du);
  const _d2 = versDate(au || du);
  if (!cours || !_d1 || !_d2 || _d2 < _d1) return [];
  const _annules = new Set((Array.isArray(cours.dates_annulees) ? cours.dates_annulees : [])
    .map((x) => String(x).slice(0, 10)));
  if (cours.date) {
    const _f = String(cours.date).slice(0, 10);
    return (_f >= versIso(_d1) && _f <= versIso(_d2) && !_annules.has(_f)) ? [_f] : [];
  }
  const _wd = parseInt(cours.weekday, 10);
  if (Number.isNaN(_wd)) return null;
  const _res = [];
  for (let _t = _d1.getTime(); _t <= _d2.getTime(); _t += 86400000) {
    const _j = new Date(_t);
    if (_j.getUTCDay() === _wd && !_annules.has(versIso(_j))) _res.push(versIso(_j));
  }
  return _res;
};

const CourseReminderMessage = ({ choisis, entetes, onMaj }) => {
  const [edition, setEdition] = useState(false);
  const [texte, setTexte] = useState('');
  const [du, setDu] = useState('');
  const [au, setAu] = useState('');
  const [plage, setPlage] = useState(false);
  const [apercu, setApercu] = useState(false);
  const [envoi, setEnvoi] = useState(false);
  const [erreur, setErreur] = useState('');
  const [info, setInfo] = useState('');
  // V673b : crayon = UN cours precis (jamais les autres coches) ; null = nouveau message multi-cours.
  const [cible, setCible] = useState(null);
  // V673d : plusieurs cours en « une seule seance » -> UNE date PAR cours (sa vraie seance).
  const [dates, setDates] = useState({});

  const aujourdhui = aujourdhuiZurich();
  const avecMessage = useMemo(
    () => choisis.filter((c) => c.message_exceptionnel && c.message_exceptionnel.texte),
    [choisis]);
  const cibles = useMemo(() => (cible ? [cible] : choisis), [cible, choisis]);
  const muets = useMemo(
    () => cibles.filter((c) => c.reminders_enabled !== true), [cibles]);

  const ouvrir = useCallback((existant) => {
    const _m = existant && existant.message_exceptionnel;
    const _du = (_m && _m.du) || prochaineSeance(existant || choisis[0], aujourdhui);
    setCible(existant || null);
    setDates(existant ? {} : Object.fromEntries(
      choisis.map((c) => [c.id, prochaineSeance(c, aujourdhui)])));
    setTexte((_m && _m.texte) || '');
    setDu(_du);
    setAu((_m && _m.au) || _du);
    setPlage(Boolean(_m && _m.au && _m.au !== _m.du));
    setApercu(false);
    setErreur('');
    setInfo('');
    setEdition(true);
  }, [choisis, aujourdhui]);

  const fermer = () => { setEdition(false); setErreur(''); setCible(null); };

  const parCours = !plage && cibles.length > 1;
  /** Periode envoyee pour CE cours : sa propre date si plusieurs cours, sinon la commune. */
  const periodeDe = (c) => {
    if (parCours) { const _d = dates[c.id] || ''; return { du: _d, au: _d }; }
    return { du, au: plage ? au : du };
  };

  const refus = (() => {
    if (!texte.trim()) return 'Écris le message à transmettre.';
    if (texte.length > MAX_CARACTERES) return `${MAX_CARACTERES} caractères au plus.`;
    for (let _i = 0; _i < cibles.length; _i += 1) {
      const _p = periodeDe(cibles[_i]);
      if (!_p.du) return 'Choisis la date de la séance concernée.';
      if (!_p.au || _p.au < _p.du) return 'La date de fin précède la date de début.';
      if (_p.au < aujourdhui) return 'Cette date est déjà passée.';
      const _s = seancesDansPeriode(cibles[_i], _p.du, _p.au);
      if (_s && _s.length === 0) {
        return plage
          ? `Aucune séance de ${libelleCours(cibles[_i])} dans cette période.`
          : `Le ${dateLisible(_p.du)} n'est pas un jour de ${libelleCours(cibles[_i])}.`;
      }
    }
    return '';
  })();

  /** UN APPEL PAR COURS, EN SERIE ; chacun compte pour lui-meme. */
  const executer = async (cibles, faire) => {
    setEnvoi(true);
    setErreur('');
    setInfo('');
    const _echecs = [];
    for (let _i = 0; _i < cibles.length; _i += 1) {
      const _c = cibles[_i];
      try {
        // eslint-disable-next-line no-await-in-loop
        const res = await faire(_c);
        onMaj(_c.id, res && res.data ? (res.data.message_exceptionnel || null) : null);
      } catch (e) {
        const _d = e?.response?.data?.detail;
        _echecs.push(`${libelleCours(_c)}${typeof _d === 'string' && _d ? ` (${_d})` : ''}`);
      }
    }
    setEnvoi(false);
    return _echecs;
  };

  const enregistrer = async () => {
    if (refus || envoi) return;
    const _texte = texte.trim();
    const _echecs = await executer(cibles, (c) => axios.put(
      `${API}/coach/courses/${encodeURIComponent(c.id)}/reminder-message`,
      { texte: _texte, ...periodeDe(c) }, entetes));
    if (_echecs.length) {
      setErreur(`Non enregistré pour : ${_echecs.join(', ')}.`);
    } else {
      setEdition(false);
      setCible(null);
      setInfo(cibles.length > 1
        ? `Message enregistré pour ${cibles.length} cours.`
        : 'Message enregistré.');
    }
  };

  const retirer = async (cibles) => {
    if (envoi) return;
    const _echecs = await executer(cibles, (c) => axios.delete(
      `${API}/coach/courses/${encodeURIComponent(c.id)}/reminder-message`, entetes));
    if (_echecs.length) setErreur(`Non retiré pour : ${_echecs.join(', ')}.`);
    else setInfo('Message retiré. Les prochains rappels repartent comme d’habitude.');
  };

  const styleChamp = { colorScheme: 'dark', backgroundColor: 'rgba(0,0,0,0.45)', fontSize: '16px' };
  const classeChamp = 'rounded-lg border border-white/10 text-white px-2 py-2 '
    + 'focus:outline-none focus:border-white/30 min-w-0';
  const accent = { color: 'var(--primary-color, #D91CD2)' };
  const premier = cibles[0];

  return (
    <div className="mt-4 pt-3 border-t border-white/10 w-full max-w-md" data-testid="crm-zone">
      {/* Les messages DEJA poses sur les cours coches : une ligne chacun. */}
      {!edition && avecMessage.map((c) => (
        <div
          key={c.id}
          className="flex items-start gap-2 text-xs rounded-lg px-2 py-2 mb-2"
          style={{ background: 'rgba(var(--primary-rgb, 217, 28, 210), 0.08)' }}
          data-testid={`crm-existant-${c.id}`}
        >
          <SvgIcon name="messageSquare" size={14} style={{ ...accent, flexShrink: 0, marginTop: '2px' }} />
          <span className="min-w-0 flex-1">
            <span className="block text-white/80 break-words">
              {libelleCours(c)}
              <span className="text-white/40"> · {periodeLisible(c.message_exceptionnel)}</span>
            </span>
            <span
              className="block text-white/50 break-words"
              style={{ display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}
            >
              {c.message_exceptionnel.texte}
            </span>
          </span>
          <button
            type="button" onClick={() => ouvrir(c)} disabled={envoi}
            className="p-1.5 rounded-lg text-white/50 hover:text-white/90 shrink-0"
            aria-label={`Modifier le message de ${libelleCours(c)}`}
            data-testid={`crm-modifier-${c.id}`}
          >
            <SvgIcon name="edit" size={14} />
          </button>
          <button
            type="button" onClick={() => retirer([c])} disabled={envoi}
            className="p-1.5 rounded-lg text-white/50 hover:text-white/90 shrink-0"
            aria-label={`Retirer le message de ${libelleCours(c)}`}
            data-testid={`crm-retirer-${c.id}`}
          >
            <SvgIcon name="trash" size={14} />
          </button>
        </div>
      ))}

      {!edition && (
        <button
          type="button" onClick={() => ouvrir(null)}
          className="text-xs flex items-center gap-1.5 hover:opacity-80" style={accent}
          data-testid="crm-ajouter"
        >
          <SvgIcon name="plusCircle" size={14} />
          {avecMessage.length > 0 ? 'Nouveau message exceptionnel' : 'Ajouter un message exceptionnel'}
        </button>
      )}

      {edition && (
        <div className="space-y-2" data-testid="crm-editeur">
          <p className="text-xs text-white" data-testid="crm-cible">
            <span className="text-white/50">{cible ? 'Modification pour : ' : 'Cours concernés : '}</span>
            <strong style={accent}>{cibles.map(libelleCours).join(', ')}</strong>
          </p>
          <p className="text-white/50 text-xs">
            Absence, remplacement, changement… Ce message accompagnera le rappel
            {cibles.length > 1 ? ` des ${cibles.length} cours cochés` : ' de ce cours'}
            , uniquement pour les séances choisies.
          </p>
          <textarea
            value={texte}
            onChange={(e) => { setTexte(e.target.value.slice(0, MAX_CARACTERES)); setErreur(''); }}
            rows={5}
            maxLength={MAX_CARACTERES}
            placeholder="Ex. : Exceptionnellement, Coach Bassi sera absent ce mercredi. Le cours est maintenu et sera assuré par Marie."
            className={`${classeChamp} w-full resize-y`}
            style={styleChamp}
            aria-label="Message exceptionnel"
            data-testid="crm-texte"
          />
          <p className="text-[11px] text-white/35 text-right" data-testid="crm-compteur">
            {texte.length}/{MAX_CARACTERES}
          </p>

          {/* V673d : plusieurs cours, une seance chacun -> UNE date par cours, lisible. */}
          {parCours && (
            <div className="space-y-1.5 text-xs text-white/70" data-testid="crm-dates">
              <p className="text-white/50">Séance concernée, pour chaque cours :</p>
              {cibles.map((c) => (
                <label key={c.id} className="flex flex-wrap items-center gap-2" data-testid={`crm-date-${c.id}`}>
                  <span className="min-w-0 flex-1 break-words text-white/80">{libelleCours(c)}</span>
                  <input
                    type="date" value={dates[c.id] || ''} min={aujourdhui}
                    onChange={(e) => { const _v = e.target.value; setDates((d) => ({ ...d, [c.id]: _v })); }}
                    className={classeChamp} style={styleChamp}
                    aria-label={`Date de la séance de ${libelleCours(c)}`}
                    data-testid={`crm-du-${c.id}`}
                  />
                  <span className="basis-full text-white/45" data-testid={`crm-lisible-${c.id}`}>
                    {dateLisible(dates[c.id])}
                  </span>
                </label>
              ))}
            </div>
          )}

          {!parCours && (
          <div className="flex flex-wrap items-center gap-2 text-xs text-white/70">
            <label className="flex items-center gap-2">
              {plage ? 'Séances du' : 'Séance du'}
              <input
                type="date" value={du} min={aujourdhui}
                onChange={(e) => { setDu(e.target.value); if (!plage) setAu(e.target.value); }}
                className={classeChamp} style={styleChamp}
                data-testid="crm-du"
              />
            </label>
            {plage && (
              <label className="flex items-center gap-2">
                au
                <input
                  type="date" value={au} min={du || aujourdhui}
                  onChange={(e) => setAu(e.target.value)}
                  className={classeChamp} style={styleChamp}
                  data-testid="crm-au"
                />
              </label>
            )}
          </div>
          )}
          {/* V673d : en periode, les VRAIES seances de chaque cours, avant d'enregistrer. */}
          {plage && (
            <ul className="text-[11px] text-white/50 space-y-0.5" data-testid="crm-seances">
              {cibles.map((c) => {
                const _s = seancesDansPeriode(c, du, au);
                return (
                  <li key={c.id} className="break-words" data-testid={`crm-seances-${c.id}`}>
                    {libelleCours(c)} :{' '}
                    {_s === null ? 'dates à vérifier'
                      : (_s.length ? _s.map(dateLisible).join(', ') : 'aucune séance dans cette période')}
                  </li>
                );
              })}
            </ul>
          )}
          <button
            type="button"
            onClick={() => { setPlage((p) => !p); setAu(du); }}
            className="text-[11px] hover:opacity-80" style={accent}
            data-testid="crm-plage"
          >
            {plage ? 'Une seule séance' : 'Plusieurs séances (période)'}
          </button>

          {muets.length > 0 && (
            <p className="text-white/60 text-xs" data-testid="crm-muets">
              Rappels désactivés pour {muets.map(libelleCours).join(', ')} : le message n&apos;y
              partira pas tant que les rappels ne sont pas activés.
            </p>
          )}
          <p className="text-white/35 text-[11px]" data-testid="crm-deja-envoyes">
            Les rappels déjà envoyés ne sont jamais renvoyés.
          </p>

          <button
            type="button" onClick={() => setApercu((a) => !a)}
            className="text-xs flex items-center gap-1.5 text-white/70 hover:text-white"
            aria-expanded={apercu}
            data-testid="crm-apercu-bascule"
          >
            <SvgIcon name={apercu ? 'eyeOff' : 'eye'} size={14} />
            {apercu ? 'Masquer l’aperçu' : 'Aperçu du rappel'}
          </button>

          {apercu && (
            <div
              className="rounded-xl p-3 text-xs space-y-2"
              style={{ background: 'rgba(0,0,0,0.5)', border: '1px solid rgba(255,255,255,0.08)' }}
              data-testid="crm-apercu"
            >
              <p className="text-white/40 text-[11px] uppercase tracking-wide">E-mail</p>
              <p className="text-white">Bonjour [prénom],</p>
              <p className="text-white/80">
                Petit rappel : tu es inscrit(e) à{' '}
                <strong style={accent}>{premier ? (premier.name || 'ton cours') : 'ton cours'}</strong>.
              </p>
              <p className="text-white/80">
                C&apos;est <strong style={accent}>{dateLisible(premier ? periodeDe(premier).du : du)}{premier && premier.time ? ` à ${premier.time}` : ''}</strong>.
              </p>
              <div
                className="rounded-lg px-3 py-2"
                style={{ background: 'rgba(255,255,255,0.06)', borderLeft: '3px solid var(--primary-color, #D91CD2)' }}
              >
                <p className="text-[10px] uppercase tracking-wide mb-1" style={accent}>Message de ton coach</p>
                <p className="text-white whitespace-pre-line break-words" data-testid="crm-apercu-texte">
                  {texte.trim() || '…'}
                </p>
              </div>
              <p className="text-white/40 text-[11px] uppercase tracking-wide pt-1">Notification</p>
              <p className="text-white/70 break-words" data-testid="crm-apercu-push">
                {premier ? (premier.name || 'Ton cours') : 'Ton cours'} — rappel habituel
                <br />
                <span className="text-white/90">
                  {(() => {
                    const _t = texte.trim().split(/\s+/).join(' ');
                    return _t.length > 140 ? `${_t.slice(0, 139)}…` : (_t || '…');
                  })()}
                </span>
              </p>
            </div>
          )}

          {refus && texte.length > 0 && (
            <p className="text-white/60 text-xs" data-testid="crm-refus">{refus}</p>
          )}

          <div className="flex items-center gap-3 pt-1">
            <button
              type="button" onClick={enregistrer} disabled={Boolean(refus) || envoi}
              className="text-xs px-3 py-2 rounded-lg text-white disabled:opacity-40"
              style={{ backgroundColor: 'var(--primary-color, #D91CD2)' }}
              data-testid="crm-enregistrer"
            >
              {envoi ? 'Enregistrement…'
                : (cible ? 'Enregistrer pour ce cours'
                  : (cibles.length > 1 ? `Enregistrer pour ${cibles.length} cours` : 'Enregistrer le message'))}
            </button>
            <button
              type="button" onClick={fermer} disabled={envoi}
              className="text-xs text-white/50 hover:text-white/80"
              data-testid="crm-annuler"
            >
              Annuler
            </button>
          </div>
        </div>
      )}

      {info && <p className="text-xs text-white/60 mt-2" data-testid="crm-info">{info}</p>}
      {erreur && <p className="text-xs text-white/60 mt-2 break-words" data-testid="crm-erreur">{erreur}</p>}
    </div>
  );
};

export default CourseReminderMessage;
