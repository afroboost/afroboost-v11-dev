/**
 * OptinSubscribe — V332
 * Inscriptions volontaires : WhatsApp et newsletter e-mail.
 *
 * RGPD : la case de consentement est OBLIGATOIRE (le bouton reste inactif tant
 * qu'elle n'est pas cochée), et le LIBELLÉ EXACT affiché ici est envoyé au serveur
 * dans `consent_text` — c'est lui qui fait preuve, pas un simple booléen.
 *
 * Règle projet : aucune couleur codée en dur (toujours var(--primary-color, …)),
 * et aucune icône en emoji — uniquement des SVG inline.
 */
import { useState } from "react";
import axios from "axios";

const API = `${process.env.REACT_APP_BACKEND_URL || ''}/api`;

// Le numéro WhatsApp Afroboost (Meta Cloud API), au format wa.me (sans « + »).
const WHATSAPP_NUMERO = "41767639928";
const WHATSAPP_TEXTE = "Je veux recevoir les actus Afroboost";

const TEXTE_CONSENT_WA = "J'accepte de recevoir les actualités Afroboost sur WhatsApp.";
const TEXTE_CONSENT_MAIL = "J'accepte de recevoir la newsletter Afroboost par e-mail.";

const IconeWhatsApp = ({ size = 18 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
    <path d="M17.47 14.38c-.3-.15-1.75-.86-2.02-.96-.27-.1-.47-.15-.67.15-.2.3-.77.96-.94 1.16-.17.2-.35.22-.64.07-.3-.15-1.25-.46-2.38-1.47-.88-.78-1.47-1.75-1.65-2.05-.17-.3-.02-.46.13-.6.13-.14.3-.35.45-.52.15-.17.2-.3.3-.5.1-.2.05-.37-.02-.52-.08-.15-.67-1.6-.92-2.2-.24-.58-.49-.5-.67-.5h-.57c-.2 0-.52.07-.79.37-.27.3-1.04 1.02-1.04 2.47s1.06 2.87 1.21 3.07c.15.2 2.1 3.2 5.08 4.49.71.3 1.26.49 1.69.63.71.22 1.36.19 1.87.12.57-.09 1.75-.72 2-1.41.25-.7.25-1.29.17-1.41-.07-.13-.27-.2-.57-.35z" />
    <path d="M12.04 2C6.58 2 2.13 6.45 2.13 11.91c0 1.75.46 3.46 1.32 4.96L2 22l5.25-1.38a9.86 9.86 0 0 0 4.79 1.22h.01c5.46 0 9.91-4.45 9.91-9.91C21.96 6.45 17.5 2 12.04 2zm0 18.02h-.01a8.2 8.2 0 0 1-4.19-1.15l-.3-.18-3.12.82.83-3.04-.2-.31a8.19 8.19 0 0 1-1.26-4.37c0-4.54 3.7-8.23 8.25-8.23 2.2 0 4.27.86 5.83 2.42a8.19 8.19 0 0 1 2.41 5.82c0 4.54-3.7 8.22-8.24 8.22z" />
  </svg>
);

const IconeMail = ({ size = 18 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
       strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <rect x="2" y="4" width="20" height="16" rx="2" />
    <path d="m22 7-10 6L2 7" />
  </svg>
);

const champStyle = {
  width: '100%', padding: '10px 12px', borderRadius: 10,
  border: '1px solid rgba(255,255,255,0.14)', background: 'rgba(255,255,255,0.04)',
  color: '#fff', fontSize: '0.88rem', boxSizing: 'border-box', outline: 'none'
};

const OptinSubscribe = () => {
  // WhatsApp
  const [nom, setNom] = useState('');
  const [tel, setTel] = useState('');
  const [okWa, setOkWa] = useState(false);
  const [envoiWa, setEnvoiWa] = useState(false);
  const [msgWa, setMsgWa] = useState(null);      // { type: 'ok'|'ko', texte }

  // Newsletter
  const [email, setEmail] = useState('');
  const [okMail, setOkMail] = useState(false);
  const [envoiMail, setEnvoiMail] = useState(false);
  const [msgMail, setMsgMail] = useState(null);

  const erreurLisible = (err, repli) =>
    (err && err.response && err.response.data && err.response.data.detail) || repli;

  const inscrireWhatsApp = async (e) => {
    e.preventDefault();
    if (!okWa || envoiWa) return;
    setEnvoiWa(true); setMsgWa(null);
    try {
      const r = await axios.post(`${API}/subscribers/optin`, {
        channel: 'whatsapp', phone: tel.trim(), name: nom.trim(),
        consent: true, consent_text: TEXTE_CONSENT_WA, source: 'accueil'
      });
      setMsgWa({ type: 'ok', texte: (r.data && r.data.message) || 'Inscription confirmée.' });
      setTel(''); setNom(''); setOkWa(false);
    } catch (err) {
      setMsgWa({ type: 'ko', texte: erreurLisible(err, "L'inscription a échoué. Réessayez.") });
    } finally { setEnvoiWa(false); }
  };

  const inscrireNewsletter = async (e) => {
    e.preventDefault();
    if (!okMail || envoiMail) return;
    setEnvoiMail(true); setMsgMail(null);
    try {
      const r = await axios.post(`${API}/subscribers/optin`, {
        channel: 'email', email: email.trim(),
        consent: true, consent_text: TEXTE_CONSENT_MAIL, source: 'accueil'
      });
      setMsgMail({ type: 'ok', texte: (r.data && r.data.message) || 'Vérifiez votre boîte e-mail.' });
      setEmail(''); setOkMail(false);
    } catch (err) {
      setMsgMail({ type: 'ko', texte: erreurLisible(err, "L'inscription a échoué. Réessayez.") });
    } finally { setEnvoiMail(false); }
  };

  const Retour = ({ msg }) => msg ? (
    <p style={{ margin: '8px 0 0', fontSize: '0.78rem', lineHeight: 1.45,
                color: msg.type === 'ok' ? '#4ade80' : '#fca5a5' }}>
      {msg.texte}
    </p>
  ) : null;

  const Case = ({ coche, onChange, libelle, testid }) => (
    <label style={{ display: 'flex', alignItems: 'flex-start', gap: 8, cursor: 'pointer',
                    color: 'rgba(255,255,255,0.6)', fontSize: '0.74rem', lineHeight: 1.4 }}>
      <input type="checkbox" checked={coche} onChange={(e) => onChange(e.target.checked)}
             data-testid={testid}
             style={{ marginTop: 2, accentColor: 'var(--primary-color, #D91CD2)', flexShrink: 0 }} />
      <span>{libelle}</span>
    </label>
  );

  const bouton = (actif, enCours) => ({
    width: '100%', marginTop: 10, padding: '10px', borderRadius: 999, border: 'none',
    background: actif ? 'var(--primary-color, #D91CD2)' : 'rgba(255,255,255,0.12)',
    color: actif ? '#fff' : 'rgba(255,255,255,0.4)',
    fontWeight: 700, fontSize: '0.85rem',
    cursor: !actif ? 'not-allowed' : (enCours ? 'wait' : 'pointer')
  });

  return (
    <div className="max-w-4xl mx-auto px-4 mb-8 fade-in-section" data-testid="optin-section">
      <div style={{
        display: 'grid', gap: 14,
        gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))'
      }}>

        {/* ===== WhatsApp ===== */}
        <div style={{
          background: 'rgba(255,255,255,0.03)', borderRadius: 14, padding: 18,
          border: '1px solid rgba(var(--primary-rgb, 217, 28, 210), 0.18)'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
            <span style={{ color: 'var(--primary-color, #D91CD2)' }}><IconeWhatsApp /></span>
            <h3 style={{ color: '#fff', fontSize: '0.95rem', fontWeight: 700, margin: 0 }}>
              Recevoir mes séances sur WhatsApp
            </h3>
          </div>

          {/* Lien direct : ouvre la conversation, sans formulaire. */}
          <a
            href={`https://wa.me/${WHATSAPP_NUMERO}?text=${encodeURIComponent(WHATSAPP_TEXTE)}`}
            target="_blank" rel="noopener noreferrer"
            data-testid="optin-wa-link"
            style={{
              display: 'inline-flex', alignItems: 'center', gap: 6, marginBottom: 12,
              padding: '7px 14px', borderRadius: 999, textDecoration: 'none',
              border: '1px solid rgba(var(--primary-rgb, 217, 28, 210), 0.45)',
              color: 'var(--primary-color, #D91CD2)', fontSize: '0.78rem', fontWeight: 600
            }}
          >
            <IconeWhatsApp size={14} /> Écrire sur WhatsApp
          </a>

          <form onSubmit={inscrireWhatsApp} style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <input type="text" value={nom} onChange={(e) => setNom(e.target.value.slice(0, 80))}
                   placeholder="Votre nom (facultatif)" style={champStyle} data-testid="optin-wa-nom" />
            <input type="tel" value={tel} onChange={(e) => setTel(e.target.value.slice(0, 30))}
                   placeholder="Votre numéro (ex. 079 123 45 67)" style={champStyle}
                   data-testid="optin-wa-tel" required />
            <Case coche={okWa} onChange={setOkWa} libelle={TEXTE_CONSENT_WA} testid="optin-wa-consent" />
            <button type="submit" disabled={!okWa || envoiWa || !tel.trim()}
                    style={bouton(okWa && !!tel.trim(), envoiWa)} data-testid="optin-wa-submit">
              {envoiWa ? 'Inscription…' : "S'inscrire"}
            </button>
          </form>
          <Retour msg={msgWa} />
        </div>

        {/* ===== Newsletter ===== */}
        <div style={{
          background: 'rgba(255,255,255,0.03)', borderRadius: 14, padding: 18,
          border: '1px solid rgba(255,255,255,0.10)'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
            <span style={{ color: 'var(--primary-color, #D91CD2)' }}><IconeMail /></span>
            <h3 style={{ color: '#fff', fontSize: '0.95rem', fontWeight: 700, margin: 0 }}>
              Newsletter Afroboost
            </h3>
          </div>
          <p style={{ color: 'rgba(255,255,255,0.45)', fontSize: '0.76rem', margin: '0 0 12px' }}>
            Les nouveautés et les dates de cours, par e-mail. Un clic pour se désinscrire, à tout moment.
          </p>

          <form onSubmit={inscrireNewsletter} style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value.slice(0, 120))}
                   placeholder="Votre e-mail" style={champStyle} data-testid="optin-mail-email" required />
            <Case coche={okMail} onChange={setOkMail} libelle={TEXTE_CONSENT_MAIL} testid="optin-mail-consent" />
            <button type="submit" disabled={!okMail || envoiMail || !email.trim()}
                    style={bouton(okMail && !!email.trim(), envoiMail)} data-testid="optin-mail-submit">
              {envoiMail ? 'Envoi…' : "S'inscrire"}
            </button>
          </form>
          <Retour msg={msgMail} />
        </div>
      </div>
    </div>
  );
};

export default OptinSubscribe;
