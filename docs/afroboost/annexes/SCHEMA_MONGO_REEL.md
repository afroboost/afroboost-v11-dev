# Annexe — Schéma MongoDB RÉEL (production, base `promo-credits-lab`)

> Relevé en **lecture seule** le 19/10/2026 : noms de champs, types observés sur les 300 documents les plus récents,
> nombre de documents (estimation) et index. **Aucune valeur** n'est reproduite. Un pourcentage indique un champ présent
> sur une partie seulement des documents échantillonnés (schéma souple MongoDB).

| Collection | Docs | Index (hors _id) |
|---|---:|---|
| `ai_config` | 2 | aucun |
| `ai_logs` | 663 | aucun |
| `ambassadeur_boosts` | 0 | coach_id:1,parrain_empreinte:1; payment_intent:1 |
| `analytics_monthly_reports` | 1 | cle:1 U; id:1 U |
| `app_secrets` | 1 | aucun |
| `audio_tracks` | 1 | aucun |
| `boosttribe_live` | 1 | aucun |
| `boosttribe_live_journal` | 310 | aucun |
| `boosttribe_usage` | 5 | created_dt:1 |
| `bot_quick_replies` | 6 | aucun |
| `bot_whatsapp_etat` | 1 | aucun |
| `calendar_events` | 3 | id:1 U; coach_id:1,starts_at:1,id:1; coach_id:1,event_type:1; event_type:1,status:1,starts_at:1; coach_id:1,recipient_key:1,starts_at:1; coach_id:1,prospect_id:1,starts_at:1; coach_id:1,creneau_cle:1 U; rdv_token_unique:1 U |
| `campaign_errors` | 94 | aucun |
| `campaigns` | 13 | aucun |
| `categories` | 5 | aucun |
| `chat_groups` | 14 | aucun |
| `chat_messages` | 2965 | aucun |
| `chat_participants` | 1249 | aucun |
| `chat_sessions` | 563 | aucun |
| `checkout_transactions` | 68 | aucun |
| `coach_packs` | 3 | aucun |
| `coach_profiles` | 2 | aucun |
| `coach_sessions` | 7 | aucun |
| `coaches` | 1 | aucun |
| `coaching_notes` | 0 | target_type:1,target_id:1 U |
| `code_members` | 20 | aucun |
| `comments` | 754 | aucun |
| `concept` | 20 | aucun |
| `config` | 2 | aucun |
| `contact_categories` | 13 | aucun |
| `contact_segments_config` | 1 | aucun |
| `courses` | 24 | aucun |
| `creators` | 1 | id:1 U; email:1 U; share_token:1 U; status:1,created_at:-1 |
| `deleted_items` | 65 | aucun |
| `discount_codes` | 67 | aucun |
| `emailjs_config` | 1 | aucun |
| `espace_liens_acces` | 6 | aucun |
| `evenement_places` | 2 | aucun |
| `faqs` | 4 | aucun |
| `feature_flags` | 2 | aucun |
| `free_trial_claims` | 61 | aucun |
| `google_tokens` | 1 | coach_email:1 U |
| `google_users` | 2 | aucun |
| `invitation_events` | 59 | cle:1 U; coach_id:1,type_invitation:1,evenement:1; campagne_id:1,evenement:1 |
| `invitation_relais` | 2 | jeton:1 U; preuve_cle:1 U; campagne_id:1,email_empreinte:1; campagne_id:1,generation:1 |
| `invites_live` | 2 | appareils.h:1 U; id:1 U |
| `invoices` | 1 | aucun |
| `leads` | 170 | submission_id:1 U |
| `media_links` | 2 | aucun |
| `memberships` | 6 | aucun |
| `notification_preferences` | 1 | aucun |
| `notifications` | 244 | aucun |
| `offers` | 17 | aucun |
| `page_likes` | 3 | aucun |
| `partner_payment_config` | 2 | aucun |
| `partner_prospects` | 435 | id:1 U; coach_id:1,ref:1 U; coach_id:1,dedupe_key:1; coach_id:1,status:1; coach_id:1,category:1; coach_id:1,wave:1; coach_id:1,priority:1; coach_id:1,recipient_key:1 |
| `partners` | 1 | partner_slug:1 U; lead_id:1 U; prospect_id:1 U |
| `password_resets` | 1 | aucun |
| `pawapay_transactions` | 0 | aucun |
| `payment_links` | 15 | aucun |
| `payment_transactions` | 293 | aucun |
| `payout_requests` | 0 | id:1 U; creator_id:1,created_at:-1 |
| `platform_settings` | 3 | aucun |
| `private_conversations` | 12 | aucun |
| `private_messages` | 148 | aucun |
| `progress_entries` | 0 | subscriber_code:1,entry_date:-1 |
| `prospect_campaign_actions` | 844 | id:1 U; campaign_id:1,recipient_key:1 U; coach_id:1,recipient_key:1 U; campaign_id:1,statut:1; coach_id:1,created_at:-1,id:1; coach_id:1,rfc_message_id:1; reply_token:1 U; rdv_token:1 U |
| `prospect_campaigns` | 10 | id:1 U; coach_id:1,created_at:-1,id:1; coach_id:1,etat:1; coach_id:1,idempotency_key:1 U |
| `prospect_inbound_messages` | 69 | coach_id:1,dedupe_key:1 U; coach_id:1,received_at:-1,id:1; coach_id:1,statut:1; coach_id:1,read_at:1; coach_id:1,traite_at:1 |
| `prospect_notes` | 104 | action_id:1,occurred_at:1,created_at:1; coach_id:1,created_at:-1; inbound_id:1 |
| `prospect_reply_drafts` | 53 | inbound_id:1 U; coach_id:1,updated_at:-1 |
| `prospect_reply_sends` | 52 | id:1 U; coach_id:1,created_at:-1; inbound_id:1 |
| `prospection_medias` | 28 | aucun |
| `prospection_niches` | 8 | aucun |
| `publications` | 4 | aucun |
| `push_subscriptions` | 346 | endpoint:1 U |
| `qr_validations` | 3 | aucun |
| `rattrapage_essai_historique` | 8 | aucun |
| `rattrapage_essai_historique_liste` | 7 | aucun |
| `recovery_attempts` | 21 | aucun |
| `referral_campaigns` | 12 | id:1 U; share_token:1 U; coach_id:1,status:1,updated_at:-1 |
| `referral_commissions` | 0 | id:1 U; cle_paiement:1 U; creator_id:1,created_at:-1; payment_id:1 |
| `referral_invitations` | 30 | pass_id:1,created_at:-1; sponsor_email_norm:1,created_at:-1 |
| `referral_passes` | 30 | id:1 U; share_token:1 U; invitee.email_norm:1,course_id:1,occurrence:1 U; coach_id:1,status:1,created_at:-1; origin.campaign_id:1,status:1; origin.campaign_id:1,origin.entry_key_hash:1; chain.parent_pass_id:1,chain.rang:1 U; sponsor.email_norm:1,course_id:1,occurrence:1,chain.rang:1 U |
| `referral_share_settings` | 1 | aucun |
| `reminder_sends` | 498 | aucun |
| `resend_envois` | 490 | aucun |
| `resend_evenements` | 1023 | aucun |
| `resend_quota` | 2 | aucun |
| `reservation_cancellations` | 5 | aucun |
| `reservations` | 191 | aucun |
| `seance_mouvements` | 57 | aucun |
| `session_adjustments` | 7 | aucun |
| `smart_entry_attempts` | 1720 | aucun |
| `social_proofs` | 3 | aucun |
| `spordate_bridge_usage` | 1122 | aucun |
| `subscriber_infos` | 9 | aucun |
| `subscriber_otp` | 83 | aucun |
| `subscriber_sessions` | 64 | aucun |
| `subscribers` | 43 | channel:1,value:1 U; unsubscribe_token:1; confirm_token:1 |
| `subscriptions` | 100 | aucun |
| `terms_versions` | 1 | aucun |
| `trajets_cache` | 5 | aucun |
| `upload_chunks` | 0 | aucun |
| `uploaded_files` | 113 | aucun |
| `users` | 140 | aucun |
| `users_auth` | 11 | aucun |
| `whatsapp_config` | 1 | aucun |
| `whatsapp_statuts` | 1322 | aucun |

