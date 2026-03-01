"""
Test Suite v8.9.2 - Coach Search, Stripe Connect, and Coach Isolation
Tests:
1. GET /api/coaches/search?q=xxx - Public coach search
2. GET /api/coaches/public/{id} - Public coach profile
3. POST /api/coach/stripe-connect/onboard - Stripe Connect onboarding
4. GET /api/coach/stripe-connect/status - Stripe Connect status
5. Non-regression: courses, offers, payment-links
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://video-feed-platform.preview.emergentagent.com')
API = f"{BASE_URL}/api"
SUPER_ADMIN_EMAIL = "contact.artboost@gmail.com"


class TestHealthAndNonRegression:
    """Non-regression tests for basic API functionality"""
    
    def test_01_health_check(self):
        """TEST 1 - API Health check"""
        response = requests.get(f"{API}/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "healthy"
        assert data.get("database") == "connected"
        print("TEST 1 - API Health check ✅")
    
    def test_02_get_courses(self):
        """TEST 2 - Non-regression: GET /api/courses"""
        response = requests.get(f"{API}/courses")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"TEST 2 - GET /api/courses - {len(data)} courses ✅")
    
    def test_03_get_offers(self):
        """TEST 3 - Non-regression: GET /api/offers"""
        response = requests.get(f"{API}/offers")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"TEST 3 - GET /api/offers - {len(data)} offers ✅")
    
    def test_04_get_payment_links(self):
        """TEST 4 - Non-regression: GET /api/payment-links"""
        response = requests.get(f"{API}/payment-links")
        assert response.status_code == 200
        print("TEST 4 - GET /api/payment-links ✅")
    
    def test_05_get_concept(self):
        """TEST 5 - Non-regression: GET /api/concept"""
        response = requests.get(f"{API}/concept")
        assert response.status_code == 200
        data = response.json()
        assert "appName" in data or "description" in data
        print("TEST 5 - GET /api/concept ✅")


class TestCoachSearchEndpoints:
    """Tests for public coach search feature v8.9.2"""
    
    def test_06_coach_search_empty_query(self):
        """TEST 6 - Coach search with empty query returns empty array"""
        response = requests.get(f"{API}/coaches/search?q=")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        # Empty query should return empty array (less than 2 chars)
        assert len(data) == 0
        print("TEST 6 - Coach search empty query returns [] ✅")
    
    def test_07_coach_search_short_query(self):
        """TEST 7 - Coach search with 1 character returns empty array"""
        response = requests.get(f"{API}/coaches/search?q=a")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        # Query < 2 chars should return empty array
        assert len(data) == 0
        print("TEST 7 - Coach search short query returns [] ✅")
    
    def test_08_coach_search_valid_query(self):
        """TEST 8 - Coach search with valid query (2+ chars)"""
        response = requests.get(f"{API}/coaches/search?q=test")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        # May return 0 coaches if none exist, but should be valid response
        print(f"TEST 8 - Coach search 'test' - {len(data)} results ✅")
    
    def test_09_coach_search_by_email(self):
        """TEST 9 - Coach search by email pattern"""
        response = requests.get(f"{API}/coaches/search?q=coach")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        # Verify structure if results exist
        for coach in data:
            assert "id" in coach
            assert "name" in coach
        print(f"TEST 9 - Coach search by email pattern - {len(data)} results ✅")
    
    def test_10_coach_search_special_chars(self):
        """TEST 10 - Coach search with special characters"""
        # Test with special chars - should not crash
        response = requests.get(f"{API}/coaches/search?q=test%20coach")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print("TEST 10 - Coach search with special chars - OK ✅")


class TestCoachPublicProfile:
    """Tests for public coach profile endpoint"""
    
    def test_11_coach_public_profile_not_found(self):
        """TEST 11 - Public profile for non-existent coach returns 404"""
        response = requests.get(f"{API}/coaches/public/nonexistent_coach_id_12345")
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data
        print("TEST 11 - Coach public profile 404 for invalid ID ✅")
    
    def test_12_coach_public_profile_structure(self):
        """TEST 12 - Coach public profile returns correct structure"""
        # First, try to get any existing coach from search
        search_response = requests.get(f"{API}/coaches/search?q=aa")
        coaches = search_response.json()
        
        if coaches and len(coaches) > 0:
            coach_id = coaches[0]["id"]
            response = requests.get(f"{API}/coaches/public/{coach_id}")
            assert response.status_code == 200
            data = response.json()
            assert "id" in data
            assert "name" in data
            print(f"TEST 12 - Coach public profile structure verified ✅")
        else:
            # No coaches exist, test that endpoint format is valid
            print("TEST 12 - No coaches exist, skipping profile test ✅ (SKIP)")


class TestStripeConnectEndpoints:
    """Tests for Stripe Connect integration v8.9.2"""
    
    def test_13_stripe_connect_onboard_no_email(self):
        """TEST 13 - Stripe Connect onboard without email returns 400"""
        response = requests.post(f"{API}/coach/stripe-connect/onboard", json={})
        # Should return 400 or 422 for missing email
        assert response.status_code in [400, 422]
        print("TEST 13 - Stripe Connect onboard missing email - 400 ✅")
    
    def test_14_stripe_connect_onboard_invalid_coach(self):
        """TEST 14 - Stripe Connect onboard for non-existent coach returns 404"""
        response = requests.post(f"{API}/coach/stripe-connect/onboard", json={
            "email": "nonexistent_coach_xyz@test.com"
        })
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data
        print("TEST 14 - Stripe Connect onboard invalid coach - 404 ✅")
    
    def test_15_stripe_connect_status_no_email(self):
        """TEST 15 - Stripe Connect status without email returns 401"""
        response = requests.get(f"{API}/coach/stripe-connect/status")
        assert response.status_code == 401
        print("TEST 15 - Stripe Connect status no email - 401 ✅")
    
    def test_16_stripe_connect_status_nonexistent_coach(self):
        """TEST 16 - Stripe Connect status for non-existent coach"""
        response = requests.get(f"{API}/coach/stripe-connect/status", headers={
            "X-User-Email": "nonexistent_coach_xyz@test.com"
        })
        assert response.status_code == 200
        data = response.json()
        # Should return not_found status
        assert data.get("connected") == False
        assert data.get("status") == "not_found"
        print("TEST 16 - Stripe Connect status non-existent coach ✅")


class TestCoachPacksWithSuperAdmin:
    """Tests for coach packs with Super Admin (v8.9 verified)"""
    
    def test_17_get_public_coach_packs(self):
        """TEST 17 - GET public coach packs"""
        response = requests.get(f"{API}/admin/coach-packs")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"TEST 17 - GET /api/admin/coach-packs - {len(data)} packs ✅")
    
    def test_18_get_all_coach_packs_super_admin(self):
        """TEST 18 - GET all coach packs with Super Admin"""
        response = requests.get(f"{API}/admin/coach-packs/all", headers={
            "X-User-Email": SUPER_ADMIN_EMAIL
        })
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"TEST 18 - GET /api/admin/coach-packs/all - {len(data)} packs ✅")
    
    def test_19_get_all_coach_packs_non_admin(self):
        """TEST 19 - GET all coach packs without admin - 403"""
        response = requests.get(f"{API}/admin/coach-packs/all", headers={
            "X-User-Email": "regular_user@test.com"
        })
        assert response.status_code == 403
        print("TEST 19 - Non-admin access to /all - 403 Forbidden ✅")
    
    def test_20_admin_coaches_list(self):
        """TEST 20 - GET /api/admin/coaches list"""
        response = requests.get(f"{API}/admin/coaches", headers={
            "X-User-Email": SUPER_ADMIN_EMAIL
        })
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"TEST 20 - GET /api/admin/coaches - {len(data)} coaches ✅")


class TestDefaultCoachIsolation:
    """Tests for coach_id isolation with DEFAULT_COACH_ID='bassi_default'"""
    
    def test_21_auth_role_super_admin(self):
        """TEST 21 - Auth role returns super_admin for admin email"""
        response = requests.get(f"{API}/auth/role", headers={
            "X-User-Email": SUPER_ADMIN_EMAIL
        })
        assert response.status_code == 200
        data = response.json()
        assert data.get("role") == "super_admin"
        print("TEST 21 - Auth role super_admin verified ✅")
    
    def test_22_auth_role_user(self):
        """TEST 22 - Auth role returns user for regular email"""
        response = requests.get(f"{API}/auth/role", headers={
            "X-User-Email": "regular_user@test.com"
        })
        assert response.status_code == 200
        data = response.json()
        assert data.get("role") == "user"
        print("TEST 22 - Auth role user verified ✅")
    
    def test_23_auth_role_no_email(self):
        """TEST 23 - Auth role with no email returns user"""
        response = requests.get(f"{API}/auth/role")
        assert response.status_code == 200
        data = response.json()
        assert data.get("role") == "user"
        print("TEST 23 - Auth role no email returns user ✅")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
