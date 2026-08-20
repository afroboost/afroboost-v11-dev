// V223: Écran de complément de profil, affiché une seule fois à l'ouverture
// de l'espace abonné. Isolé dans son propre fichier : SubscriberSpace.js fait
// 57 Ko et sert tous les abonnés payants actuels.
import React, { useState } from "react";
import axios from "axios";

// V223: COLORS n'est pas exporté par SubscriberSpace.js — on réplique
// localement les mêmes valeurs plutôt que de dupliquer un import impossible.
const COLORS = {
  bg: "#0A0A0F",
  primary: "var(--primary-color, #D91CD2)",
  panel: "rgba(255,255,255,0.04)",
  border: "rgba(255,255,255,0.08)",
};

// V223: même construction que SubscriberSpace.js — jamais d'URL en dur.
const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "";
const API = `${BACKEND_URL}/api`;

export default function SubscriberOnboarding({ code, subscription, onDone }) {
  const [name, setName] = useState(subscription?.name || "");
  const [whatsapp, setWhatsapp] = useState(subscription?.whatsapp || "");
  // V333 : objectifs, pré-remplis s'ils ont déjà été saisis (le backend les renvoie
  // dans `subscriber.objectifs`) — on ne redemande jamais une information acquise.
  const [objectifs, setObjectifs] = useState(subscription?.objectifs || "");
  // V333 : inscription WhatsApp (V332) proposée ici, numéro déjà saisi juste au-dessus.
  // La case est OBLIGATOIRE pour s'inscrire — c'est la preuve de consentement RGPD.
  const [optinWa, setOptinWa] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const TEXTE_CONSENT_WA = "J'accepte de recevoir les actualités Afroboost sur WhatsApp.";

  const submit = async () => {
    if (!name.trim()) {
      setError("Merci d'indiquer ton nom.");
      return;
    }
    setSaving(true);
    setError("");
    try {
      await axios.put(`${API}/subscriptions/${code}/profile`, {
        name: name.trim(),
        whatsapp: whatsapp.trim(),
        objectifs: objectifs.trim(),
        // LOT 3c-0b : l'abonné présente le code qu'il a déjà dans son URL.
        // La route exige désormais une identité (garde `_v334_autoriser`) :
        // sans ce `code`, l'abonné ne pourrait plus remplir SON profil — il n'a
        // pas de jeton d'appareil, SubscriberSpace n'en demande jamais. Le code
        // n'est PAS lu depuis l'URL côté serveur : ce serait accepter n'importe
        // quel appelant comme étant l'abonné, et le cloisonnement inter-coach
        // ne vaudrait plus rien. Même motif que V446 sur `/auto-renew`.
        code,
      });

      // V333 : inscription aux actualités WhatsApp, seulement si la case est cochée
      // ET qu'un numéro est renseigné. Volontairement NON bloquante : un échec ici
      // ne doit pas empêcher l'accès à des crédits déjà payés (règle V223).
      if (optinWa && whatsapp.trim()) {
        try {
          await axios.post(`${API}/subscribers/optin`, {
            channel: "whatsapp",
            phone: whatsapp.trim(),
            name: name.trim(),
            consent: true,
            consent_text: TEXTE_CONSENT_WA,
            source: "onboarding_email",
          });
        } catch (e) {
          /* inscription facultative : on continue sans bloquer le parcours */
        }
      }

      onDone();
    } catch (e) {
      // V223: un échec réseau ne doit jamais bloquer l'accès à des crédits déjà payés.
      setError("Enregistrement impossible. Tu peux continuer et réessayer plus tard.");
      setSaving(false);
    }
  };

  return (
    <div
      style={{
        minHeight: "100vh",
        background: COLORS.bg,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 20,
      }}
    >
      <div
        style={{
          maxWidth: 420,
          width: "100%",
          background: COLORS.panel,
          border: `1px solid ${COLORS.border}`,
          borderRadius: 16,
          padding: 28,
        }}
      >
        <h2 style={{ color: "#fff", fontSize: 22, margin: "0 0 8px", textAlign: "center" }}>
          Bienvenue chez Afroboost ! 🎉
        </h2>
        <p style={{ color: "rgba(255,255,255,0.6)", fontSize: 14, textAlign: "center", margin: "0 0 24px" }}>
          Complète ton profil pour réserver tes séances.
        </p>

        <label style={{ color: "rgba(255,255,255,0.7)", fontSize: 12, display: "block", marginBottom: 6 }}>
          Nom complet
        </label>
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          style={{
            width: "100%",
            padding: "12px",
            borderRadius: 10,
            background: COLORS.bg,
            border: `1px solid ${COLORS.border}`,
            color: "#fff",
            marginBottom: 16,
          }}
        />

        <label style={{ color: "rgba(255,255,255,0.7)", fontSize: 12, display: "block", marginBottom: 6 }}>
          WhatsApp
        </label>
        <input
          value={whatsapp}
          onChange={(e) => setWhatsapp(e.target.value)}
          placeholder="+41 76 000 00 00"
          style={{
            width: "100%",
            padding: "12px",
            borderRadius: 10,
            background: COLORS.bg,
            border: `1px solid ${COLORS.border}`,
            color: "#fff",
            marginBottom: 20,
          }}
        />

        {/* V333 : objectifs — facultatif mais mis en avant, saisi une seule fois. */}
        <label style={{ color: "rgba(255,255,255,0.7)", fontSize: 12, display: "block", marginBottom: 6 }}>
          Vos objectifs <span style={{ color: "rgba(255,255,255,0.35)" }}>(facultatif)</span>
        </label>
        <textarea
          value={objectifs}
          onChange={(e) => setObjectifs(e.target.value.slice(0, 300))}
          placeholder="Perdre du poids, prise de masse, souplesse, cardio…"
          rows={2}
          data-testid="onboarding-objectifs"
          style={{
            width: "100%",
            padding: "12px",
            borderRadius: 10,
            background: COLORS.bg,
            border: `1px solid ${COLORS.border}`,
            color: "#fff",
            marginBottom: 6,
            resize: "vertical",
            fontFamily: "inherit",
            fontSize: 14,
            boxSizing: "border-box",
          }}
        />
        <p style={{ color: "rgba(255,255,255,0.3)", fontSize: 11, margin: "0 0 18px", textAlign: "right" }}>
          {objectifs.length}/300
        </p>

        {/* V333 : inscription aux actualités WhatsApp (V332). Le numéro est celui
            saisi ci-dessus — un seul geste suffit. Case obligatoire (RGPD). */}
        {whatsapp.trim() ? (
          <label
            style={{
              display: "flex", alignItems: "flex-start", gap: 8, cursor: "pointer",
              color: "rgba(255,255,255,0.6)", fontSize: 12, lineHeight: 1.4,
              marginBottom: 18, padding: "10px 12px", borderRadius: 10,
              background: "rgba(var(--primary-rgb, 217, 28, 210), 0.06)",
              border: "1px solid rgba(var(--primary-rgb, 217, 28, 210), 0.18)",
            }}
          >
            <input
              type="checkbox"
              checked={optinWa}
              onChange={(e) => setOptinWa(e.target.checked)}
              data-testid="onboarding-optin-wa"
              style={{ marginTop: 2, accentColor: COLORS.primary, flexShrink: 0 }}
            />
            <span>
              Recevoir mes séances sur WhatsApp — {TEXTE_CONSENT_WA}
            </span>
          </label>
        ) : null}

        {error && <p style={{ color: "#ff6b6b", fontSize: 13, marginBottom: 12 }}>{error}</p>}

        <button
          onClick={submit}
          disabled={saving}
          style={{
            width: "100%",
            padding: "14px",
            borderRadius: 10,
            background: COLORS.primary,
            color: "#fff",
            fontWeight: "bold",
            border: "none",
            cursor: "pointer",
            opacity: saving ? 0.6 : 1,
          }}
        >
          {saving ? "Enregistrement…" : "C'est parti →"}
        </button>

        {/* V223: échappatoire obligatoire — sans elle, tout abonné existant sans
            name/whatsapp serait enfermé hors de crédits déjà payés. */}
        <button
          onClick={onDone}
          style={{
            width: "100%",
            marginTop: 12,
            background: "none",
            border: "none",
            color: "rgba(255,255,255,0.4)",
            fontSize: 13,
            cursor: "pointer",
          }}
        >
          Plus tard
        </button>
      </div>
    </div>
  );
}
