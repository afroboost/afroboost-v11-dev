/**
 * P0-SOCLE — LE MÉCANISME DE CHARGEMENT COMMUN.
 * =============================================
 *
 * CE QU'IL REMPLACE
 * -----------------
 * Le dépôt chargeait ses écrans avec un squelette écrit à la main, répété une
 * centaine de fois et présent dès le PREMIER commit :
 *
 *     const [x, setX] = useState([]);                 // [] veut dire « rien »
 *     useEffect(() => {
 *       Promise.all([...])                            // tout-ou-rien
 *         .then(...)
 *         .catch(e => console.error(e));              // échec muet
 *     }, []);                                         // jamais rejoué
 *
 * Trois défauts cumulés : la valeur de départ ment (0 affiché avant toute
 * réponse), l'échec est avalé, et rien ne relance. Résultat historique : deux
 * routes sur sept répondent 403, et les cinq réponses 200 sont jetées avec.
 *
 * CE QU'IL GARANTIT
 * -----------------
 *   1. `Promise.allSettled`, jamais `all` : chaque ressource réussit ou échoue
 *      SEULE. Cinq sections servies restent affichées quand deux sont refusées.
 *   2. Aucun chargement ne reste bloqué : toute clé lancée termine dans
 *      `ok`, `erreur` ou `session` — jamais en `chargement`.
 *   3. La valeur de départ n'est jamais une réponse : tant que l'état vaut
 *      `chargement`, l'écran affiche « — », pas « 0 ».
 *   4. Une requête que le serveur refusera à coup sûr ne part pas (portillon
 *      d'authentification, cf. `utils/authSession`).
 *   5. Chaque section en erreur peut être relancée SEULE, sans recharger la page.
 *
 * ANTI-BOUCLE (règle absolue du dépôt, incident V305)
 * ---------------------------------------------------
 * Les dépendances de l'effet sont exclusivement PRIMITIVES (chaînes), jamais
 * l'objet `sources` — qui est neuf à chaque rendu. Et tout `setState` compare
 * avant d'écrire : si rien n'a changé, on renvoie `prev` à l'identique.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  AUTH,
  etatAuth,
  classerEchec,
  signatureRequise,
  abonnerAuth,
} from '../utils/authSession';

/** État d'UNE section. */
export const SECTION = {
  ATTENTE: 'attente', // pas encore demandée (onglet fermé, écran inactif)
  CHARGEMENT: 'chargement',
  OK: 'ok',
  ERREUR: 'erreur',
  SESSION: 'session', // refusée faute de preuve d'authentification valable
};

/** État de l'ÉCRAN, déduit de ses sections. */
export const GLOBAL = {
  ATTENTE: 'attente',
  CHARGEMENT: 'chargement',
  OK: 'ok',
  PARTIEL: 'partiel', // au moins une réussie ET au moins une en échec
  ERREUR: 'erreur',
  SESSION_EXPIREE: 'session_expiree',
};

/** Délai avant l'unique relance automatique d'un échec RÉSEAU. */
const DELAI_RELANCE_RESEAU = 800;

/** Separateur de cles : un caractere de controle, impossible dans un nom de cle. */
const SEP = '\u0001';

export function reduireGlobal(sections) {
  const valeurs = Object.keys(sections).map((cle) => sections[cle]);
  if (!valeurs.length) return GLOBAL.OK;
  if (valeurs.some((s) => s.etat === SECTION.CHARGEMENT)) return GLOBAL.CHARGEMENT;

  const finies = valeurs.filter((s) => s.etat !== SECTION.ATTENTE);
  if (!finies.length) return GLOBAL.ATTENTE;

  if (finies.every((s) => s.etat === SECTION.SESSION)) return GLOBAL.SESSION_EXPIREE;
  if (finies.every((s) => s.etat === SECTION.ERREUR || s.etat === SECTION.SESSION)) {
    return GLOBAL.ERREUR;
  }
  if (finies.some((s) => s.etat !== SECTION.OK)) return GLOBAL.PARTIEL;
  return GLOBAL.OK;
}

function etatInitial(cles, actif) {
  const depart = {};
  cles.forEach((cle) => {
    depart[cle] = {
      etat: actif ? SECTION.CHARGEMENT : SECTION.ATTENTE,
      motif: '',
      donnees: undefined,
    };
  });
  return depart;
}

/** Applique un correctif partiel à un sous-ensemble de clés, sans rien perdre. */
function fusionner(sections, cles, correctif) {
  if (!cles || !cles.length) return sections;
  const suivant = Object.assign({}, sections);
  cles.forEach((cle) => {
    suivant[cle] = Object.assign(
      { etat: SECTION.ATTENTE, motif: '', donnees: undefined },
      suivant[cle],
      correctif
    );
  });
  return suivant;
}

