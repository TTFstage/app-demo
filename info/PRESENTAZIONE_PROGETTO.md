# RoR - Presentazione del progetto

**Rider On Road**  
**Versione documentazione:** 2.1.0  
**Aggiornamento:** 18 settembre 2026

## 1. Obiettivo

RoR è una piattaforma pensata per rider urbani e gruppi di lavoro. Riunisce gestione account, coordinamento di gruppo, mappe, posizione live, telemetria, tracce GPX, analytics ed eventi di sicurezza.

Il progetto separa l'esperienza web dall'elaborazione dei flussi GPS, così l'interfaccia e l'autenticazione restano semplici mentre la telemetria viene gestita in modo asincrono.

## 2. Valore funzionale

- Account e profilo personale protetti.
- Gruppi privati con ruoli `owner`, `admin` e `member`.
- Ingresso tramite codice o link di invito.
- Mappe con punti di interesse per il lavoro su strada.
- Posizione live visibile ai membri autorizzati dello stesso gruppo.
- Registrazione dei turni e generazione di file GPX.
- Analytics sull'attività.
- Gestione di eventi di caduta e contatti SOS.

## 3. Architettura in breve

```text
Browser
   |
   v
Nginx (HTTPS)
   |--------------------|
   v                    v
Flask / Gunicorn     FastAPI / Uvicorn
   |                    |
   |                    v
   |                 RabbitMQ
   |                    |
   |                    v
   |                 GPS worker
   |                    |
   |----------|---------|---------|
              v                   v
          PostgreSQL             Redis
              |
              v
          Volume GPX
```

Sette servizi Docker formano lo stack completo: `db`, `rabbitmq`, `redis`, `web`, `fastapi`, `gps_worker` e `nginx`.

## 4. Flusso di un turno

1. L'utente effettua il login.
2. Il client apre una sessione di telemetria e invia punti GPS.
3. FastAPI verifica la sessione direttamente con Flask.
4. L'identità viene ricavata dalla sessione, non dal payload del client.
5. RabbitMQ accoda i messaggi.
6. Il worker aggiorna la posizione live in Redis e accumula i punti validi.
7. Alla chiusura, il worker genera il GPX, calcola distanza e durata e salva i metadati.
8. La posizione live viene eliminata.

## 5. Scelte di sicurezza

- Password protette con bcrypt.
- Form con CSRF.
- Cookie `HttpOnly`, `SameSite=Lax` e `Secure` su HTTPS.
- Separazione tra reti frontend e backend.
- Database esposto solo su localhost per gli strumenti locali.
- Sessione obbligatoria per gli endpoint telemetrici.
- `.env` e chiavi TLS esclusi dal repository e dalle immagini.
- Audit automatico delle dipendenze Python.

## 6. Stack principale

| Area | Tecnologia validata |
|---|---|
| Web | Flask 3.1.3, Gunicorn 26.2.0 |
| API | FastAPI 0.141.1, Uvicorn 0.34.0 |
| Runtime | Python 3.12 |
| Persistenza | PostgreSQL 15, SQLAlchemy 2.0.52 |
| Messaggistica | RabbitMQ 3.13, Pika 1.3.2 |
| Cache live | Redis 7 |
| Proxy | Nginx Alpine |
| Orchestrazione | Docker Compose |

## 7. Qualità verificata

La copia per il repository privato è stata collaudata il 18 settembre 2026:

- build delle tre immagini applicative superata;
- 14 test automatici superati;
- analisi Ruff superata;
- dipendenze coerenti secondo `pip check`;
- nessuna vulnerabilità nota nei tre insiemi di requisiti;
- avvio completo da volumi vuoti;
- home, login e registrazione raggiungibili in HTTPS;
- API health positiva e accesso anonimo allo stream respinto;
- migrazione database all'head;
- nessun segreto o certificato privato nella distribuzione.

## 8. Cosa serve prima di un uso reale

- Definire titolare, finalità, basi giuridiche e tempi di conservazione.
- Completare la DPIA quando il trattamento previsto presenta rischio elevato.
- Implementare backup, monitoraggio e procedure di incidente.
- Gestire i segreti fuori dal repository.
- Usare un dominio e certificati TLS validi.
- Definire responsabilità e permessi operativi del team.

## 9. Documenti collegati

- `README.md`: panoramica e sviluppo;
- `GITHUB_SETUP.md`: avvio della copia privata;
- `info/DOCUMENTAZIONE_TECNICA.md`: architettura e operazioni;
- `info/DocumentazioneFlask.md`: funzionalità;
- `.env.example`: modello di configurazione senza segreti.
