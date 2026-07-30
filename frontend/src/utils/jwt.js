/**
 * V345 — Lecture NON CRYPTOGRAPHIQUE d'un JWT, côté navigateur.
 *
 * POURQUOI CE FICHIER EXISTE
 * --------------------------
 * Jusqu'ici, le frontend considérait qu'un jeton PRÉSENT dans le localStorage était
 * un jeton VALIDE (`v319HasCoachJwt` ne testait que sa longueur). Or un jeton expire
 * au bout de 7 jours (`JWT_EXPIRATION_DAYS`, api/routes/auth_routes.py). Passé ce
 * délai, on obtenait une « SESSION ZOMBIE » :
 *   - le front voyait un jeton -> il accordait l'interface coach ;
 *   - le serveur le décodait -> expiré -> 403 sur chaque appel ;
 *   - le `catch` de `loadCoachSessions` était muet -> listes vides, sans un mot.
 * L'admin voyait donc son interface, mais aucune donnée, et sans la moindre
 * explication. C'est ce que cette version supprime.
 *
 * CE QUE CE FICHIER N'EST PAS
 * ---------------------------
 * Il ne VÉRIFIE PAS la signature — c'est impossible dans un navigateur sans exposer
 * le secret, et ce serait de toute façon inutile : seul le serveur décide. On lit
 * uniquement `exp` pour éviter d'afficher une interface qui ne fonctionnera pas.
 * La sécurité reste entièrement serveur ; ceci n'est que de l'honnêteté d'affichage.
 *
 * RÈGLE DE PRUDENCE : on ne déclare un jeton expiré que si l'on a POSITIVEMENT lu
 * une date d'expiration passée. Jeton illisible, sans `exp`, ou format inattendu ->
 * considéré comme VALIDE, et c'est le serveur qui tranchera. Échouer « fermé » ici
 * verrouillerait le propriétaire dehors sur un simple détail de format — exactement
 * le travers que le dépôt combat depuis l'incident V310c.
 */

/** Décode la charge utile d'un JWT, ou renvoie null si elle est illisible. */
export function chargeUtileJeton(token) {
  try {
    const parts = String(token || '').split('.');
    if (parts.length !== 3) return null;
    let b64 = parts[1].replace(/-/g, '+').replace(/_/g, '/');
    while (b64.length % 4) b64 += '=';
    const brut = atob(b64);
    // Un email ou un nom peut contenir de l'UTF-8 : `atob` seul le mutilerait.
    let json;
    try {
      json = decodeURIComponent(escape(brut));
    } catch (e) {
      json = brut;
    }
    return JSON.parse(json);
  } catch (e) {
    return null;
  }
}

/**
 * Le jeton est-il EXPIRÉ de façon certaine ?
 * `true` UNIQUEMENT si `exp` a pu être lu et qu'il est dans le passé.
 */
export function jetonExpire(token) {
  const payload = chargeUtileJeton(token);
  if (!payload || typeof payload.exp !== 'number') return false; // dans le doute : valide
  return payload.exp * 1000 <= Date.now();
}

/** Jeton utilisable : présent, de forme plausible, et non expiré. */
export function jetonUtilisable(token) {
  if (!token || String(token).length <= 10) return false;
  return !jetonExpire(token);
}

/** Le jeton coach rangé dans le localStorage est-il utilisable ? */
export function jetonCoachUtilisable() {
  try {
    return jetonUtilisable(localStorage.getItem('afroboost_jwt'));
  } catch (e) {
    return false;
  }
}
