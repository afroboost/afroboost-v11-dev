/**
 * V610e — L'ÉDITEUR COMPLET D'UNE INVITATION EXISTANTE (tableau de bord coach).
 *
 * Le coach modifie seul : textes, description, bouton ; date / heure / lieu de
 * l'événement ; miniature, vidéo, message audio AVANT réservation, message audio
 * APRÈS réservation (« Deviens Afroboosteur ») ; les 3 tarifs et leurs bascules ;
 * la règle « offert aux membres 8 mois » ; le statut (brouillon / active / archivée).
 *
 * UNE SEULE SOURCE DE VÉRITÉ PAR DONNÉE : les textes et médias vivent sur
 * l'invitation (route existante), les prix et la date sur l'OFFRE (route
 * d'édition) — le serveur recalcule le montant de chaque paiement ; rien de passé
 * n'est réécrit. Aucun participant n'est jamais contacté depuis cet écran.
 *
 * DESIGN ÉPURÉ (CLAUDE.md) : sections repliables, une seule ouverte ; aperçu en
 * direct (mobile / bureau) à droite sur ordinateur, derrière un bouton sur mobile.
 * RÉSEAU : lecture UNE fois à l'ouverture ; simulation des tarifs sur une clé
 * PRIMITIVE (jamais un objet) ; aucun setState d'objet identique (pas de boucle).
 */
import React, { Suspense, lazy, useEffect, useMemo, useRef, useState } from 'react';
import SvgIcon from '../SvgIcon';
import InvitationMiniature from './InvitationMiniature';
import ChoixMedia from './ChoixMedia';
import InvitationPublique from '../InvitationPublique';
import InviterMesAmis from '../InviterMesAmis';
import useLargeurEcran from '../../utils/useLargeurEcran';
import { uploadToCloudinary } from '../CloudinaryUploadButton';
import { SectionAvantages, SectionUrgence } from './AvantagesMembresEditeur'; // V618M
import { formAvantages, changementsAvantages, erreurAvantages } from '../../utils/avantagesMembres'; // V618M
// V610g : L'OUTIL VIDÉO EXISTANT (Prospection → Médias « Modifier / exporter ») — découpe, formats
// Auto / 16:9 / 9:16 / 1:1, export, « Capturer cette image comme miniature ». Chargé à la demande.
const OutilVideo = lazy(() => import('./prospection/ProspectionVideoEditeur'));
import {
  lireEdition, enregistrerInvitation, enregistrerEvenement, archiverInvitation, importerMedia, lireMediasCoach,
  changementsEvenement, estSensible, erreurTarifs, quandLisible, LIBELLES_TYPE, LIBELLES_STATUT,
} from '../../utils/invitationEdition';

const PRIMAIRE = 'var(--primary-color, #D91CD2)';
const rgbaP = (a) => `rgba(var(--primary-rgb, 217, 28, 210), ${a})`;
const LIMITES = { title: 80, subtitle: 120, description: 1500, message: 280, cta_label: 30 };
const CHAMPS_INVITATION = ['title', 'subtitle', 'description', 'message', 'cta_label', 'image_url', 'image_source',
  'video_url', 'audio_url', 'audio_partage_url'];
const JOURS = ['dimanche', 'lundi', 'mardi', 'mercredi', 'jeudi', 'vendredi', 'samedi'];
const MOIS = ['janvier', 'février', 'mars', 'avril', 'mai', 'juin', 'juillet', 'août', 'septembre', 'octobre', 'novembre', 'décembre'];

const styleChamp = { width: '100%', minHeight: 44, padding: '10px 12px', borderRadius: 10, boxSizing: 'border-box', fontSize: 16,
  background: 'rgba(255,255,255,0.07)', border: `1px solid ${rgbaP(0.3)}`, color: 'rgba(255,255,255,0.96)', outline: 'none' };
const styleLabel = { display: 'block', fontSize: 13, fontWeight: 600, color: 'rgba(255,255,255,0.9)', marginBottom: 6 };
function btn(variante, actif = true) {
  return { minHeight: 44, padding: '10px 16px', borderRadius: 12, fontSize: 14.5, fontWeight: 700, boxSizing: 'border-box',
    display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 8, cursor: actif ? 'pointer' : 'not-allowed',
    opacity: actif ? 1 : 0.5, color: 'rgba(255,255,255,0.98)',
    background: variante === 'plein' ? PRIMAIRE : 'rgba(255,255,255,0.07)',
    border: variante === 'plein' ? 'none' : `1px solid ${variante === 'danger' ? 'rgba(255,140,130,0.5)' : rgbaP(0.4)}` };
}

function Champ({ id, label, aide, compteur, children }) {
  return (
    <div style={{ marginBottom: 14 }}>
      <label htmlFor={id} style={styleLabel}>{label}{compteur ? <span style={{ float: 'right', fontWeight: 500, color: 'rgba(255,255,255,0.5)' }}>{compteur}</span> : null}</label>
      {children}
      {aide ? <div style={{ fontSize: 12.5, color: 'rgba(255,255,255,0.55)', marginTop: 5 }}>{aide}</div> : null}
    </div>
  );
}

