/**
 * V610o — ESPACE : « TON IMPACT AFROBOOST » + « Partager et inviter ».
 * Le serveur décide de tout (`/api/ambassadeur/mon-impact`, session d'espace) : rien sans
 * participation confirmée à un événement (aucun bloc vide, aucun faux 0).
 */
import React, { useEffect, useState } from 'react';
import ImpactAfroboost from './ImpactAfroboost';
import InviterMesAmis from './InviterMesAmis';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';

export default function MonImpactAfroboost({ accessCode, jetonEspace, slug }) {
  const [impact, setImpact] = useState(null);
  const [partage, setPartage] = useState(false);
  const code = String(accessCode || '');
  const jeton = String(jetonEspace || '');
  const membre = String(slug || '');
  useEffect(() => {
    if (!code || !jeton) return undefined;
    let vivant = true;
    fetch(`${BACKEND_URL}/api/ambassadeur/mon-impact`, {
      method: 'POST', headers: { 'Content-Type': 'application/json', 'x-espace-token': jeton },
      body: JSON.stringify({ code, slug: membre }),
    })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => { if (vivant && d && d.ambassadeur && d.progression) setImpact(d); })
      .catch(() => { /* facultatif */ });
    return () => { vivant = false; };
  }, [code, jeton, membre]);
  if (!impact) return null;
  const lien = impact.lien && impact.lien.jeton ? impact.lien : null;
  return (
    <div data-testid="mon-impact">
      <ImpactAfroboost impact={impact} onPartager={lien ? () => setPartage((v) => !v) : undefined} />
      {partage && lien ? <InviterMesAmis relaisInitial={lien} /> : null}
    </div>
  );
}
