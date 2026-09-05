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

  // R3a : l'ecran couvre desormais DEUX manques distincts — le proprietaire
  // et le type d'un cote, la ville de l'autre. Une offre peut avoir besoin de
  // l'un, de l'autre, ou des deux ; elle apparait des qu'il lui manque quelque
  // chose. Un seul outil, comme demande — pas un second grand ecran.
  const aTraiter = (donnees?.offres || []).filter(
    (o) => o.a_classifier || o.localisation_absente);
  const nb = donnees ? aTraiter.length : null;

  const majBrouillon = (id, champ, valeur) =>
    setBrouillons((p) => ({ ...p, [id]: { ...(p[id] || {}), [champ]: valeur } }));

  const enregistrerLieu = async (offre) => {
    const b = brouillons[offre.id] || {};
    // La ville SEULE est demandee : l'adresse se pre-remplit depuis le texte
    // libre historique, et les coordonnees ne viennent que d'une proposition
    // choisie. Aucune n'est obligatoire.
    const ville = (b.location_city ?? offre.location_city ?? '').trim();
    const adresse = (b.location_address ?? offre.location_address ?? offre.location ?? '').trim();
    setEnCours(offre.id + ':lieu');
    try {
      await axios.patch(
        `${API}/offers/${offre.id}/localisation`,
        {
          location_city: ville,
          location_address: adresse,
          location_lat: b.location_lat ?? offre.location_lat ?? null,
          location_lng: b.location_lng ?? offre.location_lng ?? null
        },
        { headers: { 'X-User-Email': coachEmail || '' } }
      );
      await charger();
      if (onClassifie) onClassifie();
    } catch (e) {
      alert(e?.response?.data?.detail || "L'enregistrement du lieu a échoué.");
    } finally {
      setEnCours('');
    }
  };

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
        Classer et situer les anciennes offres
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

          {donnees && aTraiter.length === 0 && (
            <p style={ETIQUETTE}>
              Toutes les offres sont classées et situées. Rien à faire ici.
            </p>
          )}

          {donnees && donnees.partenaires.length === 0 && aTraiter.some((o) => o.a_classifier) && (
            <p style={{ ...ETIQUETTE, marginBottom: '12px' }}>
              Aucun coach partenaire n&apos;est enregistré pour l&apos;instant&nbsp;:
              seul le choix «&nbsp;Afroboost / Administrateur&nbsp;» est disponible.
            </p>
          )}

          {aTraiter.map((o) => {
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

                {o.a_classifier && (<>
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
                </>)}

                {/* R3a — OU SE PASSE-T-ELLE ? Bloc SEPARE, et enregistre
                    separement : classer une offre et la situer sont deux
                    reponses independantes, et Bassi peut n'en connaitre
                    qu'une. L'adresse historique est PROPOSEE comme point de
                    depart, jamais recopiee en base a son insu. */}
                <div style={{
                  marginTop: o.a_classifier ? '14px' : 0,
                  paddingTop: o.a_classifier ? '12px' : 0,
                  borderTop: o.a_classifier ? '1px solid rgba(255,255,255,0.10)' : 'none'
                }}>
                  <div style={{ ...ETIQUETTE, marginBottom: '6px' }}>Où se passe-t-elle&nbsp;?</div>
                  {o.location && !o.location_address && (
                    <p style={{ ...ETIQUETTE, marginBottom: '6px', fontStyle: 'italic' }}>
                      Lieu actuellement affiché&nbsp;: «&nbsp;{o.location}&nbsp;»
                      — vérifie-le avant d&apos;enregistrer.
                    </p>
                  )}
                  <input
                    type="text"
                    data-testid={`r3a-ville-${o.id}`}
                    value={b.location_city ?? o.location_city ?? ''}
                    onChange={(e) => majBrouillon(o.id, 'location_city', e.target.value)}
                    placeholder="Ville (ex : Auvernier)"
                    style={{
                      width: '100%', marginBottom: '6px', padding: '8px',
                      borderRadius: '8px', fontSize: '12px',
                      background: 'rgba(0,0,0,0.4)', color: '#fff',
                      border: '1px solid rgba(255,255,255,0.14)'
                    }}
                  />
                  <input
                    type="text"
                    data-testid={`r3a-adresse-${o.id}`}
                    value={b.location_address ?? o.location_address ?? o.location ?? ''}
                    onChange={(e) => majBrouillon(o.id, 'location_address', e.target.value)}
                    placeholder="Adresse / lieu"
                    style={{
                      width: '100%', marginBottom: '10px', padding: '8px',
                      borderRadius: '8px', fontSize: '12px',
                      background: 'rgba(0,0,0,0.4)', color: '#fff',
                      border: '1px solid rgba(255,255,255,0.14)'
                    }}
                  />
                  <button type="button"
                          data-testid={`r3a-enregistrer-lieu-${o.id}`}
                          disabled={enCours === o.id + ':lieu'}
                          onClick={() => enregistrerLieu(o)}
                          style={{
                            fontSize: '12px', padding: '8px 14px', borderRadius: '8px',
                            border: '1px solid var(--primary-color, #D91CD2)',
                            cursor: enCours === o.id + ':lieu' ? 'wait' : 'pointer',
                            background: 'transparent',
                            color: 'var(--primary-color, #D91CD2)',
                            opacity: enCours === o.id + ':lieu' ? 0.6 : 1
                          }}>
                    {enCours === o.id + ':lieu' ? 'Enregistrement…' : 'Enregistrer le lieu'}
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
