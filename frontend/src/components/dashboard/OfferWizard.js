// V224 — Wizard de creation/modification d'offre en 3 etapes.
// Le state est LOCAL : il ne remonte au parent qu'une fois, via onSave,
// ce qui preserve le comportement actuel d'une seule requete POST/PUT.
import React, { useState, useEffect } from 'react';
import axios from 'axios'; // V225: creation/modification des horaires depuis le wizard

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
  onEnhanceDescription,
  // V225: prop OPTIONNELLE (meme schema que onEnhanceDescription en V224).
  // Fournie, l'etape 2 affiche les horaires EDITABLES (POST/PUT /courses).
  // Absente, on retombe sur l'ancienne liste de cases a cocher, qui n'emet
  // aucune requete cours et reste donc valide sans URL d'API.
  API,
  // V226 CORRECTIF 1: prop OPTIONNELLE. Appelee avec l'id d'un cours SUPPRIME
  // en base, pour que le parent purge sa propre liste `courses`.
  // Sans elle, la prop `courses` — chargee une seule fois par CoachDashboard et
  // jamais rafraichie — continue de proposer le cours supprime dans le
  // selecteur « Ou rattacher un cours existant ». Le coach le rattache, modifie
  // un champ, enregistre : le `PUT /courses/{id}` renvoie 404, les horaires
  // echouent et l'offre n'est PAS ecrite — blocage jusqu'au rechargement.
  // Absente, repli silencieux : aucun montage existant n'est casse.
  onCoursesChanged
}) {
  const [step, setStep] = useState(1);
  const [form, setForm] = useState(initialOffer || {});
  // V224: chaine BRUTE saisie dans les champs variantes. Indispensable : sans
  // elle, la valeur affichee est derivee du tableau normalise, ce qui efface la
  // virgule a l'instant ou elle est tapee (« S, M » devenait « SM »).
  const [variantsRaw, setVariantsRaw] = useState({});
  const [aiLoading, setAiLoading] = useState(false);
  // V225: cours lies sous forme d'OBJETS complets, editables sur place.
  const [linkedCourses, setLinkedCourses] = useState([]);
  // V225: ids des cours reellement modifies par le coach. Seuls ceux-ci feront
  // l'objet d'un PUT a l'enregistrement — on n'emet pas N requetes a chaque fois.
  const [dirtyCourseIds, setDirtyCourseIds] = useState([]);
  // V225 CORRECTIF 1: ids des cours CREES PENDANT CETTE SESSION du wizard. Eux
  // seuls naissent `visible: false` et doivent donc etre bascules a
  // `visible: true` a l'enregistrement. Pour TOUT autre cours, la cle `visible`
  // n'est jamais envoyee : un horaire delibrement masque depuis CoursesManager
  // ne doit pas redevenir public parce qu'une offre liee est reenregistree.
  const [sessionCreatedCourseIds, setSessionCreatedCourseIds] = useState([]);
  // V225 REVUE FINALE: ids des cours crees par CE wizard, jamais vides tant que
  // le wizard reste ouvert. Distinct de `sessionCreatedCourseIds`, qui est vide
  // apres le premier enregistrement reussi (pour ne pas re-emettre
  // `visible: true`). Sans cet ensemble persistant, un cours tout juste cree
  // redeviendrait « lecture seule » des que l'enregistrement des horaires a
  // reussi mais que celui de l'offre a echoue — le wizard restant alors ouvert.
  const [sessionOwnedCourseIds, setSessionOwnedCourseIds] = useState([]);
  const [coursesError, setCoursesError] = useState('');
  const [coursesSaving, setCoursesSaving] = useState(false);
  const [addingCourse, setAddingCourse] = useState(false);
  // V226: id de l'horaire en cours d'ecriture (suppression / archivage /
  // publication). Sert uniquement a neutraliser les boutons de LA carte
  // concernee pendant la requete, sans figer tout le wizard.
  const [courseBusyId, setCourseBusyId] = useState(null);
  // V226: horaires ARCHIVES pendant cette session du wizard, conserves pour
  // pouvoir les restaurer immediatement. Rappel : `GET /courses` (server.py
  // l.1001) filtre `archived: {$ne: true}`, donc un horaire archive disparait
  // definitivement de la liste au prochain chargement — c'etait deja le cas
  // avec CoursesManager, dont la section « Cours archives » ne montrait elle
  // aussi que les archivages de la session en cours.
  const [sessionArchivedCourses, setSessionArchivedCourses] = useState([]);
  // V226 TACHE 8: report des trois fonctions que portait la section « Cours »,
  // desormais masquee (CoursesManager.js reste intact dans le code).
  // Etats repris a l'identique de CoursesManager.js l.24-28 : un envoi en cours
  // et un resultat, indexes par id de cours, plus le drapeau d'avis automatique.
  const [reviewRequestSending, setReviewRequestSending] = useState({});
  const [reviewRequestResult, setReviewRequestResult] = useState({});
  // V226 TACHE 8: MEME cle de stockage que CoursesManager.js l.27 et l.53
  // (`afroboost_auto_review_<coachEmail>`), pour que le reglage deja pose par le
  // coach depuis l'ancienne section soit repris tel quel — et non reinitialise.
  const [autoReviewEnabled, setAutoReviewEnabled] = useState(
    () => localStorage.getItem(`afroboost_auto_review_${coachEmail || ''}`) !== 'false'
  );

  useEffect(() => {
    if (open) {
      const offer = initialOffer || {};
      setForm(offer);
      // V225: les cours lies sont initialises DANS CE MEME effet que `form`.
      // Ailleurs, ils se desynchroniseraient a l'ouverture (form deja remplace,
      // linkedCourses encore sur l'offre precedente).
      const byId = new Map((courses || []).map(c => [c.id, c]));
      setLinkedCourses(
        (offer.linked_course_ids || [])
          .map(id => byId.get(id))
          .filter(Boolean)
          .map(c => ({ ...c }))   // copie : on n'edite jamais la prop du parent
      );
      setDirtyCourseIds([]);
      // V225 CORRECTIF 1: nouvelle ouverture = nouvelle session. Aucun cours
      // n'a encore ete cree ici, donc aucun basculement de visibilite permis.
      setSessionCreatedCourseIds([]);
      // V225 REVUE FINALE: idem pour l'ensemble « possede par ce wizard ». Une
      // nouvelle ouverture repart d'une ardoise vierge : les cours de l'offre
      // chargee sont juges par `visibleCourses` seul, comme avant.
      setSessionOwnedCourseIds([]);
      // V226: nouvelle ouverture = aucun archivage a restaurer.
      setSessionArchivedCourses([]);
      setCourseBusyId(null);
      setCoursesError('');
      // V226 TACHE 8: une nouvelle ouverture repart sans retour visuel d'envoi.
      setReviewRequestSending({});
      setReviewRequestResult({});
      // V226 TACHE 8: resynchronisation depuis le stockage. L'initialiseur de
      // useState ne s'execute qu'au MONTAGE du wizard, or celui-ci reste monte
      // en permanence (OffersManager.js l.521 le rend toujours, `open` pilotant
      // seulement le `return null`). Sans cette relecture, une valeur ecrite
      // apres le montage — ou un `coachEmail` arrive plus tard — ne serait
      // jamais reflectee.
      setAutoReviewEnabled(
        localStorage.getItem(`afroboost_auto_review_${coachEmail || ''}`) !== 'false'
      );
      // V224: pre-remplissage des chaines brutes depuis les tableaux existants.
      const raw = {};
      VARIANT_FIELDS.forEach(({ key }) => {
        const arr = offer.variants?.[key];
        if (Array.isArray(arr) && arr.length) raw[key] = arr.join(', ');
      });
      setVariantsRaw(raw);
      setStep(1);
    }
    // V225: `courses` est volontairement HORS des dependances. L'ajouter
    // reinitialiserait les horaires en cours de saisie a chaque rafraichissement
    // de la liste par le parent, effacant les modifications non enregistrees.
    // eslint-disable-next-line react-hooks/exhaustive-deps
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

  // ===== V225: edition des horaires directement dans l'etape 2 =====

  // V225: l'edition des cours n'est possible que si l'URL d'API est fournie.
  const canEditCourses = !!API;

  // V225 CORRECTIF 2: un cours lie n'est editable que s'il appartient au
  // perimetre du coach (meme filtre que `visibleCourses`, defini plus bas).
  // Une offre historique peut referencer le cours d'un autre coach (ou un
  // `bassi_default`) : il reste AFFICHE — il fait partie de l'offre — mais en
  // lecture seule, et aucun PUT n'est emis dessus.
  // V225 REVUE FINALE: un cours cree dans CETTE session du wizard appartient au
  // coach par construction (le serveur lui a assigne `coach_id` depuis
  // X-User-Email lors du POST). Il doit donc etre editable IMMEDIATEMENT.
  // Sans cette clause, `visibleCourses` — derive de la prop `courses`, etat du
  // parent charge une seule fois et jamais rafraichi apres le POST — ignore le
  // cours tout juste cree : il tombait dans la branche lecture seule, etait
  // exclu de `toPersist`, donc n'etait jamais publie (`visible` restait false)
  // tout en etant deja reference dans `linked_course_ids` de l'offre.
  const isCourseEditable = (id) =>
    sessionOwnedCourseIds.includes(id) || visibleCourses.some(c => c.id === id);

  const markDirty = (id) => setDirtyCourseIds(prev => (prev.includes(id) ? prev : [...prev, id]));

  // V225: une frappe ne touche QUE l'etat local. Rien n'est persiste avant
  // l'enregistrement du wizard.
  const setCourseField = (id, key, value) => {
    setLinkedCourses(prev => prev.map(c => (c.id === id ? { ...c, [key]: value } : c)));
    markDirty(id);
    if (coursesError) setCoursesError('');
  };

  // V225: le lieu est expose par l'API sous deux noms (`locationName` en base,
  // `location` en alias de lecture). On garde les deux alignes localement pour
  // que l'affichage reste coherent apres modification.
  const setCourseLocation = (id, value) => {
    setLinkedCourses(prev => prev.map(c => (c.id === id ? { ...c, locationName: value, location: value } : c)));
    markDirty(id);
    if (coursesError) setCoursesError('');
  };

  // V225: DELIEN — retire le cours de l'offre uniquement. Aucun DELETE, aucun
  // archivage : le cours reste intact en base.
  // V226 CORRECTIF 3: il n'est PLUS consultable dans CoursesManager, la section
  // « Cours » du dashboard etant masquee. Le recours est desormais le wizard
  // lui-meme : le cours reste renvoye par `GET /courses` et se rattache a
  // nouveau via le selecteur « Ou rattacher un cours existant » ci-dessous.
  const unlinkCourse = (id) => {
    setLinkedCourses(prev => prev.filter(c => c.id !== id));
    setDirtyCourseIds(prev => prev.filter(x => x !== id));
    setForm(prev => ({
      ...prev,
      linked_course_ids: (prev.linked_course_ids || []).filter(x => x !== id)
    }));
  };

  // V226: retire l'id de TOUS les registres locaux. Utilise par la suppression
  // et l'archivage, qui font disparaitre l'horaire de l'offre ET de la liste
  // editable — a la difference du delien, qui ne touche que le lien.
  const forgetCourse = (id) => {
    setLinkedCourses(prev => prev.filter(c => c.id !== id));
    setDirtyCourseIds(prev => prev.filter(x => x !== id));
    setSessionCreatedCourseIds(prev => prev.filter(x => x !== id));
    setSessionOwnedCourseIds(prev => prev.filter(x => x !== id));
    setForm(prev => ({
      ...prev,
      linked_course_ids: (prev.linked_course_ids || []).filter(x => x !== id)
    }));
  };

  // V226: SUPPRESSION DEFINITIVE. Reutilise `DELETE /courses/{id}` (server.py
  // l.1060), le meme endpoint que le hard delete existant : il efface le cours
  // ET ses reservations liees. Rien de nouveau cote serveur.
  // Garde-fou : `DELETE /courses/{id}` ne verifie QUE l'authentification, pas
  // la propriete. On n'expose donc le bouton que sur un horaire editable —
  // exactement la condition qui autorise deja l'edition (`isCourseEditable`) —
  // et on la revalide ici, pour qu'un appel ne puisse pas contourner le rendu.
  const deleteCourse = async (id) => {
    if (!canEditCourses || courseBusyId || !isCourseEditable(id)) return;
    const course = linkedCourses.find(c => c.id === id);
    const label = (course && course.name) ? course.name : 'cet horaire';
    if (!window.confirm(
      `Supprimer définitivement l'horaire « ${label} » ?\n\n` +
      'Le cours et ses réservations seront effacés de la base. ' +
      'Cette action est irréversible.\n\n' +
      // V226 CORRECTIF 2: un horaire peut etre rattache a PLUSIEURS offres. La
      // carte publique d'une autre offre survit (App.js l.2143-2145 filtre les
      // valeurs nulles), mais sa grille de reservation est filtree sur
      // `linked_course_ids` des qu'il est non vide (App.js l.5541-5542) : une
      // offre dont le seul horaire vient d'etre supprime devient SILENCIEUSEMENT
      // non reservable, grille de dates vide et sans message. Le wizard ne
      // recoit pas la liste des offres et ne peut donc ni detecter ni nettoyer
      // ce cas — on avertit explicitement le coach avant qu'il ne l'declenche.
      'Attention : cet horaire peut être utilisé par d\'autres offres. ' +
      'Celles-ci se retrouveraient alors sans aucune date de réservation.\n\n' +
      'Pour le retirer de l\'offre sans le supprimer, utilisez « Retirer de l\'offre ».'
    )) return;
    setCourseBusyId(id);
    setCoursesError('');
    try {
      await axios.delete(`${API}/courses/${id}`);
      forgetCourse(id);
      // V226 CORRECTIF 1: on previent le parent pour qu'il purge sa liste
      // `courses`. Repli silencieux si la prop n'est pas fournie.
      if (typeof onCoursesChanged === 'function') onCoursesChanged(id);
    } catch (err) {
      console.error('[V226] Suppression de l\'horaire echouee:', err);
      setCoursesError('Impossible de supprimer l\'horaire. Vérifiez votre connexion et réessayez.');
    } finally {
      setCourseBusyId(null);
    }
  };

  // V226: ARCHIVAGE. Reutilise `PUT /courses/{id}/archive` (server.py l.1051),
  // exactement l'appel de `archiveCourse` dans CoursesManager.js l.93.
  // Meme garde-fou de propriete que la suppression.
  const archiveCourse = async (id) => {
    if (!canEditCourses || courseBusyId || !isCourseEditable(id)) return;
    const course = linkedCourses.find(c => c.id === id);
    const label = (course && course.name) ? course.name : 'cet horaire';
    if (!window.confirm(
      `Archiver l'horaire « ${label} » ?\n\n` +
      'Il sera masqué et retiré de cette offre. Vous pourrez le restaurer ' +
      'tant que vous n\'aurez pas fermé cette fenêtre.'
    )) return;
    setCourseBusyId(id);
    setCoursesError('');
    try {
      await axios.put(`${API}/courses/${id}/archive`);
      if (course) setSessionArchivedCourses(prev => [...prev, { ...course, archived: true }]);
      forgetCourse(id);
    } catch (err) {
      console.error('[V226] Archivage de l\'horaire echoue:', err);
      setCoursesError('Impossible d\'archiver l\'horaire. Vérifiez votre connexion et réessayez.');
    } finally {
      setCourseBusyId(null);
    }
  };

  // V226: RESTAURATION d'un horaire archive dans cette session. Reutilise
  // `PUT /courses/{id}` avec `archived: false`, comme `restoreCourse`
  // (CoursesManager.js l.103). On ne renvoie que la cle `archived` : le $set
  // partiel du serveur laisse tout le reste intact.
  const restoreCourse = async (course) => {
    // V226 CORRECTIF 5: symetrie defensive avec les trois autres handlers, qui
    // revalident tous la propriete en tete. Non exploitable aujourd'hui — un
    // horaire n'entre dans `sessionArchivedCourses` qu'apres avoir passe la
    // meme garde dans `archiveCourse` — mais la rupture de symetrie egarerait
    // une prochaine intervention.
    // NB : on NE peut PAS se contenter de `isCourseEditable(course.id)`.
    // `archiveCourse` appelle `forgetCourse`, qui purge `sessionOwnedCourseIds` :
    // un horaire CREE puis archive dans cette meme session n'y figure donc plus
    // et, absent de `visibleCourses` (prop parent jamais rafraichie), serait
    // declare non editable — la restauration deviendrait impossible. La
    // presence dans `sessionArchivedCourses` est en soi la preuve que la garde
    // de propriete a deja ete franchie a l'archivage.
    const wasArchivedHere = sessionArchivedCourses.some(c => c.id === course.id);
    if (!canEditCourses || courseBusyId) return;
    if (!wasArchivedHere && !isCourseEditable(course.id)) return;
    setCourseBusyId(course.id);
    setCoursesError('');
    try {
      await axios.put(`${API}/courses/${course.id}`, { archived: false });
      setSessionArchivedCourses(prev => prev.filter(c => c.id !== course.id));
      // L'horaire redevient editable dans cette session : il a ete cree ou
      // reconnu editable avant l'archivage, donc il appartient bien au coach.
      setSessionOwnedCourseIds(prev => (prev.includes(course.id) ? prev : [...prev, course.id]));
      setLinkedCourses(prev => (prev.some(c => c.id === course.id)
        ? prev
        : [...prev, { ...course, archived: false }]));
      setForm(prev => {
        const ids = prev.linked_course_ids || [];
        return ids.includes(course.id) ? prev : { ...prev, linked_course_ids: [...ids, course.id] };
      });
    } catch (err) {
      console.error('[V226] Restauration de l\'horaire echouee:', err);
      setCoursesError('Impossible de restaurer l\'horaire. Vérifiez votre connexion et réessayez.');
    } finally {
      setCourseBusyId(null);
    }
  };

  // V226: PUBLICATION / MASQUAGE d'un horaire, ecrit IMMEDIATEMENT.
  // C'est le seul recours pour un horaire reste en `visible: false` apres une
  // session de wizard abandonnee (correctif V225) : `GET /courses` le renvoie
  // toujours (seul `archived` est filtre), il apparait donc bien dans la liste
  // avec son badge « masqué » et ce bouton le republie.
  // L'ecriture est immediate et non differee a `handleSave` : `buildCoursePayload`
  // n'emet `visible` que pour les cours crees dans CETTE session, et ce choix
  // V225 — ne jamais republier un horaire volontairement masque au dos du coach —
  // ne doit pas etre contourne. Ici c'est le coach qui le demande explicitement.
  const setCourseVisibility = async (id, nextVisible) => {
    if (!canEditCourses || courseBusyId || !isCourseEditable(id)) return;
    setCourseBusyId(id);
    setCoursesError('');
    try {
      await axios.put(`${API}/courses/${id}`, { visible: nextVisible });
      setLinkedCourses(prev => prev.map(c => (c.id === id ? { ...c, visible: nextVisible } : c)));
    } catch (err) {
      console.error('[V226] Changement de visibilite echoue:', err);
      setCoursesError('Impossible de changer la visibilité de l\'horaire. Réessayez.');
    } finally {
      setCourseBusyId(null);
    }
  };

  // V226 TACHE 8: DEMANDE D'AVIS MANUELLE. Report de `sendReviewRequest`
  // (CoursesManager.js l.31-47), seul appelant de `POST /api/reviews/request`
  // dans toute l'interface — masquer la section « Cours » rendait l'endpoint
  // (server.py l.14208) injoignable. Payload recopie a l'identique :
  // `{ coach_email, course_id, course_name }`, retour lu sur `res.data.sent_count`.
  // Le serveur exige `coach_email` (400 sinon, server.py l.14216) : le bouton
  // n'est donc rendu que si la prop `coachEmail` est fournie.
  // Garde de propriete identique a `deleteCourse` / `setCourseVisibility` :
  // l'action n'est proposee QUE sur un horaire editable, et la condition est
  // revalidee ici pour qu'un appel ne puisse pas contourner le rendu.
  const sendReviewRequest = async (id) => {
    if (!canEditCourses || !coachEmail || !isCourseEditable(id)) return;
    if (reviewRequestSending[id]) return;
    const course = linkedCourses.find(c => c.id === id);
    if (!course) return;
    setReviewRequestSending(prev => ({ ...prev, [id]: true }));
    try {
      const res = await axios.post(`${API}/reviews/request`, {
        coach_email: coachEmail,
        course_id: id,
        course_name: course.name
      });
      setReviewRequestResult(prev => ({ ...prev, [id]: res.data.sent_count }));
      setTimeout(() => setReviewRequestResult(prev => ({ ...prev, [id]: null })), 4000);
    } catch (err) {
      console.error('[V226] Envoi de la demande d\'avis echoue:', err);
      setReviewRequestResult(prev => ({ ...prev, [id]: -1 }));
      setTimeout(() => setReviewRequestResult(prev => ({ ...prev, [id]: null })), 3000);
    }
    setReviewRequestSending(prev => ({ ...prev, [id]: false }));
  };

  // V226 TACHE 8: AVIS AUTOMATIQUE. Report de `toggleAutoReview`
  // (CoursesManager.js l.50-54). A NOTER, verifie et non suppose : ce reglage
  // n'emet AUCUNE requete — il n'ecrit que `localStorage`. Le piege des valeurs
  // `None` de `PUT /courses/{id}` (server.py l.1045) ne s'applique donc pas
  // ici : il n'y a pas de payload. Inventer un PUT `auto_review` aurait cree un
  // champ que rien ne lit cote serveur. On reprend le comportement exact, cle
  // de stockage comprise, pour que le reglage existant du coach soit conserve.
  const toggleAutoReview = () => {
    const newVal = !autoReviewEnabled;
    setAutoReviewEnabled(newVal);
    localStorage.setItem(`afroboost_auto_review_${coachEmail || ''}`, newVal.toString());
  };

  // V225: lie un cours DEJA existant (remplace l'usage « cocher une case »).
  const linkExistingCourse = (id) => {
    if (!id) return;
    const course = visibleCourses.find(c => c.id === id);
    if (!course) return;
    setLinkedCourses(prev => (prev.some(c => c.id === id) ? prev : [...prev, { ...course }]));
    setForm(prev => {
      const ids = prev.linked_course_ids || [];
      return ids.includes(id) ? prev : { ...prev, linked_course_ids: [...ids, id] };
    });
  };

  // V225: creation d'un horaire. `locationName` est REQUIS par CourseCreate
  // (api/server.py l.353-363) : on l'envoie meme vide, sinon la requete est
  // rejetee. Aucun `coach_id` n'est transmis : le serveur l'assigne depuis
  // l'en-tete X-User-Email (server.py l.1026-1029), comportement voulu.
  // V225 CORRECTIF 1: le cours nait `visible: false`. Le POST a lieu au clic
  // (il faut un id pour editer le cours), mais un horaire cree puis abandonne
  // — « Annuler », onglet ferme, crash — ne doit JAMAIS apparaitre sur la
  // vitrine publique. Le passage a `visible: true` se fait uniquement dans
  // `buildCoursePayload`, donc au moment de l'enregistrement effectif.
  const addCourse = async () => {
    if (!canEditCourses || addingCourse) return;
    setAddingCourse(true);
    setCoursesError('');
    try {
      const res = await axios.post(`${API}/courses`, {
        name: 'Nouveau cours',
        weekday: 3,
        time: '18:30',
        locationName: '',
        mapsUrl: '',
        visible: false
      });
      const created = res.data;
      if (!created || !created.id) throw new Error('Reponse invalide');
      // V225 CORRECTIF 1: on trace l'id comme « cree dans cette session ». Seul
      // ce marqueur autorisera `buildCoursePayload` a poser `visible: true`.
      setSessionCreatedCourseIds(prev => (prev.includes(created.id) ? prev : [...prev, created.id]));
      // V225 REVUE FINALE: marque aussi le cours comme « possede par ce wizard »,
      // ce qui le rend editable sans attendre un rafraichissement de la prop
      // `courses` du parent (qui n'a jamais lieu).
      setSessionOwnedCourseIds(prev => (prev.includes(created.id) ? prev : [...prev, created.id]));
      setLinkedCourses(prev => [...prev, { ...created }]);
      setForm(prev => ({
        ...prev,
        linked_course_ids: [...(prev.linked_course_ids || []), created.id]
      }));
    } catch (err) {
      console.error('[V225] Creation de cours echouee:', err);
      setCoursesError('Impossible de créer l\'horaire. Vérifiez votre connexion et réessayez.');
    } finally {
      setAddingCourse(false);
    }
  };

  // V226 TACHE 8: DUPLICATION d'un horaire. Report de `duplicateCourse`
  // (CoursesManager.js l.72-88) : meme endpoint `POST /courses`, memes champs
  // recopies depuis la source (`name` suffixe « (copie) », `weekday`, `time`,
  // `locationName`, `mapsUrl`, `archived: false`).
  // UNE SEULE difference, imposee par le correctif V225 : le cours nait
  // `visible: false` et NON `visible: true` comme dans CoursesManager. Un
  // horaire cree depuis le wizard puis abandonne — « Annuler », onglet ferme,
  // crash — ne doit jamais atteindre la vitrine publique. La publication est
  // deleguee a `buildCoursePayload`, qui pose `visible: true` au moment de
  // l'enregistrement effectif, pour les seuls ids de `sessionCreatedCourseIds`.
  // C'est exactement le chemin de `addCourse` ci-dessus, dont ce handler ne
  // differe que par la provenance des valeurs (la carte source, pas des
  // valeurs par defaut).
  // Garde de propriete : on ne duplique que depuis un horaire editable, comme
  // pour l'edition et la suppression, condition revalidee en tete du handler.
  // La liste `courses` du parent n'est PAS notifiee, et c'est deliberé :
  // `onCoursesChanged` est cable en PURGE (`filter(c => c.id !== courseId)`,
  // OffersManager.js l.540-542) et ne sait pas ajouter. Le cours duplique est
  // rendu editable immediatement par `sessionOwnedCourseIds`, sans dependre de
  // la prop parent — meme mecanique que pour `addCourse`, qui ne notifie pas
  // davantage.
  const duplicateCourse = async (id) => {
    if (!canEditCourses || addingCourse || courseBusyId || !isCourseEditable(id)) return;
    const source = linkedCourses.find(c => c.id === id);
    if (!source) return;
    setCourseBusyId(id);
    setCoursesError('');
    try {
      const res = await axios.post(`${API}/courses`, {
        name: `${(source.name || 'Cours')} (copie)`,
        weekday: Number.isInteger(source.weekday) ? source.weekday : parseInt(source.weekday, 10) || 0,
        time: source.time || '',
        locationName: source.locationName || source.location || '',
        mapsUrl: source.mapsUrl || '',
        visible: false,
        archived: false
      });
      const created = res.data;
      if (!created || !created.id) throw new Error('Reponse invalide');
      setSessionCreatedCourseIds(prev => (prev.includes(created.id) ? prev : [...prev, created.id]));
      setSessionOwnedCourseIds(prev => (prev.includes(created.id) ? prev : [...prev, created.id]));
      setLinkedCourses(prev => [...prev, { ...created }]);
      setForm(prev => ({
        ...prev,
        linked_course_ids: [...(prev.linked_course_ids || []), created.id]
      }));
    } catch (err) {
      console.error('[V226] Duplication de l\'horaire echouee:', err);
      setCoursesError('Impossible de dupliquer l\'horaire. Vérifiez votre connexion et réessayez.');
    } finally {
      setCourseBusyId(null);
    }
  };

  // V225: PIEGE DOCUMENTE — PUT /courses/{id} fusionne avec
  // `{k: v for k, v in course_update.items() if v is not None}` (server.py
  // l.1045). Une valeur `null`/`undefined` serait donc IGNOREE et l'effacement
  // d'un champ silencieusement perdu. On normalise tout en chaine : un champ
  // vide part en chaine VIDE, jamais en null.
  // V225 CORRECTIF 1: seul un cours CREE DANS CETTE SESSION du wizard (donc ne
  // en `visible: false`) recoit `visible: true`. Pour tout autre cours, la cle
  // `visible` est totalement ABSENTE du payload : le PUT fait un `$set` partiel
  // (server.py l.1045), donc une cle absente laisse la valeur en base intacte.
  // C'est le point crucial — un horaire delibrement masque par le coach reste
  // masque, meme si l'offre qui le reference est reenregistree. On ne decide
  // jamais a la place du coach.
  // V226 CORRECTIF 3: ce masquage se pilote maintenant depuis le wizard, via le
  // bouton « Masquer » / « 👁️ Republier » de chaque carte d'horaire (la section
  // « Cours » du dashboard, qui l'hebergeait, est masquee).
  // Aucune autre cle n'est ajoutee : le $set partiel du serveur preserve
  // `playlist`, `audio_tracks` et `coach_id` des cours existants.
  const buildCoursePayload = (c) => {
    const payload = {
      name: (c.name || '').trim(),
      weekday: Number.isInteger(c.weekday) ? c.weekday : parseInt(c.weekday, 10) || 0,
      time: c.time || '',
      locationName: c.locationName || '',
      location: c.locationName || '',
      mapsUrl: c.mapsUrl || ''
    };
    if (sessionCreatedCourseIds.includes(c.id)) payload.visible = true;
    return payload;
  };

  const handleSave = async () => {
    // Seule contrainte bloquante : le nom. Le backend le type `name: str`
    // (non optionnel) et rejetterait la requete.
    if (!form.name || !form.name.trim()) {
      setStep(1);
      alert('Le nom de l\'offre est obligatoire');
      return;
    }

    // V225: persistance des horaires MODIFIES uniquement, avant de remonter
    // l'offre au parent (qui, lui, garde sa requete unique POST/PUT).
    // V225 CORRECTIF 1: on y ajoute les horaires CREES DANS CETTE SESSION, pour
    // qu'ils deviennent publics au moment ou l'offre est reellement enregistree,
    // et a ce moment-la seulement. On n'utilise PLUS `!c.visible` comme critere :
    // un horaire masque volontairement par le coach serait republie contre son
    // gre. Effet assume : un horaire cree lors d'une session ANTERIEURE restee
    // inachevee demeure invisible.
    // V226 CORRECTIF 3: le coach le republie depuis CE wizard — `GET /courses`
    // le renvoie toujours (seul `archived` y est filtre), il se rattache via
    // « Ou rattacher un cours existant » et son bouton « 👁️ Republier » le rend
    // public. CoursesManager n'est plus une voie de recours : la section
    // « Cours » du dashboard est masquee.
    // V225 CORRECTIF 2 (v224): on n'ecrit jamais un cours hors du perimetre du coach.
    const toPersist = canEditCourses
      ? linkedCourses.filter(c => isCourseEditable(c.id) && (dirtyCourseIds.includes(c.id) || sessionCreatedCourseIds.includes(c.id)))
      : [];
    if (toPersist.length) {
      const unnamed = toPersist.find(c => !(c.name || '').trim());
      if (unnamed) {
        setStep(2);
        setCoursesError('Chaque horaire doit porter un nom.');
        return;
      }
      setCoursesSaving(true);
      try {
        await Promise.all(
          toPersist.map(c => axios.put(`${API}/courses/${c.id}`, buildCoursePayload(c)))
        );
        // V225 CORRECTIF 1: l'etat local suit le basculement cote serveur, pour
        // qu'un second enregistrement ne re-emette pas les memes PUT. On ne
        // touche `visible` QUE pour les cours crees dans cette session : pour
        // les autres, la valeur en base n'a pas ete modifiee, donc l'etat local
        // ne doit rien inventer.
        setLinkedCourses(prev => prev.map(c => (
          sessionCreatedCourseIds.includes(c.id) && toPersist.some(p => p.id === c.id)
            ? { ...c, visible: true }
            : c
        )));
        setDirtyCourseIds([]);
        // V225 CORRECTIF 1: le basculement a eu lieu, ces cours sont desormais
        // des cours ordinaires. Les oublier evite de re-emettre `visible: true`
        // a chaque enregistrement ulterieur.
        setSessionCreatedCourseIds([]);
      } catch (err) {
        // V225: on NE ferme PAS le wizard en silence — meme principe que
        // handleWizardSave (OffersManager.js) qui ne ferme que si l'offre a
        // bien ete enregistree. La saisie reste en place et reste reessayable.
        console.error('[V225] Enregistrement des horaires echoue:', err);
        setStep(2);
        setCoursesError('Les horaires n\'ont pas pu être enregistrés. L\'offre n\'a pas été sauvegardée — réessayez.');
        setCoursesSaving(false);
        return;
      }
      setCoursesSaving(false);
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

      {/* V225: Cours lies — EDITABLES sur place (nom, jour, heure, lieu, Maps).
          Le coach n'a plus a quitter le wizard pour toucher un horaire. */}
      {!form.isProduct && canEditCourses && (
        <div className="p-3 rounded-lg" style={{ border: '1px solid rgba(217,28,210,0.3)', background: 'rgba(217,28,210,0.05)' }}>
          <label className="text-xs text-white font-semibold mb-2 block">
            📅 Horaires de cette offre
          </label>
          <p className="text-xs mb-3" style={{ color: 'rgba(255,255,255,0.5)' }}>
            Quand un client cliquera sur cette offre, il verra uniquement ces horaires.
            Laissez vide pour afficher tous vos cours.
          </p>

          {/* V226 TACHE 8: « Demande d'avis automatique ». Report du toggle de
              CoursesManager.js l.122-135. Il est propre au COACH, pas a un
              horaire : il reste donc UNE seule fois en tete de section, et non
              repete sur chaque carte. Rendu avec la case a cocher du wizard
              plutot qu'avec la classe `switch` du dashboard, par coherence avec
              les autres bascules de cette etape (« Prolonger automatiquement »). */}
          <label
            className="flex items-center gap-3 mb-3 p-2 rounded-lg cursor-pointer"
            style={{ background: '#0a0a0f', border: '1px solid #333', borderRadius: '12px' }}
          >
            <input
              type="checkbox"
              checked={autoReviewEnabled}
              onChange={toggleAutoReview}
              className="w-4 h-4 v224-input"
              style={{ accentColor: PINK }}
              data-testid="auto-review-toggle"
            />
            <span className="flex-1">
              <span className="block text-xs text-white font-semibold">⭐ Demande d'avis automatique</span>
              <span className="block text-xs" style={HINT_STYLE}>
                Après chaque cours, inviter les participants à laisser un avis.
              </span>
            </span>
          </label>

          {coursesError && (
            <p className="text-xs mb-3 p-2 rounded" style={{ background: 'rgba(249,115,22,0.12)', color: '#f97316' }}>
              ⚠️ {coursesError}
            </p>
          )}

          <div className="space-y-3">
            {/* V225 CORRECTIF 2: un cours hors du perimetre du coach reste
                AFFICHE (il fait partie de l'offre, le masquer deroute) mais en
                LECTURE SEULE. Il n'est pas retire de `linked_course_ids`. */}
            {/* V225 CORRECTIF 2: une SEULE passe sur `linkedCourses`, dans son
                ordre d'origine. L'ancien rendu separait les cartes en deux
                listes (lecture seule puis editables), ce qui reordonnait
                l'affichage des qu'une offre melangeait les deux cas. Le
                caractere editable se decide desormais carte par carte. */}
            {linkedCourses.map(course => (!isCourseEditable(course.id) ? (
              <div
                key={course.id}
                className="p-3 rounded-xl"
                style={{ background: '#0a0a0f', border: '1px solid #333', borderRadius: '12px', opacity: 0.75 }}
              >
                <div className="flex items-start justify-between gap-2">
                  <span className="text-sm text-white">
                    <span className="font-medium">{course.name || course.title || 'Cours'}</span>
                    <span className="text-white/50 text-xs ml-2">
                      {Number.isInteger(course.weekday) ? WEEKDAYS[course.weekday] : ''}
                      {course.time ? ` • ${course.time}` : ''}
                    </span>
                  </span>
                  <button
                    type="button"
                    onClick={() => unlinkCourse(course.id)}
                    title="Retirer cet horaire de l'offre (le cours n'est pas supprimé)"
                    aria-label="Retirer cet horaire de l'offre"
                    className="text-sm leading-none px-2 py-2 rounded-lg"
                    style={{ color: 'rgba(255,255,255,0.5)', background: 'none', border: '1px solid #333', cursor: 'pointer' }}
                  >
                    ✕
                  </button>
                </div>
                {(course.locationName || course.location) && (
                  <p className="text-xs mt-1" style={HINT_STYLE}>
                    📍 {course.locationName || course.location}
                  </p>
                )}
                {/* V226: le badge « masqué » s'affiche sur TOUTE carte dont
                    `visible === false`, y compris celle-ci. Pas de bouton de
                    republication en revanche : l'horaire n'appartient pas au
                    coach, seul son proprietaire peut le republier. */}
                {course.visible === false && (
                  <p className="text-xs mt-2">
                    <span
                      className="px-2 py-1 rounded-lg"
                      style={{ background: 'rgba(249,115,22,0.15)', color: '#f97316' }}
                    >
                      🚫 Masqué
                    </span>
                  </p>
                )}
                <p className="text-xs mt-2" style={HINT_STYLE}>
                  🔒 Horaire géré par un autre compte — lecture seule.
                </p>
              </div>
            ) : (
              <div
                key={course.id}
                className="p-3 rounded-xl"
                style={{ background: '#0a0a0f', border: '1px solid #333', borderRadius: '12px' }}
              >
                <div className="flex items-start gap-2">
                  <input
                    type="text"
                    value={course.name || ''}
                    onChange={(e) => setCourseField(course.id, 'name', e.target.value)}
                    placeholder="Nom du cours"
                    style={INPUT_STYLE}
                    className="text-sm v224-input"
                  />
                  {/* V225: DELIE seulement. Le cours n'est jamais supprime en base.
                      V226 CORRECTIF 3: pour le remettre dans l'offre, le
                      selecteur « Ou rattacher un cours existant » en bas de
                      cette etape — et non CoursesManager, dont la section
                      « Cours » n'est plus affichee. */}
                  <button
                    type="button"
                    onClick={() => unlinkCourse(course.id)}
                    title="Retirer cet horaire de l'offre (le cours n'est pas supprimé)"
                    aria-label="Retirer cet horaire de l'offre"
                    className="text-sm leading-none px-2 py-2 rounded-lg"
                    style={{ color: 'rgba(255,255,255,0.5)', background: 'none', border: '1px solid #333', cursor: 'pointer' }}
                  >
                    ✕
                  </button>
                </div>

                <div className="grid grid-cols-2 gap-2 mt-2">
                  <select
                    value={Number.isInteger(course.weekday) ? course.weekday : 0}
                    onChange={(e) => setCourseField(course.id, 'weekday', parseInt(e.target.value, 10))}
                    style={INPUT_STYLE}
                    className="text-sm v224-input"
                  >
                    {WEEKDAYS.map((d, i) => (
                      <option key={i} value={i}>{d}</option>
                    ))}
                  </select>
                  <input
                    type="time"
                    value={course.time || ''}
                    onChange={(e) => setCourseField(course.id, 'time', e.target.value)}
                    style={INPUT_STYLE}
                    className="text-sm v224-input"
                  />
                </div>

                <input
                  type="text"
                  value={course.locationName || course.location || ''}
                  onChange={(e) => setCourseLocation(course.id, e.target.value)}
                  placeholder="📍 Lieu (ex: Rue des Vallangines 97, Neuchâtel)"
                  style={INPUT_STYLE}
                  className="text-sm v224-input mt-2"
                />
                <input
                  type="url"
                  value={course.mapsUrl || ''}
                  onChange={(e) => setCourseField(course.id, 'mapsUrl', e.target.value)}
                  placeholder="🗺 Lien Google Maps (optionnel)"
                  style={INPUT_STYLE}
                  className="text-sm v224-input mt-2"
                />

                {/* V226: etat de publication de l'horaire.
                    Un horaire cree dans CETTE session est publie automatiquement
                    a l'enregistrement (V225) : on n'affiche donc pas de bouton,
                    pour ne pas court-circuiter ce garde-fou.
                    Pour TOUT autre horaire, `visible === false` affiche le badge
                    « masqué » et le bouton de republication — c'est le seul
                    recours pour un horaire laisse masque par une session
                    abandonnee, une fois la section « Cours » retiree. */}
                <div className="flex items-center justify-between gap-2 mt-3">
                  {sessionCreatedCourseIds.includes(course.id) ? (
                    <span className="text-xs" style={HINT_STYLE}>
                      🕓 Sera publié à l'enregistrement de l'offre
                    </span>
                  ) : (
                    <>
                      <span
                        className="text-xs px-2 py-1 rounded-lg"
                        style={course.visible === false
                          ? { background: 'rgba(249,115,22,0.15)', color: '#f97316' }
                          : { background: 'rgba(34,197,94,0.12)', color: '#22c55e' }}
                      >
                        {course.visible === false ? '🚫 Masqué' : '👁️ Visible'}
                      </span>
                      <button
                        type="button"
                        onClick={() => setCourseVisibility(course.id, course.visible === false)}
                        disabled={courseBusyId === course.id}
                        title={course.visible === false
                          ? 'Rendre cet horaire visible sur la vitrine publique'
                          : 'Masquer cet horaire de la vitrine publique (il reste dans l\'offre)'}
                        className="text-xs px-3 py-1 rounded-lg"
                        style={{
                          background: 'none',
                          border: `1px solid ${course.visible === false ? PINK : '#333'}`,
                          color: course.visible === false ? PINK : 'rgba(255,255,255,0.6)',
                          cursor: courseBusyId === course.id ? 'wait' : 'pointer',
                          opacity: courseBusyId === course.id ? 0.5 : 1
                        }}
                        data-testid={`course-visibility-${course.id}`}
                      >
                        {course.visible === false ? '👁️ Republier' : 'Masquer'}
                      </button>
                    </>
                  )}
                </div>

                {/* V226 TACHE 8: actions NON destructives de l'horaire —
                    duplication et demande d'avis. Regroupees dans leur propre
                    rangee, entre la publication (au-dessus) et les actions
                    destructives (en dessous), pour que l'etape 2 reste lisible
                    malgre le nombre de boutons par carte. */}
                <div className="flex items-center gap-2 flex-wrap mt-3">
                  <button
                    type="button"
                    onClick={() => duplicateCourse(course.id)}
                    disabled={courseBusyId === course.id || addingCourse}
                    title="Créer une copie de cet horaire et la rattacher à cette offre"
                    className="text-xs px-3 py-1.5 rounded-lg"
                    style={{
                      background: 'none',
                      border: '1px solid rgba(139,92,246,0.4)',
                      color: 'rgba(139,92,246,0.9)',
                      cursor: (courseBusyId === course.id || addingCourse) ? 'wait' : 'pointer',
                      opacity: (courseBusyId === course.id || addingCourse) ? 0.5 : 1
                    }}
                    data-testid={`course-duplicate-${course.id}`}
                  >
                    ⧉ Dupliquer
                  </button>
                  {/* V226 TACHE 8: sans `coachEmail`, le serveur repondrait 400
                      (« coach_email requis », server.py l.14216) : on n'affiche
                      pas un bouton qui ne peut qu'echouer. */}
                  {coachEmail && (
                    <button
                      type="button"
                      onClick={() => sendReviewRequest(course.id)}
                      disabled={!!reviewRequestSending[course.id]}
                      title="Inviter vos abonnés actifs à laisser un avis sur ce cours"
                      className="text-xs px-3 py-1.5 rounded-lg"
                      style={{
                        background: 'rgba(217,28,210,0.1)',
                        border: '1px solid rgba(217,28,210,0.3)',
                        color: PINK,
                        cursor: reviewRequestSending[course.id] ? 'wait' : 'pointer',
                        opacity: reviewRequestSending[course.id] ? 0.6 : 1
                      }}
                      data-testid={`review-request-${course.id}`}
                    >
                      {reviewRequestSending[course.id] ? '⏳' : '⭐'} Demander un avis
                    </button>
                  )}
                  {/* V226 TACHE 8: retour visuel repris de CoursesManager.js
                      l.290-296 — nombre d'envois en vert, `-1` en erreur rouge. */}
                  {reviewRequestResult[course.id] !== null && reviewRequestResult[course.id] !== undefined && (
                    <span
                      className="text-xs"
                      style={{ color: reviewRequestResult[course.id] >= 0 ? '#22c55e' : '#ef4444' }}
                    >
                      {reviewRequestResult[course.id] >= 0
                        ? `✅ Envoyé à ${reviewRequestResult[course.id]} abonné${reviewRequestResult[course.id] > 1 ? 's' : ''}`
                        : '❌ Erreur'}
                    </span>
                  )}
                </div>

                {/* V226: actions destructives, separees visuellement du reste de
                    la carte. Le ✕ ci-dessus RETIRE de l'offre (aucun effet en
                    base) ; ces deux boutons-ci touchent la base. */}
                <div className="mt-3 pt-2" style={{ borderTop: '1px solid #333' }}>
                  <p className="text-xs mb-2" style={HINT_STYLE}>
                    ✕ retire l'horaire de cette offre — le cours reste en base.
                  </p>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => unlinkCourse(course.id)}
                      disabled={courseBusyId === course.id}
                      className="text-xs px-3 py-1.5 rounded-lg"
                      style={{
                        background: 'none',
                        border: '1px solid #333',
                        color: 'rgba(255,255,255,0.6)',
                        cursor: courseBusyId === course.id ? 'wait' : 'pointer',
                        // V226 CORRECTIF 5: alignement sur les deux autres
                        // boutons de la rangee, qui grisent deja leur etat
                        // desactive.
                        opacity: courseBusyId === course.id ? 0.5 : 1
                      }}
                      data-testid={`course-unlink-${course.id}`}
                    >
                      ✕ Retirer de l'offre
                    </button>
                    {/* V226 CORRECTIF 4: bouton « Archiver » NON RENDU.
                        `GET /courses` (server.py l.1001) filtre
                        `archived: {$ne: true}` : un horaire archive disparait
                        sans retour des la fermeture du wizard, la fenetre de
                        recuperation se limitant a la session en cours. Le
                        bouton « Masquer » ci-dessus couvre le meme besoin de
                        facon pleinement REVERSIBLE (l'horaire reste dans la
                        liste, avec son badge et son bouton « Republier »).
                        Le handler `archiveCourse` et le bloc de restauration
                        sont CONSERVES tels quels, en vue d'une reactivation
                        eventuelle de ce bouton — et non parce qu'ils serviraient
                        encore. Ils sont aujourd'hui inatteignables :
                        `sessionArchivedCourses` est remis a `[]` a CHAQUE
                        ouverture du wizard, et son unique alimentateur est
                        `archiveCourse`, que plus rien n'appelle. Rendre ce
                        bouton a nouveau suffit a les remettre en service. */}
                    {false && (
                    <button
                      type="button"
                      onClick={() => archiveCourse(course.id)}
                      disabled={courseBusyId === course.id}
                      title="Archiver cet horaire : il est masqué et retiré de l'offre"
                      className="text-xs px-3 py-1.5 rounded-lg"
                      style={{
                        background: 'none',
                        border: '1px solid rgba(249,115,22,0.4)',
                        color: '#f97316',
                        cursor: courseBusyId === course.id ? 'wait' : 'pointer',
                        opacity: courseBusyId === course.id ? 0.5 : 1
                      }}
                      data-testid={`course-archive-${course.id}`}
                    >
                      📁 Archiver
                    </button>
                    )}
                    <button
                      type="button"
                      onClick={() => deleteCourse(course.id)}
                      disabled={courseBusyId === course.id}
                      title="Supprimer définitivement cet horaire de la base"
                      className="text-xs px-3 py-1.5 rounded-lg"
                      style={{
                        background: 'none',
                        border: '1px solid rgba(239,68,68,0.4)',
                        color: '#ef4444',
                        cursor: courseBusyId === course.id ? 'wait' : 'pointer',
                        opacity: courseBusyId === course.id ? 0.5 : 1
                      }}
                      data-testid={`course-delete-${course.id}`}
                    >
                      🗑 Supprimer l'horaire
                    </button>
                  </div>
                </div>
              </div>
            )))}
          </div>

          {/* V226: horaires archives PENDANT cette session, restaurables d'un
              clic. Sans ce bloc, l'archivage depuis le wizard serait sans
              retour possible — le meme piege que la section « Cours » comblait
              jusqu'ici (CoursesManager.js l.369-390). */}
          {sessionArchivedCourses.length > 0 && (
            <div className="mt-3 pt-3" style={{ borderTop: '1px solid #333' }}>
              <p className="text-xs mb-2" style={{ color: '#f97316' }}>
                📁 Archivés dans cette session ({sessionArchivedCourses.length})
              </p>
              <div className="space-y-2">
                {sessionArchivedCourses.map(course => (
                  <div
                    key={course.id}
                    className="flex items-center justify-between gap-2 p-2 rounded-xl"
                    style={{ background: '#0a0a0f', border: '1px solid rgba(249,115,22,0.3)', borderRadius: '12px' }}
                  >
                    <span className="text-xs text-white">
                      {course.name || 'Cours'}
                      <span className="text-white/50 ml-2">
                        {Number.isInteger(course.weekday) ? WEEKDAYS[course.weekday] : ''}
                        {course.time ? ` • ${course.time}` : ''}
                      </span>
                    </span>
                    <button
                      type="button"
                      onClick={() => restoreCourse(course)}
                      disabled={courseBusyId === course.id}
                      className="text-xs px-3 py-1 rounded-lg whitespace-nowrap"
                      style={{
                        background: 'none',
                        border: '1px solid rgba(34,197,94,0.4)',
                        color: '#22c55e',
                        cursor: courseBusyId === course.id ? 'wait' : 'pointer',
                        opacity: courseBusyId === course.id ? 0.5 : 1
                      }}
                      data-testid={`course-restore-${course.id}`}
                    >
                      ↩️ Restaurer
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}

          <button
            type="button"
            onClick={addCourse}
            disabled={addingCourse}
            className="w-full text-sm py-3 rounded-xl mt-3"
            style={{
              background: 'none',
              border: '1px dashed rgba(217,28,210,0.5)',
              borderRadius: '12px',
              color: PINK,
              cursor: addingCourse ? 'wait' : 'pointer'
            }}
            data-testid="add-course-schedule"
          >
            {addingCourse ? '⏳ Création...' : '+ Ajouter un horaire'}
          </button>

          {/* V225: on conserve la possibilite de rattacher un cours DEJA existant,
              qu'assuraient les anciennes cases a cocher — sinon un horaire delie
              par erreur, ou partage entre deux offres, deviendrait inatteignable. */}
          {visibleCourses.some(c => !linkedCourses.some(lc => lc.id === c.id)) && (
            <div className="mt-3">
              <label className="block text-xs mb-1" style={LABEL_STYLE}>
                Ou rattacher un cours existant
              </label>
              <select
                value=""
                onChange={(e) => { linkExistingCourse(e.target.value); e.target.value = ''; }}
                style={INPUT_STYLE}
                className="text-sm v224-input"
              >
                <option value="">— Choisir un cours —</option>
                {visibleCourses
                  .filter(c => !linkedCourses.some(lc => lc.id === c.id))
                  .map(c => (
                    <option key={c.id} value={c.id}>
                      {/* V226: on signale les horaires masques ici aussi. Un
                          horaire laisse en `visible: false` par une session
                          abandonnee n'est lie a AUCUNE offre (l'offre n'a
                          jamais ete enregistree) : cette liste est donc le seul
                          endroit ou le coach peut le retrouver pour le
                          rattacher, puis le republier. */}
                      {c.visible === false ? '🚫 ' : ''}
                      {(c.name || 'Cours')}
                      {Number.isInteger(c.weekday) ? ` • ${WEEKDAYS[c.weekday]}` : ''}
                      {c.time ? ` ${c.time}` : ''}
                    </option>
                  ))}
              </select>
            </div>
          )}

          {linkedCourses.length > 0 && (
            <p className="text-xs mt-3 text-pink-400">✓ {linkedCourses.length} horaire(s) lié(s)</p>
          )}
        </div>
      )}

      {/* V224: ancienne liste de cases a cocher. Conservee et utilisee en repli
          quand la prop `API` n'est pas fournie (aucune requete cours possible). */}
      {!form.isProduct && !canEditCourses && visibleCourses.length > 0 && (
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
                // V225: pendant l'ecriture des horaires, on evite le double-clic.
                // V225 CORRECTIF 3: `addingCourse` bloque aussi l'enregistrement.
                // Sans cela, « + Ajouter un horaire » puis « Enregistrer »
                // immediatement remontait le formulaire sans le nouvel id : le
                // POST se resolvait sur un wizard ferme (cours orphelin + setState
                // sur composant demonte).
                // V226: meme raison pour `courseBusyId` — on n'enregistre pas
                // l'offre pendant qu'une suppression, un archivage ou un
                // changement de visibilite est en vol.
                disabled={coursesSaving || addingCourse || !!courseBusyId}
                className="text-sm font-medium px-5 py-2 rounded-lg"
                style={{ background: PINK, color: '#fff', border: 'none', cursor: (coursesSaving || addingCourse || courseBusyId) ? 'wait' : 'pointer', opacity: (coursesSaving || addingCourse || courseBusyId) ? 0.6 : 1 }}
              >
                {coursesSaving ? '⏳ Enregistrement...' : (isEditing ? 'Enregistrer' : 'Créer l\'offre')}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
