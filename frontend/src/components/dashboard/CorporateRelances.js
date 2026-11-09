// V657 : factures Entreprise échues ou proches de l'échéance — « Préparer un rappel » = BROUILLON à copier.
// Aucun envoi (ni e-mail, ni WhatsApp), aucun moteur : le texte est daté sur la facture, rien d'autre.
import React, { useCallback, useEffect, useState } from 'react';
import SvgIcon from '../SvgIcon';
import { appel, messageErreur, chf, dateCh, carte, champ, boutonSecondaire, pastille } from './corporateApi';

const CorporateRelances = ({ coachEmail }) => {
  const [etat, setEtat] = useState({ chargement: true, liste: [], erreur: '' });
  const [brouillon, setBrouillon] = useState({ numero: '', texte: '' });
  const [copie, setCopie] = useState(false);
  const charger = useCallback(async () => {
    const r = await appel('/invoices/corporate/a-relancer', { email: coachEmail });
    setEtat(r.ok ? { chargement: false, liste: r.data.factures || [], erreur: '' } : { chargement: false, liste: [], erreur: messageErreur(r) });
  }, [coachEmail]);
  useEffect(() => { charger(); }, [charger]);
  const preparer = async (numero) => {
    setCopie(false);
    const r = await appel(`/invoices/${encodeURIComponent(numero)}/rappel`, { method: 'POST', email: coachEmail });
    if (r.ok) { setBrouillon({ numero, texte: r.data.texte }); charger(); } else setBrouillon({ numero, texte: messageErreur(r) });
  };
  const copier = () => {
    try { navigator.clipboard.writeText(brouillon.texte).then(() => setCopie(true)); } catch (e) { setCopie(false); }
  };
  if (etat.chargement) return null;
  return (
    <div style={{ marginTop: 12 }} data-testid="corp-relances">
      <div style={{ color: 'rgba(255,255,255,0.85)', fontWeight: 600, fontSize: 13, marginBottom: 6, display: 'flex', alignItems: 'center', gap: 6 }}>
        <SvgIcon name="fileText" size={14} /> Factures Entreprise à suivre
      </div>
      {etat.erreur && <p style={{ color: 'rgba(255,255,255,0.7)', fontSize: 12 }}>{etat.erreur}</p>}
      {!etat.erreur && etat.liste.length === 0 && <p style={{ color: 'rgba(255,255,255,0.6)', fontSize: 12 }}>Aucune facture Entreprise échue ou à échéance dans 7 jours.</p>}
      {etat.liste.map(x => (
        <div key={x.invoice_number} style={carte}>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
            <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.8)' }}>
              <div style={{ color: '#fff', fontWeight: 600 }}>{x.entreprise || '—'} · {x.invoice_number}</div>
              <div>Reste {chf(x.reste)} · échéance {dateCh(x.echeance)} · dernier rappel {x.dernier_rappel ? dateCh(x.dernier_rappel.le) : 'aucun'}</div>
            </div>
            <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
              <span style={pastille(x.en_retard ? 'alerte' : '')}>{x.en_retard ? 'En retard' : 'Bientôt due'}</span>
              <button type="button" style={boutonSecondaire} onClick={() => preparer(x.invoice_number)}>Préparer un rappel</button>
            </div>
          </div>
          {brouillon.numero === x.invoice_number && (
            <div style={{ marginTop: 8 }}>
              <textarea readOnly rows={8} value={brouillon.texte} style={{ ...champ, resize: 'vertical' }} aria-label="Brouillon de rappel" />
              <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginTop: 6 }}>
                <button type="button" style={boutonSecondaire} onClick={copier}><SvgIcon name="copy" size={14} /> Copier</button>
                <span style={{ fontSize: 11, color: 'rgba(255,255,255,0.55)' }}>{copie ? 'Copié.' : 'Brouillon seulement : rien n’est envoyé.'}</span>
              </div>
            </div>
          )}
        </div>
      ))}
    </div>
  );
};

export default CorporateRelances;
