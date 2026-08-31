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
import { QRCodeCanvas } from 'qrcode.react';
import { X, Mail, Phone, Calendar, Clock, RefreshCw, Inbox, AlertCircle, Check, Ban,
  Copy, ExternalLink, QrCode, Download } from 'lucide-react';
import { copyToClipboard } from '../../utils/clipboard';
import {
  construireLienPartenaire, p2cNomFichierQr,
  p2bSuggererSlug, p2bSlugValide,
} from '../../utils/partnerLink';

// Les deux helpers de slug vivent desormais dans `utils/partnerLink.js`, avec
// la construction du lien : une seule regle, un seul endroit. On les
// re-exporte ici pour ne pas casser ce qui les importe deja depuis ce module.
export { p2bSuggererSlug, p2bSlugValide };

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

/** P2-C — le lien personnel du partenaire, son QR, et de quoi s'en servir.
 *
 *  RIEN N'EST STOCKE. L'URL est derivee du slug par `construireLienPartenaire`,
 *  et le QR est une image de cette URL, calculee a l'affichage. Le QR encode
 *  l'URL EXACTE : aucun raccourcisseur, aucune redirection, aucun identifiant
 *  interne — ce qui est scanne chez le partenaire est ce qui est affiche ici.
 *
 *  Le QR est rendu en CANVAS et non en SVG, contrairement au reste du depot :
 *  c'est ce qui permet le telechargement PNG en une ligne
 *  (`canvas.toDataURL`), avec le meme patron que le ticket de reservation.
 *  Meme bibliotheque (`qrcode.react`, deja installee), aucune dependance
 *  ajoutee.
 */
const LienPartenaire = ({ slug, API }) => {
  const lien = construireLienPartenaire(slug);
  const [copie, setCopie] = useState(false);
  const [qrVisible, setQrVisible] = useState(false);
  const zoneQr = useRef(null);

  const copier = async () => {
    try {
      const r = await copyToClipboard(lien);
      if (r && r.success) {
        setCopie(true);
        setTimeout(() => setCopie(false), 1800);
      }
    } catch (e) { /* le bouton reste, le coach peut selectionner l'URL a la main */ }
  };

  const telecharger = () => {
    const canvas = zoneQr.current && zoneQr.current.querySelector('canvas');
    if (!canvas) return;
    const a = document.createElement('a');
    a.download = p2cNomFichierQr(slug);
    a.href = canvas.toDataURL('image/png');
    a.click();
  };

  if (!lien) return null;

  return (
    <div style={{
      marginTop: '12px', padding: '10px', borderRadius: '10px',
      background: 'rgba(34,197,94,0.06)', border: '1px solid rgba(34,197,94,0.18)',
    }}>
      <p style={{ margin: 0, color: 'rgba(255,255,255,0.5)', fontSize: '11px' }}>
        Identifiant partenaire
      </p>
      <p style={{ margin: '2px 0 8px', color: '#FFFFFF', fontSize: '13px',
                  fontWeight: 700, fontFamily: 'monospace' }}>
        {slug}
      </p>

      <p style={{ margin: 0, color: 'rgba(255,255,255,0.5)', fontSize: '11px' }}>
        Lien partenaire
      </p>
      <p data-testid="lien-partenaire" style={{
        margin: '2px 0 8px', color: 'rgba(255,255,255,0.75)', fontSize: '11px',
        fontFamily: 'monospace', wordBreak: 'break-all', lineHeight: 1.4,
      }}>
        {lien}
      </p>

      {/* P2-UX SIMPLE — CE QUE LE PARTENAIRE A A FAIRE, EN UNE PHRASE.
          Volontairement sobre : elle dit ce qui se passe, sans evoquer ce qui
          ne se passe pas. Parler de fichiers clients ou de donnees a proteger
          installerait une inquietude que personne n'a exprimee — l'interface
          suffit a montrer qu'on ne partage qu'un lien et un QR. Le partenaire
          ne voit ici que son lien, son QR et, plus tard, ses resultats : il
          n'existe aucun formulaire de reservation de ce cote, et il ne doit
          pas y en avoir. */}
      <p style={{
        margin: '0 0 10px', padding: '8px 10px', borderRadius: '8px',
        background: 'rgba(255,255,255,0.05)',
        border: '1px solid rgba(255,255,255,0.08)',
        color: 'rgba(255,255,255,0.6)', fontSize: '11px', lineHeight: 1.5,
      }}>
        Partagez votre invitation Afroboost. Votre communauté s'inscrit et
        réserve directement sa séance.
      </p>

      <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
        <BoutonAction onClick={copier} couleur={copie ? '#22c55e' : '#a78bfa'}>
          {copie ? <><Check size={13} /> Copié</> : <><Copy size={13} /> Copier</>}
        </BoutonAction>
        <a
          href={lien}
          target="_blank"
          rel="noopener noreferrer"
          style={{
            flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center',
            gap: '6px', padding: '9px 0', borderRadius: '10px', textDecoration: 'none',
            background: 'rgba(59,130,246,0.14)', border: '1px solid rgba(59,130,246,0.33)',
            color: '#3b82f6', fontSize: '12px', fontWeight: 700,
          }}
        >
          <ExternalLink size={13} /> Ouvrir
        </a>
        <BoutonAction onClick={() => setQrVisible((v) => !v)} couleur="#f59e0b">
          <QrCode size={13} /> QR code
        </BoutonAction>
      </div>

      {qrVisible && (
        <div style={{ marginTop: '10px', textAlign: 'center' }}>
          <div ref={zoneQr} style={{
            display: 'inline-block', padding: '10px',
            background: '#ffffff', borderRadius: '10px',
          }}>
            <QRCodeCanvas value={lien} size={180} level="M" includeMargin={false}
                          bgColor="#ffffff" fgColor="#000000" />
          </div>
          <div style={{ marginTop: '8px' }}>
            <BoutonAction onClick={telecharger} couleur="#22c55e">
              <Download size={13} /> Télécharger le QR
            </BoutonAction>
          </div>
        </div>
      )}

      {/* P2-D2 — les resultats, sous le lien et le QR. */}
      <StatsPartenaire slug={slug} API={API} />
    </div>
  );
};

