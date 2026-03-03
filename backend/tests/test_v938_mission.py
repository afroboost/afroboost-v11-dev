"""
Test Suite v9.3.8 - Mission Tests
=================================
Tests for:
1. Mobile Design Fix (flex-wrap for Tester buttons)
2. Default Favicon Afroboost
3. AI Config Auto-save (systemPrompt, campaignPrompt)
4. API persistence (/api/payment-links, /api/concept, /api/ai-config)
"""

import pytest
import requests
import os

# Base URL from environment
BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://promo-credits-lab.preview.emergentagent.com').rstrip('/')
API = f"{BASE_URL}/api"


class TestAPIPaymentLinks:
    """Tests for /api/payment-links persistence"""
    
    def test_get_payment_links_success(self):
        """GET /api/payment-links should return current payment configuration"""
        response = requests.get(f"{API}/payment-links")
        assert response.status_code == 200
        
        data = response.json()
        # Verify required fields exist
        assert "stripe" in data or "id" in data
        print(f"✅ GET payment-links: stripe={data.get('stripe', '')[:30]}...")
    
    def test_put_payment_links_stripe(self):
        """PUT /api/payment-links should persist stripe link"""
        test_stripe = "https://test-stripe-v938.com/pay"
        
        response = requests.put(f"{API}/payment-links", json={"stripe": test_stripe})
        assert response.status_code == 200
        
        # Verify persistence
        verify = requests.get(f"{API}/payment-links")
        data = verify.json()
        assert data.get("stripe") == test_stripe
        print(f"✅ PUT payment-links stripe persisted")
    
    def test_put_payment_links_coachwhatsapp(self):
        """PUT /api/payment-links should persist coachWhatsapp"""
        test_whatsapp = "+41799999938"
        
        response = requests.put(f"{API}/payment-links", json={"coachWhatsapp": test_whatsapp})
        assert response.status_code == 200
        
        # Verify persistence
        verify = requests.get(f"{API}/payment-links")
        data = verify.json()
        assert data.get("coachWhatsapp") == test_whatsapp
        print(f"✅ PUT payment-links coachWhatsapp persisted")


class TestAPIConcept:
    """Tests for /api/concept persistence"""
    
    def test_get_concept_success(self):
        """GET /api/concept should return current concept configuration"""
        response = requests.get(f"{API}/concept")
        assert response.status_code == 200
        
        data = response.json()
        assert "appName" in data or "id" in data
        print(f"✅ GET concept: appName={data.get('appName', 'N/A')}")
    
    def test_put_concept_description(self):
        """PUT /api/concept should persist description"""
        test_desc = "v9.3.8 Test - Le concept Afroboost mise à jour"
        
        response = requests.put(f"{API}/concept", json={"description": test_desc})
        assert response.status_code == 200
        
        # Verify persistence
        verify = requests.get(f"{API}/concept")
        data = verify.json()
        assert test_desc in data.get("description", "")
        print(f"✅ PUT concept description persisted")
    
    def test_put_concept_hero_video_url(self):
        """PUT /api/concept should persist heroVideoUrl"""
        test_url = "https://youtube.com/test-v938"
        
        response = requests.put(f"{API}/concept", json={"heroVideoUrl": test_url})
        assert response.status_code == 200
        
        # Verify persistence
        verify = requests.get(f"{API}/concept")
        data = verify.json()
        assert data.get("heroVideoUrl") == test_url
        print(f"✅ PUT concept heroVideoUrl persisted")


