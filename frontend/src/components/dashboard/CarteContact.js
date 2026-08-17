/**
 * CarteContact — CONTACTS V2, temps 2
 *
 * La vue mobile. Cinq informations, dans l'ordre où on les cherche :
 * identité, relation, statut, zone, canaux. Tout le reste — source technique,
 * identifiants, étiquettes — vit dans la fiche.
 *
 * Chaque état porte du TEXTE : « Participant », « Ancien abonné ». Une pastille
 * de couleur seule ne dit rien à qui ne connaît pas le code.
 */
import { libelleType, libelleStatut, libelleZone, drapeau } from '../../utils/contactsAffichage';
import { TYPES_CONTACT } from '../../utils/contactType';

const PRIMAIRE = 'var(--primary-color, #D91CD2)';
const BORDURE = '1px solid rgba(255,255,255,0.10)';

export default function CarteContact({ contact, onOuvrir, onClasser }) {
  const c = contact || {};
  const canaux = c.canaux || {};
  const nonClasse = !c.contact_type;

  const puce = (texte, fort) => (
    <span style={{
      fontSize: 11, padding: '2px 8px', borderRadius: 999,
      background: fort ? 'rgba(var(--primary-rgb, 217, 28, 210), 0.18)' : 'rgba(255,255,255,0.06)',
      color: fort ? '#fff' : 'rgba(255,255,255,0.6)',
      border: fort ? `1px solid ${PRIMAIRE}` : BORDURE,
      whiteSpace: 'nowrap',
    }}>{texte}</span>
  );

  const canal = (dispo, libelle) => (
    <span
      aria-label={`${libelle} ${dispo ? 'disponible' : 'indisponible'}`}
      style={{
        fontSize: 11, padding: '2px 7px', borderRadius: 6,
        background: dispo ? 'rgba(34,197,94,0.14)' : 'rgba(255,255,255,0.04)',
        color: dispo ? '#4ade80' : 'rgba(255,255,255,0.28)',
        border: `1px solid ${dispo ? 'rgba(34,197,94,0.3)' : 'rgba(255,255,255,0.07)'}`,
      }}
    >{libelle}</span>
  );

  return (
    <div
      data-testid="carte-contact"
      style={{
        border: BORDURE, borderRadius: 14, padding: 13, marginBottom: 9,
        background: 'rgba(255,255,255,0.025)',
      }}
    >
      <p style={{ margin: 0, color: '#fff', fontSize: 14.5, fontWeight: 700,
                  overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        {c.name || 'Sans nom'}
      </p>

      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 7 }}>
        {puce(libelleType(c), !nonClasse)}
        {puce(libelleStatut(c), c.statut_abonnement === 'actif')}
        <span style={{ fontSize: 11.5, color: 'rgba(255,255,255,0.5)', whiteSpace: 'nowrap' }}>
          {drapeau(c) ? `${drapeau(c)} ` : ''}{libelleZone(c)}
        </span>
      </div>

      <div style={{ display: 'flex', gap: 5, flexWrap: 'wrap', marginTop: 9 }}>
        {canal(canaux.email, 'Email')}
        {canal(canaux.whatsapp, 'WhatsApp')}
        {canal(canaux.telephone, 'Téléphone')}
      </div>

      <div style={{ display: 'flex', gap: 7, marginTop: 11, alignItems: 'center' }}>
        {nonClasse && (
          <select
            data-testid={`classer-${c.id}`}
            aria-label="Classer ce contact"
            defaultValue=""
            onChange={(e) => {
              // Une modification ne part au serveur qu'après un choix EXPLICITE :
              // ouvrir la liste ne suffit pas, et la valeur vide ne fait rien.
              if (e.target.value && onClasser) onClasser(c.id, e.target.value);
            }}
            style={{
              flex: 1, minHeight: 40, padding: '8px 10px', borderRadius: 9,
              background: '#12122a', color: 'rgba(255,255,255,0.8)',
              border: BORDURE, fontSize: 16, outline: 'none',
            }}
          >
            <option value="">Classer…</option>
            {TYPES_CONTACT.map((t) => <option key={t.valeur} value={t.valeur}>{t.libelle}</option>)}
          </select>
        )}
        <button
          type="button"
          data-testid={`ouvrir-${c.id}`}
          onClick={() => onOuvrir && onOuvrir(c)}
          style={{
            minHeight: 40, padding: '9px 18px', borderRadius: 9, border: 'none',
            cursor: 'pointer', background: PRIMAIRE, color: '#fff',
            fontSize: 13, fontWeight: 700, marginLeft: nonClasse ? 0 : 'auto',
          }}
        >
          Ouvrir
        </button>
      </div>
    </div>
  );
}
