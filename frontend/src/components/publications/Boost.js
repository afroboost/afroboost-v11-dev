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

export default PrixBoost;
