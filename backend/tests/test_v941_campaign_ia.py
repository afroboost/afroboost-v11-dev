"""
Test suite for Mission v9.4.1 - CAMPAGNES INTELLIGENTES ET NOTIFICATIONS EMAIL
Tests:
1. POST /api/ai/campaign-suggestions endpoint (3 suggestions: Promo/Relance/Info)
2. Backend email notifications with Resend
3. Non-regression: ensure existing features work
"""

import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://video-feed-platform.preview.emergentagent.com').rstrip('/')


class TestAICampaignSuggestions:
    """Tests for the AI campaign suggestions endpoint v9.4.1"""
    
    def test_ai_suggestions_endpoint_exists(self):
        """Verify the endpoint /api/ai/campaign-suggestions is accessible"""
        response = requests.post(
            f"{BASE_URL}/api/ai/campaign-suggestions",
            json={"campaign_goal": "Test objective", "campaign_name": "Test", "recipient_count": 1},
            headers={"Content-Type": "application/json"}
        )
        # Should not be 404 or 405
        assert response.status_code in [200, 400, 500], f"Endpoint should exist. Got {response.status_code}"
        print(f"✅ Endpoint /api/ai/campaign-suggestions is accessible (status: {response.status_code})")
    
    def test_ai_suggestions_returns_3_suggestions(self):
        """Verify endpoint returns exactly 3 suggestions"""
        response = requests.post(
            f"{BASE_URL}/api/ai/campaign-suggestions",
            json={
                "campaign_goal": "Promotion cours de danse ce weekend",
                "campaign_name": "Promo Weekend",
                "recipient_count": 10
            },
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get("success") == True, "Response should indicate success"
        assert "suggestions" in data, "Response should contain suggestions array"
        
        suggestions = data["suggestions"]
        assert len(suggestions) == 3, f"Expected 3 suggestions, got {len(suggestions)}"
        print(f"✅ Endpoint returns {len(suggestions)} suggestions")
    
    def test_ai_suggestions_types(self):
        """Verify suggestions have correct types: Promo, Relance, Info"""
        response = requests.post(
            f"{BASE_URL}/api/ai/campaign-suggestions",
            json={
                "campaign_goal": "Nouveau cours disponible",
                "campaign_name": "Lancement",
                "recipient_count": 5
            },
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 200
        
        data = response.json()
        suggestions = data.get("suggestions", [])
        types_found = [s.get("type") for s in suggestions]
        
        expected_types = {"Promo", "Relance", "Info"}
        actual_types = set(types_found)
        
        assert expected_types == actual_types, f"Expected types {expected_types}, got {actual_types}"
        print(f"✅ All three types present: {actual_types}")
    
    def test_ai_suggestions_contain_text(self):
        """Verify each suggestion has a text field"""
        response = requests.post(
            f"{BASE_URL}/api/ai/campaign-suggestions",
            json={
                "campaign_goal": "Offre spéciale Black Friday",
                "campaign_name": "Black Friday",
                "recipient_count": 20
            },
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 200
        
        data = response.json()
        suggestions = data.get("suggestions", [])
        
        for i, suggestion in enumerate(suggestions):
            assert "text" in suggestion, f"Suggestion {i} should have 'text' field"
            assert len(suggestion["text"]) > 0, f"Suggestion {i} text should not be empty"
            assert "{prénom}" in suggestion["text"], f"Suggestion {i} should contain {{prénom}} variable"
        
        print("✅ All suggestions contain text with {prénom} variable")
    
    def test_ai_suggestions_requires_goal(self):
        """Verify endpoint returns error without campaign_goal"""
        response = requests.post(
            f"{BASE_URL}/api/ai/campaign-suggestions",
            json={"campaign_name": "Test", "recipient_count": 1},
            headers={"Content-Type": "application/json"}
        )
        # Should return 400 or indicate error
        assert response.status_code in [400, 422], f"Expected 400/422 without goal, got {response.status_code}"
        print("✅ Endpoint correctly requires campaign_goal parameter")
    
    def test_ai_suggestions_empty_goal_rejected(self):
        """Verify endpoint rejects empty campaign_goal"""
        response = requests.post(
            f"{BASE_URL}/api/ai/campaign-suggestions",
            json={"campaign_goal": "", "campaign_name": "Test", "recipient_count": 1},
            headers={"Content-Type": "application/json"}
        )
        # Should return 400
        assert response.status_code == 400, f"Expected 400 with empty goal, got {response.status_code}"
        print("✅ Endpoint correctly rejects empty campaign_goal")


class TestNotificationBadgeNonRegression:
    """Non-regression tests for notification badge (v9.4.0 feature)"""
    
    def test_chat_sessions_endpoint(self):
        """Verify chat sessions endpoint works"""
        response = requests.get(f"{BASE_URL}/api/chat/sessions")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("✅ Chat sessions endpoint working")
    
    def test_conversations_active_endpoint(self):
        """Verify active conversations endpoint works"""
        response = requests.get(f"{BASE_URL}/api/conversations/active")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert "success" in data or "conversations" in data, "Response should have success or conversations"
        print("✅ Active conversations endpoint working")


class TestEmailNotifications:
    """Tests for email notifications via Resend (campaign email sending)"""
    
    def test_campaign_send_email_endpoint(self):
        """Verify campaign email send endpoint exists"""
        response = requests.post(
            f"{BASE_URL}/api/campaigns/send-email",
            json={"campaign_id": "test", "to_emails": ["test@example.com"]},
            headers={"Content-Type": "application/json"}
        )
        # Should not be 404 (endpoint exists)
        # Expected: 400 or 500 due to invalid campaign_id, but not 404
        assert response.status_code != 404, f"Email send endpoint should exist, got {response.status_code}"
        print(f"✅ Campaign email send endpoint exists (status: {response.status_code})")


class TestCampaignsAPI:
    """Tests for campaigns API"""
    
    def test_campaigns_list(self):
        """Verify campaigns list endpoint works"""
        response = requests.get(f"{BASE_URL}/api/campaigns")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        print(f"✅ Campaigns list endpoint working, {len(data)} campaigns found")
    
    def test_campaign_create(self):
        """Test creating a new campaign"""
        campaign_data = {
            "name": "TEST_Campaign_v941",
            "message": "Test message for {prénom}",
            "mediaUrl": "",
            "targetType": "selected",
            "selectedContacts": [],
            "channels": {"internal": True, "email": False, "whatsapp": False},
            "scheduledAt": None
        }
        
        response = requests.post(
            f"{BASE_URL}/api/campaigns",
            json=campaign_data,
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "id" in data, "Created campaign should have an id"
        assert data.get("name") == "TEST_Campaign_v941", "Campaign name should match"
        
        campaign_id = data["id"]
        print(f"✅ Campaign created with id: {campaign_id}")
        
        # Cleanup: delete the test campaign
        delete_response = requests.delete(f"{BASE_URL}/api/campaigns/{campaign_id}")
        assert delete_response.status_code in [200, 204], f"Failed to delete test campaign: {delete_response.status_code}"
        print("✅ Test campaign cleaned up")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
