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

/**
 * V339 — Résultats calculés : IMC + catégorie, rapport tour de taille/hanches, et
 * progression (depuis la première et la précédente mesure).
 *
 * Les valeurs viennent du SERVEUR (`calculs` du cockpit) : recalculer ici donnerait
 * fatalement des arrondis différents de ceux que voit le coach, ce qui décrédibilise
 * les deux affichages.
 */
export function ResultatsCalcules({ calculs }) {
  if (!calculs) return null;
  const { imc, imc_categorie, rapport_taille_hanches, progression, premiere_mesure } = calculs;
  if (!imc && !rapport_taille_hanches && !progression && !premiere_mesure) return null;

  // Une variation « bonne » ou « mauvaise » dépend de l'objectif de la personne :
  // on ne juge pas, on colore seulement le SENS (baisse / hausse / stable).
  const couleurVariation = (v) =>
    v === 0 ? "rgba(255,255,255,0.55)" : (v < 0 ? "#4ade80" : "#f59e0b");
  const signe = (v) => (v > 0 ? `+${v}` : `${v}`);

  const ligneProgression = (cle, libelle) => {
    const p = progression && progression[cle];
    if (!p) return null;
    return (
      <div key={cle} style={{ fontSize: 12, color: "rgba(255,255,255,0.6)", marginTop: 3 }}>
        <b style={{ color: "#fff" }}>{libelle}</b> : {p.actuel} {p.unite}
        {p.depuis_debut !== undefined ? (
          <> · <span style={{ color: couleurVariation(p.depuis_debut), fontWeight: 700 }}>
            {signe(p.depuis_debut)} {p.unite}
          </span> depuis le début</>
        ) : null}
        {p.depuis_precedente !== undefined ? (
          <> · <span style={{ color: couleurVariation(p.depuis_precedente), fontWeight: 700 }}>
            {signe(p.depuis_precedente)} {p.unite}
          </span> depuis la dernière fois</>
        ) : null}
      </div>
    );
  };

  return (
    <div style={{
      marginTop: 10, padding: "10px 12px", borderRadius: 10,
      background: "rgba(255,255,255,0.03)", border: BORDURE,
    }} data-testid="resultats-calcules">
      <div style={{ color: "rgba(255,255,255,0.55)", fontSize: 11.5, marginBottom: 6 }}>
        Résultat
      </div>

      {imc ? (
        <div style={{ fontSize: 12.5, color: "rgba(255,255,255,0.7)" }}>
          <b style={{ color: "#fff" }}>IMC {imc}</b>
          {imc_categorie ? <> — {imc_categorie}</> : null}
          <div style={{ color: "rgba(255,255,255,0.3)", fontSize: 10, marginTop: 2 }}>
            Indicatif — ne remplace pas un avis médical.
          </div>
        </div>
      ) : null}

      {rapport_taille_hanches ? (
        <div style={{ fontSize: 12, color: "rgba(255,255,255,0.6)", marginTop: 6 }}>
          <b style={{ color: "#fff" }}>Rapport taille/hanches</b> : {rapport_taille_hanches}
        </div>
      ) : null}

      {premiere_mesure ? (
        <div style={{ fontSize: 12, color: "rgba(255,255,255,0.45)", marginTop: 6 }}>
          Première mesure enregistrée — la progression s'affichera dès la prochaine.
        </div>
      ) : null}

      {progression ? (
        <div style={{ marginTop: 6 }}>
          {ligneProgression("poids", "Poids")}
          {ligneProgression("tour_taille", "Tour de taille")}
        </div>
      ) : null}
    </div>
  );
}

/**
 * V339 — Formulaire de mesure enrichi, PARTAGÉ entre l'abonné et le coach.
 * Tous les champs sont facultatifs : on saisit ce qu'on a mesuré, rien de plus.
 * La TAILLE (hauteur) est pré-remplie depuis le profil et n'est plus redemandée.
 */
