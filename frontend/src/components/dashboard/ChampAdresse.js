// U1b — CHAMP ADRESSE AVEC SUGGESTIONS.
//
// CE QUE CE COMPOSANT EST : un `<input type="text">` ORDINAIRE, auquel on a
// ajoute une liste de propositions. Rien de plus.
//
// CE QU'IL N'EST PAS : un selecteur. Le coach peut taper ce qu'il veut, avant,
// pendant et apres avoir choisi une proposition. Plusieurs lieux reels de la
// production ne sont PAS des adresses postales (« Salle Afroboost », « Plage
// Est de St-Blaise - La Torpille ») : les imposer dans un menu deroulant
// rendrait ces offres inmodifiables.
//
// REGLE DE PANNE : si Nominatim est injoignable, lent, ou repond n'importe
// quoi, ce champ se comporte EXACTEMENT comme l'input qu'il remplace. Pas de
// message d'erreur, pas de bandeau rouge, pas de blocage : la liste reste
// simplement vide. `chercherAdresses` ne rejette jamais (cf. adresseNominatim).
//
// AUCUN NOUVEAU CHAMP DE DONNEES. La valeur reste une chaine de texte, ecrite
// dans le champ que le parent lui designe (`location` de l'offre, ou
// `locationName` de l'horaire).

import React, { useEffect, useRef, useState } from 'react';
import SvgIcon from '../SvgIcon';
import {
  chercherAdresses,
  nettoyerTexte,
  LONGUEUR_MIN,
  DELAI_DEBOUNCE_MS,
  INTERVALLE_MINI_MS
} from '../../utils/adresseNominatim';

const PANNEAU_STYLE = {
  position: 'absolute',
  top: '100%',
  left: 0,
  right: 0,
  zIndex: 50,
  marginTop: '4px',
  maxHeight: '220px',
  overflowY: 'auto',
  overflowX: 'hidden',
  background: 'rgba(10,10,15,0.98)',
  border: '1px solid rgba(var(--primary-rgb, 217, 28, 210), 0.35)',
  borderRadius: '8px',
  boxShadow: '0 8px 24px rgba(0,0,0,0.55)'
};

function styleOption(actif) {
  return {
    display: 'flex',
    alignItems: 'flex-start',
    gap: '8px',
    width: '100%',
    minHeight: '44px', // cible tactile confortable sur telephone
    padding: '10px 12px',
    textAlign: 'left',
    background: actif ? 'rgba(var(--primary-rgb, 217, 28, 210), 0.16)' : 'none',
    border: 'none',
    borderRadius: '6px',
    color: 'rgba(255,255,255,0.92)',
    cursor: 'pointer',
    // Une adresse longue passe a la ligne au lieu d'elargir le panneau : c'est
    // ce qui garantit l'absence de debordement horizontal sur mobile.
    whiteSpace: 'normal',
    wordBreak: 'break-word'
  };
}

