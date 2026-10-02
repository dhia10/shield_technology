/**
 * Shield Technology Proprietary Telemetry Tracker (v1.0.0)
 * Non-blocking, privacy-preserving behavioral event tracker.
 * Zero external dependencies. Uses navigator.sendBeacon and fetch(keepalive).
 */
(function (window, document) {
  'use strict';

  var CONFIG = {
    endpoint: '/api/v1/telemetry/events',
    flushIntervalMs: 4000,
    maxBatchSize: 20,
    sessionKey: 'shield_telemetry_sid',
  };

  // Generate or retrieve anonymous session ID (Zero-PII)
  function getSessionId() {
    var sid = null;
    try {
      sid = sessionStorage.getItem(CONFIG.sessionKey);
      if (!sid) {
        sid = 'sid_' + Math.random().toString(36).substring(2, 10) + '_' + Date.now().toString(36);
        sessionStorage.setItem(CONFIG.sessionKey, sid);
      }
    } catch (e) {
      sid = 'sid_ephemeral_' + Math.random().toString(36).substring(2, 10);
    }
    return sid;
  }

  var sessionId = getSessionId();
  var eventQueue = [];
  var pageStartTime = Date.now();

  function pushEvent(eventType, elementId, metadata) {
    var eventObj = {
      event_type: eventType,
      session_id: sessionId,
      page_path: window.location.pathname || '/',
      element_id: elementId || null,
      duration_seconds: null,
      metadata: metadata || {},
    };
    eventQueue.push(eventObj);

    if (eventQueue.length >= CONFIG.maxBatchSize) {
      flushQueue();
    }
  }

  function flushQueue(isSync) {
    if (eventQueue.length === 0) return;

    var payload = {
      events: eventQueue.slice(0, CONFIG.maxBatchSize),
    };
    eventQueue = eventQueue.slice(payload.events.length);
    var bodyStr = JSON.stringify(payload);

    // Prioritize non-blocking navigator.sendBeacon during page transitions
    if (navigator.sendBeacon) {
      try {
        var blob = new Blob([bodyStr], { type: 'application/json' });
        var sent = navigator.sendBeacon(CONFIG.endpoint, blob);
        if (sent) return;
      } catch (err) {
        // Fallback to fetch
      }
    }

    if (window.fetch) {
      try {
        window.fetch(CONFIG.endpoint, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: bodyStr,
          keepalive: true,
        }).catch(function () {});
      } catch (err) {}
    }
  }

  // Periodic flush
  setInterval(function () {
    flushQueue(false);
  }, CONFIG.flushIntervalMs);

  // 1. Initial Page View Tracking
  if (document.readyState === 'complete' || document.readyState === 'interactive') {
    pushEvent('PAGE_VIEW', null, { title: document.title, referrer: document.referrer || null });
  } else {
    document.addEventListener('DOMContentLoaded', function () {
      pushEvent('PAGE_VIEW', null, { title: document.title, referrer: document.referrer || null });
    });
  }

  // 2. Global CTA and Navigation Click Interception
  document.addEventListener('click', function (e) {
    var target = e.target;
    var ctaEl = target.closest('a, button, [data-track-cta], input[type="submit"]');
    if (!ctaEl) return;

    var elementId = ctaEl.getAttribute('data-track-cta') ||
                    ctaEl.id ||
                    ctaEl.getAttribute('name') ||
                    (ctaEl.textContent ? ctaEl.textContent.trim().substring(0, 40) : 'unknown_cta');

    var isQuote = ctaEl.classList.contains('cta-quote') ||
                  (ctaEl.getAttribute('href') && ctaEl.getAttribute('href').indexOf('contact') !== -1);

    pushEvent(isQuote ? 'FUNNEL_STEP' : 'CTA_CLICK', elementId, {
      tag: ctaEl.tagName.toLowerCase(),
      href: ctaEl.getAttribute('href') || null,
    });
  }, { passive: true });

  // 3. Page Dwell Time on Exit
  window.addEventListener('beforeunload', function () {
    var dwellSeconds = Math.round((Date.now() - pageStartTime) / 1000);
    pushEvent('TIME_SPENT', 'page_exit', { duration_seconds: dwellSeconds });
    flushQueue(true);
  });

  // Public SDK interface
  window.ShieldTelemetry = {
    track: function (eventType, elementId, metadata) {
      pushEvent(eventType, elementId, metadata);
    },
    flush: function () {
      flushQueue(false);
    },
    getSessionId: function () {
      return sessionId;
    },
  };
})(window, document);
