param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('A', 'ACL')]
    [string]$Stage,
    [switch]$ExecuteApprovedStage,
    [string]$LiveAuthorizationReference
)

$ErrorActionPreference = 'Stop'
$repositoryRoot = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $repositoryRoot
try {
    $planRoot = 'artifacts/milestone-3c7-immediate-001'
    if ($Stage -eq 'A') {
        $planPath = Join-Path $planRoot 'a-enumeration-plan.json'
        $expectedHash = '25dcd4648d834cf4f7069d8f4fcc260c37319cb94f69602b3c169fc6f40810c8'
        $expectedBudget = 8
        $expectedAuthorization = 'A-S1-immediate-v1-A-enumeration'
        $runName = 'a-enumeration-001'
    } else {
        $planPath = Join-Path $planRoot 'acl-resolution-plan.json'
        $expectedHash = 'd89676a6c00b9274f00441d27b1c687707607da1f4d4db5a4358e5346470784b'
        $expectedBudget = 1
        $expectedAuthorization = 'A-S1-immediate-v1-ACL-resolution'
        $runName = 'acl-pin-resolution-001'
    }
    $actualHash = (Get-FileHash -LiteralPath $planPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualHash -ne $expectedHash) { throw 'STOP: plan differs from reviewed inventory.' }
    $plan = Get-Content -LiteralPath $planPath -Raw | ConvertFrom-Json
    if ($plan.maximum_requests -ne $expectedBudget -or $plan.requests.Count -ne $expectedBudget) {
        throw 'STOP: request budget mismatch.'
    }
    $now = [DateTimeOffset]::UtcNow
    $start = [DateTimeOffset]::Parse($plan.planned_started_at)
    $end = [DateTimeOffset]::Parse($plan.planned_finished_at)
    if ($now -lt $start -or $now -ge $end) {
        throw 'STOP: outside immutable collection window; obtain a newly versioned plan.'
    }
    foreach ($row in $plan.requests) {
        if ($row.source_day) {
            $sourceDay = [DateTimeOffset]::Parse($row.source_day + 'T00:00:00Z')
            if ($sourceDay.UtcDateTime.Date -ge $now.UtcDateTime.Date) {
                throw 'STOP: source UTC day is not complete.'
            }
        }
    }
    & '.\.venv\Scripts\python.exe' -c 'import sys; from pathlib import Path; from citeprobe.pilot_models import PilotPlan; from citeprobe.pilot_plans import validate_plan; validate_plan(PilotPlan.model_validate_json(Path(sys.argv[1]).read_bytes()))' $planPath
    if ($LASTEXITCODE -ne 0) { throw 'STOP: schema or canonical inventory validation failed.' }
    Write-Output "Stage=$Stage; maximum=$expectedBudget; SHA256=$actualHash"
    Write-Output "UTC window: $start through $end"
    if (-not $ExecuteApprovedStage) {
        Write-Output 'OFFLINE PREFLIGHT PASSED. No HTTP requests made. Live approval is still required.'
        return
    }
    if ($LiveAuthorizationReference -ne $expectedAuthorization) {
        throw 'STOP: supply the new stage-specific reference only after explicit live approval.'
    }
    $outputParent = 'artifacts/empirical-pilot-immediate-001'
    $outputDirectory = Join-Path $outputParent $runName
    if (Test-Path -LiteralPath $outputDirectory) {
        throw 'STOP: an attempt already exists. Do not rerun or consume another request budget.'
    }
    New-Item -ItemType Directory -Path $outputParent -Force | Out-Null
    & '.\.venv\Scripts\citeprobe.exe' pilot-run $planPath --authorize-live `
        --authorization-reference $LiveAuthorizationReference --plan-sha256 $expectedHash `
        --output-dir $outputDirectory
    if ($LASTEXITCODE -ne 0) {
        throw 'STOP: acquisition failed or is incomplete. Preserve evidence; do not rerun.'
    }
    Write-Output "Stage finished. Preserve $outputDirectory; no follow-up requests are authorized."
} finally {
    Pop-Location
}
