"""
Test v8.9.3 - Non-régression et nouvelles fonctionnalités
- NON-RÉGRESSION: GET /api/courses - Cours fitness intacts
- NON-RÉGRESSION: GET /api/offers - Offres clients intacts  
- NON-RÉGRESSION: GET /api/discount-codes - QR codes intacts
- NON-RÉGRESSION: GET /api/payment-links - Liens paiement intacts
- BACKEND: Redirection success_url vers /#coach-dashboard après achat coach
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://promo-credits-lab.preview.emergentagent.com')


class TestNonRegression:
    """Tests de non-régression v8.9.3 - Données existantes intactes"""
    
    def test_health_check(self):
        """TEST 1 - Vérification santé API"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "healthy"
        print(f"✅ TEST 1 - API Health: {data}")
    
    def test_courses_intact(self):
        """TEST 2 - NON-RÉGRESSION: Cours fitness intacts"""
        response = requests.get(f"{BASE_URL}/api/courses")
        assert response.status_code == 200
        courses = response.json()
        assert isinstance(courses, list)
        # Vérifier qu'au moins un cours existe
        assert len(courses) >= 1, "Au moins 1 cours doit exister"
        # Vérifier la structure des cours
        for course in courses:
            assert "id" in course
            assert "name" in course
        print(f"✅ TEST 2 - Courses intacts: {len(courses)} cours trouvés")
    
    def test_offers_intact(self):
        """TEST 3 - NON-RÉGRESSION: Offres clients intacts"""
        response = requests.get(f"{BASE_URL}/api/offers")
        assert response.status_code == 200
        offers = response.json()
        assert isinstance(offers, list)
        # Vérifier qu'au moins une offre existe
        assert len(offers) >= 1, "Au moins 1 offre doit exister"
        # Vérifier la structure des offres
        for offer in offers:
            assert "id" in offer
            assert "name" in offer
            assert "price" in offer
        print(f"✅ TEST 3 - Offers intacts: {len(offers)} offres trouvées")
    
    def test_discount_codes_intact(self):
        """TEST 4 - NON-RÉGRESSION: Codes promo/QR intacts"""
        response = requests.get(f"{BASE_URL}/api/discount-codes")
        assert response.status_code == 200
        codes = response.json()
        assert isinstance(codes, list)
        # Structure correcte
        for code in codes:
            assert "id" in code
            assert "code" in code
        print(f"✅ TEST 4 - Discount codes intacts: {len(codes)} codes trouvés")
    
    def test_payment_links_intact(self):
        """TEST 5 - NON-RÉGRESSION: Liens paiement intacts"""
        response = requests.get(f"{BASE_URL}/api/payment-links")
        assert response.status_code == 200
        links = response.json()
        assert isinstance(links, dict)
        # Vérifier les champs attendus
        assert "id" in links
        print(f"✅ TEST 5 - Payment links intacts: {links.get('id')}")
    
    def test_concept_intact(self):
        """TEST 6 - NON-RÉGRESSION: Concept intact"""
        response = requests.get(f"{BASE_URL}/api/concept")
        assert response.status_code == 200
        concept = response.json()
        assert isinstance(concept, dict)
        assert "id" in concept
        print(f"✅ TEST 6 - Concept intact: appName={concept.get('appName', 'Afroboost')}")


class TestCoachPacks:
    """Tests pour les packs Coach v8.9.3"""
    
    def test_coach_packs_public_endpoint(self):
        """TEST 7 - GET /api/admin/coach-packs - Endpoint public"""
        response = requests.get(f"{BASE_URL}/api/admin/coach-packs")
        assert response.status_code == 200
        packs = response.json()
        assert isinstance(packs, list)
        print(f"✅ TEST 7 - Coach packs public: {len(packs)} packs")
    
    def test_coach_packs_super_admin(self):
        """TEST 8 - GET /api/admin/coach-packs/all - Super Admin"""
        response = requests.get(
            f"{BASE_URL}/api/admin/coach-packs/all",
            headers={"X-User-Email": "contact.artboost@gmail.com"}
        )
        assert response.status_code == 200
        packs = response.json()
        assert isinstance(packs, list)
        print(f"✅ TEST 8 - Coach packs (Super Admin): {len(packs)} packs")
    
    def test_coach_packs_non_admin_forbidden(self):
        """TEST 9 - GET /api/admin/coach-packs/all - Non-admin = 403"""
        response = requests.get(
            f"{BASE_URL}/api/admin/coach-packs/all",
            headers={"X-User-Email": "user@example.com"}
        )
        assert response.status_code == 403
        print("✅ TEST 9 - Non-admin forbidden pour /all")


