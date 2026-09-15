/**
 * BilanAssociation — PHASE 3 : le bilan mensuel Association et ses exports.
 *
 * UNE SEULE réponse serveur : GET /api/analytics/cockpit?vue=association. Elle
 * porte le bilan agrégé (activité, essais, fidélisation, abonnements,
 * finances, qualité, comparaison avec la période précédente, évolution des
 * douze mois, résumé exécutif). Cet écran n'additionne rien ; il affiche.
 *
 * EXPORTS : GET /api/analytics/export?format=csv|xlsx|pdf — même calcul, même
 * jeton signé. Le navigateur passe par `fetch` avec l'en-tête Authorization
 * puis enregistre le blob : un lien direct sans jeton reçoit 401.
 *
 * CONFIDENTIALITÉ : le serveur refuse de servir un bilan qui contiendrait une
 * donnée personnelle ; l'écran n'en manipule donc aucune.
 *
 * Aucun sondage : un appel par changement de filtre.
 */
import { useState, useEffect, useMemo } from 'react';
import axios from 'axios';
import { Carte, Badge, Bloc, chf, pct } from './AnalyticsCockpit';

const API = `${process.env.REACT_APP_BACKEND_URL || ''}/api`;
const PRIMAIRE = 'var(--primary-color, #D91CD2)';
const BORDURE = '1px solid rgba(255,255,255,0.08)';
const LIBELLES_FIDELITE = { '1': '1 fois', '2_5': '2 à 5 fois', '6_10': '6 à 10 fois', plus_10: '+ de 10 fois' };

/** Le mois courant au format YYYY-MM (pour le sélecteur). */
export function moisCourantISO(d) {
  const x = d || new Date();
  return `${x.getFullYear()}-${String(x.getMonth() + 1).padStart(2, '0')}`;
}

/** Paramètres de la requête bilan — mode mois (mois=YYYY-MM) ou année. */
export function parametresBilan({ mode, mois, coachId, courseId }) {
  const p = { vue: 'association', periode: mode === 'annee' ? 'annee' : 'mois', granularite: 'mois' };
  if (mois) p.mois = mois;
  if (coachId) p.coach_id = coachId;
  if (courseId) p.course_id = courseId;
  return p;
}

/** Nom de fichier proposé à l'enregistrement. */
export function nomFichier(format, periode) {
  return `bilan-afroboost-${(periode && periode.debut ? periode.debut : '').slice(0, 7) || 'periode'}.${format}`;
}

/** Télécharge un export : fetch AVEC le jeton (intercepteur axios), puis blob. */
export async function telechargerExport(format, params, periode, ouvrir) {
  const { vue, granularite, ...reste } = params;   // l'export est toujours la vue association
  const r = await axios.get(`${API}/analytics/export`, { params: { ...reste, format }, responseType: 'blob' });
  const url = URL.createObjectURL(r.data);
  (ouvrir || ((u, nom) => {
    const a = document.createElement('a');
    a.href = u; a.download = nom; document.body.appendChild(a); a.click(); a.remove();
  }))(url, nomFichier(format, periode));
  setTimeout(() => URL.revokeObjectURL(url), 10000);
  return r;
}

const Ligne = ({ libelle, valeur, note, testid }) => (
  <div data-testid={testid} style={{ display: 'flex', justifyContent: 'space-between', gap: 10, padding: '5px 0', borderTop: BORDURE, fontSize: 12 }}>
    <span style={{ color: 'rgba(255,255,255,0.65)' }}>{libelle}</span>
    <span style={{ color: '#fff', fontWeight: 600, textAlign: 'right' }}>
      {valeur}{note ? <span style={{ color: 'rgba(255,255,255,0.4)', fontWeight: 400, marginLeft: 6, fontSize: 11 }}>{note}</span> : null}
    </span>
  </div>
);

const n = (v) => (v === null || v === undefined ? '—' : String(v).replace('.', ','));

