/**
 * V628 — « J'ai un code promo » sur un ÉVÉNEMENT à billet (ex. AFROBOOST SILENT du 28/10).
 *
 * Un lien discret ; la saisie s'ouvre dans une fenêtre (plein écran sur téléphone, carte
 * centrée sur ordinateur) : prénom, nom, e-mail, WhatsApp (facultatif), code, conditions.
 * Le SERVEUR décide de tout (POST /api/evenements/<offre>/place-code) : code 100 %, quota,
 * expiration, réservé à CET événement. Aucun paiement : la place est confirmée à 0 CHF.
 * Le prix public de l'événement et son bouton de paiement ne changent pas.
 */
import React, { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import SvgIcon from './SvgIcon';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';
const PRIMAIRE = 'var(--primary-color, #D91CD2)';
const rgbaP = (a) => `rgba(var(--primary-rgb, 217, 28, 210), ${a})`;
const RE_EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;

const CSS = `
.v628-voile{position:fixed;inset:0;z-index:10060;background:rgba(0,0,0,.72);display:flex;align-items:center;justify-content:center;padding:16px}
.v628-carte{width:100%;max-width:440px;max-height:calc(100vh - 32px);overflow-y:auto;background:var(--background-color, #14101a);border:1px solid ${rgbaP(0.35)};border-radius:18px;padding:20px;box-sizing:border-box;color:rgba(255,255,255,.95);text-align:left}
@media (max-width:600px){.v628-voile{padding:0;align-items:stretch}.v628-carte{max-width:none;max-height:none;height:100%;border-radius:0;border:none;padding:18px 16px calc(18px + env(safe-area-inset-bottom))}}
.v628-champ{width:100%;min-height:46px;border-radius:10px;padding:0 12px;box-sizing:border-box;background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.18);color:rgba(255,255,255,.95);font-size:16px}
.v628-champ:focus{outline:none;border-color:${PRIMAIRE};box-shadow:0 0 0 2px ${rgbaP(0.3)}}
.v628-etiquette{display:block;font-size:13px;margin:10px 0 4px;color:rgba(255,255,255,.8)}
`;

function bouton(plein, actif = true) {
  return { width: '100%', minHeight: 48, borderRadius: 12, fontWeight: 800, fontSize: 15, cursor: actif ? 'pointer' : 'default',
    border: plein ? 'none' : `1px solid ${rgbaP(0.45)}`, background: plein ? PRIMAIRE : 'rgba(255,255,255,0.06)',
    color: 'rgba(255,255,255,1)', opacity: actif ? 1 : 0.7 };
}

function dateLisible(iso) {
  const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(String(iso || ''));
  if (!m) return '';
  const d = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
  const jour = d.toLocaleDateString('fr-CH', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });
  return `${jour.charAt(0).toUpperCase()}${jour.slice(1)} à ${m[4]}h${m[5]}`;
}

