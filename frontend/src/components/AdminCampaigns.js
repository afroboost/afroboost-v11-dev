// AdminCampaigns.js - Gestionnaire de campagnes marketing avec envoi Email/WA/Insta
// Compatible Vercel - Extrait de App.js pour architecture modulaire
import { useState, useMemo, useEffect } from 'react';
import emailjs from '@emailjs/browser';
import SvgIcon from './SvgIcon';

// Initialisation immédiate d'EmailJS avec votre clé publique
emailjs.init("5LfgQSIEQoqq_XSqt");

// === HOOKS PERSONNALISÉS POUR LES CAMPAGNES ===

/**
 * Hook pour gérer les statistiques des contacts
 */
export const useContactStats = (allContacts, selectedContactsForCampaign, targetType) => {
  return useMemo(() => {
    const contacts = targetType === "selected" 
      ? allContacts.filter(c => selectedContactsForCampaign.includes(c.id))
      : allContacts;
    return {
      total: contacts.length,
      withEmail: contacts.filter(c => c.email && c.email.includes('@')).length,
      withPhone: contacts.filter(c => c.phone).length,
      contacts
    };
  }, [allContacts, selectedContactsForCampaign, targetType]);
};

/**
 * Hook pour la gestion du mode envoi direct
 */
export const useDirectSend = (allContacts, selectedContactsForCampaign, targetType) => {
  const [directSendMode, setDirectSendMode] = useState(false);
  const [currentWhatsAppIndex, setCurrentWhatsAppIndex] = useState(0);
  const [instagramProfile, setInstagramProfile] = useState("afroboost");
  const [messageCopied, setMessageCopied] = useState(false);
  const [isSendingAuto, setIsSendingAuto] = useState(false);

  // Obtenir les contacts pour l'envoi direct
  const getContactsForDirectSend = () => {
    if (targetType === "selected") {
      return allContacts.filter(c => selectedContactsForCampaign.includes(c.id));
    }
    return allContacts;
  };

  // Générer mailto: groupé avec BCC pour tous les emails
  const generateGroupedEmailLink = (campaignName, message, mediaUrl) => {
    const contacts = getContactsForDirectSend();
    const emails = contacts.map(c => c.email).filter(e => e && e.includes('@'));
    
    if (emails.length === 0) return null;
    
    const subject = campaignName || "Afroboost - Message";
    const body = mediaUrl 
      ? `${message}\n\n🔗 Voir le visuel: ${mediaUrl}`
      : message;
    
    const firstEmail = emails[0];
    const bccEmails = emails.slice(1).join(',');
    
    return `mailto:${firstEmail}?${bccEmails ? `bcc=${bccEmails}&` : ''}subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
  };

  // Obtenir le contact WhatsApp actuel
  const getCurrentWhatsAppContact = () => {
    const contacts = getContactsForDirectSend().filter(c => c.phone);
    return contacts[currentWhatsAppIndex] || null;
  };

  // Navigation WhatsApp
  const nextWhatsAppContact = () => {
    const contacts = getContactsForDirectSend().filter(c => c.phone);
    if (currentWhatsAppIndex < contacts.length - 1) {
      setCurrentWhatsAppIndex(currentWhatsAppIndex + 1);
    }
  };

  const prevWhatsAppContact = () => {
    if (currentWhatsAppIndex > 0) {
      setCurrentWhatsAppIndex(currentWhatsAppIndex - 1);
    }
  };

  // Copier le message pour Instagram
  const copyMessageForInstagram = async (message, mediaUrl) => {
    const fullMessage = mediaUrl 
      ? `${message}\n\n🔗 ${mediaUrl}`
      : message;
    
    try {
      await navigator.clipboard.writeText(fullMessage);
      setMessageCopied(true);
      setTimeout(() => setMessageCopied(false), 3000);
    } catch (err) {
      const textarea = document.createElement('textarea');
      textarea.value = fullMessage;
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand('copy');
      document.body.removeChild(textarea);
      setMessageCopied(true);
      setTimeout(() => setMessageCopied(false), 3000);
    }
  };

  // --- NOUVELLE FONCTION D'ENVOI AUTOMATIQUE EMAILJS ---
  const sendAutoEmailJS = async (campaignName, message) => {
    const contacts = getContactsForDirectSend().filter(c => c.email && c.email.includes('@'));
    if (contacts.length === 0) {
      alert("Aucun contact avec email valide trouvé.");
      return;
    }

    setIsSendingAuto(true);
    let successCount = 0;

    try {
      for (const contact of contacts) {
        await emailjs.send(
          "service_8mrmxim",
          "template_3n1u86p",
          {
            to_name: contact.name || "Client",
            to_email: contact.email,
            message: message,
            subject: campaignName || "Afroboost - Message Spécial"
          }
        );
        successCount++;
      }
      alert(`Félicitations ! ${successCount} email(s) envoyé(s) avec succès via EmailJS.`);
    } catch (error) {
      console.error("Erreur EmailJS:", error);
      alert("L'envoi a échoué. Vérifiez vos crédits EmailJS ou la console.");
    } finally {
      setIsSendingAuto(false);
    }
  };

  return {
    directSendMode,
    setDirectSendMode,
    currentWhatsAppIndex,
    instagramProfile,
    setInstagramProfile,
    messageCopied,
    isSendingAuto,
    sendAutoEmailJS,
    generateGroupedEmailLink,
    getCurrentWhatsAppContact,
    nextWhatsAppContact,
    prevWhatsAppContact,
    copyMessageForInstagram,
    getContactsForDirectSend
  };
};

// === FONCTIONS UTILITAIRES POUR LES CAMPAGNES ===

export const generateWhatsAppLink = (phone, message, mediaUrl, contactName) => {
  const formattedPhone = phone?.replace(/\D/g, '');
  let personalizedMessage = message;
  if (contactName) {
    const firstName = contactName.split(' ')[0];
    personalizedMessage = message.replace(/{prénom}/gi, firstName);
  }
  const fullMessage = mediaUrl 
    ? `${personalizedMessage}\n\n🔗 Voir le visuel: ${mediaUrl}`
    : personalizedMessage;
  return `https://api.whatsapp.com/send?phone=${formattedPhone}&text=${encodeURIComponent(fullMessage)}`;
};

export const generateInstagramLink = (username) => {
  return `https://instagram.com/${username || 'afroboost'}`;
};

// === COMPOSANT COMPTEUR DE CONTACTS ===
export const ContactCounter = ({ contactStats, directSendMode, onToggleDirectSend }) => (
  <div className="mb-6 p-4 rounded-xl glass border border-purple-500/30">
    <div className="flex flex-wrap items-center justify-between gap-4">
      <div>
        <h3 className="text-white font-semibold text-lg">
          <SvgIcon name="users" size={18} />{' '}Nombre de clients ciblés : <span className="text-pink-400">{contactStats.total}</span>
        </h3>
        <p className="text-sm text-white/60 mt-1">
          <SvgIcon name="mail" size={14} />{' '}{contactStats.withEmail} avec email • <SvgIcon name="phone" size={14} />{' '}{contactStats.withPhone} avec WhatsApp
        </p>
      </div>
      <div className="flex gap-2">
        <button 
          type="button"
          onClick={onToggleDirectSend}
          className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${directSendMode ? 'bg-pink-600 text-white' : 'glass text-white border border-purple-500/30'}`}
        >
          {directSendMode ? (
            <span className="inline-flex items-center gap-1.5"><SvgIcon name="check" size={14} /> Mode Envoi Direct</span>
          ) : (
            <span className="inline-flex items-center gap-1.5"><SvgIcon name="rocket" size={14} /> Envoi Direct</span>
          )}
        </button>
      </div>
    </div>
  </div>
);

// === COMPOSANT MODE ENVOI DIRECT ===
export const DirectSendPanel = ({
  contactStats,
  newCampaign,
  setNewCampaign,
  generateGroupedEmailLink,
  generateWhatsAppLink,
  getCurrentWhatsAppContact,
  currentWhatsAppIndex,
  prevWhatsAppContact,
  nextWhatsAppContact,
  instagramProfile,
  setInstagramProfile,
  copyMessageForInstagram,
  messageCopied,
  isSendingAuto,
  sendAutoEmailJS
}) => (
  <div className="mb-8 p-5 rounded-xl glass border-2 border-pink-500/50">
    <h3 className="text-white font-semibold mb-4 flex items-center gap-2">
      <SvgIcon name="rocket" size={14} />
      Envoi Direct par Canal
      <span className="text-xs text-pink-400 font-normal">(Utilisez le message ci-dessous)</span>
    </h3>

    <div className="mb-4">
      <label className="block mb-2 text-white text-sm">Message à envoyer</label>
      <textarea 
        value={newCampaign.message} 
        onChange={e => setNewCampaign({...newCampaign, message: e.target.value})}
        className="w-full px-4 py-3 rounded-lg neon-input" 
        rows={3}
        placeholder="Votre message..."
      />
      {newCampaign.mediaUrl && (
        <p className="text-xs text-green-400 mt-1"><SvgIcon name="check" size={14} />{' '}Média attaché: {newCampaign.mediaUrl.substring(0, 50)}...</p>
      )}
    </div>

    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
      
      {/* === EMAIL AUTOMATISÉ EMAILJS === */}
      <div className="p-4 rounded-xl bg-blue-900/40 border-2 border-blue-400">
        <h4 className="text-white font-bold mb-3 flex items-center gap-2 text-sm">
          <SvgIcon name="mail" size={14} />
          Email Automatique
        </h4>
        <button 
          type="button"
          onClick={() => sendAutoEmailJS(newCampaign.name, newCampaign.message)}
          disabled={isSendingAuto || contactStats.withEmail === 0}
          className={`w-full py-3 rounded-lg ${isSendingAuto ? 'bg-gray-600' : 'bg-gradient-to-r from-blue-500 to-indigo-600 hover:scale-105'} text-white text-center font-bold transition-all shadow-lg`}
        >
          {isSendingAuto ? (
            <span className="inline-flex items-center gap-1.5"><SvgIcon name="loader" size={14} className="animate-spin" /> Envoi...</span>
          ) : (
            <span className="inline-flex items-center gap-1.5"><SvgIcon name="rocket" size={14} /> Lancer l'envoi</span>
          )}
        </button>
        <p className="text-[10px] text-blue-200 mt-2 text-center">Via votre compte EmailJS</p>
      </div>

      {/* === WHATSAPP UN PAR UN === */}
      <div className="p-4 rounded-xl bg-green-900/20 border border-green-500/30">
        <h4 className="text-white font-semibold mb-3 flex items-center gap-2 text-sm">
          <SvgIcon name="phone" size={14} />
          WhatsApp
        </h4>
        {contactStats.withPhone > 0 ? (
          <>
            <p className="text-xs text-white/60 mb-2">
              Contact {currentWhatsAppIndex + 1}/{contactStats.withPhone}
            </p>
            {getCurrentWhatsAppContact() && (
              <p className="text-sm text-green-300 mb-3 truncate font-medium">
                → {getCurrentWhatsAppContact()?.name}
              </p>
            )}
            <a 
              href={getCurrentWhatsAppContact() ? generateWhatsAppLink(
                getCurrentWhatsAppContact()?.phone,
                newCampaign.message,
                newCampaign.mediaUrl,
                getCurrentWhatsAppContact()?.name
              ) : '#'}
              target="_blank"
              rel="noopener noreferrer"
              className="block w-full py-2 rounded-lg bg-green-600 hover:bg-green-700 text-white text-center font-medium mb-2 transition-all"
            >
              <span className="inline-flex items-center gap-1.5"><SvgIcon name="phone" size={14} /> Ouvrir WA</span>
            </a>
            <div className="flex gap-2">
              <button 
                type="button"
                onClick={prevWhatsAppContact}
                disabled={currentWhatsAppIndex === 0}
                aria-label="Contact précédent"
                className="flex-1 py-1 rounded-lg glass text-white text-xs disabled:opacity-30"
              >
                <SvgIcon name="arrowLeft" size={14} />
              </button>
              <button 
                type="button"
                onClick={nextWhatsAppContact}
                disabled={currentWhatsAppIndex >= contactStats.withPhone - 1}
                aria-label="Contact suivant"
                className="flex-1 py-1 rounded-lg glass text-white text-xs disabled:opacity-30"
              >
                <SvgIcon name="arrowRight" size={14} />
              </button>
            </div>
          </>
        ) : (
          <button disabled className="w-full py-3 rounded-lg bg-gray-600/50 text-gray-400 cursor-not-allowed">
            Aucun numéro
          </button>
        )}
      </div>

      {/* === INSTAGRAM DM === */}
      <div className="p-4 rounded-xl bg-purple-900/20 border border-purple-500/30">
        <h4 className="text-white font-semibold mb-3 flex items-center gap-2 text-sm">
          <SvgIcon name="camera" size={14} />
          Instagram DM
        </h4>
        <button 
          type="button"
          onClick={() => copyMessageForInstagram(newCampaign.message, newCampaign.mediaUrl)}
          className={`w-full py-2 rounded-lg ${messageCopied ? 'bg-green-600' : 'bg-purple-600 hover:bg-purple-700'} text-white text-sm font-medium mb-2 transition-all`}
        >
          {messageCopied ? (
            <span className="inline-flex items-center gap-1.5"><SvgIcon name="check" size={14} /> Copié !</span>
          ) : (
            <span className="inline-flex items-center gap-1.5"><SvgIcon name="clipboard" size={14} /> Copier</span>
          )}
        </button>
        <a 
          href={generateInstagramLink(instagramProfile)}
          target="_blank"
          rel="noopener noreferrer"
          className="block w-full py-2 rounded-lg glass text-white text-center text-xs hover:bg-purple-500/20 transition-all"
        >
          Ouvrir IG
        </a>
      </div>

    </div>
  </div>
);

// === COMPOSANT BADGE STATUT ===
export const CampaignStatusBadge = ({ status }) => {
  const statusConfig = {
    draft: { label: <><SvgIcon name="edit" size={14} /> Brouillon</>, className: 'bg-gray-600/30 text-gray-400' },
    scheduled: { label: <><SvgIcon name="clock" size={14} /> Programmée</>, className: 'bg-yellow-600/30 text-yellow-400' },
    sending: { label: <><SvgIcon name="rocket" size={14} /> En cours</>, className: 'bg-blue-600/30 text-blue-400' },
    completed: { label: <><SvgIcon name="check" size={14} /> Terminée</>, className: 'bg-green-600/30 text-green-400' },
    failed: { label: <><SvgIcon name="close" size={14} /> Échouée</>, className: 'bg-red-600/30 text-red-400' }
  };

  const config = statusConfig[status] || statusConfig.draft;

  return (
    <span className={`px-2 py-1 rounded text-xs inline-flex items-center gap-1.5 ${config.className}`}>
      {config.label}
    </span>
  );
};

// === COMPOSANT RESULT BADGE ===
export const ResultBadge = ({ status }) => {
  if (status === 'sent') {
    return <span className="px-2 py-1 rounded text-xs inline-flex items-center gap-1.5 bg-green-600/30 text-green-400"><SvgIcon name="check" size={14} /> Envoyé</span>;
  }
  if (status === 'failed') {
    return <span className="px-2 py-1 rounded text-xs inline-flex items-center gap-1.5 bg-red-600/30 text-red-400"><SvgIcon name="close" size={14} /> Échec</span>;
  }
  return <span className="px-2 py-1 rounded text-xs inline-flex items-center gap-1.5 bg-gray-600/30 text-gray-400"><SvgIcon name="hourglass" size={14} /> En attente</span>;
};

export default {
  useContactStats,
  useDirectSend,
  generateWhatsAppLink,
  generateInstagramLink,
  ContactCounter,
  DirectSendPanel,
  CampaignStatusBadge,
  ResultBadge
};