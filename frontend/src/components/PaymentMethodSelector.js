/**
 * PaymentMethodSelector - Composant réutilisable de sélection de méthode de paiement
 * Permet de choisir entre Carte Bancaire (Stripe) et Mobile Money (CinetPay)
 * v11.0 — Paiements Internationaux
 * V325 — option supplémentaire « Mobile Money (PawaPay) », affichée UNIQUEMENT si
 *        `showPawapay` est vrai (drapeau PAWAPAY_ENABLED + prestataire configuré).
 *        Drapeau OFF -> le composant est strictement identique à avant V325.
 */
import { useState } from "react";

// Icônes SVG
const CardIcon = () => (
  <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    <rect x="1" y="4" width="22" height="16" rx="2" ry="2"/>
    <line x1="1" y1="10" x2="23" y2="10"/>
  </svg>
);

const MobileMoneyIcon = () => (
  <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    <rect x="5" y="2" width="14" height="20" rx="2" ry="2"/>
    <line x1="12" y1="18" x2="12.01" y2="18"/>
    <path d="M9 6h6" />
  </svg>
);

// V325: icône PawaPay — globe + onde, pour distinguer visuellement les deux
// agrégateurs Mobile Money. SVG inline (règle projet : jamais d'emoji comme icône).
const PawaPayIcon = () => (
  <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="9" />
    <path d="M3 12h18" />
    <path d="M12 3a14 14 0 0 1 0 18a14 14 0 0 1 0-18z" />
  </svg>
);

const CheckCircleIcon = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
    <polyline points="22 4 12 14.01 9 11.01"/>
  </svg>
);

/**
 * @param {Object} props
 * @param {string} props.selected - "card" | "mobile_money" | "pawapay"
 * @param {function} props.onSelect - callback(method)
 * @param {number} props.priceChf - Prix en CHF
 * @param {number} props.priceXof - Prix en FCFA (si fourni)
 * @param {boolean} props.disabled - Désactiver la sélection
 * @param {boolean} props.showPawapay - V325: afficher l'option PawaPay (défaut: non)
 */