/** P2-D2 — un taux, rendu pour un humain.
 *
 *  LA REGLE QUI COMPTE : `null` N'EST PAS `0`.
 *  Le serveur renvoie `null` quand le denominateur est nul (`_taux`), et `0`
 *  quand il a vraiment mesure zero. Les confondre ferait lire « 0 % de
 *  presence » a un partenaire qui n'a encore envoye personne — un reproche a
 *  la place d'une absence de donnee. On rend donc un tiret cadratin pour
 *  « pas encore de donnee », et « 0 % » seulement pour un vrai zero mesure.
 */
export function p2d2Taux(valeur) {
  if (valeur === null || valeur === undefined) return '—';
  const n = Number(valeur);
  if (!Number.isFinite(n)) return '—';
  return `${Math.round(n * 1000) / 10} %`;
}

/** Un compteur. Tout ce qui n'est pas un entier positif devient un tiret :
 *  mieux vaut avouer l'ignorance qu'afficher « NaN » ou un zero invente.
 *
 *  ⚠️ `null` EST REJETE AVANT LA CONVERSION, et ce n'est pas un detail :
 *  `Number(null)` vaut `0`. Sans ce test explicite, un champ absent
 *  s'afficherait « 0 » — soit precisement la confusion que ce lot existe pour
 *  eviter, transposee des taux aux compteurs. Mesure faite : le test le
 *  rendait « 0 ». Meme raison pour la chaine vide, que `Number` rend aussi `0`. */
export function p2d2Nombre(valeur) {
  if (valeur === null || valeur === undefined || valeur === '') return '—';
  const n = Number(valeur);
  if (!Number.isFinite(n) || n < 0) return '—';
  return String(Math.trunc(n));
}

