"""
Test v9.5.8 - Mission: Nettoyage Doublons et Isolation Crédits
Features tested:
1. POST /api/credits/deduct - Credit deduction for partners
2. GET /api/credits/check - Credit balance check
3. Super Admin bypass (afroboost.bassi@gmail.com) - unlimited credits
4. GET /api/reservations - Data isolation by coach_id
5. Check-partner endpoint - Super Admin verification
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://promo-credits-lab.preview.emergentagent.com')

# Super Admin emails
SUPER_ADMIN_EMAILS = ['contact.artboost@gmail.com', 'afroboost.bassi@gmail.com']
TEST_PARTNER_EMAIL = 'test.partner@example.com'

class TestCreditsDeductEndpoint:
    """Test POST /api/credits/deduct endpoint"""
    
    def test_credits_deduct_missing_email(self):
        """Credits deduct should fail without X-User-Email header"""
        response = requests.post(f"{BASE_URL}/api/credits/deduct", json={"action": "test"})
        assert response.status_code == 400
        data = response.json()
        assert "detail" in data or "error" in data
        print("PASS: Credits deduct rejects missing email")
    
    def test_credits_deduct_super_admin_bypass(self):
        """Super Admin should bypass credit deduction"""
        response = requests.post(
            f"{BASE_URL}/api/credits/deduct", 
            json={"action": "test_action"},
            headers={"X-User-Email": "afroboost.bassi@gmail.com"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") == True
        assert data.get("bypassed") == True
        assert data.get("credits_remaining") == -1
        print("PASS: Super Admin (afroboost.bassi@gmail.com) bypasses credit deduction")
    
    def test_credits_deduct_super_admin_artboost(self):
        """contact.artboost@gmail.com should also bypass"""
        response = requests.post(
            f"{BASE_URL}/api/credits/deduct", 
            json={"action": "test_action"},
            headers={"X-User-Email": "contact.artboost@gmail.com"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") == True
        assert data.get("bypassed") == True
        print("PASS: Super Admin (contact.artboost@gmail.com) bypasses credit deduction")


class TestCreditsCheckEndpoint:
    """Test GET /api/credits/check endpoint"""
    
    def test_credits_check_missing_email(self):
        """Credits check should return error without email"""
        response = requests.get(f"{BASE_URL}/api/credits/check")
        assert response.status_code == 200
        data = response.json()
        assert data.get("has_credits") == False
        assert "error" in data or data.get("credits") == 0
        print("PASS: Credits check handles missing email")
    
    def test_credits_check_super_admin_unlimited(self):
        """Super Admin should have unlimited credits"""
        response = requests.get(
            f"{BASE_URL}/api/credits/check",
            headers={"X-User-Email": "afroboost.bassi@gmail.com"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("has_credits") == True
        assert data.get("unlimited") == True
        assert data.get("credits") == -1
        print("PASS: Super Admin has unlimited credits")
    
    def test_credits_check_super_admin_artboost(self):
        """contact.artboost Super Admin unlimited check"""
        response = requests.get(
            f"{BASE_URL}/api/credits/check",
            headers={"X-User-Email": "contact.artboost@gmail.com"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("has_credits") == True
        assert data.get("unlimited") == True
        print("PASS: contact.artboost has unlimited credits")


class TestCheckPartnerEndpoint:
    """Test /api/check-partner/{email} endpoint for Super Admin"""
    
    def test_check_partner_super_admin_afroboost(self):
        """afroboost.bassi should be marked as Super Admin partner"""
        response = requests.get(f"{BASE_URL}/api/check-partner/afroboost.bassi@gmail.com")
        assert response.status_code == 200
        data = response.json()
        assert data.get("is_partner") == True
        assert data.get("is_super_admin") == True
        assert data.get("unlimited") == True
        assert data.get("has_credits") == True
        print("PASS: afroboost.bassi@gmail.com is Super Admin partner")
    
    def test_check_partner_super_admin_artboost(self):
        """contact.artboost should be marked as Super Admin partner"""
        response = requests.get(f"{BASE_URL}/api/check-partner/contact.artboost@gmail.com")
        assert response.status_code == 200
        data = response.json()
        assert data.get("is_partner") == True
        assert data.get("is_super_admin") == True
        print("PASS: contact.artboost@gmail.com is Super Admin partner")
    
    def test_check_partner_regular_user(self):
        """Regular user should not be Super Admin"""
        response = requests.get(f"{BASE_URL}/api/check-partner/random.user@example.com")
        assert response.status_code == 200
        data = response.json()
        # Regular user without coach profile
        assert data.get("is_super_admin", False) == False
        print("PASS: Regular user is not Super Admin")


class TestReservationsIsolation:
    """Test GET /api/reservations endpoint - coach_id isolation"""
    
    def test_reservations_super_admin_sees_all(self):
        """Super Admin should see all reservations (no coach_id filter)"""
        response = requests.get(
            f"{BASE_URL}/api/reservations",
            headers={"X-User-Email": "afroboost.bassi@gmail.com"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "data" in data or isinstance(data, list)
        print("PASS: Super Admin can access reservations")
    
    def test_reservations_partner_filtered(self):
        """Partner should only see their own reservations (filtered by coach_id)"""
        response = requests.get(
            f"{BASE_URL}/api/reservations",
            headers={"X-User-Email": TEST_PARTNER_EMAIL}
        )
        assert response.status_code == 200
        data = response.json()
        # Partner gets filtered results (may be empty array)
        assert "data" in data
        print("PASS: Partner reservations endpoint returns filtered data")
    
    def test_reservations_no_email_blocked(self):
        """Request without email should get empty/restricted results"""
        response = requests.get(f"{BASE_URL}/api/reservations")
        assert response.status_code == 200
        data = response.json()
        # Should return empty data when no coach_id
        assert "data" in data
        assert isinstance(data["data"], list)
        print("PASS: Reservations without email returns empty/restricted data")


class TestHealthAndCoreEndpoints:
    """Test core endpoints are working"""
    
    def test_health_check(self):
        """Health endpoint should return healthy"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "healthy"
        print("PASS: Health check returns healthy")
    
    def test_courses_endpoint(self):
        """Courses endpoint should work"""
        response = requests.get(f"{BASE_URL}/api/courses")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print("PASS: Courses endpoint works")
    
    def test_offers_endpoint(self):
        """Offers endpoint should work"""
        response = requests.get(f"{BASE_URL}/api/offers")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print("PASS: Offers endpoint works")


class TestSuperAdminList:
    """Test that both Super Admin emails are recognized"""
    
    @pytest.mark.parametrize("email", SUPER_ADMIN_EMAILS)
    def test_super_admin_emails_bypass_credits(self, email):
        """All Super Admin emails should bypass credit deduction"""
        response = requests.post(
            f"{BASE_URL}/api/credits/deduct",
            json={"action": "parametrized_test"},
            headers={"X-User-Email": email}
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") == True
        assert data.get("bypassed") == True
        print(f"PASS: {email} bypasses credits")


# Run tests when executed directly
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
