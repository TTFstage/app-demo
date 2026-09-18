"""Ingestion API: receives telemetry from the client and publishes it to RabbitMQ (no DB persistence)."""
import json
import logging
import os
from threading import Lock
from typing import Annotated
from uuid import UUID

import pika
import requests
from fastapi import Body, FastAPI, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "rabbitmq")
RABBITMQ_PORT = int(os.getenv("RABBITMQ_PORT", "5672"))
RABBITMQ_USER = os.getenv("RABBITMQ_USER", "guest")
RABBITMQ_PASSWORD = os.getenv("RABBITMQ_PASSWORD", "guest")
RABBITMQ_QUEUE = os.getenv("RABBITMQ_QUEUE", "telemetry_stream")

app = FastAPI(title="Sensor Ingest API")


class TelemetryPoint(BaseModel):
    """Single payload accepted from the client: no raw sensor data is forwarded to the server."""

    model_config = ConfigDict(extra="forbid")

    session_id: UUID
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
    speed_kmh: float | None = Field(default=None, ge=0)
    timestamp: float = Field(gt=0)
    is_confirmed_fall: bool = False
    is_cancelled_fall: bool = False


class SessionEnd(BaseModel):
    """Signals the closure of a tracking session: triggers the GPX file close."""

    model_config = ConfigDict(extra="forbid")

    session_id: UUID


class RabbitMQPublisher:
    """Persistent connection to RabbitMQ with automatic reconnection on error."""

    def __init__(self) -> None:
        self._connection: pika.BlockingConnection | None = None
        self._channel = None
        self._lock = Lock()

    def _connect(self) -> None:
        credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASSWORD)
        params = pika.ConnectionParameters(
            host=RABBITMQ_HOST,
            port=RABBITMQ_PORT,
            credentials=credentials,
            heartbeat=30,
        )
        self._connection = pika.BlockingConnection(params)
        self._channel = self._connection.channel()
        self._channel.queue_declare(queue=RABBITMQ_QUEUE, durable=True)
        logger.info("Connected to RabbitMQ (%s:%s), queue '%s' ready.", RABBITMQ_HOST, RABBITMQ_PORT, RABBITMQ_QUEUE)

    def publish(self, body: bytes) -> None:
        # pika.BlockingConnection is not thread-safe. FastAPI executes sync
        # handlers in a thread pool, so all connection access must be serialized.
        with self._lock:
            if self._connection is None or self._connection.is_closed:
                self._connect()
            try:
                self._channel.basic_publish(
                    exchange="",
                    routing_key=RABBITMQ_QUEUE,
                    body=body,
                    properties=pika.BasicProperties(delivery_mode=2, content_type="application/json"),
                )
            except pika.exceptions.AMQPError:
                logger.warning("RabbitMQ connection lost, reconnecting...")
                self._connect()
                self._channel.basic_publish(
                    exchange="",
                    routing_key=RABBITMQ_QUEUE,
                    body=body,
                    properties=pika.BasicProperties(delivery_mode=2, content_type="application/json"),
                )


publisher = RabbitMQPublisher()


def verify_flask_session(request: Request):
    """Verifies the Flask session cookie by calling the internal auth endpoint."""
    cookies = request.headers.get("cookie", "")
    try:
        cookie_dict = {}
        for part in cookies.split(";"):
            if "=" in part:
                k, v = part.strip().split("=", 1)
                cookie_dict[k] = v
        session_cookie = cookie_dict.get("session")
        resp = requests.get(
            "http://web:8000/auth/check_session",
            cookies={"session": session_cookie} if session_cookie else {},
            timeout=2,
        )
        if resp.status_code == 200 and resp.json().get("authenticated"):
            return resp.json()
    except Exception:  # noqa: BLE001
        logger.debug("Failed to verify Flask session cookie")
    raise HTTPException(status_code=401, detail="Invalid or missing session")


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.post("/stream")
def handle_stream(
    points: Annotated[list[TelemetryPoint], Body(max_length=200)], request: Request
):
    session = verify_flask_session(request)
    if not points:
        return {"status": "ok", "count": 0}

    auth_user_id = str(session.get("user_id"))

    try:
        for point in points:
            envelope = {
                "type": "point",
                "user_id": auth_user_id,
                **point.model_dump(mode="json"),
            }
            publisher.publish(json.dumps(envelope).encode("utf-8"))
    except Exception as exc:
        logger.error("Error publishing to RabbitMQ: %s", exc)
        raise HTTPException(status_code=503, detail="Unable to forward data to RabbitMQ") from exc

    return {"status": "ok", "count": len(points)}


@app.post("/session/end")
def handle_session_end(payload: SessionEnd, request: Request):
    """Signals the GPS worker to close the buffer, apply RDP and export the final .gpx file."""
    session = verify_flask_session(request)
    auth_user_id = str(session.get("user_id"))
    try:
        envelope = {
            "type": "session_end",
            "user_id": auth_user_id,
            **payload.model_dump(mode="json"),
        }
        publisher.publish(json.dumps(envelope).encode("utf-8"))
    except Exception as exc:
        logger.error("Error publishing session end to RabbitMQ: %s", exc)
        raise HTTPException(status_code=503, detail="Unable to forward session end to RabbitMQ") from exc

    return {"status": "ok"}
