/*
 * Retro/8-bit UI sound engine built entirely on the Web Audio API oscillator -
 * no audio files to ship, so the app keeps working fully offline. Square/
 * sawtooth waves are the classic chiptune button-blip timbre.
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

  // Filtered white noise burst - a soft "whoosh"/rustle rather than a tone,
  // used for the forest theme's screen-transition sound.
  function noiseBurst({ duration = 0.35, filterFreq = 1200, q = 0.7, gain = 0.06, delay = 0 }) {
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
    filter.type = "bandpass";
    filter.frequency.value = filterFreq;
    filter.Q.value = q;
    const amp = c.createGain();
    amp.gain.setValueAtTime(0, t0);
    amp.gain.linearRampToValueAtTime(gain, t0 + duration * 0.25);
    amp.gain.exponentialRampToValueAtTime(0.0001, t0 + duration);

    noise.connect(filter).connect(amp).connect(c.destination);
    noise.start(t0);
    noise.stop(t0 + duration + 0.02);
  }

  return {
    click() { tone({ freq: 740, duration: 0.06, type: "square", gain: 0.045, glideTo: 520 }); },
    toggle() { tone({ freq: 480, duration: 0.05, type: "square", gain: 0.04, glideTo: 720 }); },
    success() {
      tone({ freq: 523, duration: 0.09, type: "square", gain: 0.05 });
      tone({ freq: 659, duration: 0.09, type: "square", gain: 0.05, delay: 0.09 });
      tone({ freq: 784, duration: 0.16, type: "square", gain: 0.05, delay: 0.18 });
    },
    error() {
      tone({ freq: 220, duration: 0.12, type: "sawtooth", gain: 0.05 });
      tone({ freq: 160, duration: 0.2, type: "sawtooth", gain: 0.05, delay: 0.1 });
    },
    // Themed accent played on every screen transition, on top of the click blip.
    transition(style) {
      if (style === "forest") {
        noiseBurst({ duration: 0.4, filterFreq: 1400, gain: 0.045 });
      } else if (style === "cyberpunk") {
        tone({ freq: 1500, duration: 0.05, type: "square", gain: 0.025, glideTo: 260 });
      } else if (style === "arcade") {
        tone({ freq: 660, duration: 0.05, type: "square", gain: 0.035 });
        tone({ freq: 990, duration: 0.07, type: "square", gain: 0.035, delay: 0.05 });
      }
      // minimal: intentionally silent - the click blip alone is enough there
    },
    setMuted(value) {
      muted = value;
      localStorage.setItem("newtik.muted", muted ? "1" : "0");
    },
    isMuted() { return muted; },
  };
})();
