/**
 * MessagesWhatsApp — V411
 * « WhatsApp » du dashboard coach : les conversations reçues sur le numéro
 * WhatsApp Business d'Afroboost, en LECTURE SEULE.
 *
 * D'OÙ VIENNENT CES DONNÉES
 * -------------------------
 * Le webhook Meta (`POST /api/webhook/whatsapp-meta`) range chaque échange via
 * `_save_whatsapp_conversation` : un fil par numéro dans `private_conversations`
 * (identifiant `whatsapp_<numéro>`, en face de `admin_afroboost`), et chaque
 * message dans `private_messages`. Ces données existaient depuis longtemps —
 * simplement, AUCUN écran ne les montrait. Cet écran ne fait que les afficher :
 * il ne crée rien, ne modifie rien, n'envoie aucun WhatsApp.
 *
 * DEUX LIMITES À CONNAÎTRE, VOLONTAIREMENT AFFICHÉES À L'UTILISATEUR
 * -----------------------------------------------------------------
 * 1. « Envoyé » = la réponse AUTOMATIQUE (IA ou menu du bot), pas un message
 *    tapé à la main : rien dans le produit ne permet d'écrire depuis ici.
 * 2. Les envois de CAMPAGNES n'apparaissent pas dans ces fils — ils sont rangés
 *    ailleurs (`chat_messages`). Ne pas le dire laisserait croire à un historique
 *    complet alors qu'il ne l'est pas.
 *
 * ACCÈS : les routes `/api/private/*` exigent depuis V411 un JWT super-admin
 * signé. Un 403 ici ne veut pas dire « panne » mais « session non signée » —
 * d'où le message explicite plutôt qu'une liste vide (leçon V345).
 */
import { useState, useEffect, useCallback } from "react";
import axios from "axios";

const API = `${process.env.REACT_APP_BACKEND_URL || ''}/api`;

const PRIMAIRE = "var(--primary-color, #D91CD2)";
const BORDURE = "1px solid rgba(255,255,255,0.08)";

/** Identifiant de la boîte du coach côté serveur (cf. `_save_whatsapp_conversation`). */
const BOITE_COACH = "admin_afroboost";

/** Le serveur préfixe le nom d'un emoji téléphone. On l'enlève : le projet impose
 *  des icônes SVG, et l'emoji stocké n'est qu'un artefact d'affichage. */
const nomPropre = (nom, repli) =>
  ((nom || "").replace(/^\s*[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]\s*/u, "").trim()) || repli || "—";

const dateHeure = (iso) => {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("fr-FR", {
      day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit",
    });
  } catch (e) { return "—"; }
};

const dateCourte = (iso) => {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleDateString("fr-FR", { day: "2-digit", month: "short" });
  } catch (e) { return "—"; }
};

/** Un message vient-il d'Afroboost (réponse automatique) ou du membre ? */
const estEnvoye = (msg) => String(msg?.sender_id || "").startsWith("admin");

function IconeTelephone({ size = 14 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
         strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6
               19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.13.96.36 1.9.7 2.81a2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.9.34 1.85.57 2.81.7A2 2 0 0 1 22 16.92z" />
    </svg>
  );
}

function IconePoubelle({ size = 14 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
         strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="3 6 5 6 21 6" />
      <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
      <line x1="10" y1="11" x2="10" y2="17" />
      <line x1="14" y1="11" x2="14" y2="17" />
    </svg>
  );
}

function Chevron({ ouvert }) {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
         strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
         style={{ transform: ouvert ? "rotate(180deg)" : "none", transition: "transform .2s" }}>
      <polyline points="6 9 12 15 18 9" />
    </svg>
  );
}

