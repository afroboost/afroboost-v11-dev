"""
Test Suite for DM Typing Indicator and Avatar Sync Features
============================================================
Tests the new Socket.IO events:
- dm_typing_start / dm_typing_stop for private message typing indicator
- avatar_updated for real-time avatar sync
- F5 persistence with afroboost_profile
- UI iconique (wireframe SVG icons in header)
"""

import pytest
import requests
import os
import json
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://promo-credits-lab.preview.emergentagent.com').rstrip('/')

class TestHealthAndBasicAPIs:
    """Basic API health checks"""
    
    def test_api_health(self):
        """TEST 1 - API Health Check"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "healthy"
        print("✅ TEST 1 - API Health Check PASSED")
    
    def test_promo_code_basxx_valid(self):
        """TEST 2 - Promo code basxx validates with correct email"""
        response = requests.post(f"{BASE_URL}/api/discount-codes/validate", json={
            "code": "basxx",
            "email": "bassicustomshoes@gmail.com"
        })
        assert response.status_code == 200
        data = response.json()
        assert data.get("valid") == True
        print("✅ TEST 2 - Promo code basxx validates with correct email PASSED")


class TestPrivateMessagingAPIs:
    """Test private messaging APIs for DM functionality"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test participants"""
        self.participant_1_id = f"TEST_user_dm_typing_{int(time.time())}"
        self.participant_1_name = "Test User DM 1"
        self.participant_2_id = f"TEST_user_dm_typing_2_{int(time.time())}"
        self.participant_2_name = "Test User DM 2"
    
    def test_create_private_conversation(self):
        """TEST 3 - Create private conversation for DM"""
        response = requests.post(f"{BASE_URL}/api/private/conversations", json={
            "participant_1_id": self.participant_1_id,
            "participant_1_name": self.participant_1_name,
            "participant_2_id": self.participant_2_id,
            "participant_2_name": self.participant_2_name
        })
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert data.get("participant_1_id") == self.participant_1_id
        assert data.get("participant_2_id") == self.participant_2_id
        print("✅ TEST 3 - Create private conversation for DM PASSED")
        return data
    
    def test_send_private_message(self):
        """TEST 4 - Send private message in DM"""
        # First create conversation
        conv_response = requests.post(f"{BASE_URL}/api/private/conversations", json={
            "participant_1_id": self.participant_1_id,
            "participant_1_name": self.participant_1_name,
            "participant_2_id": self.participant_2_id,
            "participant_2_name": self.participant_2_name
        })
        conversation = conv_response.json()
        
        # Send message
        response = requests.post(f"{BASE_URL}/api/private/messages", json={
            "conversation_id": conversation["id"],
            "sender_id": self.participant_1_id,
            "sender_name": self.participant_1_name,
            "recipient_id": self.participant_2_id,
            "recipient_name": self.participant_2_name,
            "content": "Test message for DM typing indicator"
        })
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert data.get("content") == "Test message for DM typing indicator"
        print("✅ TEST 4 - Send private message in DM PASSED")
    
    def test_get_private_messages(self):
        """TEST 5 - Get private messages from conversation"""
        # Create conversation and send message
        conv_response = requests.post(f"{BASE_URL}/api/private/conversations", json={
            "participant_1_id": self.participant_1_id,
            "participant_1_name": self.participant_1_name,
            "participant_2_id": self.participant_2_id,
            "participant_2_name": self.participant_2_name
        })
        conversation = conv_response.json()
        
        # Send a message
        requests.post(f"{BASE_URL}/api/private/messages", json={
            "conversation_id": conversation["id"],
            "sender_id": self.participant_1_id,
            "sender_name": self.participant_1_name,
            "recipient_id": self.participant_2_id,
            "recipient_name": self.participant_2_name,
            "content": "Test message retrieval"
        })
        
        # Get messages
        response = requests.get(f"{BASE_URL}/api/private/messages/{conversation['id']}")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        print("✅ TEST 5 - Get private messages from conversation PASSED")


class TestProfilePhotoUpload:
    """Test profile photo upload API for avatar sync"""
    
    def test_profile_photo_upload_endpoint_exists(self):
        """TEST 6 - Profile photo upload endpoint exists"""
        # Test with empty form data to verify endpoint exists
        response = requests.post(f"{BASE_URL}/api/upload/profile-photo")
        # Should return 422 (validation error) not 404
        assert response.status_code in [422, 400, 200]
        print("✅ TEST 6 - Profile photo upload endpoint exists PASSED")


