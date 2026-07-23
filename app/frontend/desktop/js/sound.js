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
    setMuted(value) {
      muted = value;
      localStorage.setItem("newtik.muted", muted ? "1" : "0");
    },
    isMuted() { return muted; },
  };
})();
