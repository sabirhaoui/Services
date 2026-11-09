# Validation du premier increment - 3 novembre 2026

## Effectivement verifie

- Douze tests Python reussis, dernier passage 1,12 s : exemples JSON Schema, secrets/PII imbriques refuses sans echo, IDs HMAC avant SQLite, auth, doublons et conflit, saturation 429, ecriture indisponible 503, taille 413, arrivee desordonnee, reconstruction partielle sans hypotheses, destination 503 puis 400/quarantaine puis replay/204, fermeture/reouverture SQLite, crash processus apres commit (os._exit), retention/capacite globale, anomalies synthetiques et baseline strictement anterieure, rotation cle, echantillonnage coherent par trace, NaN/version/date invalides et metriques sans donnees.
- Ruff check reussi sur src, tests, demo et scripts Python. Git diff --check reussi avant publication.
- Compose valide, image gateway Linux construite avec Python 3.14.0-slim, dependances transitives du build relevees puis verrouillees dans requirements.lock. Execution sous UID 10001 ; image API sans code de Project Twin. Les tests Windows ont reutilise un interpreteur deja installe (venv Python 3.14.8) sans y installer ni modifier de dependance ; le runtime Compose est independant.
- Cinq services du nouveau projet `independent-filebeat` demarres sous Podman 5.8.9. Docker Desktop ne repondait pas ; Podman necessitait l'execution hors sandbox Windows. Les ecritures de test ont ete placees sous .data, ignore.
- Prometheus 3.3.0 : configuration et cinq regles valides ; deux scenarios promtool, cible absente et saine, reussis.
- Smoke reel reussi sur le build final : 26 evenements synthetiques emis, donnees protegees dans Loki, API reconstruction lisible, synthese avec anomalie de latence, dashboard Grafana provisionne et alerte FilebeatLatencyAnomaly visible dans Alertmanager. Dernier compteur retenu observe : 105 (plusieurs campagnes de fixtures, pas du trafic metier).
- Panne reelle : Loki arrete dans cette pile seulement ; evenement accepte durablement ; gateway redemarre ; execution retrouvee dans SQLite ; Loki redemarre ; evenement protege retrouve dans Loki. Script fault_probe retourne accepted_during_outage=true, survived_restart=true, loki_recovery=true.
- Verification visuelle Grafana via navigateur : sante, fraicheur, couverture, backlog, incident, p50/p95/p99 et logs. Le controle a revele un selecteur All vide-compatible interdit par Loki ; corrige en .+ puis panneaux recontroles sans erreur. Capture synthetique dans screenshots/grafana.png. La panne s'est resolue ; un panneau Incidents sans donnees signifie ici aucune alerte active, pas une preuve generale d'absence d'incident.
- Etat Project Twin inspecte en lecture seule : branche codex/structuration-logs-local, changement preexistant identity/authorization.py preserve. Aucun push de Project Twin.

## Corrections issues des essais

La limite memoire Compose a ete retiree car le cgroup du Podman local refuse memory.max ; une limite de ressources doit etre retestee sur l'environnement cible. Le smoke attend maintenant la readiness lors d'un redemarrage. Les tests utilisent le thread du lifespan pour manipuler sa connexion SQLite ; la production reste un seul processus/event loop. Les valeurs JSON NaN sont refusees. Les probes HTTP utilisent 127.0.0.1 pour eviter les delais de resolution localhost de la machine.

## Rejouer

```powershell
./scripts/local.ps1 test -Python .venv/Scripts/python.exe
.venv/Scripts/python.exe -m ruff check src tests demo scripts/smoke.py scripts/fault_probe.py
./scripts/local.ps1 validate -Engine podman
podman run --rm --entrypoint /bin/promtool -v "${PWD}/deploy:/work:ro" -w /work docker.io/prom/prometheus:v3.3.0 test rules alert-tests.yml
.venv/Scripts/python.exe scripts/smoke.py
.venv/Scripts/python.exe scripts/fault_probe.py
```

Ruff est un outil de controle facultatif ; installer une version explicite si absent. fault_probe utilise Podman et interrompt temporairement uniquement le Loki de cette pile ; toujours restaure en finally. La commande promtool utilise le chemin local, a adapter si le depot est deplace. Le smoke conserve les evenements synthetiques suivant la retention configuree. Le rendement visuel necessite une connexion Grafana admin avec le mot de passe local de .env.

## Non implemente / non demontre

- Aucun branchement sur le backend metier, stdout de Project Twin, Celery reel, connecteur Oracle/LLM reel ou bases applicatives. Les exemples Celery/connecteur sont des contrats synthetiques. L'absence d'effet d'une panne de supervision sur le backend devra etre testee lors de son instrumentation ; ce depot ne le modifie pas.
- Pas d'agent Alloy/Beats, receiver OTLP, Collector ni Tempo : pas de vraie trace distribuee ni drill-down vers spans. Reconstruction de logs par trace uniquement, familles started/completed, pas de causalite ni resolution de cause racine.
- Saturation/quarantaine/replay testes avec stockage/destination controles ; le vrai test conteneur porte sur panne Loki et reprise, pas sur un disque reellement plein ou une corruption de volume.
- Pas de HA, TLS/mTLS, RBAC fin, identite par producteur, restauration de sauvegarde, suppression ciblee multi-stockages ou chiffrement au repos configure. Cle et jeton par variables d'environnement pour demo uniquement. Pas de garantie exactement une fois, ni sans perte avant acquittement.
- Pas d'historique saisonnier, precision ML mesuree, SLO 30 jours valide ou benchmark de charge/cout. L'analyse est descriptive et MAD-v1 sur observations retenues. Echantillonnage peut biaiser les comparaisons.
- Images avec tags fixes et dependances verrouillees, pas d'attestation de securite ni de revue CVE recente. Versions de reference confirmees par sources officielles ; execution locale verifiee. Les digests et hashes des wheels restent a ajouter pour durcissement reproductible.

L'utilisateur a ensuite autorise les push progressifs du code sur sabirhaoui/Services. Branche codex/filebeat-platform ; aucun deploiement distant, aucune donnee metier, aucun .env ou secret publie, aucun canal externe de notification configure.
