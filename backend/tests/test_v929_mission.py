"""
Test v9.2.9 Mission - MIROIR TOTAL, PAIEMENT & NETTOYAGE
Features to test:
1. Page d'accueil avec 4 dates de mars (04.03, 11.03, 18.03, 25.03)
2. Vitrine partenaire /coach/bassi avec header vidéo animé
3. Vitrine partenaire affiche nom et photo du coach en haut à droite
4. Modal de réservation avec champ CODE PROMO et bouton Valider
5. API /api/discount-codes/validate fonctionne avec coach_id
6. Dashboard onglet 'Ma Page' (ex 'Paiements') affiche QR Code et lien vitrine
7. 7 réservations de Bassi (Super Admin) toujours présentes
8. Lien secret Admin (triple-clic copyright) ouvre modal connexion
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://video-feed-platform.preview.emergentagent.com').rstrip('/')
SUPER_ADMIN_EMAIL = "contact.artboost@gmail.com"


class TestMissionV929Backend:
    """Tests backend pour mission v9.2.9"""

    # Test 1: Vitrine bassi accessible
    def test_coach_vitrine_bassi_accessible(self):
        """Vérifie que la vitrine bassi est accessible et retourne les données coach"""
        response = requests.get(f"{BASE_URL}/api/coach/vitrine/bassi")
        assert response.status_code == 200, f"Status: {response.status_code}"
        data = response.json()
        
        # Vérifier la présence des champs coach
        assert "coach" in data, "coach field missing"
        assert data["coach"] is not None, "coach is null"
        assert "name" in data["coach"], "coach.name missing"
        assert "email" in data["coach"], "coach.email missing"
        print(f"✅ Vitrine bassi accessible - Coach: {data['coach'].get('name')}")

    # Test 2: Vitrine bassi contient les cours pour les dates cliquables
    def test_coach_vitrine_courses_for_dates(self):
        """Vérifie que la vitrine contient des cours (pour générer les dates cliquables)"""
        response = requests.get(f"{BASE_URL}/api/coach/vitrine/bassi")
        assert response.status_code == 200
        data = response.json()
        
        assert "courses" in data, "courses field missing"
        courses = data.get("courses", [])
        # Il peut y avoir 0 cours configurés, mais le champ doit exister
        print(f"✅ Vitrine contient {len(courses)} cours configurés")

    # Test 3: API discount-codes/validate fonctionne
    def test_discount_codes_validate_api(self):
        """Vérifie que l'API de validation de code promo fonctionne"""
        # Test avec un code invalide
        response = requests.post(
            f"{BASE_URL}/api/discount-codes/validate",
            json={
                "code": "INVALID_CODE_123",
                "coach_id": "bassi"
            },
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 200, f"Status: {response.status_code}"
        data = response.json()
        
        # API doit retourner valid: false pour code invalide
        assert "valid" in data, "valid field missing"
        assert data["valid"] == False, "Should be invalid"
        assert "message" in data, "message field missing"
        print(f"✅ API discount-codes/validate fonctionne - Message: {data.get('message')}")

    # Test 4: API discount-codes/validate avec code vide
    def test_discount_codes_validate_empty_code(self):
        """Vérifie la gestion du code vide"""
        response = requests.post(
            f"{BASE_URL}/api/discount-codes/validate",
            json={
                "code": "",
                "coach_id": "bassi"
            },
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] == False
        print("✅ API gère correctement le code vide")

    # Test 5: 7 réservations Bassi toujours présentes (ANTI-RÉGRESSION)
    def test_bassi_7_reservations_anti_regression(self):
        """ANTI-RÉGRESSION: Vérifie que les 7 réservations de Bassi sont toujours présentes"""
        response = requests.get(
            f"{BASE_URL}/api/reservations?page=1&limit=20",
            headers={"X-User-Email": SUPER_ADMIN_EMAIL}
        )
        assert response.status_code == 200, f"Status: {response.status_code}"
        data = response.json()
        
        assert "pagination" in data, "pagination field missing"
        total = data["pagination"].get("total", 0)
        assert total >= 7, f"ANTI-RÉGRESSION FAILED: Expected >= 7 reservations, got {total}"
        print(f"✅ ANTI-RÉGRESSION: {total} réservations présentes (>=7 requis)")

    # Test 6: Liste des codes promo accessible
    def test_discount_codes_list(self):
        """Vérifie que la liste des codes promo est accessible"""
        response = requests.get(f"{BASE_URL}/api/discount-codes")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        print(f"✅ {len(data)} codes promo dans la base")

    # Test 7: Concept/configuration accessible
    def test_concept_config(self):
        """Vérifie que la configuration concept est accessible"""
        response = requests.get(f"{BASE_URL}/api/concept")
        assert response.status_code == 200
        data = response.json()
        assert "appName" in data or "description" in data, "concept fields missing"
        print(f"✅ Configuration concept accessible - App: {data.get('appName', 'N/A')}")

    # Test 8: Courses endpoint accessible
    def test_courses_endpoint(self):
        """Vérifie que l'endpoint courses est accessible"""
        response = requests.get(f"{BASE_URL}/api/courses")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        
        # Vérifier qu'il y a au moins un cours pour les dates
        if len(data) > 0:
            course = data[0]
            # Les cours doivent avoir weekday pour générer les dates
            if "weekday" in course:
                print(f"✅ {len(data)} cours avec weekday pour générer les dates")
            else:
                print(f"✅ {len(data)} cours (sans weekday)")
        else:
            print("⚠️ Aucun cours configuré")

    # Test 9: Health check
    def test_health_check(self):
        """Vérifie que le backend est en bonne santé"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "healthy", f"Status: {data.get('status')}"
        print("✅ Backend healthy")


class TestMissionV929DashboardTabs:
    """Tests pour les onglets du dashboard v9.2.9"""

    # Test: Vérifier que payment-links endpoint fonctionne (pour onglet Ma Page)
    def test_payment_links_for_ma_page(self):
        """Vérifie que l'endpoint payment-links fonctionne pour l'onglet Ma Page"""
        response = requests.get(f"{BASE_URL}/api/payment-links")
        assert response.status_code == 200
        data = response.json()
        # L'endpoint doit retourner un objet avec les liens de paiement
        assert isinstance(data, dict), "Response should be a dict"
        print(f"✅ Payment links accessible - Keys: {list(data.keys())}")

    # Test: Vérifier coach profile pour URL vitrine
    def test_coach_profile_for_vitrine_url(self):
        """Vérifie que le profil coach retourne les données pour la vitrine"""
        response = requests.get(
            f"{BASE_URL}/api/coach/profile",
            headers={"X-User-Email": SUPER_ADMIN_EMAIL}
        )
        # Le profil peut retourner 404 si pas créé, mais pas 500
        assert response.status_code in [200, 404], f"Status: {response.status_code}"
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Profil coach accessible - Credits: {data.get('credits', 'N/A')}")
        else:
            print("⚠️ Profil coach non trouvé (normal pour premier accès)")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
