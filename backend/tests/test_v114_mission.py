# test_v114_mission.py - Tests Mission v11.4
# Système de codes promo et crédits chat
# Features: validation code promo, abonnement avec séances, déduction automatique

import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestHealthEndpoint:
    """Santé du backend"""
    
    def test_health_endpoint(self):
        """Vérifier que le backend est en ligne"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "healthy"
        print("✅ Backend healthy")


class TestAntiRegression:
    """Anti-régression: NE PAS supprimer les données existantes"""
    
    def test_reservations_not_deleted(self):
        """Vérifier que les réservations existantes sont intactes (>= 7)"""
        response = requests.get(
            f"{BASE_URL}/api/reservations?all_data=true",
            headers={"X-User-Email": "afroboost.bassi@gmail.com"}
        )
        assert response.status_code == 200
        data = response.json()
        reservations_count = len(data.get("data", []))
        assert reservations_count >= 7, f"Attendu >= 7 réservations, trouvé {reservations_count}"
        print(f"✅ Anti-régression: {reservations_count} réservations préservées (>= 7)")
    
    def test_contacts_not_deleted(self):
        """Vérifier que les contacts existants sont intacts (>= 8)"""
        response = requests.get(
            f"{BASE_URL}/api/chat/participants",
            headers={"X-User-Email": "afroboost.bassi@gmail.com"}
        )
        assert response.status_code == 200
        data = response.json()
        contacts_count = len(data)
        assert contacts_count >= 8, f"Attendu >= 8 contacts, trouvé {contacts_count}"
        print(f"✅ Anti-régression: {contacts_count} contacts préservés (>= 8)")


class TestSubscriptionValidation:
    """Tests validation code promo et création abonnement v11.4"""
    
    def test_validate_discount_code_creates_subscription(self):
        """POST /api/discount-codes/validate - Doit créer un abonnement avec séances"""
        test_email = f"test-v114-{uuid.uuid4().hex[:8]}@test.com"
        response = requests.post(
            f"{BASE_URL}/api/discount-codes/validate",
            json={
                "code": "BOSS",
                "email": test_email,
                "name": "Test V114"
            }
        )
        assert response.status_code == 200
        data = response.json()
        
        # Vérifier code valide
        assert data.get("valid") == True, "Code BOSS devrait être valide"
        
        # Vérifier que subscription est retournée
        subscription = data.get("subscription")
        assert subscription is not None, "subscription devrait être retournée après validation"
        assert subscription.get("total_sessions") == 47, f"total_sessions devrait être 47, trouvé {subscription.get('total_sessions')}"
        assert subscription.get("remaining_sessions") == 47, f"remaining_sessions devrait être 47 pour nouvel abonné"
        print(f"✅ Validation code BOSS crée abonnement avec {subscription.get('total_sessions')} séances")
    
    def test_validate_invalid_code(self):
        """POST /api/discount-codes/validate - Code invalide retourne valid=false"""
        response = requests.post(
            f"{BASE_URL}/api/discount-codes/validate",
            json={
                "code": "INVALID_CODE_XYZ",
                "email": "test@test.com"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("valid") == False, "Code invalide devrait retourner valid=false"
        print("✅ Code invalide correctement rejeté")


class TestSubscriptionStatus:
    """Tests API statut d'abonnement v11.4"""
    
    def test_get_subscription_status(self):
        """GET /api/discount-codes/subscriptions/status - Retourne le solde abonné"""
        response = requests.get(
            f"{BASE_URL}/api/discount-codes/subscriptions/status",
            params={"email": "test-subscriber@test.com", "code": "BOSS"}
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data.get("success") == True
        assert data.get("hasSubscription") == True
        
        subscription = data.get("subscription")
        assert subscription is not None
        assert "remaining_sessions" in subscription, "remaining_sessions devrait être présent"
        assert "total_sessions" in subscription, "total_sessions devrait être présent"
        assert "used_sessions" in subscription, "used_sessions devrait être présent"
        assert subscription.get("status") == "active", "Abonnement devrait être actif"
        
        print(f"✅ Statut abonnement: {subscription.get('remaining_sessions')}/{subscription.get('total_sessions')} séances")
    
    def test_get_subscription_status_no_subscription(self):
        """GET /api/discount-codes/subscriptions/status - Utilisateur sans abonnement"""
        response = requests.get(
            f"{BASE_URL}/api/discount-codes/subscriptions/status",
            params={"email": "no-subscription@test.com"}
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data.get("hasSubscription") == False
        print("✅ Utilisateur sans abonnement correctement détecté")
    
    def test_get_subscription_status_missing_params(self):
        """GET /api/discount-codes/subscriptions/status - Sans paramètres"""
        response = requests.get(f"{BASE_URL}/api/discount-codes/subscriptions/status")
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") == False
        print("✅ Requête sans paramètres rejetée correctement")


class TestSubscriptionDeduction:
    """Tests déduction de séances v11.4"""
    
    def test_deduct_session(self):
        """POST /api/discount-codes/subscriptions/deduct - Déduit 1 séance"""
        # D'abord récupérer le statut actuel
        status_response = requests.get(
            f"{BASE_URL}/api/discount-codes/subscriptions/status",
            params={"email": "test-subscriber@test.com", "code": "BOSS"}
        )
        initial_remaining = status_response.json().get("subscription", {}).get("remaining_sessions", 0)
        
        # Déduire 1 séance
        response = requests.post(
            f"{BASE_URL}/api/discount-codes/subscriptions/deduct",
            json={"email": "test-subscriber@test.com", "code": "BOSS"}
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data.get("success") == True
        assert "remaining" in data
        assert data.get("remaining") == initial_remaining - 1, f"remaining devrait être {initial_remaining - 1}"
        print(f"✅ Séance déduite: {data.get('remaining')} restantes (avant: {initial_remaining})")
    
    def test_deduct_session_missing_email(self):
        """POST /api/discount-codes/subscriptions/deduct - Sans email"""
        response = requests.post(
            f"{BASE_URL}/api/discount-codes/subscriptions/deduct",
            json={}
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") == False
        print("✅ Déduction sans email rejetée")


class TestReservationAutoDeduction:
    """Tests déduction automatique lors de réservation v11.4"""
    
    def test_reservation_with_promo_code(self):
        """POST /api/reservations - Avec code promo valide"""
        # Créer une réservation test
        response = requests.post(
            f"{BASE_URL}/api/reservations",
            json={
                "userName": "Test Reservation V114",
                "userEmail": "test-subscriber@test.com",
                "userWhatsapp": "+41791234567",
                "courseName": "Test Course",
                "courseTime": "18:30",
                "offerName": "Test Offer",
                "totalPrice": 0,
                "quantity": 1,
                "promoCode": "BOSS",
                "source": "test_v114"
            },
            headers={"X-User-Email": "afroboost.bassi@gmail.com"}
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "reservationCode" in data, "reservationCode devrait être retourné"
        assert data.get("promoCode") == "BOSS", "promoCode devrait être BOSS"
        print(f"✅ Réservation créée avec code: {data.get('reservationCode')}")
    
    def test_reservation_deducts_session(self):
        """Vérifier que la réservation déduit automatiquement 1 séance"""
        # Récupérer le statut avant
        status_before = requests.get(
            f"{BASE_URL}/api/discount-codes/subscriptions/status",
            params={"email": "test-subscriber@test.com", "code": "BOSS"}
        ).json()
        remaining_before = status_before.get("subscription", {}).get("remaining_sessions", 0)
        
        # Créer une réservation
        response = requests.post(
            f"{BASE_URL}/api/reservations",
            json={
                "userName": "Test Auto Deduction",
                "userEmail": "test-subscriber@test.com",
                "userWhatsapp": "+41791234567",
                "courseName": "Test Course Deduction",
                "courseTime": "18:30",
                "offerName": "Test Offer Deduction",
                "totalPrice": 0,
                "quantity": 1,
                "promoCode": "BOSS",
                "source": "test_v114_deduction"
            },
            headers={"X-User-Email": "afroboost.bassi@gmail.com"}
        )
        assert response.status_code == 200
        
        # Récupérer le statut après
        status_after = requests.get(
            f"{BASE_URL}/api/discount-codes/subscriptions/status",
            params={"email": "test-subscriber@test.com", "code": "BOSS"}
        ).json()
        remaining_after = status_after.get("subscription", {}).get("remaining_sessions", 0)
        
        # Vérifier la déduction
        assert remaining_after == remaining_before - 1, f"Séance devrait être déduite: {remaining_before} -> {remaining_after}"
        print(f"✅ Déduction automatique: {remaining_before} -> {remaining_after} séances")


class TestDiscountCodesAPI:
    """Tests complémentaires sur l'API codes promo"""
    
    def test_get_discount_codes(self):
        """GET /api/discount-codes - Liste des codes"""
        response = requests.get(
            f"{BASE_URL}/api/discount-codes",
            headers={"X-User-Email": "afroboost.bassi@gmail.com"}
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        
        # Vérifier que BOSS existe
        boss_code = next((c for c in data if c.get("code") == "BOSS"), None)
        assert boss_code is not None, "Code BOSS devrait exister"
        assert boss_code.get("active") == True
        print(f"✅ {len(data)} codes promo trouvés, BOSS actif")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
