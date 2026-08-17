/**
 * InvitationTemoignage — ESSAI-5a-2
 *
 * Proposé UNIQUEMENT à quelqu'un que le coach a classé « Participant » dans
 * Contacts. Rien n'est déduit d'une adresse, d'un code ou d'une réservation :
 * la base ne peut pas savoir qui a déjà dansé avant l'existence du site.
 *
 * FACULTATIF, sans conséquence. « Pas maintenant » range l'invitation et
 * n'affecte ni l'essai, ni la réservation, ni le prix, ni les rappels.
 *
 * Rien n'est publié : la soumission part en attente de modération, et le
 * consentement à publier est distinct du fait d'écrire.
 */
import { useState } from "react";
import axios from "axios";

const API = `${process.env.REACT_APP_BACKEND_URL || ''}/api`;
const PRIMAIRE = "var(--primary-color, #D91CD2)";
const BORDURE = "1px solid rgba(255,255,255,0.10)";

// « Pas maintenant » est une préférence d'affichage, pas un fait métier :
// elle n'a pas sa place en base. Sept jours, puis on redemande une fois.
const REPOS_JOURS = 7;
const cle = (code) => `afroboost_temoignage_repos_${code || "x"}`;

export const enRepos = (code) => {
  try {
    const t = parseInt(window.localStorage.getItem(cle(code)) || "0", 10);
    return t > Date.now();
  } catch (e) { return false; }
};

const CONSENT_TEXTE =
  "J'autorise Afroboost à publier ce témoignage sur son site, ses pages d'offres et ses supports de communication.";

