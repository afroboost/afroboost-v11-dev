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
 *
 * ─────────────────────────────────────────────────────────────────────────
 * POURQUOI CET ECRAN A MENTI, ET CE QUI L'EN EMPECHE DESORMAIS
 * ─────────────────────────────────────────────────────────────────────────
 * Le 03/09/2026, le proprietaire a active les rappels « du mercredi », vu
 * « Rappels avant cours : actives », et la base n'a rien enregistre sur le
 * mercredi. Son enregistrement etait PARTI — sur le dimanche.
 *
 * Trois defauts se cumulaient, et aucun n'etait une erreur de sa part :
 *   1. l'ecran PRESELECTIONNAIT le premier cours de la liste. Or ce premier
 *      cours etait deja active : a l'ouverture, l'interrupteur affichait donc
 *      « actives » sans que personne n'ait rien fait, pour un cours que le
 *      coach ne regardait pas ;
 *   2. un cours SANS regle affichait quand meme « 24 h avant » et « 07:00 »,
 *      parce que ce sont les valeurs proposees par defaut. Deux cours — l'un
 *      configure, l'autre vierge — etaient donc VISUELLEMENT IDENTIQUES ;
 *   3. le `select` ferme ne montre qu'une ligne : la mention « rappels
 *      actifs » des autres cours restait invisible.
 *
 * Ce qui change ici : AUCUNE preselection, des cases a cocher qui montrent
 * l'etat REEL de chaque cours en permanence, un reglage applique a PLUSIEURS
 * cours en une fois, et une distinction explicite entre « enregistre » et
 * « propose ». L'ecran ne peut plus afficher un etat que la base ne porte pas.
 */

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';
const API = `${BACKEND_URL}/api`;

const memeConfig = (a, b) => JSON.stringify(a) === JSON.stringify(b);

