#!/usr/bin/env pwsh
# Helper: start n8n and run the one-shot importer that loads n8n/workflows_all.json

Set-Location -Path (Split-Path -Path $PSScriptRoot -Parent)

$legacyContainer = docker ps -a --filter "name=^/n8n$" --format "{{.Names}}"
if ($legacyContainer -eq 'n8n') {
    Write-Host "Removing legacy standalone n8n container so Compose can manage it"
    docker rm -f n8n | Out-Null
}

# Remove any stale Compose container and volume, then recreate it cleanly so the host port is published.
docker-compose down -v
docker-compose up -d --force-recreate n8n

Write-Host "Waiting for n8n port 5678 to be published (timeout 120s)..."
$timeout = 120
$elapsed = 0
while ($elapsed -lt $timeout) {
    $port = docker port open_garmin-n8n-1 5678 2>$null
    if ($port) {
        Write-Host "n8n port published: $port"
        break
    }
    Start-Sleep -Seconds 2
    $elapsed += 2
}

if ($elapsed -ge $timeout) {
    Write-Error "n8n did not publish port 5678 within $timeout seconds"
    exit 1
}

Write-Host "Waiting for n8n CLI readiness before import (timeout 180s)..."
$timeout = 180
$elapsed = 0
while ($elapsed -lt $timeout) {
    docker-compose exec -T n8n n8n list:workflow --active=true --onlyId 1>$null 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "n8n CLI is ready"
        break
    }
    Start-Sleep -Seconds 3
    $elapsed += 3
}

if ($elapsed -ge $timeout) {
    Write-Error "n8n CLI did not become ready within $timeout seconds"
    exit 1
}

# Import the workflows from inside the running n8n container.
docker-compose exec -T n8n n8n import:workflow --input=/tmp/workflows_all.json

if ($LASTEXITCODE -ne 0) {
    Write-Error "Workflow import failed"
    exit $LASTEXITCODE
}

# Activate the bundled workflows so production webhook URLs are registered.
$workflowIds = @(
    'coach-nutrition-add',
    'coach-nutrition-delete',
    'coach-nutrition-today',
    'coach-garmin-sync',
    'coach-health-manual',
    'coach-health-today',
    'coach-report-generate'
)

foreach ($workflowId in $workflowIds) {
    docker-compose exec -T n8n n8n publish:workflow --id $workflowId | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Failed to publish workflow $workflowId"
        exit $LASTEXITCODE
    }
}

docker-compose restart n8n | Out-Null

Write-Host "Waiting for n8n to come back after publish (timeout 120s)..."
$timeout = 120
$elapsed = 0
while ($elapsed -lt $timeout) {
    $port = docker port open_garmin-n8n-1 5678 2>$null
    if ($port) {
        Write-Host "n8n restarted and port published: $port"
        break
    }
    Start-Sleep -Seconds 2
    $elapsed += 2
}

if ($elapsed -ge $timeout) {
    Write-Error "n8n did not republish port 5678 after restart within $timeout seconds"
    exit 1
}

Write-Host "Waiting for n8n CLI readiness after restart (timeout 180s)..."
$timeout = 180
$elapsed = 0
while ($elapsed -lt $timeout) {
    docker-compose exec -T n8n n8n list:workflow --active=true --onlyId 1>$null 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "n8n CLI is ready after restart"
        break
    }
    Start-Sleep -Seconds 3
    $elapsed += 3
}

if ($elapsed -ge $timeout) {
    Write-Error "n8n CLI did not become ready after restart within $timeout seconds"
    exit 1
}

Write-Host "Workflows imported successfully."
