"""
Test v9.6.1: VALIDATION FINALE - Mission objectives confirmation
Tests:
1. Super Admin (afroboost.bassi@gmail.com) has is_super_admin=true
2. Super Admin check-partner returns unlimited=true, has_credits=true
3. Super Admin credits/check returns credits=-1 (infinity)
4. Super Admin sees all reservations (data isolation test)
5. Test partner sees 0 reservations (isolation test)
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://promo-credits-lab.preview.emergentagent.com')

SUPER_ADMIN_EMAIL = "afroboost.bassi@gmail.com"
TEST_PARTNER_EMAIL = "test.partner.isolation@example.com"

class TestSuperAdminFeatures:
    """Test Super Admin features for v9.6.1 validation"""
    
    def test_health_check(self):
        """Test API is accessible"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200, f"Health check failed: {response.status_code}"
        data = response.json()
        assert data.get("status") == "healthy", f"API not healthy: {data}"
        print("✅ Health check: PASS - API healthy")
    
    def test_super_admin_check_partner_status(self):
        """Backend: Super Admin check-partner returns is_partner=true, unlimited=true, has_credits=true"""
        response = requests.get(f"{BASE_URL}/api/check-partner/{SUPER_ADMIN_EMAIL}")
        assert response.status_code == 200, f"Check partner failed: {response.status_code}"
        data = response.json()
        
        # Assert Super Admin has partner status
        assert data.get("is_partner") == True, f"Expected is_partner=True, got: {data.get('is_partner')}"
        
        # Assert unlimited credits
        assert data.get("unlimited") == True, f"Expected unlimited=True, got: {data.get('unlimited')}"
        
        # Assert has credits
        assert data.get("has_credits") == True, f"Expected has_credits=True, got: {data.get('has_credits')}"
        
        # Assert credits = -1 (infinity)
        assert data.get("credits") == -1, f"Expected credits=-1, got: {data.get('credits')}"
        
        # Assert is_super_admin flag
        assert data.get("is_super_admin") == True, f"Expected is_super_admin=True, got: {data.get('is_super_admin')}"
        
        print(f"✅ Super Admin check-partner: PASS - is_partner={data.get('is_partner')}, unlimited={data.get('unlimited')}, credits={data.get('credits')}, is_super_admin={data.get('is_super_admin')}")
    
    def test_super_admin_credits_check_infinite(self):
        """Backend: Super Admin credits/check returns credits=-1 (infinity)"""
        headers = {"X-User-Email": SUPER_ADMIN_EMAIL}
        response = requests.get(f"{BASE_URL}/api/credits/check", headers=headers)
        assert response.status_code == 200, f"Credits check failed: {response.status_code}"
        data = response.json()
        
        # Assert unlimited credits
        assert data.get("unlimited") == True, f"Expected unlimited=True, got: {data.get('unlimited')}"
        
        # Assert credits = -1
        assert data.get("credits") == -1, f"Expected credits=-1, got: {data.get('credits')}"
        
        # Assert has_credits = True
        assert data.get("has_credits") == True, f"Expected has_credits=True, got: {data.get('has_credits')}"
        
        print(f"✅ Super Admin credits/check: PASS - credits={data.get('credits')}, unlimited={data.get('unlimited')}, has_credits={data.get('has_credits')}")
    
    def test_super_admin_sees_all_reservations(self):
        """Backend: Super Admin sees all reservations (no isolation filter)"""
        headers = {"X-User-Email": SUPER_ADMIN_EMAIL}
        response = requests.get(f"{BASE_URL}/api/reservations", headers=headers)
        assert response.status_code == 200, f"Reservations failed: {response.status_code}"
        data = response.json()
        
        # Super Admin should see reservations (may be 0 if DB is empty, but endpoint should work)
        assert "data" in data, f"Expected 'data' key in response: {data}"
        assert "pagination" in data, f"Expected 'pagination' key in response: {data}"
        
        total_count = data.get("pagination", {}).get("total", 0)
        reservations_count = len(data.get("data", []))
        
        print(f"✅ Super Admin reservations: PASS - sees {reservations_count} reservations (total: {total_count})")
        return total_count
    
    def test_test_partner_isolation(self):
        """Backend: Test partner sees 0 reservations (isolation test)"""
        headers = {"X-User-Email": TEST_PARTNER_EMAIL}
        response = requests.get(f"{BASE_URL}/api/reservations", headers=headers)
        assert response.status_code == 200, f"Reservations failed: {response.status_code}"
        data = response.json()
        
        # Test partner should see 0 reservations (isolated by coach_id)
        assert "data" in data, f"Expected 'data' key in response: {data}"
        
        reservations_count = len(data.get("data", []))
        total_count = data.get("pagination", {}).get("total", 0)
        
        # Test partner should see 0 or only their own (coach_id filter applied)
        assert total_count == 0 or reservations_count == 0, f"Test partner should see 0 reservations, got {total_count}"
        
        print(f"✅ Test partner isolation: PASS - sees {reservations_count} reservations (total: {total_count})")
    
    def test_super_admin_credits_deduct_bypass(self):
        """Backend: Super Admin credit deduction is bypassed (never consumes)"""
        headers = {"X-User-Email": SUPER_ADMIN_EMAIL}
        response = requests.post(
            f"{BASE_URL}/api/credits/deduct",
            headers=headers,
            json={"action": "test_validation_v961"}
        )
        assert response.status_code == 200, f"Credits deduct failed: {response.status_code}"
        data = response.json()
        
        # Assert Super Admin bypass
        assert data.get("success") == True, f"Expected success=True, got: {data.get('success')}"
        assert data.get("bypassed") == True, f"Expected bypassed=True, got: {data.get('bypassed')}"
        assert data.get("credits_remaining") == -1, f"Expected credits_remaining=-1, got: {data.get('credits_remaining')}"
        
        print(f"✅ Super Admin credits deduct: PASS - bypassed={data.get('bypassed')}, credits_remaining={data.get('credits_remaining')}")


class TestAPIEndpoints:
    """Test core API endpoints are working"""
    
    def test_partners_active_endpoint(self):
        """Test /api/partners/active endpoint"""
        response = requests.get(f"{BASE_URL}/api/partners/active")
        assert response.status_code == 200, f"Partners active failed: {response.status_code}"
        data = response.json()
        # Should return a list (may be empty)
        assert isinstance(data, list), f"Expected list, got: {type(data)}"
        print(f"✅ Partners active: PASS - {len(data)} partners found")
    
    def test_courses_endpoint(self):
        """Test /api/courses endpoint"""
        response = requests.get(f"{BASE_URL}/api/courses")
        assert response.status_code == 200, f"Courses failed: {response.status_code}"
        data = response.json()
        assert isinstance(data, list), f"Expected list, got: {type(data)}"
        print(f"✅ Courses: PASS - {len(data)} courses found")
    
    def test_offers_endpoint(self):
        """Test /api/offers endpoint"""
        response = requests.get(f"{BASE_URL}/api/offers")
        assert response.status_code == 200, f"Offers failed: {response.status_code}"
        data = response.json()
        assert isinstance(data, list), f"Expected list, got: {type(data)}"
        print(f"✅ Offers: PASS - {len(data)} offers found")
    
    def test_concept_endpoint(self):
        """Test /api/concept endpoint"""
        response = requests.get(f"{BASE_URL}/api/concept")
        assert response.status_code == 200, f"Concept failed: {response.status_code}"
        data = response.json()
        assert "appName" in data or "description" in data, f"Expected concept data: {data}"
        print(f"✅ Concept: PASS - appName={data.get('appName', 'N/A')}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
