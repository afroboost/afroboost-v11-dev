/**
 * ContactsManager.js — V146: Gestion centralisée des contacts
 * - Liste unifiée (participants + users + groupes)
 * - Sync Google Contacts OAuth2
 * - Import CSV/vCard
 * - Recherche, tags, catégories
 * - V146: Sélection multiple, suppression en masse, export CSV
 */
import React, { useState, useEffect, useRef, useCallback } from 'react';
import axios from 'axios';
import { parseContacts } from '../../utils/contactParser';

export default function ContactsManager({ API, coachEmail }) {
  const [contacts, setContacts] = useState([]);
  const [loading, setLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [filterType, setFilterType] = useState('all');
  const [googleStatus, setGoogleStatus] = useState({ connected: false, configured: false, last_sync: null });
  const [syncing, setSyncing] = useState(false);
  const [syncProgress, setSyncProgress] = useState(0);
  const [syncMessage, setSyncMessage] = useState('');
  const [showImport, setShowImport] = useState(false);
  const [importResult, setImportResult] = useState(null);
  const [deduping, setDeduping] = useState(false);
  const importRef = useRef(null);

  // V146: Sélection multiple
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [deleting, setDeleting] = useState(false);

  const headers = { 'X-User-Email': coachEmail || '' };

  const loadContacts = useCallback(async () => {
    setLoading(true);
    try {
      const res = await axios.get(`${API}/contacts/all`, { headers });
      if (res.data.success) {
        setContacts(res.data.contacts || []);
      }
    } catch (err) {
      console.error('Load contacts error:', err);
    } finally {
      setLoading(false);
    }
  }, [API, coachEmail]);

  const checkGoogleStatus = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/google-contacts/status`, { headers });
      setGoogleStatus(res.data);
    } catch (err) {
      console.error('Google status check error:', err);
    }
  }, [API, coachEmail]);

  useEffect(() => {
    loadContacts();
    checkGoogleStatus();
  }, [loadContacts, checkGoogleStatus]);

  // Google OAuth
  const connectGoogle = async () => {
    try {
      const res = await axios.get(`${API}/google-contacts/auth-url`, { headers });
      if (res.data.auth_url) {
        window.open(res.data.auth_url, 'google-auth', 'width=500,height=700,left=200,top=100');
        const poll = setInterval(async () => {
          const status = await axios.get(`${API}/google-contacts/status`, { headers });
          if (status.data.connected) {
            setGoogleStatus(status.data);
            clearInterval(poll);
          }
        }, 2000);
        setTimeout(() => clearInterval(poll), 60000);
      }
    } catch (err) {
      alert(err.response?.data?.detail || 'Erreur connexion Google');
    }
  };

  const syncGoogleContacts = async () => {
    setSyncing(true);
    setSyncProgress(10);
    setSyncMessage('Connexion à Google...');
    try {
      setSyncProgress(30);
      setSyncMessage('Récupération des contacts...');
      const res = await axios.post(`${API}/google-contacts/sync`, {}, { headers });
      setSyncProgress(90);
      setSyncMessage(res.data.message || 'Sync terminée');
      setTimeout(() => {
        setSyncProgress(100);
        loadContacts();
        checkGoogleStatus();
        setTimeout(() => {
          setSyncing(false);
          setSyncProgress(0);
          setSyncMessage('');
        }, 1500);
      }, 500);
    } catch (err) {
      setSyncMessage('❌ ' + (err.response?.data?.detail || 'Erreur sync'));
      setTimeout(() => { setSyncing(false); setSyncProgress(0); setSyncMessage(''); }, 3000);
    }
  };

  // CSV/vCard import
  const handleFileImport = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = async (evt) => {
      const text = evt.target.result;
      const parsed = parseContacts(text, file.name);
      if (parsed.length === 0) {
        setImportResult({ imported: 0, message: '❌ Aucun contact trouvé dans le fichier' });
        return;
      }
      try {
        const res = await axios.post(`${API}/contacts/bulk-import`, {
          contacts: parsed.map(c => ({ name: c.name, phone: c.phone, email: c.email, source: 'import' })),
          source: 'import'
        }, { headers });
        setImportResult({
          imported: res.data.imported,
          duplicates: res.data.duplicates,
          errors: res.data.errors,
          message: `✅ ${res.data.imported} importés, ${res.data.duplicates} doublons ignorés`
        });
        loadContacts();
      } catch (err) {
        setImportResult({ imported: 0, message: '❌ Erreur import: ' + (err.response?.data?.detail || err.message) });
      }
    };
    reader.readAsText(file);
    e.target.value = '';
  };

  // Dédupliquer
  const deduplicateContacts = async () => {
    setDeduping(true);
    try {
      const res = await axios.post(`${API}/contacts/deduplicate`, {}, { headers });
      if (res.data.success) {
        setImportResult({ imported: 0, message: `✅ ${res.data.merged} doublons fusionnés (${res.data.total_before} → ${res.data.total_after} contacts)` });
        loadContacts();
      } else {
        setImportResult({ imported: 0, message: '❌ Erreur: ' + (res.data.error || 'inconnue') });
      }
    } catch (err) {
      setImportResult({ imported: 0, message: '❌ Erreur dédup: ' + (err.response?.data?.detail || err.message) });
    } finally {
      setDeduping(false);
    }
  };

  // V146: Toggle sélection d'un contact
  const toggleSelect = (id) => {
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  // V146: Sélectionner/Désélectionner tous les contacts visibles
  const toggleSelectAll = () => {
    const visibleIds = filtered.filter(c => c.type !== 'group').map(c => c.id);
    const allSelected = visibleIds.length > 0 && visibleIds.every(id => selectedIds.has(id));
    if (allSelected) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(visibleIds));
    }
  };

  // V146: Supprimer les contacts sélectionnés
  const deleteSelected = async () => {
    if (selectedIds.size === 0) return;
    const confirm = window.confirm(`Supprimer ${selectedIds.size} contact(s) ? Cette action est irréversible.`);
    if (!confirm) return;

    setDeleting(true);
    try {
      const res = await axios.post(`${API}/contacts/bulk-delete`, {
        ids: Array.from(selectedIds)
      }, { headers });
      if (res.data.success) {
        setImportResult({ imported: 0, message: `🗑️ ${res.data.deleted} contact(s) supprimé(s)` });
        setSelectedIds(new Set());
        loadContacts();
      }
    } catch (err) {
      setImportResult({ imported: 0, message: '❌ Erreur suppression: ' + (err.response?.data?.detail || err.message) });
    } finally {
      setDeleting(false);
    }
  };

  // V146: Export CSV
  const exportCSV = () => {
    const contactsToExport = selectedIds.size > 0
      ? filtered.filter(c => selectedIds.has(c.id))
      : filtered.filter(c => c.type !== 'group');

    if (contactsToExport.length === 0) {
      setImportResult({ imported: 0, message: '⚠️ Aucun contact à exporter' });
      return;
    }

    const header = 'Nom,Email,Téléphone,Source,Tags';
    const rows = contactsToExport.map(c =>
      [
        `"${(c.name || '').replace(/"/g, '""')}"`,
        `"${(c.email || '').replace(/"/g, '""')}"`,
        `"${(c.phone || '').replace(/"/g, '""')}"`,
        `"${(c.source || '').replace(/"/g, '""')}"`,
        `"${(c.tags || []).join(', ')}"`
      ].join(',')
    );

    const csv = [header, ...rows].join('\n');
    const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `contacts_afroboost_${new Date().toISOString().slice(0, 10)}.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);

    setImportResult({ imported: 0, message: `📥 ${contactsToExport.length} contact(s) exporté(s) en CSV` });
  };

  // Filtered contacts
  const filtered = contacts.filter(c => {
    const matchSearch = !searchQuery ||
      (c.name || '').toLowerCase().includes(searchQuery.toLowerCase()) ||
      (c.email || '').toLowerCase().includes(searchQuery.toLowerCase()) ||
      (c.phone || '').includes(searchQuery);
    const matchType =
      filterType === 'all' ? true :
      filterType === 'group' ? c.type === 'group' :
      filterType === 'google' ? c.source === 'google' :
      c.type === 'user';
    return matchSearch && matchType;
  });

  const groupsCount = contacts.filter(c => c.type === 'group').length;
  const usersCount = contacts.filter(c => c.type === 'user').length;
  const googleCount = contacts.filter(c => c.source === 'google').length;
  const visibleUserIds = filtered.filter(c => c.type !== 'group').map(c => c.id);
  const allVisibleSelected = visibleUserIds.length > 0 && visibleUserIds.every(id => selectedIds.has(id));

  return (
    <div style={{ padding: '0' }}>
      {/* Header stats */}
      <div style={{ display: 'flex', gap: '8px', marginBottom: '16px', flexWrap: 'wrap' }}>
        {[
          { label: 'Total', count: contacts.length, color: '#c4b5fd' },
          { label: 'Groupes', count: groupsCount, color: '#a855f7' },
          { label: 'Contacts', count: usersCount, color: '#3b82f6' },
          { label: 'Google', count: googleCount, color: '#22c55e' }
        ].map(s => (
          <div key={s.label} style={{
            flex: 1, minWidth: '70px', padding: '10px 8px', borderRadius: '10px',
            background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.08)', textAlign: 'center'
          }}>
            <div style={{ fontSize: '20px', fontWeight: 700, color: s.color }}>{s.count}</div>
            <div style={{ fontSize: '10px', color: 'rgba(255,255,255,0.5)', marginTop: '2px' }}>{s.label}</div>
          </div>
        ))}
      </div>

      {/* Google Sync Section */}
      <div style={{
        padding: '14px', borderRadius: '12px', marginBottom: '16px',
        background: googleStatus.connected ? 'rgba(34,197,94,0.06)' : 'rgba(59,130,246,0.06)',
        border: `1px solid ${googleStatus.connected ? 'rgba(34,197,94,0.3)' : 'rgba(59,130,246,0.3)'}`
      }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: syncing ? '10px' : '0', flexWrap: 'wrap', gap: '8px' }}>
          <div>
            <span style={{ fontSize: '13px', fontWeight: 600, color: '#fff' }}>
              {googleStatus.connected ? '✅ Google Contacts connecté' : '🔗 Connecter Google Contacts'}
            </span>
            {googleStatus.last_sync && (
              <span style={{ fontSize: '11px', color: 'rgba(255,255,255,0.4)', marginLeft: '8px' }}>
                Dernière sync: {new Date(googleStatus.last_sync).toLocaleDateString('fr-FR')}
              </span>
            )}
          </div>
          <div style={{ display: 'flex', gap: '8px' }}>
            {!googleStatus.connected ? (
              <button onClick={connectGoogle} disabled={!googleStatus.configured} style={{
                padding: '8px 16px', borderRadius: '8px', border: 'none', fontSize: '12px', fontWeight: 600,
                cursor: googleStatus.configured ? 'pointer' : 'not-allowed',
                background: googleStatus.configured ? 'linear-gradient(135deg, #4285f4, #34a853)' : 'rgba(255,255,255,0.1)',
                color: '#fff', opacity: googleStatus.configured ? 1 : 0.5
              }}>
                🔗 Connecter
              </button>
            ) : (
              <button onClick={syncGoogleContacts} disabled={syncing} style={{
                padding: '8px 16px', borderRadius: '8px', border: 'none', fontSize: '12px', fontWeight: 600,
                cursor: syncing ? 'not-allowed' : 'pointer',
                background: syncing ? 'rgba(34,197,94,0.2)' : 'linear-gradient(135deg, #22c55e, #16a34a)',
                color: '#fff'
              }}>
                {syncing ? '⏳ Sync en cours...' : '🔄 Synchroniser'}
              </button>
            )}
          </div>
        </div>
        {!googleStatus.configured && (
          <p style={{ fontSize: '11px', color: '#f59e0b', margin: '8px 0 0 0' }}>
            ⚠️ Google OAuth non configuré. Ajoutez GOOGLE_CONTACTS_CLIENT_ID dans les variables Vercel.
          </p>
        )}
        {syncing && (
          <div>
            <div style={{ width: '100%', height: '6px', borderRadius: '3px', background: 'rgba(255,255,255,0.1)', overflow: 'hidden' }}>
              <div style={{ width: `${syncProgress}%`, height: '100%', borderRadius: '3px', background: 'linear-gradient(90deg, #22c55e, #34d399)', transition: 'width 0.5s ease' }} />
            </div>
            {syncMessage && <p style={{ fontSize: '11px', color: 'rgba(255,255,255,0.6)', margin: '6px 0 0 0' }}>{syncMessage}</p>}
          </div>
        )}
      </div>

      {/* Import + Actions row */}
      <div style={{ display: 'flex', gap: '6px', marginBottom: '16px', flexWrap: 'wrap' }}>
        <input ref={importRef} type="file" accept=".csv,.vcf,.txt" onChange={handleFileImport} style={{ display: 'none' }} />
        <button onClick={() => importRef.current?.click()} style={{
          flex: '1 1 auto', padding: '10px', borderRadius: '8px', fontSize: '12px', fontWeight: 500,
          background: 'rgba(217,28,210,0.08)', border: '1px dashed rgba(217,28,210,0.4)',
          color: '#D91CD2', cursor: 'pointer', minWidth: '120px'
        }}>
          📤 Importer CSV / vCard
        </button>
        <button onClick={exportCSV} title="Exporter en CSV" style={{
          padding: '10px 14px', borderRadius: '8px', fontSize: '12px', fontWeight: 500,
          background: 'rgba(59,130,246,0.1)', border: '1px solid rgba(59,130,246,0.3)',
          color: '#60a5fa', cursor: 'pointer'
        }}>
          📥 Export
        </button>
        <button onClick={deduplicateContacts} disabled={deduping} title="Fusionner les doublons" style={{
          padding: '10px 14px', borderRadius: '8px', fontSize: '12px', fontWeight: 500,
          background: 'rgba(245,158,11,0.1)', border: '1px solid rgba(245,158,11,0.3)',
          color: '#f59e0b', cursor: deduping ? 'not-allowed' : 'pointer'
        }}>
          {deduping ? '⏳' : '🧹'}
        </button>
        <button onClick={loadContacts} disabled={loading} style={{
          padding: '10px 14px', borderRadius: '8px', fontSize: '12px', fontWeight: 500,
          background: 'rgba(139,92,246,0.1)', border: '1px solid rgba(139,92,246,0.3)',
          color: '#c4b5fd', cursor: 'pointer'
        }}>
          🔄
        </button>
      </div>

      {/* V146: Barre d'actions sélection */}
      {selectedIds.size > 0 && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: '10px', padding: '10px 14px',
          borderRadius: '10px', marginBottom: '12px',
          background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.3)',
          flexWrap: 'wrap'
        }}>
          <span style={{ fontSize: '13px', color: '#fff', fontWeight: 600 }}>
            {selectedIds.size} sélectionné{selectedIds.size > 1 ? 's' : ''}
          </span>
          <button onClick={deleteSelected} disabled={deleting} style={{
            padding: '6px 14px', borderRadius: '8px', fontSize: '12px', fontWeight: 600,
            background: 'rgba(239,68,68,0.2)', border: '1px solid rgba(239,68,68,0.5)',
            color: '#f87171', cursor: deleting ? 'not-allowed' : 'pointer'
          }}>
            {deleting ? '⏳ Suppression...' : '🗑️ Supprimer'}
          </button>
          <button onClick={exportCSV} style={{
            padding: '6px 14px', borderRadius: '8px', fontSize: '12px', fontWeight: 600,
            background: 'rgba(59,130,246,0.15)', border: '1px solid rgba(59,130,246,0.4)',
            color: '#60a5fa', cursor: 'pointer'
          }}>
            📥 Exporter la sélection
          </button>
          <button onClick={() => setSelectedIds(new Set())} style={{
            padding: '6px 10px', borderRadius: '8px', fontSize: '11px',
            background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.15)',
            color: 'rgba(255,255,255,0.6)', cursor: 'pointer', marginLeft: 'auto'
          }}>
            ✕ Annuler
          </button>
        </div>
      )}

      {importResult && (
        <div style={{
          padding: '10px', borderRadius: '8px', marginBottom: '12px',
          background: importResult.message?.includes('✅') || importResult.message?.includes('🗑️') || importResult.message?.includes('📥') ? 'rgba(34,197,94,0.1)' : 'rgba(239,68,68,0.1)',
          border: `1px solid ${importResult.message?.includes('✅') || importResult.message?.includes('🗑️') || importResult.message?.includes('📥') ? 'rgba(34,197,94,0.3)' : 'rgba(239,68,68,0.3)'}`
        }}>
          <p style={{ fontSize: '12px', color: '#fff', margin: 0 }}>{importResult.message}</p>
          <button onClick={() => setImportResult(null)} style={{
            background: 'none', border: 'none', color: 'rgba(255,255,255,0.4)', fontSize: '11px', cursor: 'pointer', padding: '4px 0', marginTop: '4px'
          }}>Fermer</button>
        </div>
      )}

      {/* Search + Filters */}
      <div style={{ marginBottom: '12px' }}>
        <input
          placeholder="🔍 Rechercher par nom, email, téléphone..."
          value={searchQuery}
          onChange={e => setSearchQuery(e.target.value)}
          style={{
            width: '100%', padding: '10px 14px', borderRadius: '8px',
            background: 'rgba(255,255,255,0.08)', border: '1px solid rgba(139,92,246,0.3)',
            color: '#fff', fontSize: '13px', outline: 'none', boxSizing: 'border-box', marginBottom: '8px'
          }}
        />
        <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
          {[
            { key: 'all', label: 'Tous' },
            { key: 'group', label: '👥 Groupes' },
            { key: 'user', label: '👤 Contacts' },
            { key: 'google', label: '🔵 Google' }
          ].map(f => (
            <button key={f.key} onClick={() => setFilterType(f.key)} style={{
              padding: '5px 12px', borderRadius: '20px', fontSize: '11px', fontWeight: 500, cursor: 'pointer',
              background: filterType === f.key ? 'rgba(139,92,246,0.3)' : 'rgba(255,255,255,0.05)',
              border: filterType === f.key ? '1px solid rgba(139,92,246,0.5)' : '1px solid rgba(255,255,255,0.1)',
              color: filterType === f.key ? '#c4b5fd' : 'rgba(255,255,255,0.5)'
            }}>
              {f.label}
            </button>
          ))}
        </div>
      </div>

      {/* V146: Sélectionner tout checkbox */}
      {filtered.some(c => c.type !== 'group') && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: '8px', padding: '8px 14px',
          borderBottom: '1px solid rgba(255,255,255,0.08)', background: 'rgba(255,255,255,0.02)',
          borderRadius: '10px 10px 0 0'
        }}>
          <input
            type="checkbox"
            checked={allVisibleSelected}
            onChange={toggleSelectAll}
            style={{ width: '16px', height: '16px', accentColor: '#8b5cf6', cursor: 'pointer' }}
          />
          <span style={{ fontSize: '12px', color: 'rgba(255,255,255,0.5)', fontWeight: 500 }}>
            Sélectionner tout ({visibleUserIds.length})
          </span>
        </div>
      )}

      {/* Contacts List */}
      <div style={{
        maxHeight: '400px', overflowY: 'auto',
        borderRadius: filtered.some(c => c.type !== 'group') ? '0 0 10px 10px' : '10px',
        border: '1px solid rgba(255,255,255,0.08)',
        borderTop: filtered.some(c => c.type !== 'group') ? 'none' : undefined
      }}>
        {loading ? (
          <div style={{ padding: '30px', textAlign: 'center', color: 'rgba(255,255,255,0.4)' }}>
            ⏳ Chargement...
          </div>
        ) : filtered.length === 0 ? (
          <div style={{ padding: '30px', textAlign: 'center', color: 'rgba(255,255,255,0.4)' }}>
            {searchQuery ? 'Aucun résultat' : 'Aucun contact'}
          </div>
        ) : (
          filtered.slice(0, 200).map((c, i) => {
            const isGroup = c.type === 'group';
            const isSelected = selectedIds.has(c.id);
            return (
              <div key={c.id || i} style={{
                display: 'flex', alignItems: 'center', gap: '8px',
                padding: '10px 14px', borderBottom: '1px solid rgba(255,255,255,0.04)',
                background: isSelected ? 'rgba(139,92,246,0.12)' : i % 2 === 0 ? 'rgba(255,255,255,0.02)' : 'transparent',
                cursor: isGroup ? 'default' : 'pointer',
                transition: 'background 0.15s'
              }}
                onClick={() => { if (!isGroup) toggleSelect(c.id); }}
              >
                {/* V146: Checkbox de sélection (pas pour les groupes) */}
                {!isGroup ? (
                  <input
                    type="checkbox"
                    checked={isSelected}
                    onChange={() => toggleSelect(c.id)}
                    onClick={e => e.stopPropagation()}
                    style={{ width: '16px', height: '16px', accentColor: '#8b5cf6', cursor: 'pointer', flexShrink: 0 }}
                  />
                ) : (
                  <span style={{ width: '16px', flexShrink: 0 }} />
                )}
                <span style={{ fontSize: '16px', width: '24px', textAlign: 'center', flexShrink: 0 }}>
                  {isGroup ? '👥' : c.source === 'google' ? '🔵' : '👤'}
                </span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: '13px', color: '#fff', fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {c.name || 'Sans nom'}
                  </div>
                  <div style={{ fontSize: '11px', color: 'rgba(255,255,255,0.4)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {isGroup ? `${c.member_count || 0} membres` : [c.email, c.phone].filter(Boolean).join(' • ') || 'Pas de coordonnées'}
                  </div>
                </div>
                {c.tags?.length > 0 && (
                  <div style={{ display: 'flex', gap: '4px', flexShrink: 0 }}>
                    {c.tags.slice(0, 2).map(t => (
                      <span key={t} style={{
                        padding: '2px 8px', borderRadius: '10px', fontSize: '10px',
                        background: t === 'google' ? 'rgba(34,197,94,0.15)' : 'rgba(139,92,246,0.15)',
                        color: t === 'google' ? '#22c55e' : '#c4b5fd',
                        border: `1px solid ${t === 'google' ? 'rgba(34,197,94,0.3)' : 'rgba(139,92,246,0.3)'}`
                      }}>{t}</span>
                    ))}
                  </div>
                )}
                <span style={{
                  padding: '2px 8px', borderRadius: '10px', fontSize: '10px',
                  background: c.source === 'google' ? 'rgba(34,197,94,0.1)' : c.source === 'app' ? 'rgba(59,130,246,0.1)' : 'rgba(217,28,210,0.1)',
                  color: c.source === 'google' ? '#22c55e' : c.source === 'app' ? '#3b82f6' : '#D91CD2',
                  flexShrink: 0
                }}>
                  {c.source === 'google' ? 'Google' : c.source === 'app' ? 'App' : c.source === 'stripe_payment' ? 'Stripe' : c.source || 'Import'}
                </span>
              </div>
            );
          })
        )}
        {filtered.length > 200 && (
          <div style={{ padding: '10px', textAlign: 'center', color: 'rgba(255,255,255,0.4)', fontSize: '12px' }}>
            ... et {filtered.length - 200} autres contacts
          </div>
        )}
      </div>
    </div>
  );
}
