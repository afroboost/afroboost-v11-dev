/**
 * V618j — « ACCÉDER À MON ESPACE MEMBRE », une seule règle pour l'invitation :
 *   * une session d'espace existe sur CET appareil -> l'espace s'ouvre directement ;
 *   * sinon -> le lien d'accès part par E-MAIL (route existante /subscriber/recover), jamais à
 *     l'écran : le message reste NEUTRE (il ne dit pas si l'adresse est cliente — V389 / V591).
 * Couleurs : jetons de la page (--cp-*) ; icônes SVG.
 */
import React, { useState } from 'react';
import axios from 'axios';
import SvgIcon from '../SvgIcon';
import { urlEspaceCourant } from '../../utils/parrainage';

const API = `${process.env.REACT_APP_BACKEND_URL || ''}/api`;
export const MESSAGE_LIEN_ENVOYE = "Si cette adresse a un espace Afroboost, ton lien d'accès vient d'y être envoyé. Pense à regarder tes courriers indésirables.";

export default function AccesEspaceMembre({ email, libelle, testid, demanderEmail }) {
  const [etat, setEtat] = useState('');        // '' | 'envoi' | 'envoye' | 'saisir' | 'trop'
  const [saisi, setSaisi] = useState('');
  const ouvrir = () => {
    const cible = urlEspaceCourant();
    if (cible) { window.location.href = cible; return; }
    const mail = String(email || saisi || '').trim().toLowerCase();
    if (!mail || mail.indexOf('@') < 1) { setEtat('saisir'); return; }
    setEtat('envoi');
    axios.post(`${API}/subscriber/recover`, { email: mail }, { timeout: 15000 })
      .then(() => setEtat('envoye'))
      .catch((e) => setEtat(e && e.response && e.response.status === 429 ? 'trop' : 'envoye'));
  };
  const avecChamp = !!demanderEmail && !email && !urlEspaceCourant();
  return (
    <div data-testid={testid || 'acces-espace-membre'}>
      {avecChamp ? (
        <input className="cp-input" type="email" value={saisi} placeholder="Ton e-mail" autoComplete="email"
               onChange={(e) => setSaisi(e.target.value)} data-testid="acces-espace-email" style={{ marginBottom: 10 }} />
      ) : null}
      <button type="button" className="cp-b cp-b--primary cp-wz-cible" onClick={ouvrir} disabled={etat === 'envoi'}
              data-testid="bouton-espace-membre" style={{ width: '100%' }}>
        <SvgIcon name="user" size={20} /> {libelle || 'Accéder à mon espace membre'}
      </button>
      {etat === 'envoye' ? <p className="cp-mini" role="status" data-testid="lien-espace-envoye">{MESSAGE_LIEN_ENVOYE}</p> : null}
      {etat === 'saisir' ? <p className="cp-mini" role="status" data-testid="acces-espace-saisir">Indique ton e-mail pour recevoir ton lien d'accès.</p> : null}
      {etat === 'trop' ? <p className="cp-mini" role="status">Trop de demandes. Réessaie dans quelques minutes.</p> : null}
    </div>
  );
}
