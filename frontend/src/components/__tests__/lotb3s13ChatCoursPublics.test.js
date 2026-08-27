/**
 * LOT B3-S1.3 — LE CHAT LIT LES OCCURRENCES PUBLIQUES, JAMAIS L'ESPACE PRIVE.
 *
 * POURQUOI CE BANC EST STATIQUE. `ChatWidget.js` fait 9400 lignes en ES5 pur et
 * son montage tire la moitie de l'application ; ce qu'on doit garantir ici est
 * une propriete de la SOURCE, pas du rendu : « ce fichier n'appelle plus la
 * route privee ». Une lecture de source le prouve directement, sans dependre
 * d'un montage qui pourrait masquer l'appel derriere une branche non exercee.
 */
const fs = require('fs');
const path = require('path');

const FICHIER = path.join(__dirname, '..', 'ChatWidget.js');
const SRC = fs.readFileSync(FICHIER, 'utf8');

// La fonction sous test, isolee de ses 9400 voisines.
function corpsDe(nom) {
  const debut = SRC.indexOf('var ' + nom + ' = useCallback(');
  if (debut === -1) return '';
  const fin = SRC.indexOf('\n  }, [', debut);
  return fin === -1 ? SRC.slice(debut) : SRC.slice(debut, fin);
}

const CORPS = corpsDe('loadAvailableCourses');

describe('LOT B3-S1.3 — le chat lit la route publique, jamais l espace prive', () => {
  test('la fonction de chargement des seances existe toujours', () => {
    expect(CORPS.length).toBeGreaterThan(0);
  });

  test('1. plus AUCUN appel a la route privee /subscriber/space dans tout le fichier', () => {
    expect(SRC).not.toContain('/subscriber/space');
  });

  test('2. le chargement lit la route publique des occurrences', () => {
    expect(CORPS).toMatch(/axios\.get\(\s*API\s*\+\s*'\/courses\/occurrences'/);
  });

  test('3. il transmet le coach de la vitrine (isolation multi-tenant)', () => {
    expect(CORPS).toContain('vitrineCoachEmail');
    expect(CORPS).toMatch(/'\?coach=' \+ encodeURIComponent\(/);
  });

  test('4. il ne duplique AUCUNE logique de cours (pas de calcul de date)', () => {
    // Le depliage en occurrences appartient au serveur (`_v184_next_occurrences`).
    // Rien qui ressemble a un calcul de « prochain mercredi » ne doit vivre ici.
    expect(CORPS).not.toMatch(/getDay\(\)|setDate\(|weekday\s*[-+]|addDays/);
    expect((CORPS.match(/new Date\(/g) || []).length).toBe(0);
  });

  test('5. aucune donnee privee ne transite par ce chemin', () => {
    ['forfait_bloque', 'forfait_message', 'subscriber', 'reservations',
     'droits_restant', 'group_members', 'assignedEmail', 'whatsapp',
     'promoCode', 'access_code'].forEach((champ) => {
      expect(CORPS).not.toContain(champ);
    });
  });

  test('6. l occurrence est RECOPIEE du serveur, jamais fabriquee', () => {
    // `quand` ne peut venir que du champ `datetime` rendu par le serveur.
    expect(CORPS).toMatch(/var quand = String\(occ\.datetime \|\| ''\)\.trim\(\)/);
    const affectations = CORPS.match(/occurrenceDatetime:\s*[^,\n]+/g) || [];
    expect(affectations.length).toBe(1);
    expect(affectations[0].replace(/\s+/g, ' ')).toBe('occurrenceDatetime: quand');
  });

  test('7. fail closed : une occurrence incomplete n est pas affichee', () => {
    expect(CORPS).toContain("quand.length < 16");
    expect(CORPS).toContain('continue');
  });

  test('8. la garde LOT 1 de confirmation est intacte (derniere ligne de defense)', () => {
    expect(SRC).toContain("lot1Quand.length < 16");
    expect(SRC).toContain('Séance non identifiée');
  });

  test('9. le fichier reste en ES5 sur la zone modifiee (var, function, pas de fleche)', () => {
    expect(CORPS).not.toMatch(/=>/);
    expect(CORPS).not.toMatch(/\bconst\b|\blet\b/);
    expect(CORPS).toContain('function (');
  });

  test('10. le jeton d espace n est jamais lu ni envoye par le chat', () => {
    expect(CORPS).not.toContain('X-Espace-Token');
    expect(CORPS).not.toContain('afroboost_espace_token');
  });

  test('11. aucun code d abonne n est envoye a cette route', () => {
    expect(CORPS).not.toMatch(/accessCode|afroboostProfile/);
  });
});
