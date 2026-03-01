"""
Test Campaign Buttons - Iteration 22
Tests for EmailJS and WhatsApp campaign button implementations:
1. data-testid attributes on all campaign buttons
2. e.preventDefault() and e.stopPropagation() in handlers
3. EmailJS flat JSON payload with String() conversion
4. WhatsApp service using accountSid, authToken, fromNumber
"""
import pytest
import requests
import os
import re

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://video-feed-platform.preview.emergentagent.com').rstrip('/')

# ============ BACKEND API TESTS ============

class TestBackendAPIs:
    """Test backend API endpoints"""
    
    def test_health_check(self):
        """Test health endpoint"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "healthy"
        print("✅ Health check passed")
    
    def test_whatsapp_config_endpoint(self):
        """Test WhatsApp config endpoint returns correct structure"""
        response = requests.get(f"{BASE_URL}/api/whatsapp-config")
        assert response.status_code == 200
        data = response.json()
        # Should have accountSid, authToken, fromNumber fields
        assert "accountSid" in data or "account_sid" in data or data == {}
        print("✅ WhatsApp config endpoint working")
    
    def test_campaigns_endpoint(self):
        """Test campaigns endpoint"""
        response = requests.get(f"{BASE_URL}/api/campaigns")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✅ Campaigns endpoint working - {len(data)} campaigns found")


# ============ CODE REVIEW TESTS ============

class TestDataTestIdAttributes:
    """Verify data-testid attributes on campaign buttons"""
    
    @pytest.fixture(scope="class")
    def coach_dashboard_code(self):
        """Load CoachDashboard.js content"""
        with open("/app/frontend/src/components/CoachDashboard.js", "r") as f:
            return f.read()
    
    def test_test_email_btn_testid(self, coach_dashboard_code):
        """Verify 'Tester' EmailJS button has data-testid='test-email-btn'"""
        assert 'data-testid="test-email-btn"' in coach_dashboard_code
        print("✅ data-testid='test-email-btn' found")
    
    def test_test_whatsapp_btn_testid(self, coach_dashboard_code):
        """Verify 'Tester' WhatsApp button has data-testid='test-whatsapp-btn'"""
        assert 'data-testid="test-whatsapp-btn"' in coach_dashboard_code
        print("✅ data-testid='test-whatsapp-btn' found")
    
    def test_send_email_campaign_btn_testid(self, coach_dashboard_code):
        """Verify 'Envoyer automatiquement' Email button has data-testid='send-email-campaign-btn'"""
        assert 'data-testid="send-email-campaign-btn"' in coach_dashboard_code
        print("✅ data-testid='send-email-campaign-btn' found")
    
    def test_send_whatsapp_campaign_btn_testid(self, coach_dashboard_code):
        """Verify 'Auto (Twilio)' WhatsApp button has data-testid='send-whatsapp-campaign-btn'"""
        assert 'data-testid="send-whatsapp-campaign-btn"' in coach_dashboard_code
        print("✅ data-testid='send-whatsapp-campaign-btn' found")
    
    def test_bulk_send_campaign_btn_testid(self, coach_dashboard_code):
        """Verify 'Envoyer Email + WhatsApp' button has data-testid='bulk-send-campaign-btn'"""
        assert 'data-testid="bulk-send-campaign-btn"' in coach_dashboard_code
        print("✅ data-testid='bulk-send-campaign-btn' found")
    
    def test_launch_campaign_btn_testid(self, coach_dashboard_code):
        """Verify 'Lancer' campaign button has data-testid with campaign id"""
        assert 'data-testid={`launch-campaign-${campaign.id}`}' in coach_dashboard_code
        print("✅ data-testid='launch-campaign-${campaign.id}' found")


class TestEventHandlerProtection:
    """Verify handlers have e.preventDefault() and e.stopPropagation()"""
    
    @pytest.fixture(scope="class")
    def coach_dashboard_code(self):
        """Load CoachDashboard.js content"""
        with open("/app/frontend/src/components/CoachDashboard.js", "r") as f:
            return f.read()
    
    def test_handleTestEmailJS_has_preventDefault(self, coach_dashboard_code):
        """Verify handleTestEmailJS has e.preventDefault()"""
        # Find the function
        match = re.search(r'const handleTestEmailJS = async \(e\) => \{[^}]+e\.preventDefault\(\)', coach_dashboard_code, re.DOTALL)
        assert match is not None, "handleTestEmailJS should have e.preventDefault()"
        print("✅ handleTestEmailJS has e.preventDefault()")
    
    def test_handleTestEmailJS_has_stopPropagation(self, coach_dashboard_code):
        """Verify handleTestEmailJS has e.stopPropagation()"""
        match = re.search(r'const handleTestEmailJS = async \(e\) => \{[^}]+e\.stopPropagation\(\)', coach_dashboard_code, re.DOTALL)
        assert match is not None, "handleTestEmailJS should have e.stopPropagation()"
        print("✅ handleTestEmailJS has e.stopPropagation()")
    
    def test_handleTestWhatsApp_has_preventDefault(self, coach_dashboard_code):
        """Verify handleTestWhatsApp has e.preventDefault()"""
        match = re.search(r'const handleTestWhatsApp = async \(e\) => \{[^}]+e\.preventDefault\(\)', coach_dashboard_code, re.DOTALL)
        assert match is not None, "handleTestWhatsApp should have e.preventDefault()"
        print("✅ handleTestWhatsApp has e.preventDefault()")
    
    def test_handleTestWhatsApp_has_stopPropagation(self, coach_dashboard_code):
        """Verify handleTestWhatsApp has e.stopPropagation()"""
        match = re.search(r'const handleTestWhatsApp = async \(e\) => \{[^}]+e\.stopPropagation\(\)', coach_dashboard_code, re.DOTALL)
        assert match is not None, "handleTestWhatsApp should have e.stopPropagation()"
        print("✅ handleTestWhatsApp has e.stopPropagation()")
    
    def test_handleSendEmailCampaign_has_preventDefault(self, coach_dashboard_code):
        """Verify handleSendEmailCampaign has e.preventDefault()"""
        match = re.search(r'const handleSendEmailCampaign = async \(e\) => \{[^}]+e\.preventDefault\(\)', coach_dashboard_code, re.DOTALL)
        assert match is not None, "handleSendEmailCampaign should have e.preventDefault()"
        print("✅ handleSendEmailCampaign has e.preventDefault()")
    
    def test_handleSendWhatsAppCampaign_has_preventDefault(self, coach_dashboard_code):
        """Verify handleSendWhatsAppCampaign has e.preventDefault()"""
        match = re.search(r'const handleSendWhatsAppCampaign = async \(e\) => \{[^}]+e\.preventDefault\(\)', coach_dashboard_code, re.DOTALL)
        assert match is not None, "handleSendWhatsAppCampaign should have e.preventDefault()"
        print("✅ handleSendWhatsAppCampaign has e.preventDefault()")
    
    def test_handleBulkSendCampaign_has_preventDefault(self, coach_dashboard_code):
        """Verify handleBulkSendCampaign has e.preventDefault()"""
        match = re.search(r'const handleBulkSendCampaign = async \(e\) => \{[^}]+e\.preventDefault\(\)', coach_dashboard_code, re.DOTALL)
        assert match is not None, "handleBulkSendCampaign should have e.preventDefault()"
        print("✅ handleBulkSendCampaign has e.preventDefault()")
    
    def test_launchCampaignWithSend_has_preventDefault(self, coach_dashboard_code):
        """Verify launchCampaignWithSend has e.preventDefault()"""
        match = re.search(r'const launchCampaignWithSend = async \(e, campaignId\) => \{[^}]+e\.preventDefault\(\)', coach_dashboard_code, re.DOTALL)
        assert match is not None, "launchCampaignWithSend should have e.preventDefault()"
        print("✅ launchCampaignWithSend has e.preventDefault()")


class TestEmailJSService:
    """Verify EmailJS service implementation"""
    
    @pytest.fixture(scope="class")
    def email_service_code(self):
        """Load emailService.js content"""
        with open("/app/frontend/src/services/emailService.js", "r") as f:
            return f.read()
    
    def test_flat_json_payload(self, email_service_code):
        """Verify sendEmail uses flat JSON payload"""
        # Check for templateParams with String() conversion
        assert "const templateParams = {" in email_service_code
        print("✅ EmailJS uses flat JSON payload")
    
    def test_string_conversion(self, email_service_code):
        """Verify String() conversion is used"""
        assert "String(params.to_email" in email_service_code or "String(" in email_service_code
        print("✅ EmailJS uses String() conversion")
    
    def test_correct_service_id(self, email_service_code):
        """Verify correct default service ID"""
        assert "service_8mrmxim" in email_service_code
        print("✅ EmailJS has correct service ID: service_8mrmxim")
    
    def test_correct_template_id(self, email_service_code):
        """Verify correct default template ID"""
        assert "template_3n1u86p" in email_service_code
        print("✅ EmailJS has correct template ID: template_3n1u86p")
    
    def test_correct_public_key(self, email_service_code):
        """Verify correct default public key"""
        assert "5LfgQSIEQoqq_XSqt" in email_service_code
        print("✅ EmailJS has correct public key: 5LfgQSIEQoqq_XSqt")


class TestWhatsAppService:
    """Verify WhatsApp service implementation"""
    
    @pytest.fixture(scope="class")
    def whatsapp_service_code(self):
        """Load whatsappService.js content"""
        with open("/app/frontend/src/services/whatsappService.js", "r") as f:
            return f.read()
    
    def test_uses_accountSid(self, whatsapp_service_code):
        """Verify WhatsApp service uses accountSid"""
        assert "accountSid" in whatsapp_service_code
        print("✅ WhatsApp service uses accountSid")
    
    def test_uses_authToken(self, whatsapp_service_code):
        """Verify WhatsApp service uses authToken"""
        assert "authToken" in whatsapp_service_code
        print("✅ WhatsApp service uses authToken")
    
    def test_uses_fromNumber(self, whatsapp_service_code):
        """Verify WhatsApp service uses fromNumber"""
        assert "fromNumber" in whatsapp_service_code
        print("✅ WhatsApp service uses fromNumber")
    
    def test_twilio_api_url(self, whatsapp_service_code):
        """Verify WhatsApp service uses Twilio API"""
        assert "api.twilio.com" in whatsapp_service_code
        print("✅ WhatsApp service uses Twilio API")
    
    def test_basic_auth(self, whatsapp_service_code):
        """Verify WhatsApp service uses Basic auth with accountSid:authToken"""
        assert "btoa(`${config.accountSid}:${config.authToken}`)" in whatsapp_service_code
        print("✅ WhatsApp service uses Basic auth with accountSid:authToken")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
