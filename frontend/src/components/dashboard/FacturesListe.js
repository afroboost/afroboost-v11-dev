// V657 : liste des documents du Générateur de factures (filtre Type) + coordonnées Entreprise vérifiées.
// Un seul système de factures : tout vient de GET /api/invoices (collection `invoices`).
import React, { useCallback, useEffect, useState } from 'react';
import SvgIcon from '../SvgIcon';
import { appel, telechargerPdf, messageErreur, chf, dateCh, STATUT_FACTURE, carte, champ, boutonSecondaire, boutonPrincipal, pastille } from './corporateApi';

const CoordonneesFacturation = ({ email }) => {
  const [ouvert, setOuvert] = useState(false);
  const [f, setF] = useState(null);
  const [msg, setMsg] = useState('');
  useEffect(() => {
    if (!ouvert || f) return;
    appel('/invoices/reglages-facturation', { email }).then(r => setF(r.ok ? (r.data || {}) : {}));
  }, [ouvert, f, email]);
  const enregistrer = async (verifie) => {
    setMsg('');
    const r = await appel('/invoices/reglages-facturation', { method: 'PUT', email, body: { ...f, verifie } });
    if (r.ok) { setF(r.data); setMsg(verifie ? 'Coordonnées enregistrées et vérifiées.' : 'Enregistré (non vérifié).'); } else setMsg(messageErreur(r));
  };
  return (
    <div style={carte} data-testid="corp-coordonnees">
      <button type="button" onClick={() => setOuvert(!ouvert)} style={{ ...boutonSecondaire, border: 'none', padding: 0 }}>
        <SvgIcon name="lock" size={14} /> Coordonnées de facturation Entreprise
        {f && <span style={pastille(f.verifie ? 'ok' : 'alerte')}>{f.verifie ? 'Vérifiées' : 'Non vérifiées'}</span>}
      </button>
      {ouvert && f && (
        <div style={{ marginTop: 10 }}>
          <p style={{ color: 'rgba(255,255,255,0.6)', fontSize: 12, margin: '0 0 8px' }}>
            Utilisées UNIQUEMENT pour les devis et factures Entreprise. Aucune n'est émise tant qu'elles ne sont pas vérifiées. Aucune TVA n'est ajoutée.
          </p>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 8 }}>
            {[['nom', 'Nom de l’émetteur'], ['adresse', 'Adresse'], ['ville', 'NPA et ville'], ['iban', 'IBAN'], ['contact', 'Contact'], ['ide', 'N° IDE (facultatif)']].map(([k, l]) => (
              <input key={k} aria-label={l} placeholder={l} value={f[k] || ''} style={champ}
                onChange={e => { const v = e.target.value; setF(p => ({ ...p, [k]: v, verifie: false })); }} />
            ))}
          </div>
          <div style={{ display: 'flex', gap: 8, marginTop: 8, flexWrap: 'wrap' }}>
            <button type="button" style={boutonPrincipal} onClick={() => enregistrer(true)} data-testid="corp-coordonnees-verifier">J’ai vérifié ces coordonnées</button>
            <button type="button" style={boutonSecondaire} onClick={() => enregistrer(false)}>Enregistrer sans valider</button>
          </div>
          {msg && <p style={{ color: 'rgba(255,255,255,0.75)', fontSize: 12, marginTop: 6 }}>{msg}</p>}
        </div>
      )}
    </div>
  );
};

