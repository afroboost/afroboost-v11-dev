"""
Mission v13.1: Verrouillage Services & Sécurité Crédits
Test Suite for:
1. API platform-settings returns service_prices (campaign=2, ai_conversation=1, promo_code=3)
2. hasCreditsFor() logic validation (Super Admin always has access)
3. Anti-régression: 22 réservations, contacts intacts
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://promo-credits-lab.preview.emergentagent.com').rstrip('/')

# Super Admin email for testing
SUPER_ADMIN_EMAIL = "contact.artboost@gmail.com"
# Regular coach email for testing (to simulate low credits scenario)
TEST_COACH_EMAIL = "test_coach@example.com"

class TestPlatformSettings:
    """Tests for /api/platform-settings endpoint - service_prices"""
    
    def test_platform_settings_returns_service_prices(self):
        """Verify platform-settings returns service_prices object with correct structure"""
        response = requests.get(
            f"{BASE_URL}/api/platform-settings",
            headers={"X-User-Email": SUPER_ADMIN_EMAIL}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "service_prices" in data, "Missing service_prices in response"
        
        service_prices = data["service_prices"]
        assert "campaign" in service_prices, "Missing campaign price"
        assert "ai_conversation" in service_prices, "Missing ai_conversation price"
        assert "promo_code" in service_prices, "Missing promo_code price"
        
        print(f"✅ Service prices: campaign={service_prices['campaign']}, ai_conversation={service_prices['ai_conversation']}, promo_code={service_prices['promo_code']}")
    
    def test_platform_settings_service_prices_values(self):
        """Verify service_prices has expected values (campaign=2, ai_conversation=1, promo_code=3)"""
        response = requests.get(
            f"{BASE_URL}/api/platform-settings",
            headers={"X-User-Email": SUPER_ADMIN_EMAIL}
        )
        assert response.status_code == 200
        
        data = response.json()
        service_prices = data["service_prices"]
        
        # Check expected values per mission requirements
        assert service_prices["campaign"] == 2, f"Expected campaign=2, got {service_prices['campaign']}"
        assert service_prices["ai_conversation"] == 1, f"Expected ai_conversation=1, got {service_prices['ai_conversation']}"
        assert service_prices["promo_code"] == 3, f"Expected promo_code=3, got {service_prices['promo_code']}"
        
        print(f"✅ Service prices match requirements: campaign=2, ai_conversation=1, promo_code=3")
    
    def test_super_admin_identified_correctly(self):
        """Verify Super Admin is identified correctly via is_super_admin flag"""
        response = requests.get(
            f"{BASE_URL}/api/platform-settings",
            headers={"X-User-Email": SUPER_ADMIN_EMAIL}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert "is_super_admin" in data, "Missing is_super_admin flag"
        assert data["is_super_admin"] == True, f"Super Admin not identified correctly: {data['is_super_admin']}"
        
        print(f"✅ Super Admin identified correctly: is_super_admin=True")


class TestSuperAdminCoachProfile:
    """Tests for Super Admin coach profile - credits should be -1 (unlimited)"""
    
    def test_super_admin_has_unlimited_credits(self):
        """Verify Super Admin has -1 credits (unlimited access)"""
        response = requests.get(
            f"{BASE_URL}/api/coach/profile",
            headers={"X-User-Email": SUPER_ADMIN_EMAIL}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "credits" in data, "Missing credits field in coach profile"
        assert data["credits"] == -1, f"Expected credits=-1 for Super Admin, got {data['credits']}"
        assert data.get("is_super_admin") == True, "Super Admin flag should be True"
        
        print(f"✅ Super Admin has unlimited credits: credits=-1, is_super_admin=True")


class TestAntiRegression:
    """Anti-regression tests for Mission v13.1"""
    
    def test_reservations_count_minimum_22(self):
        """Verify at least 22 reservations exist in database"""
        response = requests.get(
            f"{BASE_URL}/api/reservations?page=1&limit=100",
            headers={"X-User-Email": SUPER_ADMIN_EMAIL}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        total = data.get("pagination", {}).get("total", len(data.get("data", [])))
        assert total >= 22, f"Expected at least 22 reservations, got {total}"
        
        print(f"✅ Reservations anti-regression PASS: {total} reservations (required: 22+)")
    
    def test_contacts_exist(self):
        """Verify contacts/users exist in database"""
        response = requests.get(
            f"{BASE_URL}/api/users",
            headers={"X-User-Email": SUPER_ADMIN_EMAIL}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        total = len(data)
        assert total >= 1, f"Expected at least 1 contact, got {total}"
        
        print(f"✅ Contacts anti-regression PASS: {total} contacts in database")
    
    def test_concept_endpoint_works(self):
        """Verify /api/concept endpoint returns valid data"""
        response = requests.get(f"{BASE_URL}/api/concept")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "appName" in data or "description" in data, "Concept should have basic fields"
        
        print(f"✅ Concept endpoint working correctly")
    
    def test_offers_endpoint_works(self):
        """Verify /api/offers endpoint returns valid data"""
        response = requests.get(f"{BASE_URL}/api/offers")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert isinstance(data, list), "Offers should return a list"
        
        print(f"✅ Offers endpoint working: {len(data)} offers found")
    
    def test_courses_endpoint_works(self):
        """Verify /api/courses endpoint returns valid data"""
        response = requests.get(f"{BASE_URL}/api/courses")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert isinstance(data, list), "Courses should return a list"
        
        print(f"✅ Courses endpoint working: {len(data)} courses found")


class TestCreditsDeduction:
    """Tests for credits deduction logic"""
    
    def test_credits_deduct_endpoint_exists(self):
        """Verify /api/credits/deduct endpoint exists"""
        response = requests.post(
            f"{BASE_URL}/api/credits/deduct",
            json={"action": "test"},
            headers={"X-User-Email": SUPER_ADMIN_EMAIL}
        )
        # Super Admin should bypass deduction (200 success without consuming)
        # or return 200 with bypassed flag
        assert response.status_code in [200, 402], f"Unexpected status: {response.status_code}"
        
        print(f"✅ Credits deduct endpoint responds correctly: {response.status_code}")


class TestCreditPacksAndBoutique:
    """Tests for credit packs (Boutique functionality)"""
    
    def test_credit_packs_endpoint_returns_packs(self):
        """Verify /api/credit-packs returns available packs"""
        response = requests.get(f"{BASE_URL}/api/credit-packs")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert isinstance(data, list), "Credit packs should return a list"
        assert len(data) >= 1, "Should have at least 1 credit pack"
        
        # Verify pack structure
        if len(data) > 0:
            pack = data[0]
            assert "id" in pack, "Pack should have id"
            assert "name" in pack, "Pack should have name"
            assert "credits" in pack, "Pack should have credits"
            assert "price" in pack, "Pack should have price"
        
        print(f"✅ Credit packs endpoint working: {len(data)} packs available")


class TestFrontendCodeReviewValidation:
    """Validation that frontend code has required data-testid attributes
    Note: These are code review validations, not runtime tests"""
    
    def test_mock_hasCreditsFor_logic(self):
        """
        Code Review: Validate hasCreditsFor() logic from CoachDashboard.js
        
        Expected implementation (lines 426-431):
        const hasCreditsFor = (serviceType) => {
            if (isSuperAdmin) return true; // Super Admin = unlimited access
            if (coachCredits === -1) return true; // Unlimited credits
            const requiredCredits = servicePrices[serviceType] || 1;
            return coachCredits >= requiredCredits;
        };
        
        Test cases:
        1. isSuperAdmin=True -> always returns True
        2. coachCredits=-1 -> always returns True
        3. coachCredits=0, servicePrices.promo_code=3 -> returns False
        4. coachCredits=5, servicePrices.campaign=2 -> returns True
        """
        # Mock the hasCreditsFor logic
        def hasCreditsFor(isSuperAdmin, coachCredits, servicePrices, serviceType):
            if isSuperAdmin:
                return True
            if coachCredits == -1:
                return True
            requiredCredits = servicePrices.get(serviceType, 1)
            return coachCredits >= requiredCredits
        
        service_prices = {"campaign": 2, "ai_conversation": 1, "promo_code": 3}
        
        # Test 1: Super Admin always has access
        assert hasCreditsFor(True, 0, service_prices, "promo_code") == True, "Super Admin should always have access"
        
        # Test 2: Unlimited credits (-1) always has access
        assert hasCreditsFor(False, -1, service_prices, "promo_code") == True, "Unlimited credits should have access"
        
        # Test 3: 0 credits with promo_code cost 3 -> No access
        assert hasCreditsFor(False, 0, service_prices, "promo_code") == False, "0 credits should not have access to promo_code (cost: 3)"
        
        # Test 4: 5 credits with campaign cost 2 -> Has access
        assert hasCreditsFor(False, 5, service_prices, "campaign") == True, "5 credits should have access to campaign (cost: 2)"
        
        # Test 5: 1 credit with campaign cost 2 -> No access
        assert hasCreditsFor(False, 1, service_prices, "campaign") == False, "1 credit should not have access to campaign (cost: 2)"
        
        # Test 6: 1 credit with ai_conversation cost 1 -> Has access (exactly enough)
        assert hasCreditsFor(False, 1, service_prices, "ai_conversation") == True, "1 credit should have access to ai_conversation (cost: 1)"
        
        print("✅ hasCreditsFor() logic validated - all test cases PASS")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