## Champs par collection

### `ai_config` (2 docs)

enabled(bool), systemPrompt(str), model(str), provider(str), lastMediaUrl(str), twintPaymentUrl(str), campaignPrompt(str), id(str 50%)

### `ai_logs` (663 docs)

timestamp(str), responseTime(float), from(str 85%), email(str 85%), whatsapp(str 85%), source(str 85%), message(str 85%), response(str 85%), id(str 15%), fromPhone(str 15%), clientName(str 15%), incomingMessage(str 15%), aiResponse(str 15%)

### `ambassadeur_boosts` (0 docs)

_(vide)_

### `analytics_monthly_reports` (1 docs)

id(str), cle(str), annee(int), mois(int), periode(dict), perimetre(dict), statut(str), version(int), schema_version(int), analytics_version(str), created_at(str), created_by(str), bilan_genere_le(str), hash(str), bilan(dict)

### `app_secrets` (1 docs)

id(str), secret(str), updated_at(str)

### `audio_tracks` (1 docs)

id(str), coach_email(str), url(str), title(str), cover_url(str), description(str), price(float), preview_duration(int), duration(NoneType), order(int), visible(bool), created_at(str)

### `boosttribe_live` (1 docs)

ended(bool), host(str), session_code(str), started_at(str), updated_at(str), ended_at(str), ended_by(str), ended_prev(dict), ended_reason(str), ended_request_id(str), ended_source(str), ended_user_agent(str), expiration_journalisee_at(NoneType), owner(str), surfaces(dict)

### `boosttribe_live_journal` (310 docs)

event(str), outcome(str), session_code(str), at(str), by(str 98%), request_id(str 98%), user_agent(str 98%), source(NoneType/str 73%), owner(NoneType/str 73%), prev(dict 58%), reconnexion(bool 42%), reason(str 33%), transition(bool 30%), meme_live(bool 30%), status(int 26%), cause(str 2%), host(str 2%), started_at(str 2%), last_seen(str 2%), age_s(int 2%), silence_s(int 2%), via(str 2%), refus(str 1%), autres_surfaces(list 1%)

### `boosttribe_usage` (5 docs)

status(str), created_at(str), kind(str), code(str), email(str), debited_at(str 60%), remaining(int 60%), created_dt(datetime 20%)

### `bot_quick_replies` (6 docs)

id(str), emoji(str), label(str), response(str), order(int), active(bool), updated_at(str), updated_by(str), icon(str), response_avant_v615(str 33%)

### `bot_whatsapp_etat` (1 docs)

telephone(str), derniere_interaction_le(str), mis_a_jour_le(str), nom(str), etape(str), creneau_demande(str), pause_jusqu_a(str), dernier_lien_le(str), dernier_lien_offre(str), dernier_lien_stripe(str)

### `calendar_events` (3 docs)

id(str), coach_id(str), title(str), description(str), location(str), starts_at(str), ends_at(str), all_day(bool), event_type(str), status(str), priority(NoneType/str), completed_at(NoneType/str), prospect_id(NoneType/str), campaign_id(NoneType/str), campaign_action_id(NoneType/str), is_deleted(bool), created_at(str), updated_at(str), recipient_key(str 67%), deleted_at(str 67%), inbound_id(NoneType 33%), origine(str 33%), meeting_type(str 33%), duration_minutes(int 33%)

### `campaign_errors` (94 docs)

campaign_id(str), campaign_name(str), error_type(str), error_code(str), error_message(str), channel(str), to_phone(str), http_status(int), created_at(str), more_info(str 24%), from_phone(str 24%)

### `campaigns` (13 docs)

id(str), name(str), message(str), mediaUrl(str), mediaFormat(str), mediaType(NoneType), targetType(str), selectedContacts(list), channels(dict), targetGroupId(str), targetIds(list), targetConversationId(NoneType/str), targetConversationName(NoneType/str), scheduledAt(NoneType/str), status(str), ctaType(NoneType/str), ctaText(NoneType/str), ctaLink(NoneType/str), systemPrompt(NoneType/str), descriptionPrompt(NoneType/str), coach_id(str), results(list), createdAt(str), updatedAt(str), targetCategories(list 85%), launchedAt(str 77%), thumbnail_source(str 8%), thumbnail_time(float 8%), thumbnail_url(str 8%), error(NoneType 8%)

