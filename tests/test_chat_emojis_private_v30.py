"""
Test Suite for Afroboost Chat Features v30
- Custom Emojis CRUD (upload, list, delete)
- Private Chat from Community (start-private)
- Session Participants endpoint
"""

import pytest
import requests
import os
import base64
import uuid

# Use the public API URL from environment
BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://video-feed-platform.preview.emergentagent.com').rstrip('/')


class TestHealthCheck:
    """Basic health check to ensure API is running"""
    
    def test_health_endpoint(self):
        """Test /api/health returns 200"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "healthy"
        print("✅ Health check passed")


class TestCustomEmojis:
    """Test custom emoji CRUD operations"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test data"""
        self.created_emoji_ids = []
        yield
        # Cleanup: delete created emojis
        for emoji_id in self.created_emoji_ids:
            try:
                requests.delete(f"{BASE_URL}/api/chat/emojis/{emoji_id}")
            except:
                pass
    
    def test_get_emojis_list(self):
        """GET /api/chat/emojis - list all custom emojis"""
        response = requests.get(f"{BASE_URL}/api/chat/emojis")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✅ GET /api/chat/emojis - returned {len(data)} emojis")
    
    def test_upload_emoji_success(self):
        """POST /api/chat/emojis - upload a custom emoji"""
        # Create a small test image (1x1 red pixel PNG in base64)
        test_image_base64 = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg=="
        
        payload = {
            "name": f"TEST_emoji_{uuid.uuid4().hex[:6]}",
            "image_data": test_image_base64,
            "category": "test"
        }
        
        response = requests.post(f"{BASE_URL}/api/chat/emojis", json=payload)
        assert response.status_code == 200
        data = response.json()
        
        # Validate response structure
        assert "id" in data
        assert data["name"] == payload["name"]
        assert data["image_data"] == payload["image_data"]
        assert data["category"] == "test"
        assert data["active"] == True
        assert "created_at" in data
        
        self.created_emoji_ids.append(data["id"])
        print(f"✅ POST /api/chat/emojis - emoji created with id: {data['id']}")
        
        return data["id"]
    
    def test_upload_emoji_missing_name(self):
        """POST /api/chat/emojis - should fail without name"""
        payload = {
            "image_data": "data:image/png;base64,test"
        }
        
        response = requests.post(f"{BASE_URL}/api/chat/emojis", json=payload)
        assert response.status_code == 400
        print("✅ POST /api/chat/emojis - correctly rejects missing name")
    
    def test_upload_emoji_missing_image(self):
        """POST /api/chat/emojis - should fail without image_data"""
        payload = {
            "name": "test_emoji"
        }
        
        response = requests.post(f"{BASE_URL}/api/chat/emojis", json=payload)
        assert response.status_code == 400
        print("✅ POST /api/chat/emojis - correctly rejects missing image_data")
    
    def test_upload_emoji_invalid_format(self):
        """POST /api/chat/emojis - should fail with invalid image format"""
        payload = {
            "name": "test_emoji",
            "image_data": "not_a_valid_base64_image"
        }
        
        response = requests.post(f"{BASE_URL}/api/chat/emojis", json=payload)
        assert response.status_code == 400
        print("✅ POST /api/chat/emojis - correctly rejects invalid image format")
    
    def test_delete_emoji_success(self):
        """DELETE /api/chat/emojis/{id} - delete an emoji"""
        # First create an emoji
        test_image_base64 = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg=="
        
        create_response = requests.post(f"{BASE_URL}/api/chat/emojis", json={
            "name": f"TEST_delete_{uuid.uuid4().hex[:6]}",
            "image_data": test_image_base64,
            "category": "test"
        })
        assert create_response.status_code == 200
        emoji_id = create_response.json()["id"]
        
        # Now delete it
        delete_response = requests.delete(f"{BASE_URL}/api/chat/emojis/{emoji_id}")
        assert delete_response.status_code == 200
        data = delete_response.json()
        assert data["success"] == True
        print(f"✅ DELETE /api/chat/emojis/{emoji_id} - emoji deleted successfully")
        
        # Verify it's gone from the list
        list_response = requests.get(f"{BASE_URL}/api/chat/emojis")
        emojis = list_response.json()
        assert not any(e["id"] == emoji_id for e in emojis)
        print("✅ Verified emoji no longer in list after deletion")
    
    def test_delete_emoji_not_found(self):
        """DELETE /api/chat/emojis/{id} - should return 404 for non-existent emoji"""
        fake_id = f"fake_{uuid.uuid4().hex}"
        response = requests.delete(f"{BASE_URL}/api/chat/emojis/{fake_id}")
        assert response.status_code == 404
        print("✅ DELETE /api/chat/emojis - correctly returns 404 for non-existent emoji")


