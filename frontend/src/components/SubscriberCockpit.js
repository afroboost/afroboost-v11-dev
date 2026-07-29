/**
 * SubscriberCockpit — V334 étape 2
 * « Mon cockpit » : la progression de l'abonné, dans son espace.
 *
 * Ce composant n'affiche QUE les données de l'abonné dont il détient le code.
 * Les chiffres viennent d'un seul appel (`GET /api/progress/{code}/cockpit`), qui
 * les calcule côté serveur — les vues coach (étape 3) et super admin (étape 4)
 * consommeront les mêmes, pour ne pas produire trois résultats différents.
 *
 * Règles projet respectées : aucune couleur codée en dur (toujours var(--primary-color, …)),
 * aucune icône en emoji (SVG inline uniquement), replié par défaut pour ne pas
 * alourdir l'espace abonné existant.
 */
import { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import DetailAbonne, { FormulaireMesure, ResultatsCalcules } from "./progress/DetailAbonne"; // V338/V339

const API = `${process.env.REACT_APP_BACKEND_URL || ''}/api`;

const C = {
  bg: "#0A0A0F",
  primary: "var(--primary-color, #D91CD2)",
  panel: "rgba(255,255,255,0.04)",
  border: "rgba(255,255,255,0.08)",
};

const IconeChevron = ({ ouvert }) => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
       strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
       style={{ transform: ouvert ? "rotate(180deg)" : "none", transition: "transform .2s" }}>
    <polyline points="6 9 12 15 18 9" />
  </svg>
);

const IconeCible = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor"
       strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="10" /><circle cx="12" cy="12" r="6" /><circle cx="12" cy="12" r="2" />
  </svg>
);

const champ = {
  width: "100%", padding: "9px 11px", borderRadius: 9,
  background: C.bg, border: `1px solid ${C.border}`, color: "#fff",
  fontSize: 14, boxSizing: "border-box", outline: "none",
};

/** Une statistique, en gros chiffre + libellé. */
const Chiffre = ({ valeur, libelle, suffixe }) => (
  <div style={{
    flex: "1 1 0", minWidth: 80, textAlign: "center",
    background: C.panel, border: `1px solid ${C.border}`, borderRadius: 12, padding: "12px 8px",
  }}>
    <div style={{ color: C.primary, fontSize: 20, fontWeight: 800, lineHeight: 1.1 }}>
      {valeur}{suffixe ? <span style={{ fontSize: 12, fontWeight: 600 }}>{suffixe}</span> : null}
    </div>
    <div style={{ color: "rgba(255,255,255,0.45)", fontSize: 10.5, marginTop: 4 }}>{libelle}</div>
  </div>
);