export default function ChampAdresse({
  value,
  onChange,
  placeholder,
  style,
  className,
  classNameConteneur,
  testId,
  ariaLabel,
  fetchImpl // injecte par les bancs de test ; en production, `fetch` global
}) {
  const [suggestions, setSuggestions] = useState([]);
  const [ouvert, setOuvert] = useState(false);
  const [actif, setActif] = useState(-1);
  // `recherche === null` signifie « aucune recherche demandee » : c'est l'etat
  // a l'ouverture du wizard et juste apres un choix. Sans ce marqueur, ouvrir
  // une offre existante declencherait une requete non sollicitee, et choisir
  // une proposition en declencherait une autre sur le texte qu'on vient de
  // poser.
  const [recherche, setRecherche] = useState(null);
  const dernierAppel = useRef(0);

  useEffect(() => {
    if (recherche === null) return undefined;
    const texte = nettoyerTexte(recherche);
    if (texte.length < LONGUEUR_MIN) {
      setSuggestions([]);
      setOuvert(false);
      return undefined;
    }

    let annule = false;
    const controleur = typeof AbortController === 'function' ? new AbortController() : null;
    // Debounce + intervalle minimal : au plus une requete par seconde emise.
    const attente = Math.max(
      DELAI_DEBOUNCE_MS,
      INTERVALLE_MINI_MS - (Date.now() - dernierAppel.current)
    );
    const minuteur = setTimeout(() => {
      dernierAppel.current = Date.now();
      chercherAdresses(texte, { controleur, fetchImpl }).then((liste) => {
        if (annule) return;
        setSuggestions(liste);
        setActif(-1);
        setOuvert(liste.length > 0);
      });
    }, attente);

    return () => {
      annule = true;
      clearTimeout(minuteur);
      // Requete en vol annulee : le coach a continue de taper, sa reponse ne
      // nous interesse plus (et Nominatim n'a pas a la finir).
      if (controleur) { try { controleur.abort(); } catch (e) { /* sans effet */ } }
    };
  }, [recherche, fetchImpl]);

  const fermer = () => { setOuvert(false); setActif(-1); };

  const choisir = (item) => {
    if (!item) return;
    onChange(item.libelle);
    setRecherche(null); // le texte pose ne relance PAS de recherche
    setSuggestions([]);
    fermer();
  };

  const surTouche = (e) => {
    if (!ouvert || suggestions.length === 0) return;
    if (e.key === 'Escape') {
      // On absorbe la touche : sinon elle refermerait le wizard entier alors
      // que le coach voulait seulement faire disparaitre la liste.
      e.preventDefault();
      e.stopPropagation();
      fermer();
      return;
    }
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActif((i) => (i + 1) % suggestions.length);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActif((i) => (i <= 0 ? suggestions.length - 1 : i - 1));
    } else if (e.key === 'Enter' && actif >= 0) {
      // Enter ne vaut choix QUE si une proposition est surlignee : sinon le
      // coach valide sa saisie libre, et rien ne doit la remplacer.
      e.preventDefault();
      choisir(suggestions[actif]);
    }
  };

  return (
    <div
      className={classNameConteneur}
      style={{ position: 'relative', width: '100%' }}
    >
      <input
        type="text"
        value={value || ''}
        onChange={(e) => { onChange(e.target.value); setRecherche(e.target.value); }}
        onFocus={() => { if (suggestions.length > 0) setOuvert(true); }}
        onBlur={fermer}
        onKeyDown={surTouche}
        placeholder={placeholder}
        aria-label={ariaLabel}
        aria-autocomplete="list"
        aria-expanded={ouvert}
        autoComplete="off"
        style={style}
        className={className}
        data-testid={testId}
      />
      {ouvert && suggestions.length > 0 && (
        <div
          role="listbox"
          style={PANNEAU_STYLE}
          data-testid={testId ? `${testId}-suggestions` : 'adresse-suggestions'}
          // `mousedown` par defaut donnerait le blur AVANT le click, et le
          // panneau disparaitrait sans que le choix soit pris en compte.
          onMouseDown={(e) => e.preventDefault()}
        >
          {suggestions.map((s, i) => (
            <button
              key={s.cle}
              type="button"
              role="option"
              aria-selected={i === actif}
              onClick={() => choisir(s)}
              onMouseEnter={() => setActif(i)}
              style={styleOption(i === actif)}
              data-testid={testId ? `${testId}-suggestion-${i}` : undefined}
            >
              <span style={{ color: 'var(--primary-color, #D91CD2)', flexShrink: 0, marginTop: '2px' }}>
                <SvgIcon name="mapPin" size={14} />
              </span>
              <span style={{ minWidth: 0 }}>
                <span className="text-sm" style={{ display: 'block' }}>{s.libelle}</span>
                {s.detail && (
                  <span className="text-xs" style={{ display: 'block', color: 'rgba(255,255,255,0.45)' }}>
                    {s.detail}
                  </span>
                )}
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
