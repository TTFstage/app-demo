(function () {
  "use strict";

  const copy = window.ROR_SETTINGS_COPY || {};

  const setText = (id, value) => {
    const element = document.getElementById(id);
    if (element) element.textContent = value;
  };
  const permissionLabel = (state) => ({
    granted: copy.allowed || "Allowed",
    denied: copy.blocked || "Blocked",
    prompt: copy.notDecided || "Not decided",
  }[state] || copy.unavailable || "Unavailable");

  const renderConnection = () => setText(
    "connection-state",
    navigator.onLine ? (copy.online || "Online") : (copy.offlineActive || "Offline · queue active"),
  );
  window.addEventListener("online", renderConnection);
  window.addEventListener("offline", renderConnection);
  renderConnection();

  if (navigator.permissions?.query) {
    navigator.permissions.query({name: "geolocation"}).then((status) => {
      const render = () => setText("permission-location", permissionLabel(status.state));
      render();
      status.addEventListener?.("change", render);
    }).catch(() => setText("permission-location", copy.askAtStart || "Ask at ride start"));
  } else {
    setText("permission-location", copy.askAtStart || "Ask at ride start");
  }

  const renderNotifications = () => {
    setText("permission-notifications", "Notification" in window ? permissionLabel(Notification.permission) : "Unavailable");
  };
  renderNotifications();

  document.querySelectorAll("[data-request-location]").forEach((button) => {
    button.addEventListener("click", () => {
      if (!("geolocation" in navigator)) {
        setText("permission-location", copy.unavailable || "Unavailable");
        return;
      }
      setText("permission-location", copy.requesting || "Requesting…");
      navigator.geolocation.getCurrentPosition(
        () => setText("permission-location", copy.allowed || "Allowed"),
        (error) => setText("permission-location", error.code === error.PERMISSION_DENIED ? (copy.blocked || "Blocked") : (copy.unavailable || "Unavailable")),
        {enableHighAccuracy: true, timeout: 10000},
      );
    });
  });

  document.querySelectorAll("[data-request-motion]").forEach((button) => {
    button.addEventListener("click", async () => {
      try {
        let granted = true;
        if (typeof DeviceMotionEvent !== "undefined" && typeof DeviceMotionEvent.requestPermission === "function") {
          granted = (await DeviceMotionEvent.requestPermission()) === "granted";
        }
        if (typeof DeviceOrientationEvent !== "undefined" && typeof DeviceOrientationEvent.requestPermission === "function") {
          granted = granted && (await DeviceOrientationEvent.requestPermission()) === "granted";
        }
        setText("permission-motion", granted ? (copy.allowed || "Allowed") : (copy.blocked || "Blocked"));
      } catch (error) {
        console.error("Motion permission request failed", error);
        setText("permission-motion", copy.unavailable || "Unavailable");
      }
    });
  });

  document.querySelectorAll("[data-request-notifications]").forEach((button) => {
    button.addEventListener("click", async () => {
      if (!("Notification" in window)) return renderNotifications();
      await Notification.requestPermission();
      renderNotifications();
      if (Notification.permission === "granted") {
        const preference = document.getElementById("browser_notifications_enabled");
        if (preference) preference.checked = true;
      }
    });
  });
})();
