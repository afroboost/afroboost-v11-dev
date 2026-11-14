# Traductions à faire relire — V670

> **Fichier GÉNÉRÉ** par `frontend/scripts/generer-relecture-i18n.mjs` depuis `src/utils/i18n-visiteur.js`. Ne pas le modifier à la main : corriger la source, puis régénérer.

## Statut des langues

| Code | Langue | Statut | Ce que cela veut dire |
|---|---|---|---|
| `fr` | Français | source | Langue d'origine. |
| `en`, `de` | English, Deutsch | complète | Interface entièrement traduite (relecture interne). |
| `sw`, `ht` | Kiswahili, Kreyòl ayisyen | **bêta — à relire** | Interface entièrement traduite, **jamais relue par un locuteur natif**. Visible dans le menu avec la mention « bêta ». |
| `ln`, `wo`, `bm`, `bas` | Lingála, Wolof, Bamanankan, Bàsàa | **partielle** | Quelques mots seulement ; **tout le reste s'affiche en français**. Aucune phrase n'a été inventée : ces langues ont trop peu de données pour qu'une traduction automatique soit fiable. Mention « partiel » dans le menu. |

## Comment relire

1. Ouvrir la table ci-dessous, colonne de la langue concernée.
2. Corriger directement dans `frontend/src/utils/i18n-visiteur.js` (clé → langue).
3. Ne JAMAIS modifier la colonne `fr` : un test vérifie que le français affiché n'a pas changé.
4. Une fois une langue relue en entier, passer son `status` de `draft` à `complete` dans `src/config/translateLangs.js` : la mention « bêta » disparaît du menu.

## Kiswahili et créole haïtien — interface visiteur (509 textes)

