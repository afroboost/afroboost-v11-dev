/**
 * V637 — VUE PARTENAIRE (page publique, accès par jeton, sans compte).
 *
 * Layout inspiré du Dashboard Créateur Afroboost (V559 / CreatorDashboard.js) :
 * 4 cartes KPI, lien d'origine, tableau des inscriptions anonymisées.
 *
 * SÉCURITÉ :
 * - Lecture seule absolue (aucun bouton d'action partenaire).
 * - Le jeton est dans l'URL, envoyé au serveur qui vérifie le hash SHA-256.
 * - Aucun email ni téléphone jamais affiché (serveur envoie nom_masque uniquement).
 * - Cache-Control: no-store posé côté serveur (réponse non mise en cache).
 *
 * RÉUTILISÉ D'AFROBOOST : classes cr-* (createur.css), SvgIcon, var(--primary-color).
 * RÉUTILISÉ DE SPORDATEUR : structure 4 KPI cards + tableau filleuls (adapté).
 * ADAPTÉ : commission 40 % Hétaïra / 60 % Afroboost, espèces, anonymisation.
 */
import React, { useEffect, useState } from 'react';
import SvgIcon from '../SvgIcon';
import '../createur/createur.css';
import './partenaire.css';

function chf(val) {
  const n = typeof val === 'number' ? val : parseFloat(val) || 0;
  return n.toFixed(2) + ' CHF';
}

function dateAffichee(iso) {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    return d.toLocaleDateString('fr-CH', { day: 'numeric', month: 'short', year: 'numeric' });
  } catch (e) { return iso; }
}

function statutBadge(statut) {
  if (statut === 'paye') {
    return (
      <span className="pv-badge pv-badge--vert">
        <SvgIcon name="check" size={12} /> Confirmé
      </span>
    );
  }
  if (statut === 'rembourse') {
    return (
      <span className="pv-badge pv-badge--rouge">
        <SvgIcon name="arrowLeft" size={12} /> Remboursé
      </span>
    );
  }
  if (statut === 'paiement_sans_reservation') {
    return (
      <span className="pv-badge pv-badge--jaune">
        <SvgIcon name="warning" size={12} /> En attente
      </span>
    );
  }
  return (
    <span className="pv-badge pv-badge--gris">{statut || '—'}</span>
  );
}

function moyenBadge(moyen) {
  if (moyen === 'especes') {
    return (
      <span className="pv-badge pv-badge--mauve">
        <SvgIcon name="dollarSign" size={12} /> Espèces
      </span>
    );
  }
  return (
    <span className="pv-badge pv-badge--gris">
      <SvgIcon name="creditCard" size={12} /> En ligne
    </span>
  );
}

