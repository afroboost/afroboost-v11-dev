// LOT A — L'ECRAN D'APRES-ESSAI
//
// Il n'apparait QUE lorsque le serveur dit que le droit est ouvert. Ce composant
// ne decide RIEN : ni qui est eligible, ni quelles offres existent, ni a quel
// prix. Il affiche ce que `GET /subscriber/space/{code}/conversion` lui rend,
// et repasse par le serveur pour acheter. C'est voulu — l'interface n'est
// jamais une barriere de securite metier, et une garde recopiee ici serait une
// seconde verite a maintenir.
//
// FICHIER SEPARE, ET C'EST DELIBERE : retirer l'ecran (rollback UI seul) tient
// dans la suppression d'un import et d'une balise, sans toucher aux protections
// serveur, qui restent en place.
//
// COULEURS : `--primary-color` du coach partout, `#D91CD2` uniquement en valeur
// de secours dans le `var()`. Aucun hexadecimal impose.
import React, { useEffect, useRef, useState } from "react";
import axios from "axios";
import SvgIcon from "./SvgIcon";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "";
const API = `${BACKEND_URL}/api`;

const PRIMAIRE = "var(--primary-color, #D91CD2)";
const OMBRE = "rgba(var(--primary-rgb, 217, 28, 210), 0.35)";
const VOILE = "rgba(var(--primary-rgb, 217, 28, 210), 0.10)";
const PANNEAU = "rgba(255,255,255,0.04)";
const BORDURE = "rgba(255,255,255,0.08)";

// Le montant vient du serveur : on ne fait que le mettre en forme. Aucun prix
// n'est ecrit dans ce fichier.
function montant(prix, devise) {
  const n = Number(prix);
  if (!Number.isFinite(n)) return "";
  const entier = Math.round(n) === n;
  return `${devise || "CHF"} ${entier ? n : n.toFixed(2)}`;
}

