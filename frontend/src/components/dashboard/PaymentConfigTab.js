// v15.0: Payment Configuration Tab - Multi-Vendor Payment System
import React, { useState } from 'react';
import axios from 'axios';

const API = process.env.REACT_APP_BACKEND_URL || '';

const PaymentConfigTab = ({ paymentConfig, setPaymentConfig, coachEmail }) => {
  const [saveStatus, setSaveStatus] = useState(null);
  const [testResults, setTestResults] = useState({});
  const [testing, setTesting] = useState({});

  const getHeaders = () => ({
    headers: { 'X-User-Email': coachEmail }
  });

  const handleChange = (field, value) => {
    const updated = { ...paymentConfig, [field]: value };
    setPaymentConfig(updated);

    // Auto-save avec debounce
    if (window._paymentSaveTimeout) clearTimeout(window._paymentSaveTimeout);
    window._paymentSaveTimeout = setTimeout(async () => {
      try {
        setSaveStatus('saving');
        await axios.put(`${API}/api/payment-config`, updated, getHeaders());
        setSaveStatus('saved');
        setTimeout(() => setSaveStatus(null), 2000);
      } catch (err) {
        console.error('[PAYMENT-CONFIG] Save error:', err);
        setSaveStatus('error');
      }
    }, 1500);
  };

  const handleTest = async (method) => {
    setTesting(prev => ({ ...prev, [method]: true }));
    setTestResults(prev => ({ ...prev, [method]: null }));
    try {
      const res = await axios.post(`${API}/api/payment-config/test/${method}`, {}, getHeaders());
      setTestResults(prev => ({ ...prev, [method]: res.data }));
    } catch (err) {
      setTestResults(prev => ({ ...prev, [method]: { success: false, message: err.response?.data?.detail || 'Erreur de connexion' } }));
    } finally {
      setTesting(prev => ({ ...prev, [method]: false }));
    }
  };

  const isConfigured = paymentConfig?.stripe_enabled || paymentConfig?.paypal_enabled || paymentConfig?.mobile_money_enabled;

  const sectionStyle = {
    background: 'rgba(255,255,255,0.03)',
    border: '1px solid rgba(255,255,255,0.1)',
    borderRadius: '12px',
    padding: '24px',
    marginBottom: '20px'
  };

  const inputStyle = {
    width: '100%',
    padding: '10px 14px',
    borderRadius: '8px',
    background: 'rgba(255,255,255,0.05)',
    border: '1px solid rgba(255,255,255,0.15)',
    color: 'white',
    fontSize: '14px',
    outline: 'none',
    fontFamily: 'monospace'
  };

  const labelStyle = {
    display: 'block',
    color: 'rgba(255,255,255,0.6)',
    fontSize: '13px',
    marginBottom: '6px',
    fontWeight: '500'
  };

  const toggleStyle = (enabled) => ({
    width: '44px',
    height: '24px',
    borderRadius: '12px',
    background: enabled ? '#D91CD2' : 'rgba(255,255,255,0.15)',
    cursor: 'pointer',
    position: 'relative',
    transition: 'background 0.2s',
    border: 'none',
    padding: 0,
    flexShrink: 0
  });

  const toggleKnobStyle = (enabled) => ({
    width: '18px',
    height: '18px',
    borderRadius: '50%',
    background: 'white',
    position: 'absolute',
    top: '3px',
    left: enabled ? '23px' : '3px',
    transition: 'left 0.2s'
  });

  const testBtnStyle = {
    padding: '8px 16px',
    borderRadius: '8px',
    border: '1px solid rgba(217, 28, 210, 0.5)',
    background: 'rgba(217, 28, 210, 0.1)',
    color: '#D91CD2',
    fontSize: '13px',
    cursor: 'pointer',
    fontWeight: '500'
  };

  return (
    <div style={{ maxWidth: '700px', margin: '0 auto' }} data-testid="payment-config-tab">
      {/* Header avec statut */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '24px' }}>
        <div>
          <h2 style={{ color: 'white', fontSize: '20px', fontWeight: 'bold', margin: 0 }}>
            Configuration des Paiements
          </h2>
          <p style={{ color: 'rgba(255,255,255,0.5)', fontSize: '13px', margin: '4px 0 0' }}>
            Configurez vos méthodes de paiement pour recevoir les paiements de vos clients
          </p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          {saveStatus === 'saving' && <span style={{ color: '#F59E0B', fontSize: '13px' }}>Sauvegarde...</span>}
          {saveStatus === 'saved' && <span style={{ color: '#22c55e', fontSize: '13px' }}>Sauvegardé</span>}
          {saveStatus === 'error' && <span style={{ color: '#ef4444', fontSize: '13px' }}>Erreur</span>}
          <span style={{
            padding: '4px 12px',
            borderRadius: '20px',
            fontSize: '12px',
            fontWeight: '600',
            background: isConfigured ? 'rgba(34, 197, 94, 0.15)' : 'rgba(239, 68, 68, 0.15)',
            color: isConfigured ? '#22c55e' : '#ef4444',
            border: `1px solid ${isConfigured ? 'rgba(34, 197, 94, 0.3)' : 'rgba(239, 68, 68, 0.3)'}`
          }}>
            {isConfigured ? 'Actif' : 'Non configuré'}
          </span>
        </div>
      </div>

      {/* Alerte si rien configuré */}
      {!isConfigured && (
        <div style={{
          background: 'rgba(245, 158, 11, 0.1)',
          border: '1px solid rgba(245, 158, 11, 0.3)',
          borderRadius: '10px',
          padding: '16px',
          marginBottom: '20px',
          display: 'flex',
          alignItems: 'flex-start',
          gap: '12px'
        }}>
          <span style={{ fontSize: '20px' }}>⚠️</span>
          <div>
            <p style={{ color: '#F59E0B', fontSize: '14px', fontWeight: '600', margin: '0 0 4px' }}>
              Paiements non configurés
            </p>
            <p style={{ color: 'rgba(255,255,255,0.6)', fontSize: '13px', margin: 0 }}>
              Vos clients ne pourront pas payer en ligne sur votre vitrine. Configurez au moins une méthode ci-dessous.
            </p>
          </div>
        </div>
      )}

      {/* ===== SECTION STRIPE ===== */}
      <div style={sectionStyle}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '20px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <span style={{ fontSize: '24px' }}>💳</span>
            <div>
              <h3 style={{ color: 'white', fontSize: '16px', fontWeight: '600', margin: 0 }}>Carte Bancaire & TWINT</h3>
              <p style={{ color: 'rgba(255,255,255,0.4)', fontSize: '12px', margin: '2px 0 0' }}>
                Via Stripe — Visa, Mastercard, TWINT (Suisse)
              </p>
            </div>
          </div>
          <button
            style={toggleStyle(paymentConfig?.stripe_enabled)}
            onClick={() => handleChange('stripe_enabled', !paymentConfig?.stripe_enabled)}
            data-testid="stripe-toggle"
          >
            <div style={toggleKnobStyle(paymentConfig?.stripe_enabled)} />
          </button>
        </div>

        {paymentConfig?.stripe_enabled && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
            <div>
              <label style={labelStyle}>Clé publique (pk_...)</label>
              <input
                type="text"
                value={paymentConfig?.stripe_publishable_key || ''}
                onChange={(e) => handleChange('stripe_publishable_key', e.target.value)}
                placeholder="pk_live_... ou pk_test_..."
                style={inputStyle}
                data-testid="stripe-pk-input"
              />
            </div>
            <div>
              <label style={labelStyle}>Clé secrète (sk_...)</label>
              <input
                type="password"
                value={paymentConfig?.stripe_secret_key || ''}
                onChange={(e) => handleChange('stripe_secret_key', e.target.value)}
                placeholder="sk_live_... ou sk_test_..."
                style={inputStyle}
                data-testid="stripe-sk-input"
              />
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              <button style={testBtnStyle} onClick={() => handleTest('stripe')} disabled={testing.stripe}>
                {testing.stripe ? 'Test...' : 'Tester la connexion'}
              </button>
              {testResults.stripe && (
                <span style={{ fontSize: '13px', color: testResults.stripe.success ? '#22c55e' : '#ef4444' }}>
                  {testResults.stripe.message}
                </span>
              )}
            </div>
          </div>
        )}
      </div>

      {/* ===== SECTION PAYPAL ===== */}
      <div style={sectionStyle}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '20px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <span style={{ fontSize: '24px' }}>🅿️</span>
            <div>
              <h3 style={{ color: 'white', fontSize: '16px', fontWeight: '600', margin: 0 }}>PayPal</h3>
              <p style={{ color: 'rgba(255,255,255,0.4)', fontSize: '12px', margin: '2px 0 0' }}>
                Paiement international sécurisé
              </p>
            </div>
          </div>
          <button
            style={toggleStyle(paymentConfig?.paypal_enabled)}
            onClick={() => handleChange('paypal_enabled', !paymentConfig?.paypal_enabled)}
            data-testid="paypal-toggle"
          >
            <div style={toggleKnobStyle(paymentConfig?.paypal_enabled)} />
          </button>
        </div>

        {paymentConfig?.paypal_enabled && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
            <div>
              <label style={labelStyle}>Client ID</label>
              <input
                type="text"
                value={paymentConfig?.paypal_client_id || ''}
                onChange={(e) => handleChange('paypal_client_id', e.target.value)}
                placeholder="Votre Client ID PayPal"
                style={inputStyle}
                data-testid="paypal-id-input"
              />
            </div>
            <div>
              <label style={labelStyle}>Client Secret</label>
              <input
                type="password"
                value={paymentConfig?.paypal_client_secret || ''}
                onChange={(e) => handleChange('paypal_client_secret', e.target.value)}
                placeholder="Votre Client Secret PayPal"
                style={inputStyle}
                data-testid="paypal-secret-input"
              />
            </div>
            <div>
              <label style={labelStyle}>Mode</label>
              <div style={{ display: 'flex', gap: '10px' }}>
                {['sandbox', 'live'].map(mode => (
                  <button key={mode} onClick={() => handleChange('paypal_mode', mode)}
                    style={{
                      padding: '8px 20px',
                      borderRadius: '8px',
                      border: `1px solid ${paymentConfig?.paypal_mode === mode ? '#D91CD2' : 'rgba(255,255,255,0.15)'}`,
                      background: paymentConfig?.paypal_mode === mode ? 'rgba(217, 28, 210, 0.15)' : 'rgba(255,255,255,0.03)',
                      color: paymentConfig?.paypal_mode === mode ? '#D91CD2' : 'rgba(255,255,255,0.5)',
                      cursor: 'pointer',
                      fontSize: '13px',
                      fontWeight: '500',
                      textTransform: 'capitalize'
                    }}
                  >
                    {mode === 'sandbox' ? '🧪 Sandbox (Test)' : '🟢 Live (Production)'}
                  </button>
                ))}
              </div>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              <button style={testBtnStyle} onClick={() => handleTest('paypal')} disabled={testing.paypal}>
                {testing.paypal ? 'Test...' : 'Tester la connexion'}
              </button>
              {testResults.paypal && (
                <span style={{ fontSize: '13px', color: testResults.paypal.success ? '#22c55e' : '#ef4444' }}>
                  {testResults.paypal.message}
                </span>
              )}
            </div>
          </div>
        )}
      </div>

      {/* ===== SECTION MOBILE MONEY ===== */}
      <div style={sectionStyle}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '20px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <span style={{ fontSize: '24px' }}>📱</span>
            <div>
              <h3 style={{ color: 'white', fontSize: '16px', fontWeight: '600', margin: 0 }}>Mobile Money</h3>
              <p style={{ color: 'rgba(255,255,255,0.4)', fontSize: '12px', margin: '2px 0 0' }}>
                Via CinetPay — MTN, Orange, Moov (Afrique)
              </p>
            </div>
          </div>
          <button
            style={toggleStyle(paymentConfig?.mobile_money_enabled)}
            onClick={() => handleChange('mobile_money_enabled', !paymentConfig?.mobile_money_enabled)}
            data-testid="mobile-money-toggle"
          >
            <div style={toggleKnobStyle(paymentConfig?.mobile_money_enabled)} />
          </button>
        </div>

        {paymentConfig?.mobile_money_enabled && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
            <div>
              <label style={labelStyle}>API Key CinetPay</label>
              <input
                type="password"
                value={paymentConfig?.cinetpay_api_key || ''}
                onChange={(e) => handleChange('cinetpay_api_key', e.target.value)}
                placeholder="Votre API Key CinetPay"
                style={inputStyle}
                data-testid="cinetpay-key-input"
              />
            </div>
            <div>
              <label style={labelStyle}>Site ID</label>
              <input
                type="text"
                value={paymentConfig?.cinetpay_site_id || ''}
                onChange={(e) => handleChange('cinetpay_site_id', e.target.value)}
                placeholder="Votre Site ID CinetPay"
                style={inputStyle}
                data-testid="cinetpay-site-input"
              />
            </div>
            <div>
              <label style={labelStyle}>Secret Key</label>
              <input
                type="password"
                value={paymentConfig?.cinetpay_secret_key || ''}
                onChange={(e) => handleChange('cinetpay_secret_key', e.target.value)}
                placeholder="Votre Secret Key CinetPay"
                style={inputStyle}
                data-testid="cinetpay-secret-input"
              />
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              <button style={testBtnStyle} onClick={() => handleTest('mobile_money')} disabled={testing.mobile_money}>
                {testing.mobile_money ? 'Test...' : 'Tester la connexion'}
              </button>
              {testResults.mobile_money && (
                <span style={{ fontSize: '13px', color: testResults.mobile_money.success ? '#22c55e' : '#ef4444' }}>
                  {testResults.mobile_money.message}
                </span>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Info box */}
      <div style={{
        background: 'rgba(99, 91, 255, 0.08)',
        border: '1px solid rgba(99, 91, 255, 0.2)',
        borderRadius: '10px',
        padding: '16px',
        display: 'flex',
        alignItems: 'flex-start',
        gap: '10px'
      }}>
        <span style={{ fontSize: '16px' }}>💡</span>
        <p style={{ color: 'rgba(255,255,255,0.5)', fontSize: '12px', margin: 0, lineHeight: '1.5' }}>
          Vos clés API sont stockées de manière sécurisée. Les paiements de vos clients seront versés directement sur votre compte.
          Pour obtenir vos clés : Stripe → dashboard.stripe.com | PayPal → developer.paypal.com | CinetPay → cinetpay.com
        </p>
      </div>
    </div>
  );
};

export default PaymentConfigTab;
