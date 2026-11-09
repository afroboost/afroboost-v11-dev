// V657 : appels authentifiés (JWT signé `afroboost_jwt` + en-tête e-mail existant) pour Corporate et factures.
const API = (process.env.REACT_APP_BACKEND_URL || '') + '/api';

export const jeton = () => {
  try { return localStorage.getItem('afroboost_jwt') || ''; } catch (e) { return ''; }
};

export const entetes = (email) => ({
  'Content-Type': 'application/json',
  'X-User-Email': email || '',
  Authorization: `Bearer ${jeton()}`,
});

// Rend { ok, status, data } — jamais d'exception pour une réponse HTTP d'erreur.
export async function appel(chemin, { method = 'GET', body, email } = {}) {
  try {
    const res = await fetch(API + chemin, {
      method,
      headers: entetes(email),
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    let data = null;
    try { data = await res.json(); } catch (e) { data = null; }
    return { ok: res.ok, status: res.status, data };
  } catch (e) {
    return { ok: false, status: 0, data: { detail: 'Connexion impossible. Réessaie.' } };
  }
}

export const messageErreur = (r) => {
  const d = r && r.data && r.data.detail;
  if (!d) return 'Erreur (' + (r ? r.status : '?') + ')';
  if (typeof d === 'string') return d;
  return d.message || 'Erreur';
};

// Télécharge un PDF (émission ou re-téléchargement). Rend { ok, numero, erreur }.
export async function telechargerPdf(chemin, { method = 'GET', body, email, nomFichier } = {}) {
  try {
    const res = await fetch(API + chemin, {
      method,
      headers: entetes(email),
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (!res.ok) {
      let d = null;
      try { d = await res.json(); } catch (e) { d = null; }
      return { ok: false, erreur: messageErreur({ status: res.status, data: d }) };
    }
    const numero = res.headers.get('X-Invoice-Number') || '';
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = (nomFichier || numero || 'document') + '.pdf';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    return { ok: true, numero };
  } catch (e) {
    return { ok: false, erreur: 'Connexion impossible. Réessaie.' };
  }
}

export const chf = (v) => (Number(v || 0)).toFixed(2) + ' CHF';
export const dateCh = (iso) => {
  if (!iso) return '—';
  const m = String(iso).match(/^(\d{4})-(\d{2})-(\d{2})/);
  return m ? `${m[3]}.${m[2]}.${m[1]}` : String(iso);
};
export const STATUT_FACTURE = { emise: 'Émise', payee: 'Payée', annulee: 'Annulée', a_emettre: 'À émettre' };
export const STATUT_CONTRAT = { devis: 'Devis', signe: 'Signé', resilie: 'Résilié', termine: 'Terminé' };

export const carte = {
  background: 'rgba(255,255,255,0.03)',
  border: '1px solid rgba(255,255,255,0.08)',
  borderRadius: '12px',
  padding: '12px',
  marginBottom: '10px',
};
export const champ = {
  background: '#0a0a1a', border: '1px solid #333', borderRadius: '8px', color: '#fff',
  padding: '8px 12px', fontSize: '13px', width: '100%', boxSizing: 'border-box',
};
export const boutonPrincipal = {
  background: 'var(--primary-color, #D91CD2)', border: 'none', borderRadius: '10px', color: '#fff',
  padding: '8px 14px', fontSize: '13px', fontWeight: 600, cursor: 'pointer',
  display: 'inline-flex', alignItems: 'center', gap: '6px',
};
export const boutonSecondaire = {
  background: 'transparent', border: '1px solid rgba(var(--primary-rgb, 217, 28, 210), 0.45)', borderRadius: '10px',
  color: 'var(--primary-color, #D91CD2)', padding: '7px 12px', fontSize: '12px', fontWeight: 600, cursor: 'pointer',
  display: 'inline-flex', alignItems: 'center', gap: '6px',
};
export const pastille = (couleur) => ({
  display: 'inline-block', fontSize: '10px', fontWeight: 700, padding: '2px 8px', borderRadius: '999px',
  background: couleur === 'ok' ? 'rgba(34,197,94,0.15)' : couleur === 'alerte' ? 'rgba(245,158,11,0.15)' : 'rgba(255,255,255,0.08)',
  color: couleur === 'ok' ? '#22c55e' : couleur === 'alerte' ? '#f59e0b' : 'rgba(255,255,255,0.7)',
});
