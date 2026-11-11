# Validation mobile — Installation et notifications push (V659 → V662f)

> Protocole à suivre sur de **vrais téléphones**. Tout est marqué **NON TESTÉ**
> jusqu'à ce que tu l'aies fait toi-même. Aucune case ne se coche depuis un
> navigateur de bureau : ni l'installation, ni le push, ni l'application fermée.

**Commits concernés** : `d70fc3d3` → `46fe924b` · **Service Worker** : `afroboost-v666`

---

## ⛔ BLOCAGE À LEVER AVANT DE COMMENCER

**Il n'existe aucune préproduction HTTPS.** Vérifié le 11/11/2026 :
`staging.`, `preprod.`, `test.` et `dev.afroboost.com` n'ont **aucun
enregistrement DNS**. Seul `afroboost.com` (production) répond.

Or l'installation PWA **et** les notifications push **exigent HTTPS avec un
certificat valide**. Un téléphone ne peut pas les tester sur `localhost`.

**Donc : ce protocole n'est pas exécutable aujourd'hui.** Trois sorties
possibles — c'est toi qui choisis, je n'en ai engagé aucune :

| Option | Ce qu'il faut faire | Remarque |
|---|---|---|
| **A. Préproduction Coolify** | créer une 2ᵉ application depuis le même dépôt, sur `preprod.afroboost.com`, avec sa **propre base** | le plus propre ; isole totalement la production |
| **B. Tunnel HTTPS temporaire** | exposer le build local derrière un tunnel (certificat valide) | rapide, mais **publie** ton build de travail sur Internet le temps du test |
| **C. Production, après ton GO** | déployer, puis tester avec des **comptes de test** | aucune infrastructure à créer ; mais le test a lieu sur le site réel |

> ⚠️ L'option A demande une base **séparée**. Pointer une préproduction sur la
> base de production ferait écrire de vraies notifications à de vrais clients.

---

## Recette de l'option A — une préproduction qui ne peut RIEN envoyer

Vérifié dans le code avant d'écrire ceci, pas supposé.

### 1. L'application Coolify

| Réglage | Valeur |
|---|---|
| Dépôt / branche | `afroboost/afroboost-v11-dev` · la branche à tester |
| Build | le **`Dockerfile`** à la racine (comme la production) |
| Domaine | `preprod.afroboost.com` |
| Health Check | **`/healthz`**, port **8080** — jamais `/health`, qui ping Mongo et redémarrerait en boucle sur un hoquet d'Atlas |

DNS : un enregistrement Cloudflare avec **proxy actif** — c'est lui qui fournit
le certificat HTTPS valide, sans lequel ni l'installation ni le push ne
fonctionnent.

### 2. Les variables à POSER

| Variable | Valeur | Pourquoi |
|---|---|---|
| `MONGO_URL` | le même cluster | — |
| `DB_NAME` | **`afroboost_preprod`** | ⚠️ **LE POINT CRITIQUE.** Une base distincte. Pointer la préproduction sur la base de production ferait écrire de vraies notifications à de vrais clients, et les boucles horaires (rappels, campagnes, relances J+3) tourneraient sur tes vraies données. |
| `JWT_SECRET` | une valeur **propre à la préproduction** | sans lui, l'auth retombe sur `X-User-Email` falsifiable — et les trois preuves d'identité de V662 ne fonctionnent pas du tout |
| `VAPID_PUBLIC_KEY` + `VAPID_PRIVATE_KEY` | les mêmes que la production, c'est sans risque | les abonnements push vivent dans la base **de la préproduction** : aucun appareil réel n'y est inscrit. Le front lit la clé publique au runtime (`GET /api/push/vapid-key`), donc **aucune variable de build** n'est nécessaire. |

### 3. Les variables à NE SURTOUT PAS POSER

Les laisser vides rend l'envoi **techniquement impossible**, ce qui vaut mieux
que de compter sur un drapeau :