### `categories` (5 docs)

name(str), icon(str)

### `chat_groups` (14 docs)

id(str), name(str), coach_id(str), member_ids(list), system_prompt(str), is_ai_active(bool), link_token(str), mode(str), created_at(str), updated_at(str), is_deleted(bool), deleted_at(str 79%), visible_to_subscribers(bool 21%)

### `chat_messages` (2965 docs)

id(str), session_id(str), sender_id(str), sender_name(str), sender_type(str), content(str), created_at(str), media_url(NoneType 96%), timestamp(str 96%), cta_type(str 88%), cta_text(str 88%), cta_link(str 88%), channel(str 72%), campaign_id(str 72%), campaign_name(str 72%), is_group(bool 28%), mode(str 4%), is_deleted(bool 4%), notified(bool 4%), deleted_at(NoneType 4%), media_expired(bool 4%)

### `chat_participants` (1249 docs)

id(str), name(str), email(str), source(str), created_at(str), coach_id(str 99%), whatsapp(str 96%), link_token(NoneType/str 94%), last_seen_at(NoneType/str 94%), updated_at(str 10%), phone(str 8%), code(str 2%), objectifs(str 2%), contact_type(str 1%), contact_type_set_at(str 1%), contact_type_set_by(str 1%), isSubscriber(bool 0%), subscriptionCode(str 0%)

### `chat_sessions` (563 docs)

id(str), participant_ids(list), mode(str), created_at(str), updated_at(str), participantEmail(str 94%), participantName(str 94%), is_ai_active(bool 87%), is_deleted(bool 87%), link_token(str 87%), deleted_at(NoneType/str 87%), title(NoneType/str 87%), notes(NoneType 87%), custom_prompt(NoneType/str 87%), deleted_by(str 37%), last_message_at(str 13%), participant_name(str 9%), coach_id(str 0%), lead_type(str 0%), tunnel_questions(list 0%), end_actions(list 0%), welcome_message(str 0%), is_smart_link(bool 0%)

### `checkout_transactions` (68 docs)

transaction_id(str), status(str), completed_at(str 91%), stripe_session_id(str 10%), coach_email(str 10%), customer_email(str 10%), customer_name(str 10%), customer_phone(str 10%), items(list 10%), total(float 10%), currency(str 10%), payment_method(str 10%), discount_code(NoneType 10%), created_at(str 10%), terms_fields(dict 7%)

### `coach_packs` (3 docs)

id(str), name(str), price(float/int), credits(int), description(str), features(list), visible(bool), stripe_price_id(str), stripe_product_id(str), created_at(str), updated_at(NoneType/str)

### `coach_profiles` (2 docs)

email(str), photo_url(str), updated_at(str), preferences(dict), photoUrl(str 50%), reminder_rules(list 50%), reminder_rules_updated_at(str 50%)

### `coach_sessions` (7 docs)

session_id(str), user_id(str), email(str), name(str), session_token(str), expires_at(str), created_at(str)

### `coaches` (1 docs)

email(str), accent_color(str), logo_url(str), updated_at(str), meta_description(str), meta_title(str), seo_keywords(str), last_login(str)

### `coaching_notes` (0 docs)

_(vide)_

### `code_members` (20 docs)

id(str), code(str), slug(str), name(str), email(str), whatsapp(str), created_at(str)

### `comments` (754 docs)

id(str), user_name(str), text(str), profile_photo(str), likes(int), is_ai(bool), is_visible(bool), coach_id(str), created_at(str)

### `concept` (20 docs)

appName(str), description(str), heroImageUrl(str), heroVideoUrl(str), id(str 95%), coach_id(NoneType/str 95%), logoUrl(str 90%), faviconUrl(str 90%), termsText(str 90%), googleReviewsUrl(str 90%), defaultLandingSection(str 90%), externalLink1Title(str 90%), externalLink1Url(str 90%), externalLink2Title(str 90%), externalLink2Url(str 90%), paymentTwint(bool 90%), paymentPaypal(bool 90%), paymentCreditCard(bool 90%), eventPosterEnabled(bool 90%), eventPosterMediaUrl(str 90%), primaryColor(str 90%), secondaryColor(str 90%), backgroundColor(str 90%), glowColor(str 90%), heroVideos(list 65%), termsTextPartners(str 45%), termsTextRecording(str 10%), eventPosterReserveLabel(str 10%), eventPosterOffersLabel(str 10%), vitrineSectionOrder(str 10%), heroCtaLabel(str 5%), heroSubtitle(str 5%), heroTitle(str 5%), heroLayout(dict 5%)

### `config` (2 docs)

background_color(str), gradient_color(str), primary_color(str), secondary_color(str), text_color(str), font_family(str), font_size(int), app_title(str), app_subtitle(str), concept_description(str), choose_session_text(str), choose_offer_text(str), user_info_text(str), button_text(str), id(str 50%)

### `contact_categories` (13 docs)

id(str), coach_id(str), name(str), color(str), icon(str), is_default(bool), order(int), created_at(str)

### `contact_segments_config` (1 docs)

id(str), version(str), cree_le(str), cree_par(str), commentaire(str), numeros_internes(list), emails_internes(list), regles(dict), segments(dict)

### `courses` (24 docs)

id(str), name(str), weekday(NoneType/int), time(str), location(NoneType/str), locationName(str), mapsUrl(str), coach_id(str), visible(bool), archived(bool), audio_tracks(NoneType/list 96%), region(str 96%), playlist(NoneType/list 92%), date(NoneType/str 83%), filmed(NoneType/bool 42%), reminders_enabled(NoneType/bool 29%), reminder_rules(NoneType/list 29%), reminders_updated_at(str 21%), saison(str 8%), visible_avant_v615(bool 8%), visible_par_saison(str 8%), duo_default_offer_id(str 8%), duo_enabled(bool 8%), duo_offer_ids(list 8%), lieu_avant_v615(dict 8%), dates_annulees(list 8%), agenda_abonne(bool 8%), duration_minutes(int 4%), v610_evenement(str 4%), created_at(str 4%), remplace_cours_id(str 4%)

### `creators` (1 docs)

