// V670 — Texte traduit contenant des mots en GRAS : « Appuyez sur les **3 points ⋮** en
// haut à droite ». Une phrase n'a pas le même ordre des mots d'une langue à l'autre :
// la traduire fragment par fragment (avant / gras / après) fabrique des phrases
// hybrides. La clé de traduction porte donc la PHRASE ENTIÈRE, avec `**` autour du
// gras, et c'est ce composant qui la rend.
//
// Aucun `dangerouslySetInnerHTML` : le texte est découpé, jamais interprété comme HTML.
import React from 'react';

/** Découpe « a **b** c » en [{ gras:false, texte:'a ' }, { gras:true, texte:'b' }, …]. */
export function decouperTexteRiche(texte) {
  const s = typeof texte === 'string' ? texte : '';
  const morceaux = [];
  const re = /\*\*([^*]+)\*\*/g;
  let dernier = 0;
  let m;
  while ((m = re.exec(s)) !== null) {
    if (m.index > dernier) morceaux.push({ gras: false, texte: s.slice(dernier, m.index) });
    morceaux.push({ gras: true, texte: m[1] });
    dernier = m.index + m[0].length;
  }
  if (dernier < s.length) morceaux.push({ gras: false, texte: s.slice(dernier) });
  return morceaux;
}

const TexteRiche = ({ texte, styleGras, classeGras }) => (
  <>
    {decouperTexteRiche(texte).map((p, i) => (
      p.gras
        ? <strong key={i} style={styleGras} className={classeGras}>{p.texte}</strong>
        : <React.Fragment key={i}>{p.texte}</React.Fragment>
    ))}
  </>
);

export default TexteRiche;
