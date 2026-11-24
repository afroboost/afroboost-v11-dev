# -*- coding: utf-8 -*-
"""V673 — MESSAGE EXCEPTIONNEL JOINT AUX RAPPELS AVANT COURS.

Ce banc rejoue le VRAI moteur `cron_reservation_reminders` (extrait de
`api/server.py` par le harnais partagé RV2), les VRAIES routes V673, et le VRAI
passage RV-AB (abonnés sans réservation). Rien n'est recopié à la main.

Aucun réseau. Aucun Push réel. Aucun e-mail réel. Aucune base réelle.

Lancement :  python3 tests/test_v673_message_exceptionnel.py
"""
try:   # V608 : point d'envoi Resend unique, visible des fonctions extraites
    import builtins as _b608, os as _o608, sys as _s608
    _s608.path.insert(0, _o608.path.dirname(_o608.path.dirname(_o608.path.abspath(__file__))))
    import api.resend_central as _rc608
    _b608._rc = _rc608
except Exception:  # noqa: BLE001
    pass
import asyncio
import copy
import io
import os
import sys
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

ICI = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.dirname(ICI)
sys.path.insert(0, ICI)
sys.path.insert(0, RACINE)
os.environ.setdefault("MONGO_URL", "mongodb://bouchon-v673:27017")

import test_rv2_rappels_push_email as H          # noqa: E402  (harnais partagé)
from api.routes import rappel_message as M       # noqa: E402

ZH = ZoneInfo("Europe/Zurich")
SRC = io.open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()
_ok = _ko = 0


def verifie(titre, cond, detail=""):
    global _ok, _ko
    if cond:
        _ok += 1
        print("PASS  %s" % titre)
    else:
        _ko += 1
        print("FAIL  %s%s" % (titre, (" — " + str(detail)) if detail else ""))


MESSAGE = ("Bonjour à toutes et à tous,\n\nExceptionnellement, Coach Bassi sera absent "
           "ce mercredi 25 novembre pour une urgence familiale.\n\nLe cours est maintenu "
           "et sera assuré par Marie.")


