// V274/V275: FAQ Afroboost — 20 questions-réponses affichées dans le chat quand
// le coach active le mode IA. Réponses instantanées (aucun appel API).
//
// V275 : question/answer sont désormais MULTILINGUES (objets par langue). Langues
// couvertes : fr (source) + ln (Lingala), wo (Wolof), sw (Swahili), bm (Bambara),
// bas (Bassa). Toute langue absente (en, de...) retombe sur le français via
// faqText(). ⚠️ Les traductions africaines sont au mieux — à faire relire par des
// locuteurs natifs avant diffusion large.

// Repli : renvoie la valeur dans la langue demandée, sinon le français.
export const faqText = (value, lang) => {
  if (value == null) return '';
  if (typeof value === 'string') return value;
  return value[lang] || value.fr || '';
};

const faqAfroboost = [
  // === CONCEPT AFROBOOST ===
  {
    id: 1,
    category: "concept",
    question: {
      fr: "C'est quoi Afroboost ?",
      ln: "Afroboost ezali nini?",
      wo: "Lan la Afroboost?",
      sw: "Afroboost ni nini?",
      bm: "Afroboost ye mun ye?",
      bas: "Afroboost i yé jam yak?"
    },
    answer: {
      fr: "Afroboost est un concept de fitness immersif qui combine la danse afrobeat, le cardio intensif et l'énergie collective. Chaque session est une expérience complète : vous transpirez, vous dansez et vous vous amusez en même temps. Pas besoin d'être danseur, juste d'avoir envie de bouger !",
      ln: "Afroboost ezali likanisi ya fitness oyo esangisi bobini ya afrobeat, cardio makasi mpe nguya ya bato nyonso. Session moko na moko ezali experience mobimba : otoki motoki, obini mpe osepeli na mbala moko. Esengeli te ozala mobini, kaka ozala na mposa ya koningana!",
      wo: "Afroboost mooy ab xam-xam bu am doole ci fitness bi di boole fecc afrobeat, cardio bu metti ak doole gu mbool. Ndajé bu nekk ab jéema bu mat : dinga ñax, dinga fecc te dinga bég ci benn waxtu. Warul nga mëna fecc, kay bëgg rekk a jaay yaram!",
      sw: "Afroboost ni dhana ya mazoezi ya kupendeza inayochanganya dansi ya afrobeat, cardio kali na nguvu ya pamoja. Kila kipindi ni tukio kamili: unatoka jasho, unacheza na unafurahia kwa wakati mmoja. Huhitaji kuwa mchezaji, unahitaji tu hamu ya kucheza!",
      bm: "Afroboost ye fitness hakili ye min bɛ afrobeat dɔnkili, cardio gɛlɛn ani jɛkulu fanga fara ɲɔgɔn kan. Waati o waati ye kokɛ dafalen ye : i bɛ wusu bɔ, i bɛ dɔn kɛ ani i bɛ nisɔndiya waati kelen na. I man kan ka kɛ dɔnkɛla ye, i mago bɛ ka lamaga dɔrɔn!",
      bas: "Afroboost i yé jam i nyena i bi ɓôdôl fitness ni danse afrobeat, cardio ni ngui i likɔŋ. Hihéga hiki i yé jéema i mal : u ñ ol matén, u nôgôl danse ni u sɔŋ i ngéda yada. U ta bé danser, kaŋ u gwés i lɔŋ!"
    }
  },
  {
    id: 2,
    category: "concept",
    question: {
      fr: "Est-ce que je dois savoir danser ?",
      ln: "Nasengeli koyeba kobina?",
      wo: "Xam naa fecc?",
      sw: "Je, ninahitaji kujua kucheza?",
      bm: "N ka kan ka dɔn dɔn wa?",
      bas: "Me nlама bé nôgôl danse?"
    },
    answer: {
      fr: "Pas du tout ! Afroboost est accessible à tous les niveaux. Les mouvements sont simples et répétitifs, l'objectif est de bouger et transpirer, pas de performer. Votre coach vous guide pas à pas.",
      ln: "Te soki moke te! Afroboost ezali mpo na bato nyonso. Baningano ezali pete mpe ezongelaka, mokano ezali koningana mpe kobimisa motoki, kasi te kosala esengo. Coach na yo akolakisa yo malembe malembe.",
      wo: "Mukk! Afroboost ñépp ñoo ko mëna def. Yëngu yi yombul te ñu koy delloowaat, jubluwaay bi mooy jóg te ñax, du wone. Sa coach dina la jàppale ndànk-ndànk.",
      sw: "Hapana kabisa! Afroboost inapatikana kwa viwango vyote. Miondoko ni rahisi na inayorudiwa, lengo ni kusonga na kutoka jasho, si kuonyesha ustadi. Kocha wako atakuongoza hatua kwa hatua.",
      bm: "Ayi fewu! Afroboost bɛ se bɛɛ ma. Lamagali ka nɔgɔn ani u bɛ segin, kuntilenna ye ka lamaga ani ka wusu bɔ, a tɛ ka ɲɛnajɛ. I ka coach bɛna i ɲɛminɛ sen fila sen fila.",
      bas: "Té to! Afroboost i yé i bôt biki. Malamga ma yé pubi ni ma nti timbil, jɔ i yé i lɔŋ ni i ol matén, ta i lémél. Coach woŋ a nti sôŋ we lôŋ ni lôŋ."
    }
  },
  {
    id: 3,
    category: "concept",
    question: {
      fr: "Quels sont les bienfaits d'une session Afroboost ?",
      ln: "Matomba ya session Afroboost ezali nini?",
      wo: "Njariñ yu ndajé Afroboost lan la?",
      sw: "Faida za kipindi cha Afroboost ni zipi?",
      bm: "Afroboost waati nafa ye mun ye?",
      bas: "Mahol ma hihéga Afroboost ma yé jam?"
    },
    answer: {
      fr: "Une session Afroboost permet de brûler entre 400 et 800 calories, améliorer votre cardio, renforcer vos muscles, réduire le stress et booster votre confiance. Le tout dans une ambiance festive et motivante !",
      ln: "Session Afroboost ezali kozikisa kati na 400 mpe 800 calories, kobongisa cardio na yo, kolendisa misuni na yo, kokitisa stress mpe kobakisa elikya na yo. Nyonso na esengo mpe na makasi!",
      wo: "Benn ndajé Afroboost dafay lakk 400 ba 800 calories, yokk sa cardio, dooleel say muscle, wàññi stress ak yokk sa kóolute. Lépp ci ab ambiance bu bég te di jóg!",
      sw: "Kipindi cha Afroboost husaidia kuchoma kati ya calori 400 na 800, kuboresha cardio yako, kuimarisha misuli, kupunguza msongo na kuongeza kujiamini. Yote katika mazingira ya furaha na yenye kutia moyo!",
      bm: "Afroboost waati kelen bɛ se ka calori 400 fo 800 jeni, ka i ka cardio ɲɛ, ka i ka fasaw barika, ka hami dɔgɔya ani ka i ka dannaya bonya. O bɛɛ ye nisɔndiya ni fanga cogo la!",
      bas: "Hihéga Afroboost i nti sôŋ i jeni calori 400 ni 800, i ɓôdôl cardio woŋ, i ngui minsôn, i kôdôl stress ni i ɓat dannga woŋ. Mam mɔ i sôŋ i ngéda i lémél!"
    }
  },
  {
    id: 4,
    category: "concept",
    question: {
      fr: "Combien de temps dure une session ?",
      ln: "Session ezalaka ngonga boni?",
      wo: "Ñaata waxtu la benn ndajé di def?",
      sw: "Kipindi kimoja huchukua muda gani?",
      bm: "Waati kelen bɛ mɛn cogo di?",
      bas: "Hihéga hi nti tabé ngéda yaŋ?"
    },
    answer: {
      fr: "Une session dure généralement entre 45 minutes et 1 heure, échauffement et retour au calme inclus. C'est intense mais le temps passe vite grâce à la musique et l'énergie du groupe !",
      ln: "Session ezalaka mingi na kati ya miniti 45 mpe ngonga 1, elongo na kobongisa nzoto mpe kopema. Ezali makasi kasi ntango elekaka mbangu na miziki mpe nguya ya lisangá!",
      wo: "Benn ndajé dafay def li ci diggante 45 simili ak 1 waxtu, ak échauffement ak noppalu. Dafa metti waaye waxtu bi dafay gaaw ndax music bi ak doole gu group bi!",
      sw: "Kipindi kwa kawaida huchukua kati ya dakika 45 na saa 1, pamoja na kupasha joto mwili na kupumzika. Ni kali lakini muda hupita haraka kwa sababu ya muziki na nguvu ya kikundi!",
      bm: "Waati kelen bɛ mɛn tuma caman miniti 45 ni lɛrɛ 1 cɛ, farikolo suma ani lafiya fara a kan. A ka gɛlɛn nka waati bɛ tɛmɛ teliya la fɔlifɛn ni jɛkulu fanga barika la!",
      bas: "Hihéga hi nti tabé i jɔ 45 minit ni 1 ngéda, ni échauffement ni lafiya. I yé ngui ndi ngéda i nti kɛ nlô i nyuu miziki ni ngui likɔŋ!"
    }
  },

  // === INSCRIPTION ET OFFRES ===
  {
    id: 5,
    category: "inscription",
    question: {
      fr: "Comment je m'inscris ?",
      ln: "Nakoki komikoma ndenge nini?",
      wo: "Naka laa man a bindu?",
      sw: "Je, najisajilije?",
      bm: "N bɛ n tɔgɔ sɛbɛn cogo di?",
      bas: "Me nti tila tôi lɛ?"
    },
    answer: {
      fr: "C'est simple : choisissez une offre sur la vitrine de votre coach, cliquez sur 'Réserver', renseignez vos informations et confirmez. Vous recevrez un code AFR- qui vous donne accès à toutes les fonctionnalités.",
      ln: "Ezali pete : poná libonza na etalasi ya coach na yo, finá 'Komisa', komá makambo na yo mpe ndima. Okozwa code AFR- oyo epesi yo nzela na makambo nyonso.",
      wo: "Yombul: tànnal benn offre ci vitrine bu sa coach, bësal ci 'Réservé', duggal say xibaar te nangul. Dinga jot benn code AFR- bu lay may accès ci lépp.",
      sw: "Ni rahisi: chagua ofa kwenye ukurasa wa kocha wako, bofya 'Weka nafasi', jaza taarifa zako na uthibitishe. Utapokea msimbo wa AFR- unaokupa ufikiaji wa vipengele vyote.",
      bm: "A ka nɔgɔn : sɔrɔyɔrɔ dɔ sugandi i ka coach ka jɛnkulu kan, digi 'A mara' kan, i ka kunnafoni sɛbɛn ani a dafa. I bɛna AFR- code sɔrɔ min bɛ sira di i ma fɛn bɛɛ ma.",
      bas: "I yé pubi : sɔ mahɔl i vitrine coach woŋ, tôp 'Tila', tila bitɔ biŋ ni kônda. U nti kôs code AFR- i nti ti we sira i mam mɔ."
    }
  },
  {
    id: 6,
    category: "inscription",
    question: {
      fr: "C'est quoi le code AFR- ?",
      ln: "Code AFR- ezali nini?",
      wo: "Lan la code AFR- bi?",
      sw: "Msimbo wa AFR- ni nini?",
      bm: "AFR- code ye mun ye?",
      bas: "Code AFR- i yé jam yak?"
    },
    answer: {
      fr: "Le code AFR- est votre identifiant unique d'abonné Afroboost. Il est généré automatiquement lors de votre inscription. Gardez-le précieusement : il vous permet d'accéder à vos sessions, publier du contenu et profiter de toutes les fonctionnalités de la plateforme.",
      ln: "Code AFR- ezali elembo na yo ya bomoko lokola moto ya Afroboost. Ezali kobima yango moko na tango ya komikoma. Bomba yango malamu : epesi yo nzela ya kokɔta na masolo na yo, kokoma makambo mpe kosepela na makambo nyonso ya plateforme.",
      wo: "Code AFR- mooy sa identifiant bu wóoru abonné Afroboost. Dafay génn boppam bu nga bindoo. Denc ko bu baax : mooy la may accès ci say ndajé, bind te jariñoo ci lépp ci plateforme bi.",
      sw: "Msimbo wa AFR- ni kitambulisho chako cha kipekee cha mwanachama wa Afroboost. Hutengenezwa kiotomatiki unaposajili. Ukihifadhi vizuri: hukuwezesha kufikia vipindi vyako, kuchapisha maudhui na kufaidi vipengele vyote vya jukwaa.",
      bm: "AFR- code ye i ka Afroboost tɔndenya taamasiyɛn kelenpe ye. A bɛ da a yɛrɛ ma i ka tɔgɔdali waati. A mara ka ɲɛ : a bɛ sira di i ma ka don i ka waatiw la, ka fɛn sɛbɛn ani ka baara kɛ ni plateforme fɛn bɛɛ ye.",
      bas: "Code AFR- i yé tamasiŋ woŋ i abonné Afroboost. I nti kɛ i yɛmɛ i ngéda u tila tôi. Bɔmba wo bôŋ : i nti ti we sira i bihéga biŋ, i tilil mam ni i sôŋ i mam mɔ ma plateforme."
    }
  },
  {
    id: 7,
    category: "inscription",
    question: {
      fr: "Quelles sont les offres disponibles ?",
      ln: "Mabonza nini ezali?",
      wo: "Ban offre yoo am?",
      sw: "Ni ofa zipi zinazopatikana?",
      bm: "Sɔrɔyɔrɔ jumɛnw bɛ yen?",
      bas: "Mahɔl ma yé lɛ?"
    },
    answer: {
      fr: "Les offres varient selon votre coach. Vous pouvez trouver des sessions à l'unité, des packs de sessions, des abonnements mensuels et des cours d'essai gratuits. Consultez la vitrine de votre coach pour voir les tarifs et les détails.",
      ln: "Mabonza ekeseni na coach na yo. Okoki kozwa session moko moko, ba pack ya session, ba abonnement ya sanza mpe ba cours ya komeka ofele. Talá etalasi ya coach na yo mpo na komona ntalo mpe makambo.",
      wo: "Offre yi day soppeeku ci sa coach. Mëna nga gis session yu benn benn, pack yu session, abonnement bu weer ak cours yu jéema yu àndul dara. Xoolal vitrine bu sa coach ngir gis njëg yi ak détails yi.",
      sw: "Ofa hutofautiana kulingana na kocha wako. Unaweza kupata vipindi vya mmoja mmoja, pakiti za vipindi, usajili wa kila mwezi na masomo ya majaribio ya bure. Angalia ukurasa wa kocha wako ili kuona bei na maelezo.",
      bm: "Sɔrɔyɔrɔw bɛ danfara i ka coach la. I bɛ se ka waati kelen kelenw, waati pack w, kalo abonnementw ani dɛsɛ fu kalanw sɔrɔ. I ka coach ka jɛnkulu lajɛ ka sɔngɔw ni kunnafoni ye.",
      bas: "Mahɔl ma nti kôbla ni coach woŋ. U nti kôs bihéga bi mɔ, pack bihéga, abonnement i sɔŋ ni bihéga bi jéema bi pam. Ɓéga vitrine coach woŋ i yɔŋ njel ni bitilga."
    }
  },
  {
    id: 8,
    category: "inscription",
    question: {
      fr: "Est-ce qu'il y a un essai gratuit ?",
      ln: "Komeka ofele ezali?",
      wo: "Am na jéema bu àndul dara?",
      sw: "Je, kuna jaribio la bure?",
      bm: "Dɛsɛ fu bɛ yen wa?",
      bas: "Jéema i pam i yé?"
    },
    answer: {
      fr: "Oui ! Certains coaches proposent des cours d'essai gratuits. Consultez les offres sur la vitrine pour voir si un essai est disponible. C'est le meilleur moyen de découvrir Afroboost sans engagement.",
      ln: "Ɛɛ! Ba coach mosusu bapesaka ba cours ya komeka ofele. Talá mabonza na etalasi mpo na komona soki komeka ezali. Ezali nzela ya malamu mpo na koyeba Afroboost kozanga engagement.",
      wo: "Waaw! Yenn coach yi day joxe cours yu jéema yu àndul dara. Xoolal offre yi ci vitrine ngir gis ndax am na jéema. Mooy yoon wi gën a baax ngir xam Afroboost te du la lëmm.",
      sw: "Ndiyo! Baadhi ya makocha hutoa masomo ya majaribio ya bure. Angalia ofa kwenye ukurasa ili kuona kama jaribio linapatikana. Ni njia bora ya kugundua Afroboost bila ahadi.",
      bm: "Ɔwɔ! Coach dɔw bɛ dɛsɛ fu kalanw di. Sɔrɔyɔrɔw lajɛ jɛnkulu kan ka a ye ni dɛsɛ bɛ sɔrɔ. O ye sira ɲuman ye ka Afroboost dɔn ni jɔ tɛ.",
      bas: "Ɛɛ! Coach bi mɔ bi ti bihéga bi jéema bi pam. Ɓéga mahɔl i vitrine i yɔŋ ibale jéema i yé. I yé nzila i lôŋ i yi Afroboost ni engagement té."
    }
  },

  // === PAIEMENT ===
  {
    id: 9,
    category: "paiement",
    question: {
      fr: "Quels moyens de paiement sont acceptés ?",
      ln: "Ndenge nini ya kofuta endimami?",
      wo: "Ban anam yu fey ñu nangu?",
      sw: "Ni njia zipi za malipo zinakubaliwa?",
      bm: "Sara cogo jumɛnw bɛ minɛ?",
      bas: "Manam ma bédga ma yé kônda?"
    },
    answer: {
      fr: "Afroboost accepte les paiements par carte bancaire (Visa, Mastercard) via Stripe, et le mobile money pour certaines régions. Le paiement est sécurisé et vous recevez une confirmation par email.",
      ln: "Afroboost endimaka kofuta na carte ya banki (Visa, Mastercard) na nzela ya Stripe, mpe mobile money mpo na bitúká mosusu. Kofuta ezali na bokengi mpe okozwa ndima na email.",
      wo: "Afroboost dafay nangu fey ci carte bancaire (Visa, Mastercard) jaare Stripe, ak mobile money ci yenn goxu yi. Fey bi dafa wóor te dinga jot benn confirmation ci email.",
      sw: "Afroboost hukubali malipo kwa kadi ya benki (Visa, Mastercard) kupitia Stripe, na pesa za simu kwa baadhi ya maeneo. Malipo ni salama na utapokea uthibitisho kwa barua pepe.",
      bm: "Afroboost bɛ sara minɛ ni banki karti ye (Visa, Mastercard) Stripe fɛ, ani telefɔni wari mara yɔrɔ dɔw la. Sara lakananen don ani i bɛna dafalen sɔrɔ email fɛ.",
      bas: "Afroboost i nti kônda bédga ni karti banki (Visa, Mastercard) i Stripe, ni mobile money i bihɔmɔ bi mɔ. Bédga i yé lakan ni u nti kôs confirmation i email."
    }
  },
  {
    id: 10,
    category: "paiement",
    question: {
      fr: "Est-ce que je peux annuler ma réservation ?",
      ln: "Nakoki kolongola réservation na ngai?",
      wo: "Man naa bàyyi sama réservation?",
      sw: "Je, ninaweza kughairi nafasi yangu?",
      bm: "N bɛ se ka n ka réservation dabila wa?",
      bas: "Me nti tômbôl réservation yɛm?"
    },
    answer: {
      fr: "Les conditions d'annulation dépendent de chaque coach et de chaque offre. Contactez directement votre coach via le chat pour connaître sa politique d'annulation.",
      ln: "Mibeko ya kolongola etaleli coach na coach mpe libonza na libonza. Bengá coach na yo mbala moko na chat mpo na koyeba mibeko na ye ya kolongola.",
      wo: "Condition yu bàyyi yi day aju ci coach bu nekk ak offre bu nekk. Jokkool ak sa coach ci chat bi ngir xam politique bu bàyyi.",
      sw: "Masharti ya kughairi hutegemea kila kocha na kila ofa. Wasiliana moja kwa moja na kocha wako kupitia gumzo ili kujua sera yake ya kughairi.",
      bm: "Dabilali sariyaw bɛ bɔ coach ni coach ani sɔrɔyɔrɔ ni sɔrɔyɔrɔ la. I ka coach wele ka telen chat fɛ ka a ka dabilali sariya dɔn.",
      bas: "Bitɔ bi tômbôl bi nti aju i coach hiki ni mahɔl hiki. Sɔŋ coach woŋ i chat i yi politik i tômbôl."
    }
  },

  // === SESSIONS ET COURS ===
  {
    id: 11,
    category: "sessions",
    question: {
      fr: "Où se déroulent les sessions ?",
      ln: "Masolo esalemaka wapi?",
      wo: "Fan la ndajé yi di ame?",
      sw: "Vipindi hufanyika wapi?",
      bm: "Waatiw bɛ kɛ min?",
      bas: "Bihéga bi nti kɛ homa?"
    },
    answer: {
      fr: "Les lieux varient selon votre coach. Consultez les détails de chaque offre pour connaître l'adresse exacte. Les sessions peuvent se dérouler en salle, en plein air ou même en ligne.",
      ln: "Bisika ekeseni na coach na yo. Talá makambo ya libonza moko na moko mpo na koyeba adresse ya sikisiki. Masolo ekoki kosalema na ndako, na libanda to kaka na Internet.",
      wo: "Bërëb yi day soppeeku ci sa coach. Xoolal détails yu offre bu nekk ngir xam adresse bu wóor. Ndajé yi mëna ame ci néeg, ci biti walla sax ci internet.",
      sw: "Maeneo hutofautiana kulingana na kocha wako. Angalia maelezo ya kila ofa ili kujua anwani kamili. Vipindi vinaweza kufanyika ndani ya ukumbi, nje au hata mtandaoni.",
      bm: "Yɔrɔw bɛ danfara i ka coach la. Sɔrɔyɔrɔ kelen kelen kunnafoni lajɛ ka yɔrɔ sɛbɛn dɔn. Waatiw bɛ se ka kɛ so kɔnɔ, kɛnɛma walima hali internet kan.",
      bas: "Bihɔmɔ bi nti kôbla ni coach woŋ. Ɓéga bitilga bi mahɔl hiki i yi adres i tôbôtôbô. Bihéga bi nti kɛ i ndap, i mbal to i internet."
    }
  },
  {
    id: 12,
    category: "sessions",
    question: {
      fr: "Que dois-je apporter à une session ?",
      ln: "Nasengeli komema nini na session?",
      wo: "Lan laa war a indi ci ndajé?",
      sw: "Nilete nini kwenye kipindi?",
      bm: "N ka kan ka mun na waati la?",
      bas: "Me nlама ni jɛ i hihéga?"
    },
    answer: {
      fr: "Prévoyez une tenue de sport confortable, des baskets, une serviette et une bouteille d'eau. Vous allez transpirer, alors hydratez-vous bien avant, pendant et après la session !",
      ln: "Bongisá bilamba ya sport ya malamu, ba basket, serviette mpe molangi ya mai. Okobimisa motoki, yango wana melá mai malamu liboso, na tango mpe nsima ya session!",
      wo: "Waajal benn habit sport bu neex, basket yi, serwiet ak benn butéel ndox. Dinga ñax, kon naanal ndox bu baax bala, ci biir ak ci ginnaaw ndajé!",
      sw: "Andaa mavazi ya michezo ya starehe, viatu vya michezo, taulo na chupa ya maji. Utatoka jasho, hivyo kunywa maji vizuri kabla, wakati na baada ya kipindi!",
      bm: "Farikolo lamini fini ɲuman, sanbara, finimugu ani ji butɛli labɛn. I bɛna wusu bɔ, o la ji min ka ɲɛ waati ɲɛ, a tuma ni a kɔfɛ!",
      bas: "Labɛn bisadga bi sport bi lémél, basket, serviet ni butéli ma malép. U nti ol matén, jɔ nyoŋ malép bôŋ bisu, i ngéda ni mbus hihéga!"
    }
  },
  {
    id: 13,
    category: "sessions",
    question: {
      fr: "Est-ce que les sessions sont en groupe ou individuelles ?",
      ln: "Masolo ezali na lisangá to moto moko?",
      wo: "Ndajé yi ci group lañu walla kenn-kenn?",
      sw: "Je, vipindi ni vya kikundi au vya mtu binafsi?",
      bm: "Waatiw bɛ kɛ jɛkulu la walima kelen kelen?",
      bas: "Bihéga bi yé i likɔŋ to bi mɔ?"
    },
    answer: {
      fr: "Les sessions Afroboost sont principalement en groupe — c'est l'énergie collective qui fait la magie ! Mais certains coaches proposent aussi des sessions privées. Consultez les offres pour plus de détails.",
      ln: "Masolo ya Afroboost ezali mingi na lisangá — ezali nguya ya bato nyonso oyo esalaka likamwisi! Kasi ba coach mosusu bapesaka mpe masolo ya moto moko. Talá mabonza mpo na makambo mingi.",
      wo: "Ndajé yu Afroboost ci group lañu ci lu ëpp — doole gu mbool gi mooy def magie bi! Waaye yenn coach yi day joxe itam ndajé yu privé. Xoolal offre yi ngir am détails yu gën a bari.",
      sw: "Vipindi vya Afroboost kwa kawaida ni vya kikundi — ni nguvu ya pamoja inayofanya uchawi! Lakini baadhi ya makocha hutoa pia vipindi vya faragha. Angalia ofa kwa maelezo zaidi.",
      bm: "Afroboost waatiw bɛ kɛ jɛkulu la kosɛbɛ — jɛkulu fanga de bɛ kabako kɛ! Nka coach dɔw bɛ waati kelenw fana di. Sɔrɔyɔrɔw lajɛ ka kunnafoni caman ye.",
      bas: "Bihéga Afroboost bi yé i likɔŋ ba — i yé ngui likɔŋ i nti bɔ magie! Ndi coach bi mɔ bi ti bihéga bi mɔ. Ɓéga mahɔl i yɔŋ bitilga bi buŋ."
    }
  },

  // === PUBLICATIONS ET COMMUNAUTÉ ===
  {
    id: 14,
    category: "communaute",
    question: {
      fr: "Comment je publie du contenu ?",
      ln: "Nakoki kokoma ndenge nini?",
      wo: "Naka laa man a bind?",
      sw: "Je, nachapishaje maudhui?",
      bm: "N bɛ fɛn sɛbɛn cogo di?",
      bas: "Me nti tilil mam lɛ?"
    },
    answer: {
      fr: "Cliquez sur le bouton 'Publier +' dans le chat. Vous pouvez partager des photos et des vidéos (max 1 minute). Recadrez votre image, choisissez votre miniature vidéo et ajoutez une légende. Votre publication sera visible pendant 48 heures.",
      ln: "Finá bouton 'Kokoma +' na chat. Okoki kokabola bafoto mpe ba vidéo (miniti 1 mpenza). Kata elilingi na yo, poná elilingi ya vidéo mpe bakisá maloba. Kokoma na yo ekomonana ngonga 48.",
      wo: "Bësal ci bouton 'Bind +' ci chat bi. Mëna nga séddoo photo ak vidéo (1 simili rekk). Dëgëral sa nataal, tànnal miniature vidéo te dolli benn légende. Sa bind dina feeñ 48 waxtu.",
      sw: "Bofya kitufe cha 'Chapisha +' kwenye gumzo. Unaweza kushiriki picha na video (dakika 1 kikomo). Punguza picha yako, chagua kijipicha cha video na uongeze maelezo. Chapisho lako litaonekana kwa saa 48.",
      bm: "'Sɛbɛn +' butɔni digi chat kɔnɔ. I bɛ se ka jaw ni video w tila (miniti 1 dama). I ka ja tigɛ, video ja fitini sugandi ani kuma fara a kan. I ka sɛbɛnni bɛna ye lɛrɛ 48 kɔnɔ.",
      bas: "Tôp butɔŋ 'Tilil +' i chat. U nti kôbôl bifôtô ni bivideo (1 minit dama). Kôdôl imag woŋ, sɔ miniature video ni ságal légende. Tilil woŋ i nti yé i 48 ngéda."
    }
  },
  {
    id: 15,
    category: "communaute",
    question: {
      fr: "Pourquoi mes publications disparaissent après 48h ?",
      ln: "Mpo na nini makomi na ngai elimwaka nsima ya 48h?",
      wo: "Lu tax samay bind di réer ci ginnaaw 48h?",
      sw: "Kwa nini machapisho yangu hupotea baada ya saa 48?",
      bm: "Mun na ne ka sɛbɛnw bɛ tunun 48h kɔfɛ?",
      bas: "Inyu kii bitilil biɛm bi nti dimbi mbus 48h?"
    },
    answer: {
      fr: "Les publications ont une durée de vie de 48 heures pour garder le contenu frais et dynamique, un peu comme les stories Instagram. Cela encourage tout le monde à partager régulièrement et maintient l'énergie de la communauté !",
      ln: "Makomi ezali na bomoi ya ngonga 48 mpo na kobatela makambo ya sika mpe ya bomoi, lokola ba stories ya Instagram. Yango elendisaka bato nyonso kokabola mbala na mbala mpe ebatelaka nguya ya lisangá!",
      wo: "Bind yi am nañu benn bakkan bu 48 waxtu ngir denc contenu bi bu bees te bu am doole, mel ni story yu Instagram. Loolu dafay xiir ñépp ñu séddoo bu baax te dafay denc doole gu mbool mi!",
      sw: "Machapisho yana muda wa kuishi wa saa 48 ili kuweka maudhui mapya na yenye msisimko, kama hadithi za Instagram. Hii huhamasisha kila mtu kushiriki mara kwa mara na kudumisha nguvu ya jamii!",
      bm: "Sɛbɛnniw si ye lɛrɛ 48 ye walasa ka fɛnw to kura ni yɛlɛma la, i n'a fɔ Instagram stories. O bɛ bɛɛ dusu don ka tila tuma ni tuma ani a bɛ jɛkulu fanga mara!",
      bas: "Bitilil bi yé ni ngéda i 48 ngéda i bɔmba mam ma nyena ni ma ngui, i nti stories Instagram. Jam i nti sôŋ bôt biki i kôbôl ni ngéda ni i mara ngui likɔŋ!"
    }
  },
  {
    id: 16,
    category: "communaute",
    question: {
      fr: "Est-ce que je peux modifier ou supprimer ma publication ?",
      ln: "Nakoki kobongola to kolongola kokoma na ngai?",
      wo: "Man naa soppi walla far sama bind?",
      sw: "Je, ninaweza kuhariri au kufuta chapisho langu?",
      bm: "N bɛ se ka n ka sɛbɛnni yɛlɛma walima ka a bɔ wa?",
      bas: "Me nti kôbla to hɛɛ tilil yɛm?"
    },
    answer: {
      fr: "Oui ! Allez dans 'Mes publications' depuis le chat, vous y trouverez toutes vos publications avec les options modifier et supprimer.",
      ln: "Ɛɛ! Kende na 'Makomi na ngai' na chat, okozwa kuna makomi na yo nyonso na baoption ya kobongola mpe kolongola.",
      wo: "Waaw! Demal ci 'Samay bind' ci chat bi, dinga fa gis say bind yépp ak option yu soppi ak far.",
      sw: "Ndiyo! Nenda kwenye 'Machapisho yangu' kutoka kwenye gumzo, utapata machapisho yako yote pamoja na chaguo za kuhariri na kufuta.",
      bm: "Ɔwɔ! Taga 'Ne ka sɛbɛnw' la ka bɔ chat la, i bɛna i ka sɛbɛnniw bɛɛ sɔrɔ yen ni yɛlɛma ni bɔli cogoyaw ye.",
      bas: "Ɛɛ! Kɛ i 'Bitilil biɛm' i chat, u nti yɔŋ bitilil biŋ mɔ ni option i kôbla ni hɛɛ."
    }
  },

  // === COACH ET PLATEFORME ===
  {
    id: 17,
    category: "plateforme",
    question: {
      fr: "Comment je contacte mon coach ?",
      ln: "Nakoki kobenga coach na ngai ndenge nini?",
      wo: "Naka laa man a jokkoo ak sama coach?",
      sw: "Je, ninawasilianaje na kocha wangu?",
      bm: "N bɛ n ka coach wele cogo di?",
      bas: "Me nti sɔŋ coach woŋ lɛ?"
    },
    answer: {
      fr: "Utilisez le chat intégré sur le site de votre coach. Vous pouvez lui envoyer un message directement. Si le mode IA est activé, vous pouvez aussi poser vos questions ici et obtenir des réponses instantanées.",
      ln: "Salelá chat oyo ezali na site ya coach na yo. Okoki kotindela ye nsango mbala moko. Soki mode IA efungwami, okoki mpe kotuna mituna awa mpe kozwa biyano mbala moko.",
      wo: "Jëfandikoo chat bi ci site bu sa coach. Mëna nga ko yónnee benn message ci noppi. Su mode IA bi ubbeeku, mëna nga laaj say laaj fi te jot tontu ci saa si.",
      sw: "Tumia gumzo lililopo kwenye tovuti ya kocha wako. Unaweza kumtumia ujumbe moja kwa moja. Ikiwa hali ya AI imewashwa, unaweza pia kuuliza maswali yako hapa na kupata majibu papo hapo.",
      bm: "I ka coach ka site chat baara. I bɛ se ka cikan ci a ma telen. Ni IA cogoya dabɔra, i bɛ se ka i ka ɲininkaliw kɛ yan fana ka jaabiw sɔrɔ o yɔrɔnin bɛɛ.",
      bas: "Bɔŋ chat i site coach woŋ. U nti lɔm nye mahéa i telen. Ibale mode IA i yé, u nti nôlôl mambadga maŋ hana ni kôs mayôl i ngéda yada."
    }
  },
  {
    id: 18,
    category: "plateforme",
    question: {
      fr: "Est-ce que je peux installer l'application sur mon téléphone ?",
      ln: "Nakoki kotia application na telefone na ngai?",
      wo: "Man naa samp application bi ci sama telefon?",
      sw: "Je, ninaweza kusakinisha programu kwenye simu yangu?",
      bm: "N bɛ se ka application sigi n ka telefɔni kan wa?",
      bas: "Me nti tééna application i telefon yɛm?"
    },
    answer: {
      fr: "Oui ! Afroboost est une application web progressive (PWA). Sur votre téléphone, ouvrez le site dans Chrome ou Safari, puis cliquez sur 'Ajouter à l'écran d'accueil'. Vous recevrez des notifications comme une vraie application !",
      ln: "Ɛɛ! Afroboost ezali application web progressive (PWA). Na telefone na yo, fungolá site na Chrome to Safari, sima finá 'Kobakisa na écran ya ndako'. Okozwa ba notifications lokola application ya solo!",
      wo: "Waaw! Afroboost ab application web progressive la (PWA). Ci sa telefon, ubbil site bi ci Chrome walla Safari, ba noppi bësal ci 'Yokk ci écran d'accueil'. Dinga jot notification yi mel ni benn application bu wóor!",
      sw: "Ndiyo! Afroboost ni programu ya wavuti inayoendelea (PWA). Kwenye simu yako, fungua tovuti katika Chrome au Safari, kisha bofya 'Ongeza kwenye skrini ya kwanza'. Utapokea arifa kama programu halisi!",
      bm: "Ɔwɔ! Afroboost ye web application ɲɛtaa (PWA) ye. I ka telefɔni kan, site da yɛlɛ Chrome walima Safari la, o kɔ digi 'A fara ekran fɔlɔ kan'. I bɛna kunnafoni sɔrɔ i n'a fɔ application yɛrɛyɛrɛ!",
      bas: "Ɛɛ! Afroboost i yé application web progressive (PWA). I telefon woŋ, bulɔ site i Chrome to Safari, mbus tôp 'Ságal i ekran i ndap'. U nti kôs notification i nti application i tôbôtôbô!"
    }
  },
  {
    id: 19,
    category: "plateforme",
    question: {
      fr: "Comment devenir coach partenaire Afroboost ?",
      ln: "Nakoki kokoma coach partenaire Afroboost ndenge nini?",
      wo: "Naka laa man a doon coach partenaire Afroboost?",
      sw: "Je, ninawezaje kuwa kocha mshirika wa Afroboost?",
      bm: "N bɛ kɛ Afroboost coach jɛɲɔgɔn ye cogo di?",
      bas: "Me nti kɛ coach partenaire Afroboost lɛ?"
    },
    answer: {
      fr: "Si vous êtes coach fitness ou danse et que vous souhaitez rejoindre la plateforme Afroboost, contactez-nous via le chat ou par email. Vous aurez votre propre vitrine personnalisée, vos outils de gestion et votre communauté.",
      ln: "Soki ozali coach ya fitness to bobini mpe olingi kokota na plateforme Afroboost, bengá biso na chat to na email. Okozala na etalasi na yo moko, bisaleli na yo ya bokambi mpe lisangá na yo.",
      wo: "Su nga doon coach fitness walla fecc te bëgg nga bokk ci plateforme Afroboost, jokkool ak nun ci chat bi walla email. Dinga am sa bopp vitrine bu personnalisé, say jumtukaay yu géstion ak sa communauté.",
      sw: "Ikiwa wewe ni kocha wa mazoezi au dansi na unataka kujiunga na jukwaa la Afroboost, wasiliana nasi kupitia gumzo au barua pepe. Utapata ukurasa wako binafsi, zana zako za usimamizi na jamii yako.",
      bm: "Ni i ye fitness walima dɔn coach ye ani i b'a fɛ ka don Afroboost plateforme la, i ka an wele chat walima email fɛ. I bɛna i yɛrɛ ka jɛnkulu kɛrɛnkɛrɛnnen sɔrɔ, i ka ɲɛmɔgɔya minɛnw ani i ka jɛkulu.",
      bas: "Ibale u yé coach fitness to danse ni u gwés kɛ i plateforme Afroboost, sɔŋ bés i chat to email. U nti kôs vitrine woŋ i mɔ, bisadga bi géstion ni likɔŋ woŋ."
    }
  },
  {
    id: 20,
    category: "plateforme",
    question: {
      fr: "Est-ce que mes données sont sécurisées ?",
      ln: "Ba données na ngai ezali na bokengi?",
      wo: "Sama données yi wóor nañu?",
      sw: "Je, data zangu ziko salama?",
      bm: "Ne ka kunnafoniw lakananen don wa?",
      bas: "Bitɔ biɛm bi yé lakan?"
    },
    answer: {
      fr: "Oui, vos données sont protégées. Les paiements passent par Stripe (certifié PCI DSS), vos informations personnelles ne sont jamais partagées avec des tiers, et chaque coach a un espace isolé.",
      ln: "Ɛɛ, ba données na yo ezali na libateli. Kofuta elekaka na Stripe (endimami PCI DSS), makambo na yo ya moto moko ekabolamaka na bato mosusu te, mpe coach moko na moko azali na esika na ye moko.",
      wo: "Waaw, say données yi ñu ko aar. Fey yi day jaar ci Stripe (certifié PCI DSS), say xibaar yu personnel duñu leen séddoo ak ñeneen, te coach bu nekk am na benn espace bu wéet.",
      sw: "Ndiyo, data zako zinalindwa. Malipo hupitia Stripe (iliyoidhinishwa PCI DSS), taarifa zako binafsi hazishirikiwi kamwe na wengine, na kila kocha ana nafasi yake iliyotengwa.",
      bm: "Ɔwɔ, i ka kunnafoniw lakananen don. Saraw bɛ tɛmɛ Stripe fɛ (PCI DSS dafalen), i ka mɔgɔ yɛrɛ kunnafoniw tɛ tila mɔgɔ wɛrɛw fɛ abada, ani coach kelen kelen bɛ ni yɔrɔ danfaralen ye.",
      bas: "Ɛɛ, bitɔ biŋ bi yé lakan. Bédga bi nti tabé i Stripe (PCI DSS), bitɔ biŋ bi mɔ bi ta kôbôl ni bôt bi buŋ, ni coach hiki a yé ni homa i mɔ."
    }
  }
];

