# UNEXECUTED. Main must grant browser-backoffice-upgrade-u1-integration first.
# This declaration is an operator assertion, not a security or spend permit.
param([Parameter(Mandatory=$true)][switch]$LeaseGranted,
      [Parameter(Mandatory=$true)][string]$RunName)
$ErrorActionPreference = 'Stop'
if (-not $LeaseGranted -or $RunName -notmatch '^u1-[a-z0-9-]{1,48}$') { throw 'Named lease and bounded new run name required' }
$u1Repo = Split-Path -Parent $PSScriptRoot
$u1Python = Join-Path $u1Repo '.venv/Scripts/python.exe'
$u1RunDir = Join-Path $u1Repo "work/$RunName"
if (Test-Path -LiteralPath $u1RunDir) { throw 'Preserve existing evidence; choose a new run name' }
$u1ReceiptDir = Join-Path $u1Repo "work/$RunName-batch"
if (Test-Path -LiteralPath $u1ReceiptDir) { throw 'Preserve existing batch evidence' }
New-Item -ItemType Directory -Path $u1ReceiptDir | Out-Null
$u1OldLocation = Get-Location
$u1PreviousBrowserPath = $env:PLAYWRIGHT_BROWSERS_PATH
$u1Step = 0
function Invoke-U1Step {
    param([string[]]$CliArguments, [int]$ExpectedExit = 0)
    $script:u1Step += 1
    $u1Log = Join-Path $u1ReceiptDir ('{0:D2}.log' -f $script:u1Step)
    $u1CommandRecord = @{ step=$script:u1Step; executable=$u1Python; argv=$CliArguments; expected_exit=$ExpectedExit }
    $u1CommandRecord | ConvertTo-Json -Compress | Add-Content -LiteralPath (Join-Path $u1ReceiptDir 'commands.jsonl')
    & $u1Python @CliArguments 2>&1 | Tee-Object -FilePath $u1Log
    $u1ActualExit = $LASTEXITCODE
    @{ step=$script:u1Step; actual_exit=$u1ActualExit } | ConvertTo-Json -Compress | Add-Content -LiteralPath (Join-Path $u1ReceiptDir 'exits.jsonl')
    if ($u1ActualExit -ne $ExpectedExit) { throw "U1 step $script:u1Step failed: preserved $u1Log; stop before any rerun" }
}
try {
    Set-Location -LiteralPath $u1Repo
    $env:PLAYWRIGHT_BROWSERS_PATH = Join-Path $u1Repo '.cache/ms-playwright'
    Invoke-U1Step -CliArguments @('-m','evaluation.freeze','--suite','heldout','--check')
    Invoke-U1Step -CliArguments @('-m','upgrade_tests.source_check','--check')
    Invoke-U1Step -CliArguments @('-m','unittest','discover','-s','upgrade_tests/contract','-v')
    Invoke-U1Step -CliArguments @('-m','unittest','discover','-s','upgrade_tests/browser','-v')
    Invoke-U1Step -CliArguments @('-m','industry_backoffice','demo','--request','fixtures/requests/cedar.json','--config','config/local-double-v2.json','--run-dir',$u1RunDir) -ExpectedExit 10
    Invoke-U1Step -CliArguments @('-m','industry_backoffice.verify','--run-dir',$u1RunDir,'--expect','awaiting')
    Invoke-U1Step -CliArguments @('-m','industry_backoffice','review','--run-dir',$u1RunDir)
    $u1OperatorDigest = Read-Host 'Inspect all ReviewV2 fields above, then type its exact digest to approve (blank stops)'
    if ($u1OperatorDigest -notmatch '^[0-9a-f]{64}$') { throw 'Manual approval not supplied; review remains pending' }
    Invoke-U1Step -CliArguments @('-m','industry_backoffice','approve','--run-dir',$u1RunDir,'--digest',$u1OperatorDigest)
    Invoke-U1Step -CliArguments @('-m','industry_backoffice','resume','--config','config/local-double-v2.json','--run-dir',$u1RunDir)
    Invoke-U1Step -CliArguments @('-m','industry_backoffice.verify','--run-dir',$u1RunDir,'--expect','created')
    Invoke-U1Step -CliArguments @('-m','industry_backoffice','resume','--config','config/local-double-v2.json','--run-dir',$u1RunDir)
    Invoke-U1Step -CliArguments @('-m','industry_backoffice.verify','--run-dir',$u1RunDir,'--expect','created')
} finally {
    $env:PLAYWRIGHT_BROWSERS_PATH = $u1PreviousBrowserPath
    Set-Location -LiteralPath $u1OldLocation.Path
}
