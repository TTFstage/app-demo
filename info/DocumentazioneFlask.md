# RoR - Documentazione funzionale

**Versione:** 2.1.0  
**Aggiornamento:** 18 settembre 2026  
**Ambito:** funzionalità visibili e comportamento applicativo

## 1. Panoramica

RoR (Rider On Road) supporta l'attività di rider e gruppi di lavoro attraverso account protetti, mappe, condivisione temporanea della posizione, telemetria GPS, tracce GPX, analytics, rilevamento di caduta e contatti SOS.

L'interfaccia web è fornita da Flask. La telemetria passa attraverso FastAPI, RabbitMQ e un worker dedicato, senza esporre direttamente database, cache o broker.

## 2. Account e profilo

Gli utenti possono:

- registrarsi con email e username;
- autenticarsi e terminare la sessione;
- visualizzare il profilo in `/auth/me`;
- gestire i dati anagrafici previsti dal modello utente;
- configurare contatti SOS;
- cancellare il proprio account tramite un'azione protetta.

Flask-Security-Too gestisce autenticazione e sessioni. Le password non vengono archiviate in chiaro.

## 3. Gruppi e ruoli

Ogni gruppo ha membri e permessi interni:

- `owner`: proprietario del gruppo;
- `admin`: amministratore delegato;
- `member`: membro standard.

Le funzioni disponibili comprendono creazione, ingresso tramite codice o token, gestione dei link di invito, modifica dei ruoli e consultazione dei membri.

La posizione live di un utente può essere richiesta soltanto da un altro membro dello stesso gruppo. Questa autorizzazione è distinta dai ruoli globali dell'applicazione.

## 4. Mappe e punti di interesse

La sezione mappa visualizza dati cartografici e punti di interesse come:

- fontanelle;
- servizi igienici;
- punti di riparazione biciclette;
- parcheggi per biciclette.

Quando il contesto di gruppo è disponibile, la mappa aggiorna periodicamente la posizione dei membri autorizzati.

## 5. Telemetria GPS

Il client invia punti a `POST /stream`. Ogni richiesta richiede una sessione Flask valida.

FastAPI:

1. verifica il cookie chiamando il servizio web interno;
2. usa l'identificativo dell'utente autenticato;
3. valida coordinate, velocità, timestamp e indicatori di caduta;
4. pubblica i messaggi nella coda RabbitMQ.

Il GPS worker:

- aggiorna la posizione live in Redis;
- conserva la posizione per un massimo predefinito di 90 secondi;
- registra gli eventi di caduta confermati con coordinate valide;
- accumula i punti per sessione;
- genera il file GPX alla chiusura del turno;
- calcola distanza e durata;
- salva i metadati del turno in PostgreSQL;
- elimina la posizione live al termine della sessione.

## 6. Tracce e analytics

Le tracce concluse vengono salvate nel volume GPX. I metadati permettono di collegare ogni sessione al proprietario, alla distanza e alla durata.

Le sezioni analytics espongono riepiloghi temporali dell'attività. Il download GPX è protetto e deve rispettare la titolarità del turno.

## 7. Sicurezza percepibile dall'utente

- Login, registrazione e azioni sensibili usano protezione CSRF.
- I cookie sono `HttpOnly`, `SameSite=Lax` e `Secure` nell'ambiente HTTPS distribuito.
- Le richieste telemetriche senza sessione restituiscono `401`.
- L'identità dei messaggi non viene accettata dal payload client.
- Il traffico HTTP viene reindirizzato a HTTPS.

Il certificato autofirmato descritto nella guida serve esclusivamente per lo sviluppo locale.

## 8. Dati trattati

Le principali categorie sono:

- dati account e anagrafici;
- appartenenza e ruolo nei gruppi;
- contatti SOS;
- posizione live temporanea;
- tracce GPX e metadati del turno;
- eventi di caduta confermati.

Le politiche definitive di conservazione, cancellazione ed export devono essere definite prima di un uso reale con utenti.

## 9. Componenti operativi

Lo stack Docker comprende sette servizi:

1. PostgreSQL;
2. RabbitMQ;
3. Redis;
4. applicazione Flask/Gunicorn;
5. API FastAPI/Uvicorn;
6. GPS worker;
7. Nginx.

Lo script di avvio del servizio web attende il database, applica le migrazioni e poi avvia Gunicorn.

## 10. Stato della build condivisibile

La copia interna del 18 settembre 2026 è stata verificata con:

- 14 test automatici superati;
- build completa delle immagini;
- avvio pulito di tutti i servizi;
- controllo delle rotte web e API;
- verifica della migrazione database;
- audit delle dipendenze senza vulnerabilità note;
- scansione anti-segreti della cartella e dell'immagine web.

I dettagli tecnici e i comandi operativi sono in `DOCUMENTAZIONE_TECNICA.md` e `GITHUB_SETUP.md`.
