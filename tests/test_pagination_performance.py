"""
Test suite for Pagination and Performance Optimization features
Tests:
1. GET /api/reservations?page=1&limit=20 - Pagination with page, limit, total, pages
2. GET /api/reservations?all_data=true - Retrieve all data (for CSV export)
3. Offer keywords field - Pre-filled when editing offers
4. Client search - Filter by title, description and keywords
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://video-feed-platform.preview.emergentagent.com').rstrip('/')

class TestReservationPagination:
    """Test reservation pagination endpoints"""
    
    def test_health_check(self):
        """Verify API is healthy"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        print("✅ API health check passed")
    
    def test_reservations_pagination_default(self):
        """Test GET /api/reservations with default pagination (page=1, limit=20)"""
        response = requests.get(f"{BASE_URL}/api/reservations")
        assert response.status_code == 200
        data = response.json()
        
        # Verify pagination structure
        assert "data" in data, "Response should have 'data' field"
        assert "pagination" in data, "Response should have 'pagination' field"
        
        pagination = data["pagination"]
        assert "page" in pagination, "Pagination should have 'page'"
        assert "limit" in pagination, "Pagination should have 'limit'"
        assert "total" in pagination, "Pagination should have 'total'"
        assert "pages" in pagination, "Pagination should have 'pages'"
        
        # Default values
        assert pagination["page"] == 1, "Default page should be 1"
        assert pagination["limit"] == 20, "Default limit should be 20"
        assert isinstance(pagination["total"], int), "Total should be integer"
        assert isinstance(pagination["pages"], int), "Pages should be integer"
        
        print(f"✅ Pagination default test passed - Total: {pagination['total']}, Pages: {pagination['pages']}")
    
    def test_reservations_pagination_custom_page_limit(self):
        """Test GET /api/reservations with custom page and limit"""
        response = requests.get(f"{BASE_URL}/api/reservations?page=1&limit=5")
        assert response.status_code == 200
        data = response.json()
        
        pagination = data["pagination"]
        assert pagination["page"] == 1
        assert pagination["limit"] == 5
        
        # Data should not exceed limit
        assert len(data["data"]) <= 5, "Data should not exceed limit"
        
        print(f"✅ Custom pagination test passed - Limit: 5, Returned: {len(data['data'])}")
    
    def test_reservations_all_data_for_export(self):
        """Test GET /api/reservations?all_data=true for CSV export"""
        response = requests.get(f"{BASE_URL}/api/reservations?all_data=true")
        assert response.status_code == 200
        data = response.json()
        
        # Should still have pagination structure
        assert "data" in data
        assert "pagination" in data
        
        # all_data=true should return all reservations
        pagination = data["pagination"]
        total = pagination["total"]
        
        # If there are reservations, all should be returned
        if total > 0:
            assert len(data["data"]) == total, f"all_data=true should return all {total} reservations"
        
        print(f"✅ All data export test passed - Total reservations: {total}")
    
    def test_reservations_pagination_page_2(self):
        """Test pagination page 2"""
        response = requests.get(f"{BASE_URL}/api/reservations?page=2&limit=10")
        assert response.status_code == 200
        data = response.json()
        
        pagination = data["pagination"]
        assert pagination["page"] == 2
        assert pagination["limit"] == 10
        
        print(f"✅ Page 2 pagination test passed")


class TestOfferKeywords:
    """Test offer keywords field for search optimization"""
    
    def test_offers_have_keywords_field(self):
        """Verify offers have keywords field"""
        response = requests.get(f"{BASE_URL}/api/offers")
        assert response.status_code == 200
        offers = response.json()
        
        assert len(offers) > 0, "Should have at least one offer"
        
        # Check first offer has keywords field
        first_offer = offers[0]
        assert "keywords" in first_offer, "Offer should have 'keywords' field"
        
        print(f"✅ Offers have keywords field - Found {len(offers)} offers")
    
    def test_create_offer_with_keywords(self):
        """Test creating an offer with keywords"""
        test_keywords = "fitness, cardio, danse, afrobeat, test"
        offer_data = {
            "name": f"TEST_Offer_Keywords_{uuid.uuid4().hex[:6]}",
            "price": 25.0,
            "visible": False,  # Hidden for testing
            "description": "Test offer with keywords",
            "keywords": test_keywords,
            "images": [],
            "category": "service",
            "isProduct": False,
            "tva": 0,
            "shippingCost": 0,
            "stock": -1
        }
        
        response = requests.post(f"{BASE_URL}/api/offers", json=offer_data)
        assert response.status_code == 200
        created_offer = response.json()
        
        assert created_offer["keywords"] == test_keywords, "Keywords should be saved"
        assert created_offer["name"] == offer_data["name"]
        
        offer_id = created_offer["id"]
        print(f"✅ Created offer with keywords - ID: {offer_id}")
        
        # Verify keywords are returned when fetching offers
        response = requests.get(f"{BASE_URL}/api/offers")
        offers = response.json()
        found_offer = next((o for o in offers if o["id"] == offer_id), None)
        assert found_offer is not None, "Created offer should be in list"
        assert found_offer["keywords"] == test_keywords, "Keywords should persist"
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/offers/{offer_id}")
        print(f"✅ Offer keywords persistence verified and cleaned up")
    
    def test_update_offer_keywords(self):
        """Test updating offer keywords"""
        # Create test offer
        offer_data = {
            "name": f"TEST_Update_Keywords_{uuid.uuid4().hex[:6]}",
            "price": 30.0,
            "visible": False,
            "description": "Test",
            "keywords": "initial, keywords",
            "images": [],
            "category": "service",
            "isProduct": False,
            "tva": 0,
            "shippingCost": 0,
            "stock": -1
        }
        
        response = requests.post(f"{BASE_URL}/api/offers", json=offer_data)
        assert response.status_code == 200
        offer_id = response.json()["id"]
        
        # Update keywords
        updated_keywords = "updated, new, keywords, fitness"
        update_data = {**offer_data, "keywords": updated_keywords}
        response = requests.put(f"{BASE_URL}/api/offers/{offer_id}", json=update_data)
        assert response.status_code == 200
        
        updated_offer = response.json()
        assert updated_offer["keywords"] == updated_keywords, "Keywords should be updated"
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/offers/{offer_id}")
        print(f"✅ Offer keywords update test passed")


