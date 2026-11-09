# filebeat : supervision independante

Nom de travail sans lien avec **Elastic Filebeat** : le produit Elastic n'est ni requis ni embarque. Ce depot est autonome ; aucun import, code metier, base ou secret de Project Twin n'est necessaire.

Project Twin reste producteur (JSON, correlation, instrumentation, protection a la source). Services heberge ingestion, protection complementaire, outbox, reconstruction, analyses et visualisation. Aucun fichier de Project Twin n'a ete modifie. Son changement existant dans `identity/authorization.py` a ete preserve.

## Demarrer localement (PowerShell)

Python 3.14 et Docker Desktop Linux ou Podman deja demarre. Les interfaces sont liees a 127.0.0.1 ; ports distincts du prototype.

```powershell
Set-Location C:\workspace\Services\filebeat-dashboard
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
./scripts/local.ps1 init
./scripts/local.ps1 config -Engine podman
./scripts/local.ps1 up -Engine podman
./scripts/local.ps1 validate -Engine podman
./scripts/local.ps1 test -Python .venv/Scripts/python.exe
./scripts/local.ps1 demo -Python .venv/Scripts/python.exe
Invoke-RestMethod http://127.0.0.1:18088/health/ready
./scripts/local.ps1 status -Engine podman
./scripts/local.ps1 stop -Engine podman
```

Remplacer `podman` par `docker` si utilise. `init` cree trois secrets distincts dans `.env` ignore ; aucun secret a copier depuis une autre application. Ne pas publier `.env`. Le mot de passe Grafana est `GRAFANA_PASSWORD` de ce fichier ; utilisateur admin. Ne pas utiliser `compose down -v` pour resoudre une panne.

- [Grafana](http://localhost:13001/d/filebeat-health) : 15 panneaux, logs, latences, sante, qualite, anomalies et alertes.
- [Prometheus](http://localhost:19090) et [Alertmanager local](http://localhost:19093).
- [API](http://localhost:18088/docs) ; ingestion `POST /v1/events`, synthese `GET /v1/summary`, reconstruction `GET /v1/executions/{trace_pseudonymisee}` ; Bearer INGEST_TOKEN. Ne pas mettre le jeton dans une URL.

La demo emet 26 observations synthetiques et une latence de 2500 ms, contre une baseline de 100-120 ms. La regle `FilebeatLatencyAnomaly` doit devenir active apres scrape/evaluation et 10 secondes de maintien. La detection porte sur la derniere operation observable de chaque groupe ; elle ne se resout qu'apres une nouvelle observation normale. Les exemples du contrat ont une date fixe pour validation de schema, la demo genere les dates au moment de l'execution.

## Arborescence

```text
contracts/       JSON Schema partage et exemples valides/invalides
src/filebeat/    api, protection, sampling, storage, analytics
demo/           emission synthetique autonome
tests/          confidentialite, contrat, panne, reprise et anomalies
deploy/         Loki, Prometheus, Grafana, Alertmanager
scripts/        commandes PowerShell et smoke test
docs/           architecture, migration, contrat, analyses et runbooks
```

Lire [architecture](docs/ARCHITECTURE.md), [contrat](docs/CONTRACT.md), [migration](docs/MIGRATION.md), [analyses](docs/ANALYTICS.md), [exploitation](docs/RUNBOOK.md) et [preuves et limites](docs/VALIDATION.md). Les fonctions sont des modules d'un gateway ; Loki, Prometheus, Grafana et Alertmanager sont des composants existants, pas des moteurs reinventes.

[Collecte des journaux de production](docs/REMOTE_LOGS.md) via DevConsole, import avec reprise et panneau Grafana.