def boucle(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ═══════════════════════════════════════════════════════════════ A. PUR
print("\n--- A : VALIDATION ET PÉRIODE (fonctions pures) ---")
J = date(2026, 11, 24)
_m, _r = M.valider({"texte": "  Salut  ", "du": "2026-11-25"}, J)
verifie("A1. message valide, `au` vaut `du` par défaut",
        _r is None and _m == {"texte": "Salut", "du": "2026-11-25", "au": "2026-11-25"}, (_m, _r))
verifie("A2. message vide refusé", M.valider({"texte": "   ", "du": "2026-11-25"}, J)[1])
verifie("A3. message trop long refusé",
        M.valider({"texte": "x" * (M.MAX_CARACTERES + 1), "du": "2026-11-25"}, J)[1])
verifie("A4. date absente refusée", M.valider({"texte": "a"}, J)[1])
verifie("A5. date illisible refusée", M.valider({"texte": "a", "du": "25/11/2026"}, J)[1])
verifie("A6. fin avant début refusée",
        M.valider({"texte": "a", "du": "2026-11-26", "au": "2026-11-25"}, J)[1])
verifie("A7. période > 31 jours refusée (pas de message « permanent »)",
        M.valider({"texte": "a", "du": "2026-11-25", "au": "2027-01-10"}, J)[1])
verifie("A8. période entièrement passée refusée",
        M.valider({"texte": "a", "du": "2026-11-20", "au": "2026-11-23"}, J)[1])
verifie("A9. corps non-objet refusé", M.valider("texte", J)[1])
verifie("A10. retours à la ligne gardés, caractères de contrôle retirés",
        M.nettoyer_texte("a\r\nb\x00c\n\n\n\nd") == "a\nbc\n\nd", repr(M.nettoyer_texte("a\r\nb\x00c\n\n\n\nd")))

_msg = {"texte": "Marie remplace", "du": "2026-11-25", "au": "2026-11-25"}
_c = {"message_exceptionnel": _msg}
_mer_1830 = datetime(2026, 11, 25, 18, 30, tzinfo=ZH).astimezone(timezone.utc)
_dim_1830 = datetime(2026, 11, 29, 18, 30, tzinfo=ZH).astimezone(timezone.utc)
verifie("A11. séance DANS la période -> message joint",
        M.message_pour_seance(_c, _mer_1830, ZH) == "Marie remplace")
verifie("A12. séance suivante HORS période -> rien (pas de réutilisation)",
        M.message_pour_seance(_c, _dim_1830, ZH) == "")
_minuit = datetime(2026, 11, 24, 23, 30, tzinfo=timezone.utc)   # = 25/11 00:30 à Zurich
verifie("A13. la date est lue en heure de ZURICH, pas en UTC",
        M.message_pour_seance(_c, _minuit, ZH) == "Marie remplace")
verifie("A14. champ absent / abîmé -> rien, sans exception",
        M.message_pour_seance({}, _mer_1830, ZH) == ""
        and M.message_pour_seance({"message_exceptionnel": "texte nu"}, _mer_1830, ZH) == ""
        and M.message_pour_seance({"message_exceptionnel": {"texte": "x"}}, _mer_1830, ZH) == ""
        and M.message_pour_seance(None, _mer_1830, ZH) == "")
verifie("A15. extrait Push borné", len(M.extrait_push("y" * 500)) == M.PUSH_MAX)
verifie("A16. corps Push inchangé sans message", M.corps_push("habituel", "") == "habituel")
_bh = M.bloc_html("<script>alert(1)</script>\nligne 2", "#D91CD2")
verifie("A17. HTML du message ÉCHAPPÉ", "<script>" not in _bh and "&lt;script&gt;" in _bh and "<br>" in _bh)


# ═══════════════════════════════════════════════════════════ B. MOTEUR
print("\n--- B : MOTEUR RÉEL (réservations) ---")


def jour_local(r):
    return datetime.fromisoformat(r["datetime"]).astimezone(ZH).date().isoformat()


def cours_msg(cid="c1", texte=MESSAGE, du=None, au=None, **kw):
    d = H.cours(cid=cid, **kw)
    if texte is not None:
        d["message_exceptionnel"] = {"texte": texte, "du": du, "au": au or du}
    return d


async def passage(resas, cours_docs, **kw):
    b, base = H.bac(resas, cours_docs=cours_docs, **kw)
    await b["cron_reservation_reminders"]()
    return b, base


async def scenarios_moteur():
    # B1 — référence SANS message : capture exacte de ce qui part aujourd'hui.
    r0 = H.resa()
    b, _ = await passage([copy.deepcopy(r0)], [H.cours()])
    ref_push, ref_mail = copy.deepcopy(H.PUSHS), copy.deepcopy(H.EMAILS)
    verifie("B1. sans message : 1 Push + 1 e-mail (comportement actuel)",
            len(ref_push) == 1 and len(ref_mail) == 1)

    # B2 — message présent mais HORS période : rendu IDENTIQUE au caractère près.
    _hier = (datetime.fromisoformat(r0["datetime"]).astimezone(ZH).date()
             - timedelta(days=3)).isoformat()
    await passage([copy.deepcopy(r0)], [cours_msg(du=_hier)])
    verifie("B2. message hors période : Push et e-mail IDENTIQUES à la référence",
            H.PUSHS == ref_push and [(e["subject"], e["html"], e["text"]) for e in H.EMAILS]
            == [(e["subject"], e["html"], e["text"]) for e in ref_mail])

    # B3 — message DANS la période.
    _j = jour_local(r0)
    b, base = await passage([copy.deepcopy(r0)], [cours_msg(du=_j)])
    _mail = H.EMAILS[0] if H.EMAILS else {}
    _push = H.PUSHS[0] if H.PUSHS else {}
    verifie("B3. e-mail : le message figure dans le HTML (échappé) et le texte",
            "Marie" in _mail.get("html", "") and "Message de ton coach" in _mail.get("html", "")
            and "assuré par Marie" in _mail.get("text", ""))
    verifie("B3b. e-mail : les informations habituelles restent (sujet, cours, heure)",
            _mail.get("subject") == ref_mail[0]["subject"]
            and "Danse Afro" in _mail.get("html", "") and "18:30" in _mail.get("html", ""))
    verifie("B3c. Push : titre inchangé, corps habituel PUIS extrait du message",
            _push.get("titre") == ref_push[0]["titre"]
            and _push.get("corps", "").startswith(ref_push[0]["corps"] + "\n")
            and "Coach Bassi" in _push.get("corps", ""))
    verifie("B3d. Push : données (tag, actions, image) inchangées",
            _push.get("data") == ref_push[0]["data"])
    verifie("B3e. un seul envoi par canal", len(H.PUSHS) == 1 and len(H.EMAILS) == 1)

    # B4 — anti-doublon : second passage, puis MODIFICATION du message.
    await b["cron_reservation_reminders"]()
    verifie("B4. second passage : AUCUN renvoi", len(H.PUSHS) == 1 and len(H.EMAILS) == 1)
    base.courses.docs[0]["message_exceptionnel"]["texte"] = "Texte modifié après envoi"
    await b["cron_reservation_reminders"]()
    verifie("B5. message modifié APRÈS envoi : rien n'est renvoyé",
            len(H.PUSHS) == 1 and len(H.EMAILS) == 1)

    # B6 — modification AVANT envoi : c'est la dernière version qui part.
    b, base = H.bac([copy.deepcopy(r0)], cours_docs=[cours_msg(du=_j, texte="Version 1")])
    base.courses.docs[0]["message_exceptionnel"]["texte"] = "Version 2"
    await b["cron_reservation_reminders"]()
    verifie("B6. message modifié AVANT envoi : la version courante part",
            H.EMAILS and "Version 2" in H.EMAILS[0]["text"] and "Version 1" not in H.EMAILS[0]["text"])

    # B7 — un message posé sur un AUTRE cours ne fuit pas.
    await passage([copy.deepcopy(r0)], [H.cours(cid="c1"), cours_msg(cid="c2", du=_j)])
    verifie("B7. message d'un autre cours : rien n'est ajouté",
            H.PUSHS == ref_push and H.EMAILS and H.EMAILS[0]["text"] == ref_mail[0]["text"])

    # B8 — préférences : e-mail coupé -> le Push seul porte le message.
    await passage([copy.deepcopy(r0)], [cours_msg(du=_j)],
                  prefs=[H.pref(before_class_email=False)])
    verifie("B8. e-mail refusé par le participant : Push seul (avec message)",
            len(H.EMAILS) == 0 and len(H.PUSHS) == 1 and "Coach Bassi" in H.PUSHS[0]["corps"])
    await passage([copy.deepcopy(r0)], [cours_msg(du=_j)],
                  prefs=[H.pref(before_class_push=False)])
    verifie("B8b. Push refusé par le participant : e-mail seul (avec message)",
            len(H.PUSHS) == 0 and len(H.EMAILS) == 1 and "Marie" in H.EMAILS[0]["text"])

    # B9 — rappels DÉSACTIVÉS : le message ne déclenche aucun envoi.
    await passage([copy.deepcopy(r0)], [cours_msg(du=_j, actif=False)])
    verifie("B9. cours sans rappels actifs : AUCUN envoi, même avec message",
            len(H.PUSHS) == 0 and len(H.EMAILS) == 0)

    # B10 — séance hors fenêtre : le message n'avance aucun envoi.
    r_loin = H.resa(decalage_min=600)
    await passage([r_loin], [cours_msg(du=jour_local(r_loin))])
    verifie("B10. séance hors fenêtre : aucun envoi anticipé à cause du message",
            len(H.PUSHS) == 0 and len(H.EMAILS) == 0)

    # B11 — injection HTML.
    await passage([copy.deepcopy(r0)], [cours_msg(du=_j, texte='<img src=x onerror="x">')])
    verifie("B11. HTML du coach neutralisé dans l'e-mail",
            H.EMAILS and "<img" not in H.EMAILS[0]["html"] and "&lt;img" in H.EMAILS[0]["html"])

    # B12 — message abîmé : le rappel part normalement.
    _abime = H.cours()
    _abime["message_exceptionnel"] = "pas un objet"
    await passage([copy.deepcopy(r0)], [_abime])
    verifie("B12. champ abîmé : rappel habituel, sans erreur",
            H.PUSHS == ref_push and len(H.EMAILS) == 1 and H.EMAILS[0]["text"] == ref_mail[0]["text"])

    # B13 — deux réservations, deux cours, un seul porte le message.
    ra = H.resa(rid="ra", email="a@exemple.com", courseId="c1")
    rb = H.resa(rid="rb", email="b@exemple.com", courseId="c2")
    await passage([ra, rb], [cours_msg(cid="c1", du=_j), H.cours(cid="c2")])
    _par = {e["to"][0]: e["text"] for e in H.EMAILS}
    verifie("B13. multi-cours : seul le participant du cours concerné reçoit le message",
            "Marie" in _par.get("a@exemple.com", "") and "Marie" not in _par.get("b@exemple.com", "x"),
            list(_par))


boucle(scenarios_moteur())


# ════════════════════════════════════════════════════════════ C. ROUTES
print("\n--- C : ROUTES RÉELLES (poser / retirer) ---")


def charger_routes():
    b, base = H.bac([], cours_docs=[
        {"id": "c1", "name": "Mercredi", "coach_id": "coach@exemple.com",
         "reminders_enabled": True, "reminder_rules": [{"type": "relative", "minutes": 1440}]},
        {"id": "c9", "name": "Autre", "coach_id": "autre@exemple.com"}])
    b["api_router"] = type("r", (), {k: staticmethod(lambda *a, **kw: (lambda f: f))
                                     for k in ("get", "put", "delete", "post")})
    code = "\n\n".join(H.extraire(n) for n in (
        "_v673_cours_du_coach", "v673_ecrire_message_exceptionnel",
        "v673_retirer_message_exceptionnel"))
    exec(compile(code, "<v673>", "exec"), b)
    return b, base


async def appel(f, *a):
    try:
        return 200, await f(*a)
    except H._HTTP as e:
        return e.status_code, e.detail


async def scenarios_routes():
    b, base = charger_routes()
    H.APPELANT[0] = "coach@exemple.com"
    _dem = (datetime.now(timezone.utc).astimezone(ZH).date() + timedelta(days=1)).isoformat()
    _avant = copy.deepcopy(base.courses.docs[0])

    st, _ = await appel(b["v673_ecrire_message_exceptionnel"], "c1",
                        H._Requete({"texte": MESSAGE, "du": _dem}))
    _doc = base.courses.docs[0]
    verifie("C1. propriétaire : 200 et message enregistré",
            st == 200 and _doc.get("message_exceptionnel", {}).get("texte") == MESSAGE, st)
    verifie("C2. réglages de rappel INTACTS (activation + règles)",
            _doc["reminders_enabled"] == _avant["reminders_enabled"]
            and _doc["reminder_rules"] == _avant["reminder_rules"])
    st, _ = await appel(b["v673_ecrire_message_exceptionnel"], "c1",
                        H._Requete({"texte": "Nouveau", "du": _dem}))
    verifie("C3. modification : le message est remplacé",
            st == 200 and base.courses.docs[0]["message_exceptionnel"]["texte"] == "Nouveau")
    st, _ = await appel(b["v673_ecrire_message_exceptionnel"], "c9",
                        H._Requete({"texte": "x", "du": _dem}))
    verifie("C4. cours d'un autre coach : 403", st == 403, st)
    st, _ = await appel(b["v673_ecrire_message_exceptionnel"], "zz",
                        H._Requete({"texte": "x", "du": _dem}))
    verifie("C5. cours inconnu : 404", st == 404, st)
    st, d = await appel(b["v673_ecrire_message_exceptionnel"], "c1",
                        H._Requete({"texte": "", "du": _dem}))
    verifie("C6. message vide : 400 avec motif lisible", st == 400 and "vide" in d, (st, d))
    st, _ = await appel(b["v673_ecrire_message_exceptionnel"], "c1",
                        H._Requete({"texte": "x", "du": "2020-01-01"}))
    verifie("C7. période passée : 400", st == 400, st)
    verifie("C7b. un refus ne touche pas le message en place",
            base.courses.docs[0]["message_exceptionnel"]["texte"] == "Nouveau")
    st, _ = await appel(b["v673_retirer_message_exceptionnel"], "c9", H._Requete({}))
    verifie("C8. retrait sur le cours d'un autre coach : 403", st == 403, st)
    st, _ = await appel(b["v673_retirer_message_exceptionnel"], "c1", H._Requete({}))
    verifie("C9. retrait : 200 et champ supprimé, règles intactes",
            st == 200 and "message_exceptionnel" not in base.courses.docs[0]
            and base.courses.docs[0]["reminder_rules"] == _avant["reminder_rules"], st)
    H.APPELANT[0] = "admin@exemple.com"
    st, _ = await appel(b["v673_ecrire_message_exceptionnel"], "c9",
                        H._Requete({"texte": "x", "du": _dem}))
    verifie("C10. super-admin : peut poser sur tout cours", st == 200, st)
    H.APPELANT[0] = "coach@exemple.com"


boucle(scenarios_routes())

print("\n--- D : STRUCTURE ---")
_upd = SRC[SRC.find('@api_router.put("/courses/{course_id}")'):]
_upd = _upd[:_upd.find("@api_router", 10)]
verifie("D1. l'édition générique d'un cours ne peut PAS écrire le message",
        '"message_exceptionnel") or _v646_cle.startswith("owner_")' in _upd)
_rem = H.extraire("rv3_ecrire_rappels_du_cours")
verifie("D2. la route des réglages de rappel n'a pas été modifiée par V673",
        "message_exceptionnel" not in _rem and "V673" not in _rem)
verifie("D3. le message n'entre dans aucune clé d'anti-doublon",
        "message" not in H.extraire("n1b2_cle") and "message" not in H.extraire("rv2_reserver_canal"))


# ═════════════════════════════════════════════════════════ E. RV-AB réel
print("\n--- E : ABONNÉS SANS RÉSERVATION (passage RV-AB réel) ---")
import api.server as S                                    # noqa: E402

_ENVOIS, _PUSHS = [], []


class _Coll(H._Coll):
    async def insert_one(self, d):
        await asyncio.sleep(0)
        if any(x.get("_id") == d.get("_id") for x in self.docs):
            raise RuntimeError("E11000 doublon")
        self.docs.append(copy.deepcopy(d))

    async def delete_one(self, q):
        await asyncio.sleep(0)
        self.docs = [x for x in self.docs if not H._match(x, q)]


class _DB:
    def __init__(self, cours):
        self.courses = _Coll(cours)
        self.subscriptions = _Coll([{"id": "s1", "email": "abo@exemple.com", "status": "active",
                                     "remaining_sessions": 5, "offer_id": "o1",
                                     "offer_name": "Unité", "code": "AFR-TEST01"}])
        self.reservations = _Coll([])
        self.reminder_sends = _Coll([])

    def __getitem__(self, k):
        return getattr(self, k)


async def rvab(cours, maintenant, instant):
    _ENVOIS[:] = []
    _PUSHS[:] = []
    sauv = {k: getattr(S, k) for k in ("db", "get_feature_flags", "rv2_envoyer_email_rappel",
                                       "send_push_by_email", "rv2_canal_autorise",
                                       "_v426_offre_de_labonnement", "_v259_primary_color")}
    try:
        S.db = _DB(cours)

        async def _flags():
            return {"REMINDERS_SUBSCRIBERS_ENABLED": True, "REMINDERS_SUBSCRIBERS_DRY_RUN": False}

        async def _mail(*a, **kw):
            _ENVOIS.append((a, kw))
            return True

        async def _push(email, titre, corps, data=None):
            _PUSHS.append(corps)
            return True

        async def _oui(*a, **k):
            return True

        async def _offre(*a, **k):
            return {"linked_course_ids": ["c1"]}

        async def _couleur(*a, **k):
            return "#D91CD2"
        S.get_feature_flags, S.rv2_envoyer_email_rappel = _flags, _mail
        S.send_push_by_email, S.rv2_canal_autorise = _push, _oui
        S._v426_offre_de_labonnement, S._v259_primary_color = _offre, _couleur

        def _inst(v):
            try:
                d = datetime.fromisoformat(str(v))
            except ValueError:
                return None
            return (d if d.tzinfo else d.replace(tzinfo=ZH)).astimezone(timezone.utc)

        async def _vendus():
            return {"c1"}
        return await S._rvab_passage(maintenant, ZH, timedelta(minutes=30),
                                     maintenant + timedelta(minutes=2910), _inst, _vendus, 4)
    finally:
        for k, v in sauv.items():
            setattr(S, k, v)


async def scenarios_rvab():
    # Mercredi 25/11/2026 18:30 (weekday JS : mercredi = 3) ; règle « 24 h avant ».
    instant = datetime(2026, 11, 25, 18, 30, tzinfo=ZH).astimezone(timezone.utc)
    maintenant = instant - timedelta(minutes=1440)
    base_c = {"id": "c1", "name": "Mercredi Afro", "weekday": 3, "time": "18:30",
              "reminders_enabled": True, "archived": False,
              "reminder_rules": [{"type": "relative", "minutes": 1440}]}
    r = await rvab([dict(base_c)], maintenant, instant)
    verifie("E1. sans message : l'abonné reçoit le rappel habituel",
            len(_ENVOIS) == 1 and "message_coach" not in _ENVOIS[0][1] and len(_PUSHS) == 1
            and "\n" not in _PUSHS[0], (r, _ENVOIS))
    avec = dict(base_c, message_exceptionnel={"texte": "Marie remplace Bassi",
                                              "du": "2026-11-25", "au": "2026-11-25"})
    await rvab([avec], maintenant, instant)
    verifie("E2. avec message dans la période : e-mail + Push le portent",
            len(_ENVOIS) == 1 and _ENVOIS[0][1].get("message_coach") == "Marie remplace Bassi"
            and len(_PUSHS) == 1 and _PUSHS[0].endswith("\nMarie remplace Bassi"), (_ENVOIS, _PUSHS))
    hors = dict(base_c, message_exceptionnel={"texte": "x", "du": "2026-11-29", "au": "2026-11-29"})
    await rvab([hors], maintenant, instant)
    verifie("E3. message pour une autre date : rappel habituel",
            len(_ENVOIS) == 1 and "message_coach" not in _ENVOIS[0][1])


boucle(scenarios_rvab())

# Rendu réel du gabarit « non réservé » avec message
_s, _h, _t = S.rv2_contenu_rappel_non_reserve("Awa", "Mercredi Afro", "mercredi 25 novembre",
                                              "18:30", "#D91CD2", message_coach="Marie <b>")
_s0, _h0, _t0 = S.rv2_contenu_rappel_non_reserve("Awa", "Mercredi Afro", "mercredi 25 novembre",
                                                 "18:30", "#D91CD2")
verifie("E4. gabarit abonné : message échappé présent, sujet inchangé",
        "Marie &lt;b&gt;" in _h and "Marie <b>" in _t and _s == _s0)
verifie("E5. gabarit abonné sans message : identique à l'appel d'avant V673",
        (_s0, _h0, _t0) == S.rv2_contenu_rappel_non_reserve(
            "Awa", "Mercredi Afro", "mercredi 25 novembre", "18:30", "#D91CD2", message_coach=""))

print("\n%d PASS · %d FAIL" % (_ok, _ko))
print("E-mails / Push RÉELS : 0 — envoyeurs simulés, base en mémoire")
sys.exit(1 if _ko else 0)
