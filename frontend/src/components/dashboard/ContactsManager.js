/**
 * ContactsManager.js â V146: Gestion centralisÃ©e des contacts
 * - Liste unifiÃ©e (participants + users + groupes)
 * - Sync Google Contacts OAuth2
 * - Import CSV/vCard
 * - Recherche, tags, catÃ©gories
 * - V146: SÃ©lection multiple, suppression en masse, export CSV
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

  // V146: SÃ©lection multiple
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [deleting, setDeleting] = useState(false);

  // V154: CatÃ©gories de contacts
  const [categories, setCategories] = useState([]);
  const [filterCategory, setFilterCategory] = useState('all');
  const [showCategoryManager, setShowCategoryManager] = useState(false);
  const [newCatName, setNewCatName] = useState('');
  const [newCatColor, setNewCatColor] = useState('#8B5CF6');
  const [newCatIcon, setNewCatIcon] = useState('ð');
  const [editingCat, setEditingCat] = useState(null);
  const [assigningCategory, setAssigningCategory] = useState(false);

  const headers = { 'X-User-Email': coachEmail || '' };

  // V161: Birthday Calendar states
  var _bdm = useState(new Date().getMonth());
  var birthdayMonth = _bdm[0]; var setBirthdayMonth = _bdm[1];
  var _bdy = useState(new Date().getFullYear());
  var birthdayYear = _bdy[0]; var setBirthdayYear = _bdy[1];
  var _bdd = useState([]);
  var birthdayData = _bdd[0]; var setBirthdayData = _bdd[1];
  var _bdl = useState(false);
  var birthdayLoading = _bdl[0]; var setBirthdayLoading = _bdl[1];

  // V161: Fetch all participants with birthdays
  var fetchBirthdays = React.useCallback(function() {
    setBirthdayLoading(true);
    fetch(API + '/chat/participants', { headers: headers })
      .then(function(r) { return r.json(); })
      .then(function(data) {
        var arr = Array.isArray(data) ? data : [];
        var withBday = arr.filter(function(p) { return p.birthday; });
        setBirthdayData(withBday);
        setBirthdayLoading(false);
      })
      .catch(function() { setBirthdayLoading(false); });
  }, [API]);

  React.useEffect(function() {
    if (filterType === 'birthday') { fetchBirthdays(); }
  }, [filterType, fetchBirthdays]);

  var getBirthdayCalendar = function() {
    var firstDay = new Date(birthdayYear, birthdayMonth, 1).getDay();
    var daysInMonth = new Date(birthdayYear, birthdayMonth + 1, 0).getDate();
    var weeks = [];
    var currentWeek = [];
    for (var d = 0; d < firstDay; d++) { currentWeek.push(null); }
    for (var day = 1; day <= daysInMonth; day++) {
      var mm = String(birthdayMonth + 1).padStart(2, '0');
      var dd = String(day).padStart(2, '0');
      var key = mm + '-' + dd;
      var matches = birthdayData.filter(function(p) { return p.birthday === key; });
      currentWeek.push({ day: day, matches: matches });
      if (currentWeek.length === 7) { weeks.push(currentWeek); currentWeek = []; }
    }
    if (currentWeek.length > 0) {
      while (currentWeek.length < 7) currentWeek.push(null);
      weeks.push(currentWeek);
    }
    return weeks;
  };

  var monthNames = ['Janvier','F\u00e9vrier','Mars','Avril','Mai','Juin','Juillet','Ao\u00fbt','Septembre','Octobre','Novembre','D\u00e9cembre'];

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

  // V154: Load categories
  const loadCategories = useCallback(async () => {
    try {
      var res = await axios.get(API + '/contact-categories', { headers: headers });
      if (res.data.success) {
        setCategories(res.data.categories || []);
      }
    } catch (err) {
      console.error('Load categories error:', err);
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
    loadCategories();
  }, [loadContacts, checkGoogleStatus, loadCategories]);

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
    setSyncMessage('Connexion Ã  Google...');
    try {
      setSyncProgress(30);
      setSyncMessage('RÃ©cupÃ©ration des contacts...');
      const res = await axios.post(`${API}/google-contacts/sync`, {}, { headers });
      setSyncProgress(90);
      setSyncMessage(res.data.message || 'Sync terminÃ©e');
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
      setSyncMessage('â ' + (err.response?.data?.detail || 'Erreur sync'));
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
        setImportResult({ imported: 0, message: 'â Aucun contact trouvÃ© dans le fichier' });
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
          message: `â ${res.data.imported} importÃ©s, ${res.data.duplicates} doublons ignorÃ©s`
        });
        loadContacts();
      } catch (err) {
        setImportResult({ imported: 0, message: 'â Erreur import: ' + (err.response?.data?.detail || err.message) });
      }
    };
    reader.readAsText(file);
    e.target.value = '';
  };

  // DÃ©dupliquer
  const deduplicateContacts = async () => {
    setDeduping(true);
    try {
      const res = await axios.post(`${API}/contacts/deduplicate`, {}, { headers });
      if (res.data.success) {
        setImportResult({ imported: 0, message: `â ${res.data.merged} doublons fusionnÃ©s (${res.data.total_before} â ${res.data.total_after} contacts)` });
        loadContacts();
      } else {
        setImportResult({ imported: 0, message: 'â Erreur: ' + (res.data.error || 'inconnue') });
      }
    } catch (err) {
      setImportResult({ imported: 0, message: 'â Erreur dÃ©dup: ' + (err.response?.data?.detail || err.message) });
    } finally {
      setDeduping(false);
    }
  };

  // V146: Toggle sÃ©lection d'un contact
  const toggleSelect = (id) => {
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  // V146: SÃ©lectionner/DÃ©sÃ©lectionner tous les contacts visibles
  const toggleSelectAll = () => {
    const visibleIds = filtered.filter(c => c.type !== 'group').map(c => c.id);
    const allSelected = visibleIds.length > 0 && visibleIds.every(id => selectedIds.has(id));
    if (allSelected) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(visibleIds));
    }
  };

  // V146: Supprimer les contacts sÃ©lectionnÃ©s
  const deleteSelected = async () => {
    if (selectedIds.size === 0) return;
    const confirm = window.confirm(`Supprimer ${selectedIds.size} contact(s) ? Cette action est irrÃ©versible.`);
    if (!confirm) return;

    setDeleting(true);
    try {
      const res = await axios.post(`${API}/contacts/bulk-delete`, {
        ids: Array.from(selectedIds)
      }, { headers });
      if (res.data.success) {
        setImportResult({ imported: 0, message: `ðï¸ ${res.data.deleted} contact(s) supprimÃ©(s)` });
        setSelectedIds(new Set());
        loadContacts();
      }
    } catch (err) {
      setImportResult({ imported: 0, message: 'â Erreur suppression: ' + (err.response?.data?.detail || err.message) });
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
      setImportResult({ imported: 0, message: 'â ï¸ Aucun contact Ã  exporter' });
      return;
    }

    const header = 'Nom,Email,TÃ©lÃ©phone,Source,Tags,CatÃ©gories';
    const rows = contactsToExport.map(c => {
      var catNames = (c.categories || []).map(function(catId) {
        var cat = categories.find(function(ct) { return ct.id === catId; });
        return cat ? cat.name : '';
      }).filter(Boolean).join(', ');
      return [
        '"' + (c.name || '').replace(/"/g, '""') + '"',
        '"' + (c.email || '').replace(/"/g, '""') + '"',
        '"' + (c.phone || '').replace(/"/g, '""') + '"',
        '"' + (c.source || '').replace(/"/g, '""') + '"',
        '"' + (c.tags || []).join(', ') + '"',
        '"' + catNames + '"'
      ].join(',');
    });

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

    setImportResult({ imported: 0, message: `ð¥ ${contactsToExport.length} contact(s) exportÃ©(s) en CSV` });
  };

  // V154: Create category
  var createCategory = async function() {
    if (!newCatName.trim()) return;
    try {
      var res = await axios.post(API + '/contact-categories', {
        name: newCatName.trim(),
        color: newCatColor,
        icon: newCatIcon
      }, { headers: headers });
      if (res.data.success) {
        setNewCatName('');
        setNewCatIcon('ð');
        loadCategories();
      }
    } catch (err) {
      var msg = (err.response && err.response.data && err.response.data.detail) || 'Erreur';
      alert(msg);
    }
  };

  // V154: Delete category
  var deleteCategory = async function(catId) {
    if (!window.confirm('Supprimer cette catÃ©gorie ? Les contacts ne seront pas supprimÃ©s.')) return;
    try {
      await axios.delete(API + '/contact-categories/' + catId, { headers: headers });
      loadCategories();
      loadContacts();
    } catch (err) {
      console.error('Delete category error:', err);
    }
  };

  // V154: Assign categories to selected contacts
  var assignCategoryToSelected = async function(catId) {
    if (selectedIds.size === 0) return;
    setAssigningCategory(true);
    try {
      await axios.post(API + '/contacts/set-categories', {
        contact_ids: Array.from(selectedIds),
        category_ids: [catId],
        mode: 'add'
      }, { headers: headers });
      setImportResult({ imported: 0, message: 'â CatÃ©gorie assignÃ©e Ã  ' + selectedIds.size + ' contact(s)' });
      loadContacts();
    } catch (err) {
      setImportResult({ imported: 0, message: 'â Erreur assignation catÃ©gorie' });
    } finally {
      setAssigningCategory(false);
    }
  };

  // V154: Remove category from selected contacts
  var removeCategoryFromSelected = async function(catId) {
    if (selectedIds.size === 0) return;
    setAssigningCategory(true);
    try {
      await axios.post(API + '/contacts/set-categories', {
        contact_ids: Array.from(selectedIds),
        category_ids: [catId],
        mode: 'remove'
      }, { headers: headers });
      setImportResult({ imported: 0, message: 'â CatÃ©gorie retirÃ©e de ' + selectedIds.size + ' contact(s)' });
      loadContacts();
    } catch (err) {
      setImportResult({ imported: 0, message: 'â Erreur retrait catÃ©gorie' });
    } finally {
      setAssigningCategory(false);
    }
  };

  // Filtered contacts â V154: ajout filtre catÃ©gorie
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
    var matchCategory = filterCategory === 'all' ? true :
      filterCategory === '__uncategorized__' ? (!c.categories || c.categories.length === 0) :
      (c.categories && c.categories.indexOf(filterCategory) !== -1);
    return matchSearch && matchType && matchCategory;
  });

  const groupsCount = contacts.filter(c => c.type === 'group').length;
  const usersCount = contacts.filter(c => c.type === 'user').length;
  const googleCount = contacts.filter(c => c.source === 'google').length;
  const visibleUserIds = filtered.filter(c => c.type !== 'group').map(c => c.id);
  const allVisibleSelected = visibleUserIds.length > 0 && visibleUserIds.every(id => selectedIds.has(id));

  // V161: Early return for birthday calendar view
  if (filterType === 'birthday') {
    return React.createElement('div', { style: { padding: '10px', background: '#111', minHeight: '100%', color: '#fff' } },
      React.createElement('div', { style: { display: 'flex', gap: '8px', marginBottom: '15px', flexWrap: 'wrap' } },
        [
          { key: 'all', label: 'Tous' },
          { key: 'group', label: '\uD83D\uDC65 Groupes' },
          { key: 'user', label: '\uD83D\uDC64 Contacts' },
          { key: 'google', label: '\uD83D\uDD35 Google' },
          { key: 'birthday', label: '\uD83C\uDF82 Anniversaires' }
        ].map(function(f) {
          return React.createElement('button', {
            key: f.key,
            onClick: function() { setFilterType(f.key); },
            style: {
              padding: '5px 12px', borderRadius: '20px', fontSize: '11px', cursor: 'pointer',
              background: f.key === 'birthday' ? 'rgba(139,92,246,0.3)' : 'transparent',
              border: f.key === 'birthday' ? '1px solid rgba(139,92,246,0.5)' : '1px solid rgba(255,255,255,0.1)',
              color: f.key === 'birthday' ? '#c4b5fd' : 'rgba(255,255,255,0.5)'
            }
          }, f.label);
        })
      ),
      React.createElement('div', { style: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '15px' } },
        React.createElement('button', { onClick: function() { var m = birthdayMonth - 1; if (m < 0) { setBirthdayMonth(11); setBirthdayYear(birthdayYear - 1); } else { setBirthdayMonth(m); } }, style: { background: 'rgba(139,92,246,0.3)', border: 'none', color: '#c4b5fd', borderRadius: '50%', width: '32px', height: '32px', cursor: 'pointer', fontSize: '16px' } }, '\u25C0'),
        React.createElement('span', { style: { color: '#fff', fontSize: '16px', fontWeight: 'bold' } }, monthNames[birthdayMonth] + ' ' + birthdayYear),
        React.createElement('button', { onClick: function() { var m = birthdayMonth + 1; if (m > 11) { setBirthdayMonth(0); setBirthdayYear(birthdayYear + 1); } else { setBirthdayMonth(m); } }, style: { background: 'rgba(139,92,246,0.3)', border: 'none', color: '#c4b5fd', borderRadius: '50%', width: '32px', height: '32px', cursor: 'pointer', fontSize: '16px' } }, '\u25B6')
      ),
      React.createElement('div', { style: { display: 'flex', gap: '10px', marginBottom: '15px' } },
        React.createElement('div', { style: { flex: 1, background: 'rgba(139,92,246,0.15)', borderRadius: '10px', padding: '10px', textAlign: 'center' } },
          React.createElement('div', { style: { color: '#D91CD2', fontSize: '20px', fontWeight: 'bold' } }, birthdayData.length),
          React.createElement('div', { style: { color: 'rgba(255,255,255,0.6)', fontSize: '10px' } }, 'Total')
        ),
        React.createElement('div', { style: { flex: 1, background: 'rgba(217,28,210,0.15)', borderRadius: '10px', padding: '10px', textAlign: 'center' } },
          React.createElement('div', { style: { color: '#D91CD2', fontSize: '20px', fontWeight: 'bold' } }, birthdayData.filter(function(p) { var mm = String(birthdayMonth + 1).padStart(2, '0'); return p.birthday && p.birthday.substring(0, 2) === mm; }).length),
          React.createElement('div', { style: { color: 'rgba(255,255,255,0.6)', fontSize: '10px' } }, 'Ce mois')
        )
      ),
      React.createElement('div', { style: { display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', gap: '2px', marginBottom: '15px' } },
        ['Dim','Lun','Mar','Mer','Jeu','Ven','Sam'].map(function(d) { return React.createElement('div', { key: d, style: { textAlign: 'center', color: 'rgba(255,255,255,0.5)', fontSize: '10px', padding: '5px' } }, d); }),
        getBirthdayCalendar().map(function(week, wi) { return week.map(function(cell, ci) { if (!cell) return React.createElement('div', { key: 'e'+wi+ci, style: { padding: '5px', minHeight: '35px' } }); var hasBday = cell.matches && cell.matches.length > 0; return React.createElement('div', { key: 'c'+wi+ci, style: { padding: '3px', minHeight: '35px', textAlign: 'center', borderRadius: '6px', background: hasBday ? 'rgba(217,28,210,0.25)' : 'rgba(255,255,255,0.03)', border: hasBday ? '1px solid rgba(217,28,210,0.5)' : '1px solid transparent' } }, React.createElement('div', { style: { color: '#fff', fontSize: '11px' } }, cell.day), hasBday ? cell.matches.map(function(m) { return React.createElement('div', { key: m.id, style: { fontSize: '8px', color: '#D91CD2', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' } }, '\uD83C\uDF82 ' + (m.name || '').split(' ')[0]); }) : null); }); })
      ),
      React.createElement('div', { style: { color: '#c4b5fd', fontSize: '12px', fontWeight: 'bold', marginBottom: '8px' } }, 'Anniversaires en ' + monthNames[birthdayMonth]),
      birthdayData.filter(function(p) { var mm = String(birthdayMonth + 1).padStart(2, '0'); return p.birthday && p.birthday.substring(0, 2) === mm; }).sort(function(a, b) { return a.birthday.localeCompare(b.birthday); }).map(function(p) { return React.createElement('div', { key: p.id, style: { display: 'flex', alignItems: 'center', gap: '8px', padding: '6px 8px', borderRadius: '8px', background: 'rgba(255,255,255,0.05)', marginBottom: '4px' } }, React.createElement('span', { style: { fontSize: '16px' } }, '\uD83C\uDF82'), React.createElement('span', { style: { color: '#fff', fontSize: '12px', flex: 1 } }, p.name || 'Membre'), React.createElement('span', { style: { color: '#D91CD2', fontSize: '11px' } }, p.birthday)); }),
      birthdayLoading ? React.createElement('div', { style: { color: '#D91CD2', textAlign: 'center', padding: '20px' } }, 'Chargement...') : null
    );
  }

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
              {googleStatus.connected ? 'â Google Contacts connectÃ©' : 'ð Connecter Google Contacts'}
            </span>
            {googleStatus.last_sync && (
              <span style={{ fontSize: '11px', color: 'rgba(255,255,255,0.4)', marginLeft: '8px' }}>
                DerniÃ¨re sync: {new Date(googleStatus.last_sync).toLocaleDateString('fr-FR')}
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
                ð Connecter
              </button>
            ) : (
              <button onClick={syncGoogleContacts} disabled={syncing} style={{
                padding: '8px 16px', borderRadius: '8px', border: 'none', fontSize: '12px', fontWeight: 600,
                cursor: syncing ? 'not-allowed' : 'pointer',
                background: syncing ? 'rgba(34,197,94,0.2)' : 'linear-gradient(135deg, #22c55e, #16a34a)',
                color: '#fff'
              }}>
                {syncing ? 'â³ Sync en cours...' : 'ð Synchroniser'}
              </button>
            )}
          </div>
        </div>
        {!googleStatus.configured && (
          <p style={{ fontSize: '11px', color: '#f59e0b', margin: '8px 0 0 0' }}>
            â ï¸ Google OAuth non configurÃ©. Ajoutez GOOGLE_CONTACTS_CLIENT_ID dans les variables Vercel.
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
          ð¤ Importer CSV / vCard
        </button>
        <button onClick={exportCSV} title="Exporter en CSV" style={{
          padding: '10px 14px', borderRadius: '8px', fontSize: '12px', fontWeight: 500,
          background: 'rgba(59,130,246,0.1)', border: '1px solid rgba(59,130,246,0.3)',
          color: '#60a5fa', cursor: 'pointer'
        }}>
          ð¥ Export
        </button>
        <button onClick={deduplicateContacts} disabled={deduping} title="Fusionner les doublons" style={{
          padding: '10px 14px', borderRadius: '8px', fontSize: '12px', fontWeight: 500,
          background: 'rgba(245,158,11,0.1)', border: '1px solid rgba(245,158,11,0.3)',
          color: '#f59e0b', cursor: deduping ? 'not-allowed' : 'pointer'
        }}>
          {deduping ? 'â³' : 'ð§¹'}
        </button>
        <button onClick={loadContacts} disabled={loading} style={{
          padding: '10px 14px', borderRadius: '8px', fontSize: '12px', fontWeight: 500,
          background: 'rgba(139,92,246,0.1)', border: '1px solid rgba(139,92,246,0.3)',
          color: '#c4b5fd', cursor: 'pointer'
        }}>
          ð
        </button>
      </div>

      {/* V146: Barre d'actions sÃ©lection */}
      {selectedIds.size > 0 && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: '10px', padding: '10px 14px',
          borderRadius: '10px', marginBottom: '12px',
          background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.3)',
          flexWrap: 'wrap'
        }}>
          <span style={{ fontSize: '13px', color: '#fff', fontWeight: 600 }}>
            {selectedIds.size} sÃ©lectionnÃ©{selectedIds.size > 1 ? 's' : ''}
          </span>
          <button onClick={deleteSelected} disabled={deleting} style={{
            padding: '6px 14px', borderRadius: '8px', fontSize: '12px', fontWeight: 600,
            background: 'rgba(239,68,68,0.2)', border: '1px solid rgba(239,68,68,0.5)',
            color: '#f87171', cursor: deleting ? 'not-allowed' : 'pointer'
          }}>
            {deleting ? 'â³ Suppression...' : 'ðï¸ Supprimer'}
          </button>
          <button onClick={exportCSV} style={{
            padding: '6px 14px', borderRadius: '8px', fontSize: '12px', fontWeight: 600,
            background: 'rgba(59,130,246,0.15)', border: '1px solid rgba(59,130,246,0.4)',
            color: '#60a5fa', cursor: 'pointer'
          }}>
            ð¥ Exporter la sÃ©lection
          </button>
          {/* V154: Category assignment for selected */}
          {categories.length > 0 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              <div style={{ display: 'flex', gap: '4px', alignItems: 'center', flexWrap: 'wrap' }}>
                <span style={{ fontSize: '11px', color: 'rgba(34,197,94,0.7)', whiteSpace: 'nowrap', fontWeight: 600 }}>+ Ajouter:</span>
                {categories.map(function(cat) {
                  return (
                    <button key={cat.id} onClick={function() { assignCategoryToSelected(cat.id); }}
                      disabled={assigningCategory}
                      title={'Ajouter Â« ' + cat.name + ' Â»'}
                      style={{
                        padding: '4px 10px', borderRadius: '6px', fontSize: '11px', fontWeight: 600,
                        background: cat.color + '20', border: '1px solid ' + cat.color + '44',
                        color: cat.color, cursor: assigningCategory ? 'not-allowed' : 'pointer',
                        display: 'inline-flex', alignItems: 'center', gap: '3px'
                      }}>
                      {cat.icon} {cat.name}
                    </button>
                  );
                })}
              </div>
              <div style={{ display: 'flex', gap: '4px', alignItems: 'center', flexWrap: 'wrap' }}>
                <span style={{ fontSize: '11px', color: 'rgba(239,68,68,0.7)', whiteSpace: 'nowrap', fontWeight: 600 }}>â Retirer:</span>
                {categories.map(function(cat) {
                  return (
                    <button key={cat.id} onClick={function() { removeCategoryFromSelected(cat.id); }}
                      disabled={assigningCategory}
                      title={'Retirer Â« ' + cat.name + ' Â»'}
                      style={{
                        padding: '4px 10px', borderRadius: '6px', fontSize: '11px', fontWeight: 600,
                        background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.25)',
                        color: '#f87171', cursor: assigningCategory ? 'not-allowed' : 'pointer',
                        display: 'inline-flex', alignItems: 'center', gap: '3px'
                      }}>
                      {cat.icon} {cat.name}
                    </button>
                  );
                })}
              </div>
            </div>
          )}
          <button onClick={() => setSelectedIds(new Set())} style={{
            padding: '6px 10px', borderRadius: '8px', fontSize: '11px',
            background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.15)',
            color: 'rgba(255,255,255,0.6)', cursor: 'pointer', marginLeft: 'auto'
          }}>
            â Annuler
          </button>
        </div>
      )}

      {importResult && (
        <div style={{
          padding: '10px', borderRadius: '8px', marginBottom: '12px',
          background: importResult.message?.includes('â') || importResult.message?.includes('ðï¸') || importResult.message?.includes('ð¥') ? 'rgba(34,197,94,0.1)' : 'rgba(239,68,68,0.1)',
          border: `1px solid ${importResult.message?.includes('â') || importResult.message?.includes('ðï¸') || importResult.message?.includes('ð¥') ? 'rgba(34,197,94,0.3)' : 'rgba(239,68,68,0.3)'}`
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
          placeholder="ð Rechercher par nom, email, tÃ©lÃ©phone..."
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
            { key: 'group', label: 'ð¥ Groupes' },
            { key: 'user', label: 'ð¤ Contacts' },
            { key: 'google', label: 'ðµ Google' }
            ,{ key: 'birthday', label: '\uD83C\uDF82 Anniversaires' }
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

      {/* V154: Category filter pills */}
      {categories.length > 0 && (
        <div style={{ display: 'flex', gap: '5px', flexWrap: 'wrap', marginBottom: '10px', marginTop: '6px' }}>
          <button onClick={() => setFilterCategory('all')} style={{
            padding: '4px 10px', borderRadius: '14px', fontSize: '10px', fontWeight: 500, cursor: 'pointer',
            background: filterCategory === 'all' ? 'rgba(217,28,210,0.25)' : 'rgba(255,255,255,0.04)',
            border: filterCategory === 'all' ? '1px solid rgba(217,28,210,0.5)' : '1px solid rgba(255,255,255,0.08)',
            color: filterCategory === 'all' ? '#D91CD2' : 'rgba(255,255,255,0.45)'
          }}>Toutes catÃ©gories</button>
          {categories.map(function(cat) {
            return (
              <button key={cat.id} onClick={function() { setFilterCategory(filterCategory === cat.id ? 'all' : cat.id); }} style={{
                padding: '4px 10px', borderRadius: '14px', fontSize: '10px', fontWeight: 500, cursor: 'pointer',
                background: filterCategory === cat.id ? cat.color + '33' : 'rgba(255,255,255,0.04)',
                border: '1px solid ' + (filterCategory === cat.id ? cat.color + '88' : 'rgba(255,255,255,0.08)'),
                color: filterCategory === cat.id ? cat.color : 'rgba(255,255,255,0.45)'
              }}>
                {cat.icon} {cat.name}
              </button>
            );
          })}
          <button onClick={function() { setFilterCategory(filterCategory === '__uncategorized__' ? 'all' : '__uncategorized__'); }} style={{
            padding: '4px 10px', borderRadius: '14px', fontSize: '10px', fontWeight: 500, cursor: 'pointer',
            background: filterCategory === '__uncategorized__' ? 'rgba(156,163,175,0.25)' : 'rgba(255,255,255,0.04)',
            border: filterCategory === '__uncategorized__' ? '1px solid rgba(156,163,175,0.5)' : '1px solid rgba(255,255,255,0.08)',
            color: filterCategory === '__uncategorized__' ? '#9CA3AF' : 'rgba(255,255,255,0.45)'
          }}>
            â Sans catÃ©gorie
          </button>
          <button onClick={function() { setShowCategoryManager(!showCategoryManager); }} style={{
            padding: '4px 10px', borderRadius: '14px', fontSize: '10px', fontWeight: 500, cursor: 'pointer',
            background: 'rgba(139,92,246,0.1)', border: '1px solid rgba(139,92,246,0.3)',
            color: '#c4b5fd'
          }}>
            âï¸ GÃ©rer
          </button>
        </div>
      )}

      {/* V154: Category Manager */}
      {showCategoryManager && (
        <div style={{
          padding: '14px', borderRadius: '12px', marginBottom: '12px',
          background: 'rgba(139,92,246,0.06)', border: '1px solid rgba(139,92,246,0.25)'
        }}>
          <div style={{ fontSize: '13px', fontWeight: 600, color: '#c4b5fd', marginBottom: '10px' }}>
            âï¸ GÃ©rer les catÃ©gories
          </div>
          {/* Existing categories */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', marginBottom: '12px' }}>
            {categories.map(function(cat) {
              return (
                <div key={cat.id} style={{
                  display: 'flex', alignItems: 'center', gap: '8px', padding: '8px 10px',
                  borderRadius: '8px', background: 'rgba(255,255,255,0.03)',
                  border: '1px solid rgba(255,255,255,0.06)'
                }}>
                  <span style={{ fontSize: '16px' }}>{cat.icon}</span>
                  <span style={{ flex: 1, fontSize: '12px', color: cat.color, fontWeight: 600 }}>{cat.name}</span>
                  <div style={{
                    width: '14px', height: '14px', borderRadius: '50%',
                    background: cat.color, flexShrink: 0
                  }} />
                  {!cat.is_default && (
                    <button onClick={function() { deleteCategory(cat.id); }} style={{
                      background: 'rgba(239,68,68,0.15)', border: '1px solid rgba(239,68,68,0.3)',
                      color: '#f87171', fontSize: '10px', padding: '3px 8px', borderRadius: '6px', cursor: 'pointer'
                    }}>â</button>
                  )}
                </div>
              );
            })}
          </div>
          {/* Add new category */}
          <div style={{ display: 'flex', gap: '6px', alignItems: 'center', flexWrap: 'wrap' }}>
            <select value={newCatIcon} onChange={function(e) { setNewCatIcon(e.target.value); }}
              style={{
                padding: '8px', borderRadius: '8px', fontSize: '16px', width: '50px',
                background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.1)',
                color: '#fff', cursor: 'pointer'
              }}>
              {['ð', 'ð', 'ð¤', 'ð¢', 'ðµ', 'ð¼', 'ðï¸', 'ð¨', 'ð¯', 'ð¡', 'ð', 'â­'].map(function(icon) {
                return <option key={icon} value={icon}>{icon}</option>;
              })}
            </select>
            <input
              value={newCatName}
              onChange={function(e) { setNewCatName(e.target.value); }}
              placeholder="Nom de la catÃ©gorie"
              onKeyDown={function(e) { if (e.key === 'Enter') { e.preventDefault(); createCategory(); } }}
              style={{
                flex: 1, padding: '8px 12px', borderRadius: '8px', fontSize: '12px',
                background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.15)',
                color: '#fff', outline: 'none', minWidth: '100px'
              }}
            />
            <input
              type="color"
              value={newCatColor}
              onChange={function(e) { setNewCatColor(e.target.value); }}
              style={{ width: '32px', height: '32px', border: 'none', borderRadius: '8px', cursor: 'pointer', background: 'transparent' }}
            />
            <button onClick={createCategory} disabled={!newCatName.trim()} style={{
              padding: '8px 14px', borderRadius: '8px', fontSize: '12px', fontWeight: 600,
              background: newCatName.trim() ? 'rgba(34,197,94,0.25)' : 'rgba(255,255,255,0.05)',
              border: '1px solid ' + (newCatName.trim() ? 'rgba(34,197,94,0.5)' : 'rgba(255,255,255,0.1)'),
              color: newCatName.trim() ? '#22c55e' : 'rgba(255,255,255,0.3)',
              cursor: newCatName.trim() ? 'pointer' : 'not-allowed'
            }}>
              + Ajouter
            </button>
          </div>
        </div>
      )}

      {/* V146: SÃ©lectionner tout checkbox */}
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
            SÃ©lectionner tout ({visibleUserIds.length})
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
            â³ Chargement...
          </div>
        ) : filtered.length === 0 ? (
          <div style={{ padding: '30px', textAlign: 'center', color: 'rgba(255,255,255,0.4)' }}>
            {searchQuery ? 'Aucun rÃ©sultat' : 'Aucun contact'}
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
                {/* V146: Checkbox de sÃ©lection (pas pour les groupes) */}
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
                  {isGroup ? 'ð¥' : c.source === 'google' ? 'ðµ' : 'ð¤'}
                </span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: '13px', color: '#fff', fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {c.name || 'Sans nom'}
                  </div>
                  <div style={{ fontSize: '11px', color: 'rgba(255,255,255,0.4)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {isGroup ? `${c.member_count || 0} membres` : [c.email, c.phone].filter(Boolean).join(' â¢ ') || 'Pas de coordonnÃ©es'}
                  </div>
                </div>
                {/* V154: Category badges */}
                {c.categories && c.categories.length > 0 && (
                  <div style={{ display: 'flex', gap: '3px', flexShrink: 0 }}>
                    {c.categories.slice(0, 2).map(function(catId) {
                      var cat = categories.find(function(ct) { return ct.id === catId; });
                      if (!cat) return null;
                      return (
                        <span key={catId} style={{
                          padding: '2px 6px', borderRadius: '8px', fontSize: '9px', fontWeight: 600,
                          background: cat.color + '22', color: cat.color,
                          border: '1px solid ' + cat.color + '44'
                        }}>{cat.icon} {cat.name}</span>
                      );
                    })}
                    {c.categories.length > 2 && (
                      <span style={{ fontSize: '9px', color: 'rgba(255,255,255,0.4)' }}>+{c.categories.length - 2}</span>
                    )}
                  </div>
                )}
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
