"""
Test suite for Batch Discount Code Generation Feature
Tests the ability to generate multiple promo codes in series (e.g., TEST-1, TEST-2, etc.)
"""
import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://promo-credits-lab.preview.emergentagent.com')

class TestDiscountCodesAPI:
    """Test discount codes CRUD operations"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test session"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        self.created_code_ids = []
        yield
        # Cleanup: Delete test codes created during tests
        for code_id in self.created_code_ids:
            try:
                self.session.delete(f"{BASE_URL}/api/discount-codes/{code_id}")
            except:
                pass
    
    def test_api_health(self):
        """Test API is accessible"""
        response = self.session.get(f"{BASE_URL}/api/")
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        print("✅ API health check passed")
    
    def test_get_discount_codes(self):
        """Test GET /api/discount-codes returns list"""
        response = self.session.get(f"{BASE_URL}/api/discount-codes")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✅ GET discount codes returned {len(data)} codes")
    
    def test_create_single_discount_code(self):
        """Test creating a single discount code"""
        code_data = {
            "code": f"TEST_SINGLE_{int(time.time())}",
            "type": "%",
            "value": 10.0,
            "assignedEmail": None,
            "courses": [],
            "maxUses": 5,
            "expiresAt": "2025-12-31"
        }
        
        response = self.session.post(f"{BASE_URL}/api/discount-codes", json=code_data)
        assert response.status_code == 200
        
        data = response.json()
        assert "id" in data
        assert data["code"] == code_data["code"]
        assert data["type"] == code_data["type"]
        assert data["value"] == code_data["value"]
        assert data["active"] == True
        
        self.created_code_ids.append(data["id"])
        print(f"✅ Created single code: {data['code']}")
    
    def test_create_batch_codes_simulation(self):
        """Test creating batch codes (simulating frontend batch generation)"""
        prefix = f"BATCH_{int(time.time()) % 10000}"
        count = 5
        created_codes = []
        
        # Simulate batch creation like frontend does
        for i in range(1, count + 1):
            code_data = {
                "code": f"{prefix}-{i}",
                "type": "100%",
                "value": 100.0,
                "assignedEmail": None,
                "courses": [],
                "maxUses": 1,
                "expiresAt": "2025-12-31"
            }
            
            response = self.session.post(f"{BASE_URL}/api/discount-codes", json=code_data)
            assert response.status_code == 200, f"Failed to create code {i}: {response.text}"
            
            data = response.json()
            assert data["code"] == f"{prefix}-{i}"
            created_codes.append(data)
            self.created_code_ids.append(data["id"])
        
        # Verify all codes were created
        assert len(created_codes) == count
        
        # Verify codes follow the pattern PREFIX-1, PREFIX-2, etc.
        for i, code in enumerate(created_codes, 1):
            assert code["code"] == f"{prefix}-{i}"
            assert code["type"] == "100%"
            assert code["value"] == 100.0
            assert code["active"] == True
        
        print(f"✅ Created batch of {count} codes: {prefix}-1 to {prefix}-{count}")
    
    def test_batch_codes_max_20_limit(self):
        """Test that batch generation respects max 20 codes limit (frontend validation)"""
        # This is a frontend validation, but we test that API can handle 20 codes
        prefix = f"MAX_{int(time.time()) % 10000}"
        max_count = 20
        
        # Create 20 codes
        for i in range(1, max_count + 1):
            code_data = {
                "code": f"{prefix}-{i}",
                "type": "%",
                "value": 50.0,
                "assignedEmail": None,
                "courses": [],
                "maxUses": None,
                "expiresAt": None
            }
            
            response = self.session.post(f"{BASE_URL}/api/discount-codes", json=code_data)
            assert response.status_code == 200
            self.created_code_ids.append(response.json()["id"])
        
        # Verify all 20 codes exist
        response = self.session.get(f"{BASE_URL}/api/discount-codes")
        all_codes = response.json()
        batch_codes = [c for c in all_codes if c["code"].startswith(prefix)]
        assert len(batch_codes) == max_count
        
        print(f"✅ Successfully created maximum batch of {max_count} codes")
    
    def test_toggle_code_active_status(self):
        """Test activating/deactivating a discount code"""
        # Create a test code
        code_data = {
            "code": f"TEST_TOGGLE_{int(time.time())}",
            "type": "CHF",
            "value": 20.0,
            "assignedEmail": None,
            "courses": [],
            "maxUses": None,
            "expiresAt": None
        }
        
        response = self.session.post(f"{BASE_URL}/api/discount-codes", json=code_data)
        assert response.status_code == 200
        code = response.json()
        self.created_code_ids.append(code["id"])
        
        # Initially active
        assert code["active"] == True
        
        # Deactivate
        response = self.session.put(f"{BASE_URL}/api/discount-codes/{code['id']}", json={"active": False})
        assert response.status_code == 200
        updated = response.json()
        assert updated["active"] == False
        
        # Reactivate
        response = self.session.put(f"{BASE_URL}/api/discount-codes/{code['id']}", json={"active": True})
        assert response.status_code == 200
        updated = response.json()
        assert updated["active"] == True
        
        print(f"✅ Toggle active status works for code: {code['code']}")
    
    def test_delete_discount_code(self):
        """Test deleting a discount code"""
        # Create a test code
        code_data = {
            "code": f"TEST_DELETE_{int(time.time())}",
            "type": "%",
            "value": 15.0,
            "assignedEmail": None,
            "courses": [],
            "maxUses": None,
            "expiresAt": None
        }
        
        response = self.session.post(f"{BASE_URL}/api/discount-codes", json=code_data)
        assert response.status_code == 200
        code = response.json()
        code_id = code["id"]
        
        # Delete the code
        response = self.session.delete(f"{BASE_URL}/api/discount-codes/{code_id}")
        assert response.status_code == 200
        
        # Verify it's deleted
        response = self.session.get(f"{BASE_URL}/api/discount-codes")
        all_codes = response.json()
        deleted_code = next((c for c in all_codes if c["id"] == code_id), None)
        assert deleted_code is None
        
        print(f"✅ Successfully deleted code: {code['code']}")
    
    def test_validate_discount_code(self):
        """Test validating a discount code"""
        # Use an existing code (VIP-1) that we know exists
        response = self.session.post(f"{BASE_URL}/api/discount-codes/validate", json={
            "code": "VIP-1",
            "email": "test@example.com",
            "courseId": ""
        })
        assert response.status_code == 200
        result = response.json()
        assert result["valid"] == True
        assert result["code"]["code"] == "VIP-1"
        
        print(f"✅ Code validation works for: VIP-1")
    
    def test_validate_invalid_code(self):
        """Test validating an invalid/non-existent code"""
        response = self.session.post(f"{BASE_URL}/api/discount-codes/validate", json={
            "code": "NONEXISTENT_CODE_12345",
            "email": "test@example.com",
            "courseId": ""
        })
        assert response.status_code == 200
        result = response.json()
        assert result["valid"] == False
        
        print("✅ Invalid code validation returns valid=False")
    
    def test_batch_codes_same_parameters(self):
        """Test that all batch codes have the same parameters (type, value, expiration)"""
        prefix = f"PARAM_{int(time.time()) % 10000}"
        count = 3
        
        # Common parameters for all codes
        common_params = {
            "type": "%",
            "value": 25.0,
            "assignedEmail": "batch@test.com",
            "courses": [],
            "maxUses": 10,
            "expiresAt": "2025-06-30"
        }
        
        created_codes = []
        for i in range(1, count + 1):
            code_data = {
                "code": f"{prefix}-{i}",
                **common_params
            }
            
            response = self.session.post(f"{BASE_URL}/api/discount-codes", json=code_data)
            assert response.status_code == 200
            data = response.json()
            created_codes.append(data)
            self.created_code_ids.append(data["id"])
        
        # Verify all codes have the same parameters
        for code in created_codes:
            assert code["type"] == common_params["type"]
            assert code["value"] == common_params["value"]
            assert code["assignedEmail"] == common_params["assignedEmail"]
            assert code["maxUses"] == common_params["maxUses"]
            assert code["expiresAt"] == common_params["expiresAt"]
        
        print(f"✅ All {count} batch codes have identical parameters")


class TestCoachAuthentication:
    """Test coach login for accessing promo codes management"""
    
    def test_coach_login_success(self):
        """Test successful coach login"""
        response = requests.post(f"{BASE_URL}/api/coach-auth/login", json={
            "email": "coach@afroboost.com",
            "password": "afroboost123"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        print("✅ Coach login successful")
    
    def test_coach_login_failure(self):
        """Test failed coach login with wrong credentials"""
        response = requests.post(f"{BASE_URL}/api/coach-auth/login", json={
            "email": "wrong@email.com",
            "password": "wrongpassword"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["success"] == False
        print("✅ Coach login correctly rejects wrong credentials")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
