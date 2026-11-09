# Matrice de reprise du prototype

Aucun retrait du prototype avant validation et decision explicite. Les preuves historiques restent dans Project Twin, elles ne sont pas presentees comme tests de ce depot.

| Source Project Twin | Decision | Cible / verification |
|---|---|---|
| shared/logging.py structlog | Garder et adapter a terme | JSON UTC v1 a la source, retirer tenant non necessaire, pas de modification ici |
| shared/middleware.py | Garder et adapter a terme | X-Correlation-ID UUID borne, route gabarit au lieu de chemin brut ; propagation W3C a tester |
| shared/observability.py instrumentation HTTP | Decouper / garder instrumentation | Producteur optionnel, queue bornee non bloquante ; aucun gateway ou stockage central dans le backend |
| Sondes PostgreSQL/Neo4j/Redis | Garder sondes indispensables | Instrumentation productrice ; vraies connexions non revalidees ici |
| services/log-processor/app.py | Adapter / reprendre | storage.py conserve concept outbox WAL, API contrat strict et protection allowlist ; nouveau service autonome |
| Masquage regexp recursif prototype | Adapter | Refus des structures/champs libres, messages codes, HMAC IDs avant disque ; pas de promesse d'anonymisation absolue |
| deploy/observability/loki.yml | Deplacer/adopter | Reprise du fichier de configuration non secret, Loki valide et teste dans nouvelle pile |
| Autres deploy/observability | Adapter | Nouveaux provisionnements et ports independants, aucun backend metier lance |
| docker-compose.observability.yml | Retirer a terme du repo applicatif | compose.yml autonome ici ; overlay source conserve intact jusqu'a reprise verifiee |
| requirements-observability.txt | Scinder | SDK/metrics producteurs restent applicatifs ; dependances consommateur gerees ici |
| Tempo / Collector | Deplacer a terme / extension | Non embarques a ce premier increment ; vraie ingestion OTLP future |
| Dashboards/alertes du prototype | Adapter | Vue pipeline et logs generiques ; panneaux DB/HTTP applicatifs non verifies non recopies |
| README / VALIDATION prototype | Garder comme preuve historique | Nouveaux documents propres a ce depot |
| identity/authorization.py | Hors mission | Modification etrangere preservee |

Ordre de bascule : deployer la pile independante, tests synthetiques et panne/reprise, adapter producteur dans une mission distincte, tester indisponibilite consommateur sans effet metier, comparer volumes/qualite, basculer transport puis retirer composants centraux du monolithe. Retour arriere : desactiver emission optionnelle ; conserver les volumes, ne pas supprimer les sources ni toucher aux bases applicatives.
