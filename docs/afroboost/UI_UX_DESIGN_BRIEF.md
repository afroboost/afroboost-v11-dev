# UI/UX DESIGN BRIEF — Afroboost (référence de tout le site)

> Audit du design **réel** (code `0a575c9b`, 19/10/2026) puis règles de référence. Principe : **réutiliser et unifier
> l'existant**, pas de refonte totale. Règles absolues déjà en vigueur (CLAUDE.md) : couleurs du coach partout via
> variables CSS, icônes SVG uniquement, design épuré (≤ 2 actions visibles par carte, reste dans « ⋯ »), pas de flash
> de couleur au chargement, jamais de boucle d'appels.

## 1. Design system actuel (constat)

| Domaine | Réalité |
|---|---|
| Tokens de marque | `index.css` : `--primary-color:#D91CD2`, `--primary-rgb:217,28,210`, `--secondary-color:#8b5cf6`, `--background-color:#000`, `--glow-color(-strong)`, `--radius:.5rem` |
| Thème du coach | `utils/themeColor.js` pose `--primary-color`/`--primary-rgb`, met en cache `afroboost_theme_colors` ; script anti-flash dans `public/index.html` (ES5, avant le CSS) ✅ |
| Conflit | tokens shadcn **neutres** (`--primary: 0 0% 9%`) : `bg-primary` Tailwind donnerait du noir, pas la marque |
| Écarts mesurés | 2 000 hex en dur (dont 767 en repli légitime dans `var()`) ; `#8B5CF6` ×162 en dur (jamais via `--secondary-color`) ; `rgba(217,28,210,…)` en dur ×29 ; classes Tailwind purple/pink/violet/fuchsia ×151 (ne suivent pas le thème) |
| Typographie | pile système (-apple-system…), aucune webfont ; tailles souvent en ligne |
| Styles | 6 187 `style={{…}}` en ligne ; classes CSS `.btn-primary`, `.glass`, `.card-gradient`, `.card-dark`, `.neon-border`, `.neon-input` ; dégradé `linear-gradient(135deg, var(--primary-color), #8B5CF6)` ×256 |
| Composants partagés | `SvgIcon` (≈ 96 icônes, 1 054 usages) ✅ ; `EtatChargement` (`Compteur`, `SectionErreur`, `BanniereSession` non monté) ; `AfroboostAudioPlayer` ; `VideoTrimEditor` ; `MediaReponse`/`CarteMedia` |
| shadcn | 46 composants présents, **1 seul utilisé** (`Dialog`, espace membre) ; aucun Toaster monté |
| Doublons | 2 lecteurs audio, 3 `OfferCard`, 2 `QRScannerModal`, 2 sélecteurs de langue, 2 jeux d'icônes (SvgIcon + lucide-react dans 26 fichiers), emojis restants (840 hors commentaires) |
| Retours | 158 `alert()`, 39 `window.confirm()` |
| Rayons | 8 / 10 / 12 px mélangés (`borderRadius` ×1 520, `rounded-lg` ×338) |
| Breakpoints | Tailwind par défaut + media queries 480 / 639 / 767-768 / 1023-1024 + seuil JS `SEUIL_MOBILE = 720` + `[data-appareil="mobile"]` |
| Accessibilité | 312 `aria-label`, 29 `role="dialog"`, 55 `focus-visible`, cibles 44 px partielles, 18 gestions de Échap, 8 `prefers-reduced-motion`, pas de piège de focus générique |
| Live (BoostTribe) | design system **différent** : `theme.json` (`#7A5CFF`/`#E24A9E`, Space Grotesk/Inter) et habillage Afroboost `#9f2d70`/`#132058` — **≠ #D91CD2** |

