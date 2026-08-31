// PartnerApplications.js — P2-A : les candidatures partenaire deviennent lisibles.
//
// CE QU'IL CORRIGE. Le tunnel « Devenir Partenaire Afroboost » enregistre des
// candidatures depuis P1.2, mais rien ne les affichait : la carte du lien compte
// des clics, des questions et des actions, jamais des candidatures. Le coach ne
// recevait qu'une notification « Nouveau prospect » — sans le nom de
// l'établissement, sans les réponses, sans rien à faire. Les réponses étaient en
// base et personne ne pouvait les lire.
//
// P2-B ajoute la DECISION : accepter ou refuser, manuellement. Toujours aucun QR
// et aucun lien UTM affiche — c'est P2-C. Le statut « En attente » reste ce que le
// serveur calcule pour les candidatures sans decision, il n'est ecrit nulle part.
//
// LE SLUG SE SAISIT AVANT D'ACCEPTER, ET PAS APRES. Une suggestion est proposee a
// partir du nom, mais elle est MODIFIABLE : c'est le coach qui lit la candidature
// et sait si le partenaire s'appelle `akoko_tresses` ou autrement. Une generation
// automatique a partir d'un champ de texte libre produirait des adresses que
// personne n'a choisies. Et l'ecran le dit avant de valider : le slug ne pourra
// plus changer.
//
// LES RÉPONSES SONT RENDUES DE FAÇON GÉNÉRIQUE. `answers` est auto-descriptif —
// chaque entrée porte son propre libellé (`{question, answer}`). On boucle donc
// dessus sans jamais nommer `q_0` ni `q_1` : le questionnaire du tunnel peut
// gagner, perdre ou réordonner des questions sans qu'une ligne de ce fichier
// change. C'est la raison d'être de ce format, il serait dommage de la perdre en
// codant les positions en dur.
//
// TRANSPORT : `axios`, jamais `fetch`. L'intercepteur global (App.js) pose déjà
// `Authorization: Bearer` sur tous les appels axios ; `fetch` ne passe pas par
// lui et reviendrait en 403 sur une route gardée. La logique du jeton n'est
// recopiée nulle part ici — c'est l'intercepteur qui la détient, et lui seul.

import React, { useCallback, useEffect, useRef, useState } from 'react';
import axios from 'axios';
import { X, Mail, Phone, Calendar, Clock, RefreshCw, Inbox, AlertCircle, Check, Ban } from 'lucide-react';

/** Les réponses arrivent en dict (`{q_0: {...}}`) ou en liste. Les deux formes
 *  existent en base ; on rend une liste ordonnée dans les deux cas. */
export function p2aNormaliserReponses(answers) {
  if (!answers) return [];
  const brut = Array.isArray(answers)
    ? answers
    : Object.keys(answers).sort().map((cle) => answers[cle]);
  return brut
    .map((e) => {
      if (!e || typeof e !== 'object') return null;
      const question = String(e.question || '').trim();
      const answer = e.answer === null || e.answer === undefined ? '' : String(e.answer).trim();
      if (!question && !answer) return null;
      return { question, answer };
    })
    .filter(Boolean);
}

/** Suggestion de slug a partir d'un nom. Le coach peut TOUJOURS la corriger.
 *
 *  Les accents sont deplies (NFD) plutot que supprimes : « Récif » donne
 *  `recif`, pas `rcif`. Tout ce qui n'est pas [a-z0-9] devient `_`, les `_`
 *  consecutifs sont fondus, et le resultat est borne a 40 caracteres — la meme
 *  regle que le serveur, qui reste le seul a decider si un slug est valide.
 */
export function p2bSuggererSlug(nom) {
  const base = String(nom || '')
    .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/_+/g, '_')
    .replace(/^_|_$/g, '');
  return base.slice(0, 40);
}

/** Le slug est-il acceptable ? MEME regle que le serveur, mot pour mot. */
export function p2bSlugValide(slug) {
  return /^[a-z0-9_]{3,40}$/.test(String(slug || ''));
}