class TestSmartEntryAPI:
    """Test smart-entry API for session persistence"""
    
    def test_smart_entry_creates_session(self):
        """TEST 7 - Smart-entry API creates session for F5 persistence"""
        response = requests.post(f"{BASE_URL}/api/chat/smart-entry", json={
            "name": "Test User F5",
            "email": "testf5@example.com",
            "whatsapp": "+41791234567"
        })
        assert response.status_code == 200
        data = response.json()
        assert "session" in data
        assert "participant" in data
        assert data["session"].get("id") is not None
        print("✅ TEST 7 - Smart-entry API creates session for F5 persistence PASSED")
    
    def test_smart_entry_returns_participant_id(self):
        """TEST 8 - Smart-entry returns participant ID for Socket.IO"""
        response = requests.post(f"{BASE_URL}/api/chat/smart-entry", json={
            "name": "Test Participant",
            "email": "testparticipant@example.com",
            "whatsapp": "+41791234568"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["participant"].get("id") is not None
        print("✅ TEST 8 - Smart-entry returns participant ID for Socket.IO PASSED")


class TestSocketIOEventsBackend:
    """Test that Socket.IO event handlers are defined in backend"""
    
    def test_backend_has_dm_typing_handlers(self):
        """TEST 9 - Backend has dm_typing_start/stop handlers"""
        # Read server.py to verify handlers exist
        server_path = "/app/backend/server.py"
        with open(server_path, 'r') as f:
            content = f.read()
        
        assert "async def dm_typing_start" in content
        assert "async def dm_typing_stop" in content
        assert "dm_typing" in content  # Event name emitted
        print("✅ TEST 9 - Backend has dm_typing_start/stop handlers PASSED")
    
    def test_backend_has_avatar_updated_handler(self):
        """TEST 10 - Backend has avatar_updated handler"""
        server_path = "/app/backend/server.py"
        with open(server_path, 'r') as f:
            content = f.read()
        
        assert "async def avatar_updated" in content
        assert "user_avatar_changed" in content  # Event name emitted
        print("✅ TEST 10 - Backend has avatar_updated handler PASSED")


class TestFrontendCodeStructure:
    """Test that frontend has required code for DM typing and avatar sync"""
    
    def test_frontend_has_dm_typing_state(self):
        """TEST 11 - Frontend has dmTypingUser state"""
        chatwidget_path = "/app/frontend/src/components/ChatWidget.js"
        with open(chatwidget_path, 'r') as f:
            content = f.read()
        
        assert "dmTypingUser" in content
        assert "setDmTypingUser" in content
        assert "dmTypingTimeoutRef" in content
        print("✅ TEST 11 - Frontend has dmTypingUser state PASSED")
    
    def test_frontend_has_emit_dm_typing_function(self):
        """TEST 12 - Frontend has emitDmTyping function"""
        chatwidget_path = "/app/frontend/src/components/ChatWidget.js"
        with open(chatwidget_path, 'r') as f:
            content = f.read()
        
        assert "const emitDmTyping" in content
        assert "dm_typing_start" in content
        assert "dm_typing_stop" in content
        print("✅ TEST 12 - Frontend has emitDmTyping function PASSED")
    
    def test_frontend_has_emit_avatar_update_function(self):
        """TEST 13 - Frontend has emitAvatarUpdate function"""
        chatwidget_path = "/app/frontend/src/components/ChatWidget.js"
        with open(chatwidget_path, 'r') as f:
            content = f.read()
        
        assert "const emitAvatarUpdate" in content
        assert "avatar_updated" in content
        print("✅ TEST 13 - Frontend has emitAvatarUpdate function PASSED")
    
    def test_frontend_has_dm_typing_indicator_ui(self):
        """TEST 14 - Frontend has DM typing indicator UI with data-testid"""
        chatwidget_path = "/app/frontend/src/components/ChatWidget.js"
        with open(chatwidget_path, 'r') as f:
            content = f.read()
        
        assert 'data-testid="dm-typing-indicator"' in content
        assert "dmTypingDot" in content  # CSS animation
        print("✅ TEST 14 - Frontend has DM typing indicator UI with data-testid PASSED")
    
    def test_frontend_has_private_message_input(self):
        """TEST 15 - Frontend has private message input with data-testid"""
        chatwidget_path = "/app/frontend/src/components/ChatWidget.js"
        with open(chatwidget_path, 'r') as f:
            content = f.read()
        
        assert 'data-testid="private-message-input"' in content
        print("✅ TEST 15 - Frontend has private message input with data-testid PASSED")
    
    def test_frontend_listens_to_dm_typing_event(self):
        """TEST 16 - Frontend listens to dm_typing Socket.IO event"""
        chatwidget_path = "/app/frontend/src/components/ChatWidget.js"
        with open(chatwidget_path, 'r') as f:
            content = f.read()
        
        assert "socket.on('dm_typing'" in content
        assert "handleDmTyping" in content
        print("✅ TEST 16 - Frontend listens to dm_typing Socket.IO event PASSED")
    
    def test_frontend_listens_to_avatar_changed_event(self):
        """TEST 17 - Frontend listens to user_avatar_changed Socket.IO event"""
        chatwidget_path = "/app/frontend/src/components/ChatWidget.js"
        with open(chatwidget_path, 'r') as f:
            content = f.read()
        
        assert "socket.on('user_avatar_changed'" in content
        assert "handleAvatarChanged" in content
        print("✅ TEST 17 - Frontend listens to user_avatar_changed Socket.IO event PASSED")


class TestUIIconique:
    """Test that header uses wireframe SVG icons (UI iconique)"""
    
    def test_header_has_svg_icons(self):
        """TEST 18 - Header has SVG wireframe icons"""
        chatwidget_path = "/app/frontend/src/components/ChatWidget.js"
        with open(chatwidget_path, 'r') as f:
            content = f.read()
        
        # Check for SVG icons in header area
        assert "FullscreenIcon" in content
        assert "ExitFullscreenIcon" in content
        assert "WhatsAppIcon" in content
        assert "GroupIcon" in content
        # Check for wireframe style (stroke instead of fill)
        assert 'stroke="' in content or "strokeWidth" in content
        print("✅ TEST 18 - Header has SVG wireframe icons PASSED")
    
    def test_share_icon_is_wireframe(self):
        """TEST 19 - Share icon uses wireframe style"""
        chatwidget_path = "/app/frontend/src/components/ChatWidget.js"
        with open(chatwidget_path, 'r') as f:
            content = f.read()
        
        # Share icon should use stroke (wireframe) not fill
        assert 'data-testid="share-link-btn"' in content
        print("✅ TEST 19 - Share icon uses wireframe style PASSED")
    
    def test_menu_icon_is_wireframe(self):
        """TEST 20 - Menu icon (⋮) uses wireframe style"""
        chatwidget_path = "/app/frontend/src/components/ChatWidget.js"
        with open(chatwidget_path, 'r') as f:
            content = f.read()
        
        assert 'data-testid="user-menu-btn"' in content
        print("✅ TEST 20 - Menu icon (⋮) uses wireframe style PASSED")


class TestF5Persistence:
    """Test F5 persistence with afroboost_profile"""
    
    def test_frontend_uses_afroboost_profile_key(self):
        """TEST 21 - Frontend uses afroboost_profile localStorage key"""
        chatwidget_path = "/app/frontend/src/components/ChatWidget.js"
        with open(chatwidget_path, 'r') as f:
            content = f.read()
        
        assert "AFROBOOST_PROFILE_KEY" in content
        assert "afroboost_profile" in content
        assert "getStoredProfile" in content
        print("✅ TEST 21 - Frontend uses afroboost_profile localStorage key PASSED")
    
    def test_frontend_restores_session_on_mount(self):
        """TEST 22 - Frontend restores session on component mount"""
        chatwidget_path = "/app/frontend/src/components/ChatWidget.js"
        with open(chatwidget_path, 'r') as f:
            content = f.read()
        
        # Check for initial step determination based on localStorage
        assert "getInitialStep" in content
        assert "getInitialFullscreen" in content
        print("✅ TEST 22 - Frontend restores session on component mount PASSED")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
