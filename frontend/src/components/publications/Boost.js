/**
 * V342 — Boost payant des publications (place de marché des vitrines).
 *
 * Publier sur SA vitrine (coach) ou sur celle de SON coach (abonné) reste GRATUIT.
 * Le Boost sert uniquement à apparaître 48 h sur une AUTRE vitrine, ou sur la page
 * d'accueil. L'argent va au propriétaire de la vitrine de destination.
 *
 * Ce fichier regroupe les briques partagées pour ne pas les dupliquer :
 *   - `usePrixBoost`  : le prix courant, lu au serveur (source unique de vérité) ;
 *   - `PrixBoost`     : l'info « Boost : N CHF » + crayon de réglage (super-admin) ;
 *
 * Le prix affiché n'est JAMAIS celui qui sera facturé : le serveur relit
 * `boost_price_chf` au moment de créer le paiement. Ici, c'est de l'affichage.
 */
import { useState, useEffect, useCallback } from 'react';
import { createPortal } from 'react-dom';
import axios from 'axios';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';
const API = `${BACKEND_URL}/api`;

const PRIMAIRE = 'var(--primary-color, #D91CD2)';

// Les mêmes que côté serveur. Sert UNIQUEMENT à décider d'afficher ou non le
// crayon : l'écriture, elle, est refusée par le serveur (403) sans JWT admin.
const SUPER_ADMINS = ['contact.artboost@gmail.com', 'afroboost.bassi@gmail.com'];

/** Email de l'utilisateur courant, lu là où l'application le range déjà. */
export const emailCourant = () => {
  try {
    const brut = localStorage.getItem('afroboost_coach_user');
    if (brut) {
      const parsed = JSON.parse(brut);
      if (parsed && parsed.email) return String(parsed.email).toLowerCase().trim();
    }
  } catch (e) { /* ignore */ }
  try {
    const idBrut = localStorage.getItem('afroboost_identity') || localStorage.getItem('af_chat_client');
    if (idBrut) {
      const parsed = JSON.parse(idBrut);
      if (parsed && parsed.email) return String(parsed.email).toLowerCase().trim();
    }
  } catch (e) { /* ignore */ }
  try {
    return (localStorage.getItem('afroboost_admin_persist') || '').toLowerCase().trim();
  } catch (e) { /* ignore */ }
  return '';
};

/** Vrai si l'utilisateur courant est super-admin (affichage seulement). */
export const estSuperAdmin = () => SUPER_ADMINS.indexOf(emailCourant()) !== -1;

/**
 * Prix du Boost. Un seul appel réseau par montage, et un événement global pour que
 * TOUTES les instances affichées se mettent à jour quand l'admin change le montant
 * (sinon le crayon d'un encart ne rafraîchirait pas l'info-bulle d'un autre).
 */
export const usePrixBoost = () => {
  const [prix, setPrix] = useState(null); // null = pas encore chargé

  const charger = useCallback(() => {
    axios.get(`${API}/settings/boost-price`)
      .then((r) => setPrix(Number(r.data && r.data.price_chf) || null))
      .catch(() => setPrix(null));
  }, []);

  useEffect(() => {
    charger();
    const onChange = (e) => {
      const p = e && e.detail && Number(e.detail.price_chf);
      if (p) setPrix(p); else charger();
    };
    window.addEventListener('afroboost:boost-price-changed', onChange);
    return () => window.removeEventListener('afroboost:boost-price-changed', onChange);
  }, [charger]);

  return prix;
};

const IconeCrayon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor"
       strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M12 20h9" />
    <path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4 12.5-12.5z" />
  </svg>
);

/**
 * Info « Boost : N CHF », avec un crayon discret réservé au super-admin.
 * Le crayon ouvre un mini-champ ; l'enregistrement passe par le serveur, qui
 * refuse (403) toute écriture sans JWT super-admin — le masquage n'est qu'un confort.
 */
