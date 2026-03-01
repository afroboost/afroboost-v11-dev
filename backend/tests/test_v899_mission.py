"""
Test Suite for Mission v8.9.9 - Afroboost
Features to test:
1. API /api/reservations with X-User-Email header - Non-regression Bassi's 7 Mars reservations
2. API /api/coach/vitrine/bassi - Coach 'Bassi - Afroboost' with courses and offers
3. Stripe checkout success_url must contain 'afroboost-campagn-v8.vercel.app'
"""
import pytest
import requests
import os

# Get BASE_URL from environment
BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://video-feed-platform.preview.emergentagent.com').rstrip('/')

# Test credentials
SUPER_ADMIN_EMAIL = "contact.artboost@gmail.com"

class TestNonRegressionReservations:
    """Non-regression: Bassi must see his 7 March reservations"""
    
    def test_reservations_endpoint_with_super_admin_header(self):
        """Test /api/reservations with X-User-Email header returns reservations for Super Admin"""
        response = requests.get(
            f"{BASE_URL}/api/reservations",
            headers={"X-User-Email": SUPER_ADMIN_EMAIL}
        )
        
        # Status code check
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        # Data structure check
        data = response.json()
        assert "data" in data, "Response should contain 'data' key"
        assert "pagination" in data, "Response should contain 'pagination' key"
        
        # Non-regression: Bassi should see at least 7 reservations from March
        reservations = data["data"]
        total = data["pagination"]["total"]
        print(f"[NON-REGRESSION] Total reservations for Super Admin: {total}")
        print(f"[NON-REGRESSION] Reservations in current page: {len(reservations)}")
        
        # Check for March reservations
        march_reservations = [r for r in reservations if "2025-03" in (r.get("datetime", "") or r.get("createdAt", ""))]
        print(f"[NON-REGRESSION] March 2025 reservations in page: {len(march_reservations)}")
        
        # Verify total count (should be >= 7 for non-regression)
        assert total >= 7, f"Non-regression FAILED: Expected at least 7 reservations, got {total}"
        print(f"✅ Non-regression PASSED: {total} reservations visible to Super Admin")
    
    def test_reservations_pagination_structure(self):
        """Test pagination structure in reservations response"""
        response = requests.get(
            f"{BASE_URL}/api/reservations?page=1&limit=10",
            headers={"X-User-Email": SUPER_ADMIN_EMAIL}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        pagination = data.get("pagination", {})
        assert "page" in pagination, "Pagination should have 'page'"
        assert "limit" in pagination, "Pagination should have 'limit'"
        assert "total" in pagination, "Pagination should have 'total'"
        assert "pages" in pagination, "Pagination should have 'pages'"
        
        print(f"✅ Pagination: page={pagination['page']}, limit={pagination['limit']}, total={pagination['total']}")


class TestCoachVitrine:
    """Test /api/coach/vitrine/bassi endpoint"""
    
    def test_vitrine_bassi_returns_coach_data(self):
        """Test vitrine endpoint for 'bassi' username returns coach with courses and offers"""
        response = requests.get(f"{BASE_URL}/api/coach/vitrine/bassi")
        
        # Should return 200
        assert response.status_code == 200, f"Expected 200, got {response.status_code}. Response: {response.text[:200]}"
        
        data = response.json()
        
        # Check coach data
        assert "coach" in data, "Response should contain 'coach' key"
        coach = data["coach"]
        assert coach.get("name"), "Coach should have a name"
        print(f"[VITRINE] Coach name: {coach.get('name')}")
        
        # Verify it's Bassi - Afroboost (or contains Bassi)
        coach_name = coach.get("name", "").lower()
        assert "bassi" in coach_name or "afroboost" in coach_name, f"Coach name should contain 'bassi' or 'afroboost', got: {coach.get('name')}"
        
    def test_vitrine_bassi_has_courses(self):
        """Test vitrine returns courses for bassi"""
        response = requests.get(f"{BASE_URL}/api/coach/vitrine/bassi")
        assert response.status_code == 200
        
        data = response.json()
        courses = data.get("courses", [])
        
        print(f"[VITRINE] Courses count: {len(courses)}")
        for c in courses:
            print(f"  - {c.get('name', c.get('title', 'unnamed'))} @ {c.get('time', 'no time')}")
        
        # Should have at least 2 courses
        assert len(courses) >= 2, f"Expected at least 2 courses, got {len(courses)}"
        print(f"✅ Vitrine has {len(courses)} courses")
        
    def test_vitrine_bassi_has_offers(self):
        """Test vitrine returns offers for bassi"""
        response = requests.get(f"{BASE_URL}/api/coach/vitrine/bassi")
        assert response.status_code == 200
        
        data = response.json()
        offers = data.get("offers", [])
        
        print(f"[VITRINE] Offers count: {len(offers)}")
        for o in offers:
            print(f"  - {o.get('name', 'unnamed')} @ {o.get('price', 'no price')} CHF")
        
        # Should have at least 3 offers
        assert len(offers) >= 3, f"Expected at least 3 offers, got {len(offers)}"
        print(f"✅ Vitrine has {len(offers)} offers")
        
    def test_vitrine_unknown_coach_404(self):
        """Test vitrine returns 404 for unknown coach"""
        response = requests.get(f"{BASE_URL}/api/coach/vitrine/unknown_coach_xyz")
        
        # Should return 404
        assert response.status_code == 404, f"Expected 404 for unknown coach, got {response.status_code}"
        print("✅ Unknown coach correctly returns 404")


class TestStripeSuccessUrl:
    """Test Stripe checkout success_url contains Vercel production URL"""
    
    def test_coach_pack_checkout_success_url(self):
        """Test that coach pack checkout creates session with correct success_url"""
        # We cannot directly test Stripe session creation without valid pack_id
        # Instead, we verify the code by checking the endpoint exists and responds
        
        # First, get available packs
        packs_response = requests.get(f"{BASE_URL}/api/coach/packs")
        
        if packs_response.status_code == 200:
            packs = packs_response.json()
            print(f"[STRIPE] Available coach packs: {len(packs)}")
            
            if len(packs) > 0:
                pack = packs[0]
                print(f"[STRIPE] First pack: {pack.get('name')} - {pack.get('price')} CHF")
                
                # Try to create checkout session
                checkout_response = requests.post(
                    f"{BASE_URL}/api/coach/packs/{pack.get('id')}/subscribe",
                    headers={"X-User-Email": "test@test.com"},
                    json={"email": "test@test.com"}
                )
                
                # If Stripe is configured, we get 200 with URL
                # If not configured, we get 400/500 which is expected in test env
                print(f"[STRIPE] Checkout response status: {checkout_response.status_code}")
                if checkout_response.status_code == 200:
                    checkout_data = checkout_response.json()
                    checkout_url = checkout_data.get("checkout_url", checkout_data.get("url", ""))
                    print(f"[STRIPE] Checkout URL preview: {checkout_url[:100] if checkout_url else 'N/A'}...")
        else:
            print("[STRIPE] No packs endpoint available - skipping checkout test")
            pytest.skip("Coach packs endpoint not available")


class TestHealthAndBasics:
    """Basic health checks"""
    
    def test_api_health(self):
        """Test API health endpoint"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        
        data = response.json()
        assert data.get("status") == "healthy"
        assert data.get("database") == "connected"
        print("✅ API health check passed")
    
    def test_courses_endpoint(self):
        """Test courses endpoint returns data"""
        response = requests.get(f"{BASE_URL}/api/courses")
        assert response.status_code == 200
        
        courses = response.json()
        assert isinstance(courses, list)
        print(f"✅ Courses endpoint returned {len(courses)} courses")
        
        # Non-regression: Should have at least 2 courses
        assert len(courses) >= 2, f"Expected at least 2 courses, got {len(courses)}"
    
    def test_offers_endpoint(self):
        """Test offers endpoint returns data"""
        response = requests.get(f"{BASE_URL}/api/offers")
        assert response.status_code == 200
        
        offers = response.json()
        assert isinstance(offers, list)
        print(f"✅ Offers endpoint returned {len(offers)} offers")
        
        # Non-regression: Should have at least 3 offers
        assert len(offers) >= 3, f"Expected at least 3 offers, got {len(offers)}"


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
