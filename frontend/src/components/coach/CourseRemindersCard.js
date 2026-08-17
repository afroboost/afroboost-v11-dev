import React, { useState, useEffect, useMemo, useRef, useCallback, memo } from 'react';
import axios from 'axios';
import SvgIcon from '../SvgIcon';
import {
  MAX_REGLES, DELAIS, HEURES_JOUR_MEME, JOUR_MEME_DEFAUT,
  valeurMoment, refusDeConfig, libelleCours
} from './reminderMoments';

/**
 * Rappels avant cours — le coach choisit COURS PAR COURS.
 *
 * Deux niveaux, et ils ne se confondent pas :
 *   - ICI, le coach dit quels cours envoient des rappels, et a quels moments ;
 *   - dans son espace, le participant dit s'il veut le Push, l'e-mail, ou rien.
 * Un cours eteint ne reveille personne, quelles que soient les preferences du
 * participant ; un participant qui a coupe un canal ne le recoit pas, meme si
 * le coach a tout allume. Le refus gagne toujours.
 *
 * Un cours dont les rappels n'ont jamais ete actives reste MUET. C'est
 * volontaire : au deploiement, aucun cours historique ne se met a ecrire aux
 * gens sans que personne l'ait demande.
 */

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';
const API = `${BACKEND_URL}/api`;

const memeConfig = (a, b) => JSON.stringify(a) === JSON.stringify(b);

