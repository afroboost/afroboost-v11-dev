"""
Test Event Poster Feature - Backend API Tests
Tests for eventPosterEnabled and eventPosterMediaUrl in Concept model
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://video-feed-platform.preview.emergentagent.com')

class TestEventPosterAPI:
    """Tests for Event Poster feature in Concept API"""
    
    def test_health_check(self):
        """Test API health endpoint"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        print("✅ Health check passed")
    
    def test_get_concept_has_event_poster_fields(self):
        """Test that concept includes eventPosterEnabled and eventPosterMediaUrl fields"""
        response = requests.get(f"{BASE_URL}/api/concept")
        assert response.status_code == 200
        data = response.json()
        
        # Check eventPosterEnabled field exists
        assert "eventPosterEnabled" in data, "eventPosterEnabled field missing from concept"
        assert isinstance(data["eventPosterEnabled"], bool), "eventPosterEnabled should be boolean"
        print(f"✅ eventPosterEnabled: {data['eventPosterEnabled']}")
        
        # Check eventPosterMediaUrl field exists
        assert "eventPosterMediaUrl" in data, "eventPosterMediaUrl field missing from concept"
        assert isinstance(data["eventPosterMediaUrl"], str), "eventPosterMediaUrl should be string"
        print(f"✅ eventPosterMediaUrl: {data['eventPosterMediaUrl'][:50]}..." if len(data.get('eventPosterMediaUrl', '')) > 50 else f"✅ eventPosterMediaUrl: {data.get('eventPosterMediaUrl', '')}")
    
    def test_update_concept_event_poster_enabled(self):
        """Test updating eventPosterEnabled field"""
        # Get current state
        response = requests.get(f"{BASE_URL}/api/concept")
        assert response.status_code == 200
        original_data = response.json()
        original_enabled = original_data.get("eventPosterEnabled", False)
        
        # Toggle the value
        new_enabled = not original_enabled
        update_response = requests.put(
            f"{BASE_URL}/api/concept",
            json={"eventPosterEnabled": new_enabled}
        )
        assert update_response.status_code == 200
        updated_data = update_response.json()
        assert updated_data["eventPosterEnabled"] == new_enabled
        print(f"✅ Updated eventPosterEnabled to: {new_enabled}")
        
        # Restore original value
        restore_response = requests.put(
            f"{BASE_URL}/api/concept",
            json={"eventPosterEnabled": original_enabled}
        )
        assert restore_response.status_code == 200
        print(f"✅ Restored eventPosterEnabled to: {original_enabled}")
    
    def test_update_concept_event_poster_media_url(self):
        """Test updating eventPosterMediaUrl field"""
        # Get current state
        response = requests.get(f"{BASE_URL}/api/concept")
        assert response.status_code == 200
        original_data = response.json()
        original_url = original_data.get("eventPosterMediaUrl", "")
        
        # Update with test URL
        test_url = "https://images.unsplash.com/photo-test-event-poster"
        update_response = requests.put(
            f"{BASE_URL}/api/concept",
            json={"eventPosterMediaUrl": test_url}
        )
        assert update_response.status_code == 200
        updated_data = update_response.json()
        assert updated_data["eventPosterMediaUrl"] == test_url
        print(f"✅ Updated eventPosterMediaUrl to test URL")
        
        # Restore original value
        restore_response = requests.put(
            f"{BASE_URL}/api/concept",
            json={"eventPosterMediaUrl": original_url}
        )
        assert restore_response.status_code == 200
        print(f"✅ Restored eventPosterMediaUrl")
    
    def test_concept_supports_youtube_url(self):
        """Test that concept can store YouTube URLs for event poster"""
        youtube_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        
        # Get current state
        response = requests.get(f"{BASE_URL}/api/concept")
        original_url = response.json().get("eventPosterMediaUrl", "")
        
        # Update with YouTube URL
        update_response = requests.put(
            f"{BASE_URL}/api/concept",
            json={"eventPosterMediaUrl": youtube_url}
        )
        assert update_response.status_code == 200
        updated_data = update_response.json()
        assert updated_data["eventPosterMediaUrl"] == youtube_url
        print(f"✅ YouTube URL stored successfully")
        
        # Restore original
        requests.put(f"{BASE_URL}/api/concept", json={"eventPosterMediaUrl": original_url})
    
    def test_concept_supports_vimeo_url(self):
        """Test that concept can store Vimeo URLs for event poster"""
        vimeo_url = "https://vimeo.com/123456789"
        
        # Get current state
        response = requests.get(f"{BASE_URL}/api/concept")
        original_url = response.json().get("eventPosterMediaUrl", "")
        
        # Update with Vimeo URL
        update_response = requests.put(
            f"{BASE_URL}/api/concept",
            json={"eventPosterMediaUrl": vimeo_url}
        )
        assert update_response.status_code == 200
        updated_data = update_response.json()
        assert updated_data["eventPosterMediaUrl"] == vimeo_url
        print(f"✅ Vimeo URL stored successfully")
        
        # Restore original
        requests.put(f"{BASE_URL}/api/concept", json={"eventPosterMediaUrl": original_url})


class TestCoachAuth:
    """Test Coach authentication for accessing Event Poster settings"""
    
    def test_coach_login_success(self):
        """Test coach login with valid credentials"""
        response = requests.post(
            f"{BASE_URL}/api/coach-auth/login",
            json={"email": "coach@afroboost.com", "password": "afroboost123"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        print("✅ Coach login successful")
    
    def test_coach_login_failure(self):
        """Test coach login with invalid credentials"""
        response = requests.post(
            f"{BASE_URL}/api/coach-auth/login",
            json={"email": "wrong@email.com", "password": "wrongpassword"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] == False
        print("✅ Coach login correctly rejected invalid credentials")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
