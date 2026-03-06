/**
 * CampaignCalendar.js - v11: Vue calendrier interactive pour campagnes
 * Affiche les campagnes programmées dans une grille mensuelle
 * Clic sur un jour → pré-remplir la date dans le formulaire
 */
import React, { useState, useMemo } from 'react';

const STATUS_COLORS = {
  draft: { bg: 'rgba(107, 114, 128, 0.3)', border: '#6b7280', label: 'Brouillon' },
  scheduled: { bg: 'rgba(59, 130, 246, 0.3)', border: '#3b82f6', label: 'Programmée' },
  sending: { bg: 'rgba(249, 115, 22, 0.3)', border: '#f97316', label: 'En cours' },
  completed: { bg: 'rgba(34, 197, 94, 0.3)', border: '#22c55e', label: 'Terminée' },
  sent: { bg: 'rgba(34, 197, 94, 0.3)', border: '#22c55e', label: 'Envoyée' },
  failed: { bg: 'rgba(239, 68, 68, 0.3)', border: '#ef4444', label: 'Échouée' }
};

const DAYS_FR = ['Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam', 'Dim'];
const MONTHS_FR = [
  'Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin',
  'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre'
];

export default function CampaignCalendar({ campaigns = [], onDayClick, onCampaignClick }) {
  const [currentDate, setCurrentDate] = useState(new Date());

  const year = currentDate.getFullYear();
  const month = currentDate.getMonth();

  // Construire la grille du mois
  const calendarDays = useMemo(() => {
    const firstDay = new Date(year, month, 1);
    const lastDay = new Date(year, month + 1, 0);
    const startDayOfWeek = (firstDay.getDay() + 6) % 7; // Lundi = 0
    const daysInMonth = lastDay.getDate();

    const days = [];
    // Jours vides avant le 1er
    for (let i = 0; i < startDayOfWeek; i++) {
      days.push(null);
    }
    // Jours du mois
    for (let d = 1; d <= daysInMonth; d++) {
      days.push(d);
    }
    return days;
  }, [year, month]);

  // Indexer les campagnes par jour
  const campaignsByDay = useMemo(() => {
    const map = {};
    campaigns.forEach(c => {
      const dateStr = c.scheduledAt || c.createdAt;
      if (!dateStr) return;
      const d = new Date(dateStr);
      if (d.getFullYear() === year && d.getMonth() === month) {
        const day = d.getDate();
        if (!map[day]) map[day] = [];
        map[day].push(c);
      }
    });
    return map;
  }, [campaigns, year, month]);

  const today = new Date();
  const isToday = (day) => day && today.getFullYear() === year && today.getMonth() === month && today.getDate() === day;

  const prevMonth = () => setCurrentDate(new Date(year, month - 1, 1));
  const nextMonth = () => setCurrentDate(new Date(year, month + 1, 1));
  const goToday = () => setCurrentDate(new Date());

  const handleDayClick = (day) => {
    if (!day) return;
    const dateStr = `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
    onDayClick?.(dateStr);
  };

  // Compter les stats du mois
  const monthStats = useMemo(() => {
    const stats = { total: 0, scheduled: 0, completed: 0, failed: 0 };
    campaigns.forEach(c => {
      const dateStr = c.scheduledAt || c.createdAt;
      if (!dateStr) return;
      const d = new Date(dateStr);
      if (d.getFullYear() === year && d.getMonth() === month) {
        stats.total++;
        if (c.status === 'scheduled') stats.scheduled++;
        if (c.status === 'completed' || c.status === 'sent') stats.completed++;
        if (c.status === 'failed') stats.failed++;
      }
    });
    return stats;
  }, [campaigns, year, month]);

  return (
    <div className="mb-6 p-4 rounded-xl glass border border-purple-500/20">
      {/* Header: Navigation */}
      <div className="flex items-center justify-between mb-4">
        <button type="button" onClick={prevMonth}
          style={{ background: 'rgba(139, 92, 246, 0.2)', border: '1px solid rgba(139, 92, 246, 0.3)', color: '#fff', borderRadius: '8px', padding: '6px 12px', fontSize: '13px', cursor: 'pointer' }}>
          ◀
        </button>
        <div className="text-center">
          <h3 className="text-white font-semibold text-sm sm:text-base">
            📅 {MONTHS_FR[month]} {year}
          </h3>
          <div className="flex items-center justify-center gap-3 mt-1">
            {monthStats.total > 0 && (
              <span className="text-xs text-white/60">
                {monthStats.total} campagne{monthStats.total > 1 ? 's' : ''}
                {monthStats.scheduled > 0 && <span style={{ color: '#3b82f6' }}> • {monthStats.scheduled} prog.</span>}
                {monthStats.completed > 0 && <span style={{ color: '#22c55e' }}> • {monthStats.completed} ok</span>}
                {monthStats.failed > 0 && <span style={{ color: '#ef4444' }}> • {monthStats.failed} err</span>}
              </span>
            )}
          </div>
        </div>
        <div className="flex gap-2">
          <button type="button" onClick={goToday}
            style={{ background: 'rgba(139, 92, 246, 0.15)', border: '1px solid rgba(139, 92, 246, 0.3)', color: '#c4b5fd', borderRadius: '8px', padding: '6px 10px', fontSize: '11px', cursor: 'pointer' }}>
            Aujourd'hui
          </button>
          <button type="button" onClick={nextMonth}
            style={{ background: 'rgba(139, 92, 246, 0.2)', border: '1px solid rgba(139, 92, 246, 0.3)', color: '#fff', borderRadius: '8px', padding: '6px 12px', fontSize: '13px', cursor: 'pointer' }}>
            ▶
          </button>
        </div>
      </div>

      {/* Jours de la semaine */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', gap: '2px', marginBottom: '4px' }}>
        {DAYS_FR.map(d => (
          <div key={d} style={{ textAlign: 'center', fontSize: '11px', color: 'rgba(255,255,255,0.4)', fontWeight: 600, padding: '4px 0' }}>
            {d}
          </div>
        ))}
      </div>

      {/* Grille calendrier */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', gap: '2px' }}>
        {calendarDays.map((day, idx) => {
          const dayCampaigns = day ? (campaignsByDay[day] || []) : [];
          const todayClass = isToday(day);

          return (
            <div
              key={idx}
              onClick={() => handleDayClick(day)}
              style={{
                minHeight: '52px',
                padding: '4px',
                borderRadius: '8px',
                cursor: day ? 'pointer' : 'default',
                background: todayClass
                  ? 'rgba(139, 92, 246, 0.25)'
                  : day ? 'rgba(255,255,255,0.03)' : 'transparent',
                border: todayClass
                  ? '2px solid rgba(139, 92, 246, 0.6)'
                  : day ? '1px solid rgba(255,255,255,0.06)' : 'none',
                transition: 'all 0.15s ease'
              }}
              onMouseEnter={e => { if (day) e.currentTarget.style.background = 'rgba(139, 92, 246, 0.15)'; }}
              onMouseLeave={e => { if (day) e.currentTarget.style.background = todayClass ? 'rgba(139, 92, 246, 0.25)' : 'rgba(255,255,255,0.03)'; }}
            >
              {day && (
                <>
                  <div style={{ fontSize: '11px', fontWeight: todayClass ? 700 : 400, color: todayClass ? '#c4b5fd' : 'rgba(255,255,255,0.6)', marginBottom: '2px' }}>
                    {day}
                  </div>
                  {/* Pastilles campagnes (max 3 affichées) */}
                  {dayCampaigns.slice(0, 3).map((c, i) => {
                    const sc = STATUS_COLORS[c.status] || STATUS_COLORS.draft;
                    return (
                      <div
                        key={c.id || i}
                        onClick={(e) => { e.stopPropagation(); onCampaignClick?.(c); }}
                        title={`${c.name} (${sc.label})`}
                        style={{
                          fontSize: '9px',
                          lineHeight: '1.2',
                          padding: '1px 4px',
                          marginBottom: '1px',
                          borderRadius: '4px',
                          background: sc.bg,
                          borderLeft: `2px solid ${sc.border}`,
                          color: '#fff',
                          whiteSpace: 'nowrap',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          cursor: 'pointer'
                        }}
                      >
                        {c.name}
                      </div>
                    );
                  })}
                  {dayCampaigns.length > 3 && (
                    <div style={{ fontSize: '9px', color: 'rgba(255,255,255,0.4)', textAlign: 'center' }}>
                      +{dayCampaigns.length - 3}
                    </div>
                  )}
                </>
              )}
            </div>
          );
        })}
      </div>

      {/* Légende */}
      <div className="flex flex-wrap gap-3 mt-3 pt-3" style={{ borderTop: '1px solid rgba(255,255,255,0.08)' }}>
        {Object.entries(STATUS_COLORS).filter(([k]) => k !== 'sent').map(([key, val]) => (
          <div key={key} className="flex items-center gap-1.5">
            <div style={{ width: '8px', height: '8px', borderRadius: '50%', background: val.border }} />
            <span style={{ fontSize: '10px', color: 'rgba(255,255,255,0.5)' }}>{val.label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
