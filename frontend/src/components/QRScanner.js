// QRScanner.js - Modal de scan QR avec gestion propre de la caméra
// Compatible Vercel - Extrait de App.js pour architecture modulaire
import { useState, useRef, useEffect } from 'react';

// Note: Html5Qrcode est chargé via CDN dans index.html
// Référence globale: window.Html5Qrcode

// === QR SCANNER MODAL ===
export const QRScannerModal = ({ onClose, onValidate, scanResult, scanError, onManualValidation }) => {
  const [scanning, setScanning] = useState(false);
  const [cameraError, setCameraError] = useState(null);
  const [manualMode, setManualMode] = useState(false);
  const [permissionStatus, setPermissionStatus] = useState('unknown'); // unknown, granted, denied
  const [initializingCamera, setInitializingCamera] = useState(false);
  const scannerRef = useRef(null);
  const html5QrCodeRef = useRef(null);

  // Check camera permissions - Enhanced with direct getUserMedia test
  const checkCameraPermission = async () => {
    try {
      // Check if we're on HTTPS (required for camera access)
      const isLocalhost = window.location.hostname === 'localhost' || 
                          window.location.hostname === '127.0.0.1' ||
                          window.location.hostname.includes('.local');
      const isSecure = window.location.protocol === 'https:' || isLocalhost;
      
      if (!isSecure) {
        setCameraError("Le scan caméra nécessite une connexion HTTPS sécurisée.");
        setManualMode(true);
        return false;
      }

      // Check if mediaDevices is available
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        setCameraError("Votre navigateur ne supporte pas l'accès à la caméra.");
        setManualMode(true);
        return false;
      }

      // Try to get permission status via Permissions API first
      if (navigator.permissions && navigator.permissions.query) {
        try {
          const result = await navigator.permissions.query({ name: 'camera' });
          setPermissionStatus(result.state);
          if (result.state === 'denied') {
            setCameraError("L'accès à la caméra a été refusé. Autorisez l'accès dans les paramètres de votre navigateur, puis réessayez.");
            return false;
          }
        } catch (e) {
          // Permission query not supported (e.g., Safari), continue anyway
          console.log("Permissions API not supported, continuing...");
        }
      }
      return true;
    } catch (err) {
      console.error("Permission check error:", err);
      return true; // Try anyway
    }
  };

  // Direct camera test before using html5-qrcode
  const testCameraAccess = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ 
        video: { facingMode: 'environment' } 
      });
      // Successfully got access, stop the stream immediately
      stream.getTracks().forEach(track => track.stop());
      return true;
    } catch (err) {
      console.error("Direct camera test failed:", err);
      return false;
    }
  };

  // Start camera scanning with enhanced error handling
  const startScanning = async () => {
    setCameraError(null);
    setInitializingCamera(true);
    
    // Check permissions first
    const canProceed = await checkCameraPermission();
    if (!canProceed) {
      setInitializingCamera(false);
      return;
    }

    // Direct camera access test
    const cameraWorks = await testCameraAccess();
    if (!cameraWorks) {
      setCameraError("Impossible d'accéder à la caméra. Vérifiez les permissions et réessayez.");
      setInitializingCamera(false);
      return;
    }

    setScanning(true);
    setInitializingCamera(false);
    
    try {
      // Wait for the DOM element to be ready
      await new Promise(resolve => setTimeout(resolve, 100));
      
      const readerElement = document.getElementById("qr-reader");
      if (!readerElement) {
        throw new Error("Scanner container not found");
      }

      // IMPORTANT: Stop any previous session first using getState()
      if (html5QrCodeRef.current) {
        try {
          // getState(): 0 = NOT_STARTED, 1 = SCANNING, 2 = PAUSED
          if (html5QrCodeRef.current.getState && html5QrCodeRef.current.getState() !== 0) {
            await html5QrCodeRef.current.stop();
          }
          html5QrCodeRef.current = null;
        } catch (e) {
          console.log("Clearing previous session:", e);
          html5QrCodeRef.current = null;
        }
      }

      // Utiliser la référence globale Html5Qrcode
      const Html5Qrcode = window.Html5Qrcode;
      if (!Html5Qrcode) {
        setCameraError("La librairie de scan QR n'est pas disponible. Utilisez le mode manuel ci-dessous.");
        setManualMode(true);
        setScanning(false);
        setInitializingCamera(false);
        return;
      }

      const html5QrCode = new Html5Qrcode("qr-reader");
      html5QrCodeRef.current = html5QrCode;
      
      // Get available cameras
      let cameras = [];
      try {
        cameras = await Html5Qrcode.getCameras();
      } catch (camErr) {
        console.error("Camera enumeration error:", camErr);
        // Fallback: try with facingMode constraint
        await html5QrCode.start(
          { facingMode: "environment" },
          { fps: 10, qrbox: { width: 200, height: 200 }, aspectRatio: 1.0 },
          handleQrCodeSuccess,
          () => {}
        );
        setPermissionStatus('granted');
        return;
      }
      
      if (!cameras || cameras.length === 0) {
        // Try facingMode fallback
        await html5QrCode.start(
          { facingMode: "environment" },
          { fps: 10, qrbox: { width: 200, height: 200 }, aspectRatio: 1.0 },
          handleQrCodeSuccess,
          () => {}
        );
        setPermissionStatus('granted');
        return;
      }
      
      // Prefer back camera on mobile (usually last in list)
      const backCamera = cameras.find(c => c.label?.toLowerCase().includes('back') || c.label?.toLowerCase().includes('arrière'));
      const cameraId = backCamera?.id || (cameras.length > 1 ? cameras[cameras.length - 1].id : cameras[0].id);
      
      await html5QrCode.start(
        cameraId,
        {
          fps: 10,
          qrbox: { width: 200, height: 200 },
          aspectRatio: 1.0
        },
        handleQrCodeSuccess,
        () => {} // Ignore scan errors (expected when no QR visible)
      );
      
      setPermissionStatus('granted');
    } catch (err) {
      console.error("Camera error:", err);
      handleCameraError(err);
      setScanning(false);
    }
  };

  // Handle QR code detection — V156: Support codes abonnement (?qr=CODE) + réservation
  const handleQrCodeSuccess = (decodedText) => {
    let code = decodedText;

    // V156: Extraire le code depuis URL ?qr=CODE (QR abonnement côté abonné)
    if (decodedText.includes('?qr=')) {
      try {
        const url = new URL(decodedText);
        code = url.searchParams.get('qr')?.toUpperCase() || decodedText;
      } catch {
        // Fallback regex si URL invalide
        const qrMatch = decodedText.match(/[?&]qr=([^&]+)/i);
        if (qrMatch) code = qrMatch[1].toUpperCase();
      }
    } else if (decodedText.includes('/validate/')) {
      // URL de validation réservation: .../reservations/{code}/validate
      code = decodedText.split('/validate/').pop().split('/')[0].split('?')[0].toUpperCase();
    } else if (decodedText.match(/AF[A-Z0-9]+/i)) {
      // Code de réservation direct (AF1368C426, etc.)
      const match = decodedText.match(/AF[A-Z0-9]{6,}/i);
      if (match) code = match[0].toUpperCase();
    }

    // Stop scanning and validate
    stopScanning();
    if (code) {
      onValidate(code.trim());
    }
  };

  // Handle camera errors with user-friendly messages
  const handleCameraError = (err) => {
    const errString = err?.message || err?.toString() || '';
    let errorMessage = "Impossible d'accéder à la caméra.";
    
    if (errString.includes('Permission') || errString.includes('NotAllowed')) {
      errorMessage = "Permission caméra refusée. Autorisez l'accès dans les paramètres de votre navigateur, puis réessayez.";
      setPermissionStatus('denied');
    } else if (errString.includes('NotFound') || errString.includes('détectée') || errString.includes('No video')) {
      errorMessage = "Aucune caméra détectée sur cet appareil.";
    } else if (errString.includes('NotReadable') || errString.includes('already in use') || errString.includes('AbortError')) {
      errorMessage = "La caméra est déjà utilisée. Fermez les autres applications utilisant la caméra et réessayez.";
    } else if (errString.includes('OverconstrainedError')) {
      errorMessage = "Votre caméra ne supporte pas les paramètres requis. Essayez un autre appareil.";
    }
    
    setCameraError(errorMessage);
  };

  // Retry camera access
  const retryCamera = async () => {
    setCameraError(null);
    setManualMode(false);
    // Small delay before retry
    setTimeout(() => startScanning(), 300);
  };

  // Stop camera scanning - CRITICAL for proper cleanup
  const stopScanning = () => {
    if (html5QrCodeRef.current) {
      html5QrCodeRef.current.stop().catch(() => {});
      html5QrCodeRef.current = null;
    }
    setScanning(false);
  };

  // Cleanup on unmount - ESSENTIAL to prevent camera lock
  useEffect(() => {
    return () => {
      if (html5QrCodeRef.current) {
        html5QrCodeRef.current.stop().catch(() => {});
      }
    };
  }, []);

  // Handle close - ALWAYS stop scanner first
  const handleClose = () => {
    stopScanning();
    onClose();
  };

  return (
    <div className="modal-overlay" onClick={handleClose}>
      <div className="modal-content glass rounded-xl p-6 max-w-md w-full neon-border" onClick={e => e.stopPropagation()}>
        <div className="flex justify-between items-center mb-4">
          <h3 className="text-xl font-bold text-white">📷 Scanner un ticket</h3>
          <button onClick={handleClose} className="text-2xl text-white hover:text-purple-400">×</button>
        </div>
        
        {/* Success Result — V156: gère réservation ET abonnement */}
        {scanResult?.success && (
          <div className="p-4 rounded-lg bg-green-600/30 border border-green-500 mb-4 animate-pulse">
            <div className="flex items-center gap-3">
              <span className="text-5xl">✅</span>
              <div>
                <p className="text-white font-bold text-xl">
                  {scanResult.subscriptionInfo ? 'Séance validée !' : 'Ticket validé !'}
                </p>
                <p className="text-green-300 text-lg">{scanResult.reservation?.userName}</p>
                <p className="text-green-300 text-sm">{scanResult.reservation?.reservationCode}</p>
                {scanResult.subscriptionInfo && (
                  <p className="text-green-200 text-sm font-bold mt-1">
                    {scanResult.subscriptionInfo.remaining}/{scanResult.subscriptionInfo.total} séances restantes
                  </p>
                )}
                {scanResult.message && !scanResult.subscriptionInfo && (
                  <p className="text-green-200 text-xs mt-1">{scanResult.message}</p>
                )}
              </div>
            </div>
          </div>
        )}
        
        {/* Error */}
        {scanError && (
          <div className="p-4 rounded-lg bg-red-600/30 border border-red-500 mb-4">
            <p className="text-red-300">❌ {scanError}</p>
          </div>
        )}
        
        {/* Camera Error with Retry Button */}
        {cameraError && (
          <div className="p-4 rounded-lg bg-yellow-600/30 border border-yellow-500 mb-4">
            <p className="text-yellow-300 text-sm mb-3">⚠️ {cameraError}</p>
            <button 
              onClick={retryCamera}
              className="w-full py-2 rounded-lg bg-yellow-600 hover:bg-yellow-700 text-white text-sm flex items-center justify-center gap-2"
            >
              🔄 Réessayer l'accès caméra
            </button>
          </div>
        )}
        
        {/* Camera Scanner */}
        {!scanResult?.success && !manualMode && (
          <div className="mb-4">
            {/* Initializing Camera Indicator */}
            {initializingCamera && (
              <div className="flex flex-col items-center justify-center py-8 mb-4">
                <div className="animate-spin rounded-full h-12 w-12 border-4 border-purple-500 border-t-transparent mb-4"></div>
                <p className="text-white text-sm">Initialisation de la caméra...</p>
              </div>
            )}
            
            <div 
              id="qr-reader" 
              ref={scannerRef}
              className="rounded-lg overflow-hidden mb-4"
              style={{ 
                width: '300px', 
                height: scanning ? '300px' : '0px',
                minHeight: scanning ? '300px' : '0px',
                background: scanning ? '#000' : 'transparent',
                display: initializingCamera ? 'none' : 'block',
                margin: '0 auto'
              }}
            />
            
            {!scanning && !initializingCamera ? (
              <button 
                onClick={startScanning}
                className="w-full py-4 rounded-lg btn-primary flex items-center justify-center gap-2 text-lg"
                data-testid="start-camera-btn"
              >
                📷 Activer la caméra
              </button>
            ) : (
              <button 
                onClick={stopScanning}
                className="w-full py-3 rounded-lg bg-red-600 hover:bg-red-700 text-white"
              >
                ⏹ Arrêter le scan
              </button>
            )}
            
            <button 
              onClick={() => { stopScanning(); setManualMode(true); }}
              className="w-full mt-3 py-2 rounded-lg glass text-white text-sm opacity-70 hover:opacity-100"
            >
              ⌨️ Saisie manuelle
            </button>
          </div>
        )}
        
        {/* Manual code input (fallback) */}
        {!scanResult?.success && manualMode && (
          <div>
            <form onSubmit={onManualValidation} className="space-y-4">
              <p className="text-white text-sm opacity-70">Entrez le code de réservation :</p>
              <input 
                type="text" 
                name="code"
                placeholder="AFR-XXXXXX"
                className="w-full px-4 py-3 rounded-lg neon-input uppercase text-center text-xl tracking-widest"
                autoFocus
                data-testid="manual-code-input"
              />
              <button type="submit" className="w-full py-3 rounded-lg btn-primary" data-testid="validate-code-btn">
                ✓ Valider le ticket
              </button>
            </form>
            <button 
              onClick={() => setManualMode(false)}
              className="w-full mt-3 py-2 rounded-lg glass text-white text-sm opacity-70 hover:opacity-100"
            >
              📷 Retour au scan caméra
            </button>
          </div>
        )}
      </div>
    </div>
  );
};

export default QRScannerModal;
