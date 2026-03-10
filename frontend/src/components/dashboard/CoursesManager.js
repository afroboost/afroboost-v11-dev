/**
 * CoursesManager Component v88
 * Gestion des cours + bouton Studio Audio glow + contrôle avis
 */
import React, { useState } from 'react';
import axios from 'axios';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';
const API = `${BACKEND_URL}/api`;

const CoursesManager = ({
  courses,
  setCourses,
  newCourse,
  setNewCourse,
  updateCourse,
  openAudioModal,
  hideAudioButton = false,
  lang,
  t,
  coachEmail
}) => {
  // v88: État pour la demande d'avis
  const [reviewRequestSending, setReviewRequestSending] = useState({});
  const [reviewRequestSuccess, setReviewRequestSuccess] = useState({});
  const [autoReviewEnabled, setAutoReviewEnabled] = useState(() => {
    return localStorage.getItem(`afroboost_auto_review_${coachEmail || ''}`) !== 'false';
  });

  // v88: Envoyer manuellement une demande d'avis pour un cours
  const sendReviewRequest = async (course) => {
    setReviewRequestSending(prev => ({ ...prev, [course.id]: true }));
    try {
      const res = await axios.post(`${API}/reviews/request`, {
        coach_email: coachEmail,
        course_id: course.id,
        course_name: course.name
      });
      setReviewRequestSuccess(prev => ({ ...prev, [course.id]: res.data.sent_count }));
      setTimeout(() => setReviewRequestSuccess(prev => ({ ...prev, [course.id]: null })), 4000);
    } catch (err) {
      console.error("Erreur envoi demande avis:", err);
      setReviewRequestSuccess(prev => ({ ...prev, [course.id]: -1 }));
      setTimeout(() => setReviewRequestSuccess(prev => ({ ...prev, [course.id]: null })), 3000);
    }
    setReviewRequestSending(prev => ({ ...prev, [course.id]: false }));
  };

  // v88: Toggle auto-review
  const toggleAutoReview = () => {
    const newVal = !autoReviewEnabled;
    setAutoReviewEnabled(newVal);
    localStorage.setItem(`afroboost_auto_review_${coachEmail || ''}`, newVal.toString());
  };