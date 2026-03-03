"""
Mission v9.7.2 Tests - Unicité des comptes et logique de navigation
- Test /api/partners/active returns unique partners
- Test check-partner endpoint
- Verify partner structure
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://promo-credits-lab.preview.emergentagent.com')

class TestPartnersActiveAPI:
    """Tests for /api/partners/active endpoint - Mission v9.7.2"""
    
    def test_partners_active_returns_list(self):
        """Test that /api/partners/active returns a list"""
        response = requests.get(f"{BASE_URL}/api/partners/active")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ /api/partners/active returns list with {len(data)} partners")
    
    def test_partners_are_unique_by_email(self):
        """Mission v9.7.2 - Verify no duplicate partners by email"""
        response = requests.get(f"{BASE_URL}/api/partners/active")
        assert response.status_code == 200
        data = response.json()
        
        emails = [p.get('email', '').lower().strip() for p in data if p.get('email')]
        unique_emails = set(emails)
        
        # Check for duplicates
        assert len(emails) == len(unique_emails), f"Found duplicate emails! Total: {len(emails)}, Unique: {len(unique_emails)}"
        print(f"✓ All {len(data)} partners have unique emails")
        print(f"  Emails: {emails}")
    
    def test_partners_have_unique_ids(self):
        """Verify each partner has a unique ID"""
        response = requests.get(f"{BASE_URL}/api/partners/active")
        assert response.status_code == 200
        data = response.json()
        
        ids = [p.get('id', '') for p in data if p.get('id')]
        unique_ids = set(ids)
        
        assert len(ids) == len(unique_ids), f"Found duplicate IDs!"
        print(f"✓ All partners have unique IDs: {ids}")
    
    def test_partners_have_required_fields(self):
        """Verify each partner has required fields"""
        response = requests.get(f"{BASE_URL}/api/partners/active")
        assert response.status_code == 200
        data = response.json()
        
        required_fields = ['email', 'id']
        for partner in data:
            for field in required_fields:
                assert field in partner, f"Partner missing field: {field}"
        print(f"✓ All partners have required fields: {required_fields}")


class TestCheckPartnerAPI:
    """Tests for /api/check-partner endpoint"""
    
    def test_super_admin_is_partner(self):
        """Super admin should return is_partner: true"""
        email = "afroboost.bassi@gmail.com"
        response = requests.get(f"{BASE_URL}/api/check-partner/{email}")
        assert response.status_code == 200
        data = response.json()
        
        assert data.get('is_partner') == True, f"Super admin should be is_partner=true"
        assert data.get('is_super_admin') == True, f"Should be is_super_admin=true"
        print(f"✓ Super admin {email} returns is_partner=true, is_super_admin=true")
    
    def test_second_super_admin_is_partner(self):
        """Second super admin should return is_partner: true"""
        email = "contact.artboost@gmail.com"
        response = requests.get(f"{BASE_URL}/api/check-partner/{email}")
        assert response.status_code == 200
        data = response.json()
        
        assert data.get('is_partner') == True
        assert data.get('is_super_admin') == True
        print(f"✓ Super admin {email} returns is_partner=true, is_super_admin=true")
    
    def test_non_partner_returns_false(self):
        """Non-partner email should return is_partner: false"""
        email = "random_test_user_12345@nonexistent.com"
        response = requests.get(f"{BASE_URL}/api/check-partner/{email}")
        assert response.status_code == 200
        data = response.json()
        
        assert data.get('is_partner') == False
        print(f"✓ Non-partner returns is_partner=false")
    
    def test_email_case_insensitivity(self):
        """Email check should be case-insensitive"""
        emails = ["AFROBOOST.BASSI@GMAIL.COM", "Afroboost.Bassi@Gmail.Com"]
        for email in emails:
            response = requests.get(f"{BASE_URL}/api/check-partner/{email}")
            assert response.status_code == 200
            data = response.json()
            # Super admin should still be recognized regardless of case
            assert data.get('is_partner') == True, f"Case-insensitive check failed for {email}"
        print(f"✓ Email check is case-insensitive")


class TestHealthEndpoint:
    """Basic health check"""
    
    def test_health_endpoint(self):
        """Test health endpoint"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        print("✓ Health endpoint returns 200")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
