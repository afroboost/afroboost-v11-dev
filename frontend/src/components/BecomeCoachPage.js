/**
 * BecomeCoachPage - Page "Devenir Partenaire" v9.4.7
 * Permet aux nouveaux partenaires (coachs/vendeurs) de s'inscrire et de payer leur pack
 */
import { useState, useEffect, useRef } from "react";
import axios from "axios";
import PaymentMethodSelector from "./PaymentMethodSelector";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';
const API = `${BACKEND_URL}/api`;

// Icônes SVG minimalistes
const CheckIcon = () => (
  <svg className="w-5 h-5 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
  </svg>
);

const CrownIcon = () => (
  <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.5}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M12 2L9 9l-7 2 5 5-1 7 6-3 6 3-1-7 5-5-7-2-3-7z" />
  </svg>
);


const BecomeCoachPage = ({ onClose, onSuccess }) => {
  const [packs, setPacks] = useState([]);
  const [selectedPack, setSelectedPack] = useState(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  
  const [isCheckingAuth, setIsCheckingAuth] = useState(true);
  const hasProcessedRef = useRef(false);
  
  // v11.0: Méthode de paiement (card = Stripe, mobile_money = CinetPay)
  const [paymentMethod, setPaymentMethod] = useState('card');

  // v11.6: Mot de passe + CGU
  const [showPassword, setShowPassword] = useState(false);
  const [acceptedCGU, setAcceptedCGU] = useState(false);

  // Formulaire d'inscription
  const [formData, setFormData] = useState({
    name: '',
    email: '',
    phone: '',
    password: '',
    promoCode: ''
  });




  // Charger les packs disponibles
  useEffect(() => {
    const fetchPacks = async () => {
      try {
        const res = await axios.get(`${API}/admin/coach-packs`);
        setPacks(res.data || []);
        if (res.data && res.data.length > 0) {
          setSelectedPack(res.data[0]);
        }
      } catch (err) {
        console.error('[COACH-PACKS] Erreur:', err);
        setError('Impossible de charger les offres');
      } finally {
        setLoading(false);
      }
    };
    fetchPacks();
  }, []);


  const handleInputChange = (e) => {
    const { name, value } = e.target;
    setFormData(prev => ({ ...prev, [name]: value }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();

    const email = formData.email;
    const name = formData.name;

    if (!name || !email || !selectedPack) {
      setError('Veuillez remplir tous les champs obligatoires');
      return;
    }

    // v11.6: Validation CGU obligatoire
    if (!acceptedCGU) {
      setError('Vous devez accepter les conditions générales d\'utilisation');
      return;
    }

    if (!formData.password) {
      setError('Veuillez choisir un mot de passe');
      return;
    }
    if (formData.password && formData.password.length < 6) {
      setError('Le mot de passe doit contenir au moins 6 caractères');
      return;
    }

    setSubmitting(true);
    setError(null);

    try {
      // === CAS SPÉCIFIQUE 0 CHF : Inscription immédiate sans paiement ===
      if (!selectedPack.price || selectedPack.price <= 0) {
        const registerRes = await axios.post(`${API}/cinetpay/register-free`, {
          email: email,
          name: name,
          phone: formData.phone,
          pack_id: selectedPack.id,
          password: formData.password
        }, { withCredentials: true });

        if (registerRes.data?.success) {
          // Session active — stocker les infos partenaire
          const user = registerRes.data.user;
          localStorage.setItem('afroboost_coach_user', JSON.stringify(user));
          localStorage.setItem('afroboost_coach_mode', 'true');
          localStorage.setItem('redirect_to_dash', 'true');
          localStorage.setItem('afroboost_redirect_message', '🎉 Bienvenue Partenaire ! Votre pack est activé.');

          // Redirection directe vers le Dashboard sans relogin
          window.location.hash = '#partner-dashboard';
          window.location.reload();
          onSuccess?.(registerRes.data);
        }
        return;
      }

      // v11.0: Paiement selon la méthode choisie (price > 0)

      // === MOBILE MONEY (CinetPay) ===
      if (paymentMethod === 'mobile_money') {
        try {
          const response = await axios.post(`${API}/cinetpay/create-coach-checkout`, {
            pack_id: selectedPack.id,
            customer_email: email,
            customer_name: name,
            customer_phone: formData.phone
          });

          if (response.data.payment_url) {
            // Sauvegarder les infos pour la redirection post-paiement
            localStorage.setItem('afroboost_pending_partner', JSON.stringify({
              email, name, phone: formData.phone, password: formData.password || '',
              pack_id: selectedPack.id, transaction_id: response.data.transaction_id
            }));
            window.location.href = response.data.payment_url;
            return;
          } else {
            setError("Erreur lors de la création du paiement Mobile Money");
          }
        } catch (mmErr) {
          console.error('[MOBILE_MONEY] Erreur:', mmErr);
          const errMsg = mmErr.response?.data?.detail || '';
          if (mmErr.response?.status === 503 || errMsg.includes('pas configuré') || errMsg.includes('pas disponible')) {
            setError('Le paiement Mobile Money est temporairement indisponible. Veuillez utiliser la Carte Bancaire ou réessayer plus tard.');
          } else {
            setError(errMsg || 'Erreur Mobile Money. Vérifiez votre connexion et réessayez.');
          }
          setSubmitting(false);
          return;
        }
      }

      // === CARTE BANCAIRE (Stripe) ===
      if (paymentMethod === 'card') {
        if (!selectedPack.stripe_price_id) {
          setError('Ce pack n\'a pas de prix Stripe configuré. Contactez l\'administrateur.');
          setSubmitting(false);
          return;
        }
        console.log('[REGISTER] Création checkout Stripe pour pack:', selectedPack.name, 'price_id:', selectedPack.stripe_price_id);
        const response = await axios.post(`${API}/stripe/create-coach-checkout`, {
          price_id: selectedPack.stripe_price_id,
          pack_id: selectedPack.id,
          email: email,
          name: name,
          phone: formData.phone,
          promo_code: formData.promoCode
        });

        console.log('[REGISTER] Réponse Stripe:', response.data);
        if (response.data.checkout_url) {
          // Sauvegarder les infos pour la redirection post-paiement
          localStorage.setItem('afroboost_pending_partner', JSON.stringify({
            email, name, phone: formData.phone, password: formData.password || '',
            pack_id: selectedPack.id
          }));
          window.location.href = response.data.checkout_url;
          return;
        } else {
          setError('Erreur: pas d\'URL de paiement reçue. Réessayez.');
        }
      }

      // Fallback
      if (paymentMethod !== 'card' && paymentMethod !== 'mobile_money') {
        setError('Méthode de paiement non reconnue.');
      }
    } catch (err) {
      console.error('[REGISTER] Erreur:', err);
      const detail = err.response?.data?.detail;
      const message = typeof detail === 'string' ? detail :
        Array.isArray(detail) ? detail.map(d => d.msg || JSON.stringify(d)).join(', ') :
        'Erreur lors de l\'inscription. Vérifiez votre connexion et réessayez.'
      setError(message);
    } finally {
      setSubmitting(false);
    }
  };

  if (loading || isCheckingAuth) {
    return (
      <div className="fixed inset-0 bg-black/90 z-50 flex items-center justify-center">
        <div className="text-white text-lg">Chargement...</div>
      </div>
    );
  }

  return (
    <div className="fixed inset-0 bg-black/95 z-50 overflow-y-auto">
      <div className="min-h-screen py-8 px-4">
        {/* Header */}
        <div className="max-w-4xl mx-auto">
          <div className="flex justify-between items-center mb-8">
            <h1 className="text-2xl sm:text-3xl font-bold text-white flex items-center gap-3">
              <span style={{ color: '#D91CD2' }}><CrownIcon /></span>
              Devenir Partenaire Afroboost
            </h1>
            <button 
              onClick={onClose}
              className="text-white/60 hover:text-white text-2xl p-2"
              data-testid="close-become-coach"
            >
              ✕
            </button>
          </div>



          {/* Avantages */}
          <div className="glass rounded-2xl p-6 mb-8" style={{ border: '1px solid rgba(217, 28, 210, 0.3)' }}>
            <h2 className="text-xl font-semibold text-white mb-4">Pourquoi devenir Partenaire Afroboost ?</h2>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div className="flex items-start gap-3">
                <CheckIcon />
                <div>
                  <h3 className="text-white font-medium">CRM Automatisé</h3>
                  <p className="text-white/60 text-sm">Tous vos contacts centralisés</p>
                </div>
              </div>
              <div className="flex items-start gap-3">
                <CheckIcon />
                <div>
                  <h3 className="text-white font-medium">Chat IA Intégré</h3>
                  <p className="text-white/60 text-sm">Assistant virtuel pour vos clients</p>
                </div>
              </div>
              <div className="flex items-start gap-3">
                <CheckIcon />
                <div>
                  <h3 className="text-white font-medium">Page de Vente Perso</h3>
                  <p className="text-white/60 text-sm">Votre vitrine professionnelle</p>
                </div>
              </div>
            </div>
          </div>

          {/* Packs */}
          <h2 className="text-xl font-semibold text-white mb-4">Choisissez votre Pack</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 mb-8">
            {packs.map(pack => (
              <div
                key={pack.id}
                onClick={() => setSelectedPack(pack)}
                className={`glass rounded-xl p-5 cursor-pointer transition-all hover:scale-105 ${
                  selectedPack?.id === pack.id 
                    ? 'ring-2 ring-purple-500' 
                    : ''
                }`}
                style={{ 
                  border: selectedPack?.id === pack.id 
                    ? '2px solid #D91CD2' 
                    : '1px solid rgba(255,255,255,0.1)'
                }}
                data-testid={`pack-${pack.id}`}
              >
                <h3 className="text-lg font-bold text-white mb-2">{pack.name}</h3>
                <div className="text-3xl font-bold mb-2" style={{ color: '#D91CD2' }}>
                  {pack.price} CHF
                </div>
                <div className="text-white/70 text-sm mb-3">
                  {pack.credits} crédits inclus
                </div>
                {pack.description && (
                  <p className="text-white/50 text-xs mb-3">{pack.description}</p>
                )}
                {pack.features && pack.features.length > 0 && (
                  <ul className="space-y-1">
                    {pack.features.map((feature, idx) => (
                      <li key={idx} className="flex items-center gap-2 text-xs text-white/70">
                        <CheckIcon />
                        {feature}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            ))}
            
            {packs.length === 0 && (
              <div className="col-span-full text-center py-8">
                <p className="text-white/60">Aucun pack disponible pour le moment</p>
              </div>
            )}
          </div>

          {/* Formulaire */}
          {selectedPack && (
            <div className="glass rounded-2xl p-6" style={{ border: '1px solid rgba(217, 28, 210, 0.3)' }}>
              <h2 className="text-xl font-semibold text-white mb-4">
                {'Vos Informations'}
              </h2>
              
              <form onSubmit={handleSubmit} className="space-y-4">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div>
                    <label className="text-white/70 text-sm mb-1 block">Nom complet *</label>
                    <input
                      type="text"
                      name="name"
                      value={formData.name}
                      onChange={handleInputChange}
                      required
                      className="w-full px-4 py-3 rounded-lg disabled:opacity-60"
                      style={{ background: 'rgba(255,255,255,0.1)', border: '1px solid rgba(255,255,255,0.2)', color: '#fff' }}
                      data-testid="coach-name-input"
                    />
                  </div>
                  <div>
                    <label className="text-white/70 text-sm mb-1 block">Email *</label>
                    <input
                      type="email"
                      name="email"
                      value={formData.email}
                      onChange={handleInputChange}
                      required
                      className="w-full px-4 py-3 rounded-lg disabled:opacity-60"
                      style={{ background: 'rgba(255,255,255,0.1)', border: '1px solid rgba(255,255,255,0.2)', color: '#fff' }}
                      data-testid="coach-email-input"
                    />
                  </div>
                  <div>
                    <label className="text-white/70 text-sm mb-1 block">Téléphone</label>
                    <input
                      type="tel"
                      name="phone"
                      value={formData.phone}
                      onChange={handleInputChange}
                      className="w-full px-4 py-3 rounded-lg"
                      style={{ background: 'rgba(255,255,255,0.1)', border: '1px solid rgba(255,255,255,0.2)', color: '#fff' }}
                      data-testid="coach-phone-input"
                    />
                  </div>
                  <div>
                    <label className="text-white/70 text-sm mb-1 block">Code Promo</label>
                    <input
                      type="text"
                      name="promoCode"
                      value={formData.promoCode}
                      onChange={handleInputChange}
                      placeholder="Optionnel"
                      className="w-full px-4 py-3 rounded-lg"
                      style={{ background: 'rgba(255,255,255,0.1)', border: '1px solid rgba(255,255,255,0.2)', color: '#fff' }}
                      data-testid="coach-promo-input"
                    />
                  </div>
                </div>

                  <div style={{ position: 'relative' }}>
                    <label className="text-white/70 text-sm mb-1 block">Mot de passe *</label>
                    <input
                      type={showPassword ? 'text' : 'password'}
                      name="password"
                      value={formData.password}
                      onChange={handleInputChange}
                      required
                      minLength={6}
                      placeholder="Minimum 6 caractères"
                      className="w-full px-4 py-3 rounded-lg"
                      style={{ background: 'rgba(255,255,255,0.1)', border: '1px solid rgba(255,255,255,0.2)', color: '#fff', paddingRight: '48px' }}
                      data-testid="coach-password-input"
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword(!showPassword)}
                      style={{
                        position: 'absolute', right: '12px', top: '32px',
                        background: 'none', border: 'none', color: 'rgba(255,255,255,0.5)',
                        cursor: 'pointer', fontSize: '14px'
                      }}
                    >
                      {showPassword ? '🙈' : '👁️'}
                    </button>
                  </div>

                {/* v11.6: Case CGU obligatoire */}
                <div style={{ display: 'flex', alignItems: 'flex-start', gap: '10px', padding: '8px 0' }}>
                  <input
                    type="checkbox"
                    id="cgu-checkbox"
                    checked={acceptedCGU}
                    onChange={(e) => setAcceptedCGU(e.target.checked)}
                    style={{ marginTop: '3px', accentColor: '#D91CD2', width: '18px', height: '18px', cursor: 'pointer' }}
                    data-testid="cgu-checkbox"
                  />
                  <label htmlFor="cgu-checkbox" style={{ color: 'rgba(255,255,255,0.7)', fontSize: '13px', cursor: 'pointer' }}>
                    J'accepte les{' '}
                    <a
                      href="/cgu"
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{ color: '#D91CD2', textDecoration: 'underline' }}
                      onClick={(e) => e.stopPropagation()}
                    >
                      conditions générales d'utilisation
                    </a>
                    {' '}d'Afroboost *
                  </label>
                </div>

                {error && (
                  <div style={{ padding: '12px', borderRadius: '8px', background: 'rgba(239,68,68,0.15)', border: '1px solid rgba(239,68,68,0.4)', color: '#fca5a5', fontSize: '14px' }}>
                    {error}
                  </div>
                )}

                {/* v11.0: Sélecteur de méthode de paiement */}
                {selectedPack.price > 0 && (
                  <PaymentMethodSelector
                    selected={paymentMethod}
                    onSelect={setPaymentMethod}
                    priceChf={selectedPack.price}
                    priceXof={selectedPack.price_xof}
                    disabled={submitting}
                  />
                )}

                {/* Récapitulatif */}
                <div style={{ paddingTop: '16px', borderTop: '1px solid rgba(255,255,255,0.1)' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                    <span style={{ color: 'rgba(255,255,255,0.7)' }}>Pack sélectionné:</span>
                    <span style={{ color: '#fff', fontWeight: '600' }}>{selectedPack.name}</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                    <span style={{ color: 'rgba(255,255,255,0.7)' }}>Crédits inclus:</span>
                    <span style={{ color: '#fff', fontWeight: '600' }}>{selectedPack.credits}</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ color: '#fff', fontSize: '18px' }}>Total:</span>
                    <span style={{ fontSize: '24px', fontWeight: '700', color: '#D91CD2' }}>
                      {paymentMethod === 'mobile_money'
                        ? `${(selectedPack.price_xof || Math.round(selectedPack.price * 400)).toLocaleString('fr-FR')} FCFA`
                        : `${selectedPack.price} CHF`
                      }
                    </span>
                  </div>
                </div>

                <button
                  type="submit"
                  disabled={submitting || !acceptedCGU || !formData.name || !formData.email || !formData.password}
                  style={{
                    width: '100%',
                    padding: '16px',
                    borderRadius: '12px',
                    color: '#fff',
                    fontWeight: '700',
                    fontSize: '18px',
                    border: 'none',
                    cursor: submitting ? 'wait' : 'pointer',
                    opacity: (submitting || !acceptedCGU || !formData.name || !formData.email || !formData.password) ? 0.5 : 1,
                    background: paymentMethod === 'mobile_money'
                      ? 'linear-gradient(135deg, #F59E0B, #D97706)'
                      : 'linear-gradient(135deg, #D91CD2, #8b5cf6)',
                    transition: 'all 0.2s',
                    transform: 'scale(1)'
                  }}
                  data-testid="submit-coach-registration"
                >
                  {submitting
                    ? 'Traitement...'
                    : selectedPack.price > 0
                      ? paymentMethod === 'mobile_money'
                        ? `Payer via Mobile Money`
                        : `Payer ${selectedPack.price} CHF`
                      : 'S\'inscrire gratuitement'
                  }
                </button>
              </form>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default BecomeCoachPage;