prenom(str), nom(str), telephone(str), reseaux(str), motivation(str), payout_method(str), payout_detail(str), reglement_accepte(bool), id(str), email(str), role_origine(str), status(str), share_token(NoneType), created_at(str), updated_at(str), history(list)

### `deleted_items` (65 docs)

id(str), original_collection(str), original_id(str), coach_id(NoneType/str), deleted_at(str), deleted_by(str), payload(dict), related(dict 55%)

### `discount_codes` (67 docs)

id(str), code(str), type(str), value(float/int), assignedEmail(NoneType/str), courses(list), maxUses(int), used(int), active(bool), coach_id(NoneType/str 84%), expiresAt(NoneType/str 63%), montant_encaisse(float 63%), devise(str 63%), origine_paiement(str 63%), seances_a_l_achat(int 63%), encaissement_saisi_par(str 63%), encaissement_saisi_le(str 63%), source(str 55%), created_at(str 55%), stripe_amount(NoneType/float/int 51%), multi_member(bool 48%), shared_sessions(bool 48%), targetCategories(list 43%), name(str 36%), transaction_id(str 36%), payment_method(str 36%), total_paid(float/int 36%), currency(str 36%), expired_code_migration_at(str 28%), expired_code_migration_reason(str 28%), session_id(str 18%), paid_currency(str 15%), canonical(bool 15%), canonical_decided_at(str 15%), canonical_decided_by(str 15%), canonical_reason(str 15%), emails_envoyes(dict 13%), used_recale_at(str 3%), correction(str 1%), corrige_le(str 1%), updated_at(str 1%)

### `emailjs_config` (1 docs)

serviceId(str), templateId(str), publicKey(str)

### `espace_liens_acces` (6 docs)

code(str), email(str), coach_id(str), slug(str), created_at(str), expires_at(str), ouvertures(int), derniere_ouverture(str 67%)

### `evenement_places` (2 docs)

offer_id(str), source(str), statut(str), created_at(str), reservation_id(str), reserve_le(str)

### `faqs` (4 docs)

id(str), coach_email(str), question(str), answer(str), category(str), order(int), created_at(str), updated_at(str)

### `feature_flags` (2 docs)

AUDIO_SERVICE_ENABLED(bool), VIDEO_SERVICE_ENABLED(bool), STREAMING_SERVICE_ENABLED(bool), updatedAt(NoneType/str), updatedBy(NoneType/str), id(str 50%), SUBSCRIBER_STRICT_ENTRY(bool 50%), REQUIRE_COACH_JWT(bool 50%), PAWAPAY_ENABLED(bool 50%), PUBLICATIONS_NO_EXPIRY(bool 50%), SUPERADMIN_JWT_STRICT(bool 50%), CHAT_READ_STRICT(bool 50%), BOT_MENU_ENABLED(bool 50%), P1_TRIAL_J0_ENABLED(bool 50%), P1_TRIAL_J0_ENVOI_REEL(bool 50%), P1_TRIAL_J3_ENABLED(bool 50%), AUTO_PRESENCE_TRIAL_ENABLED(bool 50%), META_WEBHOOK_SIGNATURE_ENABLED(bool 50%), AUTO_PRESENCE_TRIAL_ECRITURE_REELLE(bool 50%), P3_REPONSE_ACTIF(bool 50%), P3_REPONSE_ENVOI_REEL(bool 50%), SOCIAL_PROFILE_LINKS(bool 50%), REMINDERS_SUBSCRIBERS_DRY_RUN(bool 50%), REMINDERS_SUBSCRIBERS_ENABLED(bool 50%), parrainage_duo_enabled(bool 50%), parrainage_chaine_enabled(bool 50%), invitation_chaine_campagne_enabled(bool 50%), P1E_TEST_CONTROLE(bool 50%), P1E_ESSAI_NON_RESERVE_ENABLED(bool 50%), P1E_ESSAI_NON_RESERVE_ENVOI_REEL(bool 50%), P1D_TEST_CONTROLE(bool 50%), P1_TRIAL_J3_ENVOI_REEL(bool 50%), RATTRAPAGE_HIST_MODE_TEST(bool 50%), RATTRAPAGE_HIST_ENVOI_REEL(bool 50%), UPLOADS_IDENTITE_STRICTE(bool 50%), P3_LAUNCH_ENABLED(bool 50%), P3_LAUNCH_ENVOI_REEL(bool 50%), P3_RELANCE_ENABLED(bool 50%), P3_RELANCE_ENVOI_REEL(bool 50%)

### `free_trial_claims` (61 docs)

created_at(str), actif(bool 90%)

### `google_tokens` (1 docs)

coach_email(str), access_token(str), created_at(str), expires_at(str), refresh_token(str), scope(str), updated_at(str), revoked_at(str)

### `google_users` (2 docs)

user_id(str), email(str), name(str), picture(str), is_coach(bool), created_at(str), last_login(str)

### `invitation_events` (59 docs)

id(str), at(str), evenement(str), source(str), type_invitation(str), campagne_id(NoneType/str), coach_id(str), generation(int), jeton(str), cle(str)

### `invitation_relais` (2 docs)

id(str), jeton(str), campagne_id(str), racine_jeton(str), coach_id(str), type_invitation(str), parent_jeton(str), parent_relais_id(NoneType), generation(int), inviteur_prenom(str), email_empreinte(str), email_canon(str), auto_invitation(bool), preuve_nature(str), preuve_cle(str), created_at(str), attribue_le(str), reservation_id(str)

### `invites_live` (2 docs)

id(str), pseudo(str), photo_url(str), email(str), whatsapp(str), email_verified_at(NoneType), appareils(list), created_at(str), updated_at(str)

### `invoices` (1 docs)

invoice_number(str), date(str), emitter(dict), recipient(dict), items(list), total(float), notes(str), created_at(str)

### `leads` (170 docs)

email(str), whatsapp(str), source(str), id(str 76%), firstName(str 62%), createdAt(str 62%), participant_id(NoneType/str 38%), session_id(NoneType/str 38%), link_token(str 38%), name(str 38%), answers(dict 38%), created_at(str 38%), coach_id(str 38%), submission_id(str 13%), acquisition_only(bool 7%), updatedAt(str 4%)

### `media_links` (2 docs)

slug(str), created_at(str), thumbnail(str), title(str), video_url(str), custom_thumbnail(NoneType 50%), description(str 50%), cta_text(str 50%), cta_link(str 50%)