class TestSuperAdminPanel:
    """Tests pour le Super Admin Panel v8.9.3"""
    
    def test_admin_coaches_list(self):
        """TEST 10 - GET /api/admin/coaches - Liste des coachs"""
        response = requests.get(
            f"{BASE_URL}/api/admin/coaches",
            headers={"X-User-Email": "contact.artboost@gmail.com"}
        )
        assert response.status_code == 200
        coaches = response.json()
        assert isinstance(coaches, list)
        print(f"✅ TEST 10 - Admin coaches list: {len(coaches)} coachs")
    
    def test_auth_role_super_admin(self):
        """TEST 11 - GET /api/auth/role - Super Admin role"""
        response = requests.get(
            f"{BASE_URL}/api/auth/role",
            headers={"X-User-Email": "contact.artboost@gmail.com"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("role") == "super_admin"
        print(f"✅ TEST 11 - Super Admin role vérifié")
    
    def test_auth_role_regular_user(self):
        """TEST 12 - GET /api/auth/role - Regular user role"""
        response = requests.get(
            f"{BASE_URL}/api/auth/role",
            headers={"X-User-Email": "user@example.com"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("role") == "user"
        print(f"✅ TEST 12 - Regular user role vérifié")


class TestCoachSearch:
    """Tests pour la recherche de coach v8.9.3"""
    
    def test_coach_search_empty(self):
        """TEST 13 - GET /api/coaches/search?q= - Recherche vide"""
        response = requests.get(f"{BASE_URL}/api/coaches/search?q=")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✅ TEST 13 - Coach search empty: {len(data)} résultats")
    
    def test_coach_search_short_query(self):
        """TEST 14 - GET /api/coaches/search?q=a - Requête trop courte"""
        response = requests.get(f"{BASE_URL}/api/coaches/search?q=a")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 0  # Minimum 2 caractères requis
        print("✅ TEST 14 - Coach search short query returns empty")
    
    def test_coach_search_valid(self):
        """TEST 15 - GET /api/coaches/search?q=test - Recherche valide"""
        response = requests.get(f"{BASE_URL}/api/coaches/search?q=test")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✅ TEST 15 - Coach search 'test': {len(data)} résultats")


class TestStripeConnect:
    """Tests pour Stripe Connect v8.9.3"""
    
    def test_stripe_connect_onboard_missing_email(self):
        """TEST 16 - POST /api/coach/stripe-connect/onboard - Email manquant"""
        response = requests.post(
            f"{BASE_URL}/api/coach/stripe-connect/onboard",
            json={}
        )
        assert response.status_code == 400
        print("✅ TEST 16 - Stripe Connect onboard: email requis")
    
    def test_stripe_connect_status_no_email(self):
        """TEST 17 - GET /api/coach/stripe-connect/status - Sans header email"""
        response = requests.get(f"{BASE_URL}/api/coach/stripe-connect/status")
        assert response.status_code == 401
        print("✅ TEST 17 - Stripe Connect status: header X-User-Email requis")
    
    def test_stripe_connect_status_non_coach(self):
        """TEST 18 - GET /api/coach/stripe-connect/status - Non-coach"""
        response = requests.get(
            f"{BASE_URL}/api/coach/stripe-connect/status",
            headers={"X-User-Email": "nonexistent@example.com"}
        )
        assert response.status_code == 200
        data = response.json()
        # Coach non trouvé = status not_found
        assert data.get("status") in ["not_found", "not_connected", "error"]
        print(f"✅ TEST 18 - Stripe Connect status non-coach: {data.get('status')}")


class TestReservations:
    """Tests pour les réservations v8.9.3"""
    
    def test_reservations_pagination(self):
        """TEST 19 - GET /api/reservations - Pagination"""
        response = requests.get(f"{BASE_URL}/api/reservations?page=1&limit=5")
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "pagination" in data
        assert "page" in data["pagination"]
        assert "total" in data["pagination"]
        print(f"✅ TEST 19 - Reservations pagination: {data['pagination']['total']} total")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
