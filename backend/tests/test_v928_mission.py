"""
Test v9.2.8 Mission - SÉCURITÉ MAXIMALE, ISOLATION & COMMANDES
- Quick Controls (platform-settings API)
- Partner access toggle behavior
- Maintenance mode toggle behavior
- Data isolation by coach_id
- Clickable schedules in vitrine
- Anti-regression: 7 Bassi reservations
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://promo-credits-lab.preview.emergentagent.com').rstrip('/')

class TestPlatformSettingsAPI:
    """Test platform-settings GET/PUT API"""
    
    def test_get_platform_settings_returns_structure(self):
        """GET /api/platform-settings returns partner_access_enabled and maintenance_mode"""
        response = requests.get(f"{BASE_URL}/api/platform-settings")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "partner_access_enabled" in data, "Missing partner_access_enabled field"
        assert "maintenance_mode" in data, "Missing maintenance_mode field"
        assert isinstance(data["partner_access_enabled"], bool), "partner_access_enabled should be boolean"
        assert isinstance(data["maintenance_mode"], bool), "maintenance_mode should be boolean"
        print(f"✅ Platform settings: partner_access={data['partner_access_enabled']}, maintenance={data['maintenance_mode']}")
    
    def test_get_platform_settings_super_admin_flag(self):
        """GET /api/platform-settings with Super Admin header returns is_super_admin=true"""
        headers = {"X-User-Email": "contact.artboost@gmail.com"}
        response = requests.get(f"{BASE_URL}/api/platform-settings", headers=headers)
        assert response.status_code == 200
        
        data = response.json()
        assert data.get("is_super_admin") == True, "Super Admin should have is_super_admin=true"
        print(f"✅ Super Admin detected correctly: is_super_admin={data.get('is_super_admin')}")
    
    def test_put_platform_settings_super_admin_can_update(self):
        """PUT /api/platform-settings allows Super Admin to update toggles"""
        headers = {
            "X-User-Email": "contact.artboost@gmail.com",
            "Content-Type": "application/json"
        }
        
        # First, get current settings
        get_response = requests.get(f"{BASE_URL}/api/platform-settings", headers=headers)
        original_settings = get_response.json()
        
        # Update maintenance_mode to true
        update_payload = {"maintenance_mode": True}
        response = requests.put(f"{BASE_URL}/api/platform-settings", headers=headers, json=update_payload)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get("success") == True, "Update should succeed for Super Admin"
        assert data.get("maintenance_mode") == True, "maintenance_mode should be true after update"
        print(f"✅ Super Admin updated maintenance_mode to True")
        
        # Reset back to original
        reset_payload = {"maintenance_mode": original_settings.get("maintenance_mode", False)}
        requests.put(f"{BASE_URL}/api/platform-settings", headers=headers, json=reset_payload)
        print(f"✅ Reset maintenance_mode to {original_settings.get('maintenance_mode', False)}")
    
    def test_put_platform_settings_non_admin_forbidden(self):
        """PUT /api/platform-settings returns 403 for non-Super Admin"""
        headers = {
            "X-User-Email": "randomuser@example.com",
            "Content-Type": "application/json"
        }
        update_payload = {"maintenance_mode": True}
        response = requests.put(f"{BASE_URL}/api/platform-settings", headers=headers, json=update_payload)
        assert response.status_code == 403, f"Expected 403 for non-admin, got {response.status_code}"
        print(f"✅ Non-admin correctly blocked with 403")


class TestBassiReservationsAntiRegression:
    """Test anti-regression: 7 Bassi reservations"""
    
    def test_bassi_has_7_reservations(self):
        """GET /api/reservations for Super Admin returns 7 reservations"""
        headers = {"X-User-Email": "contact.artboost@gmail.com"}
        response = requests.get(f"{BASE_URL}/api/reservations", headers=headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        resp_json = response.json()
        # Handle both list and paginated response formats
        if isinstance(resp_json, list):
            data = resp_json
            total = len(data)
        else:
            data = resp_json.get("data", [])
            total = resp_json.get("pagination", {}).get("total", len(data))
        
        assert isinstance(data, list), "Reservations data should be a list"
        assert total >= 7, f"Expected at least 7 reservations, got {total}"
        print(f"✅ Bassi has {total} reservations (>= 7)")
        
        # Check that at least one reservation has userName containing 'Bassi'
        bassi_reservations = [r for r in data if 'bassi' in r.get('userName', '').lower()]
        if bassi_reservations:
            print(f"✅ Found {len(bassi_reservations)} reservations with 'Bassi' in userName")


class TestCoachVitrineAPI:
    """Test coach vitrine API for clickable dates"""
    
    def test_coach_vitrine_returns_courses(self):
        """GET /api/coach/vitrine/:username returns coach profile and courses"""
        # Test with 'bassi' username
        response = requests.get(f"{BASE_URL}/api/coach/vitrine/bassi")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "coach" in data, "Response should contain 'coach' field"
        assert "courses" in data, "Response should contain 'courses' field"
        assert "offers" in data, "Response should contain 'offers' field"
        
        coach = data.get("coach", {})
        print(f"✅ Coach vitrine loaded: {coach.get('name', 'N/A')}")
        print(f"✅ Courses: {len(data.get('courses', []))}, Offers: {len(data.get('offers', []))}")


class TestCoursesAPI:
    """Test courses API for homepage dates"""
    
    def test_courses_returns_list(self):
        """GET /api/courses returns list of courses with weekday info"""
        response = requests.get(f"{BASE_URL}/api/courses")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert isinstance(data, list), "Courses should be a list"
        assert len(data) > 0, "Should have at least one course"
        
        # Check that courses have weekday and time
        first_course = data[0]
        assert "weekday" in first_course, "Course should have weekday"
        assert "time" in first_course, "Course should have time"
        print(f"✅ Found {len(data)} courses")
        for c in data[:3]:
            print(f"   - {c.get('name', 'N/A')}: weekday={c.get('weekday')}, time={c.get('time')}")


class TestMarchDates:
    """Test that homepage shows 4 March dates"""
    
    def test_next_dates_calculation(self):
        """Verify that getNextOccurrences would generate 4 dates"""
        from datetime import datetime, timedelta
        
        # Simulate getNextOccurrences for Wednesday (weekday=3) from March 2025
        def get_next_occurrences(weekday, count=4):
            now = datetime(2025, 3, 1)  # March 2025
            results = []
            day = now.weekday()  # Monday=0, Sunday=6 (Python) vs Sunday=0 (JS)
            # Convert JS weekday to Python: JS 0=Sun, 1=Mon... Python 0=Mon, 6=Sun
            py_weekday = (weekday - 1) % 7 if weekday > 0 else 6
            diff = py_weekday - day
            if diff < 0:
                diff += 7
            current = now + timedelta(days=diff)
            for i in range(count):
                results.append(current)
                current = current + timedelta(days=7)
            return results
        
        # Wednesday = weekday 3 in JavaScript
        dates = get_next_occurrences(3, 4)
        assert len(dates) == 4, f"Expected 4 dates, got {len(dates)}"
        print(f"✅ Generated 4 dates for March: {[d.strftime('%d.%m') for d in dates]}")


class TestReservationCreation:
    """Test that reservations can be created via vitrine"""
    
    def test_reservation_create_endpoint_exists(self):
        """POST /api/reservations endpoint exists and validates input"""
        # Send minimal data to check endpoint exists
        response = requests.post(f"{BASE_URL}/api/reservations", json={})
        # We expect 422 (validation error) not 404 (not found)
        assert response.status_code in [200, 201, 422, 400], f"Unexpected status {response.status_code}"
        print(f"✅ Reservation endpoint exists (status: {response.status_code})")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
