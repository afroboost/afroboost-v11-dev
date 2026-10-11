/**
 * V595 — CAMPAGNES → PROSPECTION → RÉSULTATS. LECTURE SEULE.
 * Mesurer si la prospection fonctionne : entonnoir, taux, comparaisons, période.
 * Aucune performance inventée : sans donnée, l'écran affiche 0 et « — ».
 */
import React, { useMemo, useState } from 'react';
import useProspectionDonnees from '../../../hooks/useProspectionDonnees';
import useNichesProspection from '../../../hooks/useNichesProspection';
import {
  PERIODES, compter, tauxDe, taux, grouper, paysDe, villeDe, canalDe, campagneDe, cleNicheProspect,
  rdvParFicheDe, LIBELLES_CANAL, libellesNiches,
} from '../../../utils/prospectionStats';
import { Titre, Grille, Carte, Tableau, Bandeau, EtatLecture, Puce, Bouton, DOUX, TEXTE, PRIMAIRE, heure, pct } from './ui';

const COMPARAISONS = [
  { id: 'niche', libelle: 'Par niche', cleNiche: true, libellesNiche: true },
  { id: 'niche_pays', libelle: 'Niche + pays', cleNichePays: true },
  { id: 'pays', libelle: 'Par pays', cle: paysDe },
  { id: 'ville', libelle: 'Par ville', cle: villeDe },
  { id: 'canal', libelle: 'Par canal', cle: canalDe, libelles: LIBELLES_CANAL },
  { id: 'campagne', libelle: 'Par campagne', cle: campagneDe },
];


function libelleNichePays(cle, NOM_NICHE) {
  const [n, pays] = String(cle).split('|');
  return `${NOM_NICHE[n] || 'Non classé'} ${pays}`;
}

