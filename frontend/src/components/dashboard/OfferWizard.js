// V224 — Wizard de creation/modification d'offre en 3 etapes.
// Le state est LOCAL : il ne remonte au parent qu'une fois, via onSave,
// ce qui preserve le comportement actuel d'une seule requete POST/PUT.
import React, { useState, useEffect } from 'react';

const STEPS = [
  { n: 1, label: 'Bases' },
  { n: 2, label: 'Logistique' },
  { n: 3, label: 'Medias' }
];

const PINK = '#D91CD2';
const ACCENT_BORDER = 'rgba(217,28,210,0.2)';

// V224: style commun a tous les inputs du wizard (palette v224-constraints).
const INPUT_STYLE = {
  background: '#0a0a0f',
  border: '1px solid #333',
  borderRadius: '8px',
  color: '#fff',
  padding: '10px',
  width: '100%'
};

const LABEL_STYLE = { color: 'rgba(255,255,255,0.7)' };
const HINT_STYLE = { color: 'rgba(255,255,255,0.4)' };

const WEEKDAYS = ['Dimanche', 'Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi'];

// V224: cles des variantes produit, dans l'ordre d'affichage.
const VARIANT_FIELDS = [
  { key: 'sizes', placeholder: 'S, M, L, XL' },
  { key: 'colors', placeholder: 'Noir, Blanc' },
  { key: 'weights', placeholder: '0.5kg, 1kg' }
];

// V224: normalisation d'URL video pour la previsualisation.
// Logique alignee sur MediaViewer.js (extractYouTubeId / getVideoType) sans
// importer le module : YouTube (watch?v=, youtu.be, embed/), Vimeo, sinon brut.
const extractYouTubeId = (url) => {
  const watchMatch = url.match(/[?&]v=([a-zA-Z0-9_-]{11})/);
  if (watchMatch) return watchMatch[1];
  const shortMatch = url.match(/youtu\.be\/([a-zA-Z0-9_-]{11})/);
  if (shortMatch) return shortMatch[1];
  const embedMatch = url.match(/embed\/([a-zA-Z0-9_-]{11})/);
  if (embedMatch) return embedMatch[1];
  return null;
};

const toEmbedUrl = (url) => {
  if (!url) return '';
  const lower = url.toLowerCase();
  if (lower.includes('youtube.com') || lower.includes('youtu.be')) {
    const id = extractYouTubeId(url);
    return id ? `https://www.youtube.com/embed/${id}?modestbranding=1&rel=0` : url;
  }
  if (lower.includes('vimeo.com')) {
    // player.vimeo.com/video/ID est deja une URL d'embed valide.
    if (lower.includes('player.vimeo.com')) return url;
    const vimeoMatch = url.match(/vimeo\.com\/(?:video\/)?(\d+)/);
    return vimeoMatch ? `https://player.vimeo.com/video/${vimeoMatch[1]}` : url;
  }
  return url;
};

// V224: paliers de prix progressif — repris a l'identique de OffersManager.js (V223).
// V225: chaque palier porte aussi une cle de libelle (`labelKey`) et un
// placeholder, pour rendre le nom du palier editable sans dupliquer le bloc
// de rendu en trois copies quasi identiques.
const PROGRESSIVE_TIERS = [
  { key: 'price_early_bird', label: '✨ Early Bird (plus de 7 jours avant)', labelKey: 'label_early_bird', placeholder: 'Prévente' },
  { key: 'price_standard', label: '⏱ Standard (plus de 24h avant)', labelKey: 'label_standard', placeholder: 'Standard' },
  { key: 'price_last_minute', label: '⚡ Last Minute (moins de 24h)', labelKey: 'label_last_minute', placeholder: 'Dernière min.' }
];

