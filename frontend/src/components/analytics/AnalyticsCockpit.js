/**
 * AnalyticsCockpit — PHASE 1 (participants / réservations) + PHASE 2 (revenus,
 * abonnements, essais & conversion).
 *
 * Un seul appel : GET /api/analytics/cockpit. Le serveur calcule TOUT depuis sa
 * table de faits et sa table d'achats ; cet écran n'additionne rien, ne devine
 * rien — il affiche, et il affiche aussi la COUVERTURE (présence vérifiée sur N,
 * valeur connue sur N) et le PÉRIMÈTRE de chaque section (les sections de la
 * phase 2 sont globales période/coach : le filtre cours ne s'y applique pas, et
 * l'écran le dit au lieu de mélanger en silence).
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
const LIBELLES_MOYEN = {
  stripe_card: 'Stripe — carte', stripe_twint: 'Stripe — TWINT', stripe_indetermine: 'Stripe — moyen non déterminé',
  twint: 'TWINT (manuel)', virement: 'Virement', especes: 'Espèces', mobile_money: 'Mobile Money', offert: 'Offert', inconnu: 'Inconnu',
};
const LIBELLES_CATEGORIE = { pulse_x10: 'Pulse X10', abonnement: 'Abonnement', carte_membre: 'Carte membre', essai: 'Essai', autre: 'Autre' };

/** Mise en forme d'un montant déjà calculé par le serveur — aucune addition ici. */
export function chf(v) {
  if (v === null || v === undefined) return '—';
  const n = Number(v);
  if (Number.isNaN(n)) return '—';
  const [ent, dec] = n.toFixed(2).split('.');
  return `${ent.replace(/\B(?=(\d{3})+(?!\d))/g, ' ')},${dec} CHF`;
}
export const pct = (v) => (v === null || v === undefined ? '—' : `${String(v).replace('.', ',')} %`);

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

