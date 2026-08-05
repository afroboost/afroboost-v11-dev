/**
 * PawaPayCountrySelect — V382
 *
 * Sélecteur du PAYS du client pour un paiement Mobile Money PawaPay.
 * Le pays pilote la devise et l'opérateur : sans lui, `resoudre_pays()` côté
 * serveur ne peut pas trancher entre les pays ouverts sur le compte et refuse
 * le paiement (400). C'est ce qui rendait Mobile Money inutilisable hors du
 * pays de repli.
 *
 * La liste vient du BACKEND (`/api/pawapay/available` -> `countries_detail`),
 * pas d'une liste figée dans le bundle : un marché qui s'ouvre côté PawaPay
 * apparaît ici sans redéployer le frontend.
 *
 * Le composant ne rend RIEN tant que la liste n'est pas connue : mieux vaut
 * aucun champ qu'un champ vide qui laisserait croire à une panne.
 */
import { useEffect, useState } from "react";
import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';
const API = `${BACKEND_URL}/api`;

// Un seul appel réseau pour toute la page, même si plusieurs sélecteurs sont
// montés (offres + Boost peuvent coexister). La promesse est mémorisée, pas le
// résultat : un échec n'est donc pas gravé pour toute la session.
let promesseListe = null;

export const chargerPaysPawapay = () => {
  if (!promesseListe) {
    promesseListe = axios.get(`${API}/pawapay/available`)
      .then((r) => (r.data && r.data.countries_detail) || [])
      .catch(() => { promesseListe = null; return []; });
  }
  return promesseListe;
};

const GlobeIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="9" />
    <path d="M3 12h18" />
    <path d="M12 3a14 14 0 0 1 0 18a14 14 0 0 1 0-18z" />
  </svg>
);

/**
 * @param {string}   props.value     - code ISO alpha-3 choisi (ex. « CIV »)
 * @param {Function} props.onChange  - reçoit le code choisi
 * @param {boolean}  props.disabled
 * @param {Array}    props.countries - liste déjà chargée par le parent (optionnel)
 */
const PawaPayCountrySelect = ({ value, onChange, disabled = false, countries = null }) => {
  const [liste, setListe] = useState(countries || []);

  useEffect(() => {
    if (countries) { setListe(countries); return; }
    let vivant = true;
    chargerPaysPawapay().then((l) => { if (vivant) setListe(l); });
    return () => { vivant = false; };
  }, [countries]);

  if (!liste.length) return null;

  const labelStyle = {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
    color: 'rgba(255,255,255,0.6)',
    fontSize: '13px',
    fontWeight: '500',
    margin: '0 0 6px'
  };

  const selectStyle = {
    width: '100%',
    padding: '12px 14px',
    borderRadius: '10px',
    border: `1px solid ${value ? 'var(--primary-color, #D91CD2)' : 'rgba(255,255,255,0.15)'}`,
    background: 'rgba(255,255,255,0.04)',
    color: 'white',
    fontSize: '15px',
    outline: 'none',
    cursor: disabled ? 'not-allowed' : 'pointer',
    opacity: disabled ? 0.6 : 1
  };

  return (
    <div style={{ marginTop: '14px' }}>
      <label style={labelStyle} htmlFor="pawapay-pays">
        <GlobeIcon />
        Votre pays
      </label>
      <select
        id="pawapay-pays"
        data-testid="pawapay-country-select"
        value={value || ''}
        disabled={disabled}
        onChange={(e) => onChange && onChange(e.target.value)}
        style={selectStyle}
      >
        <option value="" style={{ background: '#1a1a1a' }}>Choisissez votre pays…</option>
        {liste.map((p) => (
          <option key={p.code} value={p.code} style={{ background: '#1a1a1a' }}>
            {p.label} — {p.currency}
          </option>
        ))}
      </select>
      <p style={{ color: 'rgba(255,255,255,0.4)', fontSize: '12px', margin: '6px 0 0' }}>
        Le montant vous sera présenté en {value
          ? (liste.find((p) => p.code === value) || {}).currency
          : 'devise locale'} sur la page de paiement.
      </p>
    </div>
  );
};

export default PawaPayCountrySelect;