// V275d : traductions Créole (haïtien/antillais) des 20 Q&R, injectees dans la
// structure existante (question.ht / answer.ht). Table separee pour ne pas
// gonfler chaque objet ci-dessus.
const _HT_FAQ = {
  1: { q: "Kisa Afroboost ye?", a: "Afroboost se yon konsèp fitness imèsif ki melanje dans afrobeat, kadyo entans ak enèji kolektif. Chak sesyon se yon eksperyans konplè : ou swe, ou danse epi ou amize an menm tan. Ou pa bezwen konn danse, jis vle bouje!" },
  2: { q: "Èske mwen dwe konn danse?", a: "Non menm! Afroboost aksesib pou tout nivo. Mouvman yo senp epi yo repete, objektif la se bouje ak swe, se pa fè espektak. Kòch ou ap gide ou etap pa etap." },
  3: { q: "Ki byenfè yon sesyon Afroboost genyen?", a: "Yon sesyon Afroboost pèmèt boule ant 400 ak 800 kalori, amelyore kadyo ou, ranfòse misk ou, diminye estrès epi ogmante konfyans ou. Tout sa nan yon anbyans fèt ak motivan!" },
  4: { q: "Konbyen tan yon sesyon dire?", a: "Yon sesyon dire jeneralman ant 45 minit ak 1 èdtan, ak echofman ak retou nan kalm. Li entans men tan an pase vit gras ak mizik la ak enèji gwoup la!" },
  5: { q: "Kijan mwen enskri?", a: "Se senp : chwazi yon òf sou vitrin kòch ou, klike sou 'Rezève', antre enfòmasyon ou epi konfime. W ap resevwa yon kòd AFR- ki ba ou aksè a tout fonksyonalite yo." },
  6: { q: "Kisa kòd AFR- a ye?", a: "Kòd AFR- a se idantifyan inik ou kòm abòne Afroboost. Li jenere otomatikman lè ou enskri. Kenbe l byen : li pèmèt ou jwenn aksè a sesyon ou yo, pibliye kontni epi pwofite tout fonksyonalite platfòm la." },
  7: { q: "Ki òf ki disponib?", a: "Òf yo varye selon kòch ou. Ou ka jwenn sesyon inik, pakè sesyon, abònman chak mwa ak kou esè gratis. Gade vitrin kòch ou pou wè pri yo ak detay yo." },
  8: { q: "Èske gen yon esè gratis?", a: "Wi! Kèk kòch ofri kou esè gratis. Gade òf yo sou vitrin lan pou wè si gen yon esè disponib. Se pi bon fason pou dekouvri Afroboost san angajman." },
  9: { q: "Ki mwayen peman yo aksepte?", a: "Afroboost aksepte peman ak kat bankè (Visa, Mastercard) atravè Stripe, ak lajan mobil pou kèk rejyon. Peman an sekirize epi w ap resevwa yon konfimasyon pa imèl." },
  10: { q: "Èske mwen ka anile rezèvasyon mwen?", a: "Kondisyon anilasyon yo depann de chak kòch ak chak òf. Kontakte kòch ou dirèkteman nan chat la pou konnen politik anilasyon li." },
  11: { q: "Kote sesyon yo fèt?", a: "Kote yo varye selon kòch ou. Gade detay chak òf pou konnen adrès egzak la. Sesyon yo ka fèt nan yon sal, deyò oswa menm anliy." },
  12: { q: "Kisa mwen dwe pote nan yon sesyon?", a: "Prepare yon rad espò konfòtab, soulye espò, yon sèvyèt ak yon boutèy dlo. Ou pral swe, kidonk bwè dlo byen anvan, pandan ak apre sesyon an!" },
  13: { q: "Èske sesyon yo an gwoup oswa endividyèl?", a: "Sesyon Afroboost yo prensipalman an gwoup — se enèji kolektif la ki fè maji a! Men kèk kòch ofri tou sesyon prive. Gade òf yo pou plis detay." },
  14: { q: "Kijan mwen pibliye kontni?", a: "Klike sou bouton 'Pibliye +' nan chat la. Ou ka pataje foto ak videyo (maksimòm 1 minit). Koupe imaj ou, chwazi miniyati videyo ou epi ajoute yon lejand. Piblikasyon ou ap vizib pandan 48 èdtan." },
  15: { q: "Poukisa piblikasyon mwen disparèt apre 48è?", a: "Piblikasyon yo gen yon dire lavi 48 èdtan pou kenbe kontni an fre ak dinamik, tankou istwa Instagram yo. Sa ankouraje tout moun pataje regilyèman epi kenbe enèji kominote a!" },
  16: { q: "Èske mwen ka modifye oswa efase piblikasyon mwen?", a: "Wi! Ale nan 'Piblikasyon mwen' depi nan chat la, w ap jwenn tout piblikasyon ou yo ak opsyon pou modifye ak efase." },
  17: { q: "Kijan mwen kontakte kòch mwen?", a: "Sèvi ak chat entegre a sou sit kòch ou. Ou ka voye yon mesaj dirèkteman ba li. Si mòd IA a aktive, ou ka poze kesyon ou yo isit la tou epi jwenn repons imedyat." },
  18: { q: "Èske mwen ka enstale aplikasyon an sou telefòn mwen?", a: "Wi! Afroboost se yon aplikasyon web pwogresif (PWA). Sou telefòn ou, ouvri sit la nan Chrome oswa Safari, epi klike sou 'Ajoute nan ekran akèy la'. W ap resevwa notifikasyon tankou yon vrè aplikasyon!" },
  19: { q: "Kijan pou vin kòch patnè Afroboost?", a: "Si ou se yon kòch fitness oswa dans epi ou vle rejwenn platfòm Afroboost la, kontakte nou nan chat la oswa pa imèl. W ap gen pwòp vitrin pèsonalize ou, zouti jesyon ou ak kominote ou." },
  20: { q: "Èske done mwen yo an sekirite?", a: "Wi, done ou yo pwoteje. Peman yo pase atravè Stripe (sètifye PCI DSS), enfòmasyon pèsonèl ou yo pa janm pataje ak lòt moun, epi chak kòch gen yon espas izole." }
};
faqAfroboost.forEach((item) => {
  const h = _HT_FAQ[item.id];
  if (h) {
    if (item.question && typeof item.question === 'object') item.question.ht = h.q;
    if (item.answer && typeof item.answer === 'object') item.answer.ht = h.a;
  }
});