const CourseRemindersCard = ({ coachEmail }) => {
  const [cours, setCours] = useState([]);
  const [coursId, setCoursId] = useState('');
  const [actif, setActif] = useState(false);
  const [regles, setRegles] = useState([]);
  const [enregistre, setEnregistre] = useState({ actif: false, regles: [] });
  const [chargement, setChargement] = useState(true);
  const [indisponible, setIndisponible] = useState('');
  const [envoi, setEnvoi] = useState(false);
  const [erreur, setErreur] = useState('');
  const [confirme, setConfirme] = useState(false);

  const monte = useRef(true);
  const minuteur = useRef(null);

  const entetes = useMemo(
    () => ({ headers: { 'X-User-Email': coachEmail || '' } }), [coachEmail]);

  useEffect(() => {
    monte.current = true;
    return () => {
      monte.current = false;
      if (minuteur.current) clearTimeout(minuteur.current);
    };
  }, []);

  // La liste sert AUSSI de source de configuration : `reminders_enabled` et
  // `reminder_rules` voyagent avec chaque cours. Un seul aller-retour.
  useEffect(() => {
    let annule = false;
    (async () => {
      try {
        // PAS `\/courses?scope=mine` : cette liste-la sert d'abord la vitrine
        // et filtre `archived`, ce qui faisait disparaitre les vraies seances
        // recurrentes du coach — celles que ses offres vendent. La route
        // dediee applique la regle d'ADMINISTRATION, pas celle de publication.
        const res = await axios.get(`${API}/coach/courses/reminders`, entetes);
        if (annule) return;
        // Aucun filtre ici : le serveur a deja tranche. En rajouter un
        // reintroduirait exactement le bug qu'on vient de corriger.
        const _liste = (Array.isArray(res.data) ? res.data : []).filter(Boolean);
        setCours(_liste);
        if (_liste.length > 0) setCoursId((prec) => prec || _liste[0].id);
      } catch (e) {
        if (annule) return;
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

  const choisi = useMemo(
    () => cours.find((c) => c.id === coursId) || null, [cours, coursId]);

  // La liste est lue par une reference, PAS par la dependance de l'effet.
  // Sinon l'enregistrement, qui rafraichit la liste, recreerait l'objet du
  // cours choisi, relancerait cet effet et effacerait la confirmation que le
  // coach vient tout juste de voir apparaitre.
  const coursRef = useRef([]);
  coursRef.current = cours;

  // Changer de cours recharge SA configuration : sans cela, le coach croirait
  // regler le mercredi alors qu'il regarde les reglages du dimanche.
  useEffect(() => {
    const _c = coursRef.current.find((x) => x.id === coursId);
    if (!_c) return;
    const _actif = _c.reminders_enabled === true;
    const _regles = Array.isArray(_c.reminder_rules) && _c.reminder_rules.length > 0
      ? _c.reminder_rules
      : [{ type: 'relative', minutes: 1440 }, { ...JOUR_MEME_DEFAUT }];
    setActif(_actif);
    setRegles(_regles);
    setEnregistre({ actif: _actif, regles: _c.reminder_rules || [] });
    setErreur('');
    setConfirme(false);
  }, [coursId]);

  const refus = useMemo(() => (actif ? refusDeConfig(regles) : ''), [actif, regles]);
  const modifie = !memeConfig({ actif, regles: actif ? regles : enregistre.regles }, enregistre);

  const majRegles = useCallback((suivantes) => {
    setRegles(suivantes);
    setConfirme(false);
    setErreur('');
  }, []);

  const changerMoment = (index, valeur) => {
    const _s = regles.slice();
    _s[index] = valeur === 'same_day'
      ? { ...JOUR_MEME_DEFAUT }
      : { type: 'relative', minutes: parseInt(valeur.slice(4), 10) };
    majRegles(_s);
  };

  const changerHeure = (index, valeur) => {
    const [_h, _m] = valeur.split(':').map((x) => parseInt(x, 10));
    const _s = regles.slice();
    _s[index] = { type: 'same_day', heure: _h, minute: _m };
    majRegles(_s);
  };

  const ajouter = () => {
    const _defaut = regles.some((r) => r.type === 'relative' && r.minutes === 1440)
      ? { ...JOUR_MEME_DEFAUT }
      : { type: 'relative', minutes: 1440 };
    majRegles(regles.concat([_defaut]));
  };

  const retirer = (index) => majRegles(regles.filter((_, i) => i !== index));

  const basculer = () => {
    setActif((prec) => !prec);
    setConfirme(false);
    setErreur('');
  };

  const enregistrer = async () => {
    if (refus || envoi || !coursId) return;
    setEnvoi(true);
    setErreur('');
    try {
      const res = await axios.put(
        `${API}/coach/courses/${encodeURIComponent(coursId)}/reminders`,
        { enabled: actif, rules: actif ? regles : [] }, entetes);
      if (!monte.current) return;
      const _actif = res.data?.reminders_enabled === true;
      const _regles = Array.isArray(res.data?.rules) ? res.data.rules : [];
      setActif(_actif);
      if (_actif && _regles.length > 0) setRegles(_regles);
      setEnregistre({ actif: _actif, regles: _regles });
      setCours((prec) => prec.map((c) => (c.id === coursId
        ? { ...c, reminders_enabled: _actif, reminder_rules: _regles } : c)));
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
    colorScheme: 'dark',
    backgroundColor: 'rgba(0,0,0,0.45)',
    fontSize: '16px'
  };
  const classeChamp = 'rounded-lg border border-white/10 text-white '
    + 'px-2 py-2 focus:outline-none focus:border-white/30 min-w-0';

  return (
    <div className="card-gradient rounded-xl p-4">
      <div className="flex items-center gap-2 flex-wrap">
        <SvgIcon name="bell" size={16} style={{ color: 'var(--primary-color, #D91CD2)' }} />
        <h2 className="font-semibold text-white text-base sm:text-lg">Rappels avant cours</h2>
      </div>
      <p className="text-white/50 text-xs mt-1">
        Choisis les cours qui envoient des rappels. Ils partent par notification Push
        et par e-mail, selon les préférences de chaque participant.
      </p>

      {chargement && (
        <p className="text-white/40 text-xs mt-3 flex items-center gap-2">
          <SvgIcon name="loader" size={14} className="animate-spin" /> Chargement&hellip;
        </p>
      )}

      {!chargement && indisponible && (
        <p className="text-white/40 text-xs mt-3">{indisponible}</p>
      )}

      {!chargement && !indisponible && cours.length === 0 && (
        <p className="text-white/40 text-xs mt-3" data-testid="cr-aucun-cours">
          Aucun cours à configurer pour le moment.
        </p>
      )}

      {!chargement && !indisponible && cours.length > 0 && (
        <>
          <div className="mt-3 max-w-md">
            <label className="block text-white/50 text-xs mb-1" htmlFor="cr-cours">Cours</label>
            <select
              id="cr-cours"
              value={coursId}
              onChange={(e) => setCoursId(e.target.value)}
              className={`${classeChamp} w-full`}
              style={styleChamp}
              aria-label="Cours à configurer"
              data-testid="cr-cours"
            >
              {cours.map((c) => (
                <option key={c.id} value={c.id}>
                  {libelleCours(c)}
                  {(c.offres || []).some((o) => o.publique) ? ' • vendu' : ''}
                  {c.reminders_enabled === true ? ' • rappels actifs' : ''}
                </option>
              ))}
            </select>
          </div>

          {choisi && (() => {
            // On dit au coach ce que ce cours EST reellement : vendu par quelles
            // offres, publie ou non. Sans cela, six brouillons homonymes sont
            // indiscernables de la vraie seance — c'est ce qui a fait poser les
            // rappels au mauvais endroit.
            const publiques = (choisi.offres || []).filter((o) => o.publique);
            const masquees = (choisi.offres || []).filter((o) => !o.publique);
            return (
              <div className="text-white/40 text-xs mt-2 space-y-1" data-testid="cr-contexte">
                {publiques.length > 0 && (
                  <p data-testid="cr-vendu-par">
                    Vendu par&nbsp;: {publiques.map((o) => o.name).join(', ')}
                  </p>
                )}
                {publiques.length === 0 && masquees.length > 0 && (
                  <p data-testid="cr-offre-masquee">
                    Rattaché uniquement à une offre masquée&nbsp;: pas réservable publiquement.
                  </p>
                )}
                {publiques.length === 0 && masquees.length === 0 && (
                  <p data-testid="cr-sans-offre">
                    Aucune offre ne mène à ce cours&nbsp;: personne ne peut le réserver,
                    donc aucun rappel ne partira.
                  </p>
                )}
                {choisi.visible === false && (
                  <p data-testid="cr-non-publie">
                    Non publié sur ta vitrine. Tu peux quand même régler ses rappels.
                  </p>
                )}
              </div>
            );
          })()}

          <button
            type="button"
            onClick={basculer}
            role="switch"
            aria-checked={actif}
            className="mt-3 flex items-center gap-2 text-xs"
            data-testid="cr-actif"
          >
            <span
              className="inline-block rounded-full"
              style={{
                width: '34px', height: '20px', flexShrink: 0, transition: 'background 0.2s',
                background: actif ? 'var(--primary-color, #D91CD2)' : 'rgba(255,255,255,0.18)',
                position: 'relative'
              }}
            >
              <span
                className="inline-block rounded-full bg-white"
                style={{
                  width: '14px', height: '14px', position: 'absolute', top: '3px',
                  left: actif ? '17px' : '3px', transition: 'left 0.2s'
                }}
              />
            </span>
            <span className="text-white/80">
              Rappels avant cours&nbsp;: {actif ? 'activés' : 'désactivés'}
            </span>
          </button>

          {actif && (
            <>
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
                        data-testid={`cr-moment-${index}`}
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
                          data-testid={`cr-heure-${index}`}
                        >
                          {HEURES_JOUR_MEME.map((h) => (
                            <option key={h.label} value={`${h.heure}:${h.minute}`}>{h.label}</option>
                          ))}
                        </select>
                      )}
                    </div>

                    {regles.length > 1 && (
                      <button
                        type="button"
                        onClick={() => retirer(index)}
                        className="text-white/40 hover:text-white/80 p-2 rounded-lg shrink-0"
                        aria-label={`Retirer le rappel ${index + 1}`}
                        data-testid={`cr-retirer-${index}`}
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
                  data-testid="cr-ajouter"
                >
                  <SvgIcon name="plusCircle" size={14} /> Ajouter un second rappel
                </button>
              )}

              <p className="text-white/40 text-xs mt-2" data-testid="cr-fuseau">
                Fuseau horaire : Europe/Zurich
              </p>
            </>
          )}

          {refus && (
            <p className="text-white/60 text-xs mt-2" data-testid="cr-refus">{refus}</p>
          )}

          <div className="mt-3 flex items-center gap-3">
            <button
              type="button"
              onClick={enregistrer}
              disabled={!modifie || Boolean(refus) || envoi}
              className="text-xs px-3 py-2 rounded-lg text-white disabled:opacity-40"
              style={{ backgroundColor: 'var(--primary-color, #D91CD2)' }}
              data-testid="cr-enregistrer"
            >
              {envoi ? 'Enregistrement…' : 'Enregistrer'}
            </button>
            {confirme && (
              <span className="text-xs text-white/60" data-testid="cr-confirme">Enregistré</span>
            )}
          </div>

          {erreur && (
            <p className="text-white/60 text-xs mt-2" data-testid="cr-erreur">{erreur}</p>
          )}
        </>
      )}
    </div>
  );
};

export default memo(CourseRemindersCard);
