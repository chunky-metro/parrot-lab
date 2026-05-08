// storage.js — localStorage wrapper for parrot-lab.
// All keys are namespaced with `parrot-lab:`. Values are JSON-encoded.
// Owns: streak (consecutive-day), per-phrase attempt history, settings.

(function () {
  'use strict';

  const PREFIX = 'parrot-lab:';
  const KEY_STREAK = PREFIX + 'streak';
  const KEY_HISTORY = PREFIX + 'history';
  const KEY_SETTINGS = PREFIX + 'settings';
  const HISTORY_CAP = 500;

  function todayLocal() {
    const d = new Date();
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const dd = String(d.getDate()).padStart(2, '0');
    return `${y}-${m}-${dd}`;
  }

  function dayDiff(a, b) {
    // a, b are YYYY-MM-DD; returns whole-day diff a-b.
    const da = new Date(a + 'T00:00:00');
    const db = new Date(b + 'T00:00:00');
    return Math.round((da - db) / 86400000);
  }

  function readJSON(key, fallback) {
    try {
      const raw = localStorage.getItem(key);
      return raw == null ? fallback : JSON.parse(raw);
    } catch (e) {
      console.warn('storage read failed', key, e);
      return fallback;
    }
  }

  function writeJSON(key, value) {
    try {
      localStorage.setItem(key, JSON.stringify(value));
      return true;
    } catch (e) {
      console.warn('storage write failed', key, e);
      return false;
    }
  }

  class Storage {
    getStreak() {
      return readJSON(KEY_STREAK, {
        current_days: 0,
        longest_days: 0,
        last_practice_date: null,
        total_attempts: 0,
        total_passes: 0
      });
    }

    incrementStreak(passed) {
      const s = this.getStreak();
      const today = todayLocal();
      if (s.last_practice_date === today) {
        // already practiced today; no streak increment
      } else if (s.last_practice_date && dayDiff(today, s.last_practice_date) === 1) {
        s.current_days += 1;
      } else {
        s.current_days = 1;
      }
      s.last_practice_date = today;
      s.longest_days = Math.max(s.longest_days, s.current_days);
      s.total_attempts += 1;
      if (passed) s.total_passes += 1;
      writeJSON(KEY_STREAK, s);
      return s;
    }

    resetStreak() {
      writeJSON(KEY_STREAK, {
        current_days: 0,
        longest_days: 0,
        last_practice_date: null,
        total_attempts: 0,
        total_passes: 0
      });
    }

    getAttempt(phraseId) {
      const h = readJSON(KEY_HISTORY, { attempts: [], per_phrase: {} });
      return h.per_phrase[phraseId] || null;
    }

    saveAttempt({ phraseId, score, soundedLike, ts }) {
      const h = readJSON(KEY_HISTORY, { attempts: [], per_phrase: {} });
      const attempt = {
        phrase_id: phraseId,
        score: score,
        sounded_like: soundedLike,
        timestamp: ts || new Date().toISOString()
      };
      h.attempts.push(attempt);
      if (h.attempts.length > HISTORY_CAP) {
        h.attempts.splice(0, h.attempts.length - HISTORY_CAP);
      }
      const stats = h.per_phrase[phraseId] || {
        best_score: 0,
        recent_scores: [],
        attempt_count: 0,
        mastered: false
      };
      stats.attempt_count += 1;
      stats.recent_scores.push(score);
      if (stats.recent_scores.length > 5) stats.recent_scores.shift();
      stats.best_score = Math.max(stats.best_score, score);
      stats.mastered = stats.best_score >= 90 && stats.attempt_count >= 3;
      h.per_phrase[phraseId] = stats;
      writeJSON(KEY_HISTORY, h);
      return attempt;
    }

    getHistory(limit) {
      const h = readJSON(KEY_HISTORY, { attempts: [], per_phrase: {} });
      const all = h.attempts;
      if (limit && limit > 0) return all.slice(-limit);
      return all;
    }

    getSettings() {
      return readJSON(KEY_SETTINGS, {
        streakPassThreshold: 70,
        lang: 'es'
      });
    }

    saveSettings(s) {
      const cur = this.getSettings();
      writeJSON(KEY_SETTINGS, Object.assign({}, cur, s));
    }
  }

  window.Storage = Storage;
})();