export default function PartnerView({ token }) {
  const [etat, setEtat] = useState('chargement'); // chargement | ok | erreur | expire
  const [data, setData] = useState(null);

  useEffect(() => {
    if (!token) { setEtat('erreur'); return; }
    const tok = token.replace(/[^A-Za-z0-9_-]/g, '');
    if (tok.length < 10) { setEtat('erreur'); return; }
    setEtat('chargement');
    fetch(`/api/partner/view/${encodeURIComponent(tok)}`, {
      headers: { 'Cache-Control': 'no-store' },
    })
      .then((r) => {
        if (r.status === 429) return Promise.reject(new Error('rate'));
        if (r.status === 404) return Promise.reject(new Error('expire'));
        if (!r.ok) return Promise.reject(new Error('erreur'));
        return r.json();
      })
      .then((d) => { setData(d); setEtat('ok'); })
      .catch((e) => {
        if (e.message === 'expire') setEtat('expire');
        else if (e.message === 'rate') setEtat('rate');
        else setEtat('erreur');
      });
  }, [token]);

  if (etat === 'chargement') {
    return (
      <div className="pv-root pv-centre" style={{ minHeight: '100vh' }}>
        <div className="pv-loader">
          <SvgIcon name="loader" size={32} />
        </div>
      </div>
    );
  }

  if (etat === 'expire' || etat === 'erreur') {
    return (
      <div className="pv-root pv-centre" style={{ minHeight: '100vh' }}>
        <div className="pv-erreur">
          <SvgIcon name="lock" size={40} />
          <h2 className="pv-erreur-titre">Lien non valide</h2>
          <p className="pv-erreur-texte">
            Ce lien de suivi a expiré ou n'est plus actif.<br />
            Contacte le coach pour obtenir un nouveau lien.
          </p>
        </div>
      </div>
    );
  }

  if (etat === 'rate') {
    return (
      <div className="pv-root pv-centre" style={{ minHeight: '100vh' }}>
        <div className="pv-erreur">
          <SvgIcon name="hourglass" size={40} />
          <h2 className="pv-erreur-titre">Trop de requêtes</h2>
          <p className="pv-erreur-texte">Patiente quelques instants puis actualise.</p>
        </div>
      </div>
    );
  }

  const t = data || {};
  const totaux = t.totaux || {};
  const lignes = Array.isArray(t.lignes) ? t.lignes : [];
  const confirmes = lignes.filter((l) => l.statut === 'paye' || l.statut === 'especes');
  const pct = typeof t.pct_partenaire === 'number' ? t.pct_partenaire : 40;
  const nomPartenaire = t.partner_name || 'Partenaire';
  const code = t.code || '';

  return (
    <div className="pv-root" style={{ minHeight: '100vh' }}>
      <div className="pv-contenu">

        {/* En-tête */}
        <div className="cr-entete">
          <h1 className="cr-titre" style={{ color: 'var(--primary-color, #D91CD2)' }}>
            {nomPartenaire}
          </h1>
          <p className="cr-sous">
            {code ? <>Suivi des inscriptions liées {code.includes(',') ? 'aux codes' : 'au code'} <strong style={{ color: '#fff' }}>{code}</strong>{' '}— </> : 'Commission '}
            <strong style={{ color: 'var(--primary-color, #D91CD2)' }}>{pct} %</strong>
          </p>
        </div>

        {/* KPI cards — pattern Creator Dashboard Afroboost */}
        <div className="cr-kpis">
          <div className="cr-kpi">
            <span className="cr-kpi-tete">
              <SvgIcon name="users" size={14} /> Inscriptions
            </span>
            <b className="cr-kpi-val">{totaux.nb_inscriptions || 0}</b>
          </div>
          <div className="cr-kpi">
            <span className="cr-kpi-tete">
              <SvgIcon name="check" size={14} /> Confirmées
            </span>
            <b className="cr-kpi-val">{confirmes.length}</b>
          </div>
          <div className="cr-kpi">
            <span className="cr-kpi-tete">
              <SvgIcon name="dollarSign" size={14} /> Net encaissé
            </span>
            <b className="cr-kpi-val cr-accent">{chf(totaux.total_net_chf)}</b>
          </div>
          <div className="cr-kpi">
            <span className="cr-kpi-tete">
              <SvgIcon name="trophy" size={14} /> Ta part ({pct} %)
            </span>
            <b className="cr-kpi-val cr-accent">{chf(totaux.part_partenaire_chf)}</b>
          </div>
        </div>

        {/* Tableau des inscriptions */}
        <div className="cr-carte">
          <h3 className="cr-h3">
            <SvgIcon name="fileText" size={16} /> Détail des inscriptions
          </h3>
          {lignes.length === 0 ? (
            <div className="pv-vide">
              <SvgIcon name="users" size={36} />
              <p>Aucune inscription pour le moment.</p>
            </div>
          ) : (
            <div className="pv-tableau">
              {lignes.map((l, i) => (
                <div key={l.session_id || `l-${i}`} className={`pv-ligne ${l.statut === 'rembourse' ? 'pv-ligne--grise' : ''}`}>
                  <div className="pv-ligne-gauche">
                    <span className="pv-nom">{l.nom_masque || '—'}</span>
                    <span className="pv-date">{dateAffichee(l.date_paiement || l.date_seance)}</span>
                  </div>
                  <div className="pv-ligne-droite">
                    <span className="pv-montant">
                      {l.statut !== 'rembourse' ? chf(l.montant_chf) : <s className="text-red-400">{chf(l.montant_chf)}</s>}
                    </span>
                    <div className="pv-badges">
                      {statutBadge(l.statut)}
                      {moyenBadge(l.moyen)}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Récapitulatif financier */}
        {totaux.total_net_chf > 0 && (
          <div className="cr-carte pv-recap">
            <h3 className="cr-h3">
              <SvgIcon name="barChart" size={16} /> Récapitulatif
            </h3>
            <div className="pv-recapligne">
              <span>Total encaissé</span>
              <strong>{chf(totaux.total_net_chf)}</strong>
            </div>
            <div className="pv-recapligne pv-recapligne--accent">
              <span>Votre part ({pct} %)</span>
              <strong>{chf(totaux.part_partenaire_chf)}</strong>
            </div>
            <div className="pv-recapligne pv-recapligne--muted">
              <span>Part Afroboost ({100 - pct} %)</span>
              <span>{chf(totaux.part_afroboost_chf)}</span>
            </div>
            {totaux.nb_rembourses > 0 && (
              <div className="pv-recapligne pv-recapligne--rouge">
                <span>Remboursements exclus</span>
                <span>{totaux.nb_rembourses} inscription{totaux.nb_rembourses > 1 ? 's' : ''}</span>
              </div>
            )}
          </div>
        )}

        {/* Bas de page */}
        <p className="pv-footer">
          Vue en lecture seule — fournie par Afroboost.
          Les montants sont indicatifs jusqu'au versement effectif.
        </p>
      </div>
    </div>
  );
}
