/*
 * "Парсинг канала" tab: takes a YouTube/TikTok channel URL, renders the
 * channel header + a grid of recent videos with views/likes/comments, and
 * an expandable "Общая информация" panel summarising the last day/week/month.
 */
const ChannelParser = (() => {
  function formatCount(n) {
    if (n === null || n === undefined) return "—";
    if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(n >= 10_000_000 ? 0 : 1)} млн`;
    if (n >= 1_000) return `${(n / 1_000).toFixed(n >= 10_000 ? 0 : 1)} тыс`;
    return String(n);
  }

  function formatDuration(sec) {
    if (!sec) return "";
    const m = Math.floor(sec / 60);
    const s = Math.floor(sec % 60);
    return `${m}:${String(s).padStart(2, "0")}`;
  }

  const ICONS = {
    views: `<svg viewBox="0 0 24 24" fill="none"><path d="M2 12s3.6-6.5 10-6.5S22 12 22 12s-3.6 6.5-10 6.5S2 12 2 12Z" stroke="currentColor" stroke-width="1.7"/><circle cx="12" cy="12" r="2.6" stroke="currentColor" stroke-width="1.7"/></svg>`,
    likes: `<svg viewBox="0 0 24 24" fill="none"><path d="M12 20s-7.5-4.6-7.5-9.4A4.1 4.1 0 0 1 12 8a4.1 4.1 0 0 1 7.5 2.6C19.5 15.4 12 20 12 20Z" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/></svg>`,
    comments: `<svg viewBox="0 0 24 24" fill="none"><path d="M20 4H4a1.5 1.5 0 0 0-1.5 1.5v9A1.5 1.5 0 0 0 4 16h3v4l4.5-4H20a1.5 1.5 0 0 0 1.5-1.5v-9A1.5 1.5 0 0 0 20 4Z" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/></svg>`,
  };

  function renderChannel(data) {
    const ch = data.channel;
    const avatar = document.getElementById("channel-avatar");
    if (ch.avatar) {
      avatar.src = ch.avatar;
      avatar.style.display = "";
    } else {
      avatar.style.display = "none";
    }
    document.getElementById("channel-name").textContent = ch.name;
    document.getElementById("channel-subs").textContent =
      ch.subscribers ? `${formatCount(ch.subscribers)} подписчиков` : "";

    const grid = document.getElementById("channel-videos");
    grid.innerHTML = "";
    for (const v of data.videos) {
      const card = document.createElement("div");
      card.className = "video-card";
      card.innerHTML = `
        <div class="video-thumb-wrap">
          ${v.thumbnail ? `<img class="video-thumb" src="${v.thumbnail}" alt="" loading="lazy">` : `<div class="video-thumb"></div>`}
          ${v.duration_sec ? `<span class="video-duration">${formatDuration(v.duration_sec)}</span>` : ""}
        </div>
        <div class="video-title" title="${v.title.replace(/"/g, "&quot;")}">${v.title}</div>
        <div class="video-stats">
          <span class="video-stat" title="Просмотры">${ICONS.views}${formatCount(v.views)}</span>
          <span class="video-stat" title="Лайки">${ICONS.likes}${formatCount(v.likes)}</span>
          <span class="video-stat" title="Комментарии">${ICONS.comments}${formatCount(v.comments)}</span>
        </div>
      `;
      if (v.url) {
        card.addEventListener("dblclick", () => window.open(v.url, "_blank"));
      }
      grid.appendChild(card);
    }

    renderTotals(data.totals);
    collapseStats();
  }

  function collapseStats() {
    // Reset on every fresh parse: the panel's animated max-height is a pixel
    // value measured from the *previous* channel's content, so leaving it
    // open across a re-render would clip or overshoot the new content.
    const panel = document.getElementById("stats-panel");
    const toggle = document.getElementById("btn-stats-toggle");
    panel.classList.remove("open");
    toggle.classList.remove("open");
    panel.style.maxHeight = "0px";
  }

  function renderTotals(totals) {
    const inner = document.getElementById("stats-panel-inner");
    const rows = [
      ["day", "За сутки"],
      ["week", "За неделю"],
      ["month", "За месяц"],
    ];
    inner.innerHTML = `
      <p class="hint" style="margin:0 0 14px">
        Считается по последним загруженным видео канала — это срез свежей активности, а не статистика за всё время.
      </p>
      <div class="stats-grid">
        ${rows.map(([key, label]) => {
          const t = totals[key] || { views: 0, likes: 0, comments: 0, videos: 0 };
          return `
            <div class="stats-card">
              <div class="stats-card-label">${label}</div>
              <div class="stats-card-videos">${t.videos} видео</div>
              <div class="stats-row">${ICONS.views}<span>${formatCount(t.views)}</span></div>
              <div class="stats-row">${ICONS.likes}<span>${formatCount(t.likes)}</span></div>
              <div class="stats-row">${ICONS.comments}<span>${formatCount(t.comments)}</span></div>
            </div>
          `;
        }).join("")}
      </div>
    `;
  }

  async function parse() {
    const url = document.getElementById("parser-url").value.trim();
    if (!url) return showError("Вставьте ссылку на канал.");

    const btn = document.getElementById("btn-parse");
    const loading = document.getElementById("parser-loading");
    const result = document.getElementById("parser-result");

    btn.disabled = true;
    loading.classList.remove("hidden");
    result.classList.add("hidden");
    try {
      const res = await fetch("/api/parse-channel", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url }),
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Не удалось проанализировать канал");
      }
      renderChannel(await res.json());
      result.classList.remove("hidden");
    } catch (e) {
      showError(e.message);
    } finally {
      btn.disabled = false;
      loading.classList.add("hidden");
    }
  }

  function init() {
    const btn = document.getElementById("btn-parse");
    if (!btn) return;
    btn.addEventListener("click", parse);
    document.getElementById("parser-url").addEventListener("keydown", (e) => {
      if (e.key === "Enter") parse();
    });

    const toggle = document.getElementById("btn-stats-toggle");
    const panel = document.getElementById("stats-panel");
    toggle.addEventListener("click", () => {
      const opening = !panel.classList.contains("open");
      panel.classList.toggle("open", opening);
      toggle.classList.toggle("open", opening);
      // Animating to the measured content height (rather than `auto`, which
      // isn't animatable) is what makes the expand actually glide open.
      panel.style.maxHeight = opening ? `${panel.scrollHeight}px` : "0px";
    });
  }

  return { init };
})();

document.addEventListener("DOMContentLoaded", ChannelParser.init);
