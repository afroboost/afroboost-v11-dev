/**
 * V534 — BILLETS DUO : les deux billets d'un Pass Duo débloqué.
 *
 * Un billet par rôle (parrain / invité), chacun avec SON QR — la valeur
 * `qr_value` vient du serveur et respecte le format déjà accepté par le
 * scanner (contrat §5, TicketDTO) : rien n'est fabriqué ici. Fond blanc
 * obligatoire sous le QR : c'est la seule condition pour qu'il se scanne, la
 * couleur du coach ne s'y applique pas (comme « Mon QR Code » de l'espace).
 */
import React from 'react';
import { QRCodeSVG } from 'qrcode.react';
import SvgIcon from '../SvgIcon';
import { libelleJour, libelleHeure } from '../../utils/parrainage';

const LIBELLE_ROLE = {
  sponsor: 'Séance déduite de ton forfait',
  invitee: 'Essai gratuit Afroboost',
};

export function libelleRole(role) {
  return LIBELLE_ROLE[role] || '';
}

/**
 * V562 — le titre du billet selon QUI regarde : « Ton billet » pour le sien,
 * « Billet de <Prénom> » pour l'autre. `vue` = 'parrain' | 'ami' (défaut : parrain).
 */
export function titreBillet(ticket, vue) {
  const t = ticket || {};
  const aMoi = (vue === 'ami' && t.role === 'invitee') || (vue !== 'ami' && t.role === 'sponsor');
  if (aMoi) return 'Ton billet';
  const nom = t.first_name || (t.role === 'invitee' ? 'ton ami' : 'ton parrain');
  return `Billet de ${nom}`;
}

function Billet({ ticket, vue }) {
  const valide = !!ticket.validated;
  // V562 : l'origine RÉELLE vient du serveur ; repli sur l'ancien libellé si absent.
  const origine = ticket.origine || libelleRole(ticket.role);
  const quand = ticket.date ? [libelleJour(ticket.date), libelleHeure(ticket.date)].filter(Boolean).join(' · ') : '';
  return (
    <div
      className={`cp-card cp-ticket${valide ? ' cp-ticket--validated' : ''}`}
      data-testid={`billet-${ticket.role || 'x'}`}
    >
      <div>
        <b data-testid={`billet-titre-${ticket.role || 'x'}`}>{titreBillet(ticket, vue)}</b>
        <small data-testid={`billet-origine-${ticket.role || 'x'}`}>{origine}</small>
        {quand ? <small>{quand}</small> : null}
        {ticket.reservationCode ? (
          <small className="cp-code-inline">Code {ticket.reservationCode}</small>
        ) : null}
        {valide ? (
          <small style={{ color: 'var(--cp-ok-soft)' }}>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
              <SvgIcon name="check" size={12} /> Participation validée
            </span>
          </small>
        ) : null}
      </div>
      {ticket.qr_value ? (
        <div className="cp-qr" aria-label={`QR code de ${ticket.first_name || ''}`}>
          <QRCodeSVG value={String(ticket.qr_value)} size={93} level="M" includeMargin={false}
                     bgColor="#ffffff" fgColor="#000000" />
        </div>
      ) : null}
    </div>
  );
}

/**
 * @param {object[]} tickets  TicketDTO[] du serveur
 * @param {boolean}  compact  sans le rappel « Arrivez 15 minutes avant »
 */
export default function BilletsDuo({ tickets, compact, vue }) {
  const liste = Array.isArray(tickets) ? tickets.filter(Boolean) : [];
  if (!liste.length) return null;
  // Le parrain d'abord, puis l'invité : l'ordre du duo, pas celui du serveur.
  const ordre = liste.slice().sort((a, b) => (a.role === 'sponsor' ? -1 : 0) - (b.role === 'sponsor' ? -1 : 0));
  return (
    <div data-testid="billets-duo">
      {ordre.map((t, i) => <Billet key={t.reservationCode || t.role || i} ticket={t} vue={vue} />)}
      {!compact && (
        <p className="cp-center cp-fine">Arrivez 15 minutes avant · Eau et serviette · Téléphone en mode avion</p>
      )}
    </div>
  );
}
