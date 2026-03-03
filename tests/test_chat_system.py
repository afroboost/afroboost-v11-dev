"""
Test suite for Enhanced Chat System APIs
Tests: smart-entry, generate-link, toggle-ai, participants, sessions, coach-response
"""
import pytest
import requests
import os
import uuid

# Get BASE_URL from environment
BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
if not BASE_URL:
    BASE_URL = "https://promo-credits-lab.preview.emergentagent.com"

class TestChatSmartEntry:
    """Tests for /api/chat/smart-entry - intelligent entry point with user recognition"""
    
    def test_smart_entry_new_user(self):
        """Test smart entry with a new user - should create participant and session"""
        unique_email = f"test_new_{uuid.uuid4().hex[:8]}@example.com"
        payload = {
            "name": "Test New User",
            "email": unique_email,
            "whatsapp": "+41791234567"
        }
        
        response = requests.post(f"{BASE_URL}/api/chat/smart-entry", json=payload)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "participant" in data, "Response should contain participant"
        assert "session" in data, "Response should contain session"
        assert "is_returning" in data, "Response should contain is_returning flag"
        assert "message" in data, "Response should contain welcome message"
        
        # New user should not be returning
        assert data["is_returning"] == False, "New user should not be marked as returning"
        
        # Verify participant data
        participant = data["participant"]
        assert participant["name"] == "Test New User"
        assert participant["email"] == unique_email
        assert "id" in participant
        
        # Verify session data
        session = data["session"]
        assert "id" in session
        assert session["mode"] == "ai"
        assert session["is_ai_active"] == True
        
        print(f"✅ Smart entry new user: participant_id={participant['id']}, session_id={session['id']}")
        
        return participant, session
    
    def test_smart_entry_returning_user(self):
        """Test smart entry with returning user - should recognize and return history"""
        # First, create a user
        unique_email = f"test_return_{uuid.uuid4().hex[:8]}@example.com"
        payload = {
            "name": "Test Returning User",
            "email": unique_email,
            "whatsapp": "+41791234568"
        }
        
        # First entry
        response1 = requests.post(f"{BASE_URL}/api/chat/smart-entry", json=payload)
        assert response1.status_code == 200
        data1 = response1.json()
        assert data1["is_returning"] == False
        
        # Second entry with same email - should be recognized
        response2 = requests.post(f"{BASE_URL}/api/chat/smart-entry", json=payload)
        assert response2.status_code == 200
        
        data2 = response2.json()
        assert data2["is_returning"] == True, "User should be recognized as returning"
        assert "Ravi de te revoir" in data2["message"], "Welcome message should indicate returning user"
        
        # Should have same participant ID
        assert data1["participant"]["id"] == data2["participant"]["id"], "Same participant should be returned"
        
        print(f"✅ Smart entry returning user recognized: {data2['participant']['name']}")
    
    def test_smart_entry_with_link_token(self):
        """Test smart entry via shareable link"""
        # First generate a link
        link_response = requests.post(f"{BASE_URL}/api/chat/generate-link", json={"title": "Test Link"})
        assert link_response.status_code == 200
        link_data = link_response.json()
        link_token = link_data["link_token"]
        
        # Now use smart entry with the link token
        unique_email = f"test_link_{uuid.uuid4().hex[:8]}@example.com"
        payload = {
            "name": "Test Link User",
            "email": unique_email,
            "link_token": link_token
        }
        
        response = requests.post(f"{BASE_URL}/api/chat/smart-entry", json=payload)
        assert response.status_code == 200
        
        data = response.json()
        # Should use the session from the link
        assert data["session"]["link_token"] == link_token, "Should use session from link"
        
        print(f"✅ Smart entry with link token: session uses link {link_token}")
    
    def test_smart_entry_missing_name(self):
        """Test smart entry without name - should fail"""
        payload = {
            "email": "test@example.com"
        }
        
        response = requests.post(f"{BASE_URL}/api/chat/smart-entry", json=payload)
        assert response.status_code == 400, "Should fail without name"
        
        print("✅ Smart entry correctly rejects missing name")


