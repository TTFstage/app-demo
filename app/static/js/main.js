// Ride tracking, fall detection and resilient telemetry delivery.
let watchId = null;
let isTracking = false;
let isPaused = false;
let pauseStart = null;
let pausedTotalMs = 0;
let rideMap = null;
let rideLine = null;
let rideMarker = null;
let ridePath = [];
let sendInterval = null;
let flushInterval = null;
let metricInterval = null;
let activeFlush = null;

let lastAcc = null;
let lastGyro = null;
let currentIntervalMs = 50;
let t0 = null;
let lastGps = null;
let lastDistanceGps = null;
let totalDistanceKm = 0;
let lastSuccessfulSync = null;
let sessionId = null;

let headingEstimator = new HeadingEstimator();
let signalProcessor = new SignalProcessor();
let fallDetector = new FallDetector();

const QUEUE_KEY = `ror.telemetry.queue.v1.user-${window.RIDER_ID}`;
const END_QUEUE_KEY = `ror.telemetry.sessionEnds.v1.user-${window.RIDER_ID}`;
const ACTIVE_KEY = `ror.telemetry.active.v1.user-${window.RIDER_ID}`;
const copy = window.ROR_RIDE_COPY || {};
const MAX_QUEUED_POINTS = 8000;
const settings = window.ROR_SETTINGS || {
    telemetryEnabled: true,
    fallDetectionEnabled: true,
    highAccuracyGps: true,
    browserNotificationsEnabled: false,
};

let dataBuffer = loadJson(QUEUE_KEY, []);
let pendingSessionEnds = loadJson(END_QUEUE_KEY, []);
let persistTimer = null;
let sosCountdownTimer = null;
let sosCountdownValue = 10;
let sosLock = false;

function loadJson(key, fallback) {
    try {
        const value = JSON.parse(localStorage.getItem(key));
        return Array.isArray(value) ? value : fallback;
    } catch (error) {
        console.warn(`Unable to read ${key}`, error);
        return fallback;
    }
}

function persistQueues() {
    clearTimeout(persistTimer);
    persistTimer = null;
    try {
        if (dataBuffer.length > MAX_QUEUED_POINTS) {
            dataBuffer = dataBuffer.slice(-MAX_QUEUED_POINTS);
        }
        localStorage.setItem(QUEUE_KEY, JSON.stringify(dataBuffer));
        localStorage.setItem(END_QUEUE_KEY, JSON.stringify(pendingSessionEnds));
    } catch (error) {
        console.error("Unable to preserve the offline queue", error);
    }
    updateMetric("metric-queue", String(dataBuffer.length));
}

function schedulePersist() {
    if (persistTimer !== null) return;
    persistTimer = setTimeout(persistQueues, 300);
}

function csrfToken() {
    return document.querySelector('meta[name="csrf-token"]')?.content || "";
}

function updateMetric(id, value) {
    const element = document.getElementById(id);
    if (element) element.textContent = value;
}

function setRideStatus(message, state = "neutral") {
    const element = document.getElementById("status");
    if (!element) return;
    element.textContent = message;
    element.dataset.state = state;
}

function formatDuration(milliseconds) {
    const seconds = Math.max(0, Math.floor(milliseconds / 1000));
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const remaining = seconds % 60;
    const prefix = hours ? `${String(hours).padStart(2, "0")}:` : "";
    return `${prefix}${String(minutes).padStart(2, "0")}:${String(remaining).padStart(2, "0")}`;
}

function updateLiveMetrics() {
    const elapsed = t0 ? Date.now() - t0 - pausedTotalMs - (isPaused && pauseStart ? Date.now() - pauseStart : 0) : 0;
    updateMetric("metric-duration", formatDuration(elapsed));
    updateMetric("metric-distance", `${totalDistanceKm.toFixed(2)} km`);
    updateMetric(
        "metric-speed",
        lastGps && Number.isFinite(lastGps.speed) ? `${lastGps.speed.toFixed(1)} km/h` : "— km/h",
    );
    updateMetric("metric-gps", lastGps ? copy.locked : copy.waiting);
    updateMetric("metric-network", navigator.onLine ? copy.online : copy.offline);
    updateMetric("metric-queue", String(dataBuffer.length));
    updateMetric(
        "metric-sync",
        lastSuccessfulSync ? lastSuccessfulSync.toLocaleTimeString([], {hour: "2-digit", minute: "2-digit"}) : "—",
    );
}