function identiques(a, b) {
  const clesA = Object.keys(a);
  const clesB = Object.keys(b);
  if (clesA.length !== clesB.length) return false;
  for (let i = 0; i < clesA.length; i += 1) {
    const cle = clesA[i];
    const x = a[cle];
    const y = b[cle];
    if (!y || x.etat !== y.etat || x.motif !== y.motif || x.donnees !== y.donnees) return false;
  }
  return true;
}

function estProtegee(descripteur) {
  if (!descripteur) return false;
  if (descripteur.signature === true) return true;
  if (descripteur.signature === false) return false;
  return signatureRequise(descripteur.url);
}

function extraire(descripteur, valeur) {
  if (descripteur && typeof descripteur.extraire === 'function') return descripteur.extraire(valeur);
  if (valeur && typeof valeur === 'object' && 'data' in valeur) return valeur.data;
  return valeur;
}

/**
 * @param {Object} sources  { cle: { url, appel, signature?, extraire? } }
 *                          `url` sert au portillon ; `appel` renvoie une promesse.
 * @param {Object} [options] { deps: [primitives], actif: bool, surSessionInvalide: fn }
 */
export default function useChargement(sources, options) {
  const opts = options || {};
  const actif = opts.actif !== false;
  const deps = opts.deps || [];

  // `sources` et `options` sont neufs à chaque rendu : on les garde dans des
  // refs pour ne JAMAIS les mettre en dépendance d'un effet (règle anti-boucle).
  const sourcesRef = useRef(sources);
  sourcesRef.current = sources;
  const optsRef = useRef(opts);
  optsRef.current = opts;

  const clesJointes = Object.keys(sources).join(SEP);
  const cles = useMemo(() => (clesJointes ? clesJointes.split(SEP) : []), [clesJointes]);

  const [sections, setSections] = useState(() => etatInitial(Object.keys(sources), actif));

  const sectionsRef = useRef(sections);
  sectionsRef.current = sections;

  const vivant = useRef(true);
  const minuteries = useRef([]);
  // Cles dont une requete est REELLEMENT en vol. Indispensable pour distinguer
  // « en cours de chargement » de « parque en attendant que l'auth soit connue » :
  // sans cette distinction, une section mise en attente pendant AUTH EN_COURS ne
  // repartait jamais et restait en « chargement » — un loader infini.
  const enVol = useRef({});
  useEffect(() => {
    vivant.current = true;
    const enCours = minuteries.current;
    return () => {
      vivant.current = false;
      enCours.forEach((id) => clearTimeout(id));
      enCours.length = 0;
    };
  }, []);

  const majSections = useCallback((transformation) => {
    if (!vivant.current) return;
    setSections((prec) => {
      const suivant = transformation(prec);
      return identiques(prec, suivant) ? prec : suivant;
    });
  }, []);

  const executer = useCallback(
    async (clesDemandees, autoriserRelance) => {
      const source = sourcesRef.current;
      const liste = (clesDemandees || Object.keys(source)).filter((cle) => source[cle]);
      if (!liste.length) return;

      const auth = etatAuth();

      // (1) AUTH EN COURS — on ne conclut pas, on attend. La requête partirait
      //     sans jeton et récolterait un 403 purement mécanique. L'abonnement
      //     `abonnerAuth` ci-dessous la relancera dès que l'état sera connu.
      if (auth === AUTH.EN_COURS) {
        majSections((prec) => fusionner(prec, liste, { etat: SECTION.CHARGEMENT, motif: '' }));
        return;
      }

      // (2) PORTILLON — une requête dont le serveur exige la signature ne part
      //     pas sans preuve signée. On ne contourne rien : on évite un aller-
      //     retour dont on connaît déjà le verdict, et on l'annonce honnêtement
      //     (« session » et non « erreur »).
      const bloquees = [];
      const aLancer = [];
      liste.forEach((cle) => {
        if (estProtegee(source[cle]) && auth !== AUTH.VALIDE) bloquees.push(cle);
        else aLancer.push(cle);
      });

      majSections((prec) => {
        let suivant = fusionner(prec, bloquees, { etat: SECTION.SESSION, motif: 'session' });
        suivant = fusionner(suivant, aLancer, { etat: SECTION.CHARGEMENT, motif: '' });
        return suivant;
      });

      if (!aLancer.length) return;

      aLancer.forEach((cle) => { enVol.current[cle] = true; });

      let resultats = null;
      try {
        // `allSettled` : une branche rejetée n'emporte plus les autres.
        resultats = await Promise.allSettled(
          aLancer.map((cle) => Promise.resolve().then(() => source[cle].appel()))
        );
      } finally {
        aLancer.forEach((cle) => { delete enVol.current[cle]; });
        // FILET DE SÉCURITÉ. Si quoi que ce soit d'imprévu remonte ici, aucune
        // clé ne doit rester en « chargement » — c'est la promesse n° 2.
        if (!resultats) {
          majSections((prec) => fusionner(prec, aLancer, { etat: SECTION.ERREUR, motif: 'serveur' }));
        }
      }

      if (!vivant.current || !resultats) return;

      // (3) ESCALADE — distinguer le cas A du cas B.
      //     Si TOUTES les requêtes à signature obligatoire ont été refusées en
      //     401/403, ce n'est pas « cette ressource-là » qui est en cause : c'est
      //     la preuve d'authentification elle-même, même si le jeton PARAISSAIT
      //     valide côté navigateur (secret changé, compte révoqué...).
      const refusAuth = {};
      aLancer.forEach((cle, i) => {
        const r = resultats[i];
        if (r.status === 'rejected') {
          const statut = r.reason && r.reason.response && r.reason.response.status;
          refusAuth[cle] = statut === 401 || statut === 403;
        }
      });
      const protegees = aLancer.filter((cle) => estProtegee(source[cle]));
      const escalade = protegees.length > 0 && protegees.every((cle) => refusAuth[cle] === true);

      const aRelancerReseau = [];

      majSections((prec) => {
        const suivant = Object.assign({}, prec);
        aLancer.forEach((cle, i) => {
          const r = resultats[i];
          const precedent = prec[cle] || {};
          if (r.status === 'fulfilled') {
            suivant[cle] = {
              etat: SECTION.OK,
              motif: '',
              donnees: extraire(source[cle], r.value),
            };
            return;
          }
          let motif = classerEchec(r.reason);
          if (escalade && refusAuth[cle]) motif = 'session';
          if (motif === 'reseau') aRelancerReseau.push(cle);
          suivant[cle] = {
            etat: motif === 'session' ? SECTION.SESSION : SECTION.ERREUR,
            motif,
            // On CONSERVE les données déjà obtenues : un échec de rafraîchissement
            // ne doit pas effacer ce que le coach avait sous les yeux.
            donnees: precedent.donnees,
          };
        });
        return suivant;
      });

      if (escalade && typeof optsRef.current.surSessionInvalide === 'function') {
        optsRef.current.surSessionInvalide();
      }

      // (4) UNE SEULE relance automatique, et uniquement sur échec RÉSEAU.
      //     C'est ce qui absorbe les coupures de conteneur mesurées à 1-2 %
      //     (V320) sans jamais boucler : les 4xx ne sont JAMAIS relancés, et la
      //     relance elle-même ne se relance pas (`autoriserRelance` à false).
      if (autoriserRelance !== false && aRelancerReseau.length) {
        const id = setTimeout(() => {
          if (vivant.current) executer(aRelancerReseau, false);
        }, DELAI_RELANCE_RESEAU);
        minuteries.current.push(id);
      }
    },
    [majSections]
  );

  const signatureDeps = deps
    .map((d) => (d === null || d === undefined ? '' : String(d)))
    .join(SEP);

  useEffect(() => {
    if (!actif) {
      majSections((prec) => fusionner(prec, Object.keys(sourcesRef.current), { etat: SECTION.ATTENTE }));
      return;
    }
    executer(null, true);
    // Dépendances volontairement PRIMITIVES : `sources` (objet neuf à chaque
    // rendu) déclencherait une boucle d'appels — interdit dans ce dépôt.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [actif, signatureDeps, clesJointes, executer, majSections]);

  // Quand l'authentification redevient valable (fin de connexion, reconnexion),
  // on relance UNIQUEMENT les sections refusées pour cause de session.
  // DES QUE L'ETAT D'AUTHENTIFICATION REDEVIENT CONNU, on rejoue :
  //   - les sections refusees faute de preuve (reconnexion reussie) ;
  //   - les sections PARQUEES pendant AUTH EN_COURS, c'est-a-dire affichees en
  //     « chargement » alors qu'aucune requete n'est en vol. Sans cette seconde
  //     famille, une connexion en cours au montage laissait l'ecran tourner
  //     indefiniment — le loader infini que ce lot supprime.
  useEffect(
    () =>
      abonnerAuth((info) => {
        if (info.etat === AUTH.EN_COURS) return; // toujours indetermine
        const aRelancer = Object.keys(sectionsRef.current).filter((cle) => {
          const etat = sectionsRef.current[cle].etat;
          if (etat === SECTION.SESSION) return true;
          return etat === SECTION.CHARGEMENT && !enVol.current[cle];
        });
        if (aRelancer.length) executer(aRelancer, true);
      }),
    [executer]
  );

  const reessayer = useCallback((cle) => executer(cle ? [cle] : null, true), [executer]);

  const donnees = useMemo(() => {
    const carte = {};
    Object.keys(sections).forEach((cle) => {
      carte[cle] = sections[cle].donnees;
    });
    return carte;
  }, [sections]);

  const global = useMemo(() => reduireGlobal(sections), [sections]);

  return {
    global,
    sections,
    donnees,
    reessayer,
    cles,
    chargement: global === GLOBAL.CHARGEMENT,
    sessionExpiree: global === GLOBAL.SESSION_EXPIREE,
  };
}
