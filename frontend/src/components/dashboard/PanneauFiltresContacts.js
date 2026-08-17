/**
 * PanneauFiltresContacts — CONTACTS V2, temps 1
 *
 * Tous les critères vivent ICI, derrière un seul bouton. C'était la condition
 * pour ne pas aggraver le mobile : une rangée de chips de plus aurait fait
 * quatre lignes sur un petit écran.
 *
 * Panneau latéral sur desktop, feuille montante sur mobile — même composant,
 * la différence tient à deux propriétés CSS.
 */
import {
  TYPES, STATUTS, ZONES, CANAUX, CONSENTEMENTS,
  FILTRES_VIDES, nombreFiltresActifs,
} from '../../utils/contactsFiltres';

const PRIMAIRE = 'var(--primary-color, #D91CD2)';
const BORDURE = '1px solid rgba(255,255,255,0.10)';

export default function PanneauFiltresContacts({ ouvert, filtres, onChange, onFermer, pays = [], nbResultats = null }) {
  if (!ouvert) return null;
  const f = { ...FILTRES_VIDES, ...(filtres || {}) };

  const basculer = (cle, valeur) => {
    const liste = f[cle] || [];
    onChange({
      ...f,
      [cle]: liste.includes(valeur) ? liste.filter((v) => v !== valeur) : [...liste, valeur],
    });
  };

  const groupe = (titre, cle, options, note) => (
    <div style={{ marginBottom: 16 }}>
      <p style={{ margin: '0 0 6px', color: 'rgba(255,255,255,0.5)', fontSize: 11,
                  textTransform: 'uppercase', letterSpacing: 0.5 }}>
        {titre}
      </p>
      {note && (
        <p style={{ margin: '0 0 6px', color: 'rgba(255,255,255,0.35)', fontSize: 10.5, lineHeight: 1.4 }}>
          {note}
        </p>
      )}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
        {options.map((o) => {
          const actif = (f[cle] || []).includes(o.valeur);
          return (
            <button
              key={o.valeur}
              type="button"
              data-testid={`filtre-${cle}-${o.valeur}`}
              aria-pressed={actif}
              onClick={() => basculer(cle, o.valeur)}
              style={{
                padding: '9px 13px', minHeight: 40, borderRadius: 999, fontSize: 12.5, cursor: 'pointer',
                border: actif ? `1px solid ${PRIMAIRE}` : BORDURE,
                background: actif ? PRIMAIRE : 'transparent',
                color: actif ? '#fff' : 'rgba(255,255,255,0.6)',
                fontWeight: actif ? 700 : 500,
              }}
            >
              {o.libelle}
            </button>
          );
        })}
      </div>
    </div>
  );

  const n = nombreFiltresActifs(f);

  return (
    <div
      data-testid="panneau-filtres"
      onClick={onFermer}
      style={{ position: 'fixed', inset: 0, zIndex: 9000, background: 'rgba(0,0,0,0.7)',
               display: 'flex', alignItems: 'flex-end', justifyContent: 'center' }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: '#0a0a1a', border: BORDURE, width: '100%', maxWidth: 560,
          // Feuille montante sur mobile, panneau centré au-delà : une seule
          // règle, aucune media query.
          borderRadius: '18px 18px 0 0', padding: 18,
          maxHeight: '85vh', overflowY: 'auto',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
          <h3 style={{ margin: 0, color: '#fff', fontSize: 15, fontWeight: 800 }}>
            Filtres{n ? ` (${n})` : ''}
          </h3>
          <button type="button" data-testid="filtres-fermer" onClick={onFermer} aria-label="Fermer"
            style={{ background: 'none', border: 'none', color: '#fff', fontSize: 26, lineHeight: 1, cursor: 'pointer' }}>
            ×
          </button>
        </div>

        {groupe('Type', 'types', TYPES)}
        {groupe('Statut commercial', 'statuts', STATUTS)}
        {groupe('Zone', 'zones', ZONES)}
        {/* CONTACTS V2 temps 2 — les PAYS reellement presents, avec leur
            nombre. On ne propose pas un filtre qui ne rendrait personne. */}
        {pays.length > 0 && groupe(
          'Pays', 'pays',
          pays.map((p) => ({ valeur: p.code, libelle: `${p.drapeau ? p.drapeau + ' ' : ''}${p.nom} (${p.n})` })),
          'La zone regroupe ; le pays précise.')}
        {groupe('Canal disponible', 'canaux', CANAUX,
          "Le canal existe. Cela ne signifie pas qu'une campagne est autorisée.")}
        {groupe('Consentement e-mail', 'consentEmail', CONSENTEMENTS)}
        {groupe('Consentement WhatsApp', 'consentWhatsapp', CONSENTEMENTS)}

        <div style={{ display: 'flex', gap: 8, marginTop: 6 }}>
          <button type="button" data-testid="filtres-reinitialiser"
            onClick={() => onChange({ ...FILTRES_VIDES })}
            style={{ flex: 1, padding: '12px 14px', minHeight: 46, borderRadius: 10, cursor: 'pointer',
                     background: 'transparent', border: BORDURE, color: 'rgba(255,255,255,0.65)', fontSize: 13 }}>
            Réinitialiser
          </button>
          <button type="button" data-testid="filtres-appliquer" onClick={onFermer}
            style={{ flex: 1, padding: '12px 14px', minHeight: 46, borderRadius: 10, border: 'none', cursor: 'pointer',
                     background: PRIMAIRE, color: '#fff', fontSize: 13, fontWeight: 700 }}>
            {typeof nbResultats === 'number'
              ? `Voir ${nbResultats} contact${nbResultats > 1 ? 's' : ''}`
              : 'Voir les résultats'}
          </button>
        </div>
      </div>
    </div>
  );
}
