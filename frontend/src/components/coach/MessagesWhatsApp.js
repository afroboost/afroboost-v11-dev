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

  /** Ouvre un fil ; charge ses messages s'ils ne sont pas déjà là. */
  const basculer = async (fil) => {
    if (ouvert === fil.id) { setOuvert(null); return; }
    setOuvert(fil.id);
    if (messages[fil.id]) return;
    try {
      const rm = await axios.get(`${API}/private/messages/${fil.id}`);
      setMessages((prev) => ({ ...prev, [fil.id]: Array.isArray(rm.data) ? rm.data : [] }));
    } catch (e) {
      setMessages((prev) => ({ ...prev, [fil.id]: [] }));
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
        Lecture seule. « Envoyé » désigne la réponse automatique (IA ou menu du bot) —
        les envois de campagnes n'apparaissent pas ici.
      </div>

      {erreur && (
        <div style={{ color: "#ff8080", fontSize: 12, marginBottom: 10 }}>{erreur}</div>
      )}

      {fils.length === 0 && !erreur && (
        <div style={{ color: "rgba(255,255,255,0.5)", fontSize: 13, padding: 12 }}>
          Aucune conversation WhatsApp pour le moment.
        </div>
      )}

      {fils.map((fil) => {
        const msgs = messages[fil.id];
        const nom = nomPropre(fil.participant_1_name, fil.phone);
        const estOuvert = ouvert === fil.id;
        return (
          <div key={fil.id} style={{
            border: estOuvert ? `1px solid ${PRIMAIRE}` : BORDURE,
            borderRadius: 10, marginBottom: 8, overflow: "hidden",
            background: "rgba(255,255,255,0.03)",
          }}>
            <button
              onClick={() => basculer(fil)}
              style={{
                width: "100%", display: "flex", alignItems: "center", gap: 10,
                padding: "10px 12px", background: "transparent", border: "none",
                cursor: "pointer", textAlign: "left",
              }}
            >
              <span style={{ color: PRIMAIRE, display: "inline-flex", flexShrink: 0 }}>
                <IconeTelephone size={16} />
              </span>
              <span style={{ flex: 1, minWidth: 0 }}>
                <span style={{
                  display: "block", color: "#fff", fontSize: 13, fontWeight: 600,
                  overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                }}>{nom}</span>
                <span style={{ display: "block", color: "rgba(255,255,255,0.5)", fontSize: 11 }}>
                  {fil.phone || "—"}
                  {msgs ? ` · ${msgs.length} message${msgs.length > 1 ? "s" : ""}` : ""}
                </span>
              </span>
              <span style={{ color: "rgba(255,255,255,0.5)", fontSize: 11, flexShrink: 0 }}>
                {dateCourte(fil.last_message_at)}
              </span>
              <span style={{ color: "rgba(255,255,255,0.5)", display: "inline-flex", flexShrink: 0 }}>
                <Chevron ouvert={estOuvert} />
              </span>
            </button>

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
                          {sortant ? "Envoyé" : "Reçu"} · {dateHeure(m.created_at)}
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
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
