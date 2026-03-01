"""
Test SoundManager.js Refactoring - Iteration 53
Tests:
1. SoundManager.js file exists with extracted functions
2. ChatWidget.js imports from SoundManager
3. playSoundIfEnabled uses useCallback with correct dependencies
4. MemoizedMessageBubble optimized comparison
5. getSilenceHoursLabel() used dynamically
6. Build compiles without errors
"""

import pytest
import requests
import os
import re

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://video-feed-platform.preview.emergentagent.com')

# === SOUNDMANAGER.JS FILE TESTS ===

class TestSoundManagerFile:
    """Tests for the new SoundManager.js file"""
    
    def test_soundmanager_file_exists(self):
        """SoundManager.js file should exist"""
        file_path = '/app/frontend/src/services/SoundManager.js'
        assert os.path.exists(file_path), f"SoundManager.js not found at {file_path}"
    
    def test_soundmanager_has_isInSilenceHours(self):
        """SoundManager.js should export isInSilenceHours function"""
        with open('/app/frontend/src/services/SoundManager.js', 'r') as f:
            content = f.read()
        assert 'export const isInSilenceHours' in content, "isInSilenceHours not exported"
        assert 'hour >= SILENCE_START_HOUR || hour < SILENCE_END_HOUR' in content, "isInSilenceHours logic incorrect"
    
    def test_soundmanager_has_getSilenceHoursLabel(self):
        """SoundManager.js should export getSilenceHoursLabel function"""
        with open('/app/frontend/src/services/SoundManager.js', 'r') as f:
            content = f.read()
        assert 'export const getSilenceHoursLabel' in content, "getSilenceHoursLabel not exported"
        assert 'SILENCE_START_HOUR' in content and 'SILENCE_END_HOUR' in content, "getSilenceHoursLabel should use constants"
    
    def test_soundmanager_has_playSoundIfAllowed(self):
        """SoundManager.js should export playSoundIfAllowed function"""
        with open('/app/frontend/src/services/SoundManager.js', 'r') as f:
            content = f.read()
        assert 'export const playSoundIfAllowed' in content, "playSoundIfAllowed not exported"
        assert 'silenceAutoEnabled && isInSilenceHours()' in content, "playSoundIfAllowed should check silence mode"
    
    def test_soundmanager_has_SOUND_TYPES(self):
        """SoundManager.js should export SOUND_TYPES constant"""
        with open('/app/frontend/src/services/SoundManager.js', 'r') as f:
            content = f.read()
        assert 'export const SOUND_TYPES' in content, "SOUND_TYPES not exported"
        assert "MESSAGE: 'message'" in content, "SOUND_TYPES.MESSAGE missing"
        assert "PRIVATE: 'private'" in content, "SOUND_TYPES.PRIVATE missing"
        assert "COACH: 'coach'" in content, "SOUND_TYPES.COACH missing"
    
    def test_soundmanager_constants(self):
        """SoundManager.js should have correct silence hour constants"""
        with open('/app/frontend/src/services/SoundManager.js', 'r') as f:
            content = f.read()
        assert 'SILENCE_START_HOUR = 22' in content, "SILENCE_START_HOUR should be 22"
        assert 'SILENCE_END_HOUR = 8' in content, "SILENCE_END_HOUR should be 8"
    
    def test_soundmanager_file_size(self):
        """SoundManager.js should be around 156 lines (reasonable size)"""
        with open('/app/frontend/src/services/SoundManager.js', 'r') as f:
            lines = len(f.readlines())
        assert 100 < lines < 200, f"SoundManager.js has {lines} lines, expected ~156"


# === CHATWIDGET.JS IMPORT TESTS ===

