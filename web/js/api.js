// api.js — talks to the phoneme alignment serverless function.
// Mocked by default until M3 ships the real endpoint.

(function () {
  'use strict';

  const ALIGN_BASE_URL = 'https://parrot-lab-align-brxpk.sprites.app';
  const USE_MOCK = true; // flip to false once /align is live

  function mockResult(expectedText) {
    // deterministic-ish mock keyed off phrase length so different phrases get different "scores"
    const len = (expectedText || '').length;
    const score = 60 + ((len * 7) % 35); // 60..94
    const expectedPhonemes = ['b', 'w', 'e', 'n', 'a', 's', ' ', 't', 'a', 'ɾ', 'ð', 'e', 's'];
    const actualPhonemes   = ['b', 'w', 'e', 'n', 'a', 's', ' ', 't', 'a', 'r', 'ð', 'e'];
    const alignment = expectedPhonemes.map((p, i) => ({
      expected: p,
      actual: actualPhonemes[i] != null ? actualPhonemes[i] : '',
      kind: actualPhonemes[i] === p ? 'match' : (actualPhonemes[i] == null ? 'del' : 'sub')
    }));
    return {
      score: score,
      expected_phonemes: expectedPhonemes.join(''),
      actual_phonemes: actualPhonemes.join(''),
      alignment: alignment,
      mistakes: [
        { at: 9, expected: 'ɾ', got: 'r', kind: 'sub',
          hint: "the tap 'ɾ' came out as English 'r' — try a quick tongue-flick instead of a curl" },
        { at: 12, expected: 's', got: '',  kind: 'del',
          hint: "missed the final 's' — say 'TAR-dehs', not 'TAR-deh'" }
      ],
      expected_respelling: 'BWAY-nahs TAR-dehs',
      sounded_like_respelling: 'BWAY-nahs TAR-deh',
      stt_transcript: expectedText || '',
      model_version: 'mock-v0',
      latency_ms: 500
    };
  }

  async function alignAttempt({ audioBlob, expectedText, lang }) {
    if (USE_MOCK) {
      await new Promise((r) => setTimeout(r, 500));
      return mockResult(expectedText);
    }
    const fd = new FormData();
    fd.append('audio', audioBlob, 'attempt.webm');
    fd.append('expected_text', expectedText || '');
    fd.append('lang', lang || 'es');
    const res = await fetch(ALIGN_BASE_URL + '/align', { method: 'POST', body: fd });
    if (!res.ok) {
      const text = await res.text().catch(() => '');
      throw new Error(`align failed: ${res.status} ${text}`);
    }
    return await res.json();
  }

  window.parrotApi = { alignAttempt: alignAttempt, ALIGN_BASE_URL: ALIGN_BASE_URL, USE_MOCK: USE_MOCK };
})();
