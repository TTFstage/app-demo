# Certificati TLS locali

Questa directory deve contenere solo certificati generati localmente. Le chiavi private non vanno mai caricate su GitHub.

Con OpenSSL disponibile nel terminale, dalla radice del progetto esegui:

```bash
openssl req -x509 -nodes -newkey rsa:2048 \
  -keyout nginx/certs/privkey.pem \
  -out nginx/certs/fullchain.pem \
  -days 365 \
  -config nginx/certs/req.cnf \
  -extensions v3_req
```

Il file `req.cnf` imposta `localhost` e `127.0.0.1` come nomi validi per lo sviluppo. In produzione usa un certificato emesso per il dominio reale e gestisci la chiave tramite il sistema di secret del deployment.

Al termine devono esistere localmente questi file, entrambi ignorati da Git:

- `nginx/certs/fullchain.pem`
- `nginx/certs/privkey.pem`

Verifica la configurazione prima dell'avvio:

```bash
docker compose config --quiet
```

Non usare il certificato autofirmato in produzione e non condividere mai `privkey.pem` tramite chat, email o repository.