const LigneFacture = ({ x, email, onMaj }) => {
  const [details, setDetails] = useState(false);
  const [paiement, setPaiement] = useState({ montant: '', mode: 'virement', date: '', reference: '' });
  const [msg, setMsg] = useState('');
  const corp = x.type === 'corporate';
  const reste = Math.max(0, Number(x.total || 0) - Number(x.montant_paye || 0));
  const payer = async () => {
    setMsg('');
    const r = await appel(`/invoices/${encodeURIComponent(x.invoice_number)}/paiement`, { method: 'POST', email, body: paiement });
    if (r.ok) { setMsg('Paiement enregistré.'); setPaiement({ montant: '', mode: 'virement', date: '', reference: '' }); onMaj(); } else setMsg(messageErreur(r));
  };
  return (
    <div style={carte} data-testid="facture-ligne">
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
        <div style={{ minWidth: 0 }}>
          <div style={{ color: '#fff', fontWeight: 600, fontSize: 13 }}>
            {x.invoice_number} {x.type_document === 'devis' && <span style={pastille()}>Devis</span>}
          </div>
          <div style={{ color: 'rgba(255,255,255,0.6)', fontSize: 12 }}>
            {corp ? (x.contrat?.entreprise || x.entreprise || '—') : ((x.recipient && x.recipient.name) || '—')} · {chf(x.total)}
          </div>
        </div>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          {x.statut && <span style={pastille(x.statut === 'payee' ? 'ok' : x.statut === 'emise' ? 'alerte' : '')}>{STATUT_FACTURE[x.statut] || x.statut}</span>}
          <button type="button" style={boutonSecondaire} aria-label="Télécharger le PDF"
            onClick={() => telechargerPdf(`/invoices/${encodeURIComponent(x.invoice_number)}/pdf`, { email })}>
            <SvgIcon name="download" size={14} />
          </button>
          {corp && (
            <button type="button" style={boutonSecondaire} aria-label="Détails" onClick={() => setDetails(!details)}>
              <SvgIcon name="moreHorizontal" size={14} />
            </button>
          )}
        </div>
      </div>
      {details && corp && (
        <div style={{ marginTop: 10, fontSize: 12, color: 'rgba(255,255,255,0.75)', display: 'grid', gap: 4 }}>
          <div>Contrat : {x.contrat ? `${x.contrat.places} places · ${x.contrat.duree_mois} mois · ${chf(x.contrat.prix_mensuel)}/mois · total ${chf(x.contrat.total)}` : '—'}</div>
          <div>Émise le {x.date || '—'}{x.echeance ? ` · échéance ${dateCh(x.echeance)}` : ''}{x.mois ? ` · édition ${x.mois}` : ''}</div>
          {x.type_document === 'facture' && <div>Payé {chf(x.montant_paye)} · reste {chf(reste)}</div>}
          <div>Dernier rappel : {x.dernier_rappel ? dateCh(x.dernier_rappel) : 'aucun'}</div>
          {x.type_document === 'facture' && x.statut === 'emise' && (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))', gap: 6, marginTop: 6 }}>
              <input style={champ} type="number" min="0" step="0.01" placeholder="Montant reçu" aria-label="Montant reçu" value={paiement.montant} onChange={e => { const v = e.target.value; setPaiement(p => ({ ...p, montant: v })); }} />
              <select style={champ} aria-label="Moyen" value={paiement.mode} onChange={e => { const v = e.target.value; setPaiement(p => ({ ...p, mode: v })); }}>
                <option value="virement">Virement</option><option value="twint">TWINT</option><option value="especes">Espèces</option>
              </select>
              <input style={champ} type="date" aria-label="Date du paiement" value={paiement.date} onChange={e => { const v = e.target.value; setPaiement(p => ({ ...p, date: v })); }} />
              <input style={champ} placeholder="Référence" aria-label="Référence" value={paiement.reference} onChange={e => { const v = e.target.value; setPaiement(p => ({ ...p, reference: v })); }} />
              <button type="button" style={boutonPrincipal} onClick={payer} disabled={!paiement.montant}>Enregistrer le paiement</button>
            </div>
          )}
          {msg && <div>{msg}</div>}
        </div>
      )}
    </div>
  );
};

const FacturesListe = ({ coachEmail, isSuperAdmin }) => {
  const [ouvert, setOuvert] = useState(false);
  const [type, setType] = useState('');
  const [page, setPage] = useState(1);
  const [etat, setEtat] = useState({ chargement: false, liste: [], total: 0, erreur: '' });
  const [rev, setRev] = useState(0);
  const charger = useCallback(async () => {
    setEtat(p => ({ ...p, chargement: true, erreur: '' }));
    const r = await appel(`/invoices?page=${page}${type ? '&type=' + type : ''}`, { email: coachEmail });
    setEtat(r.ok ? { chargement: false, liste: r.data.factures || [], total: r.data.total || 0, erreur: '' }
      : { chargement: false, liste: [], total: 0, erreur: messageErreur(r) });
  }, [page, type, coachEmail]);
  useEffect(() => { if (ouvert) charger(); }, [ouvert, charger, rev]);
  return (
    <div style={{ padding: '0 16px 16px' }} data-testid="factures-liste">
      {isSuperAdmin && <CoordonneesFacturation email={coachEmail} />}
      <button type="button" style={boutonSecondaire} onClick={() => setOuvert(!ouvert)} data-testid="factures-liste-ouvrir">
        <SvgIcon name="fileText" size={14} /> {ouvert ? 'Masquer les documents émis' : 'Documents émis'}
      </button>
      {ouvert && (
        <div style={{ marginTop: 10 }}>
          <div style={{ display: 'flex', gap: 6, marginBottom: 8 }} role="group" aria-label="Type">
            {[['', 'Toutes'], ['corporate', 'Entreprise']].map(([v, l]) => (
              <button key={v || 'toutes'} type="button" onClick={() => { setType(v); setPage(1); }}
                style={type === v ? boutonPrincipal : boutonSecondaire} aria-pressed={type === v}>{l}</button>
            ))}
          </div>
          {etat.chargement && <p style={{ color: 'rgba(255,255,255,0.6)', fontSize: 12 }}>Chargement…</p>}
          {etat.erreur && <p style={{ color: 'rgba(255,255,255,0.75)', fontSize: 12 }}>{etat.erreur}</p>}
          {!etat.chargement && !etat.erreur && etat.liste.length === 0 && <p style={{ color: 'rgba(255,255,255,0.6)', fontSize: 12 }}>Aucun document.</p>}
          {etat.liste.map(x => <LigneFacture key={x.invoice_number + (x.created_at || '')} x={x} email={coachEmail} onMaj={() => setRev(v => v + 1)} />)}
          {etat.total > 50 && (
            <div style={{ display: 'flex', gap: 8, justifyContent: 'center' }}>
              <button type="button" style={boutonSecondaire} disabled={page <= 1} onClick={() => setPage(page - 1)}>Précédent</button>
              <button type="button" style={boutonSecondaire} disabled={page * 50 >= etat.total} onClick={() => setPage(page + 1)}>Suivant</button>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default FacturesListe;
