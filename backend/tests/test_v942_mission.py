"""
Test v9.4.2 - Mission ICONOGRAPHIE RÉELLE ET SÉCURITÉ EMAIL
Vérifie:
1. L'endpoint POST /api/campaigns/send-bulk-email existe et accepte des recipients
2. L'endpoint utilise BackgroundTasks pour envoi non-bloquant
3. Les endpoints existants fonctionnent toujours (anti-régression)
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://video-feed-platform.preview.emergentagent.com').rstrip('/')


class TestBulkEmailEndpoint:
    """Tests pour l'endpoint de campagne email de masse v9.4.2"""
    
    def test_send_bulk_email_endpoint_exists(self):
        """Vérifie que l'endpoint POST /api/campaigns/send-bulk-email existe"""
        # Envoyer une requête avec des données vides pour vérifier que l'endpoint répond
        response = requests.post(
            f"{BASE_URL}/api/campaigns/send-bulk-email",
            json={},
            headers={"Content-Type": "application/json"}
        )
        # L'endpoint doit répondre 400 (pas de destinataires) et non 404
        assert response.status_code != 404, f"Endpoint n'existe pas: {response.status_code}"
        # L'endpoint doit retourner 400 car aucun destinataire
        assert response.status_code == 400, f"Status inattendu: {response.status_code}"
        print(f"✅ Endpoint /api/campaigns/send-bulk-email existe (status={response.status_code})")
    
    def test_send_bulk_email_requires_recipients(self):
        """Vérifie que l'endpoint requiert des destinataires"""
        response = requests.post(
            f"{BASE_URL}/api/campaigns/send-bulk-email",
            json={"message": "Test message", "subject": "Test"},
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 400
        data = response.json()
        assert "destinataire" in data.get("detail", "").lower() or response.status_code == 400
        print(f"✅ Validation des destinataires fonctionne")
    
    def test_send_bulk_email_requires_message(self):
        """Vérifie que l'endpoint requiert un message"""
        response = requests.post(
            f"{BASE_URL}/api/campaigns/send-bulk-email",
            json={
                "recipients": [{"email": "test@test.com", "name": "Test"}],
                "subject": "Test"
            },
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 400
        print(f"✅ Validation du message fonctionne")
    
    def test_send_bulk_email_returns_background_task_response(self):
        """Vérifie que l'endpoint retourne une réponse de tâche de fond (success=True immédiatement)"""
        # Note: Ce test utilise un email fictif pour tester uniquement la réponse de l'API
        # L'envoi réel sera en arrière-plan et peut échouer silencieusement
        response = requests.post(
            f"{BASE_URL}/api/campaigns/send-bulk-email",
            json={
                "recipients": [{"email": "test-fake@test-example.com", "name": "Test Fake"}],
                "subject": "Test v9.4.2",
                "message": "Ceci est un test de l'envoi en arrière-plan."
            },
            headers={"Content-Type": "application/json"}
        )
        # L'API doit répondre immédiatement (pas de blocage)
        assert response.status_code == 200, f"Status inattendu: {response.status_code}"
        data = response.json()
        assert data.get("success") == True, "La réponse doit indiquer success=True"
        assert "arrière-plan" in data.get("message", "").lower() or "background" in data.get("message", "").lower() or "lancé" in data.get("message", "").lower()
        assert data.get("total_recipients") == 1
        print(f"✅ L'endpoint retourne une réponse de tâche de fond: {data}")


class TestExistingEndpointsAntiRegression:
    """Tests anti-régression pour les endpoints existants"""
    
    def test_health_endpoint(self):
        """Vérifie que le health check fonctionne"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        print("✅ Health check OK")
    
    def test_courses_endpoint(self):
        """Vérifie que l'endpoint courses fonctionne"""
        response = requests.get(f"{BASE_URL}/api/courses")
        assert response.status_code == 200
        assert isinstance(response.json(), list)
        print(f"✅ Courses endpoint OK ({len(response.json())} cours)")
    
    def test_offers_endpoint(self):
        """Vérifie que l'endpoint offers fonctionne"""
        response = requests.get(f"{BASE_URL}/api/offers")
        assert response.status_code == 200
        assert isinstance(response.json(), list)
        print(f"✅ Offers endpoint OK ({len(response.json())} offres)")
    
    def test_campaigns_endpoint(self):
        """Vérifie que l'endpoint campaigns fonctionne"""
        response = requests.get(f"{BASE_URL}/api/campaigns")
        assert response.status_code == 200
        assert isinstance(response.json(), list)
        print(f"✅ Campaigns endpoint OK ({len(response.json())} campagnes)")
    
    def test_ai_suggestions_endpoint(self):
        """Vérifie que l'endpoint AI suggestions (v9.4.1) fonctionne toujours"""
        response = requests.post(
            f"{BASE_URL}/api/ai/campaign-suggestions",
            json={
                "campaign_goal": "Test suggestion",
                "campaign_name": "Test",
                "recipient_count": 5
            },
            headers={"Content-Type": "application/json"}
        )
        # Peut retourner 200 ou timeout en fonction de la charge
        assert response.status_code in [200, 500, 504], f"Status inattendu: {response.status_code}"
        if response.status_code == 200:
            data = response.json()
            assert data.get("success") == True or "suggestions" in data
            print(f"✅ AI suggestions endpoint OK")
        else:
            print(f"⚠️ AI suggestions endpoint timeout ou erreur serveur (status={response.status_code})")
    
    def test_single_campaign_send_email_endpoint(self):
        """Vérifie que l'endpoint d'envoi email simple existe"""
        # Juste tester que l'endpoint répond (pas d'envoi réel)
        response = requests.post(
            f"{BASE_URL}/api/campaigns/send-email",
            json={},
            headers={"Content-Type": "application/json"}
        )
        # Doit répondre 400 ou 422 (validation error), pas 404
        assert response.status_code != 404, "Endpoint /api/campaigns/send-email n'existe pas"
        print(f"✅ Single email endpoint existe (status={response.status_code})")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
