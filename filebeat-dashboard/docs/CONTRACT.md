# Contrat producteur v1.0.0

Autorite : `contracts/event-1.0.0.schema.json`, JSON Schema Draft 2020-12 avec verification des formats (pas seulement des types). Exemples HTTP, Celery et connecteur dans `contracts/examples/`. Ces schemas ne dependent d'aucun code Project Twin.

Obligatoires : schema_version exacte, event_id UUID, event_type (http/job/connector started/completed), timestamp UTC suffixe Z, service.name et version, environment, level, message code et trace_id/span_id hexadecimaux non nuls, attributes. Facultatifs : request_id/job_id UUID, duration_ms (millisecondes finies >=0 <=24h), outcome success/error/unknown. Les timestamps d'entree acceptent 6 jours de retard et 5 minutes d'avance maximum. `observed_timestamp` est fourni par le gateway au format UTC : le producteur ne peut pas l'imposer.

Attributs autorises : http_method enum borne, status_code 100..599, operation et error_code enum bornes. Aucune structure libre ou imbriquee : les secrets/PII imbriques sont rejetes avant tout stockage ; pas de simple regexp promettant de nettoyer tout texte libre. Messages limites a operation.started/completed/failed. Aucune URL brute, prompt, cookie, SQL, header, nom, email, tenant ou utilisateur. Producteur : ne pas placer de donnees dans les IDs, meme si le gateway les pseudonymise.

Les champs inconnus sont refuses. Toute extension du schema exige une nouvelle version et un lecteur explicitement compatible ; changement incompatible => version majeure, compatibilite parallele a introduire avant migration. Pas d'acceptation silencieuse des versions futures.

Deduplication : environnement/service/event_id pseudonymise, digest du contenu protege hors observed_timestamp. Meme payload protege => 202 accepted=false ; autre contenu => 409. Fenetre de dedup locale 24h pour les evenements livres. Une nouvelle cle de pseudonymisation change l'identite : eviter les retries traversant une rotation, vider la file productrice avant rotation ou introduire un keyring multi-version avant production.

Pseudonymisation HMAC-SHA256 avec separation du domaine par type d'identifiant ; cle >=32 caracteres aleatoires distincte du jeton d'ingestion, ID de cle visible. Meme trace => meme pseudonyme entre services partageant cette politique. Les tenants/utilisateurs sont exclus. C'est une pseudonymisation, pas une anonymisation irreversible : correlations, frequences et horodatages peuvent reidentifier. Cle accessible au seul gateway local, a gerer dans un secret manager en production. Rotation : choisir une nouvelle cle et un nouvel ID, redemarrer de facon coordonnee, accepter une rupture de correlation documentee ; aucun outil de remapping secret n'est fourni.

Echantillonnage : SAMPLE_RATE dans [0,1], defaut 1. Hash stable de trace pseudonymisee, decision commune pour tous ses evenements ordinaires. Erreurs toujours conservees ; peut creer une trace partielle et biaise les volumes/latences. Pas de ponderation/estimation du trafic total dans les dashboards. Changer taux/cle coupe la comparabilite ; politique a versionner avant production. Les compteurs sampled_out distinguent cette reduction intentionnelle d'un rejet ou d'un backlog. Aucun echantillonnage metier producteur n'est suppose.

| Code | Signification | Action |
|---|---|---|
| 202 true | commit durable | ne pas renvoyer |
| 202 false duplicate | deja connu | ne pas renvoyer |
| 202 false sampled_out | reduction intentionnelle non persistee | ne pas renvoyer |
| 401 | jeton absent/invalide | corriger acces |
| 409 | identite en conflit | corriger ID/contenu |
| 413 / 422 | taille/contrat incorrect | corriger producteur, aucun brut conserve |
| 429 | capacite bornee | retry meme ID apres Retry-After |
| 503 | stockage indisponible | retry meme ID avec delai borne |

Le tampon producteur et les abandons avant acquittement sont sa responsabilite. Le gateway ne peut pas mesurer les evenements jamais recus.

Les journaux de collecte utilisent `log.received` avec le message constant du meme nom. Trace et span sont facultatifs pour ce type uniquement. Le niveau `UNKNOWN` indique une severite non reconnue. Les journaux historiques peuvent depasser six jours de retard et restent soumis a la limite future de cinq minutes. Le gateway accepte uniquement les metadonnees du schema. La livraison Loki utilise `source_service`, `source_environment` et `source_level` dans le JSON pour eviter une collision avec les labels de flux.
