/**
 * CampaignCalendar.js - v12: Calendrier dynamique avec drag & drop
 * - Clic sur jour vide → ouvre modal création avec date pré-remplie
 * - Clic sur campagne → ouvre modal édition
 * - Drag & drop pour déplacer une campagne entre jours
 * - Menu contextuel (clic long / clic droit) pour dupliquer
 * - Bouton "+" flottant pour créer
 */
import React, { useState, useMemo, useCallback } from 'react';

const STATUS_COLORS = {
  draft: { bg: 'rgba(107,114,128,0.3)', border: '#6b7280', label: 'Brouillon' },
  scheduled: { bg: 'rgba(59,130,246,0.3)', border: '#3b82f6', label: 'Programmée' },
  sending: { bg: 'rgba(249,115,22,0.3)', border: '#f97316', label: 'En cours' },
  completed: { bg: 'rgba(34,197,94,0.3)', border: '#22c55e', label: 'Terminée' },
  sent: { bg: 'rgba(34,197,94,0.3)', border: '#22c55e', label: 'Envoyée' },
  failed: { bg: 'rgba(239,68,68,0.3)', border: '#ef4444', label: 'Échouée' }
};

const DAYS_FR = ['Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam', 'Dim'];
const MONTHS_FR = ['Janvier','Février','Mars','Avril','Mai','Juin','Juillet','Août','Septembre','Octobre','Novembre','Décembre'];

