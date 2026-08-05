/**
 * PawaPayOfferButton — V382
 *
 * Bouton « Payer par Mobile Money » pour les OFFRES / abonnements.
 *
 * Conçu pour être STRICTEMENT ADDITIF : il vit à côté du bouton « Réserver »
 * existant et ne touche à rien du parcours Stripe, qui reste identique au
 * caractère près. Si PawaPay est désactivé — ou si le moindre appel échoue —
 * le composant ne rend RIEN et la page est celle d'avant.
 *
 * Il collecte l'e-mail lui-même, et ce n'est pas un détail de confort : la page
 * hébergée PawaPay ne demande que l'opérateur et le numéro. Sans e-mail,
 * `activate_after_payment` n'a personne à qui envoyer le code d'accès — le
 * paiement serait encaissé sans rien délivrer.
 *
 * Le PRIX part en CHF (`amount_chf`) : c'est le serveur qui convertit vers la
 * devise du pays choisi. Le navigateur ne connaît pas les taux et n'a pas à
 * fixer un montant.
 */
import { useEffect, useState } from "react";
import axios from "axios";
import PawaPayCountrySelect, { chargerPaysPawapay } from "./PawaPayCountrySelect";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';
const API = `${BACKEND_URL}/api`;

const PhoneIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    <rect x="5" y="2" width="14" height="20" rx="2" ry="2" />
    <line x1="12" y1="18" x2="12.01" y2="18" />
  </svg>
);

