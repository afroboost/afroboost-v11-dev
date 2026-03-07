/**
 * FAQManager Component v17.2
 * CRUD FAQ + Génération IA de réponses
 */
import React, { useState, useEffect, useCallback } from 'react';

const FAQManager = ({ API, coachEmail, t }) => {
  const [faqs, setFaqs] = useState([]);
  const [newQuestion, setNewQuestion] = useState('');
  const [newAnswer, setNewAnswer] = useState('');
  const [editingId, setEditingId] = useState(null);
  const [aiLoading, setAiLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  const loadFaqs = useCallback(async () => {
    if (!coachEmail) return;
    try {
      const res = await fetch(`${API}/coach/faqs/${coachEmail}`);
      const data = await res.json();
      setFaqs(Array.isArray(data) ? data : []);
    } catch {
      setFaqs([]);
    }
  }, [API, coachEmail]);

  useEffect(() => { loadFaqs(); }, [loadFaqs]);

  const handleSave = async (e) => {
    e?.preventDefault();
    if (!newQuestion.trim()) return;
    setSaving(true);
    try {
      if (editingId) {
        await fetch(`${API}/coach/faq/${editingId}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json', 'X-User-Email': coachEmail },
          body: JSON.stringify({ question: newQuestion, answer: newAnswer })
        });
      } else {
        await fetch(`${API}/coach/faq`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-User-Email': coachEmail },
          body: JSON.stringify({ question: newQuestion, answer: newAnswer, order: faqs.length })
        });
      }
      setNewQuestion('');
      setNewAnswer('');
      setEditingId(null);
      await loadFaqs();
    } catch (err) {
      console.error('[FAQ]', err);
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (faqId) => {
    if (!window.confirm('Supprimer cette FAQ ?')) return;
    try {
      await fetch(`${API}/coach/faq/${faqId}`, {
        method: 'DELETE',
        headers: { 'X-User-Email': coachEmail }
      });
      await loadFaqs();
    } catch (err) {
      console.error('[FAQ delete]', err);
    }
  };

  const startEdit = (faq) => {
    setEditingId(faq.id);
    setNewQuestion(faq.question);
    setNewAnswer(faq.answer || '');
  };

  const cancelEdit = () => {
    setEditingId(null);
    setNewQuestion('');
    setNewAnswer('');
  };

  const handleAIAnswer = async () => {
    if (!newQuestion.trim()) return;
    setAiLoading(true);
    try {
      const res = await fetch(`${API}/ai/enhance-text`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: newQuestion, context: 'faq_answer' })
      });
      const data = await res.json();
      if (data.enhanced_text && !data.fallback) {
        setNewAnswer(data.enhanced_text);
      }
    } catch (err) {
      console.error('[AI FAQ]', err);
    } finally {
      setAiLoading(false);
    }
  };

  return (
    <div style={{
      background: 'rgba(139, 92, 246, 0.05)',
      border: '1px solid rgba(139, 92, 246, 0.2)',
      borderRadius: '12px',
      padding: '20px',
      marginTop: '16px'
    }}>
      <h3 style={{ color: '#fff', fontWeight: 600, fontSize: '16px', margin: '0 0 16px 0' }}>
        ❓ FAQ ({faqs.length})
      </h3>

      {/* Liste des FAQs existantes */}
      {faqs.length > 0 && (
        <div style={{ maxHeight: '300px', overflowY: 'auto', marginBottom: '16px' }}>
          {faqs.map((faq) => (
            <div key={faq.id} style={{
              padding: '12px',
              borderRadius: '8px',
              background: 'rgba(0,0,0,0.2)',
              border: '1px solid rgba(139,92,246,0.15)',
              marginBottom: '8px'
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <div style={{ flex: 1 }}>
                  <p style={{ color: '#fff', fontWeight: 600, fontSize: '13px', margin: '0 0 4px 0' }}>
                    {faq.question}
                  </p>
                  {faq.answer && (
                    <p style={{ color: 'rgba(255,255,255,0.6)', fontSize: '12px', margin: 0 }}>
                      {faq.answer}
                    </p>
                  )}
                </div>
                <div style={{ display: 'flex', gap: '6px', marginLeft: '8px', flexShrink: 0 }}>
                  <button
                    onClick={() => startEdit(faq)}
                    style={{
                      padding: '4px 8px', borderRadius: '6px', fontSize: '11px',
                      background: 'rgba(139,92,246,0.2)', border: '1px solid rgba(139,92,246,0.3)',
                      color: '#a78bfa', cursor: 'pointer'
                    }}
                  >
                    ✏️
                  </button>
                  <button
                    onClick={() => handleDelete(faq.id)}
                    style={{
                      padding: '4px 8px', borderRadius: '6px', fontSize: '11px',
                      background: 'rgba(239,68,68,0.2)', border: '1px solid rgba(239,68,68,0.3)',
                      color: '#ef4444', cursor: 'pointer'
                    }}
                  >
                    🗑️
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Formulaire */}
      <form onSubmit={handleSave} style={{
        padding: '12px',
        borderRadius: '8px',
        background: 'rgba(139,92,246,0.08)',
        border: '1px solid rgba(139,92,246,0.25)'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
          <span style={{ color: '#fff', fontSize: '13px', fontWeight: 600 }}>
            {editingId ? '✏️ Modifier' : '➕ Nouvelle FAQ'}
          </span>
          {editingId && (
            <button type="button" onClick={cancelEdit} style={{
              color: '#ef4444', fontSize: '12px', background: 'none', border: 'none', cursor: 'pointer'
            }}>
              ✕ Annuler
            </button>
          )}
        </div>

        <input
          type="text"
          value={newQuestion}
          onChange={(e) => setNewQuestion(e.target.value)}
          placeholder="Question (ex: Quels sont les horaires des cours ?)"
          required
          style={{
            width: '100%', padding: '10px 12px', borderRadius: '8px', marginBottom: '8px',
            background: 'rgba(139, 92, 246, 0.1)', border: '1px solid rgba(139, 92, 246, 0.3)',
            color: '#fff', fontSize: '13px', outline: 'none'
          }}
          data-testid="faq-question-input"
        />

        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
          <textarea
            value={newAnswer}
            onChange={(e) => setNewAnswer(e.target.value)}
            placeholder="Réponse..."
            rows={2}
            style={{
              flex: 1, padding: '10px 12px', borderRadius: '8px',
              background: 'rgba(139, 92, 246, 0.1)', border: '1px solid rgba(139, 92, 246, 0.3)',
              color: '#fff', fontSize: '13px', outline: 'none', resize: 'none'
            }}
            data-testid="faq-answer-input"
          />
          <button
            type="button"
            onClick={handleAIAnswer}
            disabled={aiLoading || !newQuestion.trim()}
            style={{
              padding: '8px 12px', borderRadius: '8px', whiteSpace: 'nowrap',
              background: aiLoading ? 'rgba(139,92,246,0.2)' : 'rgba(217,28,210,0.2)',
              border: '1px solid rgba(217,28,210,0.4)',
              color: '#D91CD2', fontSize: '12px',
              cursor: (aiLoading || !newQuestion.trim()) ? 'not-allowed' : 'pointer',
              opacity: !newQuestion.trim() ? 0.4 : 1
            }}
            data-testid="ai-faq-answer"
          >
            {aiLoading ? '⏳' : '✨ IA'}
          </button>
        </div>

        <button
          type="submit"
          disabled={saving || !newQuestion.trim()}
          style={{
            width: '100%', padding: '10px', borderRadius: '8px',
            background: saving ? 'rgba(139,92,246,0.3)' : 'linear-gradient(135deg, #D91CD2, #8b5cf6)',
            color: '#fff', fontWeight: 600, fontSize: '13px', border: 'none',
            cursor: saving ? 'wait' : 'pointer',
            opacity: !newQuestion.trim() ? 0.5 : 1
          }}
          data-testid="save-faq"
        >
          {saving ? '⏳...' : editingId ? '💾 Enregistrer' : '➕ Ajouter FAQ'}
        </button>
      </form>
    </div>
  );
};

export default FAQManager;
