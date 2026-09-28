/**
 * InvitationPartageCard — V551 (Parrainage V2)
 * Carte coach « Invitation & partage » : l'image et le message par défaut que
 * les membres envoient quand ils invitent un ami (aperçu WhatsApp).
 *
 * Routes : GET/PUT /api/referral/share-settings, POST …/share-settings/image.
 * L'IDENTITÉ EST CELLE DU JETON : le corps n'envoie JAMAIS d'e-mail ni de
 * coach_id. Le serveur décide à qui appartiennent les réglages.
 */
import { useState, useEffect, useCallback, useRef } from "react";
import axios from "axios";
import SvgIcon from "../SvgIcon";

const API_DEFAUT = `${process.env.REACT_APP_BACKEND_URL || ''}/api`;

const PRIMAIRE = "var(--primary-color, #D91CD2)";
const FOND_PRIMAIRE = "rgba(var(--primary-rgb, 217, 28, 210), 0.15)";
const BORDURE = "1px solid rgba(255,255,255,0.08)";

export const MAX_OCTETS = 3 * 1024 * 1024;
export const MAX_MESSAGE = 280;
const TYPES_OK = ["image/jpeg", "image/png", "image/webp"];

/** Contrôle client AVANT envoi. Renvoie un message d'erreur ou null.
 *  Le serveur revérifie tout (type, signature binaire, taille). */
export function verifierFichier(f) {
  if (!f) return "Aucun fichier choisi.";
  if (!TYPES_OK.includes(f.type)) return "Format refusé : choisissez une image JPEG, PNG ou WebP.";
  if (f.size > MAX_OCTETS) return "Image trop lourde : 3 Mo maximum.";
  return null;
}

function messageErreur(e) {
  const st = e && e.response && e.response.status;
  if (st === 401 || st === 403) return "Réservé au coach connecté. Reconnectez-vous pour modifier ces réglages.";
  if (st === 413) return "Image trop lourde : 3 Mo maximum.";
  const detail = e && e.response && e.response.data && e.response.data.detail;
  if (typeof detail === "string" && detail) return detail;
  return "Impossible de joindre le serveur. Réessayez dans un instant.";
}

const bouton = (actif = true) => ({
  display: "inline-flex", alignItems: "center", gap: 6,
  padding: "8px 12px", borderRadius: 10, fontSize: 13, fontWeight: 600,
  border: `1px solid ${PRIMAIRE}`, background: FOND_PRIMAIRE, color: "#fff",
  cursor: actif ? "pointer" : "not-allowed", opacity: actif ? 1 : 0.5,
});
const boutonDiscret = (actif = true) => ({
  ...bouton(actif), border: BORDURE, background: "transparent",
  color: "rgba(255,255,255,0.75)", fontWeight: 500,
});