export default function SubscriberCockpit({ accessCode }) {
  const [ouvert, setOuvert] = useState(false);
  const [data, setData] = useState(null);      // null = pas encore chargé
  const [erreur, setErreur] = useState("");
  const [saisieOuverte, setSaisieOuverte] = useState(false);
  const [retour, setRetour] = useState(null);

  const charger = useCallback(async () => {
    if (!accessCode) return;
    try {
      const r = await axios.get(
        `${API}/progress/${encodeURIComponent(accessCode)}/cockpit`,
        { params: { code: accessCode } }
      );
      setData(r.data);
      setErreur("");
    } catch (e) {
      // Échec honnête : on ne montre jamais un cockpit vide en prétendant
      // que l'abonné n'a rien fait.
      setErreur("Impossible de charger votre progression pour le moment.");
    }
  }, [accessCode]);

  // Chargé seulement à l'ouverture : l'espace abonné doit rester rapide.
  useEffect(() => { if (ouvert && data === null) charger(); }, [ouvert, data, charger]);

  const stats = (data && data.stats) || {};
  // Une courbe n'a de sens qu'à partir de deux points.
  const courbePoids = ((data && data.entries) || [])
    .filter((e) => typeof e.weight_kg === "number")
    .map((e) => ({
      date: new Date(e.entry_date).toLocaleDateString("fr-FR", { day: "2-digit", month: "short" }),
      poids: e.weight_kg,
    }));

  return (
    <section
      style={{ background: C.panel, border: `1px solid ${C.border}`, borderRadius: 14, overflow: "hidden" }}
      data-testid="subscriber-cockpit"
    >
      <button
        type="button"
        onClick={() => setOuvert(!ouvert)}
        style={{
          width: "100%", display: "flex", alignItems: "center", justifyContent: "space-between",
          gap: 8, padding: "14px 16px", background: "none", border: "none",
          color: "#fff", cursor: "pointer", textAlign: "left",
        }}
        data-testid="cockpit-toggle"
      >
        <span style={{ fontSize: 15, fontWeight: 700 }}>Mon cockpit</span>
        <span style={{ color: "rgba(255,255,255,0.5)" }}><IconeChevron ouvert={ouvert} /></span>
      </button>

      {ouvert && (
        <div style={{ padding: "0 16px 16px" }}>
          {erreur ? (
            <p style={{ color: "#fca5a5", fontSize: 13, margin: "8px 0" }}>{erreur}</p>
          ) : data === null ? (
            <p style={{ color: "rgba(255,255,255,0.4)", fontSize: 13, margin: "8px 0" }}>Chargement…</p>
          ) : (
            <>
              {/* ===== Objectifs (V333), en tête ===== */}
              {data.objectifs ? (
                <div style={{
                  display: "flex", gap: 8, alignItems: "flex-start", marginBottom: 14,
                  padding: "10px 12px", borderRadius: 10,
                  background: "rgba(var(--primary-rgb, 217, 28, 210), 0.08)",
                  border: "1px solid rgba(var(--primary-rgb, 217, 28, 210), 0.2)",
                }}>
                  <span style={{ color: C.primary, marginTop: 2 }}><IconeCible /></span>
                  <div>
                    <div style={{ color: C.primary, fontSize: 11, fontWeight: 700, marginBottom: 2 }}>
                      Mes objectifs
                    </div>
                    <div style={{ color: "rgba(255,255,255,0.75)", fontSize: 13, lineHeight: 1.45 }}>
                      {data.objectifs}
                    </div>
                  </div>
                </div>
              ) : null}

              {/* ===== Chiffres de pratique ===== */}
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 14 }}>
                <Chiffre valeur={stats.seances_suivies ?? 0} libelle="séances suivies" />
                <Chiffre valeur={stats.seances_a_venir ?? 0} libelle="à venir" />
                <Chiffre
                  valeur={stats.regularite_par_semaine === null || stats.regularite_par_semaine === undefined
                    ? "—" : stats.regularite_par_semaine}
                  suffixe={stats.regularite_par_semaine ? "/sem" : ""}
                  libelle="régularité"
                />
                <Chiffre valeur={stats.anciennete_jours ?? 0} suffixe=" j" libelle="ancienneté" />
              </div>
              {stats.regularite_par_semaine === null ? (
                <p style={{ color: "rgba(255,255,255,0.3)", fontSize: 10.5, margin: "-8px 0 14px" }}>
                  La régularité s'affiche après une semaine de pratique.
                </p>
              ) : null}

              {/* V339 : IMC, rapport taille/hanches, progression — calculés par le
                  serveur, donc identiques à ce que voit le coach. */}
              <ResultatsCalcules calculs={data.calculs} />

              {/* ===== Courbe de poids ===== */}
              {courbePoids.length >= 2 ? (
                <div style={{ marginBottom: 14 }}>
                  <div style={{ color: "rgba(255,255,255,0.6)", fontSize: 11.5, marginBottom: 6 }}>
                    Évolution du poids (kg)
                  </div>
                  <div style={{ width: "100%", height: 160 }}>
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={courbePoids} margin={{ top: 5, right: 8, bottom: 0, left: -20 }}>
                        <CartesianGrid stroke="rgba(255,255,255,0.06)" vertical={false} />
                        <XAxis dataKey="date" tick={{ fill: "rgba(255,255,255,0.4)", fontSize: 10 }}
                               axisLine={false} tickLine={false} />
                        <YAxis domain={["auto", "auto"]} tick={{ fill: "rgba(255,255,255,0.4)", fontSize: 10 }}
                               axisLine={false} tickLine={false} width={44} />
                        <Tooltip
                          contentStyle={{ background: "#141428", border: `1px solid ${C.border}`,
                                          borderRadius: 8, fontSize: 12 }}
                          labelStyle={{ color: "rgba(255,255,255,0.6)" }}
                        />
                        <Line type="monotone" dataKey="poids" stroke="var(--primary-color, #D91CD2)"
                              strokeWidth={2} dot={{ r: 3 }} />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              ) : courbePoids.length === 1 ? (
                <p style={{ color: "rgba(255,255,255,0.4)", fontSize: 12, margin: "0 0 14px" }}>
                  Première mesure enregistrée ({courbePoids[0].poids} kg). La courbe apparaîtra dès la deuxième.
                </p>
              ) : null}

              {/* ===== Photos avant / après ===== */}
              {data.photos && data.photos.length > 0 ? (
                <div style={{ marginBottom: 14 }}>
                  <div style={{ color: "rgba(255,255,255,0.6)", fontSize: 11.5, marginBottom: 6 }}>
                    Photos ({data.photos.length})
                  </div>
                  <div style={{ display: "flex", gap: 8, overflowX: "auto", paddingBottom: 4 }}>
                    {data.photos.map((p, i) => (
                      <div key={i} style={{ flexShrink: 0, textAlign: "center" }}>
                        <img src={p.photo_url} alt=""
                             style={{ width: 84, height: 112, objectFit: "cover", borderRadius: 8,
                                      border: `1px solid ${C.border}` }} />
                        <div style={{ color: "rgba(255,255,255,0.35)", fontSize: 10, marginTop: 3 }}>
                          {new Date(p.entry_date).toLocaleDateString("fr-FR", { day: "2-digit", month: "short" })}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}

              {/* V334 : cockpit encore vide -> on invite au premier pas plutot que
                  d'afficher une page de zeros, qui decourage. */}
              {(stats.seances_suivies || 0) === 0 && (data.entries || []).length === 0 ? (
                <p style={{ color: "rgba(255,255,255,0.45)", fontSize: 12.5, lineHeight: 1.5,
                            margin: "0 0 12px" }}>
                  Enregistrez votre première mesure pour commencer à suivre vos progrès.
                  Vos séances viendront s'y ajouter automatiquement.
                </p>
              ) : null}

              {/* V338 : séances datées + note du coach — MÊME bloc que côté coach
                  et côté super-admin, pour un rendu strictement identique. */}
              <div style={{ marginBottom: 14 }}>
                <DetailAbonne
                  code={accessCode}
                  seances={stats.seances}
                  codePreuve={accessCode}
                  peutEcrire={false}
                />
              </div>

              {/* ===== Saisie d'une mesure ===== */}
              <button
                type="button"
                onClick={() => setSaisieOuverte(!saisieOuverte)}
                style={{
                  display: "inline-flex", alignItems: "center", gap: 6, padding: "7px 14px",
                  borderRadius: 999, background: "none",
                  border: "1px solid rgba(var(--primary-rgb, 217, 28, 210), 0.45)",
                  color: C.primary, fontSize: 12.5, fontWeight: 600, cursor: "pointer",
                }}
                data-testid="cockpit-add-toggle"
              >
                + Ajouter une mesure
              </button>

              {saisieOuverte && (
                <div style={{ marginTop: 10 }}>
                  {/* V339 : formulaire enrichi PARTAGÉ avec la vue coach — mêmes
                      champs, mêmes règles, même mémorisation de la taille. */}
                  <FormulaireMesure
                    code={accessCode}
                    codePreuve={accessCode}
                    tailleCm={data.taille_cm}
                    onEnregistre={async () => { setData(null); await charger(); }}
                  />
                </div>
              )}

              {retour ? (
                <p style={{ margin: "8px 0 0", fontSize: 12,
                            color: retour.type === "ok" ? "#4ade80" : "#fca5a5" }}>
                  {retour.texte}
                </p>
              ) : null}
            </>
          )}
        </div>
      )}
    </section>
  );
}
