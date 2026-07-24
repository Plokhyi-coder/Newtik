/*
 * Ambient background particles per visual style - falling leaves (forest),
 * digital rain (cyberpunk), rising embers (volcano). The layer sits behind
 * #app (z-index 0) so particles only ever show in the empty margin around
 * the card, never over readable text or controls.
 */
const Particles = (() => {
  let layer = null;
  let intervalId = null;

  function ensureLayer() {
    if (!layer) {
      layer = document.createElement("div");
      layer.id = "particle-layer";
      layer.setAttribute("aria-hidden", "true");
      document.body.appendChild(layer);
    }
    return layer;
  }

  function clear() {
    if (intervalId) clearInterval(intervalId);
    intervalId = null;
    if (layer) layer.innerHTML = "";
  }

  const LEAVES = ["/assets/leaf-green.svg", "/assets/leaf-gold.svg", "/assets/leaf-red.svg"];
  const EMBER = "/assets/ember.svg";
  const MATRIX_CHARS = "アイウエオカキクケコサシスセソタチツテト0123456789";
  const MATRIX_TOKENS = ["ERROR", "NULL", "0x1F", "404", "SEGV", "0xFF", "WARN"];

  function spawnLeaf() {
    const el = document.createElement("img");
    el.src = LEAVES[Math.floor(Math.random() * LEAVES.length)];
    el.alt = "";
    el.className = "particle particle-leaf";
    const size = 16 + Math.random() * 14;
    el.style.width = `${size}px`;
    el.style.left = `${Math.random() * 100}vw`;
    el.style.setProperty("--fall-duration", `${10 + Math.random() * 8}s`);
    el.style.setProperty("--drift", `${(Math.random() * 2 - 1) * 130}px`);
    el.style.setProperty("--spin", `${(Math.random() > 0.5 ? 1 : -1) * (200 + Math.random() * 360)}deg`);
    ensureLayer().appendChild(el);
    el.addEventListener("animationend", () => el.remove());
  }

  function spawnEmber() {
    const el = document.createElement("img");
    el.src = EMBER;
    el.alt = "";
    el.className = "particle particle-spark";
    const size = 12 + Math.random() * 16;
    el.style.width = `${size}px`;
    el.style.left = `${Math.random() * 100}vw`;
    el.style.setProperty("--fall-duration", `${3.5 + Math.random() * 3}s`);
    el.style.setProperty("--drift", `${(Math.random() * 2 - 1) * 90}px`);
    ensureLayer().appendChild(el);
    el.addEventListener("animationend", () => el.remove());
  }

  function startMatrixRain() {
    const target = ensureLayer();
    const columns = Math.floor(window.innerWidth / 24);
    for (let i = 0; i < columns; i++) {
      if (Math.random() > 0.5) continue; // sparse-ish - a visible drizzle, not a wall of text
      const col = document.createElement("div");
      col.className = "particle-matrix-col";
      col.style.left = `${i * 24}px`;
      col.style.animationDuration = `${5 + Math.random() * 6}s`;
      col.style.animationDelay = `${-Math.random() * 6}s`;
      const lines = [];
      const tokenLine = Math.floor(Math.random() * 16);
      for (let j = 0; j < 16; j++) {
        if (j === tokenLine && Math.random() > 0.4) {
          lines.push(MATRIX_TOKENS[Math.floor(Math.random() * MATRIX_TOKENS.length)]);
        } else {
          lines.push(MATRIX_CHARS[Math.floor(Math.random() * MATRIX_CHARS.length)]);
        }
      }
      // Bright leading glyph reads as the "head" of the falling stream, the
      // rest trails off dimmer via the base class color/opacity. No line
      // breaks - vertical-rl already stacks characters top-to-bottom on its own.
      col.innerHTML = `<span>${lines[0]}</span>${lines.slice(1).join("")}`;
      target.appendChild(col);
    }
  }

  function setStyle(style) {
    clear();
    if (style === "forest") {
      spawnLeaf();
      intervalId = setInterval(spawnLeaf, 900);
    } else if (style === "volcano") {
      spawnEmber();
      intervalId = setInterval(spawnEmber, 280);
    } else if (style === "cyberpunk") {
      startMatrixRain();
    }
    // minimal: no particles - the point of that style is calm emptiness
  }

  return { setStyle };
})();