const CourseRemindersCard = ({ coachEmail }) => {
  const [cours, setCours] = useState([]);
  // PLUSIEURS cours, et AUCUN par defaut. Le tableau vide est l'etat initial
  // legitime : tant que le coach n'a pas choisi, l'ecran n'affiche l'etat de
  // personne — il ne peut donc plus afficher celui d'un cours qu'on ne
  // regarde pas.
  const [coursIds, setCoursIds] = useState([]);
  const [actif, setActif] = useState(false);
  const [regles, setRegles] = useState([]);
  const [enregistre, setEnregistre] = useState({ actif: false, regles: [] });
  // Vrai quand les regles affichees sont une PROPOSITION, pas ce que la base
  // porte. L'ecran le dit ; sans cela un cours vierge se lit comme un cours
  // configure.
  const [proposees, setProposees] = useState(false);
  const [rapport, setRapport] = useState('');
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
        const res = await axios.get(`${API}/coach/courses`, entetes);
        if (annule) return;
        // Aucun filtre ici : le serveur a deja tranche. En rajouter un
        // reintroduirait exactement le bug qu'on vient de corriger.
        const _liste = (Array.isArray(res.data) ? res.data : []).filter(Boolean);
        setCours(_liste);
        // AUCUNE PRESELECTION. C'est la ligne qui a fait poser les rappels sur
        // le mauvais cours : elle choisissait `_liste[0]`, qui se trouvait etre
        // deja active, et l'ecran s'ouvrait donc sur « actives » — pour un
        // cours que le coach n'avait pas demande.
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

  const choisis = useMemo(
    () => cours.filter((c) => coursIds.indexOf(c.id) !== -1), [cours, coursIds]);
  const choisi = choisis.length === 1 ? choisis[0] : null;

  /** Les cours coches portent-ils DEJA le meme reglage ? PURE. */
  const divergents = useMemo(() => {
    if (choisis.length < 2) return false;
    const _signature = (c) => JSON.stringify({
      a: c.reminders_enabled === true,
      r: Array.isArray(c.reminder_rules) ? c.reminder_rules : []
    });
    const _premier = _signature(choisis[0]);
    return choisis.some((c) => _signature(c) !== _premier);
  }, [choisis]);

  // La liste est lue par une reference, PAS par la dependance de l'effet.
  // Sinon l'enregistrement, qui rafraichit la liste, recreerait l'objet du
  // cours choisi, relancerait cet effet et effacerait la confirmation que le
  // coach vient tout juste de voir apparaitre.
  const coursRef = useRef([]);
  coursRef.current = cours;

  // Changer de cours recharge SA configuration : sans cela, le coach croirait
  // regler le mercredi alors qu'il regarde les reglages du dimanche.
  // La selection change -> on relit l'etat REEL. Plus aucun `return` muet :
  // une selection vide REINITIALISE l'affichage au lieu de laisser en place
  // l'etat du cours precedent.
  useEffect(() => {
    setErreur('');
    setConfirme(false);
    setRapport('');
    const _choisis = coursRef.current.filter((x) => coursIds.indexOf(x.id) !== -1);
    if (_choisis.length === 0) {
      setActif(false);
      setRegles([]);
      setProposees(false);
      setEnregistre({ actif: false, regles: [] });
      return;
    }
    // Le premier coche donne l'etat affiche. S'ils divergent, l'ecran le dit
    // juste au-dessus — on n'invente pas une moyenne entre deux reglages.
    const _c = _choisis[0];
    const _actif = _c.reminders_enabled === true;
    const _dejaEnBase = Array.isArray(_c.reminder_rules) && _c.reminder_rules.length > 0;
    setActif(_actif);
    setRegles(_dejaEnBase
      ? _c.reminder_rules
      : [{ type: 'relative', minutes: 1440 }, { ...JOUR_MEME_DEFAUT }]);
    setProposees(!_dejaEnBase);
    setEnregistre({ actif: _actif, regles: _c.reminder_rules || [] });
  }, [coursIds]);

  const refus = useMemo(() => (actif ? refusDeConfig(regles) : ''), [actif, regles]);
  // ENREGISTRABLE DES QU'UN COURS EST COCHE. Appliquer un reglage identique a
  // un second cours est une action legitime, meme si le premier le porte deja :
  // bloquer sur « rien n'a change » laissait un bouton gris sans explication.
  const modifie = coursIds.length > 1 || divergents || proposees
    || !memeConfig({ actif, regles: actif ? regles : enregistre.regles }, enregistre);

  const majRegles = useCallback((suivantes) => {
    setRegles(suivantes);
    setConfirme(false);
    setErreur('');
    setRapport('');
    // Toucher une regle, c'est deja ne plus afficher celle de la base.
    setProposees(true);
  }, []);

  const basculerCours = useCallback((id) => {
    setCoursIds((prec) => (prec.indexOf(id) === -1
      ? prec.concat([id])
      : prec.filter((x) => x !== id)));
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

  /**
   * Enregistre le MEME reglage sur TOUS les cours coches.
   *
   * UN APPEL PAR COURS, EN SERIE, ET CHACUN COMPTE POUR LUI-MEME. Un echec sur
   * le second n'efface pas le succes du premier : on rend un compte exact
   * (« 2 cours sur 2 »), et l'ecran ne reflete que ce que le SERVEUR a confirme.
   *
   * L'ETAT LOCAL SUIT LA REPONSE, JAMAIS L'INTENTION. C'est la regle qui
   * empeche l'ecran de mentir : si le serveur refuse, rien ne bascule.
   */
  const enregistrer = async () => {
    if (refus || envoi || coursIds.length === 0) return;
    setEnvoi(true);
    setErreur('');
    setRapport('');
    const _corps = { enabled: actif, rules: actif ? regles : [] };
    const _reussis = [];
    const _echecs = [];
    for (let _i = 0; _i < coursIds.length; _i += 1) {
      const _id = coursIds[_i];
      try {
        // eslint-disable-next-line no-await-in-loop
        const res = await axios.put(
          `${API}/coach/courses/${encodeURIComponent(_id)}/reminders`, _corps, entetes);
        const _a = res.data?.reminders_enabled === true;
        const _r = Array.isArray(res.data?.rules) ? res.data.rules : [];
        _reussis.push({ id: _id, actif: _a, regles: _r });
      } catch (e) {
        const _detail = e?.response?.data?.detail;
        _echecs.push({
          id: _id,
          motif: typeof _detail === 'string' && _detail
            ? _detail
            : 'Enregistrement impossible. Réessaie dans un instant.'
        });
      }
    }
    try {
      if (!monte.current) return;
      // La liste locale n'est mise a jour que pour les cours REELLEMENT ecrits.
      if (_reussis.length > 0) {
        setCours((prec) => prec.map((c) => {
          const _ok = _reussis.find((x) => x.id === c.id);
          return _ok
            ? { ...c, reminders_enabled: _ok.actif, reminder_rules: _ok.regles }
            : c;
        }));
        const _ref = _reussis[0];
        setActif(_ref.actif);
        if (_ref.actif && _ref.regles.length > 0) setRegles(_ref.regles);
        setEnregistre({ actif: _ref.actif, regles: _ref.regles });
        setProposees(false);
      }
      if (_echecs.length === 0) {
        setConfirme(true);
        setRapport(coursIds.length > 1
          ? `${_reussis.length} cours sur ${coursIds.length} enregistrés.`
          : '');
        if (minuteur.current) clearTimeout(minuteur.current);
        minuteur.current = setTimeout(() => { if (monte.current) setConfirme(false); }, 4000);
      } else {
        // JAMAIS « enregistré » quand un cours a échoué. On nomme les cours
        // concernés : « une erreur est survenue » ne dit pas quoi refaire.
        const _noms = _echecs.map((x) => {
          const _c = coursRef.current.find((y) => y.id === x.id);
          return _c ? libelleCours(_c) : x.id;
        });
        setErreur(`Non enregistré pour : ${_noms.join(', ')}. ${_echecs[0].motif}`);
      }
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
          <fieldset className="mt-3 max-w-md" data-testid="cr-cours">
            <legend className="text-white/50 text-xs mb-1">
              Cours à régler — coche un ou plusieurs
            </legend>
            <div className="space-y-1 max-h-64 overflow-y-auto pr-1">
              {cours.map((c) => {
                const _coche = coursIds.indexOf(c.id) !== -1;
                const _on = c.reminders_enabled === true;
                return (
                  <label
                    key={c.id}
                    className="flex items-center gap-2 text-xs text-white/80 rounded-lg
                               px-2 py-2 cursor-pointer border"
                    style={{
                      borderColor: _coche
                        ? 'var(--primary-color, #D91CD2)'
                        : 'rgba(255,255,255,0.08)',
                      background: _coche
                        ? 'rgba(var(--primary-rgb, 217, 28, 210), 0.08)'
                        : 'transparent'
                    }}
                    data-testid={`cr-cours-${c.id}`}
                  >
                    <input
                      type="checkbox"
                      checked={_coche}
                      onChange={() => basculerCours(c.id)}
                      aria-label={`Régler les rappels de ${libelleCours(c)}`}
                      style={{ accentColor: 'var(--primary-color, #D91CD2)' }}
                    />
                    <span className="min-w-0 flex-1 truncate">
                      {libelleCours(c)}
                      {(c.offres || []).some((o) => o.publique) ? ' • vendu' : ''}
                    </span>
                    {/* L'ETAT REEL DE CHAQUE COURS, LISIBLE SANS RIEN OUVRIR.
                        C'est ce qui manquait : dans un `select` fermé, la
                        mention « rappels actifs » des autres cours était
                        invisible, et l'écran paraissait dire que TOUT était
                        réglé alors qu'un seul cours l'était. */}
                    <span
                      className="shrink-0 text-[11px]"
                      style={{ color: _on ? 'var(--primary-color, #D91CD2)' : 'rgba(255,255,255,0.35)' }}
                      data-testid={`cr-etat-${c.id}`}
                    >
                      {_on ? 'rappels actifs' : 'aucun rappel'}
                    </span>
                  </label>
                );
              })}
            </div>
          </fieldset>

          {coursIds.length === 0 && (
            <p className="text-white/40 text-xs mt-2" data-testid="cr-aucun-choix">
              Coche au moins un cours pour voir et régler ses rappels.
            </p>
          )}

          {divergents && (
            <p className="text-white/60 text-xs mt-2" data-testid="cr-divergents">
              Ces cours n&apos;ont pas le même réglage aujourd&apos;hui. Ce que tu
              enregistres ici s&apos;appliquera à tous les cours cochés.
            </p>
          )}

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

          {coursIds.length > 0 && (
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
          )}

          {coursIds.length > 0 && actif && proposees && (
            <p className="text-white/40 text-xs mt-2" data-testid="cr-proposees">
              Ces horaires sont une proposition&nbsp;: rien n&apos;est encore
              enregistré pour ce cours. Clique sur Enregistrer pour les poser.
            </p>
          )}

          {coursIds.length > 0 && actif && (
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
              disabled={coursIds.length === 0 || !modifie || Boolean(refus) || envoi}
              className="text-xs px-3 py-2 rounded-lg text-white disabled:opacity-40"
              style={{ backgroundColor: 'var(--primary-color, #D91CD2)' }}
              data-testid="cr-enregistrer"
            >
              {envoi ? 'Enregistrement…' : 'Enregistrer'}
            </button>
            {confirme && (
              <span className="text-xs text-white/60" data-testid="cr-confirme">
                Enregistré{rapport ? ` — ${rapport}` : ''}
              </span>
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