export default function BilanAssociation({ coaches = [] }) {
  const [mode, setMode] = useState('mois');
  const [mois, setMois] = useState(moisCourantISO());
  const [coachId, setCoachId] = useState('');
  const [courseId, setCourseId] = useState('');
  const [kpi, setKpi] = useState(null);
  const [chargement, setChargement] = useState(false);
  const [erreur, setErreur] = useState('');
  const [exportEnCours, setExportEnCours] = useState('');

  const params = useMemo(() => parametresBilan({ mode, mois, coachId, courseId }), [mode, mois, coachId, courseId]);
  const cleParams = JSON.stringify(params);

  useEffect(() => {
    let vivant = true;
    if (!params.mois) return undefined;
    setChargement(true); setErreur('');
    axios.get(`${API}/analytics/cockpit`, { params })
      .then((r) => { if (vivant) setKpi(r.data); })
      .catch((e) => {
        if (!vivant) return;
        const s = e && e.response && e.response.status;
        setErreur(s === 401 || s === 403 ? 'Accès refusé : reconnecte-toi (jeton signé requis).' : 'Chargement impossible.');
      })
      .finally(() => { if (vivant) setChargement(false); });
    return () => { vivant = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cleParams]);

  const [coursServeur, setCoursServeur] = useState([]);
  useEffect(() => {
    if (kpi && Array.isArray(kpi.cours_disponibles) && kpi.cours_disponibles.length) {
      setCoursServeur((prev) => (JSON.stringify(prev) === JSON.stringify(kpi.cours_disponibles) ? prev : kpi.cours_disponibles));
    }
  }, [kpi]);

  const b = kpi && kpi.association;
  const exporter = async (format) => {
    setExportEnCours(format); setErreur('');
    try { await telechargerExport(format, params, b && b.periode); } catch (e) {
      const s = e && e.response && e.response.status;
      setErreur(s === 401 || s === 403 ? 'Export refusé : jeton signé requis.' : `Export ${format.toUpperCase()} impossible.`);
    } finally { setExportEnCours(''); }
  };

  const select = { background: 'rgba(255,255,255,0.06)', border: BORDURE, color: '#fff', borderRadius: 8, padding: '6px 10px', fontSize: 12 };
  const bouton = (actif) => ({
    background: actif ? 'rgba(var(--primary-rgb, 217, 28, 210), 0.25)' : 'rgba(255,255,255,0.06)',
    border: actif ? `1px solid ${PRIMAIRE}` : BORDURE, color: actif ? '#fff' : 'rgba(255,255,255,0.6)',
  });

  return (
    <div data-testid="bilan-association" style={{ display: 'flex', flexDirection: 'column', gap: 14, minWidth: 0 }}>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, alignItems: 'center' }}>
        <button type="button" data-testid="mode-mois" onClick={() => setMode('mois')} className="px-3 py-1.5 rounded-full text-xs font-medium" style={bouton(mode === 'mois')}>Mois</button>
        <button type="button" data-testid="mode-annee" onClick={() => setMode('annee')} className="px-3 py-1.5 rounded-full text-xs font-medium" style={bouton(mode === 'annee')}>Année</button>
        <input type="month" value={mois} onChange={(e) => setMois(e.target.value)} aria-label="Mois" data-testid="filtre-mois" style={select} />
        {coaches.length > 0 && (
          <select value={coachId} onChange={(e) => setCoachId(e.target.value)} aria-label="Coach" data-testid="filtre-coach" style={select}>
            <option value="">Ensemble Afroboost / Association</option>
            {coaches.map((x) => <option key={x.email} value={x.email}>{x.name || x.email}</option>)}
          </select>
        )}
        {coursServeur.length > 0 && (
          <select value={courseId} onChange={(e) => setCourseId(e.target.value)} aria-label="Cours" data-testid="filtre-cours" style={select}>
            <option value="">Tous les cours</option>
            {coursServeur.filter((x) => x.id).map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}
          </select>
        )}
        {chargement && <span style={{ color: 'rgba(255,255,255,0.5)', fontSize: 12 }}>Calcul…</span>}
      </div>

      {erreur && <div role="alert" style={{ color: 'rgba(248,113,113,0.95)', fontSize: 12 }}>{erreur}</div>}

      {b && (
        <>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center', justifyContent: 'space-between' }}>
            <div>
              <div data-testid="bilan-titre" style={{ color: '#fff', fontSize: 16, fontWeight: 800 }}>Bilan {b.periode.libelle}</div>
              <div data-testid="bilan-perimetre" style={{ color: 'rgba(255,255,255,0.5)', fontSize: 11 }}>
                Périmètre : {b.perimetre.libelle}{b.perimetre.cours !== 'tous' ? ` · cours : ${b.perimetre.cours}` : ''}
              </div>
              {b.perimetre.note ? <div data-testid="bilan-note-cours" style={{ color: 'rgba(251, 191, 36, 0.95)', fontSize: 11 }}>{b.perimetre.note}</div> : null}
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {['csv', 'xlsx', 'pdf'].map((f) => (
                <button key={f} type="button" data-testid={`export-${f}`} disabled={!!exportEnCours} onClick={() => exporter(f)}
                  className="px-3 py-1.5 rounded-full text-xs font-medium" style={bouton(exportEnCours === f)}>
                  {f === 'csv' ? 'Exporter CSV' : f === 'xlsx' ? 'Exporter Excel' : 'Télécharger le bilan PDF'}
                </button>
              ))}
            </div>
          </div>

          <Bloc titre="Résumé exécutif" testid="bilan-resume">
            <div style={{ color: 'rgba(255,255,255,0.85)', fontSize: 13, lineHeight: 1.5 }}>{b.resume_executif}</div>
          </Bloc>

          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10 }}>
            <Carte testid="bilan-seances" valeur={b.activite.seances} libelle="Séances" />
            <Carte testid="bilan-reservations" valeur={b.activite.reservations} libelle="Réservations" />
            <Carte testid="bilan-uniques" valeur={b.activite.participants_uniques} libelle="Participants uniques" precision={`${b.activite.nouveaux} nouveaux · ${b.activite.recurrents} récurrents`} />
            <Carte testid="bilan-moyenne" valeur={n(b.activite.moyenne_par_seance)} libelle="Moyenne / séance" />
            <Carte testid="bilan-ca" valeur={chf(b.finances.ca_prouve)} libelle="CA prouvé" precision={`Stripe ${chf(b.finances.stripe)} · manuel ${chf(b.finances.manuel)}`} />
            <Carte testid="bilan-essais" valeur={b.essais.accordes} libelle="Essais accordés" precision={`${b.essais.presence_confirmee} présence(s) confirmée(s)`} />
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 12 }}>
            <Bloc titre="Activité" qualite={b.qualite.presence} testid="bilan-activite">
              <Ligne libelle="Mercredi" valeur={`${b.activite.mercredi.reservations} réserv. · ${b.activite.mercredi.seances} séance(s)`} note={`moy. ${n(b.activite.mercredi.moyenne)}`} />
              <Ligne libelle="Dimanche" valeur={`${b.activite.dimanche.reservations} réserv. · ${b.activite.dimanche.seances} séance(s)`} note={`moy. ${n(b.activite.dimanche.moyenne)}`} />
              <Ligne libelle="Autres jours" valeur={b.activite.autres_jours} />
              <Ligne libelle="Présence" valeur={b.presence.libelle} testid="bilan-presence" />
              <div style={{ color: 'rgba(255,255,255,0.4)', fontSize: 11, marginTop: 6 }}>Les réservations non vérifiées ne sont jamais comptées comme absences.</div>
            </Bloc>
            <Bloc titre="Essais gratuits" qualite={b.qualite.conversion} testid="bilan-essais-bloc">
              <Ligne libelle="Essais accordés" valeur={b.essais.accordes} />
              <Ligne libelle="Essais réservés" valeur={b.essais.reserves} />
              <Ligne libelle="Présences confirmées" valeur={b.essais.presence_confirmee} note={`${b.essais.presence_inconnue} inconnue(s)`} />
              <Ligne libelle="Couverture de présence" valeur={pct(b.essais.couverture_pct)} />
              <Ligne libelle="Conversions confirmées" valeur={b.essais.conversions_confirmees} note="KPI principal" testid="bilan-conversions" />
              <Ligne libelle="Conversions probables" valeur={b.essais.conversions_probables} note="à part" />
            </Bloc>
            <Bloc titre="Fidélisation" testid="bilan-fidelisation">
              {Object.keys(LIBELLES_FIDELITE).map((k) => <Ligne key={k} libelle={`Venus ${LIBELLES_FIDELITE[k]}`} valeur={b.fidelisation[k]} />)}
            </Bloc>
            <Bloc titre="Abonnements" qualite={b.qualite.renouvellements} testid="bilan-abonnements">
              <Ligne libelle="Abonnements actifs" valeur={b.abonnements.actifs} />
              <Ligne libelle="Nouveaux" valeur={b.abonnements.nouveaux} />
              <Ligne libelle="Pulse X10 actifs" valeur={b.abonnements.pulse_actifs} testid="bilan-pulse" />
              <Ligne libelle="Pulse X10 vendus" valeur={b.abonnements.pulse_vendus} />
              <Ligne libelle="Cartes membres actives" valeur={b.abonnements.cartes_actives} testid="bilan-cartes" />
              <Ligne libelle="Cartes membres vendues" valeur={b.abonnements.cartes_vendues} />
              <Ligne libelle="Renouvellements confirmés" valeur={b.abonnements.renouvellements_confirmes} note="KPI principal" />
              <Ligne libelle="Renouvellements probables" valeur={b.abonnements.renouvellements_probables} note="non comptés" />
            </Bloc>
            <Bloc titre="Finances" qualite={b.qualite.montants} testid="bilan-finances">
              <Ligne libelle="CA prouvé" valeur={chf(b.finances.ca_prouve)} />
              <Ligne libelle="dont Stripe" valeur={chf(b.finances.stripe)} />
              <Ligne libelle="dont manuel" valeur={chf(b.finances.manuel)} />
              <Ligne libelle="Achats payés" valeur={b.finances.achats_payes} note={`${b.finances.gratuits} offert(s)`} />
              <Ligne libelle="Panier moyen" valeur={chf(b.finances.panier_moyen)} />
              {Object.keys(b.finances.par_moyen || {}).map((m) => (
                <Ligne key={m} libelle={b.finances.par_moyen[m].libelle} valeur={`${b.finances.par_moyen[m].nombre} · ${chf(b.finances.par_moyen[m].montant)}`} />
              ))}
              <div data-testid="bilan-hors-ca" style={{ marginTop: 10, padding: 8, borderRadius: 8, border: '1px solid rgba(251, 191, 36, 0.35)' }}>
                <div style={{ color: 'rgba(251, 191, 36, 0.95)', fontSize: 11, fontWeight: 700, marginBottom: 4 }}>À part — jamais additionnés au CA prouvé</div>
                <Ligne libelle="Montants déclarés non prouvés" valeur={chf(b.finances.hors_ca.declare_non_prouve_montant)} note={`${b.finances.hors_ca.declare_non_prouve_nombre} achat(s)`} />
                <Ligne libelle="Paiements en attente" valeur={`${b.finances.hors_ca.pending_nombre} · ${chf(b.finances.hors_ca.pending_montant)} déclarés`} />
                <Ligne libelle="Données financières inconnues" valeur={b.finances.hors_ca.inconnus} />
              </div>
              <div style={{ color: 'rgba(255,255,255,0.4)', fontSize: 11, marginTop: 6 }}>{b.finances.remboursements}.</div>
            </Bloc>
            <Bloc titre={`Comparaison avec ${b.comparaison.periode_precedente.libelle}`} testid="bilan-comparaison">
              {Object.keys(b.comparaison.indicateurs).map((k) => {
                const v = b.comparaison.indicateurs[k];
                const couleur = v.variation_pct === null || v.variation_pct === undefined ? 'rgba(255,255,255,0.5)'
                  : v.variation_pct >= 0 ? 'rgba(74, 222, 128, 0.9)' : 'rgba(248,113,113,0.95)';
                return (
                  <div key={k} data-testid={`comparaison-${k}`} style={{ display: 'flex', justifyContent: 'space-between', gap: 8, padding: '5px 0', borderTop: BORDURE, fontSize: 12 }}>
                    <span style={{ color: 'rgba(255,255,255,0.65)' }}>{v.libelle_indicateur}</span>
                    <span style={{ color: '#fff' }}>{n(v.precedent)} → {n(v.actuel)} <span style={{ color: couleur, fontWeight: 700, marginLeft: 6 }}>{v.libelle}</span></span>
                  </div>
                );
              })}
            </Bloc>
          </div>

          <Bloc titre={`Évolution ${b.evolution_annuelle.annee}`} testid="bilan-evolution">
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', minWidth: 560, fontSize: 12, color: 'rgba(255,255,255,0.8)', borderCollapse: 'collapse' }}>
                <thead>
                  <tr style={{ color: 'rgba(255,255,255,0.45)', fontSize: 11 }}>
                    <th style={{ textAlign: 'left', padding: '4px 6px' }}>Mois</th>
                    <th style={{ textAlign: 'right', padding: '4px 6px' }}>Participants</th>
                    <th style={{ textAlign: 'right', padding: '4px 6px' }}>Réservations</th>
                    <th style={{ textAlign: 'right', padding: '4px 6px' }}>Séances</th>
                    <th style={{ textAlign: 'right', padding: '4px 6px' }}>Essais</th>
                    <th style={{ textAlign: 'right', padding: '4px 6px' }}>CA prouvé</th>
                  </tr>
                </thead>
                <tbody>
                  {b.evolution_annuelle.mois.map((m) => (
                    <tr key={m.numero} data-testid={`evolution-${m.numero}`} style={{ borderTop: BORDURE, opacity: m.futur ? 0.35 : 1 }}>
                      <td style={{ padding: '4px 6px' }}>{m.mois}{m.futur ? <span style={{ color: 'rgba(255,255,255,0.45)', fontSize: 10, marginLeft: 4 }}>(à venir)</span> : null}</td>
                      <td style={{ textAlign: 'right', padding: '4px 6px' }}>{m.participants}</td>
                      <td style={{ textAlign: 'right', padding: '4px 6px' }}>{m.reservations}</td>
                      <td style={{ textAlign: 'right', padding: '4px 6px' }}>{m.seances}</td>
                      <td style={{ textAlign: 'right', padding: '4px 6px' }}>{m.essais}</td>
                      <td style={{ textAlign: 'right', padding: '4px 6px' }}>{chf(m.ca_prouve)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Bloc>

          <Bloc titre="Qualité des données" testid="bilan-qualite">
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginBottom: 8, fontSize: 11, color: 'rgba(255,255,255,0.65)' }}>
              présence <Badge niveau={b.qualite.presence} /> · montants <Badge niveau={b.qualite.montants} /> · moyen de paiement <Badge niveau={b.qualite.moyen_paiement} /> · renouvellements <Badge niveau={b.qualite.renouvellements} /> · conversion <Badge niveau={b.qualite.conversion} />
            </div>
            {b.qualite.phrases.map((ph, i) => <div key={i} style={{ color: 'rgba(255,255,255,0.55)', fontSize: 11, marginTop: 3 }}>{ph}</div>)}
          </Bloc>

          <div style={{ color: 'rgba(255,255,255,0.35)', fontSize: 10 }}>
            Généré le {b.genere_le} · Données générées à partir du système Afroboost. Les données personnelles des participants ne sont pas incluses.
          </div>
        </>
      )}
    </div>
  );
}
