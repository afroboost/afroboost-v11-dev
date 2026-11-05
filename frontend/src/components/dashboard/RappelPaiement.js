/**
 * V648 — RAPPEL DU DEUXIÈME PAIEMENT (coach uniquement).
 *
 * RappelPaiementDialog : aperçu obligatoire, puis confirmation explicite. Le navigateur n'envoie
 * qu'une empreinte et une confirmation : le serveur relit le montant, l'abonnement, le destinataire
 * et les droits, et reconstruit le message. Rien de ce qui est affiché ici ne part tel quel.
 *
 * RappelPaiementReglages : le choix Manuel / Automatique. L'automatique n'est PAS activé : ce choix
 * est rangé et les délais J-3, J0, J+3 ne sont montrés qu'en simulation, en lecture seule.
 */
import React, { useEffect, useState } from 'react';
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
  incertain: 'À vérifier : le message est peut-être parti',
  en_cours: 'Envoi en cours',
};

const STYLE_FENETRE = { background: 'var(--background-color, #0a0a0a)', borderColor: 'rgba(var(--primary-rgb, 217, 28, 210), 0.35)' };
const CLASSE_FENETRE = 'w-[calc(100vw-32px)] max-w-lg max-h-[90vh] overflow-y-auto text-white rounded-lg outline-none focus:outline-none focus-visible:outline-none';
const STYLE_ACTION = { background: 'var(--primary-color, #D91CD2)', color: 'var(--primary-contrast-color, #fff)' };

function detailErreur(err, secours) {
  const d = err?.response?.data?.detail;
  if (d && typeof d === 'object') return d;
  return { type: 'erreur', message: typeof d === 'string' ? d : secours };
}

export function RappelPaiementDialog({ rappel, ouvert, onFermer, onEnvoye }) {
  const subId = rappel?.subscription_id;
  const [apercu, setApercu] = useState(null);
  const [chargement, setChargement] = useState(false);
  const [erreur, setErreur] = useState('');
  const [confirme, setConfirme] = useState(false);
  const [envoi, setEnvoi] = useState(false);
  const [resultat, setResultat] = useState(null);
  const [repriseOfferte, setRepriseOfferte] = useState(false);

  useEffect(() => {
    if (!ouvert || !subId) return undefined;
    let vivant = true;
    setApercu(null); setErreur(''); setConfirme(false); setResultat(null); setRepriseOfferte(false);
    setChargement(true);
    axios.get(`${API}/${encodeURIComponent(subId)}/apercu`)
      .then((r) => { if (vivant) setApercu(r.data); })
      .catch((e) => { if (vivant) setErreur(detailErreur(e, "L'aperçu n'a pas pu être chargé.").message); })
      .finally(() => { if (vivant) setChargement(false); });
    return () => { vivant = false; };
  }, [ouvert, subId]);

  const dejaFait = (apercu?.historique || []).find((h) => h.echeance === apercu?.echeance && h.palier === 'manuel');
  const dejaEnvoye = dejaFait?.statut === 'envoye';
  const incertain = dejaFait?.statut === 'incertain' || repriseOfferte;

  const envoyer = async () => {
    if (!confirme || envoi || !apercu?.empreinte) return;
    setEnvoi(true); setErreur('');
    try {
      const r = await axios.post(`${API}/${encodeURIComponent(subId)}/envoyer`, {
        empreinte: apercu.empreinte, confirmation: true, reprise_incertain: incertain,
      });
      setResultat(r.data);
      if (r.data?.envoye) onEnvoye?.();
    } catch (e) {
      const d = detailErreur(e, "L'envoi a échoué : aucun message n'est parti.");
      setErreur(d.message);
      if (d.reprise_possible) setRepriseOfferte(true);
      setConfirme(false);
      onEnvoye?.();                      // l'encadré doit refléter l'état réel, même après un refus
    } finally {
      setEnvoi(false);
    }
  };

  return (
    <Dialog open={!!ouvert} onOpenChange={(o) => { if (!o) onFermer?.(); }}>
      <DialogContent className={CLASSE_FENETRE} style={STYLE_FENETRE} data-testid="v648-dialogue">
        <DialogHeader>
          <DialogTitle className="text-left">Rappel de paiement</DialogTitle>
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
              <dt className="text-white/50">Solde</dt>
              <dd className="text-white font-semibold" data-testid="v648-montant">{montant(apercu.reste, apercu.devise)}</dd>
              <dt className="text-white/50">Échéance</dt>
              <dd className="text-white" data-testid="v648-echeance">{dateCH(apercu.echeance)}</dd>
              <dt className="text-white/50">Objet</dt>
              <dd className="text-white" data-testid="v648-sujet">{apercu.sujet}</dd>
            </dl>
            <div className="rounded-md px-3 py-3 text-white/90 whitespace-pre-wrap text-sm" data-testid="v648-texte"
              style={{ background: 'rgba(255,255,255,0.06)' }}>{apercu.texte}</div>

            {apercu.avertissement && (
              <p className="text-xs text-white" data-testid="v648-avertissement">{apercu.avertissement}</p>
            )}

            {dejaEnvoye ? (
              <p className="text-sm text-white font-semibold" data-testid="v648-deja-envoye">
                Déjà envoyé le {dateCH(dejaFait.envoye_le)} pour cette échéance.
              </p>
            ) : (
              <>
                {incertain && (
                  <p className="text-xs text-white" data-testid="v648-incertain">
                    Le dernier envoi n'a pas pu être confirmé. Réessayer ne crée pas de doublon pendant 23 heures.
                  </p>
                )}
                <label className="flex items-start gap-2 text-xs text-white cursor-pointer">
                  <input type="checkbox" className="w-4 h-4 mt-0.5 rounded" checked={confirme}
                    onChange={(e) => setConfirme(e.target.checked)} data-testid="v648-confirmation" />
                  Je confirme que ce solde reste dû et que je veux envoyer ce rappel.
                </label>
                <button type="button" disabled={!confirme || envoi} onClick={envoyer} data-testid="v648-envoyer"
                  className="w-full py-2 rounded-md text-sm font-semibold disabled:opacity-40 disabled:cursor-not-allowed"
                  style={STYLE_ACTION}>
                  {envoi ? 'Envoi…' : (incertain ? 'Réessayer' : 'Envoyer le rappel')}
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
            <summary className="cursor-pointer">Historique ({apercu.historique.length})</summary>
            <ul className="mt-2 space-y-1">
              {apercu.historique.map((h) => (
                <li key={`${h.echeance}-${h.palier}`}>
                  Échéance {dateCH(h.echeance)} · {montant(h.montant, h.devise)} · {LIBELLES_STATUT[h.statut] || h.statut}
                  {h.envoye_le ? ` le ${dateCH(h.envoye_le)}` : ''}
                </li>
              ))}
            </ul>
          </details>
        )}
      </DialogContent>
    </Dialog>
  );
}

