"""
Test des liaisons IA (soudures) entre l'agent IA et les canaux d'envoi
- sendAIResponseViaEmail: Liaison IA -> EmailJS
- sendAIResponseViaWhatsApp: Liaison IA -> WhatsApp (Twilio/webhook)
- dispatchAIResponse: Routeur unifié pour l'agent IA
- Backend /api/send-whatsapp endpoint
"""
import pytest
import requests
import os
import re

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# === FRONTEND CODE ANALYSIS TESTS ===

class TestIALiaisonsExistence:
    """Vérifier que les fonctions de liaison IA existent dans messagingGateway.js"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Load the messagingGateway.js file content"""
        with open('/app/frontend/src/services/messagingGateway.js', 'r') as f:
            self.gateway_content = f.read()
        with open('/app/frontend/src/services/index.js', 'r') as f:
            self.index_content = f.read()
    
    def test_sendAIResponseViaEmail_exists(self):
        """sendAIResponseViaEmail function must exist"""
        assert 'export const sendAIResponseViaEmail' in self.gateway_content, \
            "sendAIResponseViaEmail function not found in messagingGateway.js"
    
    def test_sendAIResponseViaWhatsApp_exists(self):
        """sendAIResponseViaWhatsApp function must exist"""
        assert 'export const sendAIResponseViaWhatsApp' in self.gateway_content, \
            "sendAIResponseViaWhatsApp function not found in messagingGateway.js"
    
    def test_dispatchAIResponse_exists(self):
        """dispatchAIResponse function must exist"""
        assert 'export const dispatchAIResponse' in self.gateway_content, \
            "dispatchAIResponse function not found in messagingGateway.js"


class TestEmailJSConfiguration:
    """Vérifier que les IDs EmailJS sont corrects"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        with open('/app/frontend/src/services/messagingGateway.js', 'r') as f:
            self.content = f.read()
    
    def test_emailjs_service_id(self):
        """EmailJS Service ID must be service_8mrmxim"""
        assert 'EMAILJS_SERVICE_ID = "service_8mrmxim"' in self.content, \
            "EmailJS Service ID incorrect or not found"
    
    def test_emailjs_template_id(self):
        """EmailJS Template ID must be template_3n1u86p"""
        assert 'EMAILJS_TEMPLATE_ID = "template_3n1u86p"' in self.content, \
            "EmailJS Template ID incorrect or not found"
    
    def test_emailjs_public_key(self):
        """EmailJS Public Key must be 5LfgQSIEQoqq_XSqt"""
        assert 'EMAILJS_PUBLIC_KEY = "5LfgQSIEQoqq_XSqt"' in self.content, \
            "EmailJS Public Key incorrect or not found"
    
    def test_sendAIResponseViaEmail_uses_emailjs_send(self):
        """sendAIResponseViaEmail must use emailjs.send()"""
        # Find the sendAIResponseViaEmail function and check it uses emailjs.send
        pattern = r'sendAIResponseViaEmail.*?emailjs\.send\('
        match = re.search(pattern, self.content, re.DOTALL)
        assert match is not None, "sendAIResponseViaEmail does not use emailjs.send()"


class TestConsoleLogMessages:
    """Vérifier les messages console.log pour le tracking IA"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        with open('/app/frontend/src/services/messagingGateway.js', 'r') as f:
            self.content = f.read()
    
    def test_email_success_log(self):
        """Console log 'IA : Message envoyé via EmailJS' must exist"""
        assert "console.log('IA : Message envoyé via EmailJS')" in self.content, \
            "Console log for EmailJS success not found"
    
    def test_whatsapp_success_log_twilio(self):
        """Console log 'IA : Message envoyé via WhatsApp (Twilio)' must exist"""
        assert "console.log('IA : Message envoyé via WhatsApp (Twilio)')" in self.content, \
            "Console log for WhatsApp Twilio success not found"
    
    def test_whatsapp_success_log_webhook(self):
        """Console log 'IA : Message envoyé via WhatsApp (webhook)' must exist"""
        assert "console.log('IA : Message envoyé via WhatsApp (webhook)')" in self.content, \
            "Console log for WhatsApp webhook success not found"


