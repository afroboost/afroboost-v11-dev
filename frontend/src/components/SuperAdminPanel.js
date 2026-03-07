/**
 * SuperAdminPanel - Panneau de contrôle Super Admin v8.9
 * Permet de gérer les packs coach, les tarifs et les coachs partenaires
 */
import { useState, useEffect } from "react";
import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';
const API = `${BACKEND_URL}/api`;

// Icônes SVG
const CrownIcon = () => (
  <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.5}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M12 2L9 9l-7 2 5 5-1 7 6-3 6 3-1-7 5-5-7-2-3-7z" />
  </svg>
);

const PlusIcon = () => (
  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
  </svg>
);

const EditIcon = () => (
  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
  </svg>
);

const TrashIcon = () => (
  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
  </svg>
);

const SuperAdminPanel = ({ userEmail, onClose }) => {
  const [activeTab, setActiveTab] = useState('packs');
  const [packs, setPacks] = useState([]);
  const [coaches, setCoaches] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editingPack, setEditingPack] = useState(null);
  const [showPackForm, setShowPackForm] = useState(false);
  const [error, setError] = useState(null);
  
  // v12.1: État pour les prix des services
  const [servicePrices, setServicePrices] = useState({
    campaign: 1,
    ai_conversation: 1,
    promo_code: 1
  });
  const [savingPrices, setSavingPrices] = useState(false);
  
  const [aiPackLoading, setAiPackLoading] = useState(false);

  const handleAIPackEnhance = async () => {
    const text = packForm.description;
    if (!text || text.trim().length < 3) return;
    setAiPackLoading(true);
    try {
      const res = await fetch(`${API}/ai/enhance-text`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, context: 'pack' })
      });
      const data = await res.json();
      if (data.enhanced_text && !data.fallback) {
        setPackForm(prev => ({ ...prev, description: data.enhanced_text }));
      }
    } catch (err) {
      console.error('[AI Pack]', err);
    } finally {
      setAiPackLoading(false);
    }
  };

  const [packForm, setPackForm] = useState({
    name: '',
    price: '',
    credits: '',
    description: '',
    features: ''
  });

  // Charger les données
  useEffect(() => {
    const fetchData = async () => {
      try {
        const [packsRes, coachesRes, settingsRes] = await Promise.all([
          axios.get(`${API}/admin/coach-packs/all`, { headers: { 'X-User-Email': userEmail } }),
          axios.get(`${API}/admin/coaches`, { headers: { 'X-User-Email': userEmail } }),
          axios.get(`${API}/platform-settings`, { headers: { 'X-User-Email': userEmail } })
        ]);
        setPacks(packsRes.data || []);
        setCoaches(coachesRes.data || []);
        // v12.1: Charger les prix des services
        if (settingsRes.data?.service_prices) {
          setServicePrices(settingsRes.data.service_prices);
        }
      } catch (err) {
        console.error('[ADMIN] Erreur:', err);
        setError(err.response?.data?.detail || 'Erreur de chargement');
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [userEmail]);

  // v12.1: Sauvegarder les prix des services
  const handleSaveServicePrices = async () => {
    setSavingPrices(true);
    try {
      await axios.put(`${API}/platform-settings`, {
        service_prices: servicePrices
      }, { headers: { 'X-User-Email': userEmail } });
      setError(null);
    } catch (err) {
      setError(err.response?.data?.detail || 'Erreur lors de la sauvegarde des prix');
    } finally {
      setSavingPrices(false);
    }
  };

  // Créer/Modifier un pack
  const handleSavePack = async () => {
    try {
      const data = {
        name: packForm.name,
        price: parseFloat(packForm.price) || 0,
        credits: parseInt(packForm.credits) || 0,
        description: packForm.description,
        features: packForm.features.split('\n').filter(f => f.trim()),
        visible: true
      };

      if (editingPack) {
        await axios.put(`${API}/admin/coach-packs/${editingPack.id}`, data, {
          headers: { 'X-User-Email': userEmail }
        });
      } else {
        await axios.post(`${API}/admin/coach-packs`, data, {
          headers: { 'X-User-Email': userEmail }
        });
      }

      // Recharger les packs
      const res = await axios.get(`${API}/admin/coach-packs/all`, { headers: { 'X-User-Email': userEmail } });
      setPacks(res.data || []);
      
      setShowPackForm(false);
      setEditingPack(null);
      setPackForm({ name: '', price: '', credits: '', description: '', features: '' });
    } catch (err) {
      setError(err.response?.data?.detail || 'Erreur lors de la sauvegarde');
    }
  };

  // Supprimer un pack
  const handleDeletePack = async (packId) => {
    if (!window.confirm('Supprimer ce pack ?')) return;
    try {
      await axios.delete(`${API}/admin/coach-packs/${packId}`, {
        headers: { 'X-User-Email': userEmail }
      });
      setPacks(prev => prev.filter(p => p.id !== packId));
    } catch (err) {
      setError(err.response?.data?.detail || 'Erreur lors de la suppression');
    }
  };

  // Éditer un pack
  const startEditPack = (pack) => {
    setEditingPack(pack);
    setPackForm({
      name: pack.name || '',
      price: pack.price?.toString() || '',
      credits: pack.credits?.toString() || '',
      description: pack.description || '',
      features: (pack.features || []).join('\n')
    });
    setShowPackForm(true);
  };

  // Ajouter des crédits à un coach
  const handleAddCredits = async (coachEmail, credits) => {
    try {
      await axios.post(`${API}/coach/add-credits`, {
        coach_email: coachEmail,
        credits: credits
      }, { headers: { 'X-User-Email': userEmail } });
      
      // Recharger les coachs
      const res = await axios.get(`${API}/admin/coaches`, { headers: { 'X-User-Email': userEmail } });
      setCoaches(res.data || []);
    } catch (err) {
      setError(err.response?.data?.detail || 'Erreur lors de l\'ajout des crédits');
    }
  };

  // v9.0.1: Toggle statut coach (actif/inactif)
  const handleToggleCoach = async (coachId, isCurrentlyActive) => {
    try {
      await axios.post(`${API}/admin/coaches/${coachId}/toggle`, {}, { headers: { 'X-User-Email': userEmail } });
      const res = await axios.get(`${API}/admin/coaches`, { headers: { 'X-User-Email': userEmail } });
      setCoaches(res.data || []);
    } catch (err) {
      setError(err.response?.data?.detail || 'Erreur lors du changement de statut');
    }
  };

  // v9.0.1: Supprimer un coach
  const handleDeleteCoach = async (coachId, coachName) => {
    if (!window.confirm(`Supprimer définitivement le coach "${coachName}" ?\n\nCette action est irréversible.`)) return;
    try {
      await axios.delete(`${API}/admin/coaches/${coachId}`, { headers: { 'X-User-Email': userEmail } });
      const res = await axios.get(`${API}/admin/coaches`, { headers: { 'X-User-Email': userEmail } });
      setCoaches(res.data || []);
    } catch (err) {
      setError(err.response?.data?.detail || 'Erreur lors de la suppression');
    }
  };

  if (loading) {
    return (
      <div className="fixed inset-0 bg-black/95 z-50 flex items-center justify-center">
        <div className="text-white">Chargement...</div>
      </div>
    );
  }

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto" style={{ background: '#000000' }}>
      <div className="min-h-screen py-6 px-4">
        <div className="max-w-6xl mx-auto">
          {/* Header - v12.1: Design Premium Sans Cadre */}
          <div className="flex justify-between items-center mb-8">
            <div className="flex items-center gap-3">
              <span style={{ color: '#D91CD2' }}><CrownIcon /></span>
              <h1 className="text-2xl font-bold text-white">Panneau Super Admin</h1>
            </div>
            <button 
              onClick={onClose}
              className="text-white/40 hover:text-white text-2xl transition-colors"
              data-testid="close-admin-panel"
            >
              ✕
            </button>
          </div>

          {/* Tabs - v12.1: Ajout onglet Tarifs */}
          <div className="flex gap-2 mb-6 border-b border-white/10 pb-2">
            <button
              onClick={() => setActiveTab('packs')}
              className={`px-4 py-2 text-sm font-medium transition-all ${
                activeTab === 'packs' 
                  ? 'text-white' 
                  : 'text-white/40 hover:text-white/70'
              }`}
              style={activeTab === 'packs' ? { color: '#D91CD2' } : {}}
              data-testid="tab-packs"
            >
              Packs Coach ({packs.length})
            </button>
            <button
              onClick={() => setActiveTab('coaches')}
              className={`px-4 py-2 text-sm font-medium transition-all ${
                activeTab === 'coaches' 
                  ? 'text-white' 
                  : 'text-white/40 hover:text-white/70'
              }`}
              style={activeTab === 'coaches' ? { color: '#D91CD2' } : {}}
              data-testid="tab-coaches"
            >
              Coachs Partenaires ({coaches.length})
            </button>
            <button
              onClick={() => setActiveTab('pricing')}
              className={`px-4 py-2 text-sm font-medium transition-all ${
                activeTab === 'pricing' 
                  ? 'text-white' 
                  : 'text-white/40 hover:text-white/70'
              }`}
              style={activeTab === 'pricing' ? { color: '#D91CD2' } : {}}
              data-testid="tab-pricing"
            >
              💎 Tarifs Services
            </button>
          </div>

          {/* Erreur - v12.1: Design Sans Cadre */}
          {error && (
            <div className="mb-4 py-3 text-red-400 text-sm flex items-center gap-2">
              <span>⚠️</span> {error}
              <button onClick={() => setError(null)} className="ml-2 text-red-400/60 hover:text-red-400">✕</button>
            </div>
          )}

          {/* Tab Packs - v12.1: Design Premium Sans Cadre */}
          {activeTab === 'packs' && (
            <div className="space-y-6">
              {/* Bouton Créer */}
              <button
                onClick={() => {
                  setEditingPack(null);
                  setPackForm({ name: '', price: '', credits: '', description: '', features: '' });
                  setShowPackForm(true);
                }}
                className="flex items-center gap-2 px-6 py-3 text-white font-medium transition-all hover:opacity-80"
                style={{ background: 'linear-gradient(135deg, #D91CD2, #8b5cf6)', borderRadius: '8px' }}
                data-testid="create-pack-btn"
              >
                <PlusIcon />
                Créer un Pack
              </button>

              {/* Formulaire Pack - v12.1: Design Sans Cadre */}
              {showPackForm && (
                <div className="py-6" style={{ borderTop: '1px solid rgba(217, 28, 210, 0.3)', borderBottom: '1px solid rgba(217, 28, 210, 0.3)' }}>
                  <h3 className="text-lg font-semibold text-white mb-6">
                    {editingPack ? 'Modifier le Pack' : 'Nouveau Pack'}
                  </h3>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
                    <div>
                      <label className="text-white/50 text-sm mb-2 block">Nom *</label>
                      <input
                        type="text"
                        value={packForm.name}
                        onChange={(e) => setPackForm(prev => ({ ...prev, name: e.target.value }))}
                        className="w-full px-4 py-3 text-white"
                        style={{ background: 'transparent', border: 'none', borderBottom: '1px solid rgba(255,255,255,0.2)' }}
                        data-testid="pack-name-input"
                      />
                    </div>
                    <div>
                      <label className="text-white/50 text-sm mb-2 block">Prix (CHF) *</label>
                      <input
                        type="number"
                        value={packForm.price}
                        onChange={(e) => setPackForm(prev => ({ ...prev, price: e.target.value }))}
                        className="w-full px-4 py-3 text-white"
                        style={{ background: 'transparent', border: 'none', borderBottom: '1px solid rgba(255,255,255,0.2)' }}
                        data-testid="pack-price-input"
                      />
                    </div>
                    <div>
                      <label className="text-white/50 text-sm mb-2 block">Crédits inclus *</label>
                      <input
                        type="number"
                        value={packForm.credits}
                        onChange={(e) => setPackForm(prev => ({ ...prev, credits: e.target.value }))}
                        className="w-full px-4 py-3 text-white"
                        style={{ background: 'transparent', border: 'none', borderBottom: '1px solid rgba(255,255,255,0.2)' }}
                        data-testid="pack-credits-input"
                      />
                    </div>
                    <div>
                      <div className="flex items-center justify-between mb-2">
                        <label className="text-white/50 text-sm">Description</label>
                        <button
                          type="button"
                          onClick={handleAIPackEnhance}
                          disabled={aiPackLoading || !(packForm.description?.trim())}
                          className="text-xs px-2 py-1 rounded-lg"
                          style={{
                            background: aiPackLoading ? 'rgba(139,92,246,0.2)' : 'rgba(217,28,210,0.2)',
                            border: '1px solid rgba(217,28,210,0.4)',
                            color: '#D91CD2',
                            cursor: aiPackLoading ? 'wait' : 'pointer',
                            opacity: !(packForm.description?.trim()) ? 0.4 : 1
                          }}
                          data-testid="ai-enhance-pack"
                        >
                          {aiPackLoading ? '⏳ IA...' : '✨ Aide IA'}
                        </button>
                      </div>
                      <input
                        type="text"
                        value={packForm.description}
                        onChange={(e) => setPackForm(prev => ({ ...prev, description: e.target.value }))}
                        className="w-full px-4 py-3 text-white"
                        style={{ background: 'transparent', border: 'none', borderBottom: '1px solid rgba(255,255,255,0.2)' }}
                        data-testid="pack-description-input"
                      />
                    </div>
                    <div className="sm:col-span-2">
                      <label className="text-white/50 text-sm mb-2 block">Fonctionnalités (une par ligne)</label>
                      <textarea
                        value={packForm.features}
                        onChange={(e) => setPackForm(prev => ({ ...prev, features: e.target.value }))}
                        rows={3}
                        placeholder="CRM automatisé&#10;Chat IA intégré&#10;Page de vente"
                        className="w-full px-4 py-3 text-white resize-none"
                        style={{ background: 'transparent', border: 'none', borderBottom: '1px solid rgba(255,255,255,0.2)' }}
                        data-testid="pack-features-input"
                      />
                    </div>
                  </div>
                  <div className="flex justify-end gap-4 mt-6">
                    <button
                      onClick={() => { setShowPackForm(false); setEditingPack(null); }}
                      className="px-4 py-2 text-white/50 hover:text-white"
                    >
                      Annuler
                    </button>
                    <button
                      onClick={handleSavePack}
                      disabled={!packForm.name || !packForm.price || !packForm.credits}
                      className="px-6 py-2 text-white font-medium transition-all hover:opacity-80 disabled:opacity-30"
                      style={{ background: 'linear-gradient(135deg, #D91CD2, #8b5cf6)', borderRadius: '8px' }}
                      data-testid="save-pack-btn"
                    >
                      {editingPack ? 'Modifier' : 'Créer'}
                    </button>
                  </div>
                </div>
              )}

              {/* Liste des Packs - v12.1: Design Sans Cadre */}
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
                {packs.map(pack => (
                  <div 
                    key={pack.id}
                    className="py-5"
                    style={{ borderBottom: '1px solid rgba(255,255,255,0.1)' }}
                    data-testid={`pack-card-${pack.id}`}
                  >
                    <div className="flex justify-between items-start mb-2">
                      <h3 className="text-lg font-bold text-white">{pack.name}</h3>
                      <div className="flex gap-2">
                        <button
                          onClick={() => startEditPack(pack)}
                          className="text-white/40 hover:text-white transition-colors"
                          data-testid={`edit-pack-${pack.id}`}
                        >
                          <EditIcon />
                        </button>
                        <button
                          onClick={() => handleDeletePack(pack.id)}
                          className="text-red-400/60 hover:text-red-400 transition-colors"
                          data-testid={`delete-pack-${pack.id}`}
                        >
                          <TrashIcon />
                        </button>
                      </div>
                    </div>
                    <div className="text-2xl font-bold mb-1" style={{ color: '#D91CD2' }}>
                      {pack.price} CHF
                    </div>
                    <div className="text-white/50 text-sm mb-2">{pack.credits} crédits</div>
                    {pack.description && <p className="text-white/30 text-xs mb-2">{pack.description}</p>}
                    <div className="flex items-center gap-2 text-xs text-white/30">
                      {pack.stripe_price_id ? (
                        <span className="text-green-400">✓ Stripe</span>
                      ) : (
                        <span className="text-yellow-400">Sans Stripe</span>
                      )}
                      {!pack.visible && <span className="text-red-400">● Masqué</span>}
                    </div>
                  </div>
                ))}

                {packs.length === 0 && (
                  <div className="col-span-full text-center py-8 text-white/40">
                    Aucun pack créé. Créez votre premier pack coach !
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Tab Coaches */}
          {activeTab === 'coaches' && (
            <div className="space-y-4">
              {coaches.length === 0 ? (
                <div className="text-center py-8 text-white/60">
                  Aucun coach partenaire enregistré
                </div>
              ) : (
                <div className="overflow-hidden" style={{ background: 'transparent' }}>
                  <table className="w-full">
                    <thead>
                      <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.1)' }}>
                        <th className="px-4 py-3 text-left text-xs font-medium text-white/50">Coach</th>
                        <th className="px-4 py-3 text-left text-xs font-medium text-white/50">Email</th>
                        <th className="px-4 py-3 text-center text-xs font-medium text-white/50">Crédits</th>
                        <th className="px-4 py-3 text-center text-xs font-medium text-white/50">Stripe</th>
                        <th className="px-4 py-3 text-center text-xs font-medium text-white/50">Statut</th>
                        <th className="px-4 py-3 text-center text-xs font-medium text-white/50">Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {coaches.map(coach => (
                        <tr key={coach.id} style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }} data-testid={`coach-row-${coach.id}`}>
                          <td className="px-4 py-3 text-sm text-white">{coach.name}</td>
                          <td className="px-4 py-3 text-sm text-white/60">{coach.email}</td>
                          <td className="px-4 py-3 text-center">
                            <span className={`text-sm font-bold ${
                              coach.credits > 10 ? 'text-green-400' :
                              coach.credits > 0 ? 'text-yellow-400' :
                              'text-red-400'
                            }`}>
                              {coach.credits}
                            </span>
                          </td>
                          <td className="px-4 py-3 text-center">
                            <span className={`text-xs ${
                              coach.stripe_connect_id ? 'text-green-400' : 'text-white/30'
                            }`}>
                              {coach.stripe_connect_id ? '✓' : '—'}
                            </span>
                          </td>
                          <td className="px-4 py-3 text-center">
                            <span className={`text-xs ${
                              coach.is_active ? 'text-green-400' : 'text-red-400'
                            }`}>
                              {coach.is_active ? '● Actif' : '○ Inactif'}
                            </span>
                          </td>
                          <td className="px-4 py-3 text-center">
                            <div className="flex gap-2 justify-center">
                              <button
                                onClick={() => {
                                  const credits = prompt('Combien de crédits ajouter ?', '10');
                                  if (credits && parseInt(credits) > 0) {
                                    handleAddCredits(coach.email, parseInt(credits));
                                  }
                                }}
                                className="text-xs text-purple-400 hover:text-purple-300"
                                data-testid={`add-credits-${coach.id}`}
                              >
                                + Crédits
                              </button>
                              <button
                                onClick={() => handleToggleCoach(coach.id, coach.is_active)}
                                className={`text-xs ${coach.is_active ? 'text-yellow-400 hover:text-yellow-300' : 'text-green-400 hover:text-green-300'}`}
                                data-testid={`toggle-coach-${coach.id}`}
                              >
                                {coach.is_active ? '⏸' : '▶'}
                              </button>
                              <button
                                onClick={() => handleDeleteCoach(coach.id, coach.name)}
                                className="text-xs text-red-400 hover:text-red-300"
                                data-testid={`delete-coach-${coach.id}`}
                              >
                                🗑
                              </button>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}

          {/* v12.1: Tab Tarifs Services - Design Premium Sans Cadre */}
          {activeTab === 'pricing' && (
            <div className="space-y-6">
              <div className="text-white/50 text-sm mb-4">
                Définissez le coût en crédits de chaque service pour les partenaires
              </div>
              
              {/* Service: Campagne */}
              <div className="flex items-center justify-between py-4" style={{ borderBottom: '1px solid rgba(255,255,255,0.1)' }}>
                <div className="flex items-center gap-4">
                  <span className="text-2xl">📧</span>
                  <div>
                    <div className="text-white font-medium">Campagne Email/WhatsApp</div>
                    <div className="text-white/40 text-sm">Envoi de messages en masse</div>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <input
                    type="number"
                    min="0"
                    value={servicePrices.campaign}
                    onChange={(e) => setServicePrices(prev => ({ ...prev, campaign: parseInt(e.target.value) || 0 }))}
                    className="w-20 px-3 py-2 text-center text-white text-lg font-bold"
                    style={{ background: 'transparent', border: 'none', borderBottom: '2px solid #D91CD2' }}
                    data-testid="price-campaign"
                  />
                  <span className="text-white/40 text-sm">crédits</span>
                </div>
              </div>

              {/* Service: Conversation IA */}
              <div className="flex items-center justify-between py-4" style={{ borderBottom: '1px solid rgba(255,255,255,0.1)' }}>
                <div className="flex items-center gap-4">
                  <span className="text-2xl">🤖</span>
                  <div>
                    <div className="text-white font-medium">Conversation IA</div>
                    <div className="text-white/40 text-sm">Session de chat avec l'assistant</div>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <input
                    type="number"
                    min="0"
                    value={servicePrices.ai_conversation}
                    onChange={(e) => setServicePrices(prev => ({ ...prev, ai_conversation: parseInt(e.target.value) || 0 }))}
                    className="w-20 px-3 py-2 text-center text-white text-lg font-bold"
                    style={{ background: 'transparent', border: 'none', borderBottom: '2px solid #D91CD2' }}
                    data-testid="price-ai-conversation"
                  />
                  <span className="text-white/40 text-sm">crédits</span>
                </div>
              </div>

              {/* Service: Code Promo */}
              <div className="flex items-center justify-between py-4" style={{ borderBottom: '1px solid rgba(255,255,255,0.1)' }}>
                <div className="flex items-center gap-4">
                  <span className="text-2xl">🎫</span>
                  <div>
                    <div className="text-white font-medium">Génération Code Promo</div>
                    <div className="text-white/40 text-sm">Création d'un code de réduction</div>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <input
                    type="number"
                    min="0"
                    value={servicePrices.promo_code}
                    onChange={(e) => setServicePrices(prev => ({ ...prev, promo_code: parseInt(e.target.value) || 0 }))}
                    className="w-20 px-3 py-2 text-center text-white text-lg font-bold"
                    style={{ background: 'transparent', border: 'none', borderBottom: '2px solid #D91CD2' }}
                    data-testid="price-promo-code"
                  />
                  <span className="text-white/40 text-sm">crédits</span>
                </div>
              </div>

              {/* Bouton Sauvegarder */}
              <div className="pt-4">
                <button
                  onClick={handleSaveServicePrices}
                  disabled={savingPrices}
                  className="px-8 py-3 text-white font-medium transition-all hover:opacity-80 disabled:opacity-50"
                  style={{ 
                    background: 'linear-gradient(135deg, #D91CD2, #8b5cf6)',
                    borderRadius: '8px'
                  }}
                  data-testid="save-prices-btn"
                >
                  {savingPrices ? 'Sauvegarde...' : '💾 Sauvegarder les tarifs'}
                </button>
              </div>

              {/* Note */}
              <div className="text-white/30 text-xs pt-4">
                💡 Le Super Admin ne consomme jamais de crédits. Ces tarifs s'appliquent uniquement aux coachs partenaires.
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default SuperAdminPanel;
