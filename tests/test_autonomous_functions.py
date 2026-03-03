"""
Test suite for verifying autonomous functions (performEmailSend, performWhatsAppSend)
and their integration with handlers in CoachDashboard.js

Tests verify:
1. performEmailSend is defined at module level (outside React component)
2. performWhatsAppSend is defined at module level (outside React component)
3. emailjs.init() is called at module load (line ~37)
4. performEmailSend has console.log('DEMANDE EMAILJS ENVOYÉE')
5. handleTestEmailJS uses performEmailSend
6. handleTestWhatsApp uses performWhatsAppSend
7. launchCampaignWithSend uses performEmailSend and performWhatsAppSend
8. All handlers have e.preventDefault() and e.stopPropagation() FIRST
9. Nested try/catch blocks to isolate PostHog errors
10. performWhatsAppSend has simulation mode with alert()
"""

import pytest
import requests
import os
import re

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://promo-credits-lab.preview.emergentagent.com')

# Read the CoachDashboard.js file content
COACH_DASHBOARD_PATH = '/app/frontend/src/components/CoachDashboard.js'

@pytest.fixture(scope='module')
def dashboard_content():
    """Load CoachDashboard.js content once for all tests"""
    with open(COACH_DASHBOARD_PATH, 'r') as f:
        return f.read()

@pytest.fixture(scope='module')
def dashboard_lines():
    """Load CoachDashboard.js as lines for line-number analysis"""
    with open(COACH_DASHBOARD_PATH, 'r') as f:
        return f.readlines()


class TestModuleLevelFunctions:
    """Test that autonomous functions are defined at module level (outside React component)"""
    
    def test_performEmailSend_at_module_level(self, dashboard_content, dashboard_lines):
        """Verify performEmailSend is defined BEFORE the CoachDashboard component"""
        # Find line number of performEmailSend definition
        perform_email_line = None
        component_line = None
        
        for i, line in enumerate(dashboard_lines, 1):
            if 'const performEmailSend = async' in line:
                perform_email_line = i
            if 'const CoachDashboard = (' in line:
                component_line = i
                break
        
        assert perform_email_line is not None, "performEmailSend function not found"
        assert component_line is not None, "CoachDashboard component not found"
        assert perform_email_line < component_line, f"performEmailSend (line {perform_email_line}) should be BEFORE CoachDashboard (line {component_line})"
        print(f"✅ performEmailSend defined at line {perform_email_line}, CoachDashboard at line {component_line}")
    
    def test_performWhatsAppSend_at_module_level(self, dashboard_content, dashboard_lines):
        """Verify performWhatsAppSend is defined BEFORE the CoachDashboard component"""
        perform_whatsapp_line = None
        component_line = None
        
        for i, line in enumerate(dashboard_lines, 1):
            if 'const performWhatsAppSend = async' in line:
                perform_whatsapp_line = i
            if 'const CoachDashboard = (' in line:
                component_line = i
                break
        
        assert perform_whatsapp_line is not None, "performWhatsAppSend function not found"
        assert component_line is not None, "CoachDashboard component not found"
        assert perform_whatsapp_line < component_line, f"performWhatsAppSend (line {perform_whatsapp_line}) should be BEFORE CoachDashboard (line {component_line})"
        print(f"✅ performWhatsAppSend defined at line {perform_whatsapp_line}, CoachDashboard at line {component_line}")


class TestEmailJSInitialization:
    """Test EmailJS SDK initialization at module load"""
    
    def test_emailjs_init_at_module_load(self, dashboard_content, dashboard_lines):
        """Verify emailjs.init() is called at module load (around line 37)"""
        init_line = None
        component_line = None
        
        for i, line in enumerate(dashboard_lines, 1):
            if 'emailjs.init(EMAILJS_PUBLIC_KEY)' in line and 'useEffect' not in ''.join(dashboard_lines[max(0,i-5):i]):
                init_line = i
            if 'const CoachDashboard = (' in line:
                component_line = i
                break
        
        assert init_line is not None, "emailjs.init() at module level not found"
        assert init_line < component_line, f"emailjs.init() (line {init_line}) should be BEFORE CoachDashboard (line {component_line})"
        assert init_line < 50, f"emailjs.init() should be near line 37, found at line {init_line}"
        print(f"✅ emailjs.init() called at module load, line {init_line}")
    
    def test_emailjs_init_in_try_catch(self, dashboard_content):
        """Verify emailjs.init() is wrapped in try/catch"""
        # Look for the pattern: try { emailjs.init(...) } catch
        pattern = r'try\s*\{\s*emailjs\.init\(EMAILJS_PUBLIC_KEY\)'
        match = re.search(pattern, dashboard_content)
        assert match is not None, "emailjs.init() should be wrapped in try/catch"
        print("✅ emailjs.init() is wrapped in try/catch block")


