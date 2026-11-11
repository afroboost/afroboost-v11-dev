import React, { useCallback, useEffect, useState } from 'react';
import {
  CLE_DEPANNAGE, CLE_REPORT, CLE_VUE, ETAPES_ANDROID, ETAPES_IOS, faudraitMontrer,
  installationObligatoire, lireReport, modeInstallation, plateforme, reportSuivant,
} from '../utils/installationPWA';

/**
 * V659 — INSTALLER AFROBOOST SUR SON TÉLÉPHONE.
 *
 * POURQUOI CETTE FENÊTRE. Les notifications n'atteignent un iPhone que si
 * l'application a été ajoutée à l'écran d'accueil — c'est une règle d'Apple,
 * pas un choix d'Afroboost. Un abonné qui reste dans le navigateur ne sera
 * jamais prévenu d'un changement d'horaire. La fenêtre explique cela une fois,
 * clairement, puis se tait.
 *
 * CE QU'ELLE NE FAIT JAMAIS :
 *   - montrer un bouton « Installer » sur iPhone (aucune page web ne le peut :
 *     le bouton ne ferait rien, et l'utilisateur croirait à une panne) ;
 *   - bloquer l'accès au compte, aux réservations ou aux paiements ;
 *   - revenir à chaque connexion : un « Plus tard » est respecté ;
 *   - se montrer à un visiteur de passage.
 *
 * ELLE NE PARLE PAS DE NOTIFICATIONS. Installer et autoriser les notifications
 * sont deux gestes distincts : les mélanger dans une seule fenêtre, c'est
 * perdre les deux. L'activation vit dans `CarteNotifications`, après coup.
 */
