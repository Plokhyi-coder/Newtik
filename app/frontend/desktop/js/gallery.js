/*
 * Explorer-style gallery: root level shows one "folder" per finished job,
 * opening a folder shows its clips as "files" with real video thumbnails.
 * Double-click opens (folder -> navigate in, file -> play inline);
 * right-click gives Открыть/Открыть на устройстве/Удалить, same as a
 * normal desktop file explorer. Delete goes through send2trash on the
 * backend (recycle bin, not permanent), and "on device" shells out to the
 * OS's own file manager.
 */
const Gallery = (() => {
  let folders = [];
  let currentJobId = null; // null = at root
  let currentFiles = [];
  let currentFolderName = "";
  let sortMode = "recent";
  let contextTarget = null; // { kind: "folder"|"file", jobId, clipId }

  function formatSize(bytes) {
    if (bytes < 1024) return `${bytes} Б`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} КБ`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} МБ`;
  }

  function sortItems(items, sizeKey) {
    const arr = [...items];
    if (sortMode === "recent") arr.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
    else if (sortMode === "oldest") arr.sort((a, b) => new Date(a.created_at) - new Date(b.created_at));
    else if (sortMode === "size") arr.sort((a, b) => b[sizeKey] - a[sizeKey]);
    return arr;
  }

  function renderRoot() {
    document.getElementById("gallery-breadcrumb").textContent = "Все обработанные видео";
    document.getElementById("gallery-back").classList.add("hidden");

    const grid = document.getElementById("gallery-grid");
    const empty = document.getElementById("gallery-empty");
    grid.innerHTML = "";

    if (folders.length === 0) {
      empty.classList.remove("hidden");
      return;
    }
    empty.classList.add("hidden");

    for (const folder of sortItems(folders, "total_size_bytes")) {
      const el = document.createElement("div");
      el.className = "gallery-item";
      el.dataset.kind = "folder";
      el.dataset.jobId = folder.job_id;
      el.innerHTML = `
        <div class="gallery-item-icon gallery-folder-icon"><span class="icon-mask" style="mask-image:url(/assets/icon-folder.svg);-webkit-mask-image:url(/assets/icon-folder.svg)"></span></div>
        <div class="gallery-item-name" title="${folder.name}">${folder.name}</div>
        <div class="gallery-item-meta">${folder.item_count} видео · ${formatSize(folder.total_size_bytes)}</div>
      `;
      el.addEventListener("dblclick", () => openFolder(folder.job_id, folder.name));
      el.addEventListener("contextmenu", (e) => showContextMenu(e, { kind: "folder", jobId: folder.job_id }));
      grid.appendChild(el);
    }
  }

  function renderFolder() {
    document.getElementById("gallery-breadcrumb").textContent = currentFolderName;
    document.getElementById("gallery-back").classList.remove("hidden");

    const grid = document.getElementById("gallery-grid");
    const empty = document.getElementById("gallery-empty");
    grid.innerHTML = "";

    if (currentFiles.length === 0) {
      empty.classList.remove("hidden");
      return;
    }
    empty.classList.add("hidden");

    for (const file of sortItems(currentFiles, "size_bytes")) {
      const el = document.createElement("div");
      el.className = "gallery-item";
      el.dataset.kind = "file";
      el.dataset.jobId = currentJobId;
      el.dataset.clipId = file.clip_id;
      const label = file.variation_index === 0 ? "Оригинал" : `Вариант ${file.variation_index}`;
      el.innerHTML = `
        <div class="gallery-item-icon gallery-file-icon">
          <img src="/api/jobs/${currentJobId}/thumbnail/${file.clip_id}" alt="" loading="lazy">
          <span class="gallery-play-badge icon-mask" style="mask-image:url(/assets/icon-upload-play.svg);-webkit-mask-image:url(/assets/icon-upload-play.svg)"></span>
        </div>
        <div class="gallery-item-name" title="${label}">${label}</div>
        <div class="gallery-item-meta">${formatSize(file.size_bytes)}</div>
      `;
      el.addEventListener("dblclick", () => playClip(currentJobId, file.clip_id));
      el.addEventListener("contextmenu", (e) => showContextMenu(e, { kind: "file", jobId: currentJobId, clipId: file.clip_id }));
      grid.appendChild(el);
    }
  }

  async function loadRoot() {
    currentJobId = null;
    try {
      const res = await fetch("/api/gallery");
      folders = await res.json();
    } catch {
      folders = [];
    }
    renderRoot();
  }

  async function openFolder(jobId, name) {
    try {
      const res = await fetch(`/api/gallery/${jobId}`);
      if (!res.ok) return;
      const data = await res.json();
      currentJobId = jobId;
      currentFolderName = name || data.name;
      currentFiles = data.files;
      renderFolder();
    } catch {
      // stay on the current view - a transient fetch hiccup shouldn't nuke it
    }
  }

  function playClip(jobId, clipId) {
    const overlay = document.getElementById("gallery-video-overlay");
    const video = document.getElementById("gallery-video");
    video.src = `/api/jobs/${jobId}/download/${clipId}`;
    overlay.classList.remove("hidden");
  }

  function closeVideo() {
    const overlay = document.getElementById("gallery-video-overlay");
    const video = document.getElementById("gallery-video");
    video.pause();
    video.removeAttribute("src");
    video.load();
    overlay.classList.add("hidden");
  }

  function hideContextMenu() {
    document.getElementById("gallery-context-menu").classList.add("hidden");
    contextTarget = null;
  }

  function showContextMenu(e, target) {
    e.preventDefault();
    contextTarget = target;
    const menu = document.getElementById("gallery-context-menu");
    menu.classList.remove("hidden");
    const maxX = window.innerWidth - menu.offsetWidth - 8;
    const maxY = window.innerHeight - menu.offsetHeight - 8;
    menu.style.left = `${Math.min(e.clientX, maxX)}px`;
    menu.style.top = `${Math.min(e.clientY, maxY)}px`;
  }

  async function handleContextAction(action) {
    if (!contextTarget) return;
    const { kind, jobId, clipId } = contextTarget;
    hideContextMenu();

    if (action === "open") {
      if (kind === "folder") {
        const folder = folders.find((f) => f.job_id === jobId);
        openFolder(jobId, folder?.name);
      } else {
        playClip(jobId, clipId);
      }
      return;
    }

    if (action === "reveal") {
      const url = kind === "folder" ? `/api/gallery/${jobId}/reveal` : `/api/gallery/${jobId}/clips/${clipId}/reveal`;
      try {
        const res = await fetch(url, { method: "POST" });
        if (!res.ok) {
          const err = await res.json();
          showError(err.detail || "Не удалось открыть системный проводник.");
        }
      } catch {
        showError("Не удалось открыть системный проводник.");
      }
      return;
    }

    if (action === "delete") {
      const confirmed = confirm(
        kind === "folder"
          ? "Удалить всю папку с видео в корзину?"
          : "Удалить это видео в корзину?"
      );
      if (!confirmed) return;

      const url = kind === "folder" ? `/api/gallery/${jobId}` : `/api/gallery/${jobId}/clips/${clipId}`;
      try {
        await fetch(url, { method: "DELETE" });
      } catch {
        // best-effort - reload reflects whatever the backend actually did
      }
      if (kind === "folder") {
        await loadRoot();
      } else {
        await openFolder(jobId, currentFolderName);
      }
    }
  }

  function init() {
    document.getElementById("gallery-back").addEventListener("click", loadRoot);
    document.getElementById("gallery-sort").addEventListener("change", (e) => {
      sortMode = e.target.value;
      if (currentJobId) renderFolder();
      else renderRoot();
    });
    document.getElementById("gallery-video-close").addEventListener("click", closeVideo);
    document.getElementById("gallery-video-overlay").addEventListener("click", (e) => {
      if (e.target.id === "gallery-video-overlay") closeVideo();
    });

    document.getElementById("gallery-context-menu").addEventListener("click", (e) => {
      const btn = e.target.closest("button[data-action]");
      if (btn) handleContextAction(btn.dataset.action);
    });
    document.addEventListener("click", (e) => {
      if (!e.target.closest("#gallery-context-menu")) hideContextMenu();
    });
    document.addEventListener("scroll", hideContextMenu, true);
  }

  function start() {
    loadRoot();
  }

  return { init, start };
})();

document.addEventListener("DOMContentLoaded", Gallery.init);
