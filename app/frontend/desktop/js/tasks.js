/*
 * "Задачи" tab: lists every job (running or finished) with a thumbnail,
 * live progress while running, and a "finished X ago" counter once done.
 * Polls the backend while this tab is visible; the elapsed-time counters
 * refresh locally on a slower tick without a re-fetch.
 */
const Tasks = (() => {
  const STAGE_LABELS = {
    queued: "В очереди",
    download: "Скачивание",
    cut_or_analyze: "Нарезка",
    overlay: "Наложение текста",
    variations: "Генерация вариантов",
    done: "Готово",
    error: "Ошибка",
  };

  let pollTimer = null;
  let tickTimer = null;
  let jobs = [];

  function pad(n) {
    return String(n).padStart(2, "0");
  }

  function formatAgo(finishedAtIso) {
    const finished = new Date(finishedAtIso).getTime();
    if (Number.isNaN(finished)) return "";
    let diffSec = Math.max(0, Math.floor((Date.now() - finished) / 1000));
    const days = Math.floor(diffSec / 86400);
    diffSec -= days * 86400;
    const hours = Math.floor(diffSec / 3600);
    diffSec -= hours * 3600;
    const minutes = Math.floor(diffSec / 60);
    return `${pad(days)}дн.${pad(hours)}ч.${pad(minutes)}мин назад`;
  }

  function renderCard(job) {
    const el = document.createElement("div");
    el.className = "task-card";
    el.dataset.jobId = job.job_id;

    const thumb = job.thumbnail_url
      ? `<img class="task-thumb" src="${job.thumbnail_url}" alt="">`
      : `<div class="task-thumb task-thumb-placeholder"></div>`;

    let statusHtml;
    if (job.status === "done") {
      statusHtml = `
        <div class="task-status task-status-done">Готово</div>
        <div class="task-ago">${formatAgo(job.finished_at)}</div>
      `;
    } else if (job.status === "error") {
      statusHtml = `
        <div class="task-status task-status-error">Ошибка</div>
        <div class="task-error-msg">${job.error || job.progress.message || ""}</div>
      `;
    } else {
      const label = STAGE_LABELS[job.progress.stage] || job.progress.stage;
      statusHtml = `
        <div class="task-progress-bar"><div class="task-progress-fill" style="width:${job.progress.progress}%"></div></div>
        <div class="task-stage-label">${label}${job.progress.message ? ": " + job.progress.message : ""}</div>
      `;
    }

    el.innerHTML = `
      <button type="button" class="task-delete" title="Удалить из задач">✕</button>
      ${thumb}
      <div class="task-info">
        <div class="task-title" title="${job.title}">${job.title}</div>
        ${statusHtml}
      </div>
    `;

    el.querySelector(".task-delete").addEventListener("click", async (e) => {
      e.stopPropagation();
      try {
        await fetch(`/api/jobs/${job.job_id}`, { method: "DELETE" });
      } catch {
        // best-effort - the next poll resyncs the list either way
      }
      jobs = jobs.filter((j) => j.job_id !== job.job_id);
      render();
    });

    return el;
  }

  function render() {
    const list = document.getElementById("tasks-list");
    const empty = document.getElementById("tasks-empty");
    if (!list) return;
    list.innerHTML = "";
    if (jobs.length === 0) {
      empty.classList.remove("hidden");
      return;
    }
    empty.classList.add("hidden");
    for (const job of jobs) list.appendChild(renderCard(job));
  }

  async function refresh() {
    try {
      const res = await fetch("/api/jobs");
      if (!res.ok) return;
      jobs = await res.json();
      render();
    } catch {
      // offline/hiccup - keep showing the last known list
    }
  }

  function tickAgo() {
    document.querySelectorAll(".task-ago").forEach((el) => {
      const card = el.closest(".task-card");
      const job = jobs.find((j) => j.job_id === card?.dataset.jobId);
      if (job && job.finished_at) el.textContent = formatAgo(job.finished_at);
    });
  }

  function start() {
    refresh();
    clearInterval(pollTimer);
    clearInterval(tickTimer);
    pollTimer = setInterval(refresh, 3000);
    tickTimer = setInterval(tickAgo, 30000);
  }

  function stop() {
    clearInterval(pollTimer);
    clearInterval(tickTimer);
    pollTimer = null;
    tickTimer = null;
  }

  return { start, stop };
})();
