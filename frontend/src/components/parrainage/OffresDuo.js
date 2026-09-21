/**
 * V534b — L'OFFRE DU PASS DUO, CHOISIE PAR LE PARTICIPANT.
 *
 * Trois briques partagées par la carte du parrain (PassDuoCard) et la page
 * publique de l'ami (InvitationDuo) :
 *   - `SelecteurOffres` : cartes verticales radio (nom, avantage, « Offerte »,
 *     validité, conditions, badge « Recommandée ») ;
 *   - `EncartOffre` : une offre affichée telle quelle, sans faux sélecteur
 *     (« OFFRE — nom / avantage », ou « OFFRE ACTUELLE ») ;
 *   - `SheetOffres` : le sélecteur dans un panneau léger — bottom sheet
 *     ancré en bas ≤ 640 px, modale centrée au-delà (CSS `cp-sheet*`) — avec
 *     UNE seule action « Choisir cette offre ». Jamais `window.confirm`.
 *
 * Rien de technique n'est rendu : ni `offer_id`, ni collection, ni type. Les
 * identifiants ne servent qu'aux `value`/`data-testid`, jamais au texte.
 */
import React, { useEffect, useState } from 'react';
import SvgIcon from '../SvgIcon';
import { libelleOffre, avantageOffre } from '../../utils/parrainage';

/** Une carte d'offre (radio). `choisie` = sélectionnée ; `actuelle` = celle du pass. */
function CarteOffre({ offre, choisie, actuelle, onChoisir, name, disabled }) {
  const id = `cp-offre-${name}-${offre.id}`;
  return (
    <label htmlFor={id} className={`cp-offre${choisie ? ' cp-offre--on' : ''}${disabled ? ' cp-offre--off' : ''}`}
           data-testid={`offre-carte-${offre.id}`} data-choisie={choisie ? '1' : '0'}>
      <input id={id} type="radio" name={name} value={offre.id} checked={!!choisie} disabled={disabled}
             onChange={() => onChoisir(offre.id)} className="cp-offre-radio" />
      <span className="cp-offre-coche" aria-hidden="true">
        {choisie ? <SvgIcon name="check" size={14} strokeWidth="3" /> : null}
      </span>
      <span className="cp-offre-corps">
        <span className="cp-offre-tete">
          <b className="cp-offre-nom">{offre.name}</b>
          <span className="cp-offre-prix">{libelleOffre(offre)}</span>
        </span>
        {avantageOffre(offre) ? <span className="cp-offre-avantage">{avantageOffre(offre)}</span> : null}
        {offre.validity ? <span className="cp-offre-detail"><SvgIcon name="clock" size={12} /> Valable {offre.validity}</span> : null}
        {offre.conditions ? <span className="cp-offre-detail cp-offre-conditions">{offre.conditions}</span> : null}
        {(offre.recommended || actuelle) ? (
          <span className="cp-offre-badges">
            {offre.recommended ? <span className="cp-chip cp-chip--ok cp-offre-badge" data-testid="offre-badge-recommandee"><SvgIcon name="star" size={12} strokeWidth="2.5" /> Recommandée</span> : null}
            {actuelle ? <span className="cp-chip cp-chip--ext cp-offre-badge" data-testid="offre-badge-actuelle">Offre actuelle</span> : null}
          </span>
        ) : null}
      </span>
    </label>
  );
}

/**
 * Le sélecteur : cartes verticales radio.
 * @param {object[]} offres      OffreDTO[]
 * @param {string}   choix       l'id choisi (ou null : aucune présélection)
 * @param {function} onChoisir   (offer_id) => void
 * @param {string}   actuelleId  l'offre actuelle du pass (badge « Offre actuelle »)
 * @param {string}   name        nom du groupe radio (unique par écran)
 */
export function SelecteurOffres({ offres, choix, onChoisir, actuelleId, name, disabled, titre }) {
  const liste = Array.isArray(offres) ? offres : [];
  return (
    <div className="cp-offres" role="radiogroup" aria-label={titre || 'Choisis ton offre'} data-testid="offre-selecteur">
      {titre ? <div className="cp-eyebrow cp-offres-titre">{titre}</div> : null}
      {liste.map((o) => (
        <CarteOffre key={o.id} offre={o} choisie={choix != null && String(choix) === String(o.id)}
                    actuelle={actuelleId != null && String(actuelleId) === String(o.id)}
                    onChoisir={onChoisir} name={name || 'cp-offre'} disabled={disabled} />
      ))}
    </div>
  );
}

