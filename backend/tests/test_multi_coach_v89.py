"""
Test Suite for Multi-Coach System v8.9 - MISSION SAAS
Tests the following features:
- Coach Packs CRUD (Super Admin only)
- User Role Verification
- Stripe Checkout for Coach Registration
- Coaches Management
"""
import pytest
import requests
import os
import uuid

# API Base URL from environment
BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://promo-credits-lab.preview.emergentagent.com').rstrip('/')

# Super Admin Email for testing
SUPER_ADMIN_EMAIL = "contact.artboost@gmail.com"
NON_ADMIN_EMAIL = "user@example.com"

# Test pack data
TEST_PACK_DATA = {
    "name": f"TEST_Pack_{uuid.uuid4().hex[:6]}",
    "price": 49.0,
    "credits": 100,
    "description": "Test pack for automated testing",
    "features": ["Feature 1", "Feature 2"],
    "visible": True
}

class TestHealthCheck:
    """Health check tests"""
    
    def test_api_health(self):
        """TEST 1: API Health endpoint should return healthy status"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200, f"Health check failed: {response.text}"
        data = response.json()
        assert data.get("status") == "healthy"
        print("✅ TEST 1 - API Health check passed")


class TestCoachPacks:
    """Coach Packs CRUD operations tests"""
    
    def test_get_coach_packs_public(self):
        """TEST 2: GET /api/admin/coach-packs - List available packs (public)"""
        response = requests.get(f"{BASE_URL}/api/admin/coach-packs")
        assert response.status_code == 200, f"GET coach-packs failed: {response.text}"
        
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        print(f"✅ TEST 2 - GET coach-packs returned {len(data)} packs")
    
    def test_get_all_coach_packs_super_admin(self):
        """TEST 3: GET /api/admin/coach-packs/all - Super Admin can access all packs"""
        response = requests.get(
            f"{BASE_URL}/api/admin/coach-packs/all",
            headers={"X-User-Email": SUPER_ADMIN_EMAIL}
        )
        assert response.status_code == 200, f"GET all coach-packs failed: {response.text}"
        
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        print(f"✅ TEST 3 - GET all coach-packs (Super Admin) returned {len(data)} packs")
    
    def test_get_all_coach_packs_non_admin_forbidden(self):
        """TEST 4: GET /api/admin/coach-packs/all - Non-admin gets 403"""
        response = requests.get(
            f"{BASE_URL}/api/admin/coach-packs/all",
            headers={"X-User-Email": NON_ADMIN_EMAIL}
        )
        assert response.status_code == 403, f"Expected 403 for non-admin, got {response.status_code}"
        print("✅ TEST 4 - Non-admin correctly gets 403 Forbidden")
    
    def test_create_coach_pack_super_admin(self):
        """TEST 5: POST /api/admin/coach-packs - Super Admin can create pack"""
        response = requests.post(
            f"{BASE_URL}/api/admin/coach-packs",
            json=TEST_PACK_DATA,
            headers={
                "X-User-Email": SUPER_ADMIN_EMAIL,
                "Content-Type": "application/json"
            }
        )
        assert response.status_code == 200, f"POST coach-packs failed: {response.text}"
        
        data = response.json()
        assert "id" in data, "Created pack should have an ID"
        assert data["name"] == TEST_PACK_DATA["name"], "Name should match"
        assert data["price"] == TEST_PACK_DATA["price"], "Price should match"
        assert data["credits"] == TEST_PACK_DATA["credits"], "Credits should match"
        
        # Store pack_id for cleanup
        TestCoachPacks.created_pack_id = data["id"]
        print(f"✅ TEST 5 - Pack created: {data['name']} (ID: {data['id']})")
    
    def test_create_coach_pack_non_admin_forbidden(self):
        """TEST 6: POST /api/admin/coach-packs - Non-admin gets 403"""
        response = requests.post(
            f"{BASE_URL}/api/admin/coach-packs",
            json=TEST_PACK_DATA,
            headers={
                "X-User-Email": NON_ADMIN_EMAIL,
                "Content-Type": "application/json"
            }
        )
        assert response.status_code == 403, f"Expected 403 for non-admin, got {response.status_code}"
        print("✅ TEST 6 - Non-admin correctly gets 403 Forbidden on create")
    
    def test_update_coach_pack_super_admin(self):
        """TEST 7: PUT /api/admin/coach-packs/{id} - Super Admin can update pack"""
        # Use previously created pack
        pack_id = getattr(TestCoachPacks, 'created_pack_id', None)
        if not pack_id:
            pytest.skip("No pack created in previous test")
        
        updated_data = {"name": f"UPDATED_{TEST_PACK_DATA['name']}", "price": 59.0}
        response = requests.put(
            f"{BASE_URL}/api/admin/coach-packs/{pack_id}",
            json=updated_data,
            headers={
                "X-User-Email": SUPER_ADMIN_EMAIL,
                "Content-Type": "application/json"
            }
        )
        assert response.status_code == 200, f"PUT coach-packs failed: {response.text}"
        
        data = response.json()
        assert data["name"] == updated_data["name"], "Name should be updated"
        assert data["price"] == updated_data["price"], "Price should be updated"
        print(f"✅ TEST 7 - Pack updated: {data['name']}")
    
    def test_delete_coach_pack_super_admin(self):
        """TEST 8: DELETE /api/admin/coach-packs/{id} - Super Admin can delete pack"""
        pack_id = getattr(TestCoachPacks, 'created_pack_id', None)
        if not pack_id:
            pytest.skip("No pack created in previous test")
        
        response = requests.delete(
            f"{BASE_URL}/api/admin/coach-packs/{pack_id}",
            headers={"X-User-Email": SUPER_ADMIN_EMAIL}
        )
        assert response.status_code == 200, f"DELETE coach-packs failed: {response.text}"
        
        data = response.json()
        assert data.get("success") == True, "Delete should return success"
        print(f"✅ TEST 8 - Pack deleted: {pack_id}")


class TestUserRoles:
    """User role verification tests"""
    
    def test_get_role_super_admin(self):
        """TEST 9: GET /api/auth/role - Super Admin role verification"""
        response = requests.get(
            f"{BASE_URL}/api/auth/role",
            headers={"X-User-Email": SUPER_ADMIN_EMAIL}
        )
        assert response.status_code == 200, f"GET auth/role failed: {response.text}"
        
        data = response.json()
        assert data.get("role") == "super_admin", f"Expected super_admin, got {data.get('role')}"
        assert data.get("is_super_admin") == True, "is_super_admin should be True"
        assert data.get("is_coach") == True, "is_coach should be True for Super Admin"
        print("✅ TEST 9 - Super Admin role verified")
    
    def test_get_role_regular_user(self):
        """TEST 10: GET /api/auth/role - Regular user role"""
        response = requests.get(
            f"{BASE_URL}/api/auth/role",
            headers={"X-User-Email": NON_ADMIN_EMAIL}
        )
        assert response.status_code == 200, f"GET auth/role failed: {response.text}"
        
        data = response.json()
        assert data.get("is_super_admin") == False, "Non-admin should not be super_admin"
        print(f"✅ TEST 10 - Regular user role: {data.get('role')}")
    
    def test_get_role_no_email(self):
        """TEST 11: GET /api/auth/role - No email returns default user role"""
        response = requests.get(f"{BASE_URL}/api/auth/role")
        assert response.status_code == 200, f"GET auth/role failed: {response.text}"
        
        data = response.json()
        assert data.get("role") == "user", "Default role should be 'user'"
        assert data.get("is_super_admin") == False
        assert data.get("is_coach") == False
        print("✅ TEST 11 - No email returns default user role")


class TestCoachesManagement:
    """Coaches management tests"""
    
    def test_get_coaches_super_admin(self):
        """TEST 12: GET /api/admin/coaches - Super Admin can list coaches"""
        response = requests.get(
            f"{BASE_URL}/api/admin/coaches",
            headers={"X-User-Email": SUPER_ADMIN_EMAIL}
        )
        assert response.status_code == 200, f"GET coaches failed: {response.text}"
        
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        print(f"✅ TEST 12 - GET coaches returned {len(data)} coaches")
    
    def test_get_coaches_non_admin_forbidden(self):
        """TEST 13: GET /api/admin/coaches - Non-admin gets 403"""
        response = requests.get(
            f"{BASE_URL}/api/admin/coaches",
            headers={"X-User-Email": NON_ADMIN_EMAIL}
        )
        assert response.status_code == 403, f"Expected 403 for non-admin, got {response.status_code}"
        print("✅ TEST 13 - Non-admin correctly gets 403 Forbidden on coaches list")
    
    def test_coach_profile_super_admin(self):
        """TEST 14: GET /api/coach/profile - Super Admin profile"""
        response = requests.get(
            f"{BASE_URL}/api/coach/profile",
            headers={"X-User-Email": SUPER_ADMIN_EMAIL}
        )
        assert response.status_code == 200, f"GET coach/profile failed: {response.text}"
        
        data = response.json()
        assert data.get("is_super_admin") == True, "Super Admin profile should indicate super admin"
        assert data.get("role") == "super_admin"
        print("✅ TEST 14 - Super Admin profile verified")


class TestStripeCheckout:
    """Stripe checkout for coach registration tests"""
    
    def test_create_coach_checkout_missing_fields(self):
        """TEST 15: POST /api/stripe/create-coach-checkout - Missing fields returns 400"""
        response = requests.post(
            f"{BASE_URL}/api/stripe/create-coach-checkout",
            json={"email": "test@test.com"},  # Missing price_id and name
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 400, f"Expected 400 for missing fields, got {response.status_code}"
        print("✅ TEST 15 - Missing fields correctly returns 400")
    
    def test_create_coach_checkout_invalid_pack(self):
        """TEST 16: POST /api/stripe/create-coach-checkout - Invalid pack returns 404"""
        response = requests.post(
            f"{BASE_URL}/api/stripe/create-coach-checkout",
            json={
                "price_id": "price_invalid",
                "pack_id": "non_existent_pack",
                "email": "test@test.com",
                "name": "Test User"
            },
            headers={"Content-Type": "application/json"}
        )
        # Expected 404 for non-existent pack
        assert response.status_code == 404, f"Expected 404 for invalid pack, got {response.status_code}"
        print("✅ TEST 16 - Invalid pack correctly returns 404")


class TestExistingFunctionality:
    """Non-regression tests for existing functionality"""
    
    def test_courses_api(self):
        """TEST 17: GET /api/courses - Courses endpoint works"""
        response = requests.get(f"{BASE_URL}/api/courses")
        assert response.status_code == 200, f"GET courses failed: {response.text}"
        
        data = response.json()
        assert isinstance(data, list), "Courses should return a list"
        print(f"✅ TEST 17 - Courses API returned {len(data)} courses")
    
    def test_offers_api(self):
        """TEST 18: GET /api/offers - Offers endpoint works"""
        response = requests.get(f"{BASE_URL}/api/offers")
        assert response.status_code == 200, f"GET offers failed: {response.text}"
        
        data = response.json()
        assert isinstance(data, list), "Offers should return a list"
        print(f"✅ TEST 18 - Offers API returned {len(data)} offers")
    
    def test_concept_api(self):
        """TEST 19: GET /api/concept - Concept endpoint works"""
        response = requests.get(f"{BASE_URL}/api/concept")
        assert response.status_code == 200, f"GET concept failed: {response.text}"
        
        data = response.json()
        assert "appName" in data or "description" in data, "Concept should have appName or description"
        print("✅ TEST 19 - Concept API works")
    
    def test_payment_links_api(self):
        """TEST 20: GET /api/payment-links - Payment links endpoint works"""
        response = requests.get(f"{BASE_URL}/api/payment-links")
        assert response.status_code == 200, f"GET payment-links failed: {response.text}"
        
        data = response.json()
        # Should have payment method fields
        assert "stripe" in data or "paypal" in data or "twint" in data
        print("✅ TEST 20 - Payment links API works")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
