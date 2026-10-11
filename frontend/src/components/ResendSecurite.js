// V608 — « Resend — Sécurité des envois » (super-admin).
// Limiter ou non les envois Resend, avec une limite et un seuil choisis par le coach.
// Le réglage est PERSISTANT côté serveur (relu à chaque envoi, sans redéploiement).
// OFF ne coupe que le garde-fou Afroboost : le suivi de remise continue, et les limites
// du compte Resend restent applicables.
import React, { useCallback, useEffect, useState } from 'react';
import axios from 'axios';

const TEXTE = 'rgba(255,255,255,0.85)';
const DOUX = 'rgba(255,255,255,0.45)';
const ROUGE = 'rgb(239,68,68)';

const champ = {
  width: '96px', padding: '6px 8px', borderRadius: '8px', fontSize: '13px',
  background: 'rgba(0,0,0,0.35)', color: TEXTE, border: '1px solid rgba(255,255,255,0.18)',
};
const bouton = (principal) => ({
  padding: '7px 12px', borderRadius: '8px', fontSize: '12px', fontWeight: 700, cursor: 'pointer',
  border: principal ? 'none' : '1px solid rgba(255,255,255,0.22)',
  background: principal ? 'var(--primary-color, #D91CD2)' : 'transparent', color: TEXTE,
});

