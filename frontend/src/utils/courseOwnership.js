/**
 * « Ce cours est-il a moi ? » — et rien d'autre.
 *
 * La question a longtemps ete posee via la liste des cours PROPOSABLES, qui
 * ecarte les archives. Or l'appartenance n'a rien a voir avec l'archivage : les
 * vraies seances recurrentes d'un coach, celles que ses offres vendent, sont
 * archivees. Les juger sur cette liste les rendait definitivement non
 * modifiables — jour, heure et lieu compris — sans qu'aucun autre ecran ne
 * puisse prendre le relais.
 *
 * On separe donc les deux notions. Proposer un horaire a AJOUTER : on n'y met
 * pas un cours archive. Autoriser la MODIFICATION d'un cours deja rattache :
 * seule l'appartenance compte.
 */

export function appartientAuCoach(cours, { coachEmail, isSuperAdmin } = {}) {
  if (!cours) return false;
  if (isSuperAdmin) return true;
  if (!coachEmail) return true;          // portee indeterminee : on n'interdit pas
  return String(cours.coach_id || '').toLowerCase()
       === String(coachEmail || '').toLowerCase();
}

export default appartientAuCoach;
