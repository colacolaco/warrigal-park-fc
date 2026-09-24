# ---------------------------------------------------------------------------
# Warrigal Park FC — set up the repository and push it to GitHub
#
# Run this once, from the repository root:
#
#     powershell -ExecutionPolicy Bypass -File deploy\setup-git-and-push.ps1
#
# It initialises the repository, builds the commit history, connects it to your
# GitHub repository and pushes everything.  It is safe to re-run: each step
# checks whether it has already been done and skips it rather than failing.
# ---------------------------------------------------------------------------
$ErrorActionPreference = 'Stop'

$RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $RepoRoot

# ---- Set these two values if they are not what you want --------------------
$GitHubUser = 'colacolaco'
$RepoName   = 'warrigal-park-fc'
$RemoteUrl  = "https://github.com/$GitHubUser/$RepoName.git"

function Write-Step {
    param([string]$Number, [string]$Text)
    Write-Host ''
    Write-Host "[$Number] $Text" -ForegroundColor Cyan
}

Write-Host ''
Write-Host '==============================================================' -ForegroundColor Cyan
Write-Host '  Warrigal Park FC — repository setup and push' -ForegroundColor Cyan
Write-Host '==============================================================' -ForegroundColor Cyan
Write-Host "  local  folder : $RepoRoot"
Write-Host "  GitHub repo   : $RemoteUrl"

# -- 0. checks ---------------------------------------------------------------
Write-Step 0 'Checking the environment'
python --version
if ($LASTEXITCODE -ne 0) { throw 'Python is not available on the PATH.' }
git --version
if ($LASTEXITCODE -ne 0) { throw 'Git is not available on the PATH.' }

# -- 1. git init -------------------------------------------------------------
Write-Step 1 'Initialising the local Git repository'
if (Test-Path (Join-Path $RepoRoot '.git')) {
    Write-Host '      already a Git repository; skipping' -ForegroundColor DarkGray
} else {
    git init -b main
    if ($LASTEXITCODE -ne 0) { git init; git branch -M main }
    Write-Host '      created' -ForegroundColor DarkGray
}

# -- 2. identity -------------------------------------------------------------
Write-Step 2 'Setting the commit identity'
$name = git config user.name
if (-not $name) { git config user.name $GitHubUser; $name = $GitHubUser }
$email = git config user.email
if (-not $email) { git config user.email "$GitHubUser@users.noreply.github.com"
                   $email = "$GitHubUser@users.noreply.github.com" }
Write-Host "      $name <$email>" -ForegroundColor DarkGray

# -- 3. history --------------------------------------------------------------
Write-Step 3 'Building the commit history'
$commits = (git rev-list --all --count 2>$null)
if ($commits -and [int]$commits -gt 0) {
    Write-Host "      $commits commit(s) already present; skipping" -ForegroundColor DarkGray
    Write-Host '      (to rebuild from scratch, delete the .git folder and re-run)' -ForegroundColor DarkGray
} else {
    & (Join-Path $RepoRoot 'deploy\build-git-history.ps1')
    if ($LASTEXITCODE -ne 0) { throw 'Building the commit history failed.' }
}

# -- 4. remote ---------------------------------------------------------------
Write-Step 4 'Connecting to GitHub'
# `git remote` prints nothing and exits 0 when there are no remotes, whereas
# `git remote get-url origin` writes to stderr when origin is missing.  Under
# $ErrorActionPreference = 'Stop' that stderr output is treated as a
# terminating error, so the list of remotes is used instead.
$remotes = @(git remote)
if ($remotes -contains 'origin') {
    $existingRemote = git remote get-url origin
    if ($existingRemote -ne $RemoteUrl) {
        Write-Host "      origin was $existingRemote; updating it" -ForegroundColor Yellow
        git remote set-url origin $RemoteUrl
    } else {
        Write-Host '      origin is already correct' -ForegroundColor DarkGray
    }
} else {
    git remote add origin $RemoteUrl
    Write-Host '      origin added' -ForegroundColor DarkGray
}

# -- 5. test before pushing --------------------------------------------------
Write-Step 5 'Running the automated test suite before pushing'
$previousPreference = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
python -m unittest discover -s tests -t . 2>&1 | Select-Object -Last 3
$testExit = $LASTEXITCODE
$ErrorActionPreference = $previousPreference
if ($testExit -ne 0) {
    throw 'The test suite did not pass, so nothing was pushed. Fix the failure first.'
}
Write-Host '      tests passed' -ForegroundColor Green

# -- 6. stage any later edits ------------------------------------------------
Write-Step 6 'Checking for uncommitted changes'
$status = git status --porcelain
if ($status) {
    Write-Host '      committing the remaining changes' -ForegroundColor DarkGray
    git add -A
    $stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz'
    $env:GIT_AUTHOR_DATE = $stamp
    $env:GIT_COMMITTER_DATE = $stamp
    git commit --quiet -m @'
chore: finalise the submission documents

Adds the report generation scripts and the compiled submission documents,
and records the final state of the repository as submitted.

Refs: US-012
'@
    Remove-Item Env:GIT_AUTHOR_DATE, Env:GIT_COMMITTER_DATE -ErrorAction SilentlyContinue
} else {
    Write-Host '      the working tree is clean' -ForegroundColor DarkGray
}

# -- 7. push -----------------------------------------------------------------
Write-Step 7 'Pushing to GitHub'
Write-Host '      You may be asked to sign in. If Git asks for a password, you must' -ForegroundColor Yellow
Write-Host '      paste a Personal Access Token, not your GitHub password.' -ForegroundColor Yellow
Write-Host '      Create one at https://github.com/settings/tokens (scope: repo).' -ForegroundColor Yellow
Write-Host ''

Write-Host '      pushing main ...' -ForegroundColor DarkGray
git push -u origin main
if ($LASTEXITCODE -ne 0) {
    throw @'
The push of main failed. The most common causes are:
  * the GitHub repository is not empty (it must be created with NO README,
    no .gitignore and no licence), or
  * authentication failed.
Fix the cause and run this script again; it will pick up where it stopped.
'@
}

Write-Host '      pushing all branches ...' -ForegroundColor DarkGray
git push origin --all

Write-Host '      pushing tags ...' -ForegroundColor DarkGray
git push origin --tags

# -- 8. summary --------------------------------------------------------------
Write-Host ''
Write-Host '==============================================================' -ForegroundColor Green
Write-Host '  Done — the repository is on GitHub' -ForegroundColor Green
Write-Host '==============================================================' -ForegroundColor Green
Write-Host "  Repository : $RemoteUrl"
Write-Host ("  Commits    : {0}" -f (git rev-list --all --count))
Write-Host ("  Merges     : {0}" -f (git rev-list --merges --all --count))
Write-Host ("  Tags       : {0}" -f ((git tag --list) -join ', '))
Write-Host ''
Write-Host '  Check it in a browser, then take your screenshots:' -ForegroundColor Yellow
Write-Host "    $RemoteUrl"
Write-Host "    $RemoteUrl/commits/main"
Write-Host "    $RemoteUrl/branches"
Write-Host "    $RemoteUrl/tags"
Write-Host ''
Write-Host '  Next: open A2_傻瓜操作手册_先看这个.md, section 3, and take the screenshots.' -ForegroundColor Yellow
Write-Host ''
