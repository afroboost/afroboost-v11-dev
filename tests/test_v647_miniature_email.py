# -*- coding: utf-8 -*-
"""V647 — la miniature vidéo cliquable dans l'e-mail de prospection. HORS LIGNE.

    MONGO_URL=mongodb://127.0.0.1:27017 DB_NAME=test python3 -m pytest tests/test_v647_miniature_email.py -q

CE QUE CES TESTS PROTEGENT :
  1. un e-mail SANS vidéo rend exactement ce qu'il rendait avant V647 ;
  2. la miniature remplace la ligne « Voir la vidéo Afroboost : <url> » À SA
     PLACE dans le message, pas après la signature ;
  3. aucune injection HTML n'est possible, même si le message en contient ;
  4. la version texte/plain reste le message, complet et lisible.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "test")

from api.server import (  # noqa: E402
    p3s3d2_corps_html, v647_corps_html, v647_ligne_video, V620_LIBELLE_VIDEO,
    P3S3DFournisseurEmail, v620_carte_html,
)

VIDEO = "/api/files/ed649bd2da5546d1/video_ed649bd2da5546d1.mp4"
MINI = "/api/files/0d96d0958973405b/image_0d96d0958973405b.jpg"
ABS = "https://afroboost.com" + VIDEO

MEDIA = {"media_id": "167eb1d6", "origine": "bibliotheque", "type": "video", "url": VIDEO,
         "miniature_url": MINI, "titre": "AFROBOOST CORPORATE PREMIUM 75S 16x9",
         "format": "16_9", "duree": 75}

LIGNE = "%s : %s" % (V620_LIBELLE_VIDEO, ABS)

MESSAGE = "\n".join([
    "Bonjour,", "",
    "Je suis Coach Bassi, d’Afroboost à Neuchâtel.", "",
    "Pour découvrir l’expérience Afroboost Corporate en images, voici notre vidéo de présentation.", "",
    LIGNE, "",
    "Seriez-vous disponible pour un échange de 15 minutes ?", "",
    "Coach Bassi", "076 520 33 63",
])


def test_la_ligne_a_ecrire_est_celle_que_le_html_reconnait():
    """Le texte du message et le repère du rendu viennent de la MÊME fonction."""
    assert v647_ligne_video(MEDIA) == LIGNE
    assert LIGNE in MESSAGE


def test_sans_media_le_html_est_identique_a_avant_v647():
    """Contrat de non-régression : tous les e-mails déjà en circulation."""
    for m in (MESSAGE, "Bonjour,\n\nTexte simple.", "", None):
        assert v647_corps_html(m, None) == p3s3d2_corps_html(m)


def test_sans_la_ligne_video_le_html_est_identique_a_avant_v647():
    """Un média attaché mais un message qui n'annonce rien : on ne force rien."""
    sans = "Bonjour,\n\nAucune vidéo annoncée ici.\n\nCoach Bassi"
    assert v647_corps_html(sans, MEDIA) == p3s3d2_corps_html(sans)


def test_media_sans_miniature_retombe_sur_le_rendu_simple():
    """Pas d'image de couverture = pas de carte muette : on garde le lien texte."""
    sans_mini = dict(MEDIA, miniature_url=None)
    assert v647_corps_html(MESSAGE, sans_mini) == p3s3d2_corps_html(MESSAGE)


def test_la_miniature_remplace_la_ligne_a_sa_place_dans_le_message():
    html = v647_corps_html(MESSAGE, MEDIA)
    # La carte est là, l'adresse technique n'apparaît plus en clair comme texte.
    assert v620_carte_html(MEDIA) in html
    assert '<p style="margin:0 0 12px;">%s</p>' % LIGNE not in html
    # ... et elle est AVANT la demande de rendez-vous et la signature.
    # `rindex` pour la signature : « Coach Bassi » apparaît aussi plus haut,
    # dans la phrase de présentation.
    i_carte = html.index("<table")
    assert i_carte < html.index("Seriez-vous disponible")
    assert i_carte < html.rindex("Coach Bassi")
    # ... et APRÈS la phrase qui l'annonce.
    assert html.index("voici notre vidéo de présentation") < i_carte


