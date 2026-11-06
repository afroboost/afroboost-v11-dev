/**
 * V648 — section « Rappels de paiement » de la page Gestion → Paiements (coach uniquement).
 *
 * Tout passe par `/api/rappels-paiement` : le navigateur envoie une empreinte, une confirmation,
 * le texte du coach (avec des variables) et, si le suivi est incomplet, le montant confirmé. Le
 * serveur relit le montant, l'abonnement, le destinataire et les droits, et rend le message.
 * Aucun prélèvement. Rien ne part tant que l'envoi réel est coupé.
 *
 * V650 : l'éditeur et l'aide IA (une proposition, jamais un remplacement) ; l'automatique, activé
 * volontairement par le coach, ne part que si l'administration l'a ouvert.
 */
import React, { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '../ui/dialog';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';
const API = `${BACKEND_URL}/api/rappels-paiement`;

export const dateCH = (iso) => {
  const [a, m, j] = String(iso || '').slice(0, 10).split('-');
  return a && m && j ? `${j}.${m}.${a}` : iso || '';
};

const montant = (v, d) => `${Number(v).toFixed(2)} ${d || 'CHF'}`;

export const LIBELLES_STATUT = {
  envoye: 'Envoyé',
  echec: 'Refusé : aucun message parti',
  incertain: 'Envoi à vérifier : le message est peut-être parti',
  non_parti: 'Non parti : absence prouvée',
  en_cours: 'Envoi en cours',
};

const STYLE_FENETRE = { background: 'var(--background-color, #0a0a0a)', borderColor: 'rgba(var(--primary-rgb, 217, 28, 210), 0.35)' };
const CLASSE_FENETRE = 'w-[calc(100vw-32px)] max-w-lg max-h-[90vh] overflow-y-auto text-white rounded-lg outline-none focus:outline-none focus-visible:outline-none';
const STYLE_ACTION = { background: 'var(--primary-color, #D91CD2)', color: 'var(--primary-contrast-color, #fff)' };
const STYLE_BORD = { border: '1px solid var(--primary-color, #D91CD2)', color: 'var(--primary-color, #D91CD2)' };
const STYLE_CARTE = { background: 'rgba(255,255,255,0.06)' };

function detailErreur(err, secours) {
  const d = err?.response?.data?.detail;
  if (d && typeof d === 'object') return d;
  return { type: 'erreur', message: typeof d === 'string' ? d : secours };
}

function HistoriqueLignes({ lignes, avecCode = false }) {
  return (
    <ul className="space-y-2">
      {lignes.map((h) => (
        <li key={`${h.code || ''}-${h.echeance}-${h.palier}-${h.rang}`} className="rounded-md px-3 py-2 text-xs text-white/80" style={STYLE_CARTE}>
          <span className="font-semibold text-white">{h.etape}</span>
          {h.mode_envoi === 'automatique' && <span className="text-white/70" data-testid="v650-histo-auto"> · Automatique</span>}
          {avecCode && h.code && <span className="text-white/40 font-mono"> {h.code}</span>}
          {' · '}{LIBELLES_STATUT[h.statut] || h.statut}{' · '}{dateCH(h.envoye_le || h.maj_le)}
          <br />
          <span className="break-all">À {h.destinataire}</span>
          {' · '}{montant(h.montant, h.devise)} · échéance {dateCH(h.echeance)}
          <br />
          <span className="text-white/50 break-all">Par {h.envoye_par}</span>
        </li>
      ))}
    </ul>
  );
}

const TONS = [['chaleureux', 'Chaleureux'], ['professionnel', 'Professionnel'], ['direct', 'Direct']];

/** Objet, message, aide IA. La proposition reste à côté tant que le coach ne l'a pas acceptée. */
function EditeurTexte({ sujet, corps, onChange }) {
  const [ton, setTon] = useState('chaleureux');
  const [proposition, setProposition] = useState(null);
  const [attente, setAttente] = useState(false);
  const [refus, setRefus] = useState('');

  const demander = async () => {
    setRefus(''); setProposition(null); setAttente(true);
    try {
      setProposition((await axios.post(`${API}/aide-ia`, { sujet, corps, ton })).data.proposition);
    } catch (e) {
      setRefus(detailErreur(e, "L'aide IA n'a pas répondu. Ton texte n'a pas changé.").message);
    } finally {
      setAttente(false);
    }
  };

  return (
    <div className="space-y-2 text-xs text-white/80">
      <label className="block">
        Objet
        <input type="text" value={sujet} onChange={(e) => onChange({ sujet: e.target.value, corps })}
          className="w-full mt-1 px-2 py-1.5 rounded neon-input text-sm" data-testid="v650-objet" />
      </label>
      <label className="block">
        Message
        <textarea rows={5} value={corps} onChange={(e) => onChange({ sujet, corps: e.target.value })}
          className="w-full mt-1 px-2 py-1.5 rounded neon-input text-sm" data-testid="v650-corps" />
      </label>
      <p className="text-[11px] text-white/60">
        {'Garde {montant} et {echeance} : le serveur les remplit. La mention « si tu as déjà payé » et ta signature sont ajoutées.'}
      </p>
      <div className="flex flex-wrap items-center gap-2">
        <select value={ton} onChange={(e) => setTon(e.target.value)} aria-label="Ton" data-testid="v650-ton"
          className="px-2 py-1.5 rounded neon-input text-xs">
          {TONS.map(([v, n]) => <option key={v} value={v}>{n}</option>)}
        </select>
        <button type="button" disabled={attente} onClick={demander} data-testid="v650-aide-ia"
          className="px-2.5 py-1 rounded-md font-semibold disabled:opacity-40" style={STYLE_BORD}>
          {attente ? 'Aide IA…' : 'Aide IA'}
        </button>
      </div>
      {refus && <p className="text-red-400" data-testid="v650-ia-refus">{refus}</p>}
      {proposition && (
        <div className="rounded-md p-3 space-y-2" style={STYLE_CARTE} data-testid="v650-proposition">
          <p className="font-semibold text-white">{proposition.sujet}</p>
          <p className="whitespace-pre-wrap text-white/90">{proposition.corps}</p>
          <div className="flex flex-wrap gap-2">
            <button type="button" onClick={() => { onChange(proposition); setProposition(null); }} data-testid="v650-accepter"
              className="px-2.5 py-1 rounded-md font-semibold" style={STYLE_BORD}>Utiliser ce texte</button>
            <button type="button" onClick={() => setProposition(null)} data-testid="v650-ignorer"
              className="px-2.5 py-1 rounded-md text-white/80" style={{ border: '1px solid rgba(255,255,255,0.25)' }}>Ignorer</button>
          </div>
        </div>
      )}
    </div>
  );
}

export function RappelPaiementDialog({ rappel, envoiDemande = false, ouvert, onFermer, onEnvoye }) {
  const subId = rappel?.subscription_id;
  const [apercu, setApercu] = useState(null);
  const [chargement, setChargement] = useState(false);
  const [erreur, setErreur] = useState('');
  const [modeEnvoi, setModeEnvoi] = useState(false);
  const [confirme, setConfirme] = useState(false);
  const [montantSaisi, setMontantSaisi] = useState('');
  const [envoi, setEnvoi] = useState(false);
  const [resultat, setResultat] = useState(null);
  const [resendId, setResendId] = useState('');
  const [preuve, setPreuve] = useState(null);
  const [texte, setTexte] = useState(null);
  const [personnalise, setPersonnalise] = useState(false);
  const [noteModele, setNoteModele] = useState('');

  const recevoir = (donnees) => {
    setApercu(donnees);
    setTexte(donnees?.modele || null);
    setConfirme(false);
  };

  const verifier = async (absence) => {
    setErreur(''); setPreuve(null);
    try {
      const r = await axios.post(`${API}/${encodeURIComponent(subId)}/verifier-envoi`, absence ? { verifier_absence: true } : { resend_id: resendId.trim() });
      setPreuve(r.data);
      onEnvoye?.();
    } catch (e) {
      setErreur(detailErreur(e, "La vérification a échoué. Le blocage reste.").message);
    }
  };

  useEffect(() => {
    if (!ouvert || !subId) return undefined;
    let vivant = true;
    setApercu(null); setErreur(''); setConfirme(false); setMontantSaisi(''); setResultat(null);
    setTexte(null); setPersonnalise(false); setNoteModele('');
    setModeEnvoi(!!envoiDemande);
    setChargement(true);
    axios.get(`${API}/${encodeURIComponent(subId)}/apercu`)
      .then((r) => { if (vivant) recevoir(r.data); })
      .catch((e) => { if (vivant) setErreur(detailErreur(e, "L'aperçu n'a pas pu être chargé.").message); })
      .finally(() => { if (vivant) setChargement(false); });
    return () => { vivant = false; };
  }, [ouvert, subId, envoiDemande]);

  const etat = apercu?.envoi;
  const verification = !!apercu?.verification_requise;
  // Un texte modifié doit repasser par l'aperçu : on n'envoie que ce que le coach a vu.
  const modifie = !!(texte && apercu?.modele) && (texte.sujet !== apercu.modele.sujet || texte.corps !== apercu.modele.corps);
  const pret = confirme && !envoi && !modifie && (!verification || String(montantSaisi).trim() !== '');

  const actualiser = async () => {
    setErreur(''); setNoteModele('');
    try {
      recevoir((await axios.post(`${API}/${encodeURIComponent(subId)}/apercu`, texte)).data);
      setPersonnalise(true);
    } catch (e) {
      setErreur(detailErreur(e, "L'aperçu n'a pas pu être calculé.").message);
    }
  };
  const garderModele = async () => {
    setErreur(''); setNoteModele('');
    try {
      await axios.put(`${API}/modele`, texte);
      setNoteModele('Modèle enregistré pour tes prochains envois.');
    } catch (e) {
      setErreur(detailErreur(e, "Le modèle n'a pas été enregistré.").message);
    }
  };
  const reinitialiser = async () => {
    setErreur(''); setNoteModele('');
    try {
      await axios.delete(`${API}/modele`);
      recevoir((await axios.get(`${API}/${encodeURIComponent(subId)}/apercu`)).data);
      setPersonnalise(false);
      setNoteModele('Texte d\'origine rétabli.');
    } catch (e) {
      setErreur(detailErreur(e, "Le modèle n'a pas été réinitialisé.").message);
    }
  };

  const envoyer = async () => {
    if (!pret || !apercu?.empreinte) return;
    setEnvoi(true); setErreur('');
    try {
      const corps = { empreinte: apercu.empreinte, confirmation: true };
      if (verification) corps.montant_confirme = Number(String(montantSaisi).replace(',', '.'));
      if (personnalise && apercu.modele) { corps.sujet = apercu.modele.sujet; corps.corps = apercu.modele.corps; }
      const r = await axios.post(`${API}/${encodeURIComponent(subId)}/envoyer`, corps);
      setResultat(r.data);
      if (r.data?.envoye) onEnvoye?.();
    } catch (e) {
      const d = detailErreur(e, "Résultat inconnu : le message est peut-être parti. Rouvre l'aperçu avant toute autre action.");
      setErreur(d.message);
      setConfirme(false);
      onEnvoye?.();                      // la liste doit refléter l'état réel, même après un refus
    } finally {
      setEnvoi(false);
    }
  };

  return (
    <Dialog open={!!ouvert} onOpenChange={(o) => { if (!o) onFermer?.(); }}>
      <DialogContent className={CLASSE_FENETRE} style={STYLE_FENETRE} data-testid="v648-dialogue">
        <DialogHeader>
          <DialogTitle className="text-left">{etat?.etape ? `${etat.etape} de paiement` : 'Rappel de paiement'}</DialogTitle>
          <DialogDescription className="text-left text-white/60">Vérifie le message avant de confirmer.</DialogDescription>
        </DialogHeader>

        {chargement && <p className="text-sm text-white/70" data-testid="v648-chargement">Chargement…</p>}

        {apercu && apercu.possible === false && (
          <p className="text-sm text-white" data-testid="v648-impossible">{apercu.message}</p>
        )}

        {apercu?.possible && !resultat && (
          <div className="space-y-3 text-sm">
            {apercu.envoi_reel === false && (
              <p className="text-xs rounded-md px-3 py-2 text-white" data-testid="v648-envoi-coupe"
                style={{ background: 'rgba(var(--primary-rgb, 217, 28, 210), 0.15)' }}>
                L'envoi réel est désactivé : aucun e-mail ne partira.
              </p>
            )}
            <dl className="grid grid-cols-[auto,1fr] gap-x-3 gap-y-1 text-xs">
              <dt className="text-white/50">À</dt>
              <dd className="text-white break-all" data-testid="v648-destinataire">{apercu.destinataire}</dd>
              <dt className="text-white/50">Solde calculé</dt>
              <dd className="text-white font-semibold" data-testid="v648-montant">{montant(apercu.reste, apercu.devise)}</dd>
              {apercu.mode_paiement && <><dt className="text-white/50">Mode</dt><dd className="text-white" data-testid="v649-mode-apercu">{apercu.mode_paiement}</dd></>}
              <dt className="text-white/50">Échéance</dt>
              <dd className="text-white" data-testid="v648-echeance">{dateCH(apercu.echeance)}</dd>
              <dt className="text-white/50">Objet</dt>
              <dd className="text-white" data-testid="v648-sujet">{apercu.sujet}</dd>
            </dl>
            <div className="rounded-md px-3 py-3 text-white/90 whitespace-pre-wrap text-sm" data-testid="v648-texte" style={STYLE_CARTE}>{apercu.texte}</div>

            {texte && etat?.peut_envoyer && (
              <details className="text-xs" data-testid="v650-editeur">
                <summary className="cursor-pointer text-white font-semibold">Modifier le message</summary>
                <div className="mt-2 space-y-2">
                  <EditeurTexte sujet={texte.sujet} corps={texte.corps} onChange={setTexte} />
                  <div className="flex flex-wrap gap-2">
                    <button type="button" disabled={!modifie} onClick={actualiser} data-testid="v650-actualiser"
                      className="px-2.5 py-1 rounded-md font-semibold disabled:opacity-40" style={STYLE_BORD}>Voir l'aperçu</button>
                    <button type="button" onClick={garderModele} data-testid="v650-garder"
                      className="px-2.5 py-1 rounded-md text-white/80" style={{ border: '1px solid rgba(255,255,255,0.25)' }}>Garder comme modèle</button>
                    <button type="button" onClick={reinitialiser} data-testid="v650-reinitialiser"
                      className="px-2.5 py-1 rounded-md text-white/80" style={{ border: '1px solid rgba(255,255,255,0.25)' }}>Réinitialiser</button>
                  </div>
                  {modifie && <p className="text-white font-semibold" data-testid="v650-a-revoir">Texte modifié : ouvre l'aperçu avant d'envoyer.</p>}
                  {noteModele && <p className="text-white/70" data-testid="v650-note">{noteModele}</p>}
                </div>
              </details>
            )}

            {apercu.avertissement && (
              <p className="text-xs text-white font-semibold" data-testid="v648-avertissement">{apercu.avertissement}</p>
            )}

            {etat && !etat.peut_envoyer && (
              <p className="text-sm text-white font-semibold" data-testid="v648-envoi-bloque">
                {etat.message}
              </p>
            )}

            {etat?.verification_admin && !preuve?.resolu && (
              <div className="rounded-md p-3 space-y-2" style={STYLE_CARTE} data-testid="v648-verification">
                <label className="block text-xs text-white">
                  Identifiant de l'e-mail chez le fournisseur (si le journal n'en a pas)
                  <input type="text" value={resendId} onChange={(e) => setResendId(e.target.value)}
                    className="w-full mt-1 px-2 py-1.5 rounded neon-input text-sm" data-testid="v648-resend-id" />
                </label>
                <button type="button" onClick={() => verifier(false)} data-testid="v648-verifier"
                  className="w-full py-2 rounded-md text-sm font-semibold" style={STYLE_BORD}>
                  Vérifier que l'e-mail est parti
                </button>
                <button type="button" onClick={() => verifier(true)} data-testid="v648-verifier-absence"
                  className="w-full py-2 rounded-md text-sm font-semibold text-white/80" style={{ border: '1px solid rgba(255,255,255,0.25)' }}>
                  Vérifier qu'il n'est pas parti
                </button>
                <p className="text-[11px] text-white/60">N'envoie rien. Sans preuve, le blocage reste.</p>
              </div>
            )}
            {preuve && <p className="text-sm text-white font-semibold" data-testid="v648-preuve">{preuve.message}</p>}

            {etat?.peut_envoyer && !modeEnvoi && (
              <button type="button" onClick={() => setModeEnvoi(true)} data-testid="v648-continuer"
                className="w-full py-2 rounded-md text-sm font-semibold" style={STYLE_BORD}>
                Continuer vers l'envoi
              </button>
            )}

            {etat?.peut_envoyer && modeEnvoi && (
              <>
                {verification && (
                  <label className="block text-xs text-white">
                    Montant réellement dû, vérifié par toi ({apercu.devise || 'CHF'})
                    <input type="text" inputMode="decimal" value={montantSaisi} onChange={(e) => setMontantSaisi(e.target.value)}
                      className="w-full mt-1 px-2 py-1.5 rounded neon-input text-sm" data-testid="v648-montant-confirme" />
                  </label>
                )}
                <label className="flex items-start gap-2 text-xs text-white cursor-pointer">
                  <input type="checkbox" className="w-4 h-4 mt-0.5 rounded" checked={confirme}
                    onChange={(e) => setConfirme(e.target.checked)} data-testid="v648-confirmation" />
                  Je confirme que ce solde reste dû et que je veux envoyer ce message.
                </label>
                <button type="button" disabled={!pret} onClick={envoyer} data-testid="v648-envoyer"
                  className="w-full py-2 rounded-md text-sm font-semibold disabled:opacity-40 disabled:cursor-not-allowed"
                  style={STYLE_ACTION}>
                  {envoi ? 'Envoi…' : `Envoyer : ${etat.etape}`}
                </button>
              </>
            )}
          </div>
        )}

        {resultat && (
          <p className="text-sm text-white font-semibold" data-testid="v648-resultat">{resultat.message}</p>
        )}
        {erreur && <p className="text-sm text-red-400" data-testid="v648-erreur">{erreur}</p>}

        {(apercu?.historique || []).length > 0 && (
          <details className="text-xs text-white/70" data-testid="v648-historique">
            <summary className="cursor-pointer">Historique de ce client ({apercu.historique.length})</summary>
            <div className="mt-2"><HistoriqueLignes lignes={apercu.historique} /></div>
          </details>
        )}
      </DialogContent>
    </Dialog>
  );
}

