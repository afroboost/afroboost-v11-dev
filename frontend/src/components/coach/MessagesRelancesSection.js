/**
 * V588 — CAMPAGNES → PROSPECTION → MESSAGES & RELANCES. VUE DE PILOTAGE, LECTURE SEULE.
 * V588b — lisible au quotidien : « qui vient de répondre, qui attend un appel,
 * qu'est-ce que j'ai répondu, que dois-je faire ». Liste compacte défilante, recherche,
 * priorités, et un panneau de détail (plein écran sur mobile) où le PARTENAIRE parle à
 * GAUCHE et AFROBOOST à DROITE.
 *
 * CE QUE L'ÉCRAN LIT (uniquement des GET existants) :
 *   GET /prospect-campaigns (+ détail)   → actions : textes approuvés, envois, échéances, annulations
 *   GET /prospect-inbound                → conversations : réponses, non lus, état commercial, réponse Afroboost
 *   GET /partner-prospects (paginé)      → fiches : statut, ville, catégorie, contact (recherche)
 *   GET /feature-flags                   → interrupteurs de relance (affichés, jamais modifiés)
 *   GET /prospect-inbound/{id}/notes     → notes, à l'ouverture d'un dossier seulement
 *   GET /prospect-inbound/{id}/brouillon → analyse IA DÉJÀ enregistrée (résumé, prochaine action)
 *
 * CE QU'IL NE FAIT PAS : aucun POST/PATCH/PUT, aucun envoi, aucun marquage « lu ».
 * « Nouveau » = `non_lues` du serveur (le système lu/non-lu existant). Le bouton
 * « Ouvrir la conversation » passe par la porte EXISTANTE (`prospectionIntention.poser`) :
 * c'est l'écran Conversations partenaires, inchangé, qui applique sa propre lecture.
 *
 * ⚠️ Les textes J0/J+3/J+7 sont ceux de l'ACTION (approuvés), jamais `j3_message` /
 * `j7_message` de la fiche prospect (brouillons non approuvés).
 *
 * ANTI-BOUCLE (V305) : dépendances primitives ; caches par identifiant, `prev` renvoyé
 * quand rien ne change.
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import axios from 'axios';
import SvgIcon from '../SvgIcon';
import useChargement, { SECTION } from '../../hooks/useChargement';
import { SectionErreur } from '../ui/EtatChargement';
import { poser as ouvrirConversation } from '../../utils/prospectionIntention';
import {
  ETATS, LIBELLES_ETAT, FILTRES, FILTRES_CANAL, SUIVI_MANUEL_INDISPONIBLE,
  lignesRelances, compteursRelances, filtrerRelances, trierRelances, chronologie,
  dateCourte, libelleCanal, libelleStatutProspect, nomCampagne, ilYa, texteUtile,
  dernierEvenement, instant,
} from '../../utils/messagesRelances';

const PRIMAIRE = 'var(--primary-color, #D91CD2)';
const RGB = 'var(--primary-rgb, 217, 28, 210)';
const PRIMAIRE_LISIBLE = 'color-mix(in srgb, var(--primary-color, #D91CD2) 80%, white)';
const TEXTE = '#fff';
const DOUX = 'rgba(255,255,255,0.65)';
const BORD = 'rgba(255,255,255,0.12)';
const FOND_PANNEAU = 'rgb(14,10,16)';
const PAGES_PROSPECTS_MAX = 10;
/* Au-dessus des boutons fixes du tableau de bord (« Vue Visiteur », « Déconnexion »,
   z-index 9999) : le panneau doit les couvrir, sinon on clique dessus par erreur. */

/* Tons sémantiques (jamais la couleur de marque, qui reste au coach). */
const AMBRE = 'rgb(252,211,77)';
const VERT = 'rgb(134,239,172)';
const ROUGE = 'rgb(252,165,165)';
const BLEU = 'rgb(147,197,253)';
const TONS = {
  en_retard: { fond: 'rgba(245,158,11,0.18)', bord: 'rgba(245,158,11,0.5)', texte: AMBRE },
  repondu: { fond: 'rgba(34,197,94,0.18)', bord: 'rgba(34,197,94,0.45)', texte: VERT },
  refus: { fond: 'rgba(239,68,68,0.18)', bord: 'rgba(239,68,68,0.45)', texte: ROUGE },
  rebond: { fond: 'rgba(239,68,68,0.14)', bord: 'rgba(239,68,68,0.4)', texte: ROUGE },
  stoppe: { fond: 'rgba(255,255,255,0.07)', bord: 'rgba(255,255,255,0.2)', texte: 'rgba(255,255,255,0.7)' },
  manuel: { fond: 'rgba(255,255,255,0.06)', bord: 'rgba(255,255,255,0.26)', texte: 'rgba(255,255,255,0.85)' },
  envoye: { fond: `rgba(${RGB}, 0.14)`, bord: `rgba(${RGB}, 0.45)`, texte: PRIMAIRE_LISIBLE },
  prevu: { fond: 'rgba(255,255,255,0.06)', bord: `rgba(${RGB}, 0.4)`, texte: TEXTE },
  a_envoyer: { fond: 'rgba(255,255,255,0.06)', bord: `rgba(${RGB}, 0.4)`, texte: TEXTE },
  sans_objet: { fond: 'transparent', bord: 'rgba(255,255,255,0.10)', texte: 'rgba(255,255,255,0.45)' },
};

