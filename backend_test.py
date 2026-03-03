#!/usr/bin/env python3
"""
Afroboost Backend API Testing Suite
Tests all backend endpoints for the headphone reservation system
"""

import requests
import sys
import json
from datetime import datetime
from typing import Dict, Any

class AfroboostAPITester:
    def __init__(self, base_url="https://promo-credits-lab.preview.emergentagent.com"):
        self.base_url = base_url
        self.api_url = f"{base_url}/api"
        self.tests_run = 0
        self.tests_passed = 0
        self.test_results = []
        self.created_ids = {
            'courses': [],
            'offers': [],
            'users': [],
            'reservations': [],
            'discount_codes': []
        }

    def log_test(self, name: str, success: bool, details: str = "", response_data: Any = None):
        """Log test result"""
        self.tests_run += 1
        if success:
            self.tests_passed += 1
            print(f"✅ {name}")
        else:
            print(f"❌ {name} - {details}")
        
        self.test_results.append({
            'name': name,
            'success': success,
            'details': details,
            'response_data': response_data
        })

    def make_request(self, method: str, endpoint: str, data: Dict = None, expected_status: int = 200) -> tuple:
        """Make HTTP request and return success status and response data"""
        url = f"{self.api_url}/{endpoint}"
        headers = {'Content-Type': 'application/json'}
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, timeout=10)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers, timeout=10)
            elif method == 'PUT':
                response = requests.put(url, json=data, headers=headers, timeout=10)
            elif method == 'DELETE':
                response = requests.delete(url, headers=headers, timeout=10)
            else:
                return False, f"Unsupported method: {method}"

            success = response.status_code == expected_status
            
            if success:
                try:
                    return True, response.json()
                except:
                    return True, response.text
            else:
                return False, f"Status {response.status_code}, expected {expected_status}. Response: {response.text[:200]}"
                
        except requests.exceptions.RequestException as e:
            return False, f"Request failed: {str(e)}"

    def test_root_endpoint(self):
        """Test root API endpoint"""
        success, data = self.make_request('GET', '')
        self.log_test("Root API endpoint", success, "" if success else data, data)
        return success

    def test_courses_api(self):
        """Test courses CRUD operations"""
        print("\n🎯 Testing Courses API...")
        
        # GET courses
        success, data = self.make_request('GET', 'courses')
        self.log_test("GET /api/courses", success, "" if success else data, data)
        
        if success and isinstance(data, list):
            print(f"   Found {len(data)} courses")
            for course in data[:2]:  # Show first 2 courses
                print(f"   - {course.get('name', 'Unknown')} ({course.get('weekday', 'N/A')}, {course.get('time', 'N/A')})")
        
        # POST new course
        new_course = {
            "name": "Test Course",
            "weekday": 1,
            "time": "19:00",
            "locationName": "Test Location"
        }
        success, data = self.make_request('POST', 'courses', new_course, 200)
        if success and isinstance(data, dict):
            self.created_ids['courses'].append(data.get('id'))
        self.log_test("POST /api/courses", success, "" if success else data, data)
        
        return True

    def test_offers_api(self):
        """Test offers CRUD operations"""
        print("\n💰 Testing Offers API...")
        
        # GET offers
        success, data = self.make_request('GET', 'offers')
        self.log_test("GET /api/offers", success, "" if success else data, data)
        
        if success and isinstance(data, list):
            print(f"   Found {len(data)} offers")
            for offer in data[:3]:  # Show first 3 offers
                print(f"   - {offer.get('name', 'Unknown')}: CHF {offer.get('price', 'N/A')}")
        
        # POST new offer
        new_offer = {
            "name": "Test Offer",
            "price": 25.0,
            "visible": True
        }
        success, data = self.make_request('POST', 'offers', new_offer, 200)
        if success and isinstance(data, dict):
            self.created_ids['offers'].append(data.get('id'))
        self.log_test("POST /api/offers", success, "" if success else data, data)
        
        return True

    def test_users_api(self):
        """Test users CRUD operations"""
        print("\n👤 Testing Users API...")
        
        # GET users
        success, data = self.make_request('GET', 'users')
        self.log_test("GET /api/users", success, "" if success else data, data)
        
        if success and isinstance(data, list):
            print(f"   Found {len(data)} users")
        
        # POST new user
        new_user = {
            "name": "Test User",
            "email": f"test_{datetime.now().strftime('%H%M%S')}@test.com",
            "whatsapp": "+41791234567"
        }
        success, data = self.make_request('POST', 'users', new_user, 200)
        if success and isinstance(data, dict):
            self.created_ids['users'].append(data.get('id'))
        self.log_test("POST /api/users", success, "" if success else data, data)
        
        return True

    def test_reservations_api(self):
        """Test reservations CRUD operations"""
        print("\n📅 Testing Reservations API...")
        
        # GET reservations
        success, data = self.make_request('GET', 'reservations')
        self.log_test("GET /api/reservations", success, "" if success else data, data)
        
        if success and isinstance(data, list):
            print(f"   Found {len(data)} reservations")
        
        # POST new reservation (requires course and offer data)
        new_reservation = {
            "userId": "test-user-123",
            "userName": "Test User",
            "userEmail": "test@example.com",
            "userWhatsapp": "+41791234567",
            "courseId": "test-course-123",
            "courseName": "Test Course",
            "courseTime": "18:30",
            "datetime": datetime.now().isoformat(),
            "offerId": "test-offer-123",
            "offerName": "Test Offer",
            "price": 30.0,
            "quantity": 1,
            "totalPrice": 30.0
        }
        success, data = self.make_request('POST', 'reservations', new_reservation, 200)
        if success and isinstance(data, dict):
            self.created_ids['reservations'].append(data.get('id'))
            print(f"   Created reservation with code: {data.get('reservationCode', 'N/A')}")
        self.log_test("POST /api/reservations", success, "" if success else data, data)
        
        return True

    def test_discount_codes_api(self):
        """Test discount codes CRUD operations"""
        print("\n🎟️ Testing Discount Codes API...")
        
        # GET discount codes
        success, data = self.make_request('GET', 'discount-codes')
        self.log_test("GET /api/discount-codes", success, "" if success else data, data)
        
        if success and isinstance(data, list):
            print(f"   Found {len(data)} discount codes")
        
        # POST new discount code
        new_code = {
            "code": f"TEST{datetime.now().strftime('%H%M%S')}",
            "type": "%",
            "value": 10.0,
            "courses": [],
            "maxUses": None
        }
        success, data = self.make_request('POST', 'discount-codes', new_code, 200)
        if success and isinstance(data, dict):
            self.created_ids['discount_codes'].append(data.get('id'))
            print(f"   Created discount code: {data.get('code', 'N/A')}")
        self.log_test("POST /api/discount-codes", success, "" if success else data, data)
        
        # Test discount code validation
        if success and isinstance(data, dict):
            validation_data = {
                "code": data.get('code'),
                "email": "test@example.com",
                "courseId": "test-course-123"
            }
            success_val, val_data = self.make_request('POST', 'discount-codes/validate', validation_data, 200)
            self.log_test("POST /api/discount-codes/validate", success_val, "" if success_val else val_data, val_data)
        
        return True

    def test_payment_links_api(self):
        """Test payment links API"""
        print("\n💳 Testing Payment Links API...")
        
        # GET payment links
        success, data = self.make_request('GET', 'payment-links')
        self.log_test("GET /api/payment-links", success, "" if success else data, data)
        
        # PUT payment links
        update_data = {
            "stripe": "https://stripe.com/test",
            "twint": "https://twint.ch/test",
            "coachWhatsapp": "+41791234567"
        }
        success, data = self.make_request('PUT', 'payment-links', update_data, 200)
        self.log_test("PUT /api/payment-links", success, "" if success else data, data)
        
        return True

    def test_concept_api(self):
        """Test concept API"""
        print("\n💡 Testing Concept API...")
        
        # GET concept
        success, data = self.make_request('GET', 'concept')
        self.log_test("GET /api/concept", success, "" if success else data, data)
        
        if success and isinstance(data, dict):
            print(f"   Concept description: {data.get('description', 'N/A')[:50]}...")
        
        # PUT concept
        update_data = {
            "description": "Updated concept description for testing"
        }
        success, data = self.make_request('PUT', 'concept', update_data, 200)
        self.log_test("PUT /api/concept", success, "" if success else data, data)
        
        return True

    def test_config_api(self):
        """Test config API"""
        print("\n⚙️ Testing Config API...")
        
        # GET config
        success, data = self.make_request('GET', 'config')
        self.log_test("GET /api/config", success, "" if success else data, data)
        
        if success and isinstance(data, dict):
            print(f"   App title: {data.get('app_title', 'N/A')}")
            print(f"   Primary color: {data.get('primary_color', 'N/A')}")
        
        return True

    def test_coach_auth_api(self):
        """Test coach authentication API"""
        print("\n🔐 Testing Coach Auth API...")
        
        # GET coach auth info
        success, data = self.make_request('GET', 'coach-auth')
        self.log_test("GET /api/coach-auth", success, "" if success else data, data)
        
        # POST coach login (valid credentials)
        login_data = {
            "email": "coach@afroboost.com",
            "password": "afroboost123"
        }
        success, data = self.make_request('POST', 'coach-auth/login', login_data, 200)
        self.log_test("POST /api/coach-auth/login (valid)", success, "" if success else data, data)
        
        if success and isinstance(data, dict):
            print(f"   Login success: {data.get('success', False)}")
        
        # POST coach login (invalid credentials)
        invalid_login = {
            "email": "wrong@email.com",
            "password": "wrongpassword"
        }
        success, data = self.make_request('POST', 'coach-auth/login', invalid_login, 200)
        if success and isinstance(data, dict) and not data.get('success', True):
            self.log_test("POST /api/coach-auth/login (invalid)", True, "Correctly rejected invalid credentials", data)
        else:
            self.log_test("POST /api/coach-auth/login (invalid)", False, "Should have rejected invalid credentials", data)
        
        return True

    def cleanup_test_data(self):
        """Clean up test data created during testing"""
        print("\n🧹 Cleaning up test data...")
        
        # Delete created items
        for entity_type, ids in self.created_ids.items():
            for item_id in ids:
                if entity_type == 'discount_codes':
                    endpoint = f'discount-codes/{item_id}'
                else:
                    endpoint = f'{entity_type}/{item_id}'
                
                success, _ = self.make_request('DELETE', endpoint, expected_status=200)
                if success:
                    print(f"   Deleted {entity_type[:-1]} {item_id}")

    def run_all_tests(self):
        """Run all API tests"""
        print("🚀 Starting Afroboost Backend API Tests")
        print(f"🌐 Testing against: {self.base_url}")
        print("=" * 60)
        
        # Test all endpoints
        self.test_root_endpoint()
        self.test_courses_api()
        self.test_offers_api()
        self.test_users_api()
        self.test_reservations_api()
        self.test_discount_codes_api()
        self.test_payment_links_api()
        self.test_concept_api()
        self.test_config_api()
        self.test_coach_auth_api()
        
        # Cleanup
        self.cleanup_test_data()
        
        # Print summary
        print("\n" + "=" * 60)
        print(f"📊 Test Results: {self.tests_passed}/{self.tests_run} passed")
        
        if self.tests_passed == self.tests_run:
            print("🎉 All tests passed!")
            return 0
        else:
            print("⚠️ Some tests failed. Check the details above.")
            return 1

def main():
    """Main test runner"""
    tester = AfroboostAPITester()
    return tester.run_all_tests()

if __name__ == "__main__":
    sys.exit(main())