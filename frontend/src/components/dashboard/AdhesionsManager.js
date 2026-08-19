/**
 * P1-bis-a — ADHÉSIONS : la saisie à la main, et rien d'autre.
 * ============================================================
 *
 * CE QUE CET ÉCRAN FAIT : le coach enregistre qu'une personne est membre, du
 * jour J au jour J+n, et pour quel montant de carte. Il relit ensuite ce qu'il
 * a saisi.
 *
 * CE QU'IL NE FAIT PAS : aucun prix n'est modifié, aucune réduction n'est
 * proposée, aucun renouvellement n'est déclenché. Cet écran n'est branché sur
 * aucun parcours d'achat — c'est le socle de P1-bis-b, pas P1-bis-b.
 *
 * LE STATUT VIENT DU SERVEUR, ET LE SERVEUR LE CALCULE DEPUIS LES DATES.
 * Aucun booléen « est membre » n'est stocké ni affiché : « Active », « Future »
 * et « Expirée » sont trois lectures d'un couple de dates. C'est la leçon de
 * V393 — un statut figé finit toujours par mentir.
 *
 * CHARGEMENT : passe par `useChargement` (socle P0). Une liste vide ne peut
 * donc pas être confondue avec un refus : tant que la réponse n'est pas là,
 * l'écran dit « — », et un refus est annoncé comme tel.
 *
 * COULEURS : uniquement `var(--primary-color)` / `var(--primary-rgb)`. Aucun
 * hexadécimal imposé — les valeurs après la virgule sont des replis.
 * ICÔNES : SVG inline via `SvgIcon`, jamais d'emoji.
 */
import React, { useCallback, useMemo, useState } from 'react';
import axios from 'axios';
import SvgIcon from '../SvgIcon';
import useChargement, { SECTION } from '../../hooks/useChargement';
import { SectionErreur } from '../ui/EtatChargement';
import { echecDeReponse } from '../../utils/authSession';

const PRIMAIRE = 'var(--primary-color, #D91CD2)';
const PRIMAIRE_RGB = 'var(--primary-rgb, 217, 28, 210)';

/** Libellés d'affichage des statuts calculés côté serveur. */
const LIBELLE_STATUT = {
  active: 'Active',
  future: 'Future',
  expiree: 'Expirée',
  invalide: 'Dates illisibles',
};

/** Moyens de paiement — mêmes valeurs que le lot B (`B_ORIGINES_MANUELLES`). */
const MOYENS = [
  { valeur: 'especes', libelle: 'Espèces' },
  { valeur: 'twint', libelle: 'TWINT' },
  { valeur: 'virement', libelle: 'Virement' },
  { valeur: 'offert', libelle: 'Offert' },
];

const FORMULAIRE_VIDE = {
  email: '', name: '', date_debut: '', date_fin: '',
  montant: '', origine_paiement: '',
};

/** JJ.MM.AAAA à partir d'un AAAA-MM-JJ, sans passer par `Date` (aucun fuseau). */
function enDateSuisse(iso) {
  const brut = String(iso || '');
  if (!/^\d{4}-\d{2}-\d{2}$/.test(brut)) return brut || '—';
  return `${brut.slice(8, 10)}.${brut.slice(5, 7)}.${brut.slice(0, 4)}`;
}

function Pastille({ statut }) {
  // « Active » porte la couleur de marque ; les deux autres restent neutres,
  // pour que l'œil trouve les adhésions en cours sans lire.
  const enCours = statut === 'active';
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: '5px',
      padding: '2px 9px', borderRadius: '999px',
      fontSize: '11px', fontWeight: 700, whiteSpace: 'nowrap',
      color: enCours ? PRIMAIRE : 'rgba(255,255,255,0.6)',
      background: enCours ? `rgba(${PRIMAIRE_RGB}, 0.14)` : 'rgba(255,255,255,0.05)',
      border: `1px solid ${enCours ? `rgba(${PRIMAIRE_RGB}, 0.45)` : 'rgba(255,255,255,0.12)'}`,
    }}>
      {LIBELLE_STATUT[statut] || statut || '—'}
    </span>
  );
}

