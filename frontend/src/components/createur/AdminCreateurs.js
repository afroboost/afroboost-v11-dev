/**
 * V559 — CONSOLE SUPER-ADMIN : « CRÉATEURS / AFFILIATION ».
 *
 * Six vues sur le MÊME moteur (routes /api/createur/admin/*, JWT super-admin
 * exigé par le serveur — cet écran ne décide d'aucun droit) :
 *   Demandes (pending) · Créateurs · Programmes · Conversions / commissions ·
 *   Retraits (paiement MANUEL : TWINT / IBAN visibles ici seulement).
 *
 * RÉSEAU : une lecture par vue ouverte (clé = nom de la vue, une chaîne), puis
 * uniquement sur geste. Après chaque décision, la vue courante est relue.
 */
import React, { useEffect, useState } from 'react';
import axios from 'axios';
import SvgIcon from '../SvgIcon';
import {
  adminLister, adminDecisionCreateur, adminCreerProgramme, adminModifierProgramme,
  adminAnnulerCommission, adminDecisionRetrait, messageErreurCreateur, chf, dateCourte,
} from '../../utils/createur';
import './createur.css';

const VUES = [
  ['demandes', 'Demandes'], ['createurs', 'Créateurs actifs'], ['programmes', 'Programmes'],
  ['commissions', 'Conversions & commissions'], ['retraits', 'Retraits'],
];
const BACKEND = process.env.REACT_APP_BACKEND_URL || '';

function Bouton({ onClick, children, plein, disabled, testid }) {
  return (
    <button type="button" className={`cr-b${plein ? ' cr-b--plein' : ''}`} style={{ width: 'auto', minHeight: 40, fontSize: 13 }}
            onClick={onClick} disabled={disabled} data-testid={testid}>{children}</button>
  );
}

function FormProgramme({ offres, onCree }) {
  const [f, setF] = useState({ name: 'Créateurs Afroboost', offer_id: '', reward_type: 'fixed_amount', reward_value: '' });
  const [erreur, setErreur] = useState('');
  const [occupe, setOccupe] = useState(false);
  const maj = (k) => (e) => { const v = e.target.value; setF((p) => (p[k] === v ? p : Object.assign({}, p, { [k]: v }))); };
  const creer = () => {
    if (occupe) return;
    setOccupe(true); setErreur('');
    adminCreerProgramme(Object.assign({}, f, { reward_value: Number(f.reward_value) }))
      .then(() => { setF((p) => Object.assign({}, p, { offer_id: '', reward_value: '' })); onCree(); })
      .catch((e) => setErreur(messageErreurCreateur(e)))
      .finally(() => setOccupe(false));
  };
  return (
    <div className="cr-carte cr-form" data-testid="admin-programme-form">
      <h3 className="cr-h3">Nouveau programme d'affiliation</h3>
      <label className="cr-label">Nom<input className="cr-input" value={f.name} onChange={maj('name')} maxLength={80} /></label>
      <label className="cr-label">Offre
        <select className="cr-input" value={f.offer_id} onChange={maj('offer_id')} data-testid="admin-programme-offre">
          <option value="">Choisis une offre</option>
          {offres.map((o) => <option key={o.id} value={o.id}>{o.name}{Number(o.price) > 0 ? ` · ${chf(o.price)}` : ''}</option>)}
        </select>
      </label>
      <div className="cr-2col">
        <label className="cr-label">Type
          <select className="cr-input" value={f.reward_type} onChange={maj('reward_type')} data-testid="admin-programme-type">
            <option value="fixed_amount">Montant fixe (CHF)</option>
            <option value="percentage">Pourcentage (%)</option>
          </select>
        </label>
        <label className="cr-label">Valeur
          <input className="cr-input" type="number" min="0" step="0.5" value={f.reward_value} onChange={maj('reward_value')} data-testid="admin-programme-valeur" />
        </label>
      </div>
      {erreur ? <p className="cr-erreur" role="alert">{erreur}</p> : null}
      <Bouton plein onClick={creer} disabled={occupe || !f.offer_id || !f.reward_value} testid="admin-programme-creer">
        <SvgIcon name="plus" size={16} /> Créer le programme
      </Bouton>
    </div>
  );
}

