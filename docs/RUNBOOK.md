# Exploitation locale

Ne jamais afficher `.env`, payload invalide ou reponse brute d'une destination dans les logs de diagnostic. Tout est local hors push du code source demande par l'utilisateur. Pas de notification externe.

## Incident stockage ou backlog

1. `./scripts/local.ps1 status -Engine podman`, puis `podman compose logs --tail 50 gateway loki`.
2. Verifier `/health/live` et `/health/ready`, age/profondeur de queue, espace disque de la machine Podman et du volume. Le gateway peut rester ready pendant une panne Loki tant que la capacite suffit.
3. Restaurer Loki/reseau/espace disque ; ne pas effacer le spool. Observer `filebeat_delivery_total` et la diminution du backlog. Backoff 30s maximum.
4. Quarantaine >0 : diagnostiquer code/config Loki sans exporter les donnees ; corriger la cause, puis `POST /v1/quarantine/replay` avec Bearer. Le rejeu global est idempotent sur l'etat local mais peut reproduire des doublons en destination. Pas de modification brute en base ni relecture d'un secret rejete.
5. Full 429 : limiter producteur, restaurer destination, augmenter capacite seulement apres estimation disque. Les lignes sent sont supprimees apres 24h depuis reception ; pending et quarantaine restent jusqu'a action.

## Exercice panne/reprise

Dans cette nouvelle pile uniquement : `podman compose stop loki`, emettre un evenement synthetique et attendre 202 true, `podman compose restart gateway`, verifier backlog persistant puis `podman compose start loki`. Attendre jusqu'a 30s de retry et verifier la presence de l'ID pseudonymise dans Loki via Grafana Explore. Ne pas arreter les conteneurs du prototype Project Twin.

## Cle, retention et suppression

Rotation cle HMAC : nouvelle cle aleatoire et nouvel ID dans `.env` local, vider tampons producteurs, redemarrer gateway, documenter la rupture de correlation/dedup ; les payloads anciens restent proteges avec l'ancien ID et sont livrables sans cle ancienne. Ne pas supprimer la cle encore requise par un autre producteur. Pas de keyring automatique.

Retention : sent 24h SQLite ; Loki/Prometheus 7j. Les metadonnees d'ID sont retenues avec le payload, aucun coffre de donnees brutes. Les demandes de suppression impliquant plusieurs stockages doivent etre traitees dans SQLite, Loki et sauvegardes ; aucune API RGPD de suppression ciblee n'est livree. Avant usage reel, definir politique legale, effacement et test de restauration. L'environnement courant contient uniquement des fixtures synthetiques.

Sauvegarde SQLite : arreter gateway ou utiliser backup SQLite coherent ; ne pas copier seulement le .db pendant un WAL actif. Restauration a tester avant production. Les volumes sont conserves par `stop` ; suppression d'un volume n'est jamais une procedure de reprise.

## Verification

`./scripts/local.ps1 validate -Engine podman` valide Compose et regles Prometheus. `./scripts/local.ps1 test -Python .venv/Scripts/python.exe` execute les tests. `scripts/smoke.py` verifie contrat HTTP, synthese, metriques, Loki, Grafana et alerte locale a partir de `.env`, sans imprimer de secret. Pas d'envoi email/webhook configure dans Alertmanager.
