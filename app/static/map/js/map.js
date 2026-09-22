(function () {
  const copy = window.ROR_MAP_COPY || {};
  const ZOOM_THRESHOLD = 13;
  const DEBOUNCE_MS = 150;
  const GEOHASH_PRECISION = 5;

  const ENTITY_CONFIG = {
    stations: { url: "/api/v1/fountains", color: "#2563eb", label: copy.fountains },
    bicycle_repair: { url: "/api/v1/bicycle_repair", color: "#e63946", label: copy.repair },
    toilets: { url: "/api/v1/toilets", color: "#16a34a", label: copy.toilets },
    bicycleParkings: {
      url: "/api/v1/bicycle-parkings",
      color: "#ea580c",
      label: copy.parking,
    },

  };

  const map = L.map("map").setView([45.4642, 9.19], 13);
  window.map = map;

  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "&copy; OpenStreetMap contributors",
  }).addTo(map);

  // ── Cluster groups per entità ──────────────────────────────────────────────
  const clusterGroups = {};
  const requestedGeohashes = {};
  const loadingGeohashes = {};
  Object.keys(ENTITY_CONFIG).forEach((type) => {
    clusterGroups[type] = L.markerClusterGroup();
    requestedGeohashes[type] = new Set();
    loadingGeohashes[type] = new Set();
  });

  function getSelectedOverlays() {
    return Array.from(
      document.querySelectorAll('#overlay-selector input[type="checkbox"]:checked'),
    ).map((el) => el.dataset.overlay);
  }

  function markerFor(type, item) {
    const config = ENTITY_CONFIG[type];
    const icon = L.divIcon({
      className: "custom-marker",
      html: `<span style="background:${config.color}"></span>`,
      iconSize: [16, 16],
    });
    const marker = L.marker([item.lat, item.lng], { icon });

    // Add to navigator as waypoint if in nav mode
    marker.on("click", () => {
      if (navState.active) {
        // già gestito dal popup, niente da fare
      }
    });

    // Popup with "Add as waypoint" button
    const popup = L.popup().setContent(() => {
      const div = document.createElement("div");
      const config2 = ENTITY_CONFIG[type];
      const title = document.createElement("strong");
      title.textContent = config2.label;
      div.appendChild(title);
      if ((type === "stations" && item.name) || (type === "toilets" && item.openingHours)) {
        const detail = document.createElement("div");
        detail.textContent = type === "stations" ? item.name : `${copy.openingHours}: ${item.openingHours}`;
        div.appendChild(detail);
      }
      const addButton = document.createElement("button");
      addButton.className = "popup-add-btn";
      addButton.textContent = copy.addWaypoint;
      div.appendChild(addButton);
      addButton.addEventListener("click", () => {
        addWaypointFromMap(item.lat, item.lng, `${config2.label}${item.name ? ": " + item.name : ""}`);
        map.closePopup();
      });
      return div;
    });
    marker.bindPopup(popup);
    return marker;
  }

  async function fetchEntityType(type, geohashes) {
    const config = ENTITY_CONFIG[type];
    const response = await fetch(`${config.url}?gh5=${geohashes.join(",")}`);
    if (!response.ok) {
      throw new Error(`${config.label} request failed (${response.status})`);
    }
    const data = await response.json();
    if (!Array.isArray(data)) throw new Error(`${config.label} response is invalid`);
    return data;
  }

  function boundsToGeohashes(bounds) {
    return window.geohashLib.bboxes(
      bounds.getSouth(), bounds.getWest(),
      bounds.getNorth(), bounds.getEast(),
      GEOHASH_PRECISION,
    );
  }

  let debounceTimer = null;
  let updateSequence = 0;
  function scheduleUpdate() {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(updateVisibleEntities, DEBOUNCE_MS);
  }

  async function updateVisibleEntities() {
    const sequence = ++updateSequence;
    const zoom = map.getZoom();
    const selected = getSelectedOverlays();

    Object.entries(clusterGroups).forEach(([type, group]) => {
      if (!selected.includes(type) && map.hasLayer(group)) map.removeLayer(group);
    });

    if (selected.length === 0) {
      showMapHint(copy.chooseFilter);
      return;
    }

    if (zoom < ZOOM_THRESHOLD) {
      showMapHint(copy.zoom);
      return;
    }

    showMapHint(copy.loading);

    const geohashes = boundsToGeohashes(map.getBounds());
    let hadError = false;
    await Promise.all(
      selected.map(async (type) => {
        const toFetch = geohashes.filter(
          (gh) => !requestedGeohashes[type].has(gh) && !loadingGeohashes[type].has(gh),
        );
        if (toFetch.length > 0) {
          toFetch.forEach((gh) => loadingGeohashes[type].add(gh));
          try {
            const items = await fetchEntityType(type, toFetch);
            items.forEach((item) => clusterGroups[type].addLayer(markerFor(type, item)));
            toFetch.forEach((gh) => requestedGeohashes[type].add(gh));
          } catch (error) {
            hadError = true;
            console.error("Unable to load map points:", error);
          } finally {
            toFetch.forEach((gh) => loadingGeohashes[type].delete(gh));
          }
        }
        if (!map.hasLayer(clusterGroups[type])) map.addLayer(clusterGroups[type]);
      }),
    );

    if (sequence !== updateSequence) return;
    if (hadError) {
      showMapHint(copy.loadError, true);
      return;
    }

    const visibleBounds = map.getBounds();
    const visibleCount = selected.reduce(
      (total, type) => total + clusterGroups[type].getLayers().filter(
        (marker) => visibleBounds.contains(marker.getLatLng()),
      ).length,
      0,
    );
    if (visibleCount === 0) {
      showMapHint(copy.noStops);
    } else {
      hideMapHint();
    }
  }

  function showMapHint(message, isError = false) {
    const hint = document.getElementById("zoom-hint");
    hint.textContent = message;
    hint.classList.toggle("is-error", isError);
    hint.hidden = false;
  }

  function hideMapHint() {
    const hint = document.getElementById("zoom-hint");
    hint.hidden = true;
    hint.classList.remove("is-error");
  }

  map.on("moveend zoomend load", scheduleUpdate);
  document.querySelectorAll('#overlay-selector input[type="checkbox"]').forEach((el) => {
    el.addEventListener("change", scheduleUpdate);
  });
  scheduleUpdate();

  // ── Geolocalizzazione ──────────────────────────────────────────────────────
  let userLatLng = null;
  const userIcon = L.divIcon({
    className: "user-location-marker",
    html: `<div class="user-dot"></div>`,
    iconSize: [18, 18],
    iconAnchor: [9, 9],
  });
  let userMarker = null;

  map.locate({ setView: false, maxZoom: 16, watch: true });
  map.on("locationfound", (e) => {
    userLatLng = e.latlng;
    if (!userMarker) {
      userMarker = L.marker(e.latlng, { icon: userIcon, zIndexOffset: 1000 })
        .addTo(map)
        .bindPopup("📍 You are here");
    } else {
      userMarker.setLatLng(e.latlng);
    }
    // Update "current location" fields if selected
    refreshCurrentLocationFields();
  });

  // ── NAVIGATORE ─────────────────────────────────────────────────────────────

  const navState = {
    active: false,
    waypoints: [], // [{lat, lng, label, marker, isCurrentLocation}]
    routeLayer: null,
    routeInfo: null,
  };

  // Icone waypoint
  function makeWaypointIcon(label, color) {
    return L.divIcon({
      className: "waypoint-marker",
      html: `<div style="background:${color};color:#fff;border-radius:50%;width:28px;height:28px;display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:700;border:2px solid #fff;box-shadow:0 1px 4px rgba(0,0,0,.4)">${label}</div>`,
      iconSize: [28, 28],
      iconAnchor: [14, 14],
    });
  }

  const wpColors = { start: "#000000", end: "#d72638", mid: "#6b6b6b" };

  function buildNavPanel() {
    const panel = document.getElementById("nav-panel");

    // Open/close button
    const navToggle = document.getElementById("nav-toggle");
    navToggle.addEventListener("click", () => {
      const isOpen = panel.classList.toggle("hidden") === false;
      navToggle.setAttribute("aria-expanded", String(isOpen));
      navToggle.textContent = isOpen ? copy.close : copy.plan;
      if (isOpen) renderWaypointList();
    });

    // Use current location (general toggle)
    document.getElementById("use-location-btn").addEventListener("click", () => {
      if (!userLatLng) {
        showNavMsg(copy.locationWait, true);
        return;
      }
      // Se il primo waypoint non è ancora "posizione attuale", lo imposta
      if (navState.waypoints.length === 0 || !navState.waypoints[0].isCurrentLocation) {
        addWaypointAtIndex(0, userLatLng.lat, userLatLng.lng, copy.currentLocation, true);
      }
    });

    // Calculate route
    document.getElementById("calc-route-btn").addEventListener("click", calcRoute);

    // Azzera
    document.getElementById("clear-route-btn").addEventListener("click", clearRoute);

    // Search waypoint (geocoding)
    document.getElementById("wp-search-btn").addEventListener("click", geocodeAndAdd);
    document.getElementById("wp-search-input").addEventListener("keydown", (e) => {
      if (e.key === "Enter") geocodeAndAdd();
    });

    // Add nearest fountain to route
    document.getElementById("add-nearest-fountain-btn").addEventListener("click", () => addNearestOnRoute("stations"));
    document.getElementById("add-nearest-parking-btn").addEventListener("click", () => addNearestOnRoute("bicycleParkings"));

    // Click on map to add waypoint (only if nav active)
    document.getElementById("map-click-add-btn").addEventListener("click", () => {
      navState.active = !navState.active;
      const btn = document.getElementById("map-click-add-btn");
      if (navState.active) {
        btn.textContent = "✋ Stop selecting";
        btn.classList.add("active");
        map.getContainer().style.cursor = "crosshair";
      } else {
        btn.textContent = "🖱️ Select point on map";
        btn.classList.remove("active");
        map.getContainer().style.cursor = "";
      }
    });

    map.on("click", (e) => {
      if (!navState.active) return;
      addWaypointFromMap(e.latlng.lat, e.latlng.lng, formatLatLng(e.latlng.lat, e.latlng.lng));
    });
  }

  function formatLatLng(lat, lng) {
    return `${lat.toFixed(5)}, ${lng.toFixed(5)}`;
  }

  function addWaypointFromMap(lat, lng, label) {
    addWaypointEnd(lat, lng, label, false);
  }

  function addWaypointAtIndex(idx, lat, lng, label, isCurrentLocation) {
    // Rimuovi marker precedente se esiste
    if (navState.waypoints[idx]) {
      if (navState.waypoints[idx].marker) map.removeLayer(navState.waypoints[idx].marker);
    }

    const wpEntry = { lat, lng, label, isCurrentLocation, marker: null };

    if (idx === 0 && navState.waypoints.length === 0) {
      navState.waypoints.push(wpEntry);
    } else if (idx <= navState.waypoints.length) {
      navState.waypoints.splice(idx, 0, wpEntry);
    }

    updateWaypointMarkers();
    renderWaypointList();
  }

  function addWaypointEnd(lat, lng, label, isCurrentLocation = false) {
    navState.waypoints.push({ lat, lng, label, isCurrentLocation, marker: null });
    updateWaypointMarkers();
    renderWaypointList();
  }

  function updateWaypointMarkers() {
    // Rimuovi tutti i marker precedenti
    navState.waypoints.forEach((wp) => {
      if (wp.marker) { map.removeLayer(wp.marker); wp.marker = null; }
    });

    navState.waypoints.forEach((wp, i) => {
      const n = navState.waypoints.length;
      let color, iconLabel;
      if (i === 0) { color = wpColors.start; iconLabel = "A"; }
      else if (i === n - 1 && n > 1) { color = wpColors.end; iconLabel = "B"; }
      else { color = wpColors.mid; iconLabel = String(i); }

      const marker = L.marker([wp.lat, wp.lng], {
        icon: makeWaypointIcon(iconLabel, color),
        draggable: true,
        zIndexOffset: 2000,
      }).addTo(map);

      marker.on("dragend", (e) => {
        const ll = e.target.getLatLng();
        wp.lat = ll.lat;
        wp.lng = ll.lng;
        if (!wp.isCurrentLocation) wp.label = formatLatLng(ll.lat, ll.lng);
        renderWaypointList();
        if (navState.routeLayer) calcRoute(); // recalculate if a route was already present
      });

      marker.bindPopup(`<strong>${wp.label}</strong>`);
      wp.marker = marker;
    });
  }

  function removeWaypoint(idx) {
    if (navState.waypoints[idx]?.marker) map.removeLayer(navState.waypoints[idx].marker);
    navState.waypoints.splice(idx, 1);
    updateWaypointMarkers();
    renderWaypointList();
    if (navState.routeLayer) calcRoute();
  }

  function renderWaypointList() {
    const list = document.getElementById("wp-list");
    list.innerHTML = "";

    navState.waypoints.forEach((wp, i) => {
      const n = navState.waypoints.length;
      let color;
      if (i === 0) color = wpColors.start;
      else if (i === n - 1 && n > 1) color = wpColors.end;
      else color = wpColors.mid;

      const item = document.createElement("div");
      item.className = "wp-item";
      const dot = document.createElement("span");
      dot.className = "wp-dot";
      dot.style.background = color;
      const label = document.createElement("span");
      label.className = "wp-label";
      label.title = wp.label;
      label.textContent = wp.label;
      const remove = document.createElement("button");
      remove.className = "wp-remove";
      remove.type = "button";
      remove.title = copy.remove;
      remove.setAttribute("aria-label", copy.remove);
      remove.textContent = "✕";
      remove.addEventListener("click", () => removeWaypoint(i));
      item.append(dot, label, remove);
      list.appendChild(item);
    });

    // Messaggio se vuoto
    if (navState.waypoints.length === 0) {
      const empty = document.createElement("p");
      empty.className = "wp-empty";
      empty.textContent = copy.emptyWaypoints;
      list.appendChild(empty);
    }

    // Show action buttons only if enough points
    const hasEnough = navState.waypoints.length >= 2;
    document.getElementById("calc-route-btn").disabled = !hasEnough;
    document.getElementById("add-nearest-fountain-btn").disabled = !hasEnough;
    document.getElementById("add-nearest-parking-btn").disabled = !hasEnough;
  }

  function refreshCurrentLocationFields() {
    navState.waypoints.forEach((wp, i) => {
      if (wp.isCurrentLocation && userLatLng) {
        wp.lat = userLatLng.lat;
        wp.lng = userLatLng.lng;
        if (wp.marker) wp.marker.setLatLng(userLatLng);
      }
    });
  }

  // ── Geocoding (Nominatim) ───────────────────────────────────────────────────
  async function geocodeAndAdd() {
    const input = document.getElementById("wp-search-input");
    const q = input.value.trim();
    if (!q) return;

    showNavMsg(copy.searching);
    try {
      const res = await fetch(
        `https://nominatim.openstreetmap.org/search?q=${encodeURIComponent(q)}&format=json&limit=1&accept-language=${encodeURIComponent(document.documentElement.lang || "en")}`,
        { headers: { "Accept-Language": document.documentElement.lang || "en" } }
      );
      const data = await res.json();
      if (!data.length) { showNavMsg(copy.noResults, true); return; }
      const place = data[0];
      addWaypointEnd(parseFloat(place.lat), parseFloat(place.lon), place.display_name.split(",")[0]);
      map.setView([place.lat, place.lon], 15);
      input.value = "";
      showNavMsg("");
    } catch {
      showNavMsg(copy.searchError, true);
    }
  }

  // ── Routing (OSRM cycling) ──────────────────────────────────────────────────
  async function calcRoute() {
    if (navState.waypoints.length < 2) return;
    showNavMsg(copy.calculating);

    const coords = navState.waypoints.map((wp) => `${wp.lng},${wp.lat}`).join(";");
    const url = `https://router.project-osrm.org/route/v1/cycling/${coords}?overview=full&geometries=geojson&steps=false`;

    try {
      const res = await fetch(url);
      const data = await res.json();
      if (data.code !== "Ok") { showNavMsg(copy.routeNotFound, true); return; }

      const route = data.routes[0];
      if (navState.routeLayer) map.removeLayer(navState.routeLayer);

      navState.routeLayer = L.geoJSON(route.geometry, {
        style: { color: "#ff5b2e", weight: 5, opacity: 0.95 },
      }).addTo(map);

      // Zoom to route
      map.fitBounds(navState.routeLayer.getBounds(), { padding: [40, 40] });

      // Route info
      const km = (route.distance / 1000).toFixed(1);
      const min = Math.round(route.duration / 60);
      navState.routeInfo = { distance: km, duration: min };
      showNavMsg(`🚴 ${km} km · ~${min} min`);
    } catch {
      showNavMsg(copy.routeError, true);
    }
  }

  function clearRoute() {
    if (navState.routeLayer) { map.removeLayer(navState.routeLayer); navState.routeLayer = null; }
    navState.waypoints.forEach((wp) => { if (wp.marker) map.removeLayer(wp.marker); });
    navState.waypoints = [];
    renderWaypointList();
    showNavMsg("");
  }

  // ── Punto più vicino sul/nel percorso ────────────────────────────────────────
  async function addNearestOnRoute(type) {
    if (navState.waypoints.length < 2) return;
    showNavMsg(copy.looking);

    // Bounding box of the route (from waypoints)
    const lats = navState.waypoints.map((w) => w.lat);
    const lngs = navState.waypoints.map((w) => w.lng);
    const bbox = {
      s: Math.min(...lats) - 0.01,
      n: Math.max(...lats) + 0.01,
      w: Math.min(...lngs) - 0.01,
      e: Math.max(...lngs) + 0.01,
    };

    // Retrieve entities from bbox via geohash
    const geohashes = window.geohashLib.bboxes(bbox.s, bbox.w, bbox.n, bbox.e, GEOHASH_PRECISION);
    const config = ENTITY_CONFIG[type];

    try {
      const res = await fetch(`${config.url}?gh5=${geohashes.join(",")}`);
      const items = await res.json();
      if (!items.length) { showNavMsg(copy.noNearby, true); return; }

      // Center of the route
      const midLat = (Math.min(...lats) + Math.max(...lats)) / 2;
      const midLng = (Math.min(...lngs) + Math.max(...lngs)) / 2;

      // Nearest point to the center of the route
      let best = items[0], bestDist = Infinity;
      items.forEach((item) => {
        const d = Math.hypot(item.lat - midLat, item.lng - midLng);
        if (d < bestDist) { bestDist = d; best = item; }
      });

      const label = `${config.label}${best.name ? ": " + best.name : ""}`;
      // Insert as second-to-last waypoint
      const insertAt = navState.waypoints.length - 1;
      navState.waypoints.splice(insertAt, 0, { lat: best.lat, lng: best.lng, label, isCurrentLocation: false, marker: null });
      updateWaypointMarkers();
      renderWaypointList();
      await calcRoute();
    } catch {
      showNavMsg(copy.fetchError, true);
    }
  }

  function showNavMsg(msg, isError = false) {
    const el = document.getElementById("nav-msg");
    el.textContent = msg;
    el.style.color = isError ? "var(--danger)" : "var(--gray-700)";
  }

  // ── Init ────────────────────────────────────────────────────────────────────
  buildNavPanel();
  renderWaypointList();
})();