export default function OfferWizard({
  open,
  initialOffer,
  courses,
  isEditing,
  onSave,
  onCancel,
  // V224: props optionnelles. Absentes, le filtre par coach est neutre et
  // tous les cours fournis par le parent restent affiches (le parent ne
  // transmet deja que les cours pertinents).
  isSuperAdmin,
  coachEmail,
  // V224: prop OPTIONNELLE. Si fournie, un bouton « Aide IA » apparait a cote
  // du champ description (parite avec OffersManager.js). Absente, pas de bouton.
  onEnhanceDescription
}) {
  const [step, setStep] = useState(1);
  const [form, setForm] = useState(initialOffer || {});
  // V224: chaine BRUTE saisie dans les champs variantes. Indispensable : sans
  // elle, la valeur affichee est derivee du tableau normalise, ce qui efface la
  // virgule a l'instant ou elle est tapee (« S, M » devenait « SM »).
  const [variantsRaw, setVariantsRaw] = useState({});
  const [aiLoading, setAiLoading] = useState(false);

  useEffect(() => {
    if (open) {
      const offer = initialOffer || {};
      setForm(offer);
      // V224: pre-remplissage des chaines brutes depuis les tableaux existants.
      const raw = {};
      VARIANT_FIELDS.forEach(({ key }) => {
        const arr = offer.variants?.[key];
        if (Array.isArray(arr) && arr.length) raw[key] = arr.join(', ');
      });
      setVariantsRaw(raw);
      setStep(1);
    }
  }, [open, initialOffer]);

  if (!open) return null;

  const set = (key, value) => setForm(prev => ({ ...prev, [key]: value }));

  // V224: on ecrit la chaine brute (pour l'affichage) ET le tableau splitte
  // (pour la sauvegarde) en une seule frappe.
  const setVariant = (key, raw) => {
    setVariantsRaw(prev => ({ ...prev, [key]: raw }));
    set('variants', {
      ...(form.variants || {}),
      [key]: raw.split(',').map(s => s.trim()).filter(Boolean)
    });
  };

  // V224: amelioration IA de la description, deleguee au parent.
  const handleEnhanceDescription = async () => {
    if (!onEnhanceDescription || aiLoading) return;
    const current = (form.description || '').trim();
    if (!current) return;
    setAiLoading(true);
    try {
      const improved = await onEnhanceDescription(current);
      if (improved && typeof improved === 'string') set('description', improved);
    } catch (err) {
      console.error('[V224] Aide IA description echouee:', err);
    } finally {
      setAiLoading(false);
    }
  };

  const handleSave = () => {
    // Seule contrainte bloquante : le nom. Le backend le type `name: str`
    // (non optionnel) et rejetterait la requete.
    if (!form.name || !form.name.trim()) {
      setStep(1);
      alert('Le nom de l\'offre est obligatoire');
      return;
    }
    onSave(form);
  };

  // V224: filtre par coach repris de OffersManager.js l.798-799.
  const visibleCourses = (courses || []).filter(c => {
    if (c.archived) return false;
    if (isSuperAdmin) return true;
    if (!coachEmail) return true;
    return (c.coach_id || '').toLowerCase() === (coachEmail || '').toLowerCase();
  });

  const linkedIds = form.linked_course_ids || [];

  const renderStep1 = () => (
    <div className="space-y-4">
      {/* Nom */}
      <div>
        <label className="block text-xs mb-1" style={LABEL_STYLE}>Nom de l'offre *</label>
        <input
          type="text"
          value={form.name || ''}
          onChange={(e) => set('name', e.target.value)}
          placeholder="Ex: Cours à l'unité"
          style={INPUT_STYLE}
          className="text-sm v224-input"
        />
      </div>

      {/* Prix */}
      <div>
        <label className="block text-xs mb-1" style={LABEL_STYLE}>Prix (CHF)</label>
        <input
          type="number"
          value={form.price ?? ''}
          onChange={(e) => set('price', e.target.value === '' ? 0 : parseFloat(e.target.value) || 0)}
          placeholder="30"
          style={INPUT_STYLE}
          className="text-sm v224-input"
        />
      </div>

      {/* V223 repris : prix progressif 3 paliers */}
      <div className="p-4 rounded-lg" style={{ background: '#000', border: `1px solid ${ACCENT_BORDER}` }}>
        <label className="flex items-center gap-3 cursor-pointer">
          <input
            type="checkbox"
            checked={!!form.progressive_pricing}
            onChange={(e) => set('progressive_pricing', e.target.checked)}
            className="accent-[#D91CD2] w-4 h-4 v224-input"
          />
          <span className="text-white text-sm font-medium">📊 Activer les 3 paliers de prix</span>
        </label>
        <p className="text-xs mt-1 ml-7" style={{ color: 'rgba(255,255,255,0.5)' }}>
          Récompense les réservations en avance et capture les réservations de dernière minute.
        </p>

        {form.progressive_pricing && (
          <div className="mt-4 space-y-3">
            {!form.countdown_date && (
              <p className="text-xs p-2 rounded" style={{ background: 'rgba(217,28,210,0.1)', color: PINK }}>
                ⚠️ Activez le compte à rebours (étape 2 « Logistique ») : sans date de
                référence, les paliers ne s'appliquent pas et le prix normal reste affiché.
              </p>
            )}
            {PROGRESSIVE_TIERS.map(f => (
              <div key={f.key}>
                <label className="block text-xs mb-1" style={LABEL_STYLE}>{f.label}</label>
                <input
                  type="number"
                  value={form[f.key] ?? ''}
                  onChange={(e) => set(f.key, e.target.value === '' ? null : parseFloat(e.target.value))}
                  placeholder="CHF"
                  style={INPUT_STYLE}
                  className="text-sm v224-input"
                />
                {/* V225: libelle du palier, editable — affiche sur la carte publique
                    a la place du nom fige (Early Bird / Standard / Last Minute). */}
                <input
                  type="text"
                  value={form[f.labelKey] || ''}
                  onChange={(e) => set(f.labelKey, e.target.value)}
                  placeholder={f.placeholder}
                  maxLength={40}
                  style={INPUT_STYLE}
                  className="text-sm v224-input mt-1"
                />
              </div>
            ))}
            <button
              type="button"
              onClick={() => {
                const base = parseFloat(form.price) || 0;
                setForm(prev => ({
                  ...prev,
                  price_early_bird: base,
                  price_standard: Math.round(base * 1.33),
                  price_last_minute: base * 2
                }));
              }}
              className="text-xs underline"
              style={{ color: PINK }}
            >
              Réinitialiser aux valeurs suggérées
            </button>
          </div>
        )}

        <div className="mt-4">
          <label className="block text-xs mb-1" style={LABEL_STYLE}>
            Nombre de séances incluses (pack)
          </label>
          <input
            type="number"
            value={form.pack_sessions ?? ''}
            onChange={(e) => set('pack_sessions', e.target.value === '' ? null : parseInt(e.target.value, 10))}
            placeholder="ex: 10"
            style={INPUT_STYLE}
            className="text-sm v224-input"
          />
          <p className="text-xs mt-1" style={{ color: 'rgba(255,255,255,0.5)' }}>
            Si rempli, l'acheteur reçoit un espace personnel avec ce nombre de crédits.
          </p>
        </div>
      </div>

      {/* Description */}
      <div>
        <div className="flex items-center justify-between mb-1">
          <label className="text-xs" style={LABEL_STYLE}>Description</label>
          {/* V224: parite avec le bouton « Aide IA » de OffersManager.js */}
          {onEnhanceDescription && (
            <button
              type="button"
              onClick={handleEnhanceDescription}
              disabled={aiLoading || !(form.description || '').trim()}
              className="text-xs px-2 py-1 rounded-lg"
              style={{
                background: aiLoading ? 'rgba(139,92,246,0.2)' : 'rgba(217,28,210,0.2)',
                border: '1px solid rgba(217,28,210,0.4)',
                color: PINK,
                cursor: aiLoading ? 'wait' : 'pointer',
                opacity: !(form.description || '').trim() ? 0.4 : 1
              }}
              data-testid="ai-enhance-description"
            >
              {aiLoading ? '⏳ IA...' : '✨ Aide IA'}
            </button>
          )}
        </div>
        <textarea
          value={form.description || ''}
          onChange={(e) => set('description', e.target.value)}
          rows={5}
          maxLength={3000}
          placeholder="Description détaillée de votre offre (jusqu'à 3000 caractères)"
          style={INPUT_STYLE}
          className="text-sm v224-input"
        />
        <p className="text-xs mt-1" style={HINT_STYLE}>{(form.description || '').length}/3000</p>
      </div>

      {/* Mots-clés */}
      <div>
        <label className="block text-xs mb-1" style={LABEL_STYLE}>🔍 Mots-clés (pour la recherche)</label>
        <input
          type="text"
          value={form.keywords || ''}
          onChange={(e) => set('keywords', e.target.value)}
          placeholder="session, séance, cardio, danse, afro... (séparés par virgules)"
          style={INPUT_STYLE}
          className="text-sm v224-input"
        />
        <p className="text-xs mt-1" style={HINT_STYLE}>💡 Aide les clients à trouver cette offre</p>
      </div>
    </div>
  );

  const renderStep2 = () => (
    <div className="space-y-4">
      {/* V159 repris : compte a rebours */}
      <div className="p-4 rounded-lg" style={{ border: '2px solid #f59e0b', background: 'rgba(245,158,11,0.08)' }}>
        <label className="flex items-center gap-3 cursor-pointer">
          <input
            type="checkbox"
            checked={!!form.countdown_enabled}
            onChange={(e) => set('countdown_enabled', e.target.checked)}
            className="w-4 h-4 v224-input"
            style={{ accentColor: '#f59e0b' }}
            data-testid="countdown-toggle"
          />
          <span className="text-sm font-bold" style={{ color: '#f59e0b' }}>⏳ COMPTE À REBOURS</span>
        </label>

        {form.countdown_enabled ? (
          <div className="mt-3 space-y-3">
            <div>
              <label className="block text-xs mb-1" style={LABEL_STYLE}>Texte affiché</label>
              <input
                type="text"
                value={form.countdown_text || ''}
                onChange={(e) => set('countdown_text', e.target.value)}
                placeholder="L'OFFRE FINIT DANS :"
                style={INPUT_STYLE}
                className="text-sm v224-input"
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs mb-1" style={LABEL_STYLE}>Date de fin</label>
                <input
                  type="date"
                  value={form.countdown_date || ''}
                  onChange={(e) => set('countdown_date', e.target.value)}
                  style={INPUT_STYLE}
                  className="text-sm v224-input"
                />
              </div>
              <div>
                <label className="block text-xs mb-1" style={LABEL_STYLE}>Heure de fin</label>
                <input
                  type="time"
                  value={form.countdown_time || '23:59'}
                  onChange={(e) => set('countdown_time', e.target.value)}
                  style={INPUT_STYLE}
                  className="text-sm v224-input"
                />
              </div>
            </div>
            {form.countdown_date ? (
              <p className="text-xs" style={{ color: '#f59e0b', opacity: 0.9 }}>
                ⏳ Compte à rebours jusqu'au{' '}
                {new Date(form.countdown_date + 'T' + (form.countdown_time || '23:59'))
                  .toLocaleDateString('fr-CH', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })}
                {' '}à {form.countdown_time || '23:59'}
              </p>
            ) : (
              <p className="text-xs" style={HINT_STYLE}>
                Choisissez une date et heure de fin pour activer le compteur
              </p>
            )}
          </div>
        ) : (
          <p className="text-xs mt-2" style={HINT_STYLE}>
            Activez pour créer une offre limitée dans le temps
          </p>
        )}
      </div>

      {/* Duree de validite */}
      <div className="p-4 rounded-lg" style={{ border: `2px solid ${PINK}`, background: 'rgba(217,28,210,0.08)' }}>
        <p className="text-sm font-bold mb-3" style={{ color: PINK }}>⏱ DURÉE DE VALIDITÉ</p>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs mb-1" style={LABEL_STYLE}>Durée</label>
            <input
              type="number"
              min="1"
              value={form.duration_value || ''}
              onChange={(e) => set('duration_value', parseInt(e.target.value, 10) || '')}
              placeholder="Ex: 2"
              style={INPUT_STYLE}
              className="text-sm v224-input"
            />
          </div>
          <div>
            <label className="block text-xs mb-1" style={LABEL_STYLE}>Unité</label>
            <select
              value={form.duration_unit || ''}
              onChange={(e) => set('duration_unit', e.target.value || null)}
              style={INPUT_STYLE}
              className="text-sm v224-input"
            >
              <option value="">Sans limite</option>
              <option value="days">Jours</option>
              <option value="weeks">Semaines</option>
              <option value="months">Mois</option>
            </select>
          </div>
        </div>
        {form.duration_value && form.duration_unit && (
          <div className="mt-3">
            <label className="flex items-center gap-2 text-sm text-white cursor-pointer">
              <input
                type="checkbox"
                checked={form.is_auto_prolong !== false}
                onChange={(e) => set('is_auto_prolong', e.target.checked)}
                className="w-4 h-4 v224-input"
                style={{ accentColor: PINK }}
              />
              Prolonger automatiquement à l'expiration
            </label>
            <p className="text-xs mt-2" style={{ color: PINK, opacity: 0.8 }}>
              📅 Valide pendant {form.duration_value}{' '}
              {form.duration_unit === 'days' ? 'jour(s)' : form.duration_unit === 'weeks' ? 'semaine(s)' : 'mois'}
              {form.is_auto_prolong !== false ? ' • Auto-prolongation activée' : ' • Expire sans renouvellement'}
            </p>
          </div>
        )}
        {!form.duration_value && !form.duration_unit && (
          <p className="text-xs mt-2" style={HINT_STYLE}>
            Laissez vide = offre sans limite de durée (illimitée)
          </p>
        )}
        {((!form.duration_value && form.duration_unit) || (form.duration_value && !form.duration_unit)) && (
          <p className="text-xs mt-2" style={{ color: '#f97316' }}>
            ⚠️ Veuillez remplir les deux champs (durée + unité) pour activer la validité
          </p>
        )}
      </div>

      {/* Cours lies */}
      {!form.isProduct && visibleCourses.length > 0 && (
        <div className="p-3 rounded-lg" style={{ border: '1px solid rgba(217,28,210,0.3)', background: 'rgba(217,28,210,0.05)' }}>
          <label className="text-xs text-white font-semibold mb-2 block">
            📅 Cours associés à cette offre
          </label>
          <p className="text-xs mb-2" style={{ color: 'rgba(255,255,255,0.5)' }}>
            Quand un client cliquera sur cette offre, il verra uniquement ces cours.
            Laissez vide pour afficher tous vos cours.
          </p>
          <div className="max-h-48 overflow-y-auto space-y-1 pr-2" style={{ scrollbarWidth: 'thin' }}>
            {visibleCourses.map(course => {
              const linked = linkedIds.includes(course.id);
              return (
                <label
                  key={course.id}
                  className="flex items-center gap-2 text-sm text-white py-1.5 px-2 rounded cursor-pointer hover:bg-white/5"
                >
                  <input
                    type="checkbox"
                    checked={linked}
                    onChange={(e) => set(
                      'linked_course_ids',
                      e.target.checked
                        ? [...linkedIds, course.id]
                        : linkedIds.filter(id => id !== course.id)
                    )}
                    className="w-4 h-4 v224-input"
                  />
                  <span className="flex-1">
                    <span className="font-medium">{course.name || course.title || 'Cours'}</span>
                    <span className="text-white/50 text-xs ml-2">
                      {course.weekday !== undefined && WEEKDAYS[course.weekday]} • {course.time}
                    </span>
                  </span>
                </label>
              );
            })}
          </div>
          {linkedIds.length > 0 && (
            <p className="text-xs mt-2 text-pink-400">✓ {linkedIds.length} cours lié(s)</p>
          )}
        </div>
      )}

      {/* V224: metadonnees d'activite */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div>
          <label className="block text-xs mb-1" style={LABEL_STYLE}>⏲ Durée de la séance (min)</label>
          <input
            type="number"
            min="0"
            value={form.duration_minutes ?? ''}
            onChange={(e) => set('duration_minutes', e.target.value === '' ? '' : parseInt(e.target.value, 10))}
            placeholder="60"
            style={INPUT_STYLE}
            className="text-sm v224-input"
          />
        </div>
        <div>
          <label className="block text-xs mb-1" style={LABEL_STYLE}>📍 Lieu</label>
          <input
            type="text"
            value={form.location || ''}
            onChange={(e) => set('location', e.target.value)}
            placeholder="Ex: Salle Afroboost, Lausanne"
            style={INPUT_STYLE}
            className="text-sm v224-input"
          />
        </div>
        <div>
          <label className="block text-xs mb-1" style={LABEL_STYLE}>👥 Participants max</label>
          <input
            type="number"
            min="0"
            value={form.max_participants ?? ''}
            onChange={(e) => set('max_participants', e.target.value === '' ? '' : parseInt(e.target.value, 10))}
            placeholder="20"
            style={INPUT_STYLE}
            className="text-sm v224-input"
          />
        </div>
      </div>

      {/* Categorie / type / visibilite */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 items-end">
        <div>
          <label className="block text-xs mb-1" style={LABEL_STYLE}>Catégorie</label>
          <select
            value={form.category || 'service'}
            onChange={(e) => set('category', e.target.value)}
            style={INPUT_STYLE}
            className="text-sm v224-input"
          >
            <option value="service">🎧 Service / Cours</option>
            <option value="tshirt">👕 T-shirt</option>
            <option value="shoes">👟 Chaussures</option>
            <option value="supplement">💊 Complément</option>
            <option value="accessory">🎒 Accessoire</option>
          </select>
        </div>
        <label className="flex items-center gap-2 text-white text-sm py-2 cursor-pointer">
          <input
            type="checkbox"
            checked={!!form.isProduct}
            onChange={(e) => set('isProduct', e.target.checked)}
            className="w-5 h-5 v224-input"
          />
          Produit physique
        </label>
        <label className="flex items-center gap-2 text-white text-sm py-2 cursor-pointer">
          <input
            type="checkbox"
            checked={!!form.visible}
            onChange={(e) => set('visible', e.target.checked)}
            className="w-5 h-5 v224-input"
          />
          Visible
        </label>
      </div>

      {/* Bloc produit */}
      {form.isProduct && (
        <div className="p-3 rounded-lg" style={{ border: '1px solid rgba(139,92,246,0.3)' }}>
          <p className="text-xs text-purple-400 mb-3">📦 Paramètres produit</p>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            <div>
              <label className="block text-xs mb-1" style={LABEL_STYLE}>TVA (%)</label>
              <input
                type="number"
                step="0.1"
                value={form.tva || ''}
                onChange={(e) => set('tva', parseFloat(e.target.value) || 0)}
                placeholder="7.7"
                style={INPUT_STYLE}
                className="text-sm v224-input"
              />
            </div>
            <div>
              <label className="block text-xs mb-1" style={LABEL_STYLE}>Frais de port</label>
              <input
                type="number"
                step="0.1"
                value={form.shippingCost || ''}
                onChange={(e) => set('shippingCost', parseFloat(e.target.value) || 0)}
                placeholder="9.90"
                style={INPUT_STYLE}
                className="text-sm v224-input"
              />
            </div>
            <div>
              <label className="block text-xs mb-1" style={LABEL_STYLE}>Stock</label>
              <input
                type="number"
                value={form.stock ?? ''}
                onChange={(e) => set('stock', parseInt(e.target.value, 10) || -1)}
                placeholder="-1"
                style={INPUT_STYLE}
                className="text-sm v224-input"
              />
            </div>
          </div>

          {/* V224: variantes CONTROLEES (elles ne l'etaient pas dans
              OffersManager.js, d'ou leur non-pre-remplissage en edition). */}
          <div className="mt-3">
            <label className="block text-xs mb-2" style={LABEL_STYLE}>
              Variantes (séparées par virgule)
            </label>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              {VARIANT_FIELDS.map(({ key, placeholder }) => (
                <input
                  key={key}
                  type="text"
                  // V224: la chaine brute prime; le tableau ne sert que de
                  // repli quand rien n'a encore ete saisi ni pre-rempli.
                  value={variantsRaw[key] ?? (form.variants?.[key] || []).join(', ')}
                  onChange={(e) => setVariant(key, e.target.value)}
                  placeholder={placeholder}
                  style={INPUT_STYLE}
                  className="text-sm v224-input"
                />
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );

  const renderStep3 = () => (
    <div className="space-y-4">
      <div>
        <label className="block text-xs mb-2" style={LABEL_STYLE}>📷 Images (max 5 URLs)</label>
        <div className="space-y-2">
          {[0, 1, 2, 3, 4].map(i => (
            <input
              key={i}
              type="url"
              value={form.images?.[i] || ''}
              onChange={(e) => {
                const next = [...(form.images || ['', '', '', '', ''])];
                next[i] = e.target.value;
                set('images', next);
              }}
              placeholder={`Image ${i + 1}`}
              style={INPUT_STYLE}
              className="text-sm v224-input"
            />
          ))}
        </div>
      </div>

      <div>
        <label className="block text-xs mb-1" style={LABEL_STYLE}>🎬 Vidéo (URL)</label>
        <input
          type="url"
          value={form.videoUrl || ''}
          onChange={(e) => set('videoUrl', e.target.value)}
          placeholder="https://www.youtube.com/watch?v=... ou lien .mp4"
          style={INPUT_STYLE}
          className="text-sm v224-input"
        />
        {form.videoUrl && (
          <div className="mt-3" style={{ borderRadius: '8px', overflow: 'hidden' }}>
            {/YouTube|youtu\.be|vimeo/i.test(form.videoUrl) ? (
              <iframe
                src={toEmbedUrl(form.videoUrl)}
                title="Apercu video"
                style={{ width: '100%', aspectRatio: '16 / 9', border: 0 }}
                allowFullScreen
              />
            ) : (
              <video
                src={form.videoUrl}
                controls
                playsInline
                style={{ width: '100%', maxHeight: '260px', background: '#000' }}
              />
            )}
          </div>
        )}
      </div>
    </div>
  );

  return (
    <div
      // V224: on ferme sur mousedown SUR l'overlay uniquement. Un `click` se
      // declenche aussi quand le mousedown a eu lieu dans le panneau et le
      // mouseup sur l'overlay (selection de texte relachee hors du panneau),
      // ce qui detruisait toute la saisie.
      onMouseDown={(e) => { if (e.target === e.currentTarget) onCancel(); }}
      style={{
        position: 'fixed', inset: 0, zIndex: 1000,
        background: 'rgba(0,0,0,0.75)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        padding: '16px'
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: '#1a1a2e',
          border: `1px solid ${ACCENT_BORDER}`,
          borderRadius: '12px',
          width: '100%', maxWidth: '640px',
          maxHeight: '90vh', display: 'flex', flexDirection: 'column'
        }}
      >
        {/* En-tete */}
        <div className="flex items-center justify-between px-5 pt-5 pb-3">
          <h3 className="text-white font-semibold text-base">
            {isEditing ? '✏️ Modifier l\'offre' : '➕ Nouvelle offre'}
          </h3>
          <button
            type="button"
            onClick={onCancel}
            className="text-lg leading-none"
            style={{ color: 'rgba(255,255,255,0.5)', background: 'none', border: 'none', cursor: 'pointer' }}
            aria-label="Fermer"
          >
            ✕
          </button>
        </div>

        {/* Onglets */}
        <div className="flex gap-4 px-5 pb-3" style={{ borderBottom: `1px solid ${ACCENT_BORDER}` }}>
          {STEPS.map(s => (
            <button
              key={s.n}
              type="button"
              onClick={() => setStep(s.n)}
              className="text-sm font-medium pb-2 transition-all"
              style={{
                color: step === s.n ? PINK : '#666',
                borderBottom: step === s.n ? `2px solid ${PINK}` : '2px solid transparent',
                background: 'none',
                cursor: 'pointer'
              }}
            >
              ({s.n}) {s.label}
            </button>
          ))}
        </div>

        {/* Contenu de l'etape */}
        <div style={{ overflowY: 'auto', flex: 1, padding: '20px' }}>
          {step === 1 && renderStep1()}
          {step === 2 && renderStep2()}
          {step === 3 && renderStep3()}
        </div>

        {/* Pied de modal */}
        <div
          className="flex items-center justify-between gap-3 px-5 py-4"
          style={{ borderTop: `1px solid ${ACCENT_BORDER}` }}
        >
          <button
            type="button"
            onClick={onCancel}
            className="text-sm px-4 py-2 rounded-lg"
            style={{ color: 'rgba(255,255,255,0.6)', background: 'none', border: '1px solid #333', cursor: 'pointer' }}
          >
            Annuler
          </button>

          <div className="flex items-center gap-2">
            {step === 3 && (
              <button
                type="button"
                onClick={() => setStep(2)}
                className="text-sm px-4 py-2 rounded-lg"
                style={{ color: 'rgba(255,255,255,0.6)', background: 'none', border: '1px solid #333', cursor: 'pointer' }}
              >
                ← Précédent
              </button>
            )}
            {step < 3 ? (
              <button
                type="button"
                onClick={() => setStep(step + 1)}
                className="text-sm font-medium px-5 py-2 rounded-lg"
                style={{ background: PINK, color: '#fff', border: 'none', cursor: 'pointer' }}
              >
                Suivant →
              </button>
            ) : (
              <button
                type="button"
                onClick={handleSave}
                className="text-sm font-medium px-5 py-2 rounded-lg"
                style={{ background: PINK, color: '#fff', border: 'none', cursor: 'pointer' }}
              >
                {isEditing ? 'Enregistrer' : 'Créer l\'offre'}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