class TestChatWidgetImports:
    """Tests for ChatWidget.js imports from SoundManager"""
    
    def test_chatwidget_imports_soundmanager(self):
        """ChatWidget.js should import from SoundManager"""
        with open('/app/frontend/src/components/ChatWidget.js', 'r') as f:
            content = f.read()
        assert "from '../services/SoundManager'" in content, "ChatWidget should import from SoundManager"
    
    def test_chatwidget_imports_isInSilenceHours(self):
        """ChatWidget.js should import isInSilenceHours"""
        with open('/app/frontend/src/components/ChatWidget.js', 'r') as f:
            content = f.read()
        assert 'isInSilenceHours' in content, "isInSilenceHours should be imported"
    
    def test_chatwidget_imports_getSilenceHoursLabel(self):
        """ChatWidget.js should import getSilenceHoursLabel"""
        with open('/app/frontend/src/components/ChatWidget.js', 'r') as f:
            content = f.read()
        assert 'getSilenceHoursLabel' in content, "getSilenceHoursLabel should be imported"
    
    def test_chatwidget_imports_playSoundIfAllowed(self):
        """ChatWidget.js should import playSoundIfAllowed"""
        with open('/app/frontend/src/components/ChatWidget.js', 'r') as f:
            content = f.read()
        assert 'playSoundIfAllowed' in content, "playSoundIfAllowed should be imported"
    
    def test_chatwidget_imports_SOUND_TYPES(self):
        """ChatWidget.js should import SOUND_TYPES"""
        with open('/app/frontend/src/components/ChatWidget.js', 'r') as f:
            content = f.read()
        assert 'SOUND_TYPES' in content, "SOUND_TYPES should be imported"


# === USECALLBACK OPTIMIZATION TESTS ===

class TestUseCallbackOptimization:
    """Tests for playSoundIfEnabled useCallback optimization"""
    
    def test_playSoundIfEnabled_uses_useCallback(self):
        """playSoundIfEnabled should use useCallback"""
        with open('/app/frontend/src/components/ChatWidget.js', 'r') as f:
            content = f.read()
        # Find the playSoundIfEnabled definition
        pattern = r'const playSoundIfEnabled = useCallback\('
        assert re.search(pattern, content), "playSoundIfEnabled should use useCallback"
    
    def test_playSoundIfEnabled_has_dependencies(self):
        """playSoundIfEnabled useCallback should have soundEnabled and silenceAutoEnabled dependencies"""
        with open('/app/frontend/src/components/ChatWidget.js', 'r') as f:
            content = f.read()
        # Find the useCallback with dependencies
        # Pattern: }, [soundEnabled, silenceAutoEnabled]);
        assert '[soundEnabled, silenceAutoEnabled]' in content, \
            "playSoundIfEnabled should have [soundEnabled, silenceAutoEnabled] dependencies"
    
    def test_playSoundIfEnabled_delegates_to_playSoundIfAllowed(self):
        """playSoundIfEnabled should delegate to playSoundIfAllowed from SoundManager"""
        with open('/app/frontend/src/components/ChatWidget.js', 'r') as f:
            content = f.read()
        # Should call playSoundIfAllowed(type, soundEnabled, silenceAutoEnabled)
        assert 'playSoundIfAllowed(type, soundEnabled, silenceAutoEnabled)' in content, \
            "playSoundIfEnabled should delegate to playSoundIfAllowed"


# === MEMOIZEDMESSAGEBUBBLE OPTIMIZATION TESTS ===

class TestMemoizedMessageBubble:
    """Tests for MemoizedMessageBubble optimization"""
    
    def test_memoized_uses_memo(self):
        """MemoizedMessageBubble should use React.memo"""
        with open('/app/frontend/src/components/ChatWidget.js', 'r') as f:
            content = f.read()
        assert 'const MemoizedMessageBubble = memo(MessageBubble' in content, \
            "MemoizedMessageBubble should use memo()"
    
    def test_memoized_compares_msg_id(self):
        """MemoizedMessageBubble should compare msg.id"""
        with open('/app/frontend/src/components/ChatWidget.js', 'r') as f:
            content = f.read()
        assert 'prevProps.msg.id !== nextProps.msg.id' in content, \
            "MemoizedMessageBubble should compare msg.id"
    
    def test_memoized_compares_senderPhotoUrl(self):
        """MemoizedMessageBubble should compare senderPhotoUrl"""
        with open('/app/frontend/src/components/ChatWidget.js', 'r') as f:
            content = f.read()
        assert 'prevProps.msg.senderPhotoUrl !== nextProps.msg.senderPhotoUrl' in content, \
            "MemoizedMessageBubble should compare msg.senderPhotoUrl"
    
    def test_memoized_compares_profilePhotoUrl(self):
        """MemoizedMessageBubble should compare profilePhotoUrl"""
        with open('/app/frontend/src/components/ChatWidget.js', 'r') as f:
            content = f.read()
        assert 'prevProps.profilePhotoUrl !== nextProps.profilePhotoUrl' in content, \
            "MemoizedMessageBubble should compare profilePhotoUrl"
    
    def test_memoized_returns_true_for_same_message(self):
        """MemoizedMessageBubble should return true when props are equal (skip re-render)"""
        with open('/app/frontend/src/components/ChatWidget.js', 'r') as f:
            content = f.read()
        # The comparison function should return true at the end (no re-render needed)
        assert 'return true;' in content, "Comparison should return true for equal props"


