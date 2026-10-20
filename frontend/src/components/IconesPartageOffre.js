/**
 * V630 — « Partager » et « Copier le lien » en DEUX PETITES ICÔNES (action secondaire).
 *
 * V626 (tableau de bord) et V629 (fiche publique) les affichaient en gros boutons
 * encadrés. Mêmes fonctions (utils/partageOffre.js), même lien stable `/?offre=<id>` :
 * seule la présentation change. Pas de texte permanent — une infobulle au survol /
 * focus (CSS `.af-icone-action`, index.css), un nom accessible, une zone tactile de
 * 44 px sur téléphone, et « Lien copié » affiché discrètement après la copie.
 */
import React, { useState } from 'react';
import SvgIcon from './SvgIcon';
import { copierLienOffre, partagerOffre } from '../utils/partageOffre';

export default function IconesPartageOffre({ offre, idPartager, idCopier, idGroupe, idRetour, style }) {
  const [etat, setEtat] = useState('');
  const retour = (texte) => { setEtat(texte); setTimeout(() => setEtat((prev) => (prev === texte ? '' : prev)), 2200); };
  return (
    <div className="af-partage-icones" data-testid={idGroupe} style={style}>
      {etat ? <span role="status" className="af-partage-retour" data-testid={idRetour}>{etat}</span> : null}
      <button type="button" className="af-icone-action" data-infobulle="Partager" aria-label="Partager" data-testid={idPartager}
              onClick={async (e) => {
                e.stopPropagation();
                const r = await partagerOffre(offre);
                if (r && r.methode === 'copie') retour('Lien copié');
                else if (r && r.methode === 'whatsapp') retour(r.ok ? 'Lien copié' : 'WhatsApp ouvert');
              }}>
        <SvgIcon name="share" size={17} />
      </button>
      <button type="button" className="af-icone-action" data-infobulle="Copier le lien" aria-label="Copier le lien" data-testid={idCopier}
              onClick={async (e) => {
                e.stopPropagation();
                retour((await copierLienOffre(offre)) ? 'Lien copié' : 'Copie impossible');
              }}>
        <SvgIcon name="link" size={17} />
      </button>
    </div>
  );
}