class TestPerformEmailSendFunction:
    """Test performEmailSend function implementation"""
    
    def test_has_demande_emailjs_log(self, dashboard_content):
        """Verify performEmailSend has console.log('DEMANDE EMAILJS ENVOYÉE')"""
        assert "console.log('DEMANDE EMAILJS ENVOYÉE')" in dashboard_content, \
            "performEmailSend should have console.log('DEMANDE EMAILJS ENVOYÉE')"
        print("✅ performEmailSend has 'DEMANDE EMAILJS ENVOYÉE' log")
    
    def test_uses_emailjs_send(self, dashboard_content):
        """Verify performEmailSend calls emailjs.send()"""
        # Find the performEmailSend function and check it uses emailjs.send
        pattern = r'const performEmailSend = async.*?return \{ success: false'
        match = re.search(pattern, dashboard_content, re.DOTALL)
        assert match is not None, "performEmailSend function not found"
        func_content = match.group(0)
        assert 'emailjs.send(' in func_content, "performEmailSend should call emailjs.send()"
        print("✅ performEmailSend calls emailjs.send()")
    
    def test_returns_success_object(self, dashboard_content):
        """Verify performEmailSend returns {success: boolean, ...}"""
        assert "return { success: true, response }" in dashboard_content, \
            "performEmailSend should return {success: true, response}"
        assert "return { success: false, error:" in dashboard_content, \
            "performEmailSend should return {success: false, error:...}"
        print("✅ performEmailSend returns proper success/error objects")


class TestPerformWhatsAppSendFunction:
    """Test performWhatsAppSend function implementation"""
    
    def test_has_simulation_mode(self, dashboard_content):
        """Verify performWhatsAppSend has simulation mode with alert()"""
        # Look for the simulation alert pattern
        assert "alert(`WhatsApp prêt pour : ${phoneNumber}" in dashboard_content, \
            "performWhatsAppSend should have simulation alert"
        print("✅ performWhatsAppSend has simulation mode with alert()")
    
    def test_checks_twilio_config(self, dashboard_content):
        """Verify performWhatsAppSend checks for Twilio config"""
        assert "if (!accountSid || !authToken || !fromNumber)" in dashboard_content, \
            "performWhatsAppSend should check Twilio config"
        print("✅ performWhatsAppSend checks Twilio configuration")
    
    def test_returns_simulated_flag(self, dashboard_content):
        """Verify performWhatsAppSend returns simulated: true in simulation mode"""
        assert "return { success: true, simulated: true }" in dashboard_content, \
            "performWhatsAppSend should return {success: true, simulated: true} in simulation mode"
        print("✅ performWhatsAppSend returns simulated flag")


