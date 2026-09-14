/**
 * AnalyticsCockpit — PHASE 1 (participants / réservations).
 *
 * Un seul appel : GET /api/analytics/cockpit. Le serveur calcule TOUT depuis sa
 * table de faits ; cet écran n'additionne rien, ne devine rien — il affiche, et
 * il affiche aussi la COUVERTURE (présence vérifiée sur N, valeur connue sur N).
 *
 * ACCÈS : jeton signé exigé par le serveur (401/403 sinon). Le périmètre coach
 * est imposé côté serveur ; le filtre « coach » n'a d'effet que pour le
 * super-admin.
 *
 * PERFORMANCE : chargé UNIQUEMENT quand ce composant est monté (onglet actif),
 * une requête par changement de filtre, AUCUN sondage périodique.
 *
 * Couleurs : variables de marque, jamais de teinte codée en dur hors repli.
 */
import { useState, useEffect, useMemo } from 'react';
import axios from 'axios';
import {
  ResponsiveContainer, LineChart, Line, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid, Legend,
} from 'recharts';

const API = `${process.env.REACT_APP_BACKEND_URL || ''}/api`;
const PRIMAIRE = 'var(--primary-color, #D91CD2)';
const SECONDAIRE = 'var(--secondary-color, #8B5CF6)';
const BORDURE = '1px solid rgba(255,255,255,0.08)';

export const PERIODES = [
  { key: 'aujourdhui', label: "Aujourd'hui" },
  { key: 'semaine', label: 'Cette semaine' },
  { key: 'mois', label: 'Ce mois' },
  { key: 'annee', label: 'Cette année' },
  { key: 'perso', label: 'Personnalisé' },
];

const LIBELLES_DELAI = {
  jour_meme: 'Jour même', '1_jour': '1 jour avant', '2_3_jours': '2 à 3 jours',
  '4_7_jours': '4 à 7 jours', plus_7_jours: '+ de 7 jours', inconnu: 'Inconnu',
};
const LIBELLES_FIDELITE = { '1': '1 participation', '2_5': '2 à 5', '6_10': '6 à 10', plus_10: '+ de 10' };

/** Aujourd'hui (local) au format YYYY-MM-DD — pour le mode personnalisé. */
export function aujourdhuiISO(d) {
  const x = d || new Date();
  const p = (n) => String(n).padStart(2, '0');
  return `${x.getFullYear()}-${p(x.getMonth() + 1)}-${p(x.getDate())}`;
}

/** Paramètres de requête depuis l'état des filtres (testable sans réseau). */
export function parametresRequete({ periode, du, au, coachId, courseId, granularite }) {
  const p = { periode: periode || 'mois', granularite: granularite || 'jour' };
  if (p.periode === 'perso') { p.du = du || ''; p.au = au || ''; }
  if (coachId) p.coach_id = coachId;
  if (courseId) p.course_id = courseId;
  return p;
}

/** Granularité lisible selon la période : jour pour ≤ mois, semaine pour l'année. */
export function granulariteDe(periode) {
  return periode === 'annee' ? 'semaine' : 'jour';
}

const Carte = ({ valeur, libelle, precision, testid }) => (
  <div data-testid={testid} style={{
    flex: '1 1 130px', minWidth: 120, background: 'rgba(255,255,255,0.03)',
    border: BORDURE, borderRadius: 12, padding: '14px 12px', textAlign: 'center',
  }}>
    <div style={{ color: PRIMAIRE, fontSize: 24, fontWeight: 800, lineHeight: 1.1 }}>
      {valeur === null || valeur === undefined ? '—' : valeur}
    </div>
    <div style={{ color: 'rgba(255,255,255,0.55)', fontSize: 11, marginTop: 4 }}>{libelle}</div>
    {precision ? (
      <div style={{ color: 'rgba(255,255,255,0.35)', fontSize: 10, marginTop: 2 }}>{precision}</div>
    ) : null}
  </div>
);

const Badge = ({ niveau }) => {
  const couleur = niveau === 'fiable' ? 'rgba(74, 222, 128, 0.9)'
    : niveau === 'partiel' ? 'rgba(251, 191, 36, 0.9)' : 'rgba(255,255,255,0.4)';
  return (
    <span style={{
      display: 'inline-block', padding: '1px 8px', borderRadius: 999, fontSize: 10, fontWeight: 600,
      border: `1px solid ${couleur}`, color: couleur, marginLeft: 6, textTransform: 'uppercase',
    }}>{niveau || 'inconnu'}</span>
  );
};

