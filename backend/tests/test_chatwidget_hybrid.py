"""
Test suite for ChatWidget Hybrid Mode - Subscriber vs Visitor flows
Tests the dual experience based on promo code validation
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://video-feed-platform.preview.emergentagent.com').rstrip('/')


class TestDiscountCodeValidation:
    """Tests for /api/discount-codes/validate endpoint"""
    
    def test_validate_public_code_success(self):
        """Test PROMO20SECRET code - no email restriction"""
        response = requests.post(f"{BASE_URL}/api/discount-codes/validate", json={
            "code": "PROMO20SECRET",
            "email": "anyone@example.com"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] == True
        assert data["code"]["code"] == "PROMO20SECRET"
        assert data["code"]["type"] == "%"
        assert data["code"]["value"] == 20
        assert data["code"]["assignedEmail"] is None
        print("✅ PROMO20SECRET validates for any email")
    
    def test_validate_public_code_case_insensitive(self):
        """Test code validation is case-insensitive"""
        response = requests.post(f"{BASE_URL}/api/discount-codes/validate", json={
            "code": "promo20secret",  # lowercase
            "email": "test@example.com"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] == True
        print("✅ Code validation is case-insensitive")
    
    def test_validate_restricted_code_correct_email(self):
        """Test basxx code with correct assigned email"""
        response = requests.post(f"{BASE_URL}/api/discount-codes/validate", json={
            "code": "basxx",
            "email": "bassicustomshoes@gmail.com"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] == True
        assert data["code"]["code"] == "basxx"
        assert data["code"]["assignedEmail"] == "bassicustomshoes@gmail.com"
        print("✅ basxx validates with correct email")
    
    def test_validate_restricted_code_wrong_email(self):
        """Test basxx code with wrong email - should fail"""
        response = requests.post(f"{BASE_URL}/api/discount-codes/validate", json={
            "code": "basxx",
            "email": "wrong@email.com"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] == False
        assert "réservé" in data["message"].lower() or "autre compte" in data["message"].lower()
        print("✅ basxx rejected for wrong email")
    
    def test_validate_invalid_code(self):
        """Test invalid/unknown code"""
        response = requests.post(f"{BASE_URL}/api/discount-codes/validate", json={
            "code": "INVALID_CODE_12345",
            "email": "test@example.com"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] == False
        assert "inconnu" in data["message"].lower() or "invalide" in data["message"].lower()
        print("✅ Invalid code rejected correctly")
    
    def test_validate_code_without_courseid(self):
        """Test code validation without courseId (identification flow)"""
        response = requests.post(f"{BASE_URL}/api/discount-codes/validate", json={
            "code": "PROMO20SECRET",
            "email": "test@example.com"
            # No courseId - should still work for identification
        })
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] == True
        print("✅ Code validates without courseId (identification flow)")


class TestChatSmartEntry:
    """Tests for /api/chat/smart-entry endpoint"""
    
    def test_smart_entry_new_user(self):
        """Test smart entry for a new user"""
        import uuid
        unique_id = str(uuid.uuid4())[:8]
        response = requests.post(f"{BASE_URL}/api/chat/smart-entry", json={
            "name": f"TEST_NewUser_{unique_id}",
            "email": f"test_newuser_{unique_id}@example.com",
            "whatsapp": f"+4179{unique_id[:7]}"
        })
        assert response.status_code == 200
        data = response.json()
        assert "participant" in data
        assert "session" in data
        assert "message" in data
        assert f"TEST_NewUser_{unique_id}" in data["participant"]["name"]
        print(f"✅ Smart entry created new user: {data['participant']['id']}")
    
    def test_smart_entry_returning_user(self):
        """Test smart entry recognizes returning user"""
        # First entry
        response1 = requests.post(f"{BASE_URL}/api/chat/smart-entry", json={
            "name": "TEST_ReturningUser",
            "email": "test_returning@example.com",
            "whatsapp": "+41799999999"
        })
        assert response1.status_code == 200
        
        # Second entry with same email
        response2 = requests.post(f"{BASE_URL}/api/chat/smart-entry", json={
            "name": "TEST_ReturningUser",
            "email": "test_returning@example.com",
            "whatsapp": "+41799999999"
        })
        assert response2.status_code == 200
        data = response2.json()
        # Should recognize as returning user
        assert data["is_returning"] == True or "Ravi de te revoir" in data.get("message", "")
        print("✅ Smart entry recognizes returning user")


class TestCoursesAPI:
    """Tests for /api/courses endpoint"""
    
    def test_get_courses(self):
        """Test fetching available courses"""
        response = requests.get(f"{BASE_URL}/api/courses")
        assert response.status_code == 200
        courses = response.json()
        assert isinstance(courses, list)
        assert len(courses) > 0
        # Check course structure
        for course in courses:
            assert "id" in course
            assert "name" in course
            assert "time" in course
        print(f"✅ Fetched {len(courses)} courses")


class TestHealthCheck:
    """Basic health check tests"""
    
    def test_api_health(self):
        """Test API health endpoint"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        print("✅ API health check passed")
    
    def test_root_endpoint(self):
        """Test root API endpoint"""
        response = requests.get(f"{BASE_URL}/api/")
        assert response.status_code == 200
        print("✅ Root endpoint accessible")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
