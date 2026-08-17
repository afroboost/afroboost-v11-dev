/**
 * TemoignagesPublics — ESSAI-5a-2
 *
 * « ILS ONT VÉCU AFROBOOST » — une section RÉSERVÉE aux témoignages humains.
 *
 * Elle ne partage rien avec le mur de commentaires : ces derniers comptent
 * 88 textes générés par IA sur 100 affichés, et les mélanger reviendrait à
 * présenter une machine comme un participant. Les deux mondes ne se croisent
 * pas — le serveur ne rend ici que ce qui porte le marqueur de témoignage,
 * a reçu le consentement de son auteur, et a été approuvé par le coach.
 *
 * Si rien n'est approuvé, la section ne s'affiche pas du tout. Mieux vaut
 * une absence qu'une preuve sociale fabriquée.
 */
import { useState, useEffect } from "react";
import axios from "axios";

const API = `${process.env.REACT_APP_BACKEND_URL || ''}/api`;
const PRIMAIRE = "var(--primary-color, #D91CD2)";

export default function TemoignagesPublics({ offerId = "", coachId = "", limite = 6 }) {
  const [liste, setListe] = useState(null);   // null = chargement

  useEffect(() => {
    let vivant = true;
    axios
      .get(`${API}/testimonials`, {
        params: {
          offer_id: offerId || undefined,
          coach_id: coachId || undefined,
          limit: limite,
        },
      })
      .then((r) => { if (vivant) setListe((r.data && r.data.testimonials) || []); })
      // Une lecture qui échoue n'affiche rien : on ne remplace pas des
      // témoignages absents par un message d'erreur sur une page publique.
      .catch(() => { if (vivant) setListe([]); });
    return () => { vivant = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [offerId, coachId, limite]);

  if (!liste || liste.length === 0) return null;

  return (
    <section data-testid="temoignages-publics" style={{ marginTop: 28 }}>
      <h3 style={{ color: "#fff", fontSize: 15, fontWeight: 800, letterSpacing: 0.4,
                   textTransform: "uppercase", margin: "0 0 12px" }}>
        Ils ont vécu Afroboost
      </h3>
      <div style={{ display: "grid", gap: 10,
                    gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))" }}>
        {liste.map((t) => (
          <blockquote key={t.id} data-testid="temoignage-public"
            style={{ margin: 0, padding: "14px 16px", borderRadius: 14,
                     background: "rgba(255,255,255,0.04)",
                     borderLeft: `3px solid ${PRIMAIRE}` }}>
            <p style={{ margin: 0, color: "rgba(255,255,255,0.88)", fontSize: 13.5,
                        lineHeight: 1.55, whiteSpace: "pre-wrap" }}>
              {t.text}
            </p>
            {/* Le prénom n'apparaît que si la personne l'a autorisé
                séparément : consentir à publier ses mots n'est pas consentir
                à publier son identité. */}
            <footer style={{ marginTop: 8, color: "rgba(255,255,255,0.45)", fontSize: 11.5 }}>
              — {t.user_name || "Anonyme"}
            </footer>
          </blockquote>
        ))}
      </div>
    </section>
  );
}
