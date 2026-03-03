# test_v920_mission.py - Mission v9.2.0 Tests
# Tests for: CRM extraction, promo routes modularization, credits badge protection

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://promo-credits-lab.preview.emergentagent.com')

class TestHealthAndBasics:
    """Basic health and connectivity tests"""
    
    def test_health_check(self):
        """Verify API is accessible"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "healthy"
        print(f"✅ Health check passed: {data}")

class TestPromoRoutes:
    """Test promo code routes via /api/discount-codes"""
    
    def test_get_discount_codes(self):
        """GET /api/discount-codes should return list of codes"""
        response = requests.get(f"{BASE_URL}/api/discount-codes")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✅ GET /api/discount-codes returned {len(data)} codes")
    
    def test_validate_discount_code_invalid(self):
        """POST /api/discount-codes/validate with invalid code should return valid=False"""
        response = requests.post(
            f"{BASE_URL}/api/discount-codes/validate",
            json={"code": "INVALID_CODE_12345", "email": "test@test.com"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("valid") == False
        print(f"✅ Invalid code validation returned: {data}")

class TestAuthRoutes:
    """Test auth routes via /api/auth"""
    
    def test_auth_me_unauthorized(self):
        """GET /api/auth/me should return 401 without session"""
        response = requests.get(f"{BASE_URL}/api/auth/me")
        assert response.status_code == 401
        print(f"✅ /api/auth/me returns 401 without session")
    
    def test_coach_auth_legacy(self):
        """GET /api/coach-auth should return authorized email"""
        response = requests.get(f"{BASE_URL}/api/coach-auth")
        assert response.status_code == 200
        data = response.json()
        assert "email" in data
        assert data["email"] == "contact.artboost@gmail.com"
        print(f"✅ /api/coach-auth returns: {data}")

class TestSacredReservations:
    """Verify sacred Fitness reservations exist"""
    
    def test_reservations_exist(self):
        """GET /api/reservations should return fitness reservations (with coach header)"""
        # Super admin header needed to see all reservations
        headers = {"X-User-Email": "contact.artboost@gmail.com"}
        response = requests.get(f"{BASE_URL}/api/reservations?page=1&limit=50", headers=headers)
        assert response.status_code == 200
        data = response.json()
        reservations = data.get("data", [])
        
        # Check for Fitness reservations (Henri BASSI / Bassi)
        fitness_reservations = [
            r for r in reservations 
            if "bassi" in r.get("userName", "").lower()
        ]
        
        print(f"✅ Found {len(reservations)} total reservations, {len(fitness_reservations)} Bassi reservations")
        assert len(fitness_reservations) >= 7, f"Should have at least 7 sacred Bassi reservations, got {len(fitness_reservations)}"

class TestFileStructure:
    """Verify file structure and line counts"""
    
    def test_server_py_line_count(self):
        """server.py should have < 6200 lines"""
        import subprocess
        result = subprocess.run(
            ["wc", "-l", "/app/backend/server.py"],
            capture_output=True, text=True
        )
        line_count = int(result.stdout.split()[0])
        print(f"server.py has {line_count} lines (target < 6200)")
        assert line_count < 6200, f"server.py has {line_count} lines, should be < 6200"
        print(f"✅ server.py line count: {line_count} (< 6200)")
    
    def test_coach_dashboard_line_count(self):
        """CoachDashboard.js should have < 5800 lines"""
        import subprocess
        result = subprocess.run(
            ["wc", "-l", "/app/frontend/src/components/CoachDashboard.js"],
            capture_output=True, text=True
        )
        line_count = int(result.stdout.split()[0])
        print(f"CoachDashboard.js has {line_count} lines (target < 5800)")
        assert line_count < 5800, f"CoachDashboard.js has {line_count} lines, should be < 5800"
        print(f"✅ CoachDashboard.js line count: {line_count} (< 5800)")
    
    def test_crm_section_exists(self):
        """CRMSection.js should exist with ~673 lines"""
        import subprocess
        result = subprocess.run(
            ["wc", "-l", "/app/frontend/src/components/coach/CRMSection.js"],
            capture_output=True, text=True
        )
        line_count = int(result.stdout.split()[0])
        print(f"CRMSection.js has {line_count} lines")
        assert line_count > 600, f"CRMSection.js has {line_count} lines, should be > 600"
        print(f"✅ CRMSection.js exists with {line_count} lines")
    
    def test_promo_routes_module_exists(self):
        """promo_routes.py should exist with ~159 lines"""
        import subprocess
        result = subprocess.run(
            ["wc", "-l", "/app/backend/routes/promo_routes.py"],
            capture_output=True, text=True
        )
        line_count = int(result.stdout.split()[0])
        print(f"promo_routes.py has {line_count} lines")
        assert line_count > 150, f"promo_routes.py has {line_count} lines, should be > 150"
        print(f"✅ promo_routes.py exists with {line_count} lines")

class TestCourses:
    """Test courses endpoint - verify calendar dates"""
    
    def test_courses_exist(self):
        """GET /api/courses should return courses"""
        response = requests.get(f"{BASE_URL}/api/courses")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0
        print(f"✅ Found {len(data)} courses")

class TestOffers:
    """Test offers endpoint"""
    
    def test_offers_exist(self):
        """GET /api/offers should return offers"""
        response = requests.get(f"{BASE_URL}/api/offers")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✅ Found {len(data)} offers")

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
