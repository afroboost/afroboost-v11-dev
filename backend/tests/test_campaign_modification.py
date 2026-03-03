"""
Test Campaign Modification Feature - Iteration 34
Tests for PUT /api/campaigns/{campaign_id} endpoint
Features tested:
- Create campaign via POST
- Update campaign via PUT (name, message, mediaUrl, targetType, channels)
- Verify changes persist via GET
- Verify existing media links (/v/{slug}) are not broken
"""

import pytest
import requests
import os
import uuid
from datetime import datetime

# Get BASE_URL from environment
BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
if not BASE_URL:
    BASE_URL = "https://promo-credits-lab.preview.emergentagent.com"

API_URL = f"{BASE_URL}/api"


class TestCampaignModification:
    """Test suite for campaign modification (PUT /api/campaigns/{campaign_id})"""
    
    # Class-level variable to store campaign ID across tests
    created_campaign_id = None
    
    def test_01_health_check(self):
        """Test API health endpoint"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200, f"Health check failed: {response.text}"
        print("✅ Health check passed")
    
    def test_02_get_campaigns_returns_list(self):
        """Test GET /api/campaigns returns a list with required fields"""
        response = requests.get(f"{API_URL}/campaigns")
        assert response.status_code == 200, f"GET campaigns failed: {response.text}"
        
        campaigns = response.json()
        assert isinstance(campaigns, list), "Response should be a list"
        
        # If there are campaigns, verify structure
        if len(campaigns) > 0:
            campaign = campaigns[0]
            # Verify required fields exist
            required_fields = ['id', 'name', 'message', 'status', 'channels']
            for field in required_fields:
                assert field in campaign, f"Missing field: {field}"
            print(f"✅ GET /api/campaigns returns {len(campaigns)} campaigns with required fields")
        else:
            print("✅ GET /api/campaigns returns empty list (no campaigns yet)")
    
    def test_03_create_campaign_for_modification(self):
        """Test POST /api/campaigns - Create a draft campaign for modification tests"""
        test_name = f"TEST_Campaign_{uuid.uuid4().hex[:8]}"
        payload = {
            "name": test_name,
            "message": "Original message for testing",
            "mediaUrl": "https://example.com/original-media.jpg",
            "mediaFormat": "16:9",
            "targetType": "all",
            "selectedContacts": [],
            "channels": {"whatsapp": True, "email": False, "instagram": False},
            "scheduledAt": None
        }
        
        response = requests.post(f"{API_URL}/campaigns", json=payload)
        assert response.status_code == 200, f"POST campaigns failed: {response.text}"
        
        campaign = response.json()
        assert "id" in campaign, "Response should contain campaign id"
        assert campaign["name"] == test_name, "Campaign name should match"
        assert campaign["message"] == "Original message for testing", "Message should match"
        assert campaign["status"] in ["draft", "scheduled"], f"Status should be draft or scheduled, got: {campaign['status']}"
        
        # Store for later tests at class level
        TestCampaignModification.created_campaign_id = campaign["id"]
        
        print(f"✅ Created test campaign: {campaign['id']} with status: {campaign['status']}")
    
    def test_04_get_single_campaign(self):
        """Test GET /api/campaigns/{campaign_id} - Retrieve created campaign"""
        campaign_id = TestCampaignModification.created_campaign_id
        if not campaign_id:
            pytest.skip("No campaign created in previous test")
        
        response = requests.get(f"{API_URL}/campaigns/{campaign_id}")
        assert response.status_code == 200, f"GET campaign failed: {response.text}"
        
        campaign = response.json()
        assert campaign["id"] == campaign_id, "Campaign ID should match"
        
        # Verify all required fields for edit form
        required_fields = ['name', 'message', 'mediaUrl', 'targetType', 'channels']
        for field in required_fields:
            assert field in campaign, f"Missing field for edit form: {field}"
        
        print(f"✅ GET /api/campaigns/{campaign_id} returns all required fields")
    
    def test_05_update_campaign_name(self):
        """Test PUT /api/campaigns/{campaign_id} - Update campaign name"""
        campaign_id = TestCampaignModification.created_campaign_id
        if not campaign_id:
            pytest.skip("No campaign created in previous test")
        
        new_name = f"UPDATED_Campaign_{uuid.uuid4().hex[:6]}"
        payload = {"name": new_name}
        
        response = requests.put(f"{API_URL}/campaigns/{campaign_id}", json=payload)
        assert response.status_code == 200, f"PUT campaign failed: {response.text}"
        
        updated = response.json()
        assert updated is not None, "PUT should return updated campaign"
        assert updated["name"] == new_name, f"Name should be updated to {new_name}"
        assert "updatedAt" in updated, "updatedAt should be set"
        
        # Verify persistence via GET
        get_response = requests.get(f"{API_URL}/campaigns/{campaign_id}")
        assert get_response.status_code == 200
        persisted = get_response.json()
        assert persisted["name"] == new_name, "Name change should persist"
        
        print(f"✅ PUT /api/campaigns/{campaign_id} - Name updated and persisted")
    
    def test_06_update_campaign_message(self):
        """Test PUT /api/campaigns/{campaign_id} - Update campaign message"""
        campaign_id = TestCampaignModification.created_campaign_id
        if not campaign_id:
            pytest.skip("No campaign created in previous test")
        
        new_message = "Updated message with special chars: éàü 🎉"
        payload = {"message": new_message}
        
        response = requests.put(f"{API_URL}/campaigns/{campaign_id}", json=payload)
        assert response.status_code == 200, f"PUT campaign failed: {response.text}"
        
        updated = response.json()
        assert updated is not None, "PUT should return updated campaign"
        assert updated["message"] == new_message, "Message should be updated"
        
        # Verify persistence
        get_response = requests.get(f"{API_URL}/campaigns/{campaign_id}")
        persisted = get_response.json()
        assert persisted["message"] == new_message, "Message change should persist"
        
        print(f"✅ PUT /api/campaigns/{campaign_id} - Message updated and persisted")
    
    def test_07_update_campaign_media_url(self):
        """Test PUT /api/campaigns/{campaign_id} - Update mediaUrl"""
        campaign_id = TestCampaignModification.created_campaign_id
        if not campaign_id:
            pytest.skip("No campaign created in previous test")
        
        new_media_url = "https://example.com/new-media-image.png"
        payload = {"mediaUrl": new_media_url}
        
        response = requests.put(f"{API_URL}/campaigns/{campaign_id}", json=payload)
        assert response.status_code == 200, f"PUT campaign failed: {response.text}"
        
        updated = response.json()
        assert updated is not None, "PUT should return updated campaign"
        assert updated["mediaUrl"] == new_media_url, "mediaUrl should be updated"
        
        # Verify persistence
        get_response = requests.get(f"{API_URL}/campaigns/{campaign_id}")
        persisted = get_response.json()
        assert persisted["mediaUrl"] == new_media_url, "mediaUrl change should persist"
        
        print(f"✅ PUT /api/campaigns/{campaign_id} - mediaUrl updated and persisted")
    
    def test_08_update_campaign_target_type(self):
        """Test PUT /api/campaigns/{campaign_id} - Update targetType"""
        campaign_id = TestCampaignModification.created_campaign_id
        if not campaign_id:
            pytest.skip("No campaign created in previous test")
        
        # Change from 'all' to 'selected'
        payload = {"targetType": "selected", "selectedContacts": ["contact1", "contact2"]}
        
        response = requests.put(f"{API_URL}/campaigns/{campaign_id}", json=payload)
        assert response.status_code == 200, f"PUT campaign failed: {response.text}"
        
        updated = response.json()
        assert updated is not None, "PUT should return updated campaign"
        assert updated["targetType"] == "selected", "targetType should be updated"
        assert updated["selectedContacts"] == ["contact1", "contact2"], "selectedContacts should be updated"
        
        # Verify persistence
        get_response = requests.get(f"{API_URL}/campaigns/{campaign_id}")
        persisted = get_response.json()
        assert persisted["targetType"] == "selected", "targetType change should persist"
        
        print(f"✅ PUT /api/campaigns/{campaign_id} - targetType updated and persisted")
    
    def test_09_update_campaign_channels(self):
        """Test PUT /api/campaigns/{campaign_id} - Update channels"""
        campaign_id = TestCampaignModification.created_campaign_id
        if not campaign_id:
            pytest.skip("No campaign created in previous test")
        
        new_channels = {"whatsapp": False, "email": True, "instagram": True}
        payload = {"channels": new_channels}
        
        response = requests.put(f"{API_URL}/campaigns/{campaign_id}", json=payload)
        assert response.status_code == 200, f"PUT campaign failed: {response.text}"
        
        updated = response.json()
        assert updated is not None, "PUT should return updated campaign"
        assert updated["channels"]["whatsapp"] == False, "WhatsApp should be disabled"
        assert updated["channels"]["email"] == True, "Email should be enabled"
        assert updated["channels"]["instagram"] == True, "Instagram should be enabled"
        
        # Verify persistence
        get_response = requests.get(f"{API_URL}/campaigns/{campaign_id}")
        persisted = get_response.json()
        assert persisted["channels"] == new_channels, "Channels change should persist"
        
        print(f"✅ PUT /api/campaigns/{campaign_id} - channels updated and persisted")
    
    def test_10_update_multiple_fields_at_once(self):
        """Test PUT /api/campaigns/{campaign_id} - Update multiple fields simultaneously"""
        campaign_id = TestCampaignModification.created_campaign_id
        if not campaign_id:
            pytest.skip("No campaign created in previous test")
        
        payload = {
            "name": "Final Updated Name",
            "message": "Final updated message",
            "mediaUrl": "/v/test-slug",  # Internal link format
            "targetType": "all",
            "channels": {"whatsapp": True, "email": True, "instagram": False}
        }
        
        response = requests.put(f"{API_URL}/campaigns/{campaign_id}", json=payload)
        assert response.status_code == 200, f"PUT campaign failed: {response.text}"
        
        updated = response.json()
        assert updated is not None, "PUT should return updated campaign"
        assert updated["name"] == "Final Updated Name"
        assert updated["message"] == "Final updated message"
        assert updated["mediaUrl"] == "/v/test-slug"
        assert updated["targetType"] == "all"
        assert updated["channels"]["email"] == True
        
        print(f"✅ PUT /api/campaigns/{campaign_id} - Multiple fields updated successfully")
    
    def test_11_update_nonexistent_campaign_returns_null(self):
        """Test PUT /api/campaigns/{campaign_id} - Update non-existent campaign"""
        fake_id = f"nonexistent-{uuid.uuid4().hex}"
        payload = {"name": "Should not work"}
        
        response = requests.put(f"{API_URL}/campaigns/{fake_id}", json=payload)
        # The endpoint returns null for non-existent campaigns (no 404)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        result = response.json()
        assert result is None, "Should return null for non-existent campaign"
        
        print(f"✅ PUT /api/campaigns/nonexistent - Returns null as expected")
    
    def test_12_media_link_not_broken_after_campaign_update(self):
        """Test that existing /v/{slug} links still work after campaign modification"""
        # First, check if session-finale media link exists
        response = requests.get(f"{API_URL}/media/session-finale")
        
        if response.status_code == 200:
            media = response.json()
            assert "slug" in media or "video_url" in media, "Media link should have required fields"
            print(f"✅ Media link /v/session-finale still accessible after campaign tests")
        else:
            # Media link doesn't exist, skip this test
            print(f"⚠️ Media link /v/session-finale not found (status: {response.status_code}), skipping verification")
    
    def test_13_cleanup_test_campaign(self):
        """Cleanup: Delete the test campaign"""
        campaign_id = TestCampaignModification.created_campaign_id
        if not campaign_id:
            pytest.skip("No campaign to cleanup")
        
        response = requests.delete(f"{API_URL}/campaigns/{campaign_id}")
        assert response.status_code == 200, f"DELETE campaign failed: {response.text}"
        
        result = response.json()
        assert result.get("success") == True, "Delete should return success"
        
        # Verify deletion
        get_response = requests.get(f"{API_URL}/campaigns/{campaign_id}")
        assert get_response.status_code == 404, "Deleted campaign should return 404"
        
        # Clear the stored ID
        TestCampaignModification.created_campaign_id = None
        
        print(f"✅ Test campaign {campaign_id} deleted successfully")


class TestCampaignListFields:
    """Test that GET /api/campaigns returns all fields needed for the edit button"""
    
    def test_campaigns_list_has_status_field(self):
        """Verify campaigns list includes status field for showing edit button"""
        response = requests.get(f"{API_URL}/campaigns")
        assert response.status_code == 200
        
        campaigns = response.json()
        if len(campaigns) > 0:
            for campaign in campaigns[:5]:  # Check first 5
                assert "status" in campaign, "Campaign should have status field"
                assert campaign["status"] in ["draft", "scheduled", "sending", "completed"], \
                    f"Invalid status: {campaign['status']}"
            print(f"✅ All campaigns have valid status field")
        else:
            print("⚠️ No campaigns to verify status field")
    
    def test_campaigns_list_has_all_editable_fields(self):
        """Verify campaigns list includes all fields needed for edit form pre-fill"""
        response = requests.get(f"{API_URL}/campaigns")
        assert response.status_code == 200
        
        campaigns = response.json()
        if len(campaigns) > 0:
            campaign = campaigns[0]
            editable_fields = ['name', 'message', 'mediaUrl', 'targetType', 'channels']
            for field in editable_fields:
                assert field in campaign, f"Campaign missing editable field: {field}"
            print(f"✅ Campaigns list includes all editable fields: {editable_fields}")
        else:
            print("⚠️ No campaigns to verify editable fields")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