const PawaPayOfferButton = ({ offer, priceChf, disabled = false }) => {
  const [dispo, setDispo] = useState(false);
  const [ouvert, setOuvert] = useState(false);
  const [pays, setPays] = useState('');
  const [email, setEmail] = useState('');
  const [nom, setNom] = useState('');
  const [telephone, setTelephone] = useState('');
  const [occupe, setOccupe] = useState(false);
  const [erreur, setErreur] = useState('');

  // La liste de pays sert de test de disponibilité : elle n'est renvoyée que
  // lorsque le drapeau est ON *et* le prestataire configuré. Un seul appel
  // réseau pour toute la page (la promesse est mutualisée).
  useEffect(() => {
    let vivant = true;
    chargerPaysPawapay().then((l) => { if (vivant) setDispo(!!(l && l.length)); });
    return () => { vivant = false; };
  }, []);

  // V383 : le carrousel des offres défile tout seul toutes les 3,5 s. Pendant la
  // saisie de ce formulaire, il faisait glisser la carte sous les doigts de
  // l'acheteur. On previent donc le carrousel de se mettre en pause.
  //
  // Le signal de fermeture est emis par le NETTOYAGE de l'effet, pas par chaque
  // bouton : il part donc pour TOUS les chemins de sortie — « Annuler », clic
  // hors de la modale, redirection vers PawaPay, ou demontage de la carte —
  // sans qu'aucun ne puisse etre oublie et laisser le carrousel fige.
  useEffect(() => {
    if (!ouvert) return undefined;
    window.dispatchEvent(new CustomEvent('afroboost:paiement-formulaire-ouvert'));
    return () => window.dispatchEvent(new CustomEvent('afroboost:paiement-formulaire-ferme'));
  }, [ouvert]);

  // ATTENTION : ce retour anticipé doit rester APRÈS tous les hooks ci-dessus —
  // un hook placé plus bas ne serait pas appelé à chaque rendu (règles de React).
  if (!dispo || !priceChf || priceChf <= 0) return null;

  const payer = async () => {
    if (occupe) return;
    setErreur('');
    if (!email.trim() || email.indexOf('@') < 1) {
      setErreur("Votre e-mail est nécessaire pour recevoir votre code d'accès.");
      return;
    }
    if (!pays) {
      setErreur('Choisissez votre pays.');
      return;
    }
    setOccupe(true);
    try {
      const r = await axios.post(`${API}/pawapay/create-checkout`, {
        amount_chf: priceChf,
        description: `Afroboost — ${(offer && offer.name) || 'Offre'}`.slice(0, 50),
        customer_email: email.trim(),
        customer_name: nom.trim(),
        customer_phone: telephone.trim(),
        country: pays,
        // `offer_id` permet au SERVEUR de relire le nombre de séances en base.
        // Il n'est jamais envoyé depuis ici — voir V382 dans pawapay_routes.py.
        metadata: { offer_id: (offer && offer.id) || '' }
      });
      const url = r.data && r.data.payment_url;
      if (url) { window.location.href = url; return; }
      setErreur("Le paiement n'a pas pu être ouvert.");
    } catch (e) {
      setErreur((e && e.response && e.response.data && e.response.data.detail)
        || "Le paiement Mobile Money est momentanément indisponible.");
    }
    setOccupe(false);
  };

  const champStyle = {
    width: '100%',
    padding: '12px 14px',
    borderRadius: '10px',
    border: '1px solid rgba(255,255,255,0.15)',
    background: 'rgba(255,255,255,0.04)',
    color: 'white',
    fontSize: '15px',
    outline: 'none',
    boxSizing: 'border-box',
    marginTop: '10px'
  };

  return (
    <>
      <button
        type="button"
        disabled={disabled}
        onClick={(e) => { e.stopPropagation(); setOuvert(true); }}
        data-testid={`offer-pawapay-${(offer && offer.id) || 'x'}`}
        className="text-xs px-3 py-2 rounded-lg font-semibold transition-all"
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: '6px',
          background: 'transparent',
          color: 'var(--primary-color, #D91CD2)',
          border: '1px solid var(--primary-color, #D91CD2)',
          opacity: disabled ? 0.6 : 1,
          cursor: disabled ? 'not-allowed' : 'pointer'
        }}
      >
        <PhoneIcon />
        Mobile Money
      </button>

      {ouvert && (
        <div
          onClick={(e) => { e.stopPropagation(); setOuvert(false); }}
          style={{
            position: 'fixed', inset: 0, zIndex: 10000,
            background: 'rgba(0,0,0,0.75)',
            display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '16px'
          }}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              width: '100%', maxWidth: '420px',
              background: '#12121f',
              border: '1px solid rgba(var(--primary-rgb, 217, 28, 210), 0.3)',
              borderRadius: '16px', padding: '22px',
              maxHeight: '90vh', overflowY: 'auto'
            }}
          >
            <h3 style={{ color: 'white', fontSize: '17px', fontWeight: 700, margin: '0 0 4px' }}>
              Payer par Mobile Money
            </h3>
            <p style={{ color: 'rgba(255,255,255,0.5)', fontSize: '13px', margin: '0 0 8px' }}>
              {(offer && offer.name) || 'Offre'} — {priceChf} CHF
            </p>

            <input
              type="email" value={email} placeholder="Votre e-mail"
              onChange={(e) => setEmail(e.target.value)} style={champStyle}
              data-testid="pawapay-offer-email"
            />
            <input
              type="text" value={nom} placeholder="Votre nom (facultatif)"
              onChange={(e) => setNom(e.target.value)} style={champStyle}
            />

            <PawaPayCountrySelect value={pays} onChange={setPays} disabled={occupe} />

            <input
              type="tel" value={telephone} placeholder="Numéro Mobile Money (facultatif)"
              onChange={(e) => setTelephone(e.target.value)} style={champStyle}
            />
            <p style={{ color: 'rgba(255,255,255,0.4)', fontSize: '12px', margin: '6px 0 0' }}>
              Vous pourrez aussi saisir votre numéro sur la page de paiement.
            </p>

            {erreur ? (
              <p style={{ color: '#fca5a5', fontSize: '13px', margin: '12px 0 0' }}>{erreur}</p>
            ) : null}

            <div style={{ display: 'flex', gap: '10px', marginTop: '18px' }}>
              <button
                type="button" onClick={() => setOuvert(false)} disabled={occupe}
                style={{
                  flex: 1, padding: '12px', borderRadius: '10px', fontWeight: 600,
                  border: '1px solid rgba(255,255,255,0.15)', background: 'transparent',
                  color: 'rgba(255,255,255,0.7)', cursor: 'pointer'
                }}
              >
                Annuler
              </button>
              <button
                type="button" onClick={payer} disabled={occupe}
                data-testid="pawapay-offer-pay"
                style={{
                  flex: 2, padding: '12px', borderRadius: '10px', fontWeight: 700,
                  border: 'none', background: 'var(--primary-color, #D91CD2)',
                  color: 'white', cursor: occupe ? 'wait' : 'pointer', opacity: occupe ? 0.7 : 1
                }}
              >
                {occupe ? 'Un instant…' : 'Continuer'}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
};

export default PawaPayOfferButton;
