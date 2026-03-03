"""
Test Suite: Mission v9.3.2 - ÉTANCHÉITÉ TOTALE, MIROIR RÉEL & FIX BOUTON
Tests d'isolation des données (réservations/contacts) entre Super Admin et nouveaux partenaires
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://promo-credits-lab.preview.emergentagent.com').rstrip('/')

# Constants from mission requirements
SUPER_ADMIN_EMAIL = "contact.artboost@gmail.com"
TEST_PARTNER_EMAIL = "nouveau.partenaire@test.com"
EXPECTED_BASSI_RESERVATIONS = 7  # Anti-régression: 7 réservations

@pytest.fixture
def api_session():
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


class TestHealthCheck:
    """Basic API health verification"""
    
    def test_api_health(self, api_session):
        """Test backend health endpoint"""
        response = api_session.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "healthy"
        print(f"✅ API health check passed: {data}")


class TestHomepageDates:
    """Verify homepage courses load with correct dates"""
    
    def test_courses_endpoint(self, api_session):
        """Test courses endpoint returns data"""
        response = api_session.get(f"{BASE_URL}/api/courses")
        assert response.status_code == 200
        courses = response.json()
        assert isinstance(courses, list)
        assert len(courses) >= 1, "At least 1 course expected"
        print(f"✅ Courses loaded: {len(courses)} courses found")
        
        # Log course names
        for course in courses:
            print(f"   - {course.get('name', 'Unknown')} at {course.get('time', 'N/A')}")


class TestReservationsEtancheite:
    """ÉTANCHÉITÉ: Isolation des réservations entre Super Admin et partenaires"""
    
    def test_bassi_sees_all_reservations(self, api_session):
        """Super Admin (Bassi) doit voir toutes les réservations (7 minimum pour anti-régression)"""
        api_session.headers["X-User-Email"] = SUPER_ADMIN_EMAIL
        response = api_session.get(f"{BASE_URL}/api/reservations")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        total_count = data.get("pagination", {}).get("total", 0)
        assert total_count >= EXPECTED_BASSI_RESERVATIONS, \
            f"ANTI-RÉGRESSION FAILED: Bassi devrait voir au moins {EXPECTED_BASSI_RESERVATIONS} réservations, trouvé {total_count}"
        
        print(f"✅ ANTI-RÉGRESSION: Bassi voit {total_count} réservations (attendu >= {EXPECTED_BASSI_RESERVATIONS})")
    
    def test_new_partner_sees_zero_reservations(self, api_session):
        """Un nouveau partenaire doit voir 0 réservation (isolation totale)"""
        api_session.headers["X-User-Email"] = TEST_PARTNER_EMAIL
        response = api_session.get(f"{BASE_URL}/api/reservations")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        total_count = data.get("pagination", {}).get("total", 0)
        reservations = data.get("data", [])
        
        assert total_count == 0, \
            f"ÉTANCHÉITÉ FAILED: Nouveau partenaire devrait voir 0 réservation, trouvé {total_count}"
        assert len(reservations) == 0, \
            f"ÉTANCHÉITÉ FAILED: Nouveau partenaire ne devrait voir aucune donnée, trouvé {len(reservations)}"
        
        print(f"✅ ÉTANCHÉITÉ: Nouveau partenaire ({TEST_PARTNER_EMAIL}) voit {total_count} réservation(s)")


class TestContactsEtancheite:
    """ÉTANCHÉITÉ: Isolation des contacts (chat_participants) entre coachs"""
    
    def test_bassi_sees_contacts(self, api_session):
        """Super Admin (Bassi) doit voir ses contacts (8 attendus)"""
        api_session.headers["X-User-Email"] = SUPER_ADMIN_EMAIL
        response = api_session.get(f"{BASE_URL}/api/chat/participants")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        # La réponse peut être une liste ou un objet avec une liste
        participants = data if isinstance(data, list) else data.get("participants", data.get("data", []))
        
        assert len(participants) >= 1, \
            f"Bassi devrait voir au moins 1 contact, trouvé {len(participants)}"
        
        print(f"✅ Bassi voit {len(participants)} contact(s)")
    
    def test_new_partner_sees_zero_contacts(self, api_session):
        """Un nouveau partenaire doit voir 0 contact (isolation totale)"""
        api_session.headers["X-User-Email"] = TEST_PARTNER_EMAIL
        response = api_session.get(f"{BASE_URL}/api/chat/participants")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        # La réponse peut être une liste ou un objet avec une liste
        participants = data if isinstance(data, list) else data.get("participants", data.get("data", []))
        
        assert len(participants) == 0, \
            f"ÉTANCHÉITÉ CONTACTS FAILED: Nouveau partenaire devrait voir 0 contact, trouvé {len(participants)}"
        
        print(f"✅ ÉTANCHÉITÉ CONTACTS: Nouveau partenaire ({TEST_PARTNER_EMAIL}) voit {len(participants)} contact(s)")


class TestCheckPartnerAPI:
    """API /check-partner - Vérification côté serveur du statut partenaire"""
    
    def test_registered_coach_is_partner(self, api_session):
        """Un coach inscrit doit retourner is_partner=true"""
        # Tester avec l'email de bassicustomshoes qui est un coach inscrit (Henri BASSI)
        coach_email = "bassicustomshoes@gmail.com"
        response = api_session.get(f"{BASE_URL}/api/check-partner/{coach_email}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        assert data.get("is_partner") == True, \
            f"Coach inscrit devrait être partenaire, trouvé: {data}"
        
        print(f"✅ /check-partner/{coach_email} retourne is_partner=true")
        print(f"   Détails: {data}")
    
    def test_unknown_email_is_not_partner(self, api_session):
        """Un email non inscrit doit retourner is_partner=false"""
        test_email = "unknown.user.test123@nowhere.com"
        response = api_session.get(f"{BASE_URL}/api/check-partner/{test_email}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        assert data.get("is_partner") == False, \
            f"Email inconnu ne devrait pas être partenaire, trouvé: {data}"
        
        print(f"✅ /check-partner/{test_email} retourne is_partner=false")


class TestVitrineAPI:
    """API Vitrine coach - Vérification des endpoints vitrine"""
    
    def test_coach_vitrine_exists(self, api_session):
        """Test qu'une vitrine coach peut être récupérée"""
        # Utiliser le Super Admin comme test (devrait avoir une vitrine)
        response = api_session.get(f"{BASE_URL}/api/coach/vitrine/{SUPER_ADMIN_EMAIL}")
        
        # La vitrine peut exister (200) ou non (404)
        assert response.status_code in [200, 404], f"Unexpected status: {response.status_code}"
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Vitrine trouvée pour {SUPER_ADMIN_EMAIL}")
            print(f"   Coach: {data.get('coach', {}).get('name', 'N/A')}")
            print(f"   Offres: {len(data.get('offers', []))} offres")
            print(f"   Cours: {len(data.get('courses', []))} cours")
        else:
            print(f"ℹ️ Pas de vitrine configurée pour {SUPER_ADMIN_EMAIL} (404)")