export default function InstallationAfroboost({ estAbonne, prompt, onInstallee, onFermer }) {
  const [mode, setMode] = useState(null);
  const [ferme, setFerme] = useState(false);
  const [occupe, setOccupe] = useState(false);
  // V661 — la personne a demandé elle-même à revoir la fenêtre.
  const [forcee, setForcee] = useState(false);
  // V666 — « je n'arrive pas à installer ». Déclaré UNE fois, respecté ensuite :
  // on ne retient personne en otage d'un téléphone récalcitrant.
  const [depannage, setDepannage] = useState(() => {
    try { return localStorage.getItem(CLE_DEPANNAGE) === '1'; } catch (err) { return false; }
  });
  const ouvrirDepannage = useCallback(() => {
    try { localStorage.setItem(CLE_DEPANNAGE, '1'); } catch (err) { /* mode privé */ }
    setDepannage(true);
    setFerme(true);
    if (typeof onFermer === 'function') onFermer();
  }, [onFermer]);

  useEffect(() => {
    try {
      setMode(modeInstallation({
        userAgent: navigator.userAgent,
        standaloneMedia: window.matchMedia('(display-mode: standalone)').matches,
        navigatorStandalone: window.navigator.standalone,
        prompt,
      }));
    } catch (e) { setMode('non-supporte'); }
  }, [prompt]);

  // V660 — « PLUS TARD » REPORTE, IL N'EFFACE PAS. On note la date et le
  // nombre de fois : la fenêtre revient dans une semaine, trois fois au plus,
  // puis se tait pour de bon. `jamaisPlus` n'est écrit QU'APRÈS une
  // installation réussie — la seule raison de ne plus jamais demander.
  const fermer = useCallback((reporter, jamaisPlus) => {
    setFerme(true);
    try {
      if (jamaisPlus) localStorage.setItem(CLE_VUE, '1');
      else if (reporter) {
        localStorage.setItem(CLE_REPORT,
          JSON.stringify(reportSuivant(lireReport(localStorage.getItem(CLE_REPORT)))));
      }
    } catch (e) { /* mode privé : la fenêtre reviendra, sans dommage */ }
    if (typeof onFermer === 'function') onFermer();
  }, [onFermer]);

  const installer = useCallback(async () => {
    if (!prompt || occupe) return;
    setOccupe(true);
    try {
      prompt.prompt();
      const choix = await prompt.userChoice;
      if (choix && choix.outcome === 'accepted') {
        if (typeof onInstallee === 'function') onInstallee();
        fermer(false, true);   // installée : on ne redemande plus jamais
      }
    } catch (e) { /* l'invite a expiré : les instructions restent à l'écran */ }
    setOccupe(false);
  }, [prompt, occupe, onInstallee, fermer]);

  let jamaisPlus = false; let report = null;
  try {
    jamaisPlus = localStorage.getItem(CLE_VUE) === '1';
    report = lireReport(localStorage.getItem(CLE_REPORT));
  } catch (e) { /* mode privé : on propose, c'est le cas le moins pénalisant */ }
  const spontanee = faudraitMontrer({ mode, estAbonne, report, jamaisPlus });
  // V666 — SUR UN MOBILE COMPATIBLE, C'EST UNE ÉTAPE, PAS UNE SUGGESTION.
  // `installationObligatoire` sort d'elle-même pour un visiteur, pour un
  // ordinateur, pour une application déjà installée, et pour qui a déclaré
  // que l'installation échoue. Ailleurs, la fenêtre ne se referme pas d'un
  // geste : ni croix, ni clic à côté, ni « Plus tard ».
  // V669 : la plateforme entre dans la décision — un ordinateur qui sait
  // installer (Chrome de bureau déclenche `beforeinstallprompt`) ne doit
  // jamais se voir imposer l'étape.
  let plate;
  try { plate = plateforme(navigator.userAgent); } catch (err) { plate = undefined; }
  const obligatoire = installationObligatoire({ mode, estAbonne, depannage, plate });
  if (!mode || !estAbonne || mode === 'deja-installee') return null;

  // V661 — APRÈS LES TROIS RAPPELS, UNE PORTE RESTE OUVERTE.
  // La fenêtre ne s'impose plus, mais l'installation reste la condition des
  // notifications sur iPhone : la faire disparaître pour toujours, c'est
  // condamner quelqu'un qui changerait d'avis. Un lien discret prend donc le
  // relais — visible, jamais imposé — jusqu'à l'installation effective.
  // V666 — APRÈS « JE N'ARRIVE PAS À INSTALLER », ON SE TAIT.
  // Sans `depannage` ici, la grande fenêtre revenait dès la visite suivante —
  // sous sa forme reportable, certes, mais elle revenait. Déclarer que ça ne
  // marche pas doit être respecté : il reste le lien discret, rien de plus.
  if (((ferme || !spontanee) && !forcee && !obligatoire) || (depannage && !forcee)) {
    return (
      <button type="button" onClick={() => { setForcee(true); setFerme(false); }}
        data-testid="installation-lien-discret"
        style={{ display: 'inline-flex', alignItems: 'center', gap: 8,
                 background: 'rgba(var(--primary-rgb, 217, 28, 210), .12)',
                 border: '1px solid rgba(var(--primary-rgb, 217, 28, 210), .3)',
                 color: 'var(--primary-color, #D91CD2)', borderRadius: 999,
                 padding: '9px 16px', fontSize: 14, fontWeight: 700,
                 cursor: 'pointer', minHeight: 40 }}>
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor"
             strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M12 3v12m0 0 4-4m-4 4-4-4M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" />
        </svg>
        Installer Afroboost
      </button>
    );
  }

  const C = 'var(--primary-color, #D91CD2)';
  const etapes = mode === 'guide-ios' ? ETAPES_IOS
    : mode === 'instructions-android' ? ETAPES_ANDROID : null;

  return (
    <div
      role="dialog" aria-modal="true" aria-labelledby="af-inst-titre"
      data-testid="installation-afroboost"
      style={{
        position: 'fixed', inset: 0,
        // =============================================================
        // V669 — L'INSTALLATION PASSE DEVANT TOUT
        // =============================================================
        // DÉFAUT REPRODUIT ET MESURÉ dans un vrai navigateur (11/11/2026) :
        // la fenêtre d'installation s'affichait bien, mais DERRIÈRE la grande
        // fenêtre de notification (`NotificationGrande`, z-index 10050) —
        // donc invisible. C'est le « je ne vois aucune demande
        // d'installation » signalé : la fenêtre était là, cachée.
        // Mon propre commentaire V659 disait « INSTALLER AVANT D'ACTIVER, ET
        // DANS CET ORDRE » ; l'empilement disait le contraire.
        zIndex: 10200,
        background: 'rgba(0,0,0,.72)', backdropFilter: 'blur(6px)',
        display: 'flex', alignItems: 'flex-end', justifyContent: 'center',
        padding: 'max(12px, env(safe-area-inset-top)) 12px max(12px, env(safe-area-inset-bottom))',
      }}
      onClick={(e) => {
        // V666 : un clic à côté ne contourne pas une étape obligatoire.
        if (obligatoire) return;
        if (e.target === e.currentTarget) fermer(true);
      }}
    >
      <div
        className="af-inst-panneau"
        style={{
          width: 'min(94vw, 460px)', maxHeight: '85vh', overflowY: 'auto',
          background: 'linear-gradient(160deg,#141018,#0b0b0f)',
          border: '1px solid rgba(var(--primary-rgb, 217, 28, 210), .35)',
          borderRadius: 22, padding: '22px 20px 20px', color: '#fff',
          boxShadow: '0 24px 70px rgba(0,0,0,.6)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 14 }}>
          <img src="/logo192.png" alt="" width="44" height="44"
               style={{ borderRadius: 12, flexShrink: 0 }} />
          <h2 id="af-inst-titre" style={{ margin: 0, fontSize: '1.2rem', fontWeight: 800, lineHeight: 1.25 }}>
            {obligatoire
              ? 'Installe Afroboost pour accéder à ton espace membre'
              : 'Installe Afroboost sur ton téléphone'}
          </h2>
          {!obligatoire && (
          <button type="button" onClick={() => fermer(true)} aria-label="Fermer"
            style={{ marginLeft: 'auto', background: 'rgba(255,255,255,.08)', border: 0,
                     color: '#fff', borderRadius: 999, width: 36, height: 36, cursor: 'pointer',
                     flexShrink: 0, fontSize: 18, lineHeight: '36px', padding: 0 }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                 strokeWidth="2.5" strokeLinecap="round" style={{ display: 'block', margin: '0 auto' }}>
              <path d="M18 6 6 18M6 6l12 12" />
            </svg>
          </button>
          )}
        </div>

        <p style={{ margin: '0 0 14px', color: 'rgba(255,255,255,.82)', fontSize: 15, lineHeight: 1.55 }}>
          {/* V669 — le texte demandé mot pour mot quand c'est une ÉTAPE ; la
              formulation d'origine reste pour la proposition simple. */}
          {obligatoire ? (
            <>Retrouve tes <strong>réservations</strong>, ton <strong>QR code</strong>,
              tes <strong>cours</strong> et tes <strong>rappels</strong> directement depuis
              l’application Afroboost sur ton téléphone.</>
          ) : (
            <>Ton espace devient une application : un geste pour y entrer, et surtout
              les <strong>informations importantes qui arrivent jusqu’à toi</strong>.</>
          )}
        </p>

        <ul style={{ margin: '0 0 18px', padding: 0, listStyle: 'none', display: 'grid', gap: 9 }}>
          {['Tes cours et le calendrier, en un geste',
            'Tes réservations et ton abonnement',
            'Un changement d’horaire ? Tu es prévenu·e',
            'Rien à télécharger sur un magasin d’applications'].map((t) => (
            <li key={t} style={{ display: 'flex', gap: 10, alignItems: 'flex-start',
                                 fontSize: 15, color: 'rgba(255,255,255,.88)', lineHeight: 1.45 }}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke={C}
                   strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"
                   style={{ flexShrink: 0, marginTop: 2 }}>
                <path d="m20 6-11 11-5-5" />
              </svg>
              <span>{t}</span>
            </li>
          ))}
        </ul>

        {mode === 'bouton-natif' && (
          <button type="button" onClick={installer} disabled={occupe}
            data-testid="installation-bouton-natif"
            style={{ width: '100%', minHeight: 54, border: 0, borderRadius: 16,
                     background: C, color: '#fff', fontWeight: 800, fontSize: 17,
                     cursor: occupe ? 'default' : 'pointer', opacity: occupe ? .7 : 1 }}>
            {occupe ? 'Installation…' : 'Installer Afroboost'}
          </button>
        )}

        {etapes && (
          <div data-testid={mode === 'guide-ios' ? 'installation-guide-ios' : 'installation-guide-android'}>
            <p style={{ margin: '0 0 10px', fontWeight: 700, fontSize: 15 }}>
              {mode === 'guide-ios' ? 'Sur iPhone, en 5 gestes :' : 'Sur ton téléphone, en 4 gestes :'}
            </p>
            <ol style={{ margin: 0, padding: 0, listStyle: 'none', display: 'grid', gap: 11 }}>
              {etapes.map((e) => (
                <li key={e.n} style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
                  <span style={{ flexShrink: 0, width: 28, height: 28, borderRadius: 999,
                                 background: 'rgba(var(--primary-rgb, 217, 28, 210), .18)',
                                 color: C, fontWeight: 800, fontSize: 14,
                                 display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    {e.n}
                  </span>
                  <span style={{ fontSize: 15, lineHeight: 1.5, color: 'rgba(255,255,255,.9)' }}>
                    {e.texte}
                  </span>
                </li>
              ))}
            </ol>
          </div>
        )}

        {mode === 'non-supporte' && (
          <p data-testid="installation-non-supporte"
             style={{ margin: 0, fontSize: 15, lineHeight: 1.5, color: 'rgba(255,255,255,.82)' }}>
            Ce navigateur ne permet pas d’ajouter Afroboost à l’écran d’accueil.
            Depuis ton téléphone, ouvre afroboost.com dans Safari (iPhone) ou
            Chrome (Android) : l’installation y est possible. Ton compte, tes
            réservations et tes paiements fonctionnent normalement ici.
          </p>
        )}

        {/* ===============================================================
            V666 — OBLIGATOIRE N'EST PAS « SANS ISSUE »
            ===============================================================
            Sur un mobile compatible, « Plus tard » disparaît : l'installation
            est une étape. Mais il reste UNE porte, et elle est honnête — pas
            un bouton caché, pas un contournement : « Je n'arrive pas à
            installer ». Un téléphone trop ancien, un navigateur restreint, un
            réglage d'entreprise : cela existe, et personne ne doit perdre
            l'accès à ses paiements, à l'assistance ou à son compte pour
            autant. Le choix est mémorisé : on ne le redemande pas à chaque
            visite. */}
        {obligatoire ? (
          <button type="button" onClick={ouvrirDepannage}
            data-testid="installation-depannage"
            style={{ width: '100%', marginTop: 16, minHeight: 46, background: 'transparent',
                     border: '1px solid rgba(255,255,255,.18)', borderRadius: 14,
                     color: 'rgba(255,255,255,.72)', fontSize: 14, cursor: 'pointer',
                     lineHeight: 1.35, padding: '8px 12px' }}>
            Je n’arrive pas à installer — accéder quand même
          </button>
        ) : (
          <button type="button" onClick={() => fermer(true)} data-testid="installation-plus-tard"
            style={{ width: '100%', marginTop: 16, minHeight: 46, background: 'transparent',
                     border: '1px solid rgba(255,255,255,.18)', borderRadius: 14,
                     color: 'rgba(255,255,255,.72)', fontSize: 15, cursor: 'pointer' }}>
            Plus tard
          </button>
        )}
      </div>
    </div>
  );
}
