/*
 * Appearance settings: 6 color themes x 4 visual styles, persisted to
 * localStorage and applied as data-attributes on <html> so css/style.css
 * selectors (:root[data-theme-color=...], :root[data-style=...]) do the rest.
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
  { id: "cyberpunk", label: "Киберпанк", icon: "⚡" },
  { id: "forest", label: "Лесной", icon: "🌲" },
  { id: "minimal", label: "Минимал", icon: "◻" },
  { id: "arcade", label: "Ретро-аркада", icon: "▮" },
];

const ThemeManager = (() => {
  function apply(color, style) {
    document.documentElement.setAttribute("data-theme-color", color);
    document.documentElement.setAttribute("data-style", style);
  }

  function current() {
    return {
      color: localStorage.getItem("newtik.themeColor") || "violet",
      style: localStorage.getItem("newtik.style") || "minimal",
    };
  }

  function load() {
    const c = current();
    apply(c.color, c.style);
    return c;
  }

  function setColor(color) {
    localStorage.setItem("newtik.themeColor", color);
    apply(color, current().style);
  }

  function setStyle(style) {
    localStorage.setItem("newtik.style", style);
    apply(current().color, style);
  }

  return { load, current, setColor, setStyle };
})();

// Applied immediately (script sits in <head>) so there is no flash of the
// default theme before the rest of the page parses.
ThemeManager.load();

function initSettingsPanel() {
  const swatchRow = document.getElementById("swatch-row");
  const styleGrid = document.getElementById("style-grid");
  const soundToggle = document.getElementById("sound-toggle");
  const current = ThemeManager.current();

  for (const theme of THEME_COLORS) {
    const el = document.createElement("button");
    el.type = "button";
    el.className = "swatch" + (theme.id === current.color ? " selected" : "");
    el.style.background = theme.swatch;
    el.title = theme.label;
    el.addEventListener("click", () => {
      ThemeManager.setColor(theme.id);
      swatchRow.querySelectorAll(".swatch").forEach((s) => s.classList.remove("selected"));
      el.classList.add("selected");
    });
    swatchRow.appendChild(el);
  }

  for (const style of VISUAL_STYLES) {
    const el = document.createElement("button");
    el.type = "button";
    el.className = "style-card" + (style.id === current.style ? " selected" : "");
    el.innerHTML = `<span class="icon">${style.icon}</span><span>${style.label}</span>`;
    el.addEventListener("click", () => {
      ThemeManager.setStyle(style.id);
      styleGrid.querySelectorAll(".style-card").forEach((s) => s.classList.remove("selected"));
      el.classList.add("selected");
    });
    styleGrid.appendChild(el);
  }

  soundToggle.checked = !Sound.isMuted();
  soundToggle.addEventListener("change", () => Sound.setMuted(!soundToggle.checked));

  const overlay = document.getElementById("settings-overlay");
  document.getElementById("btn-settings").addEventListener("click", () => overlay.classList.remove("hidden"));
  document.getElementById("btn-settings-close").addEventListener("click", () => overlay.classList.add("hidden"));
  overlay.addEventListener("click", (e) => { if (e.target === overlay) overlay.classList.add("hidden"); });
}

document.addEventListener("DOMContentLoaded", initSettingsPanel);