export const PrixBoost = () => {
  const prix = usePrixBoost();
  const [admin] = useState(estSuperAdmin);
  const [edition, setEdition] = useState(false);
  const [valeur, setValeur] = useState('');
  const [occupe, setOccupe] = useState(false);
  const [erreur, setErreur] = useState('');

  if (prix === null) return null;

  const ouvrir = () => { setValeur(String(prix)); setErreur(''); setEdition(true); };

  const enregistrer = async () => {
    if (occupe) return;
    const n = parseInt(valeur, 10);
    if (!n || n < 1 || n > 10000) { setErreur('Montant entre 1 et 10000'); return; }
    setOccupe(true);
    setErreur('');
    try {
      const r = await axios.put(`${API}/settings/boost-price`, { price_chf: n });
      const nouveau = Number(r.data && r.data.price_chf) || n;
      setEdition(false);
      // Répercute partout (info-bulles du bouton Boost incluses).
      try {
        window.dispatchEvent(new CustomEvent('afroboost:boost-price-changed',
          { detail: { price_chf: nouveau } }));
      } catch (e) { /* ignore */ }
    } catch (e) {
      setErreur(e && e.response && e.response.status === 403
        ? 'Réservé au super-admin' : 'Enregistrement impossible');
    }
    setOccupe(false);
  };

  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}
          data-testid="boost-price">
      <span style={{ color: 'rgba(255,255,255,0.5)', fontSize: '0.7rem' }}>
        Boost : {prix} CHF
      </span>

      {admin && !edition && (
        <button type="button" onClick={ouvrir}
                title="Modifier le prix du Boost" aria-label="Modifier le prix du Boost"
                data-testid="boost-price-edit"
                style={{ background: 'none', border: 'none', padding: 2, lineHeight: 0,
                         cursor: 'pointer', color: PRIMAIRE, opacity: 0.75 }}>
          <IconeCrayon />
        </button>
      )}

      {admin && edition && (
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
          <input
            type="number" min="1" max="10000" value={valeur} autoFocus
            onChange={(e) => setValeur(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') enregistrer(); if (e.key === 'Escape') setEdition(false); }}
            data-testid="boost-price-input"
            style={{ width: 62, padding: '3px 6px', borderRadius: 6, fontSize: '0.72rem',
                     border: '1px solid rgba(255,255,255,0.18)', background: '#0a0a1a', color: '#fff' }}
          />
          <button type="button" onClick={enregistrer} disabled={occupe}
                  data-testid="boost-price-save"
                  style={{ padding: '3px 8px', borderRadius: 6, border: 'none', background: PRIMAIRE,
                           color: '#fff', fontSize: '0.7rem', fontWeight: 700,
                           cursor: occupe ? 'wait' : 'pointer' }}>
            OK
          </button>
          <button type="button" onClick={() => setEdition(false)}
                  style={{ padding: '3px 6px', borderRadius: 6, border: '1px solid rgba(255,255,255,0.18)',
                           background: 'transparent', color: '#999', fontSize: '0.7rem', cursor: 'pointer' }}>
            Annuler
          </button>
          {erreur ? (
            <span style={{ color: '#fca5a5', fontSize: '0.65rem' }}>{erreur}</span>
          ) : null}
        </span>
      )}
    </span>
  );
};

/* =====================================================================
 * ÉTAPE 2 — le bouton Boost : choix de la destination puis du moyen de paiement.
 * ===================================================================== */

const IconeBoost = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor"
       strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M13 2 3 14h7l-1 8 10-12h-7l1-8z" />
  </svg>
);

const LIBELLES_MOYENS = { stripe: 'Carte / TWINT', pawapay: 'Mobile Money' };

/**
 * Modale de Boost. Deux décisions seulement : OÙ apparaître, et COMMENT payer.
 * Le montant n'est jamais saisi ici — il est affiché à titre indicatif et
 * recalculé par le serveur au moment de créer le paiement.
 */