class TestPostHogBypass:
    """Vérifier le bypass PostHog/DataCloneError"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        with open('/app/frontend/src/services/messagingGateway.js', 'r') as f:
            self.content = f.read()
    
    def test_datacloneerror_check_in_email(self):
        """sendAIResponseViaEmail must check for DataCloneError"""
        # Check that DataCloneError is handled
        assert "DataCloneError" in self.content, \
            "DataCloneError handling not found in messagingGateway.js"
    
    def test_try_catch_in_sendAIResponseViaEmail(self):
        """sendAIResponseViaEmail must have try/catch block"""
        # Find the function and verify it has try/catch
        pattern = r'sendAIResponseViaEmail\s*=\s*async.*?try\s*\{'
        match = re.search(pattern, self.content, re.DOTALL)
        assert match is not None, "sendAIResponseViaEmail does not have try/catch block"
    
    def test_try_catch_in_sendAIResponseViaWhatsApp(self):
        """sendAIResponseViaWhatsApp must have try/catch block"""
        pattern = r'sendAIResponseViaWhatsApp\s*=\s*async.*?try\s*\{'
        match = re.search(pattern, self.content, re.DOTALL)
        assert match is not None, "sendAIResponseViaWhatsApp does not have try/catch block"
    
    def test_posthog_bypass_comment(self):
        """BYPASS CRASH POSTHOG comment must exist"""
        assert "BYPASS CRASH POSTHOG" in self.content or "bypass PostHog" in self.content.lower(), \
            "PostHog bypass comment not found"
    
    def test_datacloneerror_specific_check(self):
        """Must check error.name === 'DataCloneError'"""
        assert "error.name === 'DataCloneError'" in self.content, \
            "Specific DataCloneError name check not found"


class TestWhatsAppSimulationMode:
    """Vérifier le mode simulation WhatsApp"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        with open('/app/frontend/src/services/messagingGateway.js', 'r') as f:
            self.content = f.read()
    
    def test_simulation_mode_exists(self):
        """WhatsApp simulation mode must exist"""
        assert "Mode simulation" in self.content or "simulated: true" in self.content, \
            "WhatsApp simulation mode not found"
    
    def test_simulation_returns_success(self):
        """Simulation mode must return success: true"""
        # Check that simulation returns success
        pattern = r'simulated:\s*true.*?success:\s*true|success:\s*true.*?simulated:\s*true'
        match = re.search(pattern, self.content, re.DOTALL)
        assert match is not None or "success: true" in self.content, \
            "Simulation mode does not return success: true"


class TestDispatchAIResponse:
    """Vérifier le routeur dispatchAIResponse"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        with open('/app/frontend/src/services/messagingGateway.js', 'r') as f:
            self.content = f.read()
    
    def test_dispatch_routes_to_email(self):
        """dispatchAIResponse must route to sendAIResponseViaEmail for email channel"""
        # Check that dispatch calls sendAIResponseViaEmail when channel is email
        pattern = r"channel\s*===\s*['\"]email['\"].*?sendAIResponseViaEmail"
        match = re.search(pattern, self.content, re.DOTALL)
        assert match is not None, "dispatchAIResponse does not route to sendAIResponseViaEmail"
    
    def test_dispatch_routes_to_whatsapp(self):
        """dispatchAIResponse must route to sendAIResponseViaWhatsApp for whatsapp channel"""
        pattern = r"channel\s*===\s*['\"]whatsapp['\"].*?sendAIResponseViaWhatsApp"
        match = re.search(pattern, self.content, re.DOTALL)
        assert match is not None, "dispatchAIResponse does not route to sendAIResponseViaWhatsApp"


class TestIndexExports:
    """Vérifier que index.js exporte les nouvelles fonctions de liaison IA"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        with open('/app/frontend/src/services/index.js', 'r') as f:
            self.content = f.read()
    
    def test_export_sendAIResponseViaEmail(self):
        """index.js must export sendAIResponseViaEmail"""
        assert "sendAIResponseViaEmail" in self.content, \
            "sendAIResponseViaEmail not exported from index.js"
    
    def test_export_sendAIResponseViaWhatsApp(self):
        """index.js must export sendAIResponseViaWhatsApp"""
        assert "sendAIResponseViaWhatsApp" in self.content, \
            "sendAIResponseViaWhatsApp not exported from index.js"
    
    def test_export_dispatchAIResponse(self):
        """index.js must export dispatchAIResponse"""
        assert "dispatchAIResponse" in self.content, \
            "dispatchAIResponse not exported from index.js"
    
    def test_exports_from_messagingGateway(self):
        """Exports must come from messagingGateway.js"""
        assert "from './messagingGateway'" in self.content, \
            "Exports not from messagingGateway.js"


