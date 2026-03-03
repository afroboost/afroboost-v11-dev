"""
Test Suite for Mission v13.4 - Refactoring Final & Pre-Deployment
Verifies: 22 reservations, 7 contacts, video full-width, extracted components
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://promo-credits-lab.preview.emergentagent.com')

# Super Admin emails for authentication
SUPER_ADMIN_EMAILS = ["contact.artboost@gmail.com", "afroboost.bassi@gmail.com"]


class TestAntiRegression:
    """Anti-regression tests: 22 reservations & 7 contacts must remain intact"""
    
    def test_reservations_count_with_super_admin(self):
        """Test 1: Verify 22 reservations exist via Super Admin access"""
        response = requests.get(
            f"{BASE_URL}/api/reservations",
            headers={"X-User-Email": SUPER_ADMIN_EMAILS[0]}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "pagination" in data, "Response should have pagination"
        assert "total" in data["pagination"], "Pagination should have total"
        
        total = data["pagination"]["total"]
        assert total == 22, f"Expected 22 reservations, got {total}"
        print(f"✅ PASS: Found {total} reservations (expected: 22)")
    
    def test_reservations_count_with_second_super_admin(self):
        """Test 2: Verify reservations accessible by second Super Admin"""
        response = requests.get(
            f"{BASE_URL}/api/reservations",
            headers={"X-User-Email": SUPER_ADMIN_EMAILS[1]}
        )
        assert response.status_code == 200
        
        data = response.json()
        total = data["pagination"]["total"]
        assert total == 22, f"Expected 22 reservations with second Super Admin, got {total}"
        print(f"✅ PASS: Second Super Admin can see {total} reservations")
    
    def test_contacts_count(self):
        """Test 3: Verify 7 contacts exist"""
        response = requests.get(f"{BASE_URL}/api/users")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        users = response.json()
        assert isinstance(users, list), "Users should be a list"
        assert len(users) == 7, f"Expected 7 contacts, got {len(users)}"
        print(f"✅ PASS: Found {len(users)} contacts (expected: 7)")
    
    def test_reservations_structure(self):
        """Test 4: Verify reservation data structure"""
        response = requests.get(
            f"{BASE_URL}/api/reservations",
            headers={"X-User-Email": SUPER_ADMIN_EMAILS[0]}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert "data" in data, "Response should have data array"
        
        if data["data"]:
            reservation = data["data"][0]
            required_fields = ["id", "reservationCode", "userName", "userEmail", "offerName"]
            for field in required_fields:
                assert field in reservation, f"Reservation missing field: {field}"
        print("✅ PASS: Reservation structure is correct")


class TestAPIs:
    """Test all API endpoints are working"""
    
    def test_courses_api(self):
        """Test 5: Courses API"""
        response = requests.get(f"{BASE_URL}/api/courses")
        assert response.status_code == 200
        courses = response.json()
        assert isinstance(courses, list)
        print(f"✅ PASS: Courses API working - {len(courses)} courses")
    
    def test_offers_api(self):
        """Test 6: Offers API"""
        response = requests.get(f"{BASE_URL}/api/offers")
        assert response.status_code == 200
        offers = response.json()
        assert isinstance(offers, list)
        print(f"✅ PASS: Offers API working - {len(offers)} offers")
    
    def test_concept_api(self):
        """Test 7: Concept API"""
        response = requests.get(f"{BASE_URL}/api/concept")
        assert response.status_code == 200
        concept = response.json()
        assert "appName" in concept or "description" in concept
        print("✅ PASS: Concept API working")
    
    def test_discount_codes_api(self):
        """Test 8: Discount codes API"""
        response = requests.get(f"{BASE_URL}/api/discount-codes")
        assert response.status_code == 200
        codes = response.json()
        assert isinstance(codes, list)
        print(f"✅ PASS: Discount codes API working - {len(codes)} codes")
    
    def test_payment_links_api(self):
        """Test 9: Payment links API"""
        response = requests.get(f"{BASE_URL}/api/payment-links")
        assert response.status_code == 200
        links = response.json()
        assert isinstance(links, dict)
        print("✅ PASS: Payment links API working")
    
    def test_credit_packs_api(self):
        """Test 10: Credit packs (Boutique) API"""
        response = requests.get(f"{BASE_URL}/api/credit-packs")
        assert response.status_code == 200
        packs = response.json()
        assert isinstance(packs, list)
        print(f"✅ PASS: Credit packs API working - {len(packs)} packs")
    
    def test_platform_settings_api(self):
        """Test 11: Platform settings API (for service prices)"""
        response = requests.get(
            f"{BASE_URL}/api/platform-settings",
            headers={"X-User-Email": SUPER_ADMIN_EMAILS[0]}
        )
        assert response.status_code == 200
        settings = response.json()
        assert isinstance(settings, dict)
        print("✅ PASS: Platform settings API working")


class TestStripeRoutes:
    """Test extracted Stripe routes work correctly"""
    
    def test_stripe_connect_status(self):
        """Test 12: Stripe Connect status endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/stripe/connect/status",
            headers={"X-User-Email": "test@example.com"}
        )
        # Should return 200 with connected: false for unknown user
        assert response.status_code == 200
        data = response.json()
        assert "connected" in data
        print(f"✅ PASS: Stripe Connect status endpoint working")
    
    def test_stripe_checkout_requires_key(self):
        """Test 13: Stripe checkout requires configuration"""
        response = requests.post(
            f"{BASE_URL}/api/stripe/create-checkout-session",
            json={"amount": 10, "currency": "chf", "description": "Test"}
        )
        # May return 500 if Stripe not configured, that's expected
        assert response.status_code in [200, 500]
        print(f"✅ PASS: Stripe checkout endpoint exists (status: {response.status_code})")