const ModaleBoost = ({ pubId, subscriberCode, prix, onClose }) => {
  const [donnees, setDonnees] = useState(null); // null = chargement
  const [erreur, setErreur] = useState('');
  const [cible, setCible] = useState('');
  const [moyen, setMoyen] = useState('');
  const [telephone, setTelephone] = useState('');
  const [occupe, setOccupe] = useState(false);

  useEffect(() => {
    const q = subscriberCode ? `?subscriber_code=${encodeURIComponent(subscriberCode)}` : '';
    axios.get(`${API}/publications/${pubId}/boost/destinations${q}`)
      .then((r) => setDonnees(r.data || { destinations: [] }))
      .catch((e) => {
        setDonnees({ destinations: [] });
        setErreur(e && e.response && e.response.status === 403
          ? "Seul l'auteur peut booster cette publication."
          : "Impossible de charger les vitrines disponibles.");
      });
  }, [pubId, subscriberCode]);

  const destinations = (donnees && donnees.destinations) || [];
  const choisie = destinations.find((d) => d.target === cible) || null;
  const moyensPossibles = (choisie && choisie.providers) || [];
  const montant = (donnees && donnees.price_chf) || prix;

  const payer = async () => {
    if (occupe || !cible || !moyen) return;
    setOccupe(true);
    setErreur('');
    try {
      const corps = { target: cible, provider: moyen };
      if (subscriberCode) corps.subscriber_code = subscriberCode;
      if (moyen === 'pawapay' && telephone) corps.customer_phone = telephone;
      const r = await axios.post(`${API}/publications/${pubId}/boost/checkout`, corps);
      const url = r.data && r.data.payment_url;
      if (url) { window.location.href = url; return; }
      setErreur("Le paiement n'a pas pu être ouvert.");
    } catch (e) {
      setErreur((e && e.response && e.response.data && e.response.data.detail)
        || "Le paiement n'a pas pu être ouvert.");
    }
    setOccupe(false);
  };

  const carte = {
    background: '#12121f', borderRadius: 14, padding: 16, width: '100%', maxWidth: 420,
    maxHeight: '85vh', overflowY: 'auto', border: '1px solid rgba(255,255,255,0.08)',
  };

  return createPortal(
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, zIndex: 10000, background: 'rgba(0,0,0,0.75)',
        display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16,
      }}
      data-testid="boost-modal"
    >
      <div onClick={(e) => e.stopPropagation()} style={carte}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
          <h4 style={{ color: '#fff', fontSize: '0.95rem', margin: 0, display: 'flex',
                       alignItems: 'center', gap: 6 }}>
            <span style={{ color: PRIMAIRE, lineHeight: 0 }}><IconeBoost /></span>
            Booster cette publication
          </h4>
          <button type="button" onClick={onClose} aria-label="Fermer"
                  style={{ background: 'none', border: 'none', color: '#999', fontSize: 20,
                           cursor: 'pointer', lineHeight: 1 }}>×</button>
        </div>

        <p style={{ color: 'rgba(255,255,255,0.55)', fontSize: '0.75rem', margin: '8px 0 14px' }}>
          Apparaître <strong style={{ color: '#fff' }}>48 h</strong> sur une autre vitrine ou
          sur la page d'accueil, pour <strong style={{ color: '#fff' }}>{montant} CHF</strong>.
          Publier sur votre propre vitrine reste gratuit.
        </p>

        {donnees === null ? (
          <p style={{ color: 'rgba(255,255,255,0.4)', fontSize: '0.8rem' }}>Chargement…</p>
        ) : destinations.length === 0 ? (
          <p style={{ color: 'rgba(255,255,255,0.4)', fontSize: '0.8rem' }}>
            Aucune autre vitrine disponible pour le moment.
          </p>
        ) : (
          <>
            <p style={{ color: '#fff', fontSize: '0.8rem', fontWeight: 600, margin: '0 0 6px' }}>
              1. Où voulez-vous apparaître ?
            </p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 14 }}>
              {destinations.map((d) => {
                const dispo = (d.providers || []).length > 0;
                const actif = cible === d.target;
                return (
                  <button
                    key={d.target}
                    type="button"
                    disabled={!dispo}
                    onClick={() => { setCible(d.target); setMoyen(''); setErreur(''); }}
                    data-testid={`boost-dest-${d.target}`}
                    style={{
                      display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8,
                      padding: '9px 11px', borderRadius: 10, textAlign: 'left', fontSize: '0.8rem',
                      background: actif ? 'rgba(var(--primary-rgb, 217, 28, 210), 0.14)' : 'rgba(255,255,255,0.03)',
                      border: actif ? `1px solid ${PRIMAIRE}` : '1px solid rgba(255,255,255,0.08)',
                      color: dispo ? '#fff' : 'rgba(255,255,255,0.35)',
                      cursor: dispo ? 'pointer' : 'not-allowed',
                    }}
                  >
                    <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {d.name}
                    </span>
                    {!dispo ? (
                      <span style={{ fontSize: '0.65rem', flexShrink: 0 }}>paiement non configuré</span>
                    ) : null}
                  </button>
                );
              })}
            </div>

            {choisie ? (
              <>
                <p style={{ color: '#fff', fontSize: '0.8rem', fontWeight: 600, margin: '0 0 6px' }}>
                  2. Comment payer ?
                </p>
                <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 12 }}>
                  {moyensPossibles.map((m) => (
                    <button
                      key={m}
                      type="button"
                      onClick={() => { setMoyen(m); setErreur(''); }}
                      data-testid={`boost-moyen-${m}`}
                      style={{
                        padding: '8px 12px', borderRadius: 10, fontSize: '0.78rem', cursor: 'pointer',
                        background: moyen === m ? 'rgba(var(--primary-rgb, 217, 28, 210), 0.14)' : 'rgba(255,255,255,0.03)',
                        border: moyen === m ? `1px solid ${PRIMAIRE}` : '1px solid rgba(255,255,255,0.08)',
                        color: '#fff',
                      }}
                    >
                      {LIBELLES_MOYENS[m] || m}
                    </button>
                  ))}
                </div>

                {moyen === 'pawapay' ? (
                  <input
                    type="tel" value={telephone} placeholder="Numéro Mobile Money"
                    onChange={(e) => setTelephone(e.target.value)}
                    style={{ width: '100%', padding: '8px 10px', borderRadius: 8, marginBottom: 12,
                             border: '1px solid rgba(255,255,255,0.18)', background: '#0a0a1a',
                             color: '#fff', fontSize: '0.8rem', boxSizing: 'border-box' }}
                  />
                ) : null}
              </>
            ) : null}

            {erreur ? (
              <p style={{ color: '#fca5a5', fontSize: '0.75rem', margin: '0 0 10px' }}>{erreur}</p>
            ) : null}

            <button
              type="button" onClick={payer} disabled={!cible || !moyen || occupe}
              data-testid="boost-payer"
              style={{
                width: '100%', padding: '11px', borderRadius: 10, border: 'none', fontWeight: 700,
                fontSize: '0.85rem', color: '#fff',
                background: (!cible || !moyen) ? 'rgba(255,255,255,0.1)' : PRIMAIRE,
                cursor: (!cible || !moyen || occupe) ? 'not-allowed' : 'pointer',
              }}
            >
              {occupe ? 'Ouverture du paiement…' : `Payer ${montant} CHF`}
            </button>
          </>
        )}
      </div>
    </div>,
    document.body
  );
};

