/**
 * V638 — GESTION MULTI-PARTENAIRES (coach dashboard).
 *
 * Affiche la liste des partenaires du coach, permet de les créer / modifier /
 * supprimer, générer / révoquer leur lien public et déclarer des espèces.
 *
 * RÈGLES UX Afroboost (V597) :
 * - Au plus 2 actions visibles par carte, le reste dans un drawer.
 * - Les éditeurs s'ouvrent en modal, jamais en ligne.
 * - Aucune couleur codée en dur — var(--primary-color, #D91CD2).
 * - SVG inline uniquement — aucun emoji.
 *
 * SÉCURITÉ :
 * - Toutes les requêtes portent le JWT du coach (Authorization: Bearer …).
 * - La vue partenaire (publique) est sur /partenaire/{token}.
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import SvgIcon from '../SvgIcon';

// ─── Helpers ─────────────────────────────────────────────────────────────────

function chf(val) {
  const n = typeof val === 'number' ? val : parseFloat(val) || 0;
  return n.toFixed(2) + ' CHF';
}

function apiHeaders() {
  const jwt = localStorage.getItem('afroboost_jwt') || '';
  const email = localStorage.getItem('afroboost_identity') || '';
  const h = { 'Content-Type': 'application/json' };
  if (jwt) h['Authorization'] = `Bearer ${jwt}`;
  if (email) h['X-User-Email'] = email;
  return h;
}

async function apiFetch(path, opts = {}) {
  const r = await fetch(path, { ...opts, headers: apiHeaders() });
  if (!r.ok) {
    const msg = await r.text().catch(() => r.statusText);
    throw new Error(`${r.status}: ${msg.slice(0, 200)}`);
  }
  return r.json();
}

function lienPartenaire(token) {
  return `${window.location.origin}/partenaire/${token}`;
}

// ─── Modal générique ──────────────────────────────────────────────────────────

function Modal({ titre, onClose, children }) {
  const overlayRef = useRef();
  useEffect(() => {
    function onKey(e) { if (e.key === 'Escape') onClose(); }
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <div
      ref={overlayRef}
      onClick={(e) => { if (e.target === overlayRef.current) onClose(); }}
      style={{
        position: 'fixed', inset: 0,
        background: 'rgba(0,0,0,0.75)',
        display: 'flex', alignItems: 'flex-start', justifyContent: 'center',
        zIndex: 1200, overflowY: 'auto', padding: '24px 16px 40px',
      }}
    >
      <div style={{
        background: '#111', border: '1px solid rgba(255,255,255,0.08)',
        borderRadius: 16, width: '100%', maxWidth: 560,
        padding: '24px 20px', display: 'flex', flexDirection: 'column', gap: 16,
        color: 'rgba(255,255,255,0.9)',
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h3 style={{ margin: 0, fontSize: 18, fontWeight: 700, color: '#fff' }}>{titre}</h3>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'rgba(255,255,255,0.4)', padding: 4 }}>
            <SvgIcon name="x" size={20} />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

// ─── Formulaire partenaire ────────────────────────────────────────────────────

// V639 : sélecteur multi-valeurs (codes promo ou liens intelligents)
function SelecteurMulti({ items, selected, onToggle, labelKey, valueKey, autresPartenaires, currentPartnerId }) {
  if (!items || items.length === 0) {
    return <p style={{ fontSize: 12, color: 'rgba(255,255,255,0.3)', margin: '4px 0 0' }}>Aucun élément disponible.</p>;
  }
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 6 }}>
      {items.map((item) => {
        const val = item[valueKey];
        const label = item[labelKey] || val;
        const isSelected = selected.includes(val);
        // Détecter si un autre partenaire utilise déjà cet item
        const conflit = (autresPartenaires || []).find((p) =>
          p.id !== currentPartnerId &&
          (p.codes || []).concat(p.invitation_ids || []).includes(val)
        );
        return (
          <button
            key={val}
            type="button"
            onClick={() => onToggle(val)}
            title={conflit ? `Déjà utilisé par : ${conflit.name}` : ''}
            style={{
              padding: '5px 12px',
              borderRadius: 20,
              border: isSelected
                ? '1.5px solid var(--primary-color,#D91CD2)'
                : conflit
                  ? '1.5px solid #f59e0b'
                  : '1px solid rgba(255,255,255,0.15)',
              background: isSelected
                ? 'rgba(var(--primary-rgb,217,28,210),0.15)'
                : 'rgba(255,255,255,0.04)',
              color: isSelected ? 'var(--primary-color,#D91CD2)' : conflit ? '#f59e0b' : 'rgba(255,255,255,0.8)',
              fontSize: 13,
              cursor: 'pointer',
              fontWeight: isSelected ? 600 : 400,
              display: 'flex', alignItems: 'center', gap: 5,
            }}
          >
            {conflit && !isSelected && (
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/>
                <line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
              </svg>
            )}
            {label}
          </button>
        );
      })}
    </div>
  );
}

function FormulairePartenaire({ initial, allCodes, allLinks, autresPartenaires, onSave, onCancel, chargement }) {
  const currentPartnerId = initial?.id || null;
  const [nom, setNom] = useState(initial?.name || '');
  const [pct, setPct] = useState(initial?.pct ?? 40);
  const [selectedCodes, setSelectedCodes] = useState(initial?.codes || []);
  const [selectedInvs, setSelectedInvs] = useState(initial?.invitation_ids || []);
  const [err, setErr] = useState('');

  function toggleCode(val) {
    setSelectedCodes((prev) => prev.includes(val) ? prev.filter((c) => c !== val) : [...prev, val]);
  }
  function toggleInv(val) {
    setSelectedInvs((prev) => prev.includes(val) ? prev.filter((i) => i !== val) : [...prev, val]);
  }

  function handleSave() {
    if (!nom.trim()) { setErr('Le nom est requis.'); return; }
    const p = parseInt(pct, 10);
    if (isNaN(p) || p < 0 || p > 100) { setErr('Le pourcentage doit être entre 0 et 100.'); return; }
    setErr('');
    onSave({ name: nom.trim(), pct: p, codes: selectedCodes, invitation_ids: selectedInvs });
  }

  const inputStyle = {
    background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.12)',
    borderRadius: 8, color: '#fff', padding: '10px 12px', width: '100%', fontSize: 14,
    boxSizing: 'border-box',
  };
  const labelStyle = { fontSize: 12, color: 'rgba(255,255,255,0.5)', marginBottom: 4, display: 'block' };
  const sectionStyle = { background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.07)', borderRadius: 10, padding: '12px 14px' };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div>
        <label style={labelStyle}>Nom du partenaire *</label>
        <input value={nom} onChange={(e) => setNom(e.target.value)} style={inputStyle} placeholder="ex. Société Hétaïra" />
      </div>
      <div>
        <label style={labelStyle}>Commission partenaire (%) *</label>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <input type="number" min="0" max="100" value={pct} onChange={(e) => setPct(e.target.value)} style={{ ...inputStyle, maxWidth: 100 }} />
          <span style={{ fontSize: 13, color: 'rgba(255,255,255,0.5)' }}>
            → Afroboost garde <strong style={{ color: '#fff' }}>{100 - (parseInt(pct, 10) || 0)} %</strong>
          </span>
        </div>
      </div>
      <div style={sectionStyle}>
        <label style={labelStyle}>
          Codes promo associés
          {selectedCodes.length > 0 && <span style={{ color: 'var(--primary-color,#D91CD2)', marginLeft: 6 }}>({selectedCodes.length} sélectionné{selectedCodes.length > 1 ? 's' : ''})</span>}
        </label>
        <SelecteurMulti
          items={(allCodes || []).map((c) => ({ value: c.code, label: c.code }))}
          selected={selectedCodes}
          onToggle={toggleCode}
          labelKey="label"
          valueKey="value"
          autresPartenaires={autresPartenaires}
          currentPartnerId={currentPartnerId}
        />
        {(!allCodes || allCodes.length === 0) && (
          <p style={{ fontSize: 12, color: 'rgba(255,255,255,0.3)', margin: '4px 0 0' }}>Chargement des codes…</p>
        )}
      </div>
      <div style={sectionStyle}>
        <label style={labelStyle}>
          Liens intelligents associés
          {selectedInvs.length > 0 && <span style={{ color: 'var(--primary-color,#D91CD2)', marginLeft: 6 }}>({selectedInvs.length} sélectionné{selectedInvs.length > 1 ? 's' : ''})</span>}
        </label>
        <SelecteurMulti
          items={(allLinks || []).map((l) => ({ value: l.id, label: l.title || l.link_token || l.id }))}
          selected={selectedInvs}
          onToggle={toggleInv}
          labelKey="label"
          valueKey="value"
          autresPartenaires={autresPartenaires}
          currentPartnerId={currentPartnerId}
        />
        {(!allLinks || allLinks.length === 0) && (
          <p style={{ fontSize: 12, color: 'rgba(255,255,255,0.3)', margin: '4px 0 0' }}>Chargement des liens…</p>
        )}
      </div>
      {err && <p style={{ color: '#f87171', fontSize: 13, margin: 0 }}>{err}</p>}
      <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
        <button onClick={onCancel} disabled={chargement} style={{ background: 'rgba(255,255,255,0.07)', border: 'none', borderRadius: 8, color: 'rgba(255,255,255,0.7)', padding: '9px 18px', cursor: 'pointer', fontSize: 14 }}>
          Annuler
        </button>
        <button onClick={handleSave} disabled={chargement} style={{ background: 'var(--primary-color,#D91CD2)', border: 'none', borderRadius: 8, color: '#fff', padding: '9px 18px', cursor: chargement ? 'wait' : 'pointer', fontSize: 14, fontWeight: 600, opacity: chargement ? 0.6 : 1 }}>
          {chargement ? 'Enregistrement…' : initial ? 'Mettre à jour' : 'Créer'}
        </button>
      </div>
    </div>
  );
}

// ─── Modal détails d'un partenaire ───────────────────────────────────────────

function DetailsPartenaire({ partner, onClose, onUpdated, allCodes, allLinks, autresPartenaires }) {
  const [details, setDetails] = useState(null);
  const [chargement, setChargement] = useState(true);
  const [err, setErr] = useState('');
  const [copie, setCopie] = useState(false);
  const [editeur, setEditeur] = useState(false);
  const [especes, setEspeces] = useState(false);
  const [frm, setFrm] = useState({ prenom: '', nom: '', date: '', montant: '' });
  const [frmErr, setFrmErr] = useState('');
  const [frmOk, setFrmOk] = useState(false);

  const charger = useCallback(async () => {
    setChargement(true); setErr('');
    try {
      const d = await apiFetch(`/api/partner/partners/${partner.id}/details`);
      setDetails(d);
    } catch (e) { setErr(e.message); }
    finally { setChargement(false); }
  }, [partner.id]);

  useEffect(() => { charger(); }, [charger]);

  async function genererLien() {
    try {
      const r = await apiFetch(`/api/partner/partners/${partner.id}/generate-token`, { method: 'POST' });
      await charger();
      if (onUpdated) onUpdated();
      const url = lienPartenaire(r.token);
      try { await navigator.clipboard.writeText(url); setCopie(true); setTimeout(() => setCopie(false), 2500); } catch (_) {}
    } catch (e) { alert('Erreur : ' + e.message); }
  }

  async function revoquerLien() {
    if (!window.confirm('Révoquer ce lien ? Le partenaire n\'aura plus accès jusqu\'à la génération d\'un nouveau lien.')) return;
    try {
      await apiFetch(`/api/partner/partners/${partner.id}/revoke-token`, { method: 'DELETE' });
      await charger();
      if (onUpdated) onUpdated();
    } catch (e) { alert('Erreur : ' + e.message); }
  }

  async function copierLienActuel() {
    if (!details?.lien_actif) return;
    // On régénère pour obtenir le token (le serveur ne le stocke pas en clair)
    // Donc on génère un nouveau token = révoque l'ancien
    await genererLien();
  }

  async function sauvegarderEspeces() {
    setFrmErr(''); setFrmOk(false);
    if (!frm.prenom.trim() || !frm.nom.trim() || !frm.date || !frm.montant) {
      setFrmErr('Tous les champs sont requis.'); return;
    }
    const montant = parseFloat(frm.montant);
    if (isNaN(montant) || montant <= 0) { setFrmErr('Montant invalide.'); return; }
    try {
      const key = `${partner.id}:${Date.now()}`;
      await apiFetch(`/api/partner/partners/${partner.id}/cash`, {
        method: 'POST',
        body: JSON.stringify({ prenom: frm.prenom.trim(), nom: frm.nom.trim(), date_seance: frm.date, montant_chf: montant, idempotence_key: key }),
      });
      setFrmOk(true); setFrm({ prenom: '', nom: '', date: '', montant: '' });
      await charger();
    } catch (e) { setFrmErr(e.message); }
  }

  const t = details?.totaux || {};
  const lignes = details?.lignes || [];
  const pct = details?.pct_partenaire ?? partner.pct;

  return (
    <Modal titre={partner.name} onClose={onClose}>
      {chargement && !details && (
        <div style={{ textAlign: 'center', padding: 24, color: 'rgba(255,255,255,0.4)' }}>
          <SvgIcon name="loader" size={28} />
        </div>
      )}
      {err && <p style={{ color: '#f87171', fontSize: 13 }}>{err}</p>}
      {details && (
        <>
          {/* KPI */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2,1fr)', gap: 8 }}>
            {[
              { label: 'Inscriptions', val: t.nb_inscriptions ?? '—', icon: 'users' },
              { label: 'Confirmées', val: t.nb_confirmes ?? '—', icon: 'check' },
              { label: 'Net encaissé', val: chf(t.total_net_chf), icon: 'dollarSign', accent: true },
              { label: `Part (${pct} %)`, val: chf(t.part_partenaire_chf), icon: 'trophy', accent: true },
            ].map(({ label, val, icon, accent }) => (
              <div key={label} style={{ background: 'rgba(255,255,255,0.04)', borderRadius: 10, padding: '10px 12px' }}>
                <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.4)', display: 'flex', alignItems: 'center', gap: 4, marginBottom: 4 }}>
                  <SvgIcon name={icon} size={12} /> {label}
                </div>
                <div style={{ fontSize: 18, fontWeight: 700, color: accent ? 'var(--primary-color,#D91CD2)' : '#fff' }}>{val}</div>
              </div>
            ))}
          </div>

          {/* Conflit */}
          {t.nb_paiements_sans_reservation > 0 && (
            <div style={{ background: 'rgba(234,179,8,0.12)', borderRadius: 8, padding: '10px 12px', fontSize: 13, color: '#fde047', display: 'flex', gap: 8, alignItems: 'flex-start' }}>
              <SvgIcon name="warning" size={16} style={{ flexShrink: 0, marginTop: 1 }} />
              <span>{t.nb_paiements_sans_reservation} paiement{t.nb_paiements_sans_reservation > 1 ? 's' : ''} sans réservation confirmée (statut « en attente »). Vérifier dans les transactions.</span>
            </div>
          )}

          {/* Lien partenaire */}
          <div style={{ background: 'rgba(255,255,255,0.03)', borderRadius: 10, padding: '12px 14px', display: 'flex', flexDirection: 'column', gap: 8 }}>
            <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.45)', display: 'flex', alignItems: 'center', gap: 5 }}>
              <SvgIcon name="link" size={13} /> Lien partenaire
              {details.lien_actif
                ? <span style={{ marginLeft: 'auto', background: 'rgba(34,197,94,0.15)', color: '#86efac', borderRadius: 100, padding: '2px 8px', fontSize: 11 }}>Actif</span>
                : <span style={{ marginLeft: 'auto', background: 'rgba(255,255,255,0.06)', color: 'rgba(255,255,255,0.35)', borderRadius: 100, padding: '2px 8px', fontSize: 11 }}>Inactif</span>}
            </div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              <button onClick={genererLien} style={{ flex: 1, background: 'var(--primary-color,#D91CD2)', border: 'none', borderRadius: 8, color: '#fff', padding: '9px 14px', cursor: 'pointer', fontSize: 13, fontWeight: 600, minWidth: 140 }}>
                <SvgIcon name="link" size={14} style={{ marginRight: 5 }} />
                {details.lien_actif ? (copie ? 'Lien copié ✓' : 'Nouveau lien') : 'Générer un lien'}
              </button>
              {details.lien_actif && (
                <button onClick={revoquerLien} style={{ background: 'rgba(239,68,68,0.12)', border: '1px solid rgba(239,68,68,0.25)', borderRadius: 8, color: '#fca5a5', padding: '9px 14px', cursor: 'pointer', fontSize: 13, minWidth: 80 }}>
                  <SvgIcon name="x" size={14} style={{ marginRight: 4 }} /> Révoquer
                </button>
              )}
            </div>
            <p style={{ margin: 0, fontSize: 11, color: 'rgba(255,255,255,0.3)', lineHeight: 1.5 }}>
              Générer un nouveau lien révoque automatiquement l'ancien.
            </p>
          </div>

          {/* Déclarer espèces */}
          <button onClick={() => setEspeces((v) => !v)} style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: 8, color: 'rgba(255,255,255,0.7)', padding: '9px 14px', cursor: 'pointer', fontSize: 13, display: 'flex', alignItems: 'center', gap: 6, width: '100%' }}>
            <SvgIcon name="dollarSign" size={15} />
            {especes ? 'Masquer' : 'Déclarer un paiement en espèces'}
          </button>
          {especes && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10, padding: '2px 0' }}>
              {[
                { key: 'prenom', label: 'Prénom', type: 'text', ph: 'Alice' },
                { key: 'nom', label: 'Nom', type: 'text', ph: 'Martin' },
                { key: 'date', label: 'Date de la séance', type: 'date', ph: '' },
                { key: 'montant', label: 'Montant CHF', type: 'number', ph: '30' },
              ].map(({ key, label, type, ph }) => (
                <div key={key}>
                  <label style={{ fontSize: 12, color: 'rgba(255,255,255,0.45)', display: 'block', marginBottom: 3 }}>{label}</label>
                  <input type={type} value={frm[key]} placeholder={ph}
                    onChange={(e) => setFrm((f) => ({ ...f, [key]: e.target.value }))}
                    style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 7, color: '#fff', padding: '8px 11px', width: '100%', fontSize: 13, boxSizing: 'border-box' }}
                  />
                </div>
              ))}
              {frmErr && <p style={{ color: '#f87171', fontSize: 12, margin: 0 }}>{frmErr}</p>}
              {frmOk && <p style={{ color: '#86efac', fontSize: 12, margin: 0 }}>Paiement enregistré ✓</p>}
              <button onClick={sauvegarderEspeces} style={{ background: 'rgba(255,255,255,0.08)', border: 'none', borderRadius: 8, color: '#fff', padding: '9px 14px', cursor: 'pointer', fontSize: 13, alignSelf: 'flex-start' }}>
                Enregistrer
              </button>
            </div>
          )}

          {/* Tableau des inscriptions */}
          {lignes.length > 0 && (
            <div>
              <p style={{ fontSize: 12, color: 'rgba(255,255,255,0.4)', margin: '0 0 8px', fontWeight: 600 }}>
                {lignes.length} inscription{lignes.length > 1 ? 's' : ''}
              </p>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {lignes.slice(0, 20).map((l, i) => (
                  <div key={l.session_id || i} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '8px 10px', background: 'rgba(255,255,255,0.03)', borderRadius: 8, gap: 8 }}>
                    <div>
                      <p style={{ margin: 0, fontSize: 13, fontWeight: 600 }}>{l.nom || '—'}</p>
                      <p style={{ margin: 0, fontSize: 11, color: 'rgba(255,255,255,0.35)' }}>
                        {l.date_seance ? new Date(l.date_seance).toLocaleDateString('fr-CH') : '—'} · {l.moyen || '—'}
                      </p>
                    </div>
                    <div style={{ textAlign: 'right' }}>
                      <p style={{ margin: 0, fontSize: 14, fontWeight: 700 }}>{chf(l.montant_chf)}</p>
                      <p style={{ margin: 0, fontSize: 11, color: l.statut === 'paye' ? '#86efac' : l.statut === 'rembourse' ? '#fca5a5' : '#fde047' }}>
                        {l.statut === 'paye' ? 'Confirmé' : l.statut === 'rembourse' ? 'Remboursé' : 'En attente'}
                      </p>
                    </div>
                  </div>
                ))}
                {lignes.length > 20 && <p style={{ fontSize: 12, color: 'rgba(255,255,255,0.3)', textAlign: 'center', margin: 4 }}>… {lignes.length - 20} autres — exporter le CSV pour voir tout</p>}
              </div>
            </div>
          )}

          {/* Bas de modal : export CSV + modifier */}
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 4 }}>
            <a href={`/api/partner/partners/${partner.id}/export.csv`} download style={{ flex: 1, textDecoration: 'none', background: 'rgba(255,255,255,0.06)', borderRadius: 8, color: 'rgba(255,255,255,0.7)', padding: '9px 14px', fontSize: 13, textAlign: 'center', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 5 }}>
              <SvgIcon name="download" size={14} /> Exporter CSV
            </a>
            <button onClick={() => setEditeur(true)} style={{ flex: 1, background: 'rgba(255,255,255,0.06)', border: 'none', borderRadius: 8, color: 'rgba(255,255,255,0.7)', padding: '9px 14px', cursor: 'pointer', fontSize: 13, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 5 }}>
              <SvgIcon name="edit" size={14} /> Modifier
            </button>
          </div>
        </>
      )}

      {editeur && (
        <Modal titre={`Modifier — ${partner.name}`} onClose={() => setEditeur(false)}>
          <FormulairePartenaire
            initial={details}
            allCodes={allCodes}
            allLinks={allLinks}
            autresPartenaires={autresPartenaires}
            onCancel={() => setEditeur(false)}
            onSave={async (data) => {
              try {
                await apiFetch(`/api/partner/partners/${partner.id}`, { method: 'PUT', body: JSON.stringify(data) });
                setEditeur(false);
                await charger();
                if (onUpdated) onUpdated();
              } catch (e) { alert('Erreur : ' + e.message); }
            }}
          />
        </Modal>
      )}
    </Modal>
  );
}

