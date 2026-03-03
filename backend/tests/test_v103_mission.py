"""
Test Suite for Mission v10.3: Glow Violet, Mémoire Chat & Récap Réservation
- /api/partners/active endpoint
- /api/health endpoint
- localStorage keys verification (frontend concern)
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://promo-credits-lab.preview.emergentagent.com')

class TestMissionV103Backend:
    """Tests backend pour Mission v10.3"""
    
    def test_health_endpoint(self):
        """Health check endpoint returns healthy status"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "healthy"
        assert data.get("database") == "connected"
        print("✅ Health endpoint: OK")
    
    def test_partners_active_endpoint(self):
        """GET /api/partners/active returns list of active partners"""
        response = requests.get(f"{BASE_URL}/api/partners/active")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0
        print(f"✅ Partners active: {len(data)} partners returned")
    
    def test_partners_have_required_fields(self):
        """Partners have required fields for carousel display"""
        response = requests.get(f"{BASE_URL}/api/partners/active")
        assert response.status_code == 200
        data = response.json()
        
        for partner in data:
            # Each partner should have id and email for unique identification
            assert 'id' in partner or 'email' in partner, f"Partner missing id/email: {partner}"
            # Name for display
            assert 'name' in partner or 'platform_name' in partner, f"Partner missing name: {partner}"
        print("✅ Partners have required fields")
    
    def test_partners_unique_by_email(self):
        """Partners are unique by email (no duplicates)"""
        response = requests.get(f"{BASE_URL}/api/partners/active")
        assert response.status_code == 200
        data = response.json()
        
        emails = [p.get('email', '').lower() for p in data if p.get('email')]
        unique_emails = set(emails)
        
        assert len(emails) == len(unique_emails), f"Duplicate emails found: {len(emails)} total, {len(unique_emails)} unique"
        print(f"✅ Partners unique: {len(unique_emails)} unique emails")
    
    def test_super_admin_bassi_is_partner(self):
        """Super Admin Bassi (contact.artboost@gmail.com) is in partners list"""
        response = requests.get(f"{BASE_URL}/api/partners/active")
        assert response.status_code == 200
        data = response.json()
        
        emails = [p.get('email', '').lower() for p in data]
        # Should have at least one of the super admin emails
        super_admin_found = any(
            email in emails 
            for email in ['contact.artboost@gmail.com', 'afroboost.bassi@gmail.com']
        )
        assert super_admin_found, f"Super admin not found in partners. Emails: {emails}"
        print("✅ Super Admin Bassi found in partners")


class TestMissionV103ReservationAPI:
    """Tests for reservation-related endpoints"""
    
    def test_courses_endpoint(self):
        """GET /api/courses returns available courses"""
        response = requests.get(f"{BASE_URL}/api/courses")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✅ Courses endpoint: {len(data)} courses available")
    
    def test_offers_endpoint(self):
        """GET /api/offers returns available offers"""
        response = requests.get(f"{BASE_URL}/api/offers")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✅ Offers endpoint: {len(data)} offers available")


class TestMissionV103DiscountCodes:
    """Tests for discount code validation (used for reservations)"""
    
    def test_validate_code_endpoint_exists(self):
        """POST /api/discount-codes/validate endpoint exists"""
        # Test with invalid code - should return 200 with valid=false or 400
        response = requests.post(
            f"{BASE_URL}/api/discount-codes/validate",
            json={"code": "INVALID_TEST_CODE", "email": "test@test.com"}
        )
        # Endpoint should exist (not 404)
        assert response.status_code != 404, "Discount code validation endpoint not found"
        print(f"✅ Discount code validation endpoint exists (status: {response.status_code})")
    
    def test_check_reservation_eligibility_endpoint(self):
        """POST /api/check-reservation-eligibility endpoint exists"""
        response = requests.post(
            f"{BASE_URL}/api/check-reservation-eligibility",
            json={"code": "TEST", "email": "test@test.com"}
        )
        # Endpoint should exist (not 404)
        assert response.status_code != 404, "Check reservation eligibility endpoint not found"
        print(f"✅ Reservation eligibility endpoint exists (status: {response.status_code})")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