### `memberships` (6 docs)

id(str), email(str), name(str), coach_id(NoneType), date_debut(str), date_fin(str), source(str), subscription_id(str), created_by(str), created_at(str), updated_at(str), regularisation_historique(bool), regularise_le(str), regularise_par(str), preuve(str), offer_id(str 17%), montant_encaisse(float 17%), devise(str 17%), origine_paiement(str 17%)

### `notification_preferences` (1 docs)

email(str), role(str), preferences(dict), updated_at(str)

### `notifications` (244 docs)

id(str), coach_id(str), created_at(str), message(str), read(bool), title(str), type(str), target(str 80%), reservation_id(str 40%), action_id(str 27%), inbound_id(str 27%), organisation(str 27%), url(str 27%), read_at(str 23%), user_email(str 20%), reservation_code(str 20%), recredited(bool 20%), lead_id(str 13%), link_token(str 13%), course_id(str 4%), occurrence_cle(str 4%), user_name(str 4%), places(int 4%)

### `offers` (17 docs)

id(str), name(str), description(str), price(float), offer_type(str), category(str), isProduct(bool), billing_mode(str), season(str), audience(str), owner_type(str), coach_id(str), visible(bool), stock(int), max_participants(NoneType/int), pack_sessions(NoneType/int), linked_course_ids(list), location(str), duration_minutes(NoneType/int), thumbnail(str), videoUrl(str), images(list), progressive_pricing(bool), price_early_bird(NoneType/float), price_standard(NoneType/float), price_last_minute(NoneType/float), early_bird_days_before(int), standard_hours_before(int), label_early_bird(NoneType/str), label_standard(NoneType/str), label_last_minute(NoneType/str), countdown_enabled(bool), countdown_date(str), countdown_time(str), countdown_text(str), creates_membership(bool), duration_unit(NoneType/str), duration_value(NoneType/int), duree_mois(NoneType/int), expiration_date(NoneType/str), external_link_enabled(bool), external_link_label(NoneType), external_link_url(NoneType), first_purchase_eligible(bool), is_auto_prolong(bool), keywords(str), location_address(str), location_city(str), location_lat(NoneType), location_lng(NoneType), member_discount_pct(float), mobile_money_enabled(bool), owner_id(NoneType), position(NoneType/int), requires_active_membership(bool), shippingCost(float), social_proof_price(NoneType/float), tva(float), variants(NoneType/dict), video_aspect_ratio(str), link_only(bool 88%), created_at(str 88%), full_payment_available(bool 88%), installment_interval_mode(str 88%), installment_interval_months(NoneType/int 88%), video_trim_end(NoneType/float 88%), video_trim_start(NoneType/float 88%), last_reminded_date(NoneType 82%), last_prolonged_date(NoneType/str 82%), active_price(NoneType 71%)

### `page_likes` (3 docs)

coach_email(str), count(int)

### `partner_payment_config` (2 docs)

coach_email(str), cinetpay_api_key(str), cinetpay_secret_key(str), cinetpay_site_id(str), is_configured(bool), mobile_money_enabled(bool), paypal_client_id(str), paypal_client_secret(str), paypal_enabled(bool), paypal_mode(str), stripe_enabled(bool), stripe_publishable_key(str), stripe_secret_key(str), updated_at(str), twint_direct_url(str 50%), pawapay_api_token(str 50%), pawapay_enabled(bool 50%), pawapay_mode(str 50%)

### `partner_prospects` (435 docs)

category(str), priority(str), organisation_name(str), city(str), address(NoneType/str), website(NoneType/str), instagram(NoneType/str), facebook(NoneType/str), linkedin(NoneType/str), tiktok(NoneType/str), public_email(NoneType/str), public_phone(NoneType/str), contact_name(NoneType/str), contact_role(NoneType/str), source_url(NoneType/str), secondary_source_url(NoneType/str), wave(str), preferred_channel(str), approach(NoneType/str), subcategory(NoneType/str), backup_channel(NoneType/str), language(str), j0_fr_translation(NoneType/str), j0_message(str), j3_message(NoneType/str), j7_message(NoneType/str), interested_message(NoneType/str), notes(str), ref(NoneType/str), first_contact_at(NoneType), last_contact_at(NoneType/str), next_followup_at(NoneType), j3_sent_at(NoneType), j7_sent_at(NoneType), replied_at(NoneType/str), interested_at(NoneType), paused_at(NoneType), partner_application_id(NoneType), partner_id(NoneType), status(str), collaboration_type(NoneType/str), score(NoneType/float), niche_id(str), id(str), coach_id(str), created_at(str), updated_at(str), created_by(str), dedupe_key(str), city_key(str), website_domain(str), niche_source(str 88%), first_contact_sent_at(str 68%), audit_contact_12_10(dict 26%), canal_avant_12_10(str 6%), email_ajoute_le(str 6%), email_source_url(str 6%), j0_message_avant_12_10(str 5%), j0_message_origine(str 5%), adresse_a_corriger(bool 3%), adresse_a_corriger_motif(str 3%), relance_bloquee(str 3%), email_trouve_12_10(str 2%), exclusion_email_12_10(str 2%), verified_at(str 2%)

### `partners` (1 docs)

id(str), prospect_id(str), source(str), coach_id(str), partner_slug(str), partner_status(str), name(str), email(str), whatsapp(str), created_at(str), created_by(str)

### `password_resets` (1 docs)

token(str), email(str), user_id(str), expires_at(str), created_at(str), used(bool), used_at(str)

### `pawapay_transactions` (0 docs)

_(vide)_

### `payment_links` (15 docs)

id(str), stripe(str), paypal(str), twint(str), coachWhatsapp(str), coachNotificationEmail(str), coachNotificationPhone(str), coach_id(NoneType/str)

### `payment_transactions` (293 docs)

