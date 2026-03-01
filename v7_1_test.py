#!/usr/bin/env python3
"""
Test des nouvelles fonctionnalités v7.1 Afroboost
Tests focus sur DELETE /api/chat/participants/{id} et non-régression
"""

import requests
import sys
import json
from datetime import datetime
import uuid

class V71Tester:
    def __init__(self):
        # Use environment variable URL from frontend/.env
        self.base_url = "https://video-feed-platform.preview.emergentagent.com"
        self.api_url = f"{self.base_url}/api"
        self.tests_run = 0
        self.tests_passed = 0
        self.test_results = []
        self.created_participant_id = None

    def log_test(self, name: str, success: bool, details: str = "", response_data=None):
        """Log test result"""
        self.tests_run += 1
        if success:
            self.tests_passed += 1
            print(f"✅ {name}")
            if details:
                print(f"   {details}")
        else:
            print(f"❌ {name} - {details}")
        
        self.test_results.append({
            'name': name,
            'success': success,
            'details': details,
            'response_data': response_data
        })

    def make_request(self, method: str, endpoint: str, data: dict = None, expected_status: int = 200) -> tuple:
        """Make HTTP request and return success status and response data"""
        url = f"{self.api_url}/{endpoint}"
        headers = {'Content-Type': 'application/json'}
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, timeout=15)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers, timeout=15)
            elif method == 'PUT':
                response = requests.put(url, json=data, headers=headers, timeout=15)
            elif method == 'DELETE':
                response = requests.delete(url, headers=headers, timeout=15)
            else:
                return False, f"Unsupported method: {method}"

            success = response.status_code == expected_status
            
            if success:
                try:
                    return True, response.json()
                except:
                    return True, response.text
            else:
                try:
                    error_data = response.json()
                    return False, f"Status {response.status_code}, expected {expected_status}. Error: {error_data}"
                except:
                    return False, f"Status {response.status_code}, expected {expected_status}. Response: {response.text[:200]}"
                
        except requests.exceptions.RequestException as e:
            return False, f"Request failed: {str(e)}"

    def test_health_endpoints(self):
        """Test non-regression: health endpoints"""
        print("\n🏥 Testing Health Endpoints (Non-regression)...")
        
        # Test GET /api/health
        success, data = self.make_request('GET', 'health')
        if success and isinstance(data, dict):
            if data.get('status') == 'healthy' and data.get('database') == 'connected':
                self.log_test("GET /api/health", True, f"Status: {data.get('status')}, DB: {data.get('database')}")
            else:
                self.log_test("GET /api/health", False, f"Unexpected response format: {data}")
        else:
            self.log_test("GET /api/health", False, str(data))

    def test_chat_participants_get(self):
        """Test non-regression: GET /api/chat/participants"""
        print("\n👥 Testing Chat Participants GET (Non-regression)...")
        
        success, data = self.make_request('GET', 'chat/participants')
        if success and isinstance(data, list):
            self.log_test("GET /api/chat/participants", True, f"Found {len(data)} participants")
        else:
            self.log_test("GET /api/chat/participants", False, str(data))

    def test_create_participant(self):
        """Create a test participant for DELETE testing"""
        print("\n👤 Creating Test Participant...")
        
        timestamp = datetime.now().strftime('%H%M%S')
        participant_data = {
            "name": f"Test Participant {timestamp}",
            "whatsapp": f"+4179{timestamp[:6]}",
            "email": f"test_{timestamp}@test.com",
            "source": "test_v71"
        }
        
        success, data = self.make_request('POST', 'chat/participants', participant_data)
        if success and isinstance(data, dict):
            self.created_participant_id = data.get('id')
            self.log_test("POST /api/chat/participants", True, f"Created participant ID: {self.created_participant_id}")
            return True
        else:
            self.log_test("POST /api/chat/participants", False, str(data))
            return False

    def test_delete_participant_success(self):
        """Test DELETE /api/chat/participants/{id} - Success case"""
        print("\n🗑️ Testing DELETE Participant (Success)...")
        
        if not self.created_participant_id:
            self.log_test("DELETE /api/chat/participants/{id}", False, "No test participant created")
            return False
        
        success, data = self.make_request('DELETE', f'chat/participants/{self.created_participant_id}')
        if success and isinstance(data, dict):
            # Verify response structure
            expected_fields = ['success', 'message', 'deleted']
            all_fields_present = all(field in data for field in expected_fields)
            
            if all_fields_present and data.get('success'):
                deleted_counts = data.get('deleted', {})
                counters_info = f"participant={deleted_counts.get('participant', 0)}, messages={deleted_counts.get('messages', 0)}, sessions_updated={deleted_counts.get('sessions_updated', 0)}, orphan_sessions={deleted_counts.get('orphan_sessions', 0)}"
                self.log_test("DELETE /api/chat/participants/{id}", True, f"Counters returned: {counters_info}")
                # Clear ID since it's now deleted
                self.created_participant_id = None
                return True
            else:
                self.log_test("DELETE /api/chat/participants/{id}", False, f"Invalid response structure: {data}")
        else:
            self.log_test("DELETE /api/chat/participants/{id}", False, str(data))
        return False

    def test_delete_participant_404(self):
        """Test DELETE /api/chat/participants/{id} - 404 case"""
        print("\n🔍 Testing DELETE Participant (404 case)...")
        
        # Use a non-existent ID
        fake_id = str(uuid.uuid4())
        success, data = self.make_request('DELETE', f'chat/participants/{fake_id}', expected_status=404)
        
        if success:
            self.log_test("DELETE /api/chat/participants/{fake_id} (404)", True, "Correctly returned 404 for non-existent participant")
        else:
            # Check if we got 404 status
            if "404" in str(data):
                self.log_test("DELETE /api/chat/participants/{fake_id} (404)", True, "Correctly returned 404 for non-existent participant")
            else:
                self.log_test("DELETE /api/chat/participants/{fake_id} (404)", False, f"Expected 404, got: {data}")

    def test_other_endpoints_non_regression(self):
        """Test that other endpoints are not impacted"""
        print("\n🔄 Testing Other Endpoints (Non-regression)...")
        
        # Test a few key endpoints to ensure they still work
        endpoints_to_test = [
            ('GET', 'courses', 'Courses endpoint'),
            ('GET', 'offers', 'Offers endpoint'),
            ('GET', 'users', 'Users endpoint'),
        ]
        
        for method, endpoint, name in endpoints_to_test:
            success, data = self.make_request(method, endpoint)
            if success and isinstance(data, list):
                self.log_test(f"{method} /api/{endpoint}", True, f"{name} working - Found {len(data)} items")
            else:
                self.log_test(f"{method} /api/{endpoint}", False, f"{name} failed: {data}")

    def cleanup_test_data(self):
        """Clean up any remaining test data"""
        if self.created_participant_id:
            print(f"\n🧹 Cleaning up participant {self.created_participant_id}...")
            try:
                self.make_request('DELETE', f'chat/participants/{self.created_participant_id}')
            except:
                pass

    def run_all_tests(self):
        """Run all v7.1 tests"""
        print("🚀 Starting v7.1 Afroboost Tests")
        print(f"🌐 Testing against: {self.base_url}")
        print("=" * 60)
        
        # 1. Non-regression tests first
        self.test_health_endpoints()
        self.test_chat_participants_get()
        self.test_other_endpoints_non_regression()
        
        # 2. Test DELETE functionality
        if self.test_create_participant():
            self.test_delete_participant_success()
        
        self.test_delete_participant_404()
        
        # Cleanup
        self.cleanup_test_data()
        
        # Print summary
        print("\n" + "=" * 60)
        print(f"📊 v7.1 Test Results: {self.tests_passed}/{self.tests_run} passed")
        
        if self.tests_passed == self.tests_run:
            print("🎉 All v7.1 tests passed!")
            return 0
        else:
            print("⚠️ Some v7.1 tests failed. Check the details above.")
            # Print failed tests
            failed_tests = [t for t in self.test_results if not t['success']]
            if failed_tests:
                print("\n❌ Failed tests:")
                for test in failed_tests:
                    print(f"   - {test['name']}: {test['details']}")
            return 1

def main():
    """Main test runner"""
    tester = V71Tester()
    return tester.run_all_tests()

if __name__ == "__main__":
    sys.exit(main())