export function FormulaireMesure({ code, codePreuve = "", tailleCm, onEnregistre }) {
  const [v, setV] = useState({
    poids: "", taille: tailleCm ? String(tailleCm) : "",
    tour_taille: "", hanches: "", bras: "", cuisse: "", poitrine: "",
    masse_grasse: "", note: "",
  });
  const [envoi, setEnvoi] = useState(false);
  const [retour, setRetour] = useState(null);

  useEffect(() => {
    if (tailleCm) setV((p) => (p.taille ? p : { ...p, taille: String(tailleCm) }));
  }, [tailleCm]);

  const maj = (cle) => (e) => setV((p) => ({ ...p, [cle]: e.target.value }));

  const enregistrer = async () => {
    if (envoi) return;
    const corps = { subscriber_code: code };
    if (codePreuve) corps.code = codePreuve;
    if (v.poids.trim()) corps.weight_kg = v.poids.trim();
    if (v.taille.trim()) corps.taille_cm = v.taille.trim();
    if (v.masse_grasse.trim()) corps.body_fat_pct = v.masse_grasse.trim();
    if (v.note.trim()) corps.note = v.note.trim();
    const m = {};
    [["tour_taille", v.tour_taille], ["hanches", v.hanches], ["bras", v.bras],
     ["cuisse", v.cuisse], ["poitrine", v.poitrine]].forEach(([k, val]) => {
      if (val && val.trim()) m[k] = val.trim();
    });
    if (Object.keys(m).length) corps.measurements = m;

    if (!corps.weight_kg && !corps.measurements && !corps.body_fat_pct && !corps.note) {
      setRetour({ type: "ko", texte: "Saisissez au moins une valeur." });
      return;
    }
    setEnvoi(true); setRetour(null);
    try {
      await axios.post(`${API}/progress`, corps);
      setV((p) => ({ ...p, poids: "", tour_taille: "", hanches: "", bras: "",
                     cuisse: "", poitrine: "", masse_grasse: "", note: "" }));
      setRetour({ type: "ok", texte: "Mesure enregistrée." });
      if (onEnregistre) await onEnregistre();
    } catch (err) {
      setRetour({ type: "ko",
                  texte: err?.response?.data?.detail || "Enregistrement impossible." });
    } finally { setEnvoi(false); }
  };

  const champStyle = {
    width: "100%", padding: "8px 10px", borderRadius: 8, background: "#0a0a1a",
    border: BORDURE, color: "#fff", fontSize: 13, boxSizing: "border-box", outline: "none",
  };
  const Champ = ({ cle, libelle, unite }) => (
    <label style={{ flex: "1 1 110px", minWidth: 100 }}>
      <span style={{ display: "block", color: "rgba(255,255,255,0.45)",
                     fontSize: 10.5, marginBottom: 3 }}>
        {libelle} {unite ? `(${unite})` : ""}
      </span>
      <input type="number" step="0.1" inputMode="decimal" value={v[cle]}
             onChange={maj(cle)} style={champStyle}
             data-testid={`mesure-${cle}-${code}`} />
    </label>
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}
         data-testid={`formulaire-mesure-${code}`}>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <Champ cle="poids" libelle="Poids" unite="kg" />
        <Champ cle="taille" libelle="Taille" unite="cm" />
        <Champ cle="tour_taille" libelle="Tour de taille" unite="cm" />
      </div>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <Champ cle="hanches" libelle="Hanches" unite="cm" />
        <Champ cle="bras" libelle="Bras" unite="cm" />
        <Champ cle="cuisse" libelle="Cuisse" unite="cm" />
      </div>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <Champ cle="poitrine" libelle="Poitrine" unite="cm" />
        <Champ cle="masse_grasse" libelle="Masse grasse" unite="%" />
        <div style={{ flex: "1 1 110px", minWidth: 100 }} />
      </div>
      <input type="text" value={v.note} onChange={maj("note")}
             placeholder="Note (facultatif)" style={champStyle}
             data-testid={`mesure-note-${code}`} />
      <button type="button" onClick={enregistrer} disabled={envoi}
              data-testid={`mesure-submit-${code}`}
              style={{
                padding: "9px", borderRadius: 999, border: "none", background: PRIMAIRE,
                color: "#fff", fontWeight: 700, fontSize: 12.5,
                cursor: envoi ? "wait" : "pointer", opacity: envoi ? 0.6 : 1,
              }}>
        {envoi ? "Enregistrement…" : "Enregistrer la mesure"}
      </button>
      <p style={{ color: "rgba(255,255,255,0.3)", fontSize: 10.5, margin: 0 }}>
        Tous les champs sont facultatifs. La taille est mémorisée et ne sera plus redemandée.
      </p>
      {retour ? (
        <p style={{ margin: 0, fontSize: 11.5,
                    color: retour.type === "ok" ? "#4ade80" : "#fca5a5" }}>
          {retour.texte}
        </p>
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
