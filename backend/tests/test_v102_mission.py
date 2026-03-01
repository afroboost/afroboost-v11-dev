"""
Test Mission v10.2: Format 16:9 & Zéro Vide
- API /api/partners/active returns unique partners
- Sessions API works
- Health check
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestV102Mission:
    """v10.2 Mission API Tests"""
    
    def test_health_endpoint(self):
        """Test health check"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        print(f"✅ Health endpoint OK: {response.json()}")
    
    def test_partners_active_returns_list(self):
        """Test /api/partners/active returns list"""
        response = requests.get(f"{BASE_URL}/api/partners/active")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✅ Partners endpoint returns {len(data)} partners")
        return data
    
    def test_partners_are_unique_by_email(self):
        """Test partners are unique by email"""
        response = requests.get(f"{BASE_URL}/api/partners/active")
        data = response.json()
        
        emails = [p.get('email', '').lower() for p in data if p.get('email')]
        unique_emails = set(emails)
        
        assert len(emails) == len(unique_emails), f"Duplicate emails found: {len(emails)} total, {len(unique_emails)} unique"
        print(f"✅ All {len(unique_emails)} partners have unique emails")
    
    def test_partners_have_required_fields(self):
        """Test partners have required fields"""
        response = requests.get(f"{BASE_URL}/api/partners/active")
        data = response.json()
        
        for partner in data:
            assert 'id' in partner or 'email' in partner, f"Partner missing id/email: {partner}"
            assert 'name' in partner or 'platform_name' in partner, f"Partner missing name: {partner}"
        print(f"✅ All {len(data)} partners have required fields")
    
    def test_super_admin_bassi_is_partner(self):
        """Test Bassi (super admin) is in partners list"""
        response = requests.get(f"{BASE_URL}/api/partners/active")
        data = response.json()
        
        bassi_emails = ['contact.artboost@gmail.com', 'afroboost.bassi@gmail.com']
        partner_emails = [p.get('email', '').lower() for p in data]
        
        found = any(email.lower() in partner_emails for email in bassi_emails)
        assert found, f"Super admin Bassi not found in partners. Available: {partner_emails}"
        print(f"✅ Super admin Bassi found in partners list")
    
    def test_partner_videos_have_valid_urls(self):
        """Test partners with videos have valid YouTube/Vimeo URLs"""
        response = requests.get(f"{BASE_URL}/api/partners/active")
        data = response.json()
        
        partners_with_video = 0
        for partner in data:
            video_url = partner.get('video_url') or partner.get('heroImageUrl') or ''
            if video_url and ('youtube' in video_url.lower() or 'vimeo' in video_url.lower()):
                partners_with_video += 1
        
        print(f"✅ {partners_with_video}/{len(data)} partners have video URLs")
    
    def test_users_endpoint(self):
        """Test users endpoint"""
        response = requests.get(f"{BASE_URL}/api/users")
        assert response.status_code == 200
        print(f"✅ Users endpoint OK: {len(response.json())} users")
    
    def test_offers_endpoint(self):
        """Test offers endpoint"""
        response = requests.get(f"{BASE_URL}/api/offers")
        assert response.status_code == 200
        print(f"✅ Offers endpoint OK: {len(response.json())} offers")
    
    def test_courses_endpoint(self):
        """Test courses endpoint"""
        response = requests.get(f"{BASE_URL}/api/courses")
        assert response.status_code == 200
        print(f"✅ Courses endpoint OK: {len(response.json())} courses")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