# === GETSILENCEHOURSLABEL DYNAMIC USAGE TESTS ===

class TestGetSilenceHoursLabelUsage:
    """Tests for dynamic usage of getSilenceHoursLabel()"""
    
    def test_toggle_uses_getSilenceHoursLabel(self):
        """Toggle button should use getSilenceHoursLabel() for dynamic display"""
        with open('/app/frontend/src/components/ChatWidget.js', 'r') as f:
            content = f.read()
        # Should use getSilenceHoursLabel() in the toggle text
        assert 'getSilenceHoursLabel()' in content, "Should use getSilenceHoursLabel() dynamically"
    
    def test_toggle_shows_dynamic_hours(self):
        """Toggle should show dynamic hours like '22h-08h'"""
        with open('/app/frontend/src/components/ChatWidget.js', 'r') as f:
            content = f.read()
        # Pattern: `Silence Auto (${getSilenceHoursLabel()})`
        assert '${getSilenceHoursLabel()}' in content, "Toggle should use template literal with getSilenceHoursLabel()"
    
    def test_console_log_uses_getSilenceHoursLabel(self):
        """Console log should use getSilenceHoursLabel() for dynamic display"""
        with open('/app/frontend/src/components/ChatWidget.js', 'r') as f:
            content = f.read()
        # Pattern: `Activé (${getSilenceHoursLabel()})`
        pattern = r"Activé \(\$\{getSilenceHoursLabel\(\)\}\)"
        assert re.search(pattern, content), "Console log should use getSilenceHoursLabel()"


# === FILE SIZE TESTS ===

class TestFileSizes:
    """Tests for file size reduction"""
    
    def test_chatwidget_reduced(self):
        """ChatWidget.js should be reduced (was 3827, now ~3819)"""
        with open('/app/frontend/src/components/ChatWidget.js', 'r') as f:
            lines = len(f.readlines())
        # Should be around 3819 lines (reduced from 3827)
        assert lines < 3830, f"ChatWidget.js has {lines} lines, should be reduced"
    
    def test_soundmanager_reasonable_size(self):
        """SoundManager.js should be a reasonable size (~156 lines)"""
        with open('/app/frontend/src/services/SoundManager.js', 'r') as f:
            lines = len(f.readlines())
        assert 100 < lines < 200, f"SoundManager.js has {lines} lines"


# === BACKEND API TESTS ===

class TestBackendAPI:
    """Tests for backend API health"""
    
    def test_api_health(self):
        """API should be healthy"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get('status') == 'healthy'
    
    def test_promo_code_validation(self):
        """Promo code basxx should validate correctly"""
        response = requests.post(f"{BASE_URL}/api/discount-codes/validate", json={
            "code": "basxx",
            "email": "bassicustomshoes@gmail.com"
        })
        assert response.status_code == 200
        data = response.json()
        assert data.get('valid') == True
        assert data.get('code', {}).get('code') == 'basxx'


# === LOCALSTORAGE PERSISTENCE TESTS (Code Review) ===

class TestLocalStoragePersistence:
    """Code review tests for localStorage persistence"""
    
    def test_sound_enabled_key(self):
        """Sound enabled should use correct localStorage key"""
        with open('/app/frontend/src/services/SoundManager.js', 'r') as f:
            content = f.read()
        assert "SOUND_ENABLED_KEY = 'afroboost_sound_enabled'" in content, \
            "Sound enabled key should be 'afroboost_sound_enabled'"
    
    def test_silence_auto_key(self):
        """Silence auto should use correct localStorage key"""
        with open('/app/frontend/src/services/SoundManager.js', 'r') as f:
            content = f.read()
        assert "SILENCE_AUTO_KEY = 'afroboost_silence_auto'" in content, \
            "Silence auto key should be 'afroboost_silence_auto'"
    
    def test_chatwidget_reads_from_localstorage(self):
        """ChatWidget should read sound/silence settings from localStorage"""
        with open('/app/frontend/src/components/ChatWidget.js', 'r') as f:
            content = f.read()
        assert "localStorage.getItem('afroboost_sound_enabled')" in content, \
            "Should read sound enabled from localStorage"
        assert "localStorage.getItem('afroboost_silence_auto')" in content, \
            "Should read silence auto from localStorage"


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
