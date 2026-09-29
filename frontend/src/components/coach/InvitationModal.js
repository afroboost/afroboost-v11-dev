/**
 * InvitationModal — « + Créer » → « Invitation » (page Campagnes du coach).
 *
 * UNE INVITATION N'EST PAS UNE CAMPAGNE D'ENVOI : aucun choix de contacts,
 * aucun canal, aucune programmation, aucun crédit. Le coach prépare une carte
 * et la partage lui-même (WhatsApp, partage natif, lien, QR).
 *
 * TROIS ÉTAPES :
 *   1. Type      — Essai gratuit, Pass Duo, Événement gratuit, Événement payant ;
 *   2. Contenu   — titre, sous-titre, message (≤ 280), miniature, cours / date /
 *                  heure / lieu, offre, texte du bouton ;
 *   3. Aperçu    — enregistre (POST la 1re fois, PUT ensuite : l'id est gardé,
 *                  jamais deux POST), aperçu 1200×630, bandeau « Prénom
 *                  t'invite… », « Activer le lien », puis le partage.
 *
 * Événement payant : l'activation répond 409 tant que le fuseau horaire des
 * paliers n'est pas corrigé → brouillon seulement, partage désactivé.
 *
 * RÉSEAU : les options (cours, offres) sont lues UNE fois à l'ouverture ; tout
 * le reste part sur un geste. Aucun useEffect ne dépend d'un objet ; les
 * setState d'objet renvoient `prev` quand rien ne change (CLAUDE.md, règle
 * « JAMAIS DE BOUCLE D'APPELS API »). Auth : intercepteur axios global (JWT).
 *
 * COULEURS : uniquement var(--primary-color) / rgba(var(--primary-rgb), a) et
 * des gris neutres rgba(255,255,255,a). Icônes : SvgIcon, jamais d'emoji.
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { QRCodeSVG } from 'qrcode.react';
import SvgIcon from '../SvgIcon';
import InvitationMiniature from './InvitationMiniature';
import BandeauInvitant from '../parrainage/BandeauInvitant';
import useLargeurEcran from '../../utils/useLargeurEcran';
import '../parrainage/parrainage.css';
import '../parrainage/invitationWizard.css';
import { lienWhatsApp, copier, partager, verifierApercuNavigateur } from '../../utils/parrainage';
import {
  TYPES_INVITATION, CTA_DEFAUT, TITRE_DEFAUT, TITRE_MAX, SOUS_TITRE_MAX, MESSAGE_MAX, CTA_MAX,
  TEXTE_FUSEAU_PALIERS, offresPourType, paliersOffre, libellePrix, heureDuCours, prochaineDate,
  dateIso, formulaireInitial, construireCorps, validerInvitation, texteWhatsAppCampagne,
  lienPartage, partageable, messageErreur, lireOptions, creerInvitation, modifierInvitation,
  lireApercuBrouillon,
} from '../../utils/invitationCampagne';

const STEPS = [
  { id: 1, label: 'Type', icon: 'layers' },
  { id: 2, label: 'Contenu', icon: 'edit' },
  { id: 3, label: 'Aperçu & partage', icon: 'share' },
];

const SEUIL_BOTTOM_SHEET = 480;

// ── Styles (en ligne, comme CampaignModal ; couleurs du coach uniquement) ──
const PRIMAIRE = 'var(--primary-color, #D91CD2)';
const rgbaP = (a) => `rgba(var(--primary-rgb, 217, 28, 210), ${a})`;

const styleLabel = { display: 'block', color: 'rgba(255,255,255,0.92)', fontSize: '13px', fontWeight: 600, marginBottom: '6px' };
const styleChamp = {
  width: '100%', minHeight: '44px', padding: '10px 14px', borderRadius: '10px',
  background: 'rgba(255,255,255,0.08)', border: `1px solid ${rgbaP(0.3)}`, color: 'rgba(255,255,255,0.96)',
  fontSize: '16px', outline: 'none', boxSizing: 'border-box',
};
const styleErreur = { color: 'rgba(255,160,150,0.98)', fontSize: '12px', margin: '6px 0 0' };
const styleAide = { color: 'rgba(255,255,255,0.55)', fontSize: '12px', margin: '6px 0 0' };

function styleBouton(variante, actif) {
  const base = {
    minHeight: '44px', padding: '10px 16px', borderRadius: '10px', fontSize: '14px', fontWeight: 600,
    display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: '8px',
    cursor: actif ? 'pointer' : 'not-allowed', opacity: actif ? 1 : 0.45, boxSizing: 'border-box',
    color: 'rgba(255,255,255,0.98)', border: '1px solid transparent',
  };
  if (variante === 'plein') return Object.assign(base, { background: PRIMAIRE });
  if (variante === 'contour') return Object.assign(base, { background: rgbaP(0.12), border: `1px solid ${rgbaP(0.45)}` });
  return Object.assign(base, { background: 'rgba(255,255,255,0.08)', border: '1px solid rgba(255,255,255,0.14)' });
}

function Champ({ id, label, erreur, aide, children }) {
  return (
    <div style={{ marginBottom: '14px' }}>
      <label htmlFor={id} style={styleLabel}>{label}</label>
      {children}
      {erreur ? <p style={styleErreur} role="alert" data-testid={`${id}-erreur`}>{erreur}</p> : null}
      {!erreur && aide ? <p style={styleAide}>{aide}</p> : null}
    </div>
  );
}

/** https, ou chemin du MÊME site (« /api/files/… », « /logo512.png ») : jamais une
 *  image mixte, un « //hôte » ni un schéma exotique dans <img>. */
