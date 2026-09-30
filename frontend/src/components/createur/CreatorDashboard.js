/**
 * V559 — DASHBOARD CRÉATEUR AFROBOOST : UN SEUL écran, rendu tel quel dans
 * l'espace abonné, le dashboard coach / partenaire (onglet « Créateur ») — jamais
 * trois copies. Modèle : le Dashboard Créateur de Spordateur (4 cartes, lien +
 * QR, solde + retrait, filleuls), aux couleurs du coach (var(--primary-color)).
 *
 * Il ne calcule RIEN : chiffres, lien, filleuls et conversions viennent du
 * serveur (GET /api/createur/me). Le partage réutilise le moteur de partage du
 * parrainage (utils/parrainage : WhatsApp, carte, partage natif, copie).
 *
 * RÉSEAU : aucune lecture ici. Seul effet : précharger le fichier de la carte
 * (pour « Partager avec la carte »), clé = l'URL de la carte (une chaîne).
 */
import React, { useEffect, useState } from 'react';
import { QRCodeSVG } from 'qrcode.react';
import SvgIcon from '../SvgIcon';
import { lienWhatsApp, copier, partager, verifierApercuNavigateur } from '../../utils/parrainage';
import { chf, dateCourte } from '../../utils/createur';
import './createur.css';

function Kpi({ icone, libelle, valeur, testid, accent }) {
  return (
    <div className="cr-kpi" data-testid={testid}>
      <span className="cr-kpi-tete"><SvgIcon name={icone} size={14} /> {libelle}</span>
      <b className={accent ? 'cr-kpi-val cr-accent' : 'cr-kpi-val'}>{valeur}</b>
    </div>
  );
}

// V560 — le menu : une vue à la fois.
export const MENU = [['apercu', 'Vue d’ensemble'], ['lien', 'Lien'], ['filleuls', 'Filleuls'],
  ['conversions', 'Conversions'], ['retraits', 'Retraits']];

export const TEXTE_PARTAGE = 'Je te fais découvrir Afroboost : cardio, danse afrobeat et casques audio. Viens essayer !';