// ─── Alerte conflits ──────────────────────────────────────────────────────────

function AlerteConflits({ conflits }) {
  const [ouvert, setOuvert] = useState(false);
  if (!conflits || conflits.length === 0) return null;
  return (
    <div style={{ background: 'rgba(234,179,8,0.1)', border: '1px solid rgba(234,179,8,0.25)', borderRadius: 10, padding: '12px 14px', marginBottom: 16 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', userSelect: 'none' }} onClick={() => setOuvert((v) => !v)}>
        <SvgIcon name="warning" size={16} style={{ color: '#fde047' }} />
        <span style={{ fontSize: 13, fontWeight: 600, color: '#fde047' }}>
          {conflits.length} conflit{conflits.length > 1 ? 's' : ''} détecté{conflits.length > 1 ? 's' : ''} entre partenaires
        </span>
        <SvgIcon name={ouvert ? 'chevronUp' : 'chevronDown'} size={14} style={{ marginLeft: 'auto', color: 'rgba(255,255,255,0.4)' }} />
      </div>
      {ouvert && (
        <div style={{ marginTop: 10, display: 'flex', flexDirection: 'column', gap: 6 }}>
          {conflits.map((cf) => (
            <div key={cf.session_id} style={{ fontSize: 12, color: 'rgba(255,255,255,0.6)', padding: '6px 8px', background: 'rgba(255,255,255,0.04)', borderRadius: 6 }}>
              Session <code style={{ color: '#fde047' }}>{cf.session_id}</code> revendiquée par :{' '}
              {cf.partenaires.map((p) => p.name).join(' et ')}
              <span style={{ color: 'rgba(255,255,255,0.35)', marginLeft: 6 }}>— montant non réparti, action requise.</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ─── Composant principal ──────────────────────────────────────────────────────

export default function PartnersSection() {
  const [partenaires, setPartenaires] = useState([]);
  const [conflits, setConflits] = useState([]);
  const [chargement, setChargement] = useState(true);
  const [err, setErr] = useState('');
  const [creation, setCreation] = useState(false);
  const [details, setDetails] = useState(null);
  const [creOk, setCreOk] = useState(false);
  // V639 : options pour le formulaire
  const [allCodes, setAllCodes] = useState([]);
  const [allLinks, setAllLinks] = useState([]);

  const charger = useCallback(async () => {
    setChargement(true); setErr('');
    try {
      const [r1, r2] = await Promise.all([
        apiFetch('/api/partner/partners'),
        apiFetch('/api/partner/partners/conflicts').catch(() => ({ conflits: [] })),
      ]);
      setPartenaires(r1.partenaires || []);
      setConflits(r2.conflits || []);
    } catch (e) { setErr(e.message); }
    finally { setChargement(false); }
  }, []);

  // V639 : charger les codes et liens intelligents une seule fois
  useEffect(() => {
    Promise.all([
      apiFetch('/api/discount-codes').catch(() => []),
      apiFetch('/api/chat/links').catch(() => []),
    ]).then(([codes, links]) => {
      setAllCodes(Array.isArray(codes) ? codes : []);
      setAllLinks(Array.isArray(links) ? links : []);
    });
  }, []);

  useEffect(() => { charger(); }, [charger]);

  async function creerPartenaire(data) {
    setCreOk(false);
    try {
      await apiFetch('/api/partner/partners', { method: 'POST', body: JSON.stringify(data) });
      setCreation(false); setCreOk(true);
      await charger();
      setTimeout(() => setCreOk(false), 3000);
    } catch (e) { alert('Erreur : ' + e.message); }
  }

  async function supprimerPartenaire(p) {
    if (!window.confirm(`Supprimer le partenaire « ${p.name} » ? Les données historiques seront conservées.`)) return;
    try {
      await apiFetch(`/api/partner/partners/${p.id}`, { method: 'DELETE' });
      await charger();
    } catch (e) { alert('Erreur : ' + e.message); }
  }

  if (chargement) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: 120, color: 'var(--primary-color,#D91CD2)' }}>
        <SvgIcon name="loader" size={28} />
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>

      {/* En-tête */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 10 }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 20, fontWeight: 700, color: '#fff' }}>Partenaires</h2>
          <p style={{ margin: '3px 0 0', fontSize: 13, color: 'rgba(255,255,255,0.4)' }}>
            Suivi des revenus et liens partenaires
          </p>
        </div>
        <button
          onClick={() => setCreation(true)}
          style={{ background: 'var(--primary-color,#D91CD2)', border: 'none', borderRadius: 10, color: '#fff', padding: '10px 18px', cursor: 'pointer', fontSize: 14, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 7 }}
        >
          <SvgIcon name="plus" size={16} /> Nouveau partenaire
        </button>
      </div>

      {err && <p style={{ color: '#f87171', fontSize: 13, background: 'rgba(239,68,68,0.08)', padding: '10px 14px', borderRadius: 8, margin: 0 }}>{err}</p>}
      {creOk && <p style={{ color: '#86efac', fontSize: 13, background: 'rgba(34,197,94,0.08)', padding: '10px 14px', borderRadius: 8, margin: 0 }}>Partenaire créé ✓</p>}

      {/* Alertes conflits */}
      <AlerteConflits conflits={conflits} />

      {/* Liste des partenaires */}
      {partenaires.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '40px 0', color: 'rgba(255,255,255,0.3)' }}>
          <SvgIcon name="users" size={40} style={{ opacity: 0.2 }} />
          <p style={{ marginTop: 12, fontSize: 14 }}>Aucun partenaire pour l'instant.</p>
          <p style={{ fontSize: 13, marginTop: 4 }}>Crée le premier en cliquant sur « Nouveau partenaire ».</p>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {partenaires.map((p) => (
            <div key={p.id} style={{ background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.07)', borderRadius: 12, padding: '14px 16px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 3, minWidth: 0, flex: 1 }}>
                <span style={{ fontWeight: 700, fontSize: 15, color: '#fff' }}>{p.name}</span>
                <span style={{ fontSize: 12, color: 'rgba(255,255,255,0.4)' }}>
                  {p.pct} % — codes : {(p.codes || []).join(', ') || <em>aucun</em>}
                </span>
              </div>
              <div style={{ display: 'flex', gap: 8 }}>
                <button
                  onClick={() => setDetails(p)}
                  style={{ background: 'var(--primary-color,#D91CD2)', border: 'none', borderRadius: 8, color: '#fff', padding: '8px 14px', cursor: 'pointer', fontSize: 13, fontWeight: 600 }}
                >
                  <SvgIcon name="barChart" size={14} style={{ marginRight: 4 }} /> Détails
                </button>
                <button
                  onClick={() => supprimerPartenaire(p)}
                  title="Supprimer ce partenaire"
                  style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: 8, color: 'rgba(255,255,255,0.4)', padding: '8px 10px', cursor: 'pointer', fontSize: 13 }}
                >
                  <SvgIcon name="trash" size={14} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Modal création */}
      {creation && (
        <Modal titre="Créer un partenaire" onClose={() => setCreation(false)}>
          <FormulairePartenaire
            allCodes={allCodes}
            allLinks={allLinks}
            autresPartenaires={partenaires}
            onCancel={() => setCreation(false)}
            onSave={creerPartenaire}
          />
        </Modal>
      )}

      {/* Modal détails */}
      {details && (
        <DetailsPartenaire
          partner={details}
          onClose={() => setDetails(null)}
          onUpdated={charger}
          allCodes={allCodes}
          allLinks={allLinks}
          autresPartenaires={partenaires.filter((p) => p.id !== details.id)}
        />
      )}
    </div>
  );
}