function haversineKm(a, b) {
    const radians = (degrees) => degrees * Math.PI / 180;
    const earthRadiusKm = 6371;
    const latitudeDelta = radians(b.lat - a.lat);
    const longitudeDelta = radians(b.lon - a.lon);
    const value = Math.sin(latitudeDelta / 2) ** 2
        + Math.cos(radians(a.lat)) * Math.cos(radians(b.lat))
        * Math.sin(longitudeDelta / 2) ** 2;
    return 2 * earthRadiusKm * Math.asin(Math.sqrt(value));
}

function handleMotion(event) {
    if (!isTracking || isPaused) return;
    if (event.accelerationIncludingGravity) lastAcc = event.accelerationIncludingGravity;
    if (event.rotationRate) lastGyro = event.rotationRate;
}

async function flushBuffer() {
    if (activeFlush !== null) return activeFlush;
    if (dataBuffer.length === 0) {
        try {
            return await flushSessionEnds();
        } catch (error) {
            console.error("Session sync failed", error);
            persistQueues();
            return false;
        }
    }
    if (!navigator.onLine) {
        persistQueues();
        setRideStatus(copy.queuedStatus, "warning");
        return false;
    }

    activeFlush = (async () => {
        try {
            while (dataBuffer.length > 0) {
                const payload = dataBuffer.slice(0, 200);
                const response = await fetch("/stream", {
                    method: "POST",
                    headers: {"Content-Type": "application/json"},
                    body: JSON.stringify(payload),
                });
                if (!response.ok) throw new Error(`HTTP ${response.status}`);
                dataBuffer.splice(0, payload.length);
                lastSuccessfulSync = new Date();
                persistQueues();
            }
            if (!await flushSessionEnds()) return false;
            if (isTracking && !isPaused) setRideStatus(copy.liveStatus, "good");
            return true;
        } catch (error) {
            persistQueues();
            console.error("Telemetry sync failed", error);
            setRideStatus(copy.queuedStatus, "warning");
            return false;
        } finally {
            activeFlush = null;
            updateLiveMetrics();
        }
    })();
    return activeFlush;
}

