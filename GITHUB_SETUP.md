# Condivisione privata tra colleghi

Questa copia è destinata a un repository GitHub **privato**. Non contiene `.env`, chiavi TLS, certificati generati, cache o log. La configurazione reale deve restare fuori da Git.

## Primo avvio

1. Copia il modello di configurazione:

   ```powershell
   Copy-Item .env.example .env
   ```

   Su macOS o Linux:

   ```bash
   cp .env.example .env
   ```

2. Sostituisci tutti i valori `change-me` in `.env`. Per generare un segreto casuale:

   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(48))"
   ```

   Genera separatamente `SECRET_KEY`, `SECURITY_PASSWORD_SALT`, `DB_PASSWORD` e `RABBITMQ_PASSWORD`.

3. Genera il certificato locale seguendo `nginx/certs/README.md`.

4. Costruisci e avvia l'intero stack:

   ```bash
   docker compose up -d --build --wait
   ```

5. Apri `https://localhost`. Il certificato di sviluppo è autofirmato, quindi il browser può mostrare un avviso.

## Verifiche rapide

```bash
docker compose ps
docker compose exec -T web flask db current
docker compose logs --tail=100 web fastapi gps_worker nginx
```

La migrazione attesa nella copia validata è `c51a9f0e42d1 (head)`.

## Controlli prima di una pull request

```bash
python -m pytest -q
python -m ruff check . --ignore EXE002
python -m pip check
python -m pip_audit -r requirements.txt
python -m pip_audit -r fastapi_app/requirements.txt
python -m pip_audit -r gps_worker/requirements.txt
```

## Regole di sicurezza

- Non versionare `.env`, `*.pem`, `*.key` o `*.csr`.
- Non riutilizzare i segreti dell'ambiente di sviluppo in staging o produzione.
- Usa i secret del sistema di deployment per gli ambienti condivisi.
- Usa certificati emessi per il dominio reale in produzione.
- Esegui nuovamente test e audit dopo ogni aggiornamento delle dipendenze.

Per spegnere lo stack senza cancellare i dati:

```bash
docker compose down
```

`docker compose down -v` elimina anche i volumi e deve essere usato solo quando si vuole azzerare l'ambiente locale.