export default function AdminCreateurs() {
  const [vue, setVue] = useState('demandes');
  const [donnees, setDonnees] = useState(null);
  const [offres, setOffres] = useState([]);
  const [erreur, setErreur] = useState('');
  const [relire, setRelire] = useState(0);

  useEffect(() => {
    let vivant = true;
    setDonnees(null); setErreur('');
    const quoi = vue === 'demandes' || vue === 'createurs' ? 'createurs' : vue;
    const statut = vue === 'demandes' ? 'pending' : '';
    adminLister(quoi, statut)
      .then((d) => { if (vivant) setDonnees(d || {}); })
      .catch((e) => { if (vivant) setErreur(messageErreurCreateur(e)); });
    if (vue === 'programmes') {
      axios.get(`${BACKEND}/api/offers`, { timeout: 15000 })
        .then((r) => { if (vivant) setOffres((Array.isArray(r.data) ? r.data : []).filter((o) => o && o.id && Number(o.price) > 0)); })
        .catch(() => {});
    }
    return () => { vivant = false; };
  }, [vue, relire]);

  const agir = (promesse) => promesse.then(() => setRelire((n) => n + 1)).catch((e) => setErreur(messageErreurCreateur(e)));
  const liste = (cle) => (donnees && Array.isArray(donnees[cle]) ? donnees[cle] : []);

  let contenu = null;
  if (vue === 'demandes' || vue === 'createurs') {
    const rows = liste('createurs').filter((c) => vue === 'demandes' || c.statut !== 'pending');
    contenu = rows.length ? (
      <ul className="cr-liste">
        {rows.map((c) => (
          <li key={c.id} className="cr-carte" data-testid={`admin-createur-${c.id}`}>
            <div className="cr-ligne" style={{ background: 'transparent', border: 'none', padding: 0 }}>
              <span className="cr-nom">{c.prenom} {c.nom}</span>
              <span className="cr-statut">{c.statut}</span>
            </div>
            <p className="cr-fine">{c.email} · {c.telephone} · {c.role_origine === 'coach' ? 'Coach / partenaire' : 'Abonné'} · {dateCourte(c.cree_le)}</p>
            {c.reseaux ? <p className="cr-fine">Réseaux : {c.reseaux}</p> : null}
            {c.motivation ? <p className="cr-fine">« {c.motivation} »</p> : null}
            <p className="cr-fine">Paiement : {c.methode === 'iban' ? 'IBAN' : 'TWINT'} {c.methode_detail}</p>
            {c.lien ? <p className="cr-fine">Lien : {c.lien.replace(/^https?:\/\//, '')}</p> : null}
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 10 }}>
              {c.statut === 'pending' || c.statut === 'rejected' ? (
                <Bouton plein onClick={() => agir(adminDecisionCreateur(c.id, 'approve'))} testid="admin-approuver">Approuver</Bouton>
              ) : null}
              {c.statut === 'pending' ? <Bouton onClick={() => agir(adminDecisionCreateur(c.id, 'reject'))} testid="admin-refuser">Refuser</Bouton> : null}
              {c.statut === 'approved' ? <Bouton onClick={() => agir(adminDecisionCreateur(c.id, 'suspend'))} testid="admin-suspendre">Suspendre</Bouton> : null}
              {c.statut === 'suspended' ? <Bouton plein onClick={() => agir(adminDecisionCreateur(c.id, 'reactivate'))} testid="admin-reactiver">Réactiver</Bouton> : null}
            </div>
          </li>
        ))}
      </ul>
    ) : <p className="cr-vide">{vue === 'demandes' ? 'Aucune demande en attente.' : 'Aucun créateur.'}</p>;
  } else if (vue === 'programmes') {
    const rows = liste('programmes');
    contenu = (
      <>
        <FormProgramme offres={offres} onCree={() => setRelire((n) => n + 1)} />
        {rows.length ? (
          <ul className="cr-liste">
            {rows.map((p) => (
              <li key={p.id} className="cr-ligne" data-testid={`admin-programme-${p.id}`}>
                <span className="cr-nom">{p.offer_name || p.offer_id}</span>
                <b className="cr-accent">{p.reward_type === 'percentage' ? `${p.reward_value} %` : chf(p.reward_value)}</b>
                <span className="cr-fine">{p.name}</span>
                <Bouton onClick={() => agir(adminModifierProgramme(p.id, Object.assign({}, p, { status: p.status === 'active' ? 'inactive' : 'active' })))}
                        testid="admin-programme-bascule">
                  {p.status === 'active' ? 'Désactiver' : 'Activer'}
                </Bouton>
              </li>
            ))}
          </ul>
        ) : <p className="cr-vide">Aucun programme : aucune commission ne peut naître.</p>}
      </>
    );
  } else if (vue === 'commissions') {
    const rows = liste('commissions');
    contenu = rows.length ? (
      <ul className="cr-liste">
        {rows.map((c) => (
          <li key={c.id} className="cr-carte" data-testid={`admin-commission-${c.id}`}>
            <div className="cr-ligne" style={{ background: 'transparent', border: 'none', padding: 0 }}>
              <span className="cr-nom">{c.offre} · {chf(c.montant)}</span>
              <span className="cr-statut">{c.statut_libelle}</span>
            </div>
            <p className="cr-fine">{dateCourte(c.date)} · créateur : {c.createur || '—'} · acheteur : {c.acheteur || '—'} · origine : {c.origine === 'lien' ? 'lien créateur' : 'invitation'}</p>
            <p className="cr-fine">Commission : <b className="cr-accent">{chf(c.commission)}</b>
              {c.regularisation ? ` · régularisation ${chf(c.regularisation.montant)}` : ''}
              {c.remboursement_partiel ? ' · remboursement partiel à vérifier' : ''}</p>
            {c.statut === 'pending' || c.statut === 'confirmed' || (c.statut === 'paid' && !c.regularisation) ? (
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 8 }}>
                <Bouton onClick={() => agir(adminAnnulerCommission(c.id, 'refunded'))} testid="admin-commission-rembourser">Achat remboursé</Bouton>
                <Bouton onClick={() => agir(adminAnnulerCommission(c.id, 'cancelled'))} testid="admin-commission-annuler">Annuler</Bouton>
              </div>
            ) : null}
          </li>
        ))}
      </ul>
    ) : <p className="cr-vide">Aucune conversion.</p>;
  } else if (vue === 'retraits') {
    const rows = liste('retraits');
    contenu = rows.length ? (
      <ul className="cr-liste">
        {rows.map((r) => (
          <li key={r.id} className="cr-carte" data-testid={`admin-retrait-${r.id}`}>
            <div className="cr-ligne" style={{ background: 'transparent', border: 'none', padding: 0 }}>
              <span className="cr-nom">{r.createur} · {chf(r.montant)}</span>
              <span className="cr-statut">{r.statut_libelle}</span>
            </div>
            <p className="cr-fine">{dateCourte(r.date)} · {r.email} · {r.methode === 'iban' ? 'IBAN' : 'TWINT'} : {r.payout_detail}</p>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 8 }}>
              {r.statut === 'pending' ? <Bouton onClick={() => agir(adminDecisionRetrait(r.id, 'approve'))} testid="admin-retrait-accepter">Accepter</Bouton> : null}
              {r.statut === 'pending' || r.statut === 'approved' ? (
                <>
                  <Bouton plein onClick={() => agir(adminDecisionRetrait(r.id, 'pay'))} testid="admin-retrait-payer">Marquer payé</Bouton>
                  <Bouton onClick={() => agir(adminDecisionRetrait(r.id, 'reject'))} testid="admin-retrait-refuser">Refuser</Bouton>
                </>
              ) : null}
            </div>
          </li>
        ))}
      </ul>
    ) : <p className="cr-vide">Aucune demande de retrait.</p>;
  }

  return (
    <div className="cr-root" data-testid="admin-createurs">
      <header className="cr-entete">
        <h2 className="cr-titre">Créateurs / Affiliation</h2>
        <p className="cr-sous">Commissions directes uniquement, sur achats payés. Paiements des retraits à effectuer manuellement.</p>
      </header>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }} role="tablist">
        {VUES.map(([id, libelle]) => (
          <button key={id} type="button" role="tab" aria-selected={vue === id} onClick={() => setVue(id)}
                  className={`cr-radio${vue === id ? ' on' : ''}`} style={{ font: 'inherit', color: 'inherit', background: 'transparent' }}
                  data-testid={`admin-vue-${id}`}>{libelle}</button>
        ))}
      </div>
      {erreur ? <p className="cr-erreur" role="alert" data-testid="admin-createurs-erreur">{erreur}</p> : null}
      {!donnees && !erreur ? <p className="cr-fine" role="status">Chargement…</p> : null}
      {donnees ? contenu : null}
    </div>
  );
}
