// api.js — talks to the phoneme alignment serverless function.
// M9: web bundle served from the same sprite as /align. Use a relative URL
// so there's no CORS at all and the demo works wherever it's hosted.

(function () {
  'use strict';

  // Empty string => relative URL => same-origin fetch. Single sprite, no CORS.
  const ALIGN_BASE_URL = '';
  const USE_MOCK = false; // flip to false once /align is live

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

  function blobToBase64(blob) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onloadend = () => {
        // result is "data:<mime>;base64,<payload>" — strip the prefix.
        const result = reader.result || '';
        const comma = result.indexOf(',');
        resolve(comma === -1 ? result : result.slice(comma + 1));
      };
      reader.onerror = () => reject(reader.error || new Error('blob->b64 failed'));
      reader.readAsDataURL(blob);
    });
  }

  async function alignAttempt({ audioBlob, expectedText, expectedIpa, lang }) {
    if (USE_MOCK) {
      await new Promise((r) => setTimeout(r, 500));
      return mockResult(expectedText);
    }
    if (!expectedIpa) {
      throw new Error('expected_ipa is required (api.js): pass phrase.ipa from the corpus');
    }
    // Server expects JSON {audio_b64, expected_text, expected_ipa, lang}.
    // We base64-encode the recorded blob and POST as JSON. No multipart.
    const audio_b64 = await blobToBase64(audioBlob);
    const body = {
      audio_b64: audio_b64,
      expected_text: expectedText || '',
      expected_ipa: expectedIpa,
      lang: lang || 'es'
    };
    const res = await fetch(ALIGN_BASE_URL + '/align', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(body)
    });
    if (!res.ok) {
      const text = await res.text().catch(() => '');
      throw new Error(`align failed: ${res.status} ${text}`);
    }
    return await res.json();
  }

  window.parrotApi = { alignAttempt: alignAttempt, ALIGN_BASE_URL: ALIGN_BASE_URL, USE_MOCK: USE_MOCK };
})();