/**
 * L'icône éclair, discrète, affichée à l'auteur d'une publication.
 * `subscriberCode` non vide = l'auteur est un abonné (il n'a pas de compte).
 */
export const BoutonBoost = ({ pubId, subscriberCode }) => {
  const prix = usePrixBoost();
  const [ouvert, setOuvert] = useState(false);

  return (
    <>
      <button
        type="button"
        onClick={() => setOuvert(true)}
        data-testid={`boost-bouton-${pubId}`}
        aria-label="Booster"
        title={prix
          ? `Booster : apparaître 48 h sur une autre vitrine ou la page d'accueil — ${prix} CHF`
          : 'Booster : apparaître 48 h sur une autre vitrine ou la page d\'accueil'}
        style={{ background: 'none', border: 'none', padding: 4, lineHeight: 0,
                 cursor: 'pointer', color: PRIMAIRE }}
      >
        <IconeBoost />
      </button>
      {ouvert ? (
        <ModaleBoost pubId={pubId} subscriberCode={subscriberCode} prix={prix}
                     onClose={() => setOuvert(false)} />
      ) : null}
    </>
  );
};

/* =====================================================================
 * ÉTAPE 3 — retour du paiement : on demande au SERVEUR de confirmer.
 * ===================================================================== */

/**
 * Bandeau affiché au retour de la page de paiement (`?boost=success&bid=…`).
 *
 * Il ne décide RIEN : il appelle le serveur, qui redemande l'état réel au
 * prestataire avant d'accorder quoi que ce soit. Cet appel est indispensable en
 * place de marché — le compte Stripe d'un partenaire n'envoie pas ses webhooks à
 * Afroboost tant qu'il ne les a pas configurés lui-même.
 */
