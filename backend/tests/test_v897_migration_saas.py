"""
Test v8.9.7 - Migration Bassi Data & SaaS Multi-Coach Features
Tests:
- /api/admin/migrate-bassi-data (Super Admin only)
- /api/coach/profile (returns credits=-1 and is_super_admin=true for Bassi)
- /api/reservations with X-User-Email header (7 reservations for Bassi)
- /api/coach/vitrine/bassi (coach name, courses, offers)
"""
import pytest
import requests
import os

# Get backend URL from environment
BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
if not BASE_URL:
    BASE_URL = "https://video-feed-platform.preview.emergentagent.com"

SUPER_ADMIN_EMAIL = "contact.artboost@gmail.com"

class TestMigrationEndpoint:
    """Tests for /api/admin/migrate-bassi-data endpoint"""
    
    def test_migration_requires_super_admin(self):
        """Migration endpoint requires Super Admin header"""
        # Without header - should fail
        response = requests.post(f"{BASE_URL}/api/admin/migrate-bassi-data")
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        print(f"✅ Migration endpoint correctly rejects requests without Super Admin header")
    
    def test_migration_success_for_super_admin(self):
        """Migration endpoint works for Super Admin"""
        response = requests.post(
            f"{BASE_URL}/api/admin/migrate-bassi-data",
            headers={"X-User-Email": SUPER_ADMIN_EMAIL}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert data.get("success") is True
        assert "migrated" in data
        assert "reservations" in data["migrated"]
        assert "contacts" in data["migrated"]
        assert "campaigns" in data["migrated"]
        print(f"✅ Migration success: {data['migrated']}")


class TestCoachProfile:
    """Tests for /api/coach/profile endpoint"""
    
    def test_coach_profile_requires_email(self):
        """Coach profile requires X-User-Email header"""
        response = requests.get(f"{BASE_URL}/api/coach/profile")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print(f"✅ Coach profile correctly requires email header")
    
    def test_super_admin_profile(self):
        """Super Admin (Bassi) gets special profile with unlimited credits"""
        response = requests.get(
            f"{BASE_URL}/api/coach/profile",
            headers={"X-User-Email": SUPER_ADMIN_EMAIL}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        # Verify Super Admin properties
        assert data.get("credits") == -1, f"Expected credits=-1, got {data.get('credits')}"
        assert data.get("is_super_admin") is True, f"Expected is_super_admin=true"
        assert data.get("role") == "super_admin", f"Expected role=super_admin, got {data.get('role')}"
        print(f"✅ Super Admin profile: credits=-1, is_super_admin=true, role=super_admin")
    
    def test_unknown_coach_returns_404(self):
        """Unknown coach email returns 404"""
        response = requests.get(
            f"{BASE_URL}/api/coach/profile",
            headers={"X-User-Email": "unknown_coach@test.com"}
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print(f"✅ Unknown coach correctly returns 404")


class TestReservationsIsolation:
    """Tests for /api/reservations with coach_id isolation"""
    
    def test_reservations_with_super_admin(self):
        """Super Admin sees all reservations (at least 7)"""
        response = requests.get(
            f"{BASE_URL}/api/reservations",
            headers={"X-User-Email": SUPER_ADMIN_EMAIL}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        # Should have pagination structure
        assert "data" in data
        assert "pagination" in data
        
        total = data["pagination"]["total"]
        print(f"Total reservations for Super Admin: {total}")
        
        # Should have at least 7 reservations
        assert total >= 7, f"Expected at least 7 reservations, got {total}"
        print(f"✅ Super Admin sees {total} reservations (>= 7)")
    
    def test_reservations_pagination(self):
        """Reservations endpoint supports pagination"""
        response = requests.get(
            f"{BASE_URL}/api/reservations?page=1&limit=5",
            headers={"X-User-Email": SUPER_ADMIN_EMAIL}
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "pagination" in data
        assert data["pagination"]["page"] == 1
        assert data["pagination"]["limit"] == 5
        print(f"✅ Pagination working: page={data['pagination']['page']}, limit={data['pagination']['limit']}")


class TestCoachVitrine:
    """Tests for /api/coach/vitrine/{username} endpoint"""
    
    def test_vitrine_bassi(self):
        """Vitrine for Bassi (Super Admin) returns coach info, courses and offers"""
        response = requests.get(f"{BASE_URL}/api/coach/vitrine/bassi")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        # Should have coach info
        assert "coach" in data
        coach = data["coach"]
        assert coach.get("name") == "Bassi - Afroboost", f"Expected 'Bassi - Afroboost', got {coach.get('name')}"
        
        # Should have courses
        assert "courses" in data
        courses_count = data.get("courses_count", 0)
        print(f"Courses count: {courses_count}")
        assert courses_count >= 2, f"Expected at least 2 courses, got {courses_count}"
        
        # Should have offers
        assert "offers" in data
        offers_count = data.get("offers_count", 0)
        print(f"Offers count: {offers_count}")
        assert offers_count >= 3, f"Expected at least 3 offers, got {offers_count}"
        
        print(f"✅ Vitrine Bassi: name='{coach.get('name')}', {courses_count} courses, {offers_count} offers")
    
    def test_vitrine_afroboost(self):
        """Vitrine for 'afroboost' username also returns Bassi"""
        response = requests.get(f"{BASE_URL}/api/coach/vitrine/afroboost")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        assert data["coach"]["name"] == "Bassi - Afroboost"
        print(f"✅ /coach/vitrine/afroboost returns Bassi coach")
    
    def test_vitrine_unknown_coach_404(self):
        """Unknown coach returns 404"""
        response = requests.get(f"{BASE_URL}/api/coach/vitrine/unknown_coach_xyz")
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print(f"✅ Unknown coach vitrine correctly returns 404")


class TestNonRegression:
    """Non-regression tests for existing APIs"""
    
    def test_health_endpoint(self):
        """Health endpoint working"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        print(f"✅ Health check passed")
    
    def test_courses_endpoint(self):
        """Courses endpoint working"""
        response = requests.get(f"{BASE_URL}/api/courses")
        assert response.status_code == 200
        courses = response.json()
        assert isinstance(courses, list)
        print(f"✅ Courses endpoint: {len(courses)} courses")
    
    def test_offers_endpoint(self):
        """Offers endpoint working"""
        response = requests.get(f"{BASE_URL}/api/offers")
        assert response.status_code == 200
        offers = response.json()
        assert isinstance(offers, list)
        print(f"✅ Offers endpoint: {len(offers)} offers")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
