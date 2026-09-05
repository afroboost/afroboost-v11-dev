import React, { useCallback, useEffect, useState } from 'react';
import axios from 'axios';

/**
 * R2c — CLASSER LES OFFRES D'AVANT.
 *
 * Neuf offres existent en production sans propriétaire ni type déclarés. Rien
 * en base ne prouve à qui elles appartiennent : les attribuer d'office à
 * l'administrateur serait commode aujourd'hui, et faux le jour où un
 * partenaire réclamera la sienne. On pose donc les deux questions à celui qui
 * connaît la réponse.
 *
 * Cet écran N'EST PAS un éditeur d'offre : il n'écrit que le propriétaire et
 * le type. Le prix, la visibilité, les séances et les cours liés ne passent
 * pas par ici — c'est la raison d'être de la route séparée
 * `PATCH /offers/{id}/classification`.
 *
 * Réservé au super-admin, côté serveur comme côté écran.
 */
export default function OffersClassification({ API, isSuperAdmin, coachEmail, onClassifie }) {
  const [donnees, setDonnees] = useState(null);
  const [chargement, setChargement] = useState(false);
  const [erreur, setErreur] = useState('');
  const [ouvert, setOuvert] = useState(false);
  const [brouillons, setBrouillons] = useState({});
  const [enCours, setEnCours] = useState('');

  const charger = useCallback(async () => {
    if (!API || !isSuperAdmin) return;
    setChargement(true);
    setErreur('');
    try {
      const r = await axios.get(`${API}/offers/classification`, {
        headers: { 'X-User-Email': coachEmail || '' }
      });
      setDonnees(r.data);
    } catch (e) {
      setErreur(
        e?.response?.status === 403
          ? "Réservé à l'administrateur."
          : "Impossible de charger les offres à classifier."
      );
    } finally {
      setChargement(false);
    }
  }, [API, isSuperAdmin, coachEmail]);

  useEffect(() => { if (ouvert) charger(); }, [ouvert, charger]);

  if (!isSuperAdmin) return null;

  const aClassifier = (donnees?.offres || []).filter((o) => o.a_classifier);
  const nb = donnees ? donnees.a_classifier : null;

  const majBrouillon = (id, champ, valeur) =>
    setBrouillons((p) => ({ ...p, [id]: { ...(p[id] || {}), [champ]: valeur } }));

  const enregistrer = async (offre) => {
    const b = brouillons[offre.id] || {};
    if (!b.owner_type || !b.offer_type) {
      alert('Choisis le propriétaire ET le type avant d\'enregistrer.');
      return;
    }
    if (b.owner_type === 'partner' && !b.partner_id) {
      alert('Choisis quel partenaire possède cette offre.');
      return;
    }
    setEnCours(offre.id);
    try {
      await axios.patch(
        `${API}/offers/${offre.id}/classification`,
        {
          owner_type: b.owner_type,
          partner_id: b.owner_type === 'partner' ? b.partner_id : null,
          offer_type: b.offer_type
        },
        { headers: { 'X-User-Email': coachEmail || '' } }
      );
      await charger();
      if (onClassifie) onClassifie();
    } catch (e) {
      alert(e?.response?.data?.detail || "L'enregistrement a échoué.");
    } finally {
      setEnCours('');
    }
  };

  const CADRE = {
    borderRadius: '16px',
    padding: '16px',
    marginBottom: '16px',
    background: 'rgba(var(--primary-rgb, 217, 28, 210), 0.06)',
    border: '1px solid rgba(var(--primary-rgb, 217, 28, 210), 0.25)'
  };
  const ETIQUETTE = { color: 'rgba(255,255,255,0.72)', fontSize: '12px' };
  const BOUTON = (actif) => ({
    fontSize: '12px',
    padding: '6px 10px',
    borderRadius: '8px',
    cursor: 'pointer',
    border: `1px solid ${actif ? 'var(--primary-color, #D91CD2)' : 'rgba(255,255,255,0.14)'}`,
    background: actif ? 'rgba(var(--primary-rgb, 217, 28, 210), 0.14)' : 'transparent',
    color: actif ? 'var(--primary-color, #D91CD2)' : 'rgba(255,255,255,0.78)'
  });

  return (
    <div style={CADRE} data-testid="r2c-classification">
      <button
        type="button"
        onClick={() => setOuvert((v) => !v)}
        style={{
          display: 'flex', alignItems: 'center', gap: '8px', width: '100%',
          background: 'transparent', border: 'none', cursor: 'pointer',
          color: 'var(--primary-color, #D91CD2)', fontSize: '14px', fontWeight: 600,
          textAlign: 'left', padding: 0
        }}
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none"
             stroke="currentColor" strokeWidth="2" strokeLinecap="round"
             strokeLinejoin="round" aria-hidden="true"
             style={{ transform: ouvert ? 'rotate(90deg)' : 'none', transition: 'transform .15s' }}>
          <polyline points="9 18 15 12 9 6" />
        </svg>
        Classer les anciennes offres
        {nb !== null && nb > 0 && (
          <span style={{
            fontSize: '11px', padding: '2px 8px', borderRadius: '999px',
            background: 'var(--primary-color, #D91CD2)', color: '#fff'
          }}>{nb}</span>
        )}
      </button>

      {ouvert && (
        <div style={{ marginTop: '12px' }}>
          <p style={{ ...ETIQUETTE, marginBottom: '12px', lineHeight: 1.5 }}>
            Ces offres ont été créées avant que l&apos;on demande à qui elles
            appartiennent et ce qu&apos;elles sont. Rien en base ne permet de le
            deviner sans risque de se tromper&nbsp;: c&apos;est à toi de le dire.
          </p>

          {chargement && <p style={ETIQUETTE}>Chargement…</p>}
          {erreur && <p style={{ ...ETIQUETTE, color: '#ff8a8a' }}>{erreur}</p>}

          {donnees && aClassifier.length === 0 && (
            <p style={ETIQUETTE}>
              Toutes les offres sont classées. Rien à faire ici.
            </p>
          )}

          {donnees && donnees.partenaires.length === 0 && aClassifier.length > 0 && (
            <p style={{ ...ETIQUETTE, marginBottom: '12px' }}>
              Aucun coach partenaire n&apos;est enregistré pour l&apos;instant&nbsp;:
              seul le choix «&nbsp;Afroboost / Administrateur&nbsp;» est disponible.
            </p>
          )}

          {aClassifier.map((o) => {
            const b = brouillons[o.id] || {};
            return (
              <div key={o.id} data-testid={`r2c-offre-${o.id}`} style={{
                padding: '12px', borderRadius: '12px', marginBottom: '10px',
                background: 'rgba(0,0,0,0.28)',
                border: '1px solid rgba(255,255,255,0.10)'
              }}>
                <div style={{ color: '#fff', fontSize: '13px', fontWeight: 600, marginBottom: '2px' }}>
                  {o.name || '(sans nom)'}
                </div>
                <div style={{ ...ETIQUETTE, marginBottom: '10px' }}>
                  {o.price != null && <>{o.price} CHF · </>}
                  {o.visible ? 'visible' : 'masquée'}
                  {o.linked_course_ids.length > 0 &&
                    <> · {o.linked_course_ids.length} cours lié{o.linked_course_ids.length > 1 ? 's' : ''}</>}
                  {o.duration_value && <> · {o.duration_value} {o.duration_unit}</>}
                </div>

                <div style={{ ...ETIQUETTE, marginBottom: '4px' }}>À qui appartient-elle&nbsp;?</div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginBottom: '10px' }}>
                  {(donnees.proprietaires || []).map((p) => (
                    <button key={p.valeur} type="button"
                            data-testid={`r2c-proprio-${o.id}-${p.valeur}`}
                            disabled={p.valeur === 'partner' && donnees.partenaires.length === 0}
                            onClick={() => majBrouillon(o.id, 'owner_type', p.valeur)}
                            style={{
                              ...BOUTON(b.owner_type === p.valeur),
                              opacity: (p.valeur === 'partner' && donnees.partenaires.length === 0) ? 0.4 : 1
                            }}>
                      {p.libelle}
                    </button>
                  ))}
                </div>

                {b.owner_type === 'partner' && (
                  <select
                    value={b.partner_id || ''}
                    onChange={(e) => majBrouillon(o.id, 'partner_id', e.target.value)}
                    style={{
                      width: '100%', marginBottom: '10px', padding: '8px',
                      borderRadius: '8px', fontSize: '12px',
                      background: 'rgba(0,0,0,0.4)', color: '#fff',
                      border: '1px solid rgba(255,255,255,0.14)'
                    }}
                  >
                    <option value="">— Choisir le partenaire —</option>
                    {donnees.partenaires.map((p) => (
                      <option key={p.id} value={p.id}>{p.name}</option>
                    ))}
                  </select>
                )}

                <div style={{ ...ETIQUETTE, marginBottom: '4px' }}>Qu&apos;est-ce que c&apos;est&nbsp;?</div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginBottom: '12px' }}>
                  {(donnees.types || []).map((t) => (
                    <button key={t.valeur} type="button"
                            data-testid={`r2c-type-${o.id}-${t.valeur}`}
                            onClick={() => majBrouillon(o.id, 'offer_type', t.valeur)}
                            style={BOUTON(b.offer_type === t.valeur)}>
                      {t.libelle}
                    </button>
                  ))}
                </div>

                <button type="button"
                        data-testid={`r2c-enregistrer-${o.id}`}
                        disabled={enCours === o.id}
                        onClick={() => enregistrer(o)}
                        style={{
                          fontSize: '12px', padding: '8px 14px', borderRadius: '8px',
                          border: 'none', cursor: enCours === o.id ? 'wait' : 'pointer',
                          background: 'var(--primary-color, #D91CD2)', color: '#fff',
                          opacity: enCours === o.id ? 0.6 : 1
                        }}>
                  {enCours === o.id ? 'Enregistrement…' : 'Enregistrer'}
                </button>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
