// CAL-1 — LE CALENDRIER AFROBOOST, vu du navigateur.
//
// CE QUI EST PROUVÉ ICI, ET POURQUOI CHAQUE POINT COMPTE :
//
//   * les campagnes existantes restent visibles et cliquables — c'est la
//     seule chose que ce calendrier savait faire avant CAL-1, et la
//     généralisation ne devait rien lui retirer ;
//   * un événement d'un AUTRE type s'affiche dans la MÊME grille : c'est tout
//     l'objet du lot, une seule page et non quatre calendriers ;
//   * les trois vues (jour, semaine, mois) montrent la bonne période ;
//   * une séance de cours, PROJETÉE depuis `courses`, ne peut pas être
//     déplacée : la déplacer ici ne changerait rien en base et donnerait
//     l'illusion contraire ;
//   * aucune couleur codée en dur ne subsiste pour la marque — le fichier en
//     portait une vingtaine, et la vitrine personnalisée du coach ne
//     s'appliquait pas au calendrier ;
//   * la grille reste utilisable à largeur mobile.
//
// Aucun appel réseau : le composant ne charge rien, il reçoit tout par props.
import React from 'react';
import { createRoot } from 'react-dom/client';
import { act } from 'react-dom/test-utils';
import CampaignCalendar from '../CampaignCalendar';

let conteneur = null;
let racine = null;

async function monter(element) {
  conteneur = document.createElement('div');
  document.body.appendChild(conteneur);
  racine = createRoot(conteneur);
  await act(async () => { racine.render(element); });
  return conteneur;
}

afterEach(async () => {
  if (racine) await act(async () => { racine.unmount(); });
  if (conteneur) document.body.removeChild(conteneur);
  racine = null; conteneur = null;
});

const par = (id) => conteneur.querySelector(`[data-testid="${id}"]`);
const tous = (sel) => Array.from(conteneur.querySelectorAll(sel));
const cliquer = (el) => act(async () => {
  el.dispatchEvent(new MouseEvent('click', { bubbles: true }));
});

const cle2 = (n) => String(n).padStart(2, '0');
const isoJour = (d) => `${d.getFullYear()}-${cle2(d.getMonth() + 1)}-${cle2(d.getDate())}`;

/* Une date DANS LE MOIS COURANT : le calendrier s'ouvre sur aujourd'hui, et un
   événement daté d'un autre mois ne s'afficherait pas — le test mesurerait
   alors la navigation, pas l'affichage. */
const AUJ = new Date();
const jourDuMois = (n) => new Date(AUJ.getFullYear(), AUJ.getMonth(), n, 14, 0, 0);
const LE_15 = jourDuMois(15);

const campagne = (extra = {}) => ({
  id: 'campaign:c-1', source_id: 'c-1', source: 'campaigns',
  title: 'Silent Lakeside – Rappel J-2',
  starts_at: LE_15.toISOString(), event_type: 'campaign',
  status: 'completed', all_day: true, modifiable: true, ...extra,
});
const rendezVous = (extra = {}) => ({
  id: 'rdv-1', source_id: 'rdv-1', source: 'calendar_events',
  title: 'Appel partenariat — Festival X',
  starts_at: LE_15.toISOString(), event_type: 'appointment',
  status: 'prevu', all_day: false, modifiable: true, ...extra,
});
const cours = (extra = {}) => ({
  id: 'course:co-1:2026-09-15', source_id: 'co-1', source: 'courses',
  title: 'Afroboost Silent – Session Cardio',
  starts_at: LE_15.toISOString(), event_type: 'course',
  status: 'confirme', all_day: false, modifiable: false, ...extra,
});

