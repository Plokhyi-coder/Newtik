const state = {
  url: "",
  metadata: null,
  rangeStart: null,
  rangeEnd: null,
  clipLength: 30,
  smartCut: false,
  quality: "medium",
  variationsCount: 0,
  overlay: { text: "", position_x: "center", position_y: "center", start_sec: 0, duration_sec: 5 },
  jobId: null,
};

// Progress and results live in "Задачи"/"Галерея" now, so the wizard itself
// ends at screen 3 - starting a job hands it to the background queue and
// resets straight back to screen 1 for the next video.
const screens = ["screen-1", "screen-2", "screen-3"];
let currentScreenIndex = 0;

function showScreen(id) {
  const newIndex = screens.indexOf(id);
  const direction = newIndex >= currentScreenIndex ? "enter-forward" : "enter-back";
  currentScreenIndex = newIndex;
  Sound.transition(document.documentElement.getAttribute("data-style"));

  for (const s of screens) {
    const el = document.getElementById(s);
    if (s === id) {
      el.classList.remove("hidden", "enter-forward", "enter-back");
      void el.offsetWidth; // restart the CSS animation even if this screen was shown before
      el.classList.add(direction);
    } else {
      el.classList.add("hidden");
    }
  }
  document.querySelectorAll(".wizard-steps .dot").forEach((dot, i) => {
    dot.classList.toggle("active", i === newIndex);
    dot.classList.toggle("done", i < newIndex);
  });
}

function showBanner(message, { icon, success }) {
  const banner = document.getElementById("error-banner");
  banner.innerHTML = `<span class="icon">${icon}</span><span>${message}</span>`;
  banner.classList.toggle("is-success", !!success);
  banner.classList.remove("hidden");
  clearTimeout(showBanner._timer);
  showBanner._timer = setTimeout(() => banner.classList.add("hidden"), 6000);
}

function showError(message) {
  showBanner(message, { icon: "⚠", success: false });
  Sound.error();
}

function showSuccess(message) {
  showBanner(message, { icon: "✓", success: true });
  Sound.success();
}

// ---- Retro click sound + ripple burst on every interactive element ----
function spawnRipple(target, clientX, clientY) {
  const rect = target.getBoundingClientRect();
  const size = Math.max(rect.width, rect.height);
  const ripple = document.createElement("span");
  ripple.className = "ripple";
  ripple.style.width = ripple.style.height = `${size}px`;
  ripple.style.left = `${clientX - rect.left - size / 2}px`;
  ripple.style.top = `${clientY - rect.top - size / 2}px`;
  target.appendChild(ripple);
  ripple.addEventListener("animationend", () => ripple.remove());
}

document.addEventListener("click", (e) => {
  // .sound-pack-btn is excluded here - its own handler in theme.js already
  // plays the specific pack being previewed, so this would double up the sound.
  const interactive = e.target.closest(
    ".btn, .icon-btn, .position-grid .cell, .swatch, .shade-btn, .style-card, .quality-btn, .nav-item"
  );
  if (!interactive) return;
  Sound.click();
  if (interactive.classList.contains("btn")) spawnRipple(interactive, e.clientX, e.clientY);
});

function parseTimecode(value) {
  if (!value || !value.trim()) return null;
  const parts = value.trim().split(":").map(Number);
  if (parts.some((p) => Number.isNaN(p))) return null;
  let sec = 0;
  for (const p of parts) sec = sec * 60 + p;
  return sec;
}

function formatDuration(sec) {
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = Math.floor(sec % 60);
  return [h, m, s].map((v) => String(v).padStart(2, "0")).join(":");
}

// ---- Screen 1: analyze ----
document.getElementById("btn-analyze").addEventListener("click", async () => {
  const url = document.getElementById("url-input").value.trim();
  if (!url) return showError("Введите ссылку на видео.");

  const btn = document.getElementById("btn-analyze");
  btn.disabled = true;
  btn.textContent = "Анализ...";
  try {
    const res = await fetch("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Не удалось проанализировать видео");
    }
    const metadata = await res.json();
    state.url = url;
    state.metadata = metadata;

    document.getElementById("video-preview").style.display = "flex";
    document.getElementById("preview-thumb").src = metadata.thumbnail_url || "";
    document.getElementById("preview-title").textContent = metadata.title;
    document.getElementById("preview-duration").textContent =
      "Длительность: " + formatDuration(metadata.duration_sec);
    document.getElementById("range-row").style.display = "block";
    RangeSlider.init(metadata.duration_sec);
  } catch (e) {
    showError(e.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "Анализировать";
  }
});

