/**
 * BookingPanel.js - Panneau de réservation pour les abonnés
 *
 * v95: Sélecteur multi-abonnements — l'utilisateur choisit quel abonnement utiliser
 *
 * === SYNCHRONISATION HORAIRE ===
 * - Dates formatées en français suisse avec Intl.DateTimeFormat('fr-CH')
 * - Fuseau horaire Europe/Zurich (Suisse)
 * - Fallback de localisation: course.location || "Lieu à confirmer"
 */

import React, { memo, useMemo } from 'react';

// === FORMATTER DE DATE FRANÇAIS SUISSE (Europe/Zurich) ===
const formatCourseDate = (time, weekday) => {
  const nowStr = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Europe/Zurich',
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', hour12: false
  }).format(new Date());
  const [datePart] = nowStr.split(',');
  const todayInZurich = new Date(datePart + 'T12:00:00');
  const currentDay = todayInZurich.getDay();

  let daysUntilCourse = weekday - currentDay;
  if (daysUntilCourse < 0) daysUntilCourse += 7;

  const courseDate = new Date(todayInZurich);
  courseDate.setDate(todayInZurich.getDate() + daysUntilCourse);

  if (time) {
    const [hours, minutes] = time.split(':');
    courseDate.setHours(parseInt(hours) || 18, parseInt(minutes) || 30, 0, 0);
  }

  const formatter = new Intl.DateTimeFormat('fr-CH', {
    weekday: 'long', day: 'numeric', month: 'long', year: 'numeric',
    hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Zurich'
  });

  const formatted = formatter.format(courseDate);
  return formatted.charAt(0).toUpperCase() + formatted.slice(1);
};

const getLocationDisplay = (course) => {
  return course?.location || course?.locationName || 'Lieu à confirmer';
};

/**
 * Panneau de réservation de cours
 * v95: Ajout de subscriptions, selectedSubscription, onSelectSubscription
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
  onClose,
  // v95: Multi-abonnements
  subscriptions = [],
  selectedSubscription = null,
  onSelectSubscription = null
}) => {
  const formattedCourses = useMemo(() => {
    return availableCourses.map(course => ({
      ...course,
      formattedDate: formatCourseDate(course.time, course.weekday),
      displayLocation: getLocationDisplay(course)
    }));
  }, [availableCourses]);

  const hasMultipleSubs = subscriptions.length > 1;

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
          marginBottom: hasMultipleSubs ? '4px' : '12px',
          fontSize: '12px',
          color: '#22c55e'
        }}>
          💎 Abonné • Code: <strong>{afroboostProfile.code}</strong>
        </div>
      )}

      {/* v95: SÉLECTEUR MULTI-ABONNEMENTS */}
      {hasMultipleSubs && (
        <div style={{
          background: 'rgba(217, 28, 210, 0.1)',
          border: '1px solid rgba(217, 28, 210, 0.3)',
          borderRadius: '10px',
          padding: '10px',
          marginBottom: '8px'
        }}>
          <p style={{ color: '#D91CD2', fontSize: '12px', margin: '0 0 8px 0', fontWeight: '600' }}>
            🔄 Réserver pour quel abonnement ?
          </p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            {subscriptions.map(sub => {
              const isSelected = selectedSubscription?.id === sub.id;
              const isUnlimited = sub.total_sessions === -1 || sub.remaining_sessions === -1;
              return (
                <button
                  key={sub.id}
                  type="button"
                  onClick={() => onSelectSubscription && onSelectSubscription(sub)}
                  style={{
                    padding: '10px 12px',
                    borderRadius: '8px',
                    background: isSelected
                      ? 'linear-gradient(135deg, rgba(217, 28, 210, 0.4), rgba(147, 51, 234, 0.4))'
                      : 'rgba(255,255,255,0.05)',
                    border: isSelected
                      ? '2px solid #D91CD2'
                      : '1px solid rgba(255,255,255,0.1)',
                    color: '#fff',
                    textAlign: 'left',
                    cursor: 'pointer',
                    transition: 'all 0.2s'
                  }}
                  data-testid={`sub-${sub.id}`}
                >
                  <div style={{ fontWeight: 'bold', fontSize: '13px' }}>
                    {isSelected ? '● ' : '○ '}
                    {sub.offer_name || sub.code}
                  </div>
                  <div style={{ fontSize: '11px', color: 'rgba(255,255,255,0.6)', marginTop: '2px' }}>
                    Code: {sub.code}
                    {isUnlimited
                      ? ' • ∞ séances'
                      : ` • ${sub.remaining_sessions}/${sub.total_sessions} séances restantes`
                    }
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      )}

      {/* Info abonnement unique */}
      {subscriptions.length === 1 && (
        <div style={{
          background: 'rgba(147, 51, 234, 0.1)',
          border: '1px solid rgba(147, 51, 234, 0.2)',
          borderRadius: '8px',
          padding: '8px 12px',
          marginBottom: '8px',
          fontSize: '11px',
          color: 'rgba(255,255,255,0.6)'
        }}>
          📋 {subscriptions[0].offer_name || subscriptions[0].code}
          {subscriptions[0].total_sessions === -1 || subscriptions[0].remaining_sessions === -1
            ? ' • ∞ séances'
            : ` • ${subscriptions[0].remaining_sessions}/${subscriptions[0].total_sessions} séances restantes`
          }
        </div>
      )}

      {/* Chargement */}
      {loadingCourses && (
        <div style={{ textAlign: 'center', padding: '20px', color: '#888' }}>
          ⏳ Chargement des sessions...
        </div>
      )}

      {/* Liste des cours */}
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
              <div style={{ fontSize: '13px', marginBottom: '4px', color: '#a78bfa' }}>
                📅 {course.formattedDate}
              </div>
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
              <p style={{ color: '#a78bfa', margin: '0 0 4px 0', fontSize: '13px', fontWeight: '500' }}>
                📅 {selectedCourse.formattedDate || formatCourseDate(selectedCourse.time, selectedCourse.weekday)}
              </p>
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

          {/* v95: Rappel abonnement sélectionné */}
          {hasMultipleSubs && selectedSubscription && (
            <div style={{
              background: 'rgba(217, 28, 210, 0.15)',
              borderRadius: '6px',
              padding: '6px 10px',
              marginBottom: '10px',
              fontSize: '11px',
              color: '#D91CD2'
            }}>
              🎯 Réservation via : <strong>{selectedSubscription.offer_name || selectedSubscription.code}</strong>
            </div>
          )}

          {/* Bouton de confirmation */}
          <button
            type="button"
            onClick={onConfirmReservation}
            disabled={reservationLoading || (hasMultipleSubs && !selectedSubscription)}
            style={{
              width: '100%',
              padding: '12px',
              borderRadius: '10px',
              background: reservationLoading
                ? 'linear-gradient(135deg, #666, #555)'
                : (hasMultipleSubs && !selectedSubscription)
                  ? 'linear-gradient(135deg, #555, #444)'
                  : 'linear-gradient(135deg, #22c55e, #16a34a)',
              border: 'none',
              color: '#fff',
              fontWeight: 'bold',
              cursor: reservationLoading ? 'wait' : (hasMultipleSubs && !selectedSubscription) ? 'not-allowed' : 'pointer',
              opacity: (reservationLoading || (hasMultipleSubs && !selectedSubscription)) ? 0.7 : 1
            }}
            data-testid="confirm-reservation-btn"
          >
            {reservationLoading
              ? '⏳ Envoi en cours...'
              : (hasMultipleSubs && !selectedSubscription)
                ? '⬆️ Sélectionnez un abonnement'
                : '✅ Confirmer la réservation'
            }
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