export default function ProspectionResultats({ API }) {
  const { chargement, erreur, donnees, actualiser } = useProspectionDonnees(API);
  const { niches: listeNiches } = useNichesProspection(API);   // V598 : noms à jour (renommages)
  const [periode, setPeriode] = useState('tout');
  const [vue, setVue] = useState('niche');

  const calc = useMemo(() => {
    if (!donnees) return null;
    const options = { rdvParFiche: rdvParFicheDe(donnees.rdv), periode };
    const c = compter(donnees.fiches, options);
    const comp = COMPARAISONS.find((x) => x.id === vue) || COMPARAISONS[0];
    const nomNiche = listeNiches.reduce((m, n) => ({ ...m, [n.cle]: n.nom }), {});
    // V599 : la niche d'un prospect se lit sur son niche_id (repli : règle historique).
    const cleNiche = cleNicheProspect(listeNiches);
    const cle = comp.cleNiche ? cleNiche : (comp.cleNichePays ? (p) => `${cleNiche(p) || ''}|${paysDe(p)}` : comp.cle);
    let lignes = grouper(donnees.fiches, cle, options, comp.libellesNiche ? libellesNiches(listeNiches) : comp.libelles);
    if (vue === 'niche_pays') lignes = lignes.map((l) => ({ ...l, libelle: libelleNichePays(l.cle, nomNiche) }));
    return { c, t: tauxDe(c), lignes };
  }, [donnees, periode, vue, listeNiches]);

  if (!calc) return <EtatLecture chargement={chargement} erreur={erreur} onReessayer={actualiser} />;
  const { c, t } = calc;
  const etapes = [
    { id: 'total', libelle: 'Prospects', n: c.total },
    { id: 'contacte', libelle: 'Contactés', n: c.contacte },
    { id: 'reponse', libelle: 'Réponses', n: c.reponse },
    { id: 'interesse', libelle: 'Intéressés', n: c.interesse },
    { id: 'rdv', libelle: 'Rendez-vous', n: c.rdv },
    { id: 'accepte', libelle: 'Collaborations / acceptés', n: c.accepte },
  ];
  const max = Math.max(1, ...etapes.map((e) => e.n));
  const vide = etapes.every((e) => e.n === 0);

  return (
    <section data-testid="prospection-resultats" aria-label="Résultats de la prospection" style={{ color: TEXTE }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
        <div role="group" aria-label="Période" style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
          {PERIODES.map((p) => (
            <Puce key={p.id} actif={periode === p.id} onClick={() => setPeriode(p.id)} testid={`pr-periode-${p.id}`}>{p.libelle}</Puce>
          ))}
        </div>
        <Bouton discret onClick={actualiser} disabled={chargement}>{chargement ? 'Lecture…' : 'Actualiser'}</Bouton>
      </div>
      <div style={{ fontSize: '12px', color: DOUX, marginTop: '6px' }}>Données réelles · lues à {heure(donnees.lu_a)}</div>

      <Titre>Entonnoir</Titre>
      {vide ? (
        <Bandeau testid="pr-aucune-donnee">0 — aucune donnée sur cette période.</Bandeau>
      ) : (
        <div data-testid="pr-entonnoir" style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
          {etapes.map((e) => (
            <div key={e.id} style={{ display: 'grid', gridTemplateColumns: 'minmax(90px, 34%) 1fr auto', alignItems: 'center', gap: '8px' }}>
              <div style={{ fontSize: '12px', color: DOUX }}>{e.libelle}</div>
              <div style={{ height: '14px', borderRadius: '999px', background: 'rgba(255,255,255,0.06)', overflow: 'hidden' }}>
                <div style={{ width: `${e.n ? Math.max(2, (e.n / max) * 100) : 0}%`, height: '100%', background: PRIMAIRE, borderRadius: '999px' }} />
              </div>
              <div data-testid={`pr-etape-${e.id}`} style={{ fontSize: '13px', fontWeight: 700, minWidth: '28px', textAlign: 'right' }}>{e.n}</div>
            </div>
          ))}
        </div>
      )}

      <Titre>Taux</Titre>
      <Grille testid="pr-taux">
        <Carte libelle="Taux de réponse" valeur={pct(t.reponse)} aide="réponses / contactés" />
        <Carte libelle="Taux d'intérêt" valeur={pct(t.interet)} aide="intéressés / réponses" />
        <Carte libelle="Taux de rendez-vous" valeur={pct(t.rdv)} aide="rendez-vous / intéressés" />
        <Carte libelle="Taux de conversion" valeur={pct(t.conversion)} aide="acceptés / contactés" />
      </Grille>

      <Titre>Comparer</Titre>
      <div role="group" aria-label="Comparer" style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', marginBottom: '8px' }}>
        {COMPARAISONS.map((x) => (
          <Puce key={x.id} actif={vue === x.id} onClick={() => setVue(x.id)} testid={`pr-comparer-${x.id}`}>{x.libelle}</Puce>
        ))}
      </div>
      <Tableau testid="pr-comparaison" lignes={calc.lignes}
        colonnes={[
          { id: 'libelle', libelle: 'Groupe' },
          { id: 'n', libelle: 'Prospects' },
          { id: 'contacte', libelle: 'Contactés', rendu: (l) => l.c.contacte },
          { id: 'reponse', libelle: 'Réponses', rendu: (l) => l.c.reponse },
          { id: 'interesse', libelle: 'Intéressés', rendu: (l) => l.c.interesse },
          { id: 'rdv', libelle: 'RDV', rendu: (l) => l.c.rdv },
          { id: 'accepte', libelle: 'Acceptés', rendu: (l) => l.c.accepte },
          { id: 'tr', libelle: 'Réponse', rendu: (l) => pct(taux(l.c.reponse, l.c.contacte)) },
          { id: 'tc', libelle: 'Conversion', rendu: (l) => pct(taux(l.c.accepte, l.c.contacte)) },
        ]} />

      <div style={{ marginTop: '14px' }}>
        <Bandeau>
          Hors « Tout », chaque étape n'est comptée que si sa date tombe dans la période
          (création, premier envoi, réponse, intérêt, rendez-vous). Acceptés et refusés n'ont pas
          de date en base : ils ne comptent que dans « Tout ». « — » = pas assez de données pour un taux.
        </Bandeau>
      </div>
    </section>
  );
}