id(str), session_id(str), amount(float/int), currency(str), product_name(str), customer_email(NoneType/str), metadata(dict), payment_status(str), created_at(str), coach_id(str 87%), payment_methods(list 86%), quantity(int 69%), server_unit_price(float 36%), pricing_tier(str 36%), expected_amount(float 36%), amount_source(str 36%), price_source(str 36%), promo_code(NoneType 36%), promo_source(NoneType 36%), promo_canonical_id(NoneType 36%), quota_guard_result(NoneType 36%), warning(str 30%), tarif_applique(float 26%), tarif_raison(str 26%), tarif_devise(str 26%), tarif_fige_le(str 26%), tarif_public(float 26%), tarif_palier(str 26%), tarif_offre_id(str 26%), member_dates_proven(int 26%), member_dates_covered(int 26%), status(str 18%), webhook_received_at(str 18%), payment_method(str 13%), amount_total(int 5%), reconciled_manually(str 0%)

### `payout_requests` (0 docs)

_(vide)_

### `platform_settings` (3 docs)

updated_at(str), updated_by(str), partner_access_enabled(bool 67%), maintenance_mode(bool 67%), service_prices(dict 67%), id(str 33%), boost_price_chf(int 33%), is_super_admin(str 33%), staff_access_code(str 33%), saison_active(str 33%)

### `private_conversations` (12 docs)

id(str), participant_1_id(str), participant_1_name(str), participant_2_id(str), participant_2_name(str), last_message(str), last_message_at(str), created_at(str), channel(str), phone(str)

### `private_messages` (148 docs)

id(str), conversation_id(str), sender_id(str), sender_name(str), recipient_id(str), recipient_name(str), content(str), created_at(str), is_deleted(bool), channel(str), manuel(bool 3%), envoye_par(str 3%)

### `progress_entries` (0 docs)

_(vide)_

### `prospect_campaign_actions` (844 docs)

id(str), campaign_id(str), coach_id(str), recipient_key(str), prospect_ids(list), prospect_uuids(list), organisations(list), cities(list), category(str), priority(str), score(NoneType/float), wave(NoneType/str), language(str), channel(str), backup_channel(NoneType/str), target(str), execution_type(str), execution_reason(str), message_j0(str), message_j0_origine(str), j0_fr_translation(str), statut(str), created_at(str), updated_at(str), reply_token(str 50%), attempt_count(int 50%), claimed_at(str 50%), verrou_actif(bool 50%), attempted_at(str 50%), idempotency_key(str 50%), provider(str 50%), j14_due_at(str 50%), j3_due_at(str 50%), j7_due_at(str 50%), provider_message_id(str 50%), provider_status(str 50%), sent_at(str 50%), rfc_message_id(str 50%), message_j14(str 50%), message_j3(str 50%), message_j7(str 50%), relances_textes_version(str 50%), j3_attempts(int 45%), j3_claimed_at(str 45%), j3_verrou(bool 45%), j3_attempted_at(str 45%), j3_idempotency_key(str 45%), j3_provider(str 45%), j3_provider_message_id(str 45%), j3_provider_status(str 45%), j3_sent_at(str 45%), j3_delivered_at(str 45%), suivi_livraison(bool 26%), provider_sent_at(str 26%), relances_modele(str 26%), provider_delivered_at(str 25%), j3_sent_subject(str 23%), j3_sent_text(str 23%), j14_annule_le(str 9%), j14_annule_motif(str 9%), j3_annule_le(str 9%), j3_annule_motif(str 9%), j7_annule_le(str 9%), j7_annule_motif(str 9%), replied_at(str 9%), bounce_message(str 2%), bounce_subtype(str 2%), bounce_type(str 2%), bounced_at(str 2%), suivi_humain(bool 1%)

### `prospect_campaigns` (10 docs)

id(str), coach_id(str), nom(str), etat(str), idempotency_key(str), nb_fiches(int), nb_destinataires(int), summary(dict), created_at(str), updated_at(str), created_by(str), approved_at(str), approved_by(str), started_at(NoneType), finished_at(NoneType/str), snapshot_hash(str), subject_j0(str 90%), subject_j3(str 70%), subject_j7(str 70%), approbations(list 70%), subject_j14(str 60%), relances_approuvees_le(str 60%), relances_approuvees_par(str 60%), relances_validees(bool 60%), relances_preparees_le(str 40%), cloture_motif(str 20%), annulee_le(str 10%), motif_annulation(str 10%)

### `prospect_inbound_messages` (69 docs)

id(str), coach_id(str), campaign_id(str), action_id(str), recipient_key(str), from_email(str), to_email(str), subject(str), body_text(str), received_at(str), message_id(str), in_reply_to(list), references(list), provider(str), provider_event_id(str), dedupe_key(str), matching_method(str), matching_confidence(int), statut(str), motif(str), processed_at(str), created_at(str), provider_email_id(str), body_html(str), body_quoted(str), contenu_recupere(bool), contenu_source(str), contenu_erreur(str), read_at(str), read_by(str), demande_video(bool 84%), nature_reponse(str 84%), suivi_demande_le(NoneType 84%), suivi_demande_texte(NoneType 84%), traite_at(NoneType/str 10%), traite_par(str 6%), langue_detectee(str 4%), traduction_fr(str 4%), traduction_fr_le(str 4%), contenu_complete_le(str 3%)

### `prospect_notes` (104 docs)

id(str), coach_id(str), inbound_id(str), action_id(str), prospect_uuids(list), prospect_uuid(str), recipient_key(str), type(str), texte(str), status_after(NoneType/str), occurred_at(str), created_at(str), created_by(str), corrige_note_id(NoneType/str), origine(str 93%)

### `prospect_reply_drafts` (53 docs)

inbound_id(str), reponse_proposee(str), validation_requise(bool), motifs_validation(list), created_at(str), updated_at(str), id(str 68%), action_id(str 68%), coach_id(str 68%), recipient_key(str 68%), organisation(str 68%), to_email(str 68%), subject(str 68%), intention(str 68%), intention_modele(str 68%), langue(str 68%), resume(str 68%), demande(str 68%), prochaine_action(str 68%), ton(str 68%), modele(str 68%), version(int 68%), genere_le(str 68%), genere_par(str 68%), edite_le(str 64%), edite_par(str 64%), texte_modele(str 62%), contexte_commercial(dict 45%), origine(str 32%), analyse(dict 8%), questions_explicites(list 8%), controle_ia(dict 8%)

### `prospect_reply_sends` (52 docs)

