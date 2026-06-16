param(
    [string]$Tag = "v1.0",
    [string]$ArchivePath = "releases/WB-analyst-v1.0.zip",
    [string]$LatestJsonPath = "latest.json",
    [string]$Title = "WB analyst v1.0",
    [string]$Notes = "Stable Windows build of WB analyst.",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

function Resolve-RequiredPath {
    param([string]$PathToCheck)
    $resolved = Resolve-Path -LiteralPath $PathToCheck -ErrorAction SilentlyContinue
    if (-not $resolved) {
        throw "File not found: $PathToCheck"
    }
    return $resolved.Path
}

$archive = Resolve-RequiredPath $ArchivePath
$latestJson = Resolve-RequiredPath $LatestJsonPath

$tagExists = $false
git rev-parse -q --verify "refs/tags/$Tag" *> $null
if ($LASTEXITCODE -eq 0) {
    $tagExists = $true
}

if (-not $tagExists) {
    throw "Git tag '$Tag' was not found locally. Create and push the tag before publishing the release."
}

if ($DryRun) {
    Write-Host "Dry run: would publish GitHub Release '$Tag'"
    Write-Host "Archive: $archive"
    Write-Host "latest.json: $latestJson"
    Write-Host "Command:"
    Write-Host "gh release create $Tag `"$archive`" `"$latestJson`" --verify-tag --title `"$Title`" --notes `"$Notes`" --latest"
    exit 0
}

gh --version *> $null
gh auth status *> $null
if ($LASTEXITCODE -ne 0) {
    throw "GitHub CLI is not authenticated. Run: gh auth login"
}

$releaseExists = $false
gh release view $Tag *> $null
if ($LASTEXITCODE -eq 0) {
    $releaseExists = $true
}

if ($releaseExists) {
    gh release upload $Tag "$archive" "$latestJson" --clobber
} else {
    gh release create $Tag "$archive" "$latestJson" --verify-tag --title "$Title" --notes "$Notes" --latest
}

if ($LASTEXITCODE -ne 0) {
    throw "GitHub Release publishing failed."
}

Write-Host "GitHub Release '$Tag' is ready."