function Section({ id, titre, icone, resume, ouverte, onBasculer, children }) {
  return (
    <section data-testid={`edit-section-${id}`} style={{ borderRadius: 14, marginBottom: 10, background: 'rgba(255,255,255,0.035)',
      border: ouverte ? `1px solid ${rgbaP(0.45)}` : '1px solid rgba(255,255,255,0.09)' }}>
      <button type="button" onClick={onBasculer} aria-expanded={ouverte} data-testid={`edit-section-${id}-titre`}
              style={{ width: '100%', minHeight: 56, padding: '12px 14px', background: 'none', border: 'none', color: 'rgba(255,255,255,0.96)',
                display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer', textAlign: 'left' }}>
        <span style={{ color: PRIMAIRE, display: 'inline-flex' }}><SvgIcon name={icone} size={18} /></span>
        <span style={{ flex: 1, minWidth: 0 }}>
          <span style={{ display: 'block', fontWeight: 800, fontSize: 15 }}>{titre}</span>
          {!ouverte && resume ? <span style={{ display: 'block', fontSize: 12.5, color: 'rgba(255,255,255,0.55)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{resume}</span> : null}
        </span>
        <SvgIcon name={ouverte ? 'arrowUp' : 'arrowDown'} size={16} />
      </button>
      {ouverte ? <div style={{ padding: '2px 14px 14px' }}>{children}</div> : null}
    </section>
  );
}

function formDepuis(ed) {
  const i = (ed && ed.invitation) || {};
  const e = (ed && ed.evenement) || {};
  const t = e.tarifs || {};
  return {
    title: i.title || '', subtitle: i.subtitle || '', description: i.description || '', message: i.message || '',
    cta_label: i.cta_label || '', image_url: i.image_url || null, image_source: i.image_source || 'default',
    video_url: i.video_url || null, audio_url: i.audio_url || null, audio_partage_url: i.audio_partage_url || null,
    date: e.date || '', heure: e.heure || '', lieu: e.lieu || '',
    prevente: t.prevente != null ? String(t.prevente) : '', standard: t.standard != null ? String(t.standard) : '',
    derniere_minute: t.derniere_minute != null ? String(t.derniere_minute) : '',
    fin_prevente: t.fin_prevente || '', fin_standard: t.fin_standard || '',
    membres_actif: e.membres ? !!e.membres.actif : null,
    ...formAvantages(e),   // V618M : avantages par offre + urgence / places
  };
}

function libelleDate(date) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(String(date || ''))) return null;
  const d = new Date(`${date}T12:00:00`);
  return `${JOURS[d.getDay()]} ${d.getDate()} ${MOIS[d.getMonth()]}`;
}

/** Ce que l'invité verra : le DTO de l'invitation + le formulaire en cours + le tarif simulé. */
function dtoApercu(ed, form, simulation) {
  const i = (ed && ed.invitation) || {};
  const e = (ed && ed.evenement) || {};
  const t = (simulation && simulation.tarifs) || e.tarifs;
  let pa = i.prix_actif || null;
  if (i.type === 'event_paid' && t) {
    const actif = (simulation && simulation.palier_actif) || t.palier_actif;
    const L = t.libelles || {};
    const paliers = [['early_bird', L.prevente, form.prevente], ['standard', L.standard, form.standard], ['last_minute', L.derniere_minute, form.derniere_minute]]
      .map(([p, l, v]) => ({ palier: p, libelle: l, prix: Number(v), actif: p === actif }));
    const cur = paliers.find((p) => p.actif) || paliers[0];
    pa = { prix: cur.prix, palier: cur.palier, libelle: cur.libelle, paliers, prochain: null };
  }
  return Object.assign({}, i, {
    title: form.title, subtitle: form.subtitle, description: form.description, message: form.message, cta_label: form.cta_label,
    image_url: form.image_source === 'default' ? null : form.image_url, video_url: form.video_url, audio_url: form.audio_url,
    audio_partage_url: form.audio_partage_url,
    date_label: (e && form.date) ? libelleDate(form.date) : i.date_label, time_label: form.heure || i.time_label,
    lieu: form.lieu || i.lieu, prix_actif: pa, cible: '#',
    // V618M : l'aperçu suit immédiatement le badge et la présence d'avantages membres.
    message_places: form.urgence && form.urgence.visible && String(form.urgence.texte || '').trim() ? String(form.urgence.texte).trim() : null,
    gratuit_membres: form.avantages ? (form.membres_actif !== false && form.avantages.some((r) => r.type !== 'aucun')) : i.gratuit_membres,
  });
}

function Apercu({ dto, mode, setMode, largeurDispo, afficherApres }) {
  const largeurCadre = mode === 'bureau' ? 1024 : 390;
  const echelle = Math.min(1, (largeurDispo || largeurCadre) / largeurCadre);
  return (
    <div data-testid="edit-apercu">
      <div style={{ display: 'flex', gap: 6, marginBottom: 10 }} role="group" aria-label="Taille d'écran de l'aperçu">
        {[['mobile', 'phone', 'Mobile'], ['bureau', 'monitor', 'Ordinateur']].map(([m, ic, lib]) => (
          <button key={m} type="button" onClick={() => setMode(m)} aria-pressed={mode === m} data-testid={`edit-apercu-${m}`}
                  style={Object.assign(btn(mode === m ? 'plein' : 'contour'), { minHeight: 36, padding: '6px 12px', fontSize: 13 })}>
            <SvgIcon name={ic} size={14} /> {lib}
          </button>
        ))}
      </div>
      <div style={{ width: largeurCadre * echelle, height: 640 * echelle, overflow: 'hidden', borderRadius: 18,
        border: '1px solid rgba(255,255,255,0.14)', background: 'rgb(8,4,12)', margin: '0 auto' }}>
        <div style={{ width: largeurCadre, height: 640, transform: `scale(${echelle})`, transformOrigin: 'top left', overflowY: 'auto' }}>
          <InvitationPublique apercu={dto} token="apercu" />
        </div>
      </div>
      {afficherApres ? (
        <div style={{ marginTop: 14 }}>
          <div style={{ fontSize: 12.5, color: 'rgba(255,255,255,0.6)', marginBottom: 4 }}>Après la réservation, l'invité voit :</div>
          <InviterMesAmis apercuDetails={dto} />
        </div>
      ) : null}
    </div>
  );
}

export default function EditeurInvitation({ invitationId, onClose, onEnregistre }) {
  const { largeur } = useLargeurEcran();
  const mobile = largeur < 900;
  const [ed, setEd] = useState(null);
  const [erreurChargement, setErreurChargement] = useState('');
  const [form, setForm] = useState(null);
  const [section, setSection] = useState('contenu');
  const [modeApercu, setModeApercu] = useState('mobile');
  const [apercuOuvert, setApercuOuvert] = useState(false);
  const [simulation, setSimulation] = useState(null);
  const [occupe, setOccupe] = useState(false);
  const [message, setMessage] = useState(null);         // { ton: 'ok'|'erreur', texte }
  const [confirmation, setConfirmation] = useState(null); // { texte, relancer }
  const [miniatureOccupee, setMiniatureOccupee] = useState(false);
  const [outilVideo, setOutilVideo] = useState('');          // V610g : adresse de la vidéo ouverte dans l'outil
  const [biblioImages, setBiblioImages] = useState(null);     // null = fermée
  const panneauApercu = useRef(null);

  useEffect(() => {
    let vivant = true;
    lireEdition(invitationId)
      .then((d) => { if (vivant) { setEd(d); setForm(formDepuis(d)); } })
      .catch((e) => { if (vivant) setErreurChargement((e && e.response && e.response.status === 404) ? 'Invitation introuvable.' : 'Chargement impossible. Réessaie.'); });
    return () => { vivant = false; };
  }, [invitationId]);

  const evt = ed && ed.evenement;
  const inv = ed && ed.invitation;
  const type = inv && inv.type;
  const tarifs = evt && evt.tarifs;
  // Simulation du tarif actif : clé PRIMITIVE, appel différé (aucune boucle).
  const cleTarifs = form && tarifs ? [form.prevente, form.standard, form.derniere_minute, form.fin_prevente, form.fin_standard, form.date, form.heure].join('|') : '';
  useEffect(() => {
    if (!cleTarifs || !form || !evt) return undefined;
    const chg = changementsEvenement(form, evt);
    const corps = {};
    ['prevente', 'standard', 'derniere_minute', 'fin_prevente', 'fin_standard', 'date', 'heure'].forEach((k) => { if (k in chg) corps[k] = chg[k]; });
    if (!Object.keys(corps).length) { setSimulation((p) => (p === null ? p : null)); return undefined; }
    if (erreurTarifs(form, evt)) return undefined;
    let vivant = true;
    const t = setTimeout(() => {
      enregistrerEvenement(invitationId, Object.assign(corps, { simuler: true }))
        .then((r) => { if (vivant) setSimulation(r); }).catch(() => { if (vivant) setSimulation(null); });
    }, 450);
    return () => { vivant = false; clearTimeout(t); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cleTarifs, invitationId]);

  const apercu = useMemo(() => (ed && form ? dtoApercu(ed, form, simulation) : null), [ed, form, simulation]);
  if (erreurChargement) {
    return <Cadre mobile={mobile} onClose={onClose} titre="Modifier l'invitation"><p role="alert" style={{ color: 'rgba(255,200,190,0.95)' }}>{erreurChargement}</p></Cadre>;
  }
  if (!ed || !form) return <Cadre mobile={mobile} onClose={onClose} titre="Modifier l'invitation"><p style={{ color: 'rgba(255,255,255,0.7)' }}>Chargement…</p></Cadre>;

  const maj = (k, v) => setForm((p) => (p[k] === v ? p : Object.assign({}, p, { [k]: v })));
  const bascule = (s) => setSection((x) => (x === s ? '' : s));
  const statut = inv.status;
  const errTarifs = erreurTarifs(form, evt) || erreurAvantages(form);   // V618M
  const chgEvt = Object.assign(changementsEvenement(form, evt), changementsAvantages(form, evt));
  const chgInv = {};
  CHAMPS_INVITATION.forEach((k) => {
    const avant = k === 'image_source' ? (inv.image_source || 'default') : (inv[k] || null);
    const apres = form[k] === '' ? null : form[k];
    if ((avant || null) !== (apres || null)) chgInv[k] = apres;
  });
  if ('image_url' in chgInv && !('image_source' in chgInv)) chgInv.image_source = form.image_source;
  const modifie = Object.keys(chgInv).length > 0 || Object.keys(chgEvt).length > 0;

  const recharger = () => lireEdition(invitationId).then((d) => { setEd(d); setForm(formDepuis(d)); setSimulation(null); });
  const erreurDe = (e) => {
    const d = e && e.response && e.response.data && e.response.data.detail;
    if (d && typeof d === 'object' && d.message) return d.message;
    return typeof d === 'string' ? d : 'Enregistrement impossible. Réessaie.';
  };

  const enregistrer = async (statutCible, confirmer) => {
    if (errTarifs) {
      const av = erreurAvantages(form);   // V618M : ouvrir la section fautive
      setMessage({ ton: 'erreur', texte: errTarifs });
      setSection(!av ? 'tarifs' : (/capacit|urgence/i.test(av) ? 'urgence' : 'avantages'));
      return;
    }
    setOccupe(true); setMessage(null);
    try {
      if (Object.keys(chgEvt).length) {
        await enregistrerEvenement(invitationId, Object.assign({}, chgEvt, confirmer ? { confirmer: true } : {}));
      }
      const corps = Object.assign({}, chgInv, statutCible ? { status: statutCible } : {});
      if (Object.keys(corps).length) await enregistrerInvitation(invitationId, corps);
      await recharger();
      setMessage({ ton: 'ok', texte: statutCible === 'active' ? 'Invitation publiée.' : 'Modifications enregistrées.' });
      if (onEnregistre) onEnregistre();
    } catch (e) {
      const d = e && e.response && e.response.data && e.response.data.detail;
      if (e && e.response && e.response.status === 409 && d && d.code === 'confirmation_requise') {
        setConfirmation({ texte: d.message, relancer: () => { setConfirmation(null); enregistrer(statutCible, true); } });
      } else {
        setMessage({ ton: 'erreur', texte: erreurDe(e) });
      }
    } finally { setOccupe(false); }
  };
  const archiver = async () => {
    setConfirmation({ texte: "Archiver cette invitation ? Son lien ne s'ouvrira plus. Les réservations déjà prises ne changent pas.", danger: true,
      relancer: async () => {
        setConfirmation(null); setOccupe(true);
        try { await archiverInvitation(invitationId); await recharger(); if (onEnregistre) onEnregistre(); setMessage({ ton: 'ok', texte: 'Invitation archivée.' }); }
        catch (e) { setMessage({ ton: 'erreur', texte: erreurDe(e) }); } finally { setOccupe(false); }
      } });
  };

  const archivee = statut === 'archived';
  const evenement = type === 'event_free' || type === 'event_paid';
  const compteur = (k) => `${String(form[k] || '').length}/${LIMITES[k]}`;
  const prixActif = (simulation && simulation.prix_actif) != null ? simulation.prix_actif : (tarifs && tarifs.prix_actif);
  const largeurApercu = mobile ? Math.min(largeur - 48, 420) : 360;

  // V610g — miniature / vidéo produites par l'outil : enregistrées TOUT DE SUITE sur l'invitation
  // (route existante, version +1 -> aperçus rafraîchis, liens intacts), sans perdre les autres
  // modifications en cours du formulaire.
  const appliquerMedia = async (corps, texte) => {
    const dto = await enregistrerInvitation(invitationId, corps);
    setEd((p) => Object.assign({}, p, { invitation: Object.assign({}, p.invitation, dto || {}, corps) }));
    setForm((p) => Object.assign({}, p, corps));
    setMessage({ ton: 'ok', texte });
    if (onEnregistre) onEnregistre();
  };
  const enregistrerMiniatureCapturee = async (fichier) => {
    const r = await uploadToCloudinary(fichier, { folder: 'invitations' });
    if (!r || !r.url) throw new Error("La miniature n'a pas pu être envoyée.");
    await appliquerMedia({ image_url: r.url, image_source: 'upload' }, 'Miniature capturée et enregistrée pour cette invitation.');
  };
  const enregistrerVersionExportee = async (fichier, meta, surProgression) => {
    const r = await importerMedia(fichier, 'video', surProgression);
    await appliquerMedia({ video_url: r.url }, 'Nouvelle version de la vidéo enregistrée pour cette invitation.');
    return "Version enregistrée : elle remplace la vidéo de l'invitation.";
  };
  const ouvrirBiblioImages = () => {
    if (biblioImages) { setBiblioImages(null); return; }
    lireMediasCoach('image').then(setBiblioImages).catch(() => setBiblioImages([]));
  };
  const choisirMiniature = (url) => {
    setForm((p) => Object.assign({}, p, { image_url: url, image_source: 'upload' }));
    setBiblioImages(null);
  };

  const contenu = (
    <>
      <Section id="contenu" titre="Contenu" icone="edit" resume={form.title || 'Titre, accroche, description, bouton'} ouverte={section === 'contenu'} onBasculer={() => bascule('contenu')}>
        <Champ id="ed-titre" label="Titre" compteur={compteur('title')}>
          <input id="ed-titre" data-testid="ed-titre" style={styleChamp} maxLength={LIMITES.title} value={form.title} onChange={(e) => maj('title', e.target.value)} disabled={archivee} />
        </Champ>
        <Champ id="ed-accroche" label="Accroche (sous le titre)" compteur={compteur('subtitle')}>
          <input id="ed-accroche" data-testid="ed-accroche" style={styleChamp} maxLength={LIMITES.subtitle} value={form.subtitle} onChange={(e) => maj('subtitle', e.target.value)} disabled={archivee} />
        </Champ>
        <Champ id="ed-description" label="Description (bloc « Détails »)" compteur={compteur('description')}
               aide={!form.description && evt && evt.description_offre ? 'Astuce : tu peux reprendre la description de ton offre.' : null}>
          <textarea id="ed-description" data-testid="ed-description" rows={5} style={Object.assign({}, styleChamp, { minHeight: 110, resize: 'vertical' })}
                    maxLength={LIMITES.description} value={form.description} onChange={(e) => maj('description', e.target.value)} disabled={archivee} />
          {!form.description && evt && evt.description_offre ? (
            <button type="button" style={Object.assign(btn('contour'), { minHeight: 36, marginTop: 8, fontSize: 13 })}
                    onClick={() => maj('description', String(evt.description_offre).slice(0, LIMITES.description))} data-testid="ed-description-reprendre">
              Reprendre la description de l'offre
            </button>
          ) : null}
        </Champ>
        <Champ id="ed-message" label="Mot d'invitation (facultatif)" compteur={compteur('message')} aide="Affiché sur la page de ton invitation, signé de ton prénom.">
          <textarea id="ed-message" data-testid="ed-message" rows={3} style={Object.assign({}, styleChamp, { minHeight: 80, resize: 'vertical' })}
                    maxLength={LIMITES.message} value={form.message} onChange={(e) => maj('message', e.target.value)} disabled={archivee} />
        </Champ>
        <Champ id="ed-cta" label="Texte du bouton" compteur={compteur('cta_label')}>
          <input id="ed-cta" data-testid="ed-cta" style={styleChamp} maxLength={LIMITES.cta_label} value={form.cta_label} onChange={(e) => maj('cta_label', e.target.value)} disabled={archivee} />
        </Champ>
      </Section>

      {evenement ? (
        <Section id="evenement" titre="Événement" icone="calendar" ouverte={section === 'evenement'} onBasculer={() => bascule('evenement')}
                 resume={[libelleDate(form.date), form.heure, form.lieu].filter(Boolean).join(' · ')}>
          {evt.participants && (evt.participants.reservations || evt.participants.paiements) ? (
            <div data-testid="ed-participants" style={{ padding: '10px 12px', borderRadius: 10, background: rgbaP(0.1), fontSize: 13, color: 'rgba(255,255,255,0.85)', marginBottom: 12 }}>
              {evt.participants.reservations} réservation(s) déjà prise(s). Une modification de date, d'heure ou de lieu vaudra pour les prochaines réservations ; personne n'est prévenu automatiquement.
            </div>
          ) : null}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
            <Champ id="ed-date" label="Date">
              <input id="ed-date" data-testid="ed-date" type="date" style={Object.assign({}, styleChamp, { minWidth: 0 })} value={form.date} onChange={(e) => maj('date', e.target.value)} disabled={archivee || !evt.date_modifiable} />
            </Champ>
            <Champ id="ed-heure" label="Heure">
              <input id="ed-heure" data-testid="ed-heure" type="time" style={Object.assign({}, styleChamp, { minWidth: 0 })} value={form.heure} onChange={(e) => maj('heure', e.target.value)} disabled={archivee || !evt.date_modifiable} />
            </Champ>
          </div>
          {evt.cours_recurrent ? <div style={{ fontSize: 12.5, color: 'rgba(255,255,255,0.55)', margin: '-6px 0 12px' }}>Cours régulier lié : si la date choisie ne correspond pas à une séance existante, une séance ponctuelle sera créée.</div> : null}
          <Champ id="ed-lieu" label="Lieu">
            <input id="ed-lieu" data-testid="ed-lieu" style={styleChamp} maxLength={160} value={form.lieu} onChange={(e) => maj('lieu', e.target.value)} disabled={archivee} />
          </Champ>
          <div style={{ fontSize: 12.5, color: 'rgba(255,255,255,0.55)' }}>Aucune limite de places n'est appliquée.</div>
        </Section>
      ) : null}

      <Section id="medias" titre="Médias" icone="video" ouverte={section === 'medias'} onBasculer={() => bascule('medias')}
               resume={[form.video_url ? 'Vidéo' : null, form.image_source !== 'default' ? 'Miniature' : null, form.audio_url ? 'Audio avant' : null, form.audio_partage_url ? 'Audio après' : null].filter(Boolean).join(' · ') || 'Miniature, vidéo, messages audio'}>
        <div style={{ marginBottom: 12 }}>
          <div style={{ fontWeight: 700, fontSize: 14, marginBottom: 2 }}>Miniature / aperçu de partage</div>
          <div style={{ fontSize: 12.5, color: 'rgba(255,255,255,0.6)', marginBottom: 8 }}>Image de la page, affiche de la vidéo et aperçu WhatsApp.</div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 10 }}>
            {form.video_url ? (
              <button type="button" style={Object.assign(btn('contour'), { minHeight: 40, fontSize: 13.5 })} onClick={() => setOutilVideo(form.video_url)}
                      data-testid="ed-miniature-capturer">
                <SvgIcon name="camera" size={15} /> Capturer depuis la vidéo
              </button>
            ) : null}
            <button type="button" style={Object.assign(btn('contour'), { minHeight: 40, fontSize: 13.5 })} onClick={ouvrirBiblioImages}
                    data-testid="ed-miniature-biblio" aria-expanded={!!biblioImages}>
              <SvgIcon name="layers" size={15} /> {biblioImages ? 'Fermer la bibliothèque' : 'Choisir dans la bibliothèque'}
            </button>
          </div>
          {biblioImages ? (
            <div data-testid="ed-miniature-liste" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(120px, 1fr))', gap: 8, marginBottom: 10 }}>
              {biblioImages.length === 0 ? <div style={{ fontSize: 13, color: 'rgba(255,255,255,0.6)' }}>Aucune image pour le moment.</div> : null}
              {biblioImages.map((m) => (
                <button key={m.url} type="button" onClick={() => choisirMiniature(m.url)} data-testid="ed-miniature-choisir" title={m.nom || ''}
                        style={{ padding: 0, borderRadius: 10, overflow: 'hidden', cursor: 'pointer', aspectRatio: '1200 / 630', background: rgbaP(0.12),
                          border: m.url === form.image_url ? `2px solid ${PRIMAIRE}` : '1px solid rgba(255,255,255,0.12)' }}>
                  <img src={m.url} alt={m.nom || ''} loading="lazy" style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }} />
                </button>
              ))}
            </div>
          ) : null}
          <InvitationMiniature value={form.image_url} source={form.image_source} defaultUrl={inv.card_url}
                               onChange={({ image_url: u, image_source: s }) => setForm((p) => Object.assign({}, p, { image_url: u, image_source: s }))}
                               onBusyChange={setMiniatureOccupee} />
        </div>
        <ChoixMedia type="video" testid="ed-video" libelle="Vidéo de l'invitation" aide="Jamais lancée automatiquement : l'invité la démarre. Tout format : 9:16, 16:9, carré…"
                    valeur={form.video_url} onChange={(u) => maj('video_url', u)} onOuvrirOutil={setOutilVideo} />
        {/* V610l : pour l'Essai gratuit, c'est LE message joué sur « Ton essai est prêt ». */}
        <ChoixMedia type="audio" testid="ed-audio-avant"
                    libelle={type === 'trial' ? 'Message audio « Ton essai est prêt » (facultatif)' : 'Message audio avant réservation (facultatif)'}
                    aide={type === 'trial' ? 'Bloc « Deviens Afroboosteur » : lancé après « Valider ma séance », une seule fois (bouton Écouter si le navigateur le bloque).' : "Écoutable sur la page de l'invitation, au clic."}
                    valeur={form.audio_url} onChange={(u) => maj('audio_url', u)} />
        {type === 'event_paid' ? (
          <ChoixMedia type="audio" testid="ed-audio-apres" libelle="Message audio après réservation / partage"
                      aide="Bloc « Deviens Afroboosteur » affiché après le paiement, avant « Inviter mes amis »."
                      valeur={form.audio_partage_url} onChange={(u) => maj('audio_partage_url', u)} />
        ) : null}
      </Section>

      {type === 'event_paid' && tarifs ? (
        <Section id="tarifs" titre="Tarifs" icone="ticket" ouverte={section === 'tarifs'} onBasculer={() => bascule('tarifs')}
                 resume={prixActif != null ? `Tarif actif : ${prixActif} CHF` : ''}>
          {[['prevente', 'fin_prevente', tarifs.libelles.prevente], ['standard', 'fin_standard', tarifs.libelles.standard], ['derniere_minute', null, tarifs.libelles.derniere_minute]].map(([k, fin, lib]) => (
            <div key={k} data-testid={`ed-palier-${k}`} style={{ padding: 12, borderRadius: 12, background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.09)', marginBottom: 10 }}>
              <div style={{ fontWeight: 800, fontSize: 14.5, marginBottom: 8 }}>{lib}</div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 10, alignItems: 'end' }}>
                <div>
                  <label htmlFor={`ed-prix-${k}`} style={styleLabel}>Prix (CHF)</label>
                  <input id={`ed-prix-${k}`} data-testid={`ed-prix-${k}`} type="number" min="1" step="0.5" inputMode="decimal" style={styleChamp}
                         value={form[k]} onChange={(e) => maj(k, e.target.value)} disabled={archivee} />
                </div>
                <div>
                  <label htmlFor={fin ? `ed-${fin}` : undefined} style={styleLabel}>Jusqu'au</label>
                  {fin ? (
                    <input id={`ed-${fin}`} data-testid={`ed-${fin}`} type="datetime-local" style={Object.assign({}, styleChamp, { minWidth: 0, maxWidth: '100%' })} value={form[fin]}
                           onChange={(e) => maj(fin, e.target.value)} disabled={archivee} />
                  ) : <div style={{ minHeight: 44, display: 'flex', alignItems: 'center', fontSize: 14, color: 'rgba(255,255,255,0.75)' }}>Début de l'événement</div>}
                </div>
              </div>
              {fin && form[fin] ? <div style={{ fontSize: 12.5, color: 'rgba(255,255,255,0.55)', marginTop: 6 }}>{quandLisible(form[fin])} (heure suisse)</div> : null}
            </div>
          ))}
          {errTarifs ? <p role="alert" data-testid="ed-tarifs-erreur" style={{ color: 'rgba(255,190,180,0.98)', fontSize: 13 }}>{errTarifs}</p> : null}
          <div data-testid="ed-tarif-actif" style={{ padding: '12px 14px', borderRadius: 12, background: rgbaP(0.14), border: `1px solid ${rgbaP(0.4)}`, fontWeight: 800 }}>
            Tarif actuellement actif : {prixActif != null ? `${prixActif} CHF` : '—'}
          </div>
          <div style={{ fontSize: 12.5, color: 'rgba(255,255,255,0.55)', marginTop: 8 }}>
            Le prix est recalculé par le serveur à chaque paiement. Les paiements déjà faits ne changent jamais. Plus aucune vente après le début.
          </div>
        </Section>
      ) : null}

      {type === 'event_paid' && evt && evt.avantages ? (
        <Section id="avantages" titre="Avantages membres" icone="heart" ouverte={section === 'avantages'} onBasculer={() => bascule('avantages')}
                 resume={(form.avantages || []).filter((r) => r.type !== 'aucun').length
                   ? `${(form.avantages || []).filter((r) => r.type !== 'aucun').length} offre(s) avec avantage` : 'Aucun avantage'}>
          <SectionAvantages evt={evt} form={form} setForm={setForm} prixPublic={prixActif} archivee={archivee} />
        </Section>
      ) : null}

      {evenement && evt && evt.urgence ? (
        <Section id="urgence" titre="Urgence / places" icone="fire" ouverte={section === 'urgence'} onBasculer={() => bascule('urgence')}
                 resume={[form.urgence && form.urgence.visible && form.urgence.texte ? form.urgence.texte : 'Aucun badge',
                   form.urgence && form.urgence.capacite_limitee ? `max ${form.urgence.capacite_max} places` : 'aucune limite'].join(' · ')}>
          <SectionUrgence evt={evt} form={form} setForm={setForm} archivee={archivee} />
        </Section>
      ) : null}

      <Section id="partage" titre="Partage & statut" icone="share" ouverte={section === 'partage'} onBasculer={() => bascule('partage')}
               resume={LIBELLES_STATUT[statut] || statut}>
        <div style={{ fontSize: 13.5, color: 'rgba(255,255,255,0.8)', marginBottom: 10 }}>
          Statut : <strong data-testid="ed-statut">{LIBELLES_STATUT[statut] || statut}</strong>
        </div>
        {inv.share_url && statut === 'active' ? (
          <a href={inv.share_url} target="_blank" rel="noopener noreferrer" style={Object.assign(btn('contour'), { textDecoration: 'none', marginBottom: 10 })} data-testid="ed-voir-page">
            <SvgIcon name="externalLink" size={15} /> Voir la page de l'invitation
          </a>
        ) : null}
        <div style={{ fontSize: 12.5, color: 'rgba(255,255,255,0.55)', marginBottom: 12 }}>
          Les liens déjà partagés (le tien et ceux de tes invités) restent valides après chaque modification.
        </div>
        {!archivee ? <button type="button" style={btn('danger', !occupe)} onClick={archiver} disabled={occupe} data-testid="ed-archiver"><SvgIcon name="archive" size={15} /> Archiver</button> : null}
      </Section>
    </>
  );

  return (
    <Cadre mobile={mobile} onClose={onClose} titre={inv.title || 'Modifier l\'invitation'}
           sousTitre={`${LIBELLES_TYPE[type] || ''} · ${LIBELLES_STATUT[statut] || statut}`}
           pied={!archivee ? (
             <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
               {mobile ? <button type="button" style={btn('contour')} onClick={() => setApercuOuvert(true)} data-testid="ed-apercu-ouvrir"><SvgIcon name="eye" size={16} /> Aperçu</button> : null}
               <button type="button" style={btn(statut === 'draft' ? 'contour' : 'plein', modifie && !occupe && !miniatureOccupee)} disabled={!modifie || occupe || miniatureOccupee}
                       onClick={() => enregistrer(null)} data-testid="ed-enregistrer">
                 <SvgIcon name="save" size={16} /> {statut === 'draft' ? 'Enregistrer le brouillon' : 'Enregistrer les modifications'}
               </button>
               {statut === 'draft' ? (
                 <button type="button" style={btn('plein', !occupe && !miniatureOccupee)} disabled={occupe || miniatureOccupee} onClick={() => enregistrer('active')} data-testid="ed-publier">
                   <SvgIcon name="send" size={16} /> Publier
                 </button>
               ) : null}
             </div>
           ) : null}>
      {message ? <div role={message.ton === 'erreur' ? 'alert' : 'status'} data-testid="ed-message-retour"
                      style={{ padding: '10px 12px', borderRadius: 10, marginBottom: 12, fontSize: 14,
                        background: message.ton === 'erreur' ? 'rgba(255,90,80,0.14)' : rgbaP(0.14), color: 'rgba(255,255,255,0.95)' }}>{message.texte}</div> : null}
      {mobile ? contenu : (
        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) 380px', gap: 18, alignItems: 'start' }}>
          <div style={{ minWidth: 0 }}>{contenu}</div>
          <div ref={panneauApercu} style={{ position: 'sticky', top: 0 }}>
            <Apercu dto={apercu} mode={modeApercu} setMode={setModeApercu} largeurDispo={largeurApercu}
                    afficherApres={type === 'event_paid' && !!form.audio_partage_url} />
          </div>
        </div>
      )}
      {mobile && apercuOuvert ? (
        <div role="dialog" aria-modal="true" aria-label="Aperçu" data-testid="ed-apercu-feuille"
             style={{ position: 'fixed', inset: 0, zIndex: 10002, background: 'rgba(0,0,0,0.88)', overflowY: 'auto', padding: 16, boxSizing: 'border-box' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
            <strong style={{ color: 'rgba(255,255,255,0.95)' }}>Aperçu</strong>
            <button type="button" style={btn('contour')} onClick={() => setApercuOuvert(false)} aria-label="Fermer l'aperçu" data-testid="ed-apercu-fermer"><SvgIcon name="close" size={16} /></button>
          </div>
          <Apercu dto={apercu} mode={modeApercu} setMode={setModeApercu} largeurDispo={largeurApercu}
                  afficherApres={type === 'event_paid' && !!form.audio_partage_url} />
        </div>
      ) : null}
      {outilVideo ? (
        <div role="dialog" aria-modal="true" aria-label="Modifier / exporter la vidéo" data-testid="ed-outil-video"
             style={{ position: 'fixed', inset: 0, zIndex: 10004, background: 'rgba(0,0,0,0.85)', overflowY: 'auto', padding: mobile ? 8 : 20, boxSizing: 'border-box' }}>
          <div style={{ maxWidth: 1000, margin: '0 auto', background: 'rgb(14,6,18)', borderRadius: 16, padding: 12, border: `1px solid ${rgbaP(0.35)}` }}>
            <Suspense fallback={<p style={{ color: 'rgba(255,255,255,0.7)' }}>Chargement de l'outil vidéo…</p>}>
              <OutilVideo API={`${process.env.REACT_APP_BACKEND_URL || ''}/api`} niche="invitation" enFenetre
                          titre="Modifier / exporter — vidéo de l'invitation"
                          original={{ id: invitationId, url: outilVideo, fichier: { nom: (String(outilVideo).split('/').pop() || 'video.mp4') } }}
                          enregistrerMiniature={enregistrerMiniatureCapturee} enregistrerVersion={enregistrerVersionExportee}
                          onFermer={() => setOutilVideo('')} onEnregistre={() => setOutilVideo('')} />
            </Suspense>
          </div>
        </div>
      ) : null}
      {confirmation ? (
        <div role="alertdialog" aria-modal="true" data-testid="ed-confirmation"
             style={{ position: 'fixed', inset: 0, zIndex: 10003, background: 'rgba(0,0,0,0.75)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16 }}>
          <div style={{ maxWidth: 420, width: '100%', padding: 18, borderRadius: 16, background: 'rgb(26,10,31)', border: `1px solid ${rgbaP(0.4)}` }}>
            <p style={{ margin: '0 0 14px', fontSize: 15, color: 'rgba(255,255,255,0.95)', lineHeight: 1.45 }}>{confirmation.texte}</p>
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', flexWrap: 'wrap' }}>
              <button type="button" style={btn('contour')} onClick={() => setConfirmation(null)} data-testid="ed-confirmation-annuler">Annuler</button>
              <button type="button" style={btn(confirmation.danger ? 'danger' : 'plein')} onClick={confirmation.relancer} data-testid="ed-confirmation-continuer">Continuer</button>
            </div>
          </div>
        </div>
      ) : null}
    </Cadre>
  );
}

function Cadre({ mobile, onClose, titre, sousTitre, pied, children }) {
  useEffect(() => {
    const surTouche = (e) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', surTouche);
    return () => document.removeEventListener('keydown', surTouche);
  }, [onClose]);
  return (
    <div role="dialog" aria-modal="true" aria-label="Modifier l'invitation" data-testid="editeur-invitation"
         style={{ position: 'fixed', inset: 0, zIndex: 10001, background: 'rgba(0,0,0,0.7)', display: 'flex', justifyContent: 'center',
           alignItems: mobile ? 'stretch' : 'center', padding: mobile ? 0 : 20, boxSizing: 'border-box' }}>
      <div style={{ width: '100%', maxWidth: mobile ? '100%' : 1100, maxHeight: mobile ? '100%' : '92vh', display: 'flex', flexDirection: 'column',
        background: 'rgb(14,6,18)', borderRadius: mobile ? 0 : 18, border: mobile ? 'none' : `1px solid ${rgbaP(0.35)}`, overflow: 'hidden', color: 'rgba(255,255,255,0.96)' }}>
        <header style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '14px 16px', borderBottom: '1px solid rgba(255,255,255,0.08)' }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontWeight: 800, fontSize: 17, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{titre}</div>
            {sousTitre ? <div style={{ fontSize: 12.5, color: 'rgba(255,255,255,0.6)' }}>{sousTitre}</div> : null}
          </div>
          <button type="button" onClick={onClose} aria-label="Fermer" data-testid="ed-fermer"
                  style={{ width: 44, height: 44, borderRadius: 12, background: 'rgba(255,255,255,0.07)', border: 'none', color: 'rgba(255,255,255,0.9)', cursor: 'pointer', display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}>
            <SvgIcon name="close" size={18} />
          </button>
        </header>
        <div style={{ flex: 1, overflowY: 'auto', padding: 16 }}>{children}</div>
        {pied ? <footer style={{ padding: '12px 16px calc(12px + env(safe-area-inset-bottom, 0px))', borderTop: '1px solid rgba(255,255,255,0.08)', background: 'rgb(14,6,18)' }}>{pied}</footer> : null}
      </div>
    </div>
  );
}
