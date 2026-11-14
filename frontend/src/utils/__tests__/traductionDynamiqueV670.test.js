// V670 — Traduction à l'affichage des contenus publics : l'original est INTOUCHABLE, la
// dépense est bornée, et tout échec se solde par le texte d'origine — jamais une erreur.
import {
  obtenirTraduction, creerEtat, langueTraduisible, cleLocale, empreinte,
  lireCacheLocal, ecrireCacheLocal, CLE_CACHE_TRADUCTIONS,
  MAX_ENTREES_CACHE, BUDGET_PAR_SESSION, PAUSE_APRES_ECHEC_MS, LONGUEUR_MAX,
} from '../traductionDynamique';

function stockage(contenu = {}, { panne = false } = {}) {
  const d = { ...contenu };
  return {
    getItem: (k) => { if (panne) throw new Error('SecurityError'); return Object.prototype.hasOwnProperty.call(d, k) ? d[k] : null; },
    setItem: (k, v) => { if (panne) throw new Error('QuotaExceededError'); d[k] = String(v); },
    _d: d,
  };
}

const reponse = (corps, ok = true, status = 200) => ({ ok, status, json: async () => corps });
const fetchOk = (traduit = 'Afrobeat dance class') =>
  jest.fn(async () => reponse({ translation: traduit, approximate: false, source: 'ia' }));

const base = () => ({ etat: creerEtat(), storage: stockage(), api: 'http://api.test/api' });

describe('Quelles langues ont le droit à une traduction automatique ?', () => {
  it.each(['en', 'de', 'sw', 'ht'])('%s : oui', (l) => expect(langueTraduisible(l)).toBe(true));
  it.each(['fr', 'ln', 'wo', 'bm', 'bas', 'xx', '', undefined])('%p : non (source, ou IA peu fiable)', (l) => {
    // « fr » : la langue d'origine. ln/wo/bm/bas : l'IA y est peu fiable — l'original vaut mieux.
    expect(langueTraduisible(l)).toBe(false);
  });
});

describe('Cas qui ne doivent JAMAIS appeler le serveur', () => {
  it.each([
    ['la langue source', 'Cours de danse', 'fr'],
    ['une langue partielle (lingala)', 'Cours de danse', 'ln'],
    ['une langue partielle (bassa)', 'Cours de danse', 'bas'],
    ['une langue inconnue', 'Cours de danse', 'klingon'],
    ['un texte vide', '', 'en'],
    ['un texte d\'un seul caractère', 'a', 'en'],
    ['un horaire sans lettre', '18:30', 'en'],
    ['un prix', '12.-', 'de'],
    ['un texte non textuel', 42, 'en'],
    ['undefined', undefined, 'en'],
    ['null', null, 'en'],
  ])('%s', async (_nom, texte, lang) => {
    const f = fetchOk();
    const r = await obtenirTraduction(texte, lang, { ...base(), fetchImpl: f });
    expect(f).not.toHaveBeenCalled();
    expect(r).toEqual({ texte, auto: false });
  });

  it('un texte trop long n\'est pas envoyé', async () => {
    const f = fetchOk();
    const long = 'a'.repeat(LONGUEUR_MAX + 1);
    const r = await obtenirTraduction(long, 'en', { ...base(), fetchImpl: f });
    expect(f).not.toHaveBeenCalled();
    expect(r.auto).toBe(false);
  });
});

