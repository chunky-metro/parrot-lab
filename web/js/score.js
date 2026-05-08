// score.js — renders score, sounded-like respelling, and mistakes into the DOM.

(function () {
  'use strict';

  function colorClass(score) {
    if (score >= 80) return 'score-high';
    if (score >= 60) return 'score-mid';
    return 'score-low';
  }

  class ScoreView {
    constructor() {
      this.scoreEl = document.getElementById('score-display');
      this.soundedEl = document.getElementById('sounded-like-display');
      this.mistakesEl = document.getElementById('mistakes-list');
      this.resultsEl = document.getElementById('results-section');
      this.progressWrap = document.getElementById('progress-bar');
      this.progressFill = this.progressWrap ? this.progressWrap.querySelector('.progress-fill') : null;
    }

    clear() {
      if (this.resultsEl) this.resultsEl.hidden = true;
      if (this.scoreEl) { this.scoreEl.textContent = ''; this.scoreEl.className = 'score-display'; }
      if (this.soundedEl) this.soundedEl.innerHTML = '';
      if (this.mistakesEl) this.mistakesEl.innerHTML = '';
      if (this.progressWrap) this.progressWrap.hidden = true;
    }

    render({ score, soundedLike, sttTranscript, degraded, expectedRespelling, mistakes, nextBadge }) {
      if (this.resultsEl) this.resultsEl.hidden = false;

      if (this.scoreEl) {
        this.scoreEl.className = 'score-display ' + colorClass(score);
        // tiny count-up animation
        const target = Math.round(score);
        let cur = 0;
        const step = Math.max(1, Math.ceil(target / 20));
        this.scoreEl.textContent = '0';
        const tick = () => {
          cur = Math.min(target, cur + step);
          this.scoreEl.textContent = String(cur);
          if (cur < target) requestAnimationFrame(tick);
        };
        requestAnimationFrame(tick);
      }

      if (this.soundedEl) {
        const expected = expectedRespelling ? `<div class="expected">target: <strong>${escape(expectedRespelling)}</strong></div>` : '';
        // "you said" prefers wizper STT (closest spanish); falls back to phonetic respelling if STT unavailable.
        let said = '';
        if (sttTranscript) {
          said = `<div class="said">you said: <strong>${escape(sttTranscript)}</strong></div>`;
        } else if (soundedLike) {
          const label = degraded ? 'you said (STT unavailable, phonetic)' : 'you said (phonetic)';
          said = `<div class="said">${label}: <strong>${escape(soundedLike)}</strong></div>`;
        }
        this.soundedEl.innerHTML = expected + said;
      }

      if (this.mistakesEl) {
        this.mistakesEl.innerHTML = '';
        (mistakes || []).forEach((m) => {
          const li = document.createElement('li');
          li.textContent = m.hint || `${m.kind}: ${m.expected || '∅'} → ${m.got || '∅'}`;
          this.mistakesEl.appendChild(li);
        });
      }

      if (this.progressWrap && this.progressFill) {
        if (nextBadge && typeof nextBadge.progress === 'number') {
          this.progressWrap.hidden = false;
          this.progressFill.style.width = Math.max(0, Math.min(100, nextBadge.progress * 100)) + '%';
        } else {
          this.progressWrap.hidden = true;
        }
      }
    }
  }

  function escape(s) {
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  window.ScoreView = ScoreView;
})();
