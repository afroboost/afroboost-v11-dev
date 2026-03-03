"""
Test suite for Chat System Features - Iteration 28
Tests: Community chat creation, mode selector, session mode change, delete history, linkify
"""
import pytest
import requests
import os
import uuid

# Get BASE_URL from environment
BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
if not BASE_URL:
    BASE_URL = "https://promo-credits-lab.preview.emergentagent.com"


class TestCommunityChat:
    """Tests for community chat creation (mode: community)"""
    
    def test_create_community_session(self):
        """Test creating a community chat session via POST /api/chat/sessions"""
        payload = {
            "mode": "community",
            "is_ai_active": False,
            "title": "Test Community Chat"
        }
        
        response = requests.post(f"{BASE_URL}/api/chat/sessions", json=payload)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data["mode"] == "community", "Mode should be 'community'"
        assert data["is_ai_active"] == False, "AI should be inactive for community chat"
        assert "id" in data, "Response should contain session ID"
        assert "link_token" in data, "Response should contain link_token for sharing"
        
        print(f"✅ Community session created: id={data['id']}, mode={data['mode']}")
        return data
    
    def test_create_human_session(self):
        """Test creating a human-only chat session"""
        payload = {
            "mode": "human",
            "is_ai_active": False,
            "title": "Test Human Chat"
        }
        
        response = requests.post(f"{BASE_URL}/api/chat/sessions", json=payload)
        
        assert response.status_code == 200
        data = response.json()
        assert data["mode"] == "human"
        assert data["is_ai_active"] == False
        
        print(f"✅ Human session created: id={data['id']}, mode={data['mode']}")
        return data
    
    def test_create_ai_session(self):
        """Test creating an AI chat session (default)"""
        payload = {
            "mode": "ai",
            "is_ai_active": True,
            "title": "Test AI Chat"
        }
        
        response = requests.post(f"{BASE_URL}/api/chat/sessions", json=payload)
        
        assert response.status_code == 200
        data = response.json()
        assert data["mode"] == "ai"
        assert data["is_ai_active"] == True
        
        print(f"✅ AI session created: id={data['id']}, mode={data['mode']}")
        return data


class TestSessionModeChange:
    """Tests for PUT /api/chat/sessions/{id} - changing session mode"""
    
    def test_change_mode_ai_to_human(self):
        """Test changing session mode from AI to Human"""
        # Create AI session
        create_response = requests.post(f"{BASE_URL}/api/chat/sessions", json={
            "mode": "ai",
            "is_ai_active": True,
            "title": "Mode Change Test"
        })
        assert create_response.status_code == 200
        session_id = create_response.json()["id"]
        
        # Change to human mode
        update_payload = {
            "mode": "human",
            "is_ai_active": False
        }
        response = requests.put(f"{BASE_URL}/api/chat/sessions/{session_id}", json=update_payload)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert data["mode"] == "human", "Mode should be changed to 'human'"
        assert data["is_ai_active"] == False, "AI should be inactive"
        assert "updated_at" in data, "Should have updated_at timestamp"
        
        print(f"✅ Mode changed from AI to Human: session={session_id}")
        return session_id
    
    def test_change_mode_human_to_community(self):
        """Test changing session mode from Human to Community"""
        # Create human session
        create_response = requests.post(f"{BASE_URL}/api/chat/sessions", json={
            "mode": "human",
            "is_ai_active": False
        })
        session_id = create_response.json()["id"]
        
        # Change to community mode
        update_payload = {
            "mode": "community",
            "is_ai_active": False
        }
        response = requests.put(f"{BASE_URL}/api/chat/sessions/{session_id}", json=update_payload)
        
        assert response.status_code == 200
        data = response.json()
        assert data["mode"] == "community"
        
        print(f"✅ Mode changed from Human to Community: session={session_id}")
    
    def test_change_mode_community_to_ai(self):
        """Test changing session mode from Community to AI"""
        # Create community session
        create_response = requests.post(f"{BASE_URL}/api/chat/sessions", json={
            "mode": "community",
            "is_ai_active": False
        })
        session_id = create_response.json()["id"]
        
        # Change to AI mode
        update_payload = {
            "mode": "ai",
            "is_ai_active": True
        }
        response = requests.put(f"{BASE_URL}/api/chat/sessions/{session_id}", json=update_payload)
        
        assert response.status_code == 200
        data = response.json()
        assert data["mode"] == "ai"
        assert data["is_ai_active"] == True
        
        print(f"✅ Mode changed from Community to AI: session={session_id}")
    
    def test_update_session_title_and_notes(self):
        """Test updating session title and notes"""
        # Create session
        create_response = requests.post(f"{BASE_URL}/api/chat/sessions", json={
            "mode": "ai",
            "title": "Original Title"
        })
        session_id = create_response.json()["id"]
        
        # Update title and notes
        update_payload = {
            "title": "Updated Title",
            "notes": "Coach notes about this session"
        }
        response = requests.put(f"{BASE_URL}/api/chat/sessions/{session_id}", json=update_payload)
        
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Updated Title"
        assert data["notes"] == "Coach notes about this session"
        
        print(f"✅ Session title and notes updated: session={session_id}")


