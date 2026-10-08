/**
 * INV-2 — la séance d'une invitation voyage du lien public jusqu'au sélecteur
 * existant de l'espace participant. Décisions pures + annonce du formulaire.
 */
import fs from 'fs';
import path from 'path';
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import {
  lireSeanceInvitation, verdictSeanceInvitation, cibleAvecSeance,
  indexSeanceInvitation, dateOccurrence, libelleSeance,
} from '../invitationSeance';
import { cibleRedirectionEssai } from '../essaiReservation';
import InvitationSeanceBandeau from '../../components/InvitationSeanceBandeau';

global.IS_REACT_ACT_ENVIRONMENT = true;

const p = (n) => String(n).padStart(2, '0');
/** « AAAA-MM-JJTHH:MM » local, dans N jours, à l'heure donnée. */
function occ(jours, heure = '18:30') {
  const d = new Date(Date.now() + jours * 86400000);
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${heure}`;
}
const O2 = occ(2);
const WD2 = dateOccurrence(O2).getDay();
const O9 = occ(9);
const WD9 = dateOccurrence(O9).getDay();

const OFFRE = { id: 'offre-essai', price: 0, linked_course_ids: ['c-42', 'c-43'] };
const CATALOGUE = [
  { id: 'c-42', name: 'Afro Cardio', weekday: WD2, time: '18:30', visible: true },
  { id: 'c-43', name: 'Afro Dance', weekday: WD9, time: '19:00', visible: true },
  { id: 'c-cache', name: 'Caché', weekday: WD2, time: '18:30', visible: false },
  { id: 'c-hors', name: 'Hors offre', weekday: WD2, time: '18:30' },
  { id: 'evt-gala', name: 'Gala', date: O9.slice(0, 10), time: '20:00' },
];

describe('INV-2 A — lecture du lien produit par cible_front (serveur)', () => {
  // La chaîne EXACTE que `cible_front` renvoie (tests/test_referral_campaigns.py, INV-2a).
  const URL_SERVEUR = '?offre=offre-1&reserver=1&course=cours-A_1&occurrence=2026-10-01T18%3A30';

  test('course + occurrence + offre lus et décodés', () => {
    expect(lireSeanceInvitation(URL_SERVEUR))
      .toEqual({ offre: 'offre-1', course: 'cours-A_1', occurrence: '2026-10-01T18:30' });
  });

  test('window.location simulé : lecture par défaut', () => {
    window.history.replaceState({}, '', `/${URL_SERVEUR}`);
    expect(lireSeanceInvitation()).toEqual({ offre: 'offre-1', course: 'cours-A_1', occurrence: '2026-10-01T18:30' });
    window.history.replaceState({}, '', '/');
  });

  test('séance valide -> formulaire annonce la séance, espace la reçoit', () => {
    const s = lireSeanceInvitation(`?offre=offre-essai&reserver=1&course=c-42&occurrence=${encodeURIComponent(O2)}`);
    const v = verdictSeanceInvitation(s, OFFRE, CATALOGUE);
    expect(v.etat).toBe('ok');
    expect(v.cours.id).toBe('c-42');
    const cible = cibleAvecSeance(cibleRedirectionEssai({ success: true, access_code: 'AFR-2287CA' }), v);
    expect(cible).toBe(`/espace/AFR-2287CA?course=c-42&occurrence=${encodeURIComponent(O2)}`);
    // …et l'espace relit EXACTEMENT la même séance.
    const relue = lireSeanceInvitation(cible.slice(cible.indexOf('?')));
    expect(relue).toMatchObject({ course: 'c-42', occurrence: O2 });
  });
});

describe('INV-2 B — deux séances : celle de l invitation', () => {
  test('index de la séance d invitation dans la liste du serveur (pas 0)', () => {
    const liste = [
      { course_id: 'c-42', datetime: `${O2}:00` },
      { course_id: 'c-43', datetime: `${O9.slice(0, 10)}T19:00:00` },
    ];
    expect(indexSeanceInvitation({ course: 'c-43', occurrence: `${O9.slice(0, 10)}T19:00` }, liste)).toBe(1);
  });

  test('la 2e séance de l offre est validée pour le formulaire', () => {
    const v = verdictSeanceInvitation({ offre: 'offre-essai', course: 'c-43', occurrence: `${O9.slice(0, 10)}T19:00` },
      OFFRE, CATALOGUE);
    expect(v.etat).toBe('ok');
    expect(v.cours.name).toBe('Afro Dance');
  });
});

describe('INV-2 C — séance invalide : rien de présélectionné, message', () => {
  const cas = [
    ['occurrence passée', { course: 'c-42', occurrence: occ(-7) }],
    ['cours inconnu', { course: 'c-supprime', occurrence: O2 }],
    ['cours masqué', { course: 'c-cache', occurrence: O2 }],
    ['cours absent de l offre', { course: 'c-hors', occurrence: O2 }],
    ['mauvaise heure', { course: 'c-42', occurrence: `${O2.slice(0, 10)}T07:15` }],
    ['mauvais jour', { course: 'c-42', occurrence: occ(3) }],
    ['date impossible', { course: 'c-42', occurrence: '2027-02-31T18:30' }],
  ];
  test.each(cas)('%s -> indisponible', (_n, s) => {
    const v = verdictSeanceInvitation({ offre: 'offre-essai', ...s }, OFFRE, CATALOGUE);
    expect(v).toEqual({ etat: 'indisponible' });
    // Aucune séance ne part vers l'espace.
    expect(cibleAvecSeance('/espace/AFR-2287CA', v)).toBe('/espace/AFR-2287CA');
  });

  test.each([
    ['cours hors motif', '?course=a%20b&occurrence=2026-10-01T18%3A30'],
    ['cours trop long', `?course=${'x'.repeat(65)}&occurrence=2026-10-01T18%3A30`],
    ['occurrence sans heure', '?course=c-42&occurrence=2026-10-01'],
    ['occurrence avec secondes', '?course=c-42&occurrence=2026-10-01T18%3A30%3A00'],
    ['injection', '?course=c-42&occurrence=2026-10-01T18%3A30%22%3E%3Cscript%3E'],
    ['un seul paramètre', '?course=c-42'],
    ['aucun', '?offre=x&reserver=1'],
  ])('paramètre malformé (%s) -> ignoré en entier', (_n, search) => {
    expect(lireSeanceInvitation(search)).toBeNull();
    expect(verdictSeanceInvitation(null, OFFRE, CATALOGUE)).toBeNull();
  });

  test('séance d une AUTRE offre que celle ouverte -> ignorée (parcours d avant)', () => {
    expect(verdictSeanceInvitation({ offre: 'autre', course: 'c-42', occurrence: O2 }, OFFRE, CATALOGUE)).toBeNull();
  });

  test('cible nulle (aucun octroi prouvé) reste nulle', () => {
    expect(cibleAvecSeance(null, { etat: 'ok', cours: { id: 'c-42' }, occurrence: O2 })).toBeNull();
  });
});

describe('INV-2 D — événement gratuit (date fixe)', () => {
  test('la date fixe + l heure de l événement -> ok', () => {
    const offreEvt = { id: 'evt', price: 0, linked_course_ids: ['evt-gala'] };
    const v = verdictSeanceInvitation({ offre: 'evt', course: 'evt-gala', occurrence: `${O9.slice(0, 10)}T20:00` },
      offreEvt, CATALOGUE);
    expect(v.etat).toBe('ok');
    expect(v.cours.id).toBe('evt-gala');
  });

  test('une autre date que la date fixe -> indisponible', () => {
    const offreEvt = { id: 'evt', price: 0, linked_course_ids: ['evt-gala'] };
    expect(verdictSeanceInvitation({ offre: 'evt', course: 'evt-gala', occurrence: `${O2.slice(0, 10)}T20:00` },
      offreEvt, CATALOGUE)).toEqual({ etat: 'indisponible' });
  });
});

describe('INV-2 — annonce dans le formulaire de la vitrine', () => {
  let el; let racine;
  afterEach(async () => { if (racine) await act(async () => racine.unmount()); if (el) el.remove(); });
  async function rendre(props) {
    el = document.createElement('div'); document.body.appendChild(el);
    await act(async () => { racine = createRoot(el); racine.render(<InvitationSeanceBandeau {...props} />); });
  }

  test('ok : cours + date + heure', async () => {
    await rendre({ etat: 'ok', nom: 'Afro Cardio', occurrence: '2026-10-01T18:30', variante: 'formulaire' });
    const t = el.querySelector('[data-testid="inv2-seance-libelle"]').textContent;
    expect(t).toContain('Afro Cardio');
    expect(t).toContain('1 octobre');
    expect(t).toContain('18:30');
    expect(el.querySelector('svg')).not.toBeNull();         // icône SVG, pas d'emoji
    expect(el.querySelector('button')).toBeNull();          // rien à cliquer : aucune réservation
  });

  test('indisponible : message clair', async () => {
    await rendre({ etat: 'indisponible', variante: 'formulaire' });
    expect(el.querySelector('[data-testid="inv2-seance-indisponible"]').textContent)
      .toContain('La séance de ton invitation n’est plus disponible');
  });

  test('libellé français', () => {
    expect(libelleSeance('2026-10-01T18:30')).toBe('jeudi 1 octobre · 18:30');
  });
});

describe('INV-2 — câblage App.js (lecture unique, aucune boucle, aucun paiement)', () => {
  const APP = fs.readFileSync(path.join(__dirname, '..', '..', 'App.js'), 'utf8');
  const code = APP.replace(/\/\*[\s\S]*?\*\//g, '')
    .split('\n').filter((l) => !l.trim().startsWith('//')).join('\n');

  test('séance lue UNE fois, par un initialiseur paresseux (aucun useEffect)', () => {
    // V594 : le setter existe pour le parcours Partenaire, mais la LECTURE reste unique et paresseuse.
    expect(code).toContain('const [inv2Seance, setInv2Seance] = useState(() => lireSeanceInvitation());');
    // Le setter n'est appelé QUE par le choix explicite du visiteur (jamais par un effet).
    const appels = code.split('\n').filter((l) => l.includes('setInv2Seance('));
    expect(appels).toHaveLength(1);
    expect(code).toMatch(/const ppChoisirSeance = \(s\) => \{\s*setInv2Seance\(s\);/);
    // Aucun effet ne lit la séance : rien ne peut se rejouer ni boucler.
    expect(code).not.toMatch(/useEffect\(\(\) => \{[^}]*inv2/);
    expect(code).not.toMatch(/\[[^\]]*inv2[^\]]*\]\);/);
  });

  test('le formulaire annonce la séance (même bandeau), la redirection ESSAI-7 la porte', () => {
    expect(code).toContain('<InvitationSeanceBandeau');
    expect(code).toContain('cibleAvecSeance(cibleRedirectionEssai(freeRes.data), inv2Verdict)');
  });

  test('aucun paiement ni réservation déclenché par la séance', () => {
    const lignes = code.split('\n').filter((l) => l.includes('inv2'));
    lignes.forEach((l) => {
      expect(l).not.toMatch(/create-checkout-session|checkout\/free|\/reservations|handleSubmit\(/);
    });
  });
});