async function sendSessionEnd(id) {
    const response = await fetch("/session/end", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({session_id: id}),
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
}

async function flushSessionEnds() {
    if (!navigator.onLine || dataBuffer.length > 0) return false;
    while (pendingSessionEnds.length > 0) {
        await sendSessionEnd(pendingSessionEnds[0]);
        pendingSessionEnds.shift();
        persistQueues();
    }
    return true;
}

function queueSessionEnd(id) {
    if (id && !pendingSessionEnds.includes(id)) pendingSessionEnds.push(id);
    persistQueues();
}

function startSOSCountdown() {
    if (sosCountdownTimer !== null || sosLock) return;
    sosLock = true;
    document.getElementById("crash-alert").style.display = "flex";
    sosCountdownValue = 10;
    document.getElementById("timer-display").innerText = sosCountdownValue;
    if (navigator.vibrate) navigator.vibrate([500, 200, 500, 200, 500]);

    sosCountdownTimer = setInterval(() => {
        sosCountdownValue -= 1;
        document.getElementById("timer-display").innerText = sosCountdownValue;
        if (sosCountdownValue > 0) {
            if (navigator.vibrate) navigator.vibrate(200);
            return;
        }
        clearInterval(sosCountdownTimer);
        sosCountdownTimer = null;
        sosLock = false;
        document.getElementById("crash-alert").style.display = "none";
        fallDetector.confirmAlert();
        triggerSOS();
    }, 1000);
}

async function triggerSOS() {
    try {
        const response = await fetch("/trigger_sos", {
            method: "POST",
            headers: {"Content-Type": "application/json", "X-CSRFToken": csrfToken()},
            body: JSON.stringify({
                session_id: sessionId,
                occurred_at: new Date().toISOString(),
                coordinates: lastGps ? {latitude: lastGps.lat, longitude: lastGps.lon} : null,
            }),
        });
        const result = await response.json().catch(() => ({}));
        if (!response.ok && response.status !== 202) throw new Error(result.error || `HTTP ${response.status}`);
        const message = result.notification_sent
            ? "SOS notification sent to your emergency provider."
            : `SOS recorded. ${result.detail || "Call emergency services directly."}`;
        if (settings.browserNotificationsEnabled && "Notification" in window
            && Notification.permission === "granted") {
            new Notification("RoR safety alert", {body: message});
        }
        alert(message);
    } catch (error) {
        console.error("SOS request failed", error);
        alert("Unable to record the SOS. Call emergency services directly.");
    }
}

function cancelSOS() {
    document.getElementById("crash-alert").style.display = "none";
    sosLock = false;
    if (sosCountdownTimer !== null) {
        clearInterval(sosCountdownTimer);
        sosCountdownTimer = null;
    }
    fallDetector.resetAlert();
}

function tick() {
    if (!isTracking || isPaused) return;
    if (t0 === null) t0 = Date.now();
    const timeSec = (Date.now() - t0 - pausedTotalMs) / 1000;
    const attitude = headingEstimator.isRunning
        ? headingEstimator.getAttitude()
        : {roll: 0, pitch: 0, yaw: 0};
    let row = {
        time_sec: timeSec,
        acc_x: lastAcc?.x ?? 0,
        acc_y: lastAcc?.y ?? 0,
        acc_z: lastAcc?.z ?? 0,
        gyro_x: lastGyro?.alpha ?? 0,
        gyro_y: lastGyro?.beta ?? 0,
        gyro_z: lastGyro?.gamma ?? 0,
        heading: headingEstimator.isRunning ? headingEstimator.getHeading() : 0,
        roll: attitude.roll,
        pitch: attitude.pitch,
        yaw: attitude.yaw,
        lat: lastGps?.lat ?? null,
        lon: lastGps?.lon ?? null,
        speed_kmh: lastGps?.speed ?? null,
        gps_time: lastGps?.time ?? null,
    };
    row = signalProcessor.process(row);
    if (settings.fallDetectionEnabled) {
        row = fallDetector.process(row);
        if (row.is_confirmed_fall) startSOSCountdown();
    } else {
        row.is_confirmed_fall = false;
        row.is_cancelled_fall = false;
    }

    dataBuffer.push({
        session_id: sessionId,
        lat: row.lat,
        lon: row.lon,
        speed_kmh: row.speed_kmh,
        timestamp: Date.now(),
        is_confirmed_fall: Boolean(row.is_confirmed_fall),
        is_cancelled_fall: Boolean(row.is_cancelled_fall),
    });
    schedulePersist();
}

function setSamplingRate(milliseconds, force = false) {
    if (currentIntervalMs === milliseconds && !force) return;
    currentIntervalMs = milliseconds;
    if (sendInterval !== null) {
        clearInterval(sendInterval);
        sendInterval = setInterval(tick, currentIntervalMs);
    }
    signalProcessor.setSamplingRate(1000 / milliseconds);
    if (isTracking && !isPaused) {
        setRideStatus(
            copy.liveStatus,
            milliseconds > 200 ? "warning" : "good",
        );
    }
}

function saveActiveRide() {
    if (!isTracking || !sessionId) return;
    try {
        localStorage.setItem(ACTIVE_KEY, JSON.stringify({
            sessionId, t0, totalDistanceKm, lastGps, lastDistanceGps,
            pausedTotalMs, pauseStart, isPaused, ridePath: ridePath.slice(-500), savedAt: Date.now(),
        }));
    } catch (error) { console.warn("Unable to save ride checkpoint", error); }
}

function updateRideControls() {
    document.getElementById("btn-start").hidden = isTracking;
    document.getElementById("btn-pause").hidden = !isTracking || isPaused;
    document.getElementById("btn-resume").hidden = !isTracking || !isPaused;
    document.getElementById("btn-stop").hidden = !isTracking;
    document.getElementById("ride-sos").hidden = !isTracking;
    document.getElementById("ride-close").hidden = isTracking;
    document.getElementById("ride-phase").textContent = !isTracking ? copy.ready : isPaused ? copy.paused : copy.live;
}

function initRideMap() {
    if (rideMap || typeof L === "undefined") return;
    rideMap = L.map("ride-map", {zoomControl: false, attributionControl: false}).setView([45.4642, 9.1900], 13);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {maxZoom: 19}).addTo(rideMap);
    rideLine = L.polyline(ridePath.map((point) => [point.lat, point.lon]), {color: "#ff5b2e", weight: 5}).addTo(rideMap);
    if (lastGps) showRidePosition(lastGps);
}

