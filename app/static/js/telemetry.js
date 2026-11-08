/**
 * Vellakshya Privacy-First Telemetry Client
 * ==============================================================================
 * Cookieless, local-first analytics client adhering to GDPR/ePrivacy standards.
 * - Strictly respects Do Not Track (DNT) / Global Privacy Control (GPC).
 * - Zero third-party cookies or persistent client fingerprinting.
 * - Captures high-level anonymized feature interactions without document text.
 * ==============================================================================
 */

(function () {
  'use strict';

  // Check user privacy preferences
  const isDNTEnabled = () => {
    return (
      window.doNotTrack === '1' ||
      navigator.doNotTrack === '1' ||
      navigator.doNotTrack === 'yes' ||
      navigator.globalPrivacyControl === true
    );
  };

  const Telemetry = {
    enabled: !isDNTEnabled(),
    sessionStartTime: Date.now(),
    eventBuffer: [],

    trackEvent(category, action, label = null) {
      if (!this.enabled) {
        return;
      }

      const eventPayload = {
        category,
        action,
        label,
        timestamp: new Date().toISOString(),
        viewportWidth: window.innerWidth,
        viewportHeight: window.innerHeight,
      };

      this.eventBuffer.push(eventPayload);

      // Keep in-memory buffer bounded
      if (this.eventBuffer.length > 100) {
        this.eventBuffer.shift();
      }

      // If an external privacy analytics endpoint is configured, dispatch beacon
      if (window.__VELLAKSHYA_ANALYTICS_ENDPOINT__) {
        try {
          if (navigator.sendBeacon) {
            navigator.sendBeacon(
              window.__VELLAKSHYA_ANALYTICS_ENDPOINT__,
              JSON.stringify(eventPayload)
            );
          }
        } catch (_) {
          // Silent fallback for offline or blocked telemetry
        }
      }
    },

    getRecentEvents() {
      return [...this.eventBuffer];
    },
  };

  // Expose to window for application and automated verification
  window.VellakshyaAnalytics = Telemetry;

  // Track initial page view
  if (Telemetry.enabled) {
    Telemetry.trackEvent('Navigation', 'PageView', window.location.pathname);
  }
})();
