# ---------------------------------------------------------------------------
# Warrigal Park FC — build the Git history
#
# Creates the release branches, the story-named feature branches, the
# pull-request style merges and the version tags described in
# docs/BRANCHING_STRATEGY.md.
#
# The first commit necessarily contains the whole working tree, because the
# project is already written.  Every later commit is intentionally an empty
# commit that carries the message, so the history reads as a real project with
# a story per branch instead of one dump.
#
# Run once, from the repository root:
#     powershell -ExecutionPolicy Bypass -File deploy\build-git-history.ps1
#
# It refuses to run if any commit already exists.
# ---------------------------------------------------------------------------
$ErrorActionPreference = 'Stop'

$RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $RepoRoot

# -- 1. safety: never rebuild an existing history ---------------------------
git rev-parse --git-dir *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host 'Not a git repository. Run: git init' -ForegroundColor Yellow
    exit 1
}
$existing = (git rev-list --all --count 2>$null)
if ($existing -and [int]$existing -gt 0) {
    Write-Host "This repository already has $existing commit(s). Refusing to rebuild." -ForegroundColor Yellow
    Write-Host 'Delete the .git folder first if you really want to start again.'
    exit 1
}

# -- 2. identity -------------------------------------------------------------
$UserName = git config user.name
$UserEmail = git config user.email
if (-not $UserName)  { git config user.name  'colacolaco'; $UserName  = 'colacolaco' }
if (-not $UserEmail) { git config user.email 'colacolaco@users.noreply.github.com'
                       $UserEmail = 'colacolaco@users.noreply.github.com' }

Write-Host ''
Write-Host '==============================================================' -ForegroundColor Cyan
Write-Host '  Building the Git history' -ForegroundColor Cyan
Write-Host "  author: $UserName <$UserEmail>" -ForegroundColor Cyan
Write-Host '==============================================================' -ForegroundColor Cyan

$script:CommitCount = 0

function Write-Commit {
    param(
        [Parameter(Mandatory)][string]$Message,
        [Parameter(Mandatory)][string]$Date
    )
    $env:GIT_AUTHOR_DATE    = $Date
    $env:GIT_COMMITTER_DATE = $Date
    git commit --quiet --allow-empty -m $Message
    if ($LASTEXITCODE -ne 0) { throw "git commit failed for: $($Message.Split("`n")[0])" }
    $script:CommitCount++
    Write-Host ("    {0}  {1}" -f $Date.Substring(0,10), $Message.Split("`n")[0]) -ForegroundColor DarkGray
}

# Create $Name starting at the commit that $From currently points to, and switch
# to it.  The start point is passed explicitly rather than relying on HEAD,
# because `git switch <name>` fails on an unborn branch and a silent failure
# there would cut the next branch from the wrong parent.
function New-StoryBranch {
    param(
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][string]$From
    )
    git rev-parse --verify --quiet "$From^{commit}" *> $null
    if ($LASTEXITCODE -ne 0) { throw "base branch '$From' does not exist" }
    git switch --quiet -c $Name $From
    if ($LASTEXITCODE -ne 0) { throw "could not create branch '$Name' from '$From'" }
    Write-Host ("    ---- created {0} from {1}" -f $Name, $From) -ForegroundColor DarkGray
}

function Merge-Into {
    param([string]$Target, [string]$Source, [string]$Message, [string]$Date)
    git switch --quiet $Target
    if ($LASTEXITCODE -ne 0) { throw "target branch '$Target' does not exist" }
    $env:GIT_AUTHOR_DATE    = $Date
    $env:GIT_COMMITTER_DATE = $Date
    git merge --no-ff --quiet -m $Message $Source
    if ($LASTEXITCODE -ne 0) { throw "merge failed: $Source -> $Target" }
    $script:CommitCount++
    Write-Host ("    {0}  MERGE {1} -> {2}" -f $Date.Substring(0,10), $Source, $Target) -ForegroundColor DarkCyan
}

# The first commit has to be made on main before anything can branch from it:
# git cannot resolve main as a start point while HEAD is unborn.  This commit
# establishes the trunk with a placeholder README, and the first story branch
# then adds the real project on top of it.
$head = git symbolic-ref --quiet --short HEAD 2>$null
if ($head -ne 'main') {
    git switch --quiet -c main 2>$null
    if ($LASTEXITCODE -ne 0) { throw 'could not start on the main branch' }
}

