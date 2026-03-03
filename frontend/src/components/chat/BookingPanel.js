/**
 * BookingPanel.js - Panneau de réservation pour les abonnés
 * 
 * Extrait de ChatWidget.js pour alléger le fichier principal.
 * Affiche la liste des cours disponibles et permet de réserver un créneau.
 * 
 * === SYNCHRONISATION HORAIRE ===
 * - Dates formatées en français avec Intl.DateTimeFormat
 * - Fuseau horaire Europe/Paris (Genève)
 * - Fallback de localisation: course.location || "Lieu à confirmer"
 */

import React, { memo, useMemo } from 'react';

// === FORMATTER DE DATE FRANÇAIS (Europe/Paris) ===
const formatCourseDate = (time, weekday) => {
  // Créer une date pour le prochain jour de la semaine correspondant
  const today = new Date();
  const currentDay = today.getDay();
  let daysUntilCourse = weekday - currentDay;
  if (daysUntilCourse <= 0) daysUntilCourse += 7;
  
  const courseDate = new Date(today);
  courseDate.setDate(today.getDate() + daysUntilCourse);
  
  // Parser l'heure (format "18:30")
  if (time) {
    const [hours, minutes] = time.split(':');
    courseDate.setHours(parseInt(hours) || 18, parseInt(minutes) || 30, 0, 0);
  }
  
  // Formater en français avec fuseau Europe/Paris (v11.5: ajout année)
  const formatter = new Intl.DateTimeFormat('fr-FR', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    timeZone: 'Europe/Paris'
  });
  
  const formatted = formatter.format(courseDate);
  // Capitaliser la première lettre
  return formatted.charAt(0).toUpperCase() + formatted.slice(1);
};

// === FALLBACK LOCALISATION ===
const getLocationDisplay = (course) => {
  return course?.location || course?.locationName || 'Lieu à confirmer';
};

/**
 * Panneau de réservation de cours
 * @param {object} afroboostProfile - Profil abonné {code, name, email, whatsapp}
 * @param {array} availableCourses - Liste des cours disponibles
 * @param {object} selectedCourse - Cours sélectionné
 * @param {function} setSelectedCourse - Setter pour sélectionner un cours
 * @param {boolean} loadingCourses - État de chargement des cours
 * @param {boolean} reservationLoading - État de chargement de la réservation
 * @param {string} reservationError - Message d'erreur
 * @param {function} onConfirmReservation - Handler de confirmation
 * @param {function} onClose - Handler de fermeture
 */
