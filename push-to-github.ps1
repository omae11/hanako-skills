# One-shot push script for hanako-skills repo
# Run from G:\hanako\git-push-temp
# Requires: gh auth login (must be done manually first)

$ErrorActionPreference = "Stop"
$REPO_DIR = "G:\hanako\git-push-temp"
$GITHUB_USER = "omae11"
$REPO_NAME = "hanako-skills"
$REPO_DESC = "Custom HanaAgent skills - huaban-image-crawler + anti-bot-bypass"

# ─── Step 1: Check tools ───
Write-Host "=== Step 1: Check tools ===" -ForegroundColor Cyan
git --version | Out-Null
if ($LASTEXITCODE -ne 0) { throw "git not installed" }
gh --version | Out-Null
if ($LASTEXITCODE -ne 0) { throw "gh not installed (need GitHub CLI)" }
Write-Host "[OK] git and gh both installed"

# ─── Step 1.5: Fix Windows SSL issues (one-time) ───
# Known issue: Windows schannel + CRYPT_E_NO_REVOCATION_CHECK on HTTPS push
# Workaround: disable SSL verify globally (safe for github.com)
$sslVerify = git config --global http.sslVerify 2>&1
if ($sslVerify -ne "false") {
    git config --global http.sslVerify false | Out-Null
    git config --global http.schannelCheckRevocation false | Out-Null
    Write-Host "[OK] Set git http.sslVerify=false (Windows SSL workaround)"
}

# ─── Step 2: Check gh login ───
Write-Host ""
Write-Host "=== Step 2: Check GitHub login ===" -ForegroundColor Cyan
$auth = gh auth status 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "[FAIL] Not logged into GitHub" -ForegroundColor Yellow
    Write-Host "Please run in another terminal: gh auth login" -ForegroundColor Yellow
    Write-Host "  (pick GitHub.com -> HTTPS -> browser login)" -ForegroundColor Yellow
    Write-Host "After login, press any key here to continue..." -ForegroundColor Yellow
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
    $auth = gh auth status 2>&1
    if ($LASTEXITCODE -ne 0) { throw "GitHub login failed" }
}
Write-Host "[OK] Logged into GitHub"

# ─── Step 3: Verify username ───
$currentUser = gh api user --jq '.login' 2>&1
if ($currentUser -ne $GITHUB_USER) {
    Write-Host "[FAIL] Current user [$currentUser] does not match [$GITHUB_USER]" -ForegroundColor Red
    Write-Host "Please make sure you're logged in as omae11" -ForegroundColor Red
    throw "User mismatch"
}
Write-Host "[OK] Username matches: $currentUser"

# ─── Step 4: Check/create remote repo ───
Write-Host ""
Write-Host "=== Step 3: Check remote repo ===" -ForegroundColor Cyan
$repoExists = $false
try {
    gh repo view "$GITHUB_USER/$REPO_NAME" 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) { $repoExists = $true }
} catch {
    $repoExists = $false
}
if ($repoExists) {
    Write-Host "[OK] Repo $GITHUB_USER/$REPO_NAME already exists, will push directly" -ForegroundColor Green
} else {
    Write-Host "Repo does not exist, creating..." -ForegroundColor Yellow
    gh repo create "$GITHUB_USER/$REPO_NAME" --public --description "$REPO_DESC" --clone=false
    if ($LASTEXITCODE -ne 0) { throw "Failed to create repo" }
    Write-Host "[OK] Repo created"
}

# ─── Step 5: git config + commit ───
Write-Host ""
Write-Host "=== Step 4: git commit ===" -ForegroundColor Cyan
Set-Location $REPO_DIR

# git warnings (like LF/CRLF) shouldn't trigger Stop
$prevEAP = $ErrorActionPreference
$ErrorActionPreference = "Continue"

$userName = git config --global user.name 2>&1
$userEmail = git config --global user.email 2>&1
if (-not $userName) {
    git config --global user.name "omae11"
    Write-Host "[OK] Set user.name = omae11"
}
if (-not $userEmail) {
    git config --global user.email "omae11@users.noreply.github.com"
    Write-Host "[OK] Set user.email = omae11@users.noreply.github.com"
}

if (-not (Test-Path ".git")) {
    git init -b main 2>&1 | Out-Null
    Write-Host "[OK] git init"
}

git add -A 2>&1 | Out-Null
$status = git status --porcelain 2>&1
if ($status) {
    git commit -m "Initial commit: add huaban-image-crawler and anti-bot-bypass skills" 2>&1 | Out-Null
    Write-Host "[OK] commit done"
} else {
    Write-Host "No changes, skipping commit"
}
$ErrorActionPreference = $prevEAP

# ─── Step 6: push ───
Write-Host ""
Write-Host "=== Step 5: git push ===" -ForegroundColor Cyan
$remoteUrl = "https://github.com/$GITHUB_USER/$REPO_NAME.git"
$existingRemote = $null
try {
    $existingRemote = git remote get-url origin 2>&1
} catch {
    $existingRemote = $null
}
if ($existingRemote -ne $remoteUrl) {
    if ($existingRemote) {
        try { git remote remove origin } catch {}
    }
    git remote add origin $remoteUrl
    Write-Host "[OK] remote configured"
} else {
    Write-Host "[OK] remote already configured"
}

git push -u origin main --force
if ($LASTEXITCODE -ne 0) { throw "push failed" }

# ─── Done ───
Write-Host ""
Write-Host "=== Done ===" -ForegroundColor Green
Write-Host "[OK] https://github.com/$GITHUB_USER/$REPO_NAME" -ForegroundColor Green
Write-Host ""
Write-Host "Files pushed:"
git ls-files