# === BACKEND API TESTS ===

class TestBackendSendWhatsAppEndpoint:
    """Tester l'endpoint backend POST /api/send-whatsapp — 100 % HORS LIGNE.

    V442-TESTS — CETTE CLASSE ENVOYAIT 4 VRAIS WHATSAPP.
    Elle faisait quatre `requests.post()` sur `{BASE_URL}/api/send-whatsapp` avec
    un corps VALIDE (`{"to": "+41791234567", "message": "..."}`). Lancée contre la
    production, elle expédiait donc quatre messages réels depuis le numéro
    business d'Afroboost — facturés au compte, comptés dans la note de qualité
    Meta, et potentiellement vus par le titulaire du numéro composé.

    Elle est désormais entièrement hors ligne : plus aucun `requests`, plus aucune
    URL. On teste le VRAI code du handler, extrait de `api/server.py` par analyse
    AST et exécuté tel quel, avec le moteur d'envoi remplacé par un mouchard qui
    enregistre l'appel au lieu de l'émettre. Le harnais est celui de
    `test_v442_send_whatsapp_auth.py` — on ne le duplique pas.

    L'assertion `status_code == 200` de `test_endpoint_returns_simulated_without_config`
    est devenue FAUSSE avec V442 (la route exige un JWT super-admin signé). Elle
    n'est pas « rafraîchie » avec un appel authentifié réel — ce serait remplacer
    un envoi par un autre envoi. Elle est remplacée par la vérification du
    comportement voulu : anonyme -> refus.
    """

    @pytest.fixture(autouse=True)
    def setup(self):
        import sys, os as _os
        _tests = _os.path.dirname(_os.path.abspath(__file__))
        if _tests not in sys.path:
            sys.path.insert(0, _tests)
        import test_v442_send_whatsapp_auth as h
        self.h = h
        self.bac = h.construire()
        h.ENVOIS.clear()

    def _appeler(self, headers, to="+41791234567", message="Test message", media=None):
        """Renvoie ('ok', resultat) ou ('refus', code). Aucun reseau."""
        import asyncio
        async def run():
            return await self.bac["send_whatsapp_message"](
                self.h.Payload(to, message, media), self.h.FausseRequete(headers))
        try:
            return ("ok", asyncio.get_event_loop().run_until_complete(run()))
        except self.h.HTTPException as e:
            return ("refus", e.status_code)

    def _bearer(self, email=None, **kw):
        return {"Authorization": "Bearer " + self.h.jeton(email or self.h.ADMIN, **kw)}

    # --- la route existe toujours (verification structurelle, sans reseau) ---
    def test_endpoint_exists(self):
        """POST /api/send-whatsapp endpoint must exist"""
        assert '@api_router.post("/send-whatsapp")' in self.h.SOURCE, \
            "/api/send-whatsapp endpoint not defined in api/server.py"
        assert callable(self.bac.get("send_whatsapp_message")), \
            "le handler send_whatsapp_message est introuvable"

    # --- ANONYME -> REFUS (remplace l'assertion 200 devenue obsolete) ---
    def test_anonymous_is_refused(self):
        """V442 : sans authentification, la route doit REFUSER — et ne rien envoyer."""
        etat, code = self._appeler({})
        assert etat == "refus" and code == 403, \
            f"Un appel anonyme aurait du etre refuse en 403, obtenu {etat} {code}"
        assert self.h.ENVOIS == [], "Un envoi a ete declenche par un appel anonyme"

    # --- AUTH INVALIDE -> REFUS ---
    @pytest.mark.parametrize("nom,headers", [
        ("X-User-Email forge",      {"X-User-Email": "contact.artboost@gmail.com"}),
        ("JWT d'un autre secret",   None),
        ("jeton illisible",         {"Authorization": "Bearer pas-un-jwt"}),
        ("Bearer vide",             {"Authorization": "Bearer "}),
        ("coach non super-admin",   "coach"),
        ("jeton abonne",            "subscriber"),
        ("JWT expire",              "expire"),
    ])
    def test_invalid_auth_is_refused(self, nom, headers):
        """V442 : toute identite non prouvee doit REFUSER — et ne rien envoyer."""
        if headers is None:
            headers = {"Authorization": "Bearer " + self.h.jeton(self.h.ADMIN, secret="mauvais")}
        elif headers == "coach":
            headers = self._bearer(self.h.COACH)
        elif headers == "subscriber":
            headers = self._bearer(self.h.ADMIN, type_="subscriber")
        elif headers == "expire":
            headers = self._bearer(self.h.ADMIN, exp=1)
        etat, code = self._appeler(headers)
        assert etat == "refus" and code == 403, f"{nom} : attendu 403, obtenu {etat} {code}"
        assert self.h.ENVOIS == [], f"{nom} : un envoi a ete declenche"

    # --- AUTH LEGITIME -> CHEMIN AUTORISE, SANS ENVOI REEL ---
    def test_legitimate_auth_reaches_engine_without_sending(self):
        """V442 : le super-admin signe passe. Le moteur est ATTEINT, jamais Meta.

        C'est la contrepartie exigee par la regle V310c du projet : ne jamais
        durcir une auth sans prouver que le chemin legitime marche encore.
        """
        etat, res = self._appeler(self._bearer())
        assert etat == "ok", f"Le super-admin legitime a ete refuse : {etat} {res}"
        assert len(self.h.ENVOIS) == 1, "Le moteur d'envoi n'a pas ete atteint"
        assert self.h.ENVOIS[0]["to_phone"] == "+41791234567"
        # Le mouchard prouve qu'aucun appel reseau n'a eu lieu : c'est LUI qui a
        # repondu, pas Meta.
        assert res.get("status") == "simulated-par-le-test", \
            "La reponse ne vient pas du mouchard — un vrai envoi a pu partir"

    def test_endpoint_accepts_required_fields(self):
        """Endpoint must accept 'to' and 'message' fields (sans reseau)."""
        etat, _ = self._appeler(self._bearer(), to="+41791234567", message="Test message from IA")
        assert etat == "ok", "Le handler a rejete un couple (to, message) valide"
        assert self.h.ENVOIS[0]["message"] == "Test message from IA", \
            "Le message n'est pas transmis tel quel au moteur"

    def test_endpoint_accepts_mediaUrl(self):
        """Endpoint must accept optional 'mediaUrl' field (sans reseau)."""
        etat, _ = self._appeler(self._bearer(), media="https://example.com/image.jpg")
        assert etat == "ok", "Le handler a rejete un mediaUrl valide"
        assert self.h.ENVOIS[0]["media_url"] == "https://example.com/image.jpg", \
            "Le mediaUrl n'est pas transmis tel quel au moteur"

    def test_no_test_of_this_class_uses_the_network(self):
        """Garde-fou : cette classe ne doit plus JAMAIS refaire d'appel reseau."""
        import ast, inspect
        src = inspect.getsource(TestBackendSendWhatsAppEndpoint)
        arbre = ast.parse("class _X:\n" + "\n".join(
            "    " + l for l in src.splitlines()[1:]))
        appels = [ast.unparse(n) for n in ast.walk(arbre)
                  if isinstance(n, ast.Call) and ast.unparse(n).startswith(
                      ("requests.", "httpx.", "urllib.", "fetch("))]
        assert appels == [], f"Appel reseau reintroduit dans les tests : {appels}"