export default function ConversionApresEssai({ code, prenom }) {
  const [etat, setEtat] = useState(null);
  const [chargement, setChargement] = useState(true);
  const [erreur, setErreur] = useState("");
  const [enCours, setEnCours] = useState("");
  // Le fetch ne depend QUE du code, une valeur primitive : faire dependre cet
  // effet d'un objet relancerait un appel a chaque rendu — la boucle d'appels
  // API qui a sature le serveur en V305.
  const demande = useRef("");

  useEffect(() => {
    const c = (code || "").trim();
    if (!c || demande.current === c) return;
    demande.current = c;
    let vivant = true;
    setChargement(true);
    axios
      .get(`${API}/subscriber/space/${encodeURIComponent(c)}/conversion`)
      .then((r) => {
        if (!vivant) return;
        setEtat(r.data?.conversion || null);
      })
      .catch(() => {
        // Un echec de lecture ne casse pas l'espace : l'ecran ne s'affiche pas,
        // le reste de la page vit sa vie.
        if (vivant) setEtat(null);
      })
      .finally(() => {
        if (vivant) setChargement(false);
      });
    return () => {
      vivant = false;
    };
  }, [code]);

  const acheter = async (offre) => {
    if (enCours) return;
    setEnCours(offre.id);
    setErreur("");
    try {
      const r = await axios.post(
        `${API}/subscriber/space/${encodeURIComponent(code)}/conversion/checkout`,
        // L'origine de retour n'est PAS envoyee : le serveur la connait
        // (`FRONTEND_URL`). La laisser au navigateur en ferait une redirection
        // ouverte au sortir du paiement Stripe.
        { offer_id: offre.id }
      );
      const url = r.data?.checkout_url;
      if (url) {
        window.location.href = url;
        return;
      }
      setErreur("Le paiement n'a pas pu démarrer. Réessaie dans un instant.");
    } catch (e) {
      setErreur(
        e?.response?.data?.detail ||
          "Le paiement n'a pas pu démarrer. Réessaie dans un instant."
      );
    } finally {
      setEnCours("");
    }
  };

  // CHARGEMENT — un bloc discret, jamais un ecran vide qui saute ensuite.
  if (chargement) {
    return (
      <section
        className="rounded-2xl p-5"
        style={{ background: PANNEAU, border: `1px solid ${BORDURE}` }}
        data-testid="conversion-chargement"
      >
        <div className="h-4 w-2/3 rounded" style={{ background: "rgba(255,255,255,0.08)" }} />
        <div className="h-3 w-1/2 rounded mt-3" style={{ background: "rgba(255,255,255,0.06)" }} />
      </section>
    );
  }

  if (!etat || !etat.eligible) return null;

  // DEJA CONVERTI — on cesse de traiter la personne comme un prospect. Un mot,
  // et rien a vendre.
  if (etat.state === "purchased") {
    return (
      <section
        className="rounded-2xl p-4 flex items-center gap-3"
        style={{ background: VOILE, border: `1px solid ${PRIMAIRE}` }}
        data-testid="conversion-terminee"
      >
        <span style={{ color: PRIMAIRE }}>
          <SvgIcon name="check" size={18} />
        </span>
        <p className="text-sm text-white/80">
          Tu as choisi ta formule — bienvenue dans l'aventure.
        </p>
      </section>
    );
  }

  const offres = Array.isArray(etat.offers) ? etat.offers : [];
  // AUCUNE OFFRE DECLAREE : le coach n'a encore rien coche. On n'affiche rien
  // plutot qu'un cadre vide — un « aucune offre disponible » serait un message
  // d'erreur adresse a la mauvaise personne.
  if (etat.state !== "open" || offres.length === 0) return null;

  return (
    <section
      className="rounded-2xl p-5"
      style={{
        background: PANNEAU,
        border: `1px solid ${PRIMAIRE}`,
        boxShadow: `0 8px 30px ${OMBRE}`,
      }}
      data-testid="conversion-apres-essai"
    >
      <p
        className="text-xs uppercase tracking-wider inline-flex items-center gap-1.5"
        style={{ color: PRIMAIRE }}
      >
        <SvgIcon name="sparkles" size={14} /> Continue l'aventure
      </p>
      <h2 className="text-lg font-bold mt-1">
        {prenom ? `Bravo ${prenom}, ` : ""}ton premier cours est terminé.
      </h2>
      <p className="text-white/60 text-sm mt-1">
        Choisis la formule qui te convient.
      </p>

      {erreur && (
        <p
          className="text-xs mt-3 px-3 py-2 rounded-lg"
          style={{ background: "rgba(239,68,68,0.15)", color: "#fca5a5" }}
          data-testid="conversion-erreur"
        >
          {erreur}
        </p>
      )}

      <div className="mt-4 space-y-3">
        {offres.map((o) => {
          const occupe = enCours === o.id;
          return (
            <div
              key={o.id}
              className="rounded-xl p-4"
              style={{
                background: o.recommended ? VOILE : "rgba(255,255,255,0.03)",
                border: `1px solid ${o.recommended ? PRIMAIRE : BORDURE}`,
              }}
              data-testid={`conversion-offre-${o.id}`}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="font-semibold truncate">{o.name}</p>
                  {o.sessions ? (
                    <p className="text-white/50 text-xs mt-0.5">
                      {o.sessions} séance{o.sessions > 1 ? "s" : ""}
                    </p>
                  ) : null}
                </div>
                <p className="text-xl font-bold shrink-0" style={{ color: PRIMAIRE }}>
                  {montant(o.price, o.currency)}
                </p>
              </div>

              {o.recommended && (
                <p
                  className="text-[11px] mt-2 inline-flex items-center gap-1"
                  style={{ color: PRIMAIRE }}
                >
                  <SvgIcon name="star" size={12} /> Offre recommandée
                </p>
              )}

              {o.description ? (
                <p className="text-white/50 text-xs mt-2">{o.description}</p>
              ) : null}

              <button
                type="button"
                onClick={() => acheter(o)}
                disabled={!!enCours}
                className="mt-3 w-full py-3 rounded-xl text-sm font-semibold transition-transform active:scale-95 disabled:opacity-60"
                style={
                  o.recommended
                    ? { background: PRIMAIRE, color: "white", boxShadow: `0 6px 20px ${OMBRE}` }
                    : { background: VOILE, color: "white", border: `1px solid ${PRIMAIRE}` }
                }
                data-testid={`conversion-cta-${o.id}`}
              >
                {occupe ? "Redirection…" : o.recommended ? "Continuer" : "Choisir"}
              </button>
            </div>
          );
        })}
      </div>
    </section>
  );
}