export default function CampaignCalendar({
  campaigns = [],
  onDayClick,         // (dateStr) => open modal with date
  onCampaignClick,    // (campaign) => open modal in edit mode
  onMoveCampaign,     // (campaignId, newDateStr) => update scheduledAt
  onDuplicateCampaign // (campaign) => duplicate
}) {
  const [currentDate, setCurrentDate] = useState(new Date());
  const [draggedCampaign, setDraggedCampaign] = useState(null);
  const [dragOverDay, setDragOverDay] = useState(null);
  const [contextMenu, setContextMenu] = useState(null); // { x, y, campaign }

  const year = currentDate.getFullYear();
  const month = currentDate.getMonth();

  const calendarDays = useMemo(() => {
    const firstDay = new Date(year, month, 1);
    const lastDay = new Date(year, month + 1, 0);
    const startDow = (firstDay.getDay() + 6) % 7;
    const days = [];
    for (let i = 0; i < startDow; i++) days.push(null);
    for (let d = 1; d <= lastDay.getDate(); d++) days.push(d);
    return days;
  }, [year, month]);

  const campaignsByDay = useMemo(() => {
    const map = {};
    campaigns.forEach(c => {
      const ds = c.scheduledAt || c.createdAt;
      if (!ds) return;
      const d = new Date(ds);
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

  const makeDateStr = useCallback((day) =>
    `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`, [year, month]);

  const monthStats = useMemo(() => {
    const s = { total: 0, scheduled: 0, completed: 0, failed: 0 };
    campaigns.forEach(c => {
      const ds = c.scheduledAt || c.createdAt;
      if (!ds) return;
      const d = new Date(ds);
      if (d.getFullYear() === year && d.getMonth() === month) {
        s.total++;
        if (c.status === 'scheduled') s.scheduled++;
        if (c.status === 'completed' || c.status === 'sent') s.completed++;
        if (c.status === 'failed') s.failed++;
      }
    });
    return s;
  }, [campaigns, year, month]);

  // Drag handlers
  const handleDragStart = (e, campaign) => {
    setDraggedCampaign(campaign);
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', campaign.id);
  };
  const handleDragOver = (e, day) => {
    if (!day || !draggedCampaign) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    setDragOverDay(day);
  };
  const handleDragLeave = () => setDragOverDay(null);
  const handleDrop = (e, day) => {
    e.preventDefault();
    if (draggedCampaign && day) {
      onMoveCampaign?.(draggedCampaign.id, makeDateStr(day));
    }
    setDraggedCampaign(null);
    setDragOverDay(null);
  };
  const handleDragEnd = () => { setDraggedCampaign(null); setDragOverDay(null); };

  // Context menu for duplicate
  const handleContextMenu = (e, campaign) => {
    e.preventDefault();
    e.stopPropagation();
    setContextMenu({ x: e.clientX, y: e.clientY, campaign });
  };

  // Close context menu on click anywhere
  const closeContextMenu = () => setContextMenu(null);

  return (
    <div style={{ marginBottom: '16px', padding: '16px', borderRadius: '12px', background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(139,92,246,0.2)' }}
      onClick={closeContextMenu}>

      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px' }}>
        <button type="button" onClick={() => setCurrentDate(new Date(year, month - 1, 1))}
          style={{ background: 'rgba(139,92,246,0.2)', border: '1px solid rgba(139,92,246,0.3)', color: '#fff', borderRadius: '8px', padding: '6px 14px', fontSize: '14px', cursor: 'pointer' }}>◀</button>
        <div style={{ textAlign: 'center' }}>
          <div style={{ color: '#fff', fontWeight: 600, fontSize: '15px' }}>📅 {MONTHS_FR[month]} {year}</div>
          {monthStats.total > 0 && (
            <div style={{ fontSize: '11px', color: 'rgba(255,255,255,0.5)', marginTop: '2px' }}>
              {monthStats.total} campagne{monthStats.total > 1 ? 's' : ''}
              {monthStats.scheduled > 0 && <span style={{ color: '#3b82f6' }}> • {monthStats.scheduled} prog.</span>}
              {monthStats.completed > 0 && <span style={{ color: '#22c55e' }}> • {monthStats.completed} ok</span>}
            </div>
          )}
        </div>
        <div style={{ display: 'flex', gap: '6px' }}>
          <button type="button" onClick={() => setCurrentDate(new Date())}
            style={{ background: 'rgba(139,92,246,0.15)', border: '1px solid rgba(139,92,246,0.3)', color: '#c4b5fd', borderRadius: '8px', padding: '5px 10px', fontSize: '11px', cursor: 'pointer' }}>Auj.</button>
          <button type="button" onClick={() => onDayClick?.(makeDateStr(today.getDate()))}
            style={{ background: 'linear-gradient(135deg, #9333ea, #6366f1)', border: 'none', color: '#fff', borderRadius: '8px', padding: '5px 12px', fontSize: '11px', cursor: 'pointer', fontWeight: 600 }}>+ Créer</button>
          <button type="button" onClick={() => setCurrentDate(new Date(year, month + 1, 1))}
            style={{ background: 'rgba(139,92,246,0.2)', border: '1px solid rgba(139,92,246,0.3)', color: '#fff', borderRadius: '8px', padding: '6px 14px', fontSize: '14px', cursor: 'pointer' }}>▶</button>
        </div>
      </div>

      {/* Day names */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', gap: '2px', marginBottom: '2px' }}>
        {DAYS_FR.map(d => (
          <div key={d} style={{ textAlign: 'center', fontSize: '10px', color: 'rgba(255,255,255,0.35)', fontWeight: 600, padding: '4px 0' }}>{d}</div>
        ))}
      </div>

      {/* Grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', gap: '2px' }}>
        {calendarDays.map((day, idx) => {
          const dayCampaigns = day ? (campaignsByDay[day] || []) : [];
          const isDragTarget = dragOverDay === day;
          const todayBool = isToday(day);

          return (
            <div key={idx}
              onClick={() => { if (day) onDayClick?.(makeDateStr(day)); }}
              onDragOver={(e) => handleDragOver(e, day)}
              onDragLeave={handleDragLeave}
              onDrop={(e) => handleDrop(e, day)}
              style={{
                minHeight: '56px', padding: '3px', borderRadius: '6px',
                cursor: day ? 'pointer' : 'default',
                background: isDragTarget ? 'rgba(139,92,246,0.3)' : todayBool ? 'rgba(139,92,246,0.2)' : day ? 'rgba(255,255,255,0.02)' : 'transparent',
                border: isDragTarget ? '2px dashed #9333ea' : todayBool ? '2px solid rgba(139,92,246,0.5)' : day ? '1px solid rgba(255,255,255,0.05)' : 'none',
                transition: 'all 0.15s'
              }}>
              {day && (
                <>
                  <div style={{ fontSize: '11px', fontWeight: todayBool ? 700 : 400, color: todayBool ? '#c4b5fd' : 'rgba(255,255,255,0.55)', marginBottom: '1px' }}>{day}</div>
                  {dayCampaigns.slice(0, 3).map((c, i) => {
                    const sc = STATUS_COLORS[c.status] || STATUS_COLORS.draft;
                    return (
                      <div key={c.id || i}
                        draggable
                        onDragStart={(e) => handleDragStart(e, c)}
                        onDragEnd={handleDragEnd}
                        onClick={(e) => { e.stopPropagation(); onCampaignClick?.(c); }}
                        onContextMenu={(e) => handleContextMenu(e, c)}
                        title={`${c.name} (${sc.label}) — Glisser pour déplacer`}
                        style={{
                          fontSize: '9px', lineHeight: '1.2', padding: '2px 4px', marginBottom: '1px',
                          borderRadius: '3px', background: sc.bg, borderLeft: `2px solid ${sc.border}`,
                          color: '#fff', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                          cursor: 'grab', opacity: draggedCampaign?.id === c.id ? 0.4 : 1
                        }}>
                        {c.name}
                      </div>
                    );
                  })}
                  {dayCampaigns.length > 3 && (
                    <div style={{ fontSize: '8px', color: 'rgba(255,255,255,0.35)', textAlign: 'center' }}>+{dayCampaigns.length - 3}</div>
                  )}
                </>
              )}
            </div>
          );
        })}
      </div>

      {/* Legend */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '10px', marginTop: '10px', paddingTop: '8px', borderTop: '1px solid rgba(255,255,255,0.06)' }}>
        {Object.entries(STATUS_COLORS).filter(([k]) => k !== 'sent').map(([key, val]) => (
          <div key={key} style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
            <div style={{ width: '7px', height: '7px', borderRadius: '50%', background: val.border }} />
            <span style={{ fontSize: '10px', color: 'rgba(255,255,255,0.4)' }}>{val.label}</span>
          </div>
        ))}
        <span style={{ fontSize: '10px', color: 'rgba(255,255,255,0.3)', marginLeft: 'auto' }}>Glisser pour déplacer • Clic droit pour dupliquer</span>
      </div>

      {/* Context Menu */}
      {contextMenu && (
        <div style={{
          position: 'fixed', left: contextMenu.x, top: contextMenu.y, zIndex: 10000,
          background: '#1a1025', borderRadius: '8px', border: '1px solid rgba(139,92,246,0.4)',
          boxShadow: '0 8px 24px rgba(0,0,0,0.5)', overflow: 'hidden', minWidth: '150px'
        }}>
          <button type="button"
            onClick={(e) => { e.stopPropagation(); onCampaignClick?.(contextMenu.campaign); setContextMenu(null); }}
            style={{ display: 'block', width: '100%', padding: '10px 14px', background: 'none', border: 'none', color: '#fff', fontSize: '13px', cursor: 'pointer', textAlign: 'left' }}
            onMouseEnter={e => e.currentTarget.style.background = 'rgba(139,92,246,0.15)'}
            onMouseLeave={e => e.currentTarget.style.background = 'transparent'}>
            ✏️ Modifier
          </button>
          <button type="button"
            onClick={(e) => { e.stopPropagation(); onDuplicateCampaign?.(contextMenu.campaign); setContextMenu(null); }}
            style={{ display: 'block', width: '100%', padding: '10px 14px', background: 'none', border: 'none', color: '#fff', fontSize: '13px', cursor: 'pointer', textAlign: 'left' }}
            onMouseEnter={e => e.currentTarget.style.background = 'rgba(139,92,246,0.15)'}
            onMouseLeave={e => e.currentTarget.style.background = 'transparent'}>
            📋 Dupliquer
          </button>
        </div>
      )}
    </div>
  );
}