/** La reponse du serveur est-elle exploitable ? On exige le champ qui porte le
 *  sens du lot. Une reponse d'une AUTRE route (ou tronquee) n'est pas rendue
 *  comme un resultat de zero : elle passe par l'etat d'erreur. */
export function p2d2ReponseUtilisable(data) {
  return !!data && typeof data === 'object' && Number.isFinite(Number(data.reservations));
}

/** P2-D2 — LES RESULTATS DU PARTENARIAT, EN LECTURE SEULE.
 *
 *  AUCUN CALCUL ICI. Les quatre nombres sortent tels quels de
 *  `GET /partners/{slug}/stats` (P2-D1). Recalculer quoi que ce soit dans le
 *  navigateur ferait exister deux definitions de « une presence » ou de « une
 *  conversion », et c'est la deuxieme qui finirait par mentir.
 *
 *  AUCUNE DONNEE PERSONNELLE. La route est agregee par construction : elle ne
 *  renvoie ni nom, ni e-mail, ni telephone, ni code d'acces, ni reservation
 *  individuelle. Ce composant n'affiche donc que des totaux — et le test le
 *  verifie sur le rendu, pas sur l'intention.
 *
 *  AUCUN POLLING. Un seul appel au montage, plus un bouton « Actualiser ».
 *  Pas de `setInterval` : le depot vient d'en retirer plusieurs (CHAT-LOOP1 a 3)
 *  et un tableau de bord n'a pas besoin de se rafraichir tout seul.
 *
 *  MONTE UNIQUEMENT DEPUIS `LienPartenaire`, donc seulement pour une
 *  candidature ACCEPTEE portant un `partner_slug` valide. La condition
 *  d'affichage est STRUCTURELLE, pas un `if` a l'interieur : une candidature en
 *  attente, refusee, ou acceptee sans slug ne monte pas ce composant et
 *  n'emet donc aucun appel.
 */
