param(
    [string]$PackageId = "cat-sweetness",
    [string]$Root = "",
    [string]$LogPath = "",
    [int]$RefreshSeconds = 2,
    [switch]$Once
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($Root)) {
    $Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}
if ([string]::IsNullOrWhiteSpace($LogPath)) {
    $candidate = Join-Path $Root "state\recovery-$PackageId.log"
    if (Test-Path $candidate) {
        $LogPath = $candidate
    } else {
        $LogPath = Join-Path $Root "state\render-$PackageId.log"
    }
}

$requestPath = Join-Path $Root "content\packages\$PackageId\viewmade-request.json"
$renderPath = Join-Path $Root "renders\$PackageId.mp4"
$jobStatePath = Join-Path $Root "state\viewmade-jobs\$PackageId.json"

function Parse-StatusLine {
    param([string]$Line)
    if ([string]::IsNullOrWhiteSpace($Line)) { return $null }
    $pattern = '^(?<ts>\S+)\s+status=(?<status>\S*)\s+stage=(?<stage>\S*)\s+pct=(?<pct>\S*)\s+eta=(?<eta>.*)$'
    $match = [regex]::Match($Line, $pattern)
    if (-not $match.Success) { return $null }
    return [pscustomobject]@{
        Timestamp = $match.Groups['ts'].Value
        Status    = $match.Groups['status'].Value
        Stage     = $match.Groups['stage'].Value
        Pct       = $match.Groups['pct'].Value
        Eta       = $match.Groups['eta'].Value.Trim()
    }
}

function Parse-Utc {
    param([string]$Value)
    if ([string]::IsNullOrWhiteSpace($Value)) { return $null }
    try {
        return [datetime]::Parse(
            $Value,
            [cultureinfo]::InvariantCulture,
            [System.Globalization.DateTimeStyles]::AllowWhiteSpaces -bor
            [System.Globalization.DateTimeStyles]::AssumeUniversal -bor
            [System.Globalization.DateTimeStyles]::AdjustToUniversal
        )
    } catch {
        return $null
    }
}

function Format-Duration {
    param([double]$Seconds)
    $total = [int][math]::Max(0, [math]::Floor($Seconds))
    $hours = [int]($total / 3600)
    $minutes = [int](($total % 3600) / 60)
    $secondsPart = $total % 60
    return ('{0:00}:{1:00}:{2:00}' -f $hours, $minutes, $secondsPart)
}

function Get-RemainingText {
    param($StatusLine)
    if ($null -eq $StatusLine) { return "bilinmiyor" }
    if ([string]::IsNullOrWhiteSpace($StatusLine.Eta) -or $StatusLine.Eta -eq "None") {
        return "bilinmiyor"
    }
    $numbers = [regex]::Matches($StatusLine.Eta, '\d+')
    if ($numbers.Count -eq 0) { return $StatusLine.Eta }
    $minutes = 0
    foreach ($number in $numbers) {
        $value = [int]$number.Value
        if ($value -gt $minutes) { $minutes = $value }
    }
    $timestamp = Parse-Utc $StatusLine.Timestamp
    if ($null -eq $timestamp) { return $StatusLine.Eta }
    $target = $timestamp.AddMinutes($minutes)
    $remaining = ($target - [datetime]::UtcNow).TotalSeconds
    if ($remaining -le 0) { return "bitmek uzere" }
    return (Format-Duration $remaining)
}

function Get-StatusColour {
    param([string]$Status)
    switch ($Status.ToLowerInvariant()) {
        "ready"     { return "Green" }
        "complete"  { return "Green" }
        "rendering" { return "Yellow" }
        "queued"    { return "DarkYellow" }
        "failed"    { return "Red" }
        default     { return "Gray" }
    }
}