id(str), inbound_id(str), action_id(str), coach_id(str), prospect_uuid(str), recipient_key(str), organisation(str), to_email(str), subject(str), draft_id(NoneType/str), draft_version(NoneType/int), draft_hash(str), language(NoneType/str), intention(NoneType/str), validation_requise(bool), generated_text(str), edited_text(NoneType/str), approved_text(str), approved_at(str), approved_by(str), send_status(str), provider(str), provider_message_id(NoneType/str), sent_at(NoneType/str), error_code(NoneType/str), created_at(str), updated_at(str), provider_status(str 85%), suivi_livraison(bool 85%), delivered_at(str 85%), media(NoneType 10%), correction(str 2%), provider_failed_constate_le(str 2%), tentative(int 2%), tentatives_precedentes(list 2%), reparation_v608d(str 2%)

### `prospection_medias` (28 docs)

id(str), coach_id(str), niche(str), format(str), url(str), statut(str), version(str), notes(NoneType), created_at(str), updated_at(str), archived_at(NoneType/str), remplace_par(NoneType/str), remplace(NoneType/list), origine(str), source_id(NoneType/str), fichier(dict), edition(NoneType/dict), cible(NoneType/dict 61%), cible_id(NoneType/str 61%)

### `prospection_niches` (8 docs)

id(str), coach_id(str), cle(str), slug(str), nom(str), ordre(int), active(bool), origine(bool), created_at(str), updated_at(str), archived_at(NoneType)

### `publications` (4 docs)

id(str), subscriber_code(str), subscriber_name(str), display_name(str), coach_id(str), author_id(str), author_photo(str), author_name(str), media_url(str), media_type(str), cloudinary_public_id(str), caption(str), thumbnail_url(str), thumbnail_public_id(str), created_at(str), expires_at(str), no_expiry(bool), trim_start(float 50%), trim_end(float 50%)

### `push_subscriptions` (346 docs)

subscription(dict), active(bool), participant_id(str), updated_at(str), email(str 17%), role(str 17%), last_push_at(str 16%), last_push_rank(int 16%), last_push_status(str 16%), device_hint(str 8%), superseded_at(str 3%), superseded_by(str 3%)

### `qr_validations` (3 docs)

id(str), code(str), type(str), validated_at(str), sessions_remaining(int), sessions_total(int)

### `rattrapage_essai_historique` (8 docs)

mode(str), code(str), statut(str), at(str), fin_at(str)

### `rattrapage_essai_historique_liste` (7 docs)

email(str), prenom(str), presence_at(str), fige_at(str)

### `recovery_attempts` (21 docs)

key(str), email(str), whatsapp(str), created_at(str)

### `referral_campaigns` (12 docs)

id(str), coach_id(str), type(str), status(str), share_token(str), version(int), title(str), subtitle(NoneType/str), message(NoneType/str), cta_label(NoneType/str), image_url(NoneType/str), image_source(str), course_id(NoneType/str), occurrence(NoneType/str), offer_id(str), inviter_display(dict), created_at(str), updated_at(str), lieu(NoneType 33%), video_url(NoneType/str 33%), audio_url(NoneType/str 33%), audio_partage_url(NoneType/str 25%), description(NoneType/str 25%), corbeille(dict 17%), copie_de(str 8%), archivee_le(str 8%), supprimee_le(str 8%)

### `referral_commissions` (0 docs)

_(vide)_

### `referral_invitations` (30 docs)

id(str), pass_id(str), sponsor_email_norm(str), channel(str), created_at(str), chain_parent_pass_id(str 40%)

### `referral_passes` (30 docs)

id(str), coach_id(str), course_id(str), occurrence(str), course_snapshot(dict), sponsor(dict), invitee(NoneType/dict), status(str), share_token(str), opened_at(NoneType/str), reservations(dict), invitee_access_code(NoneType/str), blocked_reason(NoneType), attribution(NoneType/dict), spordate_reward(dict), offer_id(str), offer_snapshot(dict), offer_history(list), version(int), created_at(str), updated_at(str), unlocked_at(NoneType/str), expires_at(str), events(list), invitation(dict 93%), invitation_version(int 93%), chain(dict 87%), inviter_display(dict 73%), preview_version(int 63%), origin(dict 60%), corbeille(dict 13%), contact_invitant(dict 7%)

### `referral_share_settings` (1 docs)

share_image_url(NoneType), updated_at(str), updated_by(str)

### `reminder_sends` (498 docs)

envoye_le(str)

### `resend_envois` (490 docs)

id(str), resend_id(str), source(str), type_email(str), critique(bool), destinataire(str), reference(NoneType), prepare_at(str), soumis_at(str), provider_status(str), raison(NoneType/str), evenements(list), delivered_at(str 99%), sent_at(str 96%), bounced_at(str 1%)

### `resend_evenements` (1023 docs)

type(str), resend_id(str), recu_at(str)

### `resend_quota` (2 docs)

actif(bool 50%), limite(int 50%), modifie_le(str 50%), modifie_par(str 50%), seuil(int 50%), plancher(int 50%), plancher_expire_at(str 50%), plancher_lu_at(str 50%), tentatives(list 50%)

### `reservation_cancellations` (5 docs)

id(str), reservation_id(str), reservationCode(str), userEmail(str), courseId(str), courseName(str), occurrence(str), code(str), est_essai(bool), quantity(int), coach_id(str), cancelled_at(str), cancelled_by(str)

### `reservations` (191 docs)

coach_id(str), id(str 99%), reservationCode(str 99%), userName(str 99%), userEmail(str 99%), userWhatsapp(str 99%), courseName(str 99%), courseTime(str 99%), datetime(str 99%), offerName(str 99%), quantity(int 99%), totalPrice(float/int 99%), promoCode(NoneType/str 99%), source(str 99%), type(str 99%), validated(bool 99%), validatedAt(NoneType/str 99%), createdAt(str 99%), discountCode(NoneType/str 98%), courseId(str 70%), offerId(str 70%), price(float/int 70%), guests(list 68%), guest_headphones(list 68%), member_slug(NoneType/str 66%), subscriptionId(NoneType/str 58%), confirmation(dict 32%), selectedDates(list 30%), selectedDatesText(NoneType/str 30%), selectedVariants(NoneType/list 30%), variantsText(NoneType 30%), isProduct(bool 30%), shippingStatus(str 30%), trackingNumber(NoneType 30%), terms_accepted(bool 29%), terms_version(str 29%), terms_accepted_at(str 29%), filmed_at_booking(bool 29%), tarif_applique(float 28%), tarif_raison(str 28%), tarif_devise(str 28%), tarif_fige_le(str 28%), userLanguage(NoneType 21%), reminders_sent(dict 9%), validation_source(str 5%), attribution(dict 4%), auto_presence_at(str 4%), headphone_status(NoneType/str 3%), headphone_updated_at(str 3%), userId(str 2%), reminder_sent(bool 1%), reminder_sent_at(str 1%), evenement_place_cle(str 1%), paiement(str 1%), droit_subscription_id(str 1%), droit_offer_id(str 1%), droit_code(str 1%), userBirthday(NoneType 1%), data(list 1%), pagination(dict 1%)