// Catégories pour le filtre (id null = tout afficher). Labels multilingues (V275/V275d).
export const faqCategories = [
  { id: null, label: { fr: 'Tout', ln: 'Nyonso', wo: 'Yépp', sw: 'Yote', bm: 'Bɛɛ', bas: 'Hiki jam', ht: 'Tout' } },
  { id: 'concept', label: { fr: 'Concept', ln: 'Likanisi', wo: 'Xam-xam', sw: 'Dhana', bm: 'Hakili', bas: 'Nyambe', ht: 'Konsèp' } },
  { id: 'inscription', label: { fr: 'Inscription', ln: 'Bokomi', wo: 'Bindu', sw: 'Usajili', bm: 'Tɔgɔda', bas: 'Tila tôi', ht: 'Enskripsyon' } },
  { id: 'paiement', label: { fr: 'Paiement', ln: 'Kofuta', wo: 'Fey', sw: 'Malipo', bm: 'Sara', bas: 'Bédga', ht: 'Peman' } },
  { id: 'sessions', label: { fr: 'Sessions', ln: 'Masolo', wo: 'Ndajé yi', sw: 'Vipindi', bm: 'Kalanso', bas: 'Bihéga', ht: 'Sesyon' } },
  { id: 'communaute', label: { fr: 'Communauté', ln: 'Lisangá', wo: 'Mbool', sw: 'Jamii', bm: 'Jɛkulu', bas: 'Likɔŋ', ht: 'Kominote' } },
  { id: 'plateforme', label: { fr: 'Plateforme', ln: 'Esika', wo: 'Plateforme', sw: 'Jukwaa', bm: 'Yɔrɔ', bas: 'Homa', ht: 'Platfòm' } }
];

// Intro + libellés du panneau FAQ, multilingues (V275/V275d).
export const faqUiText = {
  intro: {
    fr: "Posez-moi une question ! Cliquez sur un sujet ci-dessous.",
    ln: "Tuná ngai motuna! Finá likambo awa na se.",
    wo: "Laaj ma! Bësal ci benn sujet ci suuf.",
    sw: "Niulize swali! Bofya mada hapa chini.",
    bm: "Ne ɲininka! Digi kuma dɔ kan duguma.",
    bas: "Nôlôl me! Tôp njômbi hana i si.",
    ht: "Poze m yon kesyon! Klike sou yon sijè anba a."
  }
};

export default faqAfroboost;
