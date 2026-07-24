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
    const altWrap = document.getElementById("qr-alt-ips");
    const altList = document.getElementById("qr-alt-ips-list");
    if (!img) return;

    img.src = `/api/qr.png?t=${Date.now()}`; // cache-bust in case the IP changed

    try {
      const res = await fetch("/api/network-info");
      const info = await res.json();
      urlInput.value = info.mobile_url;

      if (!info.has_lan_ip) {
        warning.textContent =
          "Не удалось определить адрес в локальной сети — убедитесь, что Wi-Fi подключён.";
        warning.classList.remove("hidden");
      } else if (!info.listening_on_lan) {
        warning.textContent =
          "Сервер не отвечает по локальному адресу — попробуйте перезапустить приложение.";
        warning.classList.remove("hidden");
      } else {
        warning.classList.add("hidden");
      }

      // If this machine has more than one network adapter (VPN, Docker/Hyper-V
      // bridge, second NIC...), the primary guess above might be the wrong one -
      // offer every other candidate so the user can just try them.
      if (info.alt_ips && info.alt_ips.length) {
        altList.innerHTML = "";
        for (const alt of info.alt_ips) {
          const row = document.createElement("div");
          row.className = "input-icon-wrap";
          row.style.marginTop = "6px";
          const span = document.createElement("span");
          span.className = "icon-mask";
          span.style.maskImage = "url(/assets/icon-qr.svg)";
          span.style.webkitMaskImage = "url(/assets/icon-qr.svg)";
          const input = document.createElement("input");
          input.type = "text";
          input.readOnly = true;
          input.value = alt.mobile_url;
          input.addEventListener("click", (e) => e.target.select());
          row.appendChild(span);
          row.appendChild(input);
          altList.appendChild(row);
        }
        altWrap.classList.remove("hidden");
      } else {
        altWrap.classList.add("hidden");
      }
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
