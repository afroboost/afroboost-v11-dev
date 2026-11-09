// V657 : AFROBOOST CORPORATE — contrats entreprise (super-admin). Épuré : une carte par contrat,
// au plus 2 actions visibles, le reste dans « Détails » (accordéon, un seul ouvert à la fois).
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { QRCodeSVG } from 'qrcode.react';
import SvgIcon from '../SvgIcon';
import { appel, telechargerPdf, messageErreur, chf, dateCh, STATUT_CONTRAT, STATUT_FACTURE, carte, champ, boutonPrincipal, boutonSecondaire, pastille } from './corporateApi';

const lienPublic = (token) => (typeof window !== 'undefined' ? window.location.origin : '') + '/entreprise/' + token;
const moisCourant = () => { const d = new Date(); d.setMonth(d.getMonth() + 1); return d.toISOString().slice(0, 7); };

const Fenetre = ({ titre, onFermer, children }) => (
  <div role="dialog" aria-modal="true" aria-label={titre} style={{ position: 'fixed', inset: 0, zIndex: 1000, background: 'rgba(0,0,0,0.7)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16 }}>
    <div style={{ background: '#111', border: '1px solid rgba(var(--primary-rgb, 217, 28, 210), 0.35)', borderRadius: 14, width: 'min(560px, 100%)', maxHeight: '90vh', overflowY: 'auto', padding: 16 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
        <strong style={{ color: '#fff', fontSize: 15 }}>{titre}</strong>
        <button type="button" onClick={onFermer} aria-label="Fermer" style={{ background: 'none', border: 'none', color: 'rgba(255,255,255,0.7)', cursor: 'pointer' }}><SvgIcon name="close" size={18} /></button>
      </div>
      {children}
    </div>
  </div>
);

const NouveauDevis = ({ email, onCree, onFermer }) => {
  const [prospects, setProspects] = useState([]);
  const [f, setF] = useState({ prospect_id: '', places: 10, mois: 6, mois_debut: moisCourant(), facturation: { nom: '', adresse: '', ville: '', contact: '', email: '' } });
  const [prix, setPrix] = useState(null);
  const [msg, setMsg] = useState('');
  useEffect(() => {
    appel('/partner-prospects?category=entreprise&limit=50', { email }).then(r => setProspects(r.ok ? (r.data.prospects || r.data.items || []) : []));
  }, [email]);
  useEffect(() => {
    let vivant = true;
    appel(`/corporate/prix?places=${f.places}&mois=${f.mois}`, { email }).then(r => { if (vivant) setPrix(r.ok ? r.data : null); });
    return () => { vivant = false; };
  }, [f.places, f.mois, email]);
  const creer = async () => {
    setMsg('');
    const r = await appel('/corporate/contrats', { method: 'POST', email, body: f });
    if (r.ok) onCree(r.data); else setMsg(messageErreur(r));
  };
  const majFact = (k, v) => setF(p => ({ ...p, facturation: { ...p.facturation, [k]: v } }));
  return (
    <Fenetre titre="Nouveau devis Corporate" onFermer={onFermer}>
      <div style={{ display: 'grid', gap: 8 }}>
        <select style={champ} aria-label="Entreprise (prospect)" value={f.prospect_id} onChange={e => { const v = e.target.value; const p = prospects.find(x => x.id === v); setF(o => ({ ...o, prospect_id: v, facturation: { ...o.facturation, nom: o.facturation.nom || (p ? p.organisation_name : '') } })); }} data-testid="corp-prospect">
          <option value="">Choisir l’entreprise (Prospection, catégorie Entreprise)</option>
          {prospects.map(p => <option key={p.id} value={p.id}>{p.organisation_name}{p.city ? ' — ' + p.city : ''}</option>)}
        </select>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 8 }}>
          <select style={champ} aria-label="Places par édition" value={f.places} onChange={e => { const v = Number(e.target.value); setF(p => ({ ...p, places: v })); }} data-testid="corp-places">
            {[5, 10, 20].map(n => <option key={n} value={n}>{n} places / édition</option>)}
          </select>
          <select style={champ} aria-label="Durée" value={f.mois} onChange={e => { const v = Number(e.target.value); setF(p => ({ ...p, mois: v })); }} data-testid="corp-mois">
            {[3, 6, 12].map(n => <option key={n} value={n}>{n} mois</option>)}
          </select>
          <input style={champ} type="month" aria-label="Premier mois" value={f.mois_debut} onChange={e => { const v = e.target.value; setF(p => ({ ...p, mois_debut: v })); }} data-testid="corp-debut" />
        </div>
        <div style={{ color: 'var(--primary-color, #D91CD2)', fontWeight: 700, fontSize: 14 }} data-testid="corp-prix">
          {prix ? `${chf(prix.prix_mensuel)} / mois · total ${chf(prix.total)} · jusqu’à ${f.places * f.mois} participations` : '—'}
        </div>
        <div style={{ color: 'rgba(255,255,255,0.6)', fontSize: 12 }}>Coordonnées de facturation de l’entreprise (saisies, jamais devinées)</div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 8 }}>
          {[['nom', 'Raison sociale'], ['adresse', 'Adresse'], ['ville', 'NPA et ville'], ['contact', 'Contact'], ['email', 'E-mail comptabilité']].map(([k, l]) => (
            <input key={k} style={champ} placeholder={l} aria-label={l} value={f.facturation[k]} onChange={e => majFact(k, e.target.value)} />
          ))}
        </div>
        <button type="button" style={boutonPrincipal} onClick={creer} disabled={!f.prospect_id} data-testid="corp-creer">Créer le devis</button>
        {msg && <div style={{ color: 'rgba(255,255,255,0.8)', fontSize: 12 }}>{msg}</div>}
      </div>
    </Fenetre>
  );
};