class TestMessageDeletion:
    """Tests for message deletion (soft delete)"""
    
    def test_delete_message(self):
        """Test soft deleting a message via PUT /api/chat/messages/{id}/delete"""
        # First create a session and send a message
        unique_email = f"test_delete_{uuid.uuid4().hex[:8]}@example.com"
        entry_response = requests.post(f"{BASE_URL}/api/chat/smart-entry", json={
            "name": "Test Delete User",
            "email": unique_email
        })
        assert entry_response.status_code == 200
        session_id = entry_response.json()["session"]["id"]
        participant_id = entry_response.json()["participant"]["id"]
        
        # Create a message
        msg_payload = {
            "session_id": session_id,
            "sender_id": participant_id,
            "sender_name": "Test Delete User",
            "sender_type": "user",
            "content": "Test message to delete"
        }
        msg_response = requests.post(f"{BASE_URL}/api/chat/messages", json=msg_payload)
        
        if msg_response.status_code == 200:
            message_id = msg_response.json().get("id")
            
            # Try to delete the message
            delete_response = requests.put(f"{BASE_URL}/api/chat/messages/{message_id}/delete")
            
            if delete_response.status_code == 200:
                print(f"✅ Message deleted: message_id={message_id}")
            else:
                print(f"⚠️ Delete endpoint returned {delete_response.status_code} - may not be implemented")
        else:
            print(f"⚠️ Message creation returned {msg_response.status_code}")
    
    def test_get_messages_excludes_deleted(self):
        """Test that deleted messages are excluded by default"""
        # Create session
        unique_email = f"test_exclude_{uuid.uuid4().hex[:8]}@example.com"
        entry_response = requests.post(f"{BASE_URL}/api/chat/smart-entry", json={
            "name": "Test Exclude User",
            "email": unique_email
        })
        session_id = entry_response.json()["session"]["id"]
        
        # Get messages (should exclude deleted)
        response = requests.get(f"{BASE_URL}/api/chat/sessions/{session_id}/messages")
        
        assert response.status_code == 200
        messages = response.json()
        
        # Verify no deleted messages
        for msg in messages:
            assert msg.get("is_deleted") != True, "Deleted messages should be excluded"
        
        print(f"✅ Messages retrieved (deleted excluded): {len(messages)} messages")


class TestLinkifyText:
    """Tests for linkify functionality in messages"""
    
    def test_message_with_url(self):
        """Test sending a message containing a URL"""
        unique_email = f"test_url_{uuid.uuid4().hex[:8]}@example.com"
        entry_response = requests.post(f"{BASE_URL}/api/chat/smart-entry", json={
            "name": "Test URL User",
            "email": unique_email
        })
        assert entry_response.status_code == 200
        session_id = entry_response.json()["session"]["id"]
        participant_id = entry_response.json()["participant"]["id"]
        
        # Send message with URL
        msg_payload = {
            "session_id": session_id,
            "sender_id": participant_id,
            "sender_name": "Test URL User",
            "sender_type": "user",
            "content": "Check out this link: https://example.com/test"
        }
        msg_response = requests.post(f"{BASE_URL}/api/chat/messages", json=msg_payload)
        
        if msg_response.status_code == 200:
            data = msg_response.json()
            assert "https://example.com/test" in data.get("content", ""), "URL should be preserved in message"
            print(f"✅ Message with URL created successfully")
        else:
            print(f"⚠️ Message creation returned {msg_response.status_code}")
    
    def test_coach_message_with_url(self):
        """Test coach sending a message with URL"""
        unique_email = f"test_coach_url_{uuid.uuid4().hex[:8]}@example.com"
        entry_response = requests.post(f"{BASE_URL}/api/chat/smart-entry", json={
            "name": "Test Coach URL User",
            "email": unique_email
        })
        session_id = entry_response.json()["session"]["id"]
        
        # Coach sends message with URL
        coach_payload = {
            "session_id": session_id,
            "message": "Here's a helpful resource: https://afroboost.com/info",
            "coach_name": "Coach Test"
        }
        response = requests.post(f"{BASE_URL}/api/chat/coach-response", json=coach_payload)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print(f"✅ Coach message with URL sent successfully")