const BookingPanel = ({
  afroboostProfile,
  availableCourses,
  selectedCourse,
  setSelectedCourse,
  loadingCourses,
  reservationLoading,
  reservationError,
  onConfirmReservation,
  onClose
}) => {
  // Mémoriser le formatage des dates
  const formattedCourses = useMemo(() => {
    return availableCourses.map(course => ({
      ...course,
      formattedDate: formatCourseDate(course.time, course.weekday),
      displayLocation: getLocationDisplay(course)
    }));
  }, [availableCourses]);

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      gap: '12px',
      padding: '4px'
    }}>
      {/* Header */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: '8px'
      }}>
        <h3 style={{ color: '#fff', fontSize: '16px', margin: 0 }}>
          📅 Réserver un cours
        </h3>
        <button
          onClick={onClose}
          style={{
            background: 'none',
            border: 'none',
            color: 'rgba(255,255,255,0.6)',
            cursor: 'pointer',
            fontSize: '18px'
          }}
          data-testid="close-booking"
        >
          ✕
        </button>
      </div>

      {/* Badge abonné */}
      {afroboostProfile?.code && (
        <div style={{
          background: 'rgba(34, 197, 94, 0.2)',
          border: '1px solid rgba(34, 197, 94, 0.3)',
          borderRadius: '8px',
          padding: '8px 12px',
          marginBottom: '12px',
          fontSize: '12px',
          color: '#22c55e'
        }}>
          💎 Abonné • Code: <strong>{afroboostProfile.code}</strong>
        </div>
      )}

      {/* Chargement */}
      {loadingCourses && (
        <div style={{ textAlign: 'center', padding: '20px', color: '#888' }}>
          ⏳ Chargement des sessions...
        </div>
      )}

      {/* Liste des cours - Avec dates formatées en français */}
      {!loadingCourses && !selectedCourse && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          {formattedCourses.length === 0 && (
            <div style={{ textAlign: 'center', padding: '20px', color: '#888' }}>
              Aucune session disponible
            </div>
          )}
          {formattedCourses.map(course => (
            <button
              key={course.id}
              type="button"
              onClick={() => setSelectedCourse(course)}
              style={{
                padding: '12px',
                borderRadius: '12px',
                background: 'linear-gradient(135deg, rgba(147, 51, 234, 0.3), rgba(99, 102, 241, 0.3))',
                border: '1px solid rgba(147, 51, 234, 0.4)',
                color: '#fff',
                textAlign: 'left',
                cursor: 'pointer',
                transition: 'all 0.2s'
              }}
              data-testid={`course-${course.id}`}
            >
              <div style={{ fontWeight: 'bold', marginBottom: '4px' }}>
                {course.name}
              </div>
              {/* Date formatée en français (Europe/Paris) */}
              <div style={{ fontSize: '13px', marginBottom: '4px', color: '#a78bfa' }}>
                📅 {course.formattedDate}
              </div>
              {/* Lieu avec style discret si "Lieu à confirmer" */}
              <div style={{ 
                fontSize: '12px', 
                opacity: 0.8,
                color: course.displayLocation === 'Lieu à confirmer' ? '#999' : 'inherit',
                fontStyle: course.displayLocation === 'Lieu à confirmer' ? 'italic' : 'normal'
              }}>
                📍 {course.displayLocation}
              </div>
              {course.spotsLeft !== undefined && (
                <div style={{ 
                  fontSize: '11px', 
                  marginTop: '4px',
                  color: course.spotsLeft <= 3 ? '#f97316' : '#22c55e'
                }}>
                  {course.spotsLeft <= 0 ? '❌ Complet' : `✅ ${course.spotsLeft} place(s) restante(s)`}
                </div>
              )}
            </button>
          ))}
        </div>
      )}

      {/* Détail du cours sélectionné */}
      {selectedCourse && (
        <div style={{
          background: 'rgba(147, 51, 234, 0.2)',
          border: '1px solid rgba(147, 51, 234, 0.4)',
          borderRadius: '12px',
          padding: '16px'
        }}>
          <div style={{ 
            display: 'flex', 
            justifyContent: 'space-between', 
            alignItems: 'flex-start',
            marginBottom: '12px'
          }}>
            <div>
              <h4 style={{ color: '#fff', margin: '0 0 4px 0', fontSize: '14px' }}>
                {selectedCourse.name}
              </h4>
              {/* Date formatée en français (Europe/Paris) */}
              <p style={{ color: '#a78bfa', margin: '0 0 4px 0', fontSize: '13px', fontWeight: '500' }}>
                📅 {selectedCourse.formattedDate || formatCourseDate(selectedCourse.time, selectedCourse.weekday)}
              </p>
              {/* Lieu avec style discret si "Lieu à confirmer" */}
              {(() => {
                const loc = selectedCourse.displayLocation || getLocationDisplay(selectedCourse);
                const isPlaceholder = loc === 'Lieu à confirmer';
                return (
                  <p style={{ 
                    color: isPlaceholder ? '#999' : 'rgba(255,255,255,0.7)', 
                    margin: 0, 
                    fontSize: '12px',
                    fontStyle: isPlaceholder ? 'italic' : 'normal'
                  }}>
                    📍 {loc}
                  </p>
                );
              })()}
            </div>
            <button
              type="button"
              onClick={() => setSelectedCourse(null)}
              disabled={reservationLoading}
              style={{
                background: 'rgba(255,255,255,0.1)',
                border: 'none',
                borderRadius: '8px',
                padding: '6px 12px',
                color: '#fff',
                fontSize: '11px',
                cursor: reservationLoading ? 'not-allowed' : 'pointer',
                opacity: reservationLoading ? 0.5 : 1
              }}
            >
              ← Retour
            </button>
          </div>

          {/* Bouton de confirmation */}
          <button
            type="button"
            onClick={onConfirmReservation}
            disabled={reservationLoading}
            style={{
              width: '100%',
              padding: '12px',
              borderRadius: '10px',
              background: reservationLoading 
                ? 'linear-gradient(135deg, #666, #555)'
                : 'linear-gradient(135deg, #22c55e, #16a34a)',
              border: 'none',
              color: '#fff',
              fontWeight: 'bold',
              cursor: reservationLoading ? 'wait' : 'pointer',
              opacity: reservationLoading ? 0.7 : 1
            }}
            data-testid="confirm-reservation-btn"
          >
            {reservationLoading ? '⏳ Envoi en cours...' : '✅ Confirmer la réservation'}
          </button>

          {/* Erreur */}
          {reservationError && (
            <div style={{
              marginTop: '12px',
              padding: '8px 12px',
              borderRadius: '8px',
              background: 'rgba(239, 68, 68, 0.2)',
              border: '1px solid rgba(239, 68, 68, 0.3)',
              color: '#ef4444',
              fontSize: '12px'
            }}>
              ❌ {reservationError}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default memo(BookingPanel);
