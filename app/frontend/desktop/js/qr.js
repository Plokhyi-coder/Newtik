/*
 * "QR-передача" tab: shows a QR code (generated server-side from the LAN IP)
 * that points a phone on the same Wi-Fi at /mobile - a page listing every
 * finished clip for download. Refreshed each time the tab is opened rather
 * than polled continuously, since the LAN IP practically never changes
 * mid-session.
 */
const QRPanel = (() => {
  async function refresh() {
    const img = document.getElementById("qr-image");
    const urlInput = document.getElementById("qr-url");
    const warning = document.getElementById("qr-warning");
    if (!img) return;

    img.src = `/api/qr.png?t=${Date.now()}`; // cache-bust in case the IP changed

    try {
      const res = await fetch("/api/network-info");
      const info = await res.json();
      urlInput.value = info.mobile_url;
      warning.classList.toggle("hidden", info.lan_ip !== "127.0.0.1");
    } catch {
      warning.classList.remove("hidden");
    }
  }

  return { refresh };
})();

document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("btn-qr-refresh")?.addEventListener("click", () => QRPanel.refresh());
  document.getElementById("qr-url")?.addEventListener("click", (e) => e.target.select());
});
