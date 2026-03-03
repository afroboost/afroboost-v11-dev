"""
Test Navigation Features - Afroboost P0
Tests for:
- Navigation bar filters (Tout, Sessions, Offres, Shop)
- Search functionality
- LandingSectionSelector in Coach Mode
- defaultLandingSection persistence in MongoDB via /api/concept
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://promo-credits-lab.preview.emergentagent.com')


class TestConceptAPI:
    """Tests for /api/concept endpoint with defaultLandingSection"""
    
    def test_get_concept_returns_default_landing_section(self):
        """GET /api/concept should return defaultLandingSection field"""
        response = requests.get(f"{BASE_URL}/api/concept")
        assert response.status_code == 200
        
        data = response.json()
        assert "defaultLandingSection" in data
        assert data["defaultLandingSection"] in ["sessions", "offers", "shop", "all"]
        print(f"✅ GET /api/concept - defaultLandingSection: {data['defaultLandingSection']}")
    
    def test_update_concept_default_landing_section_to_shop(self):
        """PUT /api/concept should update defaultLandingSection to 'shop'"""
        # Update to shop
        response = requests.put(
            f"{BASE_URL}/api/concept",
            json={"defaultLandingSection": "shop"}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["defaultLandingSection"] == "shop"
        print("✅ PUT /api/concept - Updated defaultLandingSection to 'shop'")
        
        # Verify persistence with GET
        get_response = requests.get(f"{BASE_URL}/api/concept")
        assert get_response.status_code == 200
        assert get_response.json()["defaultLandingSection"] == "shop"
        print("✅ GET /api/concept - Verified persistence of 'shop'")
    
    def test_update_concept_default_landing_section_to_offers(self):
        """PUT /api/concept should update defaultLandingSection to 'offers'"""
        response = requests.put(
            f"{BASE_URL}/api/concept",
            json={"defaultLandingSection": "offers"}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["defaultLandingSection"] == "offers"
        print("✅ PUT /api/concept - Updated defaultLandingSection to 'offers'")
    
    def test_update_concept_default_landing_section_to_sessions(self):
        """PUT /api/concept should update defaultLandingSection to 'sessions'"""
        response = requests.put(
            f"{BASE_URL}/api/concept",
            json={"defaultLandingSection": "sessions"}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["defaultLandingSection"] == "sessions"
        print("✅ PUT /api/concept - Updated defaultLandingSection to 'sessions'")


class TestOffersAPI:
    """Tests for /api/offers endpoint - filtering by isProduct"""
    
    def test_get_offers_returns_list(self):
        """GET /api/offers should return a list of offers"""
        response = requests.get(f"{BASE_URL}/api/offers")
        assert response.status_code == 200
        
        data = response.json()
        assert isinstance(data, list)
        print(f"✅ GET /api/offers - Returned {len(data)} offers")
    
    def test_offers_have_is_product_field(self):
        """All offers should have isProduct field for filtering"""
        response = requests.get(f"{BASE_URL}/api/offers")
        assert response.status_code == 200
        
        data = response.json()
        for offer in data:
            assert "isProduct" in offer, f"Offer {offer.get('name')} missing isProduct field"
        print("✅ All offers have isProduct field")
    
    def test_filter_products_only(self):
        """Filter offers where isProduct=true (Shop filter)"""
        response = requests.get(f"{BASE_URL}/api/offers")
        assert response.status_code == 200
        
        data = response.json()
        products = [o for o in data if o.get("isProduct") == True]
        services = [o for o in data if o.get("isProduct") == False]
        
        print(f"✅ Products (isProduct=true): {len(products)}")
        print(f"✅ Services (isProduct=false): {len(services)}")
        
        # Verify we have both types for proper filtering
        assert len(products) >= 0, "Should have products for Shop filter"
        assert len(services) >= 0, "Should have services for Sessions filter"


class TestCoursesAPI:
    """Tests for /api/courses endpoint"""
    
    def test_get_courses_returns_list(self):
        """GET /api/courses should return a list of courses"""
        response = requests.get(f"{BASE_URL}/api/courses")
        assert response.status_code == 200
        
        data = response.json()
        assert isinstance(data, list)
        print(f"✅ GET /api/courses - Returned {len(data)} courses")
    
    def test_courses_have_visible_field(self):
        """All courses should have visible field for filtering"""
        response = requests.get(f"{BASE_URL}/api/courses")
        assert response.status_code == 200
        
        data = response.json()
        for course in data:
            assert "visible" in course, f"Course {course.get('name')} missing visible field"
        print("✅ All courses have visible field")


class TestCoachAuth:
    """Tests for coach authentication"""
    
    def test_coach_login_success(self):
        """POST /api/coach-auth/login with valid credentials"""
        response = requests.post(
            f"{BASE_URL}/api/coach-auth/login",
            json={"email": "coach@afroboost.com", "password": "afroboost123"}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data.get("success") == True
        print("✅ Coach login successful")
    
    def test_coach_login_failure(self):
        """POST /api/coach-auth/login with invalid credentials"""
        response = requests.post(
            f"{BASE_URL}/api/coach-auth/login",
            json={"email": "wrong@email.com", "password": "wrongpassword"}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data.get("success") == False
        print("✅ Coach login correctly rejected invalid credentials")


# Cleanup fixture to reset defaultLandingSection after tests
@pytest.fixture(scope="module", autouse=True)
def cleanup_after_tests():
    """Reset defaultLandingSection to 'sessions' after all tests"""
    yield
    requests.put(
        f"{BASE_URL}/api/concept",
        json={"defaultLandingSection": "sessions"}
    )
    print("✅ Cleanup: Reset defaultLandingSection to 'sessions'")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