const DELAIS = ['J-3', 'J0', 'J+3'];

/** La règle est sur le serveur : cet écran affiche son refus, il ne la recopie pas. */
function SignaturePartenaire({ valeur, onEnregistre }) {
  const [nom, setNom] = useState(valeur?.nom || '');
  const [activite, setActivite] = useState(valeur?.activite || '');
  const [refus, setRefus] = useState('');
  const [apercu, setApercu] = useState('');

  const enregistrer = async () => {
    setRefus(''); setApercu('');
    try {
      const r = await axios.put(`${API}/signature`, { nom, activite });
      setApercu(r.data?.apercu || '');
      onEnregistre?.();
    } catch (e) {
      setRefus(detailErreur(e, "La signature n'a pas été enregistrée.").message);
    }
  };

  return (
    <div className="rounded-md p-3 space-y-2" style={STYLE_CARTE} data-testid="v648-signature">
      <p className="text-xs font-semibold text-white">Ta signature</p>
      <label className="block text-xs text-white/80">
        Nom professionnel
        <input type="text" value={nom} onChange={(e) => setNom(e.target.value)}
          className="w-full mt-1 px-2 py-1.5 rounded neon-input text-sm" data-testid="v648-signature-nom" />
      </label>
      <label className="block text-xs text-white/80">
        Activité (facultatif)
        <input type="text" value={activite} onChange={(e) => setActivite(e.target.value)}
          className="w-full mt-1 px-2 py-1.5 rounded neon-input text-sm" data-testid="v648-signature-activite" />
      </label>
      <button type="button" onClick={enregistrer} data-testid="v648-signature-enregistrer"
        className="px-2.5 py-1 rounded-md text-xs font-semibold" style={STYLE_BORD}>
        Enregistrer ma signature
      </button>
      {refus && <p className="text-xs text-red-400" data-testid="v648-signature-refus">{refus}</p>}
      {apercu && <p className="text-xs text-white/80 whitespace-pre-wrap" data-testid="v648-signature-apercu">{apercu}</p>}
    </div>
  );
}

