/**
 * V637 — PANNEAU DÉTAIL PARTENAIRE (vue coach).
 *
 * Panneau modal qui s'ouvre sur le bouton « Détails » d'un code promo.
 * Regroupe, pour ce code :
 *   - Liste des inscriptions (Stripe + espèces)
 *   - Totaux 60/40 en temps réel
 *   - Paramétrage du pourcentage partenaire + nom
 *   - Génération / révocation du lien partenaire (accès sans compte)
 *   - Déclaration de paiement en espèces
 *   - Export CSV
 *
 * SÉCURITÉ : toutes les routes nécessitent un JWT coach (`/api/partner/*`).
 * ISOLATION : un coach ne voit que ses propres codes.
 * DONNÉES : aucune écriture sur `discount_codes`, `payment_transactions`,
 *   `reservations` — seules les 3 nouvelles collections V637 sont modifiées.
 */
import React, { useEffect, useState, useCallback } from 'react';
import SvgIcon from '../SvgIcon';
import axios from 'axios';

// ─── Helpers ──────────────────────────────────────────────────────────────────

function chf(val) {
  const n = typeof val === 'number' ? val : parseFloat(val) || 0;
  return n.toFixed(2) + ' CHF';
}

function dateAffichee(iso) {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    return d.toLocaleDateString('fr-CH', { day: 'numeric', month: 'short', year: 'numeric' });
  } catch (e) { return iso; }
}

function statutLabel(s) {
  if (s === 'paye') return { txt: 'Payé', cls: 'text-green-400' };
  if (s === 'rembourse') return { txt: 'Remboursé', cls: 'text-red-400' };
  if (s === 'paiement_sans_reservation') return { txt: 'Paiement (sans rés.)', cls: 'text-yellow-400' };
  if (s === 'especes') return { txt: 'Espèces', cls: 'text-purple-400' };
  return { txt: s || '—', cls: 'text-white/40' };
}

// ─── Composant principal ───────────────────────────────────────────────────────