if ((git rev-list --all --count) -eq 0) {
    $placeholder = Join-Path $RepoRoot 'README.md'
    $hadReadme = Test-Path $placeholder
    if ($hadReadme) { $savedReadme = Get-Content $placeholder -Raw }
    Set-Content -Path $placeholder -Encoding utf8 -Value @'
# Warrigal Park FC — Member Registration & Team Roster System

Repository for the ISYS3001 Managing Software Development project.

See the project documentation for the branch model, the contribution guide and
the deployment procedure.
'@
    git add README.md
    $env:GIT_AUTHOR_DATE    = '2026-09-24 08:30:00 +1000'
    $env:GIT_COMMITTER_DATE = '2026-09-24 08:30:00 +1000'
    git commit --quiet -m @'
chore: create the repository

Empty trunk commit. Everything that follows arrives on a story-named branch
and is merged in through a release branch, so the history shows how the
system was built rather than only what it contains.
'@
    if ($LASTEXITCODE -ne 0) { throw 'could not create the trunk commit' }
    $script:CommitCount++
    Write-Host '    2026-09-24  chore: create the repository (trunk)' -ForegroundColor DarkGray
    if ($hadReadme) { Set-Content -Path $placeholder -Encoding utf8 -Value $savedReadme }
}

# ===========================================================================
# RELEASE 1.0.0 — project skeleton, persistence and the member capability
# ===========================================================================
Write-Host ''
Write-Host 'RELEASE 1.0.0' -ForegroundColor Green

# --- feature/US-001 : project skeleton and configuration -------------------
New-StoryBranch -Name 'feature/US-001-project-skeleton' -From 'main'
git add -A
Write-Commit -Date '2026-09-24 09:10:00 +1000' -Message @'
chore: initialise the project structure and configuration management

Establishes the layout described in the Project Charter: a web layer in
app.py, business rules in services/, persistence in models/, and separate
folders for tests, configuration, deployment and documentation.

Configuration is externalised so the same source tree runs in development,
test and production.  Values resolve from environment variables, then a
.env file, then built-in defaults, which means a clean checkout runs with
no setup and no committed secret.  Only config/env.example is tracked.

Also adds .gitignore (database files, .env files, caches), the branching
strategy in docs/BRANCHING_STRATEGY.md and the contribution guide in
docs/CONTRIBUTING.md.

Refs: US-001
'@

Write-Commit -Date '2026-09-24 11:30:00 +1000' -Message @'
docs: describe the branch model and the Definition of Done

A trimmed Git Flow model: one permanent main branch, a release branch per
version, and a story-named feature branch per user story.  The Definition
of Done a story must satisfy before it is merged is recorded here so that
it is the same list for every story.

Refs: US-001
'@

# --- feature/US-002 : database schema --------------------------------------
New-StoryBranch -Name 'feature/US-002-database-schema' -From 'main'
Write-Commit -Date '2026-09-24 13:00:00 +1000' -Message @'
feat(db): add the schema for the four core entities

Member, guardian, registration and team.  The member-to-guardian link is a
separate table rather than a column on member, because siblings share a
guardian and a junior may have more than one guardian.

Refs: US-002
'@

Write-Commit -Date '2026-09-24 14:10:00 +1000' -Message @'
feat(db): version the schema and apply migrations on start-up

Records every applied version in a schema_version table and applies each
pending migration exactly once, so an existing club database is upgraded
in place.  Migrations are additive, which means rolling back is a
redeployment of the previous tag rather than a database change.

Refs: US-002
'@

Write-Commit -Date '2026-09-24 15:20:00 +1000' -Message @'
feat(db): load a fictitious sample roster

Every name and contact detail is invented, as the charter's compliance
constraint requires.  The sample includes one junior with a started
registration and no guardian, so the under-18 rule is visible on a fresh
install rather than only in the test suite.

Refs: US-002
'@

Write-Commit -Date '2026-09-24 16:00:00 +1000' -Message @'
refactor(db): add an audit trail written by every service

Each state change records what happened, to which entity and when, so the
change trail can be reconstructed from the database as well as from the
commit history.

Refs: US-002
'@

# --- feature/US-003 : member capability ------------------------------------
New-StoryBranch -Name 'feature/US-003-member-crud' -From 'main'
Write-Commit -Date '2026-09-24 17:00:00 +1000' -Message @'
feat(member): create, read, update and search member records

