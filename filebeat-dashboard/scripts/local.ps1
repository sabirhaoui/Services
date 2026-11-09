param([ValidateSet('init','config','up','stop','status','test','demo','replay','validate')][string]$Action='status', [ValidateSet('docker','podman')][string]$Engine='docker', [string]$Python='python', [string]$LogDirectory='C:\workspace\logs\project_twins\sftp.prod.assystan', [ValidateRange(1,10000)][int]$Limit=100)
$ErrorActionPreference='Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
if ($Action -eq 'init') {
  if (Test-Path .env) { throw '.env existe dÃ©jÃ  ; conservÃ©' }
  function New-Token { [Convert]::ToHexString([System.Security.Cryptography.RandomNumberGenerator]::GetBytes(32)) }
  @("INGEST_TOKEN=$(New-Token)","PRIVACY_KEY=$(New-Token)",'PRIVACY_KEY_ID=k1',"GRAFANA_PASSWORD=$(New-Token)") | Set-Content .env
  return
}
if ($Action -eq 'test') {
  New-Item -ItemType Directory -Path .data -Force | Out-Null
  $env:PYTHONPATH='src'
  $testTemp = Join-Path .data ('pytest-' + [guid]::NewGuid())
  & $Python -m pytest -q --basetemp $testTemp
  exit $LASTEXITCODE
}
if ($Action -eq 'demo') {
  $entry=Get-Content .env | Where-Object { $_ -like 'INGEST_TOKEN=*' }
  $env:INGEST_TOKEN=$entry.Substring('INGEST_TOKEN='.Length)
  & $Python demo/emit.py
  exit $LASTEXITCODE
}
if ($Action -eq 'replay') {
  & $Python scripts/import_remote_logs.py $LogDirectory --replay --limit $Limit
  exit $LASTEXITCODE
}
if ($Action -eq 'validate') {
  & $Engine compose config --quiet
  if ($LASTEXITCODE) { exit $LASTEXITCODE }
  & $Engine compose run --rm --no-deps --entrypoint /bin/promtool prometheus check config /etc/prometheus/prometheus.yml
  exit $LASTEXITCODE
}
switch ($Action) {
  config { & $Engine compose config --quiet }
  up { & $Engine compose up -d --build }
  stop { & $Engine compose stop }
  status { & $Engine compose ps }
}
exit $LASTEXITCODE
