"""
v8.9.4 Non-Regression Test Suite
Tests critico-non-régression pour le tunnel fitness, Stripe et les nouvelles fonctionnalités coach
"""
import pytest
import requests
import os
import uuid

# Use the external URL for testing
BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://video-feed-platform.preview.emergentagent.com').rstrip('/')


class TestNonRegressionAPIs:
    """Tests de non-régression critiques pour les APIs existantes"""
    
    def test_get_courses_intact(self):
        """NON-RÉGRESSION: GET /api/courses - Cours fitness doivent être intacts"""
        response = requests.get(f"{BASE_URL}/api/courses", timeout=10)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert isinstance(data, list), "Response should be a list of courses"
        print(f"✓ NON-REGRESSION: GET /api/courses - {len(data)} cours trouvés")
    
    def test_get_offers_intact(self):
        """NON-RÉGRESSION: GET /api/offers - Offres clients doivent être intactes"""
        response = requests.get(f"{BASE_URL}/api/offers", timeout=10)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert isinstance(data, list), "Response should be a list of offers"
        print(f"✓ NON-REGRESSION: GET /api/offers - {len(data)} offres trouvées")
    
    def test_get_discount_codes_intact(self):
        """NON-RÉGRESSION: GET /api/discount-codes - QR codes doivent être intacts"""
        response = requests.get(f"{BASE_URL}/api/discount-codes", timeout=10)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert isinstance(data, list), "Response should be a list of discount codes"
        print(f"✓ NON-REGRESSION: GET /api/discount-codes - {len(data)} codes promo trouvés")
    
    def test_get_payment_links_intact(self):
        """NON-RÉGRESSION: GET /api/payment-links - Liens paiement doivent être intacts"""
        response = requests.get(f"{BASE_URL}/api/payment-links", timeout=10)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        # Payment links can return empty dict or specific structure
        print(f"✓ NON-REGRESSION: GET /api/payment-links - Response OK")
    
    def test_get_concept_intact(self):
        """NON-RÉGRESSION: GET /api/concept - Concept doit être intact"""
        response = requests.get(f"{BASE_URL}/api/concept", timeout=10)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print(f"✓ NON-REGRESSION: GET /api/concept - Response OK")
    
    def test_get_users_intact(self):
        """NON-RÉGRESSION: GET /api/users - Utilisateurs doivent être intacts"""
        response = requests.get(f"{BASE_URL}/api/users", timeout=10)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert isinstance(data, list), "Response should be a list of users"
        print(f"✓ NON-REGRESSION: GET /api/users - {len(data)} utilisateurs trouvés")


class TestCoachPacksAPI:
    """Tests pour les endpoints admin/coach-packs"""
    
    def test_get_coach_packs(self):
        """GET /api/admin/coach-packs - Liste des packs coach"""
        response = requests.get(f"{BASE_URL}/api/admin/coach-packs", timeout=10)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert isinstance(data, list), "Response should be a list of coach packs"
        print(f"✓ GET /api/admin/coach-packs - {len(data)} packs trouvés")
        return data
    
    def test_update_coach_pack_requires_auth(self):
        """PUT /api/admin/coach-packs/{id} - Endpoint requires authentication (returns 403)"""
        test_pack_id = "0a6fbe70-8308-48f8-8f69-01e656f4a255"
        
        # First, get the current pack data (GET is public)
        response = requests.get(f"{BASE_URL}/api/admin/coach-packs", timeout=10)
        assert response.status_code == 200
        packs = response.json()
        
        # Verify pack exists
        test_pack = None
        for pack in packs:
            if pack.get('id') == test_pack_id:
                test_pack = pack
                break
        
        if not test_pack:
            pytest.skip(f"Test pack {test_pack_id} not found")
        
        # Try to update without auth - should return 403 Forbidden
        update_data = {
            "name": test_pack.get("name", "Test Pack"),
            "price": test_pack.get("price", 100),
            "sessions_included": test_pack.get("sessions_included", 10),
            "validity_days": test_pack.get("validity_days", 30),
            "is_active": test_pack.get("is_active", True)
        }
        
        response = requests.put(
            f"{BASE_URL}/api/admin/coach-packs/{test_pack_id}",
            json=update_data,
            timeout=10
        )
        # 403 Forbidden is expected - endpoint requires admin authentication
        # This is correct security behavior
        assert response.status_code == 403, f"Expected 403 (auth required), got {response.status_code}"
        print(f"✓ PUT /api/admin/coach-packs/{test_pack_id} - Correctly requires authentication (403)")
    
    def test_update_coach_pack_auth_protection(self):
        """PUT /api/admin/coach-packs/{id} - Verify auth protection for any ID"""
        random_id = str(uuid.uuid4())
        update_data = {
            "name": "Test",
            "price": 100,
            "sessions_included": 10,
            "validity_days": 30,
            "is_active": True
        }
        
        response = requests.put(
            f"{BASE_URL}/api/admin/coach-packs/{random_id}",
            json=update_data,
            timeout=10
        )
        # Should return 403 (auth required) before even checking if ID exists
        assert response.status_code == 403, f"Expected 403 (auth required), got {response.status_code}"
        print(f"✓ PUT endpoint correctly protected by authentication")


class TestFeatureFlags:
    """Test feature flags API"""
    
    def test_get_feature_flags(self):
        """GET /api/feature-flags - Feature flags doivent fonctionner"""
        response = requests.get(f"{BASE_URL}/api/feature-flags", timeout=10)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print(f"✓ GET /api/feature-flags - Response OK")


class TestHealthEndpoint:
    """Test health check"""
    
    def test_health_check(self):
        """GET / - API accessible"""
        response = requests.get(f"{BASE_URL}/", timeout=10)
        # Accept both 200 OK and redirects
        assert response.status_code in [200, 307, 308], f"Expected 200 or redirect, got {response.status_code}"
        print(f"✓ Health check - API accessible")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