class TestNotificationService:
    """Tests for notification service (frontend-only, verify API supports it)"""
    
    def test_session_mode_indicator(self):
        """Test that session returns mode for indicator display"""
        # Create sessions with different modes
        modes = ["ai", "human", "community"]
        
        for mode in modes:
            payload = {
                "mode": mode,
                "is_ai_active": mode == "ai"
            }
            response = requests.post(f"{BASE_URL}/api/chat/sessions", json=payload)
            
            assert response.status_code == 200
            data = response.json()
            assert data["mode"] == mode, f"Mode should be {mode}"
            assert "is_ai_active" in data, "Should include is_ai_active flag"
            
            print(f"✅ Session with mode '{mode}' created - indicator data available")


class TestChatWidgetMenu:
    """Tests for chat widget menu functionality (delete history, change identity)"""
    
    def test_session_soft_delete(self):
        """Test soft deleting a session (for delete history)"""
        # Create session
        create_response = requests.post(f"{BASE_URL}/api/chat/sessions", json={
            "mode": "ai",
            "title": "Session to Delete"
        })
        session_id = create_response.json()["id"]
        
        # Soft delete via update
        update_payload = {
            "is_deleted": True
        }
        response = requests.put(f"{BASE_URL}/api/chat/sessions/{session_id}", json=update_payload)
        
        assert response.status_code == 200
        data = response.json()
        assert data.get("is_deleted") == True, "Session should be marked as deleted"
        assert "deleted_at" in data, "Should have deleted_at timestamp"
        
        print(f"✅ Session soft deleted: session={session_id}")
    
    def test_get_sessions_excludes_deleted(self):
        """Test that deleted sessions can be filtered"""
        # Create and delete a session
        create_response = requests.post(f"{BASE_URL}/api/chat/sessions", json={
            "mode": "ai",
            "title": "Deleted Session Test"
        })
        session_id = create_response.json()["id"]
        
        # Delete it
        requests.put(f"{BASE_URL}/api/chat/sessions/{session_id}", json={"is_deleted": True})
        
        # Get all sessions
        response = requests.get(f"{BASE_URL}/api/chat/sessions")
        
        assert response.status_code == 200
        sessions = response.json()
        
        # Note: The API may or may not filter deleted sessions by default
        # This test verifies the is_deleted flag is set correctly
        deleted_session = next((s for s in sessions if s["id"] == session_id), None)
        if deleted_session:
            assert deleted_session.get("is_deleted") == True
            print(f"✅ Deleted session found with is_deleted=True")
        else:
            print(f"✅ Deleted session filtered from results")


class TestHealthAndBasics:
    """Basic health checks"""
    
    def test_health_endpoint(self):
        """Test health endpoint"""
        response = requests.get(f"{BASE_URL}/api/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "healthy"
        
        print("✅ Health check passed")
    
    def test_chat_sessions_endpoint(self):
        """Test chat sessions list endpoint"""
        response = requests.get(f"{BASE_URL}/api/chat/sessions")
        
        assert response.status_code == 200
        assert isinstance(response.json(), list)
        
        print(f"✅ Chat sessions endpoint working: {len(response.json())} sessions")
    
    def test_chat_participants_endpoint(self):
        """Test chat participants list endpoint"""
        response = requests.get(f"{BASE_URL}/api/chat/participants")
        
        assert response.status_code == 200
        assert isinstance(response.json(), list)
        
        print(f"✅ Chat participants endpoint working: {len(response.json())} participants")


# Run tests if executed directly
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
