"""
Test Mission v10.5: Fix bouton Maintenance et harmonisation Dashboard
- Toggle Maintenance avec glow violet #D91CD2 quand activé
- Boutons Dashboard tous avec h-10 (40px)
- API /api/partners/active fonctionne
"""
import pytest
import requests
import os
import re

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestMissionV105Backend:
    """Backend tests for Mission v10.5"""
    
    def test_health_endpoint(self):
        """Test health endpoint is accessible"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        print("✅ Health endpoint OK")
    
    def test_partners_active_endpoint(self):
        """Test /api/partners/active returns partners"""
        response = requests.get(f"{BASE_URL}/api/partners/active")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✅ /api/partners/active returns {len(data)} partners")
    
    def test_courses_endpoint(self):
        """Test courses endpoint"""
        response = requests.get(f"{BASE_URL}/api/courses")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✅ /api/courses returns {len(data)} courses")
    
    def test_offers_endpoint(self):
        """Test offers endpoint"""
        response = requests.get(f"{BASE_URL}/api/offers")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✅ /api/offers returns {len(data)} offers")
    
    def test_concept_endpoint(self):
        """Test concept endpoint"""
        response = requests.get(f"{BASE_URL}/api/concept")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
        print("✅ /api/concept returns concept data")


class TestMissionV105FrontendCode:
    """Frontend code verification for Mission v10.5"""
    
    @pytest.fixture
    def coach_dashboard_content(self):
        """Load CoachDashboard.js content"""
        with open('/app/frontend/src/components/CoachDashboard.js', 'r') as f:
            return f.read()
    
    @pytest.fixture
    def partners_carousel_content(self):
        """Load PartnersCarousel.js content"""
        with open('/app/frontend/src/components/PartnersCarousel.js', 'r') as f:
            return f.read()
    
    def test_maintenance_toggle_has_violet_glow(self, coach_dashboard_content):
        """Verify toggle Maintenance has violet glow #D91CD2 when active"""
        # Check for boxShadow with #D91CD2 violet color
        assert "boxShadow: platformSettings.maintenance_mode" in coach_dashboard_content
        assert "rgba(217, 28, 210, 0.6)" in coach_dashboard_content  # Glow color
        assert "0 0 15px rgba(217, 28, 210, 0.6)" in coach_dashboard_content  # Glow intensity
        print("✅ Toggle Maintenance has violet glow #D91CD2")
    
    def test_maintenance_toggle_has_violet_gradient(self, coach_dashboard_content):
        """Verify toggle Maintenance has violet gradient background"""
        # Check for linear-gradient with #D91CD2
        assert "linear-gradient(90deg, #D91CD2, #8b5cf6)" in coach_dashboard_content
        print("✅ Toggle Maintenance has violet gradient background")
    
    def test_maintenance_toggle_data_testid(self, coach_dashboard_content):
        """Verify toggle Maintenance has data-testid"""
        assert 'data-testid="toggle-maintenance"' in coach_dashboard_content
        print("✅ Toggle Maintenance has data-testid='toggle-maintenance'")
    
    def test_admin_button_h10(self, coach_dashboard_content):
        """Verify Admin button has h-10 class"""
        # Search for Admin button with h-10
        admin_btn_pattern = r'className="h-10.*Admin'
        assert re.search(admin_btn_pattern, coach_dashboard_content, re.DOTALL)
        print("✅ Admin button has h-10 class")
    
    def test_stripe_button_h10(self, coach_dashboard_content):
        """Verify Stripe button has h-10 class"""
        # Search for stripe connect button with h-10
        stripe_pattern = r'data-testid="stripe-connect-btn"'
        assert stripe_pattern in coach_dashboard_content
        # Verify h-10 appears before stripe button
        assert 'className="h-10' in coach_dashboard_content
        print("✅ Stripe button has h-10 class")
    
    def test_partager_button_h10(self, coach_dashboard_content):
        """Verify Partager button has h-10 class"""
        # Search for share button with h-10
        share_pattern = r'data-testid="coach-share"'
        assert share_pattern in coach_dashboard_content
        print("✅ Partager button has data-testid='coach-share'")
    
    def test_retour_button_h10(self, coach_dashboard_content):
        """Verify Retour button has h-10 class"""
        # Search for back button with h-10
        back_pattern = r'data-testid="coach-back"'
        assert back_pattern in coach_dashboard_content
        # Verify h-10 exists in className before back button
        lines = coach_dashboard_content.split('\n')
        for i, line in enumerate(lines):
            if 'data-testid="coach-back"' in line:
                # Check surrounding lines for h-10
                context = '\n'.join(lines[max(0, i-5):i+1])
                assert 'h-10' in context, f"h-10 not found near coach-back button"
                print("✅ Retour button has h-10 class")
                return
        assert False, "coach-back button not found"
    
    def test_dashboard_buttons_gap3(self, coach_dashboard_content):
        """Verify dashboard button container has gap-3"""
        # Search for flex container with gap-3
        assert "flex flex-wrap gap-3" in coach_dashboard_content
        print("✅ Dashboard button container has gap-3 (12px)")
    
    def test_like_button_violet_glow(self, partners_carousel_content):
        """Verify Like button has violet glow #D91CD2"""
        # Check for boxShadow with violet glow on like button
        assert "0 0 20px rgba(217, 28, 210, 0.8)" in partners_carousel_content
        assert "0 0 40px rgba(217, 28, 210, 0.4)" in partners_carousel_content
        print("✅ Like button has violet glow #D91CD2")
    
    def test_like_button_fill_violet(self, partners_carousel_content):
        """Verify Like button heart fills with #D91CD2"""
        assert "fill={isLiked ? '#D91CD2' : 'none'}" in partners_carousel_content
        assert "stroke={isLiked ? '#D91CD2' : 'white'}" in partners_carousel_content
        print("✅ Like button heart fills with #D91CD2 violet")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
