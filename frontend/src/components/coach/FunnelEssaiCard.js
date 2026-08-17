/**
 * FunnelEssaiCard — ESSAI-3
 * « Funnel essai gratuit » du dashboard coach : quatre étages, lus dans la base
 * métier par `GET /api/coach/funnel/free-trial`. PostHog n'est pas interrogé.
 *
 * L'ISOLATION EST FAITE PAR LE SERVEUR : la route filtre sur le coach du jeton.
 * Cet écran ne demande jamais « le funnel de X » — il n'a aucun endroit où
 * l'écrire, et c'est voulu.
 *
 * Il n'affiche AUCUNE donnée de participant : ni nom, ni adresse, ni code. La
 * réponse n'en contient pas, et cet écran ne saurait donc pas en inventer.
 *
 * Le 4e étage ne remonte pas avant le déploiement du marqueur `converted_at`
 * (ESSAI-2). Plutôt qu'un zéro muet qui passerait pour un échec commercial,
 * l'écran dit depuis quand la mesure vaut.
 */
import { useState, useEffect, useCallback } from "react";
import axios from "axios";

const API = `${process.env.REACT_APP_BACKEND_URL || ''}/api`;

const PRIMAIRE = "var(--primary-color, #D91CD2)";
const BORDURE = "1px solid rgba(255,255,255,0.08)";

const PERIODES = [
  { id: "7d", label: "7 jours" },
  { id: "30d", label: "30 jours" },
  { id: "90d", label: "90 jours" },
  { id: "all", label: "Tout" },
];

/** Les quatre étages, dans l'ordre où on les perd. */
const ETAPES = [
  { cle: "granted", titre: "Essais accordés", taux: null },
  { cle: "booked", titre: "Essais réservés", taux: "booking" },
  { cle: "attended", titre: "Essais présents", taux: "attendance" },
  { cle: "converted", titre: "Clients convertis", taux: "conversion" },
];

/** Une phrase par verdict du serveur. Aucune n'est composée ici : le serveur
 *  décide, l'écran traduit. Pas d'IA, pas de hasard. */
const DIAGNOSTICS = {
  accorde_reserve: "Votre principale perte se situe entre l'essai accordé et la réservation.",
  reserve_present: "Votre principale perte se situe entre la réservation et la présence.",
  present_converti: "Votre principale opportunité est la conversion après l'essai.",
  echantillon_faible: "Trop peu d'essais sur cette période pour en tirer une conclusion fiable.",
};

/** Un taux absent n'est pas un taux nul : « — » dit « pas encore mesurable »,
 *  « 0 % » dit « aucun ne passe ». Les confondre trompe le coach. */
export const pourcent = (t) =>
  (t === null || t === undefined || Number.isNaN(t)) ? "—" : `${Math.round(t * 100)} %`;

export const jours = (n) => {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  const s = Number(n).toFixed(1).replace(".", ",").replace(",0", "");
  return `${s} jour${Number(n) >= 2 ? "s" : ""}`;
};

const dateCourte = (iso) => {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleDateString("fr-FR",
      { day: "2-digit", month: "long", year: "numeric" });
  } catch (e) { return ""; }
};

const pilule = (actif) => ({
  padding: "6px 12px", borderRadius: 999, fontSize: 12, cursor: "pointer",
  border: actif ? `1px solid ${PRIMAIRE}` : BORDURE,
  background: actif ? PRIMAIRE : "transparent",
  color: actif ? "#fff" : "rgba(255,255,255,0.65)",
  fontWeight: actif ? 700 : 500, whiteSpace: "nowrap",
});

