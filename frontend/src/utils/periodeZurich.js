/**
 * V648 — LES BORNES D'UNE PÉRIODE, EN HEURE DE NEUCHÂTEL. FONCTIONS PURES.
 *
 * POURQUOI LE CALCUL EST ICI ET NON SUR LE SERVEUR. Les dates sont stockées en
 * UTC ; le coach pense en heure locale. « Aujourd'hui » n'est donc pas
 * « depuis minuit UTC » : à 00h30 à Neuchâtel en été, il est encore 22h30 la
 * veille en UTC. L'écran, qui a `Intl`, calcule les deux INSTANTS absolus et
 * les envoie tels quels ; le serveur ne fait qu'une comparaison de chaînes. Il
 * n'a donc aucune conversion à faire — donc aucune occasion de se tromper
 * d'une heure deux fois par an.
 *
 * `jusqu_a_iso` est une borne EXCLUE (le minuit du lendemain) : la journée
 * entière est couverte sans dépendre du nombre de décimales des horodatages
 * stockés, qui varie d'un import à l'autre.
 */

export const FUSEAU = 'Europe/Zurich';

export const PERIODES_PROSPECTS = [
  { id: 'tout', libelle: 'Toutes les dates' },
  { id: 'aujourdhui', libelle: 'Aujourd’hui' },
  { id: '7j', libelle: '7 derniers jours' },
  { id: '30j', libelle: '30 derniers jours' },
  { id: 'perso', libelle: 'Période personnalisée' },
];

const JOUR = 86400000;
const RE_JOUR = /^\d{4}-\d{2}-\d{2}$/;

/** Le décalage du fuseau, en minutes, à un instant donné. PURE. */
function decalageMinutes(ms) {
  const p = new Intl.DateTimeFormat('en-CA', {
    timeZone: FUSEAU, year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
  }).formatToParts(new Date(ms)).reduce((acc, x) => { acc[x.type] = x.value; return acc; }, {});
  const commeUTC = Date.UTC(Number(p.year), Number(p.month) - 1, Number(p.day),
    Number(p.hour) % 24, Number(p.minute), Number(p.second));
  return (commeUTC - Math.floor(ms / 1000) * 1000) / 60000;
}

/** « 2026-11-10 » -> l'instant UTC de minuit À NEUCHÂTEL ce jour-là. PURE.
    Le décalage est mesuré à MIDI : un jour de changement d'heure, midi est
    toujours du bon côté de la bascule, minuit pas forcément. */
export function debutJourZurich(aaaammjj) {
  if (!RE_JOUR.test(String(aaaammjj || ''))) return NaN;
  const midi = Date.parse(`${aaaammjj}T12:00:00Z`);
  if (!Number.isFinite(midi)) return NaN;
  return Date.parse(`${aaaammjj}T00:00:00Z`) - decalageMinutes(midi) * 60000;
}

/** L'instant `ms` -> le jour « AAAA-MM-JJ » qu'il est à Neuchâtel. PURE. */
export function jourZurich(ms) {
  const n = Number.isFinite(ms) ? ms : Date.now();
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: FUSEAU, year: 'numeric', month: '2-digit', day: '2-digit',
  }).format(new Date(n));
}

/**
 * Les deux instants à envoyer au serveur : `{ depuis_iso, jusqu_a_iso }`.
 * Chaînes vides quand la borne ne s'applique pas — l'écran les envoie telles
 * quelles, et le serveur ignore ce qui est vide.
 */
export function bornesPeriode(periode, maintenant, debut, fin) {
  const vide = { depuis_iso: '', jusqu_a_iso: '' };
  const p = periode || 'tout';
  if (p === 'tout') return vide;
  const n = Number.isFinite(maintenant) ? maintenant : Date.now();
  const aujourdhui = jourZurich(n);
  const minuitAujourdhui = debutJourZurich(aujourdhui);
  if (!Number.isFinite(minuitAujourdhui)) return vide;
  const demain = new Date(minuitAujourdhui + JOUR + 2 * 3600000);   // à l'abri d'une bascule d'heure
  const minuitDemain = debutJourZurich(jourZurich(demain.getTime()));
  const iso = (ms) => new Date(ms).toISOString();

  if (p === 'aujourdhui') {
    return { depuis_iso: iso(minuitAujourdhui), jusqu_a_iso: iso(minuitDemain) };
  }
  if (p === '7j' || p === '30j') {
    const jours = p === '7j' ? 7 : 30;
    /* « 7 derniers jours » inclut aujourd'hui : on recule de 6 jours, pas de 7
       — sinon la fenêtre en couvrirait huit. */
    const depart = debutJourZurich(jourZurich(minuitAujourdhui - (jours - 1) * JOUR + 2 * 3600000));
    return { depuis_iso: Number.isFinite(depart) ? iso(depart) : '', jusqu_a_iso: iso(minuitDemain) };
  }
  if (p === 'perso') {
    const d = debutJourZurich(debut);
    const f = debutJourZurich(fin);
    return {
      depuis_iso: Number.isFinite(d) ? iso(d) : '',
      /* La date de fin est INCLUSE pour le coach : la borne envoyée est donc le
         minuit du lendemain. */
      jusqu_a_iso: Number.isFinite(f) ? iso(debutJourZurich(jourZurich(f + JOUR + 2 * 3600000))) : '',
    };
  }
  return vide;
}
