/**
 * ArticleManager.js
 * Composant séparé pour la gestion CRUD des articles
 * - Respect de la règle anti-casse : pas de modification de CoachDashboard.js
 * - Admin-only : vérifie l'email du coach
 */

import React, { useState, useEffect } from 'react';
import axios from 'axios';

const API = process.env.REACT_APP_BACKEND_URL || '';

const ArticleManager = ({ userEmail, isVisible = true }) => {
  const [articles, setArticles] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [editingArticle, setEditingArticle] = useState(null);
  
  // Formulaire
  const [formData, setFormData] = useState({
    title: '',
    content: '',
    excerpt: '',
    imageUrl: '',
    category: 'general',
    tags: [],
    published: false
  });

  // Charger les articles
  useEffect(() => {
    if (isVisible) {
      loadArticles();
    }
  }, [isVisible]);

  const loadArticles = async () => {
    try {
      setLoading(true);
      const res = await axios.get(`${API}/api/articles`);
      setArticles(res.data || []);
      setError(null);
    } catch (err) {
      console.error('Erreur chargement articles:', err);
      setError('Impossible de charger les articles');
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    
    try {
      setLoading(true);
      
      const payload = {
        ...formData,
        email: userEmail
      };
      
      if (editingArticle) {
        // Mise à jour
        const res = await axios.put(`${API}/api/articles/${editingArticle.id}`, payload);
        setArticles(articles.map(a => a.id === editingArticle.id ? res.data : a));
      } else {
        // Création
        const res = await axios.post(`${API}/api/articles`, payload);
        setArticles([res.data, ...articles]);
      }
      
      resetForm();
      setError(null);
    } catch (err) {
      console.error('Erreur sauvegarde article:', err);
      setError(err.response?.data?.detail || 'Erreur lors de la sauvegarde');
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (articleId) => {
    if (!window.confirm('Supprimer cet article ?')) return;
    
    try {
      setLoading(true);
      await axios.delete(`${API}/api/articles/${articleId}`, {
        data: { email: userEmail }
      });
      setArticles(articles.filter(a => a.id !== articleId));
      setError(null);
    } catch (err) {
      console.error('Erreur suppression article:', err);
      setError(err.response?.data?.detail || 'Erreur lors de la suppression');
    } finally {
      setLoading(false);
    }
  };

  const handleEdit = (article) => {
    setEditingArticle(article);
    setFormData({
      title: article.title || '',
      content: article.content || '',
      excerpt: article.excerpt || '',
      imageUrl: article.imageUrl || '',
      category: article.category || 'general',
      tags: article.tags || [],
      published: article.published || false
    });
    setShowForm(true);
  };

  const resetForm = () => {
    setFormData({
      title: '',
      content: '',
      excerpt: '',
      imageUrl: '',
      category: 'general',
      tags: [],
      published: false
    });
    setEditingArticle(null);
    setShowForm(false);
  };

  if (!isVisible) return null;

  return (
    <div className="p-4 rounded-xl glass border border-purple-500/30" data-testid="article-manager">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-white font-semibold text-lg flex items-center gap-2">
          📰 Gestion des Articles
        </h3>
        <button
          onClick={() => setShowForm(!showForm)}
          className="px-4 py-2 rounded-lg bg-purple-600 hover:bg-purple-500 text-white text-sm font-medium transition-all"
          data-testid="add-article-btn"
        >
          {showForm ? '✕ Fermer' : '+ Nouvel Article'}
        </button>
      </div>

      {/* Message d'erreur */}
      {error && (
        <div className="mb-4 p-3 rounded-lg bg-red-500/20 border border-red-500/50 text-red-400 text-sm">
          ⚠️ {error}
        </div>
      )}

      {/* Formulaire de création/édition */}
      {showForm && (
        <form onSubmit={handleSubmit} className="mb-6 p-4 rounded-lg bg-black/30 border border-purple-500/20">
          <h4 className="text-white font-medium mb-4">
            {editingArticle ? '✏️ Modifier l\'article' : '📝 Nouvel article'}
          </h4>
          
          <div className="grid gap-4">
            {/* Titre */}
            <div>
              <label className="block text-white/70 text-sm mb-1">Titre *</label>
              <input
                type="text"
                value={formData.title}
                onChange={(e) => setFormData({...formData, title: e.target.value})}
                className="w-full px-3 py-2 rounded-lg bg-black/50 border border-purple-500/30 text-white"
                placeholder="Titre de l'article"
                required
                data-testid="article-title-input"
              />
            </div>
            
            {/* Extrait */}
            <div>
              <label className="block text-white/70 text-sm mb-1">Extrait</label>
              <input
                type="text"
                value={formData.excerpt}
                onChange={(e) => setFormData({...formData, excerpt: e.target.value})}
                className="w-full px-3 py-2 rounded-lg bg-black/50 border border-purple-500/30 text-white"
                placeholder="Résumé court de l'article"
                data-testid="article-excerpt-input"
              />
            </div>
            
            {/* Contenu */}
            <div>
              <label className="block text-white/70 text-sm mb-1">Contenu *</label>
              <textarea
                value={formData.content}
                onChange={(e) => setFormData({...formData, content: e.target.value})}
                className="w-full px-3 py-2 rounded-lg bg-black/50 border border-purple-500/30 text-white min-h-[150px]"
                placeholder="Contenu de l'article..."
                required
                data-testid="article-content-input"
              />
            </div>
            
            {/* Image URL */}
            <div>
              <label className="block text-white/70 text-sm mb-1">URL de l'image</label>
              <input
                type="url"
                value={formData.imageUrl}
                onChange={(e) => setFormData({...formData, imageUrl: e.target.value})}
                className="w-full px-3 py-2 rounded-lg bg-black/50 border border-purple-500/30 text-white"
                placeholder="https://..."
                data-testid="article-image-input"
              />
            </div>
            
            {/* Catégorie et Publié */}
            <div className="flex gap-4">
              <div className="flex-1">
                <label className="block text-white/70 text-sm mb-1">Catégorie</label>
                <select
                  value={formData.category}
                  onChange={(e) => setFormData({...formData, category: e.target.value})}
                  className="w-full px-3 py-2 rounded-lg bg-black/50 border border-purple-500/30 text-white"
                  data-testid="article-category-select"
                >
                  <option value="general">Général</option>
                  <option value="fitness">Fitness</option>
                  <option value="nutrition">Nutrition</option>
                  <option value="motivation">Motivation</option>
                  <option value="events">Événements</option>
                </select>
              </div>
              
              <div className="flex items-end">
                <label className="flex items-center gap-2 text-white cursor-pointer">
                  <input
                    type="checkbox"
                    checked={formData.published}
                    onChange={(e) => setFormData({...formData, published: e.target.checked})}
                    className="w-4 h-4 rounded"
                    data-testid="article-published-checkbox"
                  />
                  <span className="text-sm">Publié</span>
                </label>
              </div>
            </div>
          </div>
          
          {/* Boutons */}
          <div className="flex gap-3 mt-4">
            <button
              type="submit"
              disabled={loading}
              className="px-4 py-2 rounded-lg bg-green-600 hover:bg-green-500 text-white text-sm font-medium transition-all disabled:opacity-50"
              data-testid="save-article-btn"
            >
              {loading ? '⏳ Enregistrement...' : (editingArticle ? '💾 Mettre à jour' : '✅ Créer')}
            </button>
            <button
              type="button"
              onClick={resetForm}
              className="px-4 py-2 rounded-lg bg-gray-600 hover:bg-gray-500 text-white text-sm font-medium transition-all"
            >
              Annuler
            </button>
          </div>
        </form>
      )}

      {/* Liste des articles */}
      <div className="space-y-3">
        {loading && !articles.length ? (
          <p className="text-white/50 text-center py-8">Chargement...</p>
        ) : articles.length === 0 ? (
          <p className="text-white/50 text-center py-8">Aucun article pour le moment</p>
        ) : (
          articles.map((article) => (
            <div 
              key={article.id} 
              className="p-4 rounded-lg bg-black/30 border border-purple-500/20 hover:border-purple-500/40 transition-all"
              data-testid={`article-item-${article.id}`}
            >
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <h4 className="text-white font-medium truncate">{article.title}</h4>
                    {article.published ? (
                      <span className="px-2 py-0.5 rounded text-xs bg-green-500/20 text-green-400">Publié</span>
                    ) : (
                      <span className="px-2 py-0.5 rounded text-xs bg-yellow-500/20 text-yellow-400">Brouillon</span>
                    )}
                  </div>
                  <p className="text-white/60 text-sm truncate">{article.excerpt || article.content?.substring(0, 100)}</p>
                  <p className="text-white/40 text-xs mt-1">
                    {article.category} • {new Date(article.createdAt).toLocaleDateString('fr-FR')}
                  </p>
                </div>
                
                <div className="flex gap-2 shrink-0">
                  <button
                    onClick={() => handleEdit(article)}
                    className="px-3 py-1.5 rounded bg-blue-600/30 hover:bg-blue-600/50 text-blue-400 text-sm transition-all"
                    data-testid={`edit-article-${article.id}`}
                  >
                    ✏️
                  </button>
                  <button
                    onClick={() => handleDelete(article.id)}
                    className="px-3 py-1.5 rounded bg-red-600/30 hover:bg-red-600/50 text-red-400 text-sm transition-all"
                    data-testid={`delete-article-${article.id}`}
                  >
                    🗑️
                  </button>
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
};

export default ArticleManager;