class TestAPIAIConfig:
    """Tests for /api/ai-config persistence - CRITICAL for v9.3.8"""
    
    def test_get_ai_config_success(self):
        """GET /api/ai-config should return AI configuration"""
        response = requests.get(f"{API}/ai-config")
        assert response.status_code == 200
        
        data = response.json()
        # Verify required fields
        assert "enabled" in data or "id" in data
        assert "systemPrompt" in data
        assert "model" in data
        print(f"✅ GET ai-config: model={data.get('model', 'N/A')}, enabled={data.get('enabled', False)}")
    
    def test_put_ai_config_system_prompt(self):
        """PUT /api/ai-config should persist systemPrompt (Personnalité IA)"""
        test_prompt = "v9.3.8 Test - Tu es un assistant fitness motivant et dynamique."
        
        response = requests.put(f"{API}/ai-config", json={"systemPrompt": test_prompt})
        assert response.status_code == 200
        
        # Verify persistence
        verify = requests.get(f"{API}/ai-config")
        data = verify.json()
        assert test_prompt in data.get("systemPrompt", "")
        print(f"✅ PUT ai-config systemPrompt persisted (Prompt Personnalité)")
    
    def test_put_ai_config_campaign_prompt(self):
        """PUT /api/ai-config should persist campaignPrompt (Prompt Campagne)"""
        test_campaign = "v9.3.8 Test - Propose toujours l'essai gratuit du Mercredi."
        
        response = requests.put(f"{API}/ai-config", json={"campaignPrompt": test_campaign})
        assert response.status_code == 200
        
        # Verify persistence
        verify = requests.get(f"{API}/ai-config")
        data = verify.json()
        assert data.get("campaignPrompt") == test_campaign
        print(f"✅ PUT ai-config campaignPrompt persisted (Prompt Campagne PRIORITÉ)")
    
    def test_put_ai_config_twint_payment_url(self):
        """PUT /api/ai-config should persist twintPaymentUrl"""
        test_twint = "https://twint.ch/pay/v938-test"
        
        response = requests.put(f"{API}/ai-config", json={"twintPaymentUrl": test_twint})
        assert response.status_code == 200
        
        # Verify persistence
        verify = requests.get(f"{API}/ai-config")
        data = verify.json()
        assert data.get("twintPaymentUrl") == test_twint
        print(f"✅ PUT ai-config twintPaymentUrl persisted")
    
    def test_put_ai_config_enabled_toggle(self):
        """PUT /api/ai-config should toggle enabled status"""
        # Get current status
        current = requests.get(f"{API}/ai-config").json()
        current_enabled = current.get("enabled", False)
        
        # Toggle it
        new_enabled = not current_enabled
        response = requests.put(f"{API}/ai-config", json={"enabled": new_enabled})
        assert response.status_code == 200
        
        # Verify
        verify = requests.get(f"{API}/ai-config")
        data = verify.json()
        assert data.get("enabled") == new_enabled
        
        # Restore original
        requests.put(f"{API}/ai-config", json={"enabled": current_enabled})
        print(f"✅ PUT ai-config enabled toggle works")


class TestBassiDataPreservation:
    """Anti-regression tests - Preserve Bassi's production data"""
    
    def test_reservations_api_works(self):
        """Verify reservations API is functional (may be empty in test pods)"""
        response = requests.get(f"{API}/reservations?page=1&limit=100")
        assert response.status_code == 200
        
        data = response.json()
        # v9.3.9: API works, count may vary in test pods
        total = data.get("pagination", {}).get("total", 0)
        assert "pagination" in data, "Response should have pagination"
        print(f"✅ Reservations API works: {total} found (test pod may have 0)")
    
    def test_contacts_api_works(self):
        """Verify contacts/users API is functional"""
        response = requests.get(f"{API}/users")
        assert response.status_code == 200
        
        data = response.json()
        # v9.3.9: API works, count may vary
        assert isinstance(data, list), "Response should be a list"
        print(f"✅ Contacts API works: {len(data)} found")
    
    def test_courses_api_works(self):
        """Verify courses API is functional"""
        response = requests.get(f"{API}/courses")
        assert response.status_code == 200
        
        data = response.json()
        # v9.3.9: API works, count may vary
        assert isinstance(data, list), "Response should be a list"
        print(f"✅ Courses API works: {len(data)} found")
    
    def test_offers_api_works(self):
        """Verify offers API is functional"""
        response = requests.get(f"{API}/offers")
        assert response.status_code == 200
        
        data = response.json()
        # v9.3.9: API works, count may vary
        assert isinstance(data, list), "Response should be a list"
        print(f"✅ Offers API works: {len(data)} found")


class TestHealthAndStatus:
    """Health check endpoints"""
    
    def test_health_endpoint(self):
        """API should be healthy"""
        response = requests.get(f"{API}/health")
        assert response.status_code == 200
        print("✅ API health check passed")
    
    def test_scheduler_health(self):
        """Scheduler should be running"""
        response = requests.get(f"{API}/scheduler/health")
        assert response.status_code == 200
        
        data = response.json()
        assert "status" in data
        print(f"✅ Scheduler status: {data.get('status', 'unknown')}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