export default function InvitationPartageCard({ API = API_DEFAUT }) {
  const url = `${API}/referral/share-settings`;
  const [reglages, setReglages] = useState(null);
  const [chargement, setChargement] = useState(true);
  const [erreur, setErreur] = useState("");
  const [succes, setSucces] = useState("");
  const [message, setMessage] = useState("");
  const [enCours, setEnCours] = useState(false);
  const inputRef = useRef(null);

  const appliquer = useCallback((d) => {
    setReglages(d);
    setMessage((d && d.default_message) || "");
  }, []);

  useEffect(() => {
    let vivant = true;
    (async () => {
      try {
        const r = await axios.get(url);
        if (vivant) appliquer(r.data);
      } catch (e) {
        if (vivant) setErreur(messageErreur(e));
      } finally {
        if (vivant) setChargement(false);
      }
    })();
    return () => { vivant = false; };
  }, [url, appliquer]);

  const envoyer = async (corps, ok) => {
    setErreur(""); setSucces(""); setEnCours(true);
    try {
      const r = await axios.put(url, corps);
      appliquer(r.data);
      setSucces(ok);
    } catch (e) {
      setErreur(messageErreur(e));
    } finally {
      setEnCours(false);
    }
  };

  const enregistrerMessage = () => {
    const m = message.trim();
    if (m.length > MAX_MESSAGE) { setErreur(`Message trop long : ${MAX_MESSAGE} caractères maximum.`); return; }
    envoyer({ default_message: m || null }, "Message enregistré.");
  };

  const choisirImage = async (ev) => {
    const f = ev.target.files && ev.target.files[0];
    if (ev.target) { try { ev.target.value = ""; } catch (_) { /* jsdom */ } }
    setErreur(""); setSucces("");
    const refus = verifierFichier(f);
    if (refus) { setErreur(refus); return; }
    const fd = new FormData();
    fd.append("file", f);
    setEnCours(true);
    try {
      const r = await axios.post(`${url}/image`, fd);
      appliquer(r.data);
      setSucces("Image remplacée.");
    } catch (e) {
      setErreur(messageErreur(e));
    } finally {
      setEnCours(false);
    }
  };

  const eff = (reglages && reglages.effective) || {};
  const defauts = (reglages && reglages.defaults) || {};
  const apercuMessage = message.trim() || eff.message || defauts.message || "";

  return (
    <div data-testid="pv2-carte" style={{
      border: BORDURE, borderRadius: 14, padding: 16,
      background: "rgba(255,255,255,0.03)", color: "#fff",
    }}>
      <h3 style={{ margin: 0, fontSize: 17, fontWeight: 700, display: "flex", alignItems: "center", gap: 8 }}>
        <span style={{ color: PRIMAIRE, display: "inline-flex" }}><SvgIcon name="users" size={18} /></span>
        Invitation & partage
      </h3>
      <p style={{ margin: "6px 0 14px", fontSize: 13, color: "rgba(255,255,255,0.6)" }}>
        L'image et le message que vos membres envoient quand ils invitent un ami.
      </p>

      {chargement && (
        <div data-testid="pv2-chargement" style={{ fontSize: 13, color: "rgba(255,255,255,0.7)", display: "flex", alignItems: "center", gap: 6 }}>
          <SvgIcon name="loader" size={14} className="animate-spin" /> Chargement…
        </div>
      )}

      {erreur && (
        <div data-testid="pv2-erreur" role="alert" style={{
          margin: "8px 0", padding: "8px 10px", borderRadius: 10, fontSize: 13,
          background: "rgba(239,68,68,0.12)", border: "1px solid rgba(239,68,68,0.4)",
          display: "flex", alignItems: "center", gap: 6,
        }}>
          <SvgIcon name="warning" size={14} /> {erreur}
        </div>
      )}
      {succes && (
        <div data-testid="pv2-succes" role="status" style={{
          margin: "8px 0", padding: "8px 10px", borderRadius: 10, fontSize: 13,
          background: "rgba(34,197,94,0.12)", border: "1px solid rgba(34,197,94,0.4)",
          display: "flex", alignItems: "center", gap: 6,
        }}>
          <SvgIcon name="check" size={14} /> {succes}
        </div>
      )}

      {!chargement && reglages && (
        <div style={{ display: "grid", gap: 18 }}>
          {/* Image de partage */}
          <section>
            <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 6 }}>Image de partage</div>
            <div style={{ fontSize: 12, color: "rgba(255,255,255,0.6)", marginBottom: 8 }}>
              Image affichée dans l'aperçu WhatsApp. Format conseillé : 1200 × 630 px, 3 Mo maximum.
            </div>
            {eff.image_url ? (
              <img data-testid="pv2-image" src={eff.image_url} alt="Image de partage"
                style={{ width: "100%", maxWidth: 360, aspectRatio: "1200 / 630", objectFit: "cover", borderRadius: 10, border: BORDURE, display: "block" }} />
            ) : (
              <div style={{ width: "100%", maxWidth: 360, aspectRatio: "1200 / 630", borderRadius: 10, border: BORDURE, display: "flex", alignItems: "center", justifyContent: "center", color: "rgba(255,255,255,0.4)" }}>
                <SvgIcon name="image" size={28} />
              </div>
            )}
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 10 }}>
              <input ref={inputRef} data-testid="pv2-image-input" type="file"
                accept="image/jpeg,image/png,image/webp" onChange={choisirImage}
                style={{ display: "none" }} />
              <button type="button" data-testid="pv2-image-remplacer" disabled={enCours}
                onClick={() => inputRef.current && inputRef.current.click()} style={bouton(!enCours)}>
                <SvgIcon name="upload" size={14} /> Remplacer
              </button>
              <button type="button" data-testid="pv2-image-defaut"
                disabled={enCours || !reglages.share_image_url}
                onClick={() => envoyer({ share_image_url: null }, "Image par défaut rétablie.")}
                style={boutonDiscret(!enCours && !!reglages.share_image_url)}>
                <SvgIcon name="undo" size={14} /> Revenir à l'image par défaut
              </button>
            </div>
          </section>

          {/* Message par défaut */}
          <section>
            <label htmlFor="pv2-message" style={{ fontSize: 14, fontWeight: 600, display: "block", marginBottom: 6 }}>
              Message par défaut
            </label>
            <textarea id="pv2-message" data-testid="pv2-message" value={message}
              maxLength={MAX_MESSAGE} rows={3} placeholder={defauts.message || ""}
              onChange={(e) => { setMessage(e.target.value); setSucces(""); }}
              style={{
                width: "100%", boxSizing: "border-box", padding: 10, borderRadius: 10,
                border: BORDURE, background: "rgba(0,0,0,0.3)", color: "#fff", fontSize: 14, resize: "vertical",
              }} />
            <div style={{ fontSize: 12, color: "rgba(255,255,255,0.5)", textAlign: "right" }}>
              {message.length} / {MAX_MESSAGE}
            </div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 6 }}>
              <button type="button" data-testid="pv2-enregistrer" disabled={enCours}
                onClick={enregistrerMessage} style={bouton(!enCours)}>
                <SvgIcon name="save" size={14} /> Enregistrer
              </button>
              <button type="button" data-testid="pv2-message-defaut" disabled={enCours}
                onClick={() => envoyer({ default_message: null }, "Message par défaut rétabli.")}
                style={boutonDiscret(!enCours)}>
                <SvgIcon name="undo" size={14} /> Revenir au message par défaut
              </button>
            </div>
          </section>

          {/* Aperçu indicatif de la carte WhatsApp */}
          <section>
            <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 6 }}>Aperçu (indicatif)</div>
            <div data-testid="pv2-apercu" style={{
              maxWidth: 320, borderRadius: 10, overflow: "hidden",
              background: "rgba(255,255,255,0.06)", border: BORDURE,
            }}>
              {eff.image_url && (
                <img src={eff.image_url} alt="" style={{ width: "100%", aspectRatio: "1200 / 630", objectFit: "cover", display: "block" }} />
              )}
              <div style={{ padding: "8px 10px" }}>
                <div style={{ fontSize: 13, fontWeight: 700 }}>&lt;Prénom&gt; t'invite à Afroboost</div>
                <div style={{ fontSize: 12, color: "rgba(255,255,255,0.7)", marginTop: 2 }}>{apercuMessage}</div>
                <div style={{ fontSize: 11, color: "rgba(255,255,255,0.4)", marginTop: 4 }}>afroboost.com</div>
              </div>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
