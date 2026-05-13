// V184: Page d'accès rapide abonné
// V202: Multi-membres, lien personnel, Stripe, scroll fluide
// Lien public /espace/AFR-XXXXXX — bienvenue, séances, QR, réservation, guide

import React, { useEffect, useMemo, useState, useCallback, useRef } from "react";
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

// V196: Format sans calcul de timezone — utilise directement les champs
// .date (YYYY-MM-DD) + .time ("HH:MM") pour matcher le site principal
// qui affiche l'heure telle quelle (l'heure du cours = heure locale Zurich).
// Compatible avec :
//   - un objet occurrence : { date, time, ... }
//   - une chaîne ISO datetime (réservations existantes)
function formatOccurrence(input) {
  if (!input) return "";
  let dateStr = "";
  let timeStr = "";
  if (typeof input === "object") {
    if (input.date) {
      try {
        // T12:00:00 évite tout décalage de jour selon la timezone du navigateur
        dateStr = new Date(input.date + "T12:00:00").toLocaleDateString("fr-FR", {
          weekday: "short", day: "numeric", month: "short",
        });
      } catch {
        dateStr = input.date;
      }
    }
    timeStr = input.time || "";
  } else {
    try {
      return new Date(input).toLocaleString("fr-FR", FRENCH_DATE_OPTIONS);
    } catch {
      return String(input);
    }
  }
  return [dateStr, timeStr].filter(Boolean).join(", ");
}

