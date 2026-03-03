"""
Test Suite for Media (YouTube/Google Drive) and CTA Button Validation
Iteration 61 - Opérationnelle Médias et Boutons CTA

Tests:
1. Promo code PROMO20SECRET validation
2. Reservation eligibility check
3. Courses API (reservation calendar dates)
4. Messages sync with YouTube links
5. Messages sync with Google Drive links
6. Messages sync with CTA buttons
7. MediaParser backend module validation
"""

import pytest
import requests
import os
import sys

# Add backend to path for media_handler import
sys.path.insert(0, '/app/backend')
from media_handler import get_media_type, extract_youtube_id, drive_to_direct_url, detect_media_in_text, is_media_url

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://promo-credits-lab.preview.emergentagent.com')

class TestPromoCodeValidation:
    """Test promo code PROMO20SECRET validation"""
    
    def test_promo_code_valid(self):
        """Test PROMO20SECRET code is valid"""
        response = requests.post(f"{BASE_URL}/api/discount-codes/validate", json={
            "code": "PROMO20SECRET",
            "email": "testmedia@test.com"
        })
        assert response.status_code == 200
        data = response.json()
        assert data.get("valid") == True
        assert data.get("code", {}).get("code") == "PROMO20SECRET"
        assert data.get("code", {}).get("type") == "percent"
        assert data.get("code", {}).get("value") == 20
        print("✅ PROMO20SECRET valid: 20% discount")
    
    def test_invalid_promo_code(self):
        """Test invalid promo code rejected"""
        response = requests.post(f"{BASE_URL}/api/discount-codes/validate", json={
            "code": "INVALID123",
            "email": "test@test.com"
        })
        assert response.status_code == 200
        data = response.json()
        assert data.get("valid") == False
        print("✅ Invalid code correctly rejected")


class TestReservationEligibility:
    """Test reservation eligibility with promo code"""
    
    def test_eligibility_with_valid_code(self):
        """Test reservation eligibility with PROMO20SECRET"""
        response = requests.post(f"{BASE_URL}/api/check-reservation-eligibility", json={
            "code": "PROMO20SECRET",
            "email": "testmedia@test.com"
        })
        assert response.status_code == 200
        data = response.json()
        assert data.get("canReserve") == True
        assert data.get("code") == "PROMO20SECRET"
        assert data.get("type") == "percent"
        assert data.get("value") == 20
        print(f"✅ Reservation eligible: {data.get('remaining')} uses remaining")


class TestCoursesAPI:
    """Test courses API for reservation calendar"""
    
    def test_courses_list(self):
        """Test courses API returns data"""
        response = requests.get(f"{BASE_URL}/api/courses")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✅ Courses API returned {len(data)} courses")
        
        # Verify course structure
        for course in data:
            assert "id" in course
            assert "name" in course
            assert "time" in course
            print(f"  - Course: {course.get('name')} at {course.get('time')}")


class TestMessagesSyncWithMedia:
    """Test messages/sync endpoint with media content"""
    
    def test_sync_youtube_message(self):
        """Test sync returns messages with YouTube links"""
        response = requests.get(f"{BASE_URL}/api/messages/sync", params={
            "session_id": "5b49c35b-4a6f-4b75-9891-4e12d2e9a33e"
        })
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") == True
        assert "messages" in data
        
        # Find YouTube message
        youtube_msgs = [m for m in data["messages"] if "youtube.com" in m.get("text", "") or "youtu.be" in m.get("text", "")]
        assert len(youtube_msgs) > 0, "Should have at least one YouTube message"
        
        youtube_msg = youtube_msgs[0]
        assert "youtube.com/watch?v=" in youtube_msg["text"]
        print(f"✅ YouTube message found: {youtube_msg['text'][:50]}...")
    
    def test_sync_drive_message(self):
        """Test sync returns messages with Google Drive links"""
        response = requests.get(f"{BASE_URL}/api/messages/sync", params={
            "session_id": "5b49c35b-4a6f-4b75-9891-4e12d2e9a33e"
        })
        assert response.status_code == 200
        data = response.json()
        
        # Find Drive message
        drive_msgs = [m for m in data["messages"] if "drive.google.com" in m.get("text", "")]
        assert len(drive_msgs) > 0, "Should have at least one Drive message"
        
        drive_msg = drive_msgs[0]
        assert "drive.google.com/file/d/" in drive_msg["text"]
        print(f"✅ Google Drive message found: {drive_msg['text'][:50]}...")
    
    def test_sync_cta_message(self):
        """Test sync returns messages with CTA buttons"""
        response = requests.get(f"{BASE_URL}/api/messages/sync", params={
            "session_id": "5b49c35b-4a6f-4b75-9891-4e12d2e9a33e"
        })
        assert response.status_code == 200
        data = response.json()
        
        # Find CTA message
        cta_msgs = [m for m in data["messages"] if m.get("cta_text")]
        assert len(cta_msgs) > 0, "Should have at least one CTA message"
        
        cta_msg = cta_msgs[0]
        assert cta_msg.get("cta_text") is not None
        assert cta_msg.get("cta_link") is not None
        print(f"✅ CTA message found: {cta_msg['cta_text']} -> {cta_msg['cta_link']}")
    
    def test_sync_with_timestamp(self):
        """Test sync returns server_time_utc for mobile polling"""
        response = requests.get(f"{BASE_URL}/api/messages/sync", params={
            "session_id": "5b49c35b-4a6f-4b75-9891-4e12d2e9a33e"
        })
        assert response.status_code == 200
        data = response.json()
        
        assert "synced_at" in data
        assert "server_time_utc" in data
        print(f"✅ Sync timestamp: {data['server_time_utc']}")