/** Une offre affichée telle quelle : « OFFRE — nom / avantage » (ou un autre en-tête). */
export function EncartOffre({ offre, titre, note, testid, children }) {
  if (!offre) return null;
  return (
    <div className="cp-offre-encart" data-testid={testid || 'offre-encart'}>
      <div className="cp-eyebrow">{titre || 'Offre'}</div>
      <div className="cp-offre-tete">
        <b className="cp-offre-nom">{offre.name}</b>
        <span className="cp-offre-prix">{libelleOffre(offre)}</span>
      </div>
      {avantageOffre(offre) ? <div className="cp-offre-avantage">{avantageOffre(offre)}</div> : null}
      {offre.validity ? <div className="cp-offre-detail"><SvgIcon name="clock" size={12} /> Valable {offre.validity}</div> : null}
      {offre.conditions ? <div className="cp-offre-detail cp-offre-conditions">{offre.conditions}</div> : null}
      {note ? <p className="cp-fine cp-offre-note">{note}</p> : null}
      {children}
    </div>
  );
}

/**
 * Le panneau de changement d'offre (bottom sheet ≤ 640 px, modale au-delà).
 * @param {object[]} offres       le catalogue courant
 * @param {string}   actuelleId   l'offre actuelle (présélectionnée)
 * @param {function} onChoisir    (offer_id) => void — UNE seule action
 * @param {function} onFermer
 * @param {boolean}  occupe       un appel est en cours
 * @param {string}   message      information (ex. après un conflit de version)
 * @param {string}   erreur       refus du serveur
 */
export function SheetOffres({ offres, actuelleId, onChoisir, onFermer, occupe, message, erreur, titre, name }) {
  const liste = Array.isArray(offres) ? offres : [];
  const [choix, setChoix] = useState(actuelleId || null);
  // Après un rechargement (conflit de version), le catalogue peut avoir changé :
  // on revient sur l'offre actuelle si le choix n'existe plus.
  useEffect(() => {
    const dispo = Array.isArray(offres) ? offres : [];
    setChoix((prev) => (prev && dispo.some((o) => String(o.id) === String(prev)) ? prev : (actuelleId || null)));
  }, [actuelleId, offres]);

  useEffect(() => {
    const surTouche = (e) => { if (e.key === 'Escape' && !occupe) onFermer(); };
    document.addEventListener('keydown', surTouche);
    return () => document.removeEventListener('keydown', surTouche);
  }, [onFermer, occupe]);

  const identique = choix != null && actuelleId != null && String(choix) === String(actuelleId);
  return (
    <div className="cp-sheet-bg" role="dialog" aria-modal="true" aria-label={titre || 'Changer d’offre'}
         onClick={() => { if (!occupe) onFermer(); }} data-testid="offre-sheet">
      <div className="cp-sheet" onClick={(e) => e.stopPropagation()}>
        <div className="cp-sheet-poignee" aria-hidden="true" />
        <div className="cp-sheet-tete">
          <div>
            <div className="cp-eyebrow">{titre || 'Changer d’offre'}</div>
            <p className="cp-mini" style={{ margin: '4px 0 0' }}>Une seule offre par Pass Duo. Le changement est immédiat.</p>
          </div>
          <button type="button" className="cp-iconbtn" onClick={onFermer} disabled={occupe} aria-label="Fermer" data-testid="offre-sheet-fermer">
            <SvgIcon name="x" size={22} />
          </button>
        </div>
        {message ? <p className="cp-notice cp-sheet-message" role="status" data-testid="offre-sheet-message">{message}</p> : null}
        {liste.length ? (
          <SelecteurOffres offres={liste} choix={choix} onChoisir={setChoix} actuelleId={actuelleId} name={name || 'cp-sheet-offre'} disabled={occupe} />
        ) : (
          <p className="cp-empty" data-testid="offre-sheet-vide">Aucune autre offre n'est disponible pour cette séance.</p>
        )}
        {erreur ? <p className="cp-error" role="alert" data-testid="offre-sheet-erreur">{erreur}</p> : null}
        <button type="button" className="cp-b" onClick={() => { if (choix != null && !identique) onChoisir(choix); }}
                disabled={occupe || choix == null || identique || !liste.length} data-testid="offre-choisir">
          <SvgIcon name="check" size={20} /> {occupe ? 'Changement…' : 'Choisir cette offre'}
        </button>
      </div>
    </div>
  );
}