| Clé | Français | Kiswahili (sw) | Kreyòl (ht) |
|---|---|---|---|
| `v_1_partagez_la_video_du_cours_sur_vos` | 1. Partagez la vidéo du cours sur vos réseaux sociaux | 1. Shiriki video ya darasa kwenye mitandao yako ya kijamii | 1. Pataje videyo kou a sou rezo sosyal ou yo |
| `v_2_collez_le_lien_de_votre_publicatio` | 2. Collez le lien de votre publication ci-dessous | 2. Bandika kiungo cha chapisho lako hapa chini | 2. Kole lyen piblikasyon ou a anba a |
| `v_3_abonnez_vous_likez_et_commentez_su` | 3. Abonnez-vous, likez et commentez sur notre Instagram | 3. Jiunge, penda na toa maoni kwenye Instagram yetu | 3. Abòne w, renmen epi kòmante sou Instagram nou an |
| `v_4_expliquez_pourquoi_ce_cours_vous_i` | 4. Expliquez pourquoi ce cours vous intéresse | 4. Eleza kwa nini darasa hili linakuvutia | 4. Eksplike poukisa kou sa a enterese w |
| `v_a_venir` | À VENIR | INAKUJA | KI AP VINI |
| `v_adresse_complete_rue_numero_code_pos` | Adresse complète (rue, numéro, code postal, ville) | Anwani kamili (barabara, namba, msimbo wa posta, jiji) | Adrès konplè (ri, nimewo, kòd postal, vil) |
| `v_afroboost_installe` | Afroboost installé ! | Afroboost imesakinishwa! | Afroboost enstale! |
| `v_afroboost_retour_a_l_accueil` | Afroboost — retour à l’accueil | Afroboost — rudi mwanzo | Afroboost — tounen lakay |
| `v_ambiance_musicale_pendant_votre_sess` | Ambiance musicale pendant votre session | Mazingira ya muziki wakati wa kipindi chako | Anbyans mizikal pandan sesyon ou a |
| `v_annuler` | Annuler | Ghairi | Anile |
| `v_apercu_limite_a_30_secondes` | Aperçu limité à 30 secondes | Onyesho la awali limepunguzwa hadi sekunde 30 | Apèsi limite a 30 segonn |
| `v_aucun_avis_pour_le_moment` | Aucun avis pour le moment | Hakuna maoni kwa sasa | Pa gen okenn avi pou kounye a |
| `v_aucune_offre_disponible` | Aucune offre disponible | Hakuna ofa zinazopatikana | Pa gen okenn òf ki disponib |
| `v_avantage_membre` | Avantage membre | Faida ya mwanachama | Avantaj manm |
| `v_avantage_pour_les_membres_afroboost` | Avantage pour les membres Afroboost | Faida kwa wanachama wa Afroboost | Avantaj pou manm Afroboost yo |
| `v_boutique` | Boutique | Duka | Boutik |
| `v_ce_qui_se_passe_chez_afroboost` | Ce qui se passe chez Afroboost | Yanayotokea Afroboost | Sa k ap pase nan Afroboost |
| `v_choisissez_votre_horaire_ci_dessous_` | 👇 Choisissez votre horaire ci-dessous pour cette offre | 👇 Chagua muda wako hapa chini kwa ofa hii | 👇 Chwazi orè ou anba a pou òf sa a |
| `v_choisissez_votre_mode_de_paiement` | Choisissez votre mode de paiement | Chagua njia yako ya malipo | Chwazi mòd peman ou |
| `v_cliquez_sur_les_dates_ci_dessus_pour` | 💡 Cliquez sur les dates ci-dessus pour en ajouter ou retirer | 💡 Bofya tarehe zilizo juu ili kuongeza au kuondoa | 💡 Klike sou dat ki anlè yo pou ajoute oswa retire |
| `v_continuer` | Continuer | Endelea | Kontinye |
| `v_couleur` | Couleur | Rangi | Koulè |
| `v_date_de_naissance` | Date de naissance | Tarehe ya kuzaliwa | Dat nesans |
| `v_decouvrir` | Découvrir | Gundua | Dekouvri |
| `v_demande_envoyee` | Demande envoyée ! | Ombi limetumwa! | Demann voye! |
| `v_devise_chf_francs_suisses_livraison_` | Devise : CHF (francs suisses). Livraison : Suisse. | Sarafu: CHF (faranga za Uswisi). Uwasilishaji: Uswisi. | Lajan: CHF (fran swis). Livrezon: Lasuis. |
| `v_en_direct` | EN DIRECT | MOJA KWA MOJA | AN DIRÈK |
| `v_equipe_toi_bouge_represente_afroboos` | Équipe-toi. Bouge. Représente Afroboost. | Jiandae. Cheza. Wakilisha Afroboost. | Ekipe w. Bouje. Reprezante Afroboost. |
| `v_essai_gratuit_preuve_sociale` | Essai gratuit — preuve sociale | Jaribio la bure — uthibitisho wa kijamii | Eseye gratis — prèv sosyal |
| `v_evenement_afroboost` | Événement Afroboost | Tukio la Afroboost | Evènman Afroboost |
| `v_experience_immersive` | Expérience immersive | Uzoefu wa kuzama | Eksperyans imèsif |
| `v_expliquez_en_quelques_lignes` | Expliquez en quelques lignes... | Eleza kwa mistari michache... | Eksplike nan kèk liy... |
| `v_fermer` | Fermer | Funga | Fèmen |
| `v_fermer_et_effacer_le_ticket` | Fermer et effacer le ticket | Funga na ufute tikiti | Fèmen epi efase tikè a |
| `v_fermer_le_menu` | Fermer le menu | Funga menyu | Fèmen meni an |
| `v_gratuit` | (GRATUIT) | (BURE) | (GRATIS) |
| `v_impressum` | Impressum | Taarifa za kisheria | Enfòmasyon legal |
| `v_informations_produit` | Informations produit | Maelezo ya bidhaa | Enfòmasyon sou pwodwi a |
| `v_installation_en_cours` | Installation en cours... | Usakinishaji unaendelea... | Enstalasyon ap fèt... |
| `v_installer_afroboost` | Installer Afroboost | Sakinisha Afroboost | Enstale Afroboost |
| `v_installer_l_app` | Installer l'app | Sakinisha programu | Enstale aplikasyon an |
| `v_installer_sur_iphone` | Installer sur iPhone | Sakinisha kwenye iPhone | Enstale sou iPhone |
| `v_j_ai_compris` | J'ai compris | Nimeelewa | Mwen konprann |
| `v_l_app_apparaitra_dans_votre_tiroir_d` | L'app apparaîtra dans votre tiroir d'applications | Programu itaonekana kwenye orodha ya programu zako | Aplikasyon an ap parèt nan lis aplikasyon ou yo |
| `v_le_contenu_de_ce_site_est_fourni_a_t` | Le contenu de ce site est fourni à titre informatif. L'Association Afroboosteur décline toute responsabilité pour les erreurs ou omissions dans le contenu proposé. | Maudhui ya tovuti hii yametolewa kwa madhumuni ya taarifa tu. Chama cha Afroboosteur hakiwajibiki kwa makosa au upungufu katika maudhui yaliyotolewa. | Kontni sit sa a bay sèlman pou enfòmasyon. Asosyasyon Afroboosteur pa pran okenn responsablite pou erè oswa omisyon nan kontni ki ofri a. |
| `v_le_paiement_est_momentanement_indisp` | Le paiement est momentanement indisponible. Merci de reessayer. | Malipo hayapatikani kwa sasa. Tafadhali jaribu tena. | Peman an pa disponib pou kounye a. Tanpri eseye ankò. |
| `v_les_paiements_sont_traites_de_manier` | Les paiements sont traités de manière sécurisée via Stripe. Les moyens de paiement acceptés incluent TWINT, carte de crédit (Visa, Mastercard) et PayPal selon la configuration du coach. | Malipo huchakatwa kwa usalama kupitia Stripe. Njia za malipo zinazokubaliwa ni pamoja na TWINT, kadi ya mkopo (Visa, Mastercard) na PayPal kulingana na mipangilio ya kocha. | Peman yo trete an sekirite atravè Stripe. Mwayen peman yo aksepte yo gen ladan TWINT, kat kredi (Visa, Mastercard) ak PayPal selon konfigirasyon antrenè a. |
| `v_lien_de_votre_publication` | Lien de votre publication * | Kiungo cha chapisho lako * | Lyen piblikasyon ou a * |
| `v_lire_plus` | Lire plus | Soma zaidi | Li plis |
| `v_maintenance_en_cours` | Maintenance en cours | Matengenezo yanaendelea | Antretyen ap fèt |
| `v_media_non_disponible` | ⚠️ Média non disponible | ⚠️ Midia haipatikani | ⚠️ Medya pa disponib |
| `v_membre_afroboost_ouvrez_votre_espace` | Membre Afroboost ? Ouvrez votre espace pour voir votre tarif. | Mwanachama wa Afroboost? Fungua eneo lako ili uone bei yako. | Manm Afroboost? Louvri espas ou pou w wè pri w. |
| `v_mentions_legales` | Mentions légales | Taarifa za kisheria | Mansyon legal |
| `v_menu_afroboost` | Menu Afroboost | Menyu ya Afroboost | Meni Afroboost |
| `v_merci_de_remplir_tous_les_champs_mar` | Merci de remplir tous les champs marqués d'une étoile. | Tafadhali jaza sehemu zote zilizo na nyota. | Tanpri ranpli tout chan ki make ak yon etwal. |
| `v_moins` | Moins | Punguza | Mwens |
| `v_mon_ticket` | Mon ticket | Tikiti yangu | Tikè mwen |
| `v_moyens_de_paiement` | Moyens de paiement | Njia za malipo | Mwayen peman |
| `v_ne_fermez_pas_chrome` | Ne fermez pas Chrome | Usifunge Chrome | Pa fèmen Chrome |
| `v_offre_expiree` | Offre expirée | Ofa imekwisha muda | Òf la ekspire |
| `v_offre_precedente` | Offre précédente | Ofa iliyotangulia | Òf anvan an |
| `v_offre_suivante` | Offre suivante | Ofa inayofuata | Pwochen òf |
| `v_ouvrez_ensuite_votre_espace_avec_ce_` | Ouvrez ensuite votre espace avec ce code pour choisir la date de votre séance. | Kisha fungua eneo lako kwa msimbo huu ili kuchagua tarehe ya kipindi chako. | Apre sa, louvri espas ou ak kòd sa a pou chwazi dat sesyon ou an. |
| `v_paiement_confirme` | Paiement confirmé | Malipo yamethibitishwa | Peman konfime |
| `v_paiement_securise_stripe_twint` | Paiement sécurisé (Stripe / TWINT). | Malipo salama (Stripe / TWINT). | Peman an sekirite (Stripe / TWINT). |
| `v_partager` | 📤 Partager | 📤 Shiriki | 📤 Pataje |
| `v_partager_cette_offre` | Partager cette offre | Shiriki ofa hii | Pataje òf sa a |
| `v_photo` | Photo | Picha | Foto |
| `v_plus` | Plus | Ongeza | Plis |
| `v_poids` | Poids | Uzito | Pwa |
| `v_pour_beneficier_de_l_essai_gratuit` | Pour bénéficier de l'essai gratuit : | Ili kupata jaribio la bure: | Pou jwenn eseye gratis la: |
| `v_pourquoi_ce_cours_vous_interesse_d_o` | Pourquoi ce cours vous intéresse ? D'où venez-vous ? * | Kwa nini darasa hili linakuvutia? Unatoka wapi? * | Poukisa kou sa a enterese w? Ki kote w soti? * |
| `v_prix_public` | Prix public | Bei ya kawaida | Pri piblik |
| `v_produit_physique_adresse_de_livraiso` | 📦 Produit physique - Adresse de livraison requise | 📦 Bidhaa halisi - Anwani ya uwasilishaji inahitajika | 📦 Pwodwi fizik - Adrès livrezon obligatwa |
| `v_quantite` | Quantité | Kiasi | Kantite |
| `v_reinitialiser_les_filtres` | Réinitialiser les filtres | Weka upya vichujio | Reyinisyalize filt yo |
| `v_rejoindre_l_experience_immersive` | Rejoindre l'expérience immersive | Jiunge na uzoefu wa kuzama | Rejwenn eksperyans imèsif la |
| `v_renseigne_maintenant_tes_coordonnees` | Renseigne maintenant tes coordonnées pour créer ton espace membre et continuer ton inscription. | Weka sasa taarifa zako za mawasiliano ili uunde eneo lako la mwanachama na uendelee na usajili wako. | Ranpli koordone w kounye a pou kreye espas manm ou epi kontinye enskripsyon w. |
| `v_responsabilite` | Responsabilité | Wajibu | Responsablite |
| `v_retour_afroboost` | Retour Afroboost | Rudi Afroboost | Tounen Afroboost |
| `v_selectionnez_une_offre_pour_voir_les` | 👉 Sélectionnez une offre pour voir les horaires disponibles | 👉 Chagua ofa ili uone muda unaopatikana | 👉 Chwazi yon òf pou wè orè ki disponib yo |
| `v_selectionnez_vos_options` | 🎨 Sélectionnez vos options | 🎨 Chagua machaguo yako | 🎨 Chwazi opsyon ou yo |
| `v_super` | Super ! | Safi! | Siper! |
| `v_taille` | Taille | Ukubwa | Gwosè |
| `v_tes_informations` | Tes informations | Taarifa zako | Enfòmasyon ou yo |
| `v_ton_age_ne_sera_pas_affiche_publique` | Ton âge ne sera pas affiché publiquement sauf si tu le souhaites. On fête les anniversaires avec toute la communauté Afroboost ! | Umri wako hautaonyeshwa hadharani isipokuwa ukitaka. Tunasherehekea siku za kuzaliwa pamoja na jumuiya yote ya Afroboost! | Pa gen moun k ap wè laj ou piblikman sof si w vle. N ap fete anivèsè ansanm ak tout kominote Afroboost la! |
| `v_tout_voir` | Tout voir | Ona yote | Wè tout |
| `v_tu_as_choisi_ton_offre` | Tu as choisi ton offre. | Umechagua ofa yako. | Ou chwazi òf ou a. |
| `v_verifie` | ✓ Vérifié | ✓ Imethibitishwa | ✓ Verifye |
| `v_veuillez_selectionner_un_poids` | * Veuillez sélectionner un poids | * Tafadhali chagua uzito | * Tanpri chwazi yon pwa |
| `v_veuillez_selectionner_une_couleur` | * Veuillez sélectionner une couleur | * Tafadhali chagua rangi | * Tanpri chwazi yon koulè |
| `v_veuillez_selectionner_une_taille` | * Veuillez sélectionner une taille | * Tafadhali chagua ukubwa | * Tanpri chwazi yon gwosè |
| `v_vitrine_partenaire` | Vitrine partenaire | Onyesho la mshirika | Vitrin patnè |
| `v_voir_la_photo` | Voir la photo | Ona picha | Wè foto a |
| `v_voir_le_produit` | Voir le produit | Ona bidhaa | Wè pwodwi a |
| `v_voir_les_avis` | Voir les avis | Ona maoni | Wè avi yo |
| `v_votre_demande_d_essai_gratuit_est_en` | Votre demande d'essai gratuit est en cours de vérification. Vous recevrez un email dès qu'elle sera validée. | Ombi lako la jaribio la bure linakaguliwa. Utapokea barua pepe mara litakapoidhinishwa. | Demann eseye gratis ou an ap verifye. Ou pral resevwa yon imèl le l valide. |
| `v_votre_email` | Votre email * | Barua pepe yako * | Imèl ou * |
| `v_votre_nom` | Votre nom * | Jina lako * | Non ou * |
| `v_votre_telephone_optionnel` | Votre téléphone (optionnel) | Simu yako (si lazima) | Telefòn ou (opsyonèl) |
| `v_zoom` | Zoom | Kuza | Zoum |
| `v_langue` | Langue | Lugha | Lang |
| `v_comment_souhaitez_vous_reserver` | Comment souhaitez-vous réserver ? | Ungependa kuhifadhi vipi? | Kijan w vle rezève? |
| `v_essai_gratuit` | Essai GRATUIT | Jaribio la BURE | Eseye GRATIS |
| `v_partagez_sur_vos_reseaux_sociaux_et_` | Partagez sur vos réseaux sociaux et recevez un accès gratuit | Shiriki kwenye mitandao yako ya kijamii na upate ufikiaji wa bure | Pataje sou rezo sosyal ou yo epi resevwa aksè gratis |
| `v_reserver_directement_sans_les_etapes` | Réserver directement, sans les étapes sociales | Hifadhi moja kwa moja, bila hatua za kijamii | Rezève dirèkteman, san etap sosyal yo |
| `vm_payer_par_carte` | Payer par carte | Lipa kwa kadi | Peye ak kat |
| `vm_payer_par_twint` | Payer par TWINT | Lipa kwa TWINT | Peye ak TWINT |
| `vm_place_reservee` | Ta place est réservée | Nafasi yako imehifadhiwa | Plas ou rezève |
| `vm_confirmation_email` | Ta confirmation arrive par e-mail. | Uthibitisho wako unakuja kwa barua pepe. | Konfimasyon ou ap vini pa imèl. |
| `vm_code_acces_envoye` | 📧 Votre **code d'accès** vous est envoyé par email dans quelques instants. | 📧 **Msimbo wako wa kufikia** utatumwa kwako kwa barua pepe baada ya muda mfupi. | 📧 **Kòd aksè** ou a ap voye ba ou pa imèl nan kèk moman. |
| `vm_payer_montant` | Payer {montant} CHF | Lipa {montant} CHF | Peye {montant} CHF |
| `vm_frais_de_port` | Frais de port : CHF {montant} | Gharama ya usafirishaji: CHF {montant} | Frè livrezon: CHF {montant} |
| `vm_tva` | TVA {taux}% | VAT {taux}% | TVA {taux}% |
| `vm_plus_frais_de_port` | + CHF {montant} frais de port | + CHF {montant} gharama ya usafirishaji | + CHF {montant} frè livrezon |
| `vm_prochaine_seance` | Prochaine séance : | Kipindi kijacho: | Pwochen sesyon: |
| `vm_places` | {n} places | nafasi {n} | {n} plas |
| `vm_minutes` | {n} min | dakika {n} | {n} min |
| `vm_options` | Options: | Machaguo: | Opsyon: |
| `vm_selectionne` | Sélectionné | Imechaguliwa | Chwazi |
| `vm_maintenance_1` | Nous améliorons votre expérience Afroboost. | Tunaboresha uzoefu wako wa Afroboost. | N ap amelyore eksperyans Afroboost ou. |
| `vm_maintenance_2` | Revenez dans quelques instants ! | Rudi baada ya muda mfupi! | Tounen nan kèk moman! |
| `vm_questions` | Questions ? | Maswali? | Kesyon? |
| `vm_pass_duo` | Tu viens accompagné ? Invite un ami avec ton Pass Duo. | Unakuja na mwenzako? Mwalike rafiki kwa Pass Duo yako. | Ou vini ak yon moun? Envite yon zanmi ak Pass Duo ou a. |
| `vm_inviter_un_ami` | Inviter un ami | Mwalike rafiki | Envite yon zanmi |
| `vm_install_chrome_1` | Appuyez sur les **3 points ⋮** en haut à droite de Chrome | Gusa **nukta 3 ⋮** juu kulia mwa Chrome | Peze sou **3 pwen ⋮** anwo adwat Chrome |
| `vm_install_chrome_2` | Appuyez sur **"Installer l'application"** | Gusa **"Sakinisha programu"** | Peze sou **"Enstale aplikasyon an"** |
| `vm_install_chrome_3` | Confirmez puis **patientez 30 à 60 secondes** — Google génère votre app | Thibitisha kisha **subiri sekunde 30 hadi 60** — Google inatengeneza programu yako | Konfime epi **tann 30 a 60 segonn** — Google ap kreye aplikasyon ou a |
| `vm_install_ios_1` | Appuyez sur le bouton **Partager 📤** en bas | Gusa kitufe cha **Shiriki 📤** chini | Peze sou bouton **Pataje 📤** anba a |
| `vm_install_ios_2` | Sélectionnez **"Sur l'écran d'accueil"** | Chagua **"Ongeza kwenye Skrini ya Kwanza"** | Chwazi **"Ajoute sou ekran dakèy"** |
| `vm_install_ios_3` | Appuyez sur **"Ajouter"** | Gusa **"Ongeza"** | Peze sou **"Ajoute"** |
| `vm_install_genere` | Google génère votre application. | Google inatengeneza programu yako. | Google ap kreye aplikasyon ou a. |
| `vm_install_duree` | Cela peut prendre 30 à 60 secondes. | Hii inaweza kuchukua sekunde 30 hadi 60. | Sa ka pran 30 a 60 segonn. |
| `vm_install_ok_1` | L'app est dans votre tiroir d'applications. | Programu iko kwenye orodha ya programu zako. | Aplikasyon an nan lis aplikasyon ou yo. |
| `vm_install_ok_2` | Glissez vers le haut pour la trouver. | Telezesha juu ili kuipata. | Glise anlè pou jwenn li. |
| `vm_porte_le` | PORTE LE | BEBA | PÒTE |
| `vm_mouvement` | MOUVEMENT. | HARAKATI. | MOUVMAN AN. |
| `vm_piste_n` | Piste {n} / {total} | Wimbo {n} / {total} | Pis {n} / {total} |
| `vm_titres_prix_reduit` | Sélectionnez plusieurs titres pour un prix réduit : | Chagua nyimbo kadhaa kwa bei iliyopunguzwa: | Chwazi plizyè tit pou yon pri redwi: |
| `vm_titres_paliers` | -25% dès 2 titres, -40% dès 3 titres | -25% kuanzia nyimbo 2, -40% kuanzia nyimbo 3 | -25% apati de 2 tit, -40% apati de 3 tit |
| `vm_acheter_selection` | 🛒 Acheter la sélection ({n} titres) — {prix} CHF | 🛒 Nunua uteuzi (nyimbo {n}) — {prix} CHF | 🛒 Achte seleksyon an ({n} tit) — {prix} CHF |
| `vm_dates_selectionnees` | 📅 Dates sélectionnées ({n}) | 📅 Tarehe zilizochaguliwa ({n}) | 📅 Dat ou chwazi yo ({n}) |
| `vm_sous_total_quantite` | Sous-total ({n} x CHF {prix}) | Jumla ndogo ({n} x CHF {prix}) | Sou-total ({n} x CHF {prix}) |
| `vm_sous_total_dates` | Sous-total ({n} dates x CHF {prix}) | Jumla ndogo (tarehe {n} x CHF {prix}) | Sou-total ({n} dat x CHF {prix}) |
| `vm_reduction` | Réduction ({code}) | Punguzo ({code}) | Rediksyon ({code}) |
| `vm_publications_n` | {n} publications du coach et de ses membres | machapisho {n} ya kocha na wanachama wake | {n} piblikasyon antrenè a ak manm li yo |
| `vm_publication_1` | {n} publication du coach et de ses membres | chapisho {n} la kocha na wanachama wake | {n} piblikasyon antrenè a ak manm li yo |
| `vm_denomination` | Dénomination : | Jina: | Non: |
| `vm_adresse` | Adresse : | Anwani: | Adrès: |
| `vm_contact` | Contact : | Mawasiliano: | Kontak: |
| `vm_commentaires` | Commentaires {n} | Maoni {n} | Kòmantè {n} |
| `vm_association` | Association | Chama | Asosyasyon |
| `v_texte_d_origine` | Traduit automatiquement. Texte d’origine : | Imetafsiriwa kiotomatiki. Maandishi asilia: | Tradui otomatikman. Tèks orijinal: |
| `v_col_consulte_les_prochaines_seances_au_p` | Consulte les prochaines séances au planning. | Angalia vipindi vijavyo kwenye ratiba. | Gade pwochen sesyon yo nan orè a. |
| `v_col_decouvrir_le_live` | Découvrir le Live | Gundua Live | Dekouvri Live la |
| `v_col_en_direct` | EN DIRECT | MOJA KWA MOJA | AN DIRÈK |
| `v_col_seances_regulieres` | Séances régulières | Vipindi vya kawaida | Sesyon regilye |
| `v_col_trouver_un_partenaire_de_sport` | Trouver un partenaire de sport. | Tafuta mwenzi wa michezo. | Jwenn yon patnè espò. |
| `v_col_voir_l_offre` | Voir l’offre | Ona ofa | Wè òf la |
| `v_col_voir_le_planning` | Voir le planning | Ona ratiba | Wè orè a |
| `v_col_voir_les_seances` | Voir les séances | Ona vipindi | Wè sesyon yo |
| `v_dec_aucune_seance_annoncee_pour_l_instan` | Aucune séance annoncée pour l'instant. | Hakuna kipindi kilichotangazwa kwa sasa. | Pa gen okenn sesyon anonse pou kounye a. |
| `v_dec_complet` | Complet | Imejaa | Konplè |
| `v_dec_decouvrir_afroboost` | Découvrir Afroboost | Gundua Afroboost | Dekouvri Afroboost |
| `v_dec_premier_cours_offert` | Premier cours offert | Darasa la kwanza bure | Premye kou gratis |
| `v_dec_recherche_de_la_prochaine_seance` | Recherche de la prochaine séance… | Inatafuta kipindi kijacho… | Ap chèche pwochen sesyon an… |
| `v_dec_reserver_ma_place` | Réserver ma place | Hifadhi nafasi yangu | Rezève plas mwen |
| `v_dec_voir_le_programme` | Voir le programme | Ona ratiba ya vipindi | Wè pwogram nan |
| `v_dec_voir_toutes_les_offres` | Voir toutes les offres | Ona ofa zote | Wè tout òf yo |
| `v_hero_nouveau_chez_afroboost_ton_premier_c` | Nouveau chez Afroboost ? Ton premier cours est offert ! | Mgeni Afroboost? Darasa lako la kwanza ni bure! | Nouvo nan Afroboost? Premye kou ou a gratis! |
| `v_ses_aucune_session_programmee_pour_le_mo` | Aucune session programmée pour le moment. | Hakuna kipindi kilichopangwa kwa sasa. | Pa gen okenn sesyon pwograme pou kounye a. |
| `v_ses_calendrier_des_sessions` | Calendrier des sessions | Kalenda ya vipindi | Kalandriye sesyon yo |
| `v_ses_chargement_du_calendrier` | Chargement du calendrier… | Inapakia kalenda… | Kalandriye a ap chaje… |
| `v_ses_choisis_un_jour_marque_d_un_point` | Choisis un jour marqué d’un point. | Chagua siku iliyo na nukta. | Chwazi yon jou ki gen yon pwen. |
| `v_ses_detail_de_la_session` | Détail de la session | Maelezo ya kipindi | Detay sesyon an |
| `v_ses_evenement_date_unique` | Événement — date unique | Tukio — tarehe moja | Evènman — yon sèl dat |
| `v_ses_fermer` | Fermer | Funga | Fèmen |
| `v_ses_horaires` | Horaires | Ratiba | Orè yo |
| `v_ses_retour_au_calendrier` | Retour au calendrier | Rudi kwenye kalenda | Tounen nan kalandriye a |
| `v_aim_agrandir_le_media` | Agrandir le média | Kuza midia | Agrandi medya a |
| `v_aim_choisir_cette_formule` | Choisir cette formule | Chagua mpango huu | Chwazi fòmil sa a |
| `v_aim_fermer` | Fermer | Funga | Fèmen |
| `v_aim_media_en_grand` | Média en grand | Midia kwa ukubwa kamili | Medya an gran |
| `v_aim_mode_de_paiement` | Mode de paiement | Njia ya malipo | Mòd peman |
| `v_aim_reserver_mon_1er_cours_gratuit` | Réserver mon 1er cours gratuit | Hifadhi darasa langu la kwanza bure | Rezève premye kou mwen gratis |
| `v_aim_saison_8_mois` | Saison 8 mois | Msimu wa miezi 8 | Sezon 8 mwa |
| `v_aim_voir_l_offre` | Voir l’offre | Ona ofa | Wè òf la |
| `v_aim_voir_toutes_les_offres` | Voir toutes les offres | Ona ofa zote | Wè tout òf yo |
| `v_hero_titre_defaut` | Danse. Transpire. Lâche prise. | Cheza. Toa jasho. Jiachilie. | Danse. Swe. Lage tèt ou. |
| `v_hero_sous_titre_defaut` | Vis l'expérience Afroboost : danse afrobeat et fitness au casque, même si tu n'as jamais dansé. | Ishi uzoefu wa Afroboost: dansi ya afrobeat na mazoezi kwa vipokea sauti, hata kama hujawahi kucheza. | Viv eksperyans Afroboost: dans afrobeat ak fitnès ak kask, menm si ou pa janm danse. |
| `v_hero_cta_defaut` | Réserver mon 1er cours gratuit | Hifadhi darasa langu la kwanza bure | Rezève premye kou mwen gratis |
| `v_mem_accede_a_ton_espace` | Accède à ton espace | Fikia eneo lako | Antre nan espas ou |
| `v_mem_acceder_a_mon_espace` | Accéder à mon espace | Nenda kwenye eneo langu | Ale nan espas mwen |
| `v_mem_acces_indisponible` | Accès indisponible | Ufikiaji haupatikani | Aksè pa disponib |
| `v_mem_actif` | Actif | Hai | Aktif |
| `v_mem_activer_la_reconduction` | Activer la reconduction | Washa kusasisha kiotomatiki | Aktive renouvèlman otomatik |
| `v_mem_afficher_moins` | Afficher moins | Onyesha kidogo | Montre mwens |
| `v_mem_annulation_impossible_moins_de_2h_av` | Annulation impossible moins de 2h avant | Kughairi hakuwezekani chini ya saa 2 kabla | Pa ka anile mwens pase 2è davans |
| `v_mem_annuler` | Annuler | Ghairi | Anile |
| `v_mem_annuler_la_seance` | Annuler la séance | Ghairi kipindi | Anile sesyon an |
| `v_mem_annuler_pour_changer_de_seance` | Annuler pour changer de séance | Ghairi ili kubadilisha kipindi | Anile pou chanje sesyon |
| `v_mem_aucun_cours_disponible_pour_le_momen` | Aucun cours disponible pour le moment. | Hakuna darasa linalopatikana kwa sasa. | Pa gen okenn kou ki disponib pou kounye a. |
| `v_mem_aucun_nouveau_creneau_n_est_disponib` | Aucun nouveau créneau n'est disponible pour le moment. Reviens bientôt pour choisir ta séance. | Hakuna nafasi mpya inayopatikana kwa sasa. Rudi hivi karibuni kuchagua kipindi chako. | Pa gen okenn nouvo kreno ki disponib pou kounye a. Tounen talè pou chwazi sesyon ou. |
| `v_mem_aucune_carte_enregistree_pour_cet_ab` | Aucune carte enregistrée pour cet abonnement — renouvellement manuel uniquement. | Hakuna kadi iliyohifadhiwa kwa usajili huu — kusasisha kwa mkono tu. | Pa gen kat anrejistre pou abònman sa a — renouvèlman manyèl sèlman. |
| `v_mem_aucune_carte_enregistree_souscriptio` | Aucune carte enregistrée — souscription manuelle uniquement | Hakuna kadi iliyohifadhiwa — usajili wa mkono tu | Pa gen kat anrejistre — abònman manyèl sèlman |
| `v_mem_augmenter` | Augmenter | Ongeza | Ogmante |
| `v_mem_aujourd_hui` | AUJOURD'HUI | LEO | JODI A |
| `v_mem_bienvenue` | Bienvenue ! | Karibu! | Byenveni! |
| `v_mem_bloquer` | Bloquer | Zuia | Bloke |
| `v_mem_casques_en_cours` | Casques en cours | Vipokea sauti vinavyotumika | Kask an kou |
| `v_mem_ce_lien_n_est_plus_valable_confirme_` | Ce lien n’est plus valable. Confirme ton adresse e-mail pour recevoir un code. | Kiungo hiki hakifai tena. Thibitisha barua pepe yako ili upokee msimbo. | Lyen sa a pa valab ankò. Konfime adrès imèl ou pou resevwa yon kòd. |
| `v_mem_chargement_de_ton_espace` | Chargement de ton espace… | Inapakia eneo lako… | Espas ou a ap chaje… |
| `v_mem_choisir_ma_seance` | Choisir ma séance | Chagua kipindi changu | Chwazi sesyon mwen |
| `v_mem_choisis_maintenant_ta_seance` | Choisis maintenant ta séance. | Chagua kipindi chako sasa. | Chwazi sesyon ou kounye a. |
| `v_mem_code_d_acces_manquant_dans_l_url` | Code d'accès manquant dans l'URL | Msimbo wa kufikia haupo kwenye URL | Kòd aksè a manke nan URL la |
| `v_mem_conditions_d_utilisation` | Conditions d'utilisation | Masharti ya matumizi | Kondisyon itilizasyon |
| `v_mem_confirme_ton_adresse_e_mail_pour_rec` | Confirme ton adresse e-mail pour recevoir un code de vérification. | Thibitisha barua pepe yako ili upokee msimbo wa uthibitisho. | Konfime adrès imèl ou pou resevwa yon kòd verifikasyon. |
| `v_mem_continuer_mon_abonnement` | Continuer mon abonnement | Endelea na usajili wangu | Kontinye abònman mwen |
| `v_mem_copier_le_code` | Copier le code | Nakili msimbo | Kopye kòd la |
| `v_mem_copier_le_lien_personnel` | Copier le lien personnel | Nakili kiungo changu binafsi | Kopye lyen pèsonèl mwen |
| `v_mem_corriger_mon_e_mail` | Corriger mon e-mail | Sahihisha barua pepe yangu | Korije imèl mwen |
| `v_mem_debloquer` | Débloquer | Ondoa kizuizi | Debloke |
| `v_mem_deconnexion` | Déconnexion… | Inatoka… | Dekonèksyon… |
| `v_mem_deja_inscrit_choisis_ton_profil` | Déjà inscrit ? Choisis ton profil | Umeshajisajili? Chagua wasifu wako | Ou deja enskri? Chwazi pwofil ou |
| `v_mem_desactivee` | Désactivée | Imezimwa | Dezaktive |
| `v_mem_desactiver_la_reconduction` | Désactiver la reconduction | Zima kusasisha kiotomatiki | Dezaktive renouvèlman otomatik |
| `v_mem_diminuer` | Diminuer | Punguza | Diminye |
| `v_mem_email` | Email | Barua pepe | Imèl |
| `v_mem_entre_tes_infos_pour_obtenir_ton_lie` | Entre tes infos pour obtenir ton lien personnel | Weka taarifa zako ili upate kiungo chako binafsi | Antre enfòmasyon ou pou jwenn lyen pèsonèl ou |
| `v_mem_essai_disponible` | Essai disponible | Jaribio linapatikana | Eseye disponib |
| `v_mem_essai_effectue` | Essai effectué | Jaribio limekamilika | Eseye fèt |
| `v_mem_essai_reserve` | Essai réservé | Jaribio limehifadhiwa | Eseye rezève |
| `v_mem_etat` | État | Hali | Eta |
| `v_mem_fin_d_acces` | Fin d'accès | Mwisho wa ufikiaji | Fen aksè |
| `v_mem_inscription` | Inscription... | Inasajili... | Enskripsyon... |
| `v_mem_itineraire` | Itinéraire | Maelekezo | Direksyon |
| `v_mem_le_montant_sera_preleve_automatiquem` | Le montant sera prélevé automatiquement à la fin de vos séances. Non remboursable. | Kiasi kitakatwa kiotomatiki mwishoni mwa vipindi vyako. Hakirudishwi. | Montan an ap retire otomatikman nan fen sesyon ou yo. Pa ranbouse. |
| `v_mem_ma_progression` | Ma progression | Maendeleo yangu | Pwogrè mwen |
| `v_mem_membres_du_groupe` | Membres du groupe | Wanachama wa kikundi | Manm gwoup la |
| `v_mem_mes_prochaines_seances` | Mes prochaines séances | Vipindi vyangu vijavyo | Pwochen sesyon mwen yo |
| `v_mem_moi` | (moi) | (mimi) | (mwen) |
| `v_mem_mon_abonnement_mensuel` | Mon abonnement mensuel | Usajili wangu wa kila mwezi | Abònman mansyèl mwen |
| `v_mem_nous_avons_bien_enregistre_ta_place_` | Nous avons bien enregistré ta place. À bientôt chez Afroboost 🎧🔥 | Tumehifadhi nafasi yako. Tuonane hivi karibuni Afroboost 🎧🔥 | Nou anrejistre plas ou. Wi talè nan Afroboost 🎧🔥 |
| `v_mem_obtenir_mon_lien_personnel` | Obtenir mon lien personnel | Pata kiungo changu binafsi | Jwenn lyen pèsonèl mwen |
| `v_mem_offre` | Offre | Ofa | Òf |
| `v_mem_ouverture_de_ton_espace` | Ouverture de ton espace… | Inafungua eneo lako… | Espas ou a ap louvri… |
| `v_mem_plus_de_seances_disponibles` | Plus de séances disponibles | Hakuna vipindi vingine vinavyopatikana | Pa gen sesyon ankò ki disponib |
| `v_mem_prenom` | Prénom * | Jina la kwanza * | Prenon * |
| `v_mem_prenom_2` | Prénom | Jina la kwanza | Prenon |
| `v_mem_presente_ce_code_au_coach_a_l_entree` | Présente ce code au coach à l'entrée | Onyesha msimbo huu kwa kocha mlangoni | Montre kòd sa a bay antrenè a nan antre a |
| `v_mem_prix_mensuel` | Prix mensuel | Bei ya kila mwezi | Pri pa mwa |
| `v_mem_prochaine_echeance` | Prochaine échéance | Tarehe ijayo ya malipo | Pwochen dat limit |
| `v_mem_prochaine_etape` | Prochaine étape | Hatua inayofuata | Pwochen etap |
| `v_mem_prochaine_seance` | Prochaine séance | Kipindi kijacho | Pwochen sesyon |
| `v_mem_publier` | Publier | Chapisha | Pibliye |
| `v_mem_publier_une_photo_ou_une_video` | Publier une photo ou une vidéo | Chapisha picha au video | Pibliye yon foto oswa yon videyo |
| `v_mem_qr_code_abonne` | QR Code abonné | Msimbo wa QR wa mwanachama | Kòd QR manm |
| `v_mem_recevoir_mon_code` | Recevoir mon code | Pokea msimbo wangu | Resevwa kòd mwen |
| `v_mem_reconduction_automatique` | Reconduction automatique | Kusasisha kiotomatiki | Renouvèlman otomatik |
| `v_mem_redirection` | Redirection... | Inaelekeza... | Redireksyon... |
| `v_mem_rejoindre_cet_abonnement` | Rejoindre cet abonnement | Jiunge na usajili huu | Rejwenn abònman sa a |
| `v_mem_renouveler_mon_abonnement` | Renouveler mon abonnement | Sasisha usajili wangu | Renouvle abònman mwen |
| `v_mem_renvoyer_le_code` | Renvoyer le code | Tuma msimbo tena | Voye kòd la ankò |
| `v_mem_reserve` | Réservé | Imehifadhiwa | Rezève |
| `v_mem_reserver` | Réserver | Hifadhi | Rezève |
| `v_mem_reserver_cette_seance` | Réserver cette séance | Hifadhi kipindi hiki | Rezève sesyon sa a |
| `v_mem_reserver_une_seance` | Réserver une séance | Hifadhi kipindi | Rezève yon sesyon |
| `v_mem_resiliation_programmee` | Résiliation programmée | Kughairi kumepangwa | Rezilyasyon pwograme |
| `v_mem_resilier_mon_abonnement` | Résilier mon abonnement | Ghairi usajili wangu | Anile abònman mwen |
| `v_mem_retour_a_la_page_du_groupe` | Retour à la page du groupe | Rudi kwenye ukurasa wa kikundi | Tounen nan paj gwoup la |
| `v_mem_saisis_le_code_a_6_chiffres_recu_par` | Saisis le code à 6 chiffres reçu par e-mail. | Weka msimbo wa tarakimu 6 uliopokea kwa barua pepe. | Antre kòd 6 chif ou resevwa pa imèl la. |
| `v_mem_se_deconnecter_de_cet_appareil` | Se déconnecter de cet appareil | Toka kwenye kifaa hiki | Dekonekte sou aparèy sa a |
| `v_mem_seance_decouverte` | Séance découverte | Kipindi cha kujaribu | Sesyon dekouvèt |
| `v_mem_seances_ce_mois` | Séances ce mois | Vipindi mwezi huu | Sesyon mwa sa a |
| `v_mem_seances_restantes` | Séances restantes | Vipindi vilivyobaki | Sesyon ki rete |
| `v_mem_ta_reservation_est_confirmee` | ✅ Ta réservation est confirmée ! | ✅ Uhifadhi wako umethibitishwa! | ✅ Rezèvasyon ou konfime! |
| `v_mem_ta_seance_est_reservee` | 🔥 Ta séance est réservée ! | 🔥 Kipindi chako kimehifadhiwa! | 🔥 Sesyon ou rezève! |
| `v_mem_termine` | Terminé | Imekwisha | Fini |
| `v_mem_ton_adresse_e_mail` | ton adresse e-mail | barua pepe yako | adrès imèl ou |
| `v_mem_ton_cours_d_essai_est_active` | 🎁 Ton cours d'essai est activé ! | 🎁 Darasa lako la kujaribu limewashwa! | 🎁 Kou eseye ou a aktive! |
| `v_mem_ton_inscription_est_confirmee` | 🎉 Ton inscription est confirmée ! | 🎉 Usajili wako umethibitishwa! | 🎉 Enskripsyon ou konfime! |
| `v_mem_ton_prenom` | Ton prénom | Jina lako la kwanza | Prenon ou |
| `v_mem_ton_qr_est_pret_presente_le_au_coach` | Ton QR est prêt. Présente-le au coach à ton arrivée. | Msimbo wako wa QR uko tayari. Muonyeshe kocha unapofika. | Kòd QR ou a pare. Montre l bay antrenè a lè ou rive. |
| `v_mem_tu_as_utilise_toutes_tes_seances_con` | Tu as utilisé toutes tes séances. Contacte ton coach pour renouveler. | Umetumia vipindi vyako vyote. Wasiliana na kocha wako ili usasishe. | Ou itilize tout sesyon ou yo. Kontakte antrenè ou pou renouvle. |
| `v_mem_tu_n_as_pas_recu_de_code_ou_tu_n_as_` | Tu n'as pas reçu de code ou tu n'as plus accès à cette adresse ? Contacte ton coach, il peut t'aider. | Hukupokea msimbo au huna tena ufikiaji wa anwani hii? Wasiliana na kocha wako, anaweza kukusaidia. | Ou pa resevwa kòd la oswa ou pa gen aksè ak adrès sa a ankò? Kontakte antrenè ou, li ka ede ou. |
| `v_mem_un_membre_bloque_ne_pourra_plus_rese` | Un membre bloqué ne pourra plus réserver de séances. | Mwanachama aliyezuiwa hataweza tena kuhifadhi vipindi. | Yon manm ki bloke pa pral ka rezève sesyon ankò. |
| `v_mem_valider` | Valider | Thibitisha | Valide |
| `v_mem_verifie_le_lien_avec_ton_coach` | Vérifie le lien avec ton coach. | Hakiki kiungo na kocha wako. | Verifye lyen an ak antrenè ou. |
| `v_mem_voir_mon_qr` | Voir mon QR | Ona QR yangu | Wè QR mwen |
| `v_mem_votre_seance_decouverte_a_ete_utilis` | Votre séance découverte a été utilisée. | Kipindi chako cha kujaribu kimetumika. | Sesyon dekouvèt ou a itilize. |
| `v_mem_vous_avez_deja_reserve_votre_seance_` | Vous avez déjà réservé votre séance découverte. Annulez-la pour en choisir une autre. | Tayari umehifadhi kipindi chako cha kujaribu. Kighairi ili kuchagua kingine. | Ou deja rezève sesyon dekouvèt ou a. Anile l pou chwazi yon lòt. |
| `v_mem_whatsapp` | WhatsApp | WhatsApp | WhatsApp |
| `v_pub_a_la_une` | À LA UNE | IMEANGAZIWA | ALAVI |
| `v_pub_a_la_une_remonte_en_haut_de_l_accuei` | À la une — remonte en haut de l’accueil | Imeangaziwa — inapanda juu ya ukurasa wa mwanzo | Alavi — monte anwo paj dakèy la |
| `v_pub_actions_sur_la_publication` | Actions sur la publication | Vitendo kwenye chapisho | Aksyon sou piblikasyon an |
| `v_pub_activer_le_son` | Activer le son | Washa sauti | Aktive son an |
| `v_pub_ajoutez_une_legende` | Ajoutez une légende... | Ongeza maelezo... | Ajoute yon lejand... |
| `v_pub_annuler` | Annuler | Ghairi | Anile |
| `v_pub_annuler_la_modification` | Annuler la modification | Ghairi mabadiliko | Anile modifikasyon an |
| `v_pub_apercu` | Aperçu | Onyesho la awali | Apèsi |
| `v_pub_appuyez_pour_choisir` | Appuyez pour choisir | Gusa kuchagua | Peze pou chwazi |
| `v_pub_aucun_avis_pour_le_moment` | Aucun avis pour le moment. | Hakuna maoni kwa sasa. | Pa gen okenn avi pou kounye a. |
| `v_pub_aucun_bouton` | — aucun bouton — | — hakuna kitufe — | — pa gen bouton — |
| `v_pub_changer_de_media` | Changer de média | Badilisha midia | Chanje medya |
| `v_pub_coach` | COACH | KOCHA | ANTRENÈ |
| `v_pub_copie` | Copié ! | Imenakiliwa! | Kopye! |
| `v_pub_couper_le_son` | Couper le son | Zima sauti | Koupe son an |
| `v_pub_de_toute_la_page` | de toute la page | ya ukurasa mzima | tout paj la |
| `v_pub_duree_48_h` | Durée : 48 h | Muda: saa 48 | Dire: 48 è |
| `v_pub_duree_sans_limite` | Durée : sans limite | Muda: bila kikomo | Dire: san limit |
| `v_pub_echec_reessayez` | Échec — réessayez | Imeshindwa — jaribu tena | Echèk — eseye ankò |
| `v_pub_enregistre` | Enregistré | Imehifadhiwa | Anrejistre |
| `v_pub_enregistrement` | Enregistrement… | Inahifadhi… | Anrejistreman… |
| `v_pub_enregistrer` | Enregistrer | Hifadhi | Anrejistre |
| `v_pub_enregistrer_les_modifications` | Enregistrer les modifications | Hifadhi mabadiliko | Anrejistre modifikasyon yo |
| `v_pub_fermer` | Fermer | Funga | Fèmen |
| `v_pub_fermer_les_avis` | Fermer les avis | Funga maoni | Fèmen avi yo |
| `v_pub_image_ou_video_format_9_16` | Image ou vidéo (format 9:16) | Picha au video (umbizo wa 9:16) | Imaj oswa videyo (fòma 9:16) |
| `v_pub_laissez_vide_pour_publier_tout_de_su` | Laissez vide pour publier tout de suite. Cette publication restera en ligne sans limite de durée. | Acha wazi ili kuchapisha mara moja. Chapisho hili litabaki mtandaoni bila kikomo cha muda. | Kite vid pou pibliye touswit. Piblikasyon sa a ap rete sou entènèt san limit tan. |
| `v_pub_laissez_vide_pour_publier_tout_de_su_2` | Laissez vide pour publier tout de suite. Les 48 h de visibilité démarrent à la sortie, pas à la programmation. | Acha wazi ili kuchapisha mara moja. Saa 48 za kuonekana zinaanza wakati wa kutoka, si wakati wa kupanga. | Kite vid pou pibliye touswit. 48 è vizibilite yo kòmanse lè piblikasyon an soti, pa lè w pwograme l. |
| `v_pub_legende` | Légende | Maelezo | Lejand |
| `v_pub_lire_plus` | Lire plus | Soma zaidi | Li plis |
| `v_pub_membre` | MEMBRE | MWANACHAMA | MANM |
| `v_pub_mes_publications` | Mes publications | Machapisho yangu | Piblikasyon mwen yo |
| `v_pub_modifier` | Modifier | Hariri | Modifye |
| `v_pub_modifier_la_publication` | Modifier la publication | Hariri chapisho | Modifye piblikasyon an |
| `v_pub_navigation_publications` | Navigation publications | Urambazaji wa machapisho | Navigasyon piblikasyon yo |
| `v_pub_nom_affiche` | Nom affiché | Jina linaloonyeshwa | Non ki afiche |
| `v_pub_non_defini` | — non défini — | — haijawekwa — | — pa defini — |
| `v_pub_nouvelle_publication` | Nouvelle publication | Chapisho jipya | Nouvo piblikasyon |
| `v_pub_partager` | Partager | Shiriki | Pataje |
| `v_pub_plus_d_actions` | Plus d'actions | Vitendo zaidi | Plis aksyon |
| `v_pub_plus_tard` | Plus tard | Baadaye | Pita |
| `v_pub_programmee` | Programmée | Imepangwa | Pwograme |
| `v_pub_programmer` | Programmer | Panga | Pwograme |
| `v_pub_publication_en_cours` | Publication en cours… | Inachapisha… | Piblikasyon ap fèt… |
| `v_pub_publications_precedentes` | Publications précédentes | Machapisho yaliyotangulia | Piblikasyon anvan yo |
| `v_pub_publications_suivantes` | Publications suivantes | Machapisho yanayofuata | Piblikasyon swivan yo |
| `v_pub_publier` | Publier | Chapisha | Pibliye |
| `v_pub_recharger_du_credit` | Recharger du crédit | Ongeza salio | Ranpli kredi |
| `v_pub_rejoins_une_session_live_musique_vid` | Rejoins une session live musique + vidéo. Gratuit pour les abonné(e)s avec crédit. | Jiunge na kipindi cha moja kwa moja cha muziki + video. Bure kwa wanachama wenye salio. | Rejwenn yon sesyon an direk mizik + videyo. Gratis pou abòne ki gen kredi. |
| `v_pub_remplacer_la_video` | Remplacer la vidéo | Badilisha video | Ranplase videyo a |
| `v_pub_renouveler` | Renouveler | Sasisha | Renouvle |
| `v_pub_renouveler_48h` | Renouveler 48h | Sasisha saa 48 | Renouvle 48è |
| `v_pub_reserve_aux_abonne_e_s_avec_du_credi` | Réservé aux abonné(e)s avec du crédit. Abonne-toi pour débloquer les sessions live gratuites. | Kwa wanachama wenye salio tu. Jiunge ili ufungue vipindi vya moja kwa moja vya bure. | Rezève pou abòne ki gen kredi. Abòne w pou debloke sesyon an direk gratis yo. |
| `v_pub_s_abonner` | S'abonner | Jiunge | Abòne w |
| `v_pub_seances` | Séances | Vipindi | Sesyon yo |
| `v_pub_sessions_live_boosttribe` | Sessions live (BoostTribe) | Vipindi vya moja kwa moja (BoostTribe) | Sesyon an direk (BoostTribe) |
| `v_pub_supprimer` | Supprimer | Futa | Efase |
| `v_pub_supprimer_cette_publication` | Supprimer cette publication ? | Futa chapisho hili? | Efase piblikasyon sa a? |
| `v_pub_tu_es_abonne_e_mais_il_ne_te_reste_p` | Tu es abonné(e) mais il ne te reste plus de crédit. Recharge pour accéder aux sessions live. | Umejiunga lakini huna salio tena. Ongeza salio ili ufikie vipindi vya moja kwa moja. | Ou abòne men ou pa gen kredi ankò. Ranpli kredi pou jwenn aksè ak sesyon an direk yo. |
| `v_pub_valider` | Valider | Thibitisha | Valide |
| `v_pub_visible_48_h_puis_supprimee_automati` | Visible 48 h, puis supprimée automatiquement | Inaonekana saa 48, kisha inafutwa kiotomatiki | Vizib pandan 48 è, apre sa efase otomatikman |
| `v_pub_voir_les_offres` | Voir les offres | Ona ofa | Wè òf yo |
| `v_pub_voir_moins` | Voir moins | Ona kidogo | Wè mwens |
| `v_pub_zoom` | Zoom | Kuza | Zoum |
| `v_vit_apercu_termine` | Aperçu terminé | Onyesho la awali limekwisha | Apèsi fini |
| `v_vit_aucun_coach_specifie` | Aucun coach spécifié | Hakuna kocha aliyetajwa | Pa gen okenn antrenè presize |
| `v_vit_chargement_video` | Chargement vidéo... | Inapakia video... | Videyo ap chaje... |
| `v_vit_choisissez_d_abord_l_horaire_de_votr` | Choisissez d'abord l'horaire de votre première séance | Kwanza chagua muda wa kipindi chako cha kwanza | Chwazi dabò lè premye sesyon ou a |
| `v_vit_choisissez_votre_offre` | Choisissez votre offre | Chagua ofa yako | Chwazi òf ou |
| `v_vit_code123` | CODE123 | CODE123 | CODE123 |
| `v_vit_code_promo_optionnel` | Code Promo (optionnel) | Msimbo wa punguzo (si lazima) | Kòd pwomosyon (opsyonèl) |
| `v_vit_confirmer_la_reservation` | Confirmer la réservation | Thibitisha uhifadhi | Konfime rezèvasyon an |
| `v_vit_contenus_audio` | Contenus Audio | Maudhui ya sauti | Kontni odyo |
| `v_vit_copier_le_lien` | Copier le lien | Nakili kiungo | Kopye lyen an |
| `v_vit_email` | Email | Barua pepe | Imèl |
| `v_vit_fermer` | Fermer | Funga | Fèmen |
| `v_vit_gratuit` | GRATUIT | BURE | GRATIS |
| `v_vit_impressum` | Impressum | Taarifa za kisheria | Enfòmasyon legal |
| `v_vit_les_paiements_sont_traites_de_manier` | Les paiements sont traités de manière sécurisée via Stripe. Devise : CHF. Livraison : Suisse. | Malipo huchakatwa kwa usalama kupitia Stripe. Sarafu: CHF. Uwasilishaji: Uswisi. | Peman yo trete an sekirite atravè Stripe. Lajan: CHF. Livrezon: Lasuis. |
| `v_vit_lien_copie` | Lien copié! | Kiungo kimenakiliwa! | Lyen kopye! |
| `v_vit_lire_plus` | Lire plus | Soma zaidi | Li plis |
| `v_vit_maximum_3_seances_a_la_fois` | Maximum 3 séances à la fois | Vipindi 3 kwa wakati mmoja kwa upeo | Maksimòm 3 sesyon alafwa |
| `v_vit_mentions_legales` | Mentions légales | Taarifa za kisheria | Mansyon legal |
| `v_vit_moyens_de_paiement` | Moyens de paiement | Njia za malipo | Mwayen peman |
| `v_vit_nom_complet` | Nom complet | Jina kamili | Non konplè |
| `v_vit_nouvelle_reservation` | Nouvelle réservation | Uhifadhi mpya | Nouvo rezèvasyon |
| `v_vit_offert` | Offert | Bure | Gratis |
| `v_vit_offre_expiree` | Offre expirée | Ofa imekwisha muda | Òf la ekspire |
| `v_vit_offres_de_demarrage` | Offres de démarrage | Ofa za kuanzia | Òf demaraj |
| `v_vit_offres_disponibles` | Offres disponibles | Ofa zinazopatikana | Òf ki disponib |
| `v_vit_partager` | Partager | Shiriki | Pataje |
| `v_vit_partagez_cette_vitrine` | Partagez cette vitrine | Shiriki onyesho hili | Pataje vitrin sa a |
| `v_vit_pour_reserver_votre_offre_selectionn` | Pour réserver votre offre, sélectionnez une date ci-dessous. | Ili kuhifadhi ofa yako, chagua tarehe hapa chini. | Pou rezève òf ou a, chwazi yon dat anba a. |
| `v_vit_qr` | QR | QR | QR |
| `v_vit_questions_frequentes` | Questions fréquentes | Maswali yanayoulizwa mara kwa mara | Kesyon yo poze souvan |
| `v_vit_rechercher` | Rechercher... | Tafuta... | Chèche... |
| `v_vit_reservation_confirmee` | Réservation confirmée ! | Uhifadhi umethibitishwa! | Rezèvasyon konfime! |
| `v_vit_reservation_en_cours` | Réservation en cours... | Uhifadhi unaendelea... | Rezèvasyon ap fèt... |
| `v_vit_reserver` | Réserver | Hifadhi | Rezève |
| `v_vit_retirer_cette_seance` | Retirer cette séance | Ondoa kipindi hiki | Retire sesyon sa a |
| `v_vit_retour` | Retour | Rudi | Retounen |
| `v_vit_revoir_l_apercu` | Revoir l'aperçu | Tazama onyesho la awali tena | Gade apèsi a ankò |
| `v_vit_selectionnez_une_offre_pour_continue` | Sélectionnez une offre pour continuer | Chagua ofa ili uendelee | Chwazi yon òf pou kontinye |
| `v_vit_total` | Total | Jumla | Total |
| `v_vit_valider` | Valider | Thibitisha | Valide |
| `v_vit_verifie` | Vérifié | Imethibitishwa | Verifye |
| `v_vit_votre_nom` | Votre nom | Jina lako | Non ou |
| `v_vit_vous_recevrez_une_confirmation_par_e` | Vous recevrez une confirmation par email. | Utapokea uthibitisho kwa barua pepe. | Ou pral resevwa yon konfimasyon pa imèl. |
| `v_vit_whatsapp` | WhatsApp | WhatsApp | WhatsApp |
| `v_dev_assistant_ia` | Assistant IA | Msaidizi wa AI | Asistan AI |
| `v_dev_assistant_virtuel_pour_vos_clients` | Assistant virtuel pour vos clients | Msaidizi pepe kwa wateja wako | Yon asistan vityèl pou kliyan ou yo |
| `v_dev_aucun_pack_disponible_pour_le_moment` | Aucun pack disponible pour le moment | Hakuna kifurushi kinachopatikana kwa sasa | Pa gen okenn pak ki disponib pou kounye a |
| `v_dev_campagnes_email` | Campagnes email | Kampeni za barua pepe | Kanpay imèl |
| `v_dev_ce_pack_n_a_pas_de_prix_stripe_confi` | Ce pack n'a pas de prix Stripe configuré. Contactez l'administrateur. | Kifurushi hiki hakina bei ya Stripe iliyosanidiwa. Wasiliana na msimamizi. | Pak sa a pa gen pri Stripe konfigire. Kontakte administratè a. |
| `v_dev_chargement` | Chargement... | Inapakia... | Ap chaje... |
| `v_dev_chat_ia_integre` | Chat IA Intégré | Gumzo la AI lililojengwa ndani | Chat AI entegre |
| `v_dev_choisissez_votre_pack` | Choisissez votre Pack | Chagua Kifurushi chako | Chwazi Pak ou |
| `v_dev_code_promo` | Code Promo | Msimbo wa punguzo | Kòd pwomosyon |
| `v_dev_connecte_stripe_et_recois_tes_paieme` | Connecte Stripe et reçois tes paiements directement. | Unganisha Stripe na upokee malipo yako moja kwa moja. | Konekte Stripe epi resevwa peman ou yo dirèkteman. |
| `v_dev_credits_inclus` | Crédits inclus: | Salio linalojumuishwa: | Kredi ki enkli: |
| `v_dev_crm_automatise` | CRM Automatisé | CRM ya kiotomatiki | CRM otomatik |
| `v_dev_dashboard_complet_cours_offres_reser` | Dashboard complet : cours, offres, réservations, stats. | Dashibodi kamili: madarasa, ofa, uhifadhi, takwimu. | Dashboard konplè: kou, òf, rezèvasyon, estatistik. |
| `v_dev_devenir_partenaire_afroboost` | Devenir Partenaire Afroboost | Kuwa Mshirika wa Afroboost | Vin Patnè Afroboost |
| `v_dev_donnees_isolees` | Données isolées | Data zilizotengwa | Done izole |
| `v_dev_email` | Email * | Barua pepe * | Imèl * |
| `v_dev_envoie_des_campagnes_ciblees_pour_fi` | Envoie des campagnes ciblées pour fidéliser tes clients. | Tuma kampeni zilizolengwa ili kuwahifadhi wateja wako. | Voye kanpay sible pou fidelize kliyan ou yo. |
| `v_dev_erreur_lors_de_la_creation_du_paieme` | Erreur lors de la création du paiement Mobile Money | Hitilafu wakati wa kuunda malipo ya Mobile Money | Erè pandan kreyasyon peman Mobile Money a |
| `v_dev_erreur_lors_de_la_creation_du_paieme_2` | Erreur lors de la création du paiement PawaPay | Hitilafu wakati wa kuunda malipo ya PawaPay | Erè pandan kreyasyon peman PawaPay la |
| `v_dev_erreur_pas_d_url_de_paiement_recue_r` | Erreur: pas d'URL de paiement reçue. Réessayez. | Hitilafu: hakuna URL ya malipo iliyopokelewa. Tafadhali jaribu tena. | Erè: pa gen URL peman resevwa. Tanpri eseye ankò. |
| `v_dev_gagne_de_l_argent` | Gagne de l'argent | Pata pesa | Fè lajan |
| `v_dev_impossible_de_charger_les_offres` | Impossible de charger les offres | Imeshindwa kupakia ofa | Pa ka chaje òf yo |
| `v_dev_le_mot_de_passe_doit_contenir_au_moi` | Le mot de passe doit contenir au moins 6 caractères | Nenosiri lazima liwe na angalau herufi 6 | Modpas la dwe gen omwen 6 karaktè |
| `v_dev_le_paiement_mobile_money_est_tempora` | Le paiement Mobile Money est temporairement indisponible. Veuillez utiliser la Carte Bancaire ou réessayer plus tard. | Malipo ya Mobile Money hayapatikani kwa muda. Tafadhali tumia kadi ya benki au jaribu tena baadaye. | Peman Mobile Money pa disponib pou kounye a. Tanpri itilize yon kat bank oswa eseye ankò pita. |
| `v_dev_le_paiement_pawapay_est_temporaireme` | Le paiement PawaPay est temporairement indisponible. Veuillez utiliser une autre méthode. | Malipo ya PawaPay hayapatikani kwa muda. Tafadhali tumia njia nyingine. | Peman PawaPay pa disponib pou kounye a. Tanpri itilize yon lòt metòd. |
| `v_dev_methode_de_paiement_non_reconnue` | Méthode de paiement non reconnue. | Njia ya malipo haikutambuliwa. | Metòd peman an pa rekonèt. |
| `v_dev_minimum_6_caracteres` | Minimum 6 caractères | Angalau herufi 6 | Omwen 6 karaktè |
| `v_dev_mot_de_passe` | Mot de passe * | Nenosiri * | Modpas * |
| `v_dev_nom_complet` | Nom complet * | Jina kamili * | Non konplè * |
| `v_dev_optionnel` | Optionnel | Si lazima | Opsyonèl |
| `v_dev_pack_selectionne` | Pack sélectionné: | Kifurushi kilichochaguliwa: | Pak ou chwazi a: |
| `v_dev_page_de_vente_perso` | Page de Vente Perso | Ukurasa wa mauzo wa kibinafsi | Paj lavant pèsonalize |
| `v_dev_paiement_stripe` | Paiement Stripe | Malipo ya Stripe | Peman Stripe |
| `v_dev_pourquoi_devenir_partenaire` | 🚀 Pourquoi devenir Partenaire ? | 🚀 Kwa nini kuwa Mshirika? | 🚀 Poukisa vin Patnè? |
| `v_dev_pourquoi_devenir_partenaire_afroboos` | Pourquoi devenir Partenaire Afroboost ? | Kwa nini kuwa Mshirika wa Afroboost? | Poukisa vin Patnè Afroboost? |
| `v_dev_questions_frequentes` | Questions fréquentes | Maswali yanayoulizwa mara kwa mara | Kesyon yo poze souvan |
| `v_dev_rejoins_la_communaute_afroboost_et_l` | Rejoins la communauté Afroboost et lance ton activité de coaching avec tous les outils intégrés pour réussir. | Jiunge na jumuiya ya Afroboost na uanze biashara yako ya ukocha kwa zana zote zilizojengwa ndani ili kufanikiwa. | Rejwenn kominote Afroboost la epi lanse aktivite antrènman ou ak tout zouti entegre yo pou reyisi. |
| `v_dev_s_inscrire_gratuitement` | S'inscrire gratuitement | Jisajili bure | Enskri gratis |
| `v_dev_telephone` | Téléphone | Simu | Telefòn |
| `v_dev_tes_donnees_sont_privees_personne_d_` | Tes données sont privées. Personne d'autre n'y a accès. | Data yako ni ya faragha. Hakuna mtu mwingine mwenye ufikiaji. | Done ou yo prive. Pèsonn lòt pa gen aksè ak yo. |
| `v_dev_ton_espace_perso` | Ton espace perso | Eneo lako binafsi | Espas pèsonèl ou |
| `v_dev_total` | Total: | Jumla: | Total: |
| `v_dev_tous_vos_contacts_centralises` | Tous vos contacts centralisés | Anwani zako zote mahali pamoja | Tout kontak ou yo nan yon sèl kote |
| `v_dev_traitement` | Traitement... | Inachakata... | Ap trete... |
| `v_dev_un_chatbot_ia_pour_engager_tes_prosp` | Un chatbot IA pour engager tes prospects 24h/24. | Chatbot ya AI kuwavutia wateja watarajiwa wako saa 24. | Yon chatbot AI pou angaje pwospè ou yo 24è sou 24. |
| `v_dev_vends_tes_seances_packs_et_produits_` | Vends tes séances, packs et produits directement sur ta vitrine. | Uza vipindi, vifurushi na bidhaa zako moja kwa moja kwenye onyesho lako. | Vann sesyon, pak ak pwodwi ou yo dirèkteman sou vitrin ou. |
| `v_dev_veuillez_choisir_un_mot_de_passe` | Veuillez choisir un mot de passe | Tafadhali chagua nenosiri | Tanpri chwazi yon modpas |
| `v_dev_veuillez_remplir_tous_les_champs_obl` | Veuillez remplir tous les champs obligatoires | Tafadhali jaza sehemu zote zinazohitajika | Tanpri ranpli tout chan obligatwa yo |
| `v_dev_vos_informations` | Vos Informations | Taarifa zako | Enfòmasyon ou yo |
| `v_dev_votre_vitrine_professionnelle` | Votre vitrine professionnelle | Onyesho lako la kitaalamu | Vitrin pwofesyonèl ou |
| `v_dev_vous_devez_accepter_les_conditions_g` | Vous devez accepter les conditions générales d'utilisation | Lazima ukubali masharti ya matumizi | Ou dwe aksepte kondisyon itilizasyon yo |
| `vm_choisissez` | Choisissez {choix} | Chagua {choix} | Chwazi {choix} |
| `vm_et` |  et  |  na  |  ak  |
| `vm_prompt_size` | une taille | ukubwa | yon gwosè |
| `vm_prompt_color` | une couleur | rangi | yon koulè |
| `vm_prompt_weight` | un poids | uzito | yon pwa |
| `vm_reserver_montant` | Réserver — {montant} CHF ({n}×) | Hifadhi — {montant} CHF ({n}×) | Rezève — {montant} CHF ({n}×) |
| `vm_reserver_montant_x` | Réserver — {montant} CHF ({n}x) | Hifadhi — {montant} CHF ({n}x) | Rezève — {montant} CHF ({n}x) |
| `vm_boutique_chargement` | Chargement de la boutique… | Duka linapakia… | Boutik la ap chaje… |
| `vm_boutique_vide` | Aucun produit pour le moment. | Hakuna bidhaa kwa sasa. | Pa gen okenn pwodwi pou kounye a. |
| `vm_live_hors` | Le direct n’a pas commencé. | Matangazo ya moja kwa moja hayajaanza. | Emisyon an direk la poko kòmanse. |
| `vm_live_rejoindre` | Rejoindre le direct | Jiunge na matangazo ya moja kwa moja | Rejwenn emisyon an direk la |
| `v_app2_acceder_a_mon_espace` | Accéder à mon espace | Nenda kwenye eneo langu | Ale nan espas mwen |
| `v_app2_adresse_e_mail_inconnue` | Adresse e-mail inconnue. | Anwani ya barua pepe haijulikani. | Adrès imèl enkoni. |
| `v_app2_adresse_e_mail_invalide` | Adresse e-mail invalide. | Anwani ya barua pepe si sahihi. | Adrès imèl pa valab. |
| `v_app2_afroboost_live_est_en_direct` | Afroboost Live est en direct | Afroboost Live iko moja kwa moja | Afroboost Live an direk |
| `v_app2_afroboost_live_est_en_direct_rejoind` | Afroboost Live est en direct — rejoindre | Afroboost Live iko moja kwa moja — jiunge | Afroboost Live an direk — rejwenn |
| `v_app2_ajoutez_afroboost_a_votre_ecran` | Ajoutez Afroboost à votre écran | Ongeza Afroboost kwenye skrini yako | Ajoute Afroboost sou ekran ou |
| `v_app2_aucun_nouveau_paiement_n_a_ete_cree` | Aucun nouveau paiement n’a été créé. | Hakuna malipo mapya yaliyoundwa. | Pa gen okenn nouvo peman ki kreye. |
| `v_app2_bienvenue_choisissez_un_pack_pour_de` | ✨ Bienvenue ! Choisissez un pack pour devenir partenaire. | ✨ Karibu! Chagua kifurushi ili kuwa mshirika. | ✨ Byenveni! Chwazi yon pak pou vin yon patnè. |
| `v_app2_ce_produit_n_est_plus_disponible` | Ce produit n'est plus disponible. | Bidhaa hii haipatikani tena. | Pwodwi sa a pa disponib ankò. |
| `v_app2_chargement_du_produit` | Chargement du produit… | Inapakia bidhaa… | Pwodwi a ap chaje… |
| `v_app2_comment` | Comment ? | Vipi? | Kijan? |
| `v_app2_en_direct` | EN DIRECT | MOJA KWA MOJA | AN DIRÈK |
| `v_app2_envoi` | Envoi… | Inatuma… | Ap voye… |
| `v_app2_envoi_en_cours` | Envoi en cours… | Inatuma… | Ap voye… |
| `v_app2_envoyer_ma_demande` | Envoyer ma demande | Tuma ombi langu | Voye demann mwen |
| `v_app2_fermer_le_menu` | Fermer le menu | Funga menyu | Fèmen meni an |
| `v_app2_indique_ton_nom_et_prenom` | Indique ton nom et prénom. | Weka jina lako la kwanza na la ukoo. | Antre non ou ak prenon ou. |
| `v_app2_installer` | Installer | Sakinisha | Enstale |
| `v_app2_installer_l_app_afroboost` | Installer l'app Afroboost | Sakinisha programu ya Afroboost | Enstale aplikasyon Afroboost la |
| `v_app2_la_boutique` | La boutique | Duka | Boutik la |
| `v_app2_la_date_de_naissance_est_obligatoire` | La date de naissance est obligatoire | Tarehe ya kuzaliwa inahitajika | Dat nesans obligatwa |
| `v_app2_lien_copie` | Lien copié ! | Kiungo kimenakiliwa! | Lyen kopye! |
| `v_app2_live` | LIVE | LIVE | LIVE |
| `v_app2_numero_whatsapp_deja_utilise` | Numéro WhatsApp déjà utilisé | Nambari ya WhatsApp tayari imetumika | Nimewo WhatsApp deja itilize |
| `v_app2_numero_whatsapp_invalide_ex_41_79_12` | Numéro WhatsApp invalide (ex. +41 79 123 45 67). | Nambari ya WhatsApp si sahihi (mf. +41 79 123 45 67). | Nimewo WhatsApp pa valab (ex. +41 79 123 45 67). |
| `v_app2_offre_indisponible` | Offre indisponible | Ofa haipatikani | Òf pa disponib |
| `v_app2_ouvrir_afroboost_live` | Ouvrir Afroboost Live | Fungua Afroboost Live | Louvri Afroboost Live |
| `v_app2_ouvrir_le_menu` | Ouvrir le menu | Fungua menyu | Louvri meni an |
| `v_app2_paiement_annule_vous_pouvez_reessaye` | Paiement annulé. Vous pouvez réessayer. | Malipo yameghairiwa. Unaweza kujaribu tena. | Peman anile. Ou ka eseye ankò. |
| `v_app2_partager_cette_offre` | Partager cette offre | Shiriki ofa hii | Pataje òf sa a |
| `v_app2_son` | 🔇 Son | 🔇 Sauti | 🔇 Son |
| `v_app2_tu_as_deja_cette_formule` | Tu as déjà cette formule | Tayari una mpango huu | Ou deja gen fòmil sa a |
| `v_app2_un_instant` | Un instant… | Subiri kidogo… | Yon moman… |
| `v_app2_voir_moins_d_horaires` | Voir moins d'horaires | Ona muda mchache | Wè mwens orè |
| `v_app2_votre_session_a_expire_reconnectez_v` | Votre session a expiré. Reconnectez-vous pour retrouver vos données. | Kipindi chako kimeisha muda. Ingia tena ili kupata data yako. | Sesyon ou an ekspire. Konekte ankò pou jwenn done ou yo. |
| `v_mem2_code_invalide_ou_expire_demande_un_n` | Code invalide ou expiré. Demande un nouveau code. | Msimbo si sahihi au umeisha muda. Omba msimbo mpya. | Kòd la pa valab oswa li ekspire. Mande yon nouvo kòd. |
| `v_mem2_email_ou_whatsapp_requis` | Email ou WhatsApp requis | Barua pepe au WhatsApp inahitajika | Imèl oswa WhatsApp obligatwa |
| `v_mem2_indique_une_adresse_e_mail_valide` | Indique une adresse e-mail valide. | Weka anwani sahihi ya barua pepe. | Antre yon adrès imèl valab. |
| `v_mem2_l_envoi_n_a_pas_pu_aboutir_verifie_t` | L'envoi n'a pas pu aboutir. Vérifie ta connexion et réessaie. | Kutuma hakukufanikiwa. Angalia muunganisho wako na ujaribu tena. | Voye a pa t reyisi. Verifye koneksyon ou epi eseye ankò. |
| `v_mem2_le_code_comporte_6_chiffres` | Le code comporte 6 chiffres. | Msimbo una tarakimu 6. | Kòd la gen 6 chif. |
| `v_mem2_le_paiement_est_momentanement_indisp` | Le paiement est momentanément indisponible. Réessaye. | Malipo hayapatikani kwa muda. Jaribu tena. | Peman an pa disponib pou kounye a. Eseye ankò. |
| `v_mem2_prenom_requis` | Prénom requis | Jina la kwanza linahitajika | Prenon obligatwa |
| `v_mem2_trop_de_demandes_reessaie_dans_quelq` | Trop de demandes. Réessaie dans quelques minutes. | Maombi mengi mno. Jaribu tena baada ya dakika chache. | Twòp demann. Eseye ankò nan kèk minit. |
| `v_mem2_trop_de_tentatives_reessaie_dans_que` | Trop de tentatives. Réessaie dans quelques minutes. | Majaribio mengi mno. Jaribu tena baada ya dakika chache. | Twòp tantativ. Eseye ankò nan kèk minit. |
| `v_mem2_verification_momentanement_indisponi` | Vérification momentanément indisponible. Réessaie dans un instant. | Uthibitishaji haupatikani kwa muda. Jaribu tena baada ya muda mfupi. | Verifikasyon pa disponib pou kounye a. Eseye ankò talè. |
| `v_pub2_publication_modifiee` | Publication modifiée ! | Chapisho limesasishwa! | Piblikasyon modifye! |

