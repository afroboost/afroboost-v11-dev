/**
 * DetailAbonne — V338
 * Bloc PARTAGÉ affichant le détail d'un abonné : la liste datée de ses séances
 * effectuées et la note « Points à améliorer / Motivation ».
 *
 * POURQUOI UN COMPOSANT COMMUN : le même détail doit apparaître à l'identique dans
 * les trois écrans du Suivi — cockpit de l'abonné, vue coach, cockpit global. Trois
 * implémentations séparées finiraient inévitablement par diverger (une date formatée
 * autrement ici, une note oubliée là). Il y en a donc UNE seule, paramétrée.
 *
 * Les droits ne sont PAS décidés ici : le serveur refuse (403) ce qui n'est pas
 * permis, et ce composant se contente d'afficher ce qu'il reçoit.
 *
 * @param code        code de l'abonné
 * @param subscriberCode  code à envoyer comme preuve quand c'est l'abonné lui-même
 *                        qui regarde (vide côté coach/admin : leur session suffit)
 * @param peutEcrire  affiche la zone de saisie de la note (coach/admin uniquement)
 * @param seances     liste déjà chargée [{date, nom}] — évite un second appel quand
 *                    l'appelant a déjà le cockpit
 */
import { useState, useEffect, useCallback } from "react";
import axios from "axios";

const API = `${process.env.REACT_APP_BACKEND_URL || ''}/api`;
const PRIMAIRE = "var(--primary-color, #D91CD2)";
const BORDURE = "1px solid rgba(255,255,255,0.08)";

/** Format unique pour TOUTE la fonctionnalité : « 12 juil. 2026 ». */
export const formatDateSeance = (iso) => {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleDateString("fr-FR",
      { day: "2-digit", month: "short", year: "numeric" });
  } catch (e) { return "—"; }
};

/** Liste chronologique des séances effectuées — identique aux 3 niveaux. */
export function ListeSeances({ seances }) {
  const liste = seances || [];
  if (liste.length === 0) {
    return (
      <p style={{ color: "rgba(255,255,255,0.4)", fontSize: 12, margin: 0 }}>
        Aucune séance enregistrée.
      </p>
    );
  }
  return (
    <div style={{ maxHeight: 220, overflowY: "auto", display: "flex",
                  flexDirection: "column", gap: 4 }}>
      {liste.map((s, i) => (
        <div key={i} style={{
          display: "flex", justifyContent: "space-between", gap: 8,
          fontSize: 12, color: "rgba(255,255,255,0.6)",
          padding: "5px 8px", borderRadius: 7, background: "rgba(255,255,255,0.03)",
        }}>
          <span style={{ color: "#fff" }}>{formatDateSeance(s.date)}</span>
          <span style={{ overflow: "hidden", textOverflow: "ellipsis",
                         whiteSpace: "nowrap", maxWidth: "60%" }}>
            {s.nom || "Séance"}
          </span>
        </div>
      ))}
    </div>
  );
}

/**
 * Note « Points à améliorer / Motivation ».
 * `cibleType` vaut 'subscriber' (note d'un coach à son abonné) ou 'coach'
 * (note de l'administrateur à un coach) — même mécanique, même rendu.
 */
