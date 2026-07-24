/*
 * Appearance settings: visual style (4), an accent color/shade layer that
 * depends on the style, and per-style sound packs. Persisted to localStorage,
 * applied as data-attributes on <html> so css/style.css selectors do the rest.
 *
 * Minimal is the only style with a free choice of 6 accent colors (data-theme-color).
 * The other 3 styles each have exactly 3 fixed shades instead (data-shade="1|2|3"),
 * remembered per-style so switching styles and back restores your last pick.
 */
const THEME_COLORS = [
  { id: "violet", label: "Фиолетовый", swatch: "#8b6bff" },
  { id: "coral", label: "Коралл", swatch: "#ff6b5c" },
  { id: "mint", label: "Мята", swatch: "#14e0c4" },
  { id: "amber", label: "Янтарь", swatch: "#ffb020" },
  { id: "ocean", label: "Океан", swatch: "#3aa0ff" },
  { id: "magenta", label: "Маджента", swatch: "#ff3ec8" },
];

const VISUAL_STYLES = [
  { id: "cyberpunk", label: "Киберпанк", icon: "/assets/icon-cyberpunk.svg" },
  { id: "forest", label: "Лесной", icon: "/assets/icon-forest.svg" },
  { id: "minimal", label: "Минимал", icon: "/assets/icon-minimal.svg" },
  { id: "volcano", label: "Вулканический", icon: "/assets/icon-volcano.svg" },
];

const SHADE_PALETTES = {
  forest: [
    { id: "1", label: "Тёмный", swatch: "#2f6b3a" },
    { id: "2", label: "Средний", swatch: "#4f9e52" },
    { id: "3", label: "Яркий", swatch: "#7fe07a" },
  ],
  cyberpunk: [
    { id: "1", label: "Тёмный", swatch: "#5b3fae" },
    { id: "2", label: "Средний", swatch: "#8b5cf6" },
    { id: "3", label: "Яркий", swatch: "#c084fc" },
  ],
  volcano: [
    { id: "1", label: "Тёмный", swatch: "#8c1f1f" },
    { id: "2", label: "Средний", swatch: "#e8452c" },
    { id: "3", label: "Оранжевый", swatch: "#ffa632" },
  ],
};

const SOUND_PACKS = {
  forest: [
    { id: "0", label: "Стук по дереву" },
    { id: "1", label: "Шелест листвы" },
    { id: "2", label: "Деревянный колокольчик" },
  ],
  cyberpunk: [
    { id: "0", label: "Цифровой сигнал" },
    { id: "1", label: "Лазерный импульс" },
    { id: "2", label: "Глитч-щелчок" },
  ],
  volcano: [
    { id: "0", label: "Глухой гул" },
    { id: "1", label: "Треск угля" },
    { id: "2", label: "Каменный удар" },
  ],
};

const ThemeManager = (() => {
  function apply(color, style, shade) {
    document.documentElement.setAttribute("data-theme-color", color);
    document.documentElement.setAttribute("data-style", style);
    document.documentElement.setAttribute("data-shade", shade);
  }

  function current() {
    // "arcade" was renamed to "volcano" in this redesign - migrate any value
    // a returning user already has saved instead of silently degrading to
    // the unstyled base look.
    let style = localStorage.getItem("newtik.style") || "minimal";
    if (style === "arcade") {
      style = "volcano";
      localStorage.setItem("newtik.style", style);
    }
    return {
      color: localStorage.getItem("newtik.themeColor") || "violet",
      style,
      shade: localStorage.getItem(`newtik.shade.${style}`) || "2",
    };
  }

  function load() {
    const c = current();
    apply(c.color, c.style, c.shade);
    return c;
  }

  function setColor(color) {
    localStorage.setItem("newtik.themeColor", color);
    const c = current();
    apply(color, c.style, c.shade);
  }

  function setStyle(style) {
    localStorage.setItem("newtik.style", style);
    const c = current();
    apply(c.color, style, c.shade);
  }

  function setShade(style, shade) {
    localStorage.setItem(`newtik.shade.${style}`, shade);
    const c = current();
    apply(c.color, style, shade);
  }

  function currentSoundPack(style) {
    return localStorage.getItem(`newtik.soundPack.${style}`) || "0";
  }

  function setSoundPack(style, packId) {
    localStorage.setItem(`newtik.soundPack.${style}`, packId);
  }

  return { load, current, setColor, setStyle, setShade, currentSoundPack, setSoundPack };
})();