export function urlHttps(u) {
  const s = typeof u === 'string' ? u.trim() : '';
  if (!s || /[\s\\]/.test(s)) return '';
  if (/^\/(?![\/\\])/.test(s)) return s;
  return /^https:\/\//i.test(s) ? s : '';
}

// ═══════════════════════════════════════════════════════════════════════════
export default function InvitationModal({ isOpen, onClose, API, dateInitiale }) {
  // Monté à chaque ouverture : une ouverture = une invitation (état neuf,
  // options relues une fois, jamais un 2e POST dans la même ouverture).
  if (!isOpen) return null;
  return <ContenuInvitation onClose={onClose} API={API} dateInitiale={dateInitiale} />;
}

function ContenuInvitation({ onClose, API, dateInitiale }) {
  const { largeur } = useLargeurEcran();
  const mobile = largeur < SEUIL_BOTTOM_SHEET;
  const aujourdhui = dateIso(new Date());

  const [etape, setEtape] = useState(1);
  const [form, setForm] = useState(() => formulaireInitial('', dateInitiale));
  const [touche, setTouche] = useState(false);
  const [options, setOptions] = useState(null); // null = chargement
  const [erreurOptions, setErreurOptions] = useState('');
  const [montrerErreurs, setMontrerErreurs] = useState(false);
  const [dto, setDto] = useState(null);
  const [dernierCorps, setDernierCorps] = useState('');
  const [occupe, setOccupe] = useState(false);
  const [erreur, setErreur] = useState('');
  const [miniatureOccupee, setMiniatureOccupee] = useState(false);
  const [apercuUrl, setApercuUrl] = useState('');
  const [apercuKo, setApercuKo] = useState(false);
  const [fichierCarte, setFichierCarte] = useState(null);
  const [qrVisible, setQrVisible] = useState(false);
  const [feedback, setFeedback] = useState('');
  const [confirmFermeture, setConfirmFermeture] = useState(false);
  const enVolRef = useRef(false); // un seul enregistrement à la fois
  const idRef = useRef('');       // l'id reçu au 1er POST : ensuite, PUT seulement
  const defilementRef = useRef(null); // le conteneur défilant (remis en haut à chaque étape)
  // La date du calendrier : préremplie pour trial / pass_duo ; pour un événement,
  // seulement une fois un cours choisi (sinon « Suivant » bloquerait sur l'heure).
  const dateCalendrier = /^\d{4}-\d{2}-\d{2}$/.test(String(dateInitiale || '')) ? String(dateInitiale) : '';

  // Changement d'étape : on repart du haut (sinon l'aperçu arrive tronqué).
  useEffect(() => {
    const el = defilementRef.current;
    if (el) el.scrollTop = 0;
  }, [etape]);

  // Options : UNE lecture à l'ouverture.
  useEffect(() => {
    let vivant = true;
    lireOptions(API)
      .then((o) => { if (vivant) setOptions(o); })
      .catch((e) => {
        if (!vivant) return;
        setOptions({ courses: [], offers: [] });
        setErreurOptions(messageErreur(e, 'options'));
      });
    return () => { vivant = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!feedback) return undefined;
    const t = setTimeout(() => setFeedback(''), 2600);
    return () => clearTimeout(t);
  }, [feedback]);

  const courses = (options && options.courses) || [];
  const offers = (options && options.offers) || [];
  const type = form.type;
  const offresType = offresPourType(type, offers);
  const coursChoisi = courses.find((c) => String(c.id) === String(form.course_id)) || null;
  const offreChoisie = offers.find((o) => String(o.id) === String(form.offer_id)) || null;
  const erreurs = validerInvitation(form, offers, aujourdhui);
  const valide = Object.keys(erreurs).length === 0;
  const corps = construireCorps(form);
  const cleCorps = JSON.stringify(corps);
  const nonEnregistre = touche && cleCorps !== dernierCorps;
  const eventPaid = type === 'event_paid';

  // ── Mises à jour (renvoient prev si rien ne change) ──────────────────────
  const maj = useCallback((champ, valeur) => {
    setTouche(true);
    setForm((prev) => (prev[champ] === valeur ? prev : Object.assign({}, prev, { [champ]: valeur })));
  }, []);

  const surMiniature = useCallback((v) => {
    const image_url = (v && v.image_url) || '';
    const image_source = (v && v.image_source) || '';
    setForm((prev) => {
      if (prev.image_url === image_url && prev.image_source === image_source) return prev;
      return Object.assign({}, prev, { image_url, image_source });
    });
    setTouche(true);
  }, []);
  const surMiniatureOccupee = useCallback((b) => setMiniatureOccupee(!!b), []);

  const choisirType = (t) => {
    if (idRef.current && t !== type) return; // type figé après la création
    setErreur('');
    setMontrerErreurs(false);
    if (t !== type) {
      setForm((prev) => {
        const suivant = Object.assign({}, prev, { type: t });
        // Titre / CTA : on remplace seulement une valeur par défaut (jamais une saisie).
        if (!prev.title || prev.title === TITRE_DEFAUT[prev.type]) suivant.title = TITRE_DEFAUT[t] || '';
        if (!prev.cta_label || prev.cta_label === CTA_DEFAUT[prev.type]) suivant.cta_label = CTA_DEFAUT[t] || '';
        const evenement = t === 'event_free' || t === 'event_paid';
        if (evenement && !prev.course_id && dateCalendrier && prev.date === dateCalendrier) suivant.date = '';
        if (!evenement && !prev.date && dateCalendrier) suivant.date = dateCalendrier;
        const liste = offresPourType(t, offers);
        if (!liste.some((o) => String(o.id) === String(prev.offer_id))) {
          suivant.offer_id = liste.length === 1 ? String(liste[0].id) : '';
        }
        return suivant;
      });
    }
    setEtape(2);
  };

  const choisirCours = (id) => {
    setTouche(true);
    const c = courses.find((x) => String(x.id) === String(id)) || null;
    setForm((prev) => {
      if (prev.course_id === id) return prev;
      const suivant = Object.assign({}, prev, { course_id: id });
      if (c) {
        const h = heureDuCours(c.time);
        if (h) suivant.heure = h;
        if (!prev.date) suivant.date = dateCalendrier || prochaineDate(c.weekday, aujourdhui);
      }
      return suivant;
    });
  };

  // ── Enregistrement : POST la 1re fois, PUT ensuite ──────────────────────
  const appliquerDto = (d) => {
    if (d && d.id) {
      idRef.current = String(d.id);
      setDto((prev) => (prev && JSON.stringify(prev) === JSON.stringify(d) ? prev : d));
    }
  };

  const enregistrer = ({ force, puis } = {}) => {
    if (enVolRef.current || miniatureOccupee) return;
    if (!valide) { setMontrerErreurs(true); return; }
    if (!force && idRef.current && cleCorps === dernierCorps) {
      if (puis) puis();
      return;
    }
    enVolRef.current = true;
    setOccupe(true); setErreur('');
    const envoi = idRef.current
      ? modifierInvitation(API, idRef.current, corps)
      : creerInvitation(API, corps);
    envoi
      .then((d) => {
        appliquerDto(d);
        setDernierCorps(cleCorps);
        setTouche(false);
        setFeedback('Brouillon enregistré');
        if (puis) puis();
      })
      .catch((e) => setErreur(messageErreur(e, 'enregistrement')))
      .finally(() => { enVolRef.current = false; setOccupe(false); });
  };

  const activer = () => {
    if (enVolRef.current || !idRef.current || eventPaid) return;
    if (!valide) { setMontrerErreurs(true); return; }
    enVolRef.current = true;
    setOccupe(true); setErreur('');
    const champs = cleCorps !== dernierCorps ? Object.assign({}, corps, { status: 'active' }) : { status: 'active' };
    modifierInvitation(API, idRef.current, champs)
      .then((d) => {
        appliquerDto(d);
        setDernierCorps(cleCorps);
        setTouche(false);
        setFeedback('Lien activé : tu peux partager ton invitation');
      })
      .catch((e) => setErreur(messageErreur(e, 'activation')))
      .finally(() => { enVolRef.current = false; setOccupe(false); });
  };

  // ── Aperçu ───────────────────────────────────────────────────────────────
  const carteActive = dto && dto.status === 'active' ? urlHttps(dto.card_url) : '';
  const cleApercu = etape === 3 && dto && dto.id && !carteActive
    ? `${dto.id}|${dto.version || 0}|${dto.updated_at || ''}`
    : '';

  // Brouillon : l'image exige le jeton → blob via axios, révoqué ensuite.
  useEffect(() => {
    if (!cleApercu) return undefined;
    let vivant = true;
    let url = '';
    const id = cleApercu.split('|')[0];
    setApercuKo(false);
    lireApercuBrouillon(API, id)
      .then((blob) => {
        if (!vivant || !blob) return;
        if (typeof URL === 'undefined' || typeof URL.createObjectURL !== 'function') return;
        url = URL.createObjectURL(blob);
        setApercuUrl(url);
      })
      .catch(() => { if (vivant) setApercuKo(true); });
    return () => {
      vivant = false;
      if (url) {
        try { URL.revokeObjectURL(url); } catch (e) { /* ignore */ }
        setApercuUrl((prev) => (prev === url ? '' : prev));
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cleApercu]);

  const lien = lienPartage(dto);
  const peutPartager = partageable(dto);

  // Invitation active : la carte publique est préchargée en fichier pour
  // « Partager avec la carte » (même contrôle que le Pass Duo, V556).
  useEffect(() => {
    if (!carteActive || !lien) return undefined;
    let vivant = true;
    verifierApercuNavigateur({ cardUrl: carteActive, shareUrl: '' })
      .then((v) => { if (vivant) setFichierCarte(v && v.file ? v.file : null); })
      .catch(() => { /* partage par lien toujours possible */ });
    return () => { vivant = false; };
  }, [carteActive, lien]);

  // ── Partage (réutilise utils/parrainage) ─────────────────────────────────
  const nav = typeof navigator !== 'undefined' ? navigator : null;
  let peutCarte = false;
  if (fichierCarte && nav && typeof nav.share === 'function' && typeof nav.canShare === 'function') {
    try { peutCarte = !!nav.canShare({ files: [fichierCarte] }); } catch (e) { peutCarte = false; }
  }
  const texte = texteWhatsAppCampagne(dto);
  const surWhatsApp = () => {
    if (!peutPartager) return;
    window.open(lienWhatsApp(texte), '_blank', 'noopener'); // synchrone : geste utilisateur
  };
  const surPartagerCarte = () => {
    if (!peutPartager || !peutCarte) return;
    let p;
    try { p = nav.share({ files: [fichierCarte], text: texte }); } catch (e) { p = Promise.reject(e); }
    Promise.resolve(p).catch((e) => {
      if (e && e.name === 'AbortError') return;
      setFeedback('Le partage n’a pas abouti. Essaie un autre bouton ou copie le lien.');
    });
  };
  const surPartager = () => {
    if (!peutPartager) return;
    partager({ title: (dto && dto.title) || 'Afroboost', text: (dto && dto.message) || '', url: lien })
      .then((r) => { if (r && r.ok && r.methode === 'copie') setFeedback('Lien copié'); });
  };
  const surCopier = () => {
    if (!peutPartager) return;
    copier(lien).then((ok) => setFeedback(ok ? 'Lien copié' : 'Copie impossible : sélectionne le lien à la main'));
  };

  // ── Fermeture (croix, Échap, fond) ───────────────────────────────────────
  const demanderFermeture = () => {
    if (occupe) return;
    if (nonEnregistre) { setConfirmFermeture(true); return; }
    if (typeof onClose === 'function') onClose();
  };
  const fermerRef = useRef(demanderFermeture);
  fermerRef.current = demanderFermeture;
  useEffect(() => {
    const surTouche = (e) => { if (e.key === 'Escape') fermerRef.current(); };
    document.addEventListener('keydown', surTouche);
    return () => document.removeEventListener('keydown', surTouche);
  }, []);

  // ── Navigation ───────────────────────────────────────────────────────────
  const suivant = () => {
    setErreur('');
    if (etape === 1) { if (type) setEtape(2); return; }
    if (etape === 2) enregistrer({ puis: () => setEtape(3) });
  };
  const precedent = () => { setErreur(''); setQrVisible(false); setEtape((e) => Math.max(1, e - 1)); };

  const err = (champ) => (montrerErreurs ? erreurs[champ] : '');
  const infoType = TYPES_INVITATION.find((t) => t.id === type) || null;

  // ── Rendu des étapes ─────────────────────────────────────────────────────
  const etape1 = (
    <div>
      <p style={{ color: 'rgba(255,255,255,0.75)', fontSize: '14px', margin: '0 0 14px' }}>
        Que veux-tu offrir ? Tu partageras ensuite le lien toi-même.
      </p>
      <div style={{ display: 'grid', gridTemplateColumns: mobile ? '1fr' : '1fr 1fr', gap: '10px' }}>
        {TYPES_INVITATION.map((t) => {
          const choisi = t.id === type;
          const bloque = !!idRef.current && !choisi;
          return (
            <button key={t.id} type="button" onClick={() => choisirType(t.id)} disabled={bloque}
                    aria-pressed={choisi} data-testid={`inv-type-${t.id}`}
                    style={{
                      minHeight: '88px', textAlign: 'left', padding: '14px', borderRadius: '12px',
                      cursor: bloque ? 'not-allowed' : 'pointer', opacity: bloque ? 0.45 : 1,
                      background: choisi ? rgbaP(0.22) : 'rgba(255,255,255,0.05)',
                      border: choisi ? `1px solid ${PRIMAIRE}` : '1px solid rgba(255,255,255,0.12)',
                      color: 'rgba(255,255,255,0.96)', boxSizing: 'border-box',
                    }}>
              <span style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '15px', fontWeight: 700 }}>
                <span style={{ color: PRIMAIRE, display: 'inline-flex' }}><SvgIcon name={t.icone} size={20} /></span>
                {t.libelle}
              </span>
              <span style={{ display: 'block', fontSize: '12.5px', color: 'rgba(255,255,255,0.65)', marginTop: '6px', lineHeight: 1.35 }}>
                {t.aide}
              </span>
            </button>
          );
        })}
      </div>
      {idRef.current ? <p style={styleAide}>Le type ne change plus une fois l'invitation enregistrée.</p> : null}
    </div>
  );

  const avecCours = !!type; // les quatre types ; facultatif pour les événements
  const coursFacultatif = type === 'event_free' || type === 'event_paid';
  const avecOffre = type === 'trial' || type === 'event_free' || type === 'event_paid';
  const paliers = eventPaid ? paliersOffre(offreChoisie) : [];

  const etape2 = (
    <div>
      {infoType ? (
        <p style={{ display: 'flex', alignItems: 'center', gap: '8px', color: PRIMAIRE, fontSize: '13px', fontWeight: 700, margin: '0 0 14px' }}>
          <SvgIcon name={infoType.icone} size={16} /> {infoType.libelle}
        </p>
      ) : null}

      <Champ id="inv-titre" label="Titre" erreur={err('title')}>
        <input id="inv-titre" data-testid="inv-titre" style={styleChamp} maxLength={TITRE_MAX}
               value={form.title} onChange={(e) => maj('title', e.target.value)} autoComplete="off" />
      </Champ>
      <Champ id="inv-soustitre" label="Sous-titre (facultatif)" erreur={err('subtitle')}>
        <input id="inv-soustitre" data-testid="inv-soustitre" style={styleChamp} maxLength={SOUS_TITRE_MAX}
               value={form.subtitle} onChange={(e) => maj('subtitle', e.target.value)} autoComplete="off" />
      </Champ>
      <Champ id="inv-message" label="Message" erreur={err('message')}>
        <textarea id="inv-message" data-testid="inv-message" rows={3} maxLength={MESSAGE_MAX}
                  style={Object.assign({}, styleChamp, { resize: 'vertical', minHeight: '88px' })}
                  value={form.message} onChange={(e) => maj('message', e.target.value.slice(0, MESSAGE_MAX))} />
        <p style={Object.assign({}, styleAide, { textAlign: 'right' })} data-testid="inv-compteur">{form.message.length}/{MESSAGE_MAX}</p>
      </Champ>

      <div style={{ marginBottom: '14px' }}>
        <span style={styleLabel}>Miniature</span>
        <InvitationMiniature value={form.image_url} source={form.image_source}
                             defaultUrl={urlHttps(offreChoisie && (offreChoisie.image_url || offreChoisie.image)) || urlHttps(options && options.default_image_url)}
                             onChange={surMiniature} onBusyChange={surMiniatureOccupee} />
      </div>

      {avecCours ? (
        <>
          <Champ id="inv-cours" label={coursFacultatif ? 'Séance (facultatif)' : 'Séance'} erreur={err('course_id')}
                 aide={courses.length === 0 && options ? "Aucun cours n'est disponible pour le moment." : ''}>
            <select id="inv-cours" data-testid="inv-cours" style={styleChamp} value={form.course_id}
                    onChange={(e) => choisirCours(e.target.value)}>
              <option value="">{coursFacultatif ? 'Aucune séance liée' : 'Choisis un cours'}</option>
              {courses.map((c) => (
                <option key={c.id} value={c.id}>{c.name}{c.time ? ` · ${heureDuCours(c.time) || c.time}` : ''}</option>
              ))}
            </select>
          </Champ>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
            <Champ id="inv-date" label={coursFacultatif ? 'Date (facultatif)' : 'Date'} erreur={err('date')}>
              <input id="inv-date" data-testid="inv-date" type="date" style={styleChamp} min={aujourdhui}
                     value={form.date} onChange={(e) => maj('date', e.target.value)} />
            </Champ>
            <Champ id="inv-heure" label={coursFacultatif ? 'Heure (facultatif)' : 'Heure'} erreur={err('heure')}>
              <input id="inv-heure" data-testid="inv-heure" type="time" style={styleChamp}
                     value={form.heure} onChange={(e) => maj('heure', e.target.value)} />
            </Champ>
          </div>
          {coursChoisi && coursChoisi.location ? (
            <div style={{ marginBottom: '14px' }}>
              <span style={styleLabel}>Lieu</span>
              <p data-testid="inv-lieu" style={{ display: 'flex', alignItems: 'center', gap: '8px', margin: 0, color: 'rgba(255,255,255,0.85)', fontSize: '14px' }}>
                <SvgIcon name="mapPin" size={16} /> {coursChoisi.location}
              </p>
            </div>
          ) : null}
        </>
      ) : null}

      {avecOffre ? (
        <Champ id="inv-offre" label={eventPaid ? "Offre payante de l'événement" : 'Offre gratuite'} erreur={err('offer_id')}
               aide={options && offresType.length === 0
                 ? (eventPaid ? "Aucune offre payante n'est disponible : crée-la d'abord dans tes offres."
                   : "Aucune offre gratuite n'est disponible : crée-la d'abord dans tes offres.")
                 : ''}>
          <select id="inv-offre" data-testid="inv-offre" style={styleChamp} value={form.offer_id}
                  onChange={(e) => maj('offer_id', e.target.value)}>
            <option value="">Choisis une offre</option>
            {offresType.map((o) => (
              <option key={o.id} value={o.id}>{o.name}{eventPaid && Number(o.price) > 0 ? ` · ${libellePrix(o.price)}` : ''}</option>
            ))}
          </select>
        </Champ>
      ) : null}

      {eventPaid && offreChoisie ? (
        <div data-testid="inv-paliers" style={{ marginBottom: '14px', padding: '12px', borderRadius: '10px', background: rgbaP(0.08), border: `1px solid ${rgbaP(0.25)}` }}>
          <span style={styleLabel}>Tarifs de l'offre (lecture seule)</span>
          {paliers.length ? (
            <div style={{ display: 'grid', gridTemplateColumns: `repeat(${paliers.length}, 1fr)`, gap: '8px' }}>
              {paliers.map((p) => (
                <div key={p.cle} style={{ padding: '8px', borderRadius: '8px', background: 'rgba(255,255,255,0.05)', textAlign: 'center' }}>
                  <div style={{ fontSize: '12px', color: 'rgba(255,255,255,0.65)' }}>{p.libelle}</div>
                  <div style={{ fontSize: '15px', fontWeight: 700, color: 'rgba(255,255,255,0.96)' }}>{libellePrix(p.prix)}</div>
                </div>
              ))}
            </div>
          ) : <p style={styleAide}>Aucun prix renseigné sur cette offre.</p>}
          <p style={styleAide}>Les paliers se modifient dans l'offre elle-même.</p>
        </div>
      ) : null}

      <Champ id="inv-cta" label="Texte du bouton" erreur={err('cta_label')}>
        <input id="inv-cta" data-testid="inv-cta" style={styleChamp} maxLength={CTA_MAX}
               value={form.cta_label} onChange={(e) => maj('cta_label', e.target.value.slice(0, CTA_MAX))} autoComplete="off" />
        <p style={Object.assign({}, styleAide, { textAlign: 'right' })} data-testid="inv-cta-compteur">{form.cta_label.length}/{CTA_MAX}</p>
      </Champ>
    </div>
  );

  const inviteur = (dto && dto.inviter_display) || {};
  const imageApercu = carteActive || apercuUrl;
  const boutonPartage = (id, icone, libelle, onClick, actif) => (
    <button type="button" data-testid={id} onClick={onClick} disabled={!actif}
            style={Object.assign(styleBouton(id === 'inv-whatsapp' ? 'plein' : 'contour', actif), { width: '100%' })}>
      <SvgIcon name={icone} size={18} /> {libelle}
    </button>
  );

  const etape3 = (
    <div>
      <div data-testid="inv-apercu" style={{
        width: '100%', aspectRatio: '1200 / 630', borderRadius: '12px', overflow: 'hidden',
        background: rgbaP(0.08), border: `1px solid ${rgbaP(0.25)}`, display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}>
        {imageApercu ? (
          <img src={imageApercu} alt="Aperçu de ton invitation" width="1200" height="630"
               style={{ display: 'block', width: '100%', height: '100%', objectFit: 'cover' }} />
        ) : (
          <span style={{ color: 'rgba(255,255,255,0.6)', fontSize: '13px', padding: '12px', textAlign: 'center' }}>
            {apercuKo ? "L'aperçu n'a pas pu être chargé. Ton invitation est bien enregistrée." : 'Aperçu en préparation…'}
          </span>
        )}
      </div>

      <div className="cp-root">
        <BandeauInvitant prenom={inviteur.prenom} photoUrl={inviteur.photo_url} />
      </div>

      <p data-testid="inv-statut" style={{ fontSize: '13px', margin: '0 0 12px', color: 'rgba(255,255,255,0.75)' }}>
        {dto && dto.status === 'active' ? 'Lien actif : tu peux partager ton invitation.' : 'Brouillon : le lien n\'est pas encore actif.'}
      </p>

      {eventPaid ? (
        <p data-testid="inv-fuseau" style={{ fontSize: '13px', margin: '0 0 12px', padding: '10px 12px', borderRadius: '10px', background: rgbaP(0.1), border: `1px solid ${rgbaP(0.35)}`, color: 'rgba(255,255,255,0.9)' }}>
          {TEXTE_FUSEAU_PALIERS}
        </p>
      ) : null}

      <div style={{ display: 'grid', gridTemplateColumns: mobile ? '1fr' : '1fr 1fr', gap: '8px' }}>
        {boutonPartage('inv-whatsapp', 'send', 'WhatsApp', surWhatsApp, peutPartager)}
        {boutonPartage('inv-partager-carte', 'image', 'Partager avec la carte', surPartagerCarte, peutPartager && peutCarte)}
        {boutonPartage('inv-partager', 'share', 'Partager', surPartager, peutPartager)}
        {boutonPartage('inv-copier', 'copy', 'Copier le lien', surCopier, peutPartager)}
        {boutonPartage('inv-qr', 'qrCode', qrVisible ? 'Masquer le QR code' : 'QR code', () => setQrVisible((v) => !v), peutPartager)}
      </div>
      {peutPartager && !peutCarte ? (
        <p style={styleAide}>Le partage avec la carte dépend de ton téléphone ; le lien affiche la carte de toute façon.</p>
      ) : null}
      {!peutPartager && !eventPaid ? (
        <p style={styleAide}>Active le lien pour pouvoir le partager.</p>
      ) : null}
      {qrVisible && peutPartager ? (
        <div style={{ display: 'flex', justifyContent: 'center', marginTop: '12px' }}>
          <div style={{ background: 'rgba(255,255,255,1)', padding: '12px', borderRadius: '12px' }}>
            <QRCodeSVG value={lien} size={180} />
          </div>
        </div>
      ) : null}
      {peutPartager ? (
        <p style={Object.assign({}, styleAide, { wordBreak: 'break-all' })} data-testid="inv-lien">{lien.replace(/^https?:\/\//, '')}</p>
      ) : null}
    </div>
  );

  // ── Cadre : modale centrée (desktop) ou bottom sheet (mobile) ────────────
  const peutEnregistrer = !occupe && !miniatureOccupee;
  const brouillon = !dto || dto.status !== 'active';
  // Lien ACTIF : plus de « brouillon » ; à l'étape 3, le bouton n'apparaît que
  // s'il reste des changements non enregistrés (le PUT n'envoie jamais `status`).
  const montrerEnregistrer = etape >= 2 && (brouillon || etape === 2 || nonEnregistre);
  let libelleEnregistrer;
  if (occupe) libelleEnregistrer = mobile ? '…' : 'Enregistrement…';
  else if (brouillon) libelleEnregistrer = mobile ? 'Brouillon' : 'Enregistrer le brouillon';
  else libelleEnregistrer = mobile ? 'Enregistrer' : 'Enregistrer les modifications';

  return (
    <div style={{
      position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, background: 'rgba(0,0,0,0.8)', zIndex: 9999,
      display: 'flex', alignItems: mobile ? 'flex-end' : 'center', justifyContent: 'center', padding: mobile ? 0 : '16px',
    }} onClick={(e) => { if (e.target === e.currentTarget) demanderFermeture(); }}>
      <div data-testid="inv-modal" role="dialog" aria-modal="true" aria-labelledby="inv-titre-modale" style={{
        position: 'relative',
        background: 'linear-gradient(135deg, rgba(26,16,37,1) 0%, rgba(13,10,20,1) 100%)',
        width: '100%', maxWidth: mobile ? '100%' : '600px', maxHeight: mobile ? '92vh' : '90vh',
        borderRadius: mobile ? '16px 16px 0 0' : '16px', overflow: 'hidden',
        border: `1px solid ${rgbaP(0.3)}`, display: 'flex', flexDirection: 'column', boxSizing: 'border-box',
      }}>
        {/* En-tête */}
        <div style={{ padding: '14px 16px 12px 20px', borderBottom: `1px solid ${rgbaP(0.2)}`, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <h3 id="inv-titre-modale" style={{ color: 'rgba(255,255,255,0.98)', fontSize: '16px', fontWeight: 600, margin: 0, display: 'inline-flex', alignItems: 'center', gap: '8px' }}>
            <SvgIcon name="gift" size={16} /> Nouvelle invitation
          </h3>
          <button type="button" onClick={demanderFermeture} aria-label="Fermer" data-testid="inv-fermer" style={{
            background: 'rgba(255,255,255,0.1)', border: 'none', color: 'rgba(255,255,255,0.98)',
            width: '44px', height: '44px', borderRadius: '10px', cursor: 'pointer', display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
          }}><SvgIcon name="close" size={18} /></button>
        </div>

        {/* Étapes */}
        <div style={{ padding: '12px 20px', display: 'flex', gap: '8px' }}>
          {STEPS.map((s) => (
            <div key={s.id} aria-current={etape === s.id ? 'step' : undefined} style={{
              flex: 1, padding: '8px', borderRadius: '8px', textAlign: 'center',
              background: etape === s.id ? rgbaP(0.3) : etape > s.id ? rgbaP(0.1) : 'rgba(255,255,255,0.05)',
              border: etape === s.id ? `1px solid ${rgbaP(0.55)}` : '1px solid transparent',
              color: etape >= s.id ? 'rgba(255,255,255,0.95)' : 'rgba(255,255,255,0.35)',
            }}>
              <SvgIcon name={etape > s.id ? 'check' : s.icon} size={14} />
              <div style={{ fontSize: '11px', marginTop: '2px' }}>{s.label}</div>
            </div>
          ))}
        </div>

        {/* Contenu défilant */}
        <div ref={defilementRef} data-testid="inv-defilement" style={{ flex: 1, overflowY: 'auto', padding: '8px 20px 16px', WebkitOverflowScrolling: 'touch' }}>
          {erreurOptions ? <p role="alert" style={Object.assign({}, styleErreur, { fontSize: '14px', marginBottom: '12px' })} data-testid="inv-erreur-options">{erreurOptions}</p> : null}
          {etape === 1 ? etape1 : null}
          {etape === 2 ? (options ? etape2 : <p style={styleAide}>Chargement de tes cours et offres…</p>) : null}
          {etape === 3 ? etape3 : null}
        </div>

        {/* Pied fixe */}
        <div style={{ padding: '12px 20px', paddingBottom: mobile ? 'calc(12px + env(safe-area-inset-bottom, 0px))' : '12px', borderTop: `1px solid ${rgbaP(0.2)}` }}>
          {erreur ? <p role="alert" data-testid="inv-erreur" style={Object.assign({}, styleErreur, { fontSize: '13px', margin: '0 0 10px' })}>{erreur}</p> : null}
          {montrerErreurs && !valide && etape === 2 ? (
            <p role="alert" style={Object.assign({}, styleErreur, { margin: '0 0 10px' })}>Corrige les champs signalés pour continuer.</p>
          ) : null}
          {feedback ? <p role="status" data-testid="inv-feedback" style={{ color: 'rgba(255,255,255,0.85)', fontSize: '13px', margin: '0 0 10px' }}>{feedback}</p> : null}
          {/* Mobile : UNE ligne à 360 px — Précédent en icône 44×44, libellés courts, l'action principale prend le reste. */}
          <div data-testid="inv-pied-boutons" style={{ display: 'flex', gap: '8px', flexWrap: mobile ? 'nowrap' : 'wrap', justifyContent: 'flex-end' }}>
            {etape > 1 ? (
              <button type="button" data-testid="inv-precedent" onClick={precedent} disabled={occupe}
                      aria-label="Précédent" title="Précédent"
                      style={Object.assign(styleBouton('neutre', !occupe), mobile
                        ? { width: '44px', minWidth: '44px', padding: 0, flex: 'none', marginRight: 'auto' }
                        : { marginRight: 'auto' })}>
                <SvgIcon name="arrowLeft" size={16} />{mobile ? null : ' Précédent'}
              </button>
            ) : null}
            {montrerEnregistrer ? (
              <button type="button" data-testid="inv-enregistrer" onClick={() => enregistrer({ force: etape === 3 })}
                      disabled={!peutEnregistrer}
                      style={Object.assign(styleBouton('contour', peutEnregistrer), mobile ? { flex: 'none', padding: '10px 12px' } : {})}>
                <SvgIcon name="save" size={16} /> {libelleEnregistrer}
              </button>
            ) : null}
            {etape < 3 ? (
              <button type="button" data-testid="inv-suivant" onClick={suivant}
                      disabled={occupe || miniatureOccupee || (etape === 1 && !type)}
                      style={Object.assign(styleBouton('plein', !(occupe || miniatureOccupee || (etape === 1 && !type))), mobile ? { flex: 1, minWidth: 0 } : {})}>
                Suivant <SvgIcon name="arrowRight" size={16} />
              </button>
            ) : null}
            {etape === 3 && brouillon && !eventPaid && dto ? (
              <button type="button" data-testid="inv-activer" onClick={activer} disabled={occupe}
                      style={Object.assign(styleBouton('plein', !occupe), mobile ? { flex: 1, minWidth: 0 } : {})}>
                <SvgIcon name="zap" size={16} /> Activer le lien
              </button>
            ) : null}
          </div>
        </div>

        {/* Confirmation de fermeture (dans la modale, jamais window.confirm) */}
        {confirmFermeture ? (
          <div data-testid="inv-confirmer-fermeture" role="alertdialog" aria-modal="true" style={{
            position: 'absolute', inset: 0, background: 'rgba(0,0,0,0.72)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '20px',
          }}>
            <div style={{ width: '100%', maxWidth: '380px', padding: '18px', borderRadius: '14px', background: 'rgba(22,14,30,1)', border: `1px solid ${rgbaP(0.4)}` }}>
              <p style={{ color: 'rgba(255,255,255,0.96)', fontSize: '15px', fontWeight: 600, margin: '0 0 6px' }}>Quitter sans enregistrer ?</p>
              <p style={{ color: 'rgba(255,255,255,0.7)', fontSize: '13px', margin: '0 0 14px' }}>Tes dernières modifications seront perdues.</p>
              <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end', flexWrap: 'wrap' }}>
                <button type="button" data-testid="inv-continuer-edition" onClick={() => setConfirmFermeture(false)} style={styleBouton('contour', true)}>
                  Continuer
                </button>
                <button type="button" data-testid="inv-quitter" onClick={() => { setConfirmFermeture(false); if (typeof onClose === 'function') onClose(); }}
                        style={styleBouton('neutre', true)}>
                  Quitter
                </button>
              </div>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}