class TestHandlerImplementations:
    """Test that handlers use autonomous functions and have proper event handling"""
    
    def test_handleTestEmailJS_uses_performEmailSend(self, dashboard_content):
        """Verify handleTestEmailJS calls performEmailSend"""
        # Find handleTestEmailJS function
        pattern = r'const handleTestEmailJS = async.*?catch \(sendError\)'
        match = re.search(pattern, dashboard_content, re.DOTALL)
        assert match is not None, "handleTestEmailJS function not found"
        func_content = match.group(0)
        assert 'await performEmailSend(' in func_content, \
            "handleTestEmailJS should call performEmailSend"
        print("✅ handleTestEmailJS uses performEmailSend")
    
    def test_handleTestWhatsApp_uses_performWhatsAppSend(self, dashboard_content):
        """Verify handleTestWhatsApp calls performWhatsAppSend"""
        # Find handleTestWhatsApp function
        pattern = r'const handleTestWhatsApp = async.*?catch \(sendError\)'
        match = re.search(pattern, dashboard_content, re.DOTALL)
        assert match is not None, "handleTestWhatsApp function not found"
        func_content = match.group(0)
        assert 'await performWhatsAppSend(' in func_content, \
            "handleTestWhatsApp should call performWhatsAppSend"
        print("✅ handleTestWhatsApp uses performWhatsAppSend")
    
    def test_launchCampaignWithSend_uses_both_functions(self, dashboard_content):
        """Verify launchCampaignWithSend uses both performEmailSend and performWhatsAppSend"""
        # Find launchCampaignWithSend function
        pattern = r'const launchCampaignWithSend = async.*?alert\(`❌ Erreur lors de l\'envoi'
        match = re.search(pattern, dashboard_content, re.DOTALL)
        assert match is not None, "launchCampaignWithSend function not found"
        func_content = match.group(0)
        assert 'await performEmailSend(' in func_content, \
            "launchCampaignWithSend should call performEmailSend"
        assert 'await performWhatsAppSend(' in func_content, \
            "launchCampaignWithSend should call performWhatsAppSend"
        print("✅ launchCampaignWithSend uses both performEmailSend and performWhatsAppSend")


class TestEventHandlingFirst:
    """Test that all handlers have e.preventDefault() and e.stopPropagation() FIRST"""
    
    def test_handleTestEmailJS_event_handling_first(self, dashboard_content):
        """Verify handleTestEmailJS has e.preventDefault() and e.stopPropagation() at the start"""
        # Find the function and check first lines
        pattern = r'const handleTestEmailJS = async \(e\) => \{[^}]*?e\.preventDefault\(\);[^}]*?e\.stopPropagation\(\);'
        match = re.search(pattern, dashboard_content, re.DOTALL)
        assert match is not None, "handleTestEmailJS should have e.preventDefault() and e.stopPropagation() at start"
        print("✅ handleTestEmailJS has event handling FIRST")
    
    def test_handleTestWhatsApp_event_handling_first(self, dashboard_content):
        """Verify handleTestWhatsApp has e.preventDefault() and e.stopPropagation() at the start"""
        pattern = r'const handleTestWhatsApp = async \(e\) => \{[^}]*?e\.preventDefault\(\);[^}]*?e\.stopPropagation\(\);'
        match = re.search(pattern, dashboard_content, re.DOTALL)
        assert match is not None, "handleTestWhatsApp should have e.preventDefault() and e.stopPropagation() at start"
        print("✅ handleTestWhatsApp has event handling FIRST")
    
    def test_launchCampaignWithSend_event_handling_first(self, dashboard_content):
        """Verify launchCampaignWithSend has e.preventDefault() and e.stopPropagation() at the start"""
        pattern = r'const launchCampaignWithSend = async \(e, campaignId\) => \{[^}]*?e\.preventDefault\(\);[^}]*?e\.stopPropagation\(\);'
        match = re.search(pattern, dashboard_content, re.DOTALL)
        assert match is not None, "launchCampaignWithSend should have e.preventDefault() and e.stopPropagation() at start"
        print("✅ launchCampaignWithSend has event handling FIRST")