// Applied immediately (script sits in <head>) so there is no flash of the
// default theme before the rest of the page parses.
ThemeManager.load();

function renderColorSection() {
  const swatchRow = document.getElementById("swatch-row");
  const shadeRow = document.getElementById("shade-row");
  const soundPackRow = document.getElementById("sound-pack-row");
  const soundPackLabel = document.getElementById("sound-pack-label");
  const colorLabel = document.getElementById("color-section-label");
  const state = ThemeManager.current();

  swatchRow.innerHTML = "";
  shadeRow.innerHTML = "";
  soundPackRow.innerHTML = "";

  if (state.style === "minimal") {
    colorLabel.textContent = "Цветовая тема";
    swatchRow.classList.remove("hidden-row");
    shadeRow.classList.remove("visible");
    soundPackRow.classList.add("hidden-row");
    soundPackLabel.classList.add("hidden-row");

    for (const theme of THEME_COLORS) {
      const el = document.createElement("button");
      el.type = "button";
      el.className = "swatch" + (theme.id === state.color ? " selected" : "");
      el.style.background = theme.swatch;
      el.title = theme.label;
      el.addEventListener("click", () => {
        ThemeManager.setColor(theme.id);
        renderColorSection();
      });
      swatchRow.appendChild(el);
    }
  } else {
    colorLabel.textContent = "Оттенок";
    swatchRow.classList.add("hidden-row");
    shadeRow.classList.add("visible");
    soundPackRow.classList.remove("hidden-row");
    soundPackLabel.classList.remove("hidden-row");

    for (const shade of SHADE_PALETTES[state.style]) {
      const el = document.createElement("button");
      el.type = "button";
      el.className = "shade-btn" + (shade.id === state.shade ? " selected" : "");
      el.style.background = shade.swatch;
      el.title = shade.label;
      el.addEventListener("click", () => {
        ThemeManager.setShade(state.style, shade.id);
        renderColorSection();
      });
      shadeRow.appendChild(el);
    }

    const currentPack = ThemeManager.currentSoundPack(state.style);
    for (const pack of SOUND_PACKS[state.style]) {
      const el = document.createElement("button");
      el.type = "button";
      el.className = "sound-pack-btn" + (pack.id === currentPack ? " selected" : "");
      el.innerHTML = `
        <span class="play-icon"><span class="icon-mask" style="mask-image:url(/assets/icon-upload-play.svg);-webkit-mask-image:url(/assets/icon-upload-play.svg)"></span></span>
        <span>${pack.label}</span>
      `;
      el.addEventListener("click", () => {
        ThemeManager.setSoundPack(state.style, pack.id);
        Sound.click(state.style, pack.id);
        soundPackRow.querySelectorAll(".sound-pack-btn").forEach((b) => b.classList.remove("selected"));
        el.classList.add("selected");
      });
      soundPackRow.appendChild(el);
    }
  }
}

function initSettingsPanel() {
  const styleGrid = document.getElementById("style-grid");
  const soundToggle = document.getElementById("sound-toggle");
  const current = ThemeManager.current();

  for (const style of VISUAL_STYLES) {
    const el = document.createElement("button");
    el.type = "button";
    el.className = "style-card" + (style.id === current.style ? " selected" : "");
    el.innerHTML = `<img class="icon" src="${style.icon}" alt="" width="20" height="20"><span>${style.label}</span>`;
    el.addEventListener("click", () => {
      ThemeManager.setStyle(style.id);
      Particles.setStyle(style.id);
      styleGrid.querySelectorAll(".style-card").forEach((s) => s.classList.remove("selected"));
      el.classList.add("selected");
      renderColorSection();
    });
    styleGrid.appendChild(el);
  }

  renderColorSection();

  soundToggle.checked = !Sound.isMuted();
  soundToggle.addEventListener("change", () => Sound.setMuted(!soundToggle.checked));

  const overlay = document.getElementById("settings-overlay");
  document.getElementById("btn-settings").addEventListener("click", () => overlay.classList.remove("hidden"));
  document.getElementById("btn-settings-close").addEventListener("click", () => overlay.classList.add("hidden"));
  overlay.addEventListener("click", (e) => { if (e.target === overlay) overlay.classList.add("hidden"); });

  Particles.setStyle(current.style);
}

document.addEventListener("DOMContentLoaded", initSettingsPanel);
