(function () {
  "use strict";

  const root = document.documentElement;
  const theme = root.dataset.theme || "system";
  const media = window.matchMedia("(prefers-color-scheme: dark)");
  const applyTheme = () => {
    root.dataset.resolvedTheme = theme === "system" ? (media.matches ? "dark" : "light") : theme;
  };
  applyTheme();
  if (theme === "system") media.addEventListener?.("change", applyTheme);

  let installPrompt = null;
  const installButtons = () => document.querySelectorAll("[data-install-app]");
  window.addEventListener("beforeinstallprompt", (event) => {
    event.preventDefault();
    installPrompt = event;
    installButtons().forEach((button) => { button.disabled = false; });
    const state = document.getElementById("install-state");
    if (state) state.textContent = "Ready to install on this device.";
  });
  installButtons().forEach((button) => {
    button.addEventListener("click", async () => {
      if (!installPrompt) return;
      installPrompt.prompt();
      await installPrompt.userChoice;
      installPrompt = null;
      button.disabled = true;
    });
  });
  window.addEventListener("appinstalled", () => {
    const state = document.getElementById("install-state");
    if (state) state.textContent = "RoR is installed on this device.";
  });

  if ("serviceWorker" in navigator && (window.isSecureContext || location.hostname === "localhost")) {
    navigator.serviceWorker.register("/service-worker.js", {scope: "/"})
      .catch((error) => console.warn("Service worker registration failed", error));
  }

  document.querySelectorAll(".flash-close").forEach((button) => {
    button.addEventListener("click", () => button.closest(".flash")?.remove());
  });

  document.querySelectorAll("[data-copy]").forEach((button) => {
    button.addEventListener("click", async () => {
      const target = document.getElementById(button.dataset.copy);
      const value = target?.dataset.value || target?.textContent?.trim();
      if (!value) return;
      try {
        await navigator.clipboard.writeText(value);
        const original = button.getAttribute("aria-label") || "Copy";
        button.setAttribute("aria-label", "Copied");
        button.classList.add("is-copied");
        setTimeout(() => {
          button.setAttribute("aria-label", original);
          button.classList.remove("is-copied");
        }, 1600);
      } catch (error) {
        console.error("Unable to copy", error);
      }
    });
  });

  const toggle = document.querySelector(".nav-toggle");
  if (toggle) {
    const observer = new MutationObserver(() => {
      document.body.classList.toggle("nav-open", toggle.getAttribute("aria-expanded") === "true");
    });
    observer.observe(toggle, { attributes: true, attributeFilter: ["aria-expanded"] });
  }
})();