export const ConfirmationBoost = () => {
  const [etat, setEtat] = useState(null); // null | 'attente' | 'ok' | 'echec' | 'annule'

  useEffect(() => {
    let params;
    try { params = new URLSearchParams(window.location.search); } catch (e) { return; }
    const boost = params.get('boost');
    const bid = params.get('bid');
    if (!boost) return;

    // On nettoie l'URL tout de suite : un rafraîchissement ne doit pas rejouer
    // l'écran de confirmation (l'activation, elle, est idempotente côté serveur).
    try {
      const url = new URL(window.location.href);
      url.searchParams.delete('boost');
      url.searchParams.delete('bid');
      window.history.replaceState({}, document.title, url.pathname + url.search);
    } catch (e) { /* ignore */ }

    if (boost === 'cancelled') { setEtat('annule'); return; }
    if (boost !== 'success' || !bid) return;

    setEtat('attente');
    axios.get(`${API}/publications/boost/confirm/${encodeURIComponent(bid)}`)
      .then((r) => {
        const ok = r.data && r.data.status === 'completed';
        setEtat(ok ? 'ok' : 'echec');
        if (ok) {
          try { window.dispatchEvent(new CustomEvent('afroboost:publications-changed')); } catch (e) { /* ignore */ }
        }
      })
      .catch(() => setEtat('echec'));
  }, []);

  useEffect(() => {
    if (etat === 'ok' || etat === 'annule') {
      const t = setTimeout(() => setEtat(null), 6000);
      return () => clearTimeout(t);
    }
  }, [etat]);

  if (!etat) return null;

  const messages = {
    attente: 'Vérification du paiement…',
    ok: `C'est fait — votre publication apparaît ${48} h sur la vitrine choisie.`,
    echec: "Paiement non confirmé. Rien n'a été débité ni publié.",
    annule: 'Boost annulé.',
  };
  const couleurs = {
    attente: 'rgba(255,255,255,0.6)',
    ok: PRIMAIRE,
    echec: '#fca5a5',
    annule: 'rgba(255,255,255,0.6)',
  };

  return createPortal(
    <div
      data-testid="boost-confirmation"
      style={{
        position: 'fixed', left: '50%', transform: 'translateX(-50%)', bottom: 20, zIndex: 10001,
        maxWidth: 'min(92vw, 420px)', padding: '11px 16px', borderRadius: 12,
        background: '#12121f', border: `1px solid ${couleurs[etat]}`,
        color: '#fff', fontSize: '0.8rem', textAlign: 'center',
        boxShadow: '0 8px 24px rgba(0,0,0,0.45)',
      }}
    >
      {messages[etat]}
    </div>,
    document.body
  );
};

export default PrixBoost;
