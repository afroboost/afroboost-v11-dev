/**
 * P3-S2 — L'ÉCRAN PROSPECTION.
 * ============================
 *
 * CE QU'IL FAIT : il affiche les prospects partenaires préparés par Cowork,
 * les filtre, ouvre la fiche de chacun, et permet de corriger ce qui se corrige
 * à la main. Rien d'autre.
 *
 * CE QU'IL NE FAIT PAS, ET C'EST DÉLIBÉRÉ : il n'envoie RIEN. Aucun bouton
 * « Envoyer », aucun « Contacter », aucune relance. Les messages J0/J+3/J+7
 * sont affichés en lecture et copiables — l'envoi appartient à P3-S3, derrière
 * une file d'approbation. Un bouton d'envoi ici serait un envoi accidentel à un
 * vrai festival.
 *
 * LES PROSPECTS NE SONT PAS DES CLIENTS. Cet écran lit `partner_prospects` et
 * cette collection seule. Il ne touche ni aux contacts, ni aux abonnés, ni aux
 * participants, ni aux réservations — et ses compteurs ne modifient aucun
 * compteur métier.
 *
 * CANDIDATURE / ACCEPTÉ viennent du serveur, qui compte les prospects PORTANT
 * un lien vers P2. Ils valent 0 tant que P3-S3 n'a pas construit ce
 * rattachement : afficher ici le nombre de partenaires de P2 donnerait un
 * chiffre juste au premier coup d'œil et faux dès le premier partenaire venu
 * d'ailleurs.
 *
 * CHARGEMENT : `useChargement` (socle P0). Une liste vide ne peut donc pas être
 * confondue avec un refus — tant que la réponse n'est pas là, l'écran dit « — ».
 *
 * COULEURS : uniquement `var(--primary-color)` / `var(--primary-rgb)`. Les
 * hexadécimaux après la virgule sont des REPLIS, jamais des valeurs imposées.
 * ICÔNES : SVG inline via `SvgIcon`, jamais d'emoji.
 */
import React, { useCallback, useMemo, useState } from 'react';
import axios from 'axios';
import SvgIcon from '../SvgIcon';
import useChargement, { SECTION } from '../../hooks/useChargement';
import { SectionErreur } from '../ui/EtatChargement';

const PRIMAIRE = 'var(--primary-color, #D91CD2)';
const RGB = 'var(--primary-rgb, 217, 28, 210)';
/* LE TEXTE EST POSÉ ICI, PAS HÉRITÉ — la leçon de P3-S2.
   Le tableau de bord est sombre par dessin (`.section-gradient` et
   `.card-gradient` sont des dégradés noirs), mais le jeu de jetons shadcn
   resté actif est le jeu CLAIR : `--foreground: 0 0% 3.9%`, et la classe
   `.dark` n'est posée nulle part. Un composant qui écrit `color: inherit`
   hérite donc d'un `rgb(10,10,10)` quasi noir SUR DU NOIR — contraste 1.06,
   texte invisible. Tous les autres écrans du tableau de bord
   (AdhesionsManager, PartnerApplications, ContactsManager) posent leur
   couleur explicitement : celui-ci fait pareil. Aucun thème global n'est
   touché — ce serait un autre lot, et un risque sans rapport. */
const TEXTE = '#fff';

/* Les valeurs techniques sont celles du serveur (P3S1_CATEGORIES). Le libellé
   n'existe que pour l'affichage : c'est la clé qui voyage, jamais le mot. */
export const CATEGORIES = [
  { cle: 'festival', libelle: 'Festival' },
  { cle: 'ecole_danse', libelle: 'École de danse' },
  { cle: 'restaurant', libelle: 'Restaurant' },
  { cle: 'bar', libelle: 'Bar' },
  { cle: 'commerce', libelle: 'Commerce' },
  { cle: 'organisateur_evenement', libelle: 'Organisateur événementiel' },
  { cle: 'communaute_etudiante', libelle: 'Communauté étudiante' },
  { cle: 'influenceur', libelle: 'Influenceur' },
];

/* Les six statuts AMONT. `decouverte`, `actif` et `ambassadeur` n'y sont pas :
   ils appartiennent au partenaire (P2), pas au prospect. */
