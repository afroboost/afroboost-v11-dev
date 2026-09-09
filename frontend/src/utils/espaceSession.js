// ═══════════════════════════════════════════════════════════════════════════
// SESSION ABONNÉE — UNE SEULE DÉFINITION, TROIS LECTEURS
// ═══════════════════════════════════════════════════════════════════════════
//
// La session d'un abonné vivait déjà (LOT B3-S1) : un jeton signé `subscriber_space`
// de 30 jours, adossé à un document `subscriber_sessions` révocable par son `jti`.
// Mais elle était lue à DEUX endroits qui ne se connaissaient pas : l'intercepteur
// axios d'App.js et les fonctions privées de SubscriberSpace. Deux lectures d'une
// même clé finissent toujours par diverger — et maintenant un troisième lecteur
// arrive (le retour automatique au lancement). D'où ce module : une seule
// définition de ce qu'est une session valide.
//
// CE QUI EST STOCKÉ, ET CE QUI NE L'EST PAS. Le jeton est un JWT signé par le
// serveur : il ne contient PAS le code d'accès en clair au sens d'un secret
// réutilisable, il ne vaut que pour l'espace pour lequel l'adresse e-mail a été
// prouvée, et le serveur peut le révoquer à tout instant. Le code d'accès
// accompagne l'entrée uniquement pour savoir QUEL espace ouvrir — il ne donne
// aucun droit à lui seul depuis B3-S1.3 : la route exige le jeton.
export const ESPACE_CLE = "afroboost_espace_token";

// Le pense-bête du lancement : « je t'ai déjà ramené chez toi pour cette
// ouverture ». Il vit en sessionStorage, donc il meurt avec l'onglet — sans lui,
// un abonné qui touche « Accueil » serait immédiatement renvoyé dans son espace
// et ne pourrait plus jamais voir la vitrine.
export const ESPACE_CLE_RETOUR = "af_espace_retour_fait";

function _brut() {
  try {
    return window.localStorage.getItem(ESPACE_CLE);
  } catch (e) {
    return null;                 // mode privé, quota, stockage bloqué
  }
}

/** La session si elle est exploitable, sinon null. Jamais d'exception. */
export function lireSession() {
  const brut = _brut();
  if (!brut) return null;
  try {
    const j = JSON.parse(brut);
    if (!j || !j.token) return null;
    // Un jeton périmé n'est pas une session : ne pas l'envoyer évite de faire
    // refuser une requête que l'on sait déjà perdue.
    if (j.expires_at && new Date(j.expires_at) <= new Date()) return null;
    return {
      token: j.token,
      code: j.code || "",
      slug: j.slug || "",
      expires_at: j.expires_at || null,
    };
  } catch (e) {
    return null;
  }
}

/** La session SI elle ouvre CET espace-ci. Celui d'un autre ne vaut jamais. */
export function sessionPourEspace(code, slug) {
  const s = lireSession();
  if (!s) return null;
  if ((s.code || "") !== (code || "")) return null;
  if ((s.slug || "") !== (slug || "")) return null;
  return s;
}

export function ecrireSession(code, slug, token, expiresAt) {
  try {
    window.localStorage.setItem(ESPACE_CLE, JSON.stringify({
      token, code: code || "", slug: slug || "", expires_at: expiresAt || null,
    }));
  } catch (e) { /* stockage indisponible : l'accès prime, on réidentifiera */ }
}

/** Oublie la session ET tout ce qui pourrait faire croire qu'elle vit encore. */
export function oublierSession() {
  try { window.localStorage.removeItem(ESPACE_CLE); } catch (e) { /* ignore */ }
  // Sans cette ligne, se déconnecter puis rouvrir l'application relancerait le
  // retour automatique vers l'espace qu'on vient de quitter.
  try { window.sessionStorage.removeItem(ESPACE_CLE_RETOUR); } catch (e) { /* ignore */ }
}

/** L'adresse de l'espace de cette session, ou "" s'il n'y en a pas. */
export function urlDeLaSession(session) {
  const s = session || lireSession();
  if (!s || !s.code) return "";
  return s.slug
    ? `/espace/${encodeURIComponent(s.code)}?m=${encodeURIComponent(s.slug)}`
    : `/espace/${encodeURIComponent(s.code)}`;
}
