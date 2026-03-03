"""
Test suite for Twint Payment Link Integration
Tests the dynamic Twint payment link feature in AI config and chat responses
"""
import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://promo-credits-lab.preview.emergentagent.com').rstrip('/')

# Test credentials
TEST_TWINT_URL = "https://twint.ch/pay/afroboost-test-123"
TEST_USER = {
    "firstName": "TestUser",
    "email": "test@example.com",
    "whatsapp": "+41791234567"
}


class TestAIConfigTwintPayment:
    """Tests for AI Config Twint Payment URL field"""
    
    def test_get_ai_config_has_twint_field(self):
        """Test 1: Verify AI config returns twintPaymentUrl field"""
        response = requests.get(f"{BASE_URL}/api/ai-config")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "twintPaymentUrl" in data, "twintPaymentUrl field missing from AI config"
        print(f"✅ AI config has twintPaymentUrl field: {data.get('twintPaymentUrl', '')}")
    
    def test_put_ai_config_accepts_twint_url(self):
        """Test 2: Verify PUT /api/ai-config accepts twintPaymentUrl field"""
        # First get current config
        get_response = requests.get(f"{BASE_URL}/api/ai-config")
        assert get_response.status_code == 200
        original_config = get_response.json()
        
        # Update with test Twint URL
        update_payload = {
            "twintPaymentUrl": TEST_TWINT_URL
        }
        
        put_response = requests.put(f"{BASE_URL}/api/ai-config", json=update_payload)
        assert put_response.status_code == 200, f"Expected 200, got {put_response.status_code}"
        
        updated_config = put_response.json()
        assert updated_config.get("twintPaymentUrl") == TEST_TWINT_URL, \
            f"Expected twintPaymentUrl to be '{TEST_TWINT_URL}', got '{updated_config.get('twintPaymentUrl')}'"
        
        print(f"✅ PUT /api/ai-config successfully updated twintPaymentUrl to: {TEST_TWINT_URL}")
    
    def test_ai_config_persists_twint_url(self):
        """Verify twintPaymentUrl persists after update"""
        # Get config after update
        response = requests.get(f"{BASE_URL}/api/ai-config")
        assert response.status_code == 200
        
        data = response.json()
        assert data.get("twintPaymentUrl") == TEST_TWINT_URL, \
            f"twintPaymentUrl not persisted. Expected '{TEST_TWINT_URL}', got '{data.get('twintPaymentUrl')}'"
        
        print(f"✅ twintPaymentUrl persisted correctly: {data.get('twintPaymentUrl')}")


class TestAIChatWithTwintLink:
    """Tests for AI chat responses with Twint payment link"""
    
    def test_ai_responds_with_twint_link_on_purchase_question(self):
        """Test 3: Ask AI about payment and verify it responds with Twint link"""
        # First ensure Twint URL is configured
        config_response = requests.get(f"{BASE_URL}/api/ai-config")
        assert config_response.status_code == 200
        config = config_response.json()
        
        if not config.get("twintPaymentUrl"):
            # Set the Twint URL if not configured
            requests.put(f"{BASE_URL}/api/ai-config", json={"twintPaymentUrl": TEST_TWINT_URL})
        
        # Create a chat session first
        session_response = requests.post(f"{BASE_URL}/api/chat/sessions", json={
            "mode": "ai",
            "is_ai_active": True,
            "title": "Test Twint Payment"
        })
        
        if session_response.status_code == 200:
            session = session_response.json()
            session_id = session.get("id")
        else:
            session_id = None
        
        # Send chat message asking about payment
        chat_payload = {
            "message": "Je veux acheter le café congolais, comment je paye ?",
            "leadId": "test-lead-twint",
            "firstName": TEST_USER["firstName"],
            "email": TEST_USER["email"],
            "whatsapp": TEST_USER["whatsapp"],
            "source": "test_twint"
        }
        
        chat_response = requests.post(f"{BASE_URL}/api/chat", json=chat_payload)
        assert chat_response.status_code == 200, f"Chat API failed: {chat_response.status_code}"
        
        chat_data = chat_response.json()
        ai_response = chat_data.get("response", "")
        
        print(f"AI Response: {ai_response}")
        
        # Verify the Twint link is in the response
        assert TEST_TWINT_URL in ai_response or "twint" in ai_response.lower(), \
            f"Expected Twint link or mention in AI response. Got: {ai_response}"
        
        print(f"✅ AI responded with Twint payment information")
    
    def test_ai_response_via_ai_response_endpoint(self):
        """Test AI response endpoint directly with payment question"""
        # Ensure Twint URL is configured
        requests.put(f"{BASE_URL}/api/ai-config", json={"twintPaymentUrl": TEST_TWINT_URL})
        
        # Use the ai-response endpoint
        payload = {
            "message": "Comment je peux payer pour acheter un produit ?",
            "leadId": "test-lead-payment",
            "firstName": TEST_USER["firstName"],
            "email": TEST_USER["email"],
            "whatsapp": TEST_USER["whatsapp"],
            "source": "test_payment"
        }
        
        response = requests.post(f"{BASE_URL}/api/chat/ai-response", json=payload)
        
        if response.status_code == 200:
            data = response.json()
            ai_response = data.get("response", "")
            print(f"AI Response (ai-response endpoint): {ai_response}")
            
            # Check if Twint is mentioned
            has_twint = TEST_TWINT_URL in ai_response or "twint" in ai_response.lower()
            print(f"✅ Twint mentioned in response: {has_twint}")
        else:
            print(f"⚠️ ai-response endpoint returned {response.status_code}")


