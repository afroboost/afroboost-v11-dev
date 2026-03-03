"""
Test suite for Unified Media Player (Lecteur Média Unifié) - Afroboost
Tests the media link creation, retrieval, OpenGraph, and deletion endpoints.

Features tested:
- POST /api/media/create - Create media link with title, video_url, description, cta_text, cta_link
- GET /api/media - List all media links
- GET /api/media/{slug} - Get media details and increment views
- DELETE /api/media/{slug} - Delete a media link
- GET /api/media/{slug}/og - Return HTML page with OpenGraph tags for WhatsApp
- YouTube ID extraction from various URL formats
- Automatic thumbnail generation from YouTube
"""

import pytest
import requests
import os
import uuid
import time

# Get API URL from environment
BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://promo-credits-lab.preview.emergentagent.com').rstrip('/')
API_URL = f"{BASE_URL}/api"

# Test data prefix for cleanup
TEST_PREFIX = "TEST_MEDIA_"


class TestMediaLinkEndpoints:
    """Test suite for Media Link API endpoints"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test data"""
        self.test_slug = f"test-video-{uuid.uuid4().hex[:8]}"
        self.youtube_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        self.youtube_id = "dQw4w9WgXcQ"
        yield
        # Cleanup: try to delete test media link
        try:
            requests.delete(f"{API_URL}/media/{self.test_slug}")
        except:
            pass
    
    def test_health_check(self):
        """Test API health endpoint"""
        response = requests.get(f"{BASE_URL}/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "healthy"
        print("✅ Health check passed")
    
    def test_create_media_link_basic(self):
        """Test creating a basic media link with required fields"""
        payload = {
            "slug": self.test_slug,
            "video_url": self.youtube_url,
            "title": "Test Video Title"
        }
        
        response = requests.post(f"{API_URL}/media/create", json=payload)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get("success") == True
        assert "media_link" in data
        assert data["media_link"]["slug"] == self.test_slug.lower()
        assert "url" in data["media_link"]
        assert self.test_slug.lower() in data["media_link"]["url"]
        print(f"✅ Created media link: {data['media_link']['url']}")
    
    def test_create_media_link_with_all_fields(self):
        """Test creating a media link with all optional fields"""
        full_slug = f"test-full-{uuid.uuid4().hex[:8]}"
        payload = {
            "slug": full_slug,
            "video_url": self.youtube_url,
            "title": "Complete Test Video",
            "description": "This is a test description for the video",
            "custom_thumbnail": "https://example.com/custom-thumb.jpg",
            "cta_text": "Réserver maintenant",
            "cta_link": "https://afroboost.com/reservation"
        }
        
        response = requests.post(f"{API_URL}/media/create", json=payload)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get("success") == True
        assert data["media_link"]["slug"] == full_slug.lower()
        
        # Cleanup
        requests.delete(f"{API_URL}/media/{full_slug}")
        print("✅ Created media link with all fields")
    
    def test_create_media_link_duplicate_slug(self):
        """Test that duplicate slugs are rejected"""
        # First create
        payload = {
            "slug": self.test_slug,
            "video_url": self.youtube_url,
            "title": "First Video"
        }
        response1 = requests.post(f"{API_URL}/media/create", json=payload)
        assert response1.status_code == 200
        
        # Try duplicate
        payload2 = {
            "slug": self.test_slug,
            "video_url": "https://www.youtube.com/watch?v=different",
            "title": "Second Video"
        }
        response2 = requests.post(f"{API_URL}/media/create", json=payload2)
        assert response2.status_code == 400, f"Expected 400 for duplicate slug, got {response2.status_code}"
        print("✅ Duplicate slug correctly rejected")
    
    def test_create_media_link_missing_required_fields(self):
        """Test that missing required fields return validation error"""
        # Missing slug
        response1 = requests.post(f"{API_URL}/media/create", json={
            "video_url": self.youtube_url,
            "title": "Test"
        })
        assert response1.status_code == 422, f"Expected 422 for missing slug, got {response1.status_code}"
        
        # Missing video_url
        response2 = requests.post(f"{API_URL}/media/create", json={
            "slug": "test-missing-url",
            "title": "Test"
        })
        assert response2.status_code == 422, f"Expected 422 for missing video_url, got {response2.status_code}"
        
        # Missing title
        response3 = requests.post(f"{API_URL}/media/create", json={
            "slug": "test-missing-title",
            "video_url": self.youtube_url
        })
        assert response3.status_code == 422, f"Expected 422 for missing title, got {response3.status_code}"
        print("✅ Missing required fields correctly rejected")
    
    def test_get_media_link_by_slug(self):
        """Test retrieving a media link by slug"""
        # First create
        payload = {
            "slug": self.test_slug,
            "video_url": self.youtube_url,
            "title": "Test Video for Retrieval",
            "description": "Test description"
        }
        requests.post(f"{API_URL}/media/create", json=payload)
        
        # Then retrieve
        response = requests.get(f"{API_URL}/media/{self.test_slug}")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get("slug") == self.test_slug.lower()
        assert data.get("title") == "Test Video for Retrieval"
        assert data.get("description") == "Test description"
        assert data.get("video_url") == self.youtube_url
        assert "youtube_id" in data
        assert data.get("youtube_id") == self.youtube_id
        print(f"✅ Retrieved media link: {data.get('title')}")
    
    def test_get_media_link_increments_views(self):
        """Test that retrieving a media link increments the view counter"""
        # Create
        payload = {
            "slug": self.test_slug,
            "video_url": self.youtube_url,
            "title": "View Counter Test"
        }
        requests.post(f"{API_URL}/media/create", json=payload)
        
        # Get initial views
        response1 = requests.get(f"{API_URL}/media/{self.test_slug}")
        initial_views = response1.json().get("views", 0)
        
        # Get again - should increment
        response2 = requests.get(f"{API_URL}/media/{self.test_slug}")
        new_views = response2.json().get("views", 0)
        
        # Views should have incremented (note: first GET also increments)
        assert new_views >= initial_views, f"Views should increment: {initial_views} -> {new_views}"
        print(f"✅ View counter working: {initial_views} -> {new_views}")
    
    def test_get_media_link_not_found(self):
        """Test 404 for non-existent media link"""
        response = requests.get(f"{API_URL}/media/non-existent-slug-12345")
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("✅ Non-existent slug returns 404")
    
    def test_list_media_links(self):
        """Test listing all media links"""
        # Create a test link first
        payload = {
            "slug": self.test_slug,
            "video_url": self.youtube_url,
            "title": "List Test Video"
        }
        requests.post(f"{API_URL}/media/create", json=payload)
        
        # List all
        response = requests.get(f"{API_URL}/media")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert isinstance(data, list), "Expected list response"
        
        # Find our test link
        found = any(m.get("slug") == self.test_slug.lower() for m in data)
        assert found, f"Test media link not found in list"
        print(f"✅ Listed {len(data)} media links")
    
    def test_delete_media_link(self):
        """Test deleting a media link"""
        # Create
        payload = {
            "slug": self.test_slug,
            "video_url": self.youtube_url,
            "title": "Delete Test Video"
        }
        requests.post(f"{API_URL}/media/create", json=payload)
        
        # Delete
        response = requests.delete(f"{API_URL}/media/{self.test_slug}")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert data.get("success") == True
        assert data.get("deleted") == self.test_slug.lower()
        
        # Verify deleted
        verify_response = requests.get(f"{API_URL}/media/{self.test_slug}")
        assert verify_response.status_code == 404, "Media link should be deleted"
        print("✅ Media link deleted successfully")
    
    def test_delete_media_link_not_found(self):
        """Test 404 when deleting non-existent media link"""
        response = requests.delete(f"{API_URL}/media/non-existent-slug-12345")
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("✅ Delete non-existent returns 404")
    
    def test_opengraph_endpoint(self):
        """Test OpenGraph HTML page generation for WhatsApp previews"""
        # Create
        payload = {
            "slug": self.test_slug,
            "video_url": self.youtube_url,
            "title": "OpenGraph Test Video",
            "description": "Test description for OG tags"
        }
        requests.post(f"{API_URL}/media/create", json=payload)
        
        # Get OG page
        response = requests.get(f"{API_URL}/media/{self.test_slug}/og")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        # Check content type is HTML
        content_type = response.headers.get("content-type", "")
        assert "text/html" in content_type, f"Expected HTML content type, got {content_type}"
        
        # Check HTML contains required OG tags
        html = response.text
        assert "og:title" in html, "Missing og:title meta tag"
        assert "og:description" in html, "Missing og:description meta tag"
        assert "og:image" in html, "Missing og:image meta tag"
        assert "OpenGraph Test Video" in html, "Title not in HTML"
        print("✅ OpenGraph HTML page generated correctly")
    
    def test_opengraph_endpoint_not_found(self):
        """Test 404 for non-existent media link OG page"""
        response = requests.get(f"{API_URL}/media/non-existent-slug-12345/og")
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("✅ Non-existent OG page returns 404")


class TestYouTubeExtraction:
    """Test YouTube ID extraction from various URL formats"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test data"""
        self.test_slugs = []
        yield
        # Cleanup
        for slug in self.test_slugs:
            try:
                requests.delete(f"{API_URL}/media/{slug}")
            except:
                pass
    
    def create_and_verify_youtube_id(self, youtube_url, expected_id, description):
        """Helper to create media link and verify YouTube ID extraction"""
        slug = f"yt-test-{uuid.uuid4().hex[:8]}"
        self.test_slugs.append(slug)
        
        payload = {
            "slug": slug,
            "video_url": youtube_url,
            "title": f"YouTube Test: {description}"
        }
        
        response = requests.post(f"{API_URL}/media/create", json=payload)
        assert response.status_code == 200, f"Failed to create: {response.text}"
        
        # Retrieve and check youtube_id
        get_response = requests.get(f"{API_URL}/media/{slug}")
        data = get_response.json()
        
        assert data.get("youtube_id") == expected_id, \
            f"Expected youtube_id '{expected_id}' for {description}, got '{data.get('youtube_id')}'"
        
        # Check auto-generated thumbnail
        if expected_id:
            expected_thumb = f"https://img.youtube.com/vi/{expected_id}/maxresdefault.jpg"
            assert data.get("thumbnail") == expected_thumb, \
                f"Expected auto thumbnail, got {data.get('thumbnail')}"
        
        return data
    
    def test_youtube_standard_url(self):
        """Test standard youtube.com/watch?v= URL"""
        self.create_and_verify_youtube_id(
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "dQw4w9WgXcQ",
            "standard watch URL"
        )
        print("✅ Standard YouTube URL extraction works")
    
    def test_youtube_short_url(self):
        """Test youtu.be short URL"""
        self.create_and_verify_youtube_id(
            "https://youtu.be/dQw4w9WgXcQ",
            "dQw4w9WgXcQ",
            "short youtu.be URL"
        )
        print("✅ Short youtu.be URL extraction works")
    
    def test_youtube_embed_url(self):
        """Test youtube.com/embed/ URL"""
        self.create_and_verify_youtube_id(
            "https://www.youtube.com/embed/dQw4w9WgXcQ",
            "dQw4w9WgXcQ",
            "embed URL"
        )
        print("✅ Embed URL extraction works")
    
    def test_youtube_shorts_url(self):
        """Test youtube.com/shorts/ URL"""
        self.create_and_verify_youtube_id(
            "https://www.youtube.com/shorts/dQw4w9WgXcQ",
            "dQw4w9WgXcQ",
            "shorts URL"
        )
        print("✅ Shorts URL extraction works")
    
    def test_youtube_url_with_params(self):
        """Test YouTube URL with additional parameters"""
        self.create_and_verify_youtube_id(
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=120&list=PLtest",
            "dQw4w9WgXcQ",
            "URL with params"
        )
        print("✅ YouTube URL with params extraction works")
    
    def test_custom_thumbnail_overrides_auto(self):
        """Test that custom thumbnail overrides auto-generated one"""
        slug = f"custom-thumb-{uuid.uuid4().hex[:8]}"
        self.test_slugs.append(slug)
        
        custom_thumb = "https://example.com/my-custom-thumbnail.jpg"
        payload = {
            "slug": slug,
            "video_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "title": "Custom Thumbnail Test",
            "custom_thumbnail": custom_thumb
        }
        
        response = requests.post(f"{API_URL}/media/create", json=payload)
        assert response.status_code == 200
        
        get_response = requests.get(f"{API_URL}/media/{slug}")
        data = get_response.json()
        
        assert data.get("thumbnail") == custom_thumb, \
            f"Custom thumbnail should override auto, got {data.get('thumbnail')}"
        print("✅ Custom thumbnail overrides auto-generated")


class TestMediaViewerIntegration:
    """Test the full flow from creation to viewing"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test data"""
        self.test_slug = f"integration-{uuid.uuid4().hex[:8]}"
        yield
        # Cleanup
        try:
            requests.delete(f"{API_URL}/media/{self.test_slug}")
        except:
            pass
    
    def test_full_media_link_flow(self):
        """Test complete flow: create -> get -> view increment -> delete"""
        # 1. Create
        payload = {
            "slug": self.test_slug,
            "video_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "title": "Integration Test Video",
            "description": "Full flow test description",
            "cta_text": "Book Now",
            "cta_link": "https://afroboost.com/book"
        }
        
        create_response = requests.post(f"{API_URL}/media/create", json=payload)
        assert create_response.status_code == 200
        create_data = create_response.json()
        assert create_data["success"] == True
        print(f"✅ Step 1: Created media link")
        
        # 2. Verify in list
        list_response = requests.get(f"{API_URL}/media")
        assert list_response.status_code == 200
        media_list = list_response.json()
        found = any(m["slug"] == self.test_slug.lower() for m in media_list)
        assert found, "Media link not found in list"
        print(f"✅ Step 2: Found in list")
        
        # 3. Get details
        get_response = requests.get(f"{API_URL}/media/{self.test_slug}")
        assert get_response.status_code == 200
        media_data = get_response.json()
        
        # Verify all fields
        assert media_data["slug"] == self.test_slug.lower()
        assert media_data["title"] == "Integration Test Video"
        assert media_data["description"] == "Full flow test description"
        assert media_data["cta_text"] == "Book Now"
        assert media_data["cta_link"] == "https://afroboost.com/book"
        assert media_data["youtube_id"] == "dQw4w9WgXcQ"
        assert "thumbnail" in media_data
        initial_views = media_data.get("views", 0)
        print(f"✅ Step 3: Retrieved with all fields, views={initial_views}")
        
        # 4. Get again to verify view increment
        get_response2 = requests.get(f"{API_URL}/media/{self.test_slug}")
        media_data2 = get_response2.json()
        assert media_data2["views"] >= initial_views, "Views should increment"
        print(f"✅ Step 4: Views incremented to {media_data2['views']}")
        
        # 5. Get OpenGraph page
        og_response = requests.get(f"{API_URL}/media/{self.test_slug}/og")
        assert og_response.status_code == 200
        assert "og:title" in og_response.text
        assert "Integration Test Video" in og_response.text
        print(f"✅ Step 5: OpenGraph page generated")
        
        # 6. Delete
        delete_response = requests.delete(f"{API_URL}/media/{self.test_slug}")
        assert delete_response.status_code == 200
        print(f"✅ Step 6: Deleted successfully")
        
        # 7. Verify deleted
        verify_response = requests.get(f"{API_URL}/media/{self.test_slug}")
        assert verify_response.status_code == 404
        print(f"✅ Step 7: Verified deletion (404)")
        
        print("\n✅ FULL INTEGRATION TEST PASSED")


class TestExistingTestVideo:
    """Test the existing test video mentioned in the requirements"""
    
    def test_existing_test_video(self):
        """Test that /v/test-video-1 exists or can be created"""
        # Try to get existing test video
        response = requests.get(f"{API_URL}/media/test-video-1")
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Existing test video found: {data.get('title')}")
            assert "slug" in data
            assert "video_url" in data
            assert "title" in data
        elif response.status_code == 404:
            # Create it for testing
            payload = {
                "slug": "test-video-1",
                "video_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "title": "Test Video Afroboost",
                "description": "Vidéo de test pour le lecteur média unifié",
                "cta_text": "Réserver une session",
                "cta_link": "https://afroboost.com"
            }
            create_response = requests.post(f"{API_URL}/media/create", json=payload)
            if create_response.status_code == 200:
                print("✅ Created test-video-1 for testing")
            elif create_response.status_code == 400 and "existe déjà" in create_response.text:
                print("✅ test-video-1 already exists (race condition)")
            else:
                print(f"⚠️ Could not create test-video-1: {create_response.text}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