const PaymentMethodSelector = ({ selected, onSelect, priceChf, priceXof, disabled = false, showPawapay = false }) => {
  const [hoveredMethod, setHoveredMethod] = useState(null);

  // Calculer le prix FCFA si pas fourni (taux approximatif)
  const displayXof = priceXof || Math.round(priceChf * 400);

  const methods = [
    {
      id: "card",
      label: "Carte Bancaire",
      subtitle: "Visa, Mastercard, TWINT",
      price: `${priceChf} CHF`,
      icon: <CardIcon />,
      color: "#4F46E5",
      providers: ["Visa", "Mastercard", "TWINT"]
    },
    {
      id: "mobile_money",
      label: "Mobile Money",
      subtitle: "MTN, Orange, Moov/Airtel",
      price: `${displayXof.toLocaleString('fr-FR')} FCFA`,
      icon: <MobileMoneyIcon />,
      color: "#F59E0B",
      providers: ["MTN Money", "Orange Money", "Moov Money"]
    }
  ];

  // V325: PawaPay ajouté SEULEMENT si activé — sinon `methods` est celui d'avant.
  if (showPawapay) {
    methods.push({
      id: "pawapay",
      label: "Mobile Money +",
      subtitle: "M-Pesa, MTN, Orange, Airtel",
      price: `${displayXof.toLocaleString('fr-FR')} FCFA`,
      icon: <PawaPayIcon />,
      color: "#10B981",
      providers: ["M-Pesa", "MTN MoMo", "Orange Money", "Airtel Money"]
    });
  }

  // V325: à 2 méthodes la grille reste exactement '1fr 1fr' (aucun changement visuel
  // quand PawaPay est OFF) ; à 3 elle s'adapte et se replie sur mobile.
  const gridColumns = methods.length > 2
    ? 'repeat(auto-fit, minmax(130px, 1fr))'
    : '1fr 1fr';

  return (
    <div style={{ marginBottom: '16px' }}>
      <p style={{ color: 'rgba(255,255,255,0.7)', fontSize: '14px', marginBottom: '12px', fontWeight: '500' }}>
        Méthode de paiement
      </p>
      <div style={{ display: 'grid', gridTemplateColumns: gridColumns, gap: '12px' }}>
        {methods.map((method) => {
          const isSelected = selected === method.id;
          const isHovered = hoveredMethod === method.id;

          return (
            <button
              key={method.id}
              type="button"
              disabled={disabled}
              onClick={() => onSelect(method.id)}
              onMouseEnter={() => setHoveredMethod(method.id)}
              onMouseLeave={() => setHoveredMethod(null)}
              style={{
                position: 'relative',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                padding: '16px 12px',
                borderRadius: '12px',
                border: isSelected
                  ? `2px solid ${method.color}`
                  : '1px solid rgba(255,255,255,0.15)',
                background: isSelected
                  ? `${method.color}15`
                  : isHovered
                    ? 'rgba(255,255,255,0.08)'
                    : 'rgba(255,255,255,0.04)',
                cursor: disabled ? 'not-allowed' : 'pointer',
                opacity: disabled ? 0.5 : 1,
                transition: 'all 0.2s ease',
                transform: isSelected ? 'scale(1.02)' : 'scale(1)',
                textAlign: 'center',
                outline: 'none',
                width: '100%'
              }}
              data-testid={`payment-method-${method.id}`}
            >
              {/* Badge sélectionné */}
              {isSelected && (
                <div style={{
                  position: 'absolute',
                  top: '8px',
                  right: '8px',
                  color: method.color
                }}>
                  <CheckCircleIcon />
                </div>
              )}

              {/* Icône */}
              <div style={{
                color: isSelected ? method.color : 'rgba(255,255,255,0.6)',
                marginBottom: '8px',
                transition: 'color 0.2s'
              }}>
                {method.icon}
              </div>

              {/* Label */}
              <div style={{
                color: isSelected ? '#fff' : 'rgba(255,255,255,0.8)',
                fontWeight: '600',
                fontSize: '14px',
                marginBottom: '2px'
              }}>
                {method.label}
              </div>

              {/* Sous-titre providers */}
              <div style={{
                color: 'rgba(255,255,255,0.45)',
                fontSize: '11px',
                marginBottom: '8px'
              }}>
                {method.subtitle}
              </div>

              {/* Prix */}
              <div style={{
                color: isSelected ? method.color : 'rgba(255,255,255,0.6)',
                fontWeight: '700',
                fontSize: '16px',
                transition: 'color 0.2s'
              }}>
                {method.price}
              </div>
            </button>
          );
        })}
      </div>

      {/* Info sous le sélecteur */}
      {selected === 'mobile_money' && (
        <div style={{
          marginTop: '10px',
          padding: '10px 14px',
          borderRadius: '8px',
          background: 'rgba(245, 158, 11, 0.1)',
          border: '1px solid rgba(245, 158, 11, 0.25)',
          fontSize: '12px',
          color: 'rgba(255,255,255,0.6)'
        }}>
          💡 Vous serez redirigé vers CinetPay pour finaliser le paiement via Mobile Money.
          Disponible dans 10 pays d'Afrique francophone.
        </div>
      )}
      {selected === 'pawapay' && (
        <div style={{
          marginTop: '10px',
          padding: '10px 14px',
          borderRadius: '8px',
          background: 'rgba(16, 185, 129, 0.1)',
          border: '1px solid rgba(16, 185, 129, 0.25)',
          fontSize: '12px',
          color: 'rgba(255,255,255,0.6)'
        }}>
          💡 Vous serez redirigé vers PawaPay pour payer avec votre portefeuille mobile
          (M-Pesa, MTN MoMo, Orange Money, Airtel Money…).
        </div>
      )}
      {selected === 'card' && (
        <div style={{
          marginTop: '10px',
          padding: '10px 14px',
          borderRadius: '8px',
          background: 'rgba(79, 70, 229, 0.1)',
          border: '1px solid rgba(79, 70, 229, 0.25)',
          fontSize: '12px',
          color: 'rgba(255,255,255,0.6)'
        }}>
          🔒 Paiement sécurisé par Stripe. Carte bancaire et TWINT acceptés.
        </div>
      )}
    </div>
  );
};

export default PaymentMethodSelector;