const Bloc = ({ titre, qualite, children, testid }) => (
  <div data-testid={testid} style={{ border: BORDURE, borderRadius: 12, padding: 14, background: 'rgba(255,255,255,0.02)', minWidth: 0 }}>
    <div style={{ color: '#fff', fontSize: 13, fontWeight: 700, marginBottom: 10 }}>
      {titre}{qualite ? <Badge niveau={qualite} /> : null}
    </div>
    {children}
  </div>
);

const styleTooltip = { background: 'rgba(15,15,25,0.95)', border: BORDURE, borderRadius: 8, color: '#fff', fontSize: 12 };
const axe = { stroke: 'rgba(255,255,255,0.35)', fontSize: 10 };

export default function AnalyticsCockpit({ coaches = [], courses = [] }) {
  const [periode, setPeriode] = useState('mois');
  const [du, setDu] = useState(aujourdhuiISO(new Date(Date.now() - 30 * 86400000)));
  const [au, setAu] = useState(aujourdhuiISO());
  const [coachId, setCoachId] = useState('');
  const [courseId, setCourseId] = useState('');
  const [kpi, setKpi] = useState(null);
  const [chargement, setChargement] = useState(false);
  const [erreur, setErreur] = useState('');

  const params = useMemo(() => parametresRequete({
    periode, du, au, coachId, courseId, granularite: granulariteDe(periode),
  }), [periode, du, au, coachId, courseId]);
  const cleParams = JSON.stringify(params);

  useEffect(() => {
    let vivant = true;
    if (params.periode === 'perso' && (!params.du || !params.au)) return undefined;
    setChargement(true); setErreur('');
    axios.get(`${API}/analytics/cockpit`, { params })
      .then((r) => { if (vivant) setKpi(r.data); })
      .catch((e) => {
        if (!vivant) return;
        const s = e && e.response && e.response.status;
        setErreur(s === 401 || s === 403
          ? 'Accès refusé : reconnecte-toi (jeton signé requis).'
          : 'Chargement impossible.');
      })
      .finally(() => { if (vivant) setChargement(false); });
    return () => { vivant = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cleParams]);

  // Liste des cours : celle passée en prop, sinon celle que le serveur tire de
  // ses propres faits (`cours_disponibles`, complète même quand un cours est
  // sélectionné). Mémorisée pour ne pas disparaître pendant un rechargement.
  const [coursServeur, setCoursServeur] = useState([]);
  useEffect(() => {
    if (kpi && Array.isArray(kpi.cours_disponibles) && kpi.cours_disponibles.length) {
      setCoursServeur((prev) => (JSON.stringify(prev) === JSON.stringify(kpi.cours_disponibles) ? prev : kpi.cours_disponibles));
    }
  }, [kpi]);
  const listeCours = courses.length ? courses : coursServeur;

  const p = kpi && kpi.participants; const c = kpi && kpi.cours; const r = kpi && kpi.reservation;
  const pres = kpi && kpi.presence; const q = (kpi && kpi.qualite) || {};

  const serieHeures = r ? Object.keys(r.par_heure).map((h) => ({ heure: `${h}h`, reservations: r.par_heure[h] })) : [];
  const serieDelai = r ? Object.keys(LIBELLES_DELAI).filter((k) => k !== 'inconnu' || r.anticipation[k]).map((k) => ({ categorie: LIBELLES_DELAI[k], reservations: r.anticipation[k] || 0 })) : [];
  const serieFidelite = kpi ? Object.keys(LIBELLES_FIDELITE).map((k) => ({ categorie: LIBELLES_FIDELITE[k], participants: kpi.fidelite[k] || 0 })) : [];
  const serieJours = c ? [
    { jour: 'Mercredi', reservations: c.mercredi.reservations, participants: c.mercredi.participants, seances: c.mercredi.seances },
    { jour: 'Dimanche', reservations: c.dimanche.reservations, participants: c.dimanche.participants, seances: c.dimanche.seances },
  ] : [];

  const select = { background: 'rgba(255,255,255,0.06)', border: BORDURE, color: '#fff', borderRadius: 8, padding: '6px 10px', fontSize: 12 };

  return (
    <div data-testid="analytics-cockpit" style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      {/* Filtres */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, alignItems: 'center' }}>
        {PERIODES.map((x) => (
          <button key={x.key} type="button" onClick={() => setPeriode(x.key)} data-testid={`periode-${x.key}`}
            className="px-3 py-1.5 rounded-full text-xs font-medium transition-all"
            style={{
              background: periode === x.key ? `rgba(var(--primary-rgb, 217, 28, 210), 0.25)` : 'rgba(255,255,255,0.06)',
              border: periode === x.key ? `1px solid ${PRIMAIRE}` : BORDURE,
              color: periode === x.key ? '#fff' : 'rgba(255,255,255,0.6)',
            }}>{x.label}</button>
        ))}
        {periode === 'perso' && (
          <span style={{ display: 'inline-flex', gap: 6, alignItems: 'center' }}>
            <input type="date" value={du} onChange={(e) => setDu(e.target.value)} aria-label="Du" data-testid="filtre-du" style={select} />
            <span style={{ color: 'rgba(255,255,255,0.5)', fontSize: 12 }}>→</span>
            <input type="date" value={au} onChange={(e) => setAu(e.target.value)} aria-label="Au" data-testid="filtre-au" style={select} />
          </span>
        )}
        {coaches.length > 0 && (
          <select value={coachId} onChange={(e) => setCoachId(e.target.value)} aria-label="Coach" data-testid="filtre-coach" style={select}>
            <option value="">Tous les coachs</option>
            {coaches.map((x) => <option key={x.email} value={x.email}>{x.name || x.email}</option>)}
          </select>
        )}
        {listeCours.length > 0 && (
          <select value={courseId} onChange={(e) => setCourseId(e.target.value)} aria-label="Cours" data-testid="filtre-cours" style={select}>
            <option value="">Tous les cours</option>
            {listeCours.filter((x) => x.id).map((x) => (
              <option key={x.id} value={x.id}>{x.name}{x.reservations ? ` (${x.reservations})` : ''}</option>
            ))}
          </select>
        )}
        {chargement && <span style={{ color: 'rgba(255,255,255,0.5)', fontSize: 12 }}>Calcul…</span>}
      </div>

      {erreur && <div role="alert" style={{ color: 'rgba(248,113,113,0.95)', fontSize: 12 }}>{erreur}</div>}

      {kpi && (
        <>
          <div style={{ color: 'rgba(255,255,255,0.4)', fontSize: 11 }}>
            Du {kpi.periode.debut} au {kpi.periode.fin_exclue} (exclu) · périmètre : {kpi.perimetre.coach_id}
            {kpi.ecartees && kpi.ecartees.produits ? ` · ${kpi.ecartees.produits} achat(s) boutique exclu(s)` : ''}
          </div>

          {/* Cartes KPI */}
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10 }}>
            <Carte testid="kpi-participants" valeur={p.reservations_cours} libelle="Participants (réservations)" precision={p.sans_email ? `${p.sans_email} sans e-mail` : ''} />
            <Carte testid="kpi-uniques" valeur={p.uniques} libelle="Participants uniques" />
            <Carte testid="kpi-nouveaux" valeur={p.nouveaux} libelle="Nouveaux" precision={`${p.recurrents} récurrents`} />
            <Carte testid="kpi-essais" valeur={kpi.essais.detectes} libelle="Essais gratuits" />
            <Carte testid="kpi-seances" valeur={c.seances} libelle="Nombre de cours" />
            <Carte testid="kpi-moyenne" valeur={c.moyenne_par_seance} libelle="Moyenne / cours" />
          </div>

          {/* Présence : couverture explicite, jamais de no-show déduit */}
          <Bloc titre="Présence" qualite={q.presence} testid="bloc-presence">
            <div style={{ color: 'rgba(255,255,255,0.75)', fontSize: 12 }}>
              {pres.confirmee} confirmée(s) · {pres.absente} absence(s) déclarée(s) · {pres.inconnue} inconnue(s)
            </div>
            <div style={{ color: 'rgba(255,255,255,0.45)', fontSize: 11, marginTop: 4 }}>
              Présences vérifiées : {pres.libelle}
              {pres.couverture_pct !== null && pres.couverture_pct !== undefined ? ` · couverture ${String(pres.couverture_pct).replace('.', ',')} %` : ''}
              {' — les réservations non vérifiées ne sont jamais comptées comme absences.'}
            </div>
          </Bloc>

          {/* Graphiques */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 12 }}>
            <Bloc titre="Évolution des participants" testid="graph-evolution">
              <ResponsiveContainer width="100%" height={200}>
                <LineChart data={kpi.evolution}>
                  <CartesianGrid stroke="rgba(255,255,255,0.06)" />
                  <XAxis dataKey="periode" tick={axe} />
                  <YAxis tick={axe} allowDecimals={false} width={28} />
                  <Tooltip contentStyle={styleTooltip} />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  <Line isAnimationActive={false} type="monotone" dataKey="reservations" name="Réservations" stroke={PRIMAIRE} strokeWidth={2} dot={false} />
                  <Line isAnimationActive={false} type="monotone" dataKey="participants" name="Participants uniques" stroke={SECONDAIRE} strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </Bloc>
            <Bloc titre="Mercredi vs Dimanche" testid="graph-jours">
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={serieJours}>
                  <CartesianGrid stroke="rgba(255,255,255,0.06)" />
                  <XAxis dataKey="jour" tick={axe} />
                  <YAxis tick={axe} allowDecimals={false} width={28} />
                  <Tooltip contentStyle={styleTooltip} />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  <Bar isAnimationActive={false} dataKey="reservations" name="Réservations" fill={PRIMAIRE} radius={[6, 6, 0, 0]} />
                  <Bar isAnimationActive={false} dataKey="participants" name="Participants uniques" fill={SECONDAIRE} radius={[6, 6, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
              <div style={{ color: 'rgba(255,255,255,0.45)', fontSize: 11 }}>
                Mercredi : {c.mercredi.seances} séance(s), moy. {c.mercredi.moyenne ?? '—'} · Dimanche : {c.dimanche.seances} séance(s), moy. {c.dimanche.moyenne ?? '—'}
                {c.autres_jours ? ` · autres jours : ${c.autres_jours}` : ''}
              </div>
            </Bloc>
            <Bloc titre="Heures de réservation" testid="graph-heures">
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={serieHeures}>
                  <CartesianGrid stroke="rgba(255,255,255,0.06)" />
                  <XAxis dataKey="heure" tick={axe} interval={3} />
                  <YAxis tick={axe} allowDecimals={false} width={28} />
                  <Tooltip contentStyle={styleTooltip} />
                  <Bar isAnimationActive={false} dataKey="reservations" name="Réservations" fill={PRIMAIRE} radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </Bloc>
            <Bloc titre="Anticipation des réservations" testid="graph-anticipation">
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={serieDelai}>
                  <CartesianGrid stroke="rgba(255,255,255,0.06)" />
                  <XAxis dataKey="categorie" tick={axe} />
                  <YAxis tick={axe} allowDecimals={false} width={28} />
                  <Tooltip contentStyle={styleTooltip} />
                  <Bar isAnimationActive={false} dataKey="reservations" name="Réservations" fill={SECONDAIRE} radius={[6, 6, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
              <div style={{ color: 'rgba(255,255,255,0.45)', fontSize: 11 }}>
                Délai moyen réservation → cours : {r.delai_moyen_jours ?? '—'} jour(s)
              </div>
            </Bloc>
            <Bloc titre="Fidélité (participations cumulées)" testid="graph-fidelite">
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={serieFidelite}>
                  <CartesianGrid stroke="rgba(255,255,255,0.06)" />
                  <XAxis dataKey="categorie" tick={axe} />
                  <YAxis tick={axe} allowDecimals={false} width={28} />
                  <Tooltip contentStyle={styleTooltip} />
                  <Bar isAnimationActive={false} dataKey="participants" name="Participants" fill={PRIMAIRE} radius={[6, 6, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </Bloc>
          </div>

          <div style={{ color: 'rgba(255,255,255,0.35)', fontSize: 10 }}>
            Qualité — présence : {q.presence} · valeur financière : {q.valeur_financiere} ({q.valeurs_connues ?? 0} connue(s)) · identité : {q.identite}
            {q.conflits_nom_email ? ` · ${q.conflits_nom_email} e-mail(s) avec plusieurs noms` : ''}
          </div>
        </>
      )}
    </div>
  );
}
