[CmdletBinding()]
param(
    [string]$OutputPath,
    [string]$VerificationPath,
    [switch]$Force
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$packageRoot = "model-atlas-mvp-review"
$dateStamp = Get-Date -Format "yyyyMMdd-HHmmss"

if ([string]::IsNullOrWhiteSpace($OutputPath)) {
    $OutputPath = Join-Path (Split-Path $projectRoot -Parent) (
        "model-atlas-mvp-review-{0}.zip" -f $dateStamp
    )
}

$outputFullPath = [System.IO.Path]::GetFullPath($OutputPath)
if ([System.IO.Path]::GetExtension($outputFullPath) -ne ".zip") {
    throw "OutputPath must end with .zip: $outputFullPath"
}

$checksumPath = "$outputFullPath.sha256"
foreach ($candidate in @($outputFullPath, $checksumPath)) {
    if ([System.IO.File]::Exists($candidate)) {
        if (-not $Force) {
            throw "Output already exists. Choose another path or pass -Force: $candidate"
        }
        [System.IO.File]::Delete($candidate)
    }
}

$outputDirectory = Split-Path $outputFullPath -Parent
if (-not [System.IO.Directory]::Exists($outputDirectory)) {
    [System.IO.Directory]::CreateDirectory($outputDirectory) | Out-Null
}

$rootFiles = @(
    ".env.example",
    ".gitattributes",
    ".gitignore",
    "CONTRIBUTING.md",
    "docker-compose.yml",
    "EVALUATOR_GUIDE_KO.md",
    "HANDOFF_SUMMARY.md",
    "Makefile",
    "MVP_SCOPE_KO.md",
    "MVP_REVIEW_GUIDE_KO.md",
    "README.md",
    "SECURITY.md",
    "SUBMISSION_README.md"
)

$sourceDirectories = @(
    ".github",
    "artifacts",
    "backend",
    "data",
    "deploy",
    "docs",
    "experiments",
    "frontend",
    "reference_workload",
    "tools"
)

$excludedSegments = @(
    ".git",
    ".cache",
    ".venv",
    ".next",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    ".turbo",
    "__pycache__",
    "build",
    "coverage",
    "dist",
    "htmlcov",
    "node_modules",
    "playwright-report",
    "test-results",
    "tmp"
)

function Get-ProjectRelativePath {
    param([System.IO.FileInfo]$File)

    $relative = $File.FullName.Substring($projectRoot.Length)
    while ($relative.StartsWith("\") -or $relative.StartsWith("/")) {
        $relative = $relative.Substring(1)
    }
    return $relative.Replace("\", "/")
}

function Test-IncludedFile {
    param([System.IO.FileInfo]$File)

    $relative = Get-ProjectRelativePath -File $File
    $segments = $relative -split "/"
    foreach ($segment in $segments) {
        if ($excludedSegments -contains $segment) {
            return $false
        }
        if ($segment -like "*.egg-info" -or $segment -like ".venv*") {
            return $false
        }
    }

    $leaf = $File.Name
    if ($leaf -match "(?i)^\.env(?:\..+)?$" -and -not $leaf.EndsWith(".example")) {
        return $false
    }
    if ($leaf -match "(?i)\.(db|log|p12|pfx|pyc|pyo|sqlite|sqlite3|tsbuildinfo|zip|onnx|gguf|safetensors|pt|pth|bin|ckpt|h5|hdf5)$") {
        return $false
    }
    if ($leaf -match "(?i)(?:private.*\.pem|\.key)$") {
        return $false
    }
    if ($leaf -match "(?i)^(?:id_dsa|id_ecdsa|id_ed25519|id_rsa)$") {
        return $false
    }
    if ($leaf -eq ".DS_Store" -or $leaf -eq ".coverage") {
        return $false
    }
    return $true
}

function Get-IncludedSourceFiles {
    param([string]$Directory)

    # Prune excluded directories before walking them, including inaccessible caches.
    foreach ($child in Get-ChildItem -LiteralPath $Directory -Force) {
        if ($child.PSIsContainer) {
            if ($excludedSegments -contains $child.Name -or $child.Name -like '.venv*' -or $child.Name -like '*.egg-info') {
                continue
            }
            if ($child.Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
                throw "Refusing to traverse a linked source directory: $($child.FullName)"
            }
            Get-IncludedSourceFiles -Directory $child.FullName
        }
        elseif (Test-IncludedFile -File $child) {
            if ($child.Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
                throw "Refusing a linked source file: $($child.FullName)"
            }
            $child
        }
    }
}

function Get-BytesHash {
    param([byte[]]$Bytes)

    $sha256 = [System.Security.Cryptography.SHA256]::Create()
    try {
        $digest = $sha256.ComputeHash($Bytes)
        return [System.BitConverter]::ToString($digest).Replace("-", "").ToLowerInvariant()
    }
    finally {
        $sha256.Dispose()
    }
}

function Get-TextHash {
    param([string]$Content)

    $encoding = New-Object System.Text.UTF8Encoding($false)
    return Get-BytesHash -Bytes $encoding.GetBytes($Content)
}

function Add-TextEntry {
    param(
        [System.IO.Compression.ZipArchive]$Archive,
        [string]$EntryName,
        [string]$Content
    )

    $entry = $Archive.CreateEntry(
        $EntryName,
        [System.IO.Compression.CompressionLevel]::Optimal
    )
    $encoding = New-Object System.Text.UTF8Encoding($false)
    $writer = New-Object System.IO.StreamWriter($entry.Open(), $encoding)
    try {
        $writer.Write($Content)
    }
    finally {
        $writer.Dispose()
    }
}

function Get-ZipEntryHash {
    param([System.IO.Compression.ZipArchiveEntry]$Entry)

    $sha256 = [System.Security.Cryptography.SHA256]::Create()
    $stream = $Entry.Open()
    try {
        $digest = $sha256.ComputeHash($stream)
        return [System.BitConverter]::ToString($digest).Replace("-", "").ToLowerInvariant()
    }
    finally {
        $stream.Dispose()
        $sha256.Dispose()
    }
}

$sourceFiles = @()
foreach ($relativePath in $rootFiles) {
    $fullPath = Join-Path $projectRoot $relativePath
    if (-not [System.IO.File]::Exists($fullPath)) {
        throw "Required package file is missing: $relativePath"
    }
    $sourceFiles += Get-Item -LiteralPath $fullPath -Force
}

foreach ($relativeDirectory in $sourceDirectories) {
    $fullDirectory = Join-Path $projectRoot $relativeDirectory
    if (-not [System.IO.Directory]::Exists($fullDirectory)) {
        throw "Required package directory is missing: $relativeDirectory"
    }
    $sourceFiles += Get-IncludedSourceFiles -Directory $fullDirectory
}

$sourceFiles = @($sourceFiles | Sort-Object FullName -Unique)
if ($sourceFiles.Count -eq 0) {
    throw "No source files were selected for the package."
}

$verificationStatus = [ordered]@{ status = "not_supplied" }
if (-not [string]::IsNullOrWhiteSpace($VerificationPath)) {
    $verificationFile = Get-Item -LiteralPath $VerificationPath
    if ($sourceFiles.FullName -notcontains $verificationFile.FullName) {
        throw "VerificationPath must be a selected source file inside the project."
    }
    $verification = Get-Content -LiteralPath $verificationFile.FullName -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($verification.schema_version -ne "mvp-closeout-verification-v1") {
        throw "Unsupported verification receipt schema."
    }
    $verificationStatus = [ordered]@{
        status = "recorded_checks_only"
        receipt_path = Get-ProjectRelativePath -File $verificationFile
        receipt_sha256 = (Get-FileHash -LiteralPath $verificationFile.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        checks = $verification.checks
        external_review = $verification.external_review
    }
}

$sourceBytes = [long]0
$manifestRows = @()
foreach ($file in $sourceFiles) {
    $relative = Get-ProjectRelativePath -File $file
    $sourceBytes += $file.Length
    $hash = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    $manifestRows += [PSCustomObject]@{ Path = $relative; Hash = $hash }
}

$exclusionsText = @'
# Package Exclusions

This is a reproducible source and evidence-review package, not a runtime image or model-weight bundle.

Excluded intentionally:

- `.git`, `.venv*`, `node_modules`, `.next`, caches, coverage, and build output
- PostgreSQL data, Docker images, containers, and named volumes
- Ollama and other external model weights, including ONNX, GGUF and Safetensors checkpoints
- actual `.env` files and runtime-projected secrets
- private-key material, including `artifacts/supply-chain/demo-publisher-private.pem`
- transient logs, databases, temporary files, and previous ZIP files

The public files under `artifacts/` are development reference evidence. They do not establish
production publisher identity or production eligibility. Generate a new development signer locally
when a supply-chain demo is required; never treat the omitted demo private key as distributable evidence.
'@
$exclusionsText = $exclusionsText.Replace("`r`n", "`n")

$packageInfo = [ordered]@{
    schema_version = "model-atlas-evaluation-package-v2"
    package = $packageRoot
    project = "Model Atlas"
    scope = "portfolio-mvp-closeout"
    current_entry_point = "MVP_REVIEW_GUIDE_KO.md"
    created_at_utc = [DateTime]::UtcNow.ToString("o")
    source_file_count = $sourceFiles.Count
    source_bytes = $sourceBytes
    payload_entry_count = $sourceFiles.Count + 2
    archive_entry_count = $sourceFiles.Count + 3
    verification_status = $verificationStatus
    boundaries = @(
        "No model weights are included.",
        "No production deployment authorization is implied.",
        "A fresh review database contains mock demo evidence, not the original runtime database.",
        "Historical reports describe their own dates; start with MVP_REVIEW_GUIDE_KO.md.",
        "Bundled paging, CA, trust-source, and public artifact evidence are development fixtures.",
        "The evaluator should rerun tests in the target environment."
    )
}
$packageInfoText = (($packageInfo | ConvertTo-Json -Depth 12) + "`n").Replace("`r`n", "`n")

$manifestRows += [PSCustomObject]@{
    Path = "EXCLUSIONS.md"
    Hash = Get-TextHash -Content $exclusionsText
}
$manifestRows += [PSCustomObject]@{
    Path = "PACKAGE_INFO.json"
    Hash = Get-TextHash -Content $packageInfoText
}
$manifestRows = @($manifestRows | Sort-Object Path)
$manifestText = (($manifestRows | ForEach-Object { "{0}  {1}" -f $_.Hash, $_.Path }) -join "`n") + "`n"

$archiveStream = $null
$archive = $null
try {
    $archiveStream = [System.IO.File]::Open(
        $outputFullPath,
        [System.IO.FileMode]::CreateNew,
        [System.IO.FileAccess]::ReadWrite,
        [System.IO.FileShare]::None
    )
    $archive = New-Object System.IO.Compression.ZipArchive(
        $archiveStream,
        [System.IO.Compression.ZipArchiveMode]::Create,
        $true
    )

    foreach ($file in $sourceFiles) {
        $relative = Get-ProjectRelativePath -File $file
        $entryName = "$packageRoot/$relative"
        [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
            $archive,
            $file.FullName,
            $entryName,
            [System.IO.Compression.CompressionLevel]::Optimal
        ) | Out-Null
    }

    Add-TextEntry -Archive $archive -EntryName "$packageRoot/EXCLUSIONS.md" -Content $exclusionsText
    Add-TextEntry -Archive $archive -EntryName "$packageRoot/PACKAGE_INFO.json" -Content $packageInfoText
    Add-TextEntry -Archive $archive -EntryName "$packageRoot/MANIFEST.sha256" -Content $manifestText
}
catch {
    if ($null -ne $archive) {
        $archive.Dispose()
        $archive = $null
    }
    if ($null -ne $archiveStream) {
        $archiveStream.Dispose()
        $archiveStream = $null
    }
    if ([System.IO.File]::Exists($outputFullPath)) {
        [System.IO.File]::Delete($outputFullPath)
    }
    throw
}
finally {
    if ($null -ne $archive) {
        $archive.Dispose()
    }
    if ($null -ne $archiveStream) {
        $archiveStream.Dispose()
    }
}

$requiredEntries = @(
    "$packageRoot/MVP_REVIEW_GUIDE_KO.md",
    "$packageRoot/MVP_SCOPE_KO.md",
    "$packageRoot/deploy/mvp-review.compose.yml",
    "$packageRoot/EVALUATOR_GUIDE_KO.md",
    "$packageRoot/README.md",
    "$packageRoot/SUBMISSION_README.md",
    "$packageRoot/backend/app/main.py",
    "$packageRoot/frontend/package.json",
    "$packageRoot/frontend/app/release-decisions/[id]/page.tsx",
    "$packageRoot/docs/architecture.md",
    "$packageRoot/docs/staging_paging_qualification.md",
    "$packageRoot/docs/reports/2026-09-13_mvp_closeout_ko.md",
    "$packageRoot/tools/build_evaluation_package.ps1",
    "$packageRoot/EXCLUSIONS.md",
    "$packageRoot/PACKAGE_INFO.json",
    "$packageRoot/MANIFEST.sha256"
)

$readArchive = [System.IO.Compression.ZipFile]::OpenRead($outputFullPath)
try {
    $entryNames = @($readArchive.Entries | ForEach-Object { $_.FullName })
    if (@($entryNames | Sort-Object -Unique).Count -ne $entryNames.Count) {
        throw "Archive validation failed; duplicate paths."
    }
    foreach ($requiredEntry in $requiredEntries) {
        if ($entryNames -notcontains $requiredEntry) {
            throw "Archive validation failed; required entry is missing: $requiredEntry"
        }
    }

    $prohibitedEntries = @()
    foreach ($entryName in $entryNames) {
        if ($entryName -match '(^|/)\.\.(/|$)|\\|:' -or -not $entryName.StartsWith("$packageRoot/")) {
            throw "Archive validation failed; unsafe path: $entryName"
        }
        if ($entryName -match "(?i)(^|/)(?:\.git|\.cache|\.venv[^/]*|\.next|\.pytest_cache|\.ruff_cache|__pycache__|node_modules|tmp)(/|$)") {
            $prohibitedEntries += $entryName
            continue
        }
        if ($entryName -match "(?i)(?:private.*\.pem|\.(?:key|p12|pfx|onnx|gguf|safetensors|pt|pth|bin|ckpt|h5|hdf5))$") {
            $prohibitedEntries += $entryName
            continue
        }
        if ($entryName -match "(?i)(^|/)\.env(?:\.[^/]+)?$" -and $entryName -notmatch "(?i)\.example$") {
            $prohibitedEntries += $entryName
        }
    }
    if ($prohibitedEntries.Count -gt 0) {
        throw "Archive validation failed; prohibited entries found: $($prohibitedEntries -join ', ')"
    }

    $manifestEntry = $readArchive.GetEntry("$packageRoot/MANIFEST.sha256")
    $reader = New-Object System.IO.StreamReader($manifestEntry.Open(), [System.Text.Encoding]::UTF8)
    try {
        $storedManifest = $reader.ReadToEnd()
    }
    finally {
        $reader.Dispose()
    }

    $verifiedManifestEntries = 0
    foreach ($line in ($storedManifest -split "`n")) {
        $line = $line.TrimEnd("`r")
        if ([string]::IsNullOrWhiteSpace($line)) {
            continue
        }
        if ($line -notmatch "^([0-9a-f]{64})  (.+)$") {
            throw "Archive validation failed; malformed manifest row: $line"
        }
        $expectedHash = $Matches[1]
        $relativeEntry = $Matches[2]
        $payloadEntry = $readArchive.GetEntry("$packageRoot/$relativeEntry")
        if ($null -eq $payloadEntry) {
            throw "Archive validation failed; manifest entry is missing: $relativeEntry"
        }
        $actualHash = Get-ZipEntryHash -Entry $payloadEntry
        if ($actualHash -ne $expectedHash) {
            throw "Archive validation failed; hash mismatch: $relativeEntry"
        }
        $verifiedManifestEntries += 1
    }

    if ($verifiedManifestEntries -ne ($readArchive.Entries.Count - 1)) {
        throw (
            "Archive validation failed; manifest covers {0} of {1} payload entries." -f
            $verifiedManifestEntries,
            ($readArchive.Entries.Count - 1)
        )
    }
    $archiveEntryCount = $readArchive.Entries.Count
}
finally {
    $readArchive.Dispose()
}

$zipFile = Get-Item -LiteralPath $outputFullPath
$zipHash = (Get-FileHash -LiteralPath $outputFullPath -Algorithm SHA256).Hash.ToLowerInvariant()
$checksumLine = "$zipHash  $($zipFile.Name)`n"
[System.IO.File]::WriteAllText(
    $checksumPath,
    $checksumLine,
    (New-Object System.Text.UTF8Encoding($false))
)

[PSCustomObject]@{
    zip_path = $outputFullPath
    checksum_path = $checksumPath
    sha256 = $zipHash
    zip_bytes = $zipFile.Length
    archive_entry_count = $archiveEntryCount
    manifest_verified_entries = $verifiedManifestEntries
    prohibited_entry_count = 0
    status = "verified"
} | ConvertTo-Json -Depth 4