## 2. Palette de référence
| Rôle | Valeur | Usage |
|---|---|---|
| Fond | `#000000` (`--background-color`) | fond global, surfaces sombres |
| Marque | `#D91CD2` (repli de `var(--primary-color)`) | actions principales, focus, sélection, liens |
| Marque transparente | `rgba(var(--primary-rgb), 0.08 → 0.5)` | fonds de cartes actives, bordures |
| Texte | `#FFFFFF` ; secondaire `rgba(255,255,255,0.68)` (jamais < 0,5 d'opacité : contraste) | |
| Secondaire | `var(--secondary-color, #8B5CF6)` | dégradés uniquement |
| États (sémantiques, hors marque) | succès `rgb(134,239,172)` / `#22C55E` ; erreur `rgb(252,165,165)` / `#EF4444` ; attention `#F59E0B` | badges, messages |
**Règle** : une couleur de marque n'est jamais écrite en dur ; elle passe par `var(--primary-color, #D91CD2)` ou `rgba(var(--primary-rgb, 217, 28, 210), a)`. Les couleurs d'état restent fixes (lisibilité). Le Live doit à terme lire les mêmes variables (aujourd'hui `#9f2d70`).

## 3. Typographie
Pile système (rapide, lisible). Échelle recommandée : 12 (méta), 13-14 (corps dashboard), 15-16 (corps public), 18-20 (titres de section), 28-40 (hero). Graisse 600-700 pour titres et boutons. Pas d'ajout de webfont sans besoin (performance mobile).

## 4. Boutons
| Variante | Style de référence | Existant à réutiliser |
|---|---|---|
| Principal | fond `var(--primary-color)`, texte blanc, rayon 10, hauteur ≥ 40 (≥ 44 mobile) | `.btn-primary`, styles `bouton(true)` |
| Secondaire | fond `rgba(255,255,255,0.07)`, bordure `rgba(var(--primary-rgb),0.45)` | `bouton(false)`, `stylePetitBouton` |
| Discret / lien | texte couleur marque éclaircie (`color-mix(… 80%, white)`) | `styleLien` |
| Danger | bordure/texte erreur, confirmation explicite | — |
États : survol (luminosité +5 %), focus (anneau 2 px marque, `focus-visible`), désactivé (opacité 0,5-0,6 + `cursor:not-allowed` + raison visible si utile), chargement (spinner `SvgIcon loader` + libellé « …ement »). **Max 2 actions visibles par carte**.

## 5. Formulaires
Champs sombres (`rgba(0,0,0,0.32)`), bordure marque transparente, libellé au-dessus, aide sous le champ, erreur en rouge sous le champ (pas d'`alert`). Le texte saisi n'est **jamais** perdu sur erreur. Champs requis marqués ; validation serveur toujours prioritaire.

## 6. Cartes
Fond `rgba(255,255,255,0.04-0.08)`, bordure `rgba(255,255,255,0.1)` ou marque si active, rayon 12, padding 12-16. Une carte = une idée, au plus 2 actions, le reste dans « ⋯ ». Emplacement vide → « + Ajouter », jamais une grande carte vide.

## 7. Modales et tiroirs
Plein écran sur mobile, centrée ≤ 640 px sur desktop, fond `rgba(0,0,0,0.7)`, fermeture par ✕, Échap et clic extérieur, `role="dialog"` + `aria-modal`. Un éditeur s'ouvre en modale/tiroir, jamais au milieu de la page. Référence : fenêtre « Ajouter un média » (V620).

## 8. Navigation
Vitrine : barre haute (logo, langue, Live, menu). Dashboard : onglets repliables (`coach-nav`) + sous-cartes « Gestion ». Espace membre : menu rapide. Pas de routeur : documenter tout nouvel écran dans `APP_FLOW.md` §0.1.

## 9. Tabs
Pastilles (rayon 999) : actif = fond marque ; inactif = secondaire. Compteur entre parenthèses calculé **avant** filtrage.

## 10. Alertes / retours
Cible : bandeau intégré dans la section (succès vert, erreur rouge, info neutre) + toast discret pour les actions rapides. Remplacer progressivement les 158 `alert()` (en commençant par le dashboard). Messages en français simple, qui disent quoi faire (« Réessayer », « Recharger »).

## 11. Badges
Pastille (rayon 999, 11 px, bordure transparente) : statut (« À répondre », « Remis ✓ », « Vidéo demandée »), crédits, fonctionnalités Live (cible : « Live ✓ », « Enregistrement 🔒 » → icône SVG cadenas, pas d'emoji).

## 12. Lecteurs audio / vidéo / médias
Audio : **`AfroboostAudioPlayer`** seul (retirer `AudioPlayer` historique à terme). Vidéo : `preload="metadata"`, jamais d'autoplay sonore, image d'aperçu à 15 % de la durée, `playsInline`. Médias choisis via une bibliothèque (jamais d'URL technique saisie ou affichée). E-mails : carte miniature + « ▶ Voir la vidéo ».

## 13. Dashboard
Densité moyenne, une colonne de travail, sections repliables (accordéon fermé par défaut), chiffres en tuiles lues **depuis le serveur** (jamais la longueur d'une page). Fil de conversation : bulles envoyé/reçu, « Voir plus ».

## 14. Tables
Desktop : tableau avec en-tête collant, pagination ≤ 50. Mobile : cartes à la place du tableau. Colonne vide → « — » (jamais « null »).

## 15. Crédit utilisateur (cible Live)
Solde toujours visible (chip « 850 crédits »), historique en liste chronologique (+ vert, − neutre, motif, date, auteur), coût affiché **avant** l'action (« Démarrer — 10 crédits »), état « crédits insuffisants » avec lien « Recharger ».

## 16. Statut Live
Pastille « LIVE EN COURS » (point rouge animé, respect de `prefers-reduced-motion`), compteur de participants, durée ; états : en attente / en direct / terminé / connexion perdue (reconnexion…).

## 17. Responsive
| Format | Largeur de test | Règles |
|---|---|---|
| Mobile | **390 px** (et 360) | une colonne, gouttières 16 px, zéro défilement horizontal, cibles ≥ 44 px, éditeurs en plein écran |
| Tablette | 768 px | deux colonnes possibles, modales centrées |
| Desktop | 1280 px | grille 2-3 colonnes, largeur de lecture ≤ 720 px pour le texte |
Breakpoint mobile de référence : **720 px** (déjà utilisé par `useLargeurEcran`) ; aligner progressivement les media queries.

## 18. Espacements
Échelle 4 / 8 / 12 / 16 / 24 / 32. Rayons : 8 (champs), 10 (boutons), 12 (cartes), 999 (pastilles).

## 19. Accessibilité
Contraste ≥ 4,5:1 (texte blanc ≥ 0,5 d'opacité sur noir), `focus-visible` sur tout élément interactif, `aria-label` sur boutons-icônes, ordre de tabulation logique, piège de focus dans les modales, `prefers-reduced-motion`, langue `lang="fr"`. Zones tactiles **≥ 44 × 44 px**.

## 20. États d'interface
| État | Règle |
|---|---|
| Focus | anneau 2 px marque, jamais supprimé |
| Survol | légère élévation de luminosité, pas d'effet sur mobile |
| Désactivé | opacité 0,5-0,6 + raison si non évidente |
| Chargement | squelette pour les listes, spinner + libellé pour les actions ; jamais de « 0 » trompeur pendant le chargement |
| Succès | message vert court, l'écran montre l'état serveur relu |
| Erreur | message rouge actionnable, données saisies conservées, « Réessayer » |

## 21. Grands écrans couverts
Vitrine (hero, offres, cours, événements, partenaires), réservation + paiement, essai / invitation / Pass Duo, événement, espace membre, parrainage, chat widget, dashboard coach (réservations, gestion, codes, contacts, campagnes, prospection, invitation, conversations, corbeille), super-admin (cockpit, analytics), vitrine partenaire, Live (iframe), écran admin crédits/droits (cible).

## 22. Recommandations (sans refonte)
1. Créer 4 composants partagés réutilisant les styles existants : `Bouton`, `Modale`, `Retour` (bandeau/toast), `Onglets`.
2. Remplacer `#8B5CF6` en dur par `var(--secondary-color, #8B5CF6)` et les classes Tailwind purple/pink par des variables.
3. Brancher le Live sur les mêmes variables de marque.
4. Supprimer le code mort UI (2 sauvegardes CoachDashboard, CoachVitrine, 45 composants shadcn inutilisés, `ui/index.jsx`).
5. Remplacer les emojis restants par `SvgIcon` à chaque écran touché (règle déjà en place).
