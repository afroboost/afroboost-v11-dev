// V184: Page d'accès rapide abonné
// V202: Multi-membres, lien personnel, Stripe, scroll fluide
// Lien public /espace/AFR-XXXXXX — bienvenue, séances, QR, réservation, guide

import React, { useEffect, useMemo, useState, useCallback, useRef, lazy, Suspense } from "react";
import axios from "axios";
import ConditionsParticipation from './ConditionsParticipation'; // ESSAI-5a-1
import InvitationTemoignage, { enRepos } from './InvitationTemoignage'; // ESSAI-5a-2
import ConversionApresEssai from './ConversionApresEssai'; // LOT A
import { QRCodeSVG } from "qrcode.react";
import { Dialog, DialogContent, DialogTitle } from "./ui/dialog";
import { copyToClipboard } from "../utils/clipboard";
import SubscriberOnboarding from "./SubscriberOnboarding"; // V223
// V334 etape 2 : « Mon cockpit » charge A LA DEMANDE (React.lazy).
// Il embarque recharts, qui pese ~98 ko gzip : l'inclure dans le bundle
// principal ferait payer ce poids a CHAQUE visiteur, pour une section repliee
// par defaut. En lazy, le morceau n'est telecharge qu'a l'ouverture du cockpit.
const SubscriberCockpit = lazy(() => import("./SubscriberCockpit"));
import SvgIcon from "./SvgIcon";
import { PublishModal } from "./Publications"; // V261
// ESSAI-7 : la mesure du dernier pas du funnel — « une seance a ete reservee ».
import { funnelTracer } from "../utils/funnelEssai";
// ESSAI-7 : l'etat d'essai REELLEMENT affichable, decide hors de cet ecran et
// teste a part. Il avance d'un cran des qu'une reservation est confirmee, sans
// attendre un rechargement.
import { etatEssaiAffiche } from "../utils/essaiReservation";
// N2 : la MEME lecture de l'heure que le serveur (`n2_instant_reel`). Sans
// elle, une date naive serait lue dans le fuseau du navigateur et l'ecran
// pourrait offrir « Annuler » alors que le serveur refuse.
import { instantReelCours, estAujourdhuiZurich } from "../utils/heureCours";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "";
const API = `${BACKEND_URL}/api`;

const COLORS = {
  bg: "#0A0A0F",
  primary: "var(--primary-color, #D91CD2)",
  secondary: "#FF2DAA",
  panel: "rgba(255,255,255,0.04)",
  border: "rgba(255,255,255,0.08)",
};

// N2 — LA MEME VALEUR QUE LE SERVEUR (`T1_DELAI_ANNULATION_H`), decidee par le
// proprietaire le 25/08/2026. L'ecran offrait « Annuler » jusqu'a 2 h, le
// serveur refusait sous 24 h : entre les deux, le bouton etait mort.
const DELAI_ANNULATION_H = 2;

