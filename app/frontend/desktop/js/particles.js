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
    const size = 6 + Math.random() * 10;
    el.style.width = `${size}px`;
    el.style.left = `${Math.random() * 100}vw`;
    el.style.setProperty("--fall-duration", `${4 + Math.random() * 4}s`);
    ensureLayer().appendChild(el);
    el.addEventListener("animationend", () => el.remove());
  }

  function startMatrixRain() {
    const target = ensureLayer();
    const columns = Math.floor(window.innerWidth / 24);
    for (let i = 0; i < columns; i++) {
      if (Math.random() > 0.3) continue; // sparse - a hint of rain, not a wall of text
      const col = document.createElement("div");
      col.className = "particle-matrix-col";
      col.style.left = `${i * 24}px`;
      col.style.animationDuration = `${5 + Math.random() * 6}s`;
      col.style.animationDelay = `${-Math.random() * 6}s`;
      let text = "";
      for (let j = 0; j < 16; j++) text += MATRIX_CHARS[Math.floor(Math.random() * MATRIX_CHARS.length)] + "\n";
      col.textContent = text;
      target.appendChild(col);
    }
  }

  function setStyle(style) {
    clear();
    if (style === "forest") {
      spawnLeaf();
      intervalId = setInterval(spawnLeaf, 900);
    } else if (style === "volcano") {
      intervalId = setInterval(spawnEmber, 400);
    } else if (style === "cyberpunk") {
      startMatrixRain();
    }
    // minimal: no particles - the point of that style is calm emptiness
  }

  return { setStyle };
})();