export const STATUTS = [
  { cle: 'a_contacter', libelle: 'À contacter' },
  { cle: 'contacte', libelle: 'Contacté' },
  { cle: 'repondu', libelle: 'Répondu' },
  { cle: 'interesse', libelle: 'Intéressé' },
  { cle: 'sans_reponse_pause', libelle: 'Sans réponse — pause' },
  { cle: 'refuse', libelle: 'Refusé' },
];

export const COLLABORATIONS = [
  { cle: '', libelle: '— non défini' },
  { cle: 'community', libelle: 'Communauté (lien + QR)' },
  { cle: 'event_programming', libelle: 'Prestation / programmation' },
  { cle: 'both', libelle: 'Les deux' },
];

const PRIORITES = ['A', 'B', 'C'];
const TAILLES = [25, 50];

const libelleDe = (liste, cle) => {
  const trouve = liste.find((x) => x.cle === cle);
  return trouve ? trouve.libelle : (cle || '—');
};

/* Une valeur absente s'affiche « — », jamais 0 ni une chaîne vide : c'est ce
   qui distingue « pas de donnée » de « donnée nulle ». */
const ou = (valeur) => {
  if (valeur === null || valeur === undefined || valeur === '') return '—';
  return valeur;
};

const estUrl = (v) => typeof v === 'string' && /^https?:\/\//i.test(v.trim());

/* Un lien externe ne s'ouvre JAMAIS tout seul : c'est un `<a>` que l'humain
   clique. `noopener` empêche la page ouverte d'accéder à la nôtre. */
function LienExterne({ href, children }) {
  const url = (href || '').trim();
  if (!url) return <span>—</span>;
  const complet = estUrl(url) ? url : `https://${url.replace(/^\/+/, '')}`;
  return (
    <a
      href={complet}
      target="_blank"
      rel="noopener noreferrer"
      style={{ color: PRIMAIRE, textDecoration: 'none', wordBreak: 'break-all' }}
    >
      {children || url}{' '}
      <SvgIcon name="externalLink" size={11} />
    </a>
  );
}

function Tuile({ libelle, valeur, actif, onClick }) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        flex: '1 1 110px',
        minWidth: '104px',
        textAlign: 'left',
        padding: '10px 12px',
        borderRadius: '10px',
        cursor: onClick ? 'pointer' : 'default',
        border: `1px solid ${actif ? PRIMAIRE : 'rgba(255,255,255,0.10)'}`,
        background: actif ? `rgba(${RGB}, 0.16)` : 'rgba(255,255,255,0.04)',
        color: 'inherit',
      }}
      data-testid={`tuile-${libelle}`}
    >
      <div style={{ fontSize: '11px', opacity: 0.65, lineHeight: 1.3 }}>{libelle}</div>
      <div style={{ fontSize: '20px', fontWeight: 700, color: actif ? PRIMAIRE : 'inherit' }}>
        {valeur}
      </div>
    </button>
  );
}

function Etiquette({ texte, ton }) {
  const fonds = {
    neutre: 'rgba(255,255,255,0.08)',
    primaire: `rgba(${RGB}, 0.18)`,
  };
  return (
    <span
      style={{
        display: 'inline-block',
        padding: '2px 8px',
        borderRadius: '999px',
        fontSize: '11px',
        whiteSpace: 'nowrap',
        background: fonds[ton] || fonds.neutre,
        color: ton === 'primaire' ? PRIMAIRE : 'inherit',
      }}
    >
      {texte}
    </span>
  );
}

