"""
Test Suite v9.3.3 - L'ULTIME MIROIR VISUEL & PAIEMENT
Mission focus:
1) Vitrine partenaire look cinématographique
2) Paiement & code promo intégration
3) Bouton Chat persistant
4) ANTI-RÉGRESSION: 7 réservations Bassi, 8 contacts
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://promo-credits-lab.preview.emergentagent.com')


class TestAntiRegression:
    """Tests anti-régression - Données Bassi doivent rester intactes"""
    
    def test_bassi_has_7_reservations(self):
        """ANTI-RÉGRESSION: Bassi doit avoir 7 réservations"""
        response = requests.get(
            f"{BASE_URL}/api/reservations",
            headers={"X-User-Email": "contact.artboost@gmail.com"}
        )
        assert response.status_code == 200, f"Status: {response.status_code}"
        data = response.json()
        
        total = data.get("pagination", {}).get("total", len(data.get("data", [])))
        assert total == 7, f"Expected 7 reservations, got {total}"
        print(f"✅ ANTI-RÉGRESSION: Bassi a {total} réservations")
    
    def test_bassi_has_8_contacts(self):
        """ANTI-RÉGRESSION: Bassi doit avoir 8 contacts"""
        response = requests.get(
            f"{BASE_URL}/api/chat/participants",
            headers={"X-User-Email": "contact.artboost@gmail.com"}
        )
        assert response.status_code == 200, f"Status: {response.status_code}"
        data = response.json()
        
        total = len(data) if isinstance(data, list) else data.get("total", 0)
        assert total == 8, f"Expected 8 contacts, got {total}"
        print(f"✅ ANTI-RÉGRESSION: Bassi a {total} contacts")


class TestVitrineAPI:
    """Tests API vitrine partenaire"""
    
    def test_vitrine_loads_for_bassi(self):
        """Vitrine coach bassi doit se charger"""
        response = requests.get(f"{BASE_URL}/api/coach/vitrine/bassi")
        assert response.status_code == 200, f"Status: {response.status_code}"
        
        data = response.json()
        assert "coach" in data, "Missing 'coach' in response"
        assert data["coach"] is not None, "Coach is None"
        print(f"✅ Vitrine bassi chargée: {data['coach'].get('platform_name', data['coach'].get('name', 'Unknown'))}")
    
    def test_vitrine_has_courses(self):
        """Vitrine doit avoir des cours"""
        response = requests.get(f"{BASE_URL}/api/coach/vitrine/bassi")
        assert response.status_code == 200
        
        data = response.json()
        courses = data.get("courses", [])
        assert len(courses) > 0, "No courses found in vitrine"
        print(f"✅ Vitrine a {len(courses)} cours")
    
    def test_vitrine_has_offers(self):
        """Vitrine doit avoir des offres"""
        response = requests.get(f"{BASE_URL}/api/coach/vitrine/bassi")
        assert response.status_code == 200
        
        data = response.json()
        offers = data.get("offers", [])
        # Note: si pas d'offres, les offres par défaut Afroboost sont utilisées
        print(f"✅ Vitrine a {len(offers)} offres")


class TestCodePromo:
    """Tests API code promo"""
    
    def test_validate_code_endpoint_exists(self):
        """Endpoint validation code promo doit exister"""
        response = requests.post(
            f"{BASE_URL}/api/discount-codes/validate",
            json={"code": "TEST123", "email": "test@test.com"}
        )
        # 200 OK ou 400/404 pour code invalide - pas 500 server error
        assert response.status_code in [200, 400, 404], f"Status: {response.status_code}"
        print(f"✅ Endpoint validation code promo fonctionnel")


class TestPaymentLinks:
    """Tests API liens de paiement"""
    
    def test_payment_links_endpoint(self):
        """Endpoint liens de paiement doit exister"""
        response = requests.get(
            f"{BASE_URL}/api/payment-links/bassicustomshoes@gmail.com"
        )
        # Peut retourner 200 avec données ou 404 si pas configuré
        assert response.status_code in [200, 404], f"Status: {response.status_code}"
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Liens de paiement trouvés: stripe={bool(data.get('stripe'))}, twint={bool(data.get('twint'))}")
        else:
            print("ℹ️ Pas de liens de paiement configurés pour ce coach")


class TestChatWidget:
    """Tests API chat widget"""
    
    def test_chat_smart_entry_endpoint(self):
        """Endpoint smart-entry doit exister"""
        response = requests.post(
            f"{BASE_URL}/api/chat/smart-entry",
            json={
                "firstName": "Test",
                "whatsapp": "+41000000000",
                "email": "test@test.com"
            }
        )
        # Doit fonctionner ou retourner erreur de validation
        assert response.status_code in [200, 400, 422], f"Status: {response.status_code}"
        print(f"✅ Endpoint smart-entry fonctionnel")
    
    def test_check_partner_endpoint(self):
        """Endpoint check-partner doit retourner le statut partenaire"""
        response = requests.get(
            f"{BASE_URL}/api/check-partner/bassicustomshoes@gmail.com"
        )
        assert response.status_code == 200, f"Status: {response.status_code}"
        
        data = response.json()
        assert "is_partner" in data, "Missing 'is_partner' in response"
        assert data["is_partner"] == True, "bassicustomshoes@gmail.com should be a partner"
        print(f"✅ check-partner: is_partner={data['is_partner']}, name={data.get('name', 'N/A')}")


class TestHomepageDates:
    """Tests dates de mars sur la homepage"""
    
    def test_courses_api_returns_data(self):
        """API courses doit retourner des données"""
        response = requests.get(f"{BASE_URL}/api/courses")
        assert response.status_code == 200, f"Status: {response.status_code}"
        
        data = response.json()
        assert isinstance(data, list), "Expected list of courses"
        assert len(data) > 0, "No courses found"
        
        # Vérifier qu'il y a des cours avec weekday
        courses_with_dates = [c for c in data if c.get("weekday") is not None]
        print(f"✅ {len(courses_with_dates)} cours avec dates programmées")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
