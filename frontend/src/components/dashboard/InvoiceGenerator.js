// V199: Générateur de factures PDF — utilise POST /api/invoices/generate
import React, { useState } from 'react';
import axios from 'axios';
import SvgIcon from '../SvgIcon';

const API = (process.env.REACT_APP_BACKEND_URL || '') + '/api';

const inputStyle = {
  background: '#0a0a1a',
  border: '1px solid #333',
  borderRadius: '8px',
  color: '#fff',
  padding: '8px 12px',
  fontSize: '13px',
  width: '100%',
  boxSizing: 'border-box',
};

const InvoiceGenerator = ({ coachEmail }) => {
  // V199: Émetteur pré-rempli avec les infos Association Afroboosteur
  const [emitter, setEmitter] = useState({
    name: 'Association Afroboosteur',
    address: 'Rue de Maillefer 39',
    city: '2000 Neuchâtel',
    iban: 'CH77 0900 0000 1688 2939 4',
    ide: 'CHE-407.097.646',
    contact: 'Bassi Henri',
  });

  const [recipient, setRecipient] = useState({ name: '', address: '', city: '' });
  const [items, setItems] = useState([{ description: '', quantity: 1, unit_price: 0 }]);
  const [notes, setNotes] = useState(
    "Paiement à l'avance par virement bancaire.\nUtilisation des séances dès réception du paiement."
  );
  const [loading, setLoading] = useState(false);
  const [aiLoading, setAiLoading] = useState(false);

  const addItem = () => setItems(prev => prev.concat([{ description: '', quantity: 1, unit_price: 0 }]));
  const removeItem = (index) => setItems(prev => prev.filter((_, i) => i !== index));
  const updateItem = (index, field, value) => {
    setItems(prev => {
      const copy = prev.slice();
      copy[index] = { ...copy[index], [field]: value };
      return copy;
    });
  };

  const total = items.reduce((sum, it) => {
    const q = parseFloat(it.quantity) || 0;
    const p = parseFloat(it.unit_price) || 0;
    return sum + q * p;
  }, 0);

  // V199: Bouton IA — réutilise /api/ai/enhance-text avec context 'legal' (le seul approprié pour des modalités)
  const enhanceNotesWithAI = async () => {
    if (!notes || !notes.trim()) {
      // Pour le bouton "✨ Auto IA" partant de zéro on injecte une base courte que l'IA va enrichir
      setNotes("Paiement à l'avance par virement bancaire. IBAN ci-dessus. Utilisation des séances dès réception du paiement.");
      // Laisser un tick pour que le state se propage avant le call
      setTimeout(() => enhanceNotesWithAI(), 50);
      return;
    }
    setAiLoading(true);
    try {
      const res = await axios.post(`${API}/ai/enhance-text`, { text: notes, context: 'legal' });
      if (res?.data?.enhanced_text && !res.data.fallback) {
        setNotes(res.data.enhanced_text);
      }
    } catch (e) {
      console.error('[V199 AI notes]', e?.message || e);
    } finally {
      setAiLoading(false);
    }
  };

  const generatePDF = async () => {
    if (loading) return;
    setLoading(true);
    try {
      const res = await fetch(`${API}/invoices/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-User-Email': coachEmail || '' },
        body: JSON.stringify({
          emitter,
          recipient,
          items: items.map(it => ({
            description: it.description,
            quantity: parseFloat(it.quantity) || 0,
            unit_price: parseFloat(it.unit_price) || 0,
            total: (parseFloat(it.quantity) || 0) * (parseFloat(it.unit_price) || 0),
          })),
          notes,
        }),
      });
      if (!res.ok) throw new Error('HTTP ' + res.status);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      const safeName = (recipient.name || 'afroboost').replace(/[^a-zA-Z0-9_-]+/g, '_');
      a.download = `facture_${safeName}.pdf`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (e) {
      console.error('[V199 PDF]', e?.message || e);
      alert('Erreur lors de la génération du PDF');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ padding: '16px' }} data-testid="invoice-generator">
      {/* === Émetteur === */}
      <h4 style={{ color: 'var(--primary-color, #D91CD2)', marginBottom: '8px', fontSize: '14px', fontWeight: 600 }}>Émetteur</h4>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', marginBottom: '16px' }}>
        <input value={emitter.name} onChange={e => setEmitter({ ...emitter, name: e.target.value })} placeholder="Nom" style={inputStyle} />
        <input value={emitter.address} onChange={e => setEmitter({ ...emitter, address: e.target.value })} placeholder="Adresse" style={inputStyle} />
        <input value={emitter.city} onChange={e => setEmitter({ ...emitter, city: e.target.value })} placeholder="Ville" style={inputStyle} />
        <input value={emitter.iban} onChange={e => setEmitter({ ...emitter, iban: e.target.value })} placeholder="IBAN" style={inputStyle} />
        <input value={emitter.ide} onChange={e => setEmitter({ ...emitter, ide: e.target.value })} placeholder="N° IDE" style={inputStyle} />
        <input value={emitter.contact} onChange={e => setEmitter({ ...emitter, contact: e.target.value })} placeholder="Contact" style={inputStyle} />
      </div>

      {/* === Destinataire === */}
      <h4 style={{ color: '#8B5CF6', marginBottom: '8px', fontSize: '14px', fontWeight: 600 }}>Destinataire</h4>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', marginBottom: '16px' }}>
        <input value={recipient.name} onChange={e => setRecipient({ ...recipient, name: e.target.value })} placeholder="Nom du destinataire" style={inputStyle} />
        <input value={recipient.address} onChange={e => setRecipient({ ...recipient, address: e.target.value })} placeholder="Adresse" style={inputStyle} />
        <input value={recipient.city} onChange={e => setRecipient({ ...recipient, city: e.target.value })} placeholder="Ville" style={inputStyle} />
      </div>

      {/* === Prestations === */}
      <h4 style={{ color: '#FF2DAA', marginBottom: '8px', fontSize: '14px', fontWeight: 600 }}>Prestations</h4>
      {items.map((it, index) => (
        <div
          key={index}
          style={{ display: 'grid', gridTemplateColumns: '2fr 70px 110px 110px 40px', gap: '8px', marginBottom: '6px', alignItems: 'center' }}
        >
          <input value={it.description} onChange={e => updateItem(index, 'description', e.target.value)} placeholder="Description" style={inputStyle} />
          <input type="number" min="0" value={it.quantity} onChange={e => updateItem(index, 'quantity', e.target.value)} placeholder="Qté" style={inputStyle} />
          <input type="number" min="0" step="0.01" value={it.unit_price} onChange={e => updateItem(index, 'unit_price', e.target.value)} placeholder="Prix unit." style={inputStyle} />
          <div style={{ color: '#fff', fontSize: '13px', fontWeight: 600 }}>
            {((parseFloat(it.quantity) || 0) * (parseFloat(it.unit_price) || 0)).toFixed(2)} CHF
          </div>
          <button
            onClick={() => removeItem(index)}
            disabled={items.length === 1}
            style={{ background: items.length === 1 ? '#333' : '#ff4444', border: 'none', borderRadius: '8px', color: '#fff', cursor: items.length === 1 ? 'not-allowed' : 'pointer', padding: '6px 8px' }}
            title="Supprimer la ligne"
            aria-label="Supprimer la ligne"
          ><SvgIcon name="close" size={14} /></button>
        </div>
      ))}
      <button
        onClick={addItem}
        style={{ background: 'transparent', border: '1px dashed #555', borderRadius: '8px', color: '#888', padding: '8px', width: '100%', cursor: 'pointer', marginBottom: '16px' }}
      >+ Ajouter une ligne</button>

      <div style={{ textAlign: 'right', color: 'var(--primary-color, #D91CD2)', fontSize: '18px', fontWeight: 700, marginBottom: '16px' }}>
        Total : {total.toFixed(2)} CHF
      </div>

      {/* === Modalités === */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
        <h4 style={{ color: '#888', margin: 0, fontSize: '14px', fontWeight: 600 }}>Modalités de paiement</h4>
        <button
          onClick={enhanceNotesWithAI}
          disabled={aiLoading}
          style={{ padding: '4px 10px', background: aiLoading ? 'rgba(139,92,246,0.3)' : 'linear-gradient(135deg, var(--primary-color, #D91CD2), #8B5CF6)', border: 'none', borderRadius: '8px', color: '#fff', fontSize: '11px', cursor: aiLoading ? 'wait' : 'pointer', fontWeight: 600 }}
          title="Améliorer les modalités avec l'IA"
        >
          {aiLoading
            ? <span style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}><SvgIcon name="loader" size={14} className="animate-spin" /> IA…</span>
            : <span style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}><SvgIcon name="sparkles" size={14} /> Auto IA</span>}
        </button>
      </div>
      <textarea
        value={notes}
        onChange={e => setNotes(e.target.value)}
        rows={3}
        style={{ ...inputStyle, resize: 'vertical' }}
        placeholder="Paiement à l'avance par virement bancaire..."
      />

      {/* === Action: Générer PDF === */}
      <button
        onClick={generatePDF}
        disabled={loading || items.every(it => !it.description && !it.unit_price)}
        style={{
          width: '100%', padding: '14px', marginTop: '16px',
          background: 'linear-gradient(135deg, var(--primary-color, #D91CD2), #8B5CF6)',
          border: 'none', borderRadius: '12px', color: '#fff',
          fontSize: '16px', fontWeight: 700,
          cursor: loading ? 'wait' : 'pointer',
          opacity: loading ? 0.7 : 1,
          display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px',
        }}
        data-testid="invoice-generate-btn"
      >
        {loading
          ? <><SvgIcon name="loader" size={16} className="animate-spin" />Génération en cours…</>
          : <><SvgIcon name="file" size={16} />Générer la facture PDF</>}
      </button>
    </div>
  );
};

export default InvoiceGenerator;
