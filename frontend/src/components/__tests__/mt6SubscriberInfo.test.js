/**
 * MT-6 — `/api/subscriber-info/{code}` ne livre plus e-mail / WhatsApp /
 * anniversaire à qui ne présente que le code. Ce banc prouve, sur la SOURCE
 * (ChatWidget.js est trop gros pour être monté ici), que les écrans abonnés
 * restent fonctionnels :
 *   - la lecture passe par axios, donc par l'intercepteur qui joint le jeton
 *     d'appareil (X-Subscriber-Token) -> l'abonné déjà connecté garde sa fiche ;
 *   - sur un appareil neuf, le WhatsApp est relu APRÈS l'émission du jeton et
 *     AVANT smart-entry -> rien n'est redemandé ;
 *   - la connexion automatique QR / ?code= exige toujours e-mail + WhatsApp +
 *     anniversaire : avec la réponse anonyme ({exists, name}) elle ne se
 *     déclenche plus, le formulaire s'ouvre pré-rempli.
 * Le comportement serveur est prouvé par tests/test_mt6_subscriber_info.py.
 */
const fs = require('fs');
const path = require('path');

const RACINE = path.join(__dirname, '..', '..', '..', '..');
const lire = (p) => fs.readFileSync(path.join(RACINE, p), 'utf8');

function sansCommentaires(src) {
  return src
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:])\/\/.*$/gm, '$1');
}

const CHAT = sansCommentaires(lire('frontend/src/components/ChatWidget.js'));
const APP = sansCommentaires(lire('frontend/src/App.js'));
const SERVEUR = lire('api/server.py');

test('la lecture de la fiche passe par axios (intercepteur = jeton abonné joint)', () => {
  expect(CHAT).toMatch(/axios\.get\(API \+ '\/subscriber-info\/' \+ encodeURIComponent\(c\)\)/);
  expect(APP).toMatch(/localStorage\.getItem\('afroboost_subscriber_token'\)/);
  expect(APP).toMatch(/config\.headers\['X-Subscriber-Token'\] = subTok/);
});

test('connexion : jeton émis, PUIS relecture du WhatsApp, PUIS smart-entry', () => {
  const debut = CHAT.indexOf('const connectSubscriberWithData');
  expect(debut).toBeGreaterThan(-1);
  const corps = CHAT.slice(debut, debut + 12000);
  const iJeton = corps.indexOf('v296EnsureSubscriberToken(profile.code, profile.email)');
  const iRelecture = corps.indexOf('_infoJeton = await v294FetchSubscriberInfo(profile.code)');
  const iEntree = corps.indexOf('await handleSmartEntry(');
  expect(iJeton).toBeGreaterThan(-1);
  expect(iRelecture).toBeGreaterThan(iJeton);
  expect(iEntree).toBeGreaterThan(iRelecture);
  expect(corps).toMatch(/if \(_subTok && !profile\.whatsapp\)/);
});

test('connexion automatique QR / ?code= : exige toujours la fiche complète', () => {
  const conds = CHAT.match(/info && info\.exists && info\.name && info\.whatsapp && info\.email && info\.birthday/g) || [];
  expect(conds.length).toBe(2);
  // Repli intact : le formulaire s'ouvre pré-rempli avec le code.
  expect(CHAT).toMatch(/code: qrCode,/);
  expect(CHAT).toMatch(/code: urlCode,/);
});

test('serveur : la route lit la requête et la réponse anonyme ne porte que exists + name', () => {
  expect(SERVEUR).toMatch(/async def v294_get_subscriber_info\(code: str, request: Request\)/);
  expect(SERVEUR).toMatch(/return \{"exists": True, "name": \(\(doc or \{\}\)\.get\("name"\) or name or ""\)\}/);
  expect(SERVEUR).toMatch(/raise HTTPException\(status_code=403, detail="Jeton abonné requis pour ce code"\)/);
});
