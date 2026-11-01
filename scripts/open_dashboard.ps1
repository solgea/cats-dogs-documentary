#requires -Version 5.1
<#
.SYNOPSIS
    Streamlit dashboard'u ayakta oldugunda varsayilan tarayiciyi acar.

.DESCRIPTION
    http://localhost:8502/_stcore/health adresini yoklar; sunucu "ok"
    dondurdugunde tarayiciyi bir kez acar. Sunucu hic hazir olmazsa
    zaman asimina dusup sessizce cikar (exit 1).

.PARAMETER Url
    Dashboard adresi. Varsayilan: http://localhost:8502

.PARAMETER TimeoutSeconds
    En fazla kac saniye beklenecegi. Varsayilan: 120

.PARAMETER ProbeTimeoutMs
    Tek bir yoklamanin en fazla suresi (ms). Varsayilan: 750

.PARAMETER IntervalMs
    Iki deneme arasi bekleme (ms). Varsayilan: 200

.PARAMETER NoOpen
    Tarayiciyi acmaz, yalnizca sunucunun hazir olmasini bekler (test icin).

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File scripts\open_dashboard.ps1
#>
param(
    [string]$Url = "http://localhost:8502",
    [int]$TimeoutSeconds = 120,
    [int]$ProbeTimeoutMs = 750,
    [int]$IntervalMs = 200,
    [switch]$NoOpen
)

$base = $Url.TrimEnd('/')
$health = "$base/_stcore/health"

if ($ProbeTimeoutMs -lt 100) { $ProbeTimeoutMs = 100 }
if ($IntervalMs -lt 0) { $IntervalMs = 0 }

$deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)

while ([DateTime]::UtcNow -lt $deadline) {
    try {
        $request = [System.Net.WebRequest]::Create($health)
        $request.Method = 'GET'
        $request.Timeout = $ProbeTimeoutMs
        $request.Proxy = $null

        $response = $request.GetResponse()
        $status = [int]$response.StatusCode
        $reader = New-Object System.IO.StreamReader($response.GetResponseStream())
        $body = $reader.ReadToEnd().Trim()
        $reader.Close()
        $response.Close()

        # Streamlit hazir oldugunda saglik ucu "ok" dondurur.
        if ($status -eq 200 -and $body -match '^ok$') {
            if ($NoOpen) {
                Write-Output "HAZIR: $base"
            }
            else {
                Start-Process $base
            }
            exit 0
        }
    }
    catch {
        # Sunucu henuz dinlemiyor / yanit vermiyor: beklemeye devam.
    }

    if ($IntervalMs -gt 0) { Start-Sleep -Milliseconds $IntervalMs }
}

Write-Output "ZAMAN ASIMI: $base hazir olmadi."
exit 1
