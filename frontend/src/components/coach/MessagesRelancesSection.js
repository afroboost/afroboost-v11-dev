/**
 * V588 — CAMPAGNES → PROSPECTION → MESSAGES & RELANCES. VUE DE PILOTAGE, LECTURE SEULE.
 * V588b — lisible au quotidien : « qui vient de répondre, qui attend un appel,
 * qu'est-ce que j'ai répondu, que dois-je faire ». Liste compacte défilante, recherche,
 * priorités, et un panneau de détail (plein écran sur mobile) où le PARTENAIRE parle à
 * GAUCHE et AFROBOOST à DROITE.
 * V642 — UX PREMIUM : split-pane desktop (liste | conversation), mobile bascule.
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
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import axios from 'axios';
import SvgIcon from '../SvgIcon';
import useChargement, { SECTION } from '../../hooks/useChargement';
import { SectionErreur } from '../ui/EtatChargement';
import { ElementFil } from './FilConversation';
import { poser as ouvrirConversation } from '../../utils/prospectionIntention';
import {
  ETATS, LIBELLES_ETAT, FILTRES, FILTRES_CANAL, SUIVI_MANUEL_INDISPONIBLE,
  lignesRelances, compteursRelances, filtrerRelances, trierRelances, chronologie,
  dateCourte, libelleCanal, libelleStatutProspect, nomCampagne, ilYa,
  dernierEvenement, instant,
} from '../../utils/messagesRelances';

const PRIMAIRE = 'var(--primary-color, #D91CD2)';
const RGB = 'var(--primary-rgb, 217, 28, 210)';
const PRIMAIRE_LISIBLE = 'color-mix(in srgb, var(--primary-color, #D91CD2) 80%, white)';
const TEXTE = '#fff';
const DOUX = 'rgba(255,255,255,0.55)';
const BORD = 'rgba(255,255,255,0.10)';
const PAGES_PROSPECTS_MAX = 10;

const AMBRE = 'rgb(252,211,77)';
const VERT = 'rgb(134,239,172)';
const ROUGE = 'rgb(252,165,165)';
const BLEU = 'rgb(147,197,253)';
const TONS = {
  en_retard: { fond: 'rgba(245,158,11,0.12)', bord: 'rgba(245,158,11,0.4)', texte: AMBRE },
  repondu: { fond: 'rgba(34,197,94,0.12)', bord: 'rgba(34,197,94,0.35)', texte: VERT },
  refus: { fond: 'rgba(239,68,68,0.12)', bord: 'rgba(239,68,68,0.35)', texte: ROUGE },
  rebond: { fond: 'rgba(239,68,68,0.10)', bord: 'rgba(239,68,68,0.3)', texte: ROUGE },
  stoppe: { fond: 'rgba(255,255,255,0.05)', bord: 'rgba(255,255,255,0.16)', texte: 'rgba(255,255,255,0.6)' },
  manuel: { fond: 'rgba(255,255,255,0.04)', bord: 'rgba(255,255,255,0.2)', texte: 'rgba(255,255,255,0.75)' },
  envoye: { fond: `rgba(${RGB}, 0.10)`, bord: `rgba(${RGB}, 0.35)`, texte: PRIMAIRE_LISIBLE },
  remis: { fond: 'rgba(34,197,94,0.12)', bord: 'rgba(34,197,94,0.35)', texte: VERT },
  en_cours: { fond: 'rgba(255,255,255,0.04)', bord: `rgba(${RGB}, 0.3)`, texte: TEXTE },
  echec: { fond: 'rgba(239,68,68,0.12)', bord: 'rgba(239,68,68,0.35)', texte: ROUGE },
  prevu: { fond: 'rgba(255,255,255,0.04)', bord: `rgba(${RGB}, 0.3)`, texte: TEXTE },
  a_envoyer: { fond: 'rgba(255,255,255,0.04)', bord: `rgba(${RGB}, 0.3)`, texte: TEXTE },
  sans_objet: { fond: 'transparent', bord: 'rgba(255,255,255,0.08)', texte: 'rgba(255,255,255,0.4)' },
};

function Pastille({ etat, children, testid }) {
  const t = TONS[etat] || TONS.sans_objet;
  return (
    <span data-testid={testid} style={{ display: 'inline-flex', alignItems: 'center', gap: '3px', padding: '1px 7px',
      borderRadius: '999px', fontSize: '10.5px', fontWeight: 600, whiteSpace: 'nowrap',
      background: t.fond, border: `1px solid ${t.bord}`, color: t.texte }}>
      {children || LIBELLES_ETAT[etat] || etat}
    </span>
  );
}

function BadgeNouveau({ n }) {
  return (
    <span data-testid="mr-badge-nouveau" style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', padding: '1px 7px',
      borderRadius: '999px', fontSize: '10px', fontWeight: 800, letterSpacing: '0.03em', whiteSpace: 'nowrap',
      background: PRIMAIRE, color: '#fff' }}>
      <span aria-hidden="true" style={{ width: '5px', height: '5px', borderRadius: '50%', background: '#fff' }} />
      {n > 1 ? n : ''}NOUVEAU
    </span>
  );
}
function BadgeAppel() {
  return (
    <span data-testid="mr-badge-appel" style={{ display: 'inline-flex', alignItems: 'center', gap: '3px', padding: '1px 7px',
      borderRadius: '999px', fontSize: '10px', fontWeight: 700, whiteSpace: 'nowrap',
      background: 'rgba(59,130,246,0.14)', border: '1px solid rgba(96,165,250,0.5)', color: BLEU }}>
      <SvgIcon name="phone" size={10} /> Appel à faire
    </span>
  );
}
function BadgeAttendue() {
  return (
    <span data-testid="mr-badge-attendue" style={{ display: 'inline-flex', alignItems: 'center', gap: '3px', padding: '1px 7px',
      borderRadius: '999px', fontSize: '10px', fontWeight: 700, whiteSpace: 'nowrap',
      background: 'rgba(245,158,11,0.12)', border: '1px solid rgba(245,158,11,0.45)', color: AMBRE }}>
      <SvgIcon name="clock" size={10} /> Attendue
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

function Compteur({ libelle, valeur, actif, onClick, ton, testid }) {
  const couleur = ton === 'bleu' ? BLEU : ton === 'rouge' ? ROUGE : ton === 'ambre' ? AMBRE : ton === 'marque' ? PRIMAIRE_LISIBLE : TEXTE;
  const fort = !!ton && valeur !== '—' && Number(valeur) > 0;
  return (
    <button type="button" onClick={onClick} data-testid={testid} aria-pressed={!!actif}
      style={{ flex: '1 1 0', minWidth: '68px', textAlign: 'center', padding: '5px 6px', borderRadius: '8px',
        cursor: onClick ? 'pointer' : 'default', color: TEXTE,
        border: `1px solid ${actif ? `rgba(${RGB}, 0.6)` : 'rgba(255,255,255,0.08)'}`,
        background: actif ? `rgba(${RGB}, 0.14)` : 'transparent' }}>
      <div style={{ fontSize: '9.5px', color: DOUX, lineHeight: 1.2 }}>{libelle}</div>
      <div style={{ fontSize: '16px', fontWeight: 700, color: fort ? couleur : TEXTE, lineHeight: 1.2, marginTop: '1px' }}>{valeur}</div>
    </button>
  );
}

function Puce({ actif, onClick, children, testid }) {
  return (
    <button type="button" onClick={onClick} data-testid={testid} aria-pressed={actif}
      style={{ padding: '3px 8px', borderRadius: '999px', fontSize: '11px', cursor: 'pointer', color: TEXTE,
        fontWeight: actif ? 700 : 500, whiteSpace: 'nowrap', flexShrink: 0,
        border: `1px solid ${actif ? `rgba(${RGB}, 0.6)` : 'rgba(255,255,255,0.12)'}`,
        background: actif ? `rgba(${RGB}, 0.22)` : 'transparent' }}>
      {children}
    </button>
  );
}

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

/* ─── CARTE COMPACTE (liste gauche) ─── */
function Carte({ l, maintenant, onOuvrir, active }) {
  const ev = l.dernierMessageLe ? { titre: 'Réponse reçue', quand: l.dernierMessageLe } : dernierEvenement(l);
  const evTexte = ev ? `${ev.titre} ${ilYa(ev.quand, maintenant)}` : '';
  const date = dateOuRetard(l);
  return (
    <li data-testid="mr-ligne" data-etat={l.etat} data-nouveau={l.nonLues > 0 ? 'oui' : 'non'}
      data-appel={l.appel ? 'oui' : 'non'} data-attendue={l.reponseAttendue ? 'oui' : 'non'}>
      <button type="button" onClick={onOuvrir} data-testid="mr-ligne-entete" aria-expanded={active}
        style={{ width: '100%', textAlign: 'left', cursor: 'pointer', color: TEXTE, padding: '8px 10px',
          borderRadius: '8px', display: 'flex', flexDirection: 'column', gap: '2px',
          borderLeft: active ? `3px solid ${PRIMAIRE}` : '3px solid transparent',
          border: `1px solid ${active ? `rgba(${RGB}, 0.5)` : l.nonLues ? `rgba(${RGB}, 0.35)` : 'transparent'}`,
          background: active ? `rgba(${RGB}, 0.12)` : l.nonLues > 0 ? `rgba(${RGB}, 0.06)` : 'transparent',
          transition: 'background 0.15s' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '6px' }}>
          <span style={{ fontSize: '13px', fontWeight: l.nonLues > 0 || l.appel ? 700 : 500, minWidth: 0,
            overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {l.organisation}
          </span>
          <span style={{ display: 'flex', gap: '3px', flexShrink: 0 }}>
            <Badges l={l} />
          </span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '6px', fontSize: '11px', color: DOUX }}>
          <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {`Prochaine action : ${l.prochaineAction}`}{date ? ` · ${date}` : ''}
          </span>
          {!l.nonLues && !l.appel && !l.reponseAttendue && <Pastille etat={l.etat} testid="mr-etat" />}
        </div>
        {(l.etat === ETATS.MANUEL || evTexte) && (
          <div style={{ fontSize: '10.5px', color: DOUX, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {l.etat === ETATS.MANUEL ? SUIVI_MANUEL_INDISPONIBLE : evTexte}
          </div>
        )}
        {l.extrait && l.nonLues > 0 && (
          <div data-testid="mr-extrait" style={{ fontSize: '11px', color: 'rgba(255,255,255,0.7)', fontStyle: 'italic',
            overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            « {l.extrait} »
          </div>
        )}
      </button>
    </li>
  );
}

/* ─── BULLES DE CONVERSATION ─── */
function Bulle({ cote, titre, quand, objet, corps, pied, testid }) {
  const droite = cote === 'afroboost';
  return (
    <div data-testid={testid} data-cote={cote} style={{ display: 'flex', justifyContent: droite ? 'flex-end' : 'flex-start' }}>
      <div style={{ maxWidth: '88%', minWidth: 0, padding: '8px 10px', borderRadius: droite ? '12px 12px 4px 12px' : '12px 12px 12px 4px',
        background: droite ? `rgba(${RGB}, 0.16)` : 'rgba(255,255,255,0.06)',
        border: `1px solid ${droite ? `rgba(${RGB}, 0.45)` : 'rgba(255,255,255,0.14)'}` }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: '8px', fontSize: '10px',
          letterSpacing: '0.04em', textTransform: 'uppercase', color: droite ? PRIMAIRE_LISIBLE : 'rgba(255,255,255,0.65)' }}>
          <span style={{ fontWeight: 800 }}>{droite ? 'Afroboost' : 'Partenaire'}{titre ? ` · ${titre}` : ''}</span>
          <span style={{ textTransform: 'none', letterSpacing: 0, color: DOUX, whiteSpace: 'nowrap' }}>{dateCourte(quand)}</span>
        </div>
        {objet && <div style={{ fontSize: '11px', color: DOUX, marginTop: '2px', overflowWrap: 'anywhere' }}>{objet}</div>}
        {corps && <div style={{ fontSize: '12.5px', lineHeight: 1.5, color: TEXTE, whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', marginTop: '4px' }}>{corps}</div>}
        {pied}
      </div>
    </div>
  );
}

function EvenementSysteme({ ev }) {
  const couleur = ev.genre === 'stop' ? ROUGE : ev.genre === 'retard' ? AMBRE : ev.genre === 'note' ? TEXTE : DOUX;
  return (
    <div data-testid="mr-evenement" data-genre={ev.genre} style={{ display: 'flex', justifyContent: 'center' }}>
      <div style={{ maxWidth: '92%', textAlign: 'center', fontSize: '10.5px', color: couleur, padding: ev.genre === 'note' ? '5px 8px' : '2px 4px',
        borderRadius: '6px', border: ev.genre === 'note' ? '1px dashed rgba(255,255,255,0.22)' : 'none', overflowWrap: 'anywhere' }}>
        <span style={{ color: DOUX }}>{dateCourte(ev.quand)} · </span>
        <strong>{ev.titre}</strong>{ev.detail ? ` — ${ev.detail}` : ''}
      </div>
    </div>
  );
}

function filDe(l, notes, brouillon) {
  const a = l.action || {};
  const conv = l.conversation;
  const items = [];
  if (conv && Array.isArray(conv.messages_fil)) {
    conv.messages_fil.forEach((e, i) => {
      if (!e) return;
      items.push({ t: instant(e.date), rendu: () => <ElementFil key={e.id || `f${i}`} e={e} /> });
    });
    chronologie(l, notes || [])
      .filter((ev) => !/^J0 envoyé|^J\+(3|7|14) envoyé|^Réponse reçue|^Réponse envoyée/.test(ev.titre))
      .forEach((ev, i) => items.push({ t: instant(ev.quand), rendu: () => <EvenementSysteme key={`s${i}`} ev={ev} /> }));
    return items.filter((x) => Number.isFinite(x.t)).sort((x, y) => x.t - y.t);
  }
  if (a.sent_at) {
    items.push({ t: instant(a.sent_at), rendu: () => (
      <Bulle key="j0" testid="mr-bulle-afroboost" cote="afroboost" titre="Message J0" quand={a.sent_at}
        objet={l.j0.objet} corps={l.j0.message} />) });
  }
  ['j3', 'j7', 'j14'].forEach((e) => {
    if (a[`${e}_sent_at`] && l[e]) {
      items.push({ t: instant(a[`${e}_sent_at`]), rendu: () => (
        <Bulle key={e} testid="mr-bulle-afroboost" cote="afroboost"
          titre={e === 'j3' ? 'Relance J+3' : e === 'j7' ? 'Relance J+7' : 'Relance J+14'}
          quand={a[`${e}_sent_at`]} objet={l[e].objet} corps={l[e].message} />) });
    }
  });
  ((conv && conv.messages_recus) || []).forEach((m, i) => {
    if (!m) return;
    items.push({ t: instant(m.received_at), rendu: () => (
      <Bulle key={`p${i}`} testid="mr-bulle-partenaire" cote="partenaire" titre={m.read_at ? '' : 'non lu'} quand={m.received_at}
        objet={m.subject} corps={m.body_text || '(aucun contenu lisible pour ce message)'}
        pied={m.from_email ? <div style={{ fontSize: '10px', color: DOUX, marginTop: '4px' }}>{m.from_email}</div> : null} />) });
  });
  const rep = conv && conv.derniere_reponse_afroboost;
  if (rep && rep.sent_at) {
    const b = brouillon || null;
    const ecritLe = b ? instant(b.edite_le || b.updated_at || b.genere_le) : NaN;
    const texteBrouillon = b && Number.isFinite(ecritLe) && ecritLe <= instant(rep.sent_at) ? (b.reponse_proposee || '') : '';
    items.push({ t: instant(rep.sent_at), rendu: () => (
      <Bulle key="rep" testid="mr-bulle-afroboost" cote="afroboost" titre="Réponse" quand={rep.sent_at} objet={rep.objet}
        corps={texteBrouillon}
        pied={<div style={{ fontSize: '10px', color: DOUX, marginTop: '4px' }}>
          {texteBrouillon ? 'Texte du brouillon validé avant l\'envoi.' : 'Réponse envoyée (son texte n\'est pas conservé ici).'}
        </div>} />) });
  }
  chronologie(l, notes || [])
    .filter((ev) => !/^J0 envoyé|^J\+(3|7|14) envoyé|^Réponse reçue|^Réponse envoyée/.test(ev.titre))
    .forEach((ev, i) => items.push({ t: instant(ev.quand), rendu: () => <EvenementSysteme key={`s${i}`} ev={ev} /> }));
  return items.filter((x) => Number.isFinite(x.t)).sort((x, y) => x.t - y.t);
}

function DetailEtape({ e }) {
  const nom = e.etape === 'j3' ? 'Relance J+3' : e.etape === 'j7' ? 'Relance J+7'
    : e.etape === 'j14' ? 'Relance J+14' : 'Message initial J0';
  return (
    <details data-testid={`mr-etape-${e.etape}`} style={{ border: `1px solid ${BORD}`, borderRadius: '8px', padding: '7px 9px', background: 'rgba(0,0,0,0.18)' }}>
      <summary style={{ cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '6px', flexWrap: 'wrap', listStyle: 'none' }}>
        <strong style={{ fontSize: '12px' }}>{nom}</strong>
        <span style={{ display: 'flex', gap: '4px', alignItems: 'center', fontSize: '10.5px', color: DOUX }}>
          {e.date_envoi ? `${dateCourte(e.date_envoi)}` : e.date_prevue ? `prévu ${dateCourte(e.date_prevue)}` : ''}
          <Pastille etat={e.livraison ? e.livraison.code : e.etat} testid={e.livraison ? `mr-livraison-${e.etape}` : undefined}>
            {e.livraison ? e.livraison.libelle : (e.etat === ETATS.EN_RETARD ? `Retard ${e.retard_jours}j` : undefined)}
          </Pastille>
        </span>
      </summary>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', marginTop: '6px', fontSize: '12px' }}>
        <div style={{ color: DOUX }}>Canal : <span style={{ color: TEXTE }}>{libelleCanal(e.canal)}</span>
          {' · '}Prévu : <span style={{ color: TEXTE }}>{dateCourte(e.date_prevue)}</span>
          {' · '}Soumis : <span style={{ color: TEXTE }}>{dateCourte(e.date_envoi)}</span>
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

const ETIQUETTE = { fontSize: '10px', color: DOUX, textTransform: 'uppercase', letterSpacing: '0.04em' };

/* ─── PANNEAU DE DÉTAIL (inline à droite sur desktop, plein écran mobile) ─── */
function PanneauDetail({ l, maintenant, notes, notesEnCours, brouillon, onFermer, mobile }) {
  const corpsRef = useRef(null);
  useEffect(() => {
    if (corpsRef.current) corpsRef.current.scrollTop = corpsRef.current.scrollHeight;
  }, [l.id]);
  useEffect(() => {
    const surTouche = (e) => { if (e.key === 'Escape') onFermer(); };
    window.addEventListener('keydown', surTouche);
    return () => window.removeEventListener('keydown', surTouche);
  }, [onFermer]);
  const fil = useMemo(() => filDe(l, notes, brouillon), [l, notes, brouillon]);
  const ids = (l.conversation && l.conversation.message_ids) || [];
  const dossier = ids[ids.length - 1] || '';
  const analyse = brouillon && (brouillon.prochaine_action || brouillon.resume) ? brouillon : null;

  return (
    <div data-testid="mr-panneau" style={{ display: 'flex', flexDirection: 'column', height: '100%', color: TEXTE, background: '#000' }}>
      {/* En-tête compact */}
      <div style={{ padding: '10px 12px', borderBottom: `1px solid ${BORD}`, flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
          <button type="button" onClick={onFermer} data-testid="mr-retour"
            style={{ display: mobile ? 'inline-flex' : 'none', alignItems: 'center', padding: '5px', borderRadius: '6px',
              border: 'none', background: 'rgba(255,255,255,0.08)', color: TEXTE, cursor: 'pointer' }}>
            <SvgIcon name="arrowLeft" size={16} />
          </button>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: '15px', fontWeight: 700, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{l.organisation}</div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px', alignItems: 'center', marginTop: '2px' }}>
              <Badges l={l} />
              <Pastille etat={l.etat}>{l.etat === ETATS.EN_RETARD ? `Retard ${(l.j3.etat === ETATS.EN_RETARD ? l.j3 : l.j7).retard_jours}j` : undefined}</Pastille>
              <span style={{ fontSize: '11px', color: DOUX }}>
                {[libelleCanal(l.canal), l.statutProspect ? libelleStatutProspect(l.statutProspect) : ''].filter(Boolean).join(' · ')}
              </span>
            </div>
          </div>
          <button type="button" onClick={onFermer} aria-label="Fermer" data-testid="mr-fermer"
            style={{ display: mobile ? 'none' : 'inline-flex', padding: '5px', borderRadius: '6px', border: 'none', background: 'rgba(255,255,255,0.08)', color: TEXTE, cursor: 'pointer' }}>
            <SvgIcon name="x" size={14} />
          </button>
        </div>
        <div style={{ fontSize: '12px', color: DOUX }}>
          Prochaine action : <span style={{ color: TEXTE, fontWeight: 600 }} data-testid="mr-panneau-action">{l.prochaineAction}</span>
          {dateOuRetard(l) ? <span style={{ color: l.etat === ETATS.EN_RETARD ? AMBRE : DOUX }}> · {dateOuRetard(l)}</span> : null}
        </div>
      </div>

      {/* Barre d'actions */}
      <div style={{ padding: '8px 12px', borderBottom: `1px solid ${BORD}`, flexShrink: 0, display: 'flex', flexWrap: 'wrap', gap: '6px', alignItems: 'center' }}>
        {dossier && (
          <button type="button" data-testid="mr-ouvrir-conversation" onClick={() => { onFermer(); ouvrirConversation(dossier); }}
            style={{ display: 'inline-flex', alignItems: 'center', gap: '5px', padding: '6px 12px', borderRadius: '8px',
              border: `1px solid rgba(${RGB}, 0.5)`, background: `rgba(${RGB}, 0.14)`, color: TEXTE, cursor: 'pointer', fontSize: '12px', fontWeight: 600 }}>
            <SvgIcon name="messageCircle" size={12} /> Répondre
          </button>
        )}
        {l.conversation && (
          <div style={{ display: 'flex', gap: '10px', fontSize: '11px', color: DOUX, flexWrap: 'wrap' }}>
            <span>Dernier msg : <strong style={{ color: TEXTE }}>{l.dernierMessageLe ? quandLisible(l.dernierMessageLe, maintenant) : '—'}</strong></span>
            <span>Réponse AF : <strong data-testid="mr-derniere-afroboost" style={{ color: l.reponseAttendue ? AMBRE : TEXTE }}>
              {l.derniereReponseAfroboostLe
                ? dateCourte(l.derniereReponseAfroboostLe)
                : l.reponseAttendue ? 'Aucune · Réponse attendue' : 'Aucune'}
            </strong></span>
          </div>
        )}
      </div>

      {/* Corps défilant */}
      <div ref={corpsRef} data-testid="mr-panneau-corps" style={{ flex: 1, overflowY: 'auto', overscrollBehavior: 'contain', padding: '10px 12px 24px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
        {l.etat === ETATS.MANUEL && (
          <div data-testid="mr-suivi-manuel" style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '11.5px',
            padding: '6px 8px', borderRadius: '6px', border: '1px dashed rgba(255,255,255,0.25)' }}>
            <SvgIcon name="info" size={12} />
            <span>Suivi manuel — {SUIVI_MANUEL_INDISPONIBLE.toLowerCase()}</span>
          </div>
        )}

        {analyse && (
          <div data-testid="mr-analyse-ia" style={{ fontSize: '11.5px', padding: '6px 8px', borderRadius: '6px', border: `1px solid ${BORD}`, background: 'rgba(255,255,255,0.02)' }}>
            <div style={{ ...ETIQUETTE, marginBottom: '2px' }}>Analyse IA</div>
            {analyse.resume && <div style={{ color: TEXTE }}>{analyse.resume}</div>}
            {analyse.prochaine_action && <div style={{ color: DOUX, marginTop: '2px' }}>Suggestion : <span style={{ color: TEXTE }}>{analyse.prochaine_action}</span></div>}
          </div>
        )}

        <section data-testid="mr-fil" style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
          {fil.length === 0 && <div style={{ fontSize: '12px', color: DOUX }}>Aucun échange enregistré.</div>}
          {fil.map((x) => x.rendu())}
          {notesEnCours && <div style={{ fontSize: '10.5px', color: DOUX, textAlign: 'center' }}>Chargement des notes…</div>}
        </section>

        <details style={{ marginTop: '4px' }}>
          <summary style={{ cursor: 'pointer', fontSize: '11px', fontWeight: 700, color: DOUX }}>Séquence automatique</summary>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '5px', marginTop: '6px' }}>
            <DetailEtape e={l.j0} />
            <DetailEtape e={l.j3} />
            <DetailEtape e={l.j7} />
            {l.j14 && (l.j14.date_envoi || (l.j14.message || '').trim()) ? <DetailEtape e={l.j14} /> : null}
          </div>
        </details>
      </div>
    </div>
  );
}

async function lireProspects(base) {
  const tous = [];
  for (let page = 0; page < PAGES_PROSPECTS_MAX; page += 1) {
    const rep = await axios.get(`${base}/partner-prospects`, { params: { limit: 50, offset: page * 50, inclure_corbeille: 1 } });
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [base, id, chemin, connu]);
  return { valeur: id ? cache[id] : undefined, enCours: !!id && enCours === id };
}
const extraireNotes = (d) => (d && Array.isArray(d.notes) ? d.notes : []);
const extraireBrouillon = (d) => (d && d.brouillon) || null;

/* ─── RESPONSIVE : détecte < 768px ─── */
function useEstMobile(seuil) {
  const s = seuil || 768;
  const [mobile, setMobile] = useState(() => typeof window !== 'undefined' && window.innerWidth < s);
  useEffect(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return undefined;
    const mq = window.matchMedia(`(max-width: ${s - 1}px)`);
    const cb = (e) => setMobile(e.matches);
    mq.addEventListener('change', cb);
    setMobile(mq.matches);
    return () => mq.removeEventListener('change', cb);
  }, [s]);
  return mobile;
}

export default function MessagesRelancesSection({ API, actif }) {
  const base = API || '/api';
  const [filtre, setFiltre] = useState('tous');
  const [canal, setCanal] = useState('tous');
  const [recherche, setRecherche] = useState('');
  const [campagneId, setCampagneId] = useState('');
  const [ouverteId, setOuverteId] = useState('');
  const mobile = useEstMobile(768);

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
  const donneesR = sR && sR.etat === SECTION.OK ? sR.donnees : null;
  const donneesP = sP && sP.etat === SECTION.OK ? sP.donnees : null;
  const conversations = useMemo(() => (donneesR && donneesR.conversations) || [], [donneesR]);
  const prospects = useMemo(() => (donneesP && donneesP.prospects) || [], [donneesP]);
  const drapeaux = (sD && sD.etat === SECTION.OK && sD.donnees) ? (sD.donnees.flags || sD.donnees) : null;
  const relancesOuvertes = !!(drapeaux && drapeaux.P3_RELANCE_ENABLED && drapeaux.P3_RELANCE_ENVOI_REEL);

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

  const basculerFiltre = (f) => setFiltre((prev) => (prev === f ? 'tous' : f));
  const fermer = useCallback(() => setOuverteId(''), []);

  const enChargement = [sC, sR, sP].some((s) => !s || s.etat === SECTION.CHARGEMENT || s.etat === SECTION.ATTENTE);
  const erreur = [['campagnes', sC, 'les campagnes'], ['reponses', sR, 'les réponses'], ['prospects', sP, 'les prospects']]
    .find(([, s]) => s && (s.etat === SECTION.ERREUR || s.etat === SECTION.SESSION));
  const v = (n) => (enChargement ? '—' : n);

  /* V642 : layout split desktop | bascule mobile */
  const voirListe = !mobile || !ligneOuverte;
  const voirDetail = !mobile || !!ligneOuverte;

  return (
    <div data-testid="messages-relances" style={{ color: TEXTE, display: 'flex', flexDirection: 'column', gap: '8px' }}>
      {/* ─── EN-TÊTE ─── */}
      <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between', gap: '6px' }}>
        <div style={{ minWidth: 0 }}>
          <h3 style={{ margin: 0, fontSize: '16px', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '6px' }}>
            <SvgIcon name="send" size={14} /> Messages & relances
          </h3>
          <div style={{ fontSize: '11px', color: DOUX }}>
            Lecture seule{campagne ? <> · <strong style={{ color: TEXTE }}>{nomCampagne(campagne.campaign)}</strong></> : null}
          </div>
        </div>
        <span data-testid="mr-interrupteurs" style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', fontSize: '10.5px',
          padding: '3px 8px', borderRadius: '999px', border: `1px solid ${BORD}`, color: DOUX }}>
          <SvgIcon name="lock" size={10} />
          {drapeaux === null ? 'Relances : ?' : relancesOuvertes ? 'Relances ouvertes' : 'Relances fermées'}
        </span>
      </div>

      {erreur && <SectionErreur motif={erreur[1].motif} quoi={erreur[2]} compact
        onReessayer={() => chargement.reessayer(erreur[0])} data-testid="mr-erreur" />}

      {campagnes.length > 1 && (
        <select value={campagne ? campagne.campaign.id : ''} onChange={(e) => { setCampagneId(e.target.value); setOuverteId(''); }}
          style={{ background: 'rgba(0,0,0,0.35)', color: TEXTE, border: `1px solid ${BORD}`, borderRadius: '6px', padding: '5px 6px', fontSize: '12px', maxWidth: '280px' }}>
          {campagnes.map((c) => <option key={c.campaign.id} value={c.campaign.id}>{nomCampagne(c.campaign)}</option>)}
        </select>
      )}

      {/* ─── COMPTEURS ─── */}
      <div data-testid="mr-compteurs" style={{ display: 'flex', gap: '4px', flexWrap: 'wrap' }}>
        <Compteur testid="mr-c-a-traiter" libelle="À traiter" valeur={v(compteurs.aTraiter)} ton="marque" actif={filtre === 'a_traiter'} onClick={() => basculerFiltre('a_traiter')} />
        <Compteur testid="mr-c-nouveaux" libelle="Nouveaux" valeur={v(compteurs.nouveaux)} ton="marque" actif={filtre === 'nouveaux'} onClick={() => basculerFiltre('nouveaux')} />
        <Compteur testid="mr-c-appels" libelle="Appels" valeur={v(compteurs.appels)} ton="bleu" actif={filtre === 'appels'} onClick={() => basculerFiltre('appels')} />
        <Compteur testid="mr-c-j3-retard" libelle="Retard" valeur={v(compteurs.j3EnRetard)} ton="ambre" actif={filtre === 'en_retard'} onClick={() => basculerFiltre('en_retard')} />
        <Compteur testid="mr-c-reponses" libelle="Réponses" valeur={v(compteurs.reponses)} actif={filtre === 'repondus'} onClick={() => basculerFiltre('repondus')} />
        <Compteur testid="mr-c-stoppes" libelle="Stoppés" valeur={v(compteurs.stoppes)} actif={filtre === 'stoppes'} onClick={() => basculerFiltre('stoppes')} />
      </div>

      {/* ─── FILTRES + RECHERCHE ─── */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
        <div style={{ position: 'relative' }}>
          <span style={{ position: 'absolute', left: '8px', top: '50%', transform: 'translateY(-50%)', color: DOUX, display: 'inline-flex' }}>
            <SvgIcon name="search" size={13} />
          </span>
          <input type="search" value={recherche} onChange={(e) => setRecherche(e.target.value)} data-testid="mr-recherche"
            placeholder="Organisation, ville, e-mail…" aria-label="Rechercher"
            style={{ width: '100%', boxSizing: 'border-box', padding: '6px 8px 6px 28px', borderRadius: '8px', fontSize: '12px',
              background: 'rgba(255,255,255,0.04)', color: TEXTE, border: `1px solid ${BORD}`, outline: 'none' }} />
        </div>
        <div style={{ display: 'flex', gap: '4px', overflowX: 'auto', paddingBottom: '1px' }}>
          {FILTRES.map((f) => <Puce key={f.id} testid={`mr-filtre-${f.id}`} actif={filtre === f.id} onClick={() => setFiltre(f.id)}>{f.libelle}</Puce>)}
        </div>
        <div style={{ display: 'flex', gap: '4px', overflowX: 'auto', paddingBottom: '1px' }}>
          {FILTRES_CANAL.map((c) => <Puce key={c.id} testid={`mr-canal-${c.id}`} actif={canal === c.id} onClick={() => setCanal(c.id)}>{c.libelle}</Puce>)}
        </div>
      </div>

      {!enChargement && compteurs.reponsesAttendues > 0 && (
        <div data-testid="mr-stats" style={{ fontSize: '11px', color: DOUX }}>
          {compteurs.reponsesAttendues} réponse{compteurs.reponsesAttendues > 1 ? 's' : ''} attendue{compteurs.reponsesAttendues > 1 ? 's' : ''}
        </div>
      )}

      <div data-testid="mr-resultat" style={{ fontSize: '11px', color: DOUX }}>
        {enChargement ? '…' : `${visibles.length} destinataire${visibles.length > 1 ? 's' : ''}`}
      </div>

      {!enChargement && !campagne && !erreur && (
        <div style={{ fontSize: '12px', color: DOUX }}>Aucune campagne de prospection pour l'instant.</div>
      )}

      {/* ─── SPLIT PANE (desktop) / BASCULE (mobile) ─── */}
      <div style={{ display: 'flex', gap: '0', height: 'min(72vh, 640px)', border: `1px solid ${BORD}`, borderRadius: '10px', overflow: 'hidden', background: '#000' }}>
        {/* COLONNE GAUCHE : liste */}
        {voirListe && (
          <div style={{ width: mobile ? '100%' : '340px', minWidth: mobile ? undefined : '280px', maxWidth: mobile ? undefined : '400px',
            flexShrink: 0, display: 'flex', flexDirection: 'column', overflow: 'hidden',
            borderRight: mobile ? 'none' : `1px solid ${BORD}` }}>
            <ul data-testid="mr-liste" style={{ listStyle: 'none', margin: 0, padding: '4px', flex: 1,
              overflowY: 'auto', overscrollBehavior: 'contain', display: 'flex', flexDirection: 'column', gap: '2px' }}>
              {visibles.map((l) => (
                <Carte key={l.id} l={l} maintenant={maintenant} active={ouverteId === l.id} onOuvrir={() => setOuverteId(l.id)} />
              ))}
              {!enChargement && visibles.length === 0 && (
                <li style={{ fontSize: '12px', color: DOUX, padding: '16px 12px', textAlign: 'center' }}>Aucun destinataire ne correspond.</li>
              )}
            </ul>
          </div>
        )}

        {/* COLONNE DROITE : détail */}
        {voirDetail && (
          <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
            {ligneOuverte ? (
              <PanneauDetail l={ligneOuverte} maintenant={maintenant} notes={notes.valeur} notesEnCours={notes.enCours}
                brouillon={brouillon.valeur} onFermer={fermer} mobile={mobile} />
            ) : (
              <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: DOUX, fontSize: '13px' }}>
                <div style={{ textAlign: 'center' }}>
                  <SvgIcon name="messageCircle" size={28} />
                  <div style={{ marginTop: '8px' }}>Sélectionne un destinataire</div>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
