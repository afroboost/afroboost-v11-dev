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
import React, { useRef, useEffect, useState } from 'react';
import { QRCodeSVG } from 'qrcode.react';
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
  const [qrVisible, setQrVisible] = useState(null);
  const [copieInv, setCopieInv] = useState(null);
  const qrRefs = useRef({});

  function copierUrl(id, url) {
    navigator.clipboard.writeText(url).then(() => {
      setCopieInv(id); setTimeout(() => setCopieInv(null), 2500);
    }).catch(() => {});
  }

  function telechargerQR(id, titre) {
    const wrapper = qrRefs.current[id];
    if (!wrapper) return;
    const svg = wrapper.querySelector('svg');
    if (!svg) return;
    const svgData = new XMLSerializer().serializeToString(svg);
    const blob = new Blob([svgData], { type: 'image/svg+xml' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = `qr-${(titre || 'invitation').replace(/[^a-z0-9]/gi, '-').toLowerCase()}.svg`;
    a.click(); URL.revokeObjectURL(url);
  }

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

        {/* V639c — Inviter des participants */}
        {Array.isArray(t.invitations_publiques) && t.invitations_publiques.length > 0 && (
          <div className="cr-carte" style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <h3 className="cr-h3"><SvgIcon name="gift" size={16} /> Inviter des participants</h3>
            {t.invitations_publiques.map((inv, idx) => (
              <div key={idx} style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                <div style={{ fontSize: 14, fontWeight: 600 }}>{inv.title}</div>
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                  <button onClick={() => copierUrl(idx, inv.share_url)}
                          style={{ flex: 1, minWidth: 80, background: 'rgba(255,255,255,0.08)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: 8, color: '#fff', padding: '9px 12px', cursor: 'pointer', fontSize: 13, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6 }}>
                    <SvgIcon name="copy" size={14} /> {copieInv === idx ? 'Copié ✓' : 'Copier le lien'}
                  </button>
                  <a href={`https://wa.me/?text=${encodeURIComponent('Rejoins Afroboost : ' + inv.share_url)}`}
                     target="_blank" rel="noopener noreferrer"
                     style={{ flex: 1, minWidth: 80, background: 'rgba(37,211,102,0.12)', border: '1px solid rgba(37,211,102,0.25)', borderRadius: 8, color: '#86efac', padding: '9px 12px', fontSize: 13, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6, textDecoration: 'none' }}>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347z"/><path d="M12 0C5.373 0 0 5.373 0 12c0 2.136.562 4.134 1.541 5.869L.057 23.986l6.305-1.483A11.953 11.953 0 0012 24c6.627 0 12-5.373 12-12S18.627 0 12 0zm0 21.75a9.75 9.75 0 110-19.5 9.75 9.75 0 010 19.5z"/></svg>
                    WhatsApp
                  </a>
                  <button onClick={() => setQrVisible((v) => v === idx ? null : idx)}
                          style={{ flex: 1, minWidth: 80, background: 'rgba(255,255,255,0.08)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: 8, color: '#fff', padding: '9px 12px', cursor: 'pointer', fontSize: 13, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6 }}>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg>
                    QR code
                  </button>
                </div>
                {qrVisible === idx && (
                  <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10 }}>
                    <div ref={(el) => { qrRefs.current[idx] = el; }} style={{ background: '#fff', padding: 10, borderRadius: 8, display: 'inline-block' }}>
                      <QRCodeSVG value={inv.share_url} size={160} bgColor="#ffffff" fgColor="#1a0a1f" level="M" />
                    </div>
                    <button onClick={() => telechargerQR(idx, inv.title)}
                            style={{ background: 'rgba(255,255,255,0.08)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: 8, color: 'rgba(255,255,255,0.75)', padding: '8px 14px', cursor: 'pointer', fontSize: 12, display: 'flex', alignItems: 'center', gap: 5 }}>
                      <SvgIcon name="download" size={13} /> Télécharger le QR
                    </button>
                  </div>
                )}
              </div>
            ))}
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
