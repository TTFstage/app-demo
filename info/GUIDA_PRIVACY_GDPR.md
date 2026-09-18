# RoR - Guida progettuale privacy e GDPR

**Aggiornamento:** 18 settembre 2026  
**Ambito:** promemoria tecnico-organizzativo per la progettazione  
**Avvertenza:** questo documento non è consulenza legale e non certifica la conformità del servizio.

## 1. Perché la privacy è centrale

RoR può trattare dati account, dati anagrafici, appartenenza a gruppi, contatti SOS, posizione live, tracce GPX ed eventi di caduta. La geolocalizzazione permette di ricostruire spostamenti, orari e abitudini; richiede quindi misure proporzionate al contesto e alle finalità reali.

La posizione non è automaticamente una categoria particolare di dati ai sensi dell'articolo 9 GDPR, ma può comportare rischi elevati e può rivelare indirettamente informazioni molto delicate.

## 2. Stato tecnico attuale

| Dato | Dove viene trattato | Comportamento attuale |
|---|---|---|
| Account e anagrafica | PostgreSQL | conservati fino a cancellazione o altra regola applicativa |
| Ruoli e gruppi | PostgreSQL | autorizzano funzioni e visibilità tra membri |
| Posizione live | Redis | TTL predefinito di 90 secondi; eliminata anche a fine turno |
| Traccia GPX | volume Docker | prodotta alla chiusura della sessione |
| Metadati turno | PostgreSQL | sessione, proprietario, percorso GPX, distanza e durata |
| Caduta confermata | PostgreSQL | registrata solo con coordinate valide |
| Contatti SOS | PostgreSQL | associati all'utente |

Questa tabella descrive il codice, non stabilisce per quanto tempo i dati debbano essere conservati in un servizio reale.

## 3. Decisioni obbligatorie per il titolare

Prima di offrire il servizio a utenti reali occorre documentare almeno:

1. titolare del trattamento e contatto privacy;
2. finalità distinta per ogni categoria di dato;
3. base giuridica applicabile a ogni finalità;
4. soggetti autorizzati a vedere posizione, GPX, cadute e contatti SOS;
5. tempi di conservazione e cancellazione, inclusi backup e log;
6. fornitori, subfornitori, luoghi di hosting e trasferimenti internazionali;
7. modalità di esercizio dei diritti degli interessati;
8. procedura per violazioni dei dati personali;
9. necessità e contenuto di una valutazione d'impatto (DPIA).

## 4. Privacy by design e minimizzazione

- Raccogliere soltanto i campi necessari alla funzione dichiarata.
- Rendere evidente quando il tracking è attivo e chi può vedere la posizione.
- Consentire all'utente di interrompere la condivisione live.
- Mantenere breve il TTL della posizione live e motivare ogni estensione.
- Separare autorizzazioni applicative, accessi tecnici e accessi amministrativi.
- Cifrare il traffico e proteggere database, broker, cache, backup e volume GPX.
- Evitare dati personali e segreti nei log.
- Verificare la cancellazione dei dati collegati quando viene eliminato un account.

## 5. Trasparenza e diritti

L'informativa dovrebbe spiegare con linguaggio chiaro:

- quali dati vengono raccolti;
- perché vengono raccolti;
- chi può consultarli;
- per quanto tempo vengono conservati;
- quali funzioni sono obbligatorie e quali opzionali;
- come revocare un consenso quando il consenso è la base applicabile;
- come chiedere accesso, rettifica, portabilità o cancellazione;
- come contattare il titolare o il DPO, se designato.

L'applicazione dispone della cancellazione account, ma la procedura organizzativa deve coprire anche copie di backup, log, archivi e sistemi di terzi.

## 6. DPIA

L'articolo 35 GDPR richiede una DPIA quando il trattamento previsto può presentare un rischio elevato per i diritti e le libertà delle persone. Tracking sistematico, scala, durata, vulnerabilità degli interessati, combinazione di dati e funzioni di sicurezza sono elementi da valutare nel contesto concreto.

Per RoR è opportuno eseguire e documentare uno screening DPIA prima del rilascio. Se lo screening indica rischio elevato, la DPIA deve precedere il trattamento e descrivere necessità, proporzionalità, rischi, misure e rischio residuo. Se il rischio elevato residuo non può essere mitigato, occorre valutare la consultazione preventiva dell'autorità competente.

## 7. Checklist prima della produzione

- [ ] Registro dei trattamenti completato.
- [ ] Finalità, base giuridica e tempi di conservazione approvati.
- [ ] Informativa e meccanismi di controllo coerenti con il codice.
- [ ] Screening DPIA e, se necessario, DPIA completati.
- [ ] Contratti e ruoli dei fornitori verificati.
- [ ] Backup, restore e cancellazione provati.
- [ ] Gestione centralizzata e rotazione dei segreti.
- [ ] Controlli di accesso e audit log definiti.
- [ ] Piano di risposta agli incidenti e data breach.
- [ ] Test di sicurezza e dipendenze aggiornati.

## 8. Fonti ufficiali

- [Regolamento (UE) 2016/679 - testo consolidato](https://eur-lex.europa.eu/eli/reg/2016/679/oj)
- [EDPB - Data protection impact assessment](https://www.edpb.europa.eu/topics/accountability-and-compliance-tools/data-protection-impact-assessment_en)
- [EDPB - Data protection by design e conformità per PMI](https://www.edpb.europa.eu/sme/be-compliant/be-compliant_en)
- [EDPB - Linee guida DPIA e trattamenti ad alto rischio](https://www.edpb.europa.eu/our-work-tools/our-documents/guidelines/data-protection-impact-assessments-high-risk-processing_en)

## 9. File tecnici esaminati

- `app/auth/models.py`
- `app/auth/routes.py`
- `fastapi_app/main.py`
- `gps_worker/worker_consumer.py`
- `gps_worker/stream_manager.py`
- `config.py`
- `docker-compose.yml`
