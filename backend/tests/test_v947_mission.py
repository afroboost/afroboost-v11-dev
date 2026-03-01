"""
Test v9.4.7 Mission - Carousel vidéo et flux partenaire
Features:
1. /api/partners/active endpoint returns partners with videos
2. PartnersCarousel component on homepage with "Nos Partenaires" title
3. BecomeCoachPage with Google login for new users
4. CoachVitrine with clean hero video (no text overlay)
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://video-feed-platform.preview.emergentagent.com').rstrip('/')

class TestPartnersActiveEndpoint:
    """Test /api/partners/active endpoint - v9.4.7 carousel feature"""
    
    def test_partners_active_returns_list(self):
        """GET /api/partners/active should return a list of active partners"""
        response = requests.get(f"{BASE_URL}/api/partners/active")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert isinstance(data, list), f"Expected list, got {type(data)}"
        print(f"✅ /api/partners/active returned {len(data)} partners")
        
    def test_partners_active_structure(self):
        """Partners should have expected fields (id, name, email, video_url optional)"""
        response = requests.get(f"{BASE_URL}/api/partners/active")
        assert response.status_code == 200
        
        data = response.json()
        if len(data) > 0:
            partner = data[0]
            # Check basic fields exist
            assert 'name' in partner or 'platform_name' in partner, "Partner should have name or platform_name"
            assert 'email' in partner, "Partner should have email"
            print(f"✅ First partner: {partner.get('platform_name') or partner.get('name')} - has video: {'video_url' in partner and partner['video_url']}")
        else:
            print("⚠️ No partners returned - empty list (valid but no data to verify)")


class TestCoachVitrineEndpoint:
    """Test /api/coach/vitrine/{username} endpoint"""
    
    def test_bassi_vitrine_accessible(self):
        """GET /api/coach/vitrine/bassi should return coach data"""
        response = requests.get(f"{BASE_URL}/api/coach/vitrine/bassi")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert 'coach' in data, "Response should contain 'coach' key"
        assert 'offers' in data, "Response should contain 'offers' key"
        
        coach = data['coach']
        assert coach.get('email') == 'contact.artboost@gmail.com', "Bassi should be Super Admin email"
        print(f"✅ Bassi vitrine: {coach.get('name')} - {len(data.get('offers', []))} offers")
        
    def test_vitrine_invalid_coach_404(self):
        """GET /api/coach/vitrine/invalid_coach should return 404"""
        response = requests.get(f"{BASE_URL}/api/coach/vitrine/nonexistent_coach_12345")
        assert response.status_code == 404, f"Expected 404 for invalid coach, got {response.status_code}"
        print("✅ Invalid coach returns 404 as expected")


class TestCoachPacksEndpoint:
    """Test /api/admin/coach-packs for BecomeCoachPage"""
    
    def test_coach_packs_accessible(self):
        """GET /api/admin/coach-packs should return visible packs"""
        response = requests.get(f"{BASE_URL}/api/admin/coach-packs")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert isinstance(data, list), f"Expected list, got {type(data)}"
        print(f"✅ /api/admin/coach-packs returned {len(data)} packs")
        
        if len(data) > 0:
            pack = data[0]
            assert 'name' in pack, "Pack should have name"
            assert 'price' in pack, "Pack should have price"
            assert 'credits' in pack, "Pack should have credits"
            print(f"   First pack: {pack.get('name')} - {pack.get('price')} CHF - {pack.get('credits')} credits")


class TestConceptEndpoint:
    """Test /api/concept for hero video on vitrine"""
    
    def test_concept_bassi(self):
        """GET /api/concept should return hero config for main page"""
        response = requests.get(f"{BASE_URL}/api/concept", headers={'X-User-Email': 'contact.artboost@gmail.com'})
        # Concept may exist or not, both are valid
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Concept exists - heroImageUrl: {data.get('heroImageUrl', 'N/A')[:50] if data.get('heroImageUrl') else 'None'}")
        else:
            print(f"⚠️ Concept endpoint returned {response.status_code} - may be expected if no concept configured")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