export function NoteMotivation({ cibleType, cibleId, codePreuve = "", peutEcrire = false }) {
  const [note, setNote] = useState(undefined);   // undefined = chargement
  const [texte, setTexte] = useState("");
  const [envoi, setEnvoi] = useState(false);
  const [retour, setRetour] = useState(null);

  const charger = useCallback(async () => {
    if (!cibleId) return;
    try {
      const r = await axios.get(
        `${API}/notes/${cibleType}/${encodeURIComponent(cibleId)}`,
        codePreuve ? { params: { code: codePreuve } } : undefined
      );
      setNote(r.data.note || null);
      setTexte((r.data.note && r.data.note.text) || "");
    } catch (e) {
      // Pas le droit de lire, ou aucune note : dans les deux cas on n'affiche rien
      // plutôt qu'un message d'erreur anxiogène sur un encart de motivation.
      setNote(null);
    }
  }, [cibleType, cibleId, codePreuve]);

  useEffect(() => { charger(); }, [charger]);

  const enregistrer = async () => {
    if (envoi) return;
    setEnvoi(true); setRetour(null);
    try {
      await axios.post(`${API}/notes`, {
        target_type: cibleType, target_id: cibleId, text: texte,
      });
      setRetour({ type: "ok", texte: texte.trim() ? "Message enregistré." : "Message retiré." });
      await charger();
    } catch (err) {
      setRetour({ type: "ko",
                  texte: err?.response?.data?.detail || "Enregistrement impossible." });
    } finally { setEnvoi(false); }
  };

  if (note === undefined) return null;

  const titreLecture = cibleType === "coach"
    ? "Retour de l'administrateur"
    : "Retour de votre coach";

  return (
    <div style={{ marginTop: 10 }}>
      {/* Vue du DESTINATAIRE : encart lisible, ton bienveillant. */}
      {!peutEcrire && note && note.text ? (
        <div style={{
          padding: "10px 12px", borderRadius: 10,
          background: "rgba(var(--primary-rgb, 217, 28, 210), 0.08)",
          border: "1px solid rgba(var(--primary-rgb, 217, 28, 210), 0.2)",
        }}>
          <div style={{ color: PRIMAIRE, fontSize: 11, fontWeight: 700, marginBottom: 4 }}>
            {titreLecture}
          </div>
          <div style={{ color: "rgba(255,255,255,0.78)", fontSize: 13, lineHeight: 1.5,
                        whiteSpace: "pre-wrap" }}>
            {note.text}
          </div>
        </div>
      ) : null}

      {/* Vue de l'AUTEUR : saisie. */}
      {peutEcrire ? (
        <div>
          <div style={{ color: "rgba(255,255,255,0.55)", fontSize: 11.5, marginBottom: 5 }}>
            Points à améliorer / Motivation
          </div>
          <textarea
            value={texte}
            onChange={(e) => setTexte(e.target.value.slice(0, 2000))}
            rows={3}
            placeholder="Un mot d'encouragement, un point à travailler…"
            data-testid={`note-texte-${cibleId}`}
            style={{
              width: "100%", padding: "9px 11px", borderRadius: 9, background: "#0a0a1a",
              border: BORDURE, color: "#fff", fontSize: 13, boxSizing: "border-box",
              resize: "vertical", fontFamily: "inherit", outline: "none",
            }}
          />
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 6 }}>
            <button type="button" onClick={enregistrer} disabled={envoi}
                    data-testid={`note-submit-${cibleId}`}
                    style={{
                      padding: "7px 16px", borderRadius: 999, border: "none",
                      background: PRIMAIRE, color: "#fff", fontWeight: 700, fontSize: 12,
                      cursor: envoi ? "wait" : "pointer", opacity: envoi ? 0.6 : 1,
                    }}>
              {envoi ? "Enregistrement…" : "Enregistrer"}
            </button>
            <span style={{ color: "rgba(255,255,255,0.3)", fontSize: 10.5 }}>
              {texte.length}/2000 — visible par le destinataire
            </span>
          </div>
          {retour ? (
            <p style={{ margin: "6px 0 0", fontSize: 11.5,
                        color: retour.type === "ok" ? "#4ade80" : "#fca5a5" }}>
              {retour.texte}
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

/** Bloc complet : séances datées + note. Utilisé tel quel aux 3 niveaux. */
export default function DetailAbonne({ code, seances, codePreuve = "", peutEcrire = false }) {
  return (
    <div data-testid={`detail-abonne-${code}`}>
      <div style={{ color: "rgba(255,255,255,0.55)", fontSize: 11.5, margin: "0 0 6px" }}>
        Séances effectuées
      </div>
      <ListeSeances seances={seances} />
      <NoteMotivation cibleType="subscriber" cibleId={code}
                      codePreuve={codePreuve} peutEcrire={peutEcrire} />
    </div>
  );
}