describe('Traduction d\'un contenu public', () => {
  it('demande une traduction PUBLIQUE (cache: true) et la rend, marquée automatique', async () => {
    const f = fetchOk('Afrobeat dance class');
    const r = await obtenirTraduction('Cours de danse afrobeat', 'en', { ...base(), fetchImpl: f });
    expect(f).toHaveBeenCalledTimes(1);
    const [url, init] = f.mock.calls[0];
    expect(url).toBe('http://api.test/api/translate');
    expect(JSON.parse(init.body)).toEqual({ text: 'Cours de danse afrobeat', target_lang: 'en', cache: true });
    expect(r).toEqual({ texte: 'Afrobeat dance class', auto: true });
  });

  it('⚠️ l\'original n\'est JAMAIS modifié (objet gelé : toute écriture lèverait)', async () => {
    const offre = Object.freeze({ name: 'Cours de danse afrobeat', description: 'Un cours fun.' });
    const f = fetchOk('Afrobeat dance class');
    const r = await obtenirTraduction(offre.name, 'en', { ...base(), fetchImpl: f });
    expect(r.texte).toBe('Afrobeat dance class');
    expect(offre.name).toBe('Cours de danse afrobeat');
    expect(offre.description).toBe('Un cours fun.');
  });

  it('⚠️ ne retraduit pas deux fois : la seconde demande vient du cache local', async () => {
    const f = fetchOk();
    const b = { ...base(), fetchImpl: f };
    await obtenirTraduction('Cours de danse afrobeat', 'en', b);
    const r2 = await obtenirTraduction('Cours de danse afrobeat', 'en', b);
    expect(f).toHaveBeenCalledTimes(1);
    expect(r2).toEqual({ texte: 'Afrobeat dance class', auto: true });
  });

  it('le cache survit à un « rechargement » (nouvel état de page, même stockage)', async () => {
    const f = fetchOk();
    const storage = stockage();
    await obtenirTraduction('Cours de danse afrobeat', 'en', { etat: creerEtat(), storage, api: 'x', fetchImpl: f });
    const r = await obtenirTraduction('Cours de danse afrobeat', 'en', { etat: creerEtat(), storage, api: 'x', fetchImpl: f });
    expect(f).toHaveBeenCalledTimes(1);
    expect(r.auto).toBe(true);
  });

  it('chaque langue a sa propre traduction du même texte', async () => {
    const f = jest.fn(async (_u, init) => reponse({ translation: `[${JSON.parse(init.body).target_lang}]`, approximate: false }));
    const b = { ...base(), fetchImpl: f };
    expect((await obtenirTraduction('Cours de danse', 'en', b)).texte).toBe('[en]');
    expect((await obtenirTraduction('Cours de danse', 'de', b)).texte).toBe('[de]');
    expect(f).toHaveBeenCalledTimes(2);
  });

  it('⚠️ deux demandes SIMULTANÉES du même texte ne font qu\'UN appel', async () => {
    let liberer;
    const f = jest.fn(() => new Promise((res) => { liberer = () => res(reponse({ translation: 'T', approximate: false })); }));
    const b = { ...base(), fetchImpl: f };
    const p1 = obtenirTraduction('Cours de danse', 'en', b);
    const p2 = obtenirTraduction('Cours de danse', 'en', b);
    const p3 = obtenirTraduction('  Cours   de danse ', 'en', b);       // mêmes mots, espaces différents
    liberer();
    const [a, c, d] = await Promise.all([p1, p2, p3]);
    expect(f).toHaveBeenCalledTimes(1);
    expect([a.texte, c.texte, d.texte]).toEqual(['T', 'T', 'T']);
  });
});

describe('Pannes — toujours l\'original, jamais d\'erreur', () => {
  const original = 'Cours de danse afrobeat';
  const rien = { texte: original, auto: false };

  it.each([
    ['HTTP 429 (limite de débit)', () => jest.fn(async () => reponse({}, false, 429))],
    ['HTTP 502 (IA en panne)', () => jest.fn(async () => reponse({}, false, 502))],
    ['réseau coupé', () => jest.fn(async () => { throw new TypeError('Failed to fetch'); })],
    ['JSON invalide', () => jest.fn(async () => ({ ok: true, status: 200, json: async () => { throw new SyntaxError('x'); } }))],
    ['traduction vide', () => jest.fn(async () => reponse({ translation: '   ', approximate: false }))],
    ['réponse sans traduction', () => jest.fn(async () => reponse({}))],
    ['traduction « approximative » (mots français restés)', () => jest.fn(async () => reponse({ translation: 'Cours of dance', approximate: true }))],
  ])('%s', async (_nom, fabrique) => {
    const r = await obtenirTraduction(original, 'en', { ...base(), fetchImpl: fabrique() });
    expect(r).toEqual(rien);
  });

  it('un échec n\'est PAS mis en cache local', async () => {
    const b = base();
    await obtenirTraduction(original, 'en', { ...b, fetchImpl: jest.fn(async () => reponse({}, false, 502)) });
    expect(lireCacheLocal(b.storage)).toEqual({});
  });

  it('⚠️ un service en panne n\'est pas harcelé : pause de 5 minutes, puis nouvel essai', async () => {
    const b = base();
    let t = 1_000_000;
    const f = jest.fn(async () => reponse({}, false, 502));
    const opts = { ...b, fetchImpl: f, maintenant: () => t };
    await obtenirTraduction(original, 'en', opts);
    await obtenirTraduction(original, 'en', opts);
    t += PAUSE_APRES_ECHEC_MS - 1000;
    await obtenirTraduction(original, 'en', opts);
    expect(f).toHaveBeenCalledTimes(1);                 // toujours en pause
    t += 2000;
    await obtenirTraduction(original, 'en', opts);
    expect(f).toHaveBeenCalledTimes(2);                 // pause écoulée : on réessaie
  });

  it('⚠️ un service qui ne répond pas est interrompu (délai) : l\'original s\'affiche', async () => {
    const f = jest.fn((_u, init) => new Promise((_res, rej) => {
      init.signal.addEventListener('abort', () => rej(new Error('abort')));
    }));
    const r = await obtenirTraduction(original, 'en', { ...base(), fetchImpl: f, delai: 15 });
    expect(r).toEqual(rien);
  });

  it('sans fetch disponible (environnement ancien) : l\'original, sans exception', async () => {
    const ancien = global.fetch;
    global.fetch = undefined;          // hermétique : aucune requête réseau ne peut partir
    try {
      const r = await obtenirTraduction(original, 'en', { ...base(), fetchImpl: null });
      expect(r).toEqual(rien);
    } finally {
      global.fetch = ancien;
    }
  });
});