export default function FunnelEssaiCard() {
  const [donnees, setDonnees] = useState(null);   // null = chargement
  const [erreur, setErreur] = useState("");
  const [periode, setPeriode] = useState("30d");
  const [offre, setOffre] = useState("");

  const charger = useCallback(async () => {
    setDonnees(null);
    setErreur("");
    try {
      const r = await axios.get(`${API}/coach/funnel/free-trial`, {
        params: { period: periode, offer_id: offre || undefined },
      });
      setDonnees(r.data || null);
    } catch (e) {
      setDonnees(null);
      setErreur(e?.response?.status === 403 || e?.response?.status === 401
        ? "Accès refusé — reconnectez-vous."
        : "Impossible de charger le funnel pour le moment.");
    }
  }, [periode, offre]);

  useEffect(() => { charger(); }, [charger]);

  const titre = (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between",
                  flexWrap: "wrap", gap: 8, marginBottom: 12 }}>
      <h3 style={{ color: "#fff", fontSize: 16, fontWeight: 800, margin: 0 }}>
        Funnel essai gratuit
      </h3>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
        {PERIODES.map((p) => (
          <button key={p.id} type="button" data-testid={`funnel-periode-${p.id}`}
                  aria-pressed={periode === p.id}
                  onClick={() => setPeriode(p.id)} style={pilule(periode === p.id)}>
            {p.label}
          </button>
        ))}
      </div>
    </div>
  );

  const cadre = (contenu) => (
    <div data-testid="funnel-essai" style={{
      background: "#0a0a1a", border: BORDURE, borderRadius: 14, padding: 16,
    }}>
      {titre}
      {contenu}
    </div>
  );

  if (erreur) {
    return cadre(
      <div data-testid="funnel-erreur" style={{ textAlign: "center", padding: "18px 8px" }}>
        <p style={{ color: "rgba(255,255,255,0.75)", fontSize: 13, margin: "0 0 12px" }}>{erreur}</p>
        <button type="button" onClick={charger} style={{ ...pilule(true), padding: "8px 18px" }}>
          Réessayer
        </button>
      </div>
    );
  }

  if (!donnees) {
    return cadre(
      <div data-testid="funnel-chargement" aria-busy="true">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} style={{
            height: 54, marginBottom: 8, borderRadius: 10,
            background: "rgba(255,255,255,0.05)",
            width: `${100 - i * 14}%`,
          }} />
        ))}
      </div>
    );
  }

  const { granted, booked, attended, converted, rates, offers } = donnees;
  const compteurs = { granted, booked, attended, converted };
  const diag = donnees.diagnostic || {};
  const couv = donnees.coverage || {};
  const delai = donnees.conversion_delay || {};

  const selecteurOffre = (offers && offers.length > 1) ? (
    <select data-testid="funnel-offre" value={offre} aria-label="Filtrer par offre"
            onChange={(e) => setOffre(e.target.value)}
            style={{
              width: "100%", marginBottom: 12, padding: "9px 10px", borderRadius: 8,
              background: "#12122a", border: BORDURE, color: "#fff",
              // 16 px minimum : en dessous, iOS zoome sur le champ à l'ouverture.
              fontSize: 16, boxSizing: "border-box", outline: "none",
            }}>
      <option value="">Toutes les offres</option>
      {offers.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
    </select>
  ) : null;

  if (!granted) {
    return cadre(
      <>
        {selecteurOffre}
        <p data-testid="funnel-vide" style={{
          color: "rgba(255,255,255,0.6)", fontSize: 13, textAlign: "center",
          padding: "18px 8px", margin: 0, lineHeight: 1.5,
        }}>
          Aucun essai gratuit accordé sur cette période.<br />
          Élargissez la période pour voir plus loin.
        </p>
      </>
    );
  }

  return cadre(
    <>
      {selecteurOffre}

      <div role="list" data-testid="funnel-etapes">
        {ETAPES.map((e, i) => {
          const valeur = compteurs[e.cle] || 0;
          // La largeur dit la proportion d'un coup d'oeil ; le chiffre reste
          // lisible même quand la barre est presque vide.
          const part = granted ? Math.max(18, Math.round((valeur / granted) * 100)) : 100;
          return (
            <div key={e.cle} role="listitem">
              {i > 0 && (
                <div style={{
                  display: "flex", alignItems: "center", gap: 6,
                  padding: "5px 0 5px 14px", fontSize: 12,
                  color: "rgba(255,255,255,0.5)",
                }}>
                  <span aria-hidden="true">↓</span>
                  <strong data-testid={`funnel-taux-${e.taux}`} style={{ color: PRIMAIRE }}>
                    {pourcent(rates ? rates[e.taux] : null)}
                  </strong>
                </div>
              )}
              <div style={{
                width: `${part}%`, minWidth: 150, borderRadius: 12,
                border: BORDURE, padding: "11px 14px",
                background: `linear-gradient(90deg, ${PRIMAIRE}33, rgba(255,255,255,0.03))`,
                display: "flex", alignItems: "baseline", gap: 10,
              }}>
                <span data-testid={`funnel-${e.cle}`} style={{
                  color: "#fff", fontSize: 24, fontWeight: 800, lineHeight: 1,
                }}>{valeur}</span>
                <span style={{
                  color: "rgba(255,255,255,0.75)", fontSize: 12, fontWeight: 600,
                }}>{e.titre}</span>
              </div>
            </div>
          );
        })}
      </div>

      <div style={{
        display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))",
        gap: 8, marginTop: 14,
      }}>
        <div style={{ border: BORDURE, borderRadius: 10, padding: "10px 12px" }}>
          <div style={{ color: "rgba(255,255,255,0.55)", fontSize: 11 }}>
            Conversion essai → client
          </div>
          <div data-testid="funnel-global" style={{ color: "#fff", fontSize: 18, fontWeight: 800 }}>
            {pourcent(rates ? rates.overall : null)}
          </div>
        </div>
        <div style={{ border: BORDURE, borderRadius: 10, padding: "10px 12px" }}>
          <div style={{ color: "rgba(255,255,255,0.55)", fontSize: 11 }}>
            Délai moyen de conversion
          </div>
          <div data-testid="funnel-delai" style={{ color: "#fff", fontSize: 18, fontWeight: 800 }}>
            {jours(delai.average_days)}
          </div>
          {delai.sample_size > 0 && (
            <div style={{ color: "rgba(255,255,255,0.4)", fontSize: 10, marginTop: 2 }}>
              médiane {jours(delai.median_days)} · {delai.sample_size} conversion
              {delai.sample_size > 1 ? "s" : ""}
            </div>
          )}
        </div>
      </div>

      {DIAGNOSTICS[diag.cle] && (
        <p data-testid="funnel-diagnostic" style={{
          margin: "12px 0 0", padding: "10px 12px", borderRadius: 10,
          background: "rgba(255,255,255,0.04)", borderLeft: `3px solid ${PRIMAIRE}`,
          color: "rgba(255,255,255,0.85)", fontSize: 13, lineHeight: 1.45,
        }}>
          {DIAGNOSTICS[diag.cle]}
        </p>
      )}

      {couv.partial && (
        <p data-testid="funnel-couverture" style={{
          margin: "10px 0 0", color: "rgba(255,255,255,0.4)", fontSize: 11, lineHeight: 1.4,
        }}>
          Les conversions sont mesurées depuis le {dateCourte(couv.conversion_measured_since)}.
          Les essais accordés avant cette date apparaissent, mais leur achat éventuel
          n'a pas pu être enregistré.
        </p>
      )}
    </>
  );
}
