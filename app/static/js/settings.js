(function () {
  "use strict";

  const setText = (id, value) => {
    const element = document.getElementById(id);
    if (element) element.textContent = value;
  };
  const permissionLabel = (state) => ({granted: "Allowed", denied: "Blocked", prompt: "Not decided"}[state] || "Unavailable");

  const renderConnection = () => setText("connection-state", navigator.onLine ? "Online" : "Offline · queue active");
  window.addEventListener("online", renderConnection);
  window.addEventListener("offline", renderConnection);
  renderConnection();

  if (navigator.permissions?.query) {
    navigator.permissions.query({name: "geolocation"}).then((status) => {
      const render = () => setText("permission-location", permissionLabel(status.state));
      render();
      status.addEventListener?.("change", render);
    }).catch(() => setText("permission-location", "Ask at ride start"));
  } else {
    setText("permission-location", "Ask at ride start");
  }

  const renderNotifications = () => {
    setText("permission-notifications", "Notification" in window ? permissionLabel(Notification.permission) : "Unavailable");
  };
  renderNotifications();

  document.querySelectorAll("[data-request-location]").forEach((button) => {
    button.addEventListener("click", () => {
      if (!("geolocation" in navigator)) {
        setText("permission-location", "Unavailable");
        return;
      }
      setText("permission-location", "Requesting…");
      navigator.geolocation.getCurrentPosition(
        () => setText("permission-location", "Allowed"),
        (error) => setText("permission-location", error.code === error.PERMISSION_DENIED ? "Blocked" : "Unavailable"),
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
        setText("permission-motion", granted ? "Allowed" : "Blocked");
      } catch (error) {
        console.error("Motion permission request failed", error);
        setText("permission-motion", "Unavailable");
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
