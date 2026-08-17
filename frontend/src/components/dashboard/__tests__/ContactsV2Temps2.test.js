/**
 * CONTACTS V2 — temps 2 : carte mobile, fiche contact, tri, pays.
 *
 * Le dépôt n'a aucune media query : la responsivité passe par la largeur lue,
 * ce qui la rend testable — on peut vraiment vérifier 375, 390, 430 et desktop.
 */
import React from 'react';
import { createRoot } from 'react-dom/client';
import CarteContact from '../CarteContact';
import FicheContact from '../FicheContact';
import PanneauFiltresContacts from '../PanneauFiltresContacts';
import { trierContacts, paysPresents, libelleType, libelleStatut, libelleZone } from '../../../utils/contactsAffichage';
import { FILTRES_VIDES, filtrerContacts } from '../../../utils/contactsFiltres';

global.IS_REACT_ACT_ENVIRONMENT = true;
const act = React.act;

const MARIE = {
  id: 'c1', name: 'Marie Dupont', email: 'marie@x.io', whatsapp: '+41791234567',
  contact_type: 'participant', statut_abonnement: 'actif', zone: 'suisse', pays: 'CH',
  source: 'chat_login', created_at: '2026-03-01',
  canaux: { email: true, whatsapp: true, telephone: true },
  consentement: { email: 'autorise', whatsapp: 'inconnu' },
};
const ANON = {
  id: 'c2', name: 'Zoé Martin', email: '', whatsapp: '',
  contact_type: null, statut_abonnement: 'non_abonne', zone: 'inconnue', pays: null,
  source: 'firebase-app', created_at: '2026-07-01',
  canaux: { email: false, whatsapp: false, telephone: false },
  consentement: { email: 'inconnu', whatsapp: 'inconnu' },
};

let conteneur = null;
let racine = null;

async function monter(el) {
  conteneur = document.createElement('div');
  document.body.appendChild(conteneur);
  racine = createRoot(conteneur);
  await act(async () => { racine.render(el); });
}
afterEach(async () => {
  if (racine) await act(async () => { racine.unmount(); });
  if (conteneur) conteneur.remove();
  racine = null; conteneur = null;
});
const par = (id) => conteneur.querySelector(`[data-testid="${id}"]`);
const texte = () => conteneur.textContent;
async function cliquer(el) {
  await act(async () => { el.dispatchEvent(new MouseEvent('click', { bubbles: true })); });
}

describe('CONTACTS V2 temps 2 — carte mobile', () => {
  test('M1. cinq informations, dans l’ordre : identité, relation, statut, zone, canaux', async () => {
    await monter(<CarteContact contact={MARIE} />);
    expect(par('carte-contact')).not.toBeNull();
    expect(texte()).toMatch(/Marie Dupont[\s\S]*Participant[\s\S]*Abonné actif[\s\S]*Suisse[\s\S]*Email[\s\S]*WhatsApp/);
  });

  test('M2. la source technique ne pollue PAS la carte', async () => {
    await monter(<CarteContact contact={MARIE} />);
    expect(texte()).not.toMatch(/chat_login|firebase-app|c1/);
  });

  test('M3. chaque état porte du TEXTE, jamais une couleur seule', async () => {
    await monter(<CarteContact contact={ANON} />);
    expect(texte()).toMatch(/Non classé/);
    expect(texte()).toMatch(/Non abonné/);
    expect(texte()).toMatch(/Zone inconnue/);
  });

  test('M4. un non classé propose « Classer » sans ouvrir la fiche', async () => {
    const classer = jest.fn();
    await monter(<CarteContact contact={ANON} onClasser={classer} />);
    expect(par('classer-c2')).not.toBeNull();
    // Ouvrir la liste ne doit RIEN envoyer : seul un choix explicite écrit.
    expect(classer).not.toHaveBeenCalled();
    const sel = par('classer-c2');
    const poser = Object.getOwnPropertyDescriptor(window.HTMLSelectElement.prototype, 'value').set;
    await act(async () => {
      poser.call(sel, 'participant');
      sel.dispatchEvent(new Event('change', { bubbles: true }));
    });
    expect(classer).toHaveBeenCalledWith('c2', 'participant');
  });

  test('M5. un contact déjà classé n’affiche pas « Classer »', async () => {
    await monter(<CarteContact contact={MARIE} />);
    expect(par('classer-c1')).toBeNull();
  });

  test('M6. cibles tactiles ≥ 40 px', async () => {
    await monter(<CarteContact contact={ANON} onClasser={() => {}} />);
    expect(parseInt(par('ouvrir-c2').style.minHeight, 10)).toBeGreaterThanOrEqual(40);
    expect(parseInt(par('classer-c2').style.minHeight, 10)).toBeGreaterThanOrEqual(40);
    // 16 px : en dessous, iOS zoome sur le champ à l'ouverture du menu.
    expect(par('classer-c2').style.fontSize).toBe('16px');
  });
});

