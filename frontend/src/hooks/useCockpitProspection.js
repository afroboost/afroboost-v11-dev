/**
 * V587c — l'état du cockpit Campagnes → Prospection, en UN seul endroit.
 *
 * UNE SEULE SOURCE DE VÉRITÉ pour la vue affichée : `vuePilote`.
 *   - '' tant que rien n'a été choisi : l'écran Prospection garde son choix par
 *     défaut (les réponses s'il y en a, la liste sinon) ;
 *   - un clic sur une section (`choisir`) ou une DEMANDE ponctuelle de l'écran
 *     (`demander`, conversation ciblée par une notification) la change ;
 *   - rien d'autre ne la réécrit — en particulier JAMAIS `surEtat`.
 *
 * `surEtat` reçoit de l'écran des valeurs PRIMITIVES (vue réellement affichée,
 * nb de conversations, total) qui ne servent qu'à l'AFFICHAGE (surlignage,
 * compteurs). Elles ne repartent jamais vers l'écran : aucun cycle possible.
 * V587b synchronisait dans les deux sens → boucle de rendu infinie au remontage.
 */
import { useCallback, useState } from 'react';

export default function useCockpitProspection() {
  const [vuePilote, setVuePilote] = useState('');
  const [vueActive, setVueActive] = useState('');
  const [nbConversations, setNbConversations] = useState(null);
  const [total, setTotal] = useState(null);

  const choisir = useCallback((vue) => { if (vue) setVuePilote(vue); }, []);
  const demander = useCallback((vue) => { if (vue) setVuePilote(vue); }, []);
  const surEtat = useCallback((vue, nbConv, tot) => {
    setVueActive(vue || '');
    setNbConversations(typeof nbConv === 'number' ? nbConv : null);
    setTotal(typeof tot === 'number' ? tot : null);
  }, []);

  return { vuePilote, vueActive, nbConversations, total, choisir, demander, surEtat };
}
