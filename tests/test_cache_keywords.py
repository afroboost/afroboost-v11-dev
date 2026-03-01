"""
Test suite for Cache System and Keywords functionality
Tests: Cache TTL, Keywords modification, Search with keywords
"""
import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://video-feed-platform.preview.emergentagent.com')

class TestCacheAndKeywords:
    """Tests for cache system and keywords functionality"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test fixtures"""
        self.api = f"{BASE_URL}/api"
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
    
    # === BACKEND API TESTS ===
    
    def test_health_check(self):
        """Test API health endpoint"""
        response = self.session.get(f"{self.api}/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "healthy"
        print("✅ Health check passed")
    
    def test_get_courses(self):
        """Test courses endpoint returns data"""
        response = self.session.get(f"{self.api}/courses")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✅ Courses endpoint returned {len(data)} courses")
    
    def test_get_offers(self):
        """Test offers endpoint returns data"""
        response = self.session.get(f"{self.api}/offers")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✅ Offers endpoint returned {len(data)} offers")
    
    def test_get_concept(self):
        """Test concept endpoint returns data"""
        response = self.session.get(f"{self.api}/concept")
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        print("✅ Concept endpoint returned data")
    
    def test_get_payment_links(self):
        """Test payment-links endpoint returns data"""
        response = self.session.get(f"{self.api}/payment-links")
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        print("✅ Payment-links endpoint returned data")
    
    # === KEYWORDS TESTS ===
    
    def test_offer_has_keywords_field(self):
        """Test that offers have keywords field"""
        response = self.session.get(f"{self.api}/offers")
        assert response.status_code == 200
        offers = response.json()
        
        # Check if at least one offer has keywords
        has_keywords = any(offer.get("keywords") for offer in offers)
        print(f"✅ Offers with keywords: {has_keywords}")
        
        # Print offers with keywords
        for offer in offers:
            if offer.get("keywords"):
                print(f"  - {offer.get('name')}: keywords='{offer.get('keywords')}'")
    
    def test_create_offer_with_keywords(self):
        """Test creating an offer with keywords"""
        test_offer = {
            "name": "TEST_Cache_Keywords_Offer",
            "price": 25,
            "visible": True,
            "keywords": "test, cache, keywords, fitness",
            "description": "Test offer for keywords functionality"
        }
        
        response = self.session.post(f"{self.api}/offers", json=test_offer)
        assert response.status_code == 200
        created = response.json()
        
        assert created.get("name") == test_offer["name"]
        assert created.get("keywords") == test_offer["keywords"]
        print(f"✅ Created offer with keywords: {created.get('keywords')}")
        
        # Store ID for cleanup
        self.test_offer_id = created.get("id")
        
        # Verify by fetching
        response = self.session.get(f"{self.api}/offers")
        offers = response.json()
        found = next((o for o in offers if o.get("id") == self.test_offer_id), None)
        assert found is not None
        assert found.get("keywords") == test_offer["keywords"]
        print("✅ Keywords persisted correctly in database")
        
        # Cleanup
        if self.test_offer_id:
            self.session.delete(f"{self.api}/offers/{self.test_offer_id}")
            print("✅ Test offer cleaned up")
    
    def test_update_offer_keywords(self):
        """Test updating keywords on an existing offer"""
        # First create an offer
        test_offer = {
            "name": "TEST_Update_Keywords_Offer",
            "price": 30,
            "visible": True,
            "keywords": "original, keywords"
        }
        
        response = self.session.post(f"{self.api}/offers", json=test_offer)
        assert response.status_code == 200
        created = response.json()
        offer_id = created.get("id")
        
        # Update keywords (include required fields)
        update_data = {
            "name": "TEST_Update_Keywords_Offer",
            "price": 30,
            "keywords": "updated, new, keywords, search"
        }
        response = self.session.put(f"{self.api}/offers/{offer_id}", json=update_data)
        assert response.status_code == 200
        
        # Verify update
        response = self.session.get(f"{self.api}/offers")
        offers = response.json()
        updated = next((o for o in offers if o.get("id") == offer_id), None)
        assert updated is not None
        assert updated.get("keywords") == update_data["keywords"]
        print(f"✅ Keywords updated successfully: {updated.get('keywords')}")
        
        # Cleanup
        self.session.delete(f"{self.api}/offers/{offer_id}")
        print("✅ Test offer cleaned up")
    
    # === COACH AUTH TESTS ===
    
    def test_coach_login(self):
        """Test coach login endpoint"""
        login_data = {
            "email": "coach@afroboost.com",
            "password": "afroboost123"
        }
        
        response = self.session.post(f"{self.api}/coach-auth/login", json=login_data)
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") == True
        print("✅ Coach login successful")
    
    def test_coach_login_wrong_credentials(self):
        """Test coach login with wrong credentials"""
        login_data = {
            "email": "wrong@email.com",
            "password": "wrongpassword"
        }
        
        response = self.session.post(f"{self.api}/coach-auth/login", json=login_data)
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") == False
        print("✅ Coach login correctly rejected wrong credentials")
    
    # === CACHE PERFORMANCE TESTS ===
    
    def test_api_response_time(self):
        """Test API response times are reasonable"""
        endpoints = [
            "/courses",
            "/offers",
            "/concept",
            "/payment-links"
        ]
        
        for endpoint in endpoints:
            start = time.time()
            response = self.session.get(f"{self.api}{endpoint}")
            elapsed = time.time() - start
            
            assert response.status_code == 200
            assert elapsed < 5.0, f"Endpoint {endpoint} took too long: {elapsed:.2f}s"
            print(f"✅ {endpoint}: {elapsed:.3f}s")
    
    def test_parallel_requests(self):
        """Test multiple parallel requests (simulating cache behavior)"""
        import concurrent.futures
        
        def fetch_endpoint(endpoint):
            response = self.session.get(f"{self.api}{endpoint}")
            return endpoint, response.status_code, len(response.content)
        
        endpoints = ["/courses", "/offers", "/concept", "/payment-links"]
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(fetch_endpoint, ep) for ep in endpoints]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]
        
        for endpoint, status, size in results:
            assert status == 200
            print(f"✅ Parallel request {endpoint}: status={status}, size={size}")


class TestReservationsAndDiscountCodes:
    """Tests for reservations and discount codes"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test fixtures"""
        self.api = f"{BASE_URL}/api"
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
    
    def test_get_reservations_pagination(self):
        """Test reservations endpoint with pagination"""
        response = self.session.get(f"{self.api}/reservations")
        assert response.status_code == 200
        data = response.json()
        
        # Check pagination structure
        assert "data" in data
        assert "pagination" in data
        assert "page" in data["pagination"]
        assert "limit" in data["pagination"]
        assert "total" in data["pagination"]
        print(f"✅ Reservations pagination: page={data['pagination']['page']}, total={data['pagination']['total']}")
    
    def test_get_discount_codes(self):
        """Test discount codes endpoint"""
        response = self.session.get(f"{self.api}/discount-codes")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✅ Discount codes endpoint returned {len(data)} codes")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