/** Date lisible, sans jamais afficher « Invalid Date » au coach. */
export function p2aDateLisible(valeur) {
  if (!valeur) return '—';
  try {
    const d = new Date(valeur);
    if (isNaN(d.getTime())) return '—';
    return new Intl.DateTimeFormat('fr-CH', {
      day: '2-digit', month: 'short', year: '2-digit',
      hour: '2-digit', minute: '2-digit',
    }).format(d);
  } catch (e) {
    return '—';
  }
}

const LIBELLES_DECISION = {
  pending: 'En attente',
  accepted: 'Acceptée',
  rejected: 'Refusée',
};

const COULEURS_DECISION = {
  pending: '#f59e0b',
  accepted: '#22c55e',
  rejected: '#ef4444',
};

const Etiquette = ({ decision }) => {
  const cle = LIBELLES_DECISION[decision] ? decision : 'pending';
  const couleur = COULEURS_DECISION[cle];
  return (
    <span style={{
      padding: '3px 10px', borderRadius: '10px', whiteSpace: 'nowrap',
      background: `${couleur}18`, color: couleur,
      fontSize: '10px', fontWeight: 700, letterSpacing: '0.3px',
    }}>
      {LIBELLES_DECISION[cle]}
    </span>
  );
};

const Ligne = ({ icone, valeur }) => {
  if (!valeur) return null;
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: '6px',
      color: 'rgba(255,255,255,0.55)', fontSize: '12px', minWidth: 0,
    }}>
      {icone}
      <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{valeur}</span>
    </div>
  );
};

const BoutonAction = ({ onClick, disabled, couleur, children, style }) => (
  <button
    type="button"
    onClick={onClick}
    disabled={disabled}
    style={{
      flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center',
      gap: '6px', padding: '9px 0', borderRadius: '10px',
      background: `${couleur}14`, border: `1px solid ${couleur}33`, color: couleur,
      fontSize: '12px', fontWeight: 700,
      cursor: disabled ? 'not-allowed' : 'pointer', opacity: disabled ? 0.5 : 1,
      ...style,
    }}
  >
    {children}
  </button>
);