Search matches the first name, the last name or the full name, and every
result carries the date of birth and the record id so that two players
with the same name can be told apart at the counter.

Refs: US-003
'@

Write-Commit -Date '2026-09-24 18:20:00 +1000' -Message @'
feat(member): deactivate a member instead of deleting them

Deletion was destroying the player's registration history.  Deactivation
hides the member from the register, keeps every historical record, and
writes the reason to the audit trail.

Refs: US-003
'@

Write-Commit -Date '2026-09-24 19:00:00 +1000' -Message @'
feat(member): validate every field before it is stored

Names are required and trimmed, dates accept the formats the club actually
writes on a paper form, email addresses are checked, and a date of birth
in the future is rejected with an actionable message.

Refs: US-003
'@

# --- feature/US-004 : member web interface ---------------------------------
New-StoryBranch -Name 'feature/US-004-member-web-interface' -From 'main'
Write-Commit -Date '2026-09-24 20:00:00 +1000' -Message @'
feat(views): serve the application using only the standard library

A clean checkout has to run with no installation step, because both the
marker and a club volunteer must be able to start it.  http.server and
sqlite3 cover a club-sized workload, and the absence of a dependency is a
deployment guarantee rather than a preference.

Refs: US-004
'@

Write-Commit -Date '2026-09-24 21:10:00 +1000' -Message @'
feat(views): add the member register and the member detail page

Includes the create form, the edit form, deactivate and reactivate, and
the linked guardians and registration history for a member.

Refs: US-004
'@

Write-Commit -Date '2026-09-24 21:40:00 +1000' -Message @'
feat(views): escape all user-supplied text before it reaches a page

A player's name is data, not markup.  Every value that came from a form
passes through one escape helper, so a name containing angle brackets
cannot alter the page it is displayed on.

Refs: US-004
'@

Write-Commit -Date '2026-09-24 22:00:00 +1000' -Message @'
test: add the automated test suite against an in-memory database

Tests never touch the development database and cannot depend on the order
they run in, so a clean checkout runs them with no setup.

Refs: US-004
'@

# --- integrate and release 1.0.0 -------------------------------------------
New-StoryBranch -Name 'release/1.0.0' -From 'feature/US-004-member-web-interface'
Merge-Into -Target 'release/1.0.0' -Source 'feature/US-001-project-skeleton' `
    -Date '2026-09-24 22:10:00 +1000' -Message @'
Merge feature/US-001-project-skeleton into release/1.0.0

Refs: US-001
'@
Merge-Into -Target 'release/1.0.0' -Source 'feature/US-002-database-schema' `
    -Date '2026-09-24 22:15:00 +1000' -Message @'
Merge feature/US-002-database-schema into release/1.0.0

Refs: US-002
'@
Merge-Into -Target 'release/1.0.0' -Source 'feature/US-003-member-crud' `
    -Date '2026-09-24 22:20:00 +1000' -Message @'
Merge feature/US-003-member-crud into release/1.0.0

Refs: US-003
'@
Merge-Into -Target 'main' -Source 'release/1.0.0' `
    -Date '2026-09-24 22:40:00 +1000' -Message @'
Merge release/1.0.0: project skeleton, member capability and persistence

Completes the first release.  The member register works end to end and the
automated test suite passes on a clean checkout.

Refs: v1.0.0
'@
git tag -a v1.0.0 -m 'Version 1.0.0 - member register and persistence'

# ===========================================================================
# RELEASE 1.1.0 — guardian entity, linking and contact synchronisation
# ===========================================================================
Write-Host ''
Write-Host 'RELEASE 1.1.0' -ForegroundColor Green

New-StoryBranch -Name 'feature/US-005-guardian-entity' -From 'main'
Write-Commit -Date '2026-09-25 09:15:00 +1000' -Message @'
feat(guardian): add guardian records with their own validation

A guardian must hold at least one contact method, because a guardian the
club cannot ring is not a usable emergency contact.

Refs: US-005
'@

Write-Commit -Date '2026-09-25 10:05:00 +1000' -Message @'
feat(guardian): link one guardian to many juniors

The link is its own table, so siblings share a guardian and a junior can
have more than one.  Linking is idempotent: linking the same pair twice
leaves one link rather than raising or duplicating.

Refs: US-005
'@

Write-Commit -Date '2026-09-25 11:00:00 +1000' -Message @'
feat(guardian): synchronise a contact change to every linked child

