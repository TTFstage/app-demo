# RoR - Documentazione tecnica

**Versione documento:** 2.1.0  
**Aggiornamento:** 18 settembre 2026  
**Destinazione:** condivisione interna in repository GitHub privato  
**Stato verificato:** build Docker, test automatici, audit dipendenze e avvio completo superati

## 1. Scopo del sistema

RoR (Rider On Road) è una piattaforma per rider che combina gestione utenti e gruppi, mappe, analytics, telemetria GPS, generazione di tracce GPX, posizione live ed eventi di caduta.

L'architettura è ibrida:

- Flask gestisce interfaccia web, account, sessioni, gruppi e autorizzazioni.
- FastAPI riceve la telemetria e la pubblica su RabbitMQ.
- Il GPS worker consuma la coda, aggiorna Redis, genera GPX e salva i metadati in PostgreSQL.
- Nginx espone HTTP/HTTPS e inoltra le richieste ai servizi interni.

## 2. Stack validato

| Componente | Versione o immagine | Responsabilità |
|---|---:|---|
| Python | 3.12 (`python:3.12-slim`) | Runtime dei tre servizi applicativi |
| Flask | 3.1.3 | Applicazione web WSGI |
| Flask-Security-Too | 5.8.2 | Registrazione, login, sessioni e ruoli |
| Gunicorn | 26.2.0 | Server WSGI del servizio web |
| FastAPI | 0.141.1 | API di ingestione telemetria |
| Starlette | 1.6.0, dipendenza FastAPI | Layer ASGI |
| Uvicorn | 0.34.0 | Server ASGI |
| Pydantic | 2.10.4 | Validazione dei payload |
| Requests | 2.34.2 | Verifica interna della sessione Flask |
| Pika | 1.3.2 | Client RabbitMQ |
| PostgreSQL | `postgres:15-alpine` | Persistenza relazionale |
| SQLAlchemy | 2.0.52 | ORM |
| psycopg | 3.3.4 | Driver PostgreSQL |
| RabbitMQ | `rabbitmq:3.13-management` | Coda durevole della telemetria |
| Redis | `redis:7-alpine` / client 5.2.1 | Cache della posizione live |
| Nginx | `nginx:alpine` | TLS e reverse proxy |
| pip | 26.2.1 nelle immagini | Installazione delle dipendenze |

I file `requirements.txt`, `fastapi_app/requirements.txt` e `gps_worker/requirements.txt` sono la fonte definitiva per le versioni Python.

## 3. Servizi Docker

| Servizio | Rete | Dati persistenti | Dipendenze di avvio |
|---|---|---|---|
| `db` | backend | `postgres_data` | healthcheck PostgreSQL |
| `rabbitmq` | backend | `rabbitmq_data` | healthcheck sulle porte RabbitMQ |
| `redis` | backend | `redis_data` | healthcheck `PING` |
| `web` | frontend, backend | `gpx_storage` | database e Redis sani |
| `fastapi` | frontend, backend | nessuno | RabbitMQ sano e web avviato |
| `gps_worker` | backend | `gpx_storage` | RabbitMQ, database e Redis sani |
| `nginx` | frontend | certificati montati in sola lettura | web e FastAPI avviati |

PostgreSQL è pubblicato soltanto su `127.0.0.1:5433`. Le porte applicative interne non sono pubblicate direttamente; l'accesso esterno passa da Nginx sulle porte 80 e 443.

## 4. Flusso della telemetria

1. Il client invia una lista di punti a `POST /stream` oppure chiude il turno con `POST /session/end`.
2. FastAPI estrae il cookie di sessione e chiama internamente `GET /auth/check_session` sul servizio Flask.
3. Se la sessione è assente o non valida, FastAPI restituisce `401`.
4. L'identificativo utente viene preso esclusivamente dalla sessione autenticata e aggiunto al messaggio. Il client non può attribuire dati a un altro utente.
5. Il messaggio `point` o `session_end` viene pubblicato nella coda durevole `telemetry_stream`.
6. Il worker aggiorna `position:{user_id}` in Redis con TTL configurabile, predefinito a 90 secondi.
7. I punti validi vengono accumulati e, alla chiusura, semplificati con Ramer-Douglas-Peucker e scritti in un file GPX.
8. Il worker salva i metadati del turno in `rider_shifts`, registra le cadute confermate in `fall_events` e rimuove la posizione live alla chiusura.

### Payload punto

Il modello `TelemetryPoint` accetta:

- `session_id`: UUID obbligatorio;
- `lat`: valore opzionale compreso tra -90 e 90;
- `lon`: valore opzionale compreso tra -180 e 180;
- `speed_kmh`: valore opzionale non negativo;
- `timestamp`: numero positivo;
- `is_confirmed_fall` e `is_cancelled_fall`: booleani.

I campi non dichiarati vengono rifiutati. I punti privi di coordinate valide non vengono inseriti nel GPX né nella cache live.

## 5. Web, utenti e gruppi

L'applicazione Flask usa Application Factory e Blueprint. Le aree principali sono:

