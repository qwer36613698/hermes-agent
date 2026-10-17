# Build a local CLI/source candidate. Never changes an installed Hermes profile.
[CmdletBinding()]
param(
    [string]$SourcePath = (Split-Path -Parent $PSScriptRoot),
    [string]$StatePath = 'D:\AI_Data\ManagedForks\hermes-agent',
    [string]$UpstreamTag = 'v0.22.2',
    [string]$TestPython = 'D:\AI_Data\ManagedForks\hermes-agent\test-env\Scripts\python.exe',
    [string]$BootstrapPython = 'D:\AI_Data\ManagedForks\hermes-agent\runtime\python-3.14.7+20260901-win32-x64\python.exe',
    [string]$Bash = 'C:\Program Files\Git\bin\bash.exe'
)
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true
$SourcePath = (Resolve-Path -LiteralPath $SourcePath).Path
$StatePath = [IO.Path]::GetFullPath($StatePath)
if ($StatePath.StartsWith($SourcePath + '\', [StringComparison]::OrdinalIgnoreCase) -or $StatePath -eq $SourcePath) {
    throw 'Build state must be outside the source tree.'
}
New-Item -ItemType Directory -Path $StatePath -Force | Out-Null
$lock = [IO.File]::Open((Join-Path $StatePath 'build.lock'), 'OpenOrCreate', 'ReadWrite', 'None')
$saved = @{}
foreach ($name in @('HERMES_HOME','HERMES_RUNTIME_DIR','HERMES_PYTHON','HERMES_TEST_FILE_RETRIES','PATH')) {
    $saved[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
}
Push-Location $SourcePath
try {
    if (git status --porcelain --untracked-files=all) { throw 'Commit source changes before building an immutable candidate.' }
    $sha = (git rev-parse HEAD).Trim()
    git merge-base --is-ancestor $UpstreamTag HEAD
    $id = 'custom-' + $sha.Substring(0, 12)
    $candidate = Join-Path $StatePath "packages\$id"
    if (Test-Path -LiteralPath $candidate) { throw "Candidate already exists; retained unchanged: $candidate" }
    New-Item -ItemType Directory -Path $candidate -Force | Out-Null
    $env:HERMES_HOME = Join-Path $candidate 'test-home'
    $env:HERMES_RUNTIME_DIR = Join-Path $StatePath 'runtime'
    $env:HERMES_PYTHON = $TestPython.Replace('\', '/')
    $env:HERMES_TEST_FILE_RETRIES = '0'
    $env:PATH = (Split-Path $Bash) + ';C:\Program Files\Git\usr\bin;' + $env:PATH
    $testFiles = @(Get-ChildItem tests/agent,tests/tools,tests/hermes_cli -File | Where-Object {
        $_.Name -match '^(test_verification.*|test_write_approval.*|test_memory_tool.*|test_skill_manager_tool|test_doctor.*)\.py$'
    } | ForEach-Object { [IO.Path]::GetRelativePath($SourcePath, $_.FullName).Replace('\', '/') })
    & $Bash scripts/run_tests.sh @testFiles -j 4 --tb=short *> (Join-Path $candidate 'tests.log')
    & $TestPython scripts/check --base $UpstreamTag *> (Join-Path $candidate 'checks.log')
    $archive = Join-Path $candidate 'hermes-custom-source.zip'
    git archive --format=zip "--output=$archive" HEAD
    $source = Join-Path $candidate 'source'
    Expand-Archive -LiteralPath $archive -DestinationPath $source
    $venv = Join-Path $candidate 'venv'
    & $BootstrapPython -m pm.build_env --source $source --out $venv *> (Join-Path $candidate 'build.log')
    $candidatePython = Join-Path $venv 'Scripts\python.exe'
    Push-Location $source
    try {
        & $candidatePython custom/smoke_candidate.py *> (Join-Path $candidate 'smoke.log')
        & $candidatePython -m hermes_cli.main --version *> (Join-Path $candidate 'version.log')
    } finally { Pop-Location }
    $manifest = [ordered]@{
        schemaVersion = 1; repository = 'qwer36613698/hermes-agent'; sourceCommit = $sha
        upstreamTag = $UpstreamTag; candidateTag = $id; builtAt = [DateTime]::UtcNow.ToString('o')
        platform = 'windows-x64'; packageType = 'source-with-local-cli-environment'
        testsPassed = $true; smokePassed = $true
        archive = 'hermes-custom-source.zip'; sha256 = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
        sourcePath = $source; python = $candidatePython; installPolicy = 'manual-approval'
        limitations = @('No desktop MSIX built or UI tested.', 'Local environment uses the managed Python runtime; source ZIP is not a standalone installer.')
    }
    $manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $candidate 'custom-update.json') -Encoding utf8
    Write-Output (Join-Path $candidate 'custom-update.json')
} finally {
    Pop-Location
    foreach ($name in $saved.Keys) { [Environment]::SetEnvironmentVariable($name, $saved[$name], 'Process') }
    $lock.Dispose()
}