function showRidePosition(point) {
    if (!rideMap) return;
    const position = [point.lat, point.lon];
    if (!rideMarker) rideMarker = L.circleMarker(position, {radius: 8, color: "#fff", weight: 3, fillColor: "#ff5b2e", fillOpacity: 1}).addTo(rideMap);
    else rideMarker.setLatLng(position);
    rideMap.panTo(position);
}

function openRideScreen() {
    const screen = document.getElementById("ride-screen");
    if (!screen) return;
    screen.hidden = false;
    document.body.classList.add("ride-open");
    updateRideControls();
    initRideMap();
    setTimeout(() => rideMap?.invalidateSize(), 50);
}

function closeRideScreen() {
    if (isTracking) return;
    document.getElementById("ride-screen").hidden = true;
    document.body.classList.remove("ride-open");
}

function showFinishConfirm() { document.getElementById("ride-confirm").hidden = false; }
function hideFinishConfirm() { document.getElementById("ride-confirm").hidden = true; }
function showSOSConfirm() { if (confirm(copy.sosConfirm)) triggerSOS(); }

function stopSensors() {
    window.removeEventListener("devicemotion", handleMotion);
    if (watchId !== null) navigator.geolocation.clearWatch(watchId);
    watchId = null;
    clearInterval(sendInterval);
    sendInterval = null;
    headingEstimator.stop();
}

function handlePosition(position) {
    if (!isTracking || isPaused) return;
    const nextGps = {
        lat: position.coords.latitude, lon: position.coords.longitude,
        speed: position.coords.speed !== null ? Math.max(0, position.coords.speed * 3.6) : null,
        time: position.timestamp || Date.now(), accuracy: position.coords.accuracy,
    };
    if (lastDistanceGps && nextGps.accuracy <= 100) {
        const segment = haversineKm(lastDistanceGps, nextGps);
        if (segment < 1) totalDistanceKm += segment;
    }
    if (nextGps.accuracy <= 100) lastDistanceGps = nextGps;
    lastGps = nextGps;
    if (nextGps.accuracy <= 100) {
        ridePath.push({lat: nextGps.lat, lon: nextGps.lon});
        rideLine?.addLatLng([nextGps.lat, nextGps.lon]);
    }
    showRidePosition(nextGps);
    saveActiveRide();
    updateLiveMetrics();
    if (Number.isFinite(position.coords.speed)) setSamplingRate(position.coords.speed < 0.6 ? 1000 : 50);
}