describe('Dépense bornée côté navigateur', () => {
  it(`⚠️ au plus ${BUDGET_PAR_SESSION} demandes par session, puis l'original`, async () => {
    const f = jest.fn(async () => reponse({ translation: 'T', approximate: false }));
    const b = { ...base(), fetchImpl: f };
    for (let i = 0; i < BUDGET_PAR_SESSION; i += 1) await obtenirTraduction(`Texte numéro ${i} ici`, 'en', b);
    expect(f).toHaveBeenCalledTimes(BUDGET_PAR_SESSION);
    const r = await obtenirTraduction('Un texte de plus, jamais traduit', 'en', b);
    expect(f).toHaveBeenCalledTimes(BUDGET_PAR_SESSION);
    expect(r).toEqual({ texte: 'Un texte de plus, jamais traduit', auto: false });
  });

  it('le budget n\'empêche pas de relire le cache local', async () => {
    const f = jest.fn(async () => reponse({ translation: 'T', approximate: false }));
    const b = { ...base(), fetchImpl: f };
    await obtenirTraduction('Premier texte traduit', 'en', b);
    b.etat.demandes = BUDGET_PAR_SESSION;
    const r = await obtenirTraduction('Premier texte traduit', 'en', b);
    expect(r.auto).toBe(true);
  });
});

describe('Cache local — robustesse', () => {
  it('un cache corrompu est ignoré, jamais une exception', async () => {
    const f = fetchOk('X');
    const storage = stockage({ [CLE_CACHE_TRADUCTIONS]: '{pas du json' });
    const r = await obtenirTraduction('Cours de danse', 'en', { etat: creerEtat(), storage, api: 'x', fetchImpl: f });
    expect(r.texte).toBe('X');
  });

  it.each([['"une chaîne"'], ['[1,2]'], ['null'], ['42']])('un cache de forme inattendue (%s) est ignoré', (brut) => {
    expect(lireCacheLocal(stockage({ [CLE_CACHE_TRADUCTIONS]: brut }))).toEqual({});
  });

  it('un stockage bloqué ne fait pas planter la traduction (elle marche sans cache)', async () => {
    const f = fetchOk('X');
    const r = await obtenirTraduction('Cours de danse', 'en', { etat: creerEtat(), storage: stockage({}, { panne: true }), api: 'x', fetchImpl: f });
    expect(r).toEqual({ texte: 'X', auto: true });
  });

  it(`⚠️ le cache est plafonné à ${MAX_ENTREES_CACHE} entrées, les plus anciennes partent d'abord`, () => {
    const storage = stockage();
    const gros = {};
    for (let i = 0; i < MAX_ENTREES_CACHE + 5; i += 1) gros[`k${i}`] = `v${i}`;
    ecrireCacheLocal(gros, storage);
    const relu = lireCacheLocal(storage);
    expect(Object.keys(relu)).toHaveLength(MAX_ENTREES_CACHE);
    expect(relu.k0).toBeUndefined();
    expect(relu[`k${MAX_ENTREES_CACHE + 4}`]).toBe(`v${MAX_ENTREES_CACHE + 4}`);
  });

  it('un cache qui contient une valeur non textuelle n\'est pas rendu tel quel', async () => {
    const f = fetchOk('Vraie traduction');
    const storage = stockage();
    storage.setItem(CLE_CACHE_TRADUCTIONS, JSON.stringify({ [cleLocale('en', 'Cours de danse')]: { piege: true } }));
    const r = await obtenirTraduction('Cours de danse', 'en', { etat: creerEtat(), storage, api: 'x', fetchImpl: f });
    expect(r.texte).toBe('Vraie traduction');
  });
});

describe('Clé et empreinte', () => {
  it('la clé distingue la langue et le texte, pas les espaces', () => {
    expect(cleLocale('en', 'Cours de danse')).not.toBe(cleLocale('de', 'Cours de danse'));
    expect(cleLocale('en', 'Cours de danse')).not.toBe(cleLocale('en', 'Cours de danses'));
    expect(cleLocale('en', 'Cours  de   danse ')).toBe(cleLocale('en', 'Cours de danse'));
  });
  it('la clé ne contient pas le texte (le stockage local ne révèle rien d\'utile)', () => {
    expect(cleLocale('en', 'Offre confidentielle Dupont')).not.toMatch(/Dupont|confidentielle/);
  });
  it('l\'empreinte est déterministe et sensible à la casse et aux chiffres', () => {
    expect(empreinte('abc')).toBe(empreinte('abc'));
    expect(empreinte('abc')).not.toBe(empreinte('Abc'));
    expect(empreinte('5 € offerts')).not.toBe(empreinte('5 offerts'));
  });
});
