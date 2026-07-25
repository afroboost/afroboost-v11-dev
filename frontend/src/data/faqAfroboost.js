// V274: FAQ Afroboost — 20 questions-réponses prédéfinies affichées dans le chat
// quand le coach active le mode IA. Contenu UNIVERSEL (identique pour tous les
// coaches) ; seule la couleur d'accent s'adapte au coach (var --primary-color).
// Réponses instantanées, sans appel API.

const faqAfroboost = [
  // === CONCEPT AFROBOOST ===
  {
    id: 1,
    category: "concept",
    question: "C'est quoi Afroboost ?",
    answer: "Afroboost est un concept de fitness immersif qui combine la danse afrobeat, le cardio intensif et l'énergie collective. Chaque session est une expérience complète : vous transpirez, vous dansez et vous vous amusez en même temps. Pas besoin d'être danseur, juste d'avoir envie de bouger !"
  },
  {
    id: 2,
    category: "concept",
    question: "Est-ce que je dois savoir danser ?",
    answer: "Pas du tout ! Afroboost est accessible à tous les niveaux. Les mouvements sont simples et répétitifs, l'objectif est de bouger et transpirer, pas de performer. Votre coach vous guide pas à pas."
  },
  {
    id: 3,
    category: "concept",
    question: "Quels sont les bienfaits d'une session Afroboost ?",
    answer: "Une session Afroboost permet de brûler entre 400 et 800 calories, améliorer votre cardio, renforcer vos muscles, réduire le stress et booster votre confiance. Le tout dans une ambiance festive et motivante !"
  },
  {
    id: 4,
    category: "concept",
    question: "Combien de temps dure une session ?",
    answer: "Une session dure généralement entre 45 minutes et 1 heure, échauffement et retour au calme inclus. C'est intense mais le temps passe vite grâce à la musique et l'énergie du groupe !"
  },

  // === INSCRIPTION ET OFFRES ===
  {
    id: 5,
    category: "inscription",
    question: "Comment je m'inscris ?",
    answer: "C'est simple : choisissez une offre sur la vitrine de votre coach, cliquez sur 'Réserver', renseignez vos informations et confirmez. Vous recevrez un code AFR- qui vous donne accès à toutes les fonctionnalités."
  },
  {
    id: 6,
    category: "inscription",
    question: "C'est quoi le code AFR- ?",
    answer: "Le code AFR- est votre identifiant unique d'abonné Afroboost. Il est généré automatiquement lors de votre inscription. Gardez-le précieusement : il vous permet d'accéder à vos sessions, publier du contenu et profiter de toutes les fonctionnalités de la plateforme."
  },
  {
    id: 7,
    category: "inscription",
    question: "Quelles sont les offres disponibles ?",
    answer: "Les offres varient selon votre coach. Vous pouvez trouver des sessions à l'unité, des packs de sessions, des abonnements mensuels et des cours d'essai gratuits. Consultez la vitrine de votre coach pour voir les tarifs et les détails."
  },
  {
    id: 8,
    category: "inscription",
    question: "Est-ce qu'il y a un essai gratuit ?",
    answer: "Oui ! Certains coaches proposent des cours d'essai gratuits. Consultez les offres sur la vitrine pour voir si un essai est disponible. C'est le meilleur moyen de découvrir Afroboost sans engagement."
  },

  // === PAIEMENT ===
  {
    id: 9,
    category: "paiement",
    question: "Quels moyens de paiement sont acceptés ?",
    answer: "Afroboost accepte les paiements par carte bancaire (Visa, Mastercard) via Stripe, et le mobile money pour certaines régions. Le paiement est sécurisé et vous recevez une confirmation par email."
  },
  {
    id: 10,
    category: "paiement",
    question: "Est-ce que je peux annuler ma réservation ?",
    answer: "Les conditions d'annulation dépendent de chaque coach et de chaque offre. Contactez directement votre coach via le chat pour connaître sa politique d'annulation."
  },

  // === SESSIONS ET COURS ===
  {
    id: 11,
    category: "sessions",
    question: "Où se déroulent les sessions ?",
    answer: "Les lieux varient selon votre coach. Consultez les détails de chaque offre pour connaître l'adresse exacte. Les sessions peuvent se dérouler en salle, en plein air ou même en ligne."
  },
  {
    id: 12,
    category: "sessions",
    question: "Que dois-je apporter à une session ?",
    answer: "Prévoyez une tenue de sport confortable, des baskets, une serviette et une bouteille d'eau. Vous allez transpirer, alors hydratez-vous bien avant, pendant et après la session !"
  },
  {
    id: 13,
    category: "sessions",
    question: "Est-ce que les sessions sont en groupe ou individuelles ?",
    answer: "Les sessions Afroboost sont principalement en groupe — c'est l'énergie collective qui fait la magie ! Mais certains coaches proposent aussi des sessions privées. Consultez les offres pour plus de détails."
  },

  // === PUBLICATIONS ET COMMUNAUTÉ ===
  {
    id: 14,
    category: "communaute",
    question: "Comment je publie du contenu ?",
    answer: "Cliquez sur le bouton 'Publier +' dans le chat. Vous pouvez partager des photos et des vidéos (max 1 minute). Recadrez votre image, choisissez votre miniature vidéo et ajoutez une légende. Votre publication sera visible pendant 48 heures."
  },
  {
    id: 15,
    category: "communaute",
    question: "Pourquoi mes publications disparaissent après 48h ?",
    answer: "Les publications ont une durée de vie de 48 heures pour garder le contenu frais et dynamique, un peu comme les stories Instagram. Cela encourage tout le monde à partager régulièrement et maintient l'énergie de la communauté !"
  },
  {
    id: 16,
    category: "communaute",
    question: "Est-ce que je peux modifier ou supprimer ma publication ?",
    answer: "Oui ! Allez dans 'Mes publications' depuis le chat, vous y trouverez toutes vos publications avec les options modifier et supprimer."
  },

  // === COACH ET PLATEFORME ===
  {
    id: 17,
    category: "plateforme",
    question: "Comment je contacte mon coach ?",
    answer: "Utilisez le chat intégré sur le site de votre coach. Vous pouvez lui envoyer un message directement. Si le mode IA est activé, vous pouvez aussi poser vos questions ici et obtenir des réponses instantanées."
  },
  {
    id: 18,
    category: "plateforme",
    question: "Est-ce que je peux installer l'application sur mon téléphone ?",
    answer: "Oui ! Afroboost est une application web progressive (PWA). Sur votre téléphone, ouvrez le site dans Chrome ou Safari, puis cliquez sur 'Ajouter à l'écran d'accueil'. Vous recevrez des notifications comme une vraie application !"
  },
  {
    id: 19,
    category: "plateforme",
    question: "Comment devenir coach partenaire Afroboost ?",
    answer: "Si vous êtes coach fitness ou danse et que vous souhaitez rejoindre la plateforme Afroboost, contactez-nous via le chat ou par email. Vous aurez votre propre vitrine personnalisée, vos outils de gestion et votre communauté."
  },
  {
    id: 20,
    category: "plateforme",
    question: "Est-ce que mes données sont sécurisées ?",
    answer: "Oui, vos données sont protégées. Les paiements passent par Stripe (certifié PCI DSS), vos informations personnelles ne sont jamais partagées avec des tiers, et chaque coach a un espace isolé."
  }
];

// Catégories pour le filtre (id null = tout afficher)
export const faqCategories = [
  { id: null, label: 'Tout' },
  { id: 'concept', label: 'Concept' },
  { id: 'inscription', label: 'Inscription' },
  { id: 'paiement', label: 'Paiement' },
  { id: 'sessions', label: 'Sessions' },
  { id: 'communaute', label: 'Communauté' },
  { id: 'plateforme', label: 'Plateforme' }
];

export default faqAfroboost;
