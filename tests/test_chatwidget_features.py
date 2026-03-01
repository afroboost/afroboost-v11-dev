"""
Test ChatWidget Features - Client Memorization and Synchronization
Tests for:
1. User CRUD operations (including new PUT endpoint)
2. Lead creation from widget
3. Chat API functionality
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://video-feed-platform.preview.emergentagent.com').rstrip('/')


class TestUserCRUD:
    """Test User CRUD operations including the new PUT endpoint for contact sync"""
    
    def test_get_users(self):
        """Test GET /api/users returns list of users"""
        response = requests.get(f"{BASE_URL}/api/users")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✅ GET /api/users returned {len(data)} users")
    
    def test_create_user(self):
        """Test POST /api/users creates a new user"""
        unique_id = str(uuid.uuid4())[:8]
        payload = {
            "name": f"TEST_ChatWidget_{unique_id}",
            "email": f"test_chatwidget_{unique_id}@test.com",
            "whatsapp": "+41 79 000 00 00"
        }
        response = requests.post(f"{BASE_URL}/api/users", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == payload["name"]
        assert data["email"] == payload["email"]
        assert "id" in data
        print(f"✅ POST /api/users created user: {data['name']}")
        return data["id"]
    
    def test_get_user_by_id(self):
        """Test GET /api/users/{id} returns specific user"""
        # First create a user
        unique_id = str(uuid.uuid4())[:8]
        create_response = requests.post(f"{BASE_URL}/api/users", json={
            "name": f"TEST_GetById_{unique_id}",
            "email": f"test_getbyid_{unique_id}@test.com",
            "whatsapp": "+41 79 111 11 11"
        })
        user_id = create_response.json()["id"]
        
        # Then get by ID
        response = requests.get(f"{BASE_URL}/api/users/{user_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == user_id
        print(f"✅ GET /api/users/{user_id} returned correct user")
    
    def test_update_user(self):
        """Test PUT /api/users/{id} updates user - CRITICAL for ChatWidget sync"""
        # First create a user
        unique_id = str(uuid.uuid4())[:8]
        create_response = requests.post(f"{BASE_URL}/api/users", json={
            "name": f"TEST_Update_{unique_id}",
            "email": f"test_update_{unique_id}@test.com",
            "whatsapp": "+41 79 222 22 22"
        })
        user_id = create_response.json()["id"]
        original_email = create_response.json()["email"]
        
        # Update the user
        update_payload = {
            "name": f"TEST_Updated_{unique_id}",
            "email": original_email,  # Keep same email
            "whatsapp": "+41 79 333 33 33"  # Change whatsapp
        }
        response = requests.put(f"{BASE_URL}/api/users/{user_id}", json=update_payload)
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == update_payload["name"]
        assert data["whatsapp"] == update_payload["whatsapp"]
        print(f"✅ PUT /api/users/{user_id} updated user successfully")
        
        # Verify update persisted
        get_response = requests.get(f"{BASE_URL}/api/users/{user_id}")
        assert get_response.status_code == 200
        assert get_response.json()["name"] == update_payload["name"]
        print(f"✅ Update verified via GET")
    
    def test_delete_user(self):
        """Test DELETE /api/users/{id} removes user"""
        # First create a user
        unique_id = str(uuid.uuid4())[:8]
        create_response = requests.post(f"{BASE_URL}/api/users", json={
            "name": f"TEST_Delete_{unique_id}",
            "email": f"test_delete_{unique_id}@test.com",
            "whatsapp": "+41 79 444 44 44"
        })
        user_id = create_response.json()["id"]
        
        # Delete the user
        response = requests.delete(f"{BASE_URL}/api/users/{user_id}")
        assert response.status_code == 200
        print(f"✅ DELETE /api/users/{user_id} successful")
        
        # Verify deletion
        get_response = requests.get(f"{BASE_URL}/api/users/{user_id}")
        assert get_response.status_code == 404
        print(f"✅ User deletion verified (404 on GET)")


class TestLeadCapture:
    """Test Lead capture from ChatWidget"""
    
    def test_create_lead(self):
        """Test POST /api/leads creates a new lead"""
        unique_id = str(uuid.uuid4())[:8]
        payload = {
            "firstName": f"TEST_Lead_{unique_id}",
            "whatsapp": "+41 79 555 55 55",
            "email": f"test_lead_{unique_id}@test.com",
            "source": "widget_ia"
        }
        response = requests.post(f"{BASE_URL}/api/leads", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["firstName"] == payload["firstName"]
        assert "id" in data
        print(f"✅ POST /api/leads created lead: {data['firstName']}")
    
    def test_get_leads(self):
        """Test GET /api/leads returns list of leads"""
        response = requests.get(f"{BASE_URL}/api/leads")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✅ GET /api/leads returned {len(data)} leads")
    
    def test_lead_deduplication(self):
        """Test that leads with same email are updated, not duplicated"""
        unique_id = str(uuid.uuid4())[:8]
        email = f"test_dedup_{unique_id}@test.com"
        
        # Create first lead
        payload1 = {
            "firstName": "FirstName1",
            "whatsapp": "+41 79 666 66 66",
            "email": email,
            "source": "widget_ia"
        }
        response1 = requests.post(f"{BASE_URL}/api/leads", json=payload1)
        assert response1.status_code == 200
        
        # Create second lead with same email
        payload2 = {
            "firstName": "FirstName2",
            "whatsapp": "+41 79 666 66 66",
            "email": email,
            "source": "widget_ia"
        }
        response2 = requests.post(f"{BASE_URL}/api/leads", json=payload2)
        assert response2.status_code == 200
        
        # The second should update the first, not create duplicate
        data = response2.json()
        assert data["firstName"] == "FirstName2"
        print(f"✅ Lead deduplication working - updated to: {data['firstName']}")


class TestChatAPI:
    """Test Chat API for AI assistant"""
    
    def test_chat_endpoint(self):
        """Test POST /api/chat sends message to AI"""
        payload = {
            "message": "Bonjour, quels sont vos horaires ?",
            "firstName": "TestClient",
            "leadId": ""
        }
        response = requests.post(f"{BASE_URL}/api/chat", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert "response" in data
        print(f"✅ POST /api/chat returned AI response: {data['response'][:50]}...")
    
    def test_chat_with_empty_message(self):
        """Test chat endpoint rejects empty messages"""
        payload = {
            "message": "",
            "firstName": "TestClient",
            "leadId": ""
        }
        response = requests.post(f"{BASE_URL}/api/chat", json=payload)
        # Should return 400 or error response
        assert response.status_code in [400, 422] or "error" in response.json().get("response", "").lower()
        print(f"✅ Empty message handled correctly")


class TestHealthCheck:
    """Basic health check"""
    
    def test_health(self):
        """Test /api/health returns healthy status"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        print(f"✅ Health check passed: {data}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
