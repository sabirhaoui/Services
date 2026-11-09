# Journaux distants de Project Twin

DevConsole dépose les journaux Docker Compose dans `C:\workspace\logs\project_twins\sftp.prod.assystan`. Le dashboard se reconstruit à partir des fichiers déjà présents. Le job DevConsole se lance séparément pour rafraîchir le dump si nécessaire.

```powershell
Set-Location C:\workspace\Services\filebeat-dashboard
./scripts/local.ps1 up -Engine podman
./scripts/local.ps1 replay -Limit 100
```

Le rejeu traite au plus 100 lignes valides par défaut. Il commence par `events.jsonl`, puis remonte les archives `events.*.jsonl` jusqu'à atteindre la limite. Utiliser `-LogDirectory` pour sélectionner un autre dossier de dumps et `-Limit` pour ajuster le volume. Relancer la même commande peut signaler des doublons. Loki conserve ses propres données selon sa rétention.

Le suivi local reste disponible si DevConsole continue à alimenter le dossier :

```powershell
$source = 'C:\workspace\logs\project_twins\sftp.prod.assystan'
$checkpoint = '.data/production-checkpoint.json'
$since = if (Test-Path $checkpoint) {
    (Get-Content $checkpoint -Raw | ConvertFrom-Json -DateKind String).configuration.since
} else {
    (Get-Date).ToUniversalTime().AddMinutes(-5).ToString('o')
}
python scripts/import_remote_logs.py $source --since $since --follow $checkpoint
```

Le script de suivi reste au premier plan. Utiliser un seul processus par checkpoint. Pour reprendre, relancer avec le même chemin, le même `--since` et les mêmes filtres. Pour changer la fenêtre, choisir un autre checkpoint. Sans `--since`, le suivi rejoue les archives disponibles et peut remplir la file locale. L'option `--limit` borne le nombre d'envois par lot en mode suivi.

Le script lit les archives `events.*.jsonl` et `events.jsonl`. Il enregistre son offset local après chaque lot traité et suit le fichier actif lors d'un renommage par DevConsole. Une erreur réseau ou un retour 429/503 déclenche une reprise sans avancer après la ligne bloquée. Les enveloppes invalides et les services hors liste sont comptés. La déduplication repose sur le service, l'horodatage d'origine et la ligne d'origine, indépendamment de l'heure de réception DevConsole. La rétention locale des identifiants limite la déduplication des anciens rejeux.

Dans [Grafana](http://localhost:13001/d/filebeat-health), utiliser le panneau **Journaux distants importés (sans texte brut)** et la fenêtre **Last 15 minutes**. Loki indexe l'heure d'ingestion. Le champ `timestamp` conserve l'heure d'origine en UTC à la microseconde. Les fichiers bruts restent dans le dossier DevConsole. Le gateway reçoit seulement les métadonnées autorisées, sans texte brut, cible SSH ni identifiant de trace inventé. Les logs seuls ne fournissent ni durée d'opération ni trace distribuée.

Pour un import ponctuel, passer un fichier et une limite :

```powershell
python scripts/import_remote_logs.py (Join-Path $source 'events.jsonl') --limit 20
```

Pour arrêter le suivi local, utiliser Ctrl+C.