const DELAIS = ['J-3', 'J0', 'J+3'];

export function RappelPaiementReglages({ ouvert, onFermer }) {
  const [reglages, setReglages] = useState(null);
  const [simulation, setSimulation] = useState(null);
  const [erreur, setErreur] = useState('');
  const [enregistre, setEnregistre] = useState(false);

  useEffect(() => {
    if (!ouvert) return undefined;
    let vivant = true;
    setErreur(''); setSimulation(null); setEnregistre(false);
    axios.get(`${API}/reglages`)
      .then((r) => { if (vivant) setReglages(r.data); })
      .catch(() => { if (vivant) setErreur('Le réglage n\'a pas pu être chargé.'); });
    return () => { vivant = false; };
  }, [ouvert]);

  const enregistrer = async (suivant) => {
    setErreur(''); setEnregistre(false);
    const avant = reglages;
    setReglages({ ...reglages, ...suivant });
    try {
      await axios.put(`${API}/reglages`, { mode: suivant.mode ?? reglages.mode, delais: suivant.delais ?? reglages.delais });
      setEnregistre(true);
      setSimulation(null);
    } catch (e) {
      setReglages(avant);
      setErreur(detailErreur(e, "Le réglage n'a pas été enregistré.").message);
    }
  };

  const voirSimulation = async () => {
    setErreur('');
    try {
      setSimulation((await axios.get(`${API}/simulation`)).data);
    } catch (e) {
      setErreur(detailErreur(e, "La simulation n'a pas pu être calculée.").message);
    }
  };

  const basculerDelai = (d) => {
    const set = new Set(reglages.delais || []);
    if (set.has(d)) set.delete(d); else set.add(d);
    enregistrer({ delais: DELAIS.filter((x) => set.has(x)) });
  };

  return (
    <Dialog open={!!ouvert} onOpenChange={(o) => { if (!o) onFermer?.(); }}>
      <DialogContent className={CLASSE_FENETRE} style={STYLE_FENETRE} data-testid="v648-reglages">
        <DialogHeader>
          <DialogTitle className="text-left">Rappel du deuxième paiement</DialogTitle>
          <DialogDescription className="text-left text-white/60">
            Aucun prélèvement : un rappel n'est qu'un e-mail.
          </DialogDescription>
        </DialogHeader>
        {reglages && (
          <div className="space-y-3 text-sm text-white">
            {[['MANUEL', 'Manuel', 'Tu choisis quand envoyer chaque rappel.'],
              ['AUTOMATIQUE', 'Automatique', 'Prévu pour plus tard : rien ne part tout seul pour le moment.']].map(([val, nom, aide]) => (
              <label key={val} className="flex items-start gap-2 cursor-pointer">
                <input type="radio" name="v648-mode" className="mt-1" checked={reglages.mode === val}
                  onChange={() => enregistrer({ mode: val })} data-testid={`v648-mode-${val}`} />
                <span><span className="font-semibold">{nom}</span><br /><span className="text-xs text-white/60">{aide}</span></span>
              </label>
            ))}

            {reglages.mode === 'AUTOMATIQUE' && (
              <div className="rounded-md p-3 space-y-2" style={{ background: 'rgba(255,255,255,0.06)' }}>
                <p className="text-xs font-semibold" data-testid="v648-auto-coupe">
                  L'automatique n'est pas activé. Aucun rappel ne part tout seul.
                </p>
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
              </div>
            )}

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
            {enregistre && <p className="text-xs text-white/60" data-testid="v648-enregistre">Enregistré.</p>}
          </div>
        )}
        {erreur && <p className="text-sm text-red-400" data-testid="v648-reglages-erreur">{erreur}</p>}
      </DialogContent>
    </Dialog>
  );
}
