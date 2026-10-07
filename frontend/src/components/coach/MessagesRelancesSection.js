/**
 * V588 — CAMPAGNES → PROSPECTION → MESSAGES & RELANCES. VUE DE PILOTAGE, LECTURE SEULE.
 *
 * CE QUE L'ÉCRAN FAIT : il LIT ce qui existe déjà et le met en ordre.
 *   GET /prospect-campaigns (+ détail)  → actions : textes approuvés, envois, échéances, annulations
 *   GET /prospect-inbound               → conversations : réponses, état commercial (refus), réponse Afroboost
 *   GET /partner-prospects (paginé)     → statut des fiches
 *   GET /feature-flags                  → état des interrupteurs de relance (affiché, jamais modifié)
 *   GET /prospect-inbound/{id}/notes    → notes du dossier, seulement à l'ouverture d'une ligne
 *
 * CE QU'IL NE FAIT PAS : aucun POST/PATCH/PUT, aucun bouton d'envoi, aucune copie de
 * données. Le calcul des états vit dans `utils/messagesRelances` (pur, testé).
 *
 * ⚠️ Les textes affichés sont ceux de l'ACTION (approuvés), jamais `j3_message` /
 * `j7_message` de la fiche prospect (brouillons non approuvés).
 *
 * ANTI-BOUCLE (V305) : dépendances primitives seulement ; les notes sont mises en
 * cache par identifiant et un `setState` identique renvoie `prev`.
 */
import React, { useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import SvgIcon from '../SvgIcon';
import useChargement, { SECTION } from '../../hooks/useChargement';
import { SectionErreur } from '../ui/EtatChargement';
import {
  ETATS, LIBELLES_ETAT, FILTRES, FILTRES_CANAL, SUIVI_MANUEL_INDISPONIBLE,
  lignesRelances, compteursRelances, filtrerRelances, trierRelances, chronologie,
  dateCourte, libelleCanal, libelleStatutProspect, nomCampagne,
} from '../../utils/messagesRelances';

const PRIMAIRE = 'var(--primary-color, #D91CD2)';
const RGB = 'var(--primary-rgb, 217, 28, 210)';
const PRIMAIRE_LISIBLE = 'color-mix(in srgb, var(--primary-color, #D91CD2) 80%, white)';
const TEXTE = '#fff';
const DOUX = 'rgba(255,255,255,0.65)';
const BORD = 'rgba(255,255,255,0.12)';
const PAGE = 30;
const PAGES_PROSPECTS_MAX = 10;

/* Tons sémantiques des états (jamais la couleur de marque, qui reste au coach). */
const TONS = {
  en_retard: { fond: 'rgba(245,158,11,0.22)', bord: 'rgba(245,158,11,0.55)', texte: 'rgb(252,211,77)' },
  repondu: { fond: 'rgba(34,197,94,0.20)', bord: 'rgba(34,197,94,0.5)', texte: 'rgb(134,239,172)' },
  refus: { fond: 'rgba(239,68,68,0.20)', bord: 'rgba(239,68,68,0.5)', texte: 'rgb(252,165,165)' },
  rebond: { fond: 'rgba(239,68,68,0.16)', bord: 'rgba(239,68,68,0.45)', texte: 'rgb(252,165,165)' },
  stoppe: { fond: 'rgba(255,255,255,0.08)', bord: 'rgba(255,255,255,0.22)', texte: 'rgba(255,255,255,0.7)' },
  manuel: { fond: 'rgba(255,255,255,0.06)', bord: 'rgba(255,255,255,0.28)', texte: 'rgba(255,255,255,0.85)' },
  envoye: { fond: `rgba(${RGB}, 0.16)`, bord: `rgba(${RGB}, 0.5)`, texte: PRIMAIRE_LISIBLE },
  prevu: { fond: 'rgba(255,255,255,0.06)', bord: `rgba(${RGB}, 0.45)`, texte: TEXTE },
  a_envoyer: { fond: 'rgba(255,255,255,0.06)', bord: `rgba(${RGB}, 0.45)`, texte: TEXTE },
  sans_objet: { fond: 'transparent', bord: 'rgba(255,255,255,0.10)', texte: 'rgba(255,255,255,0.45)' },
};

function Pastille({ etat, children, testid }) {
  const t = TONS[etat] || TONS.sans_objet;
  return (
    <span data-testid={testid} style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', padding: '3px 8px',
      borderRadius: '999px', fontSize: '11px', fontWeight: 600, whiteSpace: 'nowrap',
      background: t.fond, border: `1px solid ${t.bord}`, color: t.texte }}>
      {children || LIBELLES_ETAT[etat] || etat}
    </span>
  );
}

