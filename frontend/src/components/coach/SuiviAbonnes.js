/**
 * SuiviAbonnes — V334 étape 3
 * « Suivi des abonnés » du dashboard coach : la liste de SES abonnés, avec pour
 * chacun son objectif, ses chiffres de pratique et sa dernière mesure.
 *
 * L'isolation est faite par le SERVEUR (`GET /api/progress/coach/subscribers`
 * filtre sur le coach authentifié) — cet écran ne fait qu'afficher ce qu'il reçoit.
 * Il ne demande jamais « les abonnés de X » : un coach ne peut pas se désigner
 * lui-même une autre liste.
 *
 * Les abonnés les moins réguliers arrivent en premier : ce sont eux à relancer.
 */
import { useState, useEffect, useCallback } from "react";
import axios from "axios";

const API = `${process.env.REACT_APP_BACKEND_URL || ''}/api`;

const PRIMAIRE = "var(--primary-color, #D91CD2)";
const BORDURE = "1px solid rgba(255,255,255,0.08)";

const champ = {
  width: "100%", padding: "8px 10px", borderRadius: 8,
  background: "#0a0a1a", border: BORDURE, color: "#fff",
  fontSize: 13, boxSizing: "border-box", outline: "none",
};

const dateCourte = (iso) => {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleDateString("fr-FR", { day: "2-digit", month: "short" });
  } catch (e) { return "—"; }
};

export default function SuiviAbonnes() {
  const [liste, setListe] = useState(null);   // null = chargement
  const [erreur, setErreur] = useState("");
  const [ouvert, setOuvert] = useState(null); // code de l'abonné déplié
  const [poids, setPoids] = useState("");
  const [note, setNote] = useState("");
  const [envoi, setEnvoi] = useState(false);
  const [retour, setRetour] = useState(null);

  const charger = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/progress/coach/subscribers`);
      setListe(r.data.subscribers || []);
      setErreur("");
    } catch (e) {
      setListe([]);
      setErreur(e?.response?.status === 403
        ? "Accès refusé — reconnectez-vous."
        : "Impossible de charger le suivi pour le moment.");
    }
  }, []);

  useEffect(() => { charger(); }, [charger]);

  const enregistrer = async (code) => {
    if (envoi) return;
    const corps = { subscriber_code: code };
    if (poids.trim()) corps.weight_kg = poids.trim();
    if (note.trim()) corps.note = note.trim();
    if (!corps.weight_kg && !corps.note) {
      setRetour({ code, type: "ko", texte: "Saisissez au moins une valeur." });
      return;
    }
    setEnvoi(true); setRetour(null);
    try {
      await axios.post(`${API}/progress`, corps);
      setPoids(""); setNote("");
      setRetour({ code, type: "ok", texte: "Mesure enregistrée." });
      await charger();
    } catch (err) {
      setRetour({ code, type: "ko",
                  texte: err?.response?.data?.detail || "Enregistrement impossible." });
    } finally { setEnvoi(false); }
  };

  if (liste === null) {
    return <p style={{ color: "rgba(255,255,255,0.4)", fontSize: 13 }}>Chargement du suivi…</p>;
  }
  if (erreur) {
    return <p style={{ color: "#fca5a5", fontSize: 13 }}>{erreur}</p>;
  }
  if (liste.length === 0) {
    return (
      <p style={{ color: "rgba(255,255,255,0.4)", fontSize: 13 }}>
        Aucun abonné actif pour le moment.
      </p>
    );
  }

  return (
    <div data-testid="suivi-abonnes">
      <p style={{ color: "rgba(255,255,255,0.4)", fontSize: 11.5, margin: "0 0 12px" }}>
        {liste.length} abonné{liste.length > 1 ? "s" : ""} — les moins réguliers en premier.
      </p>

      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {liste.map((s) => {
          const deplie = ouvert === s.code;
          return (
            <div key={s.code} style={{
              background: "rgba(255,255,255,0.03)", border: BORDURE, borderRadius: 12, padding: 12,
            }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
                <div style={{ minWidth: 0, flex: 1 }}>
                  <div style={{ color: "#fff", fontSize: 13.5, fontWeight: 600,
                                overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {s.name || "Abonné"}
                  </div>
                  {s.objectifs ? (
                    <div style={{ color: PRIMAIRE, fontSize: 11, marginTop: 2,
                                  overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {s.objectifs}
                    </div>
                  ) : null}
                </div>
                <button
                  type="button"
                  onClick={() => { setOuvert(deplie ? null : s.code); setPoids(""); setNote(""); setRetour(null); }}
                  style={{
                    flexShrink: 0, padding: "6px 12px", borderRadius: 999,
                    border: `1px solid rgba(var(--primary-rgb, 217, 28, 210), 0.45)`,
                    background: "none", color: PRIMAIRE, fontSize: 11.5, fontWeight: 600, cursor: "pointer",
                  }}
                  data-testid={`suivi-toggle-${s.code}`}
                >
                  {deplie ? "Fermer" : "+ Mesure"}
                </button>
              </div>

              {/* Chiffres — compacts, lisibles d'un coup d'œil */}
              <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginTop: 8,
                            color: "rgba(255,255,255,0.5)", fontSize: 11 }}>
                <span><b style={{ color: "#fff" }}>{s.seances_suivies}</b> séances</span>
                <span><b style={{ color: "#fff" }}>{s.seances_a_venir}</b> à venir</span>
                <span>régularité <b style={{ color: "#fff" }}>
                  {s.regularite_par_semaine === null ? "—" : `${s.regularite_par_semaine}/sem`}
                </b></span>
                <span>dernière séance <b style={{ color: "#fff" }}>{dateCourte(s.derniere_seance)}</b></span>
                {s.derniere_mesure ? (
                  <span>dernier poids <b style={{ color: "#fff" }}>
                    {s.derniere_mesure.weight_kg ?? "—"} kg
                  </b> ({dateCourte(s.derniere_mesure.entry_date)})</span>
                ) : (
                  <span style={{ color: "rgba(255,255,255,0.3)" }}>aucune mesure</span>
                )}
              </div>

              {/* Saisie d'une mesure POUR cet abonné */}
              {deplie && (
                <div style={{ marginTop: 10, display: "flex", flexDirection: "column", gap: 7 }}>
                  <input type="number" step="0.1" inputMode="decimal" value={poids}
                         onChange={(e) => setPoids(e.target.value)}
                         placeholder="Poids (kg)" style={champ}
                         data-testid={`suivi-poids-${s.code}`} />
                  <input type="text" value={note}
                         onChange={(e) => setNote(e.target.value.slice(0, 500))}
                         placeholder="Note (facultatif)" style={champ}
                         data-testid={`suivi-note-${s.code}`} />
                  <button type="button" onClick={() => enregistrer(s.code)} disabled={envoi}
                          style={{
                            padding: "8px", borderRadius: 999, border: "none", background: PRIMAIRE,
                            color: "#fff", fontWeight: 700, fontSize: 12.5,
                            cursor: envoi ? "wait" : "pointer", opacity: envoi ? 0.6 : 1,
                          }}
                          data-testid={`suivi-submit-${s.code}`}>
                    {envoi ? "Enregistrement…" : "Enregistrer la mesure"}
                  </button>
                </div>
              )}

              {retour && retour.code === s.code ? (
                <p style={{ margin: "7px 0 0", fontSize: 11.5,
                            color: retour.type === "ok" ? "#4ade80" : "#fca5a5" }}>
                  {retour.texte}
                </p>
              ) : null}
            </div>
          );
        })}
      </div>
    </div>
  );
}