class TestConceptAPI:
    """API Concept - Configuration du concept coach (vidéo header)"""
    
    def test_concept_endpoint(self, api_session):
        """Test endpoint concept avec header X-User-Email"""
        api_session.headers["X-User-Email"] = SUPER_ADMIN_EMAIL
        response = api_session.get(f"{BASE_URL}/api/concept")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        print(f"✅ Concept chargé:")
        print(f"   App Name: {data.get('appName', 'N/A')}")
        print(f"   Hero Image URL: {data.get('heroImageUrl', 'N/A')[:50]}..." if data.get('heroImageUrl') else "   Hero Image URL: Non configuré")
        print(f"   Hero Video URL: {data.get('heroVideoUrl', 'N/A')[:50]}..." if data.get('heroVideoUrl') else "   Hero Video URL: Non configuré")


class TestPaymentLinksAPI:
    """API Payment Links - Configuration des liens de paiement"""
    
    def test_payment_links_endpoint(self, api_session):
        """Test endpoint payment-links"""
        response = api_session.get(f"{BASE_URL}/api/payment-links/{SUPER_ADMIN_EMAIL}")
        
        assert response.status_code in [200, 404], f"Unexpected status: {response.status_code}"
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Liens de paiement configurés:")
            print(f"   Stripe: {'Oui' if data.get('stripe') else 'Non'}")
            print(f"   Twint: {'Oui' if data.get('twint') else 'Non'}")
            print(f"   PayPal: {'Oui' if data.get('paypal') else 'Non'}")
        else:
            print(f"ℹ️ Pas de liens de paiement configurés pour {SUPER_ADMIN_EMAIL}")


class TestDiscountCodesAPI:
    """API Codes Promo - Validation des codes"""
    
    def test_discount_validate_endpoint(self, api_session):
        """Test endpoint de validation de code promo"""
        response = api_session.post(
            f"{BASE_URL}/api/discount-codes/validate",
            json={"code": "TESTCODE123", "coach_id": SUPER_ADMIN_EMAIL}
        )
        
        # Le code peut être valide (200) ou invalide, mais l'endpoint doit répondre
        assert response.status_code in [200, 400, 404], f"Unexpected status: {response.status_code}"
        
        data = response.json()
        print(f"✅ Validation code promo response: {data.get('valid', False)}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
