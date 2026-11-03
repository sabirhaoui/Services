# Analyses et confiance

## Descriptif implemente

Synthese API sur les evenements proteges retenus : volume, completions, erreurs outcome, p50/p95/p99 par rang superieur, couverture de duration_ms, p95 du delai observation-evenement, fraicheur. Les quantiles ne sont ni des moyennes de quantiles ni une preuve de performance utilisateur. Le dashboard calcule les quantiles des logs sur 5 minutes dans Loki ; son historique peut donc differer de la fenetre SQLite 24h. Les metriques pipeline ont un debit sur 1 minute et aucun filtre de service ; seuls logs/latences sont filtres par service/environnement.

Null/NaN = absence ou insuffisance ; 0 = observation mesuree de zero. Une absence de scrape est un incident de collecte, pas zero erreur. La couverture et la fraicheur doivent accompagner les decisions. Reconstruction triee par timestamp et ID, liste d'etapes observees et familles started/completed manquantes, aucune hypothese ajoutee. Cette premiere reconstruction est grossiere par famille de trace : pas de graphe de spans parent/enfant, pas d'alignement des multiples tentatives d'une meme tache. Une paire complete ne prouve pas que toute l'execution est couverte.

## MAD v1 implemente

Objectif : signaler une derniere latence inhabituellement haute. Variables : duration_ms, timestamp, environnement, service, version, event_type. Baseline : 20 a 100 observations strictement anterieures du meme groupe ; fenetre en nombre d'observations, sans saisonnalite. Seuil = mediane + max(6*1.4826*MAD, 50 ms). Les dates egales ne sont pas utilisees comme historique de la derniere observation. Cout O(n log n), borne par 10 000 lignes ; calcul au scrape et sur demande API, adapte uniquement au faible volume local.

Historique <20 => `insufficient_data`, panneau sans valeur exploitable. Evaluation temporelle : fixtures normales a 100-120 ms puis anomalie injectee 2500 ms ; ordre inverse d'arrivee teste, derniere observation exclue de la baseline. Cas normaux et MAD nul testes. Ces donnees controlees ne sont pas un benchmark de precision : aucun label reel, aucune precision/recall revendiquee. La hausse mesuree peut etre une modification attendue de charge, pas une cause racine.

Faux positifs : demarrage, variations de trafic, changements de version, distributions multimodales. Derive : comparer quantiles et taux d'alertes dans le temps, recalibrer sur validation temporelle distincte ; pas de recalibration automatique. Le taux d'echantillonnage differentiel des erreurs peut biaiser la baseline. Cette version n'est pas un modele ML et n'ajoute pas numpy/pandas inutiles.

## SLI/SLO et extensions proposees

SLI observe = 1 - erreurs/completions ; aucune completion => non calculable. Cible exploratoire 99,9% sur 30 jours, non certifiee : retention Prometheus/Loki 7 jours, couverture producteur inconnue. Aucun tableau ne pretend a un SLO mensuel valide. Ajouter sondes utilisateur et couverture avant alertes de budget.

Baselines saisonnieres de volumes/erreurs : attendre au moins 4 semaines couvrant memes creneaux ; mediane par heure/semaine, comparaison temporelle glissante, seuil MAD, faux positifs jours feries a surveiller. Ruptures de tendance : CUSUM ou comparaison de fenetres, historique stable suffisant et seuils calibres hors evaluation. Regroupement de signatures : codes erreurs normalises seulement, jamais prompts/stack sensibles ; un cluster ne prouve aucune cause. Comparaison de versions : groupes apparies charge/operation, minimum 100 observations par groupe, effets et intervalles avant decision. Capacite : taux entree/sortie et age backlog sur au moins une semaine, projection explicable et limites disque. Ces extensions ne sont pas implementees ; historique actuel insuffisant.
