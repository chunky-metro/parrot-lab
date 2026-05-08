// audio.js — MediaRecorder wrapper. Captures audio/webm;codecs=opus where supported.

(function () {
  'use strict';

  const PREFERRED_MIME = 'audio/webm;codecs=opus';

  function pickMime() {
    if (typeof MediaRecorder === 'undefined') return null;
    const candidates = [
      'audio/webm;codecs=opus',
      'audio/webm',
      'audio/mp4',
      'audio/ogg;codecs=opus'
    ];
    for (const m of candidates) {
      if (MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(m)) return m;
    }
    return ''; // browser default
  }

  class AudioCapture {
    constructor() {
      this.stream = null;
      this.recorder = null;
      this.chunks = [];
      this.mimeType = PREFERRED_MIME;
      this._audio = null; // playback element
    }

    async start() {
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        throw new Error('Microphone capture not supported in this browser.');
      }
      try {
        this.stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      } catch (e) {
        if (e && (e.name === 'NotAllowedError' || e.name === 'PermissionDeniedError')) {
          throw new Error('Microphone permission denied. Allow mic access and try again.');
        }
        throw new Error('Could not access microphone: ' + (e.message || e.name || 'unknown'));
      }
      const mime = pickMime();
      this.mimeType = mime || PREFERRED_MIME;
      const opts = mime ? { mimeType: mime } : undefined;
      this.recorder = new MediaRecorder(this.stream, opts);
      this.chunks = [];
      this.recorder.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) this.chunks.push(e.data);
      };
      this.recorder.start();
    }

    async stop() {
      if (!this.recorder) throw new Error('Recorder not started.');
      const recorder = this.recorder;
      const chunks = this.chunks;
      const mime = this.mimeType;
      const stream = this.stream;
      const blob = await new Promise((resolve, reject) => {
        recorder.onstop = () => {
          try {
            resolve(new Blob(chunks, { type: mime }));
          } catch (e) { reject(e); }
        };
        recorder.onerror = (ev) => reject(ev.error || new Error('recorder error'));
        try { recorder.stop(); } catch (e) { reject(e); }
      });
      // free mic
      if (stream) stream.getTracks().forEach((t) => t.stop());
      this.recorder = null;
      this.stream = null;
      return blob;
    }

    async play(blob) {
      if (!blob) return;
      if (this._audio) {
        try { this._audio.pause(); } catch (e) {}
      }
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      this._audio = audio;
      audio.onended = () => URL.revokeObjectURL(url);
      try {
        await audio.play();
      } catch (e) {
        URL.revokeObjectURL(url);
        throw e;
      }
    }
  }

  window.AudioCapture = AudioCapture;
})();