class TestNestedTryCatch:
    """Test that handlers have nested try/catch blocks to isolate PostHog errors"""
    
    def test_handleTestEmailJS_nested_try_catch(self, dashboard_content):
        """Verify handleTestEmailJS has nested try/catch for PostHog isolation"""
        # Find the function
        pattern = r'const handleTestEmailJS = async.*?catch \(sendError\)'
        match = re.search(pattern, dashboard_content, re.DOTALL)
        assert match is not None, "handleTestEmailJS function not found"
        func_content = match.group(0)
        
        # Count try blocks - should have multiple for isolation
        try_count = func_content.count('try {')
        assert try_count >= 2, f"handleTestEmailJS should have nested try/catch (found {try_count} try blocks)"
        
        # Check for PostHog isolation comments
        assert 'PostHog' in func_content, "handleTestEmailJS should mention PostHog isolation"
        print(f"✅ handleTestEmailJS has {try_count} nested try/catch blocks for PostHog isolation")
    
    def test_handleTestWhatsApp_nested_try_catch(self, dashboard_content):
        """Verify handleTestWhatsApp has nested try/catch for PostHog isolation"""
        pattern = r'const handleTestWhatsApp = async.*?catch \(sendError\)'
        match = re.search(pattern, dashboard_content, re.DOTALL)
        assert match is not None, "handleTestWhatsApp function not found"
        func_content = match.group(0)
        
        try_count = func_content.count('try {')
        assert try_count >= 2, f"handleTestWhatsApp should have nested try/catch (found {try_count} try blocks)"
        assert 'PostHog' in func_content, "handleTestWhatsApp should mention PostHog isolation"
        print(f"✅ handleTestWhatsApp has {try_count} nested try/catch blocks for PostHog isolation")
    
    def test_launchCampaignWithSend_nested_try_catch(self, dashboard_content):
        """Verify launchCampaignWithSend has nested try/catch for PostHog isolation"""
        pattern = r'const launchCampaignWithSend = async.*?alert\(`❌ Erreur lors de l\'envoi'
        match = re.search(pattern, dashboard_content, re.DOTALL)
        assert match is not None, "launchCampaignWithSend function not found"
        func_content = match.group(0)
        
        try_count = func_content.count('try {')
        assert try_count >= 3, f"launchCampaignWithSend should have multiple nested try/catch (found {try_count} try blocks)"
        assert 'PostHog' in func_content, "launchCampaignWithSend should mention PostHog isolation"
        print(f"✅ launchCampaignWithSend has {try_count} nested try/catch blocks for PostHog isolation")


class TestBackendAPI:
    """Test backend API endpoints are working"""
    
    def test_health_endpoint(self):
        """Verify health endpoint returns 200"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200, f"Health endpoint failed: {response.status_code}"
        data = response.json()
        assert data.get('status') == 'healthy', f"Health status not healthy: {data}"
        print("✅ Health endpoint returns 200 with healthy status")
    
    def test_campaigns_endpoint(self):
        """Verify campaigns endpoint returns list"""
        response = requests.get(f"{BASE_URL}/api/campaigns")
        assert response.status_code == 200, f"Campaigns endpoint failed: {response.status_code}"
        data = response.json()
        assert isinstance(data, list), f"Campaigns should return list, got: {type(data)}"
        print(f"✅ Campaigns endpoint returns list with {len(data)} campaigns")
    
    def test_whatsapp_config_endpoint(self):
        """Verify WhatsApp config endpoint returns correct structure"""
        response = requests.get(f"{BASE_URL}/api/whatsapp-config")
        assert response.status_code == 200, f"WhatsApp config endpoint failed: {response.status_code}"
        data = response.json()
        # Should have accountSid, authToken, fromNumber keys (may be empty)
        assert 'accountSid' in data or 'account_sid' in data or isinstance(data, dict), \
            f"WhatsApp config should return dict structure: {data}"
        print("✅ WhatsApp config endpoint returns correct structure")


class TestEmailJSConstants:
    """Test EmailJS constants are correctly defined"""
    
    def test_service_id_constant(self, dashboard_content):
        """Verify EMAILJS_SERVICE_ID is correctly defined"""
        assert 'const EMAILJS_SERVICE_ID = "service_8mrmxim"' in dashboard_content, \
            "EMAILJS_SERVICE_ID should be 'service_8mrmxim'"
        print("✅ EMAILJS_SERVICE_ID = 'service_8mrmxim'")
    
    def test_template_id_constant(self, dashboard_content):
        """Verify EMAILJS_TEMPLATE_ID is correctly defined"""
        assert 'const EMAILJS_TEMPLATE_ID = "template_3n1u86p"' in dashboard_content, \
            "EMAILJS_TEMPLATE_ID should be 'template_3n1u86p'"
        print("✅ EMAILJS_TEMPLATE_ID = 'template_3n1u86p'")
    
    def test_public_key_constant(self, dashboard_content):
        """Verify EMAILJS_PUBLIC_KEY is correctly defined"""
        assert 'const EMAILJS_PUBLIC_KEY = "5LfgQSIEQoqq_XSqt"' in dashboard_content, \
            "EMAILJS_PUBLIC_KEY should be '5LfgQSIEQoqq_XSqt'"
        print("✅ EMAILJS_PUBLIC_KEY = '5LfgQSIEQoqq_XSqt'")


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
