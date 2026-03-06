/**
 * Custom Hook for Data Caching
 * Provides cached data fetching with expiration for performance optimization
 */
import { useState, useEffect, useCallback, useRef } from 'react';
import axios from 'axios';

const API = (process.env.REACT_APP_BACKEND_URL || '') + '/api';

// Cache storage with TTL (Time To Live)
const cache = {
  data: {},
  timestamps: {},
  // Default TTL: 5 minutes for static data, 1 minute for dynamic data
  TTL: {
    courses: 5 * 60 * 1000,      // 5 minutes
    offers: 5 * 60 * 1000,       // 5 minutes
    concept: 10 * 60 * 1000,     // 10 minutes
    paymentLinks: 10 * 60 * 1000 // 10 minutes
  }
};

/**
 * Check if cached data is still valid
 */
const isCacheValid = (key) => {
  if (!cache.data[key] || !cache.timestamps[key]) return false;
  const ttl = cache.TTL[key] || 60000; // Default 1 minute
  return Date.now() - cache.timestamps[key] < ttl;
};

/**
 * Set data in cache
 */
const setCache = (key, data) => {
  cache.data[key] = data;
  cache.timestamps[key] = Date.now();
};

/**
 * Get data from cache
 */
const getCache = (key) => {
  if (isCacheValid(key)) {
    return cache.data[key];
  }
  return null;
};

/**
 * Invalidate cache for a specific key
 */
export const invalidateCache = (key) => {
  delete cache.data[key];
  delete cache.timestamps[key];
};

/**
 * Invalidate all cache
 */
export const invalidateAllCache = () => {
  cache.data = {};
  cache.timestamps = {};
};

/**
 * Custom hook for cached data fetching
 */
export const useDataCache = () => {
  const [courses, setCourses] = useState([]);
  const [offers, setOffers] = useState([]);
  const [concept, setConcept] = useState({});
  const [paymentLinks, setPaymentLinks] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const fetchingRef = useRef(false);

  /**
   * Fetch data with caching
   */
  const fetchWithCache = useCallback(async (key, endpoint) => {
    // Check cache first
    const cachedData = getCache(key);
    if (cachedData) {
      return cachedData;
    }

    // Fetch from API
    const response = await axios.get(`${API}/${endpoint}`);
    const data = response.data;
    
    // Store in cache
    setCache(key, data);
    
    return data;
  }, []);

  /**
   * Load all data (with cache optimization)
   */
  const loadData = useCallback(async (forceRefresh = false) => {
    if (fetchingRef.current) return;
    fetchingRef.current = true;
    
    try {
      setLoading(true);
      setError(null);

      // Invalidate cache if force refresh
      if (forceRefresh) {
        invalidateAllCache();
      }

      // Fetch all data in parallel
      const [coursesData, offersData, conceptData, linksData] = await Promise.all([
        fetchWithCache('courses', 'courses'),
        fetchWithCache('offers', 'offers'),
        fetchWithCache('concept', 'concept'),
        fetchWithCache('paymentLinks', 'payment-links')
      ]);

      setCourses(coursesData);
      setOffers(offersData);
      setConcept(conceptData);
      setPaymentLinks(linksData);

    } catch (err) {
      console.error('Error loading cached data:', err);
      setError(err.message);
    } finally {
      setLoading(false);
      fetchingRef.current = false;
    }
  }, [fetchWithCache]);

  /**
   * Refresh specific data type
   */
  const refreshData = useCallback(async (type) => {
    invalidateCache(type);
    
    const endpoints = {
      courses: 'courses',
      offers: 'offers',
      concept: 'concept',
      paymentLinks: 'payment-links'
    };

    if (endpoints[type]) {
      const data = await fetchWithCache(type, endpoints[type]);
      
      switch (type) {
        case 'courses':
          setCourses(data);
          break;
        case 'offers':
          setOffers(data);
          break;
        case 'concept':
          setConcept(data);
          break;
        case 'paymentLinks':
          setPaymentLinks(data);
          break;
        default:
          break;
      }
    }
  }, [fetchWithCache]);

  // Initial load
  useEffect(() => {
    loadData();
  }, [loadData]);

  return {
    courses,
    offers,
    concept,
    paymentLinks,
    loading,
    error,
    refreshData,
    reloadAll: () => loadData(true),
    invalidateCache,
    invalidateAllCache
  };
};

export default useDataCache;