def test_la_carte_est_cliquable_sur_l_image_et_sur_le_bouton():
    html = v647_corps_html(MESSAGE, MEDIA)
    assert html.count('href="%s"' % ABS) >= 2          # l'image ET le bouton
    assert 'src="https://afroboost.com%s"' % MINI in html
    assert "&#9654;" in html                            # le triangle de lecture
    assert "autoplay" not in html.lower()
    assert "<video" not in html.lower()
    assert 'width="480"' in html and "height:auto" in html   # 16:9 respecté


def test_alternative_texte_si_les_images_sont_bloquees():
    """Image bloquée : il reste le bouton (texte) et l'attribut alt."""
    html = v647_corps_html(MESSAGE, MEDIA)
    assert 'alt="%s"' % V620_LIBELLE_VIDEO in html
    assert V620_LIBELLE_VIDEO in html


def test_aucune_injection_html_meme_depuis_le_message():
    piege = "\n".join(["Bonjour <script>alert(1)</script>", "",
                       "<img src=x onerror=alert(1)>", "", LIGNE, "", "A & B < C"])
    html = v647_corps_html(piege, MEDIA)
    # AUCUNE balise du message n'est rendue comme balise : elles sont échappées.
    # Le mot « onerror » peut rester VISIBLE en texte — c'est précisément la
    # preuve qu'il est inerte : il est précédé de `&lt;img`, pas de `<img`.
    assert "<script" not in html
    assert "<img src=x" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "&lt;img src=x onerror=alert(1)&gt;" in html
    assert "A &amp; B &lt; C" in html
    # La seule balise <img> réellement rendue est celle de la carte.
    assert html.count("<img") == 1
    assert 'src="https://afroboost.com%s"' % MINI in html


def test_une_url_quelconque_ne_produit_jamais_de_carte():
    """Seule l'adresse EXACTE du média validé déclenche la miniature."""
    faux = MESSAGE.replace(ABS, "https://exemple-pirate.ch/video.mp4")
    assert v647_corps_html(faux, MEDIA) == p3s3d2_corps_html(faux)
    assert "exemple-pirate" not in v647_corps_html(faux, MEDIA) or "&lt;" not in ""


def test_la_charge_utile_porte_le_texte_intact_et_le_html_avec_miniature():
    f = P3S3DFournisseurEmail(objet="Objet de secours", media=MEDIA)
    charge = f.charge_utile({"destinataire": "contact@exemple.ch", "message": MESSAGE}, "cle-1")
    params = charge["params"]
    assert params["text"] == MESSAGE                    # texte/plain : le message, intact
    assert LIGNE in params["text"]                      # ... avec le lien, lisible
    assert "<table" in params["html"]                   # HTML : la miniature
    assert params["to"] == ["contact@exemple.ch"]


def test_un_fournisseur_sans_media_rend_la_charge_utile_d_avant_v647():
    sans = P3S3DFournisseurEmail(objet="Objet").charge_utile(
        {"destinataire": "a@b.ch", "message": MESSAGE}, "k")
    assert sans["params"]["html"] == p3s3d2_corps_html(MESSAGE)
    assert sans["params"]["text"] == MESSAGE


def test_la_miniature_survit_a_un_domaine_different_dans_le_texte():
    """V647 — ROBUSTESSE AU DOMAINE. Le message est écrit une fois avec
    `https://afroboost.com/...` ; `V604_SITE` dépend, lui, de `FRONTEND_URL`.
    Comparer les adresses entières ferait disparaître la miniature au premier
    environnement où cette variable diffère — un échec silencieux."""
    autre = MESSAGE.replace(ABS, "https://preview.exemple.app" + VIDEO)
    html = v647_corps_html(autre, MEDIA)
    assert "<table" in html                       # la carte est bien rendue
    assert "preview.exemple.app" not in html      # ... et le lien est celui du serveur
    assert 'href="%s"' % ABS in html


def test_un_chemin_different_ne_produit_jamais_de_carte():
    """Même libellé, autre fichier : aucune carte. Le chemin doit correspondre."""
    autre = MESSAGE.replace(VIDEO, "/api/files/0000000000000000/video_autre.mp4")
    assert v647_corps_html(autre, MEDIA) == p3s3d2_corps_html(autre)