export const Carte = ({ valeur, libelle, precision, testid }) => (
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

export const Badge = ({ niveau }) => {
  const couleur = niveau === 'fiable' ? 'rgba(74, 222, 128, 0.9)'
    : niveau === 'partiel' ? 'rgba(251, 191, 36, 0.9)' : 'rgba(255,255,255,0.4)';
  return (
    <span style={{
      display: 'inline-block', padding: '1px 8px', borderRadius: 999, fontSize: 10, fontWeight: 600,
      border: `1px solid ${couleur}`, color: couleur, marginLeft: 6, textTransform: 'uppercase',
    }}>{niveau || 'inconnu'}</span>
  );
};

export const Bloc = ({ titre, qualite, children, testid }) => (
  <div data-testid={testid} style={{ border: BORDURE, borderRadius: 12, padding: 14, background: 'rgba(255,255,255,0.02)', minWidth: 0 }}>
    <div style={{ color: '#fff', fontSize: 13, fontWeight: 700, marginBottom: 10 }}>
      {titre}{qualite ? <Badge niveau={qualite} /> : null}
    </div>
    {children}
  </div>
);

const styleTooltip = { background: 'rgba(15,15,25,0.95)', border: BORDURE, borderRadius: 8, color: '#fff', fontSize: 12 };
const axe = { stroke: 'rgba(255,255,255,0.35)', fontSize: 10 };
const note = { color: 'rgba(255,255,255,0.45)', fontSize: 11, marginTop: 4 };
const titreSection = { color: '#fff', fontSize: 15, fontWeight: 800, marginTop: 6, display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 6 };

/** Le périmètre d'une section globale, dit noir sur blanc quand un cours est filtré. */
const Perimetre = ({ courseId, texte }) => (
  <span data-testid="perimetre-global" style={{
    fontSize: 10, fontWeight: 600, padding: '1px 8px', borderRadius: 999, textTransform: 'uppercase',
    border: `1px solid ${courseId ? 'rgba(251, 191, 36, 0.9)' : 'rgba(255,255,255,0.25)'}`,
    color: courseId ? 'rgba(251, 191, 36, 0.95)' : 'rgba(255,255,255,0.5)',
  }}>{courseId ? 'Global période/coach — filtre cours NON appliqué' : (texte || 'Global période/coach')}</span>
);

function SectionRevenus({ rev, courseId }) {
  const moyens = Object.keys(rev.par_moyen || {}).filter((k) => rev.par_moyen[k].nombre > 0)
    .map((k) => ({ moyen: LIBELLES_MOYEN[k] || k, montant: rev.par_moyen[k].montant, nombre: rev.par_moyen[k].nombre }));
  const vc = rev.valeur_par_cours || { cours: [] };
  return (
    <div data-testid="section-revenus" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div style={titreSection}>Revenus <Badge niveau={rev.qualite && rev.qualite.montants} /> <Perimetre courseId={courseId} /></div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10 }}>
        <Carte testid="kpi-ca" valeur={chf(rev.ca_encaisse)} libelle="CA encaissé (prouvé)" precision={`Stripe ${chf(rev.ca_stripe)} · manuel ${chf(rev.ca_manuel)}`} />
        <Carte testid="kpi-transactions" valeur={rev.transactions_payees} libelle="Achats payés" precision={`${rev.gratuits} gratuit(s) / offert(s)`} />
        <Carte testid="kpi-panier" valeur={chf(rev.panier_moyen)} libelle="Panier moyen" />
        <Carte testid="kpi-revenu-participant" valeur={chf(rev.revenu_par_participant)} libelle="Revenu / acheteur unique" precision={`${rev.acheteurs_uniques} acheteur(s)`} />
        <Carte testid="kpi-pending" valeur={rev.en_attente.nombre} libelle="Paiements en attente" precision={`${chf(rev.en_attente.montant_declare)} déclarés, hors CA`} />
        <Carte testid="kpi-non-prouve" valeur={rev.declare_non_prouve.nombre} libelle="Montants déclarés non prouvés" precision={`${chf(rev.declare_non_prouve.montant)} hors CA · ${rev.montant_inconnu} inconnu(s)`} />
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 12 }}>
        <Bloc titre="Évolution du CA encaissé" testid="graph-ca">
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={rev.evolution || []}>
              <CartesianGrid stroke="rgba(255,255,255,0.06)" />
              <XAxis dataKey="periode" tick={axe} />
              <YAxis yAxisId="chf" tick={axe} width={40} />
              <YAxis yAxisId="n" orientation="right" tick={axe} allowDecimals={false} width={24} />
              <Tooltip contentStyle={styleTooltip} formatter={(v, n) => (n === 'CA' ? chf(v) : v)} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Line yAxisId="chf" isAnimationActive={false} type="monotone" dataKey="ca" name="CA" stroke={PRIMAIRE} strokeWidth={2} dot={false} />
              <Line yAxisId="n" isAnimationActive={false} type="monotone" dataKey="achats" name="Achats" stroke={SECONDAIRE} strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </Bloc>
        <Bloc titre="Répartition des paiements" qualite={rev.qualite && rev.qualite.moyen_paiement} testid="bloc-moyens">
          {moyens.length === 0 ? <div style={note}>Aucun encaissement prouvé sur la période.</div> : (
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={moyens} layout="vertical">
                <CartesianGrid stroke="rgba(255,255,255,0.06)" />
                <XAxis type="number" tick={axe} />
                <YAxis type="category" dataKey="moyen" tick={axe} width={150} />
                <Tooltip contentStyle={styleTooltip} formatter={(v, n) => (n === 'Montant' ? chf(v) : v)} />
                <Bar isAnimationActive={false} dataKey="montant" name="Montant" fill={PRIMAIRE} radius={[0, 6, 6, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
          <div style={note}>
            {moyens.map((m) => `${m.moyen} : ${m.nombre} (${chf(m.montant)})`).join(' · ')}
            {rev.qualite && rev.qualite.stripe_moyen_indetermine ? ` — carte ou TWINT non distingués sur ${rev.qualite.stripe_moyen_indetermine} paiement(s) Stripe.` : ''}
          </div>
        </Bloc>
        <Bloc titre="Valeur des réservations par cours" testid="table-valeur-cours">
          <div style={note}>{vc.perimetre}</div>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', fontSize: 12, color: 'rgba(255,255,255,0.8)', borderCollapse: 'collapse', marginTop: 6 }}>
              <thead><tr style={{ color: 'rgba(255,255,255,0.45)', fontSize: 11 }}>
                <th style={{ textAlign: 'left', padding: '4px 6px' }}>Cours</th><th style={{ textAlign: 'right', padding: '4px 6px' }}>Réserv.</th>
                <th style={{ textAlign: 'right', padding: '4px 6px' }}>Valeur connue</th><th style={{ textAlign: 'right', padding: '4px 6px' }}>Couverture</th>
              </tr></thead>
              <tbody>
                {(vc.cours || []).map((x) => (
                  <tr key={x.id || x.name} style={{ borderTop: BORDURE }}>
                    <td style={{ padding: '4px 6px' }}>{x.name}</td>
                    <td style={{ textAlign: 'right', padding: '4px 6px' }}>{x.reservations}</td>
                    <td style={{ textAlign: 'right', padding: '4px 6px' }}>{chf(x.valeur)}</td>
                    <td style={{ textAlign: 'right', padding: '4px 6px' }}>{x.valeurs_connues}/{x.reservations} · {pct(x.couverture_pct)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div style={note}>Total connu : {chf(vc.valeur_totale)} sur {vc.valeurs_connues}/{vc.reservations} réservation(s) — {pct(vc.couverture_pct)}.</div>
        </Bloc>
      </div>
      <div style={{ color: 'rgba(255,255,255,0.35)', fontSize: 10 }}>
        {rev.remboursements}. Un achat est compté une seule fois (droit d'accès = unité) ; seuls les montants prouvés entrent dans le CA.
      </div>
    </div>
  );
}

function SectionAbonnements({ abo, courseId }) {
  const cat = (o) => Object.keys(LIBELLES_CATEGORIE).filter((k) => o[k]).map((k) => `${LIBELLES_CATEGORIE[k]} ${o[k]}`).join(' · ') || '—';
  const rn = abo.renouvellements || {}; const cm = abo.cartes_membres || {};
  return (
    <div data-testid="section-abonnements" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div style={titreSection}>Abonnements <Perimetre courseId={courseId} /></div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10 }}>
        <Carte testid="kpi-actifs" valeur={abo.actifs.total} libelle="Actifs aujourd'hui" precision={cat(abo.actifs.par_categorie)} />
        <Carte testid="kpi-nouveaux-abos" valeur={abo.nouveaux.total} libelle="Nouveaux sur la période" precision={cat(abo.nouveaux.par_categorie)} />
        <Carte testid="kpi-expires" valeur={abo.expires.total} libelle="Expirés sur la période" precision={`${abo.expirant_bientot.total} expirent sous ${abo.expirant_bientot.jours} j`} />
        <Carte testid="kpi-pulse" valeur={abo.pulse_x10.actifs} libelle="Pulse X10 actifs" precision={`${abo.pulse_x10.vendus} vendu(s) sur la période`} />
        <Carte testid="kpi-cartes" valeur={cm.actives} libelle="Cartes membres actives" precision={`${cm.vendues} vendue(s) · ${cm.regularisees} régularisée(s) · ${cm.expirees} expirée(s)`} />
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 12 }}>
        <Bloc titre="Évolution (nouveaux / expirés / Pulse)" testid="graph-abonnements">
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={abo.evolution || []}>
              <CartesianGrid stroke="rgba(255,255,255,0.06)" />
              <XAxis dataKey="periode" tick={axe} />
              <YAxis tick={axe} allowDecimals={false} width={28} />
              <Tooltip contentStyle={styleTooltip} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Bar isAnimationActive={false} dataKey="nouveaux" name="Nouveaux" fill={PRIMAIRE} radius={[6, 6, 0, 0]} />
              <Bar isAnimationActive={false} dataKey="pulse" name="Pulse X10" fill={SECONDAIRE} radius={[6, 6, 0, 0]} />
              <Bar isAnimationActive={false} dataKey="expires" name="Expirés" fill="rgba(255,255,255,0.25)" radius={[6, 6, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </Bloc>
        <Bloc titre="Renouvellements" qualite={abo.qualite && abo.qualite.renouvellements} testid="bloc-renouvellements">
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10 }}>
            <Carte testid="kpi-renouv-confirmes" valeur={rn.confirmes} libelle="Confirmés (KPI principal)" precision="preuve explicite" />
            <Carte testid="kpi-renouv-probables" valeur={rn.probables} libelle={rn.libelle_probables || 'Renouvellements probables — non comptés dans le KPI principal'} precision="succession de droits, sans preuve explicite" />
            <Carte testid="kpi-renouv-inconnus" valeur={rn.inconnus} libelle="Inconnus" precision="fiches multiples sans ordre lisible" />
          </div>
          <div style={note}>Seuls les renouvellements CONFIRMÉS comptent dans le KPI principal ; les probables ne s'y ajoutent jamais.</div>
          {(rn.avertissement || (abo.qualite && abo.qualite.note)) ? (
            <div data-testid="note-renouv-test" style={note}>Qualité : {rn.avertissement || abo.qualite.note}</div>
          ) : null}
        </Bloc>
      </div>
    </div>
  );
}

function SectionEssais({ ess, courseId }) {
  const cp = ess.convertis_probables || {}; const pr = ess.presence || {}; const t = ess.taux || {};
  const etages = [
    { cle: 'accordes', libelle: 'Essais accordés', valeur: ess.accordes },
    { cle: 'reserves', libelle: 'Réservés', valeur: ess.reserves },
    { cle: 'presents', libelle: 'Présence confirmée', valeur: pr.confirmee },
    { cle: 'confirmes', libelle: 'Convertis (confirmés)', valeur: ess.convertis_confirmes },
    { cle: 'probables', libelle: 'Achat suivant (probable)', valeur: cp.total },
  ];
  const max = Math.max(1, ...etages.map((e) => e.valeur || 0));
  return (
    <div data-testid="section-essais" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div style={titreSection}>Essais & conversion <Badge niveau={ess.qualite && ess.qualite.conversion} /> <Perimetre courseId={courseId} /></div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 12 }}>
        <Bloc titre="Funnel" testid="funnel-essais">
          {etages.map((e) => (
            <div key={e.cle} data-testid={`funnel-${e.cle}`} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
              <div style={{ width: 150, fontSize: 11, color: 'rgba(255,255,255,0.65)', flexShrink: 0 }}>{e.libelle}</div>
              <div style={{ flex: 1, background: 'rgba(255,255,255,0.05)', borderRadius: 6, height: 18, minWidth: 0 }}>
                <div style={{ width: `${Math.round(100 * (e.valeur || 0) / max)}%`, minWidth: e.valeur ? 6 : 0, height: '100%', borderRadius: 6, background: `rgba(var(--primary-rgb, 217, 28, 210), 0.6)` }} />
              </div>
              <div style={{ width: 28, textAlign: 'right', fontSize: 12, fontWeight: 700, color: '#fff' }}>{e.valeur ?? '—'}</div>
            </div>
          ))}
          <div style={note}>
            Taux : réservation {pct(t.reservation)} · présence {pct(t.presence)} · conversion confirmée {pct(t.conversion_confirmee)} · probable {pct(t.conversion_probable)}
          </div>
          <div style={note}>
            Présence des essais réservés : {pr.confirmee} confirmée(s) · {pr.absente} absence(s) déclarée(s) · {pr.inconnue} inconnue(s) — couverture {pct(pr.couverture_pct)} ; une réservation non vérifiée n'est jamais une absence.
          </div>
        </Bloc>
        <Bloc titre="Conversion (achat suivant, même participant)" testid="bloc-conversion">
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10 }}>
            <Carte testid="kpi-conv-tout" valeur={cp.total} libelle="Vers n'importe quel achat" />
            <Carte testid="kpi-conv-pulse" valeur={cp.pulse_x10} libelle="Vers Pulse X10" />
            <Carte testid="kpi-conv-abonnement" valeur={cp.abonnement} libelle="Vers abonnement" />
            <Carte testid="kpi-conv-carte" valeur={cp.carte_membre} libelle="Vers carte membre" />
          </div>
          <div style={note}>
            Convention du funnel existant : cohorte = essais accordés sur la période, suivis sans fenêtre ; « confirmé » = marqueur converted_at (mesuré depuis le 17/08/2026).
            {ess.delai_conversion_probable_median_jours !== null && ess.delai_conversion_probable_median_jours !== undefined ? ` Délai médian essai → achat : ${ess.delai_conversion_probable_median_jours} jour(s).` : ''}
          </div>
        </Bloc>
      </div>
    </div>
  );
}

