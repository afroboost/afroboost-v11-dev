"""
Test Coach Notifications Feature
Tests for automatic notifications when a client makes a reservation.
The coach should receive email and/or WhatsApp with:
- Client name, email, WhatsApp
- Offer chosen
- Course name
- Session date
- Amount
- Reservation code
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://promo-credits-lab.preview.emergentagent.com').rstrip('/')


class TestPaymentLinksNotificationFields:
    """Test that payment-links API accepts notification fields"""
    
    def test_get_payment_links_returns_notification_fields(self):
        """GET /api/payment-links should return coachNotificationEmail and coachNotificationPhone"""
        response = requests.get(f"{BASE_URL}/api/payment-links")
        assert response.status_code == 200
        
        data = response.json()
        # Verify notification fields exist in response
        assert "coachNotificationEmail" in data, "coachNotificationEmail field missing from payment-links"
        assert "coachNotificationPhone" in data, "coachNotificationPhone field missing from payment-links"
        print(f"✅ Payment links contains notification fields: email='{data.get('coachNotificationEmail', '')}', phone='{data.get('coachNotificationPhone', '')}'")
    
    def test_update_payment_links_with_notification_email(self):
        """PUT /api/payment-links should accept coachNotificationEmail"""
        # First get current values
        get_response = requests.get(f"{BASE_URL}/api/payment-links")
        current_data = get_response.json()
        
        # Update with test notification email
        test_email = "test-notification@afroboost.com"
        update_data = {
            "stripe": current_data.get("stripe", ""),
            "paypal": current_data.get("paypal", ""),
            "twint": current_data.get("twint", ""),
            "coachWhatsapp": current_data.get("coachWhatsapp", ""),
            "coachNotificationEmail": test_email,
            "coachNotificationPhone": current_data.get("coachNotificationPhone", "")
        }
        
        response = requests.put(f"{BASE_URL}/api/payment-links", json=update_data)
        assert response.status_code == 200
        
        # Verify the update
        data = response.json()
        assert data.get("coachNotificationEmail") == test_email, f"Expected email '{test_email}', got '{data.get('coachNotificationEmail')}'"
        print(f"✅ Successfully updated coachNotificationEmail to '{test_email}'")
    
    def test_update_payment_links_with_notification_phone(self):
        """PUT /api/payment-links should accept coachNotificationPhone"""
        # First get current values
        get_response = requests.get(f"{BASE_URL}/api/payment-links")
        current_data = get_response.json()
        
        # Update with test notification phone
        test_phone = "+41791234567"
        update_data = {
            "stripe": current_data.get("stripe", ""),
            "paypal": current_data.get("paypal", ""),
            "twint": current_data.get("twint", ""),
            "coachWhatsapp": current_data.get("coachWhatsapp", ""),
            "coachNotificationEmail": current_data.get("coachNotificationEmail", ""),
            "coachNotificationPhone": test_phone
        }
        
        response = requests.put(f"{BASE_URL}/api/payment-links", json=update_data)
        assert response.status_code == 200
        
        # Verify the update
        data = response.json()
        assert data.get("coachNotificationPhone") == test_phone, f"Expected phone '{test_phone}', got '{data.get('coachNotificationPhone')}'"
        print(f"✅ Successfully updated coachNotificationPhone to '{test_phone}'")
    
    def test_update_both_notification_fields(self):
        """PUT /api/payment-links should accept both notification fields together"""
        test_email = "coach-alerts@afroboost.com"
        test_phone = "+41799876543"
        
        update_data = {
            "coachNotificationEmail": test_email,
            "coachNotificationPhone": test_phone
        }
        
        response = requests.put(f"{BASE_URL}/api/payment-links", json=update_data)
        assert response.status_code == 200
        
        # Verify both fields updated
        data = response.json()
        assert data.get("coachNotificationEmail") == test_email
        assert data.get("coachNotificationPhone") == test_phone
        print(f"✅ Successfully updated both notification fields")


class TestNotifyCoachEndpoint:
    """Test the /api/notify-coach endpoint"""
    
    @pytest.fixture(autouse=True)
    def setup_notification_config(self):
        """Setup notification config before tests"""
        # Configure notification settings
        config_data = {
            "coachNotificationEmail": "coach-test@afroboost.com",
            "coachNotificationPhone": "+41791234567"
        }
        requests.put(f"{BASE_URL}/api/payment-links", json=config_data)
        yield
    
    def test_notify_coach_returns_formatted_message(self):
        """POST /api/notify-coach should return formatted notification info"""
        payload = {
            "clientName": "Jean Dupont",
            "clientEmail": "jean.dupont@example.com",
            "clientWhatsapp": "+41791112233",
            "offerName": "Carte 10 cours",
            "courseName": "Afroboost Silent – Session Cardio",
            "sessionDate": "mercredi 15 janvier 2025 à 18:30",
            "amount": 150.0,
            "reservationCode": "AFR-TEST01"
        }
        
        response = requests.post(f"{BASE_URL}/api/notify-coach", json=payload)
        assert response.status_code == 200
        
        data = response.json()
        assert data.get("success") == True, f"Expected success=True, got {data}"
        
        # Verify response contains required fields
        assert "coachEmail" in data, "coachEmail missing from response"
        assert "coachPhone" in data, "coachPhone missing from response"
        assert "message" in data, "message missing from response"
        assert "subject" in data, "subject missing from response"
        
        print(f"✅ notify-coach returned: coachEmail='{data.get('coachEmail')}', coachPhone='{data.get('coachPhone')}'")
        print(f"✅ Subject: {data.get('subject')}")
    
    def test_notify_coach_message_contains_client_info(self):
        """Notification message should contain all client information"""
        payload = {
            "clientName": "Marie Martin",
            "clientEmail": "marie@test.com",
            "clientWhatsapp": "+41799998877",
            "offerName": "Abonnement 1 mois",
            "courseName": "Sunday Vibes",
            "sessionDate": "dimanche 19 janvier 2025 à 18:30",
            "amount": 109.0,
            "reservationCode": "AFR-MARIE1"
        }
        
        response = requests.post(f"{BASE_URL}/api/notify-coach", json=payload)
        assert response.status_code == 200
        
        data = response.json()
        message = data.get("message", "")
        
        # Verify message contains all required information
        assert "Marie Martin" in message, "Client name missing from message"
        assert "marie@test.com" in message, "Client email missing from message"
        assert "+41799998877" in message, "Client WhatsApp missing from message"
        assert "Abonnement 1 mois" in message, "Offer name missing from message"
        assert "Sunday Vibes" in message, "Course name missing from message"
        assert "109" in message, "Amount missing from message"
        assert "AFR-MARIE1" in message, "Reservation code missing from message"
        
        print(f"✅ Message contains all required client information")
        print(f"Message preview: {message[:200]}...")
    
    def test_notify_coach_without_config_returns_error(self):
        """notify-coach should return error if no notification config"""
        # Clear notification config
        requests.put(f"{BASE_URL}/api/payment-links", json={
            "coachNotificationEmail": "",
            "coachNotificationPhone": ""
        })
        
        payload = {
            "clientName": "Test User",
            "clientEmail": "test@test.com",
            "clientWhatsapp": "+41700000000",
            "offerName": "Test Offer",
            "courseName": "Test Course",
            "sessionDate": "2025-01-15",
            "amount": 30.0,
            "reservationCode": "AFR-TEST00"
        }
        
        response = requests.post(f"{BASE_URL}/api/notify-coach", json=payload)
        assert response.status_code == 200
        
        data = response.json()
        assert data.get("success") == False, "Should return success=False when no config"
        assert "message" in data, "Should return error message"
        print(f"✅ Correctly returns error when no notification config: {data.get('message')}")
    
    def test_notify_coach_with_only_email_config(self):
        """notify-coach should work with only email configured"""
        # Configure only email
        requests.put(f"{BASE_URL}/api/payment-links", json={
            "coachNotificationEmail": "only-email@test.com",
            "coachNotificationPhone": ""
        })
        
        payload = {
            "clientName": "Email Only Test",
            "clientEmail": "client@test.com",
            "clientWhatsapp": "+41700000001",
            "offerName": "Cours à l'unité",
            "courseName": "Session Cardio",
            "sessionDate": "2025-01-20",
            "amount": 30.0,
            "reservationCode": "AFR-EMAIL1"
        }
        
        response = requests.post(f"{BASE_URL}/api/notify-coach", json=payload)
        assert response.status_code == 200
        
        data = response.json()
        assert data.get("success") == True
        assert data.get("coachEmail") == "only-email@test.com"
        assert data.get("coachPhone") == ""
        print(f"✅ Works with only email configured")
    
    def test_notify_coach_with_only_phone_config(self):
        """notify-coach should work with only phone configured"""
        # Configure only phone
        requests.put(f"{BASE_URL}/api/payment-links", json={
            "coachNotificationEmail": "",
            "coachNotificationPhone": "+41791234567"
        })
        
        payload = {
            "clientName": "Phone Only Test",
            "clientEmail": "client2@test.com",
            "clientWhatsapp": "+41700000002",
            "offerName": "Carte 10 cours",
            "courseName": "Sunday Vibes",
            "sessionDate": "2025-01-21",
            "amount": 150.0,
            "reservationCode": "AFR-PHONE1"
        }
        
        response = requests.post(f"{BASE_URL}/api/notify-coach", json=payload)
        assert response.status_code == 200
        
        data = response.json()
        assert data.get("success") == True
        assert data.get("coachEmail") == ""
        assert data.get("coachPhone") == "+41791234567"
        print(f"✅ Works with only phone configured")


class TestCoachLogin:
    """Test coach authentication for accessing notification settings"""
    
    def test_coach_login_success(self):
        """Coach should be able to login with correct credentials"""
        response = requests.post(f"{BASE_URL}/api/coach-auth/login", json={
            "email": "coach@afroboost.com",
            "password": "afroboost123"
        })
        assert response.status_code == 200
        
        data = response.json()
        assert data.get("success") == True, f"Login failed: {data}"
        print(f"✅ Coach login successful")
    
    def test_coach_login_failure(self):
        """Coach login should fail with wrong credentials"""
        response = requests.post(f"{BASE_URL}/api/coach-auth/login", json={
            "email": "coach@afroboost.com",
            "password": "wrongpassword"
        })
        assert response.status_code == 200
        
        data = response.json()
        assert data.get("success") == False, "Should fail with wrong password"
        print(f"✅ Login correctly rejected with wrong password")


class TestIntegrationFlow:
    """Test the complete notification flow"""
    
    def test_complete_notification_setup_and_trigger(self):
        """Test complete flow: configure notifications -> trigger -> verify"""
        # Step 1: Configure notification settings
        config_response = requests.put(f"{BASE_URL}/api/payment-links", json={
            "coachNotificationEmail": "integration-test@afroboost.com",
            "coachNotificationPhone": "+41791234567"
        })
        assert config_response.status_code == 200
        print("✅ Step 1: Notification settings configured")
        
        # Step 2: Verify settings are saved
        get_response = requests.get(f"{BASE_URL}/api/payment-links")
        assert get_response.status_code == 200
        saved_data = get_response.json()
        assert saved_data.get("coachNotificationEmail") == "integration-test@afroboost.com"
        assert saved_data.get("coachNotificationPhone") == "+41791234567"
        print("✅ Step 2: Settings verified in database")
        
        # Step 3: Trigger notification (simulating a reservation)
        notify_response = requests.post(f"{BASE_URL}/api/notify-coach", json={
            "clientName": "Integration Test Client",
            "clientEmail": "integration@client.com",
            "clientWhatsapp": "+41700000003",
            "offerName": "Abonnement 1 mois",
            "courseName": "Afroboost Silent – Session Cardio",
            "sessionDate": "lundi 20 janvier 2025 à 18:30",
            "amount": 109.0,
            "reservationCode": "AFR-INTEG1"
        })
        assert notify_response.status_code == 200
        
        notify_data = notify_response.json()
        assert notify_data.get("success") == True
        assert notify_data.get("coachEmail") == "integration-test@afroboost.com"
        assert notify_data.get("coachPhone") == "+41791234567"
        print("✅ Step 3: Notification triggered successfully")
        
        # Step 4: Verify message format
        message = notify_data.get("message", "")
        assert "Integration Test Client" in message
        assert "integration@client.com" in message
        assert "Abonnement 1 mois" in message
        assert "109" in message
        assert "AFR-INTEG1" in message
        print("✅ Step 4: Message format verified")
        
        print("\n🎉 Complete integration flow passed!")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