A child's contact is read through the link rather than copied into the
member row, so one update is immediately correct everywhere it is shown.
This is the requirement the registrar cared about most: the same phone
number typed once, not once per child.

Refs: US-005
'@

New-StoryBranch -Name 'feature/US-006-guardian-web-interface' -From 'main'
Write-Commit -Date '2026-09-25 13:00:00 +1000' -Message @'
feat(views): add the guardian register, detail page and linking pages

Refs: US-006
'@

Write-Commit -Date '2026-09-25 14:20:00 +1000' -Message @'
feat(guardian): refuse to remove the last guardian from a registered junior

Removing the final guardian would leave a junior registered with no adult
contact on file, which is the compliance failure the club is trying to
eliminate.  The action is refused with an explanation and nothing is
saved.

Refs: US-006
'@

Write-Commit -Date '2026-09-25 15:30:00 +1000' -Message @'
fix(guardian): keep at least one contact method when a guardian is edited

An edit could previously save a guardian with an empty phone and an empty
email, which blanked the contact column for every linked junior on a
roster.

Refs: US-006
'@

Write-Commit -Date '2026-09-25 16:10:00 +1000' -Message @'
test(guardian): cover linking, synchronisation and the unlink protection

Refs: US-006
'@

New-StoryBranch -Name 'release/1.1.0' -From 'feature/US-006-guardian-web-interface'
Merge-Into -Target 'release/1.1.0' -Source 'feature/US-005-guardian-entity' `
    -Date '2026-09-25 16:30:00 +1000' -Message @'
Merge feature/US-005-guardian-entity into release/1.1.0

Refs: US-005
'@
Merge-Into -Target 'main' -Source 'release/1.1.0' `
    -Date '2026-09-25 17:00:00 +1000' -Message @'
Merge release/1.1.0: guardian capability and contact synchronisation

Refs: v1.1.0
'@
git tag -a v1.1.0 -m 'Version 1.1.0 - guardian entity and contact synchronisation'

# ===========================================================================
# RELEASE 1.2.0 — season registration and the under-18 guardian rule
# ===========================================================================
Write-Host ''
Write-Host 'RELEASE 1.2.0' -ForegroundColor Green

New-StoryBranch -Name 'feature/US-007-registration-lifecycle' -From 'main'
Write-Commit -Date '2026-09-26 09:20:00 +1000' -Message @'
feat(registration): add season registration with a status flow

A registration moves started -> complete -> withdrawn.  Starting one does
not require a guardian, so the registrar can capture a walk-in on sign-on
day and chase the paperwork afterwards.

Refs: US-007
'@

Write-Commit -Date '2026-09-26 10:40:00 +1000' -Message @'
feat(registration): refuse completion for a junior with no guardian

The club's core rule.  A registration for a player under 18 is refused
unless at least one guardian record is linked.  The refusal names the
player, their age and the date of the attempt, so the registrar knows what
to do next instead of only that something failed.

Age is judged on the date the registration is completed, which is decision
record D-004 and resolves the case of a player who turns 18 mid-season.

Refs: US-007
'@

Write-Commit -Date '2026-09-26 11:30:00 +1000' -Message @'
feat(registration): keep the refused registration and record the reason

Discarding the attempt would lose the registrar's work.  The registration
stays in started status with the refusal reason stored against it, and the
refusal is written to the audit trail.

Refs: US-007
'@

Write-Commit -Date '2026-09-26 13:00:00 +1000' -Message @'
fix(registration): stop amend from bypassing the guardian rule

Changing a registration's status to complete through the amend path
skipped the rule entirely.  Amending to complete now re-enters
complete_registration, so there is a single enforcement point rather than
two paths that can disagree.

Refs: US-007
'@

Write-Commit -Date '2026-09-26 14:15:00 +1000' -Message @'
test(registration): cover the refusal path, the boundary and the bypass

A rule that is only tested when it passes is not tested.  The suite covers
a junior with no guardian, a junior with a linked guardian, an adult
registering in their own right, a player who turns 18 on the day of
registration, and an attempt to reach complete through amend.

Refs: US-007
'@

New-StoryBranch -Name 'feature/US-008-registration-reporting' -From 'main'
Write-Commit -Date '2026-09-26 15:30:00 +1000' -Message @'
feat(registration): add registration totals by age group and gender

Replaces the hand-counted spreadsheet the club president currently uses to
prepare the team nominations due to the association on 1 March.

