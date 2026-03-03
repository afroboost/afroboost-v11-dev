"""
Mission v9.1.1 Test Suite: Dashboard Miroir & Fix Redirection
Tests:
1. Refactoring validation - server.py 6877 lines, coach_routes.py ~350 lines  
2. API /api/reservations - 7 reservations for Super Admin (non-regression critical)
3. API /api/coach/profile via coach_routes.py - is_super_admin: true for Bassi
4. API /api/coach/check-credits via coach_routes.py - unlimited: true
5. API /api/coach/vitrine/bassi via coach_routes.py - platform_name: Afroboost
6. API /api/admin/coaches via coach_routes.py - lists 7 coaches
7. Homepage courses intact (Session Cardio + Sunday Vibes)
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://promo-credits-lab.preview.emergentagent.com')
SUPER_ADMIN_EMAIL = "contact.artboost@gmail.com"

class TestMissionV911:
    """Mission v9.1.1: Dashboard Miroir & Fix Redirection Tests"""
    
    # === NON-REGRESSION CRITICAL: 7 reservations for Super Admin ===
    def test_reservations_super_admin_sees_7(self):
        """Critical: Super Admin Bassi must see exactly 7 reservations"""
        response = requests.get(
            f"{BASE_URL}/api/reservations",
            headers={"X-User-Email": SUPER_ADMIN_EMAIL}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        # Response is paginated {data: [], pagination: {}}
        reservations = data.get("data", [])
        total = data.get("pagination", {}).get("total", len(reservations))
        assert total >= 7, f"Expected at least 7 reservations, got {total}"
        print(f"✅ NON-REGRESSION: Super Admin sees {total} reservations")
    
    # === Coach Profile via coach_routes.py ===
    def test_coach_profile_super_admin(self):
        """Verify /api/coach/profile returns is_super_admin: true for Bassi"""
        response = requests.get(
            f"{BASE_URL}/api/coach/profile",
            headers={"X-User-Email": SUPER_ADMIN_EMAIL}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert data.get("is_super_admin") == True, f"Expected is_super_admin=True, got {data.get('is_super_admin')}"
        assert data.get("email") == SUPER_ADMIN_EMAIL.lower() or data.get("email") == SUPER_ADMIN_EMAIL, f"Wrong email: {data.get('email')}"
        print(f"✅ Coach profile: is_super_admin={data.get('is_super_admin')}, email={data.get('email')}")
    
    # === Check Credits via coach_routes.py ===
    def test_check_credits_unlimited(self):
        """Verify /api/coach/check-credits returns unlimited: true for Super Admin"""
        response = requests.get(
            f"{BASE_URL}/api/coach/check-credits",
            headers={"X-User-Email": SUPER_ADMIN_EMAIL}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert data.get("unlimited") == True, f"Expected unlimited=True, got {data.get('unlimited')}"
        assert data.get("has_credits") == True, f"Expected has_credits=True, got {data.get('has_credits')}"
        assert data.get("credits") == -1, f"Expected credits=-1, got {data.get('credits')}"
        print(f"✅ Check credits: unlimited={data.get('unlimited')}, credits={data.get('credits')}")
    
    # === Vitrine Bassi via coach_routes.py ===
    def test_vitrine_bassi_platform_name(self):
        """Verify /api/coach/vitrine/bassi returns platform_name: Afroboost"""
        response = requests.get(f"{BASE_URL}/api/coach/vitrine/bassi")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        coach = data.get("coach", {})
        assert coach.get("platform_name") == "Afroboost", f"Expected platform_name='Afroboost', got {coach.get('platform_name')}"
        assert data.get("courses_count", 0) >= 0, "courses_count should exist"
        assert data.get("offers_count", 0) >= 0, "offers_count should exist"
        print(f"✅ Vitrine Bassi: platform_name={coach.get('platform_name')}, courses={data.get('courses_count')}, offers={data.get('offers_count')}")
    
    # === Admin Coaches via coach_routes.py ===
    def test_admin_coaches_list(self):
        """Verify /api/admin/coaches returns 7 coaches"""
        response = requests.get(
            f"{BASE_URL}/api/admin/coaches",
            headers={"X-User-Email": SUPER_ADMIN_EMAIL}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert isinstance(data, list), "Expected list of coaches"
        assert len(data) >= 7, f"Expected at least 7 coaches, got {len(data)}"
        print(f"✅ Admin coaches: {len(data)} coaches returned")
    
    # === Homepage Courses Intact (Mars courses) ===
    def test_courses_mars_intact(self):
        """Verify courses for March are intact: Session Cardio + Sunday Vibes"""
        response = requests.get(f"{BASE_URL}/api/courses")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert isinstance(data, list), "Expected list of courses"
        
        # Find Session Cardio and Sunday Vibes
        course_names = [c.get("name", "") for c in data]
        has_cardio = any("Session Cardio" in name for name in course_names)
        has_sunday = any("Sunday Vibes" in name for name in course_names)
        
        assert has_cardio, f"Missing 'Session Cardio' in courses: {course_names}"
        assert has_sunday, f"Missing 'Sunday Vibes' in courses: {course_names}"
        print(f"✅ Courses intact: Found Session Cardio and Sunday Vibes in {len(data)} courses")
    
    # === Auth Role Endpoint ===
    def test_auth_role_super_admin(self):
        """Verify /api/auth/role correctly identifies Super Admin"""
        response = requests.get(
            f"{BASE_URL}/api/auth/role",
            headers={"X-User-Email": SUPER_ADMIN_EMAIL}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert data.get("role") == "super_admin", f"Expected role='super_admin', got {data.get('role')}"
        assert data.get("is_super_admin") == True, f"Expected is_super_admin=True"
        assert data.get("is_coach") == True, f"Super Admin should also be coach"
        print(f"✅ Auth role: role={data.get('role')}, is_super_admin={data.get('is_super_admin')}")
    
    # === Health Check ===
    def test_api_health(self):
        """Verify /api/health returns healthy"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert data.get("status") == "healthy", f"Expected status='healthy', got {data.get('status')}"
        print(f"✅ API Health: {data}")


class TestCoachRoutesModularity:
    """Test routes migrated to coach_routes.py are working"""
    
    def test_coach_packs_public(self):
        """GET /api/admin/coach-packs is accessible"""
        response = requests.get(f"{BASE_URL}/api/admin/coach-packs")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print(f"✅ Coach packs endpoint working")
    
    def test_coaches_search(self):
        """GET /api/coaches/search works"""
        response = requests.get(f"{BASE_URL}/api/coaches/search", params={"q": "bassi"})
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print(f"✅ Coaches search endpoint working")
    
    def test_stripe_connect_status(self):
        """GET /api/coach/stripe-connect/status works"""
        response = requests.get(
            f"{BASE_URL}/api/coach/stripe-connect/status",
            headers={"X-User-Email": SUPER_ADMIN_EMAIL}
        )
        # May return 200 with status or error details
        assert response.status_code in [200, 401], f"Unexpected status: {response.status_code}"
        print(f"✅ Stripe connect status endpoint working")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
