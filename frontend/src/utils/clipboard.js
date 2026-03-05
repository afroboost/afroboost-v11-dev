/**
 * clipboard.js - Fonction utilitaire robuste pour copier du texte
 *
 * Gère le fallback pour les navigateurs mobiles (Android/iOS)
 * où navigator.clipboard n'est pas disponible ou échoue silencieusement.
 *
 * Stratégie :
 * 1. Essayer navigator.clipboard.writeText (API moderne)
 * 2. Fallback via textarea + document.execCommand('copy')
 * 3. Retourner un objet { success, method } pour le feedback UI
 */

/**
 * Copie du texte dans le presse-papiers avec fallback mobile robuste.
 * @param {string} text - Le texte à copier
 * @returns {Promise<{success: boolean, method: string}>}
 */
export async function copyToClipboard(text) {
  // Tentative 1 : API Clipboard moderne (HTTPS requis)
  if (navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
    try {
      await navigator.clipboard.writeText(text);
      return { success: true, method: 'clipboard' };
    } catch (err) {
      // Certains navigateurs mobiles lèvent une erreur même si l'API existe
      console.warn('[CLIPBOARD] API moderne échouée, fallback execCommand:', err);
    }
  }

  // Tentative 2 : Fallback textarea + execCommand (compatibilité maximale)
  try {
    const textarea = document.createElement('textarea');
    textarea.value = text;

    // Styles pour rendre invisible sans casser le layout mobile
    textarea.style.position = 'fixed';
    textarea.style.left = '-9999px';
    textarea.style.top = '-9999px';
    textarea.style.opacity = '0';
    textarea.style.fontSize = '16px'; // Évite le zoom auto sur iOS

    document.body.appendChild(textarea);
    textarea.focus();
    textarea.select();

    // Sur iOS, il faut utiliser setSelectionRange
    textarea.setSelectionRange(0, textarea.value.length);

    const copied = document.execCommand('copy');
    document.body.removeChild(textarea);

    if (copied) {
      return { success: true, method: 'execCommand' };
    }
  } catch (err) {
    console.warn('[CLIPBOARD] Fallback execCommand échoué:', err);
  }

  // Aucune méthode n'a fonctionné
  return { success: false, method: 'none' };
}

export default copyToClipboard;