| Variable | Si absente |
|---|---|
| `RESEND_API_KEY` | aucun e-mail ne peut partir (17 points d'appel) |
| `META_WHATSAPP_TOKEN` | aucun WhatsApp |
| `STRIPE_SECRET_KEY` | aucun paiement — ou **uniquement** une clé `sk_test_…` |
| `PAWAPAY_API_TOKEN` · `CINETPAY_API_KEY` | aucun Mobile Money |
| `OPENAI_API_KEY` | pas d'IA (inutile pour ce test) |

Les drapeaux de campagne (`feature_flags`) sont à **False** par défaut dans une
base neuve : aucune campagne ni relance ne peut démarrer.

### 4. Empêcher l'indexation et les visiteurs

Le dépôt sert un `robots.txt` qui **autorise** les moteurs de recherche : une
préproduction sur un domaine public serait indexée (contenu dupliqué, site de
test visible). Avant d'ouvrir le domaine, poser **l'un** des deux :

- **Cloudflare Access** (Zero Trust) avec code à usage unique par e-mail — ton
  téléphone peut s'authentifier, les robots non. **Recommandé.**
- ou une règle WAF Cloudflare bloquant les robots sur ce nom d'hôte.

### 5. Les comptes de test à créer (dans la base de préproduction UNIQUEMENT)

| Quoi | Où | Minimum |
|---|---|---|
| Un **code d'accès** membre | `discount_codes` | le code, les séances, le propriétaire |
| Une **réservation** à venir | `reservations` | pour déclencher un rappel (section 4) |
| Un **compte coach** | `coach_auth` | e-mail + mot de passe de test |

N'importe quel e-mail de test suffit : sans `RESEND_API_KEY`, rien ne part.

---

## Avant de commencer — à préparer

- [ ] Un **compte membre de test** (code d'accès dédié, adresse que tu relèves)
- [ ] Un **compte coach de test**, ou ton compte coach avec la certitude de ne
      déclencher aucun envoi réel
- [ ] Un **iPhone** et un **Android** sous la main
- [ ] Accès aux **logs Coolify** (Lines = 5000) pour lire les traces `[V662…]`

**N'utilise aucune notification destinée à un vrai client.**

---

## 1. iPhone — installation

| # | Geste | Attendu | Résultat |
|---|---|---|---|
| 1.1 | Ouvrir le site dans **Safari** (pas Chrome iOS) | la fenêtre « Installer Afroboost » apparaît dans ton espace | **NON TESTÉ** |
| 1.2 | Lire le guide | **5 étapes**, et **AUCUN bouton d'installation** (impossible sur iPhone) | **NON TESTÉ** |
| 1.3 | Suivre : Partager → Sur l'écran d'accueil | l'icône apparaît | **NON TESTÉ** |
| 1.4 | Rouvrir depuis l'icône | la fenêtre d'installation **ne revient plus** | **NON TESTÉ** |
| 1.5 | Toucher « Plus tard » (avant installation) | la fenêtre se ferme, et un lien discret **« Installer Afroboost »** reste visible | **NON TESTÉ** |

## 2. Android — installation

| # | Geste | Attendu | Résultat |
|---|---|---|---|
| 2.1 | Ouvrir dans **Chrome** | la fenêtre propose un **vrai bouton** d'installation | **NON TESTÉ** |
| 2.2 | Toucher le bouton | l'invite système s'affiche, l'application s'installe | **NON TESTÉ** |
| 2.3 | Rouvrir depuis l'icône | plus aucune proposition | **NON TESTÉ** |

## 3. Activer les notifications (les deux téléphones)

| # | Geste | Attendu | Résultat |
|---|---|---|---|
| 3.1 | Activer depuis la carte des notifications | l'autorisation système est demandée **une seule fois** | **NON TESTÉ** |
| 3.2 | Accepter | l'appareil est enregistré | **NON TESTÉ** |
| 3.3 | Vérifier en base : `push_subscriptions` de cet appareil | `push_verifie: true`, `push_preuve` = `espace_b3s1` (membre) ou `coach_jwt` (coach), `preuve_exp` présent | **NON TESTÉ** |
| 3.4 | Refuser l'autorisation (sur un 2ᵉ appareil) | **aucune promesse** de notification n'est affichée | **NON TESTÉ** |

> Si `push_verifie` est **absent ou faux** après 3.2, **arrête-toi** : l'appareil
> ne recevra que des notifications neutres. Signale-le-moi.

## 4. Recevoir une notification, application FERMÉE

C'est **le** test qu'aucune simulation ne remplace.

| # | Geste | Attendu | Résultat |
|---|---|---|---|
| 4.1 | **Fermer complètement** l'application (pas seulement l'arrière-plan) | — | — |
| 4.2 | Déclencher un rappel de test sur une réservation de test | la notification **arrive** sur le téléphone | **NON TESTÉ** |
| 4.3 | Lire son contenu | nom du cours, heure, lieu — et **AUCUN code d'accès** | **NON TESTÉ** |
| 4.4 | Attendre un second rappel du même cours | il **remplace** le premier (il ne s'empile pas) | **NON TESTÉ** |
| 4.5 | Mettre le téléphone en veille 30 min, puis déclencher | elle arrive quand même (TTL 3600 s, urgence `high`) | **NON TESTÉ** |

## 5. Toucher la notification

| # | Geste | Attendu | Résultat |
|---|---|---|---|
| 5.1 | Toucher la notification | Afroboost s'ouvre | **NON TESTÉ** |
| 5.2 | Regarder où elle ouvre | **le chat** — c'est normal et voulu : le code d'accès a été **retiré** du push (V661b), car `/push/subscribe` accepte encore une adresse non vérifiée | **NON TESTÉ** |
| 5.3 | Vérifier l'absence de fuite | aucun `/espace/<CODE>` dans la notification | **NON TESTÉ** |

> **Attente à corriger** : « toucher → ouvrir directement le cours » n'est **pas**
> livré. Il demande d'abord soit une route d'espace sans code, soit
> l'authentification de `/push/subscribe`. C'est un lot séparé.

## 6. La grande fenêtre sur mobile

| # | À regarder | Attendu | Résultat |
|---|---|---|---|
| 6.1 | Largeur | occupe **94 %** de l'écran (max 520 px) | **NON TESTÉ** |
| 6.2 | Texte | **entier**, jamais coupé à 60 caractères, lisible sans zoom | **NON TESTÉ** |
| 6.3 | Boutons | atteignables au pouce (**52 px** de haut) | **NON TESTÉ** |
| 6.4 | iPhone à encoche | rien sous l'encoche ni sous la barre du bas | **NON TESTÉ** |
| 6.5 | Fil du membre | prochaine séance, séances restantes, échéance d'abonnement | **NON TESTÉ** |

## 7. Déconnexion — le contenu privé doit disparaître

| # | Geste | Attendu | Résultat |
|---|---|---|---|
| 7.1 | Se déconnecter de l'espace **membre** | logs : `[V662e] deconnexion membre : N appareil(s) denoue(s), complet=True` | **NON TESTÉ** |
| 7.2 | Déclencher une notification | elle arrive, mais **neutre** : « Vous avez une notification… » — **ni nom de cours, ni heure** | **NON TESTÉ** |
| 7.3 | Se déconnecter de l'interface **coach** | logs : `[V662f] deconnexion coach : N appareil(s) denoue(s), complet=True` | **NON TESTÉ** |
| 7.4 | Déclencher une notification coach | **neutre** également | **NON TESTÉ** |
| 7.5 | Vérifier l'autre téléphone, **resté connecté** | il reçoit toujours le **détail** (une session ne ferme pas l'autre) | **NON TESTÉ** |

> Si `complet=False` apparaît : **dis-le-moi**. Cela voudrait dire que plus de
> 500 appareils portaient cette session et que la révocation est partielle.

## 8. Reconnexion — tout revient seul

| # | Geste | Attendu | Résultat |
|---|---|---|---|
| 8.1 | Se reconnecter (membre, puis coach) | — | — |
| 8.2 | Déclencher une notification | le **détail est de retour**, sans avoir rien réactivé à la main | **NON TESTÉ** |
| 8.3 | Vérifier en base | `push_verifie: true` à nouveau | **NON TESTÉ** |

## 9. Deux parcours, séparément

| # | Parcours | Résultat |
|---|---|---|
| 9.1 | **Membre** : sections 1 à 8 depuis l'espace, avec un code de test | **NON TESTÉ** |
| 9.2 | **Coach** : sections 1 à 8 depuis le tableau de bord | **NON TESTÉ** |

---

## La limite de 500 appareils — mesurée, pas supposée

Mesure du **11/11/2026** sur la base de production :

| Mesure | Valeur |
|---|---|
| Abonnements portant un `preuve_jti` | **0** (le champ est neuf) |
| Pire accumulation sur **un identifiant** | **230** (compte coach) |
| Suivants | 32 · 27 · 10 |
| Plafond du dénouement | **500** |

**La limite n'est pas atteignable avec ces données.** Et le dénouement filtre
par **session**, pas par compte : les 230 appareils du coach se répartissent sur
toutes ses connexions passées, jamais sur une seule. Un appareil qui change
d'endpoint **remplace** sa ligne (P1-c), il ne s'accumule pas sous le même
marqueur.

**Si cela changeait**, rien n'est silencieux : la fonction renvoie
`complet=False`, la route journalise un **WARNING**, et la réponse HTTP porte
`denouement_complet: false`.

---

## Ce qui est déjà prouvé — et ce qui ne l'est pas

**Prouvé automatiquement** (144 contrôles, dont 71 contre un serveur réel) :
liaison d'identité, refus des usurpations, jeton de rotation à usage unique,
contenu neutre sans preuve, dénouement aux deux déconnexions, sessions
expirées, aucun code d'accès dans un push, aucune opération de masse.

**Jamais vérifié** : tout ce qui demande un téléphone — l'installation,
l'arrivée d'un push application fermée, l'affichage réel, le passage au neutre
observé sur l'écran. C'est exactement l'objet de ce document.

---

## Avant de déployer (quand tu donneras le GO)

1. Attendre que Coolify affiche **`Finished`** (~4 min ; le build peut échouer
   sur un OOM Terser sans que le code soit en cause)
2. Purger le cache **Cloudflare**
3. Vérifier le bundle réellement servi :
   `curl -s https://afroboost.com/ | grep -o 'static/js/main\.[0-9a-f]*\.js'`
4. Vérifier le Service Worker : il doit annoncer **`afroboost-v666`**
5. Lancer `python tests/nonregression.py` contre la production et coller le
   tableau

**Rollback** : `git revert <hash> && git push origin main`
