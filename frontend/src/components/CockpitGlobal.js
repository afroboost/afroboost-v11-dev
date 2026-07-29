/**
 * CockpitGlobal — V334 étape 4
 * Cockpit global du site, dans le panneau super admin.
 *
 * Chiffres agrégés + répartition par coach, avec exploration en profondeur :
 * global -> un coach -> ses abonnés. Les données par abonné viennent des endpoints
 * déjà en place (`/progress/coach/subscribers`), qui appliquent leurs propres droits.
 *
 * ACCÈS : le serveur exige un JWT super-admin signé sur `/progress/admin/global`.
 * Cet écran ne fait qu'afficher ; il ne décide d'aucun droit.
 */
import { useState, useEffect } from "react";
import axios from "axios";

const API = `${process.env.REACT_APP_BACKEND_URL || ''}/api`;
const PRIMAIRE = "var(--primary-color, #D91CD2)";
const BORDURE = "1px solid rgba(255,255,255,0.08)";

const Carte = ({ valeur, libelle, precision }) => (
  <div style={{
    flex: "1 1 130px", minWidth: 120, background: "rgba(255,255,255,0.03)",
    border: BORDURE, borderRadius: 12, padding: "14px 12px", textAlign: "center",
  }}>
    <div style={{ color: PRIMAIRE, fontSize: 24, fontWeight: 800, lineHeight: 1.1 }}>{valeur}</div>
    <div style={{ color: "rgba(255,255,255,0.5)", fontSize: 11, marginTop: 4 }}>{libelle}</div>
    {precision ? (
      <div style={{ color: "rgba(255,255,255,0.3)", fontSize: 10, marginTop: 2 }}>{precision}</div>
    ) : null}
  </div>
);

export default function CockpitGlobal() {
  const [data, setData] = useState(null);
  const [erreur, setErreur] = useState("");
  const [coachOuvert, setCoachOuvert] = useState(null);
  const [abonnes, setAbonnes] = useState(null);

  useEffect(() => {
    let vivant = true;
    axios.get(`${API}/progress/admin/global`)
      .then((r) => { if (vivant) { setData(r.data); setErreur(""); } })
      .catch((e) => {
        if (!vivant) return;
        setErreur(e?.response?.status === 403
          ? "Réservé au super-admin — reconnectez-vous (un jeton signé est exigé)."
          : "Impossible de charger le cockpit global.");
      });
    return () => { vivant = false; };
  }, []);

  // Exploration : on descend sur un coach. La liste renvoyée est celle que le
  // serveur autorise — en tant que super admin, elle contient tous les abonnés.
  const ouvrirCoach = async (coachId) => {
    if (coachOuvert === coachId) { setCoachOuvert(null); setAbonnes(null); return; }
    setCoachOuvert(coachId); setAbonnes(null);
    try {
      const r = await axios.get(`${API}/progress/coach/subscribers`);
      const tous = r.data.subscribers || [];
      setAbonnes(tous);
    } catch (e) {
      setAbonnes([]);
    }
  };

  if (erreur) return <p style={{ color: "#fca5a5", fontSize: 13 }}>{erreur}</p>;
  if (!data) return <p style={{ color: "rgba(255,255,255,0.4)", fontSize: 13 }}>Chargement…</p>;

  const g = data.global || {};

  return (
    <div data-testid="cockpit-global">
      <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginBottom: 16 }}>
        <Carte valeur={g.abonnes_actifs ?? 0} libelle="abonnés actifs"
               precision={`${g.abonnes_actifs_30j ?? 0} actifs sur 30 j`} />
        <Carte valeur={g.seances_totales ?? 0} libelle="séances suivies"
               precision={`${g.seances_30j ?? 0} sur 30 j`} />
        <Carte valeur={g.regularite_moyenne === null || g.regularite_moyenne === undefined
                        ? "—" : `${g.regularite_moyenne}/sem`}
               libelle="régularité moyenne"
               precision={`sur ${g.nb_regularites_mesurables ?? 0} abonné(s) mesurable(s)`} />
        <Carte valeur={g.nb_coachs ?? 0} libelle="coachs" />
        <Carte valeur={g.entrees_progression ?? 0} libelle="mesures enregistrées" />
      </div>

      <p style={{ color: "rgba(255,255,255,0.35)", fontSize: 11, margin: "0 0 12px" }}>
        La régularité moyenne ne porte que sur les abonnés ayant au moins une semaine
        de recul — un inscrit d'hier ne tire pas la moyenne vers le bas.
      </p>

      <h4 style={{ color: "#fff", fontSize: 13, fontWeight: 700, margin: "0 0 8px" }}>
        Par coach
      </h4>
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {(data.coaches || []).map((co) => {
          const ouvert = coachOuvert === co.coach_id;
          return (
            <div key={co.coach_id} style={{
              background: "rgba(255,255,255,0.03)", border: BORDURE, borderRadius: 12, padding: 12,
            }}>
              <button
                type="button"
                onClick={() => ouvrirCoach(co.coach_id)}
                style={{
                  width: "100%", display: "flex", alignItems: "center", justifyContent: "space-between",
                  gap: 8, background: "none", border: "none", color: "#fff", cursor: "pointer",
                  textAlign: "left", padding: 0,
                }}
                data-testid={`cockpit-coach-${co.coach_id}`}
              >
                <span style={{ fontSize: 13, fontWeight: 600, overflow: "hidden",
                               textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {co.name || co.coach_id}
                </span>
                <span style={{ color: "rgba(255,255,255,0.5)", fontSize: 11, flexShrink: 0 }}>
                  {co.abonnes} abonné{co.abonnes > 1 ? "s" : ""} · {co.seances} séances ·
                  {" "}{co.actifs_30j} actif{co.actifs_30j > 1 ? "s" : ""} 30 j
                </span>
              </button>

              {ouvert && (
                <div style={{ marginTop: 10, borderTop: BORDURE, paddingTop: 10 }}>
                  {abonnes === null ? (
                    <p style={{ color: "rgba(255,255,255,0.4)", fontSize: 12, margin: 0 }}>Chargement…</p>
                  ) : abonnes.length === 0 ? (
                    <p style={{ color: "rgba(255,255,255,0.4)", fontSize: 12, margin: 0 }}>Aucun abonné.</p>
                  ) : (
                    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                      {abonnes.slice(0, 50).map((s) => (
                        <div key={s.code} style={{
                          display: "flex", justifyContent: "space-between", gap: 8,
                          fontSize: 11.5, color: "rgba(255,255,255,0.6)",
                        }}>
                          <span style={{ color: "#fff", overflow: "hidden",
                                         textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                            {s.name || s.code}
                            {s.decrochage > 0.3 ? (
                              <span style={{ color: "#f59e0b", fontSize: 10, marginLeft: 6 }}>décroche</span>
                            ) : null}
                          </span>
                          <span style={{ flexShrink: 0 }}>
                            {s.seances_suivies} séances · {s.seances_30j ?? 0} sur 30 j
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
