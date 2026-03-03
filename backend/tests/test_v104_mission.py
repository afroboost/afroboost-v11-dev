"""
Mission v10.4: Persistance du Chat et Alignement Dashboard
Tests:
- API /api/partners/active fonctionne
- API /api/health fonctionne
- Header icons gap 16px (code verification)
- Message text fallback robuste (content || text || body)
- Croix fermeture récapitulatif réservation (code verification)
- Bouton Retour harmonisé avec style violet gradient
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://promo-credits-lab.preview.emergentagent.com')


class TestMissionV104:
    """Tests for Mission v10.4 - Chat Persistence and Dashboard Alignment"""
    
    def test_health_endpoint(self):
        """Verify API is healthy"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "healthy"
        print("PASS: Health endpoint returns healthy")
    
    def test_partners_active_endpoint(self):
        """Verify /api/partners/active returns data"""
        response = requests.get(f"{BASE_URL}/api/partners/active")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0
        print(f"PASS: /api/partners/active returned {len(data)} partners")
    
    def test_partners_have_required_fields(self):
        """Verify partners have required fields for display"""
        response = requests.get(f"{BASE_URL}/api/partners/active")
        assert response.status_code == 200
        data = response.json()
        
        for partner in data:
            assert 'id' in partner or '_id' in partner, f"Partner missing id: {partner}"
            assert 'email' in partner, f"Partner missing email: {partner}"
            assert 'name' in partner, f"Partner missing name: {partner}"
        print("PASS: All partners have required fields")
    
    def test_courses_endpoint(self):
        """Verify courses endpoint works"""
        response = requests.get(f"{BASE_URL}/api/courses")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"PASS: /api/courses returned {len(data)} courses")
    
    def test_offers_endpoint(self):
        """Verify offers endpoint works"""
        response = requests.get(f"{BASE_URL}/api/offers")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"PASS: /api/offers returned {len(data)} offers")
    
    def test_concept_endpoint(self):
        """Verify concept endpoint works"""
        response = requests.get(f"{BASE_URL}/api/concept")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
        print("PASS: /api/concept returns concept data")
    
    def test_validate_code_endpoint_exists(self):
        """Verify validate code endpoint exists"""
        response = requests.post(f"{BASE_URL}/api/validate-code", json={"code": "TEST"})
        # Should return 404 for invalid code, not 500 (endpoint exists but code invalid)
        assert response.status_code in [200, 400, 404, 422]
        print(f"PASS: /api/validate-code endpoint exists (status {response.status_code})")
    
    def test_check_reservation_eligibility_endpoint(self):
        """Verify check-reservation-eligibility endpoint exists"""
        response = requests.post(f"{BASE_URL}/api/check-reservation-eligibility", json={
            "code": "TEST",
            "email": "test@test.com"
        })
        assert response.status_code in [200, 400, 404, 422]
        print(f"PASS: /api/check-reservation-eligibility endpoint exists (status {response.status_code})")


class TestCodeVerificationV104:
    """Code verification tests for Mission v10.4 - verify implementation without running frontend"""
    
    def test_chatwidget_message_fallback_robuste(self):
        """Verify ChatWidget.js has robust fallback for message text"""
        chatwidget_path = "/app/frontend/src/components/ChatWidget.js"
        with open(chatwidget_path, 'r') as f:
            content = f.read()
        
        # v10.4: Check for content || text || body fallback
        assert "msg.content || msg.text || msg.body || ''" in content, \
            "Missing robust fallback: msg.content || msg.text || msg.body || ''"
        
        print("PASS: ChatWidget.js has robust message text fallback (content || text || body)")
    
    def test_chatwidget_reservation_close_button(self):
        """Verify ChatWidget.js has close button (×) on reservation summary"""
        chatwidget_path = "/app/frontend/src/components/ChatWidget.js"
        with open(chatwidget_path, 'r') as f:
            content = f.read()
        
        # v10.4: Check for close button on reservation summary
        assert 'data-testid="close-reservation-summary"' in content, \
            "Missing close button data-testid on reservation summary"
        assert 'setIsMinimized' in content, \
            "Missing isMinimized state for closing reservation summary"
        assert '×' in content or '&times;' in content, \
            "Missing × close button symbol"
        
        print("PASS: ChatWidget.js has close button (×) on reservation summary")
    
    def test_chatwidget_localstorage_keys_defined(self):
        """Verify ChatWidget.js defines localStorage keys for chat memory"""
        chatwidget_path = "/app/frontend/src/components/ChatWidget.js"
        with open(chatwidget_path, 'r') as f:
            content = f.read()
        
        assert "CHAT_CLIENT_KEY = 'af_chat_client'" in content, \
            "Missing CHAT_CLIENT_KEY definition"
        assert "AFROBOOST_IDENTITY_KEY = 'afroboost_identity'" in content, \
            "Missing AFROBOOST_IDENTITY_KEY definition"
        
        print("PASS: ChatWidget.js defines localStorage keys (af_chat_client, afroboost_identity)")
    
    def test_coachdashboard_back_button_violet_gradient(self):
        """Verify CoachDashboard.js has back button with violet gradient"""
        dashboard_path = "/app/frontend/src/components/CoachDashboard.js"
        with open(dashboard_path, 'r') as f:
            content = f.read()
        
        # v10.4: Check for back button with violet gradient
        assert 'onClick={onBack}' in content, \
            "Missing onBack click handler"
        assert 'data-testid="coach-back"' in content, \
            "Missing data-testid for back button"
        # Check for violet gradient colors (rgba(139, 92, 246) = #8B5CF6, rgba(217, 28, 210) = #D91CD2)
        assert 'rgba(139, 92, 246' in content or '#8B5CF6' in content, \
            "Missing violet color in back button gradient"
        assert 'rgba(217, 28, 210' in content or '#D91CD2' in content, \
            "Missing D91CD2 color in back button gradient"
        
        print("PASS: CoachDashboard.js has back button with violet gradient style")
    
    def test_header_icons_gap_class(self):
        """Verify header icons use gap-4 class (16px)"""
        # Check App.js or relevant header component
        app_path = "/app/frontend/src/App.js"
        with open(app_path, 'r') as f:
            content = f.read()
        
        # gap-4 = 16px in Tailwind
        assert 'gap-4' in content or 'gap: 16px' in content, \
            "Missing gap-4 class for header icons alignment"
        
        print("PASS: Header uses gap-4 (16px) for icons alignment")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