export default function CodePromoEvenement({ offreId, titre = '', inerte = false, compact = false }) {
  const [ouvert, setOuvert] = useState(false);
  const [champs, setChamps] = useState({ prenom: '', nom: '', email: '', whatsapp: '', code: '' });
  const [conditions, setConditions] = useState(false);
  const [texteConditions, setTexteConditions] = useState('');
  const [lireConditions, setLireConditions] = useState(false);
  const [etat, setEtat] = useState('');          // '' | 'envoi' | 'erreur:<texte>'
  const [resultat, setResultat] = useState(null); // réponse du serveur en cas de succès
  const premierChamp = useRef(null);

  useEffect(() => {
    if (!ouvert) return undefined;
    const avant = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    const echap = (e) => { if (e.key === 'Escape') setOuvert(false); };
    document.addEventListener('keydown', echap);
    if (premierChamp.current) { try { premierChamp.current.focus(); } catch (e) { /* ignore */ } }
    return () => { document.body.style.overflow = avant; document.removeEventListener('keydown', echap); };
  }, [ouvert]);

  useEffect(() => {
    if (!ouvert || texteConditions) return undefined;
    let annule = false;
    fetch(`${BACKEND_URL}/api/concept`).then((r) => (r.ok ? r.json() : null)).then((c) => {
      const t = String((c && c.termsText) || '').trim();
      if (!annule && t) setTexteConditions((prev) => (prev === t ? prev : t));
    }).catch(() => { /* silence : la case reste demandée */ });
    return () => { annule = true; };
  }, [ouvert, texteConditions]);

  const ouvrir = (e) => {
    if (e) { e.preventDefault(); e.stopPropagation(); }
    if (inerte) return;
    setOuvert(true);
  };
  const fermer = () => setOuvert(false);
  const maj = (cle) => (e) => {
    const v = e.target.value;
    setChamps((prev) => (prev[cle] === v ? prev : { ...prev, [cle]: v }));
    if (etat) setEtat('');
  };

  const envoyer = async (e) => {
    e.preventDefault();
    if (etat === 'envoi') return;
    const c = {
      prenom: champs.prenom.trim(), nom: champs.nom.trim(), email: champs.email.trim().toLowerCase(),
      whatsapp: champs.whatsapp.trim(), code: champs.code.trim(),
    };
    if (!c.prenom || !c.nom) { setEtat('erreur:Indique ton prénom et ton nom.'); return; }
    if (!RE_EMAIL.test(c.email)) { setEtat('erreur:Adresse e-mail invalide.'); return; }
    if (!c.code) { setEtat('erreur:Indique ton code promo.'); return; }
    if (!conditions) { setEtat("erreur:Merci d'accepter les conditions de participation."); return; }
    setEtat('envoi');
    try {
      const r = await fetch(`${BACKEND_URL}/api/evenements/${encodeURIComponent(offreId)}/place-code`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...c, terms_accepted: true }),
      });
      let j = null;
      try { j = await r.json(); } catch (x) { j = null; }
      if (r.ok && j && j.success) { setResultat(j); setEtat(''); return; }
      const detail = (j && typeof j.detail === 'string' && j.detail) || '';
      if (r.status === 429) setEtat('erreur:Trop de tentatives. Réessaie dans un moment.');
      else if (r.status >= 500 || !detail) setEtat('erreur:Réservation impossible pour le moment. Réessaie.');
      else setEtat(`erreur:${detail}`);
    } catch (x) {
      setEtat('erreur:Connexion impossible. Vérifie ta connexion et réessaie.');
    }
  };

  const resa = (resultat && resultat.reservation) || {};
  const quand = dateLisible(resa.datetime);

  return (
    <>
      <button type="button" onClick={ouvrir} data-testid="code-promo-evenement-lien"
              style={{ display: 'inline-flex', alignItems: 'center', gap: 6, margin: compact ? '8px 0 0' : '10px 0 0', padding: '6px 2px',
                background: 'none', border: 'none', color: PRIMAIRE, fontSize: 14, fontWeight: 700, cursor: inerte ? 'default' : 'pointer',
                textDecoration: 'underline', textUnderlineOffset: 3 }}>
        <SvgIcon name="ticket" size={16} /> J'ai un code promo
      </button>
      {ouvert && typeof document !== 'undefined' ? createPortal((
        <div className="v628-voile" data-testid="code-promo-evenement-fenetre" role="dialog" aria-modal="true"
             aria-labelledby="v628-titre" onClick={(e) => { e.stopPropagation(); if (e.target === e.currentTarget) fermer(); }}>
          <style>{CSS}</style>
          <div className="v628-carte">
            <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12 }}>
              <h2 id="v628-titre" style={{ margin: 0, fontSize: 19, fontWeight: 800, lineHeight: 1.25 }}>
                {resultat ? (resultat.deja_reserve ? 'Tu es déjà inscrit·e' : 'Ta place est réservée') : "J'ai un code promo"}
              </h2>
              <button type="button" onClick={fermer} aria-label="Fermer" data-testid="code-promo-evenement-fermer"
                      style={{ flex: '0 0 auto', width: 40, height: 40, borderRadius: 999, border: '1px solid rgba(255,255,255,0.2)',
                        background: 'rgba(255,255,255,0.06)', color: 'rgba(255,255,255,0.9)', cursor: 'pointer', display: 'inline-flex',
                        alignItems: 'center', justifyContent: 'center' }}>
                <SvgIcon name="x" size={18} />
              </button>
            </div>
            {titre ? <p style={{ margin: '6px 0 0', fontSize: 14, color: PRIMAIRE, fontWeight: 700 }}>{titre}</p> : null}

            {resultat ? (
              <div data-testid="code-promo-evenement-succes" role="status" style={{ marginTop: 14 }}>
                <p style={{ margin: 0, display: 'flex', gap: 8, alignItems: 'center', fontSize: 15 }}>
                  <span style={{ color: PRIMAIRE, display: 'inline-flex' }}><SvgIcon name="check" size={20} /></span>
                  {resultat.deja_reserve ? 'Une place est déjà réservée à cette adresse.' : 'Réservation confirmée, gratuitement.'}
                </p>
                {quand ? (
                  <p style={{ margin: '10px 0 0', display: 'flex', gap: 8, alignItems: 'center', fontSize: 14, color: 'rgba(255,255,255,0.85)' }}>
                    <span style={{ color: PRIMAIRE, display: 'inline-flex' }}><SvgIcon name="calendar" size={16} /></span>
                    <span>{quand}</span>
                  </p>
                ) : null}
                {!resultat.deja_reserve && resa.reservationCode ? (
                  <p data-testid="code-promo-evenement-billet" style={{ margin: '10px 0 0', fontSize: 14, color: 'rgba(255,255,255,0.85)' }}>
                    Ton billet : <strong style={{ color: 'rgba(255,255,255,1)', letterSpacing: 1 }}>{resa.reservationCode}</strong>
                  </p>
                ) : null}
                <p style={{ margin: '10px 0 16px', fontSize: 13.5, color: 'rgba(255,255,255,0.75)', lineHeight: 1.45 }}>
                  {resultat.deja_reserve
                    ? "Ta confirmation t'a été envoyée par e-mail lors de ta réservation."
                    : 'Une confirmation part à ton adresse e-mail. Présente-la à l’entrée.'}
                </p>
                <button type="button" onClick={fermer} style={bouton(true)}>Fermer</button>
              </div>
            ) : (
              <form onSubmit={envoyer} noValidate data-testid="code-promo-evenement-formulaire" style={{ marginTop: 6 }}>
                <p style={{ margin: '6px 0 2px', fontSize: 13.5, color: 'rgba(255,255,255,0.75)', lineHeight: 1.45 }}>
                  Tu as reçu un code d'invitation ? Ta place est confirmée tout de suite, sans paiement.
                </p>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                  <div>
                    <label className="v628-etiquette" htmlFor="v628-prenom">Prénom</label>
                    <input id="v628-prenom" ref={premierChamp} className="v628-champ" value={champs.prenom} onChange={maj('prenom')}
                           autoComplete="given-name" data-testid="code-promo-evenement-prenom" />
                  </div>
                  <div>
                    <label className="v628-etiquette" htmlFor="v628-nom">Nom</label>
                    <input id="v628-nom" className="v628-champ" value={champs.nom} onChange={maj('nom')}
                           autoComplete="family-name" data-testid="code-promo-evenement-nom" />
                  </div>
                </div>
                <label className="v628-etiquette" htmlFor="v628-email">E-mail</label>
                <input id="v628-email" type="email" inputMode="email" className="v628-champ" value={champs.email} onChange={maj('email')}
                       autoComplete="email" data-testid="code-promo-evenement-email" />
                <label className="v628-etiquette" htmlFor="v628-whatsapp">WhatsApp <span style={{ opacity: 0.6 }}>(facultatif)</span></label>
                <input id="v628-whatsapp" type="tel" inputMode="tel" className="v628-champ" value={champs.whatsapp} onChange={maj('whatsapp')}
                       autoComplete="tel" placeholder="+41 79 123 45 67" data-testid="code-promo-evenement-whatsapp" />
                <label className="v628-etiquette" htmlFor="v628-code">Code promo</label>
                <input id="v628-code" className="v628-champ" value={champs.code} onChange={maj('code')} autoCapitalize="characters"
                       autoComplete="off" spellCheck={false} style={{ textTransform: 'uppercase', letterSpacing: 1 }}
                       data-testid="code-promo-evenement-code" />
                <label style={{ display: 'flex', gap: 10, alignItems: 'flex-start', margin: '14px 0 0', fontSize: 13.5,
                  color: 'rgba(255,255,255,0.88)', cursor: 'pointer', lineHeight: 1.4 }}>
                  <input type="checkbox" checked={conditions} onChange={(e) => { setConditions(e.target.checked); if (etat) setEtat(''); }}
                         data-testid="code-promo-evenement-conditions"
                         style={{ width: 20, height: 20, marginTop: 1, accentColor: 'var(--primary-color, #D91CD2)', flex: '0 0 auto' }} />
                  <span>J'accepte les conditions de participation.</span>
                </label>
                {texteConditions ? (
                  <div style={{ margin: '4px 0 0 30px' }}>
                    <button type="button" onClick={() => setLireConditions((v) => !v)} aria-expanded={lireConditions}
                            style={{ background: 'none', border: 'none', padding: 0, color: PRIMAIRE, fontSize: 13, cursor: 'pointer', textDecoration: 'underline' }}>
                      {lireConditions ? 'Masquer les conditions' : 'Lire les conditions'}
                    </button>
                    {lireConditions ? (
                      <p style={{ margin: '6px 0 0', maxHeight: 160, overflowY: 'auto', fontSize: 12.5, whiteSpace: 'pre-line',
                        color: 'rgba(255,255,255,0.75)' }}>{texteConditions}</p>
                    ) : null}
                  </div>
                ) : null}
                {etat.startsWith('erreur:') ? (
                  <p role="alert" data-testid="code-promo-evenement-erreur"
                     style={{ margin: '12px 0 0', fontSize: 13.5, color: 'rgba(255,170,170,1)' }}>{etat.slice(7)}</p>
                ) : null}
                <button type="submit" disabled={etat === 'envoi'} data-testid="code-promo-evenement-valider"
                        style={{ ...bouton(true, etat !== 'envoi'), marginTop: 16 }}>
                  {etat === 'envoi' ? 'Vérification…' : 'Réserver ma place gratuite'}
                </button>
              </form>
            )}
          </div>
        </div>
      ), document.body) : null}
    </>
  );
}
