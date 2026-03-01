"""
Mission v10.6 - Design minimaliste et réparation du scroll
Tests: API endpoints + Code verification for Dashboard grid and scroll fixes
"""

import pytest
import requests
import os
import re

# Base URL from environment
BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://multi-coach-saas.preview.emergentagent.com').rstrip('/')


class TestApiEndpoints:
    """API endpoint tests for Mission v10.6"""
    
    def test_health_endpoint(self):
        """Test health endpoint"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "healthy"
        print("✅ Health endpoint returns healthy status")
    
    def test_partners_active_endpoint(self):
        """Test /api/partners/active returns partners list"""
        response = requests.get(f"{BASE_URL}/api/partners/active")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1  # At least 1 partner
        print(f"✅ Partners active endpoint returns {len(data)} partners")
    
    def test_courses_endpoint(self):
        """Test courses endpoint"""
        response = requests.get(f"{BASE_URL}/api/courses")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✅ Courses endpoint returns {len(data)} courses")
    
    def test_offers_endpoint(self):
        """Test offers endpoint"""
        response = requests.get(f"{BASE_URL}/api/offers")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✅ Offers endpoint returns {len(data)} offers")
    
    def test_concept_endpoint(self):
        """Test concept endpoint"""
        response = requests.get(f"{BASE_URL}/api/concept")
        assert response.status_code == 200
        data = response.json()
        assert "appName" in data or isinstance(data, dict)
        print("✅ Concept endpoint returns data")


class TestCoachDashboardCodeV106:
    """Code verification tests for Mission v10.6 Dashboard refactoring"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Read CoachDashboard.js file"""
        self.file_path = "/app/frontend/src/components/CoachDashboard.js"
        with open(self.file_path, 'r') as f:
            self.code = f.read()
    
    def test_back_button_fixed_position(self):
        """v10.6: Bouton Retour en position fixe en haut à gauche"""
        # Check position: 'fixed' style
        assert "position: 'fixed'" in self.code or 'position: "fixed"' in self.code
        # Check top: '12px'
        assert "top: '12px'" in self.code or 'top: "12px"' in self.code
        # Check left: '12px'
        assert "left: '12px'" in self.code or 'left: "12px"' in self.code
        # Check high zIndex
        assert "zIndex: 9999" in self.code
        print("✅ Back button has fixed position at top: 12px, left: 12px, zIndex: 9999")
    
    def test_back_button_data_testid(self):
        """v10.6: Bouton Retour has data-testid='coach-back'"""
        assert 'data-testid="coach-back"' in self.code
        print("✅ Back button has data-testid='coach-back'")
    
    def test_actions_grid_2_columns(self):
        """v10.6: Grille d'actions 2 colonnes sur mobile"""
        # Check grid-cols-2 sm:grid-cols-4
        assert "grid grid-cols-2 sm:grid-cols-4" in self.code
        print("✅ Actions grid uses 2 columns on mobile (grid-cols-2)")
    
    def test_action_cards_h20_rounded(self):
        """v10.6: Cartes d'action h-20 rounded-2xl"""
        # Check h-20 rounded-2xl pattern (multiple cards should have this)
        h20_count = self.code.count("h-20 rounded-2xl")
        assert h20_count >= 3  # At least Quick, Admin/Stripe, Partager cards
        print(f"✅ Found {h20_count} cards with h-20 rounded-2xl class")
    
    def test_quick_control_centered_mobile(self):
        """v10.6: Quick Control menu centré sur mobile avec transform -translate-x-1/2"""
        # Check transform translate-x-1/2 for centering
        assert "transform -translate-x-1/2" in self.code or "left-1/2" in self.code
        print("✅ Quick Control menu uses transform -translate-x-1/2 for centering")
    
    def test_scroll_container_padding(self):
        """v10.6: Container principal avec paddingTop 60px et paddingBottom 100px"""
        # Check paddingTop: '60px'
        assert "paddingTop: '60px'" in self.code or 'paddingTop: "60px"' in self.code
        # Check paddingBottom: '100px'
        assert "paddingBottom: '100px'" in self.code or 'paddingBottom: "100px"' in self.code
        print("✅ Container has paddingTop: 60px and paddingBottom: 100px")
    
    def test_maintenance_toggle_violet_glow(self):
        """v10.6: Toggle Maintenance avec glow violet #D91CD2"""
        # Check boxShadow with rgba(217, 28, 210 (violet) when maintenance_mode active
        assert "boxShadow: platformSettings.maintenance_mode" in self.code
        assert "0 0 15px rgba(217, 28, 210" in self.code
        print("✅ Maintenance toggle has violet glow (rgba(217, 28, 210))")
    
    def test_maintenance_toggle_data_testid(self):
        """v10.6: Toggle Maintenance has data-testid"""
        assert 'data-testid="toggle-maintenance"' in self.code
        print("✅ Maintenance toggle has data-testid='toggle-maintenance'")
    
    def test_quick_control_btn_data_testid(self):
        """v10.6: Quick Control button has data-testid"""
        assert 'data-testid="quick-control-btn"' in self.code
        print("✅ Quick Control button has data-testid='quick-control-btn'")


class TestPartnersCarouselCodeV106:
    """Code verification tests for PartnersCarousel header icons"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Read PartnersCarousel.js file"""
        self.file_path = "/app/frontend/src/components/PartnersCarousel.js"
        with open(self.file_path, 'r') as f:
            self.code = f.read()
    
    def test_header_icons_gap_16px(self):
        """v10.6: 3 icônes header alignées avec gap 16px (gap-4)"""
        # Check gap-4 in header icons container
        assert '"flex items-center gap-4"' in self.code or "'flex items-center gap-4'" in self.code or "flex items-center gap-4" in self.code
        print("✅ Header icons container uses gap-4 (16px)")
    
    def test_like_button_violet_glow(self):
        """v10.6: Bouton Like avec glow violet #D91CD2"""
        # Check boxShadow with rgba(217, 28, 210 (violet)
        assert "217, 28, 210" in self.code  # Violet color in glow
        print("✅ Like button has violet glow styling (217, 28, 210)")
    
    def test_like_button_data_testid(self):
        """v10.6: Like button has data-testid"""
        assert 'data-testid={`like-btn-' in self.code
        print("✅ Like button has dynamic data-testid")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
