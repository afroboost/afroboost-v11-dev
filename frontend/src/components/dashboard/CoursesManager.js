/**
 * CoursesManager Component v17.5
 * Gestion des cours + bouton Studio Audio glow
 */
import React from 'react';
import axios from 'axios';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';
const API = `${BACKEND_URL}/api`;

const CoursesManager = ({
  courses,
  setCourses,
  newCourse,
  setNewCourse,
  updateCourse,
  openAudioModal,
  hideAudioButton = false,
  lang,
  t
}) => {
  const WEEKDAYS_MAP = {
    fr: ["Dimanche", "Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi"],
    en: ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"],
    de: ["Sonntag", "Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag"]
  };

  const addCourse = async (e) => {
    e.preventDefault();
    try {
      const res = await axios.post(`${API}/courses`, { ...newCourse, visible: true, archived: false });
      setCourses([...courses, res.data]);
      setNewCourse({ name: "", weekday: 0, time: "18:30", locationName: "", mapsUrl: "" });
    } catch (err) {
      console.error("Erreur ajout cours:", err);
    }
  };

  const duplicateCourse = async (course) => {
    try {
      const duplicatedCourse = {
        name: `${course.name} (copie)`,
        weekday: course.weekday,
        time: course.time,
        locationName: course.locationName,
        mapsUrl: course.mapsUrl || '',
        visible: true,
        archived: false
      };
      const res = await axios.post(`${API}/courses`, duplicatedCourse);
      setCourses([...courses, res.data]);
    } catch (err) {
      console.error("Erreur duplication cours:", err);
    }
  };

  const archiveCourse = async (course) => {
    if (window.confirm(`Archiver le cours "${course.name}" ? Il sera masqué mais récupérable.`)) {
      try {
        await axios.put(`${API}/courses/${course.id}/archive`);
        setCourses(courses.map(c => c.id === course.id ? { ...c, archived: true } : c));
      } catch (err) {
        console.error("Erreur archivage cours:", err);
      }
    }
  };

  const restoreCourse = async (course) => {
    try {
      await axios.put(`${API}/courses/${course.id}`, { ...course, archived: false });
      setCourses(courses.map(c => c.id === course.id ? { ...c, archived: false } : c));
    } catch (err) {
      console.error("Erreur restauration cours:", err);
    }
  };

  // Compteur de pistes audio pour un cours
  const getTrackCount = (course) => {
    if (course.audio_tracks && course.audio_tracks.length > 0) return course.audio_tracks.length;
    if (course.playlist && course.playlist.length > 0) return course.playlist.length;
    return 0;
  };

  return (
    <div className="card-gradient rounded-xl p-6">
      <h2 className="font-semibold text-white mb-6" style={{ fontSize: '20px' }}>{t('courses')}</h2>

      {/* Liste des cours avec scroll */}
      <div style={{ maxHeight: '600px', overflowY: 'auto', paddingRight: '8px' }} className="custom-scrollbar">
        {courses.filter(c => !c.archived).map((course, idx) => (
          <div key={course.id} className="glass rounded-lg p-4 mb-4 relative">
            {/* Actions: Dupliquer + Archiver */}
            <div className="absolute top-2 right-2 flex gap-1">
              {/* Bouton dupliquer */}
              <button
                onClick={() => duplicateCourse(course)}
                className="p-2 rounded-lg hover:bg-purple-500/30 transition-colors"
                style={{ color: 'rgba(139, 92, 246, 0.8)' }}
                title="Dupliquer ce cours"
                data-testid={`duplicate-course-${course.id}`}
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"/>
                </svg>
              </button>
              {/* Bouton archiver */}
              <button
                onClick={() => archiveCourse(course)}
                className="p-2 rounded-lg hover:bg-orange-500/30 transition-colors"
                style={{ color: 'rgba(249, 115, 22, 0.8)' }}
                title="Archiver ce cours"
                data-testid={`archive-course-${course.id}`}
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4"/>
                </svg>
              </button>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pr-16">
              <div>
                <label className="block mb-1 text-white text-xs opacity-70">{t('courseName')}</label>
                <input
                  type="text"
                  value={course.name}
                  onChange={(e) => {
                    const n = [...courses];
                    const realIdx = courses.findIndex(c => c.id === course.id);
                    n[realIdx].name = e.target.value;
                    setCourses(n);
                  }}
                  onBlur={() => updateCourse(course)}
                  className="w-full px-3 py-2 rounded-lg neon-input text-sm"
                />
              </div>
              <div>
                <label className="block mb-1 text-white text-xs opacity-70">{t('location')}</label>
                <input
                  type="text"
                  value={course.locationName}
                  onChange={(e) => {
                    const n = [...courses];
                    const realIdx = courses.findIndex(c => c.id === course.id);
                    n[realIdx].locationName = e.target.value;
                    setCourses(n);
                  }}
                  onBlur={() => updateCourse(course)}
                  className="w-full px-3 py-2 rounded-lg neon-input text-sm"
                />
              </div>
              <div>
                <label className="block mb-1 text-white text-xs opacity-70">{t('weekday')}</label>
                <select
                  value={course.weekday}
                  onChange={(e) => {
                    const n = [...courses];
                    const realIdx = courses.findIndex(c => c.id === course.id);
                    n[realIdx].weekday = parseInt(e.target.value);
                    setCourses(n);
                    updateCourse({ ...course, weekday: parseInt(e.target.value) });
                  }}
                  className="w-full px-3 py-2 rounded-lg neon-input text-sm"
                >
                  {WEEKDAYS_MAP[lang].map((d, i) => <option key={i} value={i}>{d}</option>)}
                </select>
              </div>
              <div>
                <label className="block mb-1 text-white text-xs opacity-70">{t('time')}</label>
                <input
                  type="time"
                  value={course.time}
                  onChange={(e) => {
                    const n = [...courses];
                    const realIdx = courses.findIndex(c => c.id === course.id);
                    n[realIdx].time = e.target.value;
                    setCourses(n);
                  }}
                  onBlur={() => updateCourse(course)}
                  className="w-full px-3 py-2 rounded-lg neon-input text-sm"
                />
              </div>
              <div className="md:col-span-2">
                <label className="block mb-1 text-white text-xs opacity-70">{t('mapsLink')}</label>
                <input
                  type="url"
                  value={course.mapsUrl || ''}
                  onChange={(e) => {
                    const n = [...courses];
                    const realIdx = courses.findIndex(c => c.id === course.id);
                    n[realIdx].mapsUrl = e.target.value;
                    setCourses(n);
                  }}
                  onBlur={() => updateCourse(course)}
                  className="w-full px-3 py-2 rounded-lg neon-input text-sm"
                  placeholder="https://maps.google.com/..."
                />
              </div>
              {/* Toggle visibilité */}
              <div className="flex items-center gap-3 mt-2">
                <label className="text-white text-xs opacity-70">{t('visible')}</label>
                <div
                  className={`switch ${course.visible !== false ? 'active' : ''}`}
                  onClick={() => {
                    const n = [...courses];
                    const realIdx = courses.findIndex(c => c.id === course.id);
                    n[realIdx].visible = course.visible === false ? true : false;
                    setCourses(n);
                    updateCourse({ ...course, visible: n[realIdx].visible });
                  }}
                  data-testid={`course-visible-${course.id}`}
                />
                <span className="text-white text-xs opacity-50">
                  {course.visible !== false ? '👁️ Visible' : '🚫 Masqué'}
                </span>
              </div>
            </div>

            {/* === v17.5: Bouton Studio Audio GLOW === */}
            {!hideAudioButton && <div style={{ marginTop: '12px', paddingTop: '12px', borderTop: '1px solid rgba(217,28,210,0.15)' }}>
              <button
                onClick={() => openAudioModal(course)}
                data-testid={`audio-course-${course.id}`}
                style={{
                  width: '100%',
                  padding: '14px 20px',
                  borderRadius: '14px',
                  border: '1px solid rgba(217,28,210,0.4)',
                  background: 'linear-gradient(135deg, rgba(217,28,210,0.15), rgba(139,92,246,0.1))',
                  color: '#fff',
                  fontWeight: 700,
                  fontSize: '15px',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '10px',
                  position: 'relative',
                  overflow: 'hidden',
                  transition: 'all 0.3s ease',
                  boxShadow: '0 0 25px rgba(217,28,210,0.2), inset 0 0 25px rgba(217,28,210,0.05)'
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.boxShadow = '0 0 40px rgba(217,28,210,0.4), inset 0 0 30px rgba(217,28,210,0.1)';
                  e.currentTarget.style.borderColor = 'rgba(217,28,210,0.7)';
                  e.currentTarget.style.transform = 'translateY(-1px)';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.boxShadow = '0 0 25px rgba(217,28,210,0.2), inset 0 0 25px rgba(217,28,210,0.05)';
                  e.currentTarget.style.borderColor = 'rgba(217,28,210,0.4)';
                  e.currentTarget.style.transform = 'translateY(0)';
                }}
              >
                {/* Glow background effect */}
                <div style={{
                  position: 'absolute',
                  top: '50%',
                  left: '50%',
                  transform: 'translate(-50%, -50%)',
                  width: '120px',
                  height: '120px',
                  borderRadius: '50%',
                  background: 'radial-gradient(circle, rgba(217,28,210,0.2), transparent 70%)',
                  filter: 'blur(20px)',
                  pointerEvents: 'none'
                }} />
                <span style={{ fontSize: '22px', position: 'relative', zIndex: 1 }}>🎵</span>
                <span style={{ position: 'relative', zIndex: 1 }}>Gérer mon Studio Audio</span>
                {getTrackCount(course) > 0 && (
                  <span style={{
                    position: 'relative',
                    zIndex: 1,
                    background: 'linear-gradient(135deg, #d91cd2, #8b5cf6)',
                    padding: '2px 10px',
                    borderRadius: '12px',
                    fontSize: '12px',
                    fontWeight: 700
                  }}>
                    {getTrackCount(course)} piste{getTrackCount(course) > 1 ? 's' : ''}
                  </span>
                )}
              </button>
            </div>}
          </div>
        ))}
      </div>

      {/* Section Cours Archivés */}
      {courses.filter(c => c.archived).length > 0 && (
        <div className="mt-6 pt-6 border-t border-purple-500/30">
          <h3 className="text-white text-sm font-semibold mb-3 flex items-center gap-2">
            <span>📁</span> Cours archivés ({courses.filter(c => c.archived).length})
          </h3>
          <div className="space-y-2">
            {courses.filter(c => c.archived).map(course => (
              <div key={course.id} className="flex items-center justify-between p-3 rounded-lg" style={{ background: 'rgba(249, 115, 22, 0.1)', border: '1px solid rgba(249, 115, 22, 0.3)' }}>
                <span className="text-white text-sm opacity-70">{course.name}</span>
                <button
                  onClick={() => restoreCourse(course)}
                  className="px-3 py-1 rounded text-xs"
                  style={{ background: 'rgba(34, 197, 94, 0.3)', color: '#22c55e' }}
                  data-testid={`restore-course-${course.id}`}
                >
                  ↩️ Restaurer
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Formulaire Ajout */}
      <form onSubmit={addCourse} className="glass rounded-lg p-4 mt-4">
        <h3 className="text-white mb-4 font-semibold text-sm">{t('addCourse')}</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <input
            type="text"
            placeholder={t('courseName')}
            value={newCourse.name}
            onChange={e => setNewCourse({ ...newCourse, name: e.target.value })}
            className="px-3 py-2 rounded-lg neon-input text-sm"
            required
          />
          <input
            type="text"
            placeholder={t('location')}
            value={newCourse.locationName}
            onChange={e => setNewCourse({ ...newCourse, locationName: e.target.value })}
            className="px-3 py-2 rounded-lg neon-input text-sm"
          />
          <select
            value={newCourse.weekday}
            onChange={e => setNewCourse({ ...newCourse, weekday: parseInt(e.target.value) })}
            className="px-3 py-2 rounded-lg neon-input text-sm"
          >
            {WEEKDAYS_MAP[lang].map((d, i) => <option key={i} value={i}>{d}</option>)}
          </select>
          <input
            type="time"
            value={newCourse.time}
            onChange={e => setNewCourse({ ...newCourse, time: e.target.value })}
            className="px-3 py-2 rounded-lg neon-input text-sm"
          />
        </div>
        <button type="submit" className="btn-primary px-4 py-2 rounded-lg mt-4 text-sm">{t('add')}</button>
      </form>
    </div>
  );
};

export default CoursesManager;