export default function CreatorDashboard({ data, onRetrait, retraitOccupe, retraitMessage, retraitErreur }) {
  const d = data || {};
  const k = d.kpis || {};
  const lien = d.lien || '';
  const lienPartage = d.lien_partage || lien;
  const carteUrl = d.carte_url || '';
  const [qr, setQr] = useState(false);
  const [info, setInfo] = useState('');
  const [fichier, setFichier] = useState(null);
  const [vue, setVue] = useState('apercu'); // V560 : le menu du Dashboard

  useEffect(() => {
    if (!carteUrl) return undefined;
    let vivant = true;
    verifierApercuNavigateur({ cardUrl: carteUrl, shareUrl: '' })
      .then((v) => { if (vivant) setFichier(v && v.file ? v.file : null); })
      .catch(() => { /* le partage par lien reste possible */ });
    return () => { vivant = false; };
  }, [carteUrl]);

  useEffect(() => {
    if (!info) return undefined;
    const t = setTimeout(() => setInfo(''), 2600);
    return () => clearTimeout(t);
  }, [info]);

  const nav = typeof navigator !== 'undefined' ? navigator : null;
  let peutCarte = false;
  if (fichier && nav && typeof nav.share === 'function' && typeof nav.canShare === 'function') {
    try { peutCarte = !!nav.canShare({ files: [fichier] }); } catch (e) { peutCarte = false; }
  }
  const surWhatsApp = () => { if (lienPartage) window.open(lienWhatsApp(`${TEXTE_PARTAGE}\n${lienPartage}`), '_blank', 'noopener'); };
  const surCarte = () => {
    if (!peutCarte) return;
    let p;
    try { p = nav.share({ files: [fichier], text: `${TEXTE_PARTAGE}\n${lienPartage}` }); } catch (e) { p = Promise.reject(e); }
    Promise.resolve(p).catch((e) => { if (!e || e.name !== 'AbortError') setInfo('Le partage n’a pas abouti. Copie le lien.'); });
  };
  const surPartager = () => {
    if (!lienPartage) return;
    partager({ title: 'Afroboost', text: TEXTE_PARTAGE, url: lienPartage })
      .then((r) => { if (r && r.ok && r.methode === 'copie') setInfo('Lien copié'); });
  };
  const surCopier = () => { if (lien) copier(lien).then((ok) => setInfo(ok ? 'Lien copié' : 'Copie impossible : sélectionne le lien.')); };

  const commissions = Array.isArray(d.commissions) ? d.commissions : [];
  const filleuls = Array.isArray(d.filleuls) ? d.filleuls : [];
  const conversions = Array.isArray(d.conversions) ? d.conversions : [];
  const retraits = Array.isArray(d.retraits) ? d.retraits : [];

  const lienBloc = (complet) => (
    <section className="cr-carte" data-testid="cr-lien">
      <h3 className="cr-h3">Ton lien créateur</h3>
      <p className="cr-lien-texte" data-testid="cr-lien-texte">{lien.replace(/^https?:\/\//, '') || '—'}</p>
      <div className="cr-lien-actions">
        <button type="button" className="cr-b cr-b--plein" onClick={surCopier} disabled={!lien} data-testid="cr-copier">
          <SvgIcon name="copy" size={18} /> Copier
        </button>
        <button type="button" className="cr-b" onClick={() => setQr((v) => !v)} disabled={!lien} aria-expanded={qr} data-testid="cr-qr">
          <SvgIcon name="qrCode" size={18} /> {qr ? 'Masquer le QR' : 'QR'}
        </button>
      </div>
      {qr && lien ? (
        <div className="cr-qr" data-testid="cr-qr-bloc"><QRCodeSVG value={lien} size={180} level="M" includeMargin={false} /></div>
      ) : null}
      {complet ? (
        <div className="cr-partage">
          <button type="button" className="cr-b cr-b--whatsapp" onClick={surWhatsApp} disabled={!lienPartage} data-testid="cr-whatsapp">
            <SvgIcon name="messageCircle" size={18} /> WhatsApp
          </button>
          <button type="button" className="cr-b" onClick={peutCarte ? surCarte : surPartager} disabled={!lienPartage} data-testid="cr-partager">
            <SvgIcon name="share" size={18} /> Partager
          </button>
        </div>
      ) : null}
      {info ? <p className="cr-info" role="status" data-testid="cr-info">{info}</p> : null}
      {complet ? (
        <p className="cr-fine" data-testid="cr-commission">
          {commissions.length
            ? <>Commission sur chaque achat éligible via ton lien : {commissions.join(' · ')}</>
            : 'Aucune commission n’est active pour le moment.'}
        </p>
      ) : null}
    </section>
  );

  const soldeBloc = (avecListe) => (
    <section className="cr-carte cr-solde" data-testid="cr-solde">
      <div>
        <p className="cr-fine" style={{ marginTop: 0 }}>Solde disponible</p>
        <b className="cr-solde-val">{chf(k.solde)}</b>
        <p className="cr-fine">Méthode : {d.methode === 'iban' ? 'IBAN' : 'TWINT'}{d.methode_detail ? ` (${d.methode_detail})` : ''}</p>
      </div>
      <button type="button" className="cr-b cr-b--plein cr-b--grand" onClick={onRetrait}
              disabled={!d.retrait_possible || retraitOccupe} data-testid="cr-retrait">
        <SvgIcon name="creditCard" size={18} /> {retraitOccupe ? 'Envoi…' : 'Demander un retrait'}
      </button>
      {d.retrait_en_cours ? <p className="cr-fine cr-pleine" data-testid="cr-retrait-en-cours">Une demande de retrait est en cours de traitement.</p> : null}
      {!d.retrait_en_cours && !d.retrait_possible ? (
        <p className="cr-fine cr-pleine">Minimum {chf(d.retrait_min)}. Une commission devient disponible une fois confirmée.</p>
      ) : null}
      {retraitMessage ? <p className="cr-info cr-pleine" role="status">{retraitMessage}</p> : null}
      {retraitErreur ? <p className="cr-erreur cr-pleine" role="alert">{retraitErreur}</p> : null}
      {avecListe && retraits.length ? (
        <ul className="cr-liste cr-pleine" data-testid="cr-retraits">
          {retraits.map((r) => (
            <li key={r.id} className="cr-ligne">
              <span>{dateCourte(r.date)}</span><b>{chf(r.montant)}</b><span className="cr-statut">{r.statut_libelle}</span>
            </li>
          ))}
        </ul>
      ) : null}
      {avecListe && !retraits.length ? <p className="cr-vide cr-pleine">Aucun retrait pour le moment.</p> : null}
    </section>
  );

  const filleulsBloc = (
    <section className="cr-carte" data-testid="cr-filleuls">
      <h3 className="cr-h3">Mes filleuls</h3>
      {filleuls.length ? (
        <ul className="cr-liste">
          {filleuls.map((f, i) => (
            <li key={`${f.prenom}-${f.date}-${i}`} className="cr-ligne">
              <span className="cr-nom">{f.prenom}</span>
              <span className="cr-fine">{dateCourte(f.date)} · {f.origine}</span>
              <span className="cr-statut">{f.statut}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="cr-vide">Aucun filleul pour le moment. Partage ton lien pour commencer à gagner.</p>
      )}
    </section>
  );

  const conversionsBloc = (
    <section className="cr-carte" data-testid="cr-conversions">
      <h3 className="cr-h3">Mes conversions</h3>
      {conversions.length ? (
        <ul className="cr-liste">
          {conversions.map((c) => (
            <li key={c.id} className="cr-ligne cr-ligne--conv">
              <span className="cr-nom">{c.offre}</span>
              <span className="cr-fine">{dateCourte(c.date)} · {chf(c.montant)}</span>
              <b className="cr-accent">{chf(c.commission)}</b>
              <span className="cr-statut">{c.statut_libelle}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="cr-vide">Aucune conversion pour le moment : seuls les achats payés comptent.</p>
      )}
    </section>
  );

  return (
    <div className="cr-root" data-testid="creator-dashboard">
      <header className="cr-entete">
        <h2 className="cr-titre">Dashboard Créateur</h2>
        <p className="cr-sous">Suis tes revenus et tes filleuls en temps réel</p>
      </header>

      {/* V560 : un petit menu — jamais tout le contenu sur une seule longue page. */}
      <nav className="cr-menu" role="tablist" aria-label="Dashboard Créateur" data-testid="cr-menu">
        {MENU.map(([id, libelle]) => (
          <button key={id} type="button" role="tab" aria-selected={vue === id} className={vue === id ? 'on' : ''}
                  onClick={() => setVue(id)} data-testid={`cr-menu-${id}`}>{libelle}</button>
        ))}
      </nav>

      {vue === 'apercu' ? (
        <>
          <div className="cr-kpis">
            <Kpi icone="dollarSign" libelle="Gains" valeur={chf(k.gains_totaux)} testid="cr-kpi-gains" />
            <Kpi icone="clock" libelle="En attente" valeur={chf(k.en_attente)} testid="cr-kpi-attente" accent />
            <Kpi icone="users" libelle="Filleuls" valeur={String(k.filleuls || 0)} testid="cr-kpi-filleuls" />
            <Kpi icone="shoppingCart" libelle="Achats" valeur={String(k.achats || 0)} testid="cr-kpi-achats" />
          </div>
          {lienBloc(false)}
          {soldeBloc(false)}
        </>
      ) : null}
      {vue === 'lien' ? lienBloc(true) : null}
      {vue === 'filleuls' ? filleulsBloc : null}
      {vue === 'conversions' ? conversionsBloc : null}
      {vue === 'retraits' ? soldeBloc(true) : null}
    </div>
  );
}
