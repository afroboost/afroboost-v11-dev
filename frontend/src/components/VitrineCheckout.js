// v15.0: Integrated Checkout for Partner Vitrine
import React, { useState, useEffect } from 'react';
import axios from 'axios';

const API = process.env.REACT_APP_BACKEND_URL || '';

const VitrineCheckout = ({
  coachEmail,        // Email du partenaire/vendeur
  coachName,         // Nom du partenaire
  selectedBookings,  // [{course, date}] — sessions sélectionnées
  selectedOffer,     // {id, name, price} — offre sélectionnée
  customerName,      // Nom du client (depuis le formulaire de booking)
  customerEmail,     // Email du client
  customerPhone,     // Téléphone du client
  appliedDiscount,   // {type, value, code} — réduction appliquée
  onSuccess,         // Callback après paiement réussi
  onCancel           // Callback si annulation
}) => {
  const [availableMethods, setAvailableMethods] = useState([]);
  const [isConfigured, setIsConfigured] = useState(false);
  const [loading, setLoading] = useState(true);
  const [selectedMethod, setSelectedMethod] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  // Charger les méthodes de paiement disponibles du partenaire
  useEffect(() => {
    const loadPaymentStatus = async () => {
      try {
        const res = await axios.get(`${API}/api/payment-config/status/${encodeURIComponent(coachEmail)}`);
        setAvailableMethods(res.data.available_methods || []);
        setIsConfigured(res.data.is_configured || false);
        // Sélectionner la première méthode par défaut
        if (res.data.available_methods?.length > 0) {
          setSelectedMethod(res.data.available_methods[0]);
        }
      } catch (err) {
        console.error('[CHECKOUT] Erreur chargement config:', err);
        setIsConfigured(false);
      } finally {
        setLoading(false);
      }
    };
    if (coachEmail) loadPaymentStatus();
  }, [coachEmail]);

  // Calculer les items et le total
  const items = [];

  if (selectedBookings?.length > 0) {
    selectedBookings.forEach(b => {
      items.push({
        type: 'course',
        id: b.course?.id || '',
        name: b.course?.name || b.course?.title || 'Séance',
        price: selectedOffer?.price || 0,
        currency: 'CHF',
        quantity: 1
      });
    });
  }

  if (selectedOffer && (!selectedBookings || selectedBookings.length === 0)) {
    items.push({
      type: selectedOffer.type === 'audio' ? 'audio' : (selectedOffer.isProduct ? 'product' : 'offer'),
      id: selectedOffer.id || '',
      name: selectedOffer.name || 'Article',
      price: selectedOffer.price || 0,
      currency: 'CHF',
      quantity: 1
    });
  }

  // Calculer le total avec réduction
  let subtotal = items.reduce((sum, i) => sum + i.price * i.quantity, 0);
  let discountAmount = 0;

  if (appliedDiscount) {
    if (appliedDiscount.type === '100%') {
      discountAmount = subtotal;
    } else if (appliedDiscount.type === '%') {
      discountAmount = subtotal * (appliedDiscount.value / 100);
    } else {
      discountAmount = appliedDiscount.value || 0;
    }
  }

  const total = Math.max(0, subtotal - discountAmount);

  // Soumettre le paiement
  const handlePay = async () => {
    if (!selectedMethod || submitting) return;
    setSubmitting(true);
    setError('');

    try {
      const res = await axios.post(`${API}/api/checkout/create-session`, {
        coach_email: coachEmail,
        payment_method: selectedMethod,
        items: items,
        customer_name: customerName,
        customer_email: customerEmail,
        customer_phone: customerPhone || '',
        discount_code: appliedDiscount?.code || null,
        discount_amount: discountAmount > 0 ? discountAmount : null
      });

      if (res.data.free) {
        // Paiement gratuit — succès immédiat
        onSuccess?.(res.data);
        return;
      }

      if (res.data.payment_url) {
        // Rediriger vers la passerelle de paiement
        window.location.href = res.data.payment_url;
      }
    } catch (err) {
      console.error('[CHECKOUT] Erreur:', err);
      const detail = err.response?.data?.detail || '';
      if (detail.includes('non configuré') || err.response?.status === 400) {
        setError(detail || 'Cette méthode de paiement n\'est pas disponible. Essayez une autre méthode.');
      } else {
        setError('Erreur lors du paiement. Veuillez réessayer.');
      }
    } finally {
      setSubmitting(false);
    }
  };

  // === STYLES ===
  const containerStyle = {
    background: 'rgba(255,255,255,0.03)',
    border: '1px solid rgba(217, 28, 210, 0.2)',
    borderRadius: '16px',
    padding: '24px',
    marginTop: '16px'
  };

  const methodCardStyle = (id) => ({
    flex: 1,
    padding: '16px 12px',
    borderRadius: '10px',
    border: `2px solid ${selectedMethod === id ? '#D91CD2' : 'rgba(255,255,255,0.1)'}`,
    background: selectedMethod === id ? 'rgba(217, 28, 210, 0.08)' : 'rgba(255,255,255,0.02)',
    cursor: 'pointer',
    textAlign: 'center',
    transition: 'all 0.2s',
    position: 'relative'
  });

  const methodConfig = {
    card: { icon: '💳', label: 'Carte / TWINT', subtitle: 'Visa, Mastercard, TWINT' },
    paypal: { icon: '🅿️', label: 'PayPal', subtitle: 'Paiement sécurisé' },
    mobile_money: { icon: '📱', label: 'Mobile Money', subtitle: 'MTN, Orange, Moov' }
  };

  // === RENDER ===

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: '20px', color: 'rgba(255,255,255,0.4)' }}>
        Chargement des méthodes de paiement...
      </div>
    );
  }

  // Pas de prix ou gratuit → pas besoin de checkout
  if (total <= 0 && items.length > 0) {
    return (
      <div style={containerStyle}>
        <div style={{ textAlign: 'center', padding: '12px 0' }}>
          <p style={{ color: '#22c55e', fontSize: '16px', fontWeight: '600', margin: '0 0 12px' }}>
            Réservation gratuite
          </p>
          <button
            onClick={handlePay}
            disabled={submitting}
            style={{
              padding: '12px 40px',
              borderRadius: '10px',
              border: 'none',
              background: 'linear-gradient(135deg, #22c55e, #16a34a)',
              color: 'white',
              fontSize: '15px',
              fontWeight: '600',
              cursor: submitting ? 'wait' : 'pointer',
              opacity: submitting ? 0.6 : 1
            }}
          >
            {submitting ? 'Confirmation...' : 'Confirmer gratuitement'}
          </button>
        </div>
      </div>
    );
  }

  // Pas configuré
  if (!isConfigured || availableMethods.length === 0) {
    return (
      <div style={{
        background: 'rgba(245, 158, 11, 0.08)',
        border: '1px solid rgba(245, 158, 11, 0.2)',
        borderRadius: '12px',
        padding: '20px',
        textAlign: 'center',
        marginTop: '16px'
      }}>
        <p style={{ color: '#F59E0B', fontSize: '14px', fontWeight: '500', margin: '0 0 4px' }}>
          Paiement en ligne non disponible
        </p>
        <p style={{ color: 'rgba(255,255,255,0.5)', fontSize: '13px', margin: 0 }}>
          Contactez directement le coach pour réserver et payer.
        </p>
      </div>
    );
  }

  return (
    <div style={containerStyle}>
      {/* Récapitulatif */}
      {items.length > 0 && (
        <div style={{ marginBottom: '20px' }}>
          <h4 style={{ color: 'rgba(255,255,255,0.6)', fontSize: '13px', fontWeight: '500', margin: '0 0 10px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
            Récapitulatif
          </h4>
          {items.map((item, i) => (
            <div key={i} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '8px 0', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
              <span style={{ color: 'white', fontSize: '14px' }}>{item.name}</span>
              <span style={{ color: '#D91CD2', fontSize: '14px', fontWeight: '600' }}>{item.price} CHF</span>
            </div>
          ))}
          {discountAmount > 0 && (
            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
              <span style={{ color: '#22c55e', fontSize: '13px' }}>Réduction ({appliedDiscount?.code})</span>
              <span style={{ color: '#22c55e', fontSize: '13px' }}>-{discountAmount.toFixed(2)} CHF</span>
            </div>
          )}
          <div style={{ display: 'flex', justifyContent: 'space-between', padding: '12px 0 0', marginTop: '4px' }}>
            <span style={{ color: 'white', fontSize: '16px', fontWeight: '700' }}>Total</span>
            <span style={{ color: '#D91CD2', fontSize: '18px', fontWeight: '700' }}>{total.toFixed(2)} CHF</span>
          </div>
        </div>
      )}

      {/* Sélection méthode de paiement */}
      <div style={{ marginBottom: '20px' }}>
        <h4 style={{ color: 'rgba(255,255,255,0.6)', fontSize: '13px', fontWeight: '500', margin: '0 0 10px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
          Méthode de paiement
        </h4>
        <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
          {availableMethods.map(method => {
            const cfg = methodConfig[method];
            if (!cfg) return null;
            return (
              <div
                key={method}
                onClick={() => setSelectedMethod(method)}
                style={methodCardStyle(method)}
              >
                {selectedMethod === method && (
                  <div style={{ position: 'absolute', top: '6px', right: '6px', width: '18px', height: '18px', borderRadius: '50%', background: '#D91CD2', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <span style={{ color: 'white', fontSize: '11px' }}>✓</span>
                  </div>
                )}
                <div style={{ fontSize: '28px', marginBottom: '6px' }}>{cfg.icon}</div>
                <div style={{ color: 'white', fontSize: '14px', fontWeight: '600' }}>{cfg.label}</div>
                <div style={{ color: 'rgba(255,255,255,0.4)', fontSize: '11px', marginTop: '2px' }}>{cfg.subtitle}</div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Erreur */}
      {error && (
        <div style={{
          background: 'rgba(239, 68, 68, 0.1)',
          border: '1px solid rgba(239, 68, 68, 0.3)',
          borderRadius: '8px',
          padding: '10px 14px',
          marginBottom: '16px'
        }}>
          <p style={{ color: '#ef4444', fontSize: '13px', margin: 0 }}>{error}</p>
        </div>
      )}

      {/* Bouton Payer */}
      <button
        onClick={handlePay}
        disabled={submitting || !selectedMethod}
        style={{
          width: '100%',
          padding: '14px',
          borderRadius: '10px',
          border: 'none',
          background: submitting || !selectedMethod ? 'rgba(255,255,255,0.1)' : 'linear-gradient(135deg, #D91CD2, #8b5cf6)',
          color: 'white',
          fontSize: '16px',
          fontWeight: '600',
          cursor: submitting || !selectedMethod ? 'not-allowed' : 'pointer',
          transition: 'all 0.2s'
        }}
        data-testid="vitrine-pay-btn"
      >
        {submitting ? 'Redirection...' : `Payer ${total.toFixed(2)} CHF`}
      </button>

      {/* Security badge */}
      <div style={{ textAlign: 'center', marginTop: '12px' }}>
        <span style={{ color: 'rgba(255,255,255,0.3)', fontSize: '11px' }}>
          🔒 Paiement sécurisé — Vos données sont protégées
        </span>
      </div>
    </div>
  );
};

export default VitrineCheckout;