const Candidature = ({ item, onDecider, enCours }) => {
  const reponses = p2aNormaliserReponses(item.answers);
  const enAttente = (item.application_decision || 'pending') === 'pending';
  // `etape` : null (rien) | 'accept' (saisie du slug) | 'reject' (confirmation)
  const [etape, setEtape] = useState(null);
  const [slug, setSlug] = useState('');
  const [erreurLocale, setErreurLocale] = useState('');

  const ouvrirAcceptation = () => {
    // La suggestion est un POINT DE DEPART, pas une decision : le champ reste
    // libre, et c'est bien le coach qui tranche.
    setSlug(p2bSuggererSlug(item.name));
    setErreurLocale('');
    setEtape('accept');
  };

  const valider = async (decision) => {
    setErreurLocale('');
    if (decision === 'accepted' && !p2bSlugValide(slug)) {
      setErreurLocale('3 à 40 caractères : lettres minuscules, chiffres et « _ » uniquement.');
      return;
    }
    const retour = await onDecider(item, decision, decision === 'accepted' ? slug : undefined);
    // `null` = appel IGNORE (un envoi est deja en cours). Surtout ne pas le
    // confondre avec un succes : le confondre refermait l'ecran de saisie au
    // second clic d'un double clic, alors que rien n'etait encore enregistre.
    if (retour === null) return;
    if (retour) setErreurLocale(retour);
    else setEtape(null);
  };

  return (
    <div style={{
      padding: '14px', borderRadius: '12px', marginBottom: '10px',
      background: 'rgba(255,255,255,0.04)',
      border: '1px solid rgba(255,255,255,0.08)',
    }}>
      <div style={{
        display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between',
        gap: '10px', marginBottom: '8px', flexWrap: 'wrap',
      }}>
        <div style={{ minWidth: 0, flex: '1 1 160px' }}>
          <p style={{
            margin: 0, color: '#FFFFFF', fontSize: '14px', fontWeight: 700,
            overflow: 'hidden', textOverflow: 'ellipsis',
          }}>
            {item.name || 'Sans nom'}
          </p>
          <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap', marginTop: '4px' }}>
            <Ligne icone={<Calendar size={12} />} valeur={p2aDateLisible(item.created_at)} />
            <Ligne icone={<Mail size={12} />} valeur={item.email} />
            <Ligne icone={<Phone size={12} />} valeur={item.whatsapp} />
          </div>
        </div>
        <Etiquette decision={item.application_decision} />
      </div>

      {reponses.length > 0 && (
        <div style={{ marginTop: '10px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
          {reponses.map((r, i) => (
            <div key={i} style={{
              padding: '8px 10px', borderRadius: '8px',
              background: 'rgba(var(--primary-rgb, 217, 28, 210), 0.06)',
              border: '1px solid rgba(var(--primary-rgb, 217, 28, 210), 0.14)',
            }}>
              <p style={{
                margin: 0, color: 'rgba(255,255,255,0.5)', fontSize: '11px', lineHeight: 1.4,
              }}>
                {r.question}
              </p>
              <p style={{
                margin: '3px 0 0', color: '#FFFFFF', fontSize: '13px',
                fontWeight: 600, lineHeight: 1.4, wordBreak: 'break-word',
              }}>
                {r.answer || '—'}
              </p>
            </div>
          ))}
        </div>
      )}

      {/* P2-B — LA DECISION. Uniquement pour une candidature EN ATTENTE : une
          decision est definitive, et un bouton qui la renverserait n'a pas sa
          place ici (le serveur refuse d'ailleurs en 409). */}
      {enAttente && onDecider && (
        <div style={{ marginTop: '12px', paddingTop: '10px',
                      borderTop: '1px solid rgba(255,255,255,0.07)' }}>
          {etape === null && (
            <div style={{ display: 'flex', gap: '8px' }}>
              <BoutonAction onClick={ouvrirAcceptation} disabled={enCours} couleur="#22c55e">
                <Check size={13} /> Accepter
              </BoutonAction>
              <BoutonAction onClick={() => { setErreurLocale(''); setEtape('reject'); }}
                            disabled={enCours} couleur="#ef4444">
                <Ban size={13} /> Refuser
              </BoutonAction>
            </div>
          )}

          {etape === 'accept' && (
            <div>
              <p style={{ margin: '0 0 6px', color: 'rgba(255,255,255,0.6)', fontSize: '11px' }}>
                Identifiant du partenaire
              </p>
              <input
                aria-label="Identifiant du partenaire"
                value={slug}
                onChange={(e) => setSlug(e.target.value)}
                disabled={enCours}
                style={{
                  width: '100%', boxSizing: 'border-box', padding: '9px 10px',
                  borderRadius: '10px', background: 'rgba(255,255,255,0.06)',
                  border: '1px solid rgba(255,255,255,0.14)', color: '#FFFFFF',
                  fontSize: '13px', fontFamily: 'monospace',
                }}
              />
              <p style={{ margin: '6px 0 0', color: 'rgba(255,255,255,0.45)',
                          fontSize: '11px', lineHeight: 1.45 }}>
                Cet identifiant sera utilisé pour son lien personnel.
                Il ne pourra plus être modifié après l'acceptation.
              </p>
              <div style={{ display: 'flex', gap: '8px', marginTop: '10px' }}>
                <BoutonAction onClick={() => setEtape(null)} disabled={enCours} couleur="#9ca3af">
                  Annuler
                </BoutonAction>
                <BoutonAction onClick={() => valider('accepted')} disabled={enCours} couleur="#22c55e">
                  {enCours ? 'Enregistrement…' : 'Accepter le partenaire'}
                </BoutonAction>
              </div>
            </div>
          )}

          {etape === 'reject' && (
            <div>
              <p style={{ margin: 0, color: 'rgba(255,255,255,0.7)', fontSize: '12px' }}>
                Refuser cette candidature ? Cette décision est définitive.
              </p>
              <div style={{ display: 'flex', gap: '8px', marginTop: '10px' }}>
                <BoutonAction onClick={() => setEtape(null)} disabled={enCours} couleur="#9ca3af">
                  Annuler
                </BoutonAction>
                <BoutonAction onClick={() => valider('rejected')} disabled={enCours} couleur="#ef4444">
                  {enCours ? 'Enregistrement…' : 'Confirmer le refus'}
                </BoutonAction>
              </div>
            </div>
          )}

          {erreurLocale && (
            <p style={{ margin: '8px 0 0', color: '#ef4444', fontSize: '11px' }}>
              {erreurLocale}
            </p>
          )}
        </div>
      )}

      {/* Le slug, une fois acquis, est une information discrete : il sert au
          lot suivant (lien + QR), pas ici. */}
      {item.partner_slug && (
        <p style={{ margin: '10px 0 0', color: 'rgba(255,255,255,0.4)',
                    fontSize: '11px', fontFamily: 'monospace' }}>
          {item.partner_slug}
        </p>
      )}
    </div>
  );
};

const PartnerApplications = ({ isOpen, onClose, link, API }) => {
  const [chargement, setChargement] = useState(false);
  const [erreur, setErreur] = useState('');
  const [donnees, setDonnees] = useState(null);
  // `enCours` porte l'identifiant de la candidature en cours d'ecriture. Il
  // desactive TOUS les boutons de decision pendant l'appel : c'est ce qui rend
  // le double clic sans effet cote navigateur. Le serveur, lui, ne s'y fie pas
  // — son idempotence repose sur une ecriture atomique.
  const [enCours, setEnCours] = useState('');
  // ⚠️ LE VERROU EST UNE `ref`, PAS LE `state`.
  // `setEnCours` ne prend effet qu'au rendu suivant : deux clics separes de
  // moins d'un rendu voient donc tous les deux `enCours === ''` et partent tous
  // les deux. Mesure faite — le test du double clic recevait 2 appels. Une
  // `ref` change de valeur IMMEDIATEMENT, donc le second clic est arrete avant
  // l'appel. Le `state`, lui, reste : c'est lui qui grise les boutons.
  const verrou = useRef('');

  const jeton = (link && (link.link_token || link.token)) || '';

  const charger = useCallback(async () => {
    if (!jeton) return;
    setChargement(true);
    setErreur('');
    try {
      const { data } = await axios.get(`${API}/partner-applications/${encodeURIComponent(jeton)}`);
      setDonnees(data);
    } catch (e) {
      const code = e && e.response && e.response.status;
      // On distingue le refus d'accès du reste : « réessayer » ne sert à rien
      // quand la session est en cause, et laisser croire le contraire ferait
      // tourner le coach en rond.
      setErreur(
        code === 401 || code === 403
          ? 'Accès refusé — reconnectez-vous, puis rouvrez cette fenêtre.'
          : code === 404
            ? "Ce lien n'a pas de candidatures partenaire."
            : 'Chargement impossible pour le moment.'
      );
      setDonnees(null);
    } finally {
      setChargement(false);
    }
  }, [API, jeton]);

  // Dépendances PRIMITIVES uniquement (`isOpen`, `jeton`) : faire dépendre cet
  // effet de l'objet `link` le relancerait à chaque rendu du parent, ce qui est
  // exactement le motif de boucle d'appels que le dépôt proscrit.
  useEffect(() => {
    if (isOpen && jeton) charger();
  }, [isOpen, jeton, charger]);

  // P2-B — LA DECISION.
  // Renvoie '' en cas de succes, le message a afficher en cas d'echec, et
  // `null` quand l'appel est IGNORE parce qu'un envoi est deja en cours.
  // Apres succes on RECHARGE la liste : la source de verite est le serveur, et
  // recopier a la main l'etat qu'on croit avoir obtenu ferait diverger l'ecran
  // de la base au premier cas limite (rejeu, decision concurrente).
  const decider = useCallback(async (item, decision, partnerSlug) => {
    // `null` — et non `''` — pour dire « je n'ai rien fait ». La distinction
    // compte : l'appelant ne doit pas prendre un appel ignore pour un succes.
    if (!item || !item.id || verrou.current) return null;
    verrou.current = item.id;
    setEnCours(item.id);
    try {
      const corps = { decision };
      if (partnerSlug) corps.partner_slug = partnerSlug;
      await axios.patch(
        `${API}/partner-applications/${encodeURIComponent(item.id)}/decision`, corps);
      await charger();
      return '';
    } catch (e) {
      const code = e && e.response && e.response.status;
      const detail = e && e.response && e.response.data && e.response.data.detail;
      if (code === 409) {
        // Collision de slug, ou candidature deja tranchee ailleurs. Le message
        // du serveur est le bon : il sait laquelle des deux.
        await charger();
        return detail || 'Cette candidature a déjà été traitée.';
      }
      if (code === 400) return detail || 'Décision refusée.';
      if (code === 401 || code === 403) return 'Accès refusé — reconnectez-vous.';
      return 'Enregistrement impossible pour le moment.';
    } finally {
      verrou.current = '';
      setEnCours('');
    }
  }, [API, charger]);

  if (!isOpen) return null;

  const liste = (donnees && donnees.applications) || [];

  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, zIndex: 1000,
        background: 'rgba(0,0,0,0.72)',
        display: 'flex', alignItems: 'flex-end', justifyContent: 'center',
        padding: '0',
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-label="Candidatures partenaire"
        style={{
          width: '100%', maxWidth: '560px', maxHeight: '86vh',
          display: 'flex', flexDirection: 'column',
          background: '#151515',
          borderRadius: '16px 16px 0 0',
          border: '1px solid rgba(255,255,255,0.1)',
          borderBottom: 'none',
          boxShadow: '0 -8px 40px rgba(0,0,0,0.6)',
        }}
      >
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          gap: '10px', padding: '16px', borderBottom: '1px solid rgba(255,255,255,0.08)',
        }}>
          <div style={{ minWidth: 0 }}>
            <p style={{ margin: 0, color: '#FFFFFF', fontSize: '15px', fontWeight: 800 }}>
              Candidatures
            </p>
            <p style={{
              margin: '2px 0 0', color: 'rgba(255,255,255,0.45)', fontSize: '12px',
              overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
            }}>
              {(donnees && donnees.title) || (link && link.title) || 'Lien partenaire'}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Fermer"
            style={{
              width: '34px', height: '34px', flexShrink: 0, borderRadius: '10px',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.1)',
              color: 'rgba(255,255,255,0.7)', cursor: 'pointer',
            }}
          >
            <X size={16} />
          </button>
        </div>

        <div style={{ padding: '14px', overflowY: 'auto', flex: 1 }}>
          {chargement && (
            <div style={{
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              gap: '8px', padding: '32px 0', color: 'rgba(255,255,255,0.5)', fontSize: '13px',
            }}>
              <Clock size={14} /> Chargement des candidatures…
            </div>
          )}

          {!chargement && erreur && (
            <div style={{ padding: '24px 0', textAlign: 'center' }}>
              <AlertCircle size={22} color="#ef4444" />
              <p style={{ margin: '8px 0 0', color: 'rgba(255,255,255,0.7)', fontSize: '13px' }}>
                {erreur}
              </p>
              <button
                type="button"
                onClick={charger}
                style={{
                  marginTop: '12px', padding: '8px 16px', borderRadius: '10px',
                  display: 'inline-flex', alignItems: 'center', gap: '6px',
                  background: 'rgba(var(--primary-rgb, 217, 28, 210), 0.12)',
                  border: '1px solid rgba(var(--primary-rgb, 217, 28, 210), 0.28)',
                  color: 'var(--primary-color, #D91CD2)',
                  fontSize: '12px', fontWeight: 700, cursor: 'pointer',
                }}
              >
                <RefreshCw size={12} /> Réessayer
              </button>
            </div>
          )}

          {!chargement && !erreur && liste.length === 0 && (
            <div style={{ padding: '32px 0', textAlign: 'center' }}>
              <Inbox size={22} color="rgba(255,255,255,0.35)" />
              <p style={{ margin: '8px 0 0', color: 'rgba(255,255,255,0.55)', fontSize: '13px' }}>
                Aucune candidature pour l'instant.
              </p>
              <p style={{ margin: '4px 0 0', color: 'rgba(255,255,255,0.35)', fontSize: '11px' }}>
                Elles apparaîtront ici dès qu'une personne aura terminé le tunnel.
              </p>
            </div>
          )}

          {!chargement && !erreur && liste.map((item, i) => (
            <Candidature
              key={item.id || i}
              item={item}
              onDecider={decider}
              enCours={enCours === item.id}
            />
          ))}
        </div>
      </div>
    </div>
  );
};

export default PartnerApplications;
