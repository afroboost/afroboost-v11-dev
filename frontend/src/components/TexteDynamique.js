// V670 — Affiche un contenu PUBLIC du coach (nom/description d'offre, nom de cours) dans la
// langue du visiteur, SANS jamais modifier l'original (cf. utils/traductionDynamique.js).
//
// Tant que la traduction n'est pas là — ou si elle échoue, ou si la langue n'est pas
// fiable pour l'IA — on affiche l'original : aucun blanc, aucun clignotement, aucune erreur.
// Une traduction affichée porte `data-traduction="auto"` et une infobulle qui rappelle
// qu'elle est automatique et donne le texte d'origine.
import React, { useEffect, useState } from 'react';
import { useLanguage } from '../contexts/LanguageContext';
import { obtenirTraduction, langueTraduisible } from '../utils/traductionDynamique';
import { t as traduire } from '../utils/i18n';

export function useTraductionDynamique(texte, lang) {
  const source = typeof texte === 'string' ? texte : '';
  const [etat, setEtat] = useState({ source: '', lang: '', texte: '', auto: false });

  useEffect(() => {
    let vivant = true;
    if (!source || !langueTraduisible(lang)) return undefined;
    obtenirTraduction(source, lang).then((r) => {
      if (vivant) setEtat({ source, lang, texte: r.texte, auto: r.auto });
    });
    return () => { vivant = false; };
  }, [source, lang]);

  // Une traduction n'est utilisée QUE pour le texte et la langue pour lesquels elle a été
  // obtenue : si la prop ou la langue change, on repasse aussitôt à l'original.
  if (etat.auto && etat.source === source && etat.lang === lang) return { texte: etat.texte, auto: true };
  return { texte, auto: false };
}

const compacter = (x) => String(x == null ? '' : x).replace(/\s+/g, ' ').trim();

/**
 * Texte que le coach PEUT modifier mais qui a une valeur PAR DÉFAUT dans le code (hero,
 * description du concept). Tant que le coach n'y a pas touché, on affiche la traduction
 * STATIQUE de ce défaut (relue, sans réseau, sans IA) ; s'il l'a personnalisé, on retombe
 * sur la traduction dynamique de SON texte. Dans tous les cas : l'original reste intact.
 */
export function useTexteCoach(texte, defaut, cleDefaut) {
  const { language, t } = useLanguage();
  const estDefaut = !!defaut && !!cleDefaut && compacter(texte) === compacter(defaut);
  const dyn = useTraductionDynamique(estDefaut ? '' : texte, language);
  if (estDefaut) return { texte: t(cleDefaut), auto: false };
  return dyn;
}

const TexteDynamique = ({ texte, as: Balise = 'span', defaut, cleDefaut, ...props }) => {
  const { language } = useLanguage();
  const r = useTexteCoach(texte, defaut, cleDefaut);
  const attributs = { ...props };
  if (r.auto) {
    attributs.title = `${traduire('v_texte_d_origine', language)} ${texte}`;
    attributs['data-traduction'] = 'auto';
  }
  return <Balise {...attributs}>{r.texte}</Balise>;
};

export default TexteDynamique;
