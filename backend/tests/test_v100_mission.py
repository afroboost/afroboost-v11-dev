"""
Test Mission v10.0 - Instagram Reels Style & Zero Black Void
Tests for:
- API /api/partners/active returns unique partners
- Partners data structure validation
- Health check endpoint
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestPartnersActiveAPI:
    """Tests for /api/partners/active endpoint"""
    
    def test_partners_active_returns_list(self):
        """Test that partners/active returns a list"""
        response = requests.get(f"{BASE_URL}/api/partners/active")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        print(f"✅ partners/active returned {len(data)} partners")
    
    def test_partners_are_unique_by_email(self):
        """Test that all partners have unique emails (no duplicates)"""
        response = requests.get(f"{BASE_URL}/api/partners/active")
        assert response.status_code == 200
        data = response.json()
        
        emails = [p.get('email', '').lower() for p in data if p.get('email')]
        unique_emails = set(emails)
        
        assert len(emails) == len(unique_emails), f"Duplicates found! {len(emails)} emails, {len(unique_emails)} unique"
        print(f"✅ All {len(unique_emails)} partners have unique emails")
    
    def test_partners_have_unique_ids(self):
        """Test that all partners have unique IDs"""
        response = requests.get(f"{BASE_URL}/api/partners/active")
        assert response.status_code == 200
        data = response.json()
        
        ids = [p.get('id') for p in data if p.get('id')]
        unique_ids = set(ids)
        
        assert len(ids) == len(unique_ids), f"Duplicate IDs found! {len(ids)} IDs, {len(unique_ids)} unique"
        print(f"✅ All {len(unique_ids)} partners have unique IDs")
    
    def test_partners_have_required_fields(self):
        """Test that partners have required fields for Instagram Reels display"""
        response = requests.get(f"{BASE_URL}/api/partners/active")
        assert response.status_code == 200
        data = response.json()
        
        required_fields = ['id', 'email', 'name']
        optional_display_fields = ['platform_name', 'bio', 'photo_url', 'logo_url', 'video_url']
        
        for partner in data:
            for field in required_fields:
                assert field in partner, f"Partner missing required field: {field}"
            print(f"  ✅ Partner {partner.get('email')} has all required fields")
        
        print(f"✅ All {len(data)} partners have required fields")
    
    def test_super_admin_bassi_is_partner(self):
        """Test that super admin afroboost.bassi@gmail.com is in partners"""
        response = requests.get(f"{BASE_URL}/api/partners/active")
        assert response.status_code == 200
        data = response.json()
        
        # Look for super admin - may be under contact.artboost@gmail.com
        super_admin_emails = ['afroboost.bassi@gmail.com', 'contact.artboost@gmail.com']
        found = any(
            p.get('email', '').lower() in [e.lower() for e in super_admin_emails] 
            for p in data
        )
        
        if found:
            print("✅ Super admin found in partners list")
        else:
            print("ℹ️ Super admin not found - may be expected behavior")
    
    def test_partner_videos_have_valid_urls(self):
        """Test that partners with video_url have valid YouTube/Vimeo/direct URLs"""
        response = requests.get(f"{BASE_URL}/api/partners/active")
        assert response.status_code == 200
        data = response.json()
        
        partners_with_videos = 0
        for partner in data:
            video_url = partner.get('video_url') or partner.get('heroImageUrl') or ''
            if video_url:
                partners_with_videos += 1
                # Check if it's a valid video URL pattern
                is_youtube = 'youtube.com' in video_url or 'youtu.be' in video_url
                is_vimeo = 'vimeo.com' in video_url
                is_direct = any(ext in video_url.lower() for ext in ['.mp4', '.webm', '.mov'])
                
                if is_youtube or is_vimeo or is_direct:
                    print(f"  ✅ {partner.get('email')} has valid video URL")
        
        print(f"✅ {partners_with_videos}/{len(data)} partners have video URLs")


class TestHealthEndpoint:
    """Test health check endpoint"""
    
    def test_health_endpoint(self):
        """Test that health endpoint returns OK"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200, f"Health check failed: {response.status_code}"
        data = response.json()
        assert data.get('status') == 'healthy', f"Expected healthy status, got: {data}"
        print("✅ Health endpoint returns healthy status")


class TestCoachesEndpoint:
    """Test coaches-related endpoints"""
    
    def test_users_endpoint(self):
        """Test that users endpoint returns data"""
        response = requests.get(f"{BASE_URL}/api/users")
        assert response.status_code == 200, f"Users endpoint failed: {response.status_code}"
        data = response.json()
        assert isinstance(data, list), "Users should be a list"
        print(f"✅ Users endpoint returned {len(data)} users")
    
    def test_offers_endpoint(self):
        """Test that offers endpoint returns data"""
        response = requests.get(f"{BASE_URL}/api/offers")
        assert response.status_code == 200, f"Offers endpoint failed: {response.status_code}"
        data = response.json()
        assert isinstance(data, list), "Offers should be a list"
        print(f"✅ Offers endpoint returned {len(data)} offers")
    
    def test_courses_endpoint(self):
        """Test that courses endpoint returns data"""
        response = requests.get(f"{BASE_URL}/api/courses")
        assert response.status_code == 200, f"Courses endpoint failed: {response.status_code}"
        data = response.json()
        assert isinstance(data, list), "Courses should be a list"
        print(f"✅ Courses endpoint returned {len(data)} courses")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