function Pastille({ etat, children, testid }) {
  const t = TONS[etat] || TONS.sans_objet;
  return (
    <span data-testid={testid} style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', padding: '2px 8px',
      borderRadius: '999px', fontSize: '11px', fontWeight: 600, whiteSpace: 'nowrap',
      background: t.fond, border: `1px solid ${t.bord}`, color: t.texte }}>
      {children || LIBELLES_ETAT[etat] || etat}
    </span>
  );
}

/* NOUVEAU (couleur du coach, point plein) ≠ APPEL À FAIRE (bleu, téléphone) ≠ RÉPONSE ATTENDUE (ambre).
   V588c — pas de badge « URGENT » : aucune donnée existante ne prouve une urgence (lot séparé). */
function BadgeNouveau({ n }) {
  return (
    <span data-testid="mr-badge-nouveau" style={{ display: 'inline-flex', alignItems: 'center', gap: '5px', padding: '2px 8px',
      borderRadius: '999px', fontSize: '11px', fontWeight: 800, letterSpacing: '0.03em', whiteSpace: 'nowrap',
      background: PRIMAIRE, color: '#fff' }}>
      <span aria-hidden="true" style={{ width: '7px', height: '7px', borderRadius: '50%', background: '#fff' }} />
      NOUVEAU{n > 1 ? ` · ${n}` : ''}
    </span>
  );
}
function BadgeAppel() {
  return (
    <span data-testid="mr-badge-appel" style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', padding: '2px 8px',
      borderRadius: '999px', fontSize: '11px', fontWeight: 700, whiteSpace: 'nowrap',
      background: 'rgba(59,130,246,0.18)', border: '1px solid rgba(96,165,250,0.6)', color: BLEU }}>
      <SvgIcon name="phone" size={11} /> Appel à faire
    </span>
  );
}
function BadgeAttendue() {
  return (
    <span data-testid="mr-badge-attendue" style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', padding: '2px 8px',
      borderRadius: '999px', fontSize: '11px', fontWeight: 700, whiteSpace: 'nowrap',
      background: 'rgba(245,158,11,0.16)', border: '1px solid rgba(245,158,11,0.55)', color: AMBRE }}>
      <SvgIcon name="clock" size={11} /> Réponse attendue
    </span>
  );
}

function Badges({ l }) {
  return (
    <>
      {l.appel && <BadgeAppel />}
      {l.nonLues > 0 && <BadgeNouveau n={l.nonLues} />}
      {l.reponseAttendue && !l.appel && <BadgeAttendue />}
    </>
  );
}

function Tuile({ libelle, valeur, actif, onClick, ton, testid }) {
  const couleur = ton === 'bleu' ? BLEU : ton === 'rouge' ? ROUGE : ton === 'ambre' ? AMBRE : ton === 'marque' ? PRIMAIRE_LISIBLE : TEXTE;
  const fort = !!ton && valeur !== '—' && Number(valeur) > 0;
  return (
    <button type="button" onClick={onClick} data-testid={testid} aria-pressed={!!actif}
      style={{ flex: '1 1 104px', minWidth: 0, textAlign: 'left', padding: '8px 10px', borderRadius: '10px',
        cursor: onClick ? 'pointer' : 'default', color: TEXTE,
        border: `1px solid ${actif ? PRIMAIRE : 'rgba(255,255,255,0.10)'}`,
        background: actif ? `rgba(${RGB}, 0.16)` : 'rgba(255,255,255,0.04)' }}>
      <div style={{ fontSize: '11px', color: DOUX, lineHeight: 1.25 }}>{libelle}</div>
      <div style={{ fontSize: '19px', fontWeight: 700, color: fort ? couleur : TEXTE }}>{valeur}</div>
    </button>
  );
}

function Puce({ actif, onClick, children, testid }) {
  return (
    <button type="button" onClick={onClick} data-testid={testid} aria-pressed={actif}
      style={{ padding: '5px 10px', borderRadius: '999px', fontSize: '12px', cursor: 'pointer', color: TEXTE,
        fontWeight: actif ? 700 : 500, whiteSpace: 'nowrap', flexShrink: 0,
        border: `1px solid ${actif ? `rgba(${RGB}, 0.7)` : 'rgba(255,255,255,0.14)'}`,
        background: actif ? `rgba(${RGB}, 0.26)` : 'transparent' }}>
      {children}
    </button>
  );
}

/* « 05/09/2026 » seul quand c'est ancien, « 07/10/2026 · il y a 2 h » quand c'est récent. */
function quandLisible(iso, maintenant) {
  const rel = ilYa(iso, maintenant);
  return rel.indexOf('le ') === 0 ? dateCourte(iso) : `${dateCourte(iso)} · ${rel}`;
}

function dateOuRetard(l) {
  if (l.etat === ETATS.EN_RETARD) {
    const e = l.j3.etat === ETATS.EN_RETARD ? l.j3 : l.j7;
    return `en retard de ${e.retard_jours} j`;
  }
  return l.prochaineDate ? dateCourte(l.prochaineDate) : '';
}