function libelleEtape(e) {
  const nom = e.etape === 'j3' ? 'J+3' : e.etape === 'j7' ? 'J+7' : 'J0';
  if (e.etat === ETATS.EN_RETARD) return `${nom} · en retard ${e.retard_jours} j`;
  if (e.etat === ETATS.SANS_OBJET) return `${nom} · —`;
  return `${nom} · ${LIBELLES_ETAT[e.etat]}`;
}

function Tuile({ libelle, valeur, actif, onClick, accent, testid }) {
  return (
    <button type="button" onClick={onClick} data-testid={testid}
      style={{ flex: '1 1 130px', minWidth: 0, textAlign: 'left', padding: '10px 12px', borderRadius: '10px',
        cursor: onClick ? 'pointer' : 'default', color: TEXTE,
        border: `1px solid ${actif ? PRIMAIRE : accent ? 'rgba(245,158,11,0.55)' : 'rgba(255,255,255,0.10)'}`,
        background: actif ? `rgba(${RGB}, 0.16)` : accent ? 'rgba(245,158,11,0.10)' : 'rgba(255,255,255,0.04)' }}>
      <div style={{ fontSize: '11px', color: DOUX, lineHeight: 1.3 }}>{libelle}</div>
      <div style={{ fontSize: '20px', fontWeight: 700, color: actif ? PRIMAIRE_LISIBLE : accent ? 'rgb(252,211,77)' : TEXTE }}>{valeur}</div>
    </button>
  );
}

function Puce({ actif, onClick, children, testid }) {
  return (
    <button type="button" onClick={onClick} data-testid={testid} aria-pressed={actif}
      style={{ padding: '6px 11px', borderRadius: '999px', fontSize: '12px', cursor: 'pointer', color: TEXTE,
        fontWeight: actif ? 700 : 500,
        border: `1px solid ${actif ? `rgba(${RGB}, 0.7)` : 'rgba(255,255,255,0.14)'}`,
        background: actif ? `rgba(${RGB}, 0.26)` : 'transparent' }}>
      {children}
    </button>
  );
}

function Champ({ libelle, children }) {
  return (
    <div style={{ minWidth: 0 }}>
      <div style={{ fontSize: '10px', letterSpacing: '0.04em', textTransform: 'uppercase', color: DOUX }}>{libelle}</div>
      <div style={{ fontSize: '13px', color: TEXTE, overflowWrap: 'anywhere' }}>{children}</div>
    </div>
  );
}

function DetailEtape({ e }) {
  const nom = e.etape === 'j3' ? 'Relance J+3' : e.etape === 'j7' ? 'Relance J+7' : 'Message initial J0';
  return (
    <div data-testid={`mr-etape-${e.etape}`} style={{ border: `1px solid ${BORD}`, borderRadius: '10px', padding: '10px 12px',
      background: 'rgba(0,0,0,0.22)', display: 'flex', flexDirection: 'column', gap: '8px' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '8px', flexWrap: 'wrap' }}>
        <strong style={{ fontSize: '13px', color: TEXTE }}>{nom}</strong>
        <Pastille etat={e.etat}>{e.etat === ETATS.EN_RETARD ? `En retard · ${e.retard_jours} j` : undefined}</Pastille>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))', gap: '8px' }}>
        <Champ libelle="Canal">{libelleCanal(e.canal)}</Champ>
        <Champ libelle="Date prévue">{dateCourte(e.date_prevue)}</Champ>
        <Champ libelle="Date d'envoi">{dateCourte(e.date_envoi)}</Champ>
        {e.date_annulation && <Champ libelle="Annulée le">{dateCourte(e.date_annulation)}</Champ>}
      </div>
      {e.motif && <div style={{ fontSize: '12px', color: DOUX }}>{e.motif}</div>}
      {e.objet && <Champ libelle="Objet">{e.objet}</Champ>}
      <div>
        <div style={{ fontSize: '10px', letterSpacing: '0.04em', textTransform: 'uppercase', color: DOUX }}>Message approuvé</div>
        {(e.message || '').trim()
          ? <div data-testid={`mr-message-${e.etape}`} style={{ whiteSpace: 'pre-wrap', fontSize: '13px', lineHeight: 1.5, color: TEXTE,
              overflowWrap: 'anywhere', marginTop: '4px' }}>{e.message}</div>
          : <div style={{ fontSize: '12px', color: DOUX, marginTop: '4px' }}>Aucun texte approuvé pour cette étape.</div>}
      </div>
    </div>
  );
}

