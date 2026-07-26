// V295 — Référence temporelle FIABLE en Europe/Zurich.
//
// Partagée entre le panneau de réservation (BookingPanel) et la confirmation
// (ChatWidget) pour que la date affichée soit STRICTEMENT la même partout.
//
// Règle d'or : on ne fait JAMAIS de `.split(',')` sur une chaîne Intl — son
// format varie selon le navigateur (« 2026-07-26, 14:30 » ici, autre chose
// ailleurs). On lit les composantes via `formatToParts`, par leur `type`.

// « Maintenant » en Europe/Zurich, décomposé en nombres.
export function getZurichNow() {
  const parts = new Intl.DateTimeFormat('fr-CH', {
    timeZone: 'Europe/Zurich',
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', hour12: false
  }).formatToParts(new Date());
  const get = (t) => {
    const p = parts.find((x) => x.type === t);
    return p ? parseInt(p.value, 10) : 0;
  };
  let hour = get('hour');
  if (hour === 24) hour = 0; // minuit rendu « 24 » sur certains moteurs
  return { year: get('year'), month: get('month'), day: get('day'), hour, minute: get('minute') };
}

// Extrait l'heure/minute d'une chaîne « HH:MM » (défaut 18:30).
function parseTime(time) {
  let h = 18, m = 30;
  if (time) {
    const tp = String(time).split(':');
    const ph = parseInt(tp[0], 10); if (!isNaN(ph)) h = ph;
    const pm = parseInt(tp[1], 10); if (!isNaN(pm)) m = pm;
  }
  return { h, m };
}

// Prochaine occurrence d'un cours HEBDOMADAIRE (weekday 0=dim..6=sam) à « HH:MM ».
// Si c'est aujourd'hui mais que l'heure est déjà passée en Europe/Zurich,
// on bascule à la semaine suivante (ne plus afficher « aujourd'hui » à tort).
export function nextCourseDate(time, weekday) {
  const znow = getZurichNow();
  const today = new Date(znow.year, znow.month - 1, znow.day, 12, 0, 0);
  const currentDay = today.getDay();
  const { h, m } = parseTime(time);

  let daysUntil = (typeof weekday === 'number' ? weekday : 0) - currentDay;
  if (daysUntil < 0) daysUntil += 7;
  if (daysUntil === 0) {
    const nowMin = znow.hour * 60 + znow.minute;
    if (h * 60 + m <= nowMin) daysUntil = 7; // déjà passé aujourd'hui
  }

  const courseDate = new Date(today);
  courseDate.setDate(today.getDate() + daysUntil);
  courseDate.setHours(h, m, 0, 0);
  return courseDate;
}

// Date d'occurrence d'un cours, PONCTUEL (V246 : `date` = « YYYY-MM-DD ») ou
// RÉCURRENT (weekday). Renvoie un objet Date.
export function courseOccurrenceDate(course) {
  if (course && course.date) {
    const dp = String(course.date).split('-');
    if (dp.length === 3) {
      const { h, m } = parseTime(course.time);
      return new Date(parseInt(dp[0], 10), parseInt(dp[1], 10) - 1, parseInt(dp[2], 10), h, m, 0, 0);
    }
  }
  return nextCourseDate(course ? course.time : null, course ? course.weekday : null);
}

// Un cours est « passé » UNIQUEMENT s'il est ponctuel et daté avant maintenant
// (un cours récurrent a toujours une prochaine occurrence -> jamais « passé »).
export function isPastCourse(course) {
  if (!course || !course.date) return false;
  const occ = courseOccurrenceDate(course);
  const z = getZurichNow();
  const now = new Date(z.year, z.month - 1, z.day, z.hour, z.minute, 0, 0);
  return occ.getTime() < now.getTime();
}

// Libellé français suisse « Samedi 26 juillet 2026, 14:30 » (1re lettre en maj).
export function formatCourseDate(course) {
  const d = courseOccurrenceDate(course);
  const formatter = new Intl.DateTimeFormat('fr-CH', {
    weekday: 'long', day: 'numeric', month: 'long', year: 'numeric',
    hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Zurich'
  });
  const s = formatter.format(d);
  return s.charAt(0).toUpperCase() + s.slice(1);
}