class TestChatGenerateLink:
    """Tests for /api/chat/generate-link - shareable link generation"""
    
    def test_generate_link_basic(self):
        """Test basic link generation"""
        payload = {"title": "Test Chat Link"}
        
        response = requests.post(f"{BASE_URL}/api/chat/generate-link", json=payload)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "link_token" in data, "Response should contain link_token"
        assert "share_url" in data, "Response should contain share_url"
        assert "session_id" in data, "Response should contain session_id"
        
        # Link token should be a short unique string
        assert len(data["link_token"]) >= 8, "Link token should be at least 8 chars"
        
        print(f"✅ Generated link: token={data['link_token']}, url={data['share_url']}")
        
        return data
    
    def test_generate_link_without_title(self):
        """Test link generation without title - should use default"""
        response = requests.post(f"{BASE_URL}/api/chat/generate-link", json={})
        
        assert response.status_code == 200
        data = response.json()
        assert "link_token" in data
        
        print("✅ Link generated without title (uses default)")
    
    def test_get_all_links(self):
        """Test retrieving all chat links"""
        # First create a link
        requests.post(f"{BASE_URL}/api/chat/generate-link", json={"title": "Test Link for List"})
        
        response = requests.get(f"{BASE_URL}/api/chat/links")
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list), "Should return a list of links"
        
        if len(data) > 0:
            link = data[0]
            assert "link_token" in link
            assert "title" in link or link.get("title") is None
            
        print(f"✅ Retrieved {len(data)} chat links")


class TestChatToggleAI:
    """Tests for /api/chat/sessions/{id}/toggle-ai - AI mode toggle"""
    
    def test_toggle_ai_mode(self):
        """Test toggling AI mode on a session"""
        # First create a session via smart entry
        unique_email = f"test_toggle_{uuid.uuid4().hex[:8]}@example.com"
        entry_response = requests.post(f"{BASE_URL}/api/chat/smart-entry", json={
            "name": "Test Toggle User",
            "email": unique_email
        })
        assert entry_response.status_code == 200
        session_id = entry_response.json()["session"]["id"]
        initial_ai_state = entry_response.json()["session"]["is_ai_active"]
        
        # Toggle AI
        toggle_response = requests.post(f"{BASE_URL}/api/chat/sessions/{session_id}/toggle-ai")
        
        assert toggle_response.status_code == 200, f"Expected 200, got {toggle_response.status_code}"
        
        data = toggle_response.json()
        assert data["is_ai_active"] != initial_ai_state, "AI state should be toggled"
        
        # Mode should change accordingly
        expected_mode = "ai" if data["is_ai_active"] else "human"
        assert data["mode"] == expected_mode, f"Mode should be {expected_mode}"
        
        print(f"✅ AI toggled: is_ai_active={data['is_ai_active']}, mode={data['mode']}")
        
        # Toggle back
        toggle_back = requests.post(f"{BASE_URL}/api/chat/sessions/{session_id}/toggle-ai")
        assert toggle_back.status_code == 200
        assert toggle_back.json()["is_ai_active"] == initial_ai_state
        
        print("✅ AI toggled back to original state")
    
    def test_toggle_ai_invalid_session(self):
        """Test toggle AI with invalid session ID"""
        response = requests.post(f"{BASE_URL}/api/chat/sessions/invalid-session-id/toggle-ai")
        
        assert response.status_code == 404, "Should return 404 for invalid session"
        
        print("✅ Toggle AI correctly rejects invalid session")


