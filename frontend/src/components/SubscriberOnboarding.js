// V223: Écran de complément de profil, affiché une seule fois à l'ouverture
// de l'espace abonné. Isolé dans son propre fichier : SubscriberSpace.js fait
// 57 Ko et sert tous les abonnés payants actuels.
import React, { useState } from "react";
import axios from "axios";

// V223: COLORS n'est pas exporté par SubscriberSpace.js — on réplique
// localement les mêmes valeurs plutôt que de dupliquer un import impossible.
const COLORS = {
  bg: "#0A0A0F",
  primary: "#D91CD2",
  panel: "rgba(255,255,255,0.04)",
  border: "rgba(255,255,255,0.08)",
};

// V223: même construction que SubscriberSpace.js — jamais d'URL en dur.
const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "";
const API = `${BACKEND_URL}/api`;

export default function SubscriberOnboarding({ code, subscription, onDone }) {
  const [name, setName] = useState(subscription?.name || "");
  const [whatsapp, setWhatsapp] = useState(subscription?.whatsapp || "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

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
      });
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
