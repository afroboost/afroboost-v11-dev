// V670 — FIABILITÉ DES RÉSERVATIONS : un libellé traduit ne part JAMAIS vers le serveur.
//
// Le risque classique d'une traduction d'interface : afficher « Quantité » en wolof est
// anodin, mais si ce libellé (ou un nom de jour, ou le nom d'une offre traduit) est envoyé
// au serveur à la place d'un identifiant, la réservation échoue — ou pire, s'enregistre
// avec une donnée fausse — sans qu'aucune erreur ne soit visible.
//
// Le script lit l'arbre syntaxique de chaque fichier traduit et signale tout `t(...)`
// (direct, ou via une variable qui en dérive) dans le corps d'un axios.post/put/patch/fetch.
const { execFileSync } = require('child_process');
const path = require('path');

const RACINE = path.join(__dirname, '..', '..', '..');
const FICHIERS = [
  'src/App.js',
  'src/components/SubscriberSpace.js',
  'src/components/Publications.js',
  'src/components/CoachVitrine.js',
  'src/components/BecomeCoachPage.js',
  'src/components/OffresAimants.js',
  'src/components/SessionsModal.js',
  'src/components/HeroTexte.js',
  'src/components/accueil/ColonneAccueil.js',
  'src/components/accueil/DecouvrirAfroboost.js',
];

describe('Aucun texte traduit dans une requête réseau', () => {
  it('⚠️ aucun t(…) — direct ou indirect — dans le corps d\'une requête', () => {
    let sortie = '';
    try {
      sortie = execFileSync('node', ['scripts/verifier-payloads.cjs', ...FICHIERS], { cwd: RACINE, encoding: 'utf8' });
    } catch (e) {
      throw new Error(`Un libellé traduit part vers le serveur :\n${e.stdout || e.message}`);
    }
    expect(sortie).toMatch(/\d+ appels réseau examinés ; 0 t\(\) dans un corps de requête/);
  });

  it('le détecteur DÉTECTE bien un cas fautif (sinon ce test ne protège rien)', () => {
    const fs = require('fs'); const os = require('os');
    const tmp = path.join(os.tmpdir(), `faute_payload_${Date.now()}.js`);
    fs.writeFileSync(tmp, `
      import axios from 'axios';
      export function F({ t }) {
        const libelle = t('v_fermer');
        axios.post('/api/reservations', { direct: t('v_quantite') });
        axios.post('/api/reservations', { indirect: libelle });
      }`);
    try {
      let code = 0; let sortie = '';
      try { sortie = execFileSync('node', ['scripts/verifier-payloads.cjs', tmp], { cwd: RACINE, encoding: 'utf8' }); }
      catch (e) { code = e.status; sortie = e.stdout; }
      expect(code).toBe(1);
      expect(sortie).toMatch(/2 t\(\) dans un corps de requête/);
    } finally { fs.unlinkSync(tmp); }
  });
});
