// V184: Page d'accès rapide abonné
// Lien public /espace/AFR-XXXXXX — bienvenue, séances, QR, réservation, guide

import React, { useEffect, useMemo, useState, useCallback } from "react";
import axios from "axios";
import { QRCodeSVG } from "qrcode.react";
import { Dialog, DialogContent, DialogTitle } from "./ui/dialog";
import { copyToClipboard } from "../utils/clipboard";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "";
const API = `${BACKEND_URL}/api`;

const COLORS = {
  bg: "#0A0A0F",
  primary: "#D91CD2",
  secondary: "#FF2DAA",
  panel: "rgba(255,255,255,0.04)",
  border: "rgba(255,255,255,0.08)",
};

const FRENCH_DATE_OPTIONS = {
  weekday: "short",
  day: "numeric",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
};

function formatOccurrence(iso) {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleString("fr-FR", FRENCH_DATE_OPTIONS);
  } catch {
    return iso;
  }
}

export default function SubscriberSpace({ accessCode: propCode }) {
  const accessCode = useMemo(() => {
    if (propCode) return propCode.toUpperCase();
    const match = window.location.pathname.match(/^\/espace\/(.+?)\/?$/);
    return match ? decodeURIComponent(match[1]).toUpperCase() : "";
  }, [propCode]);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [data, setData] = useState(null);
  const [reservingKey, setReservingKey] = useState(null);
  const [confirmedKeys, setConfirmedKeys] = useState({});
  const [qrFullscreen, setQrFullscreen] = useState(false);
  const [actionError, setActionError] = useState("");
  const [shareCopied, setShareCopied] = useState(false);

  const loadSpace = useCallback(async () => {
    if (!accessCode) {
      setError("Code d'accès manquant dans l'URL");
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const res = await axios.get(`${API}/subscriber/space/${encodeURIComponent(accessCode)}`);
      setData(res.data);
    } catch (err) {
      const message = err?.response?.data?.detail || "Impossible de charger ton espace abonné.";
      setError(message);
    } finally {
      setLoading(false);
    }
  }, [accessCode]);

  useEffect(() => {
    loadSpace();
  }, [loadSpace]);

  const handleReserve = async (occurrence) => {
    if (!occurrence?.course_id || reservingKey) return;
    const reservationKey = `${occurrence.course_id}_${occurrence.datetime}`;
    setReservingKey(reservationKey);
    setActionError("");
    try {
      const res = await axios.post(
        `${API}/subscriber/space/${encodeURIComponent(accessCode)}/reserve/${encodeURIComponent(occurrence.course_id)}`,
        { datetime: occurrence.datetime }
      );
      setConfirmedKeys((prev) => ({ ...prev, [reservationKey]: true }));
      if (typeof res.data?.remaining_sessions === "number") {
        setData((prev) =>
          prev
            ? { ...prev, subscription: { ...prev.subscription, remaining_sessions: res.data.remaining_sessions } }
            : prev
        );
      }
    } catch (err) {
      const message = err?.response?.data?.detail || "Réservation impossible. Réessaye dans un instant.";
      setActionError(message);
    } finally {
      setReservingKey(null);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center" style={{ background: COLORS.bg, color: "white" }}>
        <div className="flex flex-col items-center gap-3">
          <div
            className="w-12 h-12 rounded-full border-2 border-t-transparent animate-spin"
            style={{ borderColor: COLORS.primary, borderTopColor: "transparent" }}
          />
          <p className="text-white/70 text-sm">Chargement de ton espace…</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center p-6" style={{ background: COLORS.bg, color: "white" }}>
        <div
          className="max-w-md w-full rounded-2xl p-6 text-center"
          style={{ background: COLORS.panel, border: `1px solid ${COLORS.border}` }}
        >
          <div className="text-4xl mb-3">🔒</div>
          <h1 className="text-xl font-semibold mb-2">Accès indisponible</h1>
          <p className="text-white/70 text-sm">{error}</p>
          <p className="text-white/40 text-xs mt-4">Vérifie le lien avec ton coach.</p>
        </div>
      </div>
    );
  }

  const subscription = data?.subscription || {};
  const subscriber = data?.subscriber || {};
  const coach = data?.coach;
  const courses = data?.upcoming_courses || [];

  const total = subscription.total_sessions || 0;
  const remaining = subscription.remaining_sessions || 0;
  const used = subscription.used_sessions || (total ? total - remaining : 0);
  const percentUsed = total > 0 ? Math.max(0, Math.min(100, Math.round((used / total) * 100))) : 0;

  const firstName = (subscriber.name || "").split(" ")[0] || "Abonné";
  const shareUrl = typeof window !== "undefined"
    ? `${window.location.origin}/espace/${subscriber.code || accessCode}`
    : "";

  const handleShareCopy = async () => {
    if (!shareUrl) return;
    const r = await copyToClipboard(shareUrl);
    if (r.success) {
      setShareCopied(true);
      setTimeout(() => setShareCopied(false), 2000);
    }
  };

  return (
    <div className="min-h-screen pb-16" style={{ background: COLORS.bg, color: "white" }}>
      <div className="max-w-md mx-auto px-4 pt-6 space-y-5">
        {/* ===== Welcome ===== */}
        <header className="flex items-center gap-3" data-testid="subscriber-space-header">
          {coach?.logo_url ? (
            <img
              src={coach.logo_url}
              alt={coach?.name || "Coach"}
              className="w-12 h-12 rounded-full object-cover"
              style={{ border: `2px solid ${COLORS.primary}` }}
            />
          ) : (
            <div
              className="w-12 h-12 rounded-full flex items-center justify-center text-lg font-bold"
              style={{ background: `linear-gradient(135deg, ${COLORS.primary}, #8b5cf6)` }}
            >
              {firstName.charAt(0).toUpperCase()}
            </div>
          )}
          <div className="flex-1 min-w-0">
            <h1 className="text-xl font-semibold leading-tight truncate">Bienvenue {firstName} !</h1>
            <p className="text-white/50 text-xs truncate">{coach?.name || "Afroboost"}</p>
          </div>
        </header>

        {/* ===== Mes séances restantes ===== */}
        <section
          className="rounded-2xl p-5"
          style={{ background: COLORS.panel, border: `1px solid ${COLORS.border}` }}
          data-testid="subscriber-space-sessions"
        >
          <div className="flex items-baseline justify-between mb-2">
            <div>
              <p className="text-white/60 text-xs uppercase tracking-wider">Séances restantes</p>
              <p className="text-3xl font-bold mt-1" style={{ color: COLORS.primary }}>
                {remaining}
                <span className="text-white/40 text-base font-normal"> / {total || "—"}</span>
              </p>
            </div>
            <span className="text-white/40 text-xs text-right max-w-[40%] truncate">{subscription.offer_name}</span>
          </div>
          <div className="w-full h-2 rounded-full overflow-hidden bg-white/10">
            <div
              className="h-full transition-all"
              style={{
                width: `${100 - percentUsed}%`,
                background: `linear-gradient(90deg, ${COLORS.primary}, ${COLORS.secondary})`,
              }}
            />
          </div>
        </section>

        {/* ===== Mon QR Code ===== */}
        <section
          className="rounded-2xl p-5 flex flex-col items-center"
          style={{ background: COLORS.panel, border: `1px solid ${COLORS.border}` }}
          data-testid="subscriber-space-qr"
        >
          <p className="text-white/60 text-xs uppercase tracking-wider mb-3">Mon QR Code</p>
          <div className="bg-white p-3 rounded-xl">
            <QRCodeSVG value={subscriber.code || accessCode} size={160} level="M" includeMargin={false} />
          </div>
          <p className="text-white/40 text-xs mt-3 font-mono">{subscriber.code || accessCode}</p>
          <button
            type="button"
            onClick={() => setQrFullscreen(true)}
            className="mt-3 px-4 py-2 rounded-full text-sm font-medium"
            style={{ background: COLORS.primary, color: "white" }}
            data-testid="qr-fullscreen-btn"
          >
            🔍 Agrandir
          </button>
        </section>

        {/* ===== Réserver une séance ===== */}
        <section
          className="rounded-2xl p-5"
          style={{ background: COLORS.panel, border: `1px solid ${COLORS.border}` }}
          data-testid="subscriber-space-reservation"
        >
          <h2 className="text-base font-semibold mb-3">Réserver une séance</h2>
          {actionError && (
            <p
              className="text-xs mb-3 px-3 py-2 rounded-lg"
              style={{ background: "rgba(239,68,68,0.15)", color: "#fca5a5" }}
            >
              {actionError}
            </p>
          )}
          {courses.length === 0 ? (
            <p className="text-white/50 text-sm">Aucun cours disponible pour le moment.</p>
          ) : (
            <ul className="space-y-2">
              {courses.slice(0, 12).map((occ) => {
                const key = `${occ.course_id}_${occ.datetime}`;
                const confirmed = confirmedKeys[key];
                const isBusy = reservingKey === key;
                return (
                  <li
                    key={key}
                    className="flex items-center justify-between gap-3 p-3 rounded-xl"
                    style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.06)" }}
                  >
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium truncate">{occ.name || "Cours"}</p>
                      <p className="text-white/50 text-xs">
                        {formatOccurrence(occ.datetime)}
                        {occ.locationName ? ` · ${occ.locationName}` : ""}
                      </p>
                    </div>
                    {confirmed ? (
                      <span
                        className="text-xs px-3 py-1 rounded-full"
                        style={{ background: "rgba(34,197,94,0.15)", color: "#86efac" }}
                      >
                        ✓ Réservé
                      </span>
                    ) : (
                      <button
                        type="button"
                        disabled={isBusy || remaining <= 0}
                        onClick={() => handleReserve(occ)}
                        className="text-xs font-semibold px-3 py-2 rounded-lg disabled:opacity-50"
                        style={{ background: COLORS.primary, color: "white" }}
                        data-testid={`reserve-${occ.course_id}`}
                      >
                        {isBusy ? "…" : "Réserver"}
                      </button>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
          {remaining <= 0 && (
            <p className="text-white/50 text-xs mt-3">
              Tu as utilisé toutes tes séances. Contacte ton coach pour renouveler.
            </p>
          )}
        </section>

        {/* ===== Guide rapide ===== */}
        <section
          className="rounded-2xl p-5"
          style={{ background: COLORS.panel, border: `1px solid ${COLORS.border}` }}
          data-testid="subscriber-space-guide"
        >
          <h2 className="text-base font-semibold mb-3">Guide rapide</h2>
          <ol className="space-y-2 text-sm text-white/80">
            <li className="flex gap-3">
              <span
                className="flex-shrink-0 w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold"
                style={{ background: COLORS.primary }}
              >
                1
              </span>
              <span>Choisis ton cours dans la liste</span>
            </li>
            <li className="flex gap-3">
              <span
                className="flex-shrink-0 w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold"
                style={{ background: COLORS.primary }}
              >
                2
              </span>
              <span>Réserve d'un tap</span>
            </li>
            <li className="flex gap-3">
              <span
                className="flex-shrink-0 w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold"
                style={{ background: COLORS.primary }}
              >
                3
              </span>
              <span>Scanne ton QR à l'entrée du cours</span>
            </li>
          </ol>
          {shareUrl && (
            <button
              type="button"
              onClick={handleShareCopy}
              className="mt-4 text-xs text-white/40 underline"
              data-testid="copy-own-link"
            >
              {shareCopied ? "✓ Lien copié" : "Copier mon lien personnel"}
            </button>
          )}
        </section>
      </div>

      {/* ===== QR Fullscreen Dialog ===== */}
      <Dialog open={qrFullscreen} onOpenChange={setQrFullscreen}>
        <DialogContent className="max-w-sm bg-white">
          <DialogTitle className="text-center text-black text-base font-semibold">QR Code abonné</DialogTitle>
          <div className="flex flex-col items-center gap-3 py-4">
            <QRCodeSVG value={subscriber.code || accessCode} size={280} level="H" includeMargin={false} />
            <p className="text-black font-mono text-sm">{subscriber.code || accessCode}</p>
            <p className="text-black/60 text-xs">Présente ce code au coach à l'entrée</p>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