// ---------------------------------------------------------------------------
describe('CAL-1 — les campagnes existantes ne perdent rien', () => {
  test('une campagne s’affiche dans la grille', async () => {
    await monter(<CampaignCalendar evenements={[campagne()]} />);
    expect(par('calendrier')).toBeTruthy();
    expect(conteneur.textContent).toContain('Silent Lakeside');
  });

  test('cliquer sur une campagne remonte l’ÉVÉNEMENT au gestionnaire', async () => {
    const vus = [];
    await monter(<CampaignCalendar evenements={[campagne()]}
                                   onEvenementClick={(e) => vus.push(e)} />);
    await cliquer(par('evenement'));
    expect(vus).toHaveLength(1);
    // c'est `source_id` qui permet de retrouver la campagne d'origine
    expect(vus[0].source_id).toBe('c-1');
  });

  test('cliquer sur un jour propose la création à cette date', async () => {
    const dates = [];
    await monter(<CampaignCalendar evenements={[]} onDayClick={(d) => dates.push(d)} />);
    await cliquer(par(`jour-${isoJour(jourDuMois(10))}`));
    expect(dates).toEqual([isoJour(jourDuMois(10))]);
  });

  test('le bouton Créer existe toujours', async () => {
    const dates = [];
    await monter(<CampaignCalendar evenements={[]} onDayClick={(d) => dates.push(d)} />);
    await cliquer(par('creer'));
    expect(dates).toHaveLength(1);
  });

  test('le menu contextuel propose Modifier et Dupliquer', async () => {
    await monter(<CampaignCalendar evenements={[campagne()]} />);
    await act(async () => {
      par('evenement').dispatchEvent(new MouseEvent('contextmenu', { bubbles: true }));
    });
    expect(par('menu-modifier')).toBeTruthy();
    expect(par('menu-dupliquer')).toBeTruthy();
  });

  test('une campagne reste déplaçable par glisser-déposer', async () => {
    await monter(<CampaignCalendar evenements={[campagne()]} />);
    expect(par('evenement').getAttribute('draggable')).toBe('true');
  });
});

// ---------------------------------------------------------------------------
describe('CAL-1 — un seul calendrier pour tous les types', () => {
  test('campagne, rendez-vous et cours cohabitent dans la MÊME grille', async () => {
    await monter(<CampaignCalendar evenements={[campagne(), rendezVous(), cours()]} />);
    expect(tous('[data-testid="evenement"]').length).toBe(3);
    expect(tous('[data-testid="grille"]').length).toBe(1);
  });

  test('la légende nomme les quatre types', async () => {
    await monter(<CampaignCalendar evenements={[]} />);
    ['Campagne', 'Rendez-vous', 'Cours', 'Événement'].forEach((l) => {
      expect(conteneur.textContent).toContain(l);
    });
  });

  /* CETTE VÉRIFICATION DISAIT LE CONTRAIRE, ET ELLE AVAIT RAISON EN CAL-1 :
     déclarer un type que rien ne savait créer aurait donné une palette pour du
     vide. CAL-2 a ouvert les tâches ; le contrat s'inverse donc, et la
     propriété de fond monte d'un cran — le type n'est pas seulement affiché,
     il FILTRE réellement. */
  test('« task » est désormais proposé — CAL-2 a ouvert les tâches', async () => {
    await monter(<CampaignCalendar evenements={[]} />);
    expect(par('filtre-task')).toBeTruthy();
    expect(conteneur.textContent).toContain('Tâche');
  });

  test('et le filtre « Tâche » ne garde que les tâches', async () => {
    const tache = { id: 't-1', source_id: 't-1', source: 'calendar_events',
                    title: 'Vérifier DKIM Resend', starts_at: LE_15.toISOString(),
                    event_type: 'task', status: 'prevu', modifiable: true };
    await monter(<CampaignCalendar evenements={[campagne(), tache, cours()]} />);
    await cliquer(par('filtre-task'));
    const restants = tous('[data-testid="evenement"]');
    expect(restants.length).toBe(1);
    expect(restants[0].textContent).toContain('DKIM');
  });

  test('un filtre ne garde que son type', async () => {
    await monter(<CampaignCalendar evenements={[campagne(), rendezVous(), cours()]} />);
    await cliquer(par('filtre-course'));
    const restants = tous('[data-testid="evenement"]');
    expect(restants.length).toBe(1);
    expect(restants[0].textContent).toContain('Session Cardio');
  });

  test('« Tout » les ramène', async () => {
    await monter(<CampaignCalendar evenements={[campagne(), rendezVous(), cours()]} />);
    await cliquer(par('filtre-appointment'));
    expect(tous('[data-testid="evenement"]').length).toBe(1);
    await cliquer(par('filtre-tout'));
    expect(tous('[data-testid="evenement"]').length).toBe(3);
  });

  test('l’heure est affichée pour un événement horaire, pas pour un tout-le-jour', async () => {
    await monter(<CampaignCalendar evenements={[rendezVous(), campagne()]} />);
    const textes = tous('[data-testid="evenement"]').map((e) => e.textContent);
    expect(textes.some((t) => /\d{2}:\d{2}/.test(t))).toBe(true);
    const camp = textes.find((t) => t.includes('Silent Lakeside'));
    expect(/^\d{2}:\d{2}/.test(camp)).toBe(false);
  });
});

