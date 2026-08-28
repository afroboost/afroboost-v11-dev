/**
 * LOT M2-A — l'origine d'un visiteur, memorisee cote navigateur.
 *
 * CE QUE CETTE COUCHE GARANTIT, et rien de plus : elle MEMORISE. Elle ne decide
 * de rien. Le serveur re-valide tout ce qu'elle envoie (`m2a_bloc_propre`) :
 * si elle se trompe ou si quelqu'un bricole son `localStorage`, aucune valeur
 * inventee n'atteint la base.
 *
 * LES DEUX REGLES QUI COMPTENT :
 *   - `first` est fige des la premiere origine connue ;
 *   - une visite DIRECTE n'ecrase jamais une origine deja connue — sinon toute
 *     personne qui revient une seconde fois deviendrait « direct », et la
 *     mesure ne voudrait plus rien dire.
 *
 * ET SURTOUT : le suivi ne doit JAMAIS casser le parcours. Chaque fonction
 * renvoie une valeur de repli plutot que de lever.
 */
import {
  CLE_ATTRIBUTION,
  attributionNormaliser,
  attributionDepuisUrl,
  attributionEnregistrer,
  attributionActuelle,
} from '../attribution';

beforeEach(() => {
  try { window.localStorage.clear(); } catch (e) { /* ignore */ }
});

describe('normalisation', () => {
  test('la liste est fermee : une source inventee est refusee', () => {
    expect(attributionNormaliser('instagram')).toBe('instagram');
    expect(attributionNormaliser('  Instagram ')).toBe('instagram');
    expect(attributionNormaliser('mon-canal-a-moi')).toBe('');
    expect(attributionNormaliser('<script>')).toBe('');
  });

  test('null, vide et valeurs demesurees ne cassent rien', () => {
    expect(attributionNormaliser(null)).toBe('');
    expect(attributionNormaliser(undefined)).toBe('');
    expect(attributionNormaliser('x'.repeat(500))).toBe('');
  });
});

describe('lecture depuis l URL et le referrer', () => {
  test('UTM Instagram reconnus', () => {
    const t = attributionDepuisUrl('?utm_source=instagram&utm_medium=social&utm_campaign=essai_neuchatel', '');
    expect(t.source).toBe('instagram');
    expect(t.medium).toBe('social');
    expect(t.campaign).toBe('essai_neuchatel');
  });

  test('sans UTM, un referrer Google donne google / organic', () => {
    const t = attributionDepuisUrl('', 'https://www.google.com/search?q=danse+afro+neuchatel');
    expect(t.source).toBe('google');
    expect(t.medium).toBe('organic');
  });

  test('la requete tapee dans Google n est JAMAIS conservee', () => {
    const t = attributionDepuisUrl('', 'https://www.google.ch/search?q=secret');
    expect(JSON.stringify(t)).not.toContain('secret');
    expect(JSON.stringify(t)).not.toContain('q=');
  });

  test('les UTM sont prioritaires sur le referrer', () => {
    const t = attributionDepuisUrl('?utm_source=instagram', 'https://www.google.com/search?q=x');
    expect(t.source).toBe('instagram');
  });

  test('une navigation INTERNE ne fabrique aucune source', () => {
    expect(attributionDepuisUrl('', 'https://afroboost.com/cours-essai-gratuit-neuchatel')).toBeNull();
  });

  test('un referrer illisible ne leve pas', () => {
    expect(attributionDepuisUrl('', 'pas une url')).toBeNull();
    expect(attributionDepuisUrl(null, null)).toBeNull();
  });
});

describe('first touch / last touch', () => {
  test('TEST 1 — Instagram : first = last = instagram', () => {
    const a = attributionEnregistrer('?utm_source=instagram&utm_medium=social', '', '/cours-essai-gratuit-neuchatel');
    expect(a.first.source).toBe('instagram');
    expect(a.last.source).toBe('instagram');
    expect(a.first.landing_path).toBe('/cours-essai-gratuit-neuchatel');
  });

  test('TEST 2 — retour direct : rien n est ecrase', () => {
    attributionEnregistrer('?utm_source=instagram', '', '/');
    const a = attributionEnregistrer('', '', '/');
    expect(a.first.source).toBe('instagram');
    expect(a.last.source).toBe('instagram');
  });

  test('TEST 3 — Instagram puis WhatsApp', () => {
    attributionEnregistrer('?utm_source=instagram&utm_medium=social', '', '/');
    const a = attributionEnregistrer('?utm_source=whatsapp&utm_medium=referral', '', '/');
    expect(a.first.source).toBe('instagram');
    expect(a.last.source).toBe('whatsapp');
  });

  test('TEST 8 — une navigation interne ne transforme pas Google en afroboost', () => {
    attributionEnregistrer('', 'https://www.google.com/search?q=x', '/cours-essai-gratuit-neuchatel');
    const a = attributionEnregistrer('', 'https://afroboost.com/', '/');
    expect(a.first.source).toBe('google');
    expect(a.last.source).toBe('google');
  });

  test('chaque touche porte son horodatage', () => {
    const a = attributionEnregistrer('?utm_source=tiktok', '', '/');
    expect(typeof a.first.touch_at).toBe('string');
    expect(a.first.touch_at.length).toBeGreaterThan(10);
  });
});

describe('robustesse — le suivi ne casse jamais le parcours', () => {
  test('TEST 5 — UTM malformes : aucune exception, aucune source inventee', () => {
    const a = attributionEnregistrer('?utm_source=' + 'x'.repeat(600) + '&utm_campaign=<img onerror=1>', '', '/');
    expect(a === null || a.first === undefined || a.first.source === '').toBeTruthy();
    expect(JSON.stringify(a)).not.toContain('onerror');
  });

  test('un stockage indisponible ne leve pas', () => {
    const vrai = window.localStorage.getItem;
    window.localStorage.getItem = () => { throw new Error('bloque'); };
    expect(() => attributionActuelle()).not.toThrow();
    expect(() => attributionEnregistrer('?utm_source=instagram', '', '/')).not.toThrow();
    window.localStorage.getItem = vrai;
  });

  test('un contenu corrompu est ignore, pas propage', () => {
    window.localStorage.setItem(CLE_ATTRIBUTION, 'ceci n est pas du JSON');
    expect(attributionActuelle()).toBeNull();
    const a = attributionEnregistrer('?utm_source=instagram', '', '/');
    expect(a.first.source).toBe('instagram');
  });

  test('une attribution expiree (plus de 30 jours) est oubliee', () => {
    const vieux = { v: 1, at: Date.now() - 31 * 86400000,
      first: { source: 'instagram' }, last: { source: 'instagram' } };
    window.localStorage.setItem(CLE_ATTRIBUTION, JSON.stringify(vieux));
    expect(attributionActuelle()).toBeNull();
  });

  test('une attribution de 29 jours est encore valable', () => {
    const recent = { v: 1, at: Date.now() - 29 * 86400000,
      first: { source: 'instagram' }, last: { source: 'instagram' } };
    window.localStorage.setItem(CLE_ATTRIBUTION, JSON.stringify(recent));
    expect(attributionActuelle().first.source).toBe('instagram');
  });

  test('aucune donnee personnelle n est jamais stockee', () => {
    attributionEnregistrer('?utm_source=instagram&utm_campaign=moi@exemple.invalid', '', '/');
    const brut = window.localStorage.getItem(CLE_ATTRIBUTION) || '';
    expect(brut).not.toContain('@');
    expect(brut).not.toContain('exemple.invalid');
  });
});