## Kiswahili et créole haïtien — réservation, paiement, billet, jours (73 textes)

| Clé | Kiswahili (sw) | Kreyòl (ht) |
|---|---|---|
| `conceptDefault` | Dhana ya Afroboost: mazoezi ya moyo + dansi ya afrobeat + vipokea sauti vya kuzama. Mazoezi ya kufurahisha, yenye nguvu na yanayofaa kila mtu. | Konsèp Afroboost la: kadyo + dans afrobeat + kask odyo imèsif. Yon antrennman amizan, plen enèji epi aksesib pou tout moun. |
| `chooseSession` | Chagua kipindi chako | Chwazi sesyon ou |
| `chooseYourSession` | Chagua kipindi chako | Chwazi sesyon ou |
| `chooseOffer` | Chagua ofa yako | Chwazi òf ou |
| `selectSessionFirst` | Chagua kipindi na tarehe ili kuhifadhi | Chwazi yon sesyon ak dat pou rezève |
| `yourInfo` | Taarifa zako | Enfòmasyon ou yo |
| `fullName` | Jina kamili | Non konplè |
| `emailRequired` | Barua pepe (lazima) | Imèl (obligatwa) |
| `whatsappRequired` | WhatsApp (lazima) | WhatsApp (obligatwa) |
| `promoCode` | Msimbo wa punguzo | Kòd pwomosyon |
| `total` | Jumla | Total |
| `alreadySubscribed` | Tayari nimejiunga | Mwen deja abòne |
| `selectProfile` | Chagua wasifu wako... | Chwazi pwofil ou... |
| `acceptTerms` | Nakubali | Mwen aksepte |
| `termsLink` | masharti ya jumla | kondisyon jeneral yo |
| `termsTitle` | Masharti ya Jumla | Kondisyon Jeneral yo |
| `quantity` | Kiasi | Kantite |
| `payAndReserve` | 💳 Lipa na uhifadhi | 💳 Peye epi rezève |
| `reserveFree` | Hifadhi bure | Rezève gratis |
| `coachLogin` | Kuingia kwa Mshirika | Koneksyon Patnè |
| `password` | Nenosiri | Modpas |
| `forgotPassword` | Umesahau nenosiri? | Ou bliye modpas ou? |
| `back` | ← Rudi | ← Retounen |
| `reservations` | Uhifadhi | Rezèvasyon yo |
| `code` | Msimbo | Kòd |
| `reservationCode` | Msimbo | Kòd |
| `name` | Jina | Non |
| `date` | Tarehe | Dat |
| `time` | Saa | Lè |
| `offer` | Ofa | Òf |
| `qty` | Idadi | Kantite |
| `paymentDone` | Malipo yamefanyika? | Peman fèt? |
| `paymentConfirmText` | Ikiwa umekamilisha malipo, bofya hapa chini ili kuthibitisha. | Si w fin fè peman an, klike anba a pou valide. |
| `confirmPayment` | ✅ Thibitisha malipo yangu | ✅ Konfime peman mwen |
| `reservationConfirmed` | Uhifadhi umethibitishwa! | Rezèvasyon konfime! |
| `print` | 🖨️ Chapisha | 🖨️ Enprime |
| `share` | 📱 Shiriki | 📱 Pataje |
| `shareBtn` | Shiriki | Pataje |
| `saveTicket` | 📥 Hifadhi tikiti yangu | 📥 Anrejistre tikè mwen |
| `shareWithImage` | 📤 Shiriki na QR | 📤 Pataje ak QR |
| `generatingImage` | Inatengenezwa... | Ap kreye... |
| `emailWhatsappRequired` | Barua pepe na nambari ya WhatsApp ni lazima. | Imèl ak nimewo WhatsApp obligatwa. |
| `invalidPromoCode` | Msimbo wa punguzo si sahihi. | Kòd pwomosyon an pa valab. |
| `noPaymentConfigured` | Malipo yanahitajika – uhifadhi hauwezekani. | Peman obligatwa – rezèvasyon pa posib. |
| `subscriberOnlyCode` | Ni wanachama waliojiunga pekee wanaoweza kutumia msimbo huu. | Sèlman abòne yo ka itilize kòd sa a. |
| `wrongCredentials` | Barua pepe au nenosiri si sahihi | Imèl oswa modpas pa kòrèk |
| `discount` | Punguzo | Rediksyon |
| `sunday` | Jumapili | Dimanch |
| `monday` | Jumatatu | Lendi |
| `tuesday` | Jumanne | Madi |
| `wednesday` | Jumatano | Mèkredi |
| `thursday` | Alhamisi | Jedi |
| `friday` | Ijumaa | Vandredi |
| `saturday` | Jumamosi | Samdi |
| `scanToValidate` | Changanua ili kuthibitisha | Eskane pou valide |
| `homeTab` | Mwanzo | Akèy |
| `communityTab` | Jumuiya | Kominote |
| `liveNav` | Moja kwa moja | An direk |
| `liveNavEnCours` | MOJA KWA MOJA SASA | AN DIRÈK KOUNYE A |
| `liveNavTitre` | Video ya moja kwa moja — jiunge na matangazo | Videyo an direk — rejwenn emisyon an |
| `noResults` | Hakuna matokeo | Pa gen rezilta |
| `tryAnotherSearch` | Jaribu neno lingine la utafutaji | Eseye yon lòt tèm rechèch |
| `results` | matokeo | rezilta |
| `shopDescription` | Bidhaa za kipekee za Afroboost | Pwodwi eksklizif Afroboost |
| `deliveryAvailable` | Uwasilishaji unapatikana | Livrezon disponib |
| `audioShop` | Duka la Sauti | Boutik Odyo |
| `audioDescription` | Muziki na maudhui ya sauti ya kipekee | Mizik ak kontni odyo eksklizif |
| `platform` | Jukwaa la makocha | Platfòm antrenè yo |
| `findCoach` | Tafuta kocha | Jwenn yon antrenè |
| `searchOffers` | Tafuta ofa... | Chèche yon òf... |
| `credits` | Salio | Kredi |
| `unlimited` | Bila kikomo | San limit |
| `noReservations` | Hakuna uhifadhi kwa sasa | Pa gen rezèvasyon pou kounye a |

## Lingala, wolof, bambara, bàsàa — le peu qui existe

Ces entrées sont du **vocabulaire** (un ou deux mots). Elles viennent de la table visiteur ou du lexique vérifié du serveur (`_V302_LEXIQUE`, avec ses sources).

- **ln** : `Fermer` → `Kokanga` ; `Fermer` → `Kokanga` ; `Fermer` → `Kokanga` ; `Fermer` → `Kokanga` ; `Fermer` → `Kokanga`
- **wo** : `Fermer` → `Tëj` ; `Fermer` → `Tëj` ; `Fermer` → `Tëj` ; `Fermer` → `Tëj` ; `Fermer` → `Tëj`
- **bm** : `Fermer` → `Datugu` ; `Fermer` → `Datugu` ; `Fermer` → `Datugu` ; `Fermer` → `Datugu` ; `Fermer` → `Datugu`
- **bas** : — (aucune entrée : tout en français)

## Retiré parce que faux

- `wo.discoverCta` : la phrase contenait « cours », « réservé » et « next » — du français et de l'anglais dans une phrase censée être en wolof. Le français vaut mieux qu'un faux wolof.