const TONS_CHRONO = { envoi: PRIMAIRE_LISIBLE, reponse: 'rgb(134,239,172)', stop: 'rgb(252,165,165)', retard: 'rgb(252,211,77)', note: TEXTE, info: DOUX };

function Chronologie({ evenements, chargement }) {
  return (
    <div data-testid="mr-chronologie">
      <div style={{ fontSize: '12px', fontWeight: 700, color: TEXTE, marginBottom: '6px' }}>Historique</div>
      {evenements.length === 0 && <div style={{ fontSize: '12px', color: DOUX }}>Aucun événement enregistré.</div>}
      <ol style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: '6px' }}>
        {evenements.map((ev, i) => (
          <li key={`${ev.quand}-${i}`} style={{ display: 'flex', gap: '10px', fontSize: '12px', lineHeight: 1.45 }}>
            <span style={{ flex: '0 0 78px', color: DOUX }}>{dateCourte(ev.quand)}</span>
            <span style={{ minWidth: 0 }}>
              <span style={{ color: TONS_CHRONO[ev.genre] || TEXTE, fontWeight: 600 }}>{ev.titre}</span>
              {ev.detail && <span style={{ color: DOUX, overflowWrap: 'anywhere' }}> — {ev.detail}</span>}
            </span>
          </li>
        ))}
      </ol>
      {chargement && <div style={{ fontSize: '11px', color: DOUX, marginTop: '6px' }}>Chargement des notes…</div>}
    </div>
  );
}

function Ligne({ l, ouverte, onBasculer, notes, notesEnCours }) {
  const evenements = useMemo(() => (ouverte ? chronologie(l, notes || []) : []), [ouverte, l, notes]);
  return (
    <li data-testid="mr-ligne" data-etat={l.etat} style={{ border: `1px solid ${ouverte ? `rgba(${RGB}, 0.5)` : BORD}`,
      borderRadius: '12px', background: 'rgba(255,255,255,0.03)' }}>
      <button type="button" onClick={onBasculer} aria-expanded={ouverte} data-testid="mr-ligne-entete"
        style={{ width: '100%', textAlign: 'left', background: 'transparent', border: 'none', cursor: 'pointer',
          color: TEXTE, padding: '12px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '8px' }}>
          <div style={{ minWidth: 0 }}>
            <div style={{ fontSize: '14px', fontWeight: 700, overflowWrap: 'anywhere' }}>{l.organisation}</div>
            <div style={{ fontSize: '11px', color: DOUX }}>
              {[l.reference, libelleCanal(l.canal), l.statutProspect ? `Fiche : ${libelleStatutProspect(l.statutProspect)}` : '']
                .filter(Boolean).join(' · ')}
            </div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexShrink: 0 }}>
            <Pastille etat={l.etat} testid="mr-etat" />
            <SvgIcon name={ouverte ? 'arrowUp' : 'arrowDown'} size={14} />
          </div>
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
          {[l.j0, l.j3, l.j7].map((e) => <Pastille key={e.etape} etat={e.etat} testid={`mr-pastille-${e.etape}`}>{libelleEtape(e)}</Pastille>)}
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px 14px', fontSize: '12px', color: DOUX }}>
          <span>Prochaine action : <span style={{ color: TEXTE }}>{l.prochaineAction}</span>
            {l.prochaineDate ? <span> · {dateCourte(l.prochaineDate)}</span> : null}</span>
          {l.reponseLe && <span>Réponse reçue : <span style={{ color: 'rgb(134,239,172)' }}>{dateCourte(l.reponseLe)}</span></span>}
          {l.motifArret && <span>Arrêt : <span style={{ color: TEXTE }}>{l.motifArret}</span></span>}
        </div>
      </button>
      {ouverte && (
        <div data-testid="mr-detail" style={{ padding: '0 12px 12px', display: 'flex', flexDirection: 'column', gap: '10px' }}>
          {l.etat === ETATS.MANUEL && (
            <div data-testid="mr-suivi-manuel" style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '12px',
              padding: '8px 10px', borderRadius: '8px', border: '1px dashed rgba(255,255,255,0.3)', color: TEXTE }}>
              <SvgIcon name="info" size={14} />
              <span>{SUIVI_MANUEL_INDISPONIBLE} : ce contact se fait à la main ({libelleCanal(l.canal)}) et aucun envoi n'est encore tracé.</span>
            </div>
          )}
          <DetailEtape e={l.j0} />
          <DetailEtape e={l.j3} />
          <DetailEtape e={l.j7} />
          <Chronologie evenements={evenements} chargement={notesEnCours} />
        </div>
      )}
    </li>
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