export default function PartnerCodeDetails({ code, onFermer }) {
  const [etat, setEtat] = useState('chargement'); // chargement | ok | erreur
  const [data, setData] = useState(null);

  // Config partenaire
  const [nomEdit, setNomEdit] = useState('');
  const [pctEdit, setPctEdit] = useState(40);
  const [sauvegardeEnCours, setSauvegardeEnCours] = useState(false);
  const [msgConfig, setMsgConfig] = useState('');

  // Espèces
  const [especesPrenom, setEspecesPrenom] = useState('');
  const [especesNom, setEspecesNom] = useState('');
  const [especesDate, setEspecesDate] = useState('');
  const [especesMontant, setEspecesMontant] = useState('');
  const [especesEnCours, setEspecesEnCours] = useState(false);
  const [msgEspeces, setMsgEspeces] = useState('');

  // Lien partenaire
  const [lienEnCours, setLienEnCours] = useState(false);
  const [msgLien, setMsgLien] = useState('');
  const [lienCopie, setLienCopie] = useState(false);

  const charger = useCallback(() => {
    if (!code) return;
    setEtat('chargement');
    axios.get(`/api/partner/codes/${encodeURIComponent(code)}/details`)
      .then((r) => {
        setData(r.data);
        setNomEdit(r.data.partner_name || '');
        setPctEdit(r.data.pct_partenaire || 40);
        setEtat('ok');
      })
      .catch(() => setEtat('erreur'));
  }, [code]);

  useEffect(() => { charger(); }, [charger]);

  // ── Sauvegarde config ──────────────────────────────────────────────────────
  const sauvegarderConfig = async () => {
    if (sauvegardeEnCours) return;
    setSauvegardeEnCours(true);
    setMsgConfig('');
    try {
      await axios.put(`/api/partner/codes/${encodeURIComponent(code)}/config`, {
        partner_name: nomEdit,
        partner_pct: parseInt(pctEdit, 10),
      });
      setMsgConfig('✓ Sauvegardé');
      charger();
    } catch {
      setMsgConfig('Erreur — réessaie');
    } finally {
      setSauvegardeEnCours(false);
      setTimeout(() => setMsgConfig(''), 3000);
    }
  };

  // ── Lien partenaire ────────────────────────────────────────────────────────
  const genererLien = async () => {
    if (lienEnCours) return;
    setLienEnCours(true);
    setMsgLien('');
    try {
      await axios.post(`/api/partner/codes/${encodeURIComponent(code)}/generate-token`);
      charger();
      setMsgLien('✓ Nouveau lien créé');
    } catch {
      setMsgLien('Erreur génération');
    } finally {
      setLienEnCours(false);
      setTimeout(() => setMsgLien(''), 4000);
    }
  };

  const revoquerLien = async () => {
    if (!window.confirm('Révoquer le lien partenaire ? Il ne fonctionnera plus immédiatement.')) return;
    setLienEnCours(true);
    try {
      await axios.delete(`/api/partner/codes/${encodeURIComponent(code)}/revoke-token`);
      charger();
      setMsgLien('Lien révoqué');
    } catch {
      setMsgLien('Erreur révocation');
    } finally {
      setLienEnCours(false);
      setTimeout(() => setMsgLien(''), 3000);
    }
  };

  const copierLien = () => {
    if (!data?.lien_partenaire) return;
    try {
      navigator.clipboard.writeText(data.lien_partenaire);
      setLienCopie(true);
      setTimeout(() => setLienCopie(false), 2500);
    } catch (e) {
      // fallback
      const el = document.createElement('textarea');
      el.value = data.lien_partenaire;
      document.body.appendChild(el);
      el.select();
      document.execCommand('copy');
      document.body.removeChild(el);
      setLienCopie(true);
      setTimeout(() => setLienCopie(false), 2500);
    }
  };

  // ── Espèces ────────────────────────────────────────────────────────────────
  const declarerEspeces = async (e) => {
    e.preventDefault();
    if (especesEnCours) return;
    const montant = parseFloat(especesMontant);
    if (!especesPrenom.trim() || !especesNom.trim() || !especesDate || isNaN(montant) || montant <= 0) {
      setMsgEspeces('Remplis tous les champs (montant > 0)');
      return;
    }
    setEspecesEnCours(true);
    setMsgEspeces('');
    const clef = `${code}:${Date.now()}-${Math.random().toString(36).slice(2)}`;
    try {
      const r = await axios.post(`/api/partner/codes/${encodeURIComponent(code)}/cash`, {
        prenom: especesPrenom.trim(),
        nom: especesNom.trim(),
        date_seance: especesDate,
        montant_chf: montant,
        idempotence_key: clef,
      });
      if (r.data.doublon) {
        setMsgEspeces('⚠ Paiement déjà enregistré (doublon détecté)');
      } else {
        setMsgEspeces('✓ Paiement en espèces enregistré');
        setEspecesPrenom('');
        setEspecesNom('');
        setEspecesDate('');
        setEspecesMontant('');
        charger();
      }
    } catch {
      setMsgEspeces('Erreur — réessaie');
    } finally {
      setEspecesEnCours(false);
      setTimeout(() => setMsgEspeces(''), 5000);
    }
  };

  // ── Export CSV ─────────────────────────────────────────────────────────────
  const exporterCsv = () => {
    window.location.href = `/api/partner/codes/${encodeURIComponent(code)}/export.csv`;
  };

  // ─── Rendu ─────────────────────────────────────────────────────────────────

  return (
    <div
      className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-0 sm:p-4"
      style={{ background: 'rgba(0,0,0,0.8)', backdropFilter: 'blur(6px)' }}
      onClick={(e) => { if (e.target === e.currentTarget) onFermer(); }}
      role="dialog"
      aria-modal="true"
      aria-label={`Détails partenaire — ${code}`}
    >
      <div
        className="w-full sm:max-w-2xl bg-[#0d0d0d] border border-white/10 rounded-t-2xl sm:rounded-2xl overflow-hidden flex flex-col"
        style={{ maxHeight: '92vh' }}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-white/10 flex-shrink-0">
          <div>
            <h2 className="text-white font-bold text-lg leading-tight">
              Suivi partenaire — <span style={{ color: 'var(--primary-color, #D91CD2)' }}>{code}</span>
            </h2>
            <p className="text-white/40 text-xs mt-0.5">
              {data?.partner_name ? `${data.partner_name} · ` : ''}{data?.pct_partenaire || 40} % commission
            </p>
          </div>
          <button
            onClick={onFermer}
            className="p-2 rounded-lg hover:bg-white/10 text-white/60"
            aria-label="Fermer"
          >
            <SvgIcon name="x" size={20} />
          </button>
        </div>

        {/* Corps défilant */}
        <div className="overflow-y-auto flex-1 px-5 py-4 space-y-6">

          {etat === 'chargement' && (
            <div className="flex items-center justify-center py-16 text-white/30">
              <SvgIcon name="loader" size={28} />
            </div>
          )}

          {etat === 'erreur' && (
            <div className="text-center py-12 text-red-400 text-sm">
              Impossible de charger les données. Vérifie ta connexion.
            </div>
          )}

          {etat === 'ok' && data && (() => {
            const totaux = data.totaux || {};
            const lignes = Array.isArray(data.lignes) ? data.lignes : [];

            return (
              <>
                {/* Totaux */}
                <section>
                  <h3 className="text-xs uppercase tracking-wider text-white/40 mb-3">Récapitulatif</h3>
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                    {[
                      { icone: 'users', label: 'Inscriptions', val: totaux.nb_inscriptions || 0, fmt: (v) => v },
                      { icone: 'dollarSign', label: 'Net encaissé', val: totaux.total_net_chf, fmt: chf, accent: true },
                      { icone: 'gift', label: `Part ${data.pct_partenaire || 40} %`, val: totaux.part_partenaire_chf, fmt: chf, accent: true },
                      { icone: 'barChart', label: 'Part Afroboost', val: totaux.part_afroboost_chf, fmt: chf },
                    ].map(({ icone, label, val, fmt, accent }) => (
                      <div key={label} className="rounded-xl p-3 bg-white/[0.03] border border-white/[0.06]">
                        <div className="flex items-center gap-1.5 text-xs text-white/40 mb-1.5">
                          <SvgIcon name={icone} size={13} />
                          {label}
                        </div>
                        <div className={`font-bold text-lg ${accent ? '' : 'text-white/80'}`}
                          style={accent ? { color: 'var(--primary-color, #D91CD2)' } : {}}>
                          {fmt(val || 0)}
                        </div>
                      </div>
                    ))}
                  </div>
                </section>

                {/* Liste des inscriptions */}
                <section>
                  <div className="flex items-center justify-between mb-3">
                    <h3 className="text-xs uppercase tracking-wider text-white/40">
                      Inscriptions ({lignes.length})
                    </h3>
                    <button
                      onClick={exporterCsv}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs bg-white/[0.06] hover:bg-white/10 text-white/70"
                    >
                      <SvgIcon name="download" size={13} /> Export CSV
                    </button>
                  </div>
                  {lignes.length === 0 ? (
                    <div className="text-center py-8 text-white/25 text-sm">
                      Aucune inscription liée à ce code.
                    </div>
                  ) : (
                    <div className="space-y-2">
                      {lignes.map((l, i) => {
                        const st = statutLabel(l.statut);
                        return (
                          <div
                            key={l.session_id || `li-${i}`}
                            className={`flex items-start justify-between gap-3 rounded-xl p-3 bg-white/[0.03] border border-white/[0.05] ${l.statut === 'rembourse' ? 'opacity-40' : ''}`}
                          >
                            <div className="min-w-0">
                              <div className="font-semibold text-sm text-white/90 truncate">{l.nom}</div>
                              <div className="text-xs text-white/35 mt-0.5">
                                {dateAffichee(l.date_paiement || l.date_seance)}
                                {l.date_seance && l.date_paiement && l.date_paiement !== l.date_seance && (
                                  <span> · séance {dateAffichee(l.date_seance)}</span>
                                )}
                              </div>
                              {l.reduction_chf > 0 && (
                                <div className="text-xs text-white/30 mt-0.5">
                                  Réduction : {chf(l.reduction_chf)}
                                </div>
                              )}
                            </div>
                            <div className="flex flex-col items-end gap-1 flex-shrink-0">
                              <div className="font-bold text-sm text-white/90">{chf(l.montant_chf)}</div>
                              <div className={`text-xs font-semibold ${st.cls}`}>{st.txt}</div>
                              {l.moyen === 'especes' && (
                                <div className="text-[10px] text-purple-400/70">espèces</div>
                              )}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </section>

                {/* Config partenaire */}
                <section>
                  <h3 className="text-xs uppercase tracking-wider text-white/40 mb-3">Configuration partenaire</h3>
                  <div className="rounded-xl p-4 bg-white/[0.03] border border-white/[0.06] space-y-3">
                    <div>
                      <label className="block text-xs text-white/50 mb-1">Nom du partenaire</label>
                      <input
                        type="text"
                        value={nomEdit}
                        onChange={(e) => setNomEdit(e.target.value)}
                        className="w-full bg-black/60 border border-white/10 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-white/30"
                        placeholder="ex. Société Hétaïra"
                        maxLength={120}
                      />
                    </div>
                    <div>
                      <label className="block text-xs text-white/50 mb-1">
                        Commission partenaire (%)
                      </label>
                      <input
                        type="number"
                        min={0}
                        max={100}
                        value={pctEdit}
                        onChange={(e) => setPctEdit(e.target.value)}
                        className="w-full bg-black/60 border border-white/10 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-white/30"
                      />
                      <p className="text-xs text-white/30 mt-1">
                        Afroboost reçoit {100 - (parseInt(pctEdit, 10) || 0)} %
                      </p>
                    </div>
                    <div className="flex items-center gap-3">
                      <button
                        onClick={sauvegarderConfig}
                        disabled={sauvegardeEnCours}
                        className="px-4 py-2 rounded-lg text-sm font-semibold"
                        style={{ background: 'var(--primary-color, #D91CD2)', color: '#fff' }}
                      >
                        {sauvegardeEnCours ? (
                          <span className="inline-flex items-center gap-2"><SvgIcon name="loader" size={14} /> Sauvegarde…</span>
                        ) : (
                          <span className="inline-flex items-center gap-2"><SvgIcon name="check" size={14} /> Sauvegarder</span>
                        )}
                      </button>
                      {msgConfig && <span className="text-sm text-white/60">{msgConfig}</span>}
                    </div>
                  </div>
                </section>

                {/* Lien partenaire */}
                <section>
                  <h3 className="text-xs uppercase tracking-wider text-white/40 mb-3">Lien d'accès partenaire</h3>
                  <div className="rounded-xl p-4 bg-white/[0.03] border border-white/[0.06] space-y-3">
                    <p className="text-xs text-white/45 leading-relaxed">
                      Le partenaire accède au suivi de ses inscriptions via un lien privé, sans créer de compte.
                      Seuls les noms masqués (prénom + initiale) sont visibles.
                    </p>
                    {data.lien_actif && data.lien_partenaire ? (
                      <>
                        <div className="flex items-center gap-2">
                          <div className="flex-1 px-3 py-2 bg-black/60 border border-white/10 rounded-lg text-xs text-white/60 overflow-hidden truncate">
                            {data.lien_partenaire}
                          </div>
                          <button
                            onClick={copierLien}
                            className={`px-3 py-2 rounded-lg text-xs font-semibold ${lienCopie ? 'bg-green-500/20 text-green-400' : 'bg-white/[0.07] text-white/70 hover:bg-white/10'}`}
                          >
                            <span className="inline-flex items-center gap-1.5">
                              <SvgIcon name={lienCopie ? 'check' : 'copy'} size={13} />
                              {lienCopie ? 'Copié !' : 'Copier'}
                            </span>
                          </button>
                        </div>
                        <div className="flex gap-2">
                          <button
                            onClick={genererLien}
                            disabled={lienEnCours}
                            className="px-3 py-2 rounded-lg text-xs bg-blue-500/20 text-blue-300 hover:bg-blue-500/30"
                          >
                            <span className="inline-flex items-center gap-1.5">
                              <SvgIcon name="refresh" size={13} /> Régénérer
                            </span>
                          </button>
                          <button
                            onClick={revoquerLien}
                            disabled={lienEnCours}
                            className="px-3 py-2 rounded-lg text-xs bg-red-500/15 text-red-400 hover:bg-red-500/25"
                          >
                            <span className="inline-flex items-center gap-1.5">
                              <SvgIcon name="lock" size={13} /> Révoquer
                            </span>
                          </button>
                        </div>
                      </>
                    ) : (
                      <button
                        onClick={genererLien}
                        disabled={lienEnCours}
                        className="px-4 py-2 rounded-lg text-sm font-semibold bg-white/[0.07] hover:bg-white/10 text-white/80"
                      >
                        <span className="inline-flex items-center gap-2">
                          <SvgIcon name="link" size={14} />
                          {lienEnCours ? 'Génération…' : 'Créer le lien partenaire'}
                        </span>
                      </button>
                    )}
                    {msgLien && <p className="text-xs text-white/50">{msgLien}</p>}
                  </div>
                </section>

                {/* Déclaration espèces */}
                <section>
                  <h3 className="text-xs uppercase tracking-wider text-white/40 mb-3">Ajouter un paiement en espèces</h3>
                  <div className="rounded-xl p-4 bg-white/[0.03] border border-white/[0.06]">
                    <form onSubmit={declarerEspeces} className="space-y-3">
                      <div className="grid grid-cols-2 gap-3">
                        <div>
                          <label className="block text-xs text-white/50 mb-1">Prénom</label>
                          <input
                            type="text"
                            value={especesPrenom}
                            onChange={(e) => setEspecesPrenom(e.target.value)}
                            className="w-full bg-black/60 border border-white/10 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-white/30"
                            placeholder="Alice"
                            maxLength={80}
                          />
                        </div>
                        <div>
                          <label className="block text-xs text-white/50 mb-1">Nom</label>
                          <input
                            type="text"
                            value={especesNom}
                            onChange={(e) => setEspecesNom(e.target.value)}
                            className="w-full bg-black/60 border border-white/10 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-white/30"
                            placeholder="Martin"
                            maxLength={80}
                          />
                        </div>
                      </div>
                      <div className="grid grid-cols-2 gap-3">
                        <div>
                          <label className="block text-xs text-white/50 mb-1">Date de la séance</label>
                          <input
                            type="date"
                            value={especesDate}
                            onChange={(e) => setEspecesDate(e.target.value)}
                            className="w-full bg-black/60 border border-white/10 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-white/30"
                          />
                        </div>
                        <div>
                          <label className="block text-xs text-white/50 mb-1">Montant (CHF)</label>
                          <input
                            type="number"
                            min="0.01"
                            step="0.01"
                            value={especesMontant}
                            onChange={(e) => setEspecesMontant(e.target.value)}
                            className="w-full bg-black/60 border border-white/10 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-white/30"
                            placeholder="30.00"
                          />
                        </div>
                      </div>
                      <div className="flex items-center gap-3">
                        <button
                          type="submit"
                          disabled={especesEnCours}
                          className="px-4 py-2 rounded-lg text-sm font-semibold bg-white/[0.07] hover:bg-white/10 text-white/80"
                        >
                          <span className="inline-flex items-center gap-2">
                            <SvgIcon name="dollarSign" size={14} />
                            {especesEnCours ? 'Enregistrement…' : 'Enregistrer'}
                          </span>
                        </button>
                        {msgEspeces && <span className="text-xs text-white/55">{msgEspeces}</span>}
                      </div>
                    </form>
                  </div>
                </section>
              </>
            );
          })()}
        </div>
      </div>
    </div>
  );
}
