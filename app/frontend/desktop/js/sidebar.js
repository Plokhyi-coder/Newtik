/*
 * Sidebar navigation: switches between top-level app sections, animates the
 * active-item indicator to slide to whichever item was picked, and lets the
 * user resize the sidebar by dragging its right edge (persisted) or collapse
 * it to an icon-only rail.
 */
const SECTION_IDS = ["upload", "gallery", "qr", "tasks"];

function moveNavIndicator(activeItem) {
  const indicator = document.getElementById("nav-indicator");
  const nav = document.getElementById("sidebar-nav");
  if (!indicator || !activeItem) return;
  const navRect = nav.getBoundingClientRect();
  const itemRect = activeItem.getBoundingClientRect();
  indicator.style.transform = `translateY(${itemRect.top - navRect.top}px)`;
}

function switchSection(sectionId) {
  for (const id of SECTION_IDS) {
    const el = document.getElementById(`section-${id}`);
    if (el) el.classList.toggle("hidden", id !== sectionId);
  }
  document.querySelectorAll(".nav-item[data-section]").forEach((item) => {
    item.classList.toggle("active", item.dataset.section === sectionId);
  });
  const activeItem = document.querySelector(`.nav-item[data-section="${sectionId}"]`);
  moveNavIndicator(activeItem);
}

function initSidebarNav() {
  document.querySelectorAll(".nav-item[data-section]").forEach((item) => {
    item.addEventListener("click", () => switchSection(item.dataset.section));
  });
  // Position the indicator correctly on first paint (fonts/layout can shift it).
  requestAnimationFrame(() => moveNavIndicator(document.querySelector(".nav-item.active")));
  window.addEventListener("resize", () => {
    moveNavIndicator(document.querySelector(".nav-item.active"));
  });
}

function initSidebarCollapse() {
  const sidebar = document.getElementById("sidebar");
  const btn = document.getElementById("btn-sidebar-collapse");
  const collapsed = localStorage.getItem("newtik.sidebarCollapsed") === "1";
  if (collapsed) sidebar.classList.add("collapsed");

  btn.addEventListener("click", () => {
    sidebar.classList.toggle("collapsed");
    localStorage.setItem("newtik.sidebarCollapsed", sidebar.classList.contains("collapsed") ? "1" : "0");
    setTimeout(() => moveNavIndicator(document.querySelector(".nav-item.active")), 260);
  });
}

function initSidebarResize() {
  const sidebar = document.getElementById("sidebar");
  const handle = document.getElementById("sidebar-resize-handle");
  const MIN_WIDTH = 200;
  const MAX_WIDTH = 420;

  const savedWidth = parseInt(localStorage.getItem("newtik.sidebarWidth"), 10);
  if (savedWidth && savedWidth >= MIN_WIDTH && savedWidth <= MAX_WIDTH) {
    sidebar.style.setProperty("--sidebar-width", `${savedWidth}px`);
  }

  let dragging = false;

  handle.addEventListener("mousedown", (e) => {
    e.preventDefault();
    dragging = true;
    sidebar.classList.add("resizing");
    handle.classList.add("dragging");
  });

  window.addEventListener("mousemove", (e) => {
    if (!dragging) return;
    const width = Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, e.clientX));
    sidebar.style.setProperty("--sidebar-width", `${width}px`);
    moveNavIndicator(document.querySelector(".nav-item.active"));
  });

  window.addEventListener("mouseup", () => {
    if (!dragging) return;
    dragging = false;
    sidebar.classList.remove("resizing");
    handle.classList.remove("dragging");
    const width = parseInt(getComputedStyle(sidebar).width, 10);
    localStorage.setItem("newtik.sidebarWidth", String(width));
  });
}

function initLogoLink() {
  const link = document.getElementById("logo-by-link");
  if (!link) return;
  link.addEventListener("click", (e) => {
    e.preventDefault();
    window.open("https://t.me/plokhyi", "_blank");
  });
}

document.addEventListener("DOMContentLoaded", () => {
  initSidebarNav();
  initSidebarCollapse();
  initSidebarResize();
  initLogoLink();
});