### `seance_mouvements` (57 docs)

type(str), reservation_id(str), code(str), fiche_id(str), quantite(int), source(str), statut(str), at(str), used_apres(int)

### `session_adjustments` (7 docs)

id(str), subscription_id(str), coach_email(str), action(str), amount(int), remaining_before(int), remaining_after(int), timestamp(str)

### `smart_entry_attempts` (1720 docs)

ip(str), at(str)

### `social_proofs` (3 docs)

id(str), offer_id(str), offer_name(str), client_name(str), client_email(str), client_phone(str), video_link(str), instagram_username(str), motivation(str), status(str), coach_id(str), created_at(str), reviewed_at(str), reviewed_by(str), terms_accepted(bool 67%), terms_version(str 67%), terms_accepted_at(str 67%), filmed_at_booking(bool 67%)

### `spordate_bridge_usage` (1122 docs)

email(str), origine(str), created_at(str), created_dt(datetime)

### `subscriber_infos` (9 docs)

code(str), coach_id(str), email(str), name(str), updated_at(str), whatsapp(str 78%), birthday(str 33%)

### `subscriber_otp` (83 docs)

id(str), code(str), slug(str), created_at(str), expires_at(str), essais(int), used(bool), envoye(bool), coach_id(NoneType/str), otp_empreinte(str 76%), email(str 76%), used_at(str 70%), membre_slug(str 49%)

### `subscriber_sessions` (64 docs)

jti(str), code(str), email(str), coach_id(str), slug(str), created_at(str), expires_at(str), revoked(bool), revoked_at(str 11%), origine(str 9%), revoked_reason(str 5%), renewed_at(str 5%)

### `subscribers` (43 docs)

channel(str), value(str), created_at(str), source(str), status(str), updated_at(str), id(str 91%), name(str 91%), unsubscribe_token(str 33%), consent_at(str 19%), consent_text(str 19%), opted_out_at(str 14%), opted_out_source(str 5%), status_before_opt_out(str 5%)

### `subscriptions` (100 docs)

id(str), email(str), name(str), code(str), offer_name(str), total_sessions(int), used_sessions(int), remaining_sessions(int), expires_at(NoneType/str), status(str), created_at(str), updated_at(str), coach_id(str 96%), source(str 87%), whatsapp(str 63%), auto_renew(bool 56%), renewal_price(float/int 56%), renewal_sessions(int 56%), renewal_warnings_sent(list 56%), montant_encaisse(float 53%), devise(str 53%), origine_paiement(str 53%), encaissement_saisi_par(str 53%), encaissement_saisi_le(str 53%), seances_a_l_achat(int 53%), offer_id(str 43%), offer_price(NoneType/float 36%), expired_migration_at(str 25%), expired_migration_reason(str 25%), objectifs(str 17%), stripe_customer_id(NoneType/str 15%), stripe_payment_method(NoneType/str 15%), last_renewal_date(NoneType 15%), deleted_at(str 11%), deleted_by(str 11%), deleted_reason(str 11%), statut_avant_suppression(str 11%), conversion_eligible_at(str 10%), conversion_first_viewed_at(str 10%), attribution(dict 8%), suivi_paiement(dict 6%), date_debut(str 2%), converted_at(str 2%), converted_by_subscription_id(str 2%), converted_event_sent(bool 2%), converted_props(dict 2%), relances_essai(dict 2%), superseded_at(str 2%), superseded_by(str 2%), billing_mode(str 1%), duree_mois(int 1%), stripe_subscription_id(str 1%), stripe_invoices(list 1%), payment_mode(str 1%), installment_interval_months(int 1%), saison_debut(str 1%), reference_paiement(str 1%), acquisition_source(str 1%), pass_duo_id(str 1%), pass_duo_offer_id(str 1%), pass_duo_role(str 1%), offer_rattachee_le(str 1%), offer_rattachee_par(str 1%)

### `terms_versions` (1 docs)

version(str), coach_id(str), created_at(str), text(str), text_recording(str)

### `trajets_cache` (5 docs)

calcule_le(str), expire_le(str), incertain(bool), km(int), lat(float), lieu(str), lon(float), minutes(int), source(str), statut(str), ville(str)

### `upload_chunks` (0 docs)

_(vide)_

### `uploaded_files` (113 docs)

file_id(str), filename(str), original_name(str), content_type(str), asset_type(str), size(int), created_at(datetime), coach_email(str 89%), storage(str 59%), data(bytes 41%), participant_id(str 9%), sha256(str 2%)

### `users` (140 docs)

name(str), email(str 99%), createdAt(str 99%), id(str 99%), whatsapp(str 95%), photoUrl(str 78%), photo_url(str 78%), language(str 36%), updatedAt(str 36%), accessCode(str 21%), role(str 21%), phone(str 6%), source(str 6%), group_code(str 6%), coach_id(str 6%), age(int 2%), bio(str 2%), passions(str 2%), participant_id(str 1%), birthday(str 1%), birthday_updated_at(str 1%), show_age_public(bool 1%)

### `users_auth` (11 docs)

user_id(str), email(str), name(str), password_hash(str), auth_method(str), is_coach(bool), picture(str), created_at(str), updated_at(str), pending_validation(bool 9%)

### `whatsapp_config` (1 docs)

accountSid(str), authToken(str), fromNumber(str), apiMode(str)

### `whatsapp_statuts` (1322 docs)

wamid(str), statut(str), destinataire(str), horodatage_meta(str), conversation(NoneType), tarification(NoneType/dict), erreurs(list), recu_le(str)