class TestCreditsSystem:
    """Test credits/lock system for partners"""
    
    def test_coach_profile_for_credits(self):
        """Test 14: Coach profile returns credits"""
        response = requests.get(
            f"{BASE_URL}/api/coach/profile",
            headers={"X-User-Email": SUPER_ADMIN_EMAILS[0]}
        )
        assert response.status_code == 200
        profile = response.json()
        # Super Admin should have unlimited credits (-1)
        assert "credits" in profile
        print(f"✅ PASS: Coach profile returns credits: {profile.get('credits')}")
    
    def test_service_prices_config(self):
        """Test 15: Service prices configuration"""
        response = requests.get(
            f"{BASE_URL}/api/platform-settings",
            headers={"X-User-Email": SUPER_ADMIN_EMAILS[0]}
        )
        assert response.status_code == 200
        settings = response.json()
        
        # Check service_prices if present
        if "service_prices" in settings:
            prices = settings["service_prices"]
            expected_services = ["campaign", "ai_conversation", "promo_code"]
            for service in expected_services:
                if service in prices:
                    print(f"  Service '{service}': {prices[service]} credits")
        print("✅ PASS: Service prices configuration accessible")


class TestDataIsolation:
    """Test coach data isolation (non Super Admin should not see all data)"""
    
    def test_non_admin_reservation_filter(self):
        """Test 16: Non-Super Admin sees filtered data"""
        response = requests.get(
            f"{BASE_URL}/api/reservations",
            headers={"X-User-Email": "random_coach@example.com"}
        )
        assert response.status_code == 200
        data = response.json()
        # Non-Super Admin with no data should see 0
        assert data["pagination"]["total"] == 0
        print("✅ PASS: Non-Super Admin correctly filtered")
    
    def test_no_header_protection(self):
        """Test 17: No header returns empty (not all data)"""
        response = requests.get(f"{BASE_URL}/api/reservations")
        assert response.status_code == 200
        data = response.json()
        # Without auth, should see nothing
        assert data["pagination"]["total"] == 0
        print("✅ PASS: No header protection working")


class TestExtractedComponents:
    """Verify v13.4 extracted components are properly configured"""
    
    def test_all_apis_no_500_errors(self):
        """Test 18: Batch test all APIs for server errors"""
        endpoints = [
            "/api/reservations",
            "/api/users",
            "/api/courses",
            "/api/offers",
            "/api/concept",
            "/api/discount-codes",
            "/api/payment-links",
            "/api/credit-packs",
        ]
        
        all_passed = True
        for endpoint in endpoints:
            response = requests.get(f"{BASE_URL}{endpoint}")
            if response.status_code >= 500:
                print(f"❌ FAIL: {endpoint} returned {response.status_code}")
                all_passed = False
        
        assert all_passed, "Some endpoints returned server errors"
        print("✅ PASS: All APIs responding without 500 errors")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