// N2 — UN `href` N'EST PAS UNE CHAINE COMME LES AUTRES.
// React n'assainit PAS les `href` : `javascript:...` s'execute au clic, dans
// la page du participant, avec son code AFR- a portee. Le serveur filtre deja
// (`n2_lien_carte`), mais l'ecran ne doit pas dependre de la promesse d'une
// autre couche : c'est LUI qui fabrique le lien, c'est LUI qui repond.
// Liste blanche, jamais liste noire — on n'enumere pas ce qui est dangereux,
// on n'accepte que ce qu'on reconnait.
const lienCarteSur = (url) => {
  const u = String(url || "").trim();
  return /^https?:\/\//i.test(u) ? u : "";
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

// ═══ LOT B3-S1.2 — LE JETON D'ESPACE, ET OU IL VIT ═══════════════════════
//
// POURQUOI CET ECRAN EXISTE. `GET /api/subscriber/space/{code}` sert l'e-mail,
// le telephone, les objectifs, le solde, les reservations et — pour un groupe —
// la liste des membres, a quiconque connait le code. Or 37 des 63 codes en base
// sont des libelles lisibles du type prenom + annee : ils ne demandent aucune
// force brute. Le code ne peut donc pas rester le seul secret.
//
// LE JETON V296 NE POUVAIT PAS SERVIR DE PREUVE : `POST /subscriber/token`
// n'exige que le code. Un jeton derive du secret qu'il protege ne protege rien.
// Celui-ci s'obtient par un code a 6 chiffres envoye a l'adresse ENREGISTREE.
//
// CLE ET EN-TETE DISTINCTS de V296 (`afroboost_subscriber_token` /
// `X-Subscriber-Token`) : le serveur rejette l'un la ou il accepte l'autre, et
// ecraser la cle du chat le casserait.
const B3S1_CLE_JETON = "afroboost_espace_token";

function b3s1LireJeton(code, slug) {
  try {
    const brut = window.localStorage.getItem(B3S1_CLE_JETON);
    if (!brut) return null;
    const j = JSON.parse(brut);
    if (!j || !j.token) return null;
    // Le jeton vaut pour UN code et UN membre : celui d'un autre espace ne doit
    // jamais ouvrir celui-ci, meme sur le meme appareil.
    if ((j.code || "") !== (code || "")) return null;
    if ((j.slug || "") !== (slug || "")) return null;
    if (j.expires_at && new Date(j.expires_at) <= new Date()) return null;
    return j;
  } catch (e) {
    return null;
  }
}

function b3s1EcrireJeton(code, slug, token, expiresAt) {
  try {
    window.localStorage.setItem(B3S1_CLE_JETON, JSON.stringify({
      token, code: code || "", slug: slug || "", expires_at: expiresAt || null,
    }));
  } catch (e) { /* stockage indisponible : l'acces prime, on reidentifiera */ }
}

function b3s1OublierJeton() {
  try { window.localStorage.removeItem(B3S1_CLE_JETON); } catch (e) { /* ignore */ }
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

  // V261: modale de publication sur le mur de la vitrine
  const [v261ShowPublish, setV261ShowPublish] = useState(false);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  // LOT B3-S1.2 — la barriere d'identification.
  const [jetonEspace, setJetonEspace] = useState(null);
  const [identEtape, setIdentEtape] = useState("email");   // "email" | "otp"
  const [identEmail, setIdentEmail] = useState("");
  const [identOtp, setIdentOtp] = useState("");
  const [identOccupe, setIdentOccupe] = useState(false);
  const [identInfo, setIdentInfo] = useState("");
  const [identErreur, setIdentErreur] = useState("");
  const [renvoiDispoA, setRenvoiDispoA] = useState(0);
  const [maintenantSec, setMaintenantSec] = useState(() => Date.now());
  const [data, setData] = useState(null);
  const [reservingKey, setReservingKey] = useState(null);
  // ESSAI-5a-1 : l'acceptation vaut pour UNE occurrence — l'annonce de
  // captation depend du cours, elle ne peut donc pas etre globale a l'ecran.
  const [conditionsOk, setConditionsOk] = useState({});
  const [conditionsRequises, setConditionsRequises] = useState(false);
  const [confirmedKeys, setConfirmedKeys] = useState({});
  // P2-UX SIMPLE — LA SEANCE QU'ON VIENT DE RESERVER, ET ELLE SEULE.
  //
  // Jusqu'ici la seule confirmation etait un badge « Reserve » de la taille
  // d'une etiquette, au milieu d'une liste de dates. Quelqu'un qui vient de
  // reserver son PREMIER cours n'a aucun repere pour savoir ce qu'il a obtenu,
  // ni ou il doit se rendre. On garde le badge — il dit l'etat de chaque date —
  // et on ajoute un panneau qui repond aux trois seules questions du moment :
  // c'est confirme, quand, ou.
  //
  // Les valeurs viennent de l'occurrence REELLEMENT envoyee au serveur, jamais
  // d'un texte fabrique : si le serveur avait refuse, on ne serait pas ici.
  const [seanceConfirmee, setSeanceConfirmee] = useState(null);
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
  const [onboardingDone, setOnboardingDone] = useState(false); // V223
  // V223: refus mémorisé par code, pour que "Plus tard" survive au rechargement.
  // localStorage peut lever (mode privé Safari, quota) : on ne bloque jamais
  // l'accès à des crédits payés pour un problème de stockage.
  const [onboardingDismissed, setOnboardingDismissed] = useState(() => {
    try {
      return !!window.localStorage.getItem(`afb_onb_${accessCode || ""}`);
    } catch (e) {
      return false;
    }
  });

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

  // LOT B3-S1.2 : on relit le jeton a chaque changement de code ou de membre.
  useEffect(() => {
    setJetonEspace(b3s1LireJeton(accessCode, memberSlug));
  }, [accessCode, memberSlug]);

  // LE CHARGEMENT EST SUBORDONNE AU JETON. Sans lui, on n'appelle meme pas la
  // route : l'ecran d'identification ne doit pas etre un rideau devant des
  // donnees deja recuperees. Tant que le serveur n'exige rien (B3-S1.3), c'est
  // CE garde-ci qui tient la porte.
  useEffect(() => {
    if (jetonEspace) {
      loadSpace();
    } else {
      setLoading(false);
    }
  }, [loadSpace, jetonEspace]);

  // Compte a rebours du bouton « Renvoyer » : une horloge locale, pas un
  // minuteur par bouton — un seul intervalle, arrete des qu'il ne sert plus.
  useEffect(() => {
    if (!renvoiDispoA || jetonEspace) return undefined;
    const t = setInterval(() => setMaintenantSec(Date.now()), 1000);
    return () => clearInterval(t);
  }, [renvoiDispoA, jetonEspace]);

  const b3s1Secondes = Math.max(0, Math.ceil((renvoiDispoA - maintenantSec) / 1000));

  // ── Demander le code a 6 chiffres ────────────────────────────────────────
  const b3s1DemanderCode = useCallback(async () => {
    const mail = (identEmail || "").trim();
    if (!mail || mail.indexOf("@") < 1) {
      setIdentErreur("Indique une adresse e-mail valide.");
      return;
    }
    setIdentOccupe(true); setIdentErreur(""); setIdentInfo("");
    try {
      const corps = { code: accessCode, email: mail };
      if (memberSlug) corps.m = memberSlug;
      const res = await axios.post(`${API}/subscriber/otp/request`, corps);
      // Le serveur repond la MEME chose que l'adresse corresponde ou non : on
      // affiche donc son message tel quel, sans jamais le completer par une
      // information sur l'existence d'un compte.
      setIdentInfo(res?.data?.message
        || "Si ces informations correspondent à un espace, un code vient d'être envoyé par e-mail.");
      setIdentEtape("otp");
      setRenvoiDispoA(Date.now() + 120000);
      setMaintenantSec(Date.now());
    } catch (err) {
      if (err?.response?.status === 429) {
        setIdentErreur("Trop de demandes. Réessaie dans quelques minutes.");
      } else {
        setIdentErreur("L'envoi n'a pas pu aboutir. Vérifie ta connexion et réessaie.");
      }
    } finally {
      setIdentOccupe(false);
    }
  }, [accessCode, memberSlug, identEmail]);

  // ── Verifier le code et recuperer le jeton ───────────────────────────────
  const b3s1ValiderCode = useCallback(async () => {
    const saisi = (identOtp || "").replace(/\D/g, "");
    if (saisi.length !== 6) {
      setIdentErreur("Le code comporte 6 chiffres.");
      return;
    }
    setIdentOccupe(true); setIdentErreur("");
    try {
      const corps = { code: accessCode, email: (identEmail || "").trim(), otp: saisi };
      if (memberSlug) corps.m = memberSlug;
      const res = await axios.post(`${API}/subscriber/otp/verify`, corps);
      const tok = res?.data?.token;
      if (!tok) throw new Error("sans jeton");
      b3s1EcrireJeton(accessCode, memberSlug, tok, res?.data?.expires_at);
      setJetonEspace({ token: tok, code: accessCode, slug: memberSlug || "" });
      setIdentOtp(""); setIdentInfo("");
    } catch (err) {
      // Le serveur ne distingue pas « faux », « expire » et « essais epuises » :
      // il renvoie un seul 400. On ne peut donc pas etre plus precis sans
      // inventer — et inventer serait exactement l'oracle qu'on evite.
      if (err?.response?.status === 429) {
        setIdentErreur("Trop de tentatives. Réessaie dans quelques minutes.");
      } else if (err?.response?.status === 503) {
        setIdentErreur("Vérification momentanément indisponible. Réessaie dans un instant.");
      } else {
        setIdentErreur("Code invalide ou expiré. Demande un nouveau code.");
      }
    } finally {
      setIdentOccupe(false);
    }
  }, [accessCode, memberSlug, identEmail, identOtp]);

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
  const [rechargeLoading, setRechargeLoading] = useState(false);

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

  // LOT R — RECHARGER LE PACK.
  //
  // LE NAVIGATEUR NE DECIDE RIEN. C'est le serveur qui a dit `eligible`, qui
  // a donne l'offre, le prix et le nombre de seances ; ce bouton ne fait que
  // transmettre. Et la caisse REVERIFIE tout (garde `lotr_garde_achat`) : un
  // bouton force depuis la console n'ouvre rien.
  const handleRecharge = async () => {
    const r = data?.recharge;
    if (rechargeLoading || !r?.eligible || !r?.offer_id) return;
    setRechargeLoading(true);
    setActionError("");
    try {
      const res = await axios.post(`${API}/create-checkout-session`, {
        productName: r.offer_name || "Recharge Afroboost",
        // Le serveur fait AUTORITE sur le montant des qu'`offerId` est fourni
        // (V428C) : cette valeur n'est qu'un affichage transmis.
        amount: r.prix,
        customerEmail: data?.subscriber?.email || "",
        originUrl: window.location.origin,
        offerId: r.offer_id,
        quantity: 1,
      });
      if (res.data?.url) {
        window.location.href = res.data.url;
      } else {
        setActionError("Le paiement est momentanément indisponible. Réessaye.");
        setRechargeLoading(false);
      }
    } catch (err) {
      setActionError(err?.response?.data?.detail
        || "Recharge impossible pour le moment.");
      setRechargeLoading(false);
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
        { datetime: occurrence.datetime, quantity: qty, guests, member_slug: memberSlug || undefined,
          terms_accepted: !!conditionsOk[reservationKey] }
      );
      // V213g: Injecter la nouvelle réservation dans data pour que le useEffect la voie
      // et que le vert reste visible instantanément (pas besoin de rafraîchir)
      const newRes = res.data?.reservation || { courseId: occurrence.course_id, datetime: occurrence.datetime };
      setData((prev) => {
        if (!prev) return prev;
        const updatedReservations = [...(prev.reservations || []), newRes];
        const updatedSub = typeof res.data?.remaining_sessions === "number"
          ? { ...prev.subscription, remaining_sessions: res.data.remaining_sessions }
          : prev.subscription;
        return { ...prev, reservations: updatedReservations, subscription: updatedSub };
      });
      // ESSAI-7 — `session_booked`, LE dernier pas du funnel.
      // Il part ICI, et nulle part ailleurs : apres la reponse du serveur,
      // donc apres qu'une reservation a REELLEMENT ete creee. Pas au clic
      // (le serveur peut refuser : plus de credit, capacite pleine, conditions
      // manquantes), pas a l'ouverture de l'ecran. Un refus part dans le
      // `catch` et ne compte pas ; un rechargement ne rejoue aucun POST, donc
      // ne peut pas produire de doublon.
      // Aucune donnee personnelle : ni code, ni prenom, ni accompagnants.
      funnelTracer('session_booked', {
        course_id: occurrence.course_id,
        places: qty,
        is_trial: !!(data?.trial && data.trial.is_trial)
      });

      // P2-UX SIMPLE : posee ICI, donc APRES la reponse du serveur — au meme
      // endroit que `session_booked`, et pour la meme raison. Un refus part
      // dans le `catch` et n'affiche aucune confirmation.
      setSeanceConfirmee({
        cle: reservationKey,
        nom: occurrence.name || "",
        datetime: occurrence.datetime,
        date: occurrence.date,
        time: occurrence.time,
        lieu: occurrence.locationName || "",
        places: qty,
      });

      // V186/V187: reset compteur + guests après réservation
      setQuantities((prev) => ({ ...prev, [reservationKey]: 1 }));
      setGuestNames((prev) => ({ ...prev, [reservationKey]: [] }));
    } catch (err) {
      const status = err?.response?.status;
      const message = err?.response?.data?.detail || "Réservation impossible. Réessaye dans un instant.";
      setActionError(message);
      // V211c: Si 409 "déjà réservé" → marquer la date en vert + recharger les données
      if (status === 409) {
        setConfirmedKeys((prev) => ({ ...prev, [reservationKey]: true }));
        loadSpace(); // Recharger pour récupérer la réservation depuis le backend
      }
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

  // ═══ LOT B3-S1.2 — LA BARRIERE D'IDENTIFICATION ═══════════════════════
  //
  // ELLE PASSE AVANT TOUT, y compris avant l'ecran de chargement : sans jeton,
  // aucune donnee privee n'a ete demandee, il n'y a donc rien a charger.
  // Elle ne doit JAMAIS etre une page morte — chaque echec laisse un message,
  // un bouton « Réessayer », la possibilite de corriger l'adresse, et le
  // recours au coach.
  if (!jetonEspace) {
    const enOtp = identEtape === "otp";
    return (
      <div className="min-h-screen flex items-center justify-center p-6"
           style={{ background: COLORS.bg, color: "white" }}>
        <div className="max-w-md w-full rounded-2xl p-6"
             style={{ background: COLORS.panel, border: `1px solid ${COLORS.border}` }}
             data-testid="espace-identification">
          <h1 className="text-xl font-semibold mb-2">Accède à ton espace</h1>
          <p className="text-white/60 text-sm mb-5">
            {enOtp
              ? "Saisis le code à 6 chiffres reçu par e-mail."
              : "Confirme ton adresse e-mail pour recevoir un code de vérification."}
          </p>

          {!enOtp && (
            <input
              type="email" inputMode="email" autoComplete="email"
              value={identEmail}
              onChange={(e) => setIdentEmail(e.target.value)}
              placeholder="ton adresse e-mail"
              data-testid="espace-email"
              className="w-full px-3 py-3 rounded-xl mb-3 text-sm"
              style={{ background: "rgba(255,255,255,0.06)", border: `1px solid ${COLORS.border}`, color: "white" }}
            />
          )}

          {enOtp && (
            <input
              type="text" inputMode="numeric" autoComplete="one-time-code" maxLength={6}
              value={identOtp}
              onChange={(e) => setIdentOtp(e.target.value.replace(/\D/g, ""))}
              placeholder="000000"
              data-testid="espace-otp"
              className="w-full px-3 py-3 rounded-xl mb-3 text-center text-2xl tracking-[0.4em]"
              style={{ background: "rgba(255,255,255,0.06)", border: `1px solid ${COLORS.border}`, color: "white" }}
            />
          )}

          {identInfo && (
            <p className="text-white/70 text-xs mb-3" data-testid="espace-info">{identInfo}</p>
          )}
          {identErreur && (
            <p className="text-sm mb-3" data-testid="espace-erreur"
               style={{ color: COLORS.primary }}>{identErreur}</p>
          )}

          <button
            type="button" disabled={identOccupe}
            onClick={enOtp ? b3s1ValiderCode : b3s1DemanderCode}
            data-testid="espace-valider"
            className="w-full py-3 rounded-xl text-sm font-semibold disabled:opacity-50"
            style={{ background: `linear-gradient(135deg, ${COLORS.primary}, ${COLORS.secondary})`, color: "white" }}>
            {identOccupe ? "…" : enOtp ? "Valider" : "Recevoir mon code"}
          </button>

          {enOtp && (
            <div className="mt-3 flex items-center justify-between gap-3">
              <button
                type="button" data-testid="espace-renvoyer"
                disabled={identOccupe || b3s1Secondes > 0}
                onClick={b3s1DemanderCode}
                className="text-xs underline disabled:opacity-40 disabled:no-underline"
                style={{ color: "rgba(255,255,255,0.7)" }}>
                {b3s1Secondes > 0 ? `Renvoyer dans ${b3s1Secondes}s` : "Renvoyer le code"}
              </button>
              <button
                type="button" data-testid="espace-corriger"
                onClick={() => { setIdentEtape("email"); setIdentOtp(""); setIdentErreur(""); setIdentInfo(""); }}
                className="text-xs underline" style={{ color: "rgba(255,255,255,0.7)" }}>
                Corriger mon e-mail
              </button>
            </div>
          )}

          <p className="text-white/40 text-xs mt-5">
            Tu n'as pas reçu de code ou tu n'as plus accès à cette adresse ?
            Contacte ton coach, il peut t'aider.
          </p>
        </div>
      </div>
    );
  }

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
          <div className="text-4xl mb-3"><SvgIcon name="lock" size={36} /></div>
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
                        <span className="inline-flex items-center gap-1.5"><SvgIcon name="user" size={14} /> {mem.name}</span>
                        <span className="text-white/30"><SvgIcon name="arrowRight" size={14} /></span>
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

  // LOT A : le total suit la meme verite que le restant (voir plus bas).
  const total = (subscription.droits_etat === "OK" && typeof subscription.droits_total === "number")
    ? subscription.droits_total
    : (subscription.total_sessions || 0);
  // ESSAI-5a-1D : l'etat de l'essai est DERIVE PAR LE SERVEUR. Cet ecran ne
  // le recalcule pas — il se contente de dire ce qu'il recoit. Absent pour un
  // forfait payant, dont l'affichage reste strictement inchange.
  const essai = data?.trial || null;
  const estEssai = !!(essai && essai.is_trial);
  const etatEssai = estEssai ? essai.state : null;

  // ═══ LOT A — LE SOLDE AFFICHE VIENT DE LA PAGE « CODE PROMO » ══════════
  //
  // Decision du 27/08/2026 : `discount_codes` fait foi. Le serveur envoie
  // desormais `droits_etat` (OK / AUCUN_DROIT / AMBIGU / INDISPONIBLE) et,
  // quand il sait, le solde canonique. Cet ecran ne recalcule RIEN : il
  // affiche ce qu'on lui donne, ou il se tait.
  //
  // AMBIGU = plusieurs forfaits, plusieurs fiches pour un meme code, ou deux
  // collections qui se contredisent. Dans ce cas on n'affiche AUCUN chiffre :
  // ni 0, ni la somme, ni le premier venu. Un solde invente ferme un droit
  // paye ou en promet un qui n'existe pas.
  const droitsEtat = subscription.droits_etat || null;
  const droitsAmbigus = droitsEtat === "AMBIGU";
  const droitsCanoniques = droitsEtat === "OK"
    && typeof subscription.droits_restant === "number"
    && typeof subscription.droits_total === "number";
  const remaining = droitsCanoniques
    ? subscription.droits_restant
    : (subscription.remaining_sessions || 0);
  const used = droitsCanoniques
    ? subscription.droits_utilise
    : (subscription.used_sessions || (total ? total - remaining : 0));
  const percentUsed = total > 0 ? Math.max(0, Math.min(100, Math.round((used / total) * 100))) : 0;
  // `noSessions` GARDE la valeur historique, celle que lit la RESERVATION cote
  // serveur. Ce lot ne touche pas a la reservation : le bouton s'active donc
  // exactement comme avant, meme quand l'affichage, lui, change.
  const noSessions = (subscription.remaining_sessions || 0) <= 0;

  // ESSAI-7 — L'ETAT QUE CET ECRAN MONTRE.
  // `t2_etat_essai` derive l'etat au CHARGEMENT. Une reservation faite juste
  // apres n'y figure donc pas : sans ce rattrapage, l'ecran continuerait a
  // reclamer « choisis ta seance » a quelqu'un qui vient d'en choisir une, et
  // il faudrait recharger la page pour le voir changer. La regle vit dans
  // `utils/essaiReservation.js`, ou elle est testee cas par cas.
  const etatEssaiVu = etatEssaiAffiche(essai, upcomingReservations.length);
  // Tant qu'aucune seance n'est choisie, choisir EST l'action principale : le
  // QR ne repond pas a « qu'est-ce que je fais maintenant ? », il repond a
  // « je suis a l'entree du cours ».
  //
  // `!noSessions` est volontaire : il existe un etat transitoire ou le droit
  // est « disponible » alors que le compteur affiche encore 0 — une seance
  // passee non honoree, dont le credit n'est rendu qu'a la prochaine tentative
  // (`t1_restituer_essais_non_honores`). Y crier « choisis ta seance » devant
  // des boutons desactives serait un mensonge : dans ce cas precis, l'ecran
  // garde exactement son affichage d'avant ce lot.
  const essaiAReserver = etatEssaiVu === "available" && !noSessions;
  const essaiReserve = etatEssaiVu === "booked";
  const essaiPrioritaire = essaiAReserver || essaiReserve;
  const prochaineSeance = upcomingReservations[0] || null;

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

  // V223: profil incomplet → écran de bienvenue, une seule fois. Lien
  // "Plus tard" obligatoire : sans lui, un abonné existant sans name/whatsapp
  // serait enfermé hors de crédits déjà payés.
  // V223: jamais pour un membre secondaire — le PUT .../profile écrit sur
  // subscriptions filtré par code seul, donc un membre écraserait le WhatsApp
  // du titulaire, relu ensuite par tout le groupe. L'onboarding ne concerne
  // que l'acheteur.
  // V223: on ne teste QUE le WhatsApp. Le backend fait toujours retomber
  // display_name sur le préfixe de l'e-mail, puis sur "Abonné" : subscriber.name
  // n'est jamais vide, le tester ne servirait à rien.
  // V223: le refus est persisté par code. Sans cela, "Plus tard" ne survivrait
  // pas au rechargement et l'écran reviendrait à chaque visite, indéfiniment,
  // pour tout abonné existant sans WhatsApp — une régression visible par tous.
  const needsOnboarding = !onboardingDone && !data?.member &&
    !subscriber.whatsapp && !onboardingDismissed;
  if (needsOnboarding) {
    return (
      <SubscriberOnboarding
        code={accessCode}
        subscription={subscriber}
        onDone={() => {
          // V223: mémoriser le refus pour ne pas rouvrir l'écran à chaque visite
          try {
            window.localStorage.setItem(`afb_onb_${accessCode || ""}`, "1");
          } catch (e) {
            /* stockage indisponible : on continue, l'accès prime */
          }
          setOnboardingDone(true);
        }}
      />
    );
  }

  return (
    <div className="min-h-screen pb-16" style={{ background: COLORS.bg, color: "white" }}>
      {/* ESSAI-7 : `flex flex-col gap-5` rend EXACTEMENT le meme espacement
          que `space-y-5`, mais permet de remonter un bloc avec `order` sans
          rien demonter. Hors parcours d'essai, tous les `order` valent 0 et
          l'ordre du DOM est conserve au pixel pres. */}
      <div className="max-w-md mx-auto px-4 pt-6 flex flex-col gap-5">
        {/* V203f: Bouton retour vers la page d'inscription multi-membre */}
        {data?.multi_member && memberSlug && (
          <button
            type="button"
            onClick={() => {
              setMemberSlug("");
              window.history.replaceState(null, "", window.location.pathname);
            }}
            className="text-xs text-white/50 hover:text-white transition-colors self-start"
            style={{ order: essaiPrioritaire ? -3 : 0 }}
          >
            <span className="inline-flex items-center gap-1.5"><SvgIcon name="arrowLeft" size={14} /> Retour à la page du groupe</span>
          </button>
        )}

        {/* ===== Welcome ===== */}
        <header className="flex items-center gap-3" data-testid="subscriber-space-header"
          style={{ order: essaiPrioritaire ? -2 : 0 }}>
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
          {/* V261: publier sur le mur de la vitrine. Present UNIQUEMENT dans
              l'espace abonne, donc invisible pour un simple visiteur — c'est
              deja la garde d'interface ; le serveur revalide le code AFR- de
              toute facon a la soumission. */}
          {/* V267: pilule « Publier + » — le rond « + » seul n'etait pas compris. */}
          <button
            type="button"
            onClick={() => setV261ShowPublish(true)}
            title="Publier une photo ou une vidéo"
            aria-label="Publier une photo ou une vidéo"
            style={{
              height: 40, borderRadius: 20, padding: '0 16px', flexShrink: 0,
              background: COLORS.primary, color: '#fff', border: 'none', cursor: 'pointer',
              display: 'flex', alignItems: 'center', gap: 6,
              fontSize: 14, fontWeight: 700,
              boxShadow: '0 2px 8px rgba(0,0,0,0.3)'
            }}
            data-testid="subscriber-publish-button"
          >
            Publier
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" style={{ flexShrink: 0 }}>
              <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
            </svg>
          </button>
        </header>

        {/* ═══ P2-UX SIMPLE — LA CONFIRMATION QUI MANQUAIT ═══════════════
            Elle prend la place de tete (`order: -2`, donc au-dessus du bloc
            ESSAI-7 qui, lui, invite a CHOISIR une seance) le temps de dire
            l'essentiel : c'est enregistre, quand, ou. Elle ne remplace pas le
            badge « Reserve » de chaque date, qui reste la source d'etat.
            Aucune redirection, aucune vente derriere : la personne vient de
            faire ce qu'on lui demandait, le parcours s'arrete ici. */}
        {seanceConfirmee && (
          <section
            className="rounded-2xl p-5"
            data-testid="p2ux-confirmation"
            style={{
              order: -2,
              background: 'rgba(34,197,94,0.10)',
              border: '1px solid rgba(34,197,94,0.45)',
            }}
          >
            <p className="text-lg font-bold" style={{ color: '#86efac' }}>
              ✅ Ta réservation est confirmée !
            </p>
            <p className="text-base font-semibold mt-2">
              {formatOccurrence(
                seanceConfirmee.date
                  ? { date: seanceConfirmee.date, time: seanceConfirmee.time }
                  : seanceConfirmee.datetime
              )}
            </p>
            {seanceConfirmee.nom && (
              <p className="text-sm opacity-80">{seanceConfirmee.nom}</p>
            )}
            {seanceConfirmee.lieu && (
              <p className="text-sm opacity-80 flex items-center gap-1.5 mt-1">
                <SvgIcon name="mapPin" size={14} /> {seanceConfirmee.lieu}
              </p>
            )}
            {seanceConfirmee.places > 1 && (
              <p className="text-sm opacity-80 mt-1">
                {seanceConfirmee.places} places réservées
              </p>
            )}
            <p className="text-sm mt-3 opacity-75">
              Nous avons bien enregistré ta place. À bientôt chez Afroboost 🎧🔥
            </p>
          </section>
        )}

        {/* ═══ ESSAI-7 — TANT QU'AUCUNE SEANCE N'EST CHOISIE, CHOISIR EST
            L'ACTION PRINCIPALE ══════════════════════════════════════════════
            Avant ce bloc, quelqu'un qui venait d'obtenir son essai arrivait
            devant un compteur, puis un QR code, et ne trouvait la liste des
            seances qu'apres le pli. Or le QR ne repond pas a « qu'est-ce que
            je fais maintenant ? » — il repond a « je suis a l'entree du
            cours ». Rien n'est cache pour autant : `order` remonte ce bloc,
            il ne demonte rien. */}
        {essaiAReserver && (
          <section
            className="rounded-2xl p-5"
            data-testid="essai7-priorite"
            style={{
              order: -1,
              background: 'rgba(var(--primary-rgb, 217, 28, 210), 0.10)',
              border: `1px solid ${COLORS.primary}`,
            }}
          >
            <p className="text-lg font-bold">🎁 Ton cours d'essai est activé !</p>
            {courses.length > 0 ? (
              <>
                <p className="text-white/60 text-xs uppercase tracking-wider mt-3">
                  Prochaine étape
                </p>
                <p className="text-sm mt-1">Choisis maintenant ta séance.</p>
                <button
                  type="button"
                  onClick={scrollToReservation}
                  data-testid="essai7-choisir"
                  className="mt-4 w-full py-3 rounded-xl font-bold transition-transform active:scale-95"
                  style={{ background: COLORS.primary, color: "white", border: "none" }}
                >
                  Choisir ma séance
                </button>
              </>
            ) : (
              /* ESSAI-7 — ZERO CRENEAU : on dit ce qui est VRAI, et on ne
                 promet rien qui n'existe pas. Aucune notification n'est
                 branchee derriere cet ecran : annoncer « on te previendra »
                 serait une promesse que personne ne tient. L'espace, lui,
                 reste entierement accessible. */
              <p className="text-sm mt-3 text-white/70" data-testid="essai7-aucun-creneau">
                Aucun nouveau créneau n'est disponible pour le moment.
                Reviens bientôt pour choisir ta séance.
              </p>
            )}
          </section>
        )}

        {/* ═══ ESSAI-7 — LA SEANCE EST CHOISIE : LE QR DEVIENT LA SUITE ════
            C'est seulement ici que le QR a un sens : il y a une seance, une
            date, une porte a franchir. Le bouton OUVRE le QR existant, il ne
            le remplace pas et ne le deplace pas. */}
        {essaiReserve && (
          <section
            className="rounded-2xl p-5"
            data-testid="essai7-reserve"
            style={{
              order: -1,
              background: 'rgba(var(--primary-rgb, 217, 28, 210), 0.10)',
              border: `1px solid ${COLORS.primary}`,
            }}
          >
            <p className="text-lg font-bold">🔥 Ta séance est réservée !</p>
            {prochaineSeance && (
              <p className="text-sm mt-2 font-semibold" style={{ color: COLORS.primary }}>
                {prochaineSeance.courseName ? `${prochaineSeance.courseName} · ` : ""}
                {formatOccurrence(prochaineSeance.datetime)}
              </p>
            )}
            {/* N2 : la meme adresse qu'ailleurs, au moment ou elle sert. */}
            {prochaineSeance && prochaineSeance.locationName ? (
              <p className="text-sm mt-1 text-white/70" data-testid="essai7-lieu">
                <span className="inline-flex items-center gap-1">
                  <SvgIcon name="mapPin" size={12} /> {prochaineSeance.locationName}
                </span>
                {lienCarteSur(prochaineSeance.mapsUrl) ? (
                  <a
                    href={lienCarteSur(prochaineSeance.mapsUrl)}
                    target="_blank"
                    rel="noreferrer"
                    className="ml-2 underline"
                    style={{ color: COLORS.primary }}
                  >
                    Itinéraire
                  </a>
                ) : null}
              </p>
            ) : null}
            <p className="text-sm mt-3 text-white/70">
              Ton QR est prêt. Présente-le au coach à ton arrivée.
            </p>
            <button
              type="button"
              onClick={() => setQrFullscreen(true)}
              data-testid="essai7-voir-qr"
              className="mt-4 w-full py-3 rounded-xl font-bold transition-transform active:scale-95"
              style={{ background: COLORS.primary, color: "white", border: "none" }}
            >
              <span className="inline-flex items-center justify-center gap-1.5">
                <SvgIcon name="ticket" size={16} /> Voir mon QR
              </span>
            </button>
          </section>
        )}

        {/* V261 */}
        {v261ShowPublish && (
          <PublishModal
            subscriberCode={accessCode}
            onClose={() => setV261ShowPublish(false)}
          />
        )}

        {/* V334 etape 2 : « Mon cockpit » — progression de l'abonné. Replie par
            defaut et charge seulement a l'ouverture : l'espace abonne doit rester
            rapide. Il n'affiche QUE les donnees de ce code. */}
        <Suspense fallback={null}>
          <SubscriberCockpit accessCode={accessCode} />
        </Suspense>

        {/* ESSAI-5a-2 : proposée UNIQUEMENT à qui le coach a classé
            « Participant » dans Contacts. Facultative, sans conséquence. */}
        {data?.testimonial?.eligible
          && !data.testimonial.already_submitted
          && !enRepos(subscription.code || accessCode) && (
          <InvitationTemoignage
            code={subscription.code || accessCode}
            prenom={firstName}
            offerId={data?.offer?.id || ''}
          />
        )}

        {/* ===== LOT A : la suite, apres un essai REELLEMENT effectue =====
            `etatEssai === "done"` n'est qu'un INDICE pour eviter un appel
            inutile : c'est le serveur qui decide de l'eligibilite, des offres
            et des prix, et qui refuse l'achat le cas echeant. Le composant se
            rend lui-meme invisible si le serveur ne lui ouvre rien. */}
        {estEssai && etatEssai === "done" && (
          <ConversionApresEssai code={subscription.code || accessCode} prenom={firstName} />
        )}

        {/* ===== Mes séances restantes ===== */}
        <section
          className="rounded-2xl p-5"
          style={{ background: COLORS.panel, border: `1px solid ${COLORS.border}` }}
          data-testid="subscriber-space-sessions"
        >
          <div className="flex items-baseline justify-between mb-2">
            {/* ESSAI-5a-1D : un essai ne se compte pas, il a un ETAT. Afficher
                « 0 / 1 » a quelqu'un qui vient de reserver lui fait croire que
                son essai est consomme, alors que seule sa presence le
                consommera. Un forfait payant garde son compteur intact. */}
            {estEssai ? (
              <div data-testid="essai-etat">
                <p className="text-white/60 text-xs uppercase tracking-wider">Séance découverte</p>
                <p className="text-2xl font-bold mt-1" style={{ color: COLORS.primary }}>
                  {etatEssai === "booked" ? "Essai réservé"
                    : etatEssai === "done" ? "Essai effectué"
                    : "Essai disponible"}
                </p>
                {etatEssai === "booked" && essai.next_session && (
                  <p className="text-white/50 text-xs mt-1" data-testid="essai-seance">
                    {essai.next_session.courseName}
                    {essai.next_session.courseTime ? ` à ${essai.next_session.courseTime}` : ""}
                  </p>
                )}
              </div>
            ) : (
            droitsAmbigus ? (
              // LOT A — on ne sait pas, donc on le dit. Le nom du forfait reste
              // affiche a droite et l'expiration plus bas : elles, ne sont pas
              // ambigues, et les taire priverait l'abonne d'informations justes.
              <div data-testid="droits-ambigus">
                <p className="text-white/60 text-xs uppercase tracking-wider">Séances restantes</p>
                <p className="text-sm mt-1 leading-snug" style={{ color: COLORS.primary }}>
                  {subscription.droits_message
                    || "Plusieurs forfaits sont enregistrés à ton nom — le coach vérifie ton solde."}
                </p>
              </div>
            ) : (
            <div>
              <p className="text-white/60 text-xs uppercase tracking-wider">Séances restantes</p>
              <p className="text-3xl font-bold mt-1" style={{ color: COLORS.primary }}>
                {remaining}
                <span className="text-white/40 text-base font-normal"> / {total || "—"}</span>
              </p>
            </div>
            ))}
            <span className="text-white/40 text-xs text-right max-w-[40%] truncate">{subscription.offer_name}</span>
          </div>
          {/* LOT A : pas de jauge quand le solde est inconnu — une barre a une
              longueur, et toute longueur serait un chiffre invente. */}
          {!droitsAmbigus && (
            <div className="w-full h-2 rounded-full overflow-hidden bg-white/10">
              <div
                className="h-full transition-all"
                style={{
                  width: `${100 - percentUsed}%`,
                  background: `linear-gradient(90deg, ${COLORS.primary}, ${COLORS.secondary})`,
                }}
              />
            </div>
          )}
          {/* V202: Bouton scroll vers réservation — accès rapide */}
          {/* LOT A : le bouton reste offert quand le solde est ambigu — ne pas
              savoir combien il reste n'est pas une raison de fermer l'acces.
              C'est le serveur qui tranche a la reservation, comme avant. */}
          {(droitsAmbigus || remaining > 0) && courses.length > 0 && (
            <button type="button" onClick={scrollToReservation}
              className="mt-3 w-full py-2 rounded-xl text-sm font-semibold transition-transform active:scale-95"
              style={{ background: `linear-gradient(135deg, ${COLORS.primary}, ${COLORS.secondary})`, color: "white" }}>
              <span className="inline-flex items-center justify-center gap-1.5"><SvgIcon name="calendar" size={14} /> Réserver une séance</span>
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
                    // V446 : l'abonné présente le code qu'il a déjà dans son URL.
                    // La route exige désormais une identité (garde `_v334_autoriser`) :
                    // sans ce `code`, un abonné ne pourrait plus régler SA propre
                    // reconduction. Il n'a pas de jeton d'appareil — SubscriberSpace
                    // n'en demande jamais, seul le ChatWidget en manipule.
                    await axios.put(`${API}/subscriptions/${encodeURIComponent(subscription.id)}/auto-renew`, { auto_renew: next, code: accessCode });
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
                    <span className={`inline-block w-2 h-2 rounded-full ${p.hp === "taken" ? "bg-red-500" : "bg-green-500"}`} />
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
            <QRCodeSVG value={memberSlug ? `${subscriber.code || accessCode}::${memberSlug}` : (subscriber.code || accessCode)} size={160} level="M" includeMargin={false} />
          </div>
          <p className="text-white/40 text-xs mt-3 font-mono">{subscriber.code || accessCode}</p>
          <button
            type="button"
            onClick={() => setQrFullscreen(true)}
            className="mt-3 px-4 py-2 rounded-full text-sm font-medium"
            style={{ background: COLORS.primary, color: "white" }}
            data-testid="qr-fullscreen-btn"
          >
            <span className="inline-flex items-center gap-1.5"><SvgIcon name="search" size={14} /> Agrandir</span>
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
                // N2 : instant REEL du cours, fuseau compris — la meme
                // lecture que le garde serveur. Une date illisible ne doit pas
                // fermer l'annulation par accident : on laisse alors le
                // serveur trancher.
                const occurrenceTs = instantReelCours(r.datetime);
                const hoursAway = (occurrenceTs - now) / 3_600_000;
                const tooLate = Number.isFinite(hoursAway) && hoursAway < DELAI_ANNULATION_H;
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
                        {/* N2 : le jour J se voit d'un coup d'oeil. Sans lui, la
                            seance du soir se confond avec celle de la semaine
                            prochaine dans la meme liste. */}
                        {estAujourdhuiZurich(r.datetime) && (
                          <span
                            data-testid="resa-aujourdhui"
                            className="ml-2 px-2 py-0.5 rounded-full text-[10px] font-bold"
                            style={{ background: COLORS.primary, color: "white" }}
                          >
                            AUJOURD'HUI
                          </span>
                        )}
                      </p>
                      {/* N2 — OU. L'adresse vit sur le COURS et n'atteignait
                          jamais cet ecran : on savait dire quand, jamais ou. */}
                      {r.locationName ? (
                        <p className="text-white/50 text-xs mt-0.5" data-testid="resa-lieu">
                          <span className="inline-flex items-center gap-1">
                            <SvgIcon name="mapPin" size={11} /> {r.locationName}
                          </span>
                          {lienCarteSur(r.mapsUrl) ? (
                            <a
                              href={lienCarteSur(r.mapsUrl)}
                              target="_blank"
                              rel="noreferrer"
                              className="ml-2 underline"
                              style={{ color: COLORS.primary }}
                              data-testid="resa-itineraire"
                            >
                              Itinéraire
                            </a>
                          ) : null}
                        </p>
                      ) : null}
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
                                  <SvgIcon name="headphones" size={12} />
                                </span>
                                <span>{p.name || `Invité ${idx + 1}`}</span>
                              </span>
                            ))}
                          </div>
                        );
                      })()}
                    </div>
                    {/* N2 — UN BOUTON GRIS NE DIT RIEN. Le `title` d'un bouton
                        desactive est invisible sur telephone : la personne
                        voyait « Annuler » eteint, sans savoir pourquoi. On
                        remplace le bouton par la RAISON, qui est vraie et
                        n'invente aucun canal de contact — il n'en existe
                        aucun d'automatise pour ce cas. */}
                    {tooLate ? (
                      <span
                        data-testid="annulation-trop-tard"
                        className="text-[11px] leading-tight text-right max-w-[46%]"
                        style={{ color: "rgba(255,255,255,0.45)" }}
                      >
                        Annulation en ligne fermée<br />
                        (moins de 2 h avant)
                      </span>
                    ) : (
                      <button
                        type="button"
                        disabled={isBusy}
                        onClick={() => handleCancelReservation(r)}
                        className="text-xs font-semibold px-3 py-2 rounded-lg disabled:opacity-40"
                        title="Annuler la séance"
                        style={{
                          background: "rgba(239,68,68,0.18)",
                          color: "#fca5a5",
                          cursor: "pointer",
                        }}
                        data-testid={`cancel-reservation-${r.id}`}
                      >
                        {isBusy ? "…" : "Annuler"}
                      </button>
                    )}
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
          style={{
            background: COLORS.panel, border: `1px solid ${COLORS.border}`, overflow: "hidden",
            // ESSAI-7 : remontee juste sous l'annonce tant qu'aucune seance
            // n'est choisie. Zero autrement — l'ordre du DOM est conserve.
            order: essaiAReserver ? -1 : 0,
          }}
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
              data-testid="essai-bandeau"
              className="text-xs mb-3 px-3 py-2 rounded-lg"
              style={{ background: "rgba(245,158,11,0.15)", color: "#fbbf24" }}
            >
              {/* ESSAI-7 : `etatEssaiVu` et non `etatEssai` — juste apres une
                  reservation, le serveur n'a pas encore rederive l'etat et ce
                  bandeau annoncait « Plus de séances disponibles » a quelqu'un
                  qui venait de reserver la sienne. */}
              {estEssai && etatEssaiVu === "booked"
                ? "Vous avez déjà réservé votre séance découverte. Annulez-la pour en choisir une autre."
                : estEssai && etatEssaiVu === "done"
                ? "Votre séance découverte a été utilisée."
                : "Plus de séances disponibles"}
            </p>
          )}
          {courses.length === 0 ? (
            /* V449 — UNE LISTE VIDE DOIT DIRE POURQUOI ELLE EST VIDE.
               Le serveur envoie DEJA `forfait_bloque` et `forfait_message`
               exactement pour ca (voir `upcoming_courses` dans server.py, V393) :
               un forfait expire ou epuise ne propose plus aucun creneau. L'ecran
               les ignorait et affichait « Aucun cours disponible pour le moment »
               — la phrase d'un planning vide, pas celle d'un forfait mort.
               Une abonnee dont l'abonnement avait expire lisait donc qu'il n'y
               avait PAS DE COURS, et le coach avec elle : le vrai motif etait
               invisible des deux cotes. On affiche le motif du serveur, jamais
               un motif recalcule ici. */
            data?.forfait_bloque ? (
              <p
                className="text-sm"
                data-testid="forfait-bloque-message"
                style={{ color: COLORS.primary }}
              >
                {data?.forfait_message
                  || "Ton abonnement n'est plus utilisable. Contacte le coach pour le renouveler."}
              </p>
            ) : (
              <p className="text-white/50 text-sm">Aucun cours disponible pour le moment.</p>
            )
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
                    // V252 FIX 4 : date UNIQUE non encore reservee -> presentee en vert
                    // « pret a reserver » (present-selectionnee). Teinte plus douce que
                    // le vert plein « confirme » (#22c55e) pour ne pas les confondre.
                    const singleReady = visibleCourses.length === 1 && isSelected && !isConfirmed;
                    return (
                      <button key={i} type="button"
                        onClick={() => { setSelectedCourseIdx(i); setActionError(""); }}
                        className="flex flex-col items-center px-2 py-2 rounded-xl text-xs transition-all"
                        style={{
                          background: isConfirmed
                            ? "rgba(34,197,94,0.25)"
                            : singleReady
                              ? "rgba(34,197,94,0.12)"
                              : isSelected
                                ? "rgba(255,255,255,0.10)"
                                : "rgba(255,255,255,0.04)",
                          border: isConfirmed
                            ? "2px solid #22c55e"
                            : singleReady
                              ? "2px solid rgba(34,197,94,0.6)"
                              : isSelected ? "2px solid rgba(255,255,255,0.5)" : "1px solid rgba(255,255,255,0.08)",
                          color: isConfirmed ? "#86efac" : singleReady ? "#86efac" : isSelected ? "white" : "rgba(255,255,255,0.6)",
                        }}
                      >
                        <span className="font-semibold" style={{ fontSize: "11px" }}>{d.date}</span>
                        <span style={{ fontSize: "10px", opacity: 0.7 }}>{d.time}</span>
                        {isConfirmed && <span style={{ fontSize: "10px" }}><SvgIcon name="check" size={14} /></span>}
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
                    const occTs = instantReelCours(occ.datetime);
                    const hoursAway = (occTs - Date.now()) / 3_600_000;
                    const tooLate = Number.isFinite(hoursAway) && hoursAway < DELAI_ANNULATION_H;
                    const isCancelling = matchingRes && cancellingId === matchingRes.id;
                    return (
                      <div className="flex items-center justify-between gap-2">
                        <span
                          className="text-xs px-3 py-1 rounded-full inline-flex items-center gap-1.5"
                          style={{ background: "rgba(34,197,94,0.15)", color: "#86efac" }}
                        >
                          <SvgIcon name="check" size={14} /> Réservé
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
                      {/* V426 : une activite NON incluse dans le forfait ne doit
                          jamais passer par « Reserver » — elle consommerait une
                          seance pour un evenement a billet separe. Le test
                          `=== false` est volontaire : tant que le backend V426
                          n'est pas deploye le champ est `undefined`, et le
                          parcours d'origine s'affiche a l'identique. */}
                      {occ.inclus_abonnement === false ? (
                        <div className="flex items-center justify-between gap-2 flex-wrap">
                          <span className="text-xs" style={{ color: "rgba(255,255,255,0.65)" }}>
                            Événement — billet séparé
                          </span>
                          <a
                            href={occ.offer_id ? `/?offre=${encodeURIComponent(occ.offer_id)}` : "/"}
                            className="text-xs font-semibold px-4 py-2 rounded-lg"
                            style={{
                              background: "rgba(255,255,255,0.10)",
                              color: "white",
                              border: `1px solid ${COLORS.primary}`,
                            }}
                            data-testid={`event-${occ.course_id}`}>
                            Voir l'événement
                          </a>
                        </div>
                      ) : (
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
                        <button type="button"
                          disabled={isBusy || noSessions
                            || (conditionsRequises && !conditionsOk[`${occ.course_id}_${occ.datetime}`])}
                          onClick={() => handleReserve(occ)}
                          className="text-xs font-semibold px-4 py-2 rounded-lg disabled:opacity-50"
                          style={{ background: COLORS.primary, color: "white" }}
                          data-testid={`reserve-${occ.course_id}`}>
                          {/* ESSAI-7 : pendant l'essai, le bouton nomme ce
                              qu'il fait — « Réserver » seul, au milieu d'une
                              liste de dates, ne dit pas LAQUELLE. */}
                          {isBusy ? "…"
                            : qty > 1 ? `Réserver ${qty} places`
                            : essaiAReserver ? "Réserver cette séance"
                            : "Réserver"}
                        </button>
                      </div>
                      )}

                      {/* ESSAI-5a-1 : ce chemin porte 74 des 132 reservations
                          reelles et n'avait jamais eu de case a cocher. */}
                      <div className="mt-2">
                        <ConditionsParticipation
                          courseId={occ.course_id}
                          accepte={!!conditionsOk[`${occ.course_id}_${occ.datetime}`]}
                          onChange={(v) => setConditionsOk((p) => ({ ...p, [`${occ.course_id}_${occ.datetime}`]: v }))}
                          onRequired={setConditionsRequises}
                        />
                      </div>

                      {occ.inclus_abonnement !== false && qty > 1 && (
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
          {/* ═══ LOT R — LA RECHARGE DU PACK ═══════════════════════════════
              Le CTA n'apparait QUE si le serveur l'a autorise. Il ne se
              montre donc jamais a quelqu'un qui a encore des seances, ni a un
              non-membre, ni a une adhesion echue — la decision du proprietaire
              vit cote serveur, pas ici.
              Quand il n'apparait pas, la RAISON s'affiche : un bouton absent
              sans explication est un bug pour celui qui le cherche. */}
          {data?.recharge?.eligible ? (
            <div className="mt-4">
              <button
                type="button"
                onClick={handleRecharge}
                disabled={rechargeLoading}
                data-testid="recharge-cta"
                className="w-full flex items-center justify-center gap-2 font-semibold rounded-2xl py-4 text-base transition-transform active:scale-95"
                style={{
                  background: `linear-gradient(135deg, ${COLORS.primary}, ${COLORS.secondary})`,
                  color: "#fff",
                  border: "none",
                  opacity: rechargeLoading ? 0.6 : 1,
                  boxShadow: "0 6px 20px rgba(var(--primary-rgb, 217, 28, 210), 0.35)",
                }}
              >
                {rechargeLoading ? "Redirection..." : (
                  <>
                    {/* Icône recharge — SVG inline, jamais un emoji */}
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
                      <path d="M21 12a9 9 0 1 1-3-6.7" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
                      <path d="M21 3v6h-6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                    </svg>
                    {/* Le libelle vient du SERVEUR : ni le nombre de seances ni
                        le prix ne sont ecrits en dur ici. */}
                    {data.recharge.seances
                      ? `Recharger ${data.recharge.seances} séances`
                      : "Recharger mon pack"}
                    {data.recharge.prix != null
                      && ` — ${data.recharge.prix} ${data.recharge.devise || "CHF"}`}
                  </>
                )}
              </button>
            </div>
          ) : (
            data?.recharge?.message ? (
              <p data-testid="recharge-motif" className="text-white/50 text-xs mt-3">
                {data.recharge.message}
              </p>
            ) : (
              remaining <= 0 && (
                <p className="text-white/50 text-xs mt-3">
                  Tu as utilisé toutes tes séances. Contacte ton coach pour renouveler.
                </p>
              )
            )
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
            <div className="mt-4 flex flex-wrap items-center gap-3">
              <button
                type="button"
                onClick={handleShareCopy}
                className="text-xs text-white/40 underline"
                data-testid="copy-own-link"
              >
                {shareCopied ? (
                  <span className="inline-flex items-center gap-1.5"><SvgIcon name="check" size={14} /> Lien copié</span>
                ) : "Copier mon lien personnel"}
              </button>
              {/* V243: partage WhatsApp du lien d'espace. Ouvre WhatsApp (app ou
                  web) avec le message pre-rempli ; l'abonne choisit le
                  destinataire — lui-meme ou un proche. */}
              <a
                href={`https://wa.me/?text=${encodeURIComponent('Mon lien de réservation Afroboost : ' + shareUrl)}`}
                target="_blank"
                rel="noopener noreferrer"
                data-testid="share-whatsapp-link"
                style={{
                  display: 'inline-flex', alignItems: 'center', gap: '6px',
                  background: '#25D366', color: '#fff',
                  padding: '6px 14px', borderRadius: '8px',
                  fontSize: '12px', fontWeight: 600, textDecoration: 'none'
                }}
              >
                <SvgIcon name="phone" size={14} /> Partager via WhatsApp
              </a>
            </div>
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
                : "rgba(var(--primary-rgb, 217, 28, 210), 0.18)",
              color: isEmpty ? "white" : "#F0A8EE",
              border: isEmpty ? "none" : `1px solid ${COLORS.primary}55`,
              boxShadow: isEmpty ? "0 6px 20px rgba(var(--primary-rgb, 217, 28, 210), 0.35)" : "none",
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

        {/* ===== V212: Gérer les membres du groupe (payeur uniquement) ===== */}
        {data?.is_payer && data?.group_members?.length > 0 && (
          <section
            className="rounded-2xl p-4"
            style={{ background: COLORS.panel, border: `1px solid ${COLORS.border}` }}
            data-testid="group-members-management"
          >
            <h2 className="text-base font-semibold mb-3">Membres du groupe</h2>
            <div className="space-y-2">
              {data.group_members.map((member) => (
                <div
                  key={member.slug || member.id}
                  className="flex items-center justify-between gap-2 rounded-xl px-3 py-2"
                  style={{
                    background: member.blocked ? "rgba(239,68,68,0.10)" : "rgba(255,255,255,0.04)",
                    border: member.blocked ? "1px solid rgba(239,68,68,0.3)" : "1px solid rgba(255,255,255,0.08)",
                  }}
                >
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium truncate" style={{ color: member.blocked ? "#fca5a5" : "white" }}>
                      {member.name || "Sans nom"}
                    </p>
                    <p className="text-xs truncate" style={{ color: "rgba(255,255,255,0.5)" }}>
                      {member.email || member.whatsapp || "—"}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={async () => {
                      try {
                        await axios.post(`${API}/subscriber/space/${encodeURIComponent(accessCode)}/member/${encodeURIComponent(member.slug)}/block`);
                        loadSpace();
                      } catch (err) {
                        console.error("[V212] Block error:", err);
                      }
                    }}
                    className="flex-shrink-0 text-xs font-medium rounded-lg px-3 py-1.5 transition-colors"
                    style={{
                      background: member.blocked ? "rgba(34,197,94,0.15)" : "rgba(239,68,68,0.15)",
                      color: member.blocked ? "#86efac" : "#fca5a5",
                      border: member.blocked ? "1px solid rgba(34,197,94,0.3)" : "1px solid rgba(239,68,68,0.3)",
                    }}
                  >
                    {member.blocked ? "Débloquer" : "Bloquer"}
                  </button>
                </div>
              ))}
            </div>
            <p className="text-xs mt-3" style={{ color: "rgba(255,255,255,0.4)" }}>
              Un membre bloqué ne pourra plus réserver de séances.
            </p>
          </section>
        )}

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
            <span className="inline-flex items-center gap-1.5"><SvgIcon name="clipboard" size={14} /> Conditions d'utilisation</span>
          </a>
        </div>
      </div>

      {/* ===== QR Fullscreen Dialog ===== */}
      <Dialog open={qrFullscreen} onOpenChange={setQrFullscreen}>
        <DialogContent className="max-w-sm bg-white">
          <DialogTitle className="text-center text-black text-base font-semibold">QR Code abonné</DialogTitle>
          <div className="flex flex-col items-center gap-3 py-4">
            <QRCodeSVG value={memberSlug ? `${subscriber.code || accessCode}::${memberSlug}` : (subscriber.code || accessCode)} size={280} level="H" includeMargin={false} />
            <p className="text-black font-mono text-sm">{subscriber.code || accessCode}</p>
            <p className="text-black/60 text-xs">Présente ce code au coach à l'entrée</p>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