/* ---------------- LA CARTE COMPACTE ---------------- */
function Carte({ l, maintenant, onOuvrir, active }) {
  const ev = l.dernierMessageLe ? { titre: 'Réponse reçue', quand: l.dernierMessageLe } : dernierEvenement(l);
  const evTexte = l.etat === ETATS.MANUEL ? SUIVI_MANUEL_INDISPONIBLE
    : ev ? `${ev.titre} ${ilYa(ev.quand, maintenant)}` : '—';
  const signal = l.nonLues > 0 || l.appel || l.reponseAttendue;
  const date = dateOuRetard(l);
  return (
    <li data-testid="mr-ligne" data-etat={l.etat} data-nouveau={l.nonLues > 0 ? 'oui' : 'non'}
      data-appel={l.appel ? 'oui' : 'non'} data-attendue={l.reponseAttendue ? 'oui' : 'non'}>
      <button type="button" onClick={onOuvrir} data-testid="mr-ligne-entete" aria-expanded={active}
        style={{ width: '100%', textAlign: 'left', cursor: 'pointer', color: TEXTE, padding: '9px 11px',
          borderRadius: '10px', display: 'flex', flexDirection: 'column', gap: '3px',
          border: `1px solid ${active ? `rgba(${RGB}, 0.6)` : l.appel ? 'rgba(96,165,250,0.5)' : l.nonLues ? `rgba(${RGB}, 0.5)` : BORD}`,
          background: l.nonLues > 0 ? `rgba(${RGB}, 0.10)` : l.appel ? 'rgba(59,130,246,0.07)' : 'rgba(255,255,255,0.03)' }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '8px' }}>
          <span style={{ fontSize: '14px', fontWeight: l.nonLues > 0 || l.appel ? 800 : 650, minWidth: 0, overflowWrap: 'anywhere' }}>
            {l.organisation}
          </span>
          <span style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'flex-end', gap: '4px', flexShrink: 0, maxWidth: '60%' }}>
            <Badges l={l} />
            {!signal && <Pastille etat={l.etat} testid="mr-etat">{l.etat === ETATS.EN_RETARD ? 'J+3 en retard' : undefined}</Pastille>}
          </span>
        </div>
        {signal ? (
          <>
            <div style={{ fontSize: '12px', color: DOUX }}>{libelleCanal(l.canal)} · {LIBELLES_ETAT[l.etat]}</div>
            {l.extrait && (
              <div data-testid="mr-extrait" style={{ fontSize: '12.5px', color: TEXTE, fontStyle: 'italic', overflowWrap: 'anywhere' }}>
                « {l.extrait} »
              </div>
            )}
            <div style={{ fontSize: '12px', color: DOUX }}>{evTexte}</div>
          </>
        ) : (
          /* Sans signal : canal et dernier événement sur UNE ligne (carte plus courte). */
          <div style={{ fontSize: '12px', color: DOUX }}>{libelleCanal(l.canal)} · {evTexte}</div>
        )}
        <div style={{ fontSize: '12px', color: DOUX }}>
          Prochaine action : <span style={{ color: TEXTE, fontWeight: 600 }}>{l.prochaineAction}</span>
          {date ? <span style={{ color: l.etat === ETATS.EN_RETARD ? AMBRE : DOUX }}> · {date}</span> : null}
        </div>
      </button>
    </li>
  );
}

