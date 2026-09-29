/**
 * L0 — QUI INVITE, VISIBLE AU MOMENT DU PARTAGE.
 *
 * « [photo ronde 40 px] Prénom t’invite à découvrir Afroboost ».
 *   - photo absente, refusée (hors liste blanche `photoAutorisee`) ou en erreur
 *     de chargement → avatar Afroboost (le logo de l'app), JAMAIS une initiale ;
 *   - prénom absent (ou qui ressemble à un e-mail / un identifiant) →
 *     « Afroboost t’invite ».
 * Aucune donnée personnelle au-delà du prénom et de la photo.
 */
import React, { useState } from 'react';
import { nomAffichable, photoAutorisee } from '../../utils/parrainage';

export const LOGO_AFROBOOST = '/logo192.png';

/**
 * L'avatar rond de l'invitant : sa photo si elle est autorisée et se charge,
 * sinon le logo Afroboost. `testidPhoto` / `testidAvatar` distinguent les deux.
 */
export function AvatarInvitant({ photoUrl, className, testidPhoto, testidAvatar }) {
  const photo = photoAutorisee(photoUrl);
  const [enEchec, setEnEchec] = useState(''); // l'URL qui a échoué (une chaîne, jamais un objet)
  const visible = !!photo && enEchec !== photo;
  return (
    <div className={`cp-av cp-wz-av cp-bi-av${className ? ` ${className}` : ''}`}>
      {visible ? (
        <img src={photo} alt="" onError={() => setEnEchec(photo)} data-testid={testidPhoto} />
      ) : (
        <img src={LOGO_AFROBOOST} alt="Afroboost" className="cp-bi-logo" data-testid={testidAvatar} />
      )}
    </div>
  );
}

export default function BandeauInvitant({ prenom, photoUrl }) {
  const nom = nomAffichable(prenom);
  return (
    <div className="cp-bi" data-testid="bandeau-invitant">
      <AvatarInvitant photoUrl={photoUrl} className="cp-bi-av--40" testidPhoto="bandeau-photo" testidAvatar="bandeau-avatar-afroboost" />
      <p className="cp-bi-texte" data-testid="bandeau-texte">
        {nom ? `${nom} t’invite à découvrir Afroboost` : 'Afroboost t’invite'}
      </p>
    </div>
  );
}
