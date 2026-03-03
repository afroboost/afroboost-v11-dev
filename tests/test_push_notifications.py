"""
Test Push Notifications System - Web Push API + Email Backup via Resend
Tests for:
- GET /api/push/vapid-key - returns VAPID public key
- POST /api/push/subscribe - registers push subscription
- POST /api/push/send - sends push notification with email fallback
- DELETE /api/push/subscribe/{participant_id} - unsubscribes
- POST /api/chat/ai-response in human mode - notifies coach
- POST /api/chat/sessions/{session_id}/toggle-ai - toggles ai/human mode
"""

import pytest
import requests
import os
import uuid

# Get BASE_URL from environment
BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
if not BASE_URL:
    BASE_URL = "https://promo-credits-lab.preview.emergentagent.com"

# Test data
TEST_PARTICIPANT_ID = "fc7f7b7e-5629-4e44-a8d6-bc1e1230754b"
TEST_SESSION_ID = "6a8a7220-0436-409b-a000-6ccf7bb2b38c"


@pytest.fixture
def api_client():
    """Shared requests session"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


class TestHealthCheck:
    """Basic health check to ensure API is running"""
    
    def test_health_check(self, api_client):
        """Test API health endpoint"""
        response = api_client.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["database"] == "connected"
        print("✅ Health check passed - API is healthy")


class TestVAPIDKey:
    """Tests for GET /api/push/vapid-key endpoint"""
    
    def test_get_vapid_key_returns_public_key(self, api_client):
        """GET /api/push/vapid-key should return the VAPID public key"""
        response = api_client.get(f"{BASE_URL}/api/push/vapid-key")
        assert response.status_code == 200
        data = response.json()
        assert "publicKey" in data
        assert isinstance(data["publicKey"], str)
        assert len(data["publicKey"]) > 0
        print(f"✅ VAPID public key returned: {data['publicKey'][:30]}...")


class TestPushSubscription:
    """Tests for POST /api/push/subscribe endpoint"""
    
    def test_subscribe_push_success(self, api_client):
        """POST /api/push/subscribe should register a push subscription"""
        # Create a mock subscription object (similar to what browser would send)
        subscription_data = {
            "participant_id": f"TEST_{uuid.uuid4().hex[:12]}",
            "subscription": {
                "endpoint": "https://fcm.googleapis.com/fcm/send/test-endpoint-123",
                "keys": {
                    "p256dh": "BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_0QTpQtUbVlUls0VJXg7A8u-Ts1XbjhazAkj7I99e8QcYP7DkM",
                    "auth": "tBHItJI5svbpez7KI4CCXg"
                }
            }
        }
        
        response = api_client.post(f"{BASE_URL}/api/push/subscribe", json=subscription_data)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        assert "message" in data
        print(f"✅ Push subscription registered for participant: {subscription_data['participant_id']}")
    
    def test_subscribe_push_missing_participant_id(self, api_client):
        """POST /api/push/subscribe should return 400 if participant_id is missing"""
        subscription_data = {
            "subscription": {
                "endpoint": "https://fcm.googleapis.com/fcm/send/test-endpoint",
                "keys": {"p256dh": "test", "auth": "test"}
            }
        }
        
        response = api_client.post(f"{BASE_URL}/api/push/subscribe", json=subscription_data)
        assert response.status_code == 400
        print("✅ Correctly rejected subscription without participant_id")
    
    def test_subscribe_push_missing_subscription(self, api_client):
        """POST /api/push/subscribe should return 400 if subscription is missing"""
        subscription_data = {
            "participant_id": "test-participant"
        }
        
        response = api_client.post(f"{BASE_URL}/api/push/subscribe", json=subscription_data)
        assert response.status_code == 400
        print("✅ Correctly rejected subscription without subscription object")


class TestPushUnsubscribe:
    """Tests for DELETE /api/push/subscribe/{participant_id} endpoint"""
    
    def test_unsubscribe_push_success(self, api_client):
        """DELETE /api/push/subscribe/{participant_id} should deactivate subscription"""
        # First create a subscription
        test_participant_id = f"TEST_unsub_{uuid.uuid4().hex[:8]}"
        subscription_data = {
            "participant_id": test_participant_id,
            "subscription": {
                "endpoint": "https://fcm.googleapis.com/fcm/send/test-unsub",
                "keys": {"p256dh": "test-key", "auth": "test-auth"}
            }
        }
        api_client.post(f"{BASE_URL}/api/push/subscribe", json=subscription_data)
        
        # Now unsubscribe
        response = api_client.delete(f"{BASE_URL}/api/push/subscribe/{test_participant_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        print(f"✅ Push subscription deactivated for: {test_participant_id}")


class TestPushSend:
    """Tests for POST /api/push/send endpoint"""
    
    def test_send_push_with_email_fallback(self, api_client):
        """POST /api/push/send should attempt push and fallback to email"""
        # First, ensure we have a participant with email for the fallback test
        # Create a test participant
        participant_id = f"TEST_push_{uuid.uuid4().hex[:8]}"
        participant_data = {
            "name": "Test Push User",
            "email": "test@example.com",
            "whatsapp": "+41791234567",
            "source": "test"
        }
        
        # Create participant
        create_response = api_client.post(f"{BASE_URL}/api/chat/participants", json=participant_data)
        if create_response.status_code == 200:
            created_participant = create_response.json()
            participant_id = created_participant.get("id", participant_id)
        
        # Register a push subscription for this participant
        subscription_data = {
            "participant_id": participant_id,
            "subscription": {
                "endpoint": "https://fcm.googleapis.com/fcm/send/test-push-send",
                "keys": {"p256dh": "test-key", "auth": "test-auth"}
            }
        }
        api_client.post(f"{BASE_URL}/api/push/subscribe", json=subscription_data)
        
        # Now send a push notification
        send_data = {
            "participant_id": participant_id,
            "title": "Test Notification",
            "body": "Ceci est un test de notification push depuis Afroboost !",
            "send_email_backup": True
        }
        
        response = api_client.post(f"{BASE_URL}/api/push/send", json=send_data)
        assert response.status_code == 200
        data = response.json()
        
        # Check response structure
        assert "push_sent" in data
        assert "email_sent" in data
        assert "participant_id" in data
        assert data["participant_id"] == participant_id
        
        # Note: push_sent will be False because VAPID keys are test keys
        # email_sent should be True (simulation mode)
        print(f"✅ Push send response: push_sent={data['push_sent']}, email_sent={data['email_sent']}")
    
    def test_send_push_missing_participant_id(self, api_client):
        """POST /api/push/send should return 400 if participant_id is missing"""
        send_data = {
            "title": "Test",
            "body": "Test message"
        }
        
        response = api_client.post(f"{BASE_URL}/api/push/send", json=send_data)
        assert response.status_code == 400
        print("✅ Correctly rejected push send without participant_id")


class TestToggleAI:
    """Tests for POST /api/chat/sessions/{session_id}/toggle-ai endpoint"""
    
    def test_toggle_ai_mode(self, api_client):
        """POST /api/chat/sessions/{session_id}/toggle-ai should toggle between ai/human modes"""
        # First create a test session
        session_data = {
            "mode": "ai",
            "is_ai_active": True,
            "title": "Test Toggle Session"
        }
        
        create_response = api_client.post(f"{BASE_URL}/api/chat/sessions", json=session_data)
        assert create_response.status_code == 200
        session = create_response.json()
        session_id = session["id"]
        initial_ai_state = session.get("is_ai_active", True)
        
        # Toggle AI
        toggle_response = api_client.post(f"{BASE_URL}/api/chat/sessions/{session_id}/toggle-ai")
        assert toggle_response.status_code == 200
        toggled_session = toggle_response.json()
        
        # Verify toggle worked
        assert toggled_session["is_ai_active"] != initial_ai_state
        expected_mode = "ai" if toggled_session["is_ai_active"] else "human"
        assert toggled_session["mode"] == expected_mode
        
        print(f"✅ AI toggled: is_ai_active={toggled_session['is_ai_active']}, mode={toggled_session['mode']}")
        
        # Toggle back
        toggle_back_response = api_client.post(f"{BASE_URL}/api/chat/sessions/{session_id}/toggle-ai")
        assert toggle_back_response.status_code == 200
        final_session = toggle_back_response.json()
        assert final_session["is_ai_active"] == initial_ai_state
        print(f"✅ AI toggled back: is_ai_active={final_session['is_ai_active']}, mode={final_session['mode']}")
    
    def test_toggle_ai_nonexistent_session(self, api_client):
        """POST /api/chat/sessions/{session_id}/toggle-ai should return 404 for non-existent session"""
        fake_session_id = "nonexistent-session-12345"
        response = api_client.post(f"{BASE_URL}/api/chat/sessions/{fake_session_id}/toggle-ai")
        assert response.status_code == 404
        print("✅ Correctly returned 404 for non-existent session")


class TestAIResponseWithCoachNotification:
    """Tests for POST /api/chat/ai-response in human mode - should notify coach"""
    
    def test_ai_response_in_human_mode_notifies_coach(self, api_client):
        """POST /api/chat/ai-response in human mode should notify coach via email"""
        # 1. Create a test participant
        participant_data = {
            "name": "Test Push User",
            "email": "testuser@example.com",
            "whatsapp": "+41791234567",
            "source": "test"
        }
        
        participant_response = api_client.post(f"{BASE_URL}/api/chat/participants", json=participant_data)
        assert participant_response.status_code == 200
        participant = participant_response.json()
        participant_id = participant["id"]
        
        # 2. Create a test session in AI mode
        session_data = {
            "mode": "ai",
            "is_ai_active": True,
            "title": "Test Coach Notification Session"
        }
        
        session_response = api_client.post(f"{BASE_URL}/api/chat/sessions", json=session_data)
        assert session_response.status_code == 200
        session = session_response.json()
        session_id = session["id"]
        
        # 3. Add participant to session
        join_response = api_client.post(f"{BASE_URL}/api/chat/sessions/{session_id}/join", json={
            "participant_id": participant_id
        })
        # Join might return 200 or session might already have participant
        
        # 4. Toggle to human mode
        toggle_response = api_client.post(f"{BASE_URL}/api/chat/sessions/{session_id}/toggle-ai")
        assert toggle_response.status_code == 200
        toggled_session = toggle_response.json()
        assert toggled_session["mode"] == "human"
        assert toggled_session["is_ai_active"] == False
        
        # 5. Send a message in human mode - should trigger coach notification
        message_data = {
            "session_id": session_id,
            "participant_id": participant_id,
            "message": "Bonjour ! Je voudrais me renseigner sur vos offres de coaching."
        }
        
        ai_response = api_client.post(f"{BASE_URL}/api/chat/ai-response", json=message_data)
        assert ai_response.status_code == 200
        response_data = ai_response.json()
        
        # In human mode, AI should not respond but coach should be notified
        assert response_data["ai_active"] == False
        assert response_data["mode"] == "human"
        assert response_data["message_saved"] == True
        assert response_data["coach_notified"] == True
        assert response_data["response"] is None  # No AI response in human mode
        
        print(f"✅ Human mode message saved, coach_notified={response_data['coach_notified']}")
        print("✅ Check backend logs for '[SIMULATION COACH EMAIL]' entry")
    
    def test_ai_response_in_ai_mode_returns_response(self, api_client):
        """POST /api/chat/ai-response in AI mode should return AI response"""
        # 1. Create a test participant
        participant_data = {
            "name": "Test AI User",
            "email": "testai@example.com",
            "whatsapp": "+41791234568",
            "source": "test"
        }
        
        participant_response = api_client.post(f"{BASE_URL}/api/chat/participants", json=participant_data)
        assert participant_response.status_code == 200
        participant = participant_response.json()
        participant_id = participant["id"]
        
        # 2. Create a test session in AI mode
        session_data = {
            "mode": "ai",
            "is_ai_active": True,
            "title": "Test AI Response Session"
        }
        
        session_response = api_client.post(f"{BASE_URL}/api/chat/sessions", json=session_data)
        assert session_response.status_code == 200
        session = session_response.json()
        session_id = session["id"]
        
        # 3. Add participant to session
        api_client.post(f"{BASE_URL}/api/chat/sessions/{session_id}/join", json={
            "participant_id": participant_id
        })
        
        # 4. Send a message in AI mode
        message_data = {
            "session_id": session_id,
            "participant_id": participant_id,
            "message": "Bonjour, quels sont vos horaires ?"
        }
        
        ai_response = api_client.post(f"{BASE_URL}/api/chat/ai-response", json=message_data)
        assert ai_response.status_code == 200
        response_data = ai_response.json()
        
        # In AI mode, should get a response with ai_active=True
        assert response_data["ai_active"] == True
        # Response structure varies: when AI responds, it has 'response' and 'mode'
        # When AI is disabled globally, it has 'message_saved'
        assert "response" in response_data or "message_saved" in response_data
        
        print(f"✅ AI mode response: ai_active={response_data['ai_active']}, has_response={response_data.get('response') is not None}")


class TestExistingTestData:
    """Tests using the provided test data from the review request"""
    
    def test_existing_participant_subscription(self, api_client):
        """Test subscription with the provided test participant ID"""
        subscription_data = {
            "participant_id": TEST_PARTICIPANT_ID,
            "subscription": {
                "endpoint": "https://fcm.googleapis.com/fcm/send/existing-test",
                "keys": {
                    "p256dh": "BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_0QTpQtUbVlUls0VJXg7A8u-Ts1XbjhazAkj7I99e8QcYP7DkM",
                    "auth": "tBHItJI5svbpez7KI4CCXg"
                }
            }
        }
        
        response = api_client.post(f"{BASE_URL}/api/push/subscribe", json=subscription_data)
        assert response.status_code == 200
        print(f"✅ Subscription registered for existing test participant: {TEST_PARTICIPANT_ID}")
    
    def test_existing_session_toggle(self, api_client):
        """Test toggle AI with the provided test session ID"""
        # First check if session exists
        response = api_client.get(f"{BASE_URL}/api/chat/sessions/{TEST_SESSION_ID}")
        
        if response.status_code == 200:
            # Session exists, test toggle
            toggle_response = api_client.post(f"{BASE_URL}/api/chat/sessions/{TEST_SESSION_ID}/toggle-ai")
            assert toggle_response.status_code == 200
            session = toggle_response.json()
            print(f"✅ Toggled existing session: mode={session['mode']}, is_ai_active={session['is_ai_active']}")
            
            # Toggle back to original state
            api_client.post(f"{BASE_URL}/api/chat/sessions/{TEST_SESSION_ID}/toggle-ai")
        else:
            print(f"⚠️ Test session {TEST_SESSION_ID} not found - skipping toggle test")
            pytest.skip("Test session not found")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