class TestPrivateChat:
    """Test private chat creation from community"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test participants"""
        self.created_participant_ids = []
        self.created_session_ids = []
        yield
        # Cleanup
        for pid in self.created_participant_ids:
            try:
                requests.delete(f"{BASE_URL}/api/chat/participants/{pid}")
            except:
                pass
        for sid in self.created_session_ids:
            try:
                requests.put(f"{BASE_URL}/api/chat/sessions/{sid}", json={"is_deleted": True})
            except:
                pass
    
    def _create_test_participant(self, name_suffix):
        """Helper to create a test participant"""
        payload = {
            "name": f"TEST_User_{name_suffix}",
            "email": f"test_{name_suffix}@example.com",
            "whatsapp": f"+4179000{name_suffix}",
            "source": "test_private_chat"
        }
        response = requests.post(f"{BASE_URL}/api/chat/participants", json=payload)
        assert response.status_code == 200
        data = response.json()
        self.created_participant_ids.append(data["id"])
        return data
    
    def test_start_private_chat_success(self):
        """POST /api/chat/start-private - create private chat between 2 participants"""
        # Create two test participants
        initiator = self._create_test_participant(uuid.uuid4().hex[:6])
        target = self._create_test_participant(uuid.uuid4().hex[:6])
        
        # Start private chat
        payload = {
            "initiator_id": initiator["id"],
            "target_id": target["id"],
            "community_session_id": "test_community"
        }
        
        response = requests.post(f"{BASE_URL}/api/chat/start-private", json=payload)
        assert response.status_code == 200
        data = response.json()
        
        # Validate response
        assert "session" in data
        assert data["is_new"] == True
        assert "message" in data
        
        session = data["session"]
        assert session["mode"] == "human"
        assert session["is_ai_active"] == False
        assert initiator["id"] in session["participant_ids"]
        assert target["id"] in session["participant_ids"]
        
        self.created_session_ids.append(session["id"])
        print(f"✅ POST /api/chat/start-private - private session created: {session['id']}")
    
    def test_start_private_chat_existing_session(self):
        """POST /api/chat/start-private - should return existing session if already exists"""
        # Create two test participants
        initiator = self._create_test_participant(uuid.uuid4().hex[:6])
        target = self._create_test_participant(uuid.uuid4().hex[:6])
        
        # Start private chat first time
        payload = {
            "initiator_id": initiator["id"],
            "target_id": target["id"]
        }
        
        response1 = requests.post(f"{BASE_URL}/api/chat/start-private", json=payload)
        assert response1.status_code == 200
        data1 = response1.json()
        assert data1["is_new"] == True
        session_id = data1["session"]["id"]
        self.created_session_ids.append(session_id)
        
        # Start private chat second time - should return existing
        response2 = requests.post(f"{BASE_URL}/api/chat/start-private", json=payload)
        assert response2.status_code == 200
        data2 = response2.json()
        assert data2["is_new"] == False
        assert data2["session"]["id"] == session_id
        print("✅ POST /api/chat/start-private - correctly returns existing session")
    
    def test_start_private_chat_missing_initiator(self):
        """POST /api/chat/start-private - should fail without initiator_id"""
        payload = {
            "target_id": "some_id"
        }
        
        response = requests.post(f"{BASE_URL}/api/chat/start-private", json=payload)
        assert response.status_code == 400
        print("✅ POST /api/chat/start-private - correctly rejects missing initiator_id")
    
    def test_start_private_chat_missing_target(self):
        """POST /api/chat/start-private - should fail without target_id"""
        payload = {
            "initiator_id": "some_id"
        }
        
        response = requests.post(f"{BASE_URL}/api/chat/start-private", json=payload)
        assert response.status_code == 400
        print("✅ POST /api/chat/start-private - correctly rejects missing target_id")
    
    def test_start_private_chat_invalid_participant(self):
        """POST /api/chat/start-private - should fail with non-existent participant"""
        payload = {
            "initiator_id": f"fake_{uuid.uuid4().hex}",
            "target_id": f"fake_{uuid.uuid4().hex}"
        }
        
        response = requests.post(f"{BASE_URL}/api/chat/start-private", json=payload)
        assert response.status_code == 404
        print("✅ POST /api/chat/start-private - correctly returns 404 for non-existent participants")


