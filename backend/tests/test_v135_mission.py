"""
Mission v13.5 - Backend Tests
Tests for:
1. Anti-regression: 22 reservations, 7 contacts
2. API endpoints health check
3. Credits system
4. New extracted components (PageVenteTab, PromoCodesTab related endpoints)
"""

import pytest
import requests
import os

# Get base URL from environment
BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://violet-marketplace-1.preview.emergentagent.com')

# Super Admin emails for testing
SUPER_ADMIN_EMAILS = ['contact.artboost@gmail.com', 'afroboost.bassi@gmail.com']

class TestAntiRegression:
    """Tests de non-régression v13.5"""
    
    def test_reservations_count_22(self):
        """Vérifier qu'on a bien 22 réservations (anti-régression)"""
        response = requests.get(
            f"{BASE_URL}/api/reservations?page=1&limit=100",
            headers={"X-User-Email": SUPER_ADMIN_EMAILS[0]}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert "pagination" in data, "Response should have pagination"
        assert data["pagination"]["total"] == 22, f"Expected 22 reservations, got {data['pagination']['total']}"
        print(f"✅ Anti-regression: {data['pagination']['total']} réservations (expected: 22)")
    
    def test_contacts_count_7(self):
        """Vérifier qu'on a bien 7 contacts (anti-régression)"""
        response = requests.get(f"{BASE_URL}/api/users")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert len(data) == 7, f"Expected 7 contacts, got {len(data)}"
        print(f"✅ Anti-regression: {len(data)} contacts (expected: 7)")


class TestAPIEndpoints:
    """Tests des endpoints API principaux"""
    
    def test_health_check(self):
        """Endpoint de santé"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        print("✅ Health endpoint OK")
    
    def test_courses_endpoint(self):
        """Endpoint des cours"""
        response = requests.get(f"{BASE_URL}/api/courses")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list), "Courses should be a list"
        print(f"✅ Courses endpoint OK - {len(data)} courses")
    
    def test_offers_endpoint(self):
        """Endpoint des offres"""
        response = requests.get(f"{BASE_URL}/api/offers")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list), "Offers should be a list"
        print(f"✅ Offers endpoint OK - {len(data)} offers")
    
    def test_concept_endpoint(self):
        """Endpoint du concept"""
        response = requests.get(f"{BASE_URL}/api/concept")
        assert response.status_code == 200
        data = response.json()
        assert "appName" in data, "Concept should have appName"
        print(f"✅ Concept endpoint OK - appName: {data.get('appName')}")
    
    def test_payment_links_endpoint(self):
        """Endpoint des liens de paiement (PageVenteTab)"""
        response = requests.get(f"{BASE_URL}/api/payment-links")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict), "Payment links should be a dict"
        print(f"✅ Payment-links endpoint OK (used by PageVenteTab)")
    
    def test_discount_codes_endpoint(self):
        """Endpoint des codes promo (PromoCodesTab)"""
        response = requests.get(f"{BASE_URL}/api/discount-codes")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list), "Discount codes should be a list"
        print(f"✅ Discount-codes endpoint OK (used by PromoCodesTab) - {len(data)} codes")


class TestCreditsSystem:
    """Tests du système de crédits"""
    
    def test_credit_packs_endpoint(self):
        """Endpoint des packs de crédits"""
        response = requests.get(f"{BASE_URL}/api/credit-packs")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list), "Credit packs should be a list"
        print(f"✅ Credit packs endpoint OK - {len(data)} packs available")
    
    def test_platform_settings_endpoint(self):
        """Endpoint des paramètres de la plateforme (service prices)"""
        response = requests.get(
            f"{BASE_URL}/api/platform-settings",
            headers={"X-User-Email": SUPER_ADMIN_EMAILS[0]}
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict), "Platform settings should be a dict"
        print(f"✅ Platform settings endpoint OK")
    
    def test_coach_profile_endpoint(self):
        """Endpoint du profil coach (pour crédits)"""
        response = requests.get(
            f"{BASE_URL}/api/coach/profile",
            headers={"X-User-Email": SUPER_ADMIN_EMAILS[0]}
        )
        # Could be 200 or 404 if profile doesn't exist
        assert response.status_code in [200, 404], f"Expected 200 or 404, got {response.status_code}"
        print(f"✅ Coach profile endpoint OK (status: {response.status_code})")


class TestStripeRoutes:
    """Tests des routes Stripe"""
    
    def test_stripe_credit_checkout(self):
        """Test de l'endpoint de création de checkout crédits (sans achat réel)"""
        # We just verify the endpoint exists and returns proper error for invalid data
        response = requests.post(
            f"{BASE_URL}/api/stripe/create-credit-checkout",
            json={"pack_id": "invalid_pack"},
            headers={"X-User-Email": SUPER_ADMIN_EMAILS[0]}
        )
        # Should return 404 (pack not found) or 400 (invalid), not 500
        assert response.status_code != 500, f"Stripe endpoint should not return 500 error"
        print(f"✅ Stripe credit checkout endpoint exists (returned {response.status_code})")
    
    def test_stripe_connect_status(self):
        """Test de l'endpoint Stripe Connect status"""
        response = requests.get(
            f"{BASE_URL}/api/coach/stripe-connect/status",
            headers={"X-User-Email": SUPER_ADMIN_EMAILS[0]}
        )
        # Should return 200 with status info
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print(f"✅ Stripe Connect status endpoint OK")


class TestDataIntegrity:
    """Tests d'intégrité des données"""
    
    def test_no_500_errors_on_reservations(self):
        """Pas d'erreur 500 sur les réservations"""
        response = requests.get(
            f"{BASE_URL}/api/reservations?page=1&limit=20",
            headers={"X-User-Email": SUPER_ADMIN_EMAILS[0]}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("✅ Reservations endpoint - no 500 errors")
    
    def test_sanitize_data_endpoint(self):
        """Test de l'endpoint de nettoyage des données"""
        response = requests.post(f"{BASE_URL}/api/sanitize-data")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        # Response has success and codes_cleaned directly (not nested in stats)
        assert "success" in data, "Response should have success"
        print(f"✅ Sanitize endpoint OK - codes_cleaned: {data.get('codes_cleaned', 0)}")


class TestNewComponentEndpoints:
    """Tests spécifiques aux nouveaux composants v13.5"""
    
    def test_payment_links_update(self):
        """Test PUT payment-links (PageVenteTab)"""
        # First get current data
        get_response = requests.get(f"{BASE_URL}/api/payment-links")
        assert get_response.status_code == 200
        current_data = get_response.json()
        
        # Update with same data (no change)
        put_response = requests.put(
            f"{BASE_URL}/api/payment-links",
            json=current_data
        )
        assert put_response.status_code == 200, f"Expected 200, got {put_response.status_code}"
        print("✅ Payment-links PUT endpoint OK (PageVenteTab auto-save)")
    
    def test_discount_codes_list(self):
        """Test GET discount-codes (PromoCodesTab)"""
        response = requests.get(f"{BASE_URL}/api/discount-codes")
        assert response.status_code == 200
        data = response.json()
        
        # Verify structure
        if len(data) > 0:
            code = data[0]
            # PromoCodesTab expects these fields
            expected_fields = ["id", "code", "type", "value"]
            for field in expected_fields:
                assert field in code, f"Code should have field '{field}'"
        print(f"✅ Discount codes structure OK for PromoCodesTab - {len(data)} codes")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