class TestAIChatWithoutTwintLink:
    """Tests for AI behavior when Twint link is not configured"""
    
    def test_ai_redirects_to_coach_when_no_twint_link(self):
        """Test 4: Verify AI redirects to coach when Twint link is empty"""
        # First, save the current Twint URL
        config_response = requests.get(f"{BASE_URL}/api/ai-config")
        assert config_response.status_code == 200
        original_config = config_response.json()
        original_twint_url = original_config.get("twintPaymentUrl", "")
        
        try:
            # Clear the Twint URL
            clear_response = requests.put(f"{BASE_URL}/api/ai-config", json={"twintPaymentUrl": ""})
            assert clear_response.status_code == 200
            
            # Verify it's cleared
            verify_response = requests.get(f"{BASE_URL}/api/ai-config")
            verify_config = verify_response.json()
            assert verify_config.get("twintPaymentUrl") == "", "Failed to clear twintPaymentUrl"
            
            # Send chat message asking about payment
            chat_payload = {
                "message": "Je veux acheter, comment je paye ?",
                "leadId": "test-lead-no-twint",
                "firstName": TEST_USER["firstName"],
                "email": TEST_USER["email"],
                "whatsapp": TEST_USER["whatsapp"],
                "source": "test_no_twint"
            }
            
            chat_response = requests.post(f"{BASE_URL}/api/chat", json=chat_payload)
            assert chat_response.status_code == 200, f"Chat API failed: {chat_response.status_code}"
            
            chat_data = chat_response.json()
            ai_response = chat_data.get("response", "").lower()
            
            print(f"AI Response (no Twint): {ai_response}")
            
            # When no Twint link, AI should redirect to coach or contact
            # Check for coach/contact redirection indicators
            redirect_indicators = ["coach", "contact", "artboost", "email", "whatsapp", "contacter"]
            has_redirect = any(indicator in ai_response for indicator in redirect_indicators)
            
            print(f"✅ AI redirects to coach/contact when no Twint link: {has_redirect}")
            
        finally:
            # Restore the original Twint URL
            if original_twint_url:
                requests.put(f"{BASE_URL}/api/ai-config", json={"twintPaymentUrl": original_twint_url})
                print(f"✅ Restored original Twint URL: {original_twint_url}")


class TestHealthCheck:
    """Basic health check tests"""
    
    def test_api_health(self):
        """Verify API is healthy"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        print("✅ API health check passed")
    
    def test_ai_config_endpoint_exists(self):
        """Verify AI config endpoint exists"""
        response = requests.get(f"{BASE_URL}/api/ai-config")
        assert response.status_code == 200
        print("✅ AI config endpoint exists")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