class TestBackendHealthCheck:
    """Vérifier que le backend est accessible"""
    
    def test_health_endpoint(self):
        """Health endpoint must return 200"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200, \
            f"Health check failed with status {response.status_code}"


# === BACKEND CODE ANALYSIS ===

class TestBackendSendWhatsAppCode:
    """Analyser le code backend pour /api/send-whatsapp"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        with open('/app/backend/server.py', 'r') as f:
            self.content = f.read()
    
    def test_endpoint_defined(self):
        """@api_router.post('/send-whatsapp') must be defined"""
        assert '@api_router.post("/send-whatsapp")' in self.content, \
            "/api/send-whatsapp endpoint not defined in server.py"
    
    def test_uses_twilio_config_from_db(self):
        """Endpoint must use Twilio config from database"""
        assert "whatsapp_config" in self.content, \
            "Endpoint does not use whatsapp_config from database"
    
    def test_simulation_mode_when_no_config(self):
        """Endpoint must return simulated when no config"""
        assert '"simulated"' in self.content or "'simulated'" in self.content, \
            "Simulation mode not implemented in backend"
    
    def test_console_log_ia_message(self):
        """Backend must log 'IA : Message envoyé via WhatsApp'"""
        assert "IA : Message envoyé via WhatsApp" in self.content or \
               "IA : Envoi WhatsApp" in self.content, \
            "IA WhatsApp log message not found in backend"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