document.getElementById("btn-to-screen-2").addEventListener("click", () => {
  if (!state.metadata) return showError("Сначала проанализируйте видео.");

  const { start, end } = RangeSlider.getRange();
  if (end <= start) return showError("«По» должно быть больше «С».");

  state.rangeStart = start;
  state.rangeEnd = end;
  showScreen("screen-2");
});

// ---- Screen 2 ----
document.getElementById("smart-cut-checkbox").addEventListener("change", (e) => {
  state.smartCut = e.target.checked;
});

document.querySelectorAll("#quality-row .quality-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll("#quality-row .quality-btn").forEach((b) => b.classList.remove("selected"));
    btn.classList.add("selected");
    state.quality = btn.dataset.quality;
  });
});

document.querySelector("#screen-2 [data-back]").addEventListener("click", () => showScreen("screen-1"));
document.querySelector("#screen-2 [data-next]").addEventListener("click", () => {
  const len = parseInt(document.getElementById("clip-length").value, 10);
  if (!len || len < 5) return showError("Укажите длину клипа в секундах.");
  state.clipLength = len;

  const variations = parseInt(document.getElementById("variations-count").value, 10) || 0;
  if (variations < 0 || variations > 5) return showError("Количество вариантов - от 0 до 5.");
  state.variationsCount = variations;

  showScreen("screen-3");
});

// ---- Screen 3: text overlay + position grid ----
document.querySelectorAll("#position-grid .cell").forEach((cell) => {
  cell.addEventListener("click", () => {
    document.querySelectorAll("#position-grid .cell").forEach((c) => c.classList.remove("selected"));
    cell.classList.add("selected");
    state.overlay.position_x = cell.dataset.x;
    state.overlay.position_y = cell.dataset.y;
  });
});

document.querySelector("#screen-3 [data-back]").addEventListener("click", () => showScreen("screen-2"));

document.getElementById("btn-start").addEventListener("click", async () => {
  state.overlay.text = document.getElementById("overlay-text").value;
  state.overlay.start_sec = parseFloat(document.getElementById("overlay-start").value) || 0;
  state.overlay.duration_sec = parseFloat(document.getElementById("overlay-duration").value) || 0;

  const payload = {
    source_url: state.url,
    time_range: { start_sec: state.rangeStart, end_sec: state.rangeEnd },
    clip_length_sec: state.clipLength,
    smart_cut_enabled: state.smartCut,
    variations_count: state.variationsCount,
    quality: state.quality,
    text_overlay: state.overlay,
  };

  const btn = document.getElementById("btn-start");
  btn.disabled = true;
  try {
    const res = await fetch("/api/jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Не удалось запустить обработку");
    }
    const data = await res.json();
    state.jobId = data.job_id;
    // Hand the job off to the background queue and reset the wizard right
    // away instead of parking the user on a progress screen - processing
    // keeps running server-side and is tracked in "Задачи", so another
    // video can be queued immediately.
    resetWizard();
    showSuccess("Обработка запущена — следите за ней во вкладке «Задачи».");
  } catch (e) {
    showError(e.message);
  } finally {
    btn.disabled = false;
  }
});

function resetWizard() {
  state.url = "";
  state.metadata = null;
  state.rangeStart = null;
  state.rangeEnd = null;
  state.overlay = { text: "", position_x: "center", position_y: "center", start_sec: 0, duration_sec: 5 };

  document.getElementById("url-input").value = "";
  document.getElementById("overlay-text").value = "";
  document.getElementById("video-preview").style.display = "none";
  document.getElementById("range-row").style.display = "none";

  showScreen("screen-1");
}