/* ---------------- LE FIL : PARTENAIRE À GAUCHE, AFROBOOST À DROITE ---------------- */
function Bulle({ cote, titre, quand, objet, corps, pied, testid }) {
  const droite = cote === 'afroboost';
  return (
    <div data-testid={testid} data-cote={cote} style={{ display: 'flex', justifyContent: droite ? 'flex-end' : 'flex-start' }}>
      <div style={{ maxWidth: '86%', minWidth: 0, padding: '9px 11px', borderRadius: droite ? '14px 14px 4px 14px' : '14px 14px 14px 4px',
        background: droite ? `rgba(${RGB}, 0.22)` : 'rgba(255,255,255,0.09)',
        border: `1px solid ${droite ? `rgba(${RGB}, 0.55)` : 'rgba(255,255,255,0.2)'}` }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: '10px', fontSize: '10.5px',
          letterSpacing: '0.04em', textTransform: 'uppercase', color: droite ? PRIMAIRE_LISIBLE : 'rgba(255,255,255,0.72)' }}>
          <span style={{ fontWeight: 800 }}>{droite ? 'Afroboost' : 'Partenaire'}{titre ? ` · ${titre}` : ''}</span>
          <span style={{ textTransform: 'none', letterSpacing: 0, color: DOUX, whiteSpace: 'nowrap' }}>{dateCourte(quand)}</span>
        </div>
        {objet && <div style={{ fontSize: '12px', color: DOUX, marginTop: '3px', overflowWrap: 'anywhere' }}>{objet}</div>}
        {corps && <div style={{ fontSize: '13px', lineHeight: 1.5, color: TEXTE, whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', marginTop: '5px' }}>{corps}</div>}
        {pied}
      </div>
    </div>
  );
}

function EvenementSysteme({ ev }) {
  const couleur = ev.genre === 'stop' ? ROUGE : ev.genre === 'retard' ? AMBRE : ev.genre === 'note' ? TEXTE : DOUX;
  return (
    <div data-testid="mr-evenement" data-genre={ev.genre} style={{ display: 'flex', justifyContent: 'center' }}>
      <div style={{ maxWidth: '92%', textAlign: 'center', fontSize: '11.5px', color: couleur, padding: ev.genre === 'note' ? '6px 10px' : '2px 6px',
        borderRadius: '8px', border: ev.genre === 'note' ? '1px dashed rgba(255,255,255,0.28)' : 'none', overflowWrap: 'anywhere' }}>
        <span style={{ color: DOUX }}>{dateCourte(ev.quand)} · </span>
        <strong>{ev.titre}</strong>{ev.detail ? ` — ${ev.detail}` : ''}
      </div>
    </div>
  );
}

/** Le fil assemblé à partir des données existantes, trié par date. */
function filDe(l, notes, brouillon) {
  const a = l.action || {};
  const conv = l.conversation;
  const items = [];
  if (a.sent_at) {
    items.push({ t: instant(a.sent_at), rendu: () => (
      <Bulle key="j0" testid="mr-bulle-afroboost" cote="afroboost" titre="Message J0" quand={a.sent_at}
        objet={l.j0.objet} corps={l.j0.message} />) });
  }
  ['j3', 'j7'].forEach((e) => {
    if (a[`${e}_sent_at`]) {
      items.push({ t: instant(a[`${e}_sent_at`]), rendu: () => (
        <Bulle key={e} testid="mr-bulle-afroboost" cote="afroboost" titre={e === 'j3' ? 'Relance J+3' : 'Relance J+7'}
          quand={a[`${e}_sent_at`]} objet={l[e].objet} corps={l[e].message} />) });
    }
  });
  ((conv && conv.messages_recus) || []).forEach((m, i) => {
    if (!m) return;
    items.push({ t: instant(m.received_at), rendu: () => (
      <Bulle key={`p${i}`} testid="mr-bulle-partenaire" cote="partenaire" titre={m.read_at ? '' : 'non lu'} quand={m.received_at}
        objet={m.subject} corps={texteUtile(m.body_text) || '(message sans texte)'}
        pied={m.from_email ? <div style={{ fontSize: '11px', color: DOUX, marginTop: '5px' }}>{m.from_email}</div> : null} />) });
  });
  const rep = conv && conv.derniere_reponse_afroboost;
  if (rep && rep.sent_at) {
    /* Le TEXTE exact envoyé n'est pas exposé par le serveur : on montre le brouillon
       validé seulement s'il a été écrit AVANT l'envoi, et on le dit. */
    const b = brouillon || null;
    const ecritLe = b ? instant(b.edite_le || b.updated_at || b.genere_le) : NaN;
    const texteBrouillon = b && Number.isFinite(ecritLe) && ecritLe <= instant(rep.sent_at) ? (b.reponse_proposee || '') : '';
    items.push({ t: instant(rep.sent_at), rendu: () => (
      <Bulle key="rep" testid="mr-bulle-afroboost" cote="afroboost" titre="Réponse" quand={rep.sent_at} objet={rep.objet}
        corps={texteBrouillon}
        pied={<div style={{ fontSize: '11px', color: DOUX, marginTop: '5px' }}>
          {texteBrouillon ? 'Texte du brouillon validé avant l\'envoi.' : 'Réponse envoyée (son texte n\'est pas conservé ici).'}
        </div>} />) });
  }
  chronologie(l, notes || [])
    .filter((ev) => !/^J0 envoyé|^J\+[37] envoyé|^Réponse reçue|^Réponse envoyée/.test(ev.titre))
    .forEach((ev, i) => items.push({ t: instant(ev.quand), rendu: () => <EvenementSysteme key={`s${i}`} ev={ev} /> }));
  return items.filter((x) => Number.isFinite(x.t)).sort((x, y) => x.t - y.t);
}

function DetailEtape({ e }) {
  const nom = e.etape === 'j3' ? 'Relance J+3' : e.etape === 'j7' ? 'Relance J+7' : 'Message initial J0';
  return (
    <details data-testid={`mr-etape-${e.etape}`} style={{ border: `1px solid ${BORD}`, borderRadius: '10px', padding: '8px 10px', background: 'rgba(0,0,0,0.22)' }}>
      <summary style={{ cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '8px', flexWrap: 'wrap', listStyle: 'none' }}>
        <strong style={{ fontSize: '13px' }}>{nom}</strong>
        <span style={{ display: 'flex', gap: '6px', alignItems: 'center', fontSize: '11px', color: DOUX }}>
          {e.date_envoi ? `envoyé ${dateCourte(e.date_envoi)}` : e.date_prevue ? `prévu ${dateCourte(e.date_prevue)}` : ''}
          <Pastille etat={e.etat}>{e.etat === ETATS.EN_RETARD ? `En retard · ${e.retard_jours} j` : undefined}</Pastille>
        </span>
      </summary>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', marginTop: '8px', fontSize: '12.5px' }}>
        <div style={{ color: DOUX }}>Canal : <span style={{ color: TEXTE }}>{libelleCanal(e.canal)}</span>
          {' · '}Prévu : <span style={{ color: TEXTE }}>{dateCourte(e.date_prevue)}</span>
          {' · '}Envoyé : <span style={{ color: TEXTE }}>{dateCourte(e.date_envoi)}</span>
          {e.date_annulation ? <> · Annulé : <span style={{ color: TEXTE }}>{dateCourte(e.date_annulation)}</span></> : null}</div>
        {e.motif && <div style={{ color: DOUX }}>{e.motif}</div>}
        {e.objet && <div style={{ color: DOUX }}>Objet : <span style={{ color: TEXTE }}>{e.objet}</span></div>}
        {(e.message || '').trim()
          ? <div data-testid={`mr-message-${e.etape}`} style={{ whiteSpace: 'pre-wrap', lineHeight: 1.5, color: TEXTE, overflowWrap: 'anywhere' }}>{e.message}</div>
          : <div style={{ color: DOUX }}>Aucun texte approuvé pour cette étape.</div>}
      </div>
    </details>
  );
}

const ETIQUETTE = { fontSize: '10.5px', color: DOUX, textTransform: 'uppercase', letterSpacing: '0.04em' };

/* ---------------- LE PANNEAU (latéral sur ordinateur, plein écran sur mobile) ---------------- */
function Panneau({ l, maintenant, notes, notesEnCours, brouillon, onFermer }) {
  useEffect(() => {
    const surTouche = (e) => { if (e.key === 'Escape') onFermer(); };
    window.addEventListener('keydown', surTouche);
    const avant = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => { window.removeEventListener('keydown', surTouche); document.body.style.overflow = avant; };
  }, [onFermer]);
  const fil = useMemo(() => filDe(l, notes, brouillon), [l, notes, brouillon]);
  const ids = (l.conversation && l.conversation.message_ids) || [];
  const dossier = ids[ids.length - 1] || '';
  const analyse = brouillon && (brouillon.prochaine_action || brouillon.resume) ? brouillon : null;

  /* Rendu dans <body> (portail) : un parent à filtre/transform ne peut pas piéger le
     panneau, qui reste un vrai plein écran sur mobile. */
  return createPortal(
    <div data-testid="mr-panneau" role="dialog" aria-modal="true" aria-label={`Dossier ${l.organisation}`}
      style={{ position: 'fixed', inset: 0, zIndex: 10050, display: 'flex', justifyContent: 'flex-end' }}>
      <div onClick={onFermer} data-testid="mr-panneau-fond" style={{ position: 'absolute', inset: 0, background: 'rgba(0,0,0,0.55)' }} />
      <aside style={{ position: 'relative', width: 'min(620px, 100vw)', height: '100%', background: FOND_PANNEAU, color: TEXTE,
        borderLeft: `1px solid rgba(${RGB}, 0.35)`, display: 'flex', flexDirection: 'column', boxShadow: '-12px 0 40px rgba(0,0,0,0.5)' }}>
        <header style={{ padding: '10px 14px 12px', borderBottom: `1px solid ${BORD}`, display: 'flex', flexDirection: 'column', gap: '7px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <button type="button" onClick={onFermer} data-testid="mr-retour"
              style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', padding: '7px 12px', borderRadius: '999px',
                border: `1px solid ${BORD}`, background: 'rgba(255,255,255,0.06)', color: TEXTE, cursor: 'pointer', fontSize: '13px', fontWeight: 600 }}>
              <SvgIcon name="arrowLeft" size={14} /> Retour à la liste
            </button>
            <div style={{ flex: 1 }} />
            <button type="button" onClick={onFermer} aria-label="Fermer" data-testid="mr-fermer"
              style={{ display: 'inline-flex', padding: '7px', borderRadius: '999px', border: `1px solid ${BORD}`, background: 'transparent', color: TEXTE, cursor: 'pointer' }}>
              <SvgIcon name="x" size={14} />
            </button>
          </div>
          <div style={{ fontSize: '17px', fontWeight: 800, overflowWrap: 'anywhere' }}>{l.organisation}</div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '5px', alignItems: 'center' }}>
            <Badges l={l} />
            <Pastille etat={l.etat}>{l.etat === ETATS.EN_RETARD ? 'J+3 en retard' : undefined}</Pastille>
            <span style={{ fontSize: '12px', color: DOUX }}>
              {[libelleCanal(l.canal), l.statutProspect ? `Fiche : ${libelleStatutProspect(l.statutProspect)}` : '', l.reference].filter(Boolean).join(' · ')}
            </span>
          </div>
          <div style={{ fontSize: '13px' }}>
            <span style={{ color: DOUX }}>Prochaine action : </span><strong data-testid="mr-panneau-action">{l.prochaineAction}</strong>
            {dateOuRetard(l) ? <span style={{ color: DOUX }}> · {dateOuRetard(l)}</span> : null}
          </div>
        </header>

        <div data-testid="mr-panneau-corps" style={{ flex: 1, overflowY: 'auto', overscrollBehavior: 'contain', padding: '12px 14px 28px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
          {l.etat === ETATS.MANUEL && (
            <div data-testid="mr-suivi-manuel" style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '12.5px',
              padding: '8px 10px', borderRadius: '8px', border: '1px dashed rgba(255,255,255,0.3)' }}>
              <SvgIcon name="info" size={14} />
              <span>Suivi manuel ({libelleCanal(l.canal)}) — {SUIVI_MANUEL_INDISPONIBLE.toLowerCase()}. Aucun envoi n'est tracé : rien n'est supposé envoyé.</span>
            </div>
          )}

          {l.conversation && (
            <div data-testid="mr-resume-echanges" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))', gap: '8px' }}>
              <div style={{ padding: '8px 10px', borderRadius: '10px', background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.16)' }}>
                <div style={ETIQUETTE}>Dernier message partenaire</div>
                <div style={{ fontSize: '13px', fontWeight: 600 }}>{l.dernierMessageLe ? quandLisible(l.dernierMessageLe, maintenant) : '—'}</div>
              </div>
              <div style={{ padding: '8px 10px', borderRadius: '10px', background: `rgba(${RGB}, 0.10)`, border: `1px solid rgba(${RGB}, 0.35)` }}>
                <div style={ETIQUETTE}>Dernière réponse Afroboost</div>
                <div data-testid="mr-derniere-afroboost" style={{ fontSize: '13px', fontWeight: 600, color: l.reponseAttendue ? AMBRE : TEXTE }}>
                  {l.derniereReponseAfroboostLe ? dateCourte(l.derniereReponseAfroboostLe) : 'Aucune'}
                  {l.reponseAttendue ? ' · Réponse attendue' : ''}
                </div>
              </div>
            </div>
          )}

          {analyse && (
            <div data-testid="mr-analyse-ia" style={{ fontSize: '12.5px', padding: '8px 10px', borderRadius: '10px', border: `1px solid ${BORD}`, background: 'rgba(255,255,255,0.03)' }}>
              <div style={{ ...ETIQUETTE, marginBottom: '3px' }}>Analyse IA enregistrée</div>
              {analyse.resume && <div style={{ color: TEXTE }}>{analyse.resume}</div>}
              {analyse.prochaine_action && <div style={{ color: DOUX, marginTop: '3px' }}>Suggestion : <span style={{ color: TEXTE }}>{analyse.prochaine_action}</span></div>}
            </div>
          )}

          {dossier && (
            <button type="button" data-testid="mr-ouvrir-conversation" onClick={() => { onFermer(); ouvrirConversation(dossier); }}
              style={{ alignSelf: 'flex-start', display: 'inline-flex', alignItems: 'center', gap: '6px', padding: '7px 12px', borderRadius: '999px',
                border: `1px solid rgba(${RGB}, 0.6)`, background: `rgba(${RGB}, 0.18)`, color: TEXTE, cursor: 'pointer', fontSize: '12.5px', fontWeight: 600 }}>
              <SvgIcon name="messageCircle" size={13} /> Ouvrir la conversation pour répondre
            </button>
          )}

          <section data-testid="mr-fil" style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            <div style={{ ...ETIQUETTE, fontSize: '12px', fontWeight: 700 }}>Historique</div>
            {fil.length === 0 && <div style={{ fontSize: '12.5px', color: DOUX }}>Aucun échange enregistré.</div>}
            {fil.map((x) => x.rendu())}
            {notesEnCours && <div style={{ fontSize: '11px', color: DOUX, textAlign: 'center' }}>Chargement des notes…</div>}
          </section>

          <section style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            <div style={{ ...ETIQUETTE, fontSize: '12px', fontWeight: 700 }}>Séquence automatique (textes approuvés)</div>
            <DetailEtape e={l.j0} />
            <DetailEtape e={l.j3} />
            <DetailEtape e={l.j7} />
          </section>
        </div>
      </aside>
    </div>,
    document.body,
  );
}