/* ═══ TRACKING 2B — ACQUISITION PAR SOURCE ═══
   Une ligne par source (first-touch de la personne, M2-A), calculée par le
   MÊME moteur que les sections ci-dessus : essai, présence (jamais « inconnue »
   comptée comme absence), un achat = une ligne, CA prouvé, renouvellements
   confirmés (les probables à part). Pas de coût d'acquisition : donnée absente. */
export function SectionSources({ sources, courseId }) {
  const lignes = (sources && sources.lignes) || [];
  const couv = (sources && sources.couverture) || {};
  const th = { textAlign: 'right', padding: '6px 8px', fontSize: 10, color: 'rgba(255,255,255,0.55)', textTransform: 'uppercase', letterSpacing: '0.05em', whiteSpace: 'nowrap', fontWeight: 600 };
  const td = { textAlign: 'right', padding: '7px 8px', fontSize: 12, color: '#fff', whiteSpace: 'nowrap', borderTop: '1px solid rgba(255,255,255,0.06)' };
  return (
    <div data-testid="section-sources" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div style={titreSection}>Acquisition — par source <Perimetre courseId={courseId} /></div>
      <Bloc titre="Source → essai → présence → achat → revenu → renouvellement" testid="tableau-sources">
        {lignes.length === 0 ? (
          <div style={note}>Aucune origine enregistrée sur la période.</div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ borderCollapse: 'collapse', width: '100%', minWidth: 900 }}>
              <thead>
                <tr>
                  <th style={{ ...th, textAlign: 'left' }}>Source</th>
                  <th style={th}>Participants</th>
                  <th style={th}>Essais</th>
                  <th style={th}>Présences</th>
                  <th style={th}>Achats</th>
                  <th style={th}>Clients</th>
                  <th style={th}>Essai → client</th>
                  <th style={th}>CA prouvé</th>
                  <th style={th}>Panier</th>
                  <th style={th}>Renouv. conf.</th>
                  <th style={th}>Prob.</th>
                  <th style={{ ...th, textAlign: 'left' }}>Offres</th>
                </tr>
              </thead>
              <tbody>
                {lignes.map((l) => (
                  <tr key={l.cle} data-testid={`source-${l.cle}`}>
                    <td style={{ ...td, textAlign: 'left', fontWeight: 700, color: l.source === 'inconnue' ? 'rgba(255,255,255,0.5)' : '#fff' }}>
                      {l.libelle}
                    </td>
                    <td style={td}>{l.participants}</td>
                    <td style={td}>{l.essais}</td>
                    <td style={td}>{l.presences_confirmees}</td>
                    <td style={td}>{l.achats}</td>
                    <td style={td}>{l.clients}</td>
                    <td style={td}>
                      {l.essais ? <>{pct(l.taux_conversion_confirmee)} <span style={{ color: 'rgba(255,255,255,0.45)' }}>(prob. {pct(l.taux_conversion_probable)})</span></> : '—'}
                      {l.essais ? <Badge niveau={l.qualite && l.qualite.conversion} /> : null}
                    </td>
                    <td style={{ ...td, fontWeight: 700 }}>{chf(l.ca_prouve)}</td>
                    <td style={td}>{l.panier_moyen === null || l.panier_moyen === undefined ? '—' : chf(l.panier_moyen)}</td>
                    <td style={td}>{l.renouvellements ? l.renouvellements.confirmes : 0}</td>
                    <td style={{ ...td, color: 'rgba(255,255,255,0.5)' }}>{l.renouvellements ? l.renouvellements.probables : 0}</td>
                    <td style={{ ...td, textAlign: 'left', whiteSpace: 'normal', color: 'rgba(255,255,255,0.7)', fontSize: 11 }}>
                      {(l.offres || []).map(([nom, n]) => `${nom} ×${n}`).join(' · ') || '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div style={note}>
          {sources && sources.convention}
          {couv.participants_total ? ` Couverture : ${couv.participants_attribues}/${couv.participants_total} participants et ${couv.achats_attribues}/${couv.achats_total} achats avec une origine connue.` : ''}
        </div>
      </Bloc>
    </div>
  );
}

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
  const rev = kpi && kpi.revenus; const abo = kpi && kpi.abonnements; const ess = kpi && kpi.essais_funnel;

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

          {/* ═══ PHASE 2 ═══ */}
          {rev && <SectionRevenus rev={rev} courseId={courseId} />}
          {abo && <SectionAbonnements abo={abo} courseId={courseId} />}
          {ess && <SectionEssais ess={ess} courseId={courseId} />}
          {/* ═══ TRACKING 2B ═══ */}
          {kpi && kpi.sources && <SectionSources sources={kpi.sources} courseId={courseId} />}
        </>
      )}
    </div>
  );
}