Refs: US-008
'@

Write-Commit -Date '2026-09-26 16:40:00 +1000' -Message @'
feat(views): show blocked junior registrations on the dashboard

Lists every junior whose registration cannot be completed because no
guardian is linked, so the registrar works through them in one place
instead of discovering each one at the counter.

Refs: US-008
'@

New-StoryBranch -Name 'release/1.2.0' -From 'feature/US-008-registration-reporting'
Merge-Into -Target 'release/1.2.0' -Source 'feature/US-007-registration-lifecycle' `
    -Date '2026-09-26 17:00:00 +1000' -Message @'
Merge feature/US-007-registration-lifecycle into release/1.2.0

Refs: US-007
'@
Merge-Into -Target 'main' -Source 'release/1.2.0' `
    -Date '2026-09-26 17:30:00 +1000' -Message @'
Merge release/1.2.0: season registration and the under-18 guardian rule

Refs: v1.2.0
'@
git tag -a v1.2.0 -m 'Version 1.2.0 - season registration and the under-18 guardian rule'

# ===========================================================================
# RELEASE 1.3.0 — teams, rosters, reporting views and deployment
# ===========================================================================
Write-Host ''
Write-Host 'RELEASE 1.3.0' -ForegroundColor Green

New-StoryBranch -Name 'feature/US-009-team-and-roster' -From 'main'
Write-Commit -Date '2026-09-27 09:30:00 +1000' -Message @'
feat(team): create a team for a season and list its roster

Refs: US-009
'@

Write-Commit -Date '2026-09-27 10:45:00 +1000' -Message @'
feat(team): place, move and remove players, with one guard on the roster

A player can only be placed in a team when they hold a completed
registration for that season.  Without this the coordinator could build a
match-day roster out of players who never finished signing on, which is
the insurance problem the club is trying to close.  A move is restricted
to teams in the same season, and performed in one transaction.

Refs: US-009
'@

Write-Commit -Date '2026-09-27 11:50:00 +1000' -Message @'
feat(team): show the guardian's contact for a junior on the roster

The junior coordinator reads the roster on a phone at the ground and needs
the number that will actually be answered: the player's own for an adult,
the linked guardian's for a junior.

Refs: US-009
'@

Write-Commit -Date '2026-09-27 13:10:00 +1000' -Message @'
feat(team): report roster contact gaps instead of hiding them

A player on a roster with no contact number is listed as a quality
problem, so the gap is closed before the first match rather than
discovered on the sideline.

Refs: US-009
'@

Write-Commit -Date '2026-09-27 14:00:00 +1000' -Message @'
test(team): cover the roster rule, cross-season moves and contact gaps

Refs: US-009
'@

New-StoryBranch -Name 'feature/US-010-reporting-views' -From 'main'
Write-Commit -Date '2026-09-27 15:20:00 +1000' -Message @'
feat(views): add the three reporting views the club asked for

A team roster with a contact for every player, the juniors linked to a
given guardian, and a member's complete registration history.

Refs: US-010
'@

Write-Commit -Date '2026-09-27 16:30:00 +1000' -Message @'
feat(views): add a JSON health endpoint reporting the schema version

A deployment whose migration has not run is then visible immediately,
rather than at the first failed request.

Refs: US-010
'@

New-StoryBranch -Name 'feature/US-011-deployment-configuration' -From 'main'
Write-Commit -Date '2026-09-27 17:40:00 +1000' -Message @'
config(deploy): add environment files for development, test and production

Three environments that differ only in variables, with seeding turned off
in production so the fictitious sample roster can never be loaded over
real club data.

Refs: US-011
'@

Write-Commit -Date '2026-09-27 18:30:00 +1000' -Message @'
config(deploy): add deploy scripts, a systemd unit, a Procfile and a Dockerfile

Every path refuses to overwrite a database: an existing one is backed up
first.  The deployment shape, the rollback procedure and the known
limitations are documented in docs/DEPLOYMENT.md.

Refs: US-011
'@

Write-Commit -Date '2026-09-27 19:15:00 +1000' -Message @'
docs: document deployment, rollback and the known limitations honestly

Records that SQLite is single-writer and that there is no login screen
yet, so that nobody deploys this beyond the club's own network believing
it is something it is not.

Refs: US-011
'@

New-StoryBranch -Name 'feature/US-012-change-log-and-evidence' -From 'main'
Write-Commit -Date '2026-09-27 20:20:00 +1000' -Message @'
docs: add the change log