const StatsPartenaire = ({ slug, API }) => {
  const [chargement, setChargement] = useState(true);
  const [erreur, setErreur] = useState(false);
  const [stats, setStats] = useState(null);

  const charger = useCallback(async () => {
    setChargement(true);
    setErreur(false);
    try {
      const { data } = await axios.get(
        `${API}/partners/${encodeURIComponent(slug)}/stats`);
      if (p2d2ReponseUtilisable(data)) {
        setStats(data);
      } else {
        setStats(null);
        setErreur(true);
      }
    } catch (e) {
      // 403 compris : on n'essaie JAMAIS de contourner l'authentification, on
      // affiche l'etat d'erreur ordinaire. Le lien et le QR, eux, restent —
      // ils ne dependent d'aucun appel reseau.
      setStats(null);
      setErreur(true);
    } finally {
      setChargement(false);
    }
  }, [API, slug]);

  // Dependance PRIMITIVE (`charger` ne depend que de `API` et `slug`, deux
  // chaines) : cet effet ne peut pas se relancer a chaque rendu du parent.
  useEffect(() => { charger(); }, [charger]);

  const conversions = (stats && stats.conversions) || {};

  return (
    <div style={{ marginTop: '12px', paddingTop: '10px',
                  borderTop: '1px solid rgba(255,255,255,0.08)' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px',
                    marginBottom: '8px' }}>
        <p style={{ margin: 0, flex: 1, color: 'rgba(255,255,255,0.75)',
                    fontSize: '12px', fontWeight: 700 }}>
          Résultats de votre partenariat
        </p>
        <button
          type="button"
          onClick={charger}
          disabled={chargement}
          aria-label="Actualiser les résultats"
          style={{
            display: 'flex', alignItems: 'center', gap: '5px',
            padding: '5px 9px', borderRadius: '8px',
            background: 'rgba(255,255,255,0.05)',
            border: '1px solid rgba(255,255,255,0.12)',
            color: 'rgba(255,255,255,0.6)', fontSize: '11px', fontWeight: 700,
            cursor: chargement ? 'not-allowed' : 'pointer',
            opacity: chargement ? 0.5 : 1,
          }}
        >
          <RefreshCw size={11} /> Actualiser
        </button>
      </div>

      {chargement && (
        <p style={{ margin: 0, color: 'rgba(255,255,255,0.45)', fontSize: '11px' }}>
          Chargement des résultats…
        </p>
      )}

      {!chargement && erreur && (
        <div style={{
          padding: '8px 10px', borderRadius: '8px',
          background: 'rgba(245,158,11,0.08)',
          border: '1px solid rgba(245,158,11,0.2)',
        }}>
          <p style={{ margin: 0, color: '#f59e0b', fontSize: '11px' }}>
            Résultats momentanément indisponibles
          </p>
        </div>
      )}

      {!chargement && !erreur && stats && (
        <>
          {/* Deux colonnes sur telephone : quatre nombres courts y tiennent
              sans rogner les libelles. `minmax(0, 1fr)` empeche une colonne de
              pousser la grille au-dela de la fenetre — c'est ce qui evite le
              debordement horizontal quand un nombre grandit. */}
          <div data-testid="p2d2-compteurs" style={{
            display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))',
            gap: '8px',
          }}>
            {[
              ['Réservations', p2d2Nombre(stats.reservations)],
              ['Personnes', p2d2Nombre(stats.unique_people)],
              ['Présences', p2d2Nombre(stats.attendances)],
              ['Conversions', p2d2Nombre(conversions.total)],
            ].map(([libelle, valeur]) => (
              <div key={libelle} style={{
                padding: '9px 10px', borderRadius: '9px', minWidth: 0,
                background: 'rgba(255,255,255,0.05)',
                border: '1px solid rgba(255,255,255,0.08)',
              }}>
                <p style={{ margin: 0, color: '#FFFFFF', fontSize: '19px',
                            fontWeight: 800, lineHeight: 1.1 }}>
                  {valeur}
                </p>
                <p style={{ margin: '2px 0 0', color: 'rgba(255,255,255,0.5)',
                            fontSize: '10px' }}>
                  {libelle}
                </p>
              </div>
            ))}
          </div>

          <p style={{ margin: '8px 0 0', color: 'rgba(255,255,255,0.45)',
                      fontSize: '10px', lineHeight: 1.5 }}>
            Taux de présence {p2d2Taux(stats.attendance_rate)}
            {' · '}
            Taux de conversion {p2d2Taux(stats.conversion_rate)}
          </p>

          <p style={{ margin: '3px 0 0', color: 'rgba(255,255,255,0.35)',
                      fontSize: '10px', lineHeight: 1.5 }}>
            Pulse {p2d2Nombre(conversions.pulse)}
            {' · '}
            Membres {p2d2Nombre(conversions.member)}
            {' · '}
            Abonnements {p2d2Nombre(conversions.subscription)}
          </p>
        </>
      )}
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

const Candidature = ({ item, onDecider, enCours, API }) => {
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

      {/* P2-C — LE LIEN PERSONNEL ET SON QR.
          Uniquement pour une candidature ACCEPTEE qui possede reellement un
          `partner_slug`. Un slug absent n'est pas un cas a rattraper : on ne
          fabrique JAMAIS un slug depuis le nom pour boucher le trou, sous
          peine de distribuer un lien qui n'attribue rien. */}
      {(item.application_decision === 'accepted') && (
        item.partner_slug
          ? <LienPartenaire slug={item.partner_slug} API={API} />
          : (
            <p style={{ margin: '12px 0 0', padding: '8px 10px', borderRadius: '8px',
                        background: 'rgba(239,68,68,0.08)',
                        border: '1px solid rgba(239,68,68,0.2)',
                        color: '#ef4444', fontSize: '11px' }}>
              Partenaire incomplet — identifiant indisponible
            </p>
          )
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
              API={API}
            />
          ))}
        </div>
      </div>
    </div>
  );
};

export default PartnerApplications;
