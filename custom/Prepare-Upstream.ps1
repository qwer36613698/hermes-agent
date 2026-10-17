# Manual preparation only: never installed or scheduled by this script.
[CmdletBinding()]
param(
    [string]$SourcePath = (Split-Path -Parent $PSScriptRoot),
    [string]$StatePath = 'D:\AI_Data\ManagedForks\hermes-agent',
    [string]$GhPath = 'D:\AI_Data\Tools\gh\bin\gh.exe'
)
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false
Set-StrictMode -Version Latest

function Invoke-Git([string[]]$GitArguments) {
    $result = & git -C $SourcePath @GitArguments
    if ($LASTEXITCODE -ne 0) { throw "git failed ($LASTEXITCODE): $($GitArguments[0])" }
    return $result
}
function Assert-NoReparseAncestor([string]$Directory) {
    $current = $Directory
    while ($current) {
        if (Test-Path -LiteralPath $current) {
            if ((Get-Item -LiteralPath $current -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) {
                throw "Reparse-point path is not allowed: $current"
            }
        }
        $parent = Split-Path -Parent $current
        if ($parent -eq $current) { break }
        $current = $parent
    }
}

$SourcePath = [IO.Path]::GetFullPath($SourcePath).TrimEnd('\', '/')
$StatePath = [IO.Path]::GetFullPath($StatePath).TrimEnd('\', '/')
Assert-NoReparseAncestor $SourcePath
Assert-NoReparseAncestor $StatePath
if (-not (Test-Path -LiteralPath $GhPath -PathType Leaf)) { throw 'GitHub CLI not found' }
$sourceRoot = (Invoke-Git @('rev-parse', '--show-toplevel') | Out-String).Trim()
if ([IO.Path]::GetFullPath($sourceRoot).TrimEnd('\', '/') -ne $SourcePath) { throw 'SourcePath must be the repository root' }
if ((Invoke-Git @('status', '--porcelain') | Out-String).Trim()) { throw 'Source worktree must be clean, including untracked files' }
$branch = (Invoke-Git @('branch', '--show-current') | Out-String).Trim()
if ($branch -ne 'custom/reliable-delivery') { throw 'Expected custom/reliable-delivery branch' }
$remote = (Invoke-Git @('remote', 'get-url', '--all', 'upstream') | Out-String).Trim()
if ($remote -cne 'https://github.com/NousResearch/hermes-agent.git') { throw 'Unexpected upstream remote URL' }
if ($StatePath -eq $SourcePath -or $StatePath.StartsWith($SourcePath + '\', [StringComparison]::OrdinalIgnoreCase) -or
    $SourcePath.StartsWith($StatePath + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'StatePath and source tree must be separate' }
New-Item -ItemType Directory -Path $StatePath -Force | Out-Null
try { $lock = [IO.File]::Open((Join-Path $StatePath 'prepare.lock'), 'OpenOrCreate', 'ReadWrite', 'None') }
catch [IO.IOException] { throw 'Another upstream preparation is running' }
try {
    $releaseJson = & $GhPath api 'repos/NousResearch/hermes-agent/releases/latest'
    if ($LASTEXITCODE -ne 0) { throw 'Cannot read latest official release' }
    $release = ($releaseJson | Out-String) | ConvertFrom-Json
    if ($release.draft -or $release.prerelease) { throw 'Only official stable releases are allowed' }
    $tag = [string]$release.tag_name
    if (-not $tag -or $tag.StartsWith('-')) { throw 'Invalid release tag' }
    Invoke-Git @('check-ref-format', "refs/tags/$tag") | Out-Null
    $remoteRefs = @(Invoke-Git @('ls-remote', '--tags', 'upstream', "refs/tags/$tag", "refs/tags/$tag^{}"))
    $tagSha = $null
    $peeledSha = $null
    foreach ($line in $remoteRefs) {
        $parts = $line -split '\s+', 2
        if ($parts.Count -ne 2 -or $parts[0] -notmatch '^[0-9a-f]{40}$') { throw 'Invalid upstream tag SHA' }
        if ($parts[1] -ceq "refs/tags/$tag") { $tagSha = $parts[0] }
        if ($parts[1] -ceq "refs/tags/$tag^{}") { $peeledSha = $parts[0] }
    }
    if (-not $tagSha) { throw 'Release tag does not exist on verified upstream' }
    $expectedCommit = if ($peeledSha) { $peeledSha } else { $tagSha }
    $unique = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ') + '-' + [Guid]::NewGuid().ToString('N')
    $fetchRef = "refs/managed-forks/hermes-agent/$unique"
    Invoke-Git @('fetch', '--no-tags', 'upstream', "refs/tags/${tag}:$fetchRef") | Out-Null
    $commit = (Invoke-Git @('rev-parse', '--verify', "$fetchRef^{commit}") | Out-String).Trim()
    if ($commit -notmatch '^[0-9a-f]{40}$' -or $commit -cne $expectedCommit) { throw 'Fetched tag commit does not match verified remote tag' }
    if (((Invoke-Git @('rev-parse', '--is-shallow-repository') | Out-String).Trim()) -eq 'true') {
        Invoke-Git @('fetch', '--unshallow', '--no-tags', 'upstream') | Out-Null
    }
    $baseCommit = (Invoke-Git @('rev-parse', '--verify', 'refs/heads/custom/reliable-delivery^{commit}') | Out-String).Trim()
    $candidateRoot = Join-Path $StatePath 'candidates'
    Assert-NoReparseAncestor $candidateRoot
    New-Item -ItemType Directory -Path $candidateRoot -Force | Out-Null
    $candidatePath = [IO.Path]::GetFullPath((Join-Path $candidateRoot $unique))
    if (-not $candidatePath.StartsWith($candidateRoot.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase) -or
        (Test-Path -LiteralPath $candidatePath)) { throw 'Unsafe or existing candidate path' }
    Invoke-Git @('worktree', 'add', '--detach', $candidatePath, $baseCommit) | Out-Null
    if ((& git -C $candidatePath status --porcelain | Out-String).Trim() -or $LASTEXITCODE -ne 0) { throw 'Candidate worktree is not clean' }
    & git -C $candidatePath merge --no-edit $commit
    if ($LASTEXITCODE -ne 0) {
        throw "Merge failed; candidate retained for manual resolution: $candidatePath. Main branch and installation were not changed."
    }
    [pscustomobject]@{
        WorktreePath = $candidatePath
        UpstreamTag = $tag
        UpstreamCommit = $commit
        BaseCommit = $baseCommit
        State = 'awaiting-build'
        NextStep = 'Run custom/Build-Candidate.ps1 with this worktree path; installation requires separate confirmation.'
    }
} finally { $lock.Dispose() }