// ---------------------------------------------------------------------------
describe('CAL-1 — les trois vues', () => {
  test('la vue par défaut est le mois, avec ses sept colonnes', async () => {
    await monter(<CampaignCalendar evenements={[]} />);
    expect(par('grille').style.gridTemplateColumns).toBe('repeat(7, 1fr)');
    expect(conteneur.textContent).toContain('Lun');
  });

  test('la vue Jour n’affiche qu’un jour', async () => {
    await monter(<CampaignCalendar evenements={[]} />);
    await cliquer(par('vue-jour'));
    expect(tous('[data-testid^="jour-"]').length).toBe(1);
    expect(par('grille').style.gridTemplateColumns).toBe('1fr');
  });

  test('la vue Semaine affiche sept jours, tous réels', async () => {
    await monter(<CampaignCalendar evenements={[]} />);
    await cliquer(par('vue-semaine'));
    expect(tous('[data-testid^="jour-"]').length).toBe(7);
    expect(par('jour-vide')).toBeNull();
  });

  test('la navigation change la période affichée', async () => {
    await monter(<CampaignCalendar evenements={[]} />);
    const avant = par('periode').textContent;
    await cliquer(conteneur.querySelector('[aria-label="Période suivante"]'));
    expect(par('periode').textContent).not.toBe(avant);
    await cliquer(conteneur.querySelector('[aria-label="Période précédente"]'));
    expect(par('periode').textContent).toBe(avant);
  });

  test('en vue mois, la grille commence par des cases vides d’alignement', async () => {
    await monter(<CampaignCalendar evenements={[]} />);
    const premier = new Date(AUJ.getFullYear(), AUJ.getMonth(), 1);
    const attendu = (premier.getDay() + 6) % 7;
    expect(tous('[data-testid="jour-vide"]').length).toBe(attendu);
  });
});

// ---------------------------------------------------------------------------
describe('CAL-1 — ce qui est projeté n’est pas modifiable', () => {
  test('une séance de cours n’est PAS déplaçable', async () => {
    await monter(<CampaignCalendar evenements={[cours()]} />);
    expect(par('evenement').getAttribute('draggable')).toBe('false');
  });

  test('son menu contextuel ne propose PAS Dupliquer', async () => {
    await monter(<CampaignCalendar evenements={[cours()]} />);
    await act(async () => {
      par('evenement').dispatchEvent(new MouseEvent('contextmenu', { bubbles: true }));
    });
    expect(par('menu-modifier')).toBeTruthy();
    expect(par('menu-dupliquer')).toBeNull();
  });

  test('aucun déplacement n’est signalé pour un cours', async () => {
    const bouges = [];
    await monter(<CampaignCalendar evenements={[cours()]} onMoveEvenement={(e, d) => bouges.push([e, d])} />);
    const cible = par(`jour-${isoJour(jourDuMois(20))}`);
    await act(async () => {
      cible.dispatchEvent(new MouseEvent('drop', { bubbles: true }));
    });
    expect(bouges).toHaveLength(0);
  });
});

// ---------------------------------------------------------------------------
describe('CAL-1 — robustesse et présentation', () => {
  test('un événement sans date ne fait pas planter et n’apparaît pas', async () => {
    await monter(<CampaignCalendar evenements={[rendezVous({ starts_at: '' }), campagne()]} />);
    expect(tous('[data-testid="evenement"]').length).toBe(1);
  });

  test('une date illisible est ignorée sans crash', async () => {
    await monter(<CampaignCalendar evenements={[rendezVous({ starts_at: 'pas-une-date' })]} />);
    expect(par('calendrier')).toBeTruthy();
    expect(tous('[data-testid="evenement"]').length).toBe(0);
  });

  test('une liste vide affiche quand même le calendrier', async () => {
    await monter(<CampaignCalendar evenements={[]} />);
    expect(par('calendrier')).toBeTruthy();
    expect(par('grille')).toBeTruthy();
  });

  test('la grille ne déborde jamais horizontalement (mobile)', async () => {
    await monter(<CampaignCalendar evenements={[campagne(), rendezVous(), cours()]} />);
    expect(par('calendrier').style.maxWidth).toBe('100%');
    expect(par('calendrier').style.overflow).toBe('hidden');
    tous('[data-testid="evenement"]').forEach((e) => {
      expect(e.style.overflow).toBe('hidden');
      expect(e.style.textOverflow).toBe('ellipsis');
    });
  });

  test('les libellés de jours restent visibles en vue mois (mobile)', async () => {
    await monter(<CampaignCalendar evenements={[]} />);
    ['Lun', 'Dim'].forEach((j) => expect(conteneur.textContent).toContain(j));
  });
});