export default function MessagesRelancesSection({ API, actif }) {
  const base = API || '/api';
  const [filtre, setFiltre] = useState('tous');
  const [canal, setCanal] = useState('tous');
  const [campagneId, setCampagneId] = useState('');
  const [ouverteId, setOuverteId] = useState('');
  const [limite, setLimite] = useState(PAGE);
  const [notesParDossier, setNotesParDossier] = useState({});
  const [notesEnCours, setNotesEnCours] = useState('');

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
  /* Les tableaux sont dérivés des DONNÉES (référence stable entre deux lectures),
     jamais recréés à chaque rendu : sinon les calculs ci-dessous repartiraient à vide. */
  const donneesR = sR && sR.etat === SECTION.OK ? sR.donnees : null;
  const donneesP = sP && sP.etat === SECTION.OK ? sP.donnees : null;
  const conversations = useMemo(() => (donneesR && donneesR.conversations) || [], [donneesR]);
  const prospects = useMemo(() => (donneesP && donneesP.prospects) || [], [donneesP]);
  const drapeaux = (sD && sD.etat === SECTION.OK && sD.donnees) ? (sD.donnees.flags || sD.donnees) : null;
  const relancesOuvertes = !!(drapeaux && drapeaux.P3_RELANCE_ENABLED && drapeaux.P3_RELANCE_ENVOI_REEL);

  /* « maintenant » figé à la minute : l'écran ne se recalcule pas en continu. */
  const minute = Math.floor(Date.now() / 60000);
  const lignes = useMemo(() => (campagne
    ? trierRelances(lignesRelances(campagne.actions, campagne.campaign, conversations, prospects, minute * 60000))
    : []), [campagne, conversations, prospects, minute]);
  const compteurs = useMemo(() => compteursRelances(lignes), [lignes]);
  const visibles = useMemo(() => filtrerRelances(lignes, filtre, canal), [lignes, filtre, canal]);

  /* Notes du dossier ouvert : lues une fois par conversation, à la demande. */
  const ligneOuverte = lignes.find((l) => l.id === ouverteId) || null;
  const dossierOuvert = (ligneOuverte && ligneOuverte.conversation && (ligneOuverte.conversation.message_ids || [])[0]) || '';
  const notesConnues = Object.prototype.hasOwnProperty.call(notesParDossier, dossierOuvert);
  useEffect(() => {
    if (!dossierOuvert || notesConnues) return undefined;
    let vivant = true;
    setNotesEnCours(dossierOuvert);
    axios.get(`${base}/prospect-inbound/${encodeURIComponent(dossierOuvert)}/notes`)
      .then((r) => (r && r.data && Array.isArray(r.data.notes) ? r.data.notes : []))
      .catch(() => [])
      .then((notes) => {
        if (!vivant) return;
        setNotesParDossier((prev) => (Object.prototype.hasOwnProperty.call(prev, dossierOuvert) ? prev : { ...prev, [dossierOuvert]: notes }));
        setNotesEnCours((prev) => (prev === dossierOuvert ? '' : prev));
      });
    return () => { vivant = false; };
  }, [base, dossierOuvert, notesConnues]);

  const choisirFiltre = (f) => { setFiltre(f); setLimite(PAGE); setOuverteId(''); };
  const choisirCanal = (c) => { setCanal(c); setLimite(PAGE); setOuverteId(''); };

  const enChargement = [sC, sR, sP].some((s) => !s || s.etat === SECTION.CHARGEMENT || s.etat === SECTION.ATTENTE);
  const erreur = [['campagnes', sC, 'les campagnes'], ['reponses', sR, 'les réponses'], ['prospects', sP, 'les prospects']]
    .find(([, s]) => s && (s.etat === SECTION.ERREUR || s.etat === SECTION.SESSION));
  const v = (n) => (enChargement ? '—' : n);

  return (
    <div data-testid="messages-relances" style={{ color: TEXTE, display: 'flex', flexDirection: 'column', gap: '14px' }}>
      <div>
        <h3 style={{ margin: 0, fontSize: '18px', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '8px' }}>
          <SvgIcon name="send" size={16} /> Messages & relances
        </h3>
        <p style={{ margin: '4px 0 0', fontSize: '12px', color: DOUX }}>
          Vue de pilotage en lecture seule : aucun message n'est envoyé depuis cet écran.
        </p>
        <div data-testid="mr-interrupteurs" style={{ marginTop: '8px', display: 'inline-flex', alignItems: 'center', gap: '6px',
          fontSize: '12px', padding: '4px 10px', borderRadius: '999px', border: `1px solid ${BORD}`, color: TEXTE }}>
          <SvgIcon name="lock" size={12} />
          {drapeaux === null ? 'Relances automatiques : état inconnu'
            : relancesOuvertes ? 'Relances automatiques : OUVERTES' : 'Relances automatiques : fermées'}
        </div>
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
      {campagne && (
        <div style={{ fontSize: '12px', color: DOUX }}>
          Campagne <strong style={{ color: TEXTE }}>{nomCampagne(campagne.campaign)}</strong>
          {campagne.campaign.etat === 'approuvee' ? ' · approuvée' : campagne.campaign.etat ? ` · ${campagne.campaign.etat}` : ''}
        </div>
      )}

      <div data-testid="mr-compteurs" style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
        <Tuile testid="mr-c-total" libelle="Total" valeur={v(compteurs.total)} actif={filtre === 'tous'} onClick={() => choisirFiltre('tous')} />
        <Tuile testid="mr-c-j0" libelle="J0 envoyés" valeur={v(compteurs.j0Envoyes)} actif={filtre === 'envoyes'} onClick={() => choisirFiltre('envoyes')} />
        <Tuile testid="mr-c-j3-avenir" libelle="J+3 à venir" valeur={v(compteurs.j3AVenir)} />
        <Tuile testid="mr-c-j3-retard" libelle="J+3 en retard" valeur={v(compteurs.j3EnRetard)} accent={compteurs.j3EnRetard > 0}
          actif={filtre === 'en_retard'} onClick={() => choisirFiltre('en_retard')} />
        <Tuile testid="mr-c-j7-avenir" libelle="J+7 à venir" valeur={v(compteurs.j7AVenir)} />
        <Tuile testid="mr-c-reponses" libelle="Réponses" valeur={v(compteurs.reponses)} actif={filtre === 'repondus'} onClick={() => choisirFiltre('repondus')} />
        <Tuile testid="mr-c-stoppes" libelle="Stoppés" valeur={v(compteurs.stoppes)} actif={filtre === 'stoppes'} onClick={() => choisirFiltre('stoppes')} />
        <Tuile testid="mr-c-manuel" libelle="À faire manuellement" valeur={v(compteurs.manuel)} actif={filtre === 'manuel'} onClick={() => choisirFiltre('manuel')} />
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
        <div role="group" aria-label="Filtrer par état" style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
          {FILTRES.map((f) => <Puce key={f.id} testid={`mr-filtre-${f.id}`} actif={filtre === f.id} onClick={() => choisirFiltre(f.id)}>{f.libelle}</Puce>)}
        </div>
        <div role="group" aria-label="Filtrer par canal" style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
          {FILTRES_CANAL.map((c) => <Puce key={c.id} testid={`mr-canal-${c.id}`} actif={canal === c.id} onClick={() => choisirCanal(c.id)}>{c.libelle}</Puce>)}
        </div>
      </div>

      <div data-testid="mr-resultat" style={{ fontSize: '12px', color: DOUX }}>
        {enChargement ? 'Chargement…' : `${visibles.length} destinataire${visibles.length > 1 ? 's' : ''}`}
        {filtre === 'en_retard' && !enChargement && ' · triés du plus ancien retard au plus récent · aucune relance ne partira tant que les interrupteurs restent fermés'}
      </div>

      {!enChargement && !campagne && !erreur && (
        <div style={{ fontSize: '13px', color: DOUX }}>Aucune campagne de prospection pour l'instant.</div>
      )}

      <ul data-testid="mr-liste" style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: '8px' }}>
        {visibles.slice(0, limite).map((l) => {
          const dossier = (l.conversation && (l.conversation.message_ids || [])[0]) || '';
          return (
            <Ligne key={l.id} l={l} ouverte={ouverteId === l.id}
              onBasculer={() => setOuverteId((prev) => (prev === l.id ? '' : l.id))}
              notes={dossier ? notesParDossier[dossier] : undefined}
              notesEnCours={!!dossier && notesEnCours === dossier} />
          );
        })}
      </ul>
      {visibles.length > limite && (
        <button type="button" data-testid="mr-plus" onClick={() => setLimite((n) => n + PAGE)}
          style={{ alignSelf: 'center', padding: '8px 16px', borderRadius: '999px', border: `1px solid ${BORD}`,
            background: 'transparent', color: TEXTE, cursor: 'pointer', fontSize: '13px' }}>
          Afficher {Math.min(PAGE, visibles.length - limite)} de plus ({visibles.length - limite} restants)
        </button>
      )}
    </div>
  );
}
