// V633 — en-tetes d'un appel `fetch` qui doit porter l'identite du coach.
//
// L'intercepteur axios d'App.js joint le JWT a tous les appels axios, mais PAS
// aux appels `fetch` : ceux de l'assistant IA (`/api/ai/enhance-text`) partaient
// donc sans aucune identite. Le serveur exige desormais un JWT signe de coach ou
// d'admin (V633) ; cette fonction le joint, sans rien changer d'autre.
//
// Sans jeton (session ancienne ou deconnectee), aucun en-tete n'est invente :
// le serveur repond 403 et l'ecran garde le texte d'origine.
export function enTetesCoach(extra) {
  const entetes = Object.assign({}, extra || {});
  try {
    const jeton = localStorage.getItem('afroboost_jwt');
    if (jeton) entetes['Authorization'] = 'Bearer ' + jeton;
  } catch (e) { /* localStorage indisponible : on part sans jeton */ }
  return entetes;
}
