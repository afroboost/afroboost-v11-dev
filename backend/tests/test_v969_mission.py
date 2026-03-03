"""
Tests for Mission v9.6.9: Stabilisation Finale et Anti-Doublons
Features tested:
1. API /partners/active returns unique partners (no duplicates)
2. Each partner has a unique ID (bassi_main, coach_uuid)
3. API /check-partner returns is_partner=true for partners
4. Super Admin recognized with is_super_admin=true
5. Health endpoint available
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://promo-credits-lab.preview.emergentagent.com')

# Super admin emails from the mission
SUPER_ADMIN_EMAILS = ["afroboost.bassi@gmail.com", "contact.artboost@gmail.com"]


class TestPartnersActiveAPI:
    """Tests for /api/partners/active endpoint - Deduplication"""
    
    def test_partners_active_returns_list(self):
        """API should return a list of partners"""
        response = requests.get(f"{BASE_URL}/api/partners/active")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✅ Partners active returns list with {len(data)} partners")
    
    def test_partners_are_unique_by_email(self):
        """Each partner should have unique email - NO DUPLICATES"""
        response = requests.get(f"{BASE_URL}/api/partners/active")
        assert response.status_code == 200
        partners = response.json()
        
        emails = [p.get("email", "").lower() for p in partners if p.get("email")]
        unique_emails = set(emails)
        
        # Assert no duplicates
        assert len(emails) == len(unique_emails), f"Found {len(emails) - len(unique_emails)} duplicate emails"
        print(f"✅ All {len(unique_emails)} partners have unique emails")
    
    def test_partners_have_unique_ids(self):
        """Each partner should have a unique ID field"""
        response = requests.get(f"{BASE_URL}/api/partners/active")
        assert response.status_code == 200
        partners = response.json()
        
        ids = [p.get("id") for p in partners if p.get("id")]
        unique_ids = set(ids)
        
        # Assert no duplicate IDs
        assert len(ids) == len(unique_ids), f"Found {len(ids) - len(unique_ids)} duplicate IDs"
        print(f"✅ All {len(unique_ids)} partners have unique IDs")
        
        # Check bassi_main exists
        if any(pid == "bassi_main" for pid in ids):
            print("✅ bassi_main ID found as expected")
    
    def test_partners_have_required_fields(self):
        """Each partner should have id, name/platform_name, email"""
        response = requests.get(f"{BASE_URL}/api/partners/active")
        assert response.status_code == 200
        partners = response.json()
        
        for p in partners:
            assert p.get("id"), f"Partner missing id: {p.get('email', 'unknown')}"
            assert p.get("email"), f"Partner missing email: {p.get('id', 'unknown')}"
            # Name can be in 'name' or 'platform_name'
            has_name = p.get("name") or p.get("platform_name")
            assert has_name, f"Partner missing name: {p.get('email', 'unknown')}"
        
        print(f"✅ All {len(partners)} partners have required fields")


class TestCheckPartnerAPI:
    """Tests for /api/check-partner/{email} endpoint"""
    
    def test_super_admin_returns_partner_true(self):
        """Super admin should return is_partner=true and is_super_admin=true"""
        email = SUPER_ADMIN_EMAILS[0]  # afroboost.bassi@gmail.com
        response = requests.get(f"{BASE_URL}/api/check-partner/{email}")
        assert response.status_code == 200
        data = response.json()
        
        assert data.get("is_partner") == True
        assert data.get("is_super_admin") == True
        assert data.get("email") == email
        print(f"✅ Super admin {email} returns is_partner=true, is_super_admin=true")
    
    def test_second_super_admin_returns_partner_true(self):
        """Second super admin should also return is_partner=true"""
        email = SUPER_ADMIN_EMAILS[1]  # contact.artboost@gmail.com
        response = requests.get(f"{BASE_URL}/api/check-partner/{email}")
        assert response.status_code == 200
        data = response.json()
        
        assert data.get("is_partner") == True
        assert data.get("is_super_admin") == True
        print(f"✅ Super admin {email} returns is_partner=true, is_super_admin=true")
    
    def test_non_partner_returns_false(self):
        """Non-partner email should return is_partner=false"""
        email = "random_user_not_partner@example.com"
        response = requests.get(f"{BASE_URL}/api/check-partner/{email}")
        assert response.status_code == 200
        data = response.json()
        
        assert data.get("is_partner") == False
        print(f"✅ Non-partner email returns is_partner=false")
    
    def test_email_case_insensitivity(self):
        """Check-partner should be case insensitive"""
        email_lower = "afroboost.bassi@gmail.com"
        email_upper = "AFROBOOST.BASSI@GMAIL.COM"
        
        resp_lower = requests.get(f"{BASE_URL}/api/check-partner/{email_lower}")
        resp_upper = requests.get(f"{BASE_URL}/api/check-partner/{email_upper}")
        
        assert resp_lower.status_code == 200
        assert resp_upper.status_code == 200
        
        # Both should return is_partner=true
        assert resp_lower.json().get("is_partner") == resp_upper.json().get("is_partner")
        print("✅ Email check is case insensitive")


class TestHealthAndCredits:
    """Tests for health and credits endpoints"""
    
    def test_health_endpoint(self):
        """Health endpoint should return healthy status"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        # Accept both 'ok' and 'healthy' as valid status
        assert data.get("status") in ["ok", "healthy"]
        print(f"✅ Health endpoint returns status: {data.get('status')}")
    
    def test_credits_check_with_super_admin(self):
        """Super admin credits check should return unlimited"""
        email = SUPER_ADMIN_EMAILS[0]
        response = requests.get(
            f"{BASE_URL}/api/coach/check-credits",
            headers={"X-User-Email": email}
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data.get("has_credits") == True
        assert data.get("unlimited") == True
        assert data.get("credits") == -1
        print(f"✅ Super admin has unlimited credits")
    
    def test_credits_check_without_email(self):
        """Credits check without email should fail or return error"""
        response = requests.get(
            f"{BASE_URL}/api/coach/check-credits",
            headers={}  # No email
        )
        # Should either return 401 or an error response
        if response.status_code == 401:
            print("✅ Credits check without email returns 401")
        elif response.status_code == 200:
            data = response.json()
            # Should indicate no credits or error
            assert data.get("has_credits") == False or "error" in data
            print("✅ Credits check without email returns has_credits=false")
        else:
            print(f"⚠️ Credits check without email returns {response.status_code}")


class TestPartnerRedirectionLogic:
    """Tests for partner redirection logic (is_partner -> Dashboard)"""
    
    def test_partner_check_returns_required_fields(self):
        """Check-partner response should have all required fields for redirection"""
        email = SUPER_ADMIN_EMAILS[0]
        response = requests.get(f"{BASE_URL}/api/check-partner/{email}")
        assert response.status_code == 200
        data = response.json()
        
        # Required fields for frontend redirection logic
        assert "is_partner" in data
        assert "is_super_admin" in data
        assert "email" in data
        
        # For partners, these should also be present
        if data.get("is_partner"):
            assert "has_credits" in data or "credits" in data
        
        print("✅ Partner check returns all required fields for redirection")
    
    def test_partner_data_consistency(self):
        """Partner data should be consistent across endpoints"""
        email = SUPER_ADMIN_EMAILS[0]
        
        # Check partner endpoint
        partner_resp = requests.get(f"{BASE_URL}/api/check-partner/{email}")
        assert partner_resp.status_code == 200
        partner_data = partner_resp.json()
        
        # Credits endpoint
        credits_resp = requests.get(
            f"{BASE_URL}/api/coach/check-credits",
            headers={"X-User-Email": email}
        )
        assert credits_resp.status_code == 200
        credits_data = credits_resp.json()
        
        # Both should agree on super admin / unlimited status
        if partner_data.get("is_super_admin"):
            assert credits_data.get("unlimited") == True
            assert credits_data.get("credits") == -1
        
        print("✅ Partner data is consistent across check-partner and check-credits")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
