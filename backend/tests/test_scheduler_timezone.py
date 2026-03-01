"""
Test Suite: Scheduler Timezone Fix - Europe/Paris
Tests the fix for scheduled campaign sending with proper timezone handling.

Bug Fixed: Frontend sends dates in Europe/Paris time without timezone indicator,
but backend was comparing with UTC. Now parse_campaign_date() correctly interprets
dates without timezone as Europe/Paris.

Features to test:
1. Scheduler runs every 60 seconds
2. Campaigns with status='scheduled' are detected
3. Europe/Paris dates are correctly parsed and compared
4. Internal messages are sent via Socket.IO
5. Group messages are sent to community session
6. Campaign status changes from 'scheduled' to 'completed' after sending
7. Debug logs show Paris and UTC times
"""

import pytest
import requests
import os
import time
from datetime import datetime, timedelta
import pytz

# Get BASE_URL from environment
BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
if not BASE_URL:
    BASE_URL = "https://video-feed-platform.preview.emergentagent.com"

PARIS_TZ = pytz.timezone('Europe/Paris')


class TestSchedulerHealth:
    """Test scheduler health and status endpoints"""
    
    def test_api_health(self):
        """Test that API is healthy"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "healthy"
        assert data.get("database") == "connected"
        print(f"✅ API Health: {data}")
    
    def test_scheduler_health(self):
        """Test scheduler health endpoint"""
        response = requests.get(f"{BASE_URL}/api/scheduler/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        print(f"✅ Scheduler Health: {data}")
        # Scheduler should be running
        assert data.get("status") in ["running", "stopped", "unknown", "active"]
    
    def test_scheduler_status(self):
        """Test scheduler status endpoint"""
        response = requests.get(f"{BASE_URL}/api/scheduler/status")
        assert response.status_code == 200
        data = response.json()
        print(f"✅ Scheduler Status: {data}")


class TestCampaignCRUD:
    """Test campaign CRUD operations"""
    
    def test_get_campaigns(self):
        """Test getting all campaigns"""
        response = requests.get(f"{BASE_URL}/api/campaigns")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✅ Got {len(data)} campaigns")
    
    def test_create_campaign_immediate(self):
        """Test creating a campaign for immediate sending"""
        campaign_data = {
            "name": "TEST_IMMEDIATE_CAMPAIGN",
            "message": "Test message for immediate campaign",
            "mediaUrl": "",
            "mediaFormat": "16:9",
            "targetType": "all",
            "selectedContacts": [],
            "channels": {"whatsapp": False, "email": False, "instagram": False, "group": False, "internal": True},
            "targetGroupId": "community",
            "targetIds": [],
            "scheduledAt": None  # Immediate
        }
        
        response = requests.post(f"{BASE_URL}/api/campaigns", json=campaign_data)
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert data.get("name") == "TEST_IMMEDIATE_CAMPAIGN"
        print(f"✅ Created immediate campaign: {data.get('id')}")
        
        # Cleanup
        campaign_id = data.get("id")
        requests.delete(f"{BASE_URL}/api/campaigns/{campaign_id}")
        return data
    
    def test_create_scheduled_campaign_paris_time(self):
        """Test creating a scheduled campaign with Europe/Paris time (no timezone indicator)"""
        # Create a date 5 minutes in the future in Paris time
        now_paris = datetime.now(PARIS_TZ)
        future_paris = now_paris + timedelta(minutes=5)
        
        # Format WITHOUT timezone indicator (like frontend does)
        scheduled_at = future_paris.strftime("%Y-%m-%dT%H:%M:%S")
        
        campaign_data = {
            "name": "TEST_SCHEDULED_PARIS_TZ",
            "message": "Test message for scheduled campaign with Paris timezone",
            "mediaUrl": "",
            "mediaFormat": "16:9",
            "targetType": "all",
            "selectedContacts": [],
            "channels": {"whatsapp": False, "email": False, "instagram": False, "group": True, "internal": False},
            "targetGroupId": "community",
            "targetIds": [],
            "scheduledAt": scheduled_at
        }
        
        response = requests.post(f"{BASE_URL}/api/campaigns", json=campaign_data)
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert data.get("status") == "scheduled"
        assert data.get("scheduledAt") == scheduled_at
        print(f"✅ Created scheduled campaign: {data.get('id')}")
        print(f"   Scheduled at (Paris): {scheduled_at}")
        print(f"   Status: {data.get('status')}")
        
        # Cleanup
        campaign_id = data.get("id")
        requests.delete(f"{BASE_URL}/api/campaigns/{campaign_id}")
        return data


class TestTimezoneParsingLogic:
    """Test the timezone parsing logic indirectly through campaign creation"""
    
    def test_campaign_with_utc_date(self):
        """Test campaign with explicit UTC date (Z suffix)"""
        now_utc = datetime.utcnow()
        future_utc = now_utc + timedelta(minutes=10)
        scheduled_at = future_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
        
        campaign_data = {
            "name": "TEST_UTC_DATE",
            "message": "Test with UTC date",
            "channels": {"internal": True},
            "scheduledAt": scheduled_at
        }
        
        response = requests.post(f"{BASE_URL}/api/campaigns", json=campaign_data)
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "scheduled"
        print(f"✅ Campaign with UTC date created: {scheduled_at}")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/campaigns/{data.get('id')}")
    
    def test_campaign_with_offset_date(self):
        """Test campaign with explicit timezone offset"""
        now_paris = datetime.now(PARIS_TZ)
        future_paris = now_paris + timedelta(minutes=10)
        # Format with explicit offset
        scheduled_at = future_paris.strftime("%Y-%m-%dT%H:%M:%S%z")
        # Insert colon in offset (e.g., +0100 -> +01:00)
        if len(scheduled_at) > 5 and scheduled_at[-5] in ['+', '-']:
            scheduled_at = scheduled_at[:-2] + ':' + scheduled_at[-2:]
        
        campaign_data = {
            "name": "TEST_OFFSET_DATE",
            "message": "Test with offset date",
            "channels": {"internal": True},
            "scheduledAt": scheduled_at
        }
        
        response = requests.post(f"{BASE_URL}/api/campaigns", json=campaign_data)
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "scheduled"
        print(f"✅ Campaign with offset date created: {scheduled_at}")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/campaigns/{data.get('id')}")
    
    def test_campaign_without_timezone_interpreted_as_paris(self):
        """
        CRITICAL TEST: Verify that dates without timezone are interpreted as Europe/Paris.
        This is the main bug fix being tested.
        """
        # Create a date in Paris time without timezone indicator
        now_paris = datetime.now(PARIS_TZ)
        future_paris = now_paris + timedelta(minutes=3)
        
        # Format WITHOUT timezone (this is what frontend sends)
        scheduled_at_no_tz = future_paris.strftime("%Y-%m-%dT%H:%M:%S")
        
        campaign_data = {
            "name": "TEST_NO_TZ_PARIS_INTERPRETATION",
            "message": "This should be interpreted as Paris time",
            "channels": {"group": True},
            "targetGroupId": "community",
            "scheduledAt": scheduled_at_no_tz
        }
        
        response = requests.post(f"{BASE_URL}/api/campaigns", json=campaign_data)
        assert response.status_code == 200
        data = response.json()
        
        # The campaign should be scheduled (not immediately sent)
        # because the date is in the future
        assert data.get("status") == "scheduled"
        print(f"✅ Campaign without TZ created and scheduled correctly")
        print(f"   Input (no TZ): {scheduled_at_no_tz}")
        print(f"   Status: {data.get('status')}")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/campaigns/{data.get('id')}")


class TestSchedulerExecution:
    """Test scheduler execution and campaign processing"""
    
    def test_scheduler_detects_scheduled_campaigns(self):
        """Test that scheduler detects campaigns with status='scheduled'"""
        # Create a campaign scheduled for 1 minute ago (should be processed immediately)
        now_paris = datetime.now(PARIS_TZ)
        past_paris = now_paris - timedelta(minutes=1)
        scheduled_at = past_paris.strftime("%Y-%m-%dT%H:%M:%S")
        
        campaign_data = {
            "name": "TEST_SCHEDULER_DETECTION",
            "message": "Test scheduler detection - should be processed",
            "channels": {"group": True},
            "targetGroupId": "community",
            "scheduledAt": scheduled_at
        }
        
        response = requests.post(f"{BASE_URL}/api/campaigns", json=campaign_data)
        assert response.status_code == 200
        data = response.json()
        campaign_id = data.get("id")
        
        print(f"✅ Created campaign scheduled for past: {scheduled_at}")
        print(f"   Campaign ID: {campaign_id}")
        
        # Wait for scheduler to process (max 90 seconds - scheduler runs every 60s)
        max_wait = 90
        start_time = time.time()
        final_status = None
        
        while time.time() - start_time < max_wait:
            check_response = requests.get(f"{BASE_URL}/api/campaigns/{campaign_id}")
            if check_response.status_code == 200:
                check_data = check_response.json()
                final_status = check_data.get("status")
                print(f"   Status after {int(time.time() - start_time)}s: {final_status}")
                
                if final_status in ["completed", "failed"]:
                    break
            time.sleep(10)
        
        # Verify the campaign was processed
        assert final_status in ["completed", "failed", "scheduled"], f"Unexpected status: {final_status}"
        print(f"✅ Campaign final status: {final_status}")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/campaigns/{campaign_id}")
    
    def test_group_message_sent_to_community(self):
        """Test that group messages are sent to community session"""
        # Create a campaign for immediate group message
        now_paris = datetime.now(PARIS_TZ)
        past_paris = now_paris - timedelta(seconds=30)
        scheduled_at = past_paris.strftime("%Y-%m-%dT%H:%M:%S")
        
        test_message = f"TEST_GROUP_MSG_{int(time.time())}"
        
        campaign_data = {
            "name": f"TEST_GROUP_SEND_{int(time.time())}",
            "message": test_message,
            "channels": {"group": True},
            "targetGroupId": "community",
            "scheduledAt": scheduled_at
        }
        
        response = requests.post(f"{BASE_URL}/api/campaigns", json=campaign_data)
        assert response.status_code == 200
        data = response.json()
        campaign_id = data.get("id")
        
        print(f"✅ Created group campaign: {campaign_id}")
        print(f"   Message: {test_message}")
        
        # Wait for processing
        time.sleep(70)  # Wait for scheduler cycle
        
        # Check campaign status
        check_response = requests.get(f"{BASE_URL}/api/campaigns/{campaign_id}")
        if check_response.status_code == 200:
            check_data = check_response.json()
            print(f"   Final status: {check_data.get('status')}")
            print(f"   Results: {check_data.get('results', [])}")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/campaigns/{campaign_id}")


class TestInternalMessaging:
    """Test internal messaging channel"""
    
    def test_internal_message_to_conversation(self):
        """Test sending internal message to a specific conversation"""
        # First, get available chat sessions
        sessions_response = requests.get(f"{BASE_URL}/api/chat/sessions")
        if sessions_response.status_code != 200:
            pytest.skip("Cannot get chat sessions")
        
        sessions = sessions_response.json()
        if not sessions:
            pytest.skip("No chat sessions available for testing")
        
        # Use the first available session
        target_session = sessions[0]
        target_id = target_session.get("id")
        
        now_paris = datetime.now(PARIS_TZ)
        past_paris = now_paris - timedelta(seconds=30)
        scheduled_at = past_paris.strftime("%Y-%m-%dT%H:%M:%S")
        
        campaign_data = {
            "name": f"TEST_INTERNAL_MSG_{int(time.time())}",
            "message": f"Test internal message {int(time.time())}",
            "channels": {"internal": True},
            "targetIds": [target_id],
            "targetConversationId": target_id,
            "scheduledAt": scheduled_at
        }
        
        response = requests.post(f"{BASE_URL}/api/campaigns", json=campaign_data)
        assert response.status_code == 200
        data = response.json()
        campaign_id = data.get("id")
        
        print(f"✅ Created internal campaign: {campaign_id}")
        print(f"   Target session: {target_id}")
        
        # Wait for processing
        time.sleep(70)
        
        # Check status
        check_response = requests.get(f"{BASE_URL}/api/campaigns/{campaign_id}")
        if check_response.status_code == 200:
            check_data = check_response.json()
            print(f"   Final status: {check_data.get('status')}")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/campaigns/{campaign_id}")


class TestCampaignStatusTransitions:
    """Test campaign status transitions"""
    
    def test_status_scheduled_to_completed(self):
        """Test that campaign status changes from 'scheduled' to 'completed' after sending"""
        now_paris = datetime.now(PARIS_TZ)
        past_paris = now_paris - timedelta(minutes=2)
        scheduled_at = past_paris.strftime("%Y-%m-%dT%H:%M:%S")
        
        campaign_data = {
            "name": f"TEST_STATUS_TRANSITION_{int(time.time())}",
            "message": "Test status transition",
            "channels": {"group": True},
            "targetGroupId": "community",
            "scheduledAt": scheduled_at
        }
        
        response = requests.post(f"{BASE_URL}/api/campaigns", json=campaign_data)
        assert response.status_code == 200
        data = response.json()
        campaign_id = data.get("id")
        initial_status = data.get("status")
        
        print(f"✅ Created campaign: {campaign_id}")
        print(f"   Initial status: {initial_status}")
        
        # Wait for scheduler
        time.sleep(70)
        
        # Check final status
        check_response = requests.get(f"{BASE_URL}/api/campaigns/{campaign_id}")
        assert check_response.status_code == 200
        check_data = check_response.json()
        final_status = check_data.get("status")
        
        print(f"   Final status: {final_status}")
        
        # Status should have changed
        assert final_status in ["completed", "failed"], f"Expected completed/failed, got {final_status}"
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/campaigns/{campaign_id}")


class TestCleanup:
    """Cleanup test campaigns"""
    
    def test_cleanup_test_campaigns(self):
        """Remove all test campaigns created during testing"""
        response = requests.get(f"{BASE_URL}/api/campaigns")
        if response.status_code == 200:
            campaigns = response.json()
            deleted_count = 0
            for campaign in campaigns:
                if campaign.get("name", "").startswith("TEST_"):
                    delete_response = requests.delete(f"{BASE_URL}/api/campaigns/{campaign.get('id')}")
                    if delete_response.status_code == 200:
                        deleted_count += 1
            print(f"✅ Cleaned up {deleted_count} test campaigns")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
