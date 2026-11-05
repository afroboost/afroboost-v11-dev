/**
 * V648 — section « Rappels de paiement » de la page Gestion → Paiements (coach uniquement).
 *
 * Tout passe par `/api/rappels-paiement` : le navigateur n'envoie qu'une empreinte, une
 * confirmation et, si le suivi est incomplet, le montant confirmé par le coach. Le serveur relit
 * le montant, l'abonnement, le destinataire et les droits, et reconstruit le message.
 * Aucun prélèvement. Rien ne part sans le clic du coach, et rien tant que l'envoi réel est coupé.
 *
 * L'automatique n'est PAS activé : ce choix est rangé, J-3, J0 et J+3 ne sont montrés qu'en
 * simulation, en lecture seule.
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
  incertain: 'À vérifier : le message est peut-être parti',
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
  const [repriseOfferte, setRepriseOfferte] = useState(false);

  useEffect(() => {
    if (!ouvert || !subId) return undefined;
    let vivant = true;
    setApercu(null); setErreur(''); setConfirme(false); setMontantSaisi(''); setResultat(null); setRepriseOfferte(false);
    setModeEnvoi(!!envoiDemande);
    setChargement(true);
    axios.get(`${API}/${encodeURIComponent(subId)}/apercu`)
      .then((r) => { if (vivant) setApercu(r.data); })
      .catch((e) => { if (vivant) setErreur(detailErreur(e, "L'aperçu n'a pas pu être chargé.").message); })
      .finally(() => { if (vivant) setChargement(false); });
    return () => { vivant = false; };
  }, [ouvert, subId, envoiDemande]);

  const etat = apercu?.envoi;
  const incertain = !!etat?.confirmation_incertain || repriseOfferte;
  const verification = !!apercu?.verification_requise;
  const pret = confirme && !envoi && (!verification || String(montantSaisi).trim() !== '');

  const envoyer = async () => {
    if (!pret || !apercu?.empreinte) return;
    setEnvoi(true); setErreur('');
    try {
      const corps = { empreinte: apercu.empreinte, confirmation: true, reprise_incertain: incertain };
      if (verification) corps.montant_confirme = Number(String(montantSaisi).replace(',', '.'));
      const r = await axios.post(`${API}/${encodeURIComponent(subId)}/envoyer`, corps);
      setResultat(r.data);
      if (r.data?.envoye) onEnvoye?.();
    } catch (e) {
      const d = detailErreur(e, "L'envoi a échoué : aucun message n'est parti.");
      setErreur(d.message);
      if (d.reprise_possible) setRepriseOfferte(true);
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
              <dt className="text-white/50">Échéance</dt>
              <dd className="text-white" data-testid="v648-echeance">{dateCH(apercu.echeance)}</dd>
              <dt className="text-white/50">Objet</dt>
              <dd className="text-white" data-testid="v648-sujet">{apercu.sujet}</dd>
            </dl>
            <div className="rounded-md px-3 py-3 text-white/90 whitespace-pre-wrap text-sm" data-testid="v648-texte" style={STYLE_CARTE}>{apercu.texte}</div>

            {apercu.avertissement && (
              <p className="text-xs text-white font-semibold" data-testid="v648-avertissement">{apercu.avertissement}</p>
            )}

            {etat && !etat.peut_envoyer && (
              <p className="text-sm text-white font-semibold" data-testid="v648-envoi-bloque">
                {etat.type === 'deja_envoye' && `Déjà envoyé pour cette échéance. Relance possible le ${dateCH(etat.prochaine_le)}.`}
                {etat.type === 'incertain_attente' && `Le dernier envoi n'a pas pu être confirmé. Nouvel essai possible${etat.prochaine_le ? ` le ${dateCH(etat.prochaine_le)}` : ' après le délai'}.`}
                {etat.type === 'en_cours' && 'Un envoi est déjà en cours.'}
              </p>
            )}

            {etat?.peut_envoyer && !modeEnvoi && (
              <button type="button" onClick={() => setModeEnvoi(true)} data-testid="v648-continuer"
                className="w-full py-2 rounded-md text-sm font-semibold" style={STYLE_BORD}>
                Continuer vers l'envoi
              </button>
            )}

            {etat?.peut_envoyer && modeEnvoi && (
              <>
                {incertain && (
                  <p className="text-xs text-white" data-testid="v648-incertain">
                    {etat.action === 'nouveau_apres_incertain'
                      ? "Le dernier envoi n'a pas pu être confirmé : ce client l'a peut-être reçu. Le délai de relance est passé, un nouveau message est possible."
                      : "Le dernier envoi n'a pas pu être confirmé. Réessayer ne crée pas de doublon pendant 23 heures."}
                  </p>
                )}
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
                  {envoi ? 'Envoi…' : (incertain ? 'Réessayer' : `Envoyer : ${etat.etape}`)}
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

function ReglagesRappels({ enregistrer, reglages, erreur, enregistre }) {
  const [simulation, setSimulation] = useState(null);
  const [erreurSim, setErreurSim] = useState('');
  const [delaiSaisi, setDelaiSaisi] = useState(String(reglages.delai_relance_jours ?? 7));

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
        ['AUTOMATIQUE', 'Automatique', 'Prévu pour plus tard : rien ne part tout seul pour le moment.']].map(([val, nom, aide]) => (
        <label key={val} className="flex items-start gap-2 cursor-pointer">
          <input type="radio" name="v648-mode" className="mt-1" checked={reglages.mode === val}
            onChange={() => { setSimulation(null); enregistrer({ mode: val }); }} data-testid={`v648-mode-${val}`} />
          <span><span className="font-semibold">{nom}</span><br /><span className="text-xs text-white/60">{aide}</span></span>
        </label>
      ))}

      <label className="block text-xs text-white/80">
        Délai avant une nouvelle relance manuelle (jours)
        <input type="number" min="1" max="60" value={delaiSaisi} onChange={(e) => setDelaiSaisi(e.target.value)} onBlur={validerDelai}
          className="block w-20 mt-1 px-2 py-1.5 rounded neon-input text-sm" data-testid="v648-delai-relance" />
      </label>

      {reglages.mode === 'AUTOMATIQUE' && (
        <div className="rounded-md p-3 space-y-2" style={STYLE_CARTE}>
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
  if (etat.confirmation_incertain) return 'Vérifier le rappel';
  return etat.etape === 'Rappel' ? 'Envoyer le rappel' : 'Envoyer la relance';
}

function LigneRappel({ ligne, onOuvrir }) {
  const etat = ligne.envoi;
  return (
    <li data-testid={`v648-ligne-${ligne.code}`} className="text-xs rounded-md px-3 py-2" style={STYLE_CARTE}>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <span className="text-white font-semibold">{ligne.nom || ligne.code}</span>
        {ligne.paiement_suivant && <span className="text-white/70">Paiement {ligne.paiement_suivant}</span>}
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
          {etat && !etat.peut_envoyer && (
            <span className="text-white/70" data-testid={`v648-attente-${ligne.code}`}>
              {etat.prochaine_le ? `Prochain envoi possible le ${dateCH(etat.prochaine_le)}` : 'Envoi indisponible pour le moment'}
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
      await axios.put(`${API}/reglages`, { mode: fusion.mode, delais: fusion.delais, delai_relance_jours: fusion.delai_relance_jours });
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

      {reglages && (
        <ReglagesRappels reglages={reglages} enregistrer={enregistrer} erreur={erreurReglages} enregistre={enregistre} />
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
