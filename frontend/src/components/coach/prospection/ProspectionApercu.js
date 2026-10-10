/**
 * V595 — CAMPAGNES → PROSPECTION → VUE D'ENSEMBLE. LECTURE SEULE.
 * Ouvrir Prospection et voir d'un coup d'œil où en est toute l'activité commerciale.
 * Chaque chiffre vient des fiches réelles (voir utils/prospectionStats.js) ; aucun
 * POST/PATCH, aucun envoi.
 */
import React, { useMemo, useState } from 'react';
import useProspectionDonnees from '../../../hooks/useProspectionDonnees';
import useNichesProspection from '../../../hooks/useNichesProspection'; // V598 : la liste des niches vient du serveur
import {
  CANAUX, compter, grouper, nicheDe, paysDe, villeDe, canalDe, rdvParFicheDe, libellesNiches,
} from '../../../utils/prospectionStats';
import { Titre, Grille, Carte, Tableau, Bandeau, EtatLecture, Bouton, Pastille, DOUX, TEXTE, heure } from './ui';

const VILLES_SUIVIES = ['Paris', 'Neuchâtel', 'Lausanne', 'Genève'];

export default function ProspectionApercu({ API }) {
  const { chargement, erreur, donnees, actualiser } = useProspectionDonnees(API);
  const { niches: listeNiches } = useNichesProspection(API);
  const [autresOuvert, setAutresOuvert] = useState(false);

  const calc = useMemo(() => {
    if (!donnees) return null;
    const fiches = donnees.fiches;
    const options = { rdvParFiche: rdvParFicheDe(donnees.rdv) };
    const c = compter(fiches, options);
    const libelles = libellesNiches(listeNiches);
    const parNiche = grouper(fiches, nicheDe, options, libelles);
    const niches = listeNiches.filter((n) => n.active !== false)
      .map((n) => parNiche.find((g) => g.cle === n.cle) || { cle: n.cle, libelle: libelles[n.cle], n: 0, c: compter([], options) });
    const nonClasses = parNiche.find((g) => g.cle === '');
    const pays = grouper(fiches, paysDe, options);
    const villes = grouper(fiches, villeDe, options);
    const canaux = grouper(fiches, canalDe, options);
    return { c, niches: nonClasses ? [...niches, nonClasses] : niches, pays, villes, canaux };
  }, [donnees, listeNiches]);

  if (!calc) return <EtatLecture chargement={chargement} erreur={erreur} onReessayer={actualiser} />;
  const { c } = calc;
  const conv = donnees.conversations;
  const refusConversation = conv && Number(conv.compteurs.refus) > c.refuse ? Number(conv.compteurs.refus) : 0;
  const nombrePays = (nom) => (calc.pays.find((g) => g.cle === nom) || { n: 0 }).n;
  const suivies = VILLES_SUIVIES.map((v) => ({ v, n: (calc.villes.find((g) => g.cle === v) || { n: 0 }).n }));
  const autres = calc.villes.filter((g) => !VILLES_SUIVIES.includes(g.cle));

  return (
    <section data-testid="prospection-apercu" aria-label="Vue d'ensemble de la prospection" style={{ color: TEXTE }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
        <div style={{ fontSize: '12px', color: DOUX }}>Données réelles · lues à {heure(donnees.lu_a)}</div>
        <Bouton discret onClick={actualiser} disabled={chargement} testid="pp-actualiser">{chargement ? 'Lecture…' : 'Actualiser'}</Bouton>
      </div>

      <Titre>Où en est la prospection</Titre>
      <Grille testid="pp-cartes">
        <Carte libelle="Total prospects" valeur={c.total} testid="pp-total" />
        <Carte libelle="À contacter" valeur={c.a_contacter} />
        <Carte libelle="Contactés" valeur={c.contacte} ton="marque" />
        <Carte libelle="Réponses" valeur={c.reponse} ton="bleu" />
        <Carte libelle="Intéressés" valeur={c.interesse} ton="vert" />
        <Carte libelle="Rendez-vous" valeur={c.rdv} aide={donnees.rdv === null ? 'calendrier illisible' : undefined} />
        <Carte libelle="Acceptés" valeur={c.accepte} ton="vert" />
        <Carte libelle="Refusés" valeur={c.refuse} ton={c.refuse ? 'rouge' : undefined} />
        <Carte libelle="Sans réponse" valeur={c.sans_reponse} ton={c.sans_reponse ? 'ambre' : undefined} />
      </Grille>
      {conv && (
        <div style={{ marginTop: '8px', fontSize: '12px', color: DOUX }} data-testid="pp-conversations">
          Conversations partenaires : <strong style={{ color: TEXTE }}>{conv.total}</strong>
          {refusConversation > 0 && <> · {refusConversation} marquée(s) « refus » dans la conversation, fiche pas encore mise à jour</>}
        </div>
      )}

      <Titre>Par niche</Titre>
      <Tableau testid="pp-niches" lignes={calc.niches}
        colonnes={[
          { id: 'libelle', libelle: 'Niche' },
          { id: 'n', libelle: 'Total' },
          { id: 'contacte', libelle: 'Contactés', rendu: (l) => l.c.contacte },
          { id: 'reponse', libelle: 'Réponses', rendu: (l) => l.c.reponse },
          { id: 'interesse', libelle: 'Intéressés', rendu: (l) => l.c.interesse },
          { id: 'accepte', libelle: 'Acceptés', rendu: (l) => l.c.accepte },
          { id: 'refuse', libelle: 'Refusés', rendu: (l) => l.c.refuse },
        ]} />

      <Titre>Par pays et par ville</Titre>
      <Grille>
        <Carte libelle="Suisse" valeur={nombrePays('Suisse')} testid="pp-suisse" />
        <Carte libelle="France" valeur={nombrePays('France')} testid="pp-france" />
        {suivies.map((s) => <Carte key={s.v} libelle={s.v} valeur={s.n} />)}
      </Grille>
      <div style={{ marginTop: '8px' }}>
        <Bouton discret onClick={() => setAutresOuvert((v) => !v)} testid="pp-autres-villes">
          {autresOuvert ? 'Masquer' : 'Voir'} les autres villes ({autres.length})
        </Bouton>
        {autresOuvert && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginTop: '8px' }}>
            {autres.map((g) => <Pastille key={g.cle || 'x'}>{g.libelle} · {g.n}</Pastille>)}
          </div>
        )}
      </div>

      <Titre>Par canal</Titre>
      <Grille testid="pp-canaux">
        {CANAUX.map((k) => {
          const g = calc.canaux.find((x) => x.cle === k.id);
          return <Carte key={k.id} libelle={k.libelle} valeur={g ? g.n : 0} />;
        })}
      </Grille>
      <div style={{ marginTop: '6px', fontSize: '11px', color: DOUX }}>
        Canal = le premier cité dans la fiche (ex. « Visite / DM » compte en Visite).
      </div>

      <div style={{ marginTop: '16px' }}>
        <Bandeau testid="pp-lecture-seule">
          Lecture seule : cet écran ne contacte personne et ne modifie aucune fiche.
          Niche, pays et canal sont déduits de la vague, de la ville et du canal noté sur chaque fiche.
        </Bandeau>
      </div>
    </section>
  );
}
