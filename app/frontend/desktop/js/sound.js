/*
 * UI sound engine built entirely on the Web Audio API - no audio files to
 * ship, so the app keeps working fully offline. Each non-minimal style has
 * 3 selectable button-click "packs" with a distinct, thematic timbre (wood
 * knock / rustle / chime for forest, digital blip / laser / glitch for
 * cyberpunk, rumble / crackle / rock-clack for volcano) - picked in the
 * Тема panel, remembered per style. Minimal has no sound pack choice, just
 * a neutral default click.
 */
const Sound = (() => {
  let ctx = null;
  let muted = localStorage.getItem("newtik.muted") === "1";

  function ensureContext() {
    if (!ctx) ctx = new (window.AudioContext || window.webkitAudioContext)();
    if (ctx.state === "suspended") ctx.resume();
    return ctx;
  }

  function tone({ freq, duration = 0.08, type = "square", gain = 0.05, glideTo = null, delay = 0 }) {
    if (muted) return;
    const c = ensureContext();
    const t0 = c.currentTime + delay;
    const osc = c.createOscillator();
    const amp = c.createGain();
    osc.type = type;
    osc.frequency.setValueAtTime(freq, t0);
    if (glideTo) osc.frequency.exponentialRampToValueAtTime(glideTo, t0 + duration);
    amp.gain.setValueAtTime(gain, t0);
    amp.gain.exponentialRampToValueAtTime(0.0001, t0 + duration);
    osc.connect(amp).connect(c.destination);
    osc.start(t0);
    osc.stop(t0 + duration + 0.02);
  }

  // Filtered noise burst - a soft "whoosh"/rustle/crackle rather than a tone.
  function noiseBurst({ duration = 0.35, filterFreq = 1200, q = 0.7, type = "bandpass", gain = 0.06, delay = 0 }) {
    if (muted) return;
    const c = ensureContext();
    const t0 = c.currentTime + delay;
    const bufferSize = Math.floor(c.sampleRate * duration);
    const buffer = c.createBuffer(1, bufferSize, c.sampleRate);
    const data = buffer.getChannelData(0);
    for (let i = 0; i < bufferSize; i++) data[i] = Math.random() * 2 - 1;

    const noise = c.createBufferSource();
    noise.buffer = buffer;
    const filter = c.createBiquadFilter();
    filter.type = type;
    filter.frequency.value = filterFreq;
    filter.Q.value = q;
    const amp = c.createGain();
    amp.gain.setValueAtTime(0, t0);
    amp.gain.linearRampToValueAtTime(gain, t0 + duration * 0.2);
    amp.gain.exponentialRampToValueAtTime(0.0001, t0 + duration);

    noise.connect(filter).connect(amp).connect(c.destination);
    noise.start(t0);
    noise.stop(t0 + duration + 0.02);
  }

  // --- Themed click packs: style -> pack id -> recipe ---
  const CLICK_PACKS = {
    forest: {
      "0": () => { // wood knock
        tone({ freq: 200, duration: 0.05, type: "triangle", gain: 0.06 });
        tone({ freq: 140, duration: 0.09, type: "triangle", gain: 0.05, delay: 0.03 });
      },
      "1": () => { // leaf rustle
        noiseBurst({ duration: 0.22, filterFreq: 2200, q: 0.9, gain: 0.05 });
      },
      "2": () => { // wooden chime
        tone({ freq: 523, duration: 0.18, type: "triangle", gain: 0.045 });
        tone({ freq: 659, duration: 0.22, type: "triangle", gain: 0.035, delay: 0.02 });
      },
    },
    cyberpunk: {
      "0": () => { // digital blip (the original default click)
        tone({ freq: 740, duration: 0.06, type: "square", gain: 0.045, glideTo: 520 });
      },
      "1": () => { // laser pulse
        tone({ freq: 1800, duration: 0.1, type: "sawtooth", gain: 0.04, glideTo: 180 });
      },
      "2": () => { // glitch stutter
        tone({ freq: 900, duration: 0.03, type: "square", gain: 0.045 });
        tone({ freq: 700, duration: 0.03, type: "square", gain: 0.04, delay: 0.045 });
        tone({ freq: 1000, duration: 0.02, type: "square", gain: 0.035, delay: 0.08 });
      },
    },
    volcano: {
      "0": () => { // low rumble
        tone({ freq: 90, duration: 0.16, type: "sine", gain: 0.07 });
        tone({ freq: 70, duration: 0.2, type: "sine", gain: 0.05, delay: 0.04 });
      },
      "1": () => { // ember crackle
        noiseBurst({ duration: 0.12, filterFreq: 3200, q: 1.2, type: "highpass", gain: 0.05 });
        noiseBurst({ duration: 0.08, filterFreq: 4000, q: 1.5, type: "highpass", gain: 0.04, delay: 0.05 });
      },
      "2": () => { // rock clack
        tone({ freq: 260, duration: 0.04, type: "square", gain: 0.055 });
        noiseBurst({ duration: 0.06, filterFreq: 1800, q: 1, gain: 0.04 });
      },
    },
  };

  function currentStyle() {
    return document.documentElement.getAttribute("data-style") || "minimal";
  }

  return {
    click(styleOverride, packOverride) {
      const style = styleOverride || currentStyle();
      const pack = CLICK_PACKS[style];
      if (!pack) {
        tone({ freq: 740, duration: 0.06, type: "square", gain: 0.045, glideTo: 520 });
        return;
      }
      const packId = packOverride ?? ThemeManager.currentSoundPack(style);
      (pack[packId] || pack["0"])();
    },
    success() {
      tone({ freq: 523, duration: 0.09, type: "square", gain: 0.05 });
      tone({ freq: 659, duration: 0.09, type: "square", gain: 0.05, delay: 0.09 });
      tone({ freq: 784, duration: 0.16, type: "square", gain: 0.05, delay: 0.18 });
    },
    error() {
      tone({ freq: 220, duration: 0.12, type: "sawtooth", gain: 0.05 });
      tone({ freq: 160, duration: 0.2, type: "sawtooth", gain: 0.05, delay: 0.1 });
    },
    // Themed accent played on every screen transition, on top of the click sound.
    transition(style) {
      if (style === "forest") {
        noiseBurst({ duration: 0.4, filterFreq: 1400, gain: 0.045 });
      } else if (style === "cyberpunk") {
        tone({ freq: 1500, duration: 0.05, type: "square", gain: 0.025, glideTo: 260 });
      } else if (style === "volcano") {
        tone({ freq: 100, duration: 0.18, type: "sine", gain: 0.04 });
      }
      // minimal: intentionally silent - the click sound alone is enough there
    },
    setMuted(value) {
      muted = value;
      localStorage.setItem("newtik.muted", muted ? "1" : "0");
    },
    isMuted() { return muted; },
  };
})();
