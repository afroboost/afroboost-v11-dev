/**
 * contactParser.js v17.3
 * Parse CSV/vCard files to extract contacts (name, phone, email)
 * Deduplication by phone/email
 */

/**
 * Parse CSV text to contacts
 * Supports: name,phone,email or phone,name,email or any header order
 */
export function parseCSV(text) {
  if (!text || !text.trim()) return [];

  const lines = text.trim().split(/\r?\n/).filter(l => l.trim());
  if (lines.length < 1) return [];

  // Detect separator
  const sep = lines[0].includes(';') ? ';' : ',';

  // Try to detect headers
  const firstLine = lines[0].toLowerCase();
  const hasHeaders = ['name', 'nom', 'phone', 'tel', 'email', 'mail'].some(h => firstLine.includes(h));

  let headers = null;
  let dataLines = lines;

  if (hasHeaders) {
    headers = lines[0].split(sep).map(h => h.trim().toLowerCase());
    dataLines = lines.slice(1);
  }

  const contacts = [];

  for (const line of dataLines) {
    const cols = line.split(sep).map(c => c.trim().replace(/^["']|["']$/g, ''));
    if (cols.length < 1) continue;

    let name = '', phone = '', email = '';

    if (headers) {
      const nameIdx = headers.findIndex(h => ['name', 'nom', 'prenom', 'firstname', 'full_name', 'fullname'].includes(h));
      const phoneIdx = headers.findIndex(h => ['phone', 'tel', 'telephone', 'mobile', 'whatsapp', 'numero'].includes(h));
      const emailIdx = headers.findIndex(h => ['email', 'mail', 'e-mail', 'courriel'].includes(h));

      name = nameIdx >= 0 ? cols[nameIdx] || '' : '';
      phone = phoneIdx >= 0 ? cols[phoneIdx] || '' : '';
      email = emailIdx >= 0 ? cols[emailIdx] || '' : '';
    } else {
      // Heuristic: detect phone (starts with + or digits), email (contains @), rest is name
      for (const col of cols) {
        if (col.includes('@') && !email) {
          email = col;
        } else if (/^[+\d(][\d\s()./-]{6,}$/.test(col) && !phone) {
          phone = col;
        } else if (!name) {
          name = col;
        }
      }
    }

    // Normalize phone
    phone = phone.replace(/[\s()./-]/g, '');

    if (name || phone || email) {
      contacts.push({ name: name || 'Sans nom', phone, email });
    }
  }

  return dedup(contacts);
}

/**
 * Parse vCard (VCF) text to contacts
 * Supports vCard 2.1, 3.0, 4.0
 */
export function parseVCard(text) {
  if (!text || !text.trim()) return [];

  const contacts = [];
  const cards = text.split(/BEGIN:VCARD/i).filter(c => c.trim());

  for (const card of cards) {
    let name = '', phone = '', email = '';

    const lines = card.split(/\r?\n/);

    for (const line of lines) {
      const upper = line.toUpperCase();

      // Full Name
      if (upper.startsWith('FN:') || upper.startsWith('FN;')) {
        name = line.split(':').slice(1).join(':').trim();
      }
      // Name fallback from N field
      if (!name && (upper.startsWith('N:') || upper.startsWith('N;'))) {
        const parts = line.split(':').slice(1).join(':').split(';');
        name = [parts[1], parts[0]].filter(p => p?.trim()).join(' ').trim();
      }
      // Phone
      if ((upper.startsWith('TEL:') || upper.startsWith('TEL;')) && !phone) {
        phone = line.split(':').slice(1).join(':').trim();
      }
      // Email
      if ((upper.startsWith('EMAIL:') || upper.startsWith('EMAIL;')) && !email) {
        email = line.split(':').slice(1).join(':').trim();
      }
    }

    // Normalize phone
    phone = phone.replace(/[\s()./-]/g, '');

    if (name || phone || email) {
      contacts.push({ name: name || 'Sans nom', phone, email });
    }
  }

  return dedup(contacts);
}

/**
 * Auto-detect format and parse
 */
export function parseContacts(text, filename = '') {
  const ext = filename.toLowerCase().split('.').pop();
  if (ext === 'vcf' || text.toUpperCase().includes('BEGIN:VCARD')) {
    return parseVCard(text);
  }
  return parseCSV(text);
}

/**
 * Deduplicate contacts by phone or email
 */
function dedup(contacts) {
  const seen = new Set();
  return contacts.filter(c => {
    const key = c.phone || c.email || c.name;
    if (!key || seen.has(key.toLowerCase())) return false;
    seen.add(key.toLowerCase());
    return true;
  });
}