/** Le texte des envois futurs, sans passer par une ligne. */
function ModeleAutomatique({ reglages, onChange }) {
  const defaut = reglages.modele_defaut || { sujet: '', corps: '' };
  const [texte, setTexte] = useState({ sujet: reglages.modele?.sujet || defaut.sujet, corps: reglages.modele?.corps || defaut.corps });
  const [note, setNote] = useState('');
  const [refus, setRefus] = useState('');

  const garder = async () => {
    setNote(''); setRefus('');
    try {
      await axios.put(`${API}/modele`, texte);
      setNote('Modèle enregistré.');
      onChange?.();
    } catch (e) {
      setRefus(detailErreur(e, "Le modèle n'a pas été enregistré.").message);
    }
  };
  const effacer = async () => {
    setNote(''); setRefus('');
    try {
      await axios.delete(`${API}/modele`);
      setTexte({ sujet: defaut.sujet, corps: defaut.corps });
      setNote('Texte d\'origine rétabli.');
      onChange?.();
    } catch (e) {
      setRefus(detailErreur(e, "Le modèle n'a pas été réinitialisé.").message);
    }
  };

  return (
    <details className="text-xs" data-testid="v650-modele-auto">
      <summary className="cursor-pointer font-semibold">Modèle des prochains envois</summary>
      <div className="mt-2 space-y-2">
        <EditeurTexte sujet={texte.sujet} corps={texte.corps} onChange={setTexte} />
        <div className="flex flex-wrap gap-2">
          <button type="button" onClick={garder} data-testid="v650-modele-garder"
            className="px-2.5 py-1 rounded-md font-semibold" style={STYLE_BORD}>Enregistrer</button>
          <button type="button" onClick={effacer} data-testid="v650-modele-effacer"
            className="px-2.5 py-1 rounded-md text-white/80" style={{ border: '1px solid rgba(255,255,255,0.25)' }}>Réinitialiser</button>
        </div>
        {note && <p className="text-white/70" data-testid="v650-modele-note">{note}</p>}
        {refus && <p className="text-red-400" data-testid="v650-modele-refus">{refus}</p>}
      </div>
    </details>
  );
}

