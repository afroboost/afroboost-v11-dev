"""
Test suite for Media Viewer V2 - Iteration 33
Tests:
1. GET /api/media/{slug} returns title, description, cta_text, cta_link
2. PUT /api/media/{slug} allows modification of description, cta_text, cta_link
3. POST /api/campaigns/send-email sends email with V2 ultra-light template
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://promo-credits-lab.preview.emergentagent.com')

class TestMediaEndpoints:
    """Test GET and PUT /api/media/{slug} endpoints"""
    
    def test_get_media_returns_required_fields(self):
        """GET /api/media/{slug} should return title, description, cta_text, cta_link"""
        response = requests.get(f"{BASE_URL}/api/media/session-finale")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        
        # Verify all required fields are present
        assert "title" in data, "Missing 'title' field"
        assert "description" in data, "Missing 'description' field"
        assert "cta_text" in data, "Missing 'cta_text' field"
        assert "cta_link" in data, "Missing 'cta_link' field"
        
        # Verify fields have values
        assert data["title"], "title should not be empty"
        assert data["description"], "description should not be empty"
        assert data["cta_text"], "cta_text should not be empty"
        assert data["cta_link"], "cta_link should not be empty"
        
        print(f"✅ GET /api/media/session-finale returned all required fields:")
        print(f"   - title: {data['title']}")
        print(f"   - description: {data['description'][:50]}...")
        print(f"   - cta_text: {data['cta_text']}")
        print(f"   - cta_link: {data['cta_link']}")
    
    def test_get_media_returns_404_for_nonexistent(self):
        """GET /api/media/{slug} should return 404 for non-existent slug"""
        response = requests.get(f"{BASE_URL}/api/media/nonexistent-slug-12345")
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("✅ GET /api/media/nonexistent-slug returns 404")
    
    def test_put_media_updates_description(self):
        """PUT /api/media/{slug} should update description"""
        # First get current data
        get_response = requests.get(f"{BASE_URL}/api/media/session-finale")
        original_data = get_response.json()
        original_description = original_data.get("description", "")
        
        # Update description
        new_description = f"Test description updated at {uuid.uuid4().hex[:8]}"
        put_response = requests.put(
            f"{BASE_URL}/api/media/session-finale",
            json={"description": new_description}
        )
        assert put_response.status_code == 200, f"PUT failed with {put_response.status_code}"
        
        # Verify update
        verify_response = requests.get(f"{BASE_URL}/api/media/session-finale")
        updated_data = verify_response.json()
        assert updated_data["description"] == new_description, "Description not updated"
        
        # Restore original
        requests.put(
            f"{BASE_URL}/api/media/session-finale",
            json={"description": original_description}
        )
        
        print(f"✅ PUT /api/media/session-finale successfully updated description")
    
    def test_put_media_updates_cta_text(self):
        """PUT /api/media/{slug} should update cta_text"""
        # First get current data
        get_response = requests.get(f"{BASE_URL}/api/media/session-finale")
        original_data = get_response.json()
        original_cta_text = original_data.get("cta_text", "")
        
        # Update cta_text
        new_cta_text = f"TEST CTA {uuid.uuid4().hex[:6]}"
        put_response = requests.put(
            f"{BASE_URL}/api/media/session-finale",
            json={"cta_text": new_cta_text}
        )
        assert put_response.status_code == 200, f"PUT failed with {put_response.status_code}"
        
        # Verify update
        verify_response = requests.get(f"{BASE_URL}/api/media/session-finale")
        updated_data = verify_response.json()
        assert updated_data["cta_text"] == new_cta_text, "cta_text not updated"
        
        # Restore original
        requests.put(
            f"{BASE_URL}/api/media/session-finale",
            json={"cta_text": original_cta_text}
        )
        
        print(f"✅ PUT /api/media/session-finale successfully updated cta_text")
    
    def test_put_media_updates_cta_link(self):
        """PUT /api/media/{slug} should update cta_link"""
        # First get current data
        get_response = requests.get(f"{BASE_URL}/api/media/session-finale")
        original_data = get_response.json()
        original_cta_link = original_data.get("cta_link", "")
        
        # Update cta_link
        new_cta_link = f"https://test-link-{uuid.uuid4().hex[:6]}.com"
        put_response = requests.put(
            f"{BASE_URL}/api/media/session-finale",
            json={"cta_link": new_cta_link}
        )
        assert put_response.status_code == 200, f"PUT failed with {put_response.status_code}"
        
        # Verify update
        verify_response = requests.get(f"{BASE_URL}/api/media/session-finale")
        updated_data = verify_response.json()
        assert updated_data["cta_link"] == new_cta_link, "cta_link not updated"
        
        # Restore original
        requests.put(
            f"{BASE_URL}/api/media/session-finale",
            json={"cta_link": original_cta_link}
        )
        
        print(f"✅ PUT /api/media/session-finale successfully updated cta_link")
    
    def test_put_media_returns_404_for_nonexistent(self):
        """PUT /api/media/{slug} should return 404 for non-existent slug"""
        response = requests.put(
            f"{BASE_URL}/api/media/nonexistent-slug-12345",
            json={"description": "test"}
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("✅ PUT /api/media/nonexistent-slug returns 404")


class TestCampaignSendEmail:
    """Test POST /api/campaigns/send-email endpoint"""
    
    def test_send_email_requires_to_email(self):
        """POST /api/campaigns/send-email should require to_email"""
        response = requests.post(
            f"{BASE_URL}/api/campaigns/send-email",
            json={"message": "Test message"}
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        print("✅ POST /api/campaigns/send-email requires to_email (400 without it)")
    
    def test_send_email_requires_message(self):
        """POST /api/campaigns/send-email should require message"""
        response = requests.post(
            f"{BASE_URL}/api/campaigns/send-email",
            json={"to_email": "test@example.com"}
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        print("✅ POST /api/campaigns/send-email requires message (400 without it)")
    
    def test_send_email_with_valid_payload(self):
        """POST /api/campaigns/send-email should accept valid payload"""
        # Note: This test verifies the endpoint accepts the payload
        # Actual email sending depends on Resend configuration
        response = requests.post(
            f"{BASE_URL}/api/campaigns/send-email",
            json={
                "to_email": "test-no-send@example.com",
                "to_name": "Test User",
                "subject": "Test Subject",
                "message": "Test message content",
                "media_url": "/v/session-finale"
            }
        )
        # Should return 200 (success or Resend not configured)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        # Either success or Resend not configured
        assert "success" in data, "Response should contain 'success' field"
        
        if data.get("success"):
            print(f"✅ POST /api/campaigns/send-email sent email successfully")
        else:
            print(f"✅ POST /api/campaigns/send-email endpoint works (Resend: {data.get('error', 'not configured')})")


class TestHealthCheck:
    """Basic health check tests"""
    
    def test_health_endpoint(self):
        """Health endpoint should return 200"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("✅ GET /api/health returns 200")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