export default function MessagesWhatsApp() {
  const [fils, setFils] = useState(null);      // null = chargement
  const [messages, setMessages] = useState({}); // { conversation_id: [msg, ...] }
  const [erreur, setErreur] = useState("");
  const [refus, setRefus] = useState(false);    // 403 = session non signée
  const [ouvert, setOuvert] = useState(null);
  const [suppression, setSuppression] = useState(null); // id du fil en cours de suppression

  // V441 — non lus. { conversation_id: nombre }. Vient du SERVEUR, jamais du
  // navigateur : un rafraîchissement ou un autre appareil retrouve le même état.
  const [nonLus, setNonLus] = useState({});

  // V434 — réponse manuelle. `brouillons` est indexé par fil : passer d'une
  // conversation à l'autre ne fait pas perdre ce qu'on était en train d'écrire.
  const [brouillons, setBrouillons] = useState({});   // { conversation_id: texte }
  const [occupe, setOccupe] = useState({});           // { conversation_id: "proposer"|"ameliorer"|"envoi" }
  const [avis, setAvis] = useState({});               // { conversation_id: {type, texte} }

  // V435 — modèles approuvés (recontact hors de la fenêtre de 24 h).
  const [modeles, setModeles] = useState(null);       // null = pas encore chargés
  const [erreurModeles, setErreurModeles] = useState("");
  const [panneau, setPanneau] = useState({});         // { conversation_id: bool }
  const [choix, setChoix] = useState({});             // { conversation_id: "nom|langue" }
  const [varsModele, setVarsModele] = useState({});   // { conversation_id: [texte, …] }
  const [simulation, setSimulation] = useState({});   // { conversation_id: objet }

  /** V433 : au-delà de ce nombre de fils, la liste défile au lieu de pousser la
   *  page. En dessous, on ne met AUCUNE contrainte de hauteur : encadrer trois
   *  conversations dans une zone qui défile ferait un cadre vide et inutile. */
  const SEUIL_DEFILEMENT = 6;

  /** V441 : relit les compteurs de non lus. NE MARQUE RIEN — c'est une simple
   *  lecture, appelable en boucle sans jamais consommer un non lu. */
  const chargerNonLus = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/private/nonlus`);
      setNonLus((prev) => {
        const suivant = (r.data && r.data.nonlus) || {};
        // Règle « jamais de boucle d'appels API » : si rien n'a changé, on rend
        // l'objet PRÉCÉDENT, sinon chaque sondage relancerait tous les effets.
        const memeTaille = Object.keys(prev).length === Object.keys(suivant).length;
        if (memeTaille && Object.keys(suivant).every((k) => prev[k] === suivant[k])) return prev;
        return suivant;
      });
    } catch (e) {
      // Un compteur indisponible ne doit JAMAIS casser la liste (leçon V345).
    }
  }, []);

  const charger = useCallback(async () => {
    setErreur(""); setRefus(false); setFils(null);
    try {
      const r = await axios.get(`${API}/private/conversations/${BOITE_COACH}`);
      const liste = Array.isArray(r.data) ? r.data.slice() : [];
      liste.sort((a, b) => String(b.last_message_at || "").localeCompare(String(a.last_message_at || "")));
      setFils(liste);

      // Le nombre de messages n'est pas porté par le fil : on le tire des messages
      // eux-mêmes. On ne le fait QUE sur un nombre raisonnable de fils — au-delà,
      // ce serait une rafale d'appels au chargement (règle « jamais de boucle
      // d'appels API ») et le compte s'affichera à l'ouverture du fil.
      if (liste.length && liste.length <= 40) {
        const paires = await Promise.all(liste.map(async (f) => {
          try {
            const rm = await axios.get(`${API}/private/messages/${f.id}`);
            return [f.id, Array.isArray(rm.data) ? rm.data : []];
          } catch (e) { return [f.id, null]; }
        }));
        const parFil = {};
        paires.forEach(([id, m]) => { if (m) parFil[id] = m; });
        setMessages(parFil);
      }
    } catch (e) {
      const code = e?.response?.status;
      if (code === 401 || code === 403) {
        setRefus(true);
      } else {
        setErreur(`Chargement impossible (HTTP ${code || "réseau"}).`);
      }
      setFils([]);
    }
  }, []);

  useEffect(() => { charger(); }, [charger]);

  /** V441 : sondage doux (5 s) des seuls compteurs — pas des messages. Le fil
   *  ouvert n'est pas rechargé : ouvrir une conversation ne doit pas dépendre du
   *  rythme du sondage, et relire les messages en boucle saturerait le serveur. */
  useEffect(() => {
    chargerNonLus();
    const t = setInterval(chargerNonLus, 5000);
    return () => clearInterval(t);
  }, [chargerNonLus]);

  /** Ouvre un fil ; charge ses messages s'ils ne sont pas déjà là. */
  const basculer = async (fil) => {
    if (ouvert === fil.id) { setOuvert(null); return; }
    setOuvert(fil.id);

    // V441 — LU ≠ REÇU. C'est le SEUL endroit du produit qui marque un fil lu, et
    // il n'est atteint que par un clic sur cette conversation. Ni le chargement de
    // la liste, ni le sondage, ni l'ouverture de l'onglet n'écrivent quoi que ce
    // soit. On vide le compteur localement tout de suite (l'écran répond au clic)
    // et le serveur, lui, fait foi au sondage suivant.
    if (nonLus[fil.id]) {
      setNonLus((prev) => { const c = { ...prev }; delete c[fil.id]; return c; });
    }
    axios.post(`${API}/private/lecture`, { conversation_id: fil.id })
      .then(() => chargerNonLus())
      .catch(() => { /* le compteur reviendra au sondage suivant : rien de perdu */ });

    if (messages[fil.id]) return;
    try {
      const rm = await axios.get(`${API}/private/messages/${fil.id}`);
      setMessages((prev) => ({ ...prev, [fil.id]: Array.isArray(rm.data) ? rm.data : [] }));
    } catch (e) {
      setMessages((prev) => ({ ...prev, [fil.id]: [] }));
    }
  };

  /** V433 : supprime DÉFINITIVEMENT un fil et ses messages.
   *
   *  La confirmation nomme le contact : « Supprimer définitivement cette
   *  conversation ? » tout court laisse le doute sur LAQUELLE, et cette action
   *  ne se rattrape pas. Le serveur revérifie le jeton super-admin de son côté —
   *  cette garde-ci n'est qu'un confort, jamais une sécurité. */
  const supprimer = async (fil) => {
    const nom = nomPropre(fil.participant_1_name, fil.phone);
    const nb = (messages[fil.id] || []).length;
    const detail = nb ? ` (${nb} message${nb > 1 ? "s" : ""})` : "";
    if (!window.confirm(
      `Supprimer définitivement cette conversation ?\n\n${nom}${detail}\n\n` +
      `Le fil et ses messages seront effacés. Cette action est irréversible.`
    )) return;

    setSuppression(fil.id);
    try {
      await axios.delete(`${API}/private/conversations/${fil.id}`);
      // Retrait local : on évite de recharger toute la liste pour une ligne.
      setFils((prev) => (prev || []).filter((f) => f.id !== fil.id));
      setMessages((prev) => { const c = { ...prev }; delete c[fil.id]; return c; });
      if (ouvert === fil.id) setOuvert(null);
    } catch (e) {
      const code = e?.response?.status;
      setErreur(code === 401 || code === 403
        ? "Suppression refusée : session non signée. Reconnectez-vous."
        : `Suppression impossible (HTTP ${code || "réseau"}).`);
    } finally {
      setSuppression(null);
    }
  };

  /** V434 : demande un brouillon à l'assistant. N'ENVOIE RIEN — le texte
   *  atterrit dans le champ de saisie, où il reste modifiable. */
  const assister = async (fil, mode) => {
    setOccupe((p) => ({ ...p, [fil.id]: mode }));
    setAvis((p) => ({ ...p, [fil.id]: null }));
    try {
      const r = await axios.post(`${API}/private/whatsapp/brouillon`, {
        conversation_id: fil.id,
        mode,
        brouillon: brouillons[fil.id] || "",
      });
      if (r.data?.success && r.data?.texte) {
        setBrouillons((p) => ({ ...p, [fil.id]: r.data.texte }));
        setAvis((p) => ({ ...p, [fil.id]: { type: "info",
          texte: "Brouillon proposé — relis-le et modifie-le avant d'envoyer." } }));
      } else {
        setAvis((p) => ({ ...p, [fil.id]: { type: "erreur",
          texte: r.data?.erreur || "L'assistant n'a rien renvoyé." } }));
      }
    } catch (e) {
      const code = e?.response?.status;
      setAvis((p) => ({ ...p, [fil.id]: { type: "erreur",
        texte: code === 401 || code === 403
          ? "Session non signée. Reconnecte-toi."
          : `Assistant indisponible (HTTP ${code || "réseau"}).` } }));
    } finally {
      setOccupe((p) => ({ ...p, [fil.id]: null }));
    }
  };

  /** V434 : envoie le message. SEUL endroit du composant qui écrit au client,
   *  et il n'est atteint que par un clic sur « Envoyer » suivi d'une
   *  confirmation. L'assistant ne peut pas l'appeler. */
  const envoyer = async (fil) => {
    const texte = (brouillons[fil.id] || "").trim();
    if (!texte) return;
    const nom = nomPropre(fil.participant_1_name, fil.phone);
    if (!window.confirm(
      `Envoyer ce message sur WhatsApp à ${nom} (${fil.phone || "—"}) ?\n\n` +
      `${texte.slice(0, 400)}${texte.length > 400 ? "…" : ""}`
    )) return;

    setOccupe((p) => ({ ...p, [fil.id]: "envoi" }));
    setAvis((p) => ({ ...p, [fil.id]: null }));
    try {
      const r = await axios.post(`${API}/private/whatsapp/envoyer`, {
        conversation_id: fil.id, texte,
      });
      if (r.data?.success) {
        setBrouillons((p) => ({ ...p, [fil.id]: "" }));
        setAvis((p) => ({ ...p, [fil.id]: { type: "ok", texte: "Message envoyé." } }));
        // Affichage immédiat, sans recharger tout le fil.
        setMessages((p) => ({ ...p, [fil.id]: [...(p[fil.id] || []), {
          id: `local-${Date.now()}`, sender_id: "admin_afroboost",
          content: texte, created_at: r.data.envoye_le, manuel: true,
        }] }));
      } else {
        setAvis((p) => ({ ...p, [fil.id]: { type: "erreur",
          texte: r.data?.erreur || "WhatsApp a refusé le message." } }));
      }
    } catch (e) {
      const code = e?.response?.status;
      setAvis((p) => ({ ...p, [fil.id]: { type: "erreur",
        texte: code === 401 || code === 403
          ? "Session non signée. Reconnecte-toi."
          : e?.response?.data?.detail || `Envoi impossible (HTTP ${code || "réseau"}).` } }));
    } finally {
      setOccupe((p) => ({ ...p, [fil.id]: null }));
    }
  };

  /** V435 : le texte tel que le client le lira — calculé côté navigateur, à
   *  l'identique du serveur, pour que la relecture soit immédiate. */
  const apercuModele = (m, vars) => {
    let t = (m && m.corps) || "";
    (vars || []).forEach((v, i) => { t = t.split(`{{${i + 1}}}`).join(v || `{{${i + 1}}}`); });
    return t;
  };

  const modeleDe = (fil) => {
    const cle = choix[fil.id];
    if (!cle || !modeles) return null;
    return modeles.find((m) => `${m.nom}|${m.langue}` === cle) || null;
  };

  /** Ouvre le panneau et charge la liste des modèles (une seule fois). */
  const ouvrirModeles = async (fil) => {
    setPanneau((p) => ({ ...p, [fil.id]: !p[fil.id] }));
    if (modeles || panneau[fil.id]) return;
    setErreurModeles("");
    try {
      const r = await axios.get(`${API}/private/whatsapp/modeles`);
      if (r.data?.success) setModeles(r.data.modeles || []);
      else setErreurModeles(r.data?.erreur || "Liste indisponible.");
    } catch (e) {
      const code = e?.response?.status;
      setErreurModeles(code === 401 || code === 403
        ? "Session non signée. Reconnecte-toi."
        : `Liste indisponible (HTTP ${code || "réseau"}).`);
    }
  };

  /** `simuler = true` -> montre l'appel construit, n'envoie RIEN. */
  const envoyerModele = async (fil, simuler) => {
    const m = modeleDe(fil);
    if (!m) return;
    const vars = (varsModele[fil.id] || []).slice(0, m.variables);

    if (!simuler) {
      if (!window.confirm(
        `Envoyer le modèle « ${m.nom} » sur WhatsApp à ` +
        `${nomPropre(fil.participant_1_name, fil.phone)} (${fil.phone || "—"}) ?\n\n` +
        `${apercuModele(m, vars)}\n\nCe message part immédiatement.`
      )) return;
    }

    setOccupe((p) => ({ ...p, [fil.id]: simuler ? "simulation" : "modele" }));
    setAvis((p) => ({ ...p, [fil.id]: null }));
    try {
      const r = await axios.post(`${API}/private/whatsapp/modele/envoyer`, {
        conversation_id: fil.id, modele: m.nom, langue: m.langue,
        variables: vars, simulation: simuler,
      });
      if (simuler) {
        setSimulation((p) => ({ ...p, [fil.id]: r.data }));
        setAvis((p) => ({ ...p, [fil.id]: { type: "info",
          texte: "Simulation : aucun appel n'a été envoyé à WhatsApp." } }));
      } else if (r.data?.success) {
        setSimulation((p) => ({ ...p, [fil.id]: null }));
        setAvis((p) => ({ ...p, [fil.id]: { type: "ok",
          texte: r.data.avertissement || "Modèle envoyé." } }));
        setMessages((p) => ({ ...p, [fil.id]: [...(p[fil.id] || []), {
          id: `local-${Date.now()}`, sender_id: "admin_afroboost",
          content: r.data.apercu, created_at: new Date().toISOString(), manuel: true,
        }] }));
      } else {
        setAvis((p) => ({ ...p, [fil.id]: { type: "erreur",
          texte: r.data?.erreur || "WhatsApp a refusé le modèle." } }));
      }
    } catch (e) {
      const code = e?.response?.status;
      setAvis((p) => ({ ...p, [fil.id]: { type: "erreur",
        texte: e?.response?.data?.detail || `Échec (HTTP ${code || "réseau"}).` } }));
    } finally {
      setOccupe((p) => ({ ...p, [fil.id]: null }));
    }
  };

  if (refus) {
    return (
      <div style={{ padding: 16, borderRadius: 10, border: BORDURE, background: "rgba(255,255,255,0.03)" }}>
        <div style={{ color: PRIMAIRE, fontWeight: 700, marginBottom: 6, fontSize: 14 }}>
          Session non signée
        </div>
        <div style={{ color: "rgba(255,255,255,0.7)", fontSize: 13, lineHeight: 1.5 }}>
          Ces conversations contiennent les numéros et les messages de vos membres :
          elles exigent une session signée. Déconnectez-vous puis reconnectez-vous
          pour obtenir un jeton, et revenez sur cet onglet.
        </div>
      </div>
    );
  }

  if (fils === null) {
    return <div style={{ color: "rgba(255,255,255,0.6)", fontSize: 13, padding: 12 }}>Chargement…</div>;
  }

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
        <div style={{ color: "#fff", fontWeight: 700, fontSize: 15 }}>
          Conversations WhatsApp
          <span style={{ color: "rgba(255,255,255,0.5)", fontWeight: 500, fontSize: 12, marginLeft: 8 }}>
            {fils.length} fil{fils.length > 1 ? "s" : ""}
          </span>
        </div>
        <button
          onClick={charger}
          style={{
            padding: "6px 12px", borderRadius: 8, cursor: "pointer",
            background: "rgba(255,255,255,0.06)", border: BORDURE,
            color: "rgba(255,255,255,0.75)", fontSize: 12,
          }}
        >
          Actualiser
        </button>
      </div>

      <div style={{
        marginBottom: 12, padding: "8px 10px", borderRadius: 8,
        border: BORDURE, background: "rgba(255,255,255,0.03)",
        color: "rgba(255,255,255,0.55)", fontSize: 11, lineHeight: 1.5,
      }}>
        « Envoyé » désigne soit la réponse automatique (IA ou menu du bot), soit un
        message que vous avez écrit ici. Les envois de campagnes n'apparaissent pas
        dans ces fils. Aucun message ne part sans votre clic sur « Envoyer ».
      </div>

      {erreur && (
        <div style={{ color: "#ff8080", fontSize: 12, marginBottom: 10 }}>{erreur}</div>
      )}

      {fils.length === 0 && !erreur && (
        <div style={{ color: "rgba(255,255,255,0.5)", fontSize: 13, padding: 12 }}>
          Aucune conversation WhatsApp pour le moment.
        </div>
      )}

      <div style={fils.length > SEUIL_DEFILEMENT
        ? { maxHeight: "60vh", overflowY: "auto", overflowX: "hidden", paddingRight: 4 }
        : undefined}>
      {/* V441 : les fils NON LUS remontent en tête (le plus récent d'abord), puis
          les autres par date. Le tri se fait à l'affichage, sur une COPIE : l'ordre
          reçu du serveur n'est pas altéré, et un fil qu'on vient de lire ne saute
          pas sous le curseur — il reprend simplement sa place au rendu suivant. */}
      {fils.slice().sort((a, b) => {
        const na = nonLus[a.id] ? 1 : 0;
        const nb = nonLus[b.id] ? 1 : 0;
        if (na !== nb) return nb - na;
        return String(b.last_message_at || "").localeCompare(String(a.last_message_at || ""));
      }).map((fil) => {
        const msgs = messages[fil.id];
        const nom = nomPropre(fil.participant_1_name, fil.phone);
        const estOuvert = ouvert === fil.id;
        const enCours = suppression === fil.id;
        const nbNonLus = nonLus[fil.id] || 0;
        return (
          <div key={fil.id} style={{
            border: estOuvert ? `1px solid ${PRIMAIRE}`
                  : (nbNonLus ? `1px solid rgba(var(--primary-rgb, 217, 28, 210), 0.55)` : BORDURE),
            borderRadius: 10, marginBottom: 8, overflow: "hidden",
            // V441 : un fond légèrement teinté de la couleur du coach — l'accent ne
            // repose pas QUE sur la pastille, pour rester lisible en un coup d'œil.
            background: nbNonLus ? "rgba(var(--primary-rgb, 217, 28, 210), 0.10)"
                                 : "rgba(255,255,255,0.03)",
          }}>
            {/* V433 : le bouton « supprimer » est un FRÈRE du bouton d'ouverture,
                jamais un enfant — un <button> dans un <button> est du HTML
                invalide, et le clic y devient imprévisible selon le navigateur. */}
            <div style={{ display: "flex", alignItems: "center" }}>
            <button
              onClick={() => basculer(fil)}
              style={{
                flex: 1, minWidth: 0, display: "flex", alignItems: "center", gap: 10,
                padding: "10px 12px", background: "transparent", border: "none",
                cursor: "pointer", textAlign: "left",
              }}
            >
              <span style={{ color: PRIMAIRE, display: "inline-flex", flexShrink: 0 }}>
                <IconeTelephone size={16} />
              </span>
              <span style={{ flex: 1, minWidth: 0 }}>
                <span style={{
                  display: "block", color: "#fff", fontSize: 13,
                  fontWeight: nbNonLus ? 800 : 600,
                  overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                }}>{nom}</span>
                <span style={{
                  display: "block", fontSize: 11,
                  color: nbNonLus ? "rgba(255,255,255,0.85)" : "rgba(255,255,255,0.5)",
                  fontWeight: nbNonLus ? 700 : 400,
                }}>
                  {fil.phone || "—"}
                  {msgs ? ` · ${msgs.length} message${msgs.length > 1 ? "s" : ""}` : ""}
                </span>
              </span>
              {/* V441 : compteur PAR conversation — « 3 » se lit d'un coup d'œil
                  là où une simple pastille ne dirait pas combien. */}
              {nbNonLus > 0 && (
                <span
                  data-testid={`nonlus-${fil.id}`}
                  aria-label={`${nbNonLus} message${nbNonLus > 1 ? "s" : ""} non lu${nbNonLus > 1 ? "s" : ""}`}
                  style={{
                    flexShrink: 0, minWidth: 20, height: 20, padding: "0 6px",
                    borderRadius: 10, background: PRIMAIRE, color: "#fff",
                    fontSize: 11, fontWeight: 800, lineHeight: "20px", textAlign: "center",
                  }}
                >{nbNonLus > 99 ? "99+" : nbNonLus}</span>
              )}
              <span style={{ color: "rgba(255,255,255,0.5)", fontSize: 11, flexShrink: 0 }}>
                {dateCourte(fil.last_message_at)}
              </span>
              <span style={{ color: "rgba(255,255,255,0.5)", display: "inline-flex", flexShrink: 0 }}>
                <Chevron ouvert={estOuvert} />
              </span>
            </button>

            <button
              onClick={() => supprimer(fil)}
              disabled={enCours}
              title="Supprimer cette conversation"
              aria-label={`Supprimer la conversation avec ${nom}`}
              data-testid={`supprimer-fil-${fil.id}`}
              style={{
                display: "inline-flex", alignItems: "center", justifyContent: "center",
                width: 34, height: 34, marginRight: 8, flexShrink: 0,
                borderRadius: 8, border: BORDURE, background: "rgba(255,255,255,0.04)",
                color: enCours ? "rgba(255,255,255,0.35)" : "rgba(255,128,128,0.85)",
                cursor: enCours ? "default" : "pointer",
              }}
            >
              <IconePoubelle size={14} />
            </button>
            </div>

            {estOuvert && (
              <div style={{ padding: "4px 12px 12px", borderTop: BORDURE }}>
                {!msgs && (
                  <div style={{ color: "rgba(255,255,255,0.5)", fontSize: 12, padding: 8 }}>Chargement…</div>
                )}
                {msgs && msgs.length === 0 && (
                  <div style={{ color: "rgba(255,255,255,0.5)", fontSize: 12, padding: 8 }}>
                    Aucun message dans ce fil.
                  </div>
                )}
                {msgs && msgs.map((m) => {
                  const sortant = estEnvoye(m);
                  return (
                    <div key={m.id} style={{
                      display: "flex",
                      justifyContent: sortant ? "flex-end" : "flex-start",
                      marginTop: 8,
                    }}>
                      <div style={{
                        maxWidth: "82%",
                        padding: "7px 10px",
                        borderRadius: 10,
                        border: BORDURE,
                        background: sortant
                          ? "rgba(var(--primary-rgb, 217, 28, 210), 0.14)"
                          : "rgba(255,255,255,0.05)",
                      }}>
                        <div style={{
                          color: sortant ? PRIMAIRE : "rgba(255,255,255,0.55)",
                          fontSize: 10, fontWeight: 700, marginBottom: 3,
                          textTransform: "uppercase", letterSpacing: ".04em",
                        }}>
                          {sortant ? (m.manuel ? "Envoyé par vous" : "Envoyé (auto)") : "Reçu"}
                          {" · "}{dateHeure(m.created_at)}
                        </div>
                        <div style={{
                          color: "rgba(255,255,255,0.9)", fontSize: 13,
                          lineHeight: 1.45, whiteSpace: "pre-wrap", wordBreak: "break-word",
                        }}>
                          {m.content || ""}
                        </div>
                      </div>
                    </div>
                  );
                })}

                {/* V434 — RÉPONDRE SOI-MÊME.
                    Le texte de l'assistant atterrit dans CE champ : il reste
                    modifiable, et rien ne part tant que « Envoyer » n'est pas
                    cliqué puis confirmé. */}
                <div style={{ marginTop: 12, paddingTop: 10, borderTop: BORDURE }}>
                  <div style={{ display: "flex", gap: 6, marginBottom: 6, flexWrap: "wrap" }}>
                    <button
                      onClick={() => assister(fil, "proposer")}
                      disabled={!!occupe[fil.id]}
                      data-testid={`ia-proposer-${fil.id}`}
                      style={{
                        padding: "5px 10px", borderRadius: 8, fontSize: 11.5,
                        border: `1px solid ${PRIMAIRE}`, background: "rgba(var(--primary-rgb, 217, 28, 210), 0.12)",
                        color: PRIMAIRE, cursor: occupe[fil.id] ? "default" : "pointer",
                        opacity: occupe[fil.id] ? 0.5 : 1,
                      }}
                    >
                      {occupe[fil.id] === "proposer" ? "Rédaction…" : "Proposer une réponse"}
                    </button>
                    <button
                      onClick={() => assister(fil, "ameliorer")}
                      disabled={!!occupe[fil.id] || !(brouillons[fil.id] || "").trim()}
                      title={!(brouillons[fil.id] || "").trim()
                        ? "Écris d'abord un brouillon" : "Reformuler et corriger"}
                      data-testid={`ia-ameliorer-${fil.id}`}
                      style={{
                        padding: "5px 10px", borderRadius: 8, fontSize: 11.5,
                        border: BORDURE, background: "rgba(255,255,255,0.05)",
                        color: "rgba(255,255,255,0.75)",
                        cursor: (occupe[fil.id] || !(brouillons[fil.id] || "").trim())
                          ? "default" : "pointer",
                        opacity: (occupe[fil.id] || !(brouillons[fil.id] || "").trim()) ? 0.45 : 1,
                      }}
                    >
                      {occupe[fil.id] === "ameliorer" ? "Correction…" : "Améliorer"}
                    </button>
                  </div>

                  <textarea
                    value={brouillons[fil.id] || ""}
                    onChange={(e) => setBrouillons((p) => ({ ...p, [fil.id]: e.target.value }))}
                    placeholder="Écris ta réponse, ou demande une proposition à l'assistant…"
                    rows={4}
                    data-testid={`saisie-${fil.id}`}
                    style={{
                      width: "100%", padding: "8px 10px", borderRadius: 8,
                      border: BORDURE, background: "rgba(0,0,0,0.25)",
                      color: "rgba(255,255,255,0.92)", fontSize: 13, lineHeight: 1.45,
                      resize: "vertical", fontFamily: "inherit",
                    }}
                  />

                  <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 6 }}>
                    <button
                      onClick={() => envoyer(fil)}
                      disabled={!!occupe[fil.id] || !(brouillons[fil.id] || "").trim()}
                      data-testid={`envoyer-${fil.id}`}
                      style={{
                        padding: "7px 16px", borderRadius: 8, fontSize: 12.5, fontWeight: 700,
                        border: "none", color: "#fff",
                        background: (occupe[fil.id] || !(brouillons[fil.id] || "").trim())
                          ? "rgba(255,255,255,0.12)"
                          : "linear-gradient(135deg, var(--primary-color, #D91CD2), rgba(139,92,246,0.9))",
                        cursor: (occupe[fil.id] || !(brouillons[fil.id] || "").trim())
                          ? "default" : "pointer",
                      }}
                    >
                      {occupe[fil.id] === "envoi" ? "Envoi…" : "Envoyer"}
                    </button>
                    <span style={{ color: "rgba(255,255,255,0.4)", fontSize: 11 }}>
                      {(brouillons[fil.id] || "").length}/4096
                    </span>
                    {avis[fil.id] && (
                      <span style={{
                        fontSize: 11.5, flex: 1,
                        color: avis[fil.id].type === "erreur" ? "#ff8080"
                             : avis[fil.id].type === "ok" ? "#7ee08a"
                             : "rgba(255,255,255,0.6)",
                      }}>
                        {avis[fil.id].texte}
                      </span>
                    )}
                  </div>

                  {/* V435 — MODÈLE APPROUVÉ.
                      Nécessaire dès que le client n'a plus écrit depuis 24 h :
                      Meta refuse alors tout texte libre. */}
                  <div style={{ marginTop: 10, paddingTop: 8, borderTop: BORDURE }}>
                    <button
                      onClick={() => ouvrirModeles(fil)}
                      data-testid={`ouvrir-modeles-${fil.id}`}
                      style={{
                        padding: "5px 10px", borderRadius: 8, fontSize: 11.5,
                        border: BORDURE, background: "rgba(255,255,255,0.05)",
                        color: "rgba(255,255,255,0.75)", cursor: "pointer",
                      }}
                    >
                      {panneau[fil.id] ? "Masquer les modèles" : "Envoyer le modèle"}
                    </button>

                    {panneau[fil.id] && (
                      <div style={{ marginTop: 8 }}>
                        <div style={{ color: "rgba(255,255,255,0.5)", fontSize: 11,
                                      lineHeight: 1.5, marginBottom: 6 }}>
                          À utiliser quand le client n'a pas écrit depuis plus de 24 h :
                          WhatsApp n'accepte alors qu'un modèle approuvé à l'avance.
                        </div>

                        {erreurModeles && (
                          <div style={{ color: "#ff8080", fontSize: 11.5 }}>{erreurModeles}</div>
                        )}
                        {!modeles && !erreurModeles && (
                          <div style={{ color: "rgba(255,255,255,0.5)", fontSize: 12 }}>Chargement…</div>
                        )}

                        {modeles && (
                          <>
                            <select
                              value={choix[fil.id] || ""}
                              onChange={(e) => {
                                setChoix((p) => ({ ...p, [fil.id]: e.target.value }));
                                setSimulation((p) => ({ ...p, [fil.id]: null }));
                                // Premier champ pré-rempli avec le prénom : c'est
                                // la variable attendue dans presque tous les cas.
                                setVarsModele((p) => ({ ...p,
                                  [fil.id]: [nomPropre(fil.participant_1_name, "").split(" ")[0] || ""] }));
                              }}
                              data-testid={`choix-modele-${fil.id}`}
                              style={{
                                width: "100%", padding: "7px 9px", borderRadius: 8,
                                border: BORDURE, background: "rgba(0,0,0,0.3)",
                                color: "rgba(255,255,255,0.9)", fontSize: 12.5,
                              }}
                            >
                              <option value="">— choisir un modèle —</option>
                              {modeles.map((m) => (
                                <option key={`${m.nom}|${m.langue}`} value={`${m.nom}|${m.langue}`}
                                        disabled={m.statut !== "APPROVED"}>
                                  {m.nom} ({m.langue}) — {m.statut === "APPROVED"
                                    ? `${m.variables} variable(s)` : m.statut}
                                </option>
                              ))}
                            </select>

                            {modeleDe(fil) && (
                              <div style={{ marginTop: 8 }}>
                                {Array.from({ length: modeleDe(fil).variables }).map((_, i) => (
                                  <input
                                    key={i}
                                    value={(varsModele[fil.id] || [])[i] || ""}
                                    onChange={(e) => setVarsModele((p) => {
                                      const v = [...(p[fil.id] || [])];
                                      v[i] = e.target.value;
                                      return { ...p, [fil.id]: v };
                                    })}
                                    placeholder={i === 0 ? "Variable 1 (prénom)" : `Variable ${i + 1}`}
                                    data-testid={`var-${i}-${fil.id}`}
                                    style={{
                                      width: "100%", padding: "6px 9px", marginBottom: 6,
                                      borderRadius: 8, border: BORDURE,
                                      background: "rgba(0,0,0,0.25)",
                                      color: "rgba(255,255,255,0.9)", fontSize: 12.5,
                                    }}
                                  />
                                ))}

                                <div style={{
                                  padding: "8px 10px", borderRadius: 8, border: BORDURE,
                                  background: "rgba(var(--primary-rgb, 217, 28, 210), 0.07)",
                                  color: "rgba(255,255,255,0.85)", fontSize: 12.5,
                                  whiteSpace: "pre-wrap", lineHeight: 1.45,
                                }}>
                                  {apercuModele(modeleDe(fil), varsModele[fil.id])}
                                  {(modeleDe(fil).boutons || []).map((b, i) => (
                                    <div key={i} style={{
                                      marginTop: 6, paddingTop: 6, borderTop: BORDURE,
                                      color: PRIMAIRE, fontSize: 12, fontWeight: 600,
                                    }}>
                                      [ {b.texte} ] {b.url ? `→ ${b.url}` : ""}
                                    </div>
                                  ))}
                                </div>

                                <div style={{ display: "flex", gap: 6, marginTop: 8, flexWrap: "wrap" }}>
                                  <button
                                    onClick={() => envoyerModele(fil, true)}
                                    disabled={!!occupe[fil.id]}
                                    data-testid={`simuler-${fil.id}`}
                                    style={{
                                      padding: "6px 12px", borderRadius: 8, fontSize: 12,
                                      border: BORDURE, background: "rgba(255,255,255,0.05)",
                                      color: "rgba(255,255,255,0.75)", cursor: "pointer",
                                    }}
                                  >
                                    {occupe[fil.id] === "simulation" ? "…" : "Voir l'appel (sans envoyer)"}
                                  </button>
                                  <button
                                    onClick={() => envoyerModele(fil, false)}
                                    disabled={!!occupe[fil.id]}
                                    data-testid={`envoyer-modele-${fil.id}`}
                                    style={{
                                      padding: "6px 14px", borderRadius: 8, fontSize: 12, fontWeight: 700,
                                      border: "none", color: "#fff",
                                      background: occupe[fil.id] ? "rgba(255,255,255,0.12)"
                                        : "linear-gradient(135deg, var(--primary-color, #D91CD2), rgba(139,92,246,0.9))",
                                      cursor: occupe[fil.id] ? "default" : "pointer",
                                    }}
                                  >
                                    {occupe[fil.id] === "modele" ? "Envoi…" : "Envoyer le modèle"}
                                  </button>
                                </div>

                                {simulation[fil.id] && (
                                  <pre style={{
                                    marginTop: 8, padding: 8, borderRadius: 8, border: BORDURE,
                                    background: "rgba(0,0,0,0.35)", color: "rgba(255,255,255,0.7)",
                                    fontSize: 10.5, overflowX: "auto", maxHeight: 220,
                                  }}>
{JSON.stringify(simulation[fil.id], null, 2)}
                                  </pre>
                                )}
                              </div>
                            )}
                          </>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )}
          </div>
        );
      })}
      </div>
    </div>
  );
}
