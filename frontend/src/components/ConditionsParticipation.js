/**
 * ConditionsParticipation — ESSAI-5a-1
 *
 * Une case, une ligne, un lien discret. Le détail n'occupe l'écran que si la
 * personne le demande.
 *
 * Ce composant existe parce que trois chemins de réservation devaient poser la
 * même question : la vitrine, l'espace abonné et le ChatWidget. La vitrine
 * avait une case, les deux autres — qui portent 113 des 132 réservations
 * réelles — n'en avaient aucune.
 *
 * Il ne DÉCIDE rien. Le serveur relit la version des conditions, l'heure et
 * l'annonce de captation du cours ; cet écran n'envoie que « j'accepte ».
 *
 * Quand aucune condition n'est publiée (`required: false`), il ne s'affiche
 * pas du tout et ne bloque rien — c'est ce qui rend le déploiement inoffensif
 * tant que le texte n'est pas écrit.
 */
import { useState, useEffect } from "react";
import axios from "axios";

const API = `${process.env.REACT_APP_BACKEND_URL || ''}/api`;
const PRIMAIRE = "var(--primary-color, #D91CD2)";

export default function ConditionsParticipation({ courseId = "", accepte, onChange, onRequired }) {
  const [etat, setEtat] = useState(null);   // null = chargement
  const [ouvert, setOuvert] = useState(false);

  useEffect(() => {
    let vivant = true;
    axios
      .get(`${API}/terms/active`, { params: { course_id: courseId || undefined } })
      .then((r) => {
        if (!vivant) return;
        setEtat(r.data || null);
        // L'appelant doit savoir s'il faut bloquer son bouton. Sans conditions
        // publiees, rien n'est exige et rien ne doit etre bloque.
        if (onRequired) onRequired(!!(r.data && r.data.required));
      })
      // Une lecture qui échoue ne doit pas bloquer une réservation : le serveur
      // reste seul juge, et il refusera si les conditions sont exigibles.
      .catch(() => {
        if (!vivant) return;
        setEtat({ required: false });
        if (onRequired) onRequired(false);
      });
    return () => { vivant = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [courseId]);

  if (!etat || !etat.required) return null;

  return (
    <>
      <label
        data-testid="conditions-participation"
        style={{
          display: "flex", alignItems: "flex-start", gap: 8, cursor: "pointer",
          fontSize: 13, lineHeight: 1.45, color: "rgba(255,255,255,0.8)",
        }}
      >
        <input
          type="checkbox"
          data-testid="conditions-case"
          checked={!!accepte}
          onChange={(e) => onChange && onChange(e.target.checked)}
          style={{ marginTop: 2, width: 18, height: 18, flexShrink: 0, accentColor: PRIMAIRE }}
        />
        <span>
          J'accepte les conditions de participation
          {etat.filmed ? " et d'image" : ""}{" "}
          <button
            type="button"
            data-testid="conditions-lien"
            onClick={(e) => { e.preventDefault(); e.stopPropagation(); setOuvert(true); }}
            style={{
              background: "none", border: "none", padding: 0, cursor: "pointer",
              color: PRIMAIRE, textDecoration: "underline", font: "inherit",
            }}
          >
            Voir les conditions
          </button>
          {etat.filmed && (
            <span data-testid="conditions-captation" style={{ display: "block", marginTop: 4, opacity: 0.65, fontSize: 12 }}>
              Cette séance est susceptible d'être photographiée ou filmée.
            </span>
          )}
        </span>
      </label>

      {ouvert && (
        <div
          data-testid="conditions-modal"
          onClick={() => setOuvert(false)}
          style={{
            position: "fixed", inset: 0, zIndex: 10000,
            background: "rgba(0,0,0,0.75)", display: "flex",
            alignItems: "center", justifyContent: "center", padding: 16,
          }}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              background: "#0a0a1a", border: "1px solid rgba(255,255,255,0.12)",
              borderRadius: 14, padding: 18, width: "100%", maxWidth: 560,
              maxHeight: "82vh", display: "flex", flexDirection: "column",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
              <h3 style={{ margin: 0, color: "#fff", fontSize: 16, fontWeight: 800 }}>
                Conditions de participation
              </h3>
              <button
                type="button"
                data-testid="conditions-fermer"
                onClick={() => setOuvert(false)}
                aria-label="Fermer"
                style={{ background: "none", border: "none", color: "#fff", fontSize: 26, lineHeight: 1, cursor: "pointer" }}
              >
                ×
              </button>
            </div>
            <div
              style={{
                overflowY: "auto", color: "rgba(255,255,255,0.85)", fontSize: 13,
                lineHeight: 1.55, whiteSpace: "pre-wrap",
              }}
            >
              {etat.text}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
