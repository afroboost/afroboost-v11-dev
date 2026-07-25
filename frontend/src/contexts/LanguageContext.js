// V277 : Contexte de langue pour l'interface VISITEUR.
//
// Source UNIQUE de vérité : l'état `lang` d'App.js est fourni comme `value` du
// Provider (voir App.js). Ce fichier n'introduit donc PAS son propre état — il
// évite ainsi le double-état qui cassait les versions précédentes. N'importe
// quel composant descendant peut lire la langue via `useLanguage()` sans qu'on
// ait à faire descendre `lang` en prop partout.
import { createContext, useContext } from 'react';
import { translations } from '../utils/i18n';

export const LanguageContext = createContext(null);

// Repli utilisé UNIQUEMENT hors Provider (ne devrait pas arriver en prod) :
// français, changement de langue neutre. Jamais de crash, jamais de clé brute.
const _fallback = {
  language: 'fr',
  setLanguage: () => {},
  t: (key) => (translations.fr && translations.fr[key]) || key,
};

export function useLanguage() {
  return useContext(LanguageContext) || _fallback;
}

export default LanguageContext;