class TestChatParticipants:
    """Tests for /api/chat/participants - CRM contacts"""
    
    def test_get_participants(self):
        """Test retrieving all chat participants"""
        response = requests.get(f"{BASE_URL}/api/chat/participants")
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list), "Should return a list"
        
        print(f"✅ Retrieved {len(data)} chat participants")
    
    def test_create_participant(self):
        """Test creating a new participant directly"""
        unique_email = f"test_create_{uuid.uuid4().hex[:8]}@example.com"
        payload = {
            "name": "Direct Create User",
            "email": unique_email,
            "whatsapp": "+41791234569",
            "source": "test_api"
        }
        
        response = requests.post(f"{BASE_URL}/api/chat/participants", json=payload)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert data["name"] == "Direct Create User"
        assert data["email"] == unique_email
        assert "id" in data
        
        print(f"✅ Created participant: {data['id']}")
        
        return data
    
    def test_get_participant_by_id(self):
        """Test retrieving a specific participant"""
        # First create one
        unique_email = f"test_get_{uuid.uuid4().hex[:8]}@example.com"
        create_response = requests.post(f"{BASE_URL}/api/chat/participants", json={
            "name": "Get By ID User",
            "email": unique_email
        })
        participant_id = create_response.json()["id"]
        
        # Now get it
        response = requests.get(f"{BASE_URL}/api/chat/participants/{participant_id}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == participant_id
        assert data["name"] == "Get By ID User"
        
        print(f"✅ Retrieved participant by ID: {participant_id}")


class TestChatSessions:
    """Tests for /api/chat/sessions - chat sessions management"""
    
    def test_get_sessions(self):
        """Test retrieving all chat sessions"""
        response = requests.get(f"{BASE_URL}/api/chat/sessions")
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list), "Should return a list"
        
        print(f"✅ Retrieved {len(data)} chat sessions")
    
    def test_create_session(self):
        """Test creating a new session directly"""
        payload = {
            "mode": "ai",
            "is_ai_active": True,
            "title": "Test Direct Session"
        }
        
        response = requests.post(f"{BASE_URL}/api/chat/sessions", json=payload)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert data["mode"] == "ai"
        assert data["is_ai_active"] == True
        assert "id" in data
        assert "link_token" in data
        
        print(f"✅ Created session: {data['id']}")
        
        return data
    
    def test_get_session_by_id(self):
        """Test retrieving a specific session"""
        # First create one
        create_response = requests.post(f"{BASE_URL}/api/chat/sessions", json={
            "mode": "ai",
            "title": "Get By ID Session"
        })
        session_id = create_response.json()["id"]
        
        # Now get it
        response = requests.get(f"{BASE_URL}/api/chat/sessions/{session_id}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == session_id
        
        print(f"✅ Retrieved session by ID: {session_id}")
    
    def test_get_session_by_token(self):
        """Test retrieving session by link token"""
        # Create via generate-link
        link_response = requests.post(f"{BASE_URL}/api/chat/generate-link", json={"title": "Token Test"})
        link_token = link_response.json()["link_token"]
        
        # Get by token
        response = requests.get(f"{BASE_URL}/api/chat/sessions/by-token/{link_token}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["link_token"] == link_token
        
        print(f"✅ Retrieved session by token: {link_token}")
    
    def test_update_session(self):
        """Test updating a session"""
        # Create session
        create_response = requests.post(f"{BASE_URL}/api/chat/sessions", json={
            "mode": "ai",
            "title": "Update Test Session"
        })
        session_id = create_response.json()["id"]
        
        # Update it
        update_payload = {
            "title": "Updated Title",
            "notes": "Test notes"
        }
        response = requests.put(f"{BASE_URL}/api/chat/sessions/{session_id}", json=update_payload)
        
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Updated Title"
        assert data["notes"] == "Test notes"
        
        print(f"✅ Updated session: {session_id}")


class TestChatCoachResponse:
    """Tests for /api/chat/coach-response - coach messaging"""
    
    def test_coach_response(self):
        """Test coach sending a message to a session"""
        # First create a session via smart entry
        unique_email = f"test_coach_{uuid.uuid4().hex[:8]}@example.com"
        entry_response = requests.post(f"{BASE_URL}/api/chat/smart-entry", json={
            "name": "Test Coach Response User",
            "email": unique_email
        })
        assert entry_response.status_code == 200
        session_id = entry_response.json()["session"]["id"]
        
        # Send coach response
        payload = {
            "session_id": session_id,
            "message": "Hello from coach!",
            "coach_name": "Test Coach"
        }
        
        response = requests.post(f"{BASE_URL}/api/chat/coach-response", json=payload)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "message_id" in data or "success" in data, "Response should indicate success"
        
        print(f"✅ Coach response sent to session: {session_id}")
    
    def test_coach_response_invalid_session(self):
        """Test coach response with invalid session"""
        payload = {
            "session_id": "invalid-session-id",
            "message": "Test message",
            "coach_name": "Coach"
        }
        
        response = requests.post(f"{BASE_URL}/api/chat/coach-response", json=payload)
        
        # Should fail with 404 or 400
        assert response.status_code in [400, 404], f"Should fail for invalid session, got {response.status_code}"
        
        print("✅ Coach response correctly rejects invalid session")


class TestChatMessages:
    """Tests for chat messages within sessions"""
    
    def test_get_session_messages(self):
        """Test retrieving messages from a session"""
        # Create session via smart entry
        unique_email = f"test_msg_{uuid.uuid4().hex[:8]}@example.com"
        entry_response = requests.post(f"{BASE_URL}/api/chat/smart-entry", json={
            "name": "Test Messages User",
            "email": unique_email
        })
        session_id = entry_response.json()["session"]["id"]
        
        # Get messages
        response = requests.get(f"{BASE_URL}/api/chat/sessions/{session_id}/messages")
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list), "Should return a list of messages"
        
        print(f"✅ Retrieved {len(data)} messages from session")


class TestHealthCheck:
    """Basic health check to ensure API is running"""
    
    def test_health_endpoint(self):
        """Test health endpoint"""
        response = requests.get(f"{BASE_URL}/api/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "healthy"
        
        print("✅ Health check passed")


# Run tests if executed directly
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
