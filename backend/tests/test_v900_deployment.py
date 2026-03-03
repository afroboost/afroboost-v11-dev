"""
Test Suite v9.0.0 - Déploiement final tunnel vitrine
Features to test:
1. Route /coach/:username accessible directly (no redirect)
2. Dynamic Coach button in ChatWidget 
3. Stripe success_url redirect to /#coach-dashboard
4. Non-regression: Super Admin sees 7 reservations for March
"""
import pytest
import requests
import os

# Get BASE_URL from environment
BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://promo-credits-lab.preview.emergentagent.com').rstrip('/')

# Test credentials
SUPER_ADMIN_EMAIL = "contact.artboost@gmail.com"


class TestNonRegression:
    """Non-regression tests - Critical for v9.0.0"""
    
    def test_reservations_count_super_admin(self):
        """
        NON-REGRESSION CRITIQUE: Super Admin doit voir ses 7 réservations
        """
        response = requests.get(
            f"{BASE_URL}/api/reservations",
            headers={"X-User-Email": SUPER_ADMIN_EMAIL}
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        total = data.get('pagination', {}).get('total', len(data.get('data', [])))
        
        # Super Admin should see at least 7 reservations
        assert total >= 7, f"Expected at least 7 reservations, got {total}"
        print(f"✅ Super Admin sees {total} reservations (expected >= 7)")
    
    def test_courses_count(self):
        """
        NON-REGRESSION: Should have 2 courses (Session Cardio, Sunday Vibes)
        """
        response = requests.get(f"{BASE_URL}/api/courses")
        
        assert response.status_code == 200
        
        courses = response.json()
        assert len(courses) >= 2, f"Expected at least 2 courses, got {len(courses)}"
        
        # Check course names
        course_names = [c.get('name', '') for c in courses]
        assert any('Session Cardio' in name for name in course_names), "Session Cardio course not found"
        assert any('Sunday Vibes' in name for name in course_names), "Sunday Vibes course not found"
        
        print(f"✅ Found {len(courses)} courses including Session Cardio and Sunday Vibes")
    
    def test_offers_count(self):
        """
        NON-REGRESSION: Should have 3 offers (30/150/109 CHF)
        """
        response = requests.get(f"{BASE_URL}/api/offers")
        
        assert response.status_code == 200
        
        offers = response.json()
        assert len(offers) >= 3, f"Expected at least 3 offers, got {len(offers)}"
        
        # Check prices
        prices = [o.get('price', 0) for o in offers]
        assert 30 in prices, "30 CHF offer not found"
        assert 150 in prices, "150 CHF offer not found"
        assert 109 in prices, "109 CHF offer not found"
        
        print(f"✅ Found {len(offers)} offers with prices: {prices}")


class TestCoachVitrine:
    """Tests for Coach Vitrine /coach/:username"""
    
    def test_vitrine_bassi_returns_coach(self):
        """
        Vitrine API should return coach 'Bassi - Afroboost'
        """
        response = requests.get(f"{BASE_URL}/api/coach/vitrine/bassi")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        coach = data.get('coach', {})
        
        assert coach.get('name') == 'Bassi - Afroboost', f"Expected 'Bassi - Afroboost', got {coach.get('name')}"
        print(f"✅ Vitrine returns coach: {coach.get('name')}")
    
    def test_vitrine_bassi_returns_courses(self):
        """
        Vitrine API should return 2 courses
        """
        response = requests.get(f"{BASE_URL}/api/coach/vitrine/bassi")
        
        assert response.status_code == 200
        
        data = response.json()
        courses = data.get('courses', [])
        
        assert len(courses) == 2, f"Expected 2 courses, got {len(courses)}"
        print(f"✅ Vitrine returns {len(courses)} courses")
    
    def test_vitrine_bassi_returns_offers(self):
        """
        Vitrine API should return 3 offers
        """
        response = requests.get(f"{BASE_URL}/api/coach/vitrine/bassi")
        
        assert response.status_code == 200
        
        data = response.json()
        offers = data.get('offers', [])
        
        assert len(offers) == 3, f"Expected 3 offers, got {len(offers)}"
        print(f"✅ Vitrine returns {len(offers)} offers")
    
    def test_vitrine_nonexistent_coach_404(self):
        """
        Vitrine API should return 404 for non-existent coach
        """
        response = requests.get(f"{BASE_URL}/api/coach/vitrine/nonexistent_coach_xyz")
        
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("✅ Non-existent coach returns 404")


class TestStripeConfiguration:
    """Tests for Stripe success_url configuration"""
    
    def test_coach_packs_exist(self):
        """
        Coach packs should be available for purchase
        """
        response = requests.get(f"{BASE_URL}/api/admin/coach-packs")
        
        assert response.status_code == 200
        
        packs = response.json()
        assert len(packs) >= 1, "No coach packs found"
        print(f"✅ Found {len(packs)} coach packs")
    
    @pytest.mark.skip(reason="Stripe checkout requires live API call - verified in code review")
    def test_stripe_success_url_contains_coach_dashboard(self):
        """
        Stripe success_url should redirect to afroboost-campagn-v8.vercel.app/#coach-dashboard
        This is verified via code review in server.py line 2532-2542
        """
        # Code contains:
        # COACH_DASHBOARD_URL = "https://afroboost-campagn-v8.vercel.app/#coach-dashboard"
        # success_url=f"{COACH_DASHBOARD_URL}?session_id={{CHECKOUT_SESSION_ID}}&welcome=true"
        pass


class TestAPIHealth:
    """Basic API health checks"""
    
    def test_api_health(self):
        """API health endpoint should return 200"""
        response = requests.get(f"{BASE_URL}/api/health")
        
        assert response.status_code == 200
        
        data = response.json()
        assert data.get('status') == 'healthy'
        print("✅ API is healthy")
    
    def test_coach_profile_endpoint(self):
        """Coach profile endpoint should work"""
        response = requests.get(
            f"{BASE_URL}/api/coach/profile",
            headers={"X-User-Email": SUPER_ADMIN_EMAIL}
        )
        
        # Should return coach profile or 404 if not a coach
        assert response.status_code in [200, 404]
        print(f"✅ Coach profile endpoint responded with {response.status_code}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
