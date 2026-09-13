param(
    [string]$BaseUrl = "http://localhost:18000/api/v1",
    [int]$FailureTimeoutSeconds = 90,
    [int]$RecoveryTimeoutSeconds = 60
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Headers = @{
    "x-model-atlas-operator-id" = "staging-failure-drill"
    "x-model-atlas-operator-name" = "Staging Failure Drill"
    "x-model-atlas-operator-role" = "SRE Lead"
}
$TestJob = $null
$FailureObserved = $false

Push-Location $ProjectRoot
try {
    docker compose stop paging-sink | Out-Null
    $TestJob = Invoke-RestMethod `
        -Method Post `
        -Uri "$BaseUrl/operations/reliability/test-pages" `
        -Headers $Headers `
        -ContentType "application/json" `
        -Body (@{
            severity = "warning"
            reason = "Exercise paging outage retry and audited recovery"
        } | ConvertTo-Json)

    $Deadline = (Get-Date).AddSeconds($FailureTimeoutSeconds)
    while ((Get-Date) -lt $Deadline) {
        $CurrentJob = Invoke-RestMethod -Uri "$BaseUrl/agents/jobs/$($TestJob.id)"
        if ($CurrentJob.status -eq "failed") {
            $FailureObserved = $true
            break
        }
        Start-Sleep -Seconds 2
    }
    if (-not $FailureObserved) {
        throw "Paging delivery did not reach dead-letter state within the drill timeout."
    }
}
finally {
    docker compose start paging-sink | Out-Null
    Start-Sleep -Seconds 5
}

$RequeueBody = @{
    reason = "Recover the paging delivery after the controlled sink outage"
    max_attempts = 4
} | ConvertTo-Json
Invoke-RestMethod `
    -Method Post `
    -Uri "$BaseUrl/agents/jobs/$($TestJob.id)/requeue" `
    -Headers $Headers `
    -ContentType "application/json" `
    -Body $RequeueBody | Out-Null

$Recovered = $false
$RecoveryDeadline = (Get-Date).AddSeconds($RecoveryTimeoutSeconds)
while ((Get-Date) -lt $RecoveryDeadline) {
    $CurrentJob = Invoke-RestMethod -Uri "$BaseUrl/agents/jobs/$($TestJob.id)"
    if ($CurrentJob.status -eq "completed") {
        $Recovered = $true
        break
    }
    if ($CurrentJob.status -eq "failed") {
        break
    }
    Start-Sleep -Seconds 1
}
if (-not $Recovered) {
    throw "Paging delivery did not recover within the drill timeout."
}

$CycleJob = Invoke-RestMethod `
    -Method Post `
    -Uri "$BaseUrl/operations/reliability/cycles" `
    -Headers $Headers `
    -ContentType "application/json" `
    -Body (@{
        reason = "Reconcile incident state after the controlled paging recovery"
    } | ConvertTo-Json)

$Normalized = $false
$Overview = $null
$NormalizationDeadline = (Get-Date).AddSeconds($RecoveryTimeoutSeconds)
while ((Get-Date) -lt $NormalizationDeadline) {
    $CurrentCycleJob = Invoke-RestMethod -Uri "$BaseUrl/agents/jobs/$($CycleJob.id)"
    $Overview = Invoke-RestMethod -Uri "$BaseUrl/operations/reliability"
    if (
        $CurrentCycleJob.status -eq "completed" -and
        $Overview.health -eq "healthy" -and
        $Overview.open_incident_count -eq 0
    ) {
        $Normalized = $true
        break
    }
    if ($CurrentCycleJob.status -eq "failed") {
        break
    }
    Start-Sleep -Seconds 1
}
if (-not $Normalized) {
    throw "Operational incidents did not reconcile after paging recovery."
}

[pscustomobject]@{
    schema_version = "model-atlas-operational-failure-drill-v1"
    outage_failure_observed = $FailureObserved
    recovery_completed = $Recovered
    job_id = $TestJob.id
    reconciliation_job_id = $CycleJob.id
    incidents_reconciled = $Normalized
    operations_health = $Overview.health
    open_incident_count = $Overview.open_incident_count
    dead_letter_count = $Overview.delivery_status_counts.failed
    staging_ready = $Overview.staging_readiness.ready
    latest_receipt_delivery_id = $Overview.staging_readiness.latest_receipt_delivery_id
} | ConvertTo-Json -Depth 5

Pop-Location