const Inscriptions = ({ contrat, mois, email }) => {
  const [etat, setEtat] = useState(null);
  const [msg, setMsg] = useState('');
  const charger = useCallback(async () => {
    const r = await appel(`/corporate/contrats/${contrat.id}/editions/${mois}/inscriptions`, { email });
    setEtat(r.ok ? r.data : { inscriptions: [], erreur: messageErreur(r) });
  }, [contrat.id, mois, email]);
  useEffect(() => { charger(); }, [charger]);
  const corriger = async (x) => {
    const nouvel = window.prompt('Nouvel e-mail (remplacer la personne) — laisser vide pour seulement renommer', '');
    const nom = window.prompt('Nom et prénom', x.userName || '');
    if (nouvel === null && nom === null) return;
    const body = {};
    if (nouvel) body.email = nouvel;
    if (nom) body.nom = nom;
    const r = await appel(`/corporate/contrats/${contrat.id}/inscriptions/${x.id}`, { method: 'PATCH', email, body });
    setMsg(r.ok ? 'Inscription corrigée.' : messageErreur(r)); charger();
  };
  const annuler = async (x) => {
    if (!window.confirm('Annuler l’inscription de ' + (x.userName || x.userEmail) + ' ? La place revient à l’entreprise.')) return;
    const r = await appel(`/corporate/contrats/${contrat.id}/inscriptions/${x.id}`, { method: 'DELETE', email });
    setMsg(r.ok ? 'Inscription annulée.' : messageErreur(r)); charger();
  };
  if (!etat) return <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.6)' }}>Chargement…</div>;
  return (
    <div style={{ marginTop: 6 }} data-testid={'corp-inscriptions-' + mois}>
      <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.7)' }}>{etat.inscriptions.length} inscrit(s) · {etat.places_restantes} place(s) libre(s){etat.delai_depasse ? ' · changements clos' : ''}</div>
      {etat.inscriptions.map(x => (
        <div key={x.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 6, padding: '6px 0', borderBottom: '1px solid rgba(255,255,255,0.06)', flexWrap: 'wrap' }}>
          <span style={{ fontSize: 12, color: '#fff' }}>{x.userName} <span style={{ color: 'rgba(255,255,255,0.55)' }}>{x.userEmail}</span></span>
          <span style={{ display: 'flex', gap: 6 }}>
            <button type="button" style={boutonSecondaire} onClick={() => corriger(x)} aria-label="Corriger"><SvgIcon name="edit" size={13} /></button>
            <button type="button" style={boutonSecondaire} onClick={() => annuler(x)} aria-label="Annuler l’inscription"><SvgIcon name="trash" size={13} /></button>
          </span>
        </div>
      ))}
      {msg && <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.8)', marginTop: 4 }}>{msg}</div>}
    </div>
  );
};

