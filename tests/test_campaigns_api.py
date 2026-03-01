"""
Afroboost Campaign API Tests - Testing Campaign Module
Tests: Campaign CRUD, Launch, Mark Sent
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://video-feed-platform.preview.emergentagent.com').rstrip('/')

@pytest.fixture(scope="session")
def api_client():
    """Shared requests session"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


class TestCampaigns:
    """Campaign CRUD and functionality tests"""
    
    def test_get_campaigns(self, api_client):
        """Test GET /api/campaigns"""
        response = api_client.get(f"{BASE_URL}/api/campaigns")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    
    def test_create_campaign_immediate(self, api_client):
        """Test creating an immediate campaign (no scheduledAt)"""
        campaign_data = {
            "name": f"TEST_Campaign_{uuid.uuid4().hex[:6]}",
            "message": "Salut {prénom}! Test message",
            "mediaUrl": "https://example.com/image.jpg",
            "mediaFormat": "16:9",
            "targetType": "all",
            "selectedContacts": [],
            "channels": {"whatsapp": True, "email": False, "instagram": False},
            "scheduledAt": None
        }
        response = api_client.post(f"{BASE_URL}/api/campaigns", json=campaign_data)
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert data["name"] == campaign_data["name"]
        assert data["message"] == campaign_data["message"]
        assert data["status"] == "draft"  # Immediate campaigns start as draft
        assert data["channels"]["whatsapp"] == True
        return data["id"]
    
    def test_create_campaign_scheduled(self, api_client):
        """Test creating a scheduled campaign"""
        campaign_data = {
            "name": f"TEST_Scheduled_{uuid.uuid4().hex[:6]}",
            "message": "Scheduled test message",
            "mediaUrl": "",
            "mediaFormat": "9:16",
            "targetType": "all",
            "selectedContacts": [],
            "channels": {"whatsapp": True, "email": True, "instagram": False},
            "scheduledAt": "2025-12-25T10:00:00"
        }
        response = api_client.post(f"{BASE_URL}/api/campaigns", json=campaign_data)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "scheduled"  # Scheduled campaigns have status "scheduled"
        assert data["scheduledAt"] == "2025-12-25T10:00:00"
        return data["id"]
    
    def test_get_single_campaign(self, api_client):
        """Test GET /api/campaigns/{id}"""
        # First create a campaign
        campaign_data = {
            "name": f"TEST_Single_{uuid.uuid4().hex[:6]}",
            "message": "Test single get",
            "mediaUrl": "",
            "mediaFormat": "16:9",
            "targetType": "all",
            "selectedContacts": [],
            "channels": {"whatsapp": True, "email": False, "instagram": False},
            "scheduledAt": None
        }
        create_response = api_client.post(f"{BASE_URL}/api/campaigns", json=campaign_data)
        campaign_id = create_response.json()["id"]
        
        # Get the campaign
        response = api_client.get(f"{BASE_URL}/api/campaigns/{campaign_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == campaign_id
        assert data["name"] == campaign_data["name"]
    
    def test_update_campaign(self, api_client):
        """Test PUT /api/campaigns/{id}"""
        # First create a campaign
        campaign_data = {
            "name": f"TEST_Update_{uuid.uuid4().hex[:6]}",
            "message": "Original message",
            "mediaUrl": "",
            "mediaFormat": "16:9",
            "targetType": "all",
            "selectedContacts": [],
            "channels": {"whatsapp": True, "email": False, "instagram": False},
            "scheduledAt": None
        }
        create_response = api_client.post(f"{BASE_URL}/api/campaigns", json=campaign_data)
        campaign_id = create_response.json()["id"]
        
        # Update the campaign
        update_data = {"message": "Updated message", "name": "Updated Name"}
        response = api_client.put(f"{BASE_URL}/api/campaigns/{campaign_id}", json=update_data)
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Updated message"
        assert data["name"] == "Updated Name"
    
    def test_launch_campaign(self, api_client):
        """Test POST /api/campaigns/{id}/launch"""
        # First create a campaign
        campaign_data = {
            "name": f"TEST_Launch_{uuid.uuid4().hex[:6]}",
            "message": "Launch test message",
            "mediaUrl": "https://example.com/video.mp4",
            "mediaFormat": "16:9",
            "targetType": "all",
            "selectedContacts": [],
            "channels": {"whatsapp": True, "email": False, "instagram": False},
            "scheduledAt": None
        }
        create_response = api_client.post(f"{BASE_URL}/api/campaigns", json=campaign_data)
        campaign_id = create_response.json()["id"]
        
        # Launch the campaign
        response = api_client.post(f"{BASE_URL}/api/campaigns/{campaign_id}/launch")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "sending"
        assert "results" in data
        assert isinstance(data["results"], list)
    
    def test_delete_campaign(self, api_client):
        """Test DELETE /api/campaigns/{id}"""
        # First create a campaign
        campaign_data = {
            "name": f"TEST_Delete_{uuid.uuid4().hex[:6]}",
            "message": "Delete test",
            "mediaUrl": "",
            "mediaFormat": "16:9",
            "targetType": "all",
            "selectedContacts": [],
            "channels": {"whatsapp": True, "email": False, "instagram": False},
            "scheduledAt": None
        }
        create_response = api_client.post(f"{BASE_URL}/api/campaigns", json=campaign_data)
        campaign_id = create_response.json()["id"]
        
        # Delete the campaign
        response = api_client.delete(f"{BASE_URL}/api/campaigns/{campaign_id}")
        assert response.status_code == 200
        
        # Verify deletion
        get_response = api_client.get(f"{BASE_URL}/api/campaigns/{campaign_id}")
        assert get_response.status_code == 404


class TestPhoneFormatting:
    """Test phone number formatting for WhatsApp links"""
    
    def test_swiss_phone_formats(self):
        """Test various Swiss phone number formats"""
        # These are the expected transformations based on formatPhoneForWhatsApp function
        test_cases = [
            # (input, expected_output)
            ("0765203363", "41765203363"),  # Swiss local format
            ("+41765203363", "41765203363"),  # With + prefix
            ("079 123 45 67", "41791234567"),  # With spaces
            ("079-123-45-67", "41791234567"),  # With dashes
            ("0041765203363", "41765203363"),  # With 0041 prefix
            ("41765203363", "41765203363"),  # Already formatted
        ]
        
        for input_phone, expected in test_cases:
            result = format_phone_for_whatsapp(input_phone)
            assert result == expected, f"Failed for {input_phone}: got {result}, expected {expected}"


def format_phone_for_whatsapp(phone):
    """Python implementation of formatPhoneForWhatsApp from frontend"""
    if not phone:
        return ''
    
    # 1. Remove ALL non-numeric characters first (spaces, dashes, dots, parentheses)
    import re
    cleaned = re.sub(r'[\s\-\.\(\)]', '', phone)
    
    # 2. Handle + prefix separately
    has_plus = cleaned.startswith('+')
    cleaned = re.sub(r'[^\d]', '', cleaned)  # Keep only digits
    
    # 3. Detect and normalize Swiss numbers
    if cleaned.startswith('0041'):
        # Format: 0041XXXXXXXXX -> 41XXXXXXXXX
        cleaned = cleaned[2:]
    elif cleaned.startswith('41') and len(cleaned) >= 11:
        # Already has country code 41
        pass
    elif cleaned.startswith('0') and (len(cleaned) == 10 or len(cleaned) == 9):
        # Swiss local format: 079XXXXXXX or 79XXXXXXX -> 4179XXXXXXX
        cleaned = '41' + cleaned[1:]
    elif not has_plus and len(cleaned) >= 9 and len(cleaned) <= 10 and not cleaned.startswith('41'):
        # Assume Swiss number without country code
        cleaned = '41' + cleaned
    
    # 4. Final validation - must have at least 10 digits for international
    if len(cleaned) < 10:
        return ''
    
    return cleaned


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