describe('CONTACTS V2 temps 2 — fiche contact', () => {
  test('P1. les quatre sections sont là', async () => {
    await monter(<FicheContact contact={MARIE} estMobile />);
    expect(texte()).toMatch(/Identité[\s\S]*Afroboost[\s\S]*Canaux disponibles[\s\S]*Consentement marketing/);
  });

  test('P2. « Inconnu » ne devient JAMAIS « Autorisé »', async () => {
    await monter(<FicheContact contact={MARIE} estMobile />);
    expect(par('consent-email').textContent).toBe('Autorisé');
    expect(par('consent-whatsapp').textContent).toBe('Inconnu');
  });

  test('P3. la fiche dit que canal ≠ autorisation', async () => {
    await monter(<FicheContact contact={MARIE} estMobile />);
    expect(texte()).toMatch(/n'autorise pas à l'utiliser pour une campagne/);
  });

  test('P4. une donnée absente est dite absente, pas inventée', async () => {
    await monter(<FicheContact contact={ANON} estMobile />);
    expect(texte()).toMatch(/Non renseigné/);
    expect(texte()).toMatch(/Zone inconnue/);
  });

  test('P5. plein écran sur mobile, panneau latéral sur desktop', async () => {
    await monter(<FicheContact contact={MARIE} estMobile />);
    const inner = par('fiche-contact').firstChild;
    expect(inner.style.width).toBe('100%');
    await act(async () => { racine.render(<FicheContact contact={MARIE} estMobile={false} />); });
    expect(par('fiche-contact').firstChild.style.width).toBe('440px');
    expect(par('fiche-contact').firstChild.style.maxWidth).toBe('100%');
  });

  test('P6. fermeture par ✕ et par clic extérieur', async () => {
    const fermer = jest.fn();
    await monter(<FicheContact contact={MARIE} estMobile onFermer={fermer} />);
    await cliquer(par('fiche-fermer'));
    await cliquer(par('fiche-contact'));
    expect(fermer).toHaveBeenCalledTimes(2);
  });

  test('P7. aucun contact → rien du tout', async () => {
    await monter(<FicheContact contact={null} estMobile />);
    expect(conteneur.textContent).toBe('');
  });
});