class TestMediaHandlerBackend:
    """Test backend media_handler.py module"""
    
    def test_youtube_detection(self):
        """Test YouTube URL detection"""
        result = get_media_type("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        assert result["type"] == "youtube"
        assert result["video_id"] == "dQw4w9WgXcQ"
        assert "embed_url" in result
        assert "thumbnail_url" in result
        print(f"✅ YouTube detected: {result['video_id']}")
    
    def test_youtube_short_url(self):
        """Test YouTube short URL (youtu.be) detection"""
        result = get_media_type("https://youtu.be/dQw4w9WgXcQ")
        assert result["type"] == "youtube"
        assert result["video_id"] == "dQw4w9WgXcQ"
        print(f"✅ YouTube short URL detected: {result['video_id']}")
    
    def test_youtube_embed_url(self):
        """Test YouTube embed URL detection"""
        result = get_media_type("https://www.youtube.com/embed/dQw4w9WgXcQ")
        assert result["type"] == "youtube"
        assert result["video_id"] == "dQw4w9WgXcQ"
        print(f"✅ YouTube embed URL detected: {result['video_id']}")
    
    def test_youtube_shorts_url(self):
        """Test YouTube Shorts URL detection"""
        result = get_media_type("https://youtube.com/shorts/abcdefghijk")
        assert result["type"] == "youtube"
        assert result["video_id"] == "abcdefghijk"
        print(f"✅ YouTube Shorts URL detected: {result['video_id']}")
    
    def test_drive_file_detection(self):
        """Test Google Drive file URL detection"""
        result = get_media_type("https://drive.google.com/file/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs/view")
        assert result["type"] == "drive"
        assert result["file_id"] == "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs"
        assert "direct_url" in result
        assert "thumbnail_url" in result
        print(f"✅ Google Drive file detected: {result['file_id']}")
    
    def test_drive_open_url(self):
        """Test Google Drive open URL detection"""
        result = get_media_type("https://drive.google.com/open?id=1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs")
        assert result["type"] == "drive"
        assert result["file_id"] == "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs"
        print(f"✅ Google Drive open URL detected: {result['file_id']}")
    
    def test_direct_image_detection(self):
        """Test direct image URL detection"""
        result = get_media_type("https://example.com/image.jpg")
        assert result["type"] == "image"
        assert result["direct_url"] == "https://example.com/image.jpg"
        print(f"✅ Direct image detected: {result['type']}")
    
    def test_extract_youtube_id_function(self):
        """Test extract_youtube_id helper function"""
        video_id = extract_youtube_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        assert video_id == "dQw4w9WgXcQ"
        print(f"✅ extract_youtube_id: {video_id}")
    
    def test_drive_to_direct_url_function(self):
        """Test drive_to_direct_url helper function"""
        direct_url = drive_to_direct_url("https://drive.google.com/file/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs/view")
        assert direct_url == "https://drive.google.com/uc?export=view&id=1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs"
        print(f"✅ drive_to_direct_url: {direct_url}")
    
    def test_detect_media_in_text_function(self):
        """Test detect_media_in_text function"""
        text = "Check out this video: https://www.youtube.com/watch?v=dQw4w9WgXcQ and more"
        result = detect_media_in_text(text)
        assert result is not None
        assert result["type"] == "youtube"
        assert result["video_id"] == "dQw4w9WgXcQ"
        print(f"✅ detect_media_in_text found: {result['type']}")
    
    def test_is_media_url_function(self):
        """Test is_media_url function"""
        assert is_media_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == True
        assert is_media_url("https://drive.google.com/file/d/123/view") == True
        assert is_media_url("https://example.com/image.png") == True
        assert is_media_url("https://example.com/page") == False
        print("✅ is_media_url: All checks passed")


class TestAPIHealth:
    """Test API health and basic connectivity"""
    
    def test_api_health(self):
        """Test API health endpoint"""
        response = requests.get(f"{BASE_URL}/api/")
        assert response.status_code == 200
        data = response.json()
        # API returns {"message": "Afroboost API"} not {"status": "healthy"}
        assert data.get("message") == "Afroboost API" or data.get("status") == "healthy"
        print(f"✅ API Health: {data}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