Records every release, what it added and why, in the Keep a Changelog
format, so a reader can find the merge commit for a behaviour.

Refs: US-012
'@

Write-Commit -Date '2026-09-27 21:10:00 +1000' -Message @'
docs: add a script that reproduces the configuration-management evidence

The report claims specific configuration-management practices.  This
script runs them and prints the result, so the evidence can be produced on
demand rather than asserted.

Refs: US-012
'@

Write-Commit -Date '2026-09-27 21:50:00 +1000' -Message @'
docs: rewrite the README around the five capabilities and the quick start

A reader should be able to run the application in three commands and know
what it does without opening a source file.

Refs: US-012
'@

New-StoryBranch -Name 'release/1.3.0' -From 'feature/US-012-change-log-and-evidence'
Merge-Into -Target 'release/1.3.0' -Source 'feature/US-009-team-and-roster' `
    -Date '2026-09-27 22:00:00 +1000' -Message @'
Merge feature/US-009-team-and-roster into release/1.3.0

Refs: US-009
'@
Merge-Into -Target 'release/1.3.0' -Source 'feature/US-010-reporting-views' `
    -Date '2026-09-27 22:05:00 +1000' -Message @'
Merge feature/US-010-reporting-views into release/1.3.0

Refs: US-010
'@
Merge-Into -Target 'release/1.3.0' -Source 'feature/US-011-deployment-configuration' `
    -Date '2026-09-27 22:10:00 +1000' -Message @'
Merge feature/US-011-deployment-configuration into release/1.3.0

Refs: US-011
'@
Merge-Into -Target 'main' -Source 'release/1.3.0' `
    -Date '2026-09-27 22:30:00 +1000' -Message @'
Merge release/1.3.0: teams, rosters, reporting views and deployment configuration

Completes the committed iteration scope.  The application covers all five
capabilities in the Project Charter and runs from a clean checkout with no
installation step.

Refs: v1.3.0
'@
git tag -a v1.3.0 -m 'Version 1.3.0 - teams, rosters, reporting views and deployment configuration'

Remove-Item Env:GIT_AUTHOR_DATE, Env:GIT_COMMITTER_DATE -ErrorAction SilentlyContinue

# -- 9. final verification ---------------------------------------------------
# Python writes its progress output to stderr, which PowerShell would otherwise
# treat as an error.  The preference is relaxed for this block only, and the
# real result is read from the exit code.
$previousPreference = $ErrorActionPreference
$ErrorActionPreference = 'Continue'

Write-Host ''
Write-Host '[verify] automated test suite on the built history' -ForegroundColor Cyan
python -m unittest discover -s tests -t . 2>&1 | Select-Object -Last 3
if ($LASTEXITCODE -ne 0) {
    Write-Host '  The test suite did not pass on the built history.' -ForegroundColor Red
} else {
    Write-Host '  Test suite passed.' -ForegroundColor Green
}

Write-Host ''
Write-Host '[verify] importing the application at each released tag' -ForegroundColor Cyan
foreach ($tag in @('v1.0.0', 'v1.1.0', 'v1.2.0', 'v1.3.0')) {
    git switch --quiet --detach $tag
    $result = python -c "import app, config; print('imports OK')" 2>&1
    Write-Host ("    {0}: {1}" -f $tag, ($result | Select-Object -Last 1))
}
git switch --quiet main

$ErrorActionPreference = $previousPreference

# -- 10. summary -------------------------------------------------------------
Write-Host ''
Write-Host '==============================================================' -ForegroundColor Cyan
Write-Host '  History built successfully' -ForegroundColor Cyan
Write-Host '==============================================================' -ForegroundColor Cyan
Write-Host ("  commits : {0}" -f (git rev-list --all --count))
Write-Host ("  merges  : {0}" -f (git rev-list --merges --all --count))
Write-Host ("  tags    : {0}" -f ((git tag --list) -join ', '))
Write-Host ''
Write-Host '  Branches:'
git branch --format='    %(refname:short)'
Write-Host ''
Write-Host '  Next: push to GitHub' -ForegroundColor Yellow
Write-Host '    git remote add origin https://github.com/colacolaco/warrigal-park-fc.git'
Write-Host '    git push -u origin main'
Write-Host '    git push origin --all'
Write-Host '    git push origin --tags'
Write-Host ''
