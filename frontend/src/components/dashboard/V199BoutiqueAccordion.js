// V199: Accordéon Paiements — 5 sections pliables
import React, { useState } from 'react';
import SvgIcon from '../SvgIcon';
import ConceptEditor from './ConceptEditor';
import PaymentConfigTab from './PaymentConfigTab';
import InvoiceGenerator from './InvoiceGenerator';

const headerStyle = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  padding: '14px 16px',
  cursor: 'pointer',
  background: '#1a1a2e',
  borderRadius: '12px',
  marginBottom: '6px',
  border: '1px solid #2a2a3e',
};

const labelStyle = {
  color: '#fff',
  fontWeight: 600,
  fontSize: '15px',
};

const bodyStyle = {
  padding: '12px',
  background: '#111',
  borderRadius: '12px',
  marginBottom: '18px',
  border: '1px solid #2a2a3e',
};

const AccordionSection = ({ id, icon, label, openMap, setOpenMap, children }) => {
  const open = !!openMap[id];
  return (
    <div data-testid={`v199-accordion-${id}`}>
      <div
        onClick={() => setOpenMap(prev => ({ ...prev, [id]: !prev[id] }))}
        style={headerStyle}
        role="button"
        aria-expanded={open}
      >
        <span style={labelStyle}>
          <span style={{ marginRight: '8px' }}>{icon}</span>
          {label}
        </span>
        <span
          style={{
            color: '#888',
            transition: 'transform 0.2s',
            transform: open ? 'rotate(180deg)' : 'rotate(0deg)',
            display: 'inline-block',
          }}
        ><SvgIcon name="arrowDown" size={16} /></span>
      </div>
      {open && <div style={bodyStyle}>{children}</div>}
    </div>
  );
};

const V199BoutiqueAccordion = ({
  concept,
  setConcept,
  conceptSaveStatus,
  saveConcept,
  API,
  t,
  isSuperAdmin,
  safeCoachUser,
  courses,
  setCourses,
  coachUser,
  vendorPaymentConfig,
  setVendorPaymentConfig,
}) => {
  // V199: Seul Configuration des Paiements ouvert par défaut
  const [openMap, setOpenMap] = useState({
    payments: true,
    conditions: false,
    logos: false,
    invoices: false,
    landing: false,
  });

  const conceptProps = {
    concept,
    setConcept,
    conceptSaveStatus,
    saveConcept,
    API,
    t,
    isSuperAdmin,
    coachEmail: safeCoachUser?.email || '',
    courses,
    setCourses,
  };

  return (
    <div style={{ maxWidth: '900px', margin: '0 auto' }}>
      {/* 1. Configuration des Paiements (ouvert par défaut) */}
      <AccordionSection id="payments" icon={<SvgIcon name="creditCard" size={16} />} label="Configuration des Paiements" openMap={openMap} setOpenMap={setOpenMap}>
        <PaymentConfigTab
          paymentConfig={vendorPaymentConfig}
          setPaymentConfig={setVendorPaymentConfig}
          coachEmail={coachUser?.email}
        />
      </AccordionSection>

      {/* 2. Conditions & Avis */}
      <AccordionSection id="conditions" icon={<SvgIcon name="edit" size={16} />} label="Conditions & Avis" openMap={openMap} setOpenMap={setOpenMap}>
        <ConceptEditor {...conceptProps} section="conditions" />
      </AccordionSection>

      {/* 3. Logos de paiement */}
      <AccordionSection id="logos" icon={<SvgIcon name="palette" size={16} />} label="Logos de paiement" openMap={openMap} setOpenMap={setOpenMap}>
        <ConceptEditor {...conceptProps} section="logos" />
      </AccordionSection>

      {/* 4. Générateur de Factures (NOUVEAU) */}
      <AccordionSection id="invoices" icon={<SvgIcon name="file" size={16} />} label="Générateur de Factures" openMap={openMap} setOpenMap={setOpenMap}>
        <InvoiceGenerator coachEmail={coachUser?.email} />
      </AccordionSection>

      {/* 5. Section d'atterrissage */}
      <AccordionSection id="landing" icon={<SvgIcon name="home" size={16} />} label="Section d'atterrissage" openMap={openMap} setOpenMap={setOpenMap}>
        <ConceptEditor {...conceptProps} section="landing" />
      </AccordionSection>
    </div>
  );
};

export default V199BoutiqueAccordion;
