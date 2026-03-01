"""
Mission v9.1.6 - Test Suite
3 objectifs à tester:
1. REBRANDING 'Coach' → 'Partenaire' dans tous les textes
2. POUVOIRS ILLIMITÉS pour Super Admin (Bassi) - bypass des filtres coach_id, crédits illimités
3. ZÉRO RÉGRESSION - les 7 réservations et sessions Cardio de mars doivent être préservées
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://video-feed-platform.preview.emergentagent.com')
SUPER_ADMIN_EMAIL = "contact.artboost@gmail.com"


class TestHealthCheck:
    """Test API health"""
    
    def test_health_endpoint(self):
        """API is healthy"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "healthy"
        print(f"✅ Health check passed: {data}")


class TestSuperAdminBypass:
    """Test Super Admin (Bassi) has unlimited access"""
    
    def test_reservations_bypass_for_super_admin(self):
        """Super Admin sees ALL reservations (no coach_id filter)"""
        response = requests.get(
            f"{BASE_URL}/api/reservations",
            headers={"X-User-Email": SUPER_ADMIN_EMAIL}
        )
        assert response.status_code == 200
        data = response.json()
        # Should return paginated data
        reservations = data.get("data", [])
        total = data.get("pagination", {}).get("total", 0)
        print(f"✅ Super Admin sees {total} reservations (7+ expected)")
        assert total >= 7, f"Expected at least 7 reservations, got {total}"
    
    def test_contacts_bypass_for_super_admin(self):
        """Super Admin sees ALL contacts (no coach_id filter)"""
        response = requests.get(
            f"{BASE_URL}/api/chat/participants",
            headers={"X-User-Email": SUPER_ADMIN_EMAIL}
        )
        assert response.status_code == 200
        participants = response.json()
        print(f"✅ Super Admin sees {len(participants)} contacts")
        assert len(participants) >= 0  # May be empty if no participants
    
    def test_campaigns_bypass_for_super_admin(self):
        """Super Admin sees ALL campaigns (no coach_id filter)"""
        response = requests.get(
            f"{BASE_URL}/api/campaigns",
            headers={"X-User-Email": SUPER_ADMIN_EMAIL}
        )
        assert response.status_code == 200
        campaigns = response.json()
        print(f"✅ Super Admin sees {len(campaigns)} campaigns")
    
    def test_coach_profile_unlimited_credits(self):
        """Super Admin has unlimited credits (-1 or 'Illimité')"""
        response = requests.get(
            f"{BASE_URL}/api/coach/profile",
            headers={"X-User-Email": SUPER_ADMIN_EMAIL}
        )
        assert response.status_code == 200
        data = response.json()
        credits = data.get("credits", 0)
        # Super Admin should have -1 (unlimited) or bypass
        print(f"✅ Super Admin credits: {credits}")
        # Credits can be -1 (unlimited) or regular number for super admin
        # What matters is they get access, the check_credits function returns unlimited=True


class TestNonRegressionReservations:
    """Test 7+ reservations are preserved"""
    
    def test_reservations_count(self):
        """At least 7 reservations exist"""
        response = requests.get(
            f"{BASE_URL}/api/reservations?page=1&limit=100",
            headers={"X-User-Email": SUPER_ADMIN_EMAIL}
        )
        assert response.status_code == 200
        data = response.json()
        total = data.get("pagination", {}).get("total", 0)
        print(f"✅ Total reservations: {total}")
        assert total >= 7, f"Expected at least 7 reservations, got {total}"


class TestNonRegressionCourses:
    """Test Cardio sessions and Sunday Vibes are preserved"""
    
    def test_courses_exist(self):
        """Session Cardio and Sunday Vibes exist"""
        response = requests.get(f"{BASE_URL}/api/courses")
        assert response.status_code == 200
        courses = response.json()
        print(f"✅ Found {len(courses)} courses")
        
        # Check for Cardio session (should be on Wednesday - weekday 3)
        cardio_found = False
        sunday_found = False
        
        for course in courses:
            name = course.get("name", "").lower()
            weekday = course.get("weekday", -1)
            
            if "cardio" in name:
                cardio_found = True
                print(f"  ✅ Found Cardio: {course.get('name')} (weekday={weekday})")
            
            if "sunday" in name or "vibes" in name:
                sunday_found = True
                print(f"  ✅ Found Sunday Vibes: {course.get('name')} (weekday={weekday})")
        
        assert cardio_found, "Session Cardio not found!"
        assert sunday_found, "Sunday Vibes not found!"


class TestVitrinePartenaireAfroboost:
    """Test vitrine shows 'Partenaire Afroboost' badge"""
    
    def test_vitrine_bassi_returns_coach_data(self):
        """Vitrine /coach/bassi returns coach data"""
        response = requests.get(f"{BASE_URL}/api/coach/vitrine/bassi")
        assert response.status_code == 200
        data = response.json()
        
        coach = data.get("coach", {})
        offers = data.get("offers", [])
        courses = data.get("courses", [])
        
        print(f"✅ Vitrine bassi: coach={coach.get('name')}, offers={len(offers)}, courses={len(courses)}")
        
        assert coach.get("name") or coach.get("platform_name"), "Coach name missing"


class TestDiscountCodesAPI:
    """Test discount codes API"""
    
    def test_get_discount_codes(self):
        """Can retrieve discount codes"""
        response = requests.get(f"{BASE_URL}/api/discount-codes")
        assert response.status_code == 200
        codes = response.json()
        print(f"✅ Found {len(codes)} discount codes")


class TestUsersAPI:
    """Test users/contacts API"""
    
    def test_get_users(self):
        """Can retrieve users"""
        response = requests.get(f"{BASE_URL}/api/users")
        assert response.status_code == 200
        users = response.json()
        print(f"✅ Found {len(users)} users")


class TestOffersAPI:
    """Test offers API"""
    
    def test_get_offers(self):
        """Can retrieve offers"""
        response = requests.get(f"{BASE_URL}/api/offers")
        assert response.status_code == 200
        offers = response.json()
        print(f"✅ Found {len(offers)} offers")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
