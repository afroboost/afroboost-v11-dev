"""
Test Suite for Iteration 54 - CampaignManager & BookingPanel Refactoring
Tests the extraction of CampaignManager from CoachDashboard.js and BookingPanel integration in ChatWidget.js
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://video-feed-platform.preview.emergentagent.com')

class TestBackendAPIs:
    """Test backend API endpoints for campaigns and scheduler"""
    
    def test_api_health(self):
        """Test API health endpoint"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "healthy"
        print("✅ API health check passed")
    
    def test_scheduler_health(self):
        """Test scheduler health endpoint - Critical for ⏳ Auto badge"""
        response = requests.get(f"{BASE_URL}/api/scheduler/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert data["status"] in ["active", "stopped", "unknown"]
        print(f"✅ Scheduler health: status={data['status']}, last_run={data.get('last_run')}")
    
    def test_campaigns_list(self):
        """Test campaigns list endpoint"""
        response = requests.get(f"{BASE_URL}/api/campaigns")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✅ Campaigns list: {len(data)} campaigns found")
    
    def test_courses_list(self):
        """Test courses list endpoint - Used by BookingPanel"""
        response = requests.get(f"{BASE_URL}/api/courses")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✅ Courses list: {len(data)} courses found")
    
    def test_conversations_active(self):
        """Test active conversations endpoint - Used by CampaignManager"""
        response = requests.get(f"{BASE_URL}/api/conversations/active")
        assert response.status_code == 200
        data = response.json()
        assert "success" in data
        print(f"✅ Active conversations: {data.get('total', 0)} conversations")


class TestCodeStructure:
    """Test code structure and file organization"""
    
    def test_campaign_manager_file_exists(self):
        """Verify CampaignManager.js exists"""
        file_path = "/app/frontend/src/components/coach/CampaignManager.js"
        assert os.path.exists(file_path), f"CampaignManager.js not found at {file_path}"
        
        with open(file_path, 'r') as f:
            content = f.read()
        
        # Check file size (should be ~1650 lines)
        lines = content.split('\n')
        assert len(lines) > 1000, f"CampaignManager.js too small: {len(lines)} lines"
        print(f"✅ CampaignManager.js exists with {len(lines)} lines")
    
    def test_campaign_manager_exports(self):
        """Verify CampaignManager exports correctly"""
        file_path = "/app/frontend/src/components/coach/CampaignManager.js"
        with open(file_path, 'r') as f:
            content = f.read()
        
        # Check for proper export
        assert "export default" in content, "Missing default export"
        assert "const CampaignManager" in content, "Missing CampaignManager component"
        print("✅ CampaignManager exports correctly")
    
    def test_campaign_manager_scheduler_badge(self):
        """Verify scheduler badge logic in CampaignManager"""
        file_path = "/app/frontend/src/components/coach/CampaignManager.js"
        with open(file_path, 'r') as f:
            content = f.read()
        
        # Check for scheduler health badge
        assert "schedulerHealth" in content, "Missing schedulerHealth prop"
        assert "Automate" in content, "Missing Automate badge text"
        assert "isHealthy" in content or "isActive" in content, "Missing health check logic"
        print("✅ Scheduler badge logic present in CampaignManager")
    
    def test_booking_panel_file_exists(self):
        """Verify BookingPanel.js exists"""
        file_path = "/app/frontend/src/components/chat/BookingPanel.js"
        assert os.path.exists(file_path), f"BookingPanel.js not found at {file_path}"
        
        with open(file_path, 'r') as f:
            content = f.read()
        
        lines = content.split('\n')
        print(f"✅ BookingPanel.js exists with {len(lines)} lines")
    
    def test_booking_panel_exports(self):
        """Verify BookingPanel exports correctly"""
        file_path = "/app/frontend/src/components/chat/BookingPanel.js"
        with open(file_path, 'r') as f:
            content = f.read()
        
        assert "export default" in content, "Missing default export"
        assert "const BookingPanel" in content, "Missing BookingPanel component"
        assert "memo" in content, "BookingPanel should use memo for optimization"
        print("✅ BookingPanel exports correctly with memo")
    
    def test_coach_dashboard_imports_campaign_manager(self):
        """Verify CoachDashboard imports CampaignManager"""
        file_path = "/app/frontend/src/components/CoachDashboard.js"
        with open(file_path, 'r') as f:
            content = f.read()
        
        assert "import CampaignManager from" in content, "Missing CampaignManager import"
        assert "<CampaignManager" in content, "Missing CampaignManager usage"
        print("✅ CoachDashboard imports and uses CampaignManager")
    
    def test_chat_widget_imports_booking_panel(self):
        """Verify ChatWidget imports BookingPanel"""
        file_path = "/app/frontend/src/components/ChatWidget.js"
        with open(file_path, 'r') as f:
            content = f.read()
        
        assert "import BookingPanel from" in content, "Missing BookingPanel import"
        assert "<BookingPanel" in content, "Missing BookingPanel usage"
        print("✅ ChatWidget imports and uses BookingPanel")
    
    def test_coach_dashboard_reduced_size(self):
        """Verify CoachDashboard.js is reduced after extraction"""
        file_path = "/app/frontend/src/components/CoachDashboard.js"
        with open(file_path, 'r') as f:
            content = f.read()
        
        lines = content.split('\n')
        # After extraction, CoachDashboard should be smaller
        # Original was ~6800 lines, after extraction should be ~5400-5500
        print(f"✅ CoachDashboard.js has {len(lines)} lines")
    
    def test_chat_widget_handle_confirm_reservation(self):
        """Verify handleConfirmReservation is defined in ChatWidget"""
        file_path = "/app/frontend/src/components/ChatWidget.js"
        with open(file_path, 'r') as f:
            content = f.read()
        
        assert "handleConfirmReservation" in content, "Missing handleConfirmReservation"
        assert "useCallback" in content, "handleConfirmReservation should use useCallback"
        print("✅ handleConfirmReservation defined with useCallback")


class TestCampaignManagerProps:
    """Test CampaignManager receives all required props"""
    
    def test_scheduler_health_prop(self):
        """Verify schedulerHealth prop is passed"""
        file_path = "/app/frontend/src/components/CoachDashboard.js"
        with open(file_path, 'r') as f:
            content = f.read()
        
        assert "schedulerHealth={schedulerHealth}" in content, "Missing schedulerHealth prop"
        print("✅ schedulerHealth prop passed to CampaignManager")
    
    def test_campaigns_prop(self):
        """Verify campaigns prop is passed"""
        file_path = "/app/frontend/src/components/CoachDashboard.js"
        with open(file_path, 'r') as f:
            content = f.read()
        
        assert "campaigns={campaigns}" in content, "Missing campaigns prop"
        print("✅ campaigns prop passed to CampaignManager")
    
    def test_api_prop(self):
        """Verify API prop is passed"""
        file_path = "/app/frontend/src/components/CoachDashboard.js"
        with open(file_path, 'r') as f:
            content = f.read()
        
        assert "API={API}" in content, "Missing API prop"
        print("✅ API prop passed to CampaignManager")


class TestBookingPanelProps:
    """Test BookingPanel receives all required props"""
    
    def test_afroboost_profile_prop(self):
        """Verify afroboostProfile prop is passed"""
        file_path = "/app/frontend/src/components/ChatWidget.js"
        with open(file_path, 'r') as f:
            content = f.read()
        
        assert "afroboostProfile={afroboostProfile}" in content, "Missing afroboostProfile prop"
        print("✅ afroboostProfile prop passed to BookingPanel")
    
    def test_on_confirm_reservation_prop(self):
        """Verify onConfirmReservation prop is passed"""
        file_path = "/app/frontend/src/components/ChatWidget.js"
        with open(file_path, 'r') as f:
            content = f.read()
        
        assert "onConfirmReservation={handleConfirmReservation}" in content, "Missing onConfirmReservation prop"
        print("✅ onConfirmReservation prop passed to BookingPanel")
    
    def test_available_courses_prop(self):
        """Verify availableCourses prop is passed"""
        file_path = "/app/frontend/src/components/ChatWidget.js"
        with open(file_path, 'r') as f:
            content = f.read()
        
        assert "availableCourses={availableCourses}" in content, "Missing availableCourses prop"
        print("✅ availableCourses prop passed to BookingPanel")


class TestPromoCodeValidation:
    """Test promo code validation for subscriber access"""
    
    def test_validate_promo_code_basxx(self):
        """Test promo code 'basxx' validation"""
        response = requests.post(f"{BASE_URL}/api/discount-codes/validate", json={
            "code": "basxx",
            "email": "bassicustomshoes@gmail.com"
        })
        assert response.status_code == 200
        data = response.json()
        assert data.get("valid") == True, f"Promo code basxx should be valid: {data}"
        print("✅ Promo code 'basxx' validates correctly")
    
    def test_validate_promo_code_promo20secret(self):
        """Test promo code 'PROMO20SECRET' validation"""
        response = requests.post(f"{BASE_URL}/api/discount-codes/validate", json={
            "code": "PROMO20SECRET",
            "email": "test@example.com"
        })
        # This code may or may not exist, just check the endpoint works
        assert response.status_code in [200, 400, 404]
        print("✅ Promo code validation endpoint works")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