class TestSessionParticipants:
    """Test session participants endpoint"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test data"""
        self.created_participant_ids = []
        self.created_session_ids = []
        yield
        # Cleanup
        for pid in self.created_participant_ids:
            try:
                requests.delete(f"{BASE_URL}/api/chat/participants/{pid}")
            except:
                pass
        for sid in self.created_session_ids:
            try:
                requests.put(f"{BASE_URL}/api/chat/sessions/{sid}", json={"is_deleted": True})
            except:
                pass
    
    def test_get_session_participants(self):
        """GET /api/chat/sessions/{id}/participants - list participants of a session"""
        # Create two participants
        p1_response = requests.post(f"{BASE_URL}/api/chat/participants", json={
            "name": f"TEST_P1_{uuid.uuid4().hex[:6]}",
            "email": f"p1_{uuid.uuid4().hex[:6]}@test.com",
            "source": "test"
        })
        p1 = p1_response.json()
        self.created_participant_ids.append(p1["id"])
        
        p2_response = requests.post(f"{BASE_URL}/api/chat/participants", json={
            "name": f"TEST_P2_{uuid.uuid4().hex[:6]}",
            "email": f"p2_{uuid.uuid4().hex[:6]}@test.com",
            "source": "test"
        })
        p2 = p2_response.json()
        self.created_participant_ids.append(p2["id"])
        
        # Create a private session between them
        private_response = requests.post(f"{BASE_URL}/api/chat/start-private", json={
            "initiator_id": p1["id"],
            "target_id": p2["id"]
        })
        session = private_response.json()["session"]
        self.created_session_ids.append(session["id"])
        
        # Get session participants
        response = requests.get(f"{BASE_URL}/api/chat/sessions/{session['id']}/participants")
        assert response.status_code == 200
        participants = response.json()
        
        assert isinstance(participants, list)
        assert len(participants) == 2
        
        participant_ids = [p["id"] for p in participants]
        assert p1["id"] in participant_ids
        assert p2["id"] in participant_ids
        
        # Validate participant structure
        for p in participants:
            assert "id" in p
            assert "name" in p
        
        print(f"✅ GET /api/chat/sessions/{session['id']}/participants - returned {len(participants)} participants")
    
    def test_get_session_participants_not_found(self):
        """GET /api/chat/sessions/{id}/participants - should return 404 for non-existent session"""
        fake_id = f"fake_{uuid.uuid4().hex}"
        response = requests.get(f"{BASE_URL}/api/chat/sessions/{fake_id}/participants")
        assert response.status_code == 404
        print("✅ GET /api/chat/sessions/{id}/participants - correctly returns 404 for non-existent session")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
