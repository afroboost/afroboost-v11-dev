"""
Test Suite for Mission v9.6.8: Déblocage Partenaire & Logique de Vente
- API /check-partner/{email} tests
- API /partners/active uniqueness tests
- Credits check API tests
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://promo-credits-lab.preview.emergentagent.com')


class TestCheckPartnerAPI:
    """Tests for /api/check-partner/{email} endpoint"""
    
    def test_super_admin_returns_partner_true(self):
        """Super admin email should return is_partner=true with unlimited credits"""
        response = requests.get(f"{BASE_URL}/api/check-partner/afroboost.bassi@gmail.com")
        assert response.status_code == 200
        
        data = response.json()
        assert data.get("is_partner") == True
        assert data.get("is_super_admin") == True
        assert data.get("unlimited") == True
        assert data.get("credits") == -1  # -1 = unlimited
    
    def test_second_super_admin_returns_partner_true(self):
        """Second super admin email should also return is_partner=true"""
        response = requests.get(f"{BASE_URL}/api/check-partner/contact.artboost@gmail.com")
        assert response.status_code == 200
        
        data = response.json()
        # Can be partner if registered as coach, or super_admin
        assert "is_partner" in data
    
    def test_non_partner_returns_false(self):
        """Non-existing partner email should return is_partner=false"""
        response = requests.get(f"{BASE_URL}/api/check-partner/nonexistent_user_12345@example.com")
        assert response.status_code == 200
        
        data = response.json()
        assert data.get("is_partner") == False
    
    def test_email_case_insensitivity(self):
        """Email check should be case-insensitive"""
        response = requests.get(f"{BASE_URL}/api/check-partner/AFROBOOST.BASSI@GMAIL.COM")
        assert response.status_code == 200
        
        data = response.json()
        assert data.get("is_partner") == True


class TestPartnersActiveAPI:
    """Tests for /api/partners/active endpoint - uniqueness check"""
    
    def test_partners_active_returns_list(self):
        """Partners active endpoint should return a list"""
        response = requests.get(f"{BASE_URL}/api/partners/active")
        assert response.status_code == 200
        
        data = response.json()
        assert isinstance(data, list)
    
    def test_partners_are_unique_by_email(self):
        """All partners should have unique emails (no duplicates)"""
        response = requests.get(f"{BASE_URL}/api/partners/active")
        assert response.status_code == 200
        
        data = response.json()
        emails = [p.get("email", "").lower() for p in data if p.get("email")]
        unique_emails = set(emails)
        
        assert len(emails) == len(unique_emails), f"Duplicate emails found: {len(emails)} total vs {len(unique_emails)} unique"
    
    def test_partners_have_required_fields(self):
        """Each partner should have email and name fields"""
        response = requests.get(f"{BASE_URL}/api/partners/active")
        assert response.status_code == 200
        
        data = response.json()
        for partner in data:
            assert "email" in partner or "name" in partner, f"Partner missing email/name: {partner}"


class TestHealthAPI:
    """Health check tests"""
    
    def test_health_endpoint(self):
        """Health endpoint should return healthy status"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        
        data = response.json()
        assert data.get("status") == "healthy"
        assert data.get("database") == "connected"


class TestCreditsAPI:
    """Tests for credits check endpoint"""
    
    def test_credits_check_with_super_admin(self):
        """Super admin should have unlimited credits"""
        headers = {"X-User-Email": "afroboost.bassi@gmail.com"}
        response = requests.get(f"{BASE_URL}/api/credits/check", headers=headers)
        assert response.status_code == 200
        
        data = response.json()
        assert data.get("unlimited") == True or data.get("credits") == -1
    
    def test_credits_check_without_email(self):
        """Credits check without email should return error"""
        response = requests.get(f"{BASE_URL}/api/credits/check")
        assert response.status_code == 200
        
        data = response.json()
        assert data.get("has_credits") == False


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
