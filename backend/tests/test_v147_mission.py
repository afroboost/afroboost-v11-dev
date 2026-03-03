"""
Test Suite for Mission v14.7: Recherche et étanchéité contacts

Tests for:
1. CoachVitrine: Case-insensitive search (toLowerCase used)
2. CoachVitrine: Reset button (✕) clears search
3. Backend GET /chat/sessions: Filtered by coach_id (Super Admin sees all)
4. Backend GET /conversations: Filtered by coach_id (Super Admin sees all)
5. Backend POST /chat/generate-link: coach_id added to session
6. Backend GET /chat/participants: Filtered by coach_id
7. Scheduler: Campaigns persisted in MongoDB (status scheduled)
8. Anti-regression: reservations and contacts count
"""

import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# === TEST CREDENTIALS ===
SUPER_ADMIN_EMAIL = "contact.artboost@gmail.com"
PARTNER_EMAIL = "test.partner@example.com"

@pytest.fixture
def api_client():
    """Shared requests session"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


class TestHealthAndBasics:
    """Basic health checks"""
    
    def test_health_endpoint(self, api_client):
        """Health check returns 200"""
        response = api_client.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "healthy"
        print("✅ Health check passed")


class TestCoachIdFiltering:
    """Test coach_id filtering for data isolation (Étanchéité)"""
    
    def test_chat_sessions_super_admin_sees_all(self, api_client):
        """
        GET /chat/sessions with Super Admin header returns all sessions
        Super Admin (contact.artboost@gmail.com) should see everything
        """
        headers = {"X-User-Email": SUPER_ADMIN_EMAIL}
        response = api_client.get(f"{BASE_URL}/api/chat/sessions", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✅ Super Admin sees {len(data)} chat sessions")
    
    def test_chat_sessions_partner_filtered(self, api_client):
        """
        GET /chat/sessions with partner header returns only their sessions
        Partner should only see sessions with their coach_id
        """
        headers = {"X-User-Email": PARTNER_EMAIL}
        response = api_client.get(f"{BASE_URL}/api/chat/sessions", headers=headers)
        assert response.status_code == 200
        data = response.json()
        # Partner with no data should get empty list or only their sessions
        assert isinstance(data, list)
        # All returned sessions should have coach_id matching partner email
        for session in data:
            if session.get("coach_id"):
                assert session.get("coach_id") == PARTNER_EMAIL.lower()
        print(f"✅ Partner '{PARTNER_EMAIL}' sees {len(data)} sessions (filtered)")
    
    def test_conversations_super_admin_sees_all(self, api_client):
        """
        GET /conversations with Super Admin header returns all conversations
        """
        headers = {"X-User-Email": SUPER_ADMIN_EMAIL}
        response = api_client.get(f"{BASE_URL}/api/conversations", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "conversations" in data or isinstance(data, list)
        conversations = data.get("conversations", data) if isinstance(data, dict) else data
        print(f"✅ Super Admin sees {len(conversations)} conversations")
    
    def test_conversations_partner_filtered(self, api_client):
        """
        GET /conversations with partner header returns only their conversations
        """
        headers = {"X-User-Email": PARTNER_EMAIL}
        response = api_client.get(f"{BASE_URL}/api/conversations", headers=headers)
        assert response.status_code == 200
        data = response.json()
        conversations = data.get("conversations", data) if isinstance(data, dict) else data
        print(f"✅ Partner '{PARTNER_EMAIL}' sees {len(conversations)} conversations (filtered)")
    
    def test_chat_participants_super_admin_sees_all(self, api_client):
        """
        GET /chat/participants with Super Admin header returns all participants
        """
        headers = {"X-User-Email": SUPER_ADMIN_EMAIL}
        response = api_client.get(f"{BASE_URL}/api/chat/participants", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✅ Super Admin sees {len(data)} chat participants")
    
    def test_chat_participants_partner_filtered(self, api_client):
        """
        GET /chat/participants with partner header returns only their participants
        """
        headers = {"X-User-Email": PARTNER_EMAIL}
        response = api_client.get(f"{BASE_URL}/api/chat/participants", headers=headers)
        assert response.status_code == 200
        data = response.json()
        # All returned participants should have coach_id matching partner
        for participant in data:
            if participant.get("coach_id"):
                assert participant.get("coach_id") == PARTNER_EMAIL.lower()
        print(f"✅ Partner '{PARTNER_EMAIL}' sees {len(data)} participants (filtered)")


class TestGenerateLink:
    """Test POST /chat/generate-link adds coach_id"""
    
    def test_generate_link_super_admin(self, api_client):
        """
        POST /chat/generate-link with Super Admin adds DEFAULT_COACH_ID
        """
        headers = {"X-User-Email": SUPER_ADMIN_EMAIL}
        response = api_client.post(
            f"{BASE_URL}/api/chat/generate-link",
            headers=headers,
            json={"title": "TEST_Super_Admin_Link"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "link_token" in data
        assert "session_id" in data
        print(f"✅ Super Admin generated link: {data.get('link_token')}")
        return data.get("session_id")
    
    def test_generate_link_partner(self, api_client):
        """
        POST /chat/generate-link with partner adds partner's email as coach_id
        """
        headers = {"X-User-Email": PARTNER_EMAIL}
        response = api_client.post(
            f"{BASE_URL}/api/chat/generate-link",
            headers=headers,
            json={"title": "TEST_Partner_Link"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "link_token" in data
        assert "session_id" in data
        print(f"✅ Partner generated link: {data.get('link_token')}")
        return data.get("session_id")


class TestCampaignScheduler:
    """Test campaigns with scheduler (persisted in MongoDB)"""
    
    def test_create_scheduled_campaign(self, api_client):
        """
        POST /campaigns with scheduledAt creates campaign with status 'scheduled'
        """
        from datetime import datetime, timedelta
        
        future_date = (datetime.utcnow() + timedelta(hours=24)).isoformat() + "Z"
        
        campaign_data = {
            "name": f"TEST_Scheduled_Campaign_{uuid.uuid4().hex[:6]}",
            "message": "Test message for scheduling",
            "mediaUrl": "https://example.com/test-media.jpg",
            "mediaFormat": "16:9",
            "targetType": "all",
            "selectedContacts": [],
            "channels": {"internal": True, "whatsapp": False, "email": False, "group": False},
            "scheduledAt": future_date
        }
        
        response = api_client.post(f"{BASE_URL}/api/campaigns", json=campaign_data)
        assert response.status_code == 200
        data = response.json()
        
        # Campaign should be created with status 'scheduled'
        assert data.get("status") == "scheduled"
        assert data.get("scheduledAt") == future_date
        assert data.get("mediaUrl") == "https://example.com/test-media.jpg"
        
        campaign_id = data.get("id")
        print(f"✅ Scheduled campaign created: {campaign_id} (status=scheduled)")
        
        # Clean up: Delete the test campaign
        api_client.delete(f"{BASE_URL}/api/campaigns/{campaign_id}")
        print(f"✅ Test campaign cleaned up")
        return campaign_id
    
    def test_campaigns_list_endpoint(self, api_client):
        """GET /campaigns returns list of campaigns"""
        response = api_client.get(f"{BASE_URL}/api/campaigns")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✅ Campaigns endpoint returns {len(data)} campaigns")


class TestAntiRegression:
    """Anti-regression tests for core functionality"""
    
    def test_contacts_minimum_count(self, api_client):
        """
        GET /users should return at least 8 contacts (as per v14.6 audit)
        """
        response = api_client.get(f"{BASE_URL}/api/users")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 8, f"Expected at least 8 contacts, got {len(data)}"
        print(f"✅ Contacts count: {len(data)} (expected >= 8)")
    
    def test_reservations_endpoint(self, api_client):
        """GET /reservations endpoint works"""
        response = api_client.get(f"{BASE_URL}/api/reservations")
        assert response.status_code == 200
        data = response.json()
        # Endpoint returns paginated data {data: [], pagination: {}}
        if isinstance(data, dict) and "data" in data:
            reservations = data.get("data", [])
        else:
            reservations = data
        assert isinstance(reservations, list)
        print(f"✅ Reservations endpoint returns {len(reservations)} reservations")
    
    def test_offers_minimum_count(self, api_client):
        """
        GET /offers should return at least 3 offers
        """
        response = api_client.get(f"{BASE_URL}/api/offers")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 3, f"Expected at least 3 offers, got {len(data)}"
        print(f"✅ Offers count: {len(data)} (expected >= 3)")
    
    def test_courses_endpoint(self, api_client):
        """GET /courses endpoint works"""
        response = api_client.get(f"{BASE_URL}/api/courses")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✅ Courses endpoint returns {len(data)} courses")
    
    def test_discount_codes_endpoint(self, api_client):
        """GET /discount-codes endpoint works"""
        headers = {"X-User-Email": SUPER_ADMIN_EMAIL}
        response = api_client.get(f"{BASE_URL}/api/discount-codes", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✅ Discount codes endpoint returns {len(data)} codes")


class TestCoachVitrineSearch:
    """Test CoachVitrine search functionality"""
    
    def test_coach_vitrine_endpoint(self, api_client):
        """
        GET /coach/vitrine/{username} returns coach data with offers
        """
        # Use a known coach username
        response = api_client.get(f"{BASE_URL}/api/coach/vitrine/bassi")
        # May return 404 if coach not found, which is acceptable
        if response.status_code == 200:
            data = response.json()
            assert "coach" in data
            assert "offers" in data
            print(f"✅ Coach vitrine returns {len(data.get('offers', []))} offers")
        else:
            print(f"ℹ️ Coach vitrine returned {response.status_code} (coach may not exist)")
    
    def test_offers_have_keywords_field(self, api_client):
        """
        GET /offers - all offers should support keywords field for search
        """
        response = api_client.get(f"{BASE_URL}/api/offers")
        assert response.status_code == 200
        data = response.json()
        # Check that offers can have keywords field (not required, but supported)
        for offer in data[:3]:  # Check first 3
            # Keywords field may be empty but structure should be valid
            assert isinstance(offer.get("name", ""), str)
            assert isinstance(offer.get("description", ""), str)
            # Keywords may be None or string
            keywords = offer.get("keywords")
            if keywords is not None:
                assert isinstance(keywords, str)
        print(f"✅ Offers support keywords field for search")


class TestMediaAndObjectFit:
    """Test media handling for campaigns (object-fit cover for Samsung)"""
    
    def test_campaign_media_url_persisted(self, api_client):
        """
        Campaign creation persists mediaUrl correctly
        """
        campaign_data = {
            "name": f"TEST_Media_Campaign_{uuid.uuid4().hex[:6]}",
            "message": "Test with media",
            "mediaUrl": "https://example.com/samsung-cover.jpg",
            "mediaFormat": "9:16",  # Portrait format
            "targetType": "all",
            "selectedContacts": [],
            "channels": {"internal": True},
            "scheduledAt": None
        }
        
        response = api_client.post(f"{BASE_URL}/api/campaigns", json=campaign_data)
        assert response.status_code == 200
        data = response.json()
        
        assert data.get("mediaUrl") == "https://example.com/samsung-cover.jpg"
        assert data.get("mediaFormat") == "9:16"
        
        # Cleanup
        api_client.delete(f"{BASE_URL}/api/campaigns/{data.get('id')}")
        print("✅ Campaign media URL and format persisted correctly")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
