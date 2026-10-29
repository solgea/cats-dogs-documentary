param(
    [string]$LogPath = "C:\Users\trycahce\AppData\Local\Temp\opencode\recover-dog-guilty-look.log",
    [string]$RequestPath = "C:\Users\trycahce\Desktop\Proje\cats-dogs-documentary\content\packages\dog-guilty-look\viewmade-request.json",
    [string]$RenderPath = "C:\Users\trycahce\Desktop\Proje\cats-dogs-documentary\renders\dog-guilty-look.mp4",
    [string]$JobStatePath = "C:\Users\trycahce\Desktop\Proje\cats-dogs-documentary\state\viewmade-jobs\dog-guilty-look.json",
    [string]$JobId = "f59f8a91-7b2b-4dbb-a03d-62effc911581",
    [string]$CreatedAt = "2026-10-28T22:16:29Z",
    [int]$RefreshSeconds = 2
)

$Host.UI.RawUI.WindowTitle = "ViewMade pilot - dog-guilty-look"

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
    if ([string]::IsNullOrWhiteSpace($StatusLine.Eta) -or $StatusLine.Eta -eq "None") { return "bilinmiyor" }
    $match = [regex]::Match($StatusLine.Eta, '(\d+)\s*min')
    if (-not $match.Success) { return $StatusLine.Eta }
    $timestamp = Parse-Utc $StatusLine.Timestamp
    if ($null -eq $timestamp) { return $StatusLine.Eta }
    $target = $timestamp.AddMinutes([int]$match.Groups[1].Value)
    $remaining = ($target - [datetime]::UtcNow).TotalSeconds
    if ($remaining -le 0) { return "başlamak üzere" }
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

$created = Parse-Utc $CreatedAt
if ($null -eq $created) { $created = [datetime]::UtcNow }

while ($true) {
    $lastLine = Get-Content $LogPath -Tail 1 -ErrorAction SilentlyContinue
    $status = Parse-StatusLine $lastLine

    $local = $null
    if (Test-Path $RequestPath) {
        try { $local = Get-Content $RequestPath -Raw | ConvertFrom-Json } catch { $local = $null }
    }

    $mp4 = $null
    if (Test-Path $RenderPath) {
        try { $mp4 = Get-Item $RenderPath } catch { $mp4 = $null }
    }

    $jobState = $null
    if (Test-Path $JobStatePath) {
        try { $jobState = Get-Content $JobStatePath -Raw | ConvertFrom-Json } catch { $jobState = $null }
    }

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
            if ($age -gt 150) { $updateAge = " (gecikmiş)" }
        }
    }

    $elapsedSeconds = ([datetime]::UtcNow - $created).TotalSeconds
    $localStatus = "-"
    $localJob = "-"
    $localError = "-"
    $localSha = "-"
    if ($null -ne $local) {
        $localStatus = $local.status
        if ($local.job_id) { $localJob = $local.job_id }
        if ($local.error) { $localError = $local.error }
        if ($local.render_sha256) { $localSha = $local.render_sha256 }
    }
    $validation = "-"
    if ($null -ne $jobState -and $null -ne $jobState.media) {
        $media = $jobState.media
        $validation = "{0}x{1} · {2:N1} sn · ses: {3}" -f $media.width, $media.height, $media.duration_s, $(if ($media.has_audio) { "var" } else { "yok" })
    }

    if ($localStatus -eq "COMPLETE") {
        $providerStatus = "COMPLETE"
        $stage = "tamamlandı"
        $pct = "100%"
        $eta = "-"
        $remaining = "tamamlandı"
    } elseif ($localStatus -eq "FAILED") {
        $providerStatus = "FAILED"
        $remaining = "durduruldu"
    }

    $colour = Get-StatusColour $providerStatus
    $Host.UI.RawUI.WindowTitle = "ViewMade $providerStatus - dog-guilty-look"

    Clear-Host
    Write-Host "==============================================================" -ForegroundColor DarkCyan
    Write-Host " ViewMade Pilot Durumu - dog-guilty-look" -ForegroundColor Cyan
    Write-Host "==============================================================" -ForegroundColor DarkCyan
    Write-Host (" Sağlayıcı durumu : ") -NoNewline
    Write-Host $providerStatus -ForegroundColor $colour
    Write-Host (" Aşama            : {0}" -f $stage)
    Write-Host (" İlerleme         : {0}" -f $pct)
    Write-Host (" Sağlayıcı ETA    : {0}" -f $eta)
    Write-Host (" Tahmini kalan    : ") -NoNewline
    Write-Host $remaining -ForegroundColor $colour
    Write-Host (" Geçen süre       : {0}" -f (Format-Duration $elapsedSeconds))
    Write-Host (" Son güncelleme   : {0}{1}" -f $lastUpdate, $updateAge) -ForegroundColor DarkGray
    Write-Host "--------------------------------------------------------------" -ForegroundColor DarkCyan
    Write-Host (" Yerel durum      : {0}" -f $localStatus)
    Write-Host (" İş kimliği       : {0}" -f $localJob)
    Write-Host (" Kredi            : 20 (iş oluşturulurken çekildi)")
    Write-Host (" MP4              : ") -NoNewline
    if ($null -ne $mp4) {
        Write-Host ("VAR - {0:N1} MB - {1}" -f ($mp4.Length / 1MB), $mp4.LastWriteTime.ToString("HH:mm:ss")) -ForegroundColor Green
    } else {
        Write-Host "henüz yok" -ForegroundColor DarkGray
    }
    Write-Host (" Doğrulama        : {0}" -f $validation)
    if ($localSha -ne "-") {
        Write-Host (" SHA-256          : {0}..." -f $localSha.Substring(0, [math]::Min(16, $localSha.Length))) -ForegroundColor DarkGray
    }
    Write-Host (" Yayın            : editör onayı bekliyor") -ForegroundColor DarkYellow
    if ($localError -ne "-") {
        Write-Host (" Hata             : {0}" -f $localError) -ForegroundColor Red
    }
    Write-Host "--------------------------------------------------------------" -ForegroundColor DarkCyan
    Write-Host (" Her {0} saniyede yenilenir. Kapatmak için Ctrl+C." -f $RefreshSeconds) -ForegroundColor DarkGray
    Write-Host "==============================================================" -ForegroundColor DarkCyan

    Start-Sleep -Seconds $RefreshSeconds
}
