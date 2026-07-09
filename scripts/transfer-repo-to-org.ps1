param(
    [string]$Repository = "unknownboy-creator/dataq-seat-watcher",
    [string]$Organization = "miscellany-lab",
    [string]$RemoteName = "origin"
)

$ErrorActionPreference = "Stop"

function Require-Command {
    param([string]$Name)

    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "'$Name' command was not found. Install it first."
    }
}

Require-Command "git"
Require-Command "gh"

$repoName = ($Repository -split "/")[-1]
$targetRepository = "$Organization/$repoName"
$targetRemote = "https://github.com/$targetRepository.git"

Write-Host "Checking GitHub CLI authentication..."
gh auth status | Out-Host

Write-Host "Checking organization membership: $Organization"
$orgs = gh api user/orgs --jq ".[].login"
if ($orgs -notcontains $Organization) {
    Write-Error "Organization '$Organization' is not visible to this account. Create it first or check your permission."
    exit 2
}

$originalRemote = git remote get-url $RemoteName
Write-Host "Current $RemoteName remote: $originalRemote"

try {
    Write-Host "Transferring $Repository to $Organization..."
    gh api --method POST "/repos/$Repository/transfer" -f "new_owner=$Organization" | Out-Host

    Write-Host "Verifying transferred repository: $targetRepository"
    gh repo view $targetRepository --json nameWithOwner,url | Out-Host

    Write-Host "Updating $RemoteName remote: $targetRemote"
    git remote set-url $RemoteName $targetRemote

    Write-Host "Done."
    git remote -v
}
catch {
    Write-Warning "Transfer failed. Restoring $RemoteName remote to: $originalRemote"
    git remote set-url $RemoteName $originalRemote
    throw
}