export default function InvitationTemoignage({ code, prenom = "", offerId = "", onFerme }) {
  const [ouvert, setOuvert] = useState(false);
  const [texte, setTexte] = useState("");
  const [publier, setPublier] = useState(false);
  const [identite, setIdentite] = useState(false);
  const [detail, setDetail] = useState(false);
  const [envoi, setEnvoi] = useState(false);
  const [fait, setFait] = useState(false);
  const [erreur, setErreur] = useState("");
  const [range, setRange] = useState(false);

  const plusTard = () => {
    try {
      window.localStorage.setItem(cle(code), String(Date.now() + REPOS_JOURS * 864e5));
    } catch (e) { /* le refus fonctionne même sans stockage */ }
    setRange(true);
    if (onFerme) onFerme();
  };

  const envoyer = async () => {
    if (!texte.trim() || envoi) return;
    setEnvoi(true);
    setErreur("");
    try {
      await axios.post(`${API}/testimonials`, {
        code,
        text: texte.trim(),
        consent_publication: publier,
        consent_identity: identite,
        consent_text: publier ? CONSENT_TEXTE : "",
        offer_id: offerId || undefined,
        recognition: "contact_participant",
      });
      setFait(true);
    } catch (e) {
      setErreur(e?.response?.data?.detail || "Envoi impossible pour le moment.");
    } finally {
      setEnvoi(false);
    }
  };

  if (range) return null;

  const cadre = {
    background: "rgba(255,255,255,0.03)", border: BORDURE,
    borderRadius: 14, padding: 14, marginBottom: 12,
  };

  if (fait) {
    return (
      <div style={cadre} data-testid="temoignage-merci">
        <p style={{ margin: 0, color: "#fff", fontSize: 14, fontWeight: 700 }}>Merci 💛</p>
        <p style={{ margin: "6px 0 0", color: "rgba(255,255,255,0.6)", fontSize: 12, lineHeight: 1.5 }}>
          {publier
            ? "Votre expérience sera relue par le coach avant d'être publiée."
            : "Votre retour a bien été enregistré. Il restera privé."}
        </p>
      </div>
    );
  }

  if (!ouvert) {
    return (
      <div style={cadre} data-testid="temoignage-invitation">
        <p style={{ margin: 0, color: "#fff", fontSize: 14, fontWeight: 700 }}>
          Tu connais déjà Afroboost&nbsp;? 💬
        </p>
        <p style={{ margin: "6px 0 12px", color: "rgba(255,255,255,0.6)", fontSize: 12, lineHeight: 1.5 }}>
          Ton expérience peut aider quelqu'un qui hésite encore à se lancer.
        </p>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <button type="button" data-testid="temoignage-ouvrir" onClick={() => setOuvert(true)}
            style={{ padding: "9px 16px", borderRadius: 999, border: "none", cursor: "pointer",
                     background: PRIMAIRE, color: "#fff", fontSize: 13, fontWeight: 700 }}>
            Partager mon expérience
          </button>
          <button type="button" data-testid="temoignage-plus-tard" onClick={plusTard}
            style={{ padding: "9px 16px", borderRadius: 999, cursor: "pointer",
                     background: "transparent", border: BORDURE,
                     color: "rgba(255,255,255,0.65)", fontSize: 13 }}>
            Pas maintenant
          </button>
        </div>
      </div>
    );
  }

  return (
    <div style={cadre} data-testid="temoignage-formulaire">
      <label style={{ display: "block", color: "#fff", fontSize: 13, fontWeight: 600, marginBottom: 6 }}>
        Comment décrirais-tu ton expérience Afroboost&nbsp;?
      </label>
      <textarea
        data-testid="temoignage-texte"
        value={texte}
        onChange={(e) => setTexte(e.target.value)}
        rows={4}
        maxLength={1500}
        placeholder="En quelques mots…"
        style={{ width: "100%", padding: "9px 10px", borderRadius: 10, background: "#0a0a1a",
                 border: BORDURE, color: "#fff", fontSize: 16, boxSizing: "border-box",
                 outline: "none", resize: "vertical" }}
      />

      <label style={{ display: "flex", alignItems: "flex-start", gap: 8, marginTop: 10,
                      fontSize: 12, color: "rgba(255,255,255,0.75)", cursor: "pointer" }}>
        <input type="checkbox" data-testid="temoignage-consent" checked={publier}
          onChange={(e) => setPublier(e.target.checked)}
          style={{ marginTop: 2, width: 16, height: 16, accentColor: PRIMAIRE }} />
        <span>
          J'autorise Afroboost à publier ce témoignage.{" "}
          <button type="button" data-testid="temoignage-detail-lien"
            onClick={(e) => { e.preventDefault(); setDetail(!detail); }}
            style={{ background: "none", border: "none", padding: 0, cursor: "pointer",
                     color: PRIMAIRE, textDecoration: "underline", font: "inherit" }}>
            Comment sera-t-il utilisé&nbsp;?
          </button>
        </span>
      </label>

      {detail && (
        <p data-testid="temoignage-detail" style={{ margin: "8px 0 0", padding: "9px 11px",
             borderRadius: 10, background: "rgba(255,255,255,0.04)",
             color: "rgba(255,255,255,0.7)", fontSize: 11.5, lineHeight: 1.5 }}>
          Votre témoignage peut apparaître sur le site Afroboost, sur les pages
          qui présentent ses offres et dans ses supports de communication. Il
          n'est publié qu'après relecture par le coach. Vous pouvez en demander
          le retrait à tout moment en écrivant à contact@afroboosteur.com.
        </p>
      )}

      {publier && (
        <label style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 8,
                        fontSize: 12, color: "rgba(255,255,255,0.75)", cursor: "pointer" }}>
          <input type="checkbox" data-testid="temoignage-identite" checked={identite}
            onChange={(e) => setIdentite(e.target.checked)}
            style={{ width: 16, height: 16, accentColor: PRIMAIRE }} />
          <span>Afficher mon prénom à côté de mon témoignage</span>
        </label>
      )}

      {publier && (
        <p data-testid="temoignage-apercu" style={{ margin: "10px 0 0", padding: "9px 11px",
             borderRadius: 10, border: `1px dashed ${PRIMAIRE}`,
             color: "rgba(255,255,255,0.6)", fontSize: 11.5, lineHeight: 1.5 }}>
          Il apparaîtra ainsi : « {texte.trim() || "…"} » —{" "}
          {identite ? (prenom || "votre prénom") : "Anonyme"}
        </p>
      )}

      {erreur && (
        <p data-testid="temoignage-erreur" style={{ margin: "8px 0 0", color: "#fbbf24", fontSize: 12 }}>
          {erreur}
        </p>
      )}

      <div style={{ display: "flex", gap: 8, marginTop: 12, flexWrap: "wrap" }}>
        <button type="button" data-testid="temoignage-envoyer" onClick={envoyer}
          disabled={!texte.trim() || envoi}
          style={{ padding: "9px 16px", borderRadius: 999, border: "none",
                   cursor: (!texte.trim() || envoi) ? "not-allowed" : "pointer",
                   background: PRIMAIRE, color: "#fff", fontSize: 13, fontWeight: 700,
                   opacity: (!texte.trim() || envoi) ? 0.5 : 1 }}>
          {envoi ? "Envoi…" : "Envoyer"}
        </button>
        <button type="button" data-testid="temoignage-plus-tard" onClick={plusTard}
          style={{ padding: "9px 16px", borderRadius: 999, cursor: "pointer",
                   background: "transparent", border: BORDURE,
                   color: "rgba(255,255,255,0.65)", fontSize: 13 }}>
          Pas maintenant
        </button>
      </div>
    </div>
  );
}