// ---------------------------------------------------------------------------
describe('CAL-1 — les couleurs de marque ne sont plus codées en dur', () => {
  const BRUT = require('fs').readFileSync(
    require('path').join(__dirname, '..', 'CampaignCalendar.js'), 'utf8');
  /* ON INSPECTE LE CODE, PAS LA PROSE. L'en-tête du fichier CITE les anciennes
     couleurs pour expliquer ce qui a été retiré — une recherche naïve mordait
     donc sur le commentaire qui dit justement qu'elles ont disparu. */
  const SOURCE = BRUT.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/[^\n]*/g, '');

  test('le fichier utilise les variables CSS du dépôt', () => {
    expect(SOURCE).toContain('var(--primary-color');
    expect(SOURCE).toContain('var(--primary-rgb');
  });

  test('la garde porte bien sur du CODE (le commentaire cite les anciennes valeurs)', () => {
    expect(BRUT).toContain('#9333ea');      // cité dans l'en-tête, à dessein
    expect(SOURCE).not.toContain('#9333ea'); // absent du code
  });

  test('les violets codés en dur ont disparu', () => {
    ['#9333ea', '#6366f1', '#c4b5fd', '139,92,246', '#1a1025'].forEach((mort) => {
      expect(SOURCE).not.toContain(mort);
    });
  });

  test('les seules couleurs fixes restantes sont SÉMANTIQUES, pas de marque', () => {
    // succès / rendez-vous / événement : elles ne dépendent pas de la marque
    // et doivent rester lisibles quelle que soit la couleur du coach.
    const hex = (SOURCE.match(/#[0-9a-fA-F]{6}/g) || [])
      .filter((h) => h !== '#D91CD2' && h.toLowerCase() !== '#fff');
    expect(hex).toEqual([]);
  });

  /* CETTE VÉRIFICATION BORNAIT CAL-1, ET ELLE AVAIT RAISON. GOOGLE-1 ajoute un
     TYPE d'événement `google` à la palette — mais afficher un type n'est pas
     dépendre de Google : le composant ne connaît ni OAuth, ni jeton, ni appel
     réseau. C'est cette distinction-là que la garde doit tenir, et elle est
     plus exigeante que la précédente. */
  test('le calendrier affiche le type google, sans en DÉPENDRE', () => {
    expect(SOURCE).toContain('google:');           // la palette, pour l'affichage
    ['oauth', 'gapi', 'accounts.google.com', 'googleapis',
     'access_token', 'refresh_token', 'client_id'].forEach((mot) => {
      expect(SOURCE).not.toContain(mot);
    });
  });

  test('un événement Google n’est jamais déplaçable', async () => {
    const g = { id: 'google:primary:g-1', source: 'google', source_id: 'g-1',
                title: 'Réunion équipe', starts_at: LE_15.toISOString(),
                event_type: 'google', status: 'confirmed', modifiable: false };
    await monter(<CampaignCalendar evenements={[g]} />);
    expect(par('evenement').getAttribute('draggable')).toBe('false');
  });

  test('il se distingue des événements Afroboost', async () => {
    const g = { id: 'google:primary:g-1', source: 'google', title: 'Réunion',
                starts_at: LE_15.toISOString(), event_type: 'google', modifiable: false };
    await monter(<CampaignCalendar evenements={[campagne(), g]} />);
    const bords = tous('[data-testid="evenement"]').map((e) => e.style.borderLeft);
    expect(new Set(bords).size).toBe(2);   // deux teintes distinctes
  });
});

// ---------------------------------------------------------------------------
// GOOGLE-2 — LA PASTILLE DE SYNCHRONISATION
//
// Elle doit dire quatre choses différentes sans encombrer une grille déjà
// dense : synchronisé, en attente, échec, et — les deux qui comptent le plus —
// « modifié dans Google » et « supprimé dans Google », qui appellent une
// décision humaine et ne doivent surtout pas passer pour un simple échec.
describe('GOOGLE-2 — l’état de synchronisation dans la grille', () => {
  const sync = (statut, extra = {}) => rendezVous({
    google: { enabled: true, status: statut, event_id: 'g-1', calendar_id: 'primary',
              last_synced_at: null, error: '', attempts: 0 },
    ...extra,
  });

  test('un événement NON synchronisé n’affiche aucune pastille', async () => {
    await monter(<CampaignCalendar evenements={[rendezVous()]} />);
    expect(tous('[data-testid^="sync-"]').length).toBe(0);
  });

  test('synchronisation demandée mais désactivée : rien non plus', async () => {
    await monter(<CampaignCalendar evenements={[rendezVous({
      google: { enabled: false, status: 'off' } })]} />);
    expect(tous('[data-testid^="sync-"]').length).toBe(0);
  });

  test('synchronisé : une pastille verte', async () => {
    await monter(<CampaignCalendar evenements={[sync('synced')]} />);
    const p = par('sync-ok');
    expect(p).toBeTruthy();
    expect(p.getAttribute('stroke')).toContain('34,197,94');
    expect(p.querySelector('title').textContent).toContain('synchronisé');
  });

  test('en attente : une pastille orange, et le mot juste', async () => {
    await monter(<CampaignCalendar evenements={[sync('pending')]} />);
    expect(par('sync-attente')).toBeTruthy();
    expect(par('sync-attente').querySelector('title').textContent).toContain('attente');
  });

  test('échec : une pastille rouge', async () => {
    await monter(<CampaignCalendar evenements={[sync('failed')]} />);
    expect(par('sync-echec')).toBeTruthy();
    expect(par('sync-echec').getAttribute('stroke')).toContain('239,68,68');
  });

  test('CONFLIT — le message parle d’arbitrage, pas d’erreur', async () => {
    await monter(<CampaignCalendar evenements={[sync('conflict')]} />);
    const t = par('sync-conflit').querySelector('title').textContent;
    expect(t).toContain('Modifié dans Google');
    expect(t.toLowerCase()).not.toContain('échec');
  });

  test('SUPPRIMÉ DANS GOOGLE — le message dit que rien n’a été recréé', async () => {
    await monter(<CampaignCalendar evenements={[sync('google_deleted')]} />);
    const t = par('sync-supprime').querySelector('title').textContent;
    expect(t).toContain('Supprimé dans Google');
    expect(t).toContain('sans votre accord');
  });

  test('reconnexion nécessaire : dit à l’utilisateur ce qu’il doit faire', async () => {
    await monter(<CampaignCalendar evenements={[sync('reconnect_required')]} />);
    expect(par('sync-reconnexion').querySelector('title').textContent)
      .toContain('reconnexion');
  });

  test('un état inconnu n’affiche RIEN plutôt qu’un symbole muet', async () => {
    await monter(<CampaignCalendar evenements={[sync('etat_de_demain')]} />);
    expect(tous('[data-testid^="sync-"]').length).toBe(0);
  });

  test('RÈGLE DU DÉPÔT — la pastille est un SVG inline, jamais un emoji', async () => {
    // Un jour DIFFÉRENT par état : la vue mois plafonne le nombre d'événements
    // affichés par case, et les empiler ici mesurerait ce plafond, pas le SVG.
    await monter(<CampaignCalendar evenements={[
      sync('synced', { starts_at: jourDuMois(4).toISOString() }),
      sync('pending', { id: 'r2', starts_at: jourDuMois(6).toISOString() }),
      sync('failed', { id: 'r3', starts_at: jourDuMois(8).toISOString() }),
      sync('conflict', { id: 'r4', starts_at: jourDuMois(10).toISOString() }),
      sync('google_deleted', { id: 'r5', starts_at: jourDuMois(12).toISOString() })]} />);
    const pastilles = tous('[data-testid^="sync-"]');
    expect(pastilles.length).toBe(5);
    pastilles.forEach((p) => expect(p.tagName.toLowerCase()).toBe('svg'));
    // Aucun caractère hors ASCII imprimable dans le rendu des pastilles.
    pastilles.forEach((p) => {
      const visible = (p.textContent || '').replace(/[\s]/g, '');
      expect(/[←-⯿\u{1F300}-\u{1FAFF}]/u.test(visible)).toBe(false);
    });
  });

  test('le titre de l’événement reste lisible à côté de la pastille', async () => {
    await monter(<CampaignCalendar evenements={[sync('synced')]} />);
    expect(par('evenement').textContent).toContain('Appel partenariat');
  });

  test('la pastille n’empêche ni le clic ni le glisser-déposer', async () => {
    const vus = [];
    await monter(<CampaignCalendar evenements={[sync('synced')]}
                                   onEvenementClick={(e) => vus.push(e.id)} />);
    await cliquer(par('evenement'));
    expect(vus).toEqual(['rdv-1']);
    expect(par('evenement').getAttribute('draggable')).toBe('true');
  });
});
