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
 * V337 — ordre : les ACTIFS QUI DÉCROCHENT d'abord, c'est-à-dire ceux qui venaient
 * régulièrement et ont ralenti sur les 30 derniers jours. Trier sur la seule
 * régularité remontait les abonnés dormants depuis toujours, sur lesquels le coach
 * ne peut rien ; ceux qui ralentissent, eux, sont rattrapables.
 */
import { useState, useEffect, useCallback } from "react";
import axios from "axios";
import DetailAbonne, { FormulaireMesure, ResultatsCalcules } from "../progress/DetailAbonne"; // V338/V339

const API = `${process.env.REACT_APP_BACKEND_URL || ''}/api`;

const PRIMAIRE = "var(--primary-color, #D91CD2)";
const BORDURE = "1px solid rgba(255,255,255,0.08)";

const champ = {
  width: "100%", padding: "8px 10px", borderRadius: 8,
  background: "#0a0a1a", border: BORDURE, color: "#fff",
  fontSize: 13, boxSizing: "border-box", outline: "none",
};

/** V339 : comparaison insensible à la casse ET aux accents. « Genevieve » doit
 *  trouver « Geneviève », sinon la recherche paraît cassée. */
const sansAccents = (t) => (t || "")
  .toString()
  .normalize("NFD")
  .replace(/[\u0300-\u036f]/g, "")
  .toLowerCase();

/** V339 : un numéro se cherche par ses CHIFFRES. « 076 », « 4176 » et « +41 76 »
 *  doivent tous retrouver le même abonné : on retire tout le reste des deux côtés. */
const chiffresSeuls = (t) => (t || "").toString().replace(/\D/g, "");

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
  const [envoi, setEnvoi] = useState(false);
  const [retour, setRetour] = useState(null);
  const [recherche, setRecherche] = useState("");   // V339

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

  // V338 : au dépliage, on charge le cockpit de CET abonné pour disposer de ses
  // séances datées. Le serveur vérifie que ce coach y a droit.
  const [detail, setDetail] = useState({});   // { [code]: {seances} }
  const ouvrirDetail = async (code) => {
    if (detail[code]) return;
    try {
      const r = await axios.get(`${API}/progress/${encodeURIComponent(code)}/cockpit`);
      // V339 : on garde AUSSI taille_cm et calculs — le formulaire et les résultats
      // en ont besoin, et ils viennent du même appel (pas de second aller-retour).
      setDetail((prev) => ({ ...prev, [code]: {
        ...(r.data.stats || {}), taille_cm: r.data.taille_cm, calculs: r.data.calculs,
      } }));
    } catch (e) {
      setDetail((prev) => ({ ...prev, [code]: { seances: [] } }));
    }
  };


  // V339 : filtrage EN MÉMOIRE sur les données déjà chargées — pas d'appel réseau à
  // chaque touche. Il ne porte que sur la liste reçue, donc uniquement les abonnés
  // que le serveur a autorisés pour ce coach : l'isolation n'est pas contournable ici.
  const q = (recherche || "").trim();
  const qTexte = sansAccents(q);
  const qChiffres = chiffresSeuls(q);
  const filtree = !q ? (liste || []) : (liste || []).filter((s) => {
    const parTexte = sansAccents(s.name).includes(qTexte)
                  || sansAccents(s.email).includes(qTexte);
    // On ne cherche par numéro que si la saisie contient des chiffres, sinon
    // « a » matcherait tout numéro (chaîne vide incluse dans n'importe quoi).
    const parNumero = qChiffres.length >= 2
      && chiffresSeuls(s.whatsapp).includes(qChiffres);
    return parTexte || parNumero;
  });

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
      {/* V339 : recherche. Reste AU-DESSUS de la zone défilante pour ne jamais
          disparaître pendant qu'on parcourt la liste. */}
      <div style={{ position: "relative", marginBottom: 8 }}>
        <input
          type="text"
          value={recherche}
          onChange={(e) => setRecherche(e.target.value)}
          placeholder="Rechercher un abonné (nom, email, WhatsApp)…"
          data-testid="suivi-recherche"
          style={{ ...champ, paddingRight: 34 }}
        />
        {recherche ? (
          <button
            type="button"
            onClick={() => setRecherche("")}
            aria-label="Effacer la recherche"
            data-testid="suivi-recherche-clear"
            style={{
              position: "absolute", right: 6, top: "50%", transform: "translateY(-50%)",
              background: "none", border: "none", color: "rgba(255,255,255,0.45)",
              cursor: "pointer", padding: 4, lineHeight: 1,
            }}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                 strokeWidth="2" strokeLinecap="round">
              <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        ) : null}
      </div>

      <p style={{ color: "rgba(255,255,255,0.4)", fontSize: 11.5, margin: "0 0 12px" }}>
        {q
          ? `${filtree.length} résultat${filtree.length > 1 ? "s" : ""} sur ${liste.length} abonné${liste.length > 1 ? "s" : ""}.`
          : `${liste.length} abonné${liste.length > 1 ? "s" : ""} — ceux qui décrochent en premier.`}
      </p>

      {filtree.length === 0 ? (
        <p style={{ color: "rgba(255,255,255,0.4)", fontSize: 13 }}>Aucun abonné trouvé.</p>
      ) : null}

      {/* V339 : zone DÉFILANTE à hauteur limitée — avec 38 abonnés la page devenait
          interminable et le reste du dashboard inatteignable. */}
      <div style={{ display: "flex", flexDirection: "column", gap: 8,
                    maxHeight: "60vh", overflowY: "auto", paddingRight: 4 }}
           data-testid="suivi-liste-defilante">
        {filtree.map((s) => {
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
                {s.decrochage > 0.3 ? (
                  <span style={{
                    flexShrink: 0, padding: "2px 8px", borderRadius: 999, fontSize: 10,
                    fontWeight: 700, background: "rgba(245,158,11,0.15)", color: "#f59e0b",
                    border: "1px solid rgba(245,158,11,0.35)",
                  }} title={`Passé de ${s.regularite_par_semaine}/sem à ${s.regularite_recente}/sem`}>
                    décroche
                  </span>
                ) : null}
                <button
                  type="button"
                  onClick={() => {
                    const suivant = deplie ? null : s.code;
                    setOuvert(suivant); setRetour(null);
                    if (suivant) ouvrirDetail(suivant);
                  }}
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
                <span>30 derniers jours <b style={{ color: s.decrochage > 0.3 ? "#f59e0b" : "#fff" }}>
                  {s.seances_30j ?? 0} séance{(s.seances_30j ?? 0) > 1 ? "s" : ""}
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
                <div style={{ marginTop: 10 }}>
                  {/* V339 : MÊME formulaire et MÊMES résultats que dans le cockpit
                      de l'abonné — un seul composant, donc aucun écart possible. */}
                  <FormulaireMesure
                    code={s.code}
                    tailleCm={(detail[s.code] || {}).taille_cm}
                    onEnregistre={async () => {
                      setDetail((prev) => { const c = { ...prev }; delete c[s.code]; return c; });
                      await ouvrirDetail(s.code);
                      await charger();
                    }}
                  />
                  <ResultatsCalcules calculs={(detail[s.code] || {}).calculs} />
                  <DetailAbonne
                    code={s.code}
                    seances={(detail[s.code] || {}).seances}
                    peutEcrire={true}
                  />
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