const CarteContrat = ({ c, email, ouvert, onBascule, onMaj, evenements }) => {
  const [msg, setMsg] = useState('');
  const [qr, setQr] = useState(false);
  const [choix, setChoix] = useState({});
  const [voir, setVoir] = useState('');
  const fin = c.finances || {};
  const agir = async (chemin, body, ok) => {
    setMsg('');
    const r = await appel(chemin, { method: 'POST', email, body });
    if (r.ok) { setMsg(ok); onMaj(r.data && r.data.id ? r.data : null); } else setMsg(messageErreur(r));
  };
  const document = async (body, ok) => {
    setMsg('');
    const r = await telechargerPdf('/invoices/generate', { method: 'POST', email, body });
    if (r.ok) { setMsg(ok + ' ' + r.numero); onMaj(null); } else setMsg(r.erreur);
  };
  const copierLien = () => { try { navigator.clipboard.writeText(lienPublic(c.token)); setMsg('Lien copié.'); } catch (e) { setMsg(lienPublic(c.token)); } };
  return (
    <div style={carte} data-testid="corp-contrat">
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
        <div>
          <div style={{ color: '#fff', fontWeight: 700, fontSize: 14 }}>{c.entreprise?.nom} <span style={pastille(c.statut === 'signe' ? 'ok' : c.statut === 'devis' ? 'alerte' : '')}>{STATUT_CONTRAT[c.statut]}</span></div>
          <div style={{ color: 'rgba(255,255,255,0.65)', fontSize: 12 }}>{c.places} places × {c.duree_mois} mois · {chf(c.prix_mensuel)}/mois · total {chf(c.total)} · payé {chf(fin.paye)} · dû {chf(fin.du)}</div>
        </div>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          {c.statut === 'devis' && <button type="button" style={boutonPrincipal} onClick={() => agir(`/corporate/contrats/${c.id}/signer`, {}, 'Contrat signé.')} data-testid="corp-signer">Confirmer la signature</button>}
          {c.statut === 'signe' && <button type="button" style={boutonPrincipal} onClick={() => setQr(!qr)} data-testid="corp-lien"><SvgIcon name="qrCode" size={14} /> Lien & QR</button>}
          <button type="button" style={boutonSecondaire} onClick={onBascule} aria-expanded={ouvert} data-testid="corp-details">Détails</button>
        </div>
      </div>
      {qr && c.statut === 'signe' && (
        <div style={{ marginTop: 10, display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
          {c.token_actif ? (
            <>
              <div style={{ background: '#fff', padding: 8, borderRadius: 8 }}><QRCodeSVG value={lienPublic(c.token)} size={132} level="M" /></div>
              <div style={{ display: 'grid', gap: 6, minWidth: 0, flex: 1 }}>
                <code style={{ fontSize: 11, color: 'rgba(255,255,255,0.8)', wordBreak: 'break-all' }} data-testid="corp-lien-url">{lienPublic(c.token)}</code>
                <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                  <button type="button" style={boutonSecondaire} onClick={copierLien}><SvgIcon name="copy" size={13} /> Copier</button>
                  <button type="button" style={boutonSecondaire} onClick={() => agir(`/corporate/contrats/${c.id}/lien`, { action: 'regenerer' }, 'Nouveau lien : l’ancien ne marche plus.')}>Régénérer</button>
                  <button type="button" style={boutonSecondaire} onClick={() => agir(`/corporate/contrats/${c.id}/lien`, { action: 'revoquer' }, 'Lien désactivé.')}>Désactiver</button>
                </div>
              </div>
            </>
          ) : (
            <button type="button" style={boutonSecondaire} onClick={() => agir(`/corporate/contrats/${c.id}/lien`, { action: 'regenerer' }, 'Nouveau lien actif.')}>Lien désactivé — en créer un nouveau</button>
          )}
        </div>
      )}
      {ouvert && (
        <div style={{ marginTop: 10, display: 'grid', gap: 10 }}>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            {c.statut !== 'resilie' && c.statut !== 'termine' && <button type="button" style={boutonSecondaire} onClick={() => document({ type_document: 'devis', corporate_contract_id: c.id }, 'Devis émis :')} data-testid="corp-devis-pdf"><SvgIcon name="fileText" size={13} /> Générer le devis (PDF)</button>}
            {c.statut === 'signe' && <button type="button" style={boutonSecondaire} onClick={() => { if (window.confirm('Résilier ? Les places des éditions à venir sont rendues, le lien est coupé.')) agir(`/corporate/contrats/${c.id}/statut`, { statut: 'resilie' }, 'Contrat résilié.'); }}>Résilier</button>}
            {c.statut === 'signe' && <button type="button" style={boutonSecondaire} onClick={() => agir(`/corporate/contrats/${c.id}/statut`, { statut: 'termine' }, 'Contrat terminé.')}>Marquer terminé</button>}
          </div>
          <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.6)', whiteSpace: 'pre-line' }}>{c.conditions}</div>
          <div>
            <div style={{ color: '#fff', fontWeight: 600, fontSize: 13, marginBottom: 4 }}>Éditions</div>
            {(c.editions || []).map(e => (
              <div key={e.mois} style={{ padding: '6px 0', borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
                  <span style={{ fontSize: 12, color: '#fff' }}>{e.mois} · {e.statut === 'planifiee' ? `${dateCh(e.date)} ${String(e.date || '').slice(11, 16)} · ${e.lieu || ''}` : 'À planifier'}</span>
                  {e.statut === 'planifiee'
                    ? <button type="button" style={boutonSecondaire} onClick={() => setVoir(voir === e.mois ? '' : e.mois)}>Inscrits</button>
                    : c.statut === 'signe' && (
                      <span style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                        <select style={{ ...champ, width: 'auto', maxWidth: 220 }} aria-label={'Événement pour ' + e.mois} value={choix[e.mois] || ''} onChange={ev => { const v = ev.target.value; setChoix(p => ({ ...p, [e.mois]: v })); }}>
                          <option value="">Lier à un événement…</option>
                          {evenements.filter(o => (o.date || '').slice(0, 7) === e.mois).map(o => <option key={o.id} value={o.id}>{o.name} — {dateCh(o.date)}</option>)}
                        </select>
                        <button type="button" style={boutonSecondaire} disabled={!choix[e.mois]} onClick={() => agir(`/corporate/contrats/${c.id}/editions/${e.mois}/lier`, { offer_id: choix[e.mois] }, 'Édition planifiée : places retenues.')} data-testid={'corp-lier-' + e.mois}>Lier</button>
                      </span>
                    )}
                </div>
                {voir === e.mois && <Inscriptions contrat={c} mois={e.mois} email={email} />}
              </div>
            ))}
          </div>
          <div>
            <div style={{ color: '#fff', fontWeight: 600, fontSize: 13, marginBottom: 4 }}>Facturation mensuelle</div>
            {(fin.echeancier || []).map(l => (
              <div key={l.mois} style={{ display: 'flex', justifyContent: 'space-between', gap: 6, padding: '4px 0', flexWrap: 'wrap', alignItems: 'center' }}>
                <span style={{ fontSize: 12, color: 'rgba(255,255,255,0.8)' }}>{l.mois} · {chf(l.montant)} {l.facture_numero ? '· ' + l.facture_numero : ''} <span style={pastille(l.statut === 'payee' ? 'ok' : l.statut === 'emise' ? 'alerte' : '')}>{STATUT_FACTURE[l.statut]}</span></span>
                {l.statut === 'a_emettre' && c.statut === 'signe' && <button type="button" style={boutonSecondaire} onClick={() => document({ corporate_contract_id: c.id, mois: l.mois }, 'Facture émise :')} data-testid={'corp-facture-' + l.mois}>Émettre la facture</button>}
              </div>
            ))}
            <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.65)', marginTop: 4 }}>Facturé {chf(fin.facture)} · payé {chf(fin.paye)} · reste dû {chf(fin.du)} (paiements : Paiements → Générateur de factures)</div>
          </div>
        </div>
      )}
      {msg && <div style={{ marginTop: 6, fontSize: 12, color: 'rgba(255,255,255,0.85)' }} data-testid="corp-msg">{msg}</div>}
    </div>
  );
};

const CorporateContrats = ({ coachEmail, offers, courses }) => {
  const [etat, setEtat] = useState({ chargement: true, liste: [], erreur: '' });
  const [ouvert, setOuvert] = useState('');
  const [creation, setCreation] = useState(false);
  const charger = useCallback(async () => {
    const r = await appel('/corporate/contrats', { email: coachEmail });
    setEtat(r.ok ? { chargement: false, liste: r.data.contrats || [], erreur: '' } : { chargement: false, liste: [], erreur: messageErreur(r) });
  }, [coachEmail]);
  useEffect(() => { charger(); }, [charger]);
  // Événements à réservation automatique, avec la date de leur cours (pour les lier à une édition).
  const evenements = useMemo(() => {
    const parId = {};
    (courses || []).forEach(c => { parId[c.id] = c; });
    return (offers || []).filter(o => o && o.offer_type === 'event' && o.evenement_reservation_auto === true && !o.archived)
      .map(o => { const c = (o.linked_course_ids || []).map(i => parId[i]).find(x => x && x.date); return { id: o.id, name: o.name, date: c ? c.date : '' }; })
      .filter(o => o.date);
  }, [offers, courses]);
  return (
    <div style={{ maxWidth: 900, margin: '12px auto 0' }} data-testid="corporate-contrats">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10, gap: 8 }}>
        <strong style={{ color: '#fff', fontSize: 15 }}>Afroboost Corporate</strong>
        <button type="button" style={boutonPrincipal} onClick={() => setCreation(true)} data-testid="corp-nouveau">+ Nouveau devis</button>
      </div>
      {etat.chargement && <p style={{ color: 'rgba(255,255,255,0.6)', fontSize: 12 }}>Chargement…</p>}
      {etat.erreur && <p style={{ color: 'rgba(255,255,255,0.8)', fontSize: 12 }}>{etat.erreur}</p>}
      {!etat.chargement && !etat.erreur && etat.liste.length === 0 && <p style={{ color: 'rgba(255,255,255,0.6)', fontSize: 12 }}>Aucun contrat. « + Nouveau devis » pour commencer.</p>}
      {etat.liste.map(c => (
        <CarteContrat key={c.id} c={c} email={coachEmail} evenements={evenements} ouvert={ouvert === c.id}
          onBascule={() => setOuvert(ouvert === c.id ? '' : c.id)} onMaj={() => charger()} />
      ))}
      {creation && <NouveauDevis email={coachEmail} onFermer={() => setCreation(false)} onCree={(c) => { setCreation(false); setOuvert(c.id); charger(); }} />}
    </div>
  );
};

export default CorporateContrats;