function startSensors() {
    setSamplingRate(50, true);
    headingEstimator.start();
    window.addEventListener("devicemotion", handleMotion);
    watchId = navigator.geolocation.watchPosition(handlePosition, (error) => {
        console.error("GPS error", error);
        updateMetric("metric-gps", copy.unavailable);
        setRideStatus(copy.locationError, "bad");
    }, {enableHighAccuracy: Boolean(settings.highAccuracyGps), maximumAge: 3000, timeout: 15000});
    sendInterval = setInterval(tick, currentIntervalMs);
}

async function startTracking() {
    if (isTracking) return;
    openRideScreen();
    if (!settings.telemetryEnabled) return setRideStatus(copy.telemetryOff, "warning");
    if (!("geolocation" in navigator)) return setRideStatus(copy.locationError, "bad");
    const button = document.getElementById("btn-start");
    button.disabled = true;
    try {
        const motionPermission = await HeadingEstimator.requestPermissions();
        if (!motionPermission && typeof DeviceMotionEvent !== "undefined"
            && typeof DeviceMotionEvent.requestPermission === "function") return setRideStatus(copy.motionError, "bad");
        const firstPosition = await new Promise((resolve, reject) => navigator.geolocation.getCurrentPosition(resolve, reject, {
            enableHighAccuracy: Boolean(settings.highAccuracyGps), maximumAge: 3000, timeout: 15000,
        }));
        isTracking = true;
        isPaused = false;
        pauseStart = null;
        pausedTotalMs = 0;
        sosLock = false;
        sessionId = window.crypto?.randomUUID ? window.crypto.randomUUID()
            : "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (character) => {
                const random = Math.random() * 16 | 0;
                return (character === "x" ? random : (random & 0x3 | 0x8)).toString(16);
            });
        fallDetector.is_cancelled_fall = false;
        totalDistanceKm = 0;
        lastDistanceGps = null;
        lastGps = null;
        ridePath = [];
        rideLine?.setLatLngs([]);
        t0 = Date.now();
        startSensors();
        handlePosition(firstPosition);
        flushInterval = setInterval(flushBuffer, 500);
        metricInterval = setInterval(() => {updateLiveMetrics(); saveActiveRide();}, 1000);
        setRideStatus(copy.liveStatus, "good");
        updateRideControls();
    } catch (error) {
        console.error("Ride start failed", error);
        setRideStatus(copy.locationError, "bad");
    } finally { button.disabled = false; }
}

function pauseTracking() {
    if (!isTracking || isPaused) return;
    isPaused = true;
    pauseStart = Date.now();
    stopSensors();
    saveActiveRide();
    setRideStatus(copy.pausedStatus, "warning");
    updateRideControls();
    updateLiveMetrics();
}

async function resumeTracking() {
    if (!isTracking || !isPaused) return;
    const button = document.getElementById("btn-resume");
    button.disabled = true;
    try {
        const position = await new Promise((resolve, reject) => navigator.geolocation.getCurrentPosition(resolve, reject, {
            enableHighAccuracy: Boolean(settings.highAccuracyGps), maximumAge: 3000, timeout: 15000,
        }));
        pausedTotalMs += Date.now() - pauseStart;
        pauseStart = null;
        isPaused = false;
        lastDistanceGps = null;
        startSensors();
        handlePosition(position);
        saveActiveRide();
        setRideStatus(copy.liveStatus, "good");
        updateRideControls();
    } catch (error) {
        console.error("Ride resume failed", error);
        setRideStatus(copy.locationError, "bad");
    } finally { button.disabled = false; }
}

async function stopTracking() {
    if (!isTracking) return;
    hideFinishConfirm();
    isTracking = false;
    isPaused = false;
    stopSensors();
    clearInterval(flushInterval);
    clearInterval(metricInterval);
    flushInterval = null;
    metricInterval = null;
    const closingSessionId = sessionId;
    sessionId = null;
    localStorage.removeItem(ACTIVE_KEY);
    queueSessionEnd(closingSessionId);
    updateRideControls();
    setRideStatus(copy.queuedStatus, "neutral");
    const sent = await flushBuffer();
    setRideStatus(sent ? copy.saved : copy.queuedStatus, sent ? "good" : "warning");
    updateLiveMetrics();
}