function ReglagesRappels({ enregistrer, reglages, erreur, enregistre, onModele }) {
  const [simulation, setSimulation] = useState(null);
  const [erreurSim, setErreurSim] = useState('');
  const [delaiSaisi, setDelaiSaisi] = useState(String(reglages.delai_relance_jours ?? 7));
  const [demandeAuto, setDemandeAuto] = useState(false);
  const delai = reglages.delai_relance_jours ?? 7;

  useEffect(() => { setDelaiSaisi(String(reglages.delai_relance_jours ?? 7)); }, [reglages.delai_relance_jours]);

  const voirSimulation = async () => {
    setErreurSim('');
    try {
      setSimulation((await axios.get(`${API}/simulation`)).data);
    } catch (e) {
      setErreurSim(detailErreur(e, "La simulation n'a pas pu être calculée.").message);
    }
  };
  const basculerDelai = (d) => {
    const set = new Set(reglages.delais || []);
    if (set.has(d)) set.delete(d); else set.add(d);
    setSimulation(null);
    enregistrer({ delais: DELAIS.filter((x) => set.has(x)) });
  };
  const validerDelai = () => {
    const n = Number(delaiSaisi);
    if (n !== reglages.delai_relance_jours) enregistrer({ delai_relance_jours: n });
  };

  return (
    <div className="space-y-3 text-sm text-white" data-testid="v648-reglages">
      {[['MANUEL', 'Manuel', 'Tu choisis quand envoyer chaque rappel.'],
        ['AUTOMATIQUE', 'Automatique', "Les rappels partent seuls, même si tu n'es pas connecté."]].map(([val, nom, aide]) => (
        <label key={val} className="flex items-start gap-2 cursor-pointer">
          <input type="radio" name="v648-mode" className="mt-1" checked={reglages.mode === val}
            onChange={() => {
              setSimulation(null);
              if (val === 'AUTOMATIQUE') { setDemandeAuto(true); return; }
              setDemandeAuto(false);
              enregistrer({ mode: val });
            }} data-testid={`v648-mode-${val}`} />
          <span><span className="font-semibold">{nom}</span><br /><span className="text-xs text-white/60">{aide}</span></span>
        </label>
      ))}

      {demandeAuto && reglages.mode !== 'AUTOMATIQUE' && (
        <div className="rounded-md p-3 space-y-2 text-xs" style={STYLE_CARTE} data-testid="v650-auto-demande">
          <p>De vrais e-mails partiront sans toi, du lundi au vendredi, de 8 h à 18 h. Les échéances déjà passées ne seront pas relancées.</p>
          <div className="flex flex-wrap gap-2">
            <button type="button" onClick={() => { setDemandeAuto(false); enregistrer({ mode: 'AUTOMATIQUE', confirmation_auto: true }); }}
              data-testid="v650-auto-confirmer" className="px-2.5 py-1 rounded-md font-semibold" style={STYLE_ACTION}>Activer l'automatique</button>
            <button type="button" onClick={() => setDemandeAuto(false)} data-testid="v650-auto-annuler"
              className="px-2.5 py-1 rounded-md text-white/80" style={{ border: '1px solid rgba(255,255,255,0.25)' }}>Annuler</button>
          </div>
        </div>
      )}

      <label className="block text-xs text-white/80">
        Délai entre deux rappels (7 à 60 jours, 3 rappels au plus par paiement)
        <input type="number" min="7" max="60" value={delaiSaisi} onChange={(e) => setDelaiSaisi(e.target.value)} onBlur={validerDelai}
          className="block w-20 mt-1 px-2 py-1.5 rounded neon-input text-sm" data-testid="v648-delai-relance" />
      </label>

      {reglages.mode === 'AUTOMATIQUE' && (
        <div className="rounded-md p-3 space-y-2" style={STYLE_CARTE}>
          {reglages.automatisation_disponible ? (
            <p className="text-xs font-semibold" data-testid="v650-auto-actif">Automatique activé.</p>
          ) : (
            <p className="text-xs font-semibold" data-testid="v648-auto-coupe">
              Ton choix est enregistré. Aucun rappel ne part tant que l'administration n'a pas ouvert l'automatique.
            </p>
          )}
          <p className="text-xs text-white/70" data-testid="v650-politique">
            {`Premier rappel au plus tôt des délais cochés, puis tous les ${delai} jours, 3 au plus. J0 et J+3 ne suivent donc pas J-3 de quelques jours.`}
          </p>
          <ModeleAutomatique reglages={reglages} onChange={onModele} />
          <div className="flex flex-wrap gap-3 text-xs">
            {DELAIS.map((d) => (
              <label key={d} className="inline-flex items-center gap-1.5 cursor-pointer">
                <input type="checkbox" checked={(reglages.delais || []).includes(d)} onChange={() => basculerDelai(d)}
                  data-testid={`v648-delai-${d}`} /> {d}
              </label>
            ))}
          </div>
          <button type="button" onClick={voirSimulation} data-testid="v648-voir-simulation"
            className="text-xs underline" style={{ color: 'var(--primary-color, #D91CD2)' }}>
            Voir la simulation
          </button>
          {simulation && (
            <div data-testid="v648-simulation" className="text-xs space-y-2">
              <p className="font-semibold">Simulation : aucun e-mail n'est envoyé.</p>
              {simulation.lignes.length === 0 && <p className="text-white/60">Aucun abonnement concerné.</p>}
              <ul className="space-y-2">
                {simulation.lignes.map((l) => (
                  <li key={l.code} className="rounded-md px-3 py-2" style={{ background: 'rgba(0,0,0,0.35)' }} data-testid={`v648-sim-${l.code}`}>
                    <span className="font-semibold">{l.nom || l.code}</span>
                    <span className="text-white/40 font-mono"> {l.code}</span>
                    {l.enverrait ? (
                      <p className="text-white/80 mt-1">
                        {l.jalons.filter((j) => j.etat !== 'passe').map((j) => `${j.palier} : ${dateCH(j.date)}`).join(' · ') || 'Tous les délais sont passés'}
                      </p>
                    ) : (
                      <p className="text-white/60 mt-1">Exclu : {l.message_exclusion}</p>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
      {enregistre && <p className="text-xs text-white/60" data-testid="v648-enregistre">Enregistré.</p>}
      {(erreur || erreurSim) && <p className="text-sm text-red-400" data-testid="v648-reglages-erreur">{erreur || erreurSim}</p>}
    </div>
  );
}

function libelleEnvoi(etat) {
  return etat.etape === 'Rappel' ? 'Envoyer le rappel' : 'Envoyer la relance';
}

function LigneRappel({ ligne, onOuvrir }) {
  const etat = ligne.envoi;
  return (
    <li data-testid={`v648-ligne-${ligne.code}`} className="text-xs rounded-md px-3 py-2" style={STYLE_CARTE}>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <span className="text-white font-semibold">{ligne.nom || ligne.code}</span>
        {ligne.paiement_suivant && <span className="text-white/70">Paiement {ligne.paiement_suivant}</span>}
        {ligne.mode_paiement && <span className="text-white/70" data-testid={`v649-mode-${ligne.code}`}>{ligne.mode_paiement}</span>}
        <span style={{ color: 'var(--primary-color, #D91CD2)', fontWeight: 600 }}>
          {montant(ligne.reste_a_payer, ligne.devise)} calculés
        </span>
        <span className={ligne.en_retard ? 'text-red-400 font-semibold' : 'text-white/70'}>
          {ligne.en_retard ? 'En retard — échéance ' : 'Échéance : '}{dateCH(ligne.prochaine_echeance)}
        </span>
        <span className="text-white/40 font-mono">{ligne.code}</span>
      </div>
      {!ligne.possible && (
        <p className="text-white/60 mt-2" data-testid={`v648-bloque-${ligne.code}`}>{ligne.message}</p>
      )}
      {ligne.possible && (
        <div className="flex flex-wrap items-center gap-2 mt-2">
          <button type="button" onClick={() => onOuvrir(ligne, false)} data-testid={`v648-voir-${ligne.code}`}
            className="px-2.5 py-1 rounded-md text-white/80" style={{ border: '1px solid rgba(255,255,255,0.25)' }}>
            Prévisualiser
          </button>
          {etat?.peut_envoyer && (
            <button type="button" onClick={() => onOuvrir(ligne, true)} data-testid={`v648-rappel-${ligne.code}`}
              className="px-2.5 py-1 rounded-md font-semibold" style={STYLE_BORD}>
              {libelleEnvoi(etat)}
            </button>
          )}
          {etat?.a_verifier && (
            <span className="font-semibold text-red-400" data-testid={`v648-a-verifier-envoi-${ligne.code}`}>Envoi à vérifier</span>
          )}
          {etat && !etat.peut_envoyer && (
            <span className="text-white/70" data-testid={`v648-attente-${ligne.code}`}>
              {etat.type === 'deja_envoye' && etat.prochaine_le ? `Prochain envoi possible le ${dateCH(etat.prochaine_le)}` : etat.message}
            </span>
          )}
          {ligne.verification_requise && (
            <span className="text-white/70" data-testid={`v648-a-verifier-${ligne.code}`}>Montant à vérifier avant l'envoi</span>
          )}
        </div>
      )}
    </li>
  );
}

export default function RappelsPaiementSection() {
  const [lignes, setLignes] = useState(null);
  const [historique, setHistorique] = useState([]);
  const [reglages, setReglages] = useState(null);
  const [envoiReel, setEnvoiReel] = useState(false);
  const [erreurListe, setErreurListe] = useState('');
  const [erreurReglages, setErreurReglages] = useState('');
  const [enregistre, setEnregistre] = useState(false);
  const [cible, setCible] = useState(null);
  const [envoiDemande, setEnvoiDemande] = useState(false);

  const relire = useCallback(() => {
    axios.get(`${API}/liste`)
      .then((r) => {
        setLignes(Array.isArray(r?.data?.lignes) ? r.data.lignes : []);
        setEnvoiReel(r?.data?.envoi_reel === true);
        setErreurListe('');
      })
      .catch((e) => { setLignes([]); setErreurListe(detailErreur(e, "La liste n'a pas pu être chargée.").message); });
    axios.get(`${API}/historique`)
      .then((r) => setHistorique(Array.isArray(r?.data?.historique) ? r.data.historique : []))
      .catch(() => setHistorique([]));
  }, []);

  useEffect(() => {
    let vivant = true;
    relire();
    axios.get(`${API}/reglages`)
      .then((r) => { if (vivant) setReglages(r.data); })
      .catch(() => { if (vivant) setErreurReglages("Le réglage n'a pas pu être chargé."); });
    return () => { vivant = false; };
  }, [relire]);

  const enregistrer = async (suivant) => {
    setErreurReglages(''); setEnregistre(false);
    const avant = reglages;
    const fusion = { ...reglages, ...suivant };
    setReglages(fusion);
    try {
      const { confirmation_auto: confirmationAuto, ...garde } = fusion;
      setReglages(garde);
      const r = await axios.put(`${API}/reglages`, {
        mode: garde.mode, delais: garde.delais, delai_relance_jours: garde.delai_relance_jours,
        ...(confirmationAuto ? { confirmation_auto: true } : {}),
      });
      if (r?.data?.auto_actif_depuis !== undefined) setReglages({ ...garde, auto_actif_depuis: r.data.auto_actif_depuis });
      setEnregistre(true);
      relire();
    } catch (e) {
      setReglages(avant);
      setErreurReglages(detailErreur(e, "Le réglage n'a pas été enregistré.").message);
    }
  };

  return (
    <div className="space-y-5" data-testid="v648-section">
      {!envoiReel && (
        <p className="text-xs rounded-md px-3 py-2 text-white" data-testid="v648-section-coupe"
          style={{ background: 'rgba(var(--primary-rgb, 217, 28, 210), 0.15)' }}>
          L'envoi réel est désactivé : aucun e-mail ne partira.
        </p>
      )}

      {reglages && reglages.signature_officielle === false && (
        <SignaturePartenaire valeur={reglages.signature} onEnregistre={relire} />
      )}

      {reglages && (
        <ReglagesRappels reglages={reglages} enregistrer={enregistrer} erreur={erreurReglages} enregistre={enregistre} onModele={relire} />
      )}

      <div>
        <p className="text-white text-sm font-semibold mb-2">Paiements restant à encaisser</p>
        {lignes === null && <p className="text-xs text-white/60">Chargement…</p>}
        {erreurListe && <p className="text-sm text-red-400" data-testid="v648-liste-erreur">{erreurListe}</p>}
        {lignes && !lignes.length && !erreurListe && <p className="text-xs text-white/60" data-testid="v648-liste-vide">Aucun paiement restant.</p>}
        {lignes && lignes.length > 0 && (
          <ul className="space-y-2" data-testid="v648-liste">
            {lignes.map((l) => (
              <LigneRappel key={l.subscription_id} ligne={l}
                onOuvrir={(ligne, envoi) => { setEnvoiDemande(envoi); setCible(ligne); }} />
            ))}
          </ul>
        )}
        <p className="text-white/40 text-[11px] mt-2">
          Solde calculé depuis tes saisies, ce n'est pas une preuve de non-paiement. Rien n'est prélevé.
        </p>
      </div>

      <details data-testid="v648-historique-general">
        <summary className="text-white text-sm font-semibold cursor-pointer">Historique des rappels ({historique.length})</summary>
        <div className="mt-2">
          {historique.length === 0
            ? <p className="text-xs text-white/60">Aucun rappel envoyé.</p>
            : <HistoriqueLignes lignes={historique} avecCode />}
        </div>
      </details>

      <RappelPaiementDialog rappel={cible} envoiDemande={envoiDemande} ouvert={!!cible}
        onFermer={() => setCible(null)} onEnvoye={relire} />
    </div>
  );
}