export default function ProspectsSection({ API }) {
  const base = API || '';

  const [filtres, setFiltres] = useState({
    status: '', category: '', priority: '', wave: '', city: '',
  });
  const [taille, setTaille] = useState(25);
  const [page, setPage] = useState(0);
  const [ouvert, setOuvert] = useState(null); // le prospect affiché en fiche
  const [brouillon, setBrouillon] = useState(null);
  const [enregistrement, setEnregistrement] = useState(false);
  const [message, setMessage] = useState(null);

  /* Les dépendances sont des CHAÎNES, jamais l'objet `filtres` — qui est neuf à
     chaque rendu et relancerait l'effet en boucle (règle absolue, incident V305). */
  const signature = [
    filtres.status, filtres.category, filtres.priority, filtres.wave, filtres.city,
    String(taille), String(page),
  ].join('|');

  const chargement = useChargement(
    {
      prospects: {
        url: `${base}/partner-prospects`,
        signature: true,
        appel: async () => {
          const params = { limit: taille, offset: page * taille };
          Object.keys(filtres).forEach((cle) => {
            if (filtres[cle]) params[cle] = filtres[cle];
          });
          const rep = await axios.get(`${base}/partner-prospects`, { params });
          return rep && rep.data ? rep.data : null;
        },
        extraire: (donnees) => donnees,
      },
    },
    { deps: [base, signature] }
  );

  const section = chargement.sections.prospects;
  const etat = (section && section.etat) || SECTION.CHARGEMENT;
  const charge = etat === SECTION.OK && section.donnees ? section.donnees : null;

  /* Dérivé de la section, jamais recopié dans un état local : aucun `setState`
     d'objet, donc aucun effet à relancer. */
  const liste = (charge && charge.prospects) || [];
  const compteurs = (charge && charge.counts) || {};
  const total = charge ? charge.total : null;
  const chargeUnFois = etat === SECTION.OK;

  const recharger = useCallback(() => chargement.reessayer('prospects'), [chargement]);

  const majFiltre = (cle, valeur) => {
    setPage(0);
    setFiltres((prec) => (prec[cle] === valeur ? prec : { ...prec, [cle]: valeur }));
  };

  const villes = useMemo(() => {
    const vues = [];
    liste.forEach((p) => {
      if (p.city && vues.indexOf(p.city) === -1) vues.push(p.city);
    });
    return vues.sort();
  }, [liste]);

  const ouvrir = (prospect) => {
    setMessage(null);
    setOuvert(prospect);
    setBrouillon({
      status: prospect.status || 'a_contacter',
      priority: prospect.priority || '',
      wave: prospect.wave || '',
      preferred_channel: prospect.preferred_channel || '',
      collaboration_type: prospect.collaboration_type || '',
      public_email: prospect.public_email || '',
      public_phone: prospect.public_phone || '',
      contact_name: prospect.contact_name || '',
      contact_role: prospect.contact_role || '',
      website: prospect.website || '',
      instagram: prospect.instagram || '',
      notes: prospect.notes || '',
      j0_message: prospect.j0_message || '',
      j3_message: prospect.j3_message || '',
      j7_message: prospect.j7_message || '',
      interested_message: prospect.interested_message || '',
    });
  };

  const fermer = () => {
    setOuvert(null);
    setBrouillon(null);
    setMessage(null);
  };

  const majBrouillon = (cle, valeur) => {
    setBrouillon((prec) => (prec && prec[cle] === valeur ? prec : { ...prec, [cle]: valeur }));
  };

  const enregistrer = async () => {
    if (!ouvert || !brouillon) return;
    setEnregistrement(true);
    setMessage(null);
    try {
      /* On n'envoie QUE ce qui a changé : un PATCH complet réécrirait des
         champs qu'on n'a pas touchés, et écraserait au passage une
         requalification arrivée entre-temps. */
      const modifs = {};
      Object.keys(brouillon).forEach((cle) => {
        const avant = ouvert[cle] === null || ouvert[cle] === undefined ? '' : ouvert[cle];
        if (String(brouillon[cle]) !== String(avant)) modifs[cle] = brouillon[cle] || null;
      });
      if (!Object.keys(modifs).length) {
        setMessage({ type: 'ok', texte: 'Rien à enregistrer.' });
        setEnregistrement(false);
        return;
      }
      const rep = await axios.patch(`${base}/partner-prospects/${ouvert.id}`, modifs);
      setOuvert(rep && rep.data ? rep.data : ouvert);
      setMessage({ type: 'ok', texte: 'Enregistré.' });
      recharger();
    } catch (err) {
      const detail = err && err.response && err.response.data && err.response.data.detail;
      setMessage({
        type: 'erreur',
        texte: typeof detail === 'string' ? detail : "Enregistrement refusé par le serveur.",
      });
    }
    setEnregistrement(false);
  };

  const nb = (cle) => (chargeUnFois ? (compteurs[cle] || 0) : '—');

  return (
    <div style={{ padding: '4px 0', color: TEXTE }} data-testid="prospection-section">
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
        <SvgIcon name="compass" size={18} />
        <h2 style={{ fontSize: '18px', fontWeight: 700, margin: 0 }}>Prospection</h2>
      </div>
      <p style={{ fontSize: '12px', opacity: 0.6, margin: '0 0 14px' }}>
        Les organisations à démarcher pour un partenariat. Aucun message n'est envoyé
        depuis cet écran.
      </p>

      {/* ---------- LES COMPTEURS ---------- */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', marginBottom: '14px' }}>
        <Tuile libelle="Total" valeur={nb('total')} actif={!filtres.status}
               onClick={() => majFiltre('status', '')} />
        {STATUTS.map((s) => (
          <Tuile
            key={s.cle}
            libelle={s.libelle}
            valeur={nb(s.cle)}
            actif={filtres.status === s.cle}
            onClick={() => majFiltre('status', filtres.status === s.cle ? '' : s.cle)}
          />
        ))}
        <Tuile libelle="Candidatures" valeur={nb('candidature')} />
        <Tuile libelle="Acceptés" valeur={nb('accepte')} />
      </div>

      {/* ---------- LES FILTRES ---------- */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', marginBottom: '12px' }}>
        <select value={filtres.category} onChange={(e) => majFiltre('category', e.target.value)}
                aria-label="Catégorie" data-testid="filtre-category" style={styleChamp}>
          <option value="">Toutes les catégories</option>
          {CATEGORIES.map((c) => <option key={c.cle} value={c.cle}>{c.libelle}</option>)}
        </select>
        <select value={filtres.status} onChange={(e) => majFiltre('status', e.target.value)}
                aria-label="Statut" data-testid="filtre-status" style={styleChamp}>
          <option value="">Tous les statuts</option>
          {STATUTS.map((s) => <option key={s.cle} value={s.cle}>{s.libelle}</option>)}
        </select>
        <select value={filtres.priority} onChange={(e) => majFiltre('priority', e.target.value)}
                aria-label="Priorité" data-testid="filtre-priority" style={styleChamp}>
          <option value="">Toutes priorités</option>
          {PRIORITES.map((p) => <option key={p} value={p}>Priorité {p}</option>)}
        </select>
        <input value={filtres.wave} onChange={(e) => majFiltre('wave', e.target.value)}
               placeholder="Vague" aria-label="Vague" data-testid="filtre-wave" style={styleChamp} />
        <input value={filtres.city} onChange={(e) => majFiltre('city', e.target.value)}
               placeholder="Ville" aria-label="Ville" data-testid="filtre-city"
               list="prospection-villes" style={styleChamp} />
        <datalist id="prospection-villes">
          {villes.map((v) => <option key={v} value={v} />)}
        </datalist>
        <select value={String(taille)} onChange={(e) => { setPage(0); setTaille(Number(e.target.value)); }}
                aria-label="Par page" data-testid="filtre-taille" style={styleChamp}>
          {TAILLES.map((n) => <option key={n} value={n}>{n} par page</option>)}
        </select>
      </div>

      {etat === SECTION.ERREUR || etat === SECTION.SESSION ? (
        <SectionErreur
          motif={(section && section.motif) || 'serveur'}
          quoi="les prospects"
          onReessayer={recharger}
        />
      ) : null}

      {etat === SECTION.CHARGEMENT && (
        <div style={{ opacity: 0.55, fontSize: '12px', padding: '10px 0' }}>
          Chargement des prospects…
        </div>
      )}

      {chargeUnFois && liste.length === 0 && (
        <div
          data-testid="prospection-vide"
          style={{
            padding: '28px 16px', textAlign: 'center', borderRadius: '12px',
            border: '1px dashed rgba(255,255,255,0.14)', opacity: 0.75, fontSize: '13px',
          }}
        >
          <SvgIcon name="compass" size={22} />
          <div style={{ marginTop: '8px' }}>
            {Object.values(filtres).some(Boolean)
              ? 'Aucun prospect ne correspond à ces filtres.'
              : 'Aucun prospect pour le moment.'}
          </div>
        </div>
      )}

      {/* ---------- LE TABLEAU (large) ---------- */}
      {chargeUnFois && liste.length > 0 && (
        <>
          <div className="hidden md:block" style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
              <thead>
                <tr style={{ textAlign: 'left', opacity: 0.6, fontSize: '11px' }}>
                  {['Organisation', 'Catégorie', 'Ville', 'Score', 'Priorité', 'Vague',
                    'Canal', 'Statut', 'Prochaine action', 'Dernier contact'].map((h) => (
                    <th key={h} style={{ padding: '6px 8px', whiteSpace: 'nowrap' }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {liste.map((p) => (
                  <tr
                    key={p.id}
                    onClick={() => ouvrir(p)}
                    data-testid={`ligne-${p.ref || p.id}`}
                    style={{ cursor: 'pointer', borderTop: '1px solid rgba(255,255,255,0.06)' }}
                  >
                    <td style={{ padding: '8px', fontWeight: 600 }}>
                      {p.organisation_name}
                      {p.ref ? <span style={{ opacity: 0.55, fontSize: '11px' }}> · {p.ref}</span> : null}
                    </td>
                    <td style={{ padding: '8px' }}>{libelleDe(CATEGORIES, p.category)}</td>
                    <td style={{ padding: '8px' }}>{ou(p.city)}</td>
                    <td style={{ padding: '8px', fontVariantNumeric: 'tabular-nums' }}>{ou(p.score)}</td>
                    <td style={{ padding: '8px' }}>{ou(p.priority)}</td>
                    <td style={{ padding: '8px' }}>{ou(p.wave)}</td>
                    <td style={{ padding: '8px', maxWidth: '160px' }}>{ou(p.preferred_channel)}</td>
                    <td style={{ padding: '8px' }}>
                      <Etiquette texte={libelleDe(STATUTS, p.status)}
                                 ton={p.status === 'a_contacter' ? 'primaire' : 'neutre'} />
                    </td>
                    <td style={{ padding: '8px' }}>{ou(p.next_followup_at)}</td>
                    <td style={{ padding: '8px' }}>{ou(p.last_contact_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* ---------- LES CARTES (mobile) ---------- */}
          <div className="md:hidden" style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {liste.map((p) => (
              <button
                key={p.id}
                type="button"
                onClick={() => ouvrir(p)}
                data-testid={`carte-${p.ref || p.id}`}
                style={{
                  textAlign: 'left', padding: '12px', borderRadius: '10px',
                  border: '1px solid rgba(255,255,255,0.10)',
                  background: 'rgba(255,255,255,0.04)', color: 'inherit',
                }}
              >
                <div style={{ fontWeight: 700, fontSize: '14px' }}>{p.organisation_name}</div>
                <div style={{ fontSize: '11px', opacity: 0.65, margin: '2px 0 6px' }}>
                  {libelleDe(CATEGORIES, p.category)} · {ou(p.city)}
                  {p.priority ? ` · Priorité ${p.priority}` : ''}
                  {p.wave ? ` · ${p.wave}` : ''}
                </div>
                <Etiquette texte={libelleDe(STATUTS, p.status)}
                           ton={p.status === 'a_contacter' ? 'primaire' : 'neutre'} />
              </button>
            ))}
          </div>

          {/* ---------- PAGINATION ---------- */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px',
                        marginTop: '12px', fontSize: '12px', flexWrap: 'wrap' }}>
            <button type="button" disabled={page === 0} onClick={() => setPage((p) => Math.max(p - 1, 0))}
                    data-testid="page-precedente" style={stylePagination(page === 0)}>
              <SvgIcon name="arrowLeft" size={12} /> Précédent
            </button>
            <span style={{ opacity: 0.7 }}>
              {page * taille + 1}–{page * taille + liste.length} sur {ou(total)}
            </span>
            <button type="button"
                    disabled={(page + 1) * taille >= (total || 0)}
                    onClick={() => setPage((p) => p + 1)}
                    data-testid="page-suivante"
                    style={stylePagination((page + 1) * taille >= (total || 0))}>
              Suivant <SvgIcon name="arrowRight" size={12} />
            </button>
          </div>
        </>
      )}

      {/* ---------- LA FICHE ---------- */}
      {ouvert && brouillon && (
        <div
          data-testid="fiche-prospect"
          onClick={fermer}
          style={{
            position: 'fixed', inset: 0, zIndex: 60, background: 'rgba(0,0,0,0.62)',
            display: 'flex', justifyContent: 'flex-end',
          }}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              width: '100%', maxWidth: '560px', height: '100%', overflowY: 'auto',
              background: '#15121a', borderLeft: `2px solid ${PRIMAIRE}`, padding: '18px',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '10px' }}>
              <div>
                <h3 style={{ margin: 0, fontSize: '17px', fontWeight: 700 }}>
                  {ouvert.organisation_name}
                </h3>
                <div style={{ fontSize: '11px', opacity: 0.6, marginTop: '2px' }}>
                  {ouvert.ref ? `${ouvert.ref} · ` : ''}{libelleDe(CATEGORIES, ouvert.category)}
                </div>
              </div>
              <button type="button" onClick={fermer} data-testid="fermer-fiche"
                      aria-label="Fermer" style={{ background: 'none', border: 'none', color: 'inherit', cursor: 'pointer' }}>
                <SvgIcon name="close" size={18} />
              </button>
            </div>

            <Bloc titre="Identité">
              <Champ libelle="Ville">{ou(ouvert.city)}</Champ>
              <Champ libelle="Adresse">{ou(ouvert.address)}</Champ>
              <Champ libelle="Site"><LienExterne href={ouvert.website} /></Champ>
              <Champ libelle="Instagram">
                {ouvert.instagram
                  ? <LienExterne href={`https://instagram.com/${String(ouvert.instagram).replace(/^@/, '')}`}
                                 children={ouvert.instagram} />
                  : '—'}
              </Champ>
              <Champ libelle="Facebook"><LienExterne href={ouvert.facebook} /></Champ>
              <Champ libelle="LinkedIn"><LienExterne href={ouvert.linkedin} /></Champ>
              <Champ libelle="TikTok"><LienExterne href={ouvert.tiktok} /></Champ>
              <Champ libelle="Source"><LienExterne href={ouvert.source_url} /></Champ>
              <Champ libelle="Source secondaire"><LienExterne href={ouvert.secondary_source_url} /></Champ>
              <Champ libelle="Vérifié le">{ou(ouvert.verified_at)}</Champ>
              <Champ libelle="Score">{ou(ouvert.score)}</Champ>
            </Bloc>

            <Bloc titre="Qualification (modifiable)">
              <Ligne libelle="Statut">
                <select value={brouillon.status} data-testid="edit-status"
                        onChange={(e) => majBrouillon('status', e.target.value)} style={styleChamp}>
                  {STATUTS.map((s) => <option key={s.cle} value={s.cle}>{s.libelle}</option>)}
                </select>
              </Ligne>
              <Ligne libelle="Priorité">
                <select value={brouillon.priority} data-testid="edit-priority"
                        onChange={(e) => majBrouillon('priority', e.target.value)} style={styleChamp}>
                  <option value="">—</option>
                  {PRIORITES.map((p) => <option key={p} value={p}>{p}</option>)}
                </select>
              </Ligne>
              <Ligne libelle="Vague">
                <input value={brouillon.wave} data-testid="edit-wave"
                       onChange={(e) => majBrouillon('wave', e.target.value)} style={styleChamp} />
              </Ligne>
              <Ligne libelle="Canal">
                <input value={brouillon.preferred_channel} data-testid="edit-channel"
                       onChange={(e) => majBrouillon('preferred_channel', e.target.value)} style={styleChamp} />
              </Ligne>
              <Ligne libelle="Collaboration">
                <select value={brouillon.collaboration_type} data-testid="edit-collaboration"
                        onChange={(e) => majBrouillon('collaboration_type', e.target.value)} style={styleChamp}>
                  {COLLABORATIONS.map((c) => <option key={c.cle} value={c.cle}>{c.libelle}</option>)}
                </select>
              </Ligne>
            </Bloc>

            <Bloc titre="Coordonnées (modifiables)">
              <Ligne libelle="E-mail">
                <input value={brouillon.public_email} data-testid="edit-email"
                       onChange={(e) => majBrouillon('public_email', e.target.value)} style={styleChamp} />
              </Ligne>
              <Ligne libelle="Téléphone">
                <input value={brouillon.public_phone} data-testid="edit-phone"
                       onChange={(e) => majBrouillon('public_phone', e.target.value)} style={styleChamp} />
              </Ligne>
              <Ligne libelle="Contact">
                <input value={brouillon.contact_name}
                       onChange={(e) => majBrouillon('contact_name', e.target.value)} style={styleChamp} />
              </Ligne>
              <Ligne libelle="Rôle">
                <input value={brouillon.contact_role}
                       onChange={(e) => majBrouillon('contact_role', e.target.value)} style={styleChamp} />
              </Ligne>
            </Bloc>

            <Bloc titre="Approche">
              <Champ libelle="Approche">{ou(ouvert.approach)}</Champ>
            </Bloc>

            {/* LES MESSAGES SONT DU TEXTE. Aucun bouton d'envoi : P3-S3. */}
            <Bloc titre="Messages préparés — aucun envoi depuis cet écran">
              {[['j0_message', 'Message J0'], ['j3_message', 'Relance J+3'],
                ['j7_message', 'Relance J+7'], ['interested_message', 'Si intéressé']].map(([cle, lib]) => (
                <div key={cle} style={{ marginBottom: '10px' }}>
                  <div style={{ fontSize: '11px', opacity: 0.6, marginBottom: '3px' }}>{lib}</div>
                  <textarea
                    value={brouillon[cle]}
                    data-testid={`edit-${cle}`}
                    onChange={(e) => majBrouillon(cle, e.target.value)}
                    rows={cle === 'j0_message' ? 6 : 3}
                    style={{ ...styleChamp, width: '100%', resize: 'vertical' }}
                  />
                </div>
              ))}
            </Bloc>

            <Bloc titre="Notes">
              <textarea value={brouillon.notes} data-testid="edit-notes" rows={6}
                        onChange={(e) => majBrouillon('notes', e.target.value)}
                        style={{ ...styleChamp, width: '100%', resize: 'vertical' }} />
            </Bloc>

            <Bloc titre="Suivi">
              <Champ libelle="Premier contact">{ou(ouvert.first_contact_at)}</Champ>
              <Champ libelle="Dernier contact">{ou(ouvert.last_contact_at)}</Champ>
              <Champ libelle="Prochaine action">{ou(ouvert.next_followup_at)}</Champ>
              <Champ libelle="Réponse le">{ou(ouvert.replied_at)}</Champ>
              <Champ libelle="Candidature liée">{ou(ouvert.partner_application_id)}</Champ>
              <Champ libelle="Partenaire lié">{ou(ouvert.partner_id)}</Champ>
            </Bloc>

            {message && (
              <div data-testid="message-fiche"
                   style={{ fontSize: '12px', margin: '8px 0',
                            color: message.type === 'ok' ? PRIMAIRE : '#ff8a80' }}>
                {message.texte}
              </div>
            )}

            <div style={{ display: 'flex', gap: '8px', marginTop: '12px' }}>
              <button type="button" onClick={enregistrer} disabled={enregistrement}
                      data-testid="enregistrer-prospect"
                      style={{ padding: '9px 16px', borderRadius: '8px', border: 'none',
                               background: PRIMAIRE, color: '#fff', fontWeight: 600,
                               cursor: enregistrement ? 'default' : 'pointer', opacity: enregistrement ? 0.6 : 1 }}>
                {enregistrement ? 'Enregistrement…' : 'Enregistrer'}
              </button>
              <button type="button" onClick={fermer}
                      style={{ padding: '9px 16px', borderRadius: '8px', color: 'inherit',
                               border: '1px solid rgba(255,255,255,0.16)', background: 'transparent',
                               cursor: 'pointer' }}>
                Fermer
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

const styleChamp = {
  padding: '7px 10px',
  borderRadius: '8px',
  border: '1px solid rgba(255,255,255,0.14)',
  background: 'rgba(255,255,255,0.05)',
  color: TEXTE,
  fontSize: '13px',
};

const stylePagination = (inactif) => ({
  padding: '6px 12px',
  borderRadius: '8px',
  border: '1px solid rgba(255,255,255,0.14)',
  background: 'transparent',
  color: 'inherit',
  cursor: inactif ? 'default' : 'pointer',
  opacity: inactif ? 0.35 : 1,
});

function Bloc({ titre, children }) {
  return (
    <section style={{ marginTop: '16px' }}>
      <div style={{ fontSize: '11px', letterSpacing: '0.06em', textTransform: 'uppercase',
                    opacity: 0.55, marginBottom: '6px' }}>
        {titre}
      </div>
      {children}
    </section>
  );
}

function Champ({ libelle, children }) {
  return (
    <div style={{ display: 'flex', gap: '8px', fontSize: '12.5px', padding: '3px 0' }}>
      <div style={{ minWidth: '132px', opacity: 0.6 }}>{libelle}</div>
      <div style={{ flex: 1, wordBreak: 'break-word' }}>{children}</div>
    </div>
  );
}

function Ligne({ libelle, children }) {
  return (
    <div style={{ display: 'flex', gap: '8px', alignItems: 'center', padding: '4px 0', flexWrap: 'wrap' }}>
      <div style={{ minWidth: '132px', opacity: 0.6, fontSize: '12.5px' }}>{libelle}</div>
      <div style={{ flex: 1, minWidth: '180px' }}>{children}</div>
    </div>
  );
}