window.addEventListener("online", () => {
    updateMetric("metric-network", copy.online);
    flushBuffer();
});
window.addEventListener("offline", () => {
    updateMetric("metric-network", copy.offline);
    persistQueues();
    setRideStatus(copy.queuedStatus, "warning");
});
window.addEventListener("pagehide", () => {
    if (isTracking && sessionId) {
        stopSensors();
        if (!isPaused) {
            isPaused = true;
            pauseStart = Date.now();
        }
        saveActiveRide();
    }
    persistQueues();
});

function updateHomeGpsPermission() {
    const element = document.getElementById("home-gps-status");
    if (!element) return;
    const labels = window.ROR_HOME_COPY || {};
    const badge = document.getElementById("home-ride-state-label");
    const setBadge = (label) => {
        if (badge) badge.textContent = settings.telemetryEnabled ? label : labels.badgeTelemetryOff;
    };
    if (!navigator.geolocation || !window.isSecureContext) {
        element.textContent = labels.gpsUnavailable || "Unavailable";
        setBadge(labels.badgeUnavailable);
        return;
    }
    if (!navigator.permissions?.query) {
        element.textContent = labels.gpsCheck || "Check at ride start";
        setBadge(labels.badgeCheck);
        return;
    }
    navigator.permissions.query({name: "geolocation"}).then((permission) => {
        const render = () => {
            element.textContent = permission.state === "granted"
                ? labels.gpsAllowed
                : permission.state === "denied" ? labels.gpsBlocked : labels.gpsCheck;
            setBadge(permission.state === "granted"
                ? labels.badgeAllowed
                : permission.state === "denied" ? labels.badgeBlocked : labels.badgeCheck);
            element.dataset.state = permission.state;
        };
        render();
        permission.onchange = render;
    }).catch(() => {
        element.textContent = labels.gpsCheck || "Check at ride start";
        setBadge(labels.badgeCheck);
    });
}

document.addEventListener("DOMContentLoaded", () => {
    updateHomeGpsPermission();
    if (window.RIDER_ID && document.getElementById("ride-screen")) {
        try {
            const saved = JSON.parse(localStorage.getItem(ACTIVE_KEY) || "null");
            if (saved && saved.sessionId && Number.isFinite(saved.t0)) {
                sessionId = saved.sessionId;
                t0 = saved.t0;
                totalDistanceKm = saved.totalDistanceKm || 0;
                lastGps = saved.lastGps || null;
                lastDistanceGps = null;
                pausedTotalMs = saved.pausedTotalMs || 0;
                pauseStart = saved.isPaused && saved.pauseStart ? saved.pauseStart : saved.savedAt || Date.now();
                isTracking = true;
                isPaused = true;
                ridePath = Array.isArray(saved.ridePath) ? saved.ridePath : [];
                flushInterval = setInterval(flushBuffer, 500);
                metricInterval = setInterval(() => {updateLiveMetrics(); saveActiveRide();}, 1000);
                openRideScreen();
                setRideStatus(copy.recover, "warning");
            }
        } catch (error) { console.warn("Unable to restore ride", error); }
        const route = new URL(window.location.href);
        if (route.searchParams.has("record")) {
            route.searchParams.delete("record");
            window.history.replaceState({}, "", route.pathname + route.search + route.hash);
            openRideScreen();
        }
    }
    updateLiveMetrics();
    if (navigator.getBattery) {
        navigator.getBattery().then((battery) => {
            const renderBattery = () => updateMetric(
                "metric-battery",
                `${Math.round(battery.level * 100)}%${battery.charging ? ` · ${copy.charging}` : ""}`,
            );
            renderBattery();
            battery.addEventListener("levelchange", renderBattery);
            battery.addEventListener("chargingchange", renderBattery);
        }).catch(() => updateMetric("metric-battery", "Unavailable"));
    }
    if (navigator.onLine && dataBuffer.length > 0) flushBuffer();
});