- home e navigazione;
- registrazione, login, profilo e cancellazione account;
- gruppi con ruoli `owner`, `admin` e `member`;
- mappe e punti di interesse;
- analytics e download GPX;
- contatti SOS;
- endpoint interno di verifica sessione.

La posizione di un membro è disponibile solo quando richiedente e destinatario appartengono allo stesso gruppo. Il dato viene letto da Redis e scompare alla chiusura del turno o alla scadenza del TTL.

## 6. Sicurezza applicativa

- Le password sono memorizzate con hash bcrypt tramite Flask-Security-Too.
- Le form usano protezione CSRF.
- I cookie di sessione e remember sono `HttpOnly`, `SameSite=Lax` e, nella configurazione distribuita, `Secure`.
- FastAPI ignora qualsiasi identità proposta dal client e usa l'utente della sessione Flask.
- Nginx reindirizza HTTP verso HTTPS e aggiunge HSTS, `X-Content-Type-Options` e `X-Frame-Options`.
- `.env`, chiavi private e certificati generati sono esclusi da Git e dal contesto Docker.
- I messaggi non validi vengono rifiutati senza retry; gli errori transitori vengono rimessi in coda.

Il certificato incluso nelle istruzioni è solo per sviluppo locale. Un ambiente reale deve usare un certificato valido e un sistema esterno di gestione dei segreti.

## 7. Configurazione

Creare `.env` partendo da `.env.example`. Le variabili obbligatorie sono:

- `SECRET_KEY` e `SECURITY_PASSWORD_SALT`;
- `DB_USER`, `DB_PASSWORD`, `DB_NAME`;
- `RABBITMQ_USER`, `RABBITMQ_PASSWORD`, `RABBITMQ_QUEUE`.

Le principali variabili operative sono:

| Variabile | Predefinito | Uso |
|---|---:|---|
| `POSITION_TTL` | 90 | Durata della posizione live in Redis, in secondi |
| `BUFFER_SIZE` | 50 | Numero di punti prima del flush temporaneo |
| `RDP_EPSILON` | 0.00004 | Tolleranza della semplificazione GPX |
| `RABBITMQ_PORT` | 5672 | Porta AMQP interna |
| `REDIS_PORT` | 6379 | Porta Redis interna |
| `SESSION_COOKIE_SECURE` | true | Invio del cookie solo tramite HTTPS |
| `REMEMBER_COOKIE_SECURE` | true | Invio del cookie remember solo tramite HTTPS |
| `FLASK_DEBUG` | false | Debug Flask; non abilitarlo in ambienti condivisi |

Non inserire segreti reali nel modello `.env.example`.

## 8. Avvio e operazioni

```bash
docker compose up -d --build --wait
docker compose ps
```

Applicazione: `https://localhost`  
Login: `https://localhost/login`  
Registrazione: `https://localhost/register`

Log principali:

```bash
docker compose logs -f web fastapi gps_worker nginx
```

Stato migrazioni:

```bash
docker compose exec -T web flask db current
```

Spegnimento senza cancellare i dati:

```bash
docker compose down
```

`docker compose down -v` elimina i volumi PostgreSQL, RabbitMQ, Redis e GPX; usarlo solo per un reset intenzionale dell'ambiente locale.

## 9. Qualità e stato dell'ultima verifica

Verifica eseguita il 18 settembre 2026 sulla copia condivisibile:

| Controllo | Esito |
|---|---|
| Build delle immagini `web`, `fastapi`, `gps_worker` | superata |
| Test automatici | 14 superati |
| Ruff | superato con esclusione documentata `EXE002` |
| `pip check` | nessuna incompatibilità |
| `pip-audit` sui tre file dei requisiti | nessuna vulnerabilità nota |
| Avvio dei sette servizi da volumi vuoti | superato |
| Home, login e registrazione HTTPS | `200` |
| Redirect HTTP verso HTTPS | `301` |
| API health interna | `{"status":"ok"}` |
| `/stream` senza sessione | `401` |
| Migrazione database | `c51a9f0e42d1 (head)` |
| Scansione di file e immagine Docker | nessun segreto o chiave privata |

## 10. Limiti e decisioni prima della produzione

- Definire conservazione, export e cancellazione per GPX, eventi di caduta e dati di gruppo.
- Eseguire una valutazione privacy/DPIA adeguata al trattamento reale.
- Configurare backup, monitoraggio, alerting e gestione centralizzata dei segreti.
- Sostituire i certificati locali con certificati validi per il dominio.
- Valutare rate limiting, limiti di coda, rotazione log e osservabilità.
- Bloccare o documentare anche la versione di `pandas`, attualmente non fissata in `requirements.txt`, se serve riproducibilità assoluta.

## 11. File di riferimento

- `README.md`: panoramica e guida di sviluppo;
- `GITHUB_SETUP.md`: avvio sicuro per i colleghi;
- `.env.example`: modello delle variabili;
- `docker-compose.yml`: orchestrazione;
- `fastapi_app/main.py`: ingestione e verifica sessione;
- `gps_worker/worker_consumer.py`: consumo coda e persistenza;
- `nginx/nginx.conf`: reverse proxy e TLS;
- `migrations/`: schema e cronologia del database.