export default function SubscriberSpace({ accessCode: propCode }) {
  const accessCode = useMemo(() => {
    if (propCode) return propCode.toUpperCase();
    const match = window.location.pathname.match(/^\/espace\/(.+?)\/?$/);
    return match ? decodeURIComponent(match[1]).toUpperCase() : "";
  }, [propCode]);

  // V202: Lire le slug membre depuis ?m=xxx dans l'URL
  const [memberSlug, setMemberSlug] = useState(() => {
    try {
      const params = new URLSearchParams(window.location.search);
      return params.get("m") || "";
    } catch { return ""; }
  });

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [data, setData] = useState(null);
  const [reservingKey, setReservingKey] = useState(null);
  const [confirmedKeys, setConfirmedKeys] = useState({});
  const [qrFullscreen, setQrFullscreen] = useState(false);
  const [actionError, setActionError] = useState("");
  const [shareCopied, setShareCopied] = useState(false);
  const [cancellingId, setCancellingId] = useState(null);
  const [quantities, setQuantities] = useState({});
  const [autoRenewBusy, setAutoRenewBusy] = useState(false);
  const [guestNames, setGuestNames] = useState({});
  // V203f: Index de la séance affichée (système compact)
  const [selectedCourseIdx, setSelectedCourseIdx] = useState(0);

  // V202: États pour le formulaire d'inscription multi-membre
  const [joinForm, setJoinForm] = useState({ name: "", email: "", whatsapp: "" });
  const [joinLoading, setJoinLoading] = useState(false);
  const [joinError, setJoinError] = useState("");
  const [stripeLoading, setStripeLoading] = useState(false);

  // V202: Ref pour scroll fluide vers la section réservation
  const reserveSectionRef = useRef(null);

  const loadSpace = useCallback(async () => {
    if (!accessCode) {
      setError("Code d'accès manquant dans l'URL");
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      // V202: Passer le slug membre dans la query si disponible
      const url = memberSlug
        ? `${API}/subscriber/space/${encodeURIComponent(accessCode)}?m=${encodeURIComponent(memberSlug)}`
        : `${API}/subscriber/space/${encodeURIComponent(accessCode)}`;
      const res = await axios.get(url);
      setData(res.data);
    } catch (err) {
      const message = err?.response?.data?.detail || "Impossible de charger ton espace abonné.";
      setError(message);
    } finally {
      setLoading(false);
    }
  }, [accessCode, memberSlug]);

  useEffect(() => {
    loadSpace();
  }, [loadSpace]);

  // V210: Réinitialiser confirmedKeys quand on change de membre
  // IMPORTANT: remplacer (pas merger) pour ne pas garder les ✓ d'un autre membre
  useEffect(() => {
    const keys = {};
    const now = Date.now();
    if (data?.reservations?.length) {
      for (const r of data.reservations) {
        if (!r?.courseId || !r?.datetime) continue;
        if (new Date(r.datetime).getTime() > now) {
          keys[`${r.courseId}_${r.datetime}`] = true;
        }
      }
    }
    // Toujours remplacer — si vide, ça remet à zéro (pas de résidus d'un autre membre)
    setConfirmedKeys(keys);
  }, [data]);

  // V202: Rejoindre un code multi-membre
  const handleJoin = async (e) => {
    e.preventDefault();
    if (!joinForm.name.trim()) { setJoinError("Prénom requis"); return; }
    if (!joinForm.email.trim() && !joinForm.whatsapp.trim()) {
      setJoinError("Email ou WhatsApp requis"); return;
    }
    setJoinLoading(true);
    setJoinError("");
    try {
      const res = await axios.post(
        `${API}/subscriber/space/${encodeURIComponent(accessCode)}/join`,
        { name: joinForm.name.trim(), email: joinForm.email.trim(), whatsapp: joinForm.whatsapp.trim() }
      );
      const slug = res.data?.member?.slug;
      if (slug) {
        setMemberSlug(slug);
        // V202: Mettre à jour l'URL sans recharger la page
        const newUrl = `${window.location.pathname}?m=${slug}`;
        window.history.replaceState(null, "", newUrl);
      }
    } catch (err) {
      setJoinError(err?.response?.data?.detail || "Inscription impossible. Réessaye.");
    } finally {
      setJoinLoading(false);
    }
  };

  // V202: Paiement Stripe
  const handleStripeCheckout = async () => {
    if (stripeLoading) return;
    setStripeLoading(true);
    try {
      const res = await axios.post(
        `${API}/subscriber/space/${encodeURIComponent(accessCode)}/stripe-checkout`,
        {
          originUrl: window.location.origin,
          member_slug: memberSlug || "",
          email: data?.subscriber?.email || joinForm.email || "",
        }
      );
      if (res.data?.checkout_url) {
        window.location.href = res.data.checkout_url;
      }
    } catch (err) {
      setActionError(err?.response?.data?.detail || "Erreur paiement. Réessaye.");
    } finally {
      setStripeLoading(false);
    }
  };

  // V202: Scroll fluide vers la section réservation
  const scrollToReservation = () => {
    reserveSectionRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

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
      // V202: Passer le member_slug si identifié
      const res = await axios.post(
        `${API}/subscriber/space/${encodeURIComponent(accessCode)}/reserve/${encodeURIComponent(occurrence.course_id)}`,
        { datetime: occurrence.datetime, quantity: qty, guests, member_slug: memberSlug || undefined }
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

  // V190: Casque en lecture seule côté abonné — seul le coach peut changer le statut
  // depuis ReservationTab.js. Le handler cycleHeadphone (V188) a été retiré ici.

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
      // V208c: Retirer le ✓ de la date annulée
      if (reservation.courseId && reservation.datetime) {
        const cancelKey = `${reservation.courseId}_${reservation.datetime}`;
        setConfirmedKeys((prev) => {
          const next = { ...prev };
          delete next[cancelKey];
          return next;
        });
      }
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

  // V202/V203: Si multi_member ET pas de membre identifié → écran d'inscription
  // data.member est présent quand le backend a trouvé le membre via ?m=slug
  if (data?.multi_member && !data?.member) {
    const mm = data;
    const mmCoach = mm.coach;
    const mmSub = mm.subscription || {};
    const mmMembers = mm.members || [];
    return (
      <div className="min-h-screen pb-16" style={{ background: COLORS.bg, color: "white" }}>
        <div className="max-w-md mx-auto px-4 pt-6 space-y-5">
          {/* Header */}
          <header className="flex items-center gap-3">
            {mmCoach?.logo_url ? (
              <img src={mmCoach.logo_url} alt={mmCoach?.name || "Coach"}
                className="w-12 h-12 rounded-full object-cover"
                style={{ border: `2px solid ${COLORS.primary}` }} />
            ) : (
              <div className="w-12 h-12 rounded-full flex items-center justify-center text-lg font-bold"
                style={{ background: `linear-gradient(135deg, ${COLORS.primary}, #8b5cf6)` }}>
                A
              </div>
            )}
            <div className="flex-1 min-w-0">
              <h1 className="text-xl font-semibold leading-tight">Bienvenue !</h1>
              <p className="text-white/50 text-xs truncate">{mmCoach?.name || "Afroboost"} · {mm.code}</p>
            </div>
          </header>

          {/* V203: Infos code — affichage clair restantes vs utilisées */}
          <section className="rounded-2xl p-5" style={{ background: COLORS.panel, border: `1px solid ${COLORS.border}` }}>
            <p className="text-white/60 text-xs uppercase tracking-wider mb-1">Séances restantes</p>
            <p className="text-lg font-semibold">
              <span style={{ color: COLORS.primary }}>{mmSub.remaining_sessions || 0}</span>
              <span className="text-white/40 text-sm"> / {mmSub.total_sessions || 0}</span>
            </p>
            <p className="text-white/40 text-xs mt-1">
              {(mmSub.total_sessions || 0) - (mmSub.remaining_sessions || 0)} séance(s) utilisée(s)
            </p>
          </section>

          {/* Formulaire d'inscription */}
          <section className="rounded-2xl p-5" style={{ background: COLORS.panel, border: `1px solid ${COLORS.border}` }}>
            <h2 className="text-base font-semibold mb-1">Rejoindre cet abonnement</h2>
            <p className="text-white/50 text-xs mb-4">Entre tes infos pour obtenir ton lien personnel</p>

            {joinError && (
              <p className="text-xs mb-3 px-3 py-2 rounded-lg"
                style={{ background: "rgba(239,68,68,0.15)", color: "#fca5a5" }}>{joinError}</p>
            )}

            <form onSubmit={handleJoin} className="space-y-3" autoComplete="off">
              <div>
                <label className="text-xs text-white/50 block mb-1">Prénom *</label>
                <input type="text" value={joinForm.name}
                  onChange={(e) => setJoinForm(f => ({ ...f, name: e.target.value }))}
                  placeholder="Ton prénom" maxLength={50} required
                  autoComplete="off" name="join-name-field"
                  className="w-full px-3 py-2 rounded-lg text-sm"
                  style={{ background: "rgba(255,255,255,0.06)", border: "1px solid rgba(255,255,255,0.12)", color: "white" }} />
              </div>
              <div>
                <label className="text-xs text-white/50 block mb-1">Email</label>
                <input type="email" value={joinForm.email}
                  onChange={(e) => setJoinForm(f => ({ ...f, email: e.target.value }))}
                  placeholder="ton@email.com" maxLength={100}
                  autoComplete="off" name="join-email-field"
                  className="w-full px-3 py-2 rounded-lg text-sm"
                  style={{ background: "rgba(255,255,255,0.06)", border: "1px solid rgba(255,255,255,0.12)", color: "white" }} />
              </div>
              <div>
                <label className="text-xs text-white/50 block mb-1">WhatsApp</label>
                <input type="tel" value={joinForm.whatsapp}
                  onChange={(e) => setJoinForm(f => ({ ...f, whatsapp: e.target.value }))}
                  placeholder="+41 7X XXX XX XX" maxLength={20}
                  autoComplete="off" name="join-whatsapp-field"
                  className="w-full px-3 py-2 rounded-lg text-sm"
                  style={{ background: "rgba(255,255,255,0.06)", border: "1px solid rgba(255,255,255,0.12)", color: "white" }} />
              </div>
              <button type="submit" disabled={joinLoading}
                className="w-full py-3 rounded-xl text-sm font-semibold transition-transform active:scale-95 disabled:opacity-50"
                style={{ background: `linear-gradient(135deg, ${COLORS.primary}, ${COLORS.secondary})`, color: "white" }}>
                {joinLoading ? "Inscription..." : "Obtenir mon lien personnel"}
              </button>
            </form>
          </section>

          {/* V204: Bouton paiement supprimé ici — seul le bouton Renouveler en bas suffit */}

          {/* V203d: Membres déjà inscrits — accès rapide + copier lien */}
          {mmMembers.length > 0 && (
            <section className="rounded-2xl p-5" style={{ background: COLORS.panel, border: `1px solid ${COLORS.border}` }}>
              <p className="text-white/60 text-xs uppercase tracking-wider mb-3">Déjà inscrit ? Choisis ton profil</p>
              <div className="space-y-2">
                {mmMembers.map((mem) => {
                  const memLink = `${window.location.origin}/espace/${mm.code}?m=${mem.slug}`;
                  return (
                    <div key={mem.slug} className="flex items-center gap-2">
                      <button type="button"
                        onClick={() => {
                          setMemberSlug(mem.slug);
                          window.history.replaceState(null, "", `${window.location.pathname}?m=${mem.slug}`);
                        }}
                        className="flex-1 flex items-center justify-between px-4 py-3 rounded-xl text-sm font-medium transition-transform active:scale-[0.98]"
                        style={{ background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.08)" }}>
                        <span>👤 {mem.name}</span>
                        <span className="text-white/30">→</span>
                      </button>
                      <button type="button" title="Copier le lien personnel"
                        onClick={async (e) => {
                          e.stopPropagation();
                          const r = await copyToClipboard(memLink);
                          if (r.success) {
                            const btn = e.currentTarget;
                            btn.textContent = "✅";
                            setTimeout(() => { btn.textContent = "🔗"; }, 1500);
                          }
                        }}
                        className="shrink-0 w-10 h-10 flex items-center justify-center rounded-xl text-sm transition-colors hover:bg-white/10"
                        style={{ background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.08)" }}>
                        🔗
                      </button>
                    </div>
                  );
                })}
              </div>
            </section>
          )}
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

  // V189: Résumé casque par personne — agrège tous les casques actifs (taken/returned)
  // sur toutes les réservations à venir, et n'affiche le badge global QUE si au moins
  // un casque est encore "taken" (= non rendu).
  const headphoneSummary = (() => {
    const items = [];
    const subscriberName = (subscriber?.name || "").split(" ")[0] || "Moi";
    for (const r of (data?.reservations || [])) {
      if (!r) continue;
      if (r.headphone_status === "taken" || r.headphone_status === "returned") {
        items.push({ name: subscriberName, hp: r.headphone_status });
      }
      const guests = Array.isArray(r.guests) ? r.guests : [];
      const guestHp = Array.isArray(r.guest_headphones) ? r.guest_headphones : [];
      guests.forEach((g, i) => {
        const hp = guestHp[i];
        if (hp === "taken" || hp === "returned") {
          items.push({ name: g || `Invité ${i + 1}`, hp });
        }
      });
    }
    return items;
  })();
  const hasActiveHeadphone = headphoneSummary.some((p) => p.hp === "taken");

  const total = subscription.total_sessions || 0;
  const remaining = subscription.remaining_sessions || 0;
  const used = subscription.used_sessions || (total ? total - remaining : 0);
  const percentUsed = total > 0 ? Math.max(0, Math.min(100, Math.round((used / total) * 100))) : 0;
  const noSessions = remaining <= 0;

  const firstName = (subscriber.name || "").split(" ")[0] || "Abonné";
  // V202: Le lien personnel inclut ?m=slug si c'est un membre
  const shareUrl = typeof window !== "undefined"
    ? memberSlug
      ? `${window.location.origin}/espace/${subscriber.code || accessCode}?m=${memberSlug}`
      : `${window.location.origin}/espace/${subscriber.code || accessCode}`
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
        {/* V203f: Bouton retour vers la page d'inscription multi-membre */}
        {data?.multi_member && memberSlug && (
          <button
            type="button"
            onClick={() => {
              setMemberSlug("");
              window.history.replaceState(null, "", window.location.pathname);
            }}
            className="text-xs text-white/50 hover:text-white transition-colors"
          >
            ← Retour à la page du groupe
          </button>
        )}

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
          {/* V202: Bouton scroll vers réservation — accès rapide */}
          {remaining > 0 && courses.length > 0 && (
            <button type="button" onClick={scrollToReservation}
              className="mt-3 w-full py-2 rounded-xl text-sm font-semibold transition-transform active:scale-95"
              style={{ background: `linear-gradient(135deg, ${COLORS.primary}, ${COLORS.secondary})`, color: "white" }}>
              📅 Réserver une séance
            </button>
          )}
        </section>

        {/* V204: Bouton paiement en haut supprimé — le bouton "Renouveler" en bas suffit */}

        {/* ===== V195: Reconduction automatique ===== */}
        {subscription?.id && (subscription.has_payment_method || subscription.auto_renew) && (
          <section
            className="rounded-2xl p-4"
            style={{ background: COLORS.panel, border: `1px solid ${COLORS.border}` }}
            data-testid="subscriber-space-auto-renew"
          >
            <div className="flex items-center justify-between gap-3">
              <div className="min-w-0">
                <p className="text-white text-sm font-semibold">Reconduction automatique</p>
                <p className="text-white/50 text-xs mt-1">
                  {subscription.auto_renew
                    ? `${(Number(subscription.renewal_price) || 0).toFixed(2)} CHF pour ${subscription.renewal_sessions || 0} séances`
                    : "Désactivée"}
                </p>
              </div>
              <button
                type="button"
                role="switch"
                aria-checked={!!subscription.auto_renew}
                disabled={autoRenewBusy || !subscription.has_payment_method}
                onClick={async () => {
                  if (autoRenewBusy) return;
                  const next = !subscription.auto_renew;
                  setAutoRenewBusy(true);
                  // Mise à jour optimiste
                  setData((prev) => prev ? { ...prev, subscription: { ...prev.subscription, auto_renew: next } } : prev);
                  try {
                    await axios.put(`${API}/subscriptions/${encodeURIComponent(subscription.id)}/auto-renew`, { auto_renew: next });
                  } catch (err) {
                    // Rollback en cas d'erreur
                    setData((prev) => prev ? { ...prev, subscription: { ...prev.subscription, auto_renew: !next } } : prev);
                    const detail = err?.response?.data?.detail || "Modification impossible.";
                    setActionError(detail);
                  } finally {
                    setAutoRenewBusy(false);
                  }
                }}
                title={subscription.has_payment_method
                  ? (subscription.auto_renew ? "Désactiver la reconduction" : "Activer la reconduction")
                  : "Aucune carte enregistrée — souscription manuelle uniquement"}
                className="flex-shrink-0 transition-all"
                style={{
                  width: 52, height: 28, borderRadius: 999, padding: 2, border: "none",
                  background: subscription.auto_renew ? COLORS.primary : "rgba(255,255,255,0.15)",
                  cursor: (autoRenewBusy || !subscription.has_payment_method) ? "not-allowed" : "pointer",
                  opacity: (autoRenewBusy || !subscription.has_payment_method) ? 0.5 : 1,
                  position: "relative",
                }}
              >
                <span
                  style={{
                    display: "block", width: 24, height: 24, borderRadius: 999,
                    background: "white", transition: "transform 0.2s",
                    transform: `translateX(${subscription.auto_renew ? 24 : 0}px)`,
                  }}
                />
              </button>
            </div>
            {subscription.auto_renew && (
              <p className="text-[10px] mt-2" style={{ color: "#fbbf24" }}>
                Le montant sera prélevé automatiquement à la fin de vos séances. Non remboursable.
              </p>
            )}
            {!subscription.has_payment_method && (
              <p className="text-[10px] mt-2 text-white/40">
                Aucune carte enregistrée pour cet abonnement — renouvellement manuel uniquement.
              </p>
            )}
          </section>
        )}

        {/* ===== V189: Badge casque global — résumé par personne ===== */}
        {hasActiveHeadphone && (
          <div
            className="rounded-2xl px-4 py-3"
            style={{
              background: "rgba(239,68,68,0.12)",
              border: "1px solid rgba(239,68,68,0.3)",
            }}
            data-testid="headphone-badge"
          >
            <p className="text-xs text-white/70 mb-1">Casques en cours</p>
            <div className="flex flex-wrap gap-x-3 gap-y-1 text-sm">
              {headphoneSummary.map((p, idx) => (
                <span key={idx} className="inline-flex items-center gap-1">
                  <span style={{ color: p.hp === "taken" ? "#ef4444" : "#22c55e" }}>
                    {p.hp === "taken" ? "🔴" : "🟢"}
                  </span>
                  <span style={{ color: p.hp === "taken" ? "#fca5a5" : "#86efac" }}>
                    {p.name}
                  </span>
                </span>
              ))}
            </div>
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
                      <p className="text-white/50 text-xs">
                        {/* V196: si courseTime est connu (string brute "HH:MM"),
                            on s'en sert pour éviter les décalages timezone des
                            anciennes réservations stockées en UTC. */}
                        {r.courseTime
                          ? formatOccurrence({ date: (r.datetime || "").slice(0, 10), time: r.courseTime })
                          : formatOccurrence(r.datetime)}
                      </p>
                      {/* V188: Liste des prénoms avec pastille casque par personne — CLIQUABLE */}
                      {(() => {
                        const subscriberName = (r.userName || subscriber.name || "").split(" ")[0] || "Moi";
                        const guests = Array.isArray(r.guests) ? r.guests : [];
                        const guestHp = Array.isArray(r.guest_headphones) ? r.guest_headphones : [];
                        // [0] = abonné principal, [1..N] = accompagnants
                        const people = [
                          { name: subscriberName, hp: r.headphone_status || null, guestIndex: null },
                          ...guests.map((g, i) => ({ name: g, hp: guestHp[i] || null, guestIndex: i })),
                        ];
                        const totalPlaces = Math.max(1, Number(r.quantity) || 1);
                        const display = people.slice(0, totalPlaces);
                        const HP_STYLE = { taken: "#ef4444", returned: "#22c55e" };
                        const HP_LABEL = { taken: "Casque pris", returned: "Casque rendu" };
                        return (
                          <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-white/70">
                            {display.map((p, idx) => (
                              <span key={idx} className="inline-flex items-center gap-1">
                                {/* V190: lecture seule — seul le coach peut modifier le statut */}
                                <span
                                  title={`🎧 ${HP_LABEL[p.hp] || "Pas de casque"}`}
                                  data-testid={`subscriber-headphone-${r.id}-${p.guestIndex ?? "main"}`}
                                  style={{ color: HP_STYLE[p.hp] || "rgba(255,255,255,0.3)", lineHeight: 1 }}
                                >
                                  🎧
                                </span>
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

        {/* ===== V203f: Réserver une séance — version compacte avec boutons dates ===== */}
        <section
          ref={reserveSectionRef}
          className="rounded-2xl p-5"
          style={{ background: COLORS.panel, border: `1px solid ${COLORS.border}`, overflow: "hidden" }}
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
          ) : (() => {
            const visibleCourses = courses.slice(0, 12);
            const safeIdx = Math.min(selectedCourseIdx, visibleCourses.length - 1);
            const occ = visibleCourses[safeIdx];
            if (!occ) return null;
            const key = `${occ.course_id}_${occ.datetime}`;
            const confirmed = confirmedKeys[key];
            const isBusy = reservingKey === key;
            const qty = getQty(key);
            const maxQty = Math.max(1, remaining);
            const dec = () => adjustQty(key, -1, maxQty);
            const inc = () => adjustQty(key, +1, maxQty);

            // Formater les boutons de dates
            const formatDateBtn = (o) => {
              try {
                if (o.date) {
                  const d = new Date(o.date + "T12:00:00");
                  const jour = d.toLocaleDateString("fr-FR", { weekday: "short", day: "numeric", month: "short" });
                  return { date: jour, time: o.time || "" };
                }
                const d = new Date(o.datetime || o);
                return {
                  date: d.toLocaleDateString("fr-FR", { weekday: "short", day: "numeric", month: "short" }),
                  time: d.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" }),
                };
              } catch { return { date: "—", time: "" }; }
            };

            return (
              <div>
                {/* Boutons de dates — scrollable horizontalement */}
                <div className="grid pb-3 mb-3" style={{ gridTemplateColumns: `repeat(${Math.min(visibleCourses.length, 4)}, 1fr)`, gap: "8px" }}>
                  {visibleCourses.map((c, i) => {
                    const d = formatDateBtn(c);
                    const isSelected = i === safeIdx;
                    const cKey = `${c.course_id}_${c.datetime}`;
                    const isConfirmed = confirmedKeys[cKey];
                    return (
                      <button key={i} type="button"
                        onClick={() => setSelectedCourseIdx(i)}
                        className="flex flex-col items-center px-2 py-2 rounded-xl text-xs transition-all"
                        style={{
                          background: isConfirmed
                            ? "rgba(34,197,94,0.25)"
                            : isSelected
                              ? `linear-gradient(135deg, ${COLORS.primary}, ${COLORS.secondary})`
                              : "rgba(255,255,255,0.04)",
                          border: isConfirmed
                            ? "2px solid #22c55e"
                            : isSelected ? "none" : "1px solid rgba(255,255,255,0.08)",
                          color: isConfirmed ? "#86efac" : isSelected ? "white" : "rgba(255,255,255,0.6)",
                        }}
                      >
                        <span className="font-semibold" style={{ fontSize: "11px" }}>{d.date}</span>
                        <span style={{ fontSize: "10px", opacity: 0.7 }}>{d.time}</span>
                        {isConfirmed && <span style={{ fontSize: "10px" }}>✓</span>}
                      </button>
                    );
                  })}
                </div>

                {/* Séance sélectionnée */}
                <div
                  className="p-4 rounded-xl"
                  style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.06)" }}
                >
                  <div className="min-w-0 mb-3">
                    <p className="text-sm font-medium">{occ.name || "Cours"}</p>
                    <p className="text-white/50 text-xs">
                      {formatOccurrence(occ)}
                      {occ.locationName ? ` · ${occ.locationName}` : ""}
                    </p>
                  </div>
                  {confirmed ? (() => {
                    // V210: Trouver la réservation correspondante pour pouvoir l'annuler
                    const matchingRes = (data?.reservations || []).find(
                      (r) => r?.courseId === occ.course_id && r?.datetime === occ.datetime
                    );
                    const occTs = new Date(occ.datetime).getTime();
                    const hoursAway = (occTs - Date.now()) / 3_600_000;
                    const tooLate = hoursAway < 2;
                    const isCancelling = matchingRes && cancellingId === matchingRes.id;
                    return (
                      <div className="flex items-center justify-between gap-2">
                        <span
                          className="text-xs px-3 py-1 rounded-full inline-block"
                          style={{ background: "rgba(34,197,94,0.15)", color: "#86efac" }}
                        >
                          ✓ Réservé
                        </span>
                        {matchingRes && (
                          <button type="button"
                            disabled={tooLate || isCancelling}
                            onClick={() => handleCancelReservation(matchingRes)}
                            className="text-xs font-semibold px-3 py-2 rounded-lg disabled:opacity-40"
                            title={tooLate ? "Annulation impossible moins de 2h avant" : "Annuler pour changer de séance"}
                            style={{
                              background: tooLate ? "rgba(255,255,255,0.06)" : "rgba(239,68,68,0.18)",
                              color: tooLate ? "rgba(255,255,255,0.4)" : "#fca5a5",
                              cursor: tooLate ? "not-allowed" : "pointer",
                            }}>
                            {isCancelling ? "…" : "Annuler"}
                          </button>
                        )}
                      </div>
                    );
                  })() : (
                    <>
                      <div className="flex items-center justify-between gap-2 flex-wrap">
                        <div className="flex items-center gap-2" data-testid={`qty-${occ.course_id}`}>
                          <button type="button" onClick={dec}
                            disabled={qty <= 1 || isBusy || noSessions} aria-label="Diminuer"
                            className="w-8 h-8 rounded-full text-sm font-bold disabled:opacity-30"
                            style={{ background: "rgba(255,255,255,0.08)", color: "white", border: "1px solid rgba(255,255,255,0.12)" }}>
                            −
                          </button>
                          <span className="text-sm font-semibold w-6 text-center">{qty}</span>
                          <button type="button" onClick={inc}
                            disabled={qty >= maxQty || isBusy || noSessions} aria-label="Augmenter"
                            className="w-8 h-8 rounded-full text-sm font-bold disabled:opacity-30"
                            style={{ background: "rgba(255,255,255,0.08)", color: "white", border: "1px solid rgba(255,255,255,0.12)" }}>
                            +
                          </button>
                        </div>
                        <button type="button" disabled={isBusy || noSessions}
                          onClick={() => handleReserve(occ)}
                          className="text-xs font-semibold px-4 py-2 rounded-lg disabled:opacity-50"
                          style={{ background: COLORS.primary, color: "white" }}
                          data-testid={`reserve-${occ.course_id}`}>
                          {isBusy ? "…" : qty > 1 ? `Réserver ${qty} places` : "Réserver"}
                        </button>
                      </div>

                      {qty > 1 && (
                        <ol className="mt-3 space-y-1 text-xs text-white/70">
                          <li className="flex items-center gap-2">
                            <span className="w-4 text-white/40">1.</span>
                            <span className="flex-1">{firstName} <span className="text-white/40">(moi)</span></span>
                          </li>
                          {Array.from({ length: qty - 1 }).map((_, i) => (
                            <li key={i} className="flex items-center gap-2">
                              <span className="w-4 text-white/40">{i + 2}.</span>
                              <input type="text"
                                value={(guestNames[key] || [])[i] || ""}
                                onChange={(e) => setGuestName(key, i, e.target.value)}
                                placeholder="Prénom" maxLength={50}
                                data-testid={`guest-input-${occ.course_id}-${i}`}
                                className="flex-1 px-2 py-1 rounded text-xs"
                                style={{ background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.12)", color: "white" }} />
                            </li>
                          ))}
                        </ol>
                      )}
                    </>
                  )}
                </div>
              </div>
            );
          })()}
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

        {/* ===== V206e: Footer — Paiement Stripe avec icônes carte + TWINT ===== */}
        <section className="pt-2" data-testid="subscriber-space-footer">
          {(() => {
            const isEmpty = remaining <= 0;
            // V206f: Individuel → toujours visible | Groupe → seulement le payeur
            const isGroup = data?.multi_member;
            const canPay = isGroup ? data?.is_payer !== false : true;
            const hasStripe = data?.stripe_amount && Number(data.stripe_amount) > 0 && canPay;
            console.log('[V207] Payment btn debug:', { stripe_amount: data?.stripe_amount, isGroup, canPay, hasStripe, is_payer: data?.is_payer });
            const btnStyle = {
              background: isEmpty
                ? `linear-gradient(135deg, ${COLORS.primary}, ${COLORS.secondary})`
                : "rgba(217,28,210,0.18)",
              color: isEmpty ? "white" : "#F0A8EE",
              border: isEmpty ? "none" : `1px solid ${COLORS.primary}55`,
              boxShadow: isEmpty ? "0 6px 20px rgba(217,28,210,0.35)" : "none",
            };
            if (hasStripe) {
              return (
                <button
                  type="button"
                  onClick={handleStripeCheckout}
                  disabled={stripeLoading}
                  data-testid="renew-subscription-btn"
                  className={`w-full flex items-center justify-center gap-3 font-semibold rounded-2xl transition-transform active:scale-95 ${isEmpty ? "py-4 text-base" : "py-3 text-sm"}`}
                  style={btnStyle}
                >
                  {stripeLoading ? "Redirection..." : (
                    <>
                      {/* Icône carte de crédit */}
                      <svg width="22" height="16" viewBox="0 0 22 16" fill="none" xmlns="http://www.w3.org/2000/svg">
                        <rect x="0.5" y="0.5" width="21" height="15" rx="2.5" stroke="currentColor"/>
                        <line x1="0" y1="5" x2="22" y2="5" stroke="currentColor" strokeWidth="1.5"/>
                        <rect x="2" y="9" width="5" height="2" rx="0.5" fill="currentColor" opacity="0.5"/>
                      </svg>
                      Renouveler mon abonnement
                      {/* Icône TWINT */}
                      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                        <rect width="24" height="24" rx="6" fill="currentColor" opacity="0.15"/>
                        <path d="M12 4L14.5 8.5L19.5 9.5L16 13.5L17 19L12 16.5L7 19L8 13.5L4.5 9.5L9.5 8.5L12 4Z" fill="currentColor" opacity="0.7"/>
                      </svg>
                    </>
                  )}
                </button>
              );
            }
            return null;
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
