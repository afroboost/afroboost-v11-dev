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
  // P1-c : les alternatives sont repliees par defaut. Une seule decision est
  // demandee au participant ; les autres options restent a un clic, jamais
  // cachees. C'est un etat d'ECRAN et rien d'autre — il ne touche ni la
  // selection, ni l'ordre, ni le prix, qui restent des verdicts serveur.
  const [autresOuvertes, setAutresOuvertes] = useState(false);
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

  // La recommandee est en tete parce que le SERVEUR l'y a mise. Les autres
  // suivent dans leur ordre `position`. Aucune recherche, aucun tri, aucun
  // filtre : l'ecran ne redecide rien.
  const autres = offres.slice(1);

  // Une seule fabrique de carte, deux poids. La mise en avant se lit dans la
  // TAILLE et la STRUCTURE, plus seulement dans la couleur : c'etait le
  // reproche fait a l'ecran precedent, six cartes de meme poids.
  const carte = (o, vedette) => {
    if (!o) return null;
    const occupe = enCours === o.id;
    return (
      <div
        key={o.id}
        className={vedette ? "rounded-xl p-4" : "rounded-lg px-3 py-2.5"}
        style={{
          background: vedette ? VOILE : "rgba(255,255,255,0.03)",
          border: `1px solid ${vedette ? PRIMAIRE : BORDURE}`,
        }}
        data-testid={`conversion-offre-${o.id}`}
      >
        {vedette && o.recommended && (
          <p
            className="text-[11px] mb-2 inline-flex items-center gap-1 font-semibold uppercase tracking-wider"
            style={{ color: PRIMAIRE }}
          >
            <SvgIcon name="star" size={12} /> Recommandé pour toi
          </p>
        )}

        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className={vedette ? "font-bold text-base truncate" : "font-medium text-sm truncate"}>
              {o.name}
            </p>
            {o.sessions ? (
              <p className="text-white/50 text-xs mt-0.5">
                {o.sessions} séance{o.sessions > 1 ? "s" : ""}
              </p>
            ) : null}
          </div>
          <p
            className={vedette ? "text-2xl font-bold shrink-0" : "text-sm font-semibold shrink-0"}
            style={{ color: PRIMAIRE }}
          >
            {montant(o.price, o.currency)}
          </p>
        </div>

        {vedette && o.description ? (
          <p className="text-white/50 text-xs mt-2">{o.description}</p>
        ) : null}

        <button
          type="button"
          onClick={() => acheter(o)}
          disabled={!!enCours}
          className={
            vedette
              ? "mt-3 w-full py-3 rounded-xl text-sm font-semibold transition-transform active:scale-95 disabled:opacity-60"
              : "mt-2 w-full py-2 rounded-lg text-xs font-medium transition-transform active:scale-95 disabled:opacity-60"
          }
          style={
            vedette
              ? { background: PRIMAIRE, color: "white", boxShadow: `0 6px 20px ${OMBRE}` }
              : { background: "transparent", color: "white", border: `1px solid ${BORDURE}` }
          }
          data-testid={`conversion-cta-${o.id}`}
        >
          {occupe ? "Redirection…" : vedette ? "Choisir cette offre" : "Choisir"}
        </button>
      </div>
    );
  };

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

      {/* P1-c — UNE DECISION, PAS UN CATALOGUE.
          Le serveur place la recommandee EN TETE : l'ecran prend `offres[0]`
          et le reste en alternatives. Il ne cherche pas, ne trie pas, ne
          filtre pas — c'est la regle de LOT A, et elle survit ici. */}
      <div className="mt-4" data-testid="conversion-recommandee">
        {carte(offres[0], true)}
      </div>

      {autres.length > 0 && (
        <>
          <button
            type="button"
            onClick={() => setAutresOuvertes((v) => !v)}
            className="mt-3 w-full py-2.5 rounded-xl text-xs font-medium inline-flex items-center justify-center gap-1.5 transition-transform active:scale-95"
            style={{ background: "transparent", color: "rgba(255,255,255,0.55)", border: `1px solid ${BORDURE}` }}
            data-testid="conversion-voir-autres"
            aria-expanded={autresOuvertes}
          >
            <SvgIcon name={autresOuvertes ? "chevron-up" : "chevron-down"} size={12} />
            {autresOuvertes ? "Masquer les autres options" : "Voir les autres options"}
          </button>

          {autresOuvertes && (
            <div className="mt-3 space-y-2" data-testid="conversion-alternatives">
              {autres.map((o) => carte(o, false))}
            </div>
          )}
        </>
      )}
    </section>
  );
}