while ($true) {
    $status = $null
    if (Test-Path $LogPath) {
        $lastLine = Get-Content $LogPath -Tail 25 -ErrorAction SilentlyContinue |
            Where-Object { $_ -match '^(\S+)\s+status=' } |
            Select-Object -Last 1
        $status = Parse-StatusLine $lastLine
    }

    $local = $null
    if (Test-Path $requestPath) {
        try { $local = Get-Content $requestPath -Raw | ConvertFrom-Json } catch { $local = $null }
    }

    $jobState = $null
    if (Test-Path $jobStatePath) {
        try { $jobState = Get-Content $jobStatePath -Raw | ConvertFrom-Json } catch { $jobState = $null }
    }

    $mp4 = $null
    if (Test-Path $renderPath) {
        try { $mp4 = Get-Item $renderPath } catch { $mp4 = $null }
    }

    $localStatus = "-"
    $localJob = "-"
    $localError = "-"
    $previousError = "-"
    $localSha = "-"
    $createdAt = $null
    if ($null -ne $local) {
        $localStatus = $local.status
        if ($local.job_id) { $localJob = $local.job_id }
        if ($local.error) {
            if ($local.status -eq "FAILED") {
                $localError = $local.error
            } else {
                $previousError = $local.error
            }
        }
        if ($local.render_sha256) { $localSha = $local.render_sha256 }
        if ($local.submission -and $local.submission.submitted_at) {
            $createdAt = Parse-Utc $local.submission.submitted_at
        }
        if ($null -eq $createdAt -and $local.updated_at) {
            $createdAt = Parse-Utc $local.updated_at
        }
    }
    if ($null -eq $createdAt -and $null -ne $jobState) {
        if ($jobState.submitted_at) { $createdAt = Parse-Utc $jobState.submitted_at }
    }
    if ($null -eq $createdAt) { $createdAt = [datetime]::UtcNow }

    $providerStatus = "bilinmiyor"
    $stage = "-"
    $pct = "-"
    $eta = "-"
    $remaining = "bilinmiyor"
    $lastUpdate = "-"
    $updateAge = ""
    if ($null -ne $status) {
        $providerStatus = $status.Status.ToUpperInvariant()
        $stage = if ($status.Stage -and $status.Stage -ne "None") { $status.Stage } else { "-" }
        $pct = if ($status.Pct -and $status.Pct -ne "None") { "$($status.Pct)%" } else { "-" }
        $eta = if ($status.Eta -and $status.Eta -ne "None") { $status.Eta } else { "-" }
        $remaining = Get-RemainingText $status
        $lastUpdate = $status.Timestamp
        $timestamp = Parse-Utc $status.Timestamp
        if ($null -ne $timestamp) {
            $age = ([datetime]::UtcNow - $timestamp).TotalSeconds
            if ($age -gt 150) { $updateAge = " (gecikmis)" }
        }
    } elseif ($null -ne $jobState) {
        if ($jobState.provider_state) {
            $providerStatus = ([string]$jobState.provider_state).ToUpperInvariant()
        }
        if ($jobState.last_polled_at) { $lastUpdate = $jobState.last_polled_at }
    }

    $credits = "20 kredi (sabit fiyat)"
    if ($null -ne $jobState -and $jobState.provider_package) {
        $charged = $jobState.provider_package.credits_charged
        $refunded = $jobState.provider_package.credits_refunded
        if ($null -ne $charged) {
            $credits = "cekilen: $charged; iade: $refunded"
        }
    } elseif ($null -ne $local -and $local.provider_package) {
        $charged = $local.provider_package.credits_charged
        $refunded = $local.provider_package.credits_refunded
        if ($null -ne $charged) {
            $credits = "cekilen: $charged; iade: $refunded"
        }
    }

    $validation = "-"
    if ($null -ne $jobState -and $null -ne $jobState.media) {
        $media = $jobState.media
        $audio = if ($media.has_audio) { "var" } else { "yok" }
        $validation = "{0}x{1} / {2:N1} sn / ses: {3}" -f $media.width, $media.height, $media.duration_s, $audio
    }

    if ($localStatus -eq "COMPLETE") {
        $providerStatus = "COMPLETE"
        $stage = "tamamlandi"
        $pct = "100%"
        $eta = "-"
        $remaining = "tamamlandi"
    } elseif ($localStatus -eq "FAILED") {
        $providerStatus = "FAILED"
        $remaining = "durduruldu"
    }

    $elapsedSeconds = ([datetime]::UtcNow - $createdAt).TotalSeconds
    $colour = Get-StatusColour $providerStatus
    try {
        $Host.UI.RawUI.WindowTitle = "ViewMade $providerStatus - $PackageId"
    } catch {
        # Non-interactive hosts may not expose a window title.
    }

    if (-not $Once) { Clear-Host }
    Write-Host "==============================================================" -ForegroundColor DarkCyan
    Write-Host " ViewMade Pilot Durumu - $PackageId" -ForegroundColor Cyan
    Write-Host "==============================================================" -ForegroundColor DarkCyan
    Write-Host (" Saglayici durumu : ") -NoNewline
    Write-Host $providerStatus -ForegroundColor $colour
    Write-Host (" Asama            : {0}" -f $stage)
    Write-Host (" Ilerleme         : {0}" -f $pct)
    Write-Host (" Saglayici ETA    : {0}" -f $eta)
    Write-Host (" Tahmini kalan    : ") -NoNewline
    Write-Host $remaining -ForegroundColor $colour
    Write-Host (" Gecen sure       : {0}" -f (Format-Duration $elapsedSeconds))
    Write-Host (" Son guncelleme   : {0}{1}" -f $lastUpdate, $updateAge) -ForegroundColor DarkGray
    Write-Host "--------------------------------------------------------------" -ForegroundColor DarkCyan
    Write-Host (" Yerel durum      : {0}" -f $localStatus)
    Write-Host (" Is kimligi       : {0}" -f $localJob)
    Write-Host (" Kredi            : {0}" -f $credits)
    Write-Host (" MP4              : ") -NoNewline
    if ($null -ne $mp4) {
        $sizeMb = $mp4.Length / 1MB
        Write-Host ("VAR - {0:N1} MB - {1}" -f $sizeMb, $mp4.LastWriteTime.ToString("HH:mm:ss")) -ForegroundColor Green
    } else {
        Write-Host "henuz yok" -ForegroundColor DarkGray
    }
    Write-Host (" Dogrulama        : {0}" -f $validation)
    if ($localSha -ne "-") {
        Write-Host (" SHA-256          : {0}..." -f $localSha.Substring(0, [math]::Min(16, $localSha.Length))) -ForegroundColor DarkGray
    }
    Write-Host (" Yayin            : editor onayi bekliyor") -ForegroundColor DarkYellow
    if ($localError -ne "-") {
        Write-Host (" Hata             : {0}" -f $localError) -ForegroundColor Red
    } elseif ($previousError -ne "-") {
        Write-Host (" Onceki hata      : {0}" -f $previousError) -ForegroundColor DarkGray
        Write-Host "                    (kurtarma devam ediyor; durum dosyasi esas alinir)" -ForegroundColor DarkGray
    }
    Write-Host "--------------------------------------------------------------" -ForegroundColor DarkCyan
    Write-Host (" Log              : {0}" -f $LogPath) -ForegroundColor DarkGray
    if (-not $Once) {
        Write-Host (" Her {0} saniyede yenilenir. Kapatmak icin Ctrl+C." -f $RefreshSeconds) -ForegroundColor DarkGray
    }
    Write-Host "==============================================================" -ForegroundColor DarkCyan

    if ($Once) { break }
    Start-Sleep -Seconds $RefreshSeconds
}
