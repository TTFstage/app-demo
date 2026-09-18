// Ride tracking, fall detection and resilient telemetry delivery.
let watchId = null;
let isTracking = false;
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
    element.textContent = `Status: ${message}`;
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
    updateMetric("metric-duration", t0 ? formatDuration(Date.now() - t0) : "00:00");
    updateMetric("metric-distance", `${totalDistanceKm.toFixed(2)} km`);
    updateMetric(
        "metric-speed",
        lastGps && Number.isFinite(lastGps.speed) ? `${lastGps.speed.toFixed(1)} km/h` : "— km/h",
    );
    updateMetric("metric-gps", lastGps ? "Locked" : "Waiting");
    updateMetric("metric-network", navigator.onLine ? "Online" : "Offline");
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
    if (!isTracking) return;
    if (event.accelerationIncludingGravity) lastAcc = event.accelerationIncludingGravity;
    if (event.rotationRate) lastGyro = event.rotationRate;
}

async function flushBuffer() {
    if (activeFlush !== null) return activeFlush;
    if (dataBuffer.length === 0) {
        try {
            await flushSessionEnds();
            return true;
        } catch (error) {
            console.error("Session sync failed", error);
            persistQueues();
            return false;
        }
    }
    if (!navigator.onLine) {
        persistQueues();
        setRideStatus("Offline — ride data is safely queued on this phone.", "warning");
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
            await flushSessionEnds();
            if (isTracking) setRideStatus("Live and synced.", "good");
            return true;
        } catch (error) {
            persistQueues();
            console.error("Telemetry sync failed", error);
            setRideStatus("Connection unavailable — data is queued for retry.", "warning");
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
    if (!isTracking) return;
    if (t0 === null) t0 = Date.now();
    const timeSec = (Date.now() - t0) / 1000;
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
    if (isTracking) {
        setRideStatus(
            milliseconds > 200 ? "Paused or stopped — battery saving mode." : "Moving — high precision tracking.",
            milliseconds > 200 ? "warning" : "good",
        );
    }
}

async function startTracking() {
    if (isTracking) return;
    if (!settings.telemetryEnabled) {
        setRideStatus("Ride telemetry is disabled in Settings.", "warning");
        return;
    }
    if (!("geolocation" in navigator)) {
        setRideStatus("This browser does not provide location access.", "bad");
        return;
    }

    const motionPermission = await HeadingEstimator.requestPermissions();
    if (!motionPermission && typeof DeviceMotionEvent !== "undefined"
        && typeof DeviceMotionEvent.requestPermission === "function") {
        setRideStatus("Motion permission was not granted.", "bad");
        return;
    }

    isTracking = true;
    sosLock = false;
    sessionId = window.crypto?.randomUUID
        ? window.crypto.randomUUID()
        : "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (character) => {
            const random = Math.random() * 16 | 0;
            const value = character === "x" ? random : (random & 0x3 | 0x8);
            return value.toString(16);
        });
    fallDetector.is_cancelled_fall = false;
    totalDistanceKm = 0;
    lastDistanceGps = null;
    lastGps = null;
    t0 = Date.now();

    const startButton = document.getElementById("btn-start");
    const stopButton = document.getElementById("btn-stop");
    startButton.style.display = "none";
    startButton.disabled = true;
    stopButton.style.display = "inline-block";
    stopButton.disabled = false;
    setSamplingRate(50, true);
    headingEstimator.start();
    window.addEventListener("devicemotion", handleMotion);

    watchId = navigator.geolocation.watchPosition((position) => {
        if (!isTracking) return;
        const nextGps = {
            lat: position.coords.latitude,
            lon: position.coords.longitude,
            speed: position.coords.speed !== null ? Math.max(0, position.coords.speed * 3.6) : null,
            time: position.timestamp || Date.now(),
            accuracy: position.coords.accuracy,
        };
        if (lastDistanceGps && nextGps.accuracy <= 100) {
            const segment = haversineKm(lastDistanceGps, nextGps);
            if (segment < 1) totalDistanceKm += segment;
        }
        if (nextGps.accuracy <= 100) lastDistanceGps = nextGps;
        lastGps = nextGps;
        updateLiveMetrics();
        if (Number.isFinite(position.coords.speed)) {
            setSamplingRate(position.coords.speed < 0.6 ? 1000 : 50);
        }
    }, (error) => {
        console.error("GPS error", error);
        updateMetric("metric-gps", "Unavailable");
        setRideStatus("Location unavailable — check this phone's permission.", "bad");
    }, {
        enableHighAccuracy: Boolean(settings.highAccuracyGps),
        maximumAge: 3000,
        timeout: 15000,
    });

    sendInterval = setInterval(tick, currentIntervalMs);
    flushInterval = setInterval(flushBuffer, 500);
    metricInterval = setInterval(updateLiveMetrics, 1000);
    updateLiveMetrics();
}

function stopTracking() {
    if (!isTracking) return;
    isTracking = false;
    window.removeEventListener("devicemotion", handleMotion);
    if (watchId !== null) navigator.geolocation.clearWatch(watchId);
    watchId = null;
    clearInterval(sendInterval);
    clearInterval(flushInterval);
    clearInterval(metricInterval);
    sendInterval = null;
    flushInterval = null;
    metricInterval = null;
    headingEstimator.stop();

    const closingSessionId = sessionId;
    sessionId = null;
    setRideStatus("Finishing and saving your ride…", "neutral");
    flushBuffer().then(async (sent) => {
        if (sent && closingSessionId) {
            try {
                await sendSessionEnd(closingSessionId);
                lastSuccessfulSync = new Date();
                setRideStatus("Ride saved.", "good");
            } catch (error) {
                console.error("Session close failed", error);
                queueSessionEnd(closingSessionId);
                setRideStatus("Ride saved locally and queued for sync.", "warning");
            }
        } else if (closingSessionId) {
            queueSessionEnd(closingSessionId);
            setRideStatus("Ride saved locally and queued for sync.", "warning");
        }
        updateLiveMetrics();
    });

    const startButton = document.getElementById("btn-start");
    const stopButton = document.getElementById("btn-stop");
    stopButton.style.display = "none";
    stopButton.disabled = true;
    startButton.style.display = "inline-block";
    startButton.disabled = false;
    updateLiveMetrics();
}

window.addEventListener("online", () => {
    updateMetric("metric-network", "Online");
    setRideStatus("Back online — syncing queued ride data…", "good");
    flushBuffer();
});
window.addEventListener("offline", () => {
    updateMetric("metric-network", "Offline");
    persistQueues();
    setRideStatus("Offline — ride data is safely queued on this phone.", "warning");
});
window.addEventListener("pagehide", () => {
    if (isTracking && sessionId) queueSessionEnd(sessionId);
    persistQueues();
});

document.addEventListener("DOMContentLoaded", () => {
    updateLiveMetrics();
    if (navigator.getBattery) {
        navigator.getBattery().then((battery) => {
            const renderBattery = () => updateMetric(
                "metric-battery",
                `${Math.round(battery.level * 100)}%${battery.charging ? " · charging" : ""}`,
            );
            renderBattery();
            battery.addEventListener("levelchange", renderBattery);
            battery.addEventListener("chargingchange", renderBattery);
        }).catch(() => updateMetric("metric-battery", "Unavailable"));
    }
    if (navigator.onLine && dataBuffer.length > 0) flushBuffer();
});
