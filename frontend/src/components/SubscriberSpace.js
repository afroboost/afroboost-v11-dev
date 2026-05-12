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
  // V185 F3: État pour l'annulation de réservation
  const [cancellingId, setCancellingId] = useState(null);
  // V186 F2: Compteurs par occurrence (multi-personnes)
  const [quantities, setQuantities] = useState({});
  // V187: Prénoms des accompagnants par occurrence (array de strings)
  const [guestNames, setGuestNames] = useState({});

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
    const qty = Math.max(1, Number(quantities[reservationKey]) || 1);
    // V187: prénoms des accompagnants (place 1 = abonné, donc on envoie qty - 1 prénoms)
    const rawGuests = guestNames[reservationKey] || [];
    const guests = rawGuests
      .slice(0, Math.max(0, qty - 1))
      .map((g) => (g || "").trim())
      .filter(Boolean);
    setReservingKey(reservationKey);
    setActionError("");
    try {
      const res = await axios.post(
        `${API}/subscriber/space/${encodeURIComponent(accessCode)}/reserve/${encodeURIComponent(occurrence.course_id)}`,
        { datetime: occurrence.datetime, quantity: qty, guests }
      );
      setConfirmedKeys((prev) => ({ ...prev, [reservationKey]: true }));
      // V186/V187: reset compteur + guests après réservation
      setQuantities((prev) => ({ ...prev, [reservationKey]: 1 }));
      setGuestNames((prev) => ({ ...prev, [reservationKey]: [] }));
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

  // V186 F2: helpers compteur
  const getQty = (key) => Math.max(1, Number(quantities[key]) || 1);
  const adjustQty = (key, delta, max) => {
    setQuantities((prev) => {
      const current = Math.max(1, Number(prev[key]) || 1);
      const next = Math.min(Math.max(1, current + delta), Math.max(1, max));
      return { ...prev, [key]: next };
    });
    // V187: tronquer la liste des prénoms si la quantité diminue
    if (delta < 0) {
      setGuestNames((prev) => {
        const cur = prev[key] || [];
        const targetGuests = Math.max(0, Math.max(1, (Number(quantities[key]) || 1) + delta) - 1);
        return { ...prev, [key]: cur.slice(0, targetGuests) };
      });
    }
  };

  // V187: éditer le prénom d'un guest à l'index donné (0-based dans la liste des accompagnants)
  const setGuestName = (key, index, value) => {
    setGuestNames((prev) => {
      const cur = [...(prev[key] || [])];
      while (cur.length <= index) cur.push("");
      cur[index] = value.slice(0, 50);
      return { ...prev, [key]: cur };
    });
  };

  // V185 F3: Annuler une réservation (avec confirmation et règle des 2h)
  const handleCancelReservation = async (reservation) => {
    if (!reservation?.id || cancellingId) return;
    const confirmed = typeof window !== "undefined"
      ? window.confirm("Êtes-vous sûr de vouloir annuler cette séance ?")
      : true;
    if (!confirmed) return;

    setCancellingId(reservation.id);
    setActionError("");
    try {
      const res = await axios.delete(
        `${API}/subscriber/space/${encodeURIComponent(accessCode)}/cancel/${encodeURIComponent(reservation.id)}`
      );
      setData((prev) => {
        if (!prev) return prev;
        const filteredReservations = (prev.reservations || []).filter((r) => r.id !== reservation.id);
        const nextSubscription = typeof res.data?.remaining_sessions === "number"
          ? { ...prev.subscription, remaining_sessions: res.data.remaining_sessions }
          : prev.subscription;
        return { ...prev, reservations: filteredReservations, subscription: nextSubscription };
      });
    } catch (err) {
      const message = err?.response?.data?.detail || "Annulation impossible. Réessaye dans un instant.";
      setActionError(message);
    } finally {
      setCancellingId(null);
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

  // V185 F3: Réservations futures, triées par date croissante
  const now = Date.now();
  const upcomingReservations = (data?.reservations || [])
    .filter((r) => r?.datetime && new Date(r.datetime).getTime() > now)
    .sort((a, b) => new Date(a.datetime).getTime() - new Date(b.datetime).getTime());

  // V185 F4: Réservation active (pour le badge casque global)
  const activeHeadphone = (data?.reservations || []).find(
    (r) => r?.headphone_status === "taken" || r?.headphone_status === "returned"
  );

  const total = subscription.total_sessions || 0;
  const remaining = subscription.remaining_sessions || 0;
  const used = subscription.used_sessions || (total ? total - remaining : 0);
  const percentUsed = total > 0 ? Math.max(0, Math.min(100, Math.round((used / total) * 100))) : 0;
  const noSessions = remaining <= 0;

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

        {/* ===== V185 F4: Badge casque (Silent Disco) ===== */}
        {activeHeadphone && (
          <div
            className="rounded-2xl px-4 py-3 flex items-center gap-3 text-sm font-medium"
            style={{
              background: activeHeadphone.headphone_status === "taken"
                ? "rgba(239,68,68,0.15)"
                : "rgba(34,197,94,0.15)",
              border: `1px solid ${activeHeadphone.headphone_status === "taken" ? "rgba(239,68,68,0.35)" : "rgba(34,197,94,0.35)"}`,
              color: activeHeadphone.headphone_status === "taken" ? "#fca5a5" : "#86efac",
            }}
            data-testid="headphone-badge"
          >
            <span style={{ fontSize: "20px" }}>🎧</span>
            <span>
              {activeHeadphone.headphone_status === "taken"
                ? "Casque en votre possession"
                : "Casque retourné ✓"}
            </span>
          </div>
        )}

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

        {/* ===== V185 F3: Mes prochaines séances (avec annulation) ===== */}
        {upcomingReservations.length > 0 && (
          <section
            className="rounded-2xl p-5"
            style={{ background: COLORS.panel, border: `1px solid ${COLORS.border}` }}
            data-testid="subscriber-space-upcoming"
          >
            <h2 className="text-base font-semibold mb-3">Mes prochaines séances</h2>
            <ul className="space-y-2">
              {upcomingReservations.map((r) => {
                const occurrenceTs = new Date(r.datetime).getTime();
                const hoursAway = (occurrenceTs - now) / 3_600_000;
                const tooLate = hoursAway < 2;
                const isBusy = cancellingId === r.id;
                const hp = r.headphone_status;
                return (
                  <li
                    key={r.id}
                    className="flex items-center justify-between gap-3 p-3 rounded-xl"
                    style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.06)" }}
                  >
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium truncate">
                        {r.courseName || "Séance"}
                        {r.quantity > 1 && (
                          <span className="ml-2 text-xs font-normal" style={{ color: COLORS.primary }}>
                            × {r.quantity} places
                          </span>
                        )}
                      </p>
                      <p className="text-white/50 text-xs">{formatOccurrence(r.datetime)}</p>
                      {/* V187: Liste des prénoms avec pastille casque par personne (lecture seule) */}
                      {(() => {
                        const subscriberName = (r.userName || subscriber.name || "").split(" ")[0] || "Moi";
                        const guests = Array.isArray(r.guests) ? r.guests : [];
                        const guestHp = Array.isArray(r.guest_headphones) ? r.guest_headphones : [];
                        const people = [
                          { name: subscriberName, hp: r.headphone_status || null },
                          ...guests.map((g, i) => ({ name: g, hp: guestHp[i] || null })),
                        ];
                        // Tronque à r.quantity au cas où
                        const totalPlaces = Math.max(1, Number(r.quantity) || 1);
                        const display = people.slice(0, totalPlaces);
                        const HP_STYLE = {
                          taken: "#ef4444",      // rouge
                          returned: "#22c55e",   // vert
                        };
                        return (
                          <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-white/70">
                            {display.map((p, idx) => (
                              <span key={idx} className="inline-flex items-center gap-1">
                                <span style={{ color: HP_STYLE[p.hp] || "rgba(255,255,255,0.3)" }} title={p.hp || "pas de casque"}>🎧</span>
                                <span>{p.name || `Invité ${idx + 1}`}</span>
                              </span>
                            ))}
                          </div>
                        );
                      })()}
                    </div>
                    <button
                      type="button"
                      disabled={tooLate || isBusy}
                      onClick={() => handleCancelReservation(r)}
                      className="text-xs font-semibold px-3 py-2 rounded-lg disabled:opacity-40"
                      title={tooLate ? "Annulation impossible moins de 2h avant" : "Annuler la séance"}
                      style={{
                        background: tooLate ? "rgba(255,255,255,0.06)" : "rgba(239,68,68,0.18)",
                        color: tooLate ? "rgba(255,255,255,0.4)" : "#fca5a5",
                        cursor: tooLate ? "not-allowed" : "pointer",
                      }}
                      data-testid={`cancel-reservation-${r.id}`}
                    >
                      {isBusy ? "…" : "Annuler"}
                    </button>
                  </li>
                );
              })}
            </ul>
          </section>
        )}

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
          {noSessions && (
            <p
              className="text-xs mb-3 px-3 py-2 rounded-lg"
              style={{ background: "rgba(245,158,11,0.15)", color: "#fbbf24" }}
            >
              Plus de séances disponibles
            </p>
          )}
          {courses.length === 0 ? (
            <p className="text-white/50 text-sm">Aucun cours disponible pour le moment.</p>
          ) : (
            <ul className="space-y-3">
              {courses.slice(0, 12).map((occ) => {
                const key = `${occ.course_id}_${occ.datetime}`;
                const confirmed = confirmedKeys[key];
                const isBusy = reservingKey === key;
                const qty = getQty(key);
                const maxQty = Math.max(1, remaining); // ne dépasse pas le solde
                const dec = () => adjustQty(key, -1, maxQty);
                const inc = () => adjustQty(key, +1, maxQty);
                return (
                  <li
                    key={key}
                    className="p-3 rounded-xl"
                    style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.06)" }}
                  >
                    <div className="min-w-0 mb-2">
                      <p className="text-sm font-medium truncate">{occ.name || "Cours"}</p>
                      <p className="text-white/50 text-xs">
                        {formatOccurrence(occ.datetime)}
                        {occ.locationName ? ` · ${occ.locationName}` : ""}
                      </p>
                    </div>
                    {confirmed ? (
                      <span
                        className="text-xs px-3 py-1 rounded-full inline-block"
                        style={{ background: "rgba(34,197,94,0.15)", color: "#86efac" }}
                      >
                        ✓ Réservé
                      </span>
                    ) : (
                      <>
                        <div className="flex items-center justify-between gap-2 flex-wrap">
                          {/* V186 F2: Compteur de places */}
                          <div className="flex items-center gap-2" data-testid={`qty-${occ.course_id}`}>
                            <button
                              type="button"
                              onClick={dec}
                              disabled={qty <= 1 || isBusy || noSessions}
                              aria-label="Diminuer"
                              className="w-8 h-8 rounded-full text-sm font-bold disabled:opacity-30"
                              style={{ background: "rgba(255,255,255,0.08)", color: "white", border: "1px solid rgba(255,255,255,0.12)" }}
                            >
                              −
                            </button>
                            <span className="text-sm font-semibold w-6 text-center">{qty}</span>
                            <button
                              type="button"
                              onClick={inc}
                              disabled={qty >= maxQty || isBusy || noSessions}
                              aria-label="Augmenter"
                              className="w-8 h-8 rounded-full text-sm font-bold disabled:opacity-30"
                              style={{ background: "rgba(255,255,255,0.08)", color: "white", border: "1px solid rgba(255,255,255,0.12)" }}
                            >
                              +
                            </button>
                          </div>
                          <button
                            type="button"
                            disabled={isBusy || noSessions}
                            onClick={() => handleReserve(occ)}
                            className="text-xs font-semibold px-3 py-2 rounded-lg disabled:opacity-50"
                            style={{ background: COLORS.primary, color: "white" }}
                            data-testid={`reserve-${occ.course_id}`}
                          >
                            {isBusy ? "…" : qty > 1 ? `Réserver ${qty} places` : "Réserver"}
                          </button>
                        </div>

                        {/* V187: liste des places + saisie des prénoms accompagnants */}
                        {qty > 1 && (
                          <ol className="mt-3 space-y-1 text-xs text-white/70">
                            <li className="flex items-center gap-2">
                              <span className="w-4 text-white/40">1.</span>
                              <span className="flex-1">{firstName} <span className="text-white/40">(moi)</span></span>
                            </li>
                            {Array.from({ length: qty - 1 }).map((_, i) => (
                              <li key={i} className="flex items-center gap-2">
                                <span className="w-4 text-white/40">{i + 2}.</span>
                                <input
                                  type="text"
                                  value={(guestNames[key] || [])[i] || ""}
                                  onChange={(e) => setGuestName(key, i, e.target.value)}
                                  placeholder="Prénom"
                                  maxLength={50}
                                  data-testid={`guest-input-${occ.course_id}-${i}`}
                                  className="flex-1 px-2 py-1 rounded text-xs"
                                  style={{
                                    background: "rgba(255,255,255,0.05)",
                                    border: "1px solid rgba(255,255,255,0.12)",
                                    color: "white",
                                  }}
                                />
                              </li>
                            ))}
                          </ol>
                        )}
                      </>
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

        {/* ===== V186 F3: Footer — Renouveler abonnement ===== */}
        <section className="pt-2" data-testid="subscriber-space-footer">
          {(() => {
            const coachSlug = coach?.id || coach?.email || "";
            const renewUrl = coachSlug ? `/coach/${encodeURIComponent(coachSlug)}` : "/";
            const isEmpty = remaining <= 0;
            return (
              <a
                href={renewUrl}
                data-testid="renew-subscription-btn"
                className={`block text-center font-semibold rounded-2xl transition-transform active:scale-95 ${isEmpty ? "py-4 text-base" : "py-3 text-sm"}`}
                style={{
                  background: isEmpty
                    ? `linear-gradient(135deg, ${COLORS.primary}, ${COLORS.secondary})`
                    : "rgba(217,28,210,0.18)",
                  color: isEmpty ? "white" : "#F0A8EE",
                  border: isEmpty ? "none" : `1px solid ${COLORS.primary}55`,
                  boxShadow: isEmpty ? "0 6px 20px rgba(217,28,210,0.35)" : "none",
                }}
              >
                🔄 Renouveler mon abonnement
              </a>
            );
          })()}
        </section>

        {/* ===== V187: Conditions d'utilisation = lien vers la page CGU ===== */}
        <div className="text-center pt-2 pb-1">
          <a
            href="/conditions"
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs underline"
            style={{ color: "rgba(255,255,255,0.5)" }}
            data-testid="subscriber-space-terms-link"
          >
            📋 Conditions d'utilisation
          </a>
        </div>
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
