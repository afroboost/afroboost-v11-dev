/**
 * OffersManager Component v13.5 (V93)
 * Gestion des offres/produits - Extrait de CoachDashboard.js
 */
import React from 'react';
import OfferWizard from './OfferWizard';   // V224
import OfferCard from './OfferCard';       // V224

const OffersManager = ({
  offers,
  setOffers,
  newOffer,
  setNewOffer,
  offersSearch,
  setOffersSearch,
  editingOfferId,
  addOffer,
  updateOffer,
  deleteOffer,
  startEditOffer,
  cancelEditOffer,
  enhanceWithAI,
  API,
  isSuperAdmin,
  coachEmail,
  consumeCredit,
  courses = [],
  t
}) => {
  const [aiLoading, setAiLoading] = React.useState(false);
  const [showOnboarding, setShowOnboarding] = React.useState(false);
  // v159: État pour accordéon Design A — quelle carte est dépliée
  const [expandedOfferId, setExpandedOfferId] = React.useState(null);

  // v159 Helper: Retourne les cours liés à une offre donnée
  const getLinkedCoursesForOffer = (offer) => {
    const ids = offer?.linked_course_ids || [];
    if (!ids.length) return [];
    return (courses || []).filter(c => ids.includes(c.id) && !c.archived);
  };

  // v159 Helper: Offre sans horaires (produit/audio/video) ?
  const isOfferWithoutSchedule = (offer) => {
    return !!(offer.isProduct || (offer.category && ['tshirt','shoes','supplement','accessory','audio','video'].includes(offer.category)));
  };

  // v159: Drag & Drop réorganisation offres (souris PC + touch mobile)
  const [draggingId, setDraggingId] = React.useState(null);
  const [dragOverId, setDragOverId] = React.useState(null);
  const touchStartY = React.useRef(0);

  const handleDragStart = (e, offerId) => {
    setDraggingId(offerId);
    if (e.dataTransfer) {
      e.dataTransfer.effectAllowed = 'move';
      e.dataTransfer.setData('text/plain', offerId);
    }
  };
  const handleDragOver = (e, offerId) => {
    e.preventDefault();
    if (e.dataTransfer) e.dataTransfer.dropEffect = 'move';
    setDragOverId(offerId);
  };
  const handleDragEnd = () => { setDraggingId(null); setDragOverId(null); };

  // V224: persistance de l'ordre extraite de handleDrop pour etre partagee avec
  // les boutons monter/descendre des cartes. La regle reste celle de v159 :
  // `position` = index dans la liste reordonnee. Seule addition : on ne PUT que
  // les offres dont la position change reellement, pour ne pas emettre N
  // requetes a chaque petit deplacement (au premier reordonnancement, aucune
  // offre n'a encore de `position`, donc toutes sont bien ecrites).
  const persistOfferOrder = async (reordered) => {
    const withPositions = reordered.map((o, i) => ({ ...o, position: i }));
    setOffers(withPositions);
    try {
      const changed = withPositions.filter(o => {
        const prev = offers.find(p => p.id === o.id);
        return !prev || prev.position !== o.position;
      });
      await Promise.all(changed.map(o => updateOffer(o)));
    } catch (err) { console.error('[V159] reorder error:', err); }
  };

  const handleDrop = async (e, targetOfferId) => {
    e.preventDefault();
    const draggedId = draggingId;
    setDraggingId(null); setDragOverId(null);
    if (!draggedId || draggedId === targetOfferId) return;
    const fromIdx = offers.findIndex(o => o.id === draggedId);
    const toIdx = offers.findIndex(o => o.id === targetOfferId);
    if (fromIdx < 0 || toIdx < 0) return;
    // Réordonner localement
    const reordered = [...offers];
    const [moved] = reordered.splice(fromIdx, 1);
    reordered.splice(toIdx, 0, moved);
    // Sauvegarder l'ordre via PUT sur chaque offre (champ position)
    // V224: setOffers + PUT delegues a persistOfferOrder (meme logique).
    await persistOfferOrder(reordered);
  };
  // Touch handlers pour mobile (swipe vertical pour réordonner)
  const handleTouchStart = (e, offerId) => {
    touchStartY.current = e.touches[0].clientY;
    setDraggingId(offerId);
  };
  const handleTouchMove = (e) => {
    if (!draggingId) return;
    const touch = e.touches[0];
    const elOver = document.elementFromPoint(touch.clientX, touch.clientY);
    const card = elOver?.closest('[data-offer-id]');
    if (card) setDragOverId(card.getAttribute('data-offer-id'));
  };
  const handleTouchEnd = (e) => {
    if (!draggingId || !dragOverId) { setDraggingId(null); setDragOverId(null); return; }
    handleDrop({ preventDefault: () => {} }, dragOverId);
  };

  // v159 Helper: Toggle lien cours ↔ offre (appelle updateOffer)
  const toggleCourseLink = async (offer, courseId) => {
    const currentIds = offer.linked_course_ids || [];
    const newIds = currentIds.includes(courseId)
      ? currentIds.filter(id => id !== courseId)
      : [...currentIds, courseId];
    const updated = { ...offer, linked_course_ids: newIds };
    // Met à jour localement puis sauvegarde
    setOffers(prev => prev.map(o => o.id === offer.id ? updated : o));
    try { await updateOffer(updated); } catch (e) { console.error('[V159] toggleCourseLink error:', e); }
  };

  // v159 Helper: Rendu section horaires pour une offre (accordéon interne)
  const WEEKDAYS = ['Dimanche','Lundi','Mardi','Mercredi','Jeudi','Vendredi','Samedi'];
  const renderScheduleSection = (offer) => {
    if (isOfferWithoutSchedule(offer)) {
      return (
        <div className="mt-3 p-3 rounded-lg text-xs" style={{ background: 'rgba(139,92,246,0.08)', color: 'rgba(255,255,255,0.6)' }}>
          {offer.category === 'audio' ? '🎵' : offer.category === 'video' ? '🎬' : '📦'} Produit sans horaire
        </div>
      );
    }
    const linkedCourses = getLinkedCoursesForOffer(offer);
    const myCourses = (courses || []).filter(c => !c.archived && (isSuperAdmin || (c.coach_id || '').toLowerCase() === (coachEmail || '').toLowerCase()));
    return (
      <div className="mt-3 p-3 rounded-lg" style={{ background: 'rgba(217,28,210,0.06)', border: '1px solid rgba(217,28,210,0.2)' }}>
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs font-semibold" style={{ color: '#d91cd2' }}>
            📅 Horaires proposés ({linkedCourses.length})
          </span>
          <span className="text-xs text-white/40">
            {linkedCourses.length === 0 ? 'Aucun — tous les cours seront proposés' : ''}
          </span>
        </div>
        {/* Liste des cours liés (chips avec bouton suppression) */}
        {linkedCourses.length > 0 && (
          <div className="flex flex-wrap gap-2 mb-3">
            {linkedCourses.map(c => (
              <div key={c.id} className="flex items-center gap-1.5 px-2 py-1 rounded-full text-xs"
                style={{ background: 'rgba(217,28,210,0.25)', border: '1px solid rgba(217,28,210,0.5)', color: '#fff' }}>
                <span>{c.name}</span>
                <span className="text-white/60">•&nbsp;{WEEKDAYS[c.weekday]}&nbsp;{c.time}</span>
                <button
                  type="button"
                  onClick={() => toggleCourseLink(offer, c.id)}
                  className="ml-1 text-white/70 hover:text-red-300"
                  title="Retirer ce créneau"
                >✕</button>
              </div>
            ))}
          </div>
        )}
        {/* Sélecteur compact pour AJOUTER un cours */}
        {myCourses.filter(c => !(offer.linked_course_ids || []).includes(c.id)).length > 0 && (
          <details>
            <summary className="cursor-pointer text-xs font-medium py-1" style={{ color: '#a78bfa' }}>
              + Ajouter un horaire à cette offre
            </summary>
            <div className="mt-2 space-y-1 max-h-40 overflow-y-auto">
              {myCourses.filter(c => !(offer.linked_course_ids || []).includes(c.id)).map(c => (
                <button
                  key={c.id}
                  type="button"
                  onClick={() => toggleCourseLink(offer, c.id)}
                  className="w-full text-left px-2 py-1.5 rounded text-xs hover:bg-white/10"
                  style={{ color: '#fff' }}
                >
                  + {c.name} <span className="text-white/50">• {WEEKDAYS[c.weekday]} {c.time}</span>
                </button>
              ))}
            </div>
          </details>
        )}
      </div>
    );
  };

  React.useEffect(() => {
    if (!isSuperAdmin) {
      try {
        const seen = localStorage.getItem('afroboost_onboarding_offers');
        if (!seen) setShowOnboarding(true);
      } catch(e) {}
    }
  }, [isSuperAdmin]);

  const dismissOnboarding = () => {
    setShowOnboarding(false);
    try { localStorage.setItem('afroboost_onboarding_offers', '1'); } catch(e) {}
  };

  const isOwnOffer = (offer) => {
    if (isSuperAdmin) return true;
    return (offer.coach_id || '').toLowerCase() === (coachEmail || '').toLowerCase();
  };

  // V224: appel IA extrait de handleAIEnhance pour etre reutilisable. Il RETOURNE
  // le texte ameliore au lieu d'ecrire dans le state : le wizard tient son propre
  // formulaire, et un setNewOffer ici changerait la reference de `initialOffer`,
  // ce qui reinitialiserait le wizard en pleine saisie.
  const fetchEnhancedText = async (text) => {
    const res = await fetch(`${API}/ai/enhance-text`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, context: 'offer' })
    });
    const data = await res.json();
    if (data.enhanced_text && !data.fallback) return data.enhanced_text;
    return null;
  };

  const handleAIEnhance = async (field) => {
    const text = field === 'name' ? newOffer.name : newOffer.description;
    if (!text || text.trim().length < 3) return;
    setAiLoading(true);
    try {
      // V224: meme requete qu'avant, deleguee a fetchEnhancedText.
      const enhanced = await fetchEnhancedText(text);
      if (enhanced) {
        if (field === 'name') {
          setNewOffer({ ...newOffer, name: enhanced });
        } else {
          setNewOffer({ ...newOffer, description: enhanced.slice(0, 150) });
        }
      }
    } catch (err) {
      console.error('[AI Enhance]', err);
    } finally {
      setAiLoading(false);
    }
  };

  // V224: branchement du bouton « Aide IA » du wizard. Meme garde de longueur
  // minimale que handleAIEnhance ; la troncature a 150 caracteres n'est PAS
  // reprise ici, le champ du wizard acceptant jusqu'a 3000 caracteres.
  const handleWizardEnhanceDescription = async (text) => {
    if (!text || text.trim().length < 3) return null;
    return await fetchEnhancedText(text);
  };

  // V224: la grille suit l'ordre du champ `position`, exactement comme la
  // vitrine publique (App.js l.4506) : ce que le coach reorganise ici est donc
  // bien ce que verront ses clients. Le tri est stable, les offres sans
  // `position` restent en fin de liste dans leur ordre d'origine.
  const orderedOffers = React.useMemo(() => {
    return [...offers].sort((a, b) => {
      const pa = typeof a.position === 'number' ? a.position : 999999;
      const pb = typeof b.position === 'number' ? b.position : 999999;
      return pa - pb;
    });
  }, [offers]);

  // V224: reorganisation depuis la grille de cartes. On travaille sur
  // orderedOffers (l'ordre affiche) et on reutilise persistOfferOrder.
  const moveOffer = (offer, direction) => {
    const from = orderedOffers.findIndex(o => o.id === offer.id);
    const to = from + direction;
    if (from < 0 || to < 0 || to >= orderedOffers.length) return;
    const reordered = [...orderedOffers];
    const [moved] = reordered.splice(from, 1);
    reordered.splice(to, 0, moved);
    persistOfferOrder(reordered);
  };

  // V224: filtre de recherche extrait une seule fois — il etait duplique dans
  // les rendus mobile et desktop.
  const filteredOffers = offersSearch
    ? orderedOffers.filter(o =>
        o.name?.toLowerCase().includes(offersSearch.toLowerCase()) ||
        o.description?.toLowerCase().includes(offersSearch.toLowerCase())
      )
    : orderedOffers;

  // V224: etat d'ouverture du wizard.
  const [wizardOpen, setWizardOpen] = React.useState(false);

  // V224: ouverture en creation
  const openCreate = () => {
    cancelEditOffer();      // remet newOffer a vide via le parent
    setWizardOpen(true);
  };

  // V224: ouverture en edition — startEditOffer pre-remplit newOffer
  const openEdit = (offer) => {
    startEditOffer(offer);
    setWizardOpen(true);
  };

  // V224: duplication — startEditOffer sans id laisse editingOfferId a undefined,
  // donc addOffer partira sur un POST (creation) et non un PUT.
  const openDuplicate = (offer) => {
    startEditOffer({ ...offer, id: undefined, name: (offer.name || '') + ' (copie)' });
    setWizardOpen(true);
  };

  // V224: le wizard remonte tout d'un coup ; on aligne newOffer (pour que le
  // formulaire reste coherent) puis on delegue a addOffer EN LUI PASSANT les
  // valeurs, ce qui evite de dependre de l'application asynchrone du state.
  // V224: on n'attend PAS setNewOffer pour enregistrer (les valeurs sont
  // passees a addOffer), et surtout on ne ferme le wizard QUE si
  // l'enregistrement a reussi : sinon les 3 etapes de saisie seraient perdues,
  // openCreate() appelant cancelEditOffer() qui remet le formulaire a vide.
  // V224: surtout PAS de setNewOffer(formValues) ici. Il changerait la reference
  // de initialOffer pendant que le modal est ouvert, ce qui declenche l'effet
  // [open, initialOffer] du wizard et le renvoie a l'etape 1 le temps de la
  // requete — puis l'y laisse en cas d'echec. addOffer recoit deja les valeurs
  // en argument et reinitialise newOffer lui-meme en cas de succes.
  const handleWizardSave = async (formValues) => {
    const saved = await addOffer(null, formValues);
    if (saved) setWizardOpen(false);
  };

  // V224: bascule visible/masquee depuis une carte. On met a jour le state local
  // pour un retour immediat, comme le faisait l'ancien rendu en liste.
  const handleToggleVisible = (offer) => {
    const updated = { ...offer, visible: offer.visible === false };
    setOffers(prev => prev.map(o => (o.id === offer.id ? updated : o)));
    updateOffer(updated);
  };

  // V224: on conserve la protection « offre d'un autre coach » que portaient les
  // boutons Supprimer de l'ancien rendu en liste.
  const handleDelete = (offerId) => {
    const offer = offers.find(o => o.id === offerId);
    if (offer && !isOwnOffer(offer)) {
      alert('🔒 Vous ne pouvez supprimer que vos propres offres');
      return;
    }
    deleteOffer(offerId);
  };

  return (
    <div className="card-gradient rounded-xl p-4 sm:p-6">
      {/* v93: Onboarding tooltips for new partners */}
      {showOnboarding && !isSuperAdmin && (
        <div style={{
          background: 'linear-gradient(135deg, rgba(217,28,210,0.15), rgba(255,45,170,0.1))',
          border: '1px solid rgba(217,28,210,0.4)',
          borderRadius: '12px',
          padding: '16px',
          marginBottom: '16px',
          position: 'relative'
        }}>
          <button onClick={dismissOnboarding} style={{
            position: 'absolute', top: '8px', right: '12px',
            background: 'none', border: 'none', color: 'rgba(255,255,255,0.5)',
            fontSize: '18px', cursor: 'pointer'
          }}>\u2715</button>
          <h3 style={{ color: '#D91CD2', fontSize: '14px', fontWeight: 'bold', marginBottom: '10px' }}>
            \ud83d\udca1 Bienvenue dans votre espace Offres !
          </h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: '8px' }}>
              <span style={{ fontSize: '16px' }}>\ud83c\udfaf</span>
              <p style={{ color: 'rgba(255,255,255,0.7)', fontSize: '12px', margin: 0 }}>
                <strong style={{ color: '#fff' }}>Cr\u00e9ez vos offres</strong> \u2014 Ajoutez vos services, cours ou produits avec prix, description et images.
              </p>
            </div>
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: '8px' }}>
              <span style={{ fontSize: '16px' }}>\ud83d\udd12</span>
              <p style={{ color: 'rgba(255,255,255,0.7)', fontSize: '12px', margin: 0 }}>
                <strong style={{ color: '#fff' }}>S\u00e9curit\u00e9</strong> \u2014 Vous ne pouvez modifier ou supprimer que vos propres offres.
              </p>
            </div>
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: '8px' }}>
              <span style={{ fontSize: '16px' }}>\ud83d\udcb3</span>
              <p style={{ color: 'rgba(255,255,255,0.7)', fontSize: '12px', margin: 0 }}>
                <strong style={{ color: '#fff' }}>Cr\u00e9dits</strong> \u2014 Chaque activation de service consomme des cr\u00e9dits. Rechargez dans la Boutique.
              </p>
            </div>
          </div>
        </div>
      )}
      {/* En-tête fixe avec titre et recherche */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3 mb-4 sticky top-0 z-10 pb-3" style={{ background: 'inherit' }}>
        <h2 className="font-semibold text-white text-lg sm:text-xl">{t('offers')}</h2>
        <div className="relative w-full sm:w-64">
          <input
            type="text"
            placeholder="🔍 Rechercher une offre..."
            value={offersSearch || ''}
            onChange={(e) => setOffersSearch(e.target.value)}
            className="w-full px-3 py-2 rounded-lg text-sm"
            style={{ background: 'rgba(139, 92, 246, 0.1)', border: '1px solid rgba(139, 92, 246, 0.3)', color: '#fff' }}
            data-testid="offers-search-input"
          />
          {offersSearch && (
            <button
              onClick={() => setOffersSearch('')}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-white/50 hover:text-white"
            >✕</button>
          )}
        </div>
      </div>
      
      {/* V224: grille de cartes */}
      <div className="flex justify-between items-center mb-4">
        <h3 className="text-white font-semibold">Mes offres</h3>
        <button type="button" onClick={openCreate} className="text-xs px-4 py-2 rounded-lg" style={{ background: '#D91CD2', color: '#fff' }}>
          + NOUVELLE OFFRE
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {filteredOffers.map(offer => {
          // V224: index dans l'ordre reel (et non dans la liste filtree), pour
          // que les fleches deplacent l'offre par rapport a ses vrais voisins.
          const orderIdx = orderedOffers.findIndex(o => o.id === offer.id);
          return (
            <OfferCard
              key={offer.id}
              offer={offer}
              onEdit={openEdit}
              onDuplicate={openDuplicate}
              onDelete={handleDelete}
              onToggleVisible={handleToggleVisible}
              // V224: affordance « offre protegee »
              canDelete={isOwnOffer(offer)}
              // V224: reorganisation. Masquee pendant une recherche : la liste
              // affichee n'etant pas complete, les fleches designeraient des
              // voisins invisibles.
              onMoveUp={offersSearch ? undefined : (o) => moveOffer(o, -1)}
              onMoveDown={offersSearch ? undefined : (o) => moveOffer(o, 1)}
              // V224 (revue finale): garde de propriete. La grille n'est pas
              // filtree par coach_id (comportement historique), or moveOffer →
              // persistOfferOrder emet un PUT sur CHAQUE offre dont la position
              // change, et PUT /offers/{id} n'a aucun controle de proprietaire
              // cote serveur. Sans cette garde, un coach non-admin reordonne la
              // vitrine d'un autre coach en un tap. Le controle serveur reste a
              // faire (ticket backend separe) — ceci en limite l'exposition.
              canMoveUp={!offersSearch && isOwnOffer(offer) && orderIdx > 0}
              canMoveDown={!offersSearch && isOwnOffer(offer) && orderIdx >= 0 && orderIdx < orderedOffers.length - 1}
            />
          );
        })}
      </div>

      <OfferWizard
        open={wizardOpen}
        initialOffer={newOffer}
        courses={courses}
        isEditing={!!editingOfferId}
        onSave={handleWizardSave}
        onCancel={() => { setWizardOpen(false); cancelEditOffer(); }}
        isSuperAdmin={isSuperAdmin}
        coachEmail={coachEmail}
        onEnhanceDescription={handleWizardEnhanceDescription}
      />

      {/* Conteneur scrollable pour les offres */}
      {/* V224: l'ancien rendu en liste est conserve mais n'est plus rendu. */}
      {false && (
      <div style={{ maxHeight: '500px', overflowY: 'auto', overflowX: 'hidden' }}>
        {/* === MOBILE VIEW: Cartes verticales === */}
        <div className="block md:hidden space-y-4">
          {(offersSearch ? offers.filter(o =>
            o.name?.toLowerCase().includes(offersSearch.toLowerCase()) ||
            o.description?.toLowerCase().includes(offersSearch.toLowerCase())
          ) : offers).map((offer, idx) => (
            <div
              key={offer.id}
              data-offer-id={offer.id}
              draggable
              onDragStart={(e) => handleDragStart(e, offer.id)}
              onDragOver={(e) => handleDragOver(e, offer.id)}
              onDragEnd={handleDragEnd}
              onDrop={(e) => handleDrop(e, offer.id)}
              onTouchMove={handleTouchMove}
              onTouchEnd={handleTouchEnd}
              className="glass rounded-lg p-4"
              style={{
                cursor: 'grab',
                opacity: draggingId === offer.id ? 0.5 : 1,
                border: dragOverId === offer.id && draggingId !== offer.id ? '2px dashed #d91cd2' : undefined,
                transition: 'opacity 0.2s',
              }}
            >
              {/* Poignée de drag (visible) */}
              <div
                onTouchStart={(e) => handleTouchStart(e, offer.id)}
                className="flex items-center gap-2 mb-2 -mt-1"
                style={{ cursor: 'grab', color: 'rgba(255,255,255,0.3)', fontSize: '14px', userSelect: 'none' }}
                title="Maintenir et glisser pour réorganiser"
              >
                <span style={{ letterSpacing: '1px' }}>⋮⋮</span>
                <span style={{ fontSize: '10px' }}>Glisser pour déplacer</span>
              </div>
              {/* Image et nom */}
              <div className="flex items-center gap-3 mb-3">
                {offer.images?.[0] || offer.thumbnail ? (
                  <img src={offer.images?.[0] || offer.thumbnail} alt="" className="w-16 h-16 rounded-lg object-cover flex-shrink-0" loading="lazy" />
                ) : (
                  <div className="w-16 h-16 rounded-lg bg-purple-900/30 flex items-center justify-center text-2xl flex-shrink-0">🎧</div>
                )}
                <div className="flex-1 min-w-0">
                  <h4 className="text-white font-semibold text-sm truncate">{offer.name}</h4>
                  <p className="text-purple-400 text-xs">{offer.price} CHF</p>
                  <p className="text-white/50 text-xs">{offer.images?.filter(i => i).length || 0} images</p>
                </div>
                {/* Toggle visible */}
                <div className="flex flex-col items-center gap-1">
                  <div 
                    className={`switch ${offer.visible ? 'active' : ''}`} 
                    onClick={() => { 
                      const n = [...offers]; 
                      n[idx].visible = !offer.visible; 
                      setOffers(n); 
                      updateOffer({ ...offer, visible: !offer.visible }); 
                    }} 
                  />
                  <span className="text-xs text-white/40">{offer.visible ? 'ON' : 'OFF'}</span>
                </div>
              </div>
              
              {/* Description */}
              {offer.description && (
                <p className="text-white/60 text-xs mb-3 italic truncate">"{offer.description}"</p>
              )}

              {/* v159 Design A: Bouton accordéon pour déplier les horaires */}
              <button
                type="button"
                onClick={() => setExpandedOfferId(expandedOfferId === offer.id ? null : offer.id)}
                className="w-full mb-2 py-2 rounded-lg text-xs font-medium flex items-center justify-between px-3"
                style={{ background: 'rgba(139,92,246,0.15)', color: '#c4b5fd', border: '1px solid rgba(139,92,246,0.3)' }}
              >
                <span>
                  {isOfferWithoutSchedule(offer)
                    ? (offer.isProduct ? '📦 Produit' : offer.category === 'audio' ? '🎵 Audio' : offer.category === 'video' ? '🎬 Vidéo' : '📦 Produit')
                    : `📅 ${getLinkedCoursesForOffer(offer).length} horaire(s) associé(s)`}
                </span>
                <span>{expandedOfferId === offer.id ? '▲' : '▼'}</span>
              </button>

              {/* Section horaires liés (accordéon) */}
              {expandedOfferId === offer.id && renderScheduleSection(offer)}

              {/* Boutons action */}
              <div className="flex gap-2 mt-2">
                <button
                  onClick={() => startEditOffer(offer)}
                  className="flex-1 py-3 rounded-lg bg-purple-600 hover:bg-purple-500 text-white text-sm font-medium"
                  data-testid={`edit-offer-${offer.id}`}
                >
                  ✏️ Modifier
                </button>
                {isOwnOffer(offer) ? (
                  <button
                    onClick={() => deleteOffer(offer.id)}
                    className="flex-1 py-3 rounded-lg bg-red-600 hover:bg-red-500 text-white text-sm font-medium"
                    data-testid={`delete-offer-${offer.id}`}
                  >
                    🗑️ Supprimer
                  </button>
                ) : (
                  <button
                    disabled
                    className="flex-1 py-3 rounded-lg bg-gray-600 text-white/30 text-sm font-medium cursor-not-allowed"
                    title="Vous ne pouvez supprimer que vos propres offres"
                  >
                    🔒 Protégée
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>

        {/* === DESKTOP VIEW: Layout horizontal === */}
        <div className="hidden md:block">
          {(offersSearch ? offers.filter(o =>
            o.name?.toLowerCase().includes(offersSearch.toLowerCase()) ||
            o.description?.toLowerCase().includes(offersSearch.toLowerCase())
          ) : offers).map((offer, idx) => (
            <div
              key={offer.id}
              data-offer-id={offer.id}
              draggable
              onDragStart={(e) => handleDragStart(e, offer.id)}
              onDragOver={(e) => handleDragOver(e, offer.id)}
              onDragEnd={handleDragEnd}
              onDrop={(e) => handleDrop(e, offer.id)}
              className="glass rounded-lg p-4 mb-4"
              style={{
                cursor: 'grab',
                opacity: draggingId === offer.id ? 0.5 : 1,
                border: dragOverId === offer.id && draggingId !== offer.id ? '2px dashed #d91cd2' : undefined,
                transition: 'opacity 0.2s',
              }}
            >
              {/* v159: Poignée de drag visible (desktop) */}
              <div className="flex items-center gap-2 mb-2" style={{ color: 'rgba(255,255,255,0.4)', fontSize: '12px', userSelect: 'none' }} title="Glisser pour réorganiser">
                <span style={{ letterSpacing: '2px', fontSize: '16px' }}>⋮⋮</span>
                <span>Glisser pour déplacer</span>
              </div>
              <div className="flex justify-between items-start mb-3">
                <div className="flex items-center gap-3">
                  {offer.images?.[0] || offer.thumbnail ? (
                    <img src={offer.images?.[0] || offer.thumbnail} alt="" className="w-12 h-12 rounded-lg object-cover" loading="lazy" />
                  ) : (
                    <div className="w-12 h-12 rounded-lg bg-purple-900/30 flex items-center justify-center text-2xl">🎧</div>
                  )}
                  <div>
                    <h4 className="text-white font-semibold">{offer.name}</h4>
                    <p className="text-purple-400 text-sm">{offer.price} CHF • {offer.images?.filter(i => i).length || 0} images</p>
                  </div>
                </div>
                <div className="flex gap-2">
                  <button 
                    onClick={() => startEditOffer(offer)}
                    className="px-3 py-2 rounded-lg bg-purple-600 hover:bg-purple-500 text-white text-xs"
                    data-testid={`edit-offer-${offer.id}`}
                  >
                    ✏️ Modifier
                  </button>
                  {isOwnOffer(offer) ? (
                    <button 
                      onClick={() => deleteOffer(offer.id)}
                      className="px-3 py-2 rounded-lg bg-red-600 hover:bg-red-500 text-white text-xs"
                      data-testid={`delete-offer-${offer.id}`}
                    >
                      🗑️ Supprimer
                    </button>
                  ) : (
                    <button 
                      disabled
                      className="px-3 py-2 rounded-lg bg-gray-600 text-white/30 text-xs cursor-not-allowed"
                      title="Vous ne pouvez supprimer que vos propres offres"
                    >
                      🔒 Protégée
                    </button>
                  )}
                  <div className="flex items-center gap-2 ml-2">
                    <span className="text-xs text-white opacity-60">{t('visible')}</span>
                    <div 
                      className={`switch ${offer.visible ? 'active' : ''}`} 
                      onClick={() => { 
                        const n = [...offers]; 
                        n[idx].visible = !offer.visible; 
                        setOffers(n); 
                        updateOffer({ ...offer, visible: !offer.visible }); 
                      }} 
                    />
                  </div>
                </div>
              </div>
              {offer.description && (
                <p className="text-white/60 text-xs mt-2 italic">"{offer.description}"</p>
              )}

              {/* v159 Design A: Accordéon horaires (Desktop) */}
              <button
                type="button"
                onClick={() => setExpandedOfferId(expandedOfferId === offer.id ? null : offer.id)}
                className="w-full mt-3 py-2 rounded-lg text-xs font-medium flex items-center justify-between px-3"
                style={{ background: 'rgba(139,92,246,0.15)', color: '#c4b5fd', border: '1px solid rgba(139,92,246,0.3)' }}
              >
                <span>
                  {isOfferWithoutSchedule(offer)
                    ? (offer.isProduct ? '📦 Produit' : offer.category === 'audio' ? '🎵 Audio' : offer.category === 'video' ? '🎬 Vidéo' : '📦 Produit')
                    : `📅 ${getLinkedCoursesForOffer(offer).length} horaire(s) associé(s)`}
                </span>
                <span>{expandedOfferId === offer.id ? '▲' : '▼'}</span>
              </button>
              {expandedOfferId === offer.id && renderScheduleSection(offer)}
            </div>
          ))}
        </div>
      </div>
      )}

      {/* Formulaire Ajout/Modification - RESPONSIVE */}
      {/* V224: ancien formulaire plat conserve, remplace par OfferWizard. */}
      {false && (
      <form id="offer-form" onSubmit={addOffer} className="glass rounded-lg p-4 mt-4 border-2 border-purple-500/50">
        <h3 className="text-white mb-4 font-semibold text-sm flex items-center gap-2">
          {editingOfferId ? '✏️ Modifier l\'offre' : '➕ Ajouter une offre'}
          {editingOfferId && (
            <button type="button" onClick={cancelEditOffer} className="ml-auto text-xs text-red-400 hover:text-red-300">
              ✕ Annuler
            </button>
          )}
        </h3>
        
        {/* Basic Info */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 sm:gap-4">
          <div>
            <label className="text-xs text-white opacity-60 mb-1 block">Nom de l'offre *</label>
            <input type="text" placeholder="Ex: Cours à l'unité" value={newOffer.name} onChange={e => setNewOffer({ ...newOffer, name: e.target.value })} className="w-full px-3 py-3 rounded-lg neon-input text-sm" required />
          </div>
          <div>
            <label className="text-xs text-white opacity-60 mb-1 block">Prix (CHF)</label>
            <input type="number" placeholder="30" value={newOffer.price} onChange={e => setNewOffer({ ...newOffer, price: parseFloat(e.target.value) || 0 })} className="w-full px-3 py-3 rounded-lg neon-input text-sm" />
          </div>
        </div>

        {/* V223: Prix progressif 3 paliers */}
        <div className="mt-4 p-4 rounded-lg" style={{ background: '#000', border: '1px solid rgba(217,28,210,0.2)' }}>
          <label className="flex items-center gap-3 cursor-pointer">
            <input
              type="checkbox"
              checked={!!newOffer.progressive_pricing}
              onChange={e => setNewOffer({ ...newOffer, progressive_pricing: e.target.checked })}
              className="accent-[#D91CD2] w-4 h-4"
            />
            <span className="text-white text-sm font-medium">📊 Activer les 3 paliers de prix</span>
          </label>
          <p className="text-xs mt-1 ml-7" style={{ color: 'rgba(255,255,255,0.5)' }}>
            Récompense les réservations en avance et capture les réservations de dernière minute.
          </p>

          {newOffer.progressive_pricing && (
            <div className="mt-4 space-y-3">
              {!newOffer.countdown_date && (
                <p className="text-xs p-2 rounded" style={{ background: 'rgba(217,28,210,0.1)', color: '#D91CD2' }}>
                  ⚠️ Activez le compte à rebours ci-dessous : sans date de référence, les
                  paliers ne s'appliquent pas et le prix normal reste affiché.
                </p>
              )}
              {[
                { key: 'price_early_bird', label: '✨ Early Bird (plus de 7 jours avant)' },
                { key: 'price_standard', label: '⏱ Standard (plus de 24h avant)' },
                { key: 'price_last_minute', label: '⚡ Last Minute (moins de 24h)' },
              ].map(f => (
                <div key={f.key}>
                  <label className="block text-xs mb-1" style={{ color: 'rgba(255,255,255,0.7)' }}>{f.label}</label>
                  <input
                    type="number"
                    value={newOffer[f.key] ?? ''}
                    onChange={e => setNewOffer({ ...newOffer, [f.key]: e.target.value === '' ? null : parseFloat(e.target.value) })}
                    className="w-full px-3 py-2 rounded-lg neon-input text-sm"
                    placeholder="CHF"
                  />
                </div>
              ))}
              <button
                type="button"
                onClick={() => {
                  const base = parseFloat(newOffer.price) || 0;
                  setNewOffer({
                    ...newOffer,
                    price_early_bird: base,
                    price_standard: Math.round(base * 1.33),
                    price_last_minute: base * 2,
                  });
                }}
                className="text-xs underline"
                style={{ color: '#D91CD2' }}
              >
                Réinitialiser aux valeurs suggérées
              </button>
            </div>
          )}

          <div className="mt-4">
            <label className="block text-xs mb-1" style={{ color: 'rgba(255,255,255,0.7)' }}>
              Nombre de séances incluses (pack)
            </label>
            <input
              type="number"
              value={newOffer.pack_sessions ?? ''}
              onChange={e => setNewOffer({ ...newOffer, pack_sessions: e.target.value === '' ? null : parseInt(e.target.value, 10) })}
              className="w-full px-3 py-2 rounded-lg neon-input text-sm"
              placeholder="ex: 10"
            />
            <p className="text-xs mt-1" style={{ color: 'rgba(255,255,255,0.5)' }}>
              Si rempli, l'acheteur reçoit un espace personnel avec ce nombre de crédits.
            </p>
          </div>
        </div>

        {/* === DURÉE DE VALIDITÉ (NOUVEAU) === */}
        <div style={{ marginTop: '14px', padding: '14px', borderRadius: '10px', border: '2px solid #D91CD2', background: 'rgba(217, 28, 210, 0.08)', boxShadow: '0 0 12px rgba(217, 28, 210, 0.25)' }}>
          <p style={{ fontSize: '14px', color: '#D91CD2', marginBottom: '12px', fontWeight: 'bold' }}>⏱ DURÉE DE VALIDITÉ (NOUVEAU)</p>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
            <div>
              <label style={{ fontSize: '12px', color: 'rgba(255,255,255,0.7)', display: 'block', marginBottom: '4px' }}>Durée</label>
              <input
                type="number"
                min="1"
                placeholder="Ex: 2"
                value={newOffer.duration_value || ''}
                onChange={e => setNewOffer({ ...newOffer, duration_value: parseInt(e.target.value) || '' })}
                className="w-full px-3 py-3 rounded-lg neon-input text-sm"
              />
            </div>
            <div>
              <label style={{ fontSize: '12px', color: 'rgba(255,255,255,0.7)', display: 'block', marginBottom: '4px' }}>Unité</label>
              <select
                value={newOffer.duration_unit || ''}
                onChange={e => setNewOffer({ ...newOffer, duration_unit: e.target.value || null })}
                className="w-full px-3 py-3 rounded-lg neon-input text-sm"
              >
                <option value="">Sans limite</option>
                <option value="days">Jours</option>
                <option value="weeks">Semaines</option>
                <option value="months">Mois</option>
              </select>
            </div>
          </div>
          {newOffer.duration_value && newOffer.duration_unit && (
            <div style={{ marginTop: '10px' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '13px', color: '#fff', cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={newOffer.is_auto_prolong !== false}
                  onChange={e => setNewOffer({ ...newOffer, is_auto_prolong: e.target.checked })}
                  style={{ width: '18px', height: '18px', accentColor: '#D91CD2' }}
                />
                Prolonger automatiquement à l'expiration
              </label>
              <p style={{ fontSize: '11px', color: '#D91CD2', marginTop: '6px', opacity: 0.8 }}>
                📅 Valide pendant {newOffer.duration_value} {newOffer.duration_unit === 'days' ? 'jour(s)' : newOffer.duration_unit === 'weeks' ? 'semaine(s)' : 'mois'}
                {newOffer.is_auto_prolong !== false ? ' • Auto-prolongation activée' : ' • Expire sans renouvellement'}
              </p>
            </div>
          )}
          {/* v152: Texte d'aide selon l'état des champs */}
          {!newOffer.duration_value && !newOffer.duration_unit && (
            <p style={{ fontSize: '11px', color: 'rgba(255,255,255,0.4)', marginTop: '6px' }}>
              Laissez vide = offre sans limite de durée (illimitée)
            </p>
          )}
          {((!newOffer.duration_value && newOffer.duration_unit) || (newOffer.duration_value && !newOffer.duration_unit)) && (
            <p style={{ fontSize: '11px', color: '#f97316', marginTop: '6px' }}>
              ⚠️ Veuillez remplir les deux champs (durée + unité) pour activer la validité
            </p>
          )}
        </div>

        {/* === V159: COMPTE À REBOURS === */}
        <div style={{ marginTop: '14px', padding: '14px', borderRadius: '10px', border: '2px solid #f59e0b', background: 'rgba(245, 158, 11, 0.08)', boxShadow: '0 0 12px rgba(245, 158, 11, 0.2)' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px' }}>
            <p style={{ fontSize: '14px', color: '#f59e0b', fontWeight: 'bold', margin: 0 }}>⏳ COMPTE À REBOURS</p>
            <div
              className={`switch ${newOffer.countdown_enabled ? 'active' : ''}`}
              onClick={function() { setNewOffer(Object.assign({}, newOffer, { countdown_enabled: !newOffer.countdown_enabled })); }}
              data-testid="countdown-toggle"
              style={{ flexShrink: 0 }}
            />
          </div>
          {newOffer.countdown_enabled && (
            <div>
              <div style={{ marginBottom: '10px' }}>
                <label style={{ fontSize: '12px', color: 'rgba(255,255,255,0.7)', display: 'block', marginBottom: '4px' }}>Texte affiché</label>
                <input
                  type="text"
                  placeholder="L'OFFRE FINIT DANS :"
                  value={newOffer.countdown_text || ''}
                  onChange={function(e) { setNewOffer(Object.assign({}, newOffer, { countdown_text: e.target.value })); }}
                  className="w-full px-3 py-3 rounded-lg neon-input text-sm"
                />
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
                <div>
                  <label style={{ fontSize: '12px', color: 'rgba(255,255,255,0.7)', display: 'block', marginBottom: '4px' }}>Date de fin</label>
                  <input
                    type="date"
                    value={newOffer.countdown_date || ''}
                    onChange={function(e) { setNewOffer(Object.assign({}, newOffer, { countdown_date: e.target.value })); }}
                    className="w-full px-3 py-3 rounded-lg neon-input text-sm"
                  />
                </div>
                <div>
                  <label style={{ fontSize: '12px', color: 'rgba(255,255,255,0.7)', display: 'block', marginBottom: '4px' }}>Heure de fin</label>
                  <input
                    type="time"
                    value={newOffer.countdown_time || '23:59'}
                    onChange={function(e) { setNewOffer(Object.assign({}, newOffer, { countdown_time: e.target.value })); }}
                    className="w-full px-3 py-3 rounded-lg neon-input text-sm"
                  />
                </div>
              </div>
              {newOffer.countdown_date && (
                <p style={{ fontSize: '11px', color: '#f59e0b', marginTop: '8px', opacity: 0.9 }}>
                  ⏳ Compte à rebours jusqu'au {new Date(newOffer.countdown_date + 'T' + (newOffer.countdown_time || '23:59')).toLocaleDateString('fr-CH', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })} à {newOffer.countdown_time || '23:59'}
                </p>
              )}
              {!newOffer.countdown_date && (
                <p style={{ fontSize: '11px', color: 'rgba(255,255,255,0.4)', marginTop: '8px' }}>
                  Choisissez une date et heure de fin pour activer le compteur
                </p>
              )}
            </div>
          )}
          {!newOffer.countdown_enabled && (
            <p style={{ fontSize: '11px', color: 'rgba(255,255,255,0.4)', marginTop: '0' }}>
              Activez pour créer une offre limitée dans le temps
            </p>
          )}
        </div>

        {/* 5 Champs d'images */}
        <div className="mt-4">
          <label className="text-xs text-white opacity-60 mb-2 block">📷 Images (max 5 URLs)</label>
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-5 gap-2">
            {[0, 1, 2, 3, 4].map(i => (
              <input 
                key={i}
                type="url" 
                placeholder={`Image ${i + 1}`}
                value={newOffer.images?.[i] || ''} 
                onChange={e => {
                  const newImages = [...(newOffer.images || ["", "", "", "", ""])];
                  newImages[i] = e.target.value;
                  setNewOffer({ ...newOffer, images: newImages });
                }}
                className="w-full px-3 py-3 rounded-lg neon-input text-xs"
              />
            ))}
          </div>
        </div>
        
        {/* Description */}
        <div className="mt-4">
          <div className="flex items-center justify-between mb-1">
            <label className="text-xs text-white opacity-60">Description (icône "i")</label>
            <button
              type="button"
              onClick={() => handleAIEnhance('description')}
              disabled={aiLoading || !(newOffer.description?.trim())}
              className="text-xs px-2 py-1 rounded-lg"
              style={{
                background: aiLoading ? 'rgba(139,92,246,0.2)' : 'rgba(217,28,210,0.2)',
                border: '1px solid rgba(217,28,210,0.4)',
                color: '#D91CD2',
                cursor: aiLoading ? 'wait' : 'pointer',
                opacity: !(newOffer.description?.trim()) ? 0.4 : 1
              }}
              data-testid="ai-enhance-description"
            >
              {aiLoading ? '⏳ IA...' : '✨ Aide IA'}
            </button>
          </div>
          <textarea
            value={newOffer.description || ''}
            onChange={e => setNewOffer({ ...newOffer, description: e.target.value })}
            className="w-full px-3 py-3 rounded-lg neon-input text-sm"
            rows={5}
            maxLength={2000}
            placeholder="Description détaillée de votre offre (jusqu'à 2000 caractères)"
          />
          <p className="text-xs mt-1" style={{ color: 'rgba(255,255,255,0.4)' }}>{(newOffer.description || '').length}/2000</p>
        </div>
        
        {/* Mots-clés */}
        <div className="mt-3">
          <label className="text-xs text-white opacity-60 mb-1 block">🔍 Mots-clés (pour la recherche)</label>
          <input
            type="text"
            value={newOffer.keywords || ''}
            onChange={e => setNewOffer({ ...newOffer, keywords: e.target.value })}
            className="w-full px-3 py-2 rounded-lg neon-input text-sm"
            placeholder="session, séance, cardio, danse, afro... (séparés par virgules)"
            data-testid="offer-keywords"
          />
          <p className="text-xs mt-1" style={{ color: 'rgba(139, 92, 246, 0.6)' }}>💡 Aide les clients à trouver cette offre</p>
        </div>

        {/* v159: Cours liés à cette offre (many-to-many) */}
        {!newOffer.isProduct && courses && courses.length > 0 && (
          <div className="mt-3 p-3 rounded-lg" style={{ border: '1px solid rgba(217, 28, 210, 0.3)', background: 'rgba(217, 28, 210, 0.05)' }}>
            <label className="text-xs text-white font-semibold mb-2 block">
              📅 Cours associés à cette offre
            </label>
            <p className="text-xs mb-2" style={{ color: 'rgba(255,255,255,0.5)' }}>
              Quand un client cliquera sur cette offre, il verra uniquement ces cours.
              Laissez vide pour afficher tous vos cours.
            </p>
            <div className="max-h-48 overflow-y-auto space-y-1 pr-2" style={{ scrollbarWidth: 'thin' }}>
              {courses
                .filter(c => !c.archived && (isSuperAdmin || (c.coach_id || '').toLowerCase() === (coachEmail || '').toLowerCase()))
                .map(course => {
                  const linked = (newOffer.linked_course_ids || []).includes(course.id);
                  const weekdays = ['Dimanche','Lundi','Mardi','Mercredi','Jeudi','Vendredi','Samedi'];
                  return (
                    <label key={course.id} className="flex items-center gap-2 text-sm text-white py-1.5 px-2 rounded cursor-pointer hover:bg-white/5">
                      <input
                        type="checkbox"
                        checked={linked}
                        onChange={(e) => {
                          const current = newOffer.linked_course_ids || [];
                          const updated = e.target.checked
                            ? [...current, course.id]
                            : current.filter(id => id !== course.id);
                          setNewOffer({ ...newOffer, linked_course_ids: updated });
                        }}
                        className="w-4 h-4"
                      />
                      <span className="flex-1">
                        <span className="font-medium">{course.name || course.title || 'Cours'}</span>
                        <span className="text-white/50 text-xs ml-2">
                          {course.weekday !== undefined && weekdays[course.weekday]} • {course.time}
                        </span>
                      </span>
                    </label>
                  );
                })}
            </div>
            {(newOffer.linked_course_ids || []).length > 0 && (
              <p className="text-xs mt-2 text-pink-400">
                ✓ {(newOffer.linked_course_ids || []).length} cours lié(s)
              </p>
            )}
          </div>
        )}
        
        {/* Category & Type */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mt-3">
          <select 
            value={newOffer.category} 
            onChange={e => setNewOffer({ ...newOffer, category: e.target.value })}
            className="px-3 py-3 rounded-lg neon-input text-sm w-full"
          >
            <option value="service">🎧 Service / Cours</option>
            <option value="tshirt">👕 T-shirt</option>
            <option value="shoes">👟 Chaussures</option>
            <option value="supplement">💊 Complément</option>
            <option value="accessory">🎒 Accessoire</option>
          </select>
          <label className="flex items-center gap-2 text-white text-sm py-2">
            <input 
              type="checkbox" 
              checked={newOffer.isProduct} 
              onChange={e => setNewOffer({ ...newOffer, isProduct: e.target.checked })} 
              className="w-5 h-5"
            />
            Produit physique
          </label>
          <label className="flex items-center gap-2 text-white text-sm py-2">
            <input 
              type="checkbox" 
              checked={newOffer.visible} 
              onChange={e => setNewOffer({ ...newOffer, visible: e.target.checked })} 
              className="w-5 h-5"
            />
            Visible
          </label>
        </div>

        {/* E-Commerce Fields */}
        {newOffer.isProduct && (
          <div className="mt-3 p-3 rounded-lg border border-purple-500/30">
            <p className="text-xs text-purple-400 mb-3">📦 Paramètres produit</p>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
              <div>
                <label className="text-xs text-white opacity-60">TVA (%)</label>
                <input type="number" placeholder="7.7" value={newOffer.tva || ''} onChange={e => setNewOffer({ ...newOffer, tva: parseFloat(e.target.value) || 0 })} className="w-full px-3 py-3 rounded-lg neon-input text-sm" step="0.1" />
              </div>
              <div>
                <label className="text-xs text-white opacity-60">Frais port</label>
                <input type="number" placeholder="9.90" value={newOffer.shippingCost || ''} onChange={e => setNewOffer({ ...newOffer, shippingCost: parseFloat(e.target.value) || 0 })} className="w-full px-3 py-3 rounded-lg neon-input text-sm" step="0.1" />
              </div>
              <div>
                <label className="text-xs text-white opacity-60">Stock</label>
                <input type="number" placeholder="-1" value={newOffer.stock} onChange={e => setNewOffer({ ...newOffer, stock: parseInt(e.target.value) || -1 })} className="w-full px-3 py-3 rounded-lg neon-input text-sm" />
              </div>
            </div>
            
            {/* Variants */}
            <div className="mt-3">
              <label className="text-xs text-white opacity-60">Variantes (séparées par virgule)</label>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mt-2">
                <input 
                  type="text" 
                  placeholder="Tailles: S, M, L, XL"
                  onChange={e => setNewOffer({ 
                    ...newOffer, 
                    variants: { ...newOffer.variants, sizes: e.target.value.split(',').map(s => s.trim()).filter(s => s) }
                  })}
                  className="w-full px-3 py-3 rounded-lg neon-input text-sm"
                />
                <input 
                  type="text" 
                  placeholder="Couleurs: Noir, Blanc"
                  onChange={e => setNewOffer({ 
                    ...newOffer, 
                    variants: { ...newOffer.variants, colors: e.target.value.split(',').map(s => s.trim()).filter(s => s) }
                  })}
                  className="w-full px-3 py-3 rounded-lg neon-input text-sm"
                />
                <input 
                  type="text" 
                  placeholder="Poids: 0.5kg, 1kg"
                  onChange={e => setNewOffer({ 
                    ...newOffer, 
                    variants: { ...newOffer.variants, weights: e.target.value.split(',').map(s => s.trim()).filter(s => s) }
                  })}
                  className="w-full px-3 py-3 rounded-lg neon-input text-sm"
                />
              </div>
            </div>
          </div>
        )}
        
        <button type="submit" className="btn-primary px-6 py-3 rounded-lg mt-4 text-sm w-full">
          {editingOfferId ? '💾 Enregistrer les modifications' : '➕ Ajouter l\'offre'}
        </button>
      </form>
      )}
    </div>
  );
};

export default OffersManager;
