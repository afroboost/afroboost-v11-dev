/**
 * ModerationTemoignages — ESSAI-5a-2
 *
 * La modération des témoignages, dans « Social Boost », à côté des
 * commentaires déjà gérés là. Aucun nouveau dashboard.
 *
 * AUCUNE PUBLICATION AUTOMATIQUE : un témoignage arrive en attente et n'en
 * sort que par une action explicite du coach. Un témoignage masqué ne
 * redevient jamais public tout seul.
 *
 * Le code d'accès du participant n'est pas rendu par le serveur : il n'est
 * pas nécessaire pour modérer, et c'est le mot de passe de la personne.
 */
import { useState, useEffect, useCallback } from "react";
import axios from "axios";

const PRIMAIRE = "var(--primary-color, #D91CD2)";
const BORDURE = "1px solid rgba(255,255,255,0.10)";

const ONGLETS = [
  { id: "pending", libelle: "En attente" },
  { id: "approved", libelle: "Publiés" },
  { id: "hidden", libelle: "Masqués" },
];

const dateCourte = (iso) => {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleDateString("fr-FR", { day: "2-digit", month: "short" });
  } catch (e) { return ""; }
};

export default function ModerationTemoignages({ API, coachEmail, axios: axiosInjecte }) {
  const http = axiosInjecte || axios;
  const [etat, setEtat] = useState("pending");
  const [liste, setListe] = useState(null);
  const [compte, setCompte] = useState({});
  const [erreur, setErreur] = useState("");

  const charger = useCallback(async () => {
    setListe(null);
    try {
      const r = await http.get(`${API}/coach/testimonials`, {
        params: { status: etat },
        headers: { "X-User-Email": coachEmail || "" },
      });
      setListe((r.data && r.data.testimonials) || []);
      setCompte((r.data && r.data.counts) || {});
      setErreur("");
    } catch (e) {
      setListe([]);
      setErreur("Impossible de charger les témoignages.");
    }
  }, [API, coachEmail, etat, http]);

  useEffect(() => { charger(); }, [charger]);

  const moderer = async (id, statut) => {
    try {
      await http.put(`${API}/coach/testimonials/${encodeURIComponent(id)}/moderation`,
        { status: statut }, { headers: { "X-User-Email": coachEmail || "" } });
      charger();
    } catch (e) {
      setErreur("Action impossible pour le moment.");
    }
  };

  const pilule = (actif) => ({
    padding: "5px 11px", borderRadius: 999, fontSize: 12, cursor: "pointer",
    border: actif ? `1px solid ${PRIMAIRE}` : BORDURE,
    background: actif ? PRIMAIRE : "transparent",
    color: actif ? "#fff" : "rgba(255,255,255,0.6)", fontWeight: actif ? 700 : 500,
  });

  const bouton = (fond) => ({
    padding: "6px 12px", borderRadius: 8, fontSize: 12, cursor: "pointer",
    border: BORDURE, background: fond, color: "#fff", fontWeight: 600,
  });

  return (
    <div data-testid="moderation-temoignages" style={{ marginTop: 18 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between",
                    flexWrap: "wrap", gap: 8, marginBottom: 10 }}>
        <h4 style={{ margin: 0, color: "#fff", fontSize: 14, fontWeight: 800 }}>
          Témoignages des participants
        </h4>
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          {ONGLETS.map((o) => (
            <button key={o.id} type="button" data-testid={`moderation-onglet-${o.id}`}
              onClick={() => setEtat(o.id)} style={pilule(etat === o.id)}>
              {o.libelle}{typeof compte[o.id] === "number" ? ` (${compte[o.id]})` : ""}
            </button>
          ))}
        </div>
      </div>

      {erreur && <p style={{ color: "#fbbf24", fontSize: 12 }}>{erreur}</p>}

      {!liste ? (
        <p style={{ color: "rgba(255,255,255,0.4)", fontSize: 12 }}>Chargement…</p>
      ) : liste.length === 0 ? (
        <p data-testid="moderation-vide" style={{ color: "rgba(255,255,255,0.4)", fontSize: 12 }}>
          Aucun témoignage dans cet état.
        </p>
      ) : (
        liste.map((t) => (
          <div key={t.id} data-testid="moderation-item"
            style={{ border: BORDURE, borderRadius: 12, padding: 12, marginBottom: 8 }}>
            <p style={{ margin: 0, color: "rgba(255,255,255,0.88)", fontSize: 13, lineHeight: 1.5,
                        whiteSpace: "pre-wrap" }}>
              {t.text}
            </p>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 10, marginTop: 8,
                          fontSize: 11, color: "rgba(255,255,255,0.45)" }}>
              <span>{dateCourte(t.created_at)}</span>
              <span>{t.consent_identity ? (t.user_name || "prénom") : "Anonyme"}</span>
              <span data-testid="moderation-consentement">
                {t.consent_publication ? "Publication autorisée" : "Publication NON autorisée"}
              </span>
              {t.recognition && <span>{t.recognition}</span>}
            </div>
            {!t.consent_publication && (
              <p style={{ margin: "8px 0 0", fontSize: 11, color: "#fbbf24" }}>
                Approuver ne le rendra pas public : la personne n'a pas autorisé la publication.
              </p>
            )}
            <div style={{ display: "flex", gap: 8, marginTop: 10, flexWrap: "wrap" }}>
              {t.moderation_status !== "approved" && (
                <button type="button" data-testid={`moderation-approuver-${t.id}`}
                  onClick={() => moderer(t.id, "approved")} style={bouton("rgba(34,197,94,0.25)")}>
                  Approuver
                </button>
              )}
              {t.moderation_status !== "hidden" && (
                <button type="button" data-testid={`moderation-masquer-${t.id}`}
                  onClick={() => moderer(t.id, "hidden")} style={bouton("rgba(239,68,68,0.22)")}>
                  Masquer
                </button>
              )}
            </div>
          </div>
        ))
      )}
    </div>
  );
}