class TestReservationProjection:
    """Test MongoDB projection for performance optimization"""
    
    def test_reservation_fields_returned(self):
        """Verify reservation response includes necessary fields"""
        response = requests.get(f"{BASE_URL}/api/reservations?page=1&limit=20")
        assert response.status_code == 200
        data = response.json()
        
        # Expected fields in projection
        expected_fields = [
            "id", "reservationCode", "userName", "userEmail", "userWhatsapp",
            "courseName", "courseTime", "datetime", "offerName", "totalPrice",
            "quantity", "validated", "validatedAt", "createdAt",
            "selectedDates", "selectedDatesText", "selectedVariants", "variantsText",
            "isProduct", "shippingStatus", "trackingNumber"
        ]
        
        if len(data["data"]) > 0:
            reservation = data["data"][0]
            for field in expected_fields:
                assert field in reservation, f"Reservation should have '{field}' field"
            print(f"✅ Reservation projection includes all {len(expected_fields)} expected fields")
        else:
            print("⚠️ No reservations to verify projection fields (empty database)")
    
    def test_no_mongodb_id_in_response(self):
        """Verify MongoDB _id is excluded from response"""
        response = requests.get(f"{BASE_URL}/api/reservations?page=1&limit=20")
        assert response.status_code == 200
        data = response.json()
        
        if len(data["data"]) > 0:
            reservation = data["data"][0]
            assert "_id" not in reservation, "MongoDB _id should be excluded"
            print("✅ MongoDB _id correctly excluded from response")
        else:
            print("⚠️ No reservations to verify _id exclusion")


class TestCreateReservationForPagination:
    """Create test reservations to verify pagination works correctly"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get course and offer IDs for creating reservations"""
        courses_response = requests.get(f"{BASE_URL}/api/courses")
        offers_response = requests.get(f"{BASE_URL}/api/offers")
        
        self.courses = courses_response.json()
        self.offers = offers_response.json()
        
        # Get first visible course and offer
        self.course = next((c for c in self.courses if c.get("visible", True)), self.courses[0] if self.courses else None)
        self.offer = next((o for o in self.offers if o.get("visible", True)), self.offers[0] if self.offers else None)
    
    def test_create_and_paginate_reservations(self):
        """Create multiple reservations and verify pagination"""
        if not self.course or not self.offer:
            pytest.skip("No course or offer available for testing")
        
        created_ids = []
        
        # Create 3 test reservations
        for i in range(3):
            reservation_data = {
                "userId": f"test_user_{uuid.uuid4().hex[:6]}",
                "userName": f"TEST_Pagination_User_{i+1}",
                "userEmail": f"test_pagination_{i+1}@test.com",
                "userWhatsapp": "+41791234567",
                "courseId": self.course["id"],
                "courseName": self.course["name"],
                "courseTime": self.course.get("time", "18:30"),
                "datetime": "2025-01-15T18:30:00",
                "offerId": self.offer["id"],
                "offerName": self.offer["name"],
                "price": self.offer["price"],
                "quantity": 1,
                "totalPrice": self.offer["price"],
                "isProduct": False,
                "selectedDates": ["2025-01-15"],
                "selectedDatesText": "15 janvier 2025"
            }
            
            response = requests.post(f"{BASE_URL}/api/reservations", json=reservation_data)
            assert response.status_code == 200
            created_ids.append(response.json()["id"])
        
        print(f"✅ Created {len(created_ids)} test reservations")
        
        # Verify pagination reflects new reservations
        response = requests.get(f"{BASE_URL}/api/reservations?page=1&limit=20")
        assert response.status_code == 200
        data = response.json()
        
        assert data["pagination"]["total"] >= 3, "Should have at least 3 reservations"
        
        # Verify all_data returns all
        response = requests.get(f"{BASE_URL}/api/reservations?all_data=true")
        all_data = response.json()
        assert len(all_data["data"]) == all_data["pagination"]["total"]
        
        print(f"✅ Pagination verified - Total: {data['pagination']['total']}")
        
        # Cleanup
        for res_id in created_ids:
            requests.delete(f"{BASE_URL}/api/reservations/{res_id}")
        
        print(f"✅ Cleaned up {len(created_ids)} test reservations")


class TestSearchFunctionality:
    """Test client search including title, description and keywords"""
    
    def test_offers_searchable_fields(self):
        """Verify offers have all searchable fields"""
        response = requests.get(f"{BASE_URL}/api/offers")
        assert response.status_code == 200
        offers = response.json()
        
        if len(offers) > 0:
            offer = offers[0]
            searchable_fields = ["name", "description", "keywords"]
            for field in searchable_fields:
                assert field in offer, f"Offer should have '{field}' for search"
            print(f"✅ Offers have all searchable fields: {searchable_fields}")
        else:
            print("⚠️ No offers to verify searchable fields")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