describe('CONTACTS V2 temps 2 — tri et pays', () => {
  const L = [
    { name: 'Zoé', created_at: '2026-01-01', statut_abonnement: 'non_abonne' },
    { name: 'alice', created_at: '2026-07-01', statut_abonnement: 'ancien' },
    { name: 'Marie', created_at: '2026-03-01', statut_abonnement: 'actif' },
  ];
  const noms = (l) => l.map((x) => x.name);

  test('T1. nom A-Z insensible à la casse', () => {
    expect(noms(trierContacts(L, 'nom_az'))).toEqual(['alice', 'Marie', 'Zoé']);
  });
  test('T2. nom Z-A', () => {
    expect(noms(trierContacts(L, 'nom_za'))).toEqual(['Zoé', 'Marie', 'alice']);
  });
  test('T3. plus récent / plus ancien', () => {
    expect(noms(trierContacts(L, 'recent'))).toEqual(['alice', 'Marie', 'Zoé']);
    expect(noms(trierContacts(L, 'ancien'))).toEqual(['Zoé', 'Marie', 'alice']);
  });
  test('T4. abonnés d’abord, puis actifs avant anciens', () => {
    expect(noms(trierContacts(L, 'abonnes'))).toEqual(['Marie', 'alice', 'Zoé']);
  });
  test('T5. trier ne modifie pas la liste d’origine', () => {
    const avant = noms(L);
    trierContacts(L, 'nom_za');
    expect(noms(L)).toEqual(avant);
  });

  test('Y1. seuls les pays réellement présents sont proposés, comptés', () => {
    const p = paysPresents([MARIE, MARIE, ANON, { pays: 'CM' }]);
    expect(p.map((x) => x.code)).toEqual(['CH', 'CM']);
    expect(p[0].n).toBe(2);
    expect(p[0].nom).toBe('Suisse');
    expect(p.find((x) => x.code === 'CM').nom).toBe('Cameroun');
  });

  test('Y2. le pays PRÉCISE la zone sans la remplacer', () => {
    const tous = [MARIE, { ...MARIE, id: 'c9', pays: 'CM', zone: 'afrique' }];
    expect(filtrerContacts(tous, { ...FILTRES_VIDES, pays: ['CM'] }, '')).toHaveLength(1);
    expect(filtrerContacts(tous, { ...FILTRES_VIDES, zones: ['afrique'] }, '')).toHaveLength(1);
    expect(filtrerContacts(tous, { ...FILTRES_VIDES, pays: ['CH', 'CM'] }, '')).toHaveLength(2);
  });

  test('Y3. libellés lisibles pour tous les états', () => {
    expect(libelleType({})).toBe('Non classé');
    expect(libelleStatut({})).toBe('Non abonné');
    expect(libelleZone({})).toBe('Zone inconnue');
    expect(libelleZone({ pays: 'SN' })).toBe('Sénégal');
  });
});

describe('CONTACTS V2 temps 2 — panneau de filtres', () => {
  test('B1. le bouton d’action annonce le nombre de résultats', async () => {
    await monter(<PanneauFiltresContacts ouvert filtres={FILTRES_VIDES}
      nbResultats={42} onChange={() => {}} onFermer={() => {}} />);
    expect(par('filtres-appliquer').textContent).toBe('Voir 42 contacts');
  });

  test('B2. les pays présents apparaissent en section propre', async () => {
    await monter(<PanneauFiltresContacts ouvert filtres={FILTRES_VIDES}
      pays={[{ code: 'CM', nom: 'Cameroun', drapeau: '🇨🇲', n: 19 }]}
      onChange={() => {}} onFermer={() => {}} />);
    expect(texte()).toMatch(/Cameroun \(19\)/);
    expect(par('filtre-pays-CM')).not.toBeNull();
  });

  test('B3. canal et consentement restent deux sections distinctes', async () => {
    await monter(<PanneauFiltresContacts ouvert filtres={FILTRES_VIDES}
      onChange={() => {}} onFermer={() => {}} />);
    expect(texte()).toMatch(/Canal disponible/);
    expect(texte()).toMatch(/Consentement e-mail/);
    expect(texte()).toMatch(/Le canal existe. Cela ne signifie pas qu'une campagne est autorisée/);
  });

  test('B4. « Réinitialiser » vide toutes les dimensions', async () => {
    const onChange = jest.fn();
    await monter(<PanneauFiltresContacts ouvert filtres={{ ...FILTRES_VIDES, types: ['participant'] }}
      onChange={onChange} onFermer={() => {}} />);
    await cliquer(par('filtres-reinitialiser'));
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ types: [], zones: [], pays: [] }));
  });

  test('B5. feuille montante : ancrée en bas, hauteur bornée, défilement interne', async () => {
    await monter(<PanneauFiltresContacts ouvert filtres={FILTRES_VIDES}
      onChange={() => {}} onFermer={() => {}} />);
    const fond = par('panneau-filtres');
    expect(fond.style.alignItems).toBe('flex-end');
    const feuille = fond.firstChild;
    expect(feuille.style.maxHeight).toBe('85vh');
    expect(feuille.style.overflowY).toBe('auto');
    expect(feuille.style.maxWidth).toBe('560px');
  });
});
