// app.js — entry point. Wires the UI loop together.

(function () {
  'use strict';

  const FALLBACK_PHRASES = [
    { id: 'es-fallback-1', text: 'buenas tardes', ipa: 'bwenas taɾðes',
      respelling: 'BWAY-nahs TAR-dehs', english_gloss: 'good afternoon', difficulty: 2 },
    { id: 'es-fallback-2', text: 'me llamo Ana',  ipa: 'me ʝamo ana',
      respelling: 'meh YAH-moh AH-nah', english_gloss: 'my name is Ana', difficulty: 1 },
    { id: 'es-fallback-3', text: '¿cómo estás?',  ipa: 'komo estas',
      respelling: 'KOH-moh ehs-TAHS', english_gloss: 'how are you?', difficulty: 1 }
  ];

  const state = {
    corpus: null,
    respelling: null,
    similarity: null,
    phrase: null,
    storage: new window.Storage(),
    audio: new window.AudioCapture(),
    score: new window.ScoreView(),
    lastBlob: null,
    isRecording: false
  };

  const els = {};

  function $(id) { return document.getElementById(id); }

  async function fetchJson(url) {
    try {
      const res = await fetch(url, { cache: 'no-cache' });
      if (!res.ok) return null;
      return await res.json();
    } catch (e) {
      return null;
    }
  }

  async function loadData() {
    const [corpus, respelling, similarity] = await Promise.all([
      fetchJson('/data/corpus_es.json'),
      fetchJson('/data/respelling_es.json'),
      fetchJson('/data/similarity_es.json')
    ]);
    // corpus may be either {phrases:[...]} or a flat array (current server shape).
    // Phrase objects may use english_translation OR english_gloss. Normalize.
    let phrases = null;
    if (Array.isArray(corpus)) {
      phrases = corpus;
    } else if (corpus && Array.isArray(corpus.phrases)) {
      phrases = corpus.phrases;
    }
    if (phrases && phrases.length) {
      phrases = phrases.map((p) => Object.assign({}, p, {
        english_gloss: p.english_gloss || p.english_translation || ''
      }));
      state.corpus = { phrases: phrases, version: (corpus && corpus.version) || 'server' };
    } else {
      state.corpus = { phrases: FALLBACK_PHRASES, version: 'fallback' };
    }
    state.respelling = respelling || { mappings: [] };
    state.similarity = similarity || { pairs: [] };
  }

  function populatePicker() {
    els.phraseSelect.innerHTML = '';
    state.corpus.phrases.forEach((p, i) => {
      const opt = document.createElement('option');
      opt.value = String(i);
      opt.textContent = p.text + (p.english_gloss ? ` — ${p.english_gloss}` : '');
      els.phraseSelect.appendChild(opt);
    });
  }

  function renderPhrase(p) {
    state.phrase = p;
    els.phraseRespelling.textContent = p.respelling || '—';
    els.phraseText.textContent = p.text || '';
    els.phraseIpa.textContent = p.ipa ? `/${p.ipa}/` : '';
    els.phraseGloss.textContent = p.english_gloss || '';
    state.score.clear();
    els.playbackControls.hidden = true;
    els.statusMessage.textContent = '';
  }

  function pickRandomPhrase() {
    const phrases = state.corpus.phrases;
    if (!phrases.length) return;
    const idx = Math.floor(Math.random() * phrases.length);
    els.phraseSelect.value = String(idx);
    renderPhrase(phrases[idx]);
  }

  function readAloud() {
    if (!state.phrase || !window.speechSynthesis) return;
    try {
      window.speechSynthesis.cancel();
      const u = new SpeechSynthesisUtterance(state.phrase.text);
      u.lang = 'es-ES';
      u.rate = 0.9;
      const voices = window.speechSynthesis.getVoices();
      const esVoice = voices.find((v) => /^es(-|_)/i.test(v.lang));
      if (esVoice) u.voice = esVoice;
      window.speechSynthesis.speak(u);
    } catch (e) {
      console.warn('TTS failed', e);
    }
  }

  async function startRecording() {
    try {
      els.statusMessage.textContent = '';
      await state.audio.start();
      state.isRecording = true;
      els.recordButton.setAttribute('aria-pressed', 'true');
      els.recordButton.querySelector('.mic-label').textContent = 'tap to stop';
      els.recordingIndicator.hidden = false;
    } catch (e) {
      els.statusMessage.textContent = e.message || 'Could not start recording.';
      console.error(e);
    }
  }

  async function stopRecording() {
    state.isRecording = false;
    els.recordButton.setAttribute('aria-pressed', 'false');
    els.recordButton.querySelector('.mic-label').textContent = 'tap to record';
    els.recordingIndicator.hidden = true;
    let blob;
    try {
      blob = await state.audio.stop();
    } catch (e) {
      els.statusMessage.textContent = 'Recording failed: ' + (e.message || e);
      return;
    }
    state.lastBlob = blob;
    els.playbackControls.hidden = false;
    els.statusMessage.textContent = 'scoring…';
    try {
      const result = await window.parrotApi.alignAttempt({
        audioBlob: blob,
        expectedText: state.phrase.text,
        expectedIpa: state.phrase.ipa,
        lang: 'es'
      });
      els.statusMessage.textContent = '';
      handleScore(result);
    } catch (e) {
      els.statusMessage.textContent = 'Scoring failed: ' + (e.message || e);
      console.error(e);
    }
  }

  function handleScore(result) {
    const settings = state.storage.getSettings();
    const passThreshold = settings.streakPassThreshold || 70;
    const passed = result.score >= passThreshold;
    state.storage.saveAttempt({
      phraseId: state.phrase.id,
      score: result.score,
      soundedLike: result.sounded_like_respelling,
      ts: new Date().toISOString()
    });
    state.storage.incrementStreak(passed);
    state.score.render({
      score: result.score,
      soundedLike: result.sounded_like_respelling,
      sttTranscript: result.stt_transcript,
      degraded: result.degraded,
      expectedRespelling: result.expected_respelling || state.phrase.respelling,
      mistakes: result.mistakes || []
    });
    refreshStats();
  }

  function refreshStats() {
    const s = state.storage.getStreak();
    els.streakCounter.textContent = String(s.current_days);
    els.attemptCounter.textContent = String(s.total_attempts);
  }

  function bind() {
    els.phraseSelect = $('phrase-select');
    els.phraseShuffle = $('phrase-shuffle');
    els.phraseText = $('phrase-text');
    els.phraseIpa = $('phrase-ipa');
    els.phraseRespelling = $('phrase-respelling');
    els.phraseGloss = $('phrase-gloss');
    els.readAloud = $('read-aloud');
    els.recordButton = $('record-button');
    els.recordingIndicator = $('recording-indicator');
    els.statusMessage = $('status-message');
    els.playbackControls = $('playback-controls');
    els.playbackButton = $('playback-button');
    els.retryButton = $('retry-button');
    els.streakCounter = $('streak-counter');
    els.attemptCounter = $('attempt-counter');

    els.phraseSelect.addEventListener('change', () => {
      const idx = parseInt(els.phraseSelect.value, 10);
      if (!isNaN(idx) && state.corpus.phrases[idx]) {
        renderPhrase(state.corpus.phrases[idx]);
      }
    });

    els.phraseShuffle.addEventListener('click', pickRandomPhrase);
    els.readAloud.addEventListener('click', readAloud);

    els.recordButton.addEventListener('click', () => {
      if (state.isRecording) stopRecording();
      else startRecording();
    });

    els.playbackButton.addEventListener('click', () => {
      if (state.lastBlob) state.audio.play(state.lastBlob).catch((e) => {
        els.statusMessage.textContent = 'Playback failed: ' + (e.message || e);
      });
    });

    els.retryButton.addEventListener('click', () => {
      state.score.clear();
      els.playbackControls.hidden = true;
      els.statusMessage.textContent = '';
    });
  }

  document.addEventListener('DOMContentLoaded', async () => {
    bind();
    els.statusMessage.textContent = 'loading sample phrases…';
    await loadData();
    populatePicker();
    pickRandomPhrase();
    refreshStats();
    els.statusMessage.textContent = '';
    // prime voices for some browsers
    if (window.speechSynthesis) window.speechSynthesis.getVoices();
  });
})();