export default function AdhesionsManager({ API }) {
  const [formulaire, setFormulaire] = useState(FORMULAIRE_VIDE);
  const [enregistrement, setEnregistrement] = useState(false);
  const [message, setMessage] = useState(null); // { type: 'ok' | 'erreur', texte }

  const base = API || '';

  // `signature: true` : cette route est JWT-strict par construction (elle rend
  // des adresses e-mail). Le portillon évite un aller-retour dont on connaît
  // déjà le verdict quand aucune preuve signée n'est en poche.
  const chargement = useChargement(
    {
      adhesions: {
        url: `${base}/memberships`,
        signature: true,
        appel: async () => {
          const rep = await axios.get(`${base}/memberships`, { params: { limit: 50 } });
          if (!rep || !rep.data || rep.data.success !== true) {
            throw echecDeReponse('adhesions non livrees', 'serveur');
          }
          return rep.data;
        },
        extraire: (donnees) => donnees,
      },
    },
    { deps: [base] }
  );

  const section = chargement.sections.adhesions;
  const etat = (section && section.etat) || SECTION.CHARGEMENT;
  const charge = etat === SECTION.OK && section.donnees ? section.donnees : null;

  // La liste est DÉRIVÉE de la section, jamais recopiée dans un état local :
  // pas de `setState` d'objet, donc aucun effet à relancer et aucune boucle
  // possible (règle absolue du dépôt, incident V305).
  const liste = (charge && charge.memberships) || [];

  const recharger = useCallback(() => chargement.reessayer('adhesions'), [chargement]);

  // « Offert » n'admet aucun montant : règle du lot B, rappelée ici pour que le
  // coach la voie AVANT d'envoyer — jamais à la place du serveur, qui reste
  // seul juge et refuse en 400.
  const offert = formulaire.origine_paiement === 'offert';

  const majChamp = (cle, valeur) => {
    setFormulaire((prec) => {
      if (prec[cle] === valeur) return prec;
      const suivant = { ...prec, [cle]: valeur };
      if (cle === 'origine_paiement' && valeur === 'offert') suivant.montant = '';
      return suivant;
    });
    setMessage(null);
  };

  const complet = useMemo(
    () => !!(formulaire.email.trim() && formulaire.date_debut && formulaire.date_fin),
    [formulaire.email, formulaire.date_debut, formulaire.date_fin]
  );

  const enregistrer = async (evenement) => {
    if (evenement && evenement.preventDefault) evenement.preventDefault();
    if (!complet || enregistrement) return;
    setEnregistrement(true);
    setMessage(null);
    try {
      const corps = {
        email: formulaire.email.trim(),
        name: formulaire.name.trim(),
        date_debut: formulaire.date_debut,
        date_fin: formulaire.date_fin,
      };
      // Champs financiers envoyés seulement s'ils sont renseignés : le serveur
      // accepte une adhésion sans montant (la carte peut être réglée plus tard).
      if (formulaire.origine_paiement) corps.origine_paiement = formulaire.origine_paiement;
      if (formulaire.montant !== '') corps.montant = formulaire.montant;

      const rep = await axios.post(`${base}/memberships`, corps);
      if (!rep || !rep.data || rep.data.success !== true) {
        throw echecDeReponse('adhesion non enregistree', 'serveur');
      }
      setFormulaire(FORMULAIRE_VIDE);
      setMessage({ type: 'ok', texte: 'Adhésion enregistrée.' });
      recharger();
    } catch (err) {
      const detail = err && err.response && err.response.data && err.response.data.detail;
      setMessage({
        type: 'erreur',
        texte: detail || "L'adhésion n'a pas pu être enregistrée.",
      });
    } finally {
      setEnregistrement(false);
    }
  };

  const styleChamp = {
    width: '100%', padding: '9px 11px', borderRadius: '9px',
    border: '1px solid rgba(255,255,255,0.12)',
    background: 'rgba(255,255,255,0.04)',
    color: '#fff', fontSize: '13px', outline: 'none',
  };
  const styleEtiquette = {
    display: 'block', marginBottom: '5px',
    fontSize: '11px', fontWeight: 600, color: 'rgba(255,255,255,0.55)',
  };

  return (
    <div style={{ marginTop: 12 }}>
      {/* ---------------------------------------------------------------- */}
      {/* Saisie                                                            */}
      {/* ---------------------------------------------------------------- */}
      <form
        onSubmit={enregistrer}
        style={{
          padding: '14px', borderRadius: '12px',
          background: 'rgba(255,255,255,0.03)',
          border: `1px solid rgba(${PRIMAIRE_RGB}, 0.25)`,
          marginBottom: '16px',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px' }}>
          <span style={{ color: PRIMAIRE, display: 'inline-flex' }}>
            <SvgIcon name="crown" size={18} color="currentColor" />
          </span>
          <span style={{ color: '#fff', fontSize: '14px', fontWeight: 700 }}>
            Enregistrer une adhésion
          </span>
        </div>

        <div style={{
          display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '10px',
        }}>
          <div>
            <label style={styleEtiquette} htmlFor="adhesion-email">Participant (e-mail)</label>
            <input
              id="adhesion-email" type="email" style={styleChamp}
              placeholder="prenom@exemple.com"
              value={formulaire.email}
              onChange={(e) => majChamp('email', e.target.value)}
            />
          </div>
          <div>
            <label style={styleEtiquette} htmlFor="adhesion-nom">Nom (facultatif)</label>
            <input
              id="adhesion-nom" type="text" style={styleChamp}
              placeholder="Prénom Nom"
              value={formulaire.name}
              onChange={(e) => majChamp('name', e.target.value)}
            />
          </div>
          <div>
            <label style={styleEtiquette} htmlFor="adhesion-debut">Début</label>
            <input
              id="adhesion-debut" type="date" style={styleChamp}
              value={formulaire.date_debut}
              onChange={(e) => majChamp('date_debut', e.target.value)}
            />
          </div>
          <div>
            <label style={styleEtiquette} htmlFor="adhesion-fin">Fin</label>
            <input
              id="adhesion-fin" type="date" style={styleChamp}
              value={formulaire.date_fin}
              onChange={(e) => majChamp('date_fin', e.target.value)}
            />
          </div>
          <div>
            <label style={styleEtiquette} htmlFor="adhesion-moyen">Moyen de paiement</label>
            <select
              id="adhesion-moyen" style={styleChamp}
              value={formulaire.origine_paiement}
              onChange={(e) => majChamp('origine_paiement', e.target.value)}
            >
              <option value="">— non renseigné —</option>
              {MOYENS.map((m) => (
                <option key={m.valeur} value={m.valeur}>{m.libelle}</option>
              ))}
            </select>
          </div>
          <div>
            <label style={styleEtiquette} htmlFor="adhesion-montant">Montant carte membre</label>
            <input
              id="adhesion-montant" type="number" min="0" step="0.05" style={{
                ...styleChamp,
                opacity: offert ? 0.45 : 1,
              }}
              placeholder={offert ? 'Offert' : 'ex. 100'}
              disabled={offert}
              value={formulaire.montant}
              onChange={(e) => majChamp('montant', e.target.value)}
            />
          </div>
        </div>

        <p style={{
          margin: '10px 0 0', fontSize: '11px', lineHeight: 1.5,
          color: 'rgba(255,255,255,0.45)',
        }}>
          Le montant est facultatif. S'il est saisi, le moyen de paiement l'est aussi —
          et « Offert » se déclare sans montant. Enregistrer une adhésion ne change
          aucun prix : les avantages membres viendront plus tard.
        </p>

        {message && (
          <div style={{
            marginTop: '10px', padding: '8px 11px', borderRadius: '9px', fontSize: '12px',
            color: message.type === 'ok' ? PRIMAIRE : 'rgba(255,255,255,0.8)',
            background: message.type === 'ok'
              ? `rgba(${PRIMAIRE_RGB}, 0.10)` : 'rgba(255,255,255,0.06)',
            border: `1px solid ${message.type === 'ok'
              ? `rgba(${PRIMAIRE_RGB}, 0.35)` : 'rgba(255,255,255,0.14)'}`,
          }}>
            {message.texte}
          </div>
        )}

        <button
          type="submit"
          disabled={!complet || enregistrement}
          style={{
            marginTop: '12px', padding: '9px 18px', borderRadius: '9px',
            border: 'none', cursor: (!complet || enregistrement) ? 'not-allowed' : 'pointer',
            background: (!complet || enregistrement)
              ? 'rgba(255,255,255,0.08)'
              : `linear-gradient(135deg, ${PRIMAIRE}, rgba(${PRIMAIRE_RGB}, 0.65))`,
            color: (!complet || enregistrement) ? 'rgba(255,255,255,0.4)' : '#fff',
            fontSize: '13px', fontWeight: 700,
          }}
        >
          {enregistrement ? 'Enregistrement…' : 'Enregistrer'}
        </button>
      </form>

      {/* ---------------------------------------------------------------- */}
      {/* Liste                                                             */}
      {/* ---------------------------------------------------------------- */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        marginBottom: '10px', gap: '10px', flexWrap: 'wrap',
      }}>
        <span style={{ color: '#fff', fontSize: '13px', fontWeight: 700 }}>
          Adhésions enregistrées
        </span>
        <span style={{ color: 'rgba(255,255,255,0.45)', fontSize: '12px' }}>
          {etat === SECTION.OK && charge ? `${charge.total} au total` : '—'}
        </span>
      </div>

      {(etat === SECTION.ERREUR || etat === SECTION.SESSION) && (
        <SectionErreur
          motif={(section && section.motif) || 'serveur'}
          quoi="les adhésions"
          onReessayer={recharger}
        />
      )}

      {etat === SECTION.CHARGEMENT && (
        <div style={{ color: 'rgba(255,255,255,0.45)', fontSize: '12px', padding: '10px 0' }}>
          Chargement…
        </div>
      )}

      {etat === SECTION.OK && liste.length === 0 && (
        <div style={{
          padding: '14px', borderRadius: '10px', fontSize: '12px',
          color: 'rgba(255,255,255,0.5)',
          background: 'rgba(255,255,255,0.03)',
          border: '1px solid rgba(255,255,255,0.08)',
        }}>
          Aucune adhésion enregistrée. Les adhésions passées ne sont pas devinées :
          seules celles saisies ici existent.
        </div>
      )}

      {etat === SECTION.OK && liste.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          {liste.map((a) => (
            <div
              key={a.id}
              style={{
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                gap: '10px', flexWrap: 'wrap',
                padding: '10px 12px', borderRadius: '10px',
                background: 'rgba(255,255,255,0.03)',
                border: '1px solid rgba(255,255,255,0.08)',
              }}
            >
              <div style={{ minWidth: 0, flex: '1 1 180px' }}>
                <div style={{
                  color: '#fff', fontSize: '13px', fontWeight: 600,
                  overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                }}>
                  {a.name || a.email}
                </div>
                {a.name && (
                  <div style={{
                    color: 'rgba(255,255,255,0.45)', fontSize: '11px',
                    overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                  }}>
                    {a.email}
                  </div>
                )}
              </div>
              <div style={{ color: 'rgba(255,255,255,0.6)', fontSize: '12px', whiteSpace: 'nowrap' }}>
                {enDateSuisse(a.date_debut)} → {enDateSuisse(a.date_fin)}
              </div>
              <div style={{ color: 'rgba(255,255,255,0.6)', fontSize: '12px', whiteSpace: 'nowrap' }}>
                {typeof a.montant_encaisse === 'number'
                  ? `${a.devise || 'CHF'} ${a.montant_encaisse.toFixed(2)}`
                  : '—'}
              </div>
              <Pastille statut={a.statut} />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
