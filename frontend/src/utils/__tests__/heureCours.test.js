/**
 * N2 — L'ECRAN ET LE SERVEUR DOIVENT LIRE LA MEME HEURE.
 *
 * Deux formats de date coexistent en base (mesure du 12/08/2026, 125
 * reservations) :
 *     57  « 2026-03-11T17:01:14.738Z »  -> UTC explicite
 *     67  « 2026-05-13T18:30:00 »       -> NAIF, en heure SUISSE
 *
 * `new Date("2026-05-13T18:30:00")` lit la seconde forme dans le fuseau du
 * NAVIGATEUR. Pour quelqu'un a Neuchatel le resultat est juste par accident ;
 * en voyage, il est faux — et l'ecran offrirait « Annuler » quand le serveur
 * refuse, ou l'inverse. C'est exactement le bouton mort qu'on vient de retirer,
 * reintroduit par la porte de derriere.
 *
 * Ces fonctions donnent a l'ecran la MEME lecture que `n2_instant_reel`
 * (api/routes/shared.py). Aucune dependance : `Intl` suffit, et il gere seul le
 * passage ete/hiver — un decalage fixe de +2 h serait faux la moitie de l'annee.
 */
import { instantReelCours, estAujourdhuiZurich } from '../heureCours';

// Le navigateur de test est en UTC : si la lecture etait naive, « 18:30 »
// vaudrait 18:30 UTC et tous les tests ci-dessous tomberaient.
const UTC = (a, m, j, h, mn) => Date.UTC(a, m - 1, j, h, mn);

describe('instantReelCours — une date sans fuseau est suisse', () => {
  test('ete : 18:30 a Neuchatel = 16:30 UTC', () => {
    expect(instantReelCours('2026-08-26T18:30:00')).toBe(UTC(2026, 8, 26, 16, 30));
  });

  test('hiver : 18:30 a Neuchatel = 17:30 UTC', () => {
    expect(instantReelCours('2026-01-14T18:30:00')).toBe(UTC(2026, 1, 14, 17, 30));
  });

  test('le passage ete/hiver n est pas un decalage fixe', () => {
    const ete = instantReelCours('2026-08-26T18:30:00');
    const hiver = instantReelCours('2026-01-14T18:30:00');
    // meme heure locale, une heure d'ecart en UTC
    expect((hiver - UTC(2026, 1, 14, 0, 0)) - (ete - UTC(2026, 8, 26, 0, 0)))
      .toBe(3600 * 1000);
  });
});

describe('instantReelCours — une date datee reste ce qu elle est', () => {
  test('suffixe Z', () => {
    expect(instantReelCours('2026-08-26T16:30:00Z')).toBe(UTC(2026, 8, 26, 16, 30));
  });

  test('decalage explicite', () => {
    expect(instantReelCours('2026-08-26T18:30:00+02:00')).toBe(UTC(2026, 8, 26, 16, 30));
  });

  test('millisecondes', () => {
    expect(instantReelCours('2026-03-11T17:01:14.738Z'))
      .toBe(Date.parse('2026-03-11T17:01:14.738Z'));
  });
});

describe('instantReelCours — rien n est invente', () => {
  test('valeur inexploitable -> NaN, jamais une date au hasard', () => {
    [null, undefined, '', '   ', 'demain', 42, {}, []].forEach((v) => {
      expect(Number.isNaN(instantReelCours(v))).toBe(true);
    });
  });
});

describe('estAujourdhuiZurich', () => {
  const jourZurich = (decalageJours) => {
    const d = new Date(Date.now() + decalageJours * 86400000);
    const p = {};
    new Intl.DateTimeFormat('en-CA', {
      timeZone: 'Europe/Zurich', year: 'numeric', month: '2-digit', day: '2-digit',
    }).formatToParts(d).forEach((x) => { p[x.type] = x.value; });
    return `${p.year}-${p.month}-${p.day}T12:00:00`;
  };

  test('une seance du jour est reconnue', () => {
    expect(estAujourdhuiZurich(jourZurich(0))).toBe(true);
  });

  test('demain et hier ne le sont pas', () => {
    expect(estAujourdhuiZurich(jourZurich(1))).toBe(false);
    expect(estAujourdhuiZurich(jourZurich(-1))).toBe(false);
  });

  test('une valeur illisible ne leve pas et repond non', () => {
    [null, '', 'demain', 42].forEach((v) => {
      expect(estAujourdhuiZurich(v)).toBe(false);
    });
  });
});