async function lireProspects(base) {
  const tous = [];
  for (let page = 0; page < PAGES_PROSPECTS_MAX; page += 1) {
    const rep = await axios.get(`${base}/partner-prospects`, { params: { limit: 50, offset: page * 50 } });
    const d = (rep && rep.data) || {};
    const lot = Array.isArray(d.prospects) ? d.prospects : [];
    tous.push(...lot);
    if (lot.length < 50 || tous.length >= (d.total || 0)) break;
  }
  return { prospects: tous };
}

async function lireCampagnes(base) {
  const rep = await axios.get(`${base}/prospect-campaigns`);
  const liste = ((rep && rep.data && rep.data.campaigns) || []).slice(0, 5);
  const details = [];
  for (const c of liste) {
    const d = await axios.get(`${base}/prospect-campaigns/${encodeURIComponent(c.id)}`);
    if (d && d.data && d.data.campaign) details.push({ campaign: d.data.campaign, actions: d.data.actions || [] });
  }
  return { campagnes: details };
}

/* Lecture GET à la demande, mise en cache par identifiant (jamais relue deux fois). */
function useLectureParId(base, id, chemin, extraire) {
  const [cache, setCache] = useState({});
  const [enCours, setEnCours] = useState('');
  const connu = !id || Object.prototype.hasOwnProperty.call(cache, id);
  useEffect(() => {
    if (connu) return undefined;
    let vivant = true;
    setEnCours(id);
    axios.get(`${base}/prospect-inbound/${encodeURIComponent(id)}/${chemin}`)
      .then((r) => extraire(r && r.data))
      .catch(() => null)
      .then((val) => {
        if (!vivant) return;
        setCache((prev) => (Object.prototype.hasOwnProperty.call(prev, id) ? prev : { ...prev, [id]: val }));
        setEnCours((prev) => (prev === id ? '' : prev));
      });
    return () => { vivant = false; };
    // `extraire` est une fonction de module, stable : volontairement hors dépendances.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [base, id, chemin, connu]);
  return { valeur: id ? cache[id] : undefined, enCours: !!id && enCours === id };
}
const extraireNotes = (d) => (d && Array.isArray(d.notes) ? d.notes : []);
const extraireBrouillon = (d) => (d && d.brouillon) || null;

export default function MessagesRelancesSection({ API, actif }) {
  const base = API || '/api';
  const [filtre, setFiltre] = useState('tous');
  const [canal, setCanal] = useState('tous');
  const [recherche, setRecherche] = useState('');
  const [campagneId, setCampagneId] = useState('');
  const [ouverteId, setOuverteId] = useState('');

  const chargement = useChargement({
    campagnes: { url: `${base}/prospect-campaigns`, signature: true, appel: () => lireCampagnes(base), extraire: (d) => d },
    reponses: { url: `${base}/prospect-inbound`, signature: true,
      appel: async () => { const r = await axios.get(`${base}/prospect-inbound`, { params: { limit: 100 } }); return r && r.data ? r.data : null; },
      extraire: (d) => d },
    prospects: { url: `${base}/partner-prospects`, signature: true, appel: () => lireProspects(base), extraire: (d) => d },
    drapeaux: { url: `${base}/feature-flags`, signature: true,
      appel: async () => { const r = await axios.get(`${base}/feature-flags`); return r && r.data ? r.data : null; },
      extraire: (d) => d },
  }, { deps: [base], actif: actif !== false });

  const sC = chargement.sections.campagnes;
  const sR = chargement.sections.reponses;
  const sP = chargement.sections.prospects;
  const sD = chargement.sections.drapeaux;
  const campagnes = (sC && sC.etat === SECTION.OK && sC.donnees && sC.donnees.campagnes) || [];
  const campagne = campagnes.find((c) => c.campaign.id === campagneId) || campagnes[0] || null;
  /* Tableaux dérivés des DONNÉES (référence stable), jamais recréés à chaque rendu. */
  const donneesR = sR && sR.etat === SECTION.OK ? sR.donnees : null;
  const donneesP = sP && sP.etat === SECTION.OK ? sP.donnees : null;
  const conversations = useMemo(() => (donneesR && donneesR.conversations) || [], [donneesR]);
  const prospects = useMemo(() => (donneesP && donneesP.prospects) || [], [donneesP]);
  const drapeaux = (sD && sD.etat === SECTION.OK && sD.donnees) ? (sD.donnees.flags || sD.donnees) : null;
  const relancesOuvertes = !!(drapeaux && drapeaux.P3_RELANCE_ENABLED && drapeaux.P3_RELANCE_ENVOI_REEL);

  /* « maintenant » figé à la minute : l'écran ne se recalcule pas en continu. */
  const minute = Math.floor(Date.now() / 60000);
  const maintenant = minute * 60000;
  const lignes = useMemo(() => (campagne
    ? trierRelances(lignesRelances(campagne.actions, campagne.campaign, conversations, prospects, minute * 60000))
    : []), [campagne, conversations, prospects, minute]);
  const compteurs = useMemo(() => compteursRelances(lignes), [lignes]);
  const visibles = useMemo(() => filtrerRelances(lignes, filtre, canal, recherche), [lignes, filtre, canal, recherche]);

  const ligneOuverte = lignes.find((l) => l.id === ouverteId) || null;
  const ids = (ligneOuverte && ligneOuverte.conversation && ligneOuverte.conversation.message_ids) || [];
  const notes = useLectureParId(base, ids[0] || '', 'notes', extraireNotes);
  const brouillon = useLectureParId(base, ids[ids.length - 1] || '', 'brouillon', extraireBrouillon);

  /* Une tuile active se désactive au second clic (retour à « Tous »). */
  const basculerFiltre = (f) => setFiltre((prev) => (prev === f ? 'tous' : f));
  const fermer = useCallback(() => setOuverteId(''), []);

  const enChargement = [sC, sR, sP].some((s) => !s || s.etat === SECTION.CHARGEMENT || s.etat === SECTION.ATTENTE);
  const erreur = [['campagnes', sC, 'les campagnes'], ['reponses', sR, 'les réponses'], ['prospects', sP, 'les prospects']]
    .find(([, s]) => s && (s.etat === SECTION.ERREUR || s.etat === SECTION.SESSION));
  const v = (n) => (enChargement ? '—' : n);
  const pluriel = (n, s, p) => (n > 1 ? p : s);

  return (
    <div data-testid="messages-relances" style={{ color: TEXTE, display: 'flex', flexDirection: 'column', gap: '10px' }}>
      <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between', gap: '8px' }}>
        <div style={{ minWidth: 0 }}>
          <h3 style={{ margin: 0, fontSize: '18px', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '8px' }}>
            <SvgIcon name="send" size={16} /> Messages & relances
          </h3>
          <div style={{ fontSize: '12px', color: DOUX }}>
            Lecture seule{campagne ? <> · campagne <strong style={{ color: TEXTE }}>{nomCampagne(campagne.campaign)}</strong></> : null}
          </div>
        </div>
        <span data-testid="mr-interrupteurs" style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', fontSize: '11.5px',
          padding: '4px 10px', borderRadius: '999px', border: `1px solid ${BORD}`, color: TEXTE }}>
          <SvgIcon name="lock" size={12} />
          {drapeaux === null ? 'Relances auto : état inconnu' : relancesOuvertes ? 'Relances auto : OUVERTES' : 'Relances auto : fermées'}
        </span>
      </div>

      {erreur && <SectionErreur motif={erreur[1].motif} quoi={erreur[2]} compact
        onReessayer={() => chargement.reessayer(erreur[0])} data-testid="mr-erreur" />}

      {campagnes.length > 1 && (
        <label style={{ fontSize: '12px', color: DOUX, display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
          Campagne
          <select value={campagne ? campagne.campaign.id : ''} onChange={(e) => { setCampagneId(e.target.value); setOuverteId(''); }}
            style={{ background: 'rgba(0,0,0,0.35)', color: TEXTE, border: `1px solid ${BORD}`, borderRadius: '8px', padding: '6px 8px' }}>
            {campagnes.map((c) => <option key={c.campaign.id} value={c.campaign.id}>{nomCampagne(c.campaign)}</option>)}
          </select>
        </label>
      )}

      <div data-testid="mr-compteurs" style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
        <Tuile testid="mr-c-a-traiter" libelle="À traiter" valeur={v(compteurs.aTraiter)} ton="marque" actif={filtre === 'a_traiter'} onClick={() => basculerFiltre('a_traiter')} />
        <Tuile testid="mr-c-nouveaux" libelle="Nouveaux messages" valeur={v(compteurs.nouveaux)} ton="marque" actif={filtre === 'nouveaux'} onClick={() => basculerFiltre('nouveaux')} />
        <Tuile testid="mr-c-appels" libelle="Appels à faire" valeur={v(compteurs.appels)} ton="bleu" actif={filtre === 'appels'} onClick={() => basculerFiltre('appels')} />
        <Tuile testid="mr-c-j3-retard" libelle="J+3 en retard" valeur={v(compteurs.j3EnRetard)} ton="ambre" actif={filtre === 'en_retard'} onClick={() => basculerFiltre('en_retard')} />
        <Tuile testid="mr-c-reponses" libelle="Réponses" valeur={v(compteurs.reponses)} actif={filtre === 'repondus'} onClick={() => basculerFiltre('repondus')} />
        <Tuile testid="mr-c-stoppes" libelle="Stoppés" valeur={v(compteurs.stoppes)} actif={filtre === 'stoppes'} onClick={() => basculerFiltre('stoppes')} />
      </div>
      <div data-testid="mr-stats" style={{ fontSize: '11.5px', color: DOUX }}>
        {enChargement ? '—' : `${compteurs.total} destinataires · ${compteurs.j0Envoyes} J0 envoyés · J+3 à venir ${compteurs.j3AVenir} · J+7 à venir ${compteurs.j7AVenir} · ${compteurs.manuel} à faire manuellement · ${compteurs.reponsesAttendues} ${pluriel(compteurs.reponsesAttendues, 'réponse attendue', 'réponses attendues')}`}
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
        <div style={{ position: 'relative' }}>
          <span style={{ position: 'absolute', left: '10px', top: '50%', transform: 'translateY(-50%)', color: DOUX, display: 'inline-flex' }}>
            <SvgIcon name="search" size={14} />
          </span>
          <input type="search" value={recherche} onChange={(e) => setRecherche(e.target.value)} data-testid="mr-recherche"
            placeholder="Rechercher : organisation, ville, catégorie, nom, e-mail, statut…" aria-label="Rechercher"
            style={{ width: '100%', boxSizing: 'border-box', padding: '8px 10px 8px 32px', borderRadius: '10px', fontSize: '13px',
              background: 'rgba(0,0,0,0.35)', color: TEXTE, border: `1px solid ${BORD}`, outline: 'none' }} />
        </div>
        <div role="group" aria-label="Filtrer par état" style={{ display: 'flex', gap: '5px', overflowX: 'auto', paddingBottom: '2px' }}>
          {FILTRES.map((f) => <Puce key={f.id} testid={`mr-filtre-${f.id}`} actif={filtre === f.id} onClick={() => setFiltre(f.id)}>{f.libelle}</Puce>)}
        </div>
        <div role="group" aria-label="Filtrer par canal" style={{ display: 'flex', gap: '5px', overflowX: 'auto', paddingBottom: '2px' }}>
          {FILTRES_CANAL.map((c) => <Puce key={c.id} testid={`mr-canal-${c.id}`} actif={canal === c.id} onClick={() => setCanal(c.id)}>{c.libelle}</Puce>)}
        </div>
      </div>

      <div data-testid="mr-resultat" style={{ fontSize: '12px', color: DOUX }}>
        {enChargement ? 'Chargement…' : `${visibles.length} ${pluriel(visibles.length, 'destinataire', 'destinataires')}`}
        {filtre === 'en_retard' && !enChargement ? ' · aucune relance ne partira tant que les interrupteurs restent fermés' : ''}
      </div>

      {!enChargement && !campagne && !erreur && (
        <div style={{ fontSize: '13px', color: DOUX }}>Aucune campagne de prospection pour l'instant.</div>
      )}

      <ul data-testid="mr-liste" style={{ listStyle: 'none', margin: 0, padding: '2px 4px 2px 0', display: 'flex', flexDirection: 'column', gap: '6px',
        maxHeight: 'min(65vh, 760px)', minHeight: '220px', overflowY: 'auto', overscrollBehavior: 'contain' }}>
        {visibles.map((l) => (
          <Carte key={l.id} l={l} maintenant={maintenant} active={ouverteId === l.id} onOuvrir={() => setOuverteId(l.id)} />
        ))}
        {!enChargement && visibles.length === 0 && (
          <li style={{ fontSize: '13px', color: DOUX, padding: '12px' }}>Aucun destinataire ne correspond.</li>
        )}
      </ul>

      {ligneOuverte && (
        <Panneau l={ligneOuverte} maintenant={maintenant} notes={notes.valeur} notesEnCours={notes.enCours}
          brouillon={brouillon.valeur} onFermer={fermer} />
      )}
    </div>
  );
}