export default function ResendSecurite({ API }) {
  const [etat, setEtat] = useState(null);          // réponse de /admin/resend/etat
  const [form, setForm] = useState({ limite: '', seuil: '' });
  const [enCours, setEnCours] = useState(false);
  const [message, setMessage] = useState('');
  const [confirmer, setConfirmer] = useState(false);

  const appliquerEtat = useCallback((e) => {
    setEtat(e);
    const r = (e && e.reglages) || {};
    setForm((p) => {
      const suivant = { limite: String(r.limite ?? ''), seuil: String(r.seuil ?? '') };
      return p.limite === suivant.limite && p.seuil === suivant.seuil ? p : suivant;
    });
  }, []);

  useEffect(() => {
    let vivant = true;
    axios.get(`${API}/admin/resend/etat`)
      .then((r) => { if (vivant) appliquerEtat(r.data); })
      .catch((e) => {
        if (!vivant) return;
        const code = e && e.response && e.response.status;
        setMessage(code === 403 ? 'Réservé au super-admin — reconnectez-vous.' : 'État Resend illisible pour le moment.');
      });
    return () => { vivant = false; };
  }, [API, appliquerEtat]);

  const reg = (etat && etat.reglages) || null;

  const enregistrer = async (actif) => {
    setEnCours(true); setMessage('');
    try {
      const r = await axios.put(`${API}/admin/resend/reglages`, {
        actif, limite: Number(form.limite), seuil: Number(form.seuil),
      });
      appliquerEtat(r.data && r.data.etat ? r.data.etat : etat);
      setMessage('Réglage enregistré.');
    } catch (e) {
      const d = e && e.response && e.response.data && e.response.data.detail;
      const code = e && e.response && e.response.status;
      setMessage(code === 403 ? 'Réservé au super-admin — reconnectez-vous.' : (d || 'Le réglage n’a pas pu être enregistré.'));
    } finally { setEnCours(false); setConfirmer(false); }
  };

  const basculer = () => {
    if (!reg) return;
    if (reg.actif) { setConfirmer(true); return; }   // ON → OFF : confirmation obligatoire
    enregistrer(true);
  };

  return (
    <div data-testid="resend-securite" style={{ marginTop: '14px', paddingTop: '12px', borderTop: '1px solid rgba(255,255,255,0.08)' }}>
      <div className="flex items-center justify-between" style={{ gap: '8px' }}>
        <div style={{ minWidth: 0 }}>
          <span style={{ fontSize: '12px', color: TEXTE }}>Resend — Sécurité des envois</span>
          <p style={{ color: DOUX, fontSize: '11px', margin: '2px 0 0' }}>Limitation des envois</p>
        </div>
        <button type="button" onClick={basculer} disabled={!reg || enCours} data-testid="resend-limitation"
                aria-pressed={!!(reg && reg.actif)} title={reg && reg.actif ? 'Désactiver' : 'Activer'}
                style={{ position: 'relative', width: '38px', height: '20px', borderRadius: '999px', border: 'none',
                         cursor: !reg || enCours ? 'not-allowed' : 'pointer', opacity: !reg || enCours ? 0.5 : 1,
                         background: reg && reg.actif ? 'var(--primary-color, #D91CD2)' : 'rgba(255,255,255,0.18)', flexShrink: 0 }}>
          <span style={{ position: 'absolute', top: '3px', left: reg && reg.actif ? '21px' : '3px', width: '14px', height: '14px',
                         borderRadius: '50%', background: 'rgb(255,255,255)', transition: 'left 0.2s ease' }} />
        </button>
      </div>

      {reg && reg.actif && (
        <div data-testid="resend-reglages" style={{ marginTop: '10px', display: 'flex', gap: '12px', flexWrap: 'wrap', alignItems: 'flex-end' }}>
          <label style={{ fontSize: '11px', color: DOUX }}>Limite
            <div><input type="number" min="1" value={form.limite} data-testid="resend-limite" style={champ}
                        onChange={(e) => setForm((p) => ({ ...p, limite: e.target.value }))} /></div>
          </label>
          <label style={{ fontSize: '11px', color: DOUX }}>Seuil de sécurité
            <div><input type="number" min="0" value={form.seuil} data-testid="resend-seuil" style={champ}
                        onChange={(e) => setForm((p) => ({ ...p, seuil: e.target.value }))} /></div>
          </label>
          <button type="button" onClick={() => enregistrer(true)} disabled={enCours} data-testid="resend-enregistrer" style={bouton(true)}>
            {enCours ? 'Enregistrement…' : 'Enregistrer'}
          </button>
        </div>
      )}

      {etat && reg && (
        <div data-testid="resend-etat" style={{ marginTop: '8px', fontSize: '11.5px', color: TEXTE, lineHeight: 1.6 }}>
          {reg.actif ? (
            <>
              {etat.compte_effectif} envois comptabilisés (24 h glissantes)
              {' · '}{etat.restants_avant_seuil} restants avant seuil
              {' · '}{etat.restants_avant_limite} restants avant limite
            </>
          ) : (
            <span data-testid="resend-off">Limitation Afroboost désactivée — les limites du compte Resend restent applicables.</span>
          )}
          {etat.plan_insuffisant && (
            <div style={{ color: ROUGE, marginTop: '2px' }}>Plan Resend insuffisant : la demande des dernières 24 h dépasse la limite.</div>
          )}
        </div>
      )}
      {message && <p data-testid="resend-message" style={{ fontSize: '11px', color: DOUX, margin: '6px 0 0' }}>{message}</p>}

      {confirmer && (
        <div role="dialog" aria-modal="true" data-testid="resend-confirmation"
             style={{ position: 'fixed', inset: 0, zIndex: 10100, background: 'rgba(0,0,0,0.6)',
                      display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '16px' }}>
          <div style={{ maxWidth: '420px', width: '100%', borderRadius: '14px', padding: '18px', background: 'rgb(20,20,24)',
                        border: '1px solid rgba(255,255,255,0.12)', color: TEXTE }}>
            <div style={{ fontWeight: 700, fontSize: '15px' }}>Désactiver la limite Afroboost ?</div>
            <p style={{ fontSize: '13px', color: DOUX, margin: '8px 0 14px', lineHeight: 1.5 }}>
              Les envois ne seront plus bloqués par le quota interne. Les limites de votre abonnement Resend continueront de s’appliquer.
            </p>
            <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end' }}>
              <button type="button" onClick={() => setConfirmer(false)} data-testid="resend-annuler" style={bouton(false)}>Annuler</button>
              <button type="button" onClick={() => enregistrer(false)} data-testid="resend-desactiver" style={bouton(true)}>Désactiver</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
