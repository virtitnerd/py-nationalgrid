<#
.SYNOPSIS
    Tests parallel date-window chunking against the National Grid AMI 15-min endpoint.
    Fires all chunks simultaneously and reports status, record count, and latency per chunk.

.DESCRIPTION
    Run this AFTER obtaining a bearer token from the Python client (see step 0 below).
    Requires PowerShell 7+ for -Parallel support.

.EXAMPLE
    # Step 0: get a token from Python
    #   python - <<'EOF'
    #   import asyncio, aionatgrid
    #   async def main():
    #       async with aionatgrid.NationalGridClient("user@example.com", "secret") as c:
    #           await c._ensure_authenticated()
    #           print(c._access_token)
    #   asyncio.run(main())
    #   EOF

    .\Test-ParallelChunks.ps1 `
        -BearerToken "eyJ..." `
        -MeterNumber "12345678" `
        -PremiseNumber "98765" `
        -ServicePointNumber "SP001" `
        -MeterPointNumber "MP001" `
        -DateFrom "2024-01-01" `
        -DateTo   "2025-01-01" `
        -ChunkDays 90 `
        -ThrottleLimit 10
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory)][string] $BearerToken,

    # Meter identifiers — copy from get_billing_account() meter.nodes output
    [Parameter(Mandatory)][string] $MeterNumber,
    [Parameter(Mandatory)][string] $PremiseNumber,
    [Parameter(Mandatory)][string] $ServicePointNumber,
    [Parameter(Mandatory)][string] $MeterPointNumber,

    # Date range to cover (inclusive, YYYY-MM-DD)
    [Parameter(Mandatory)][string] $DateFrom,
    [Parameter(Mandatory)][string] $DateTo,

    # Size of each chunk in days
    [int] $ChunkDays = 90,

    # Max parallel requests — start low (2-3) and increase to probe the limit
    [int] $ThrottleLimit = 5,

    # Which root field / operation to hit
    [string] $RootField      = "amiEnergyUsages15Min",
    [string] $OperationName  = "NrtDailyUsage15Min"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ── Validate PowerShell version ──────────────────────────────────────────────
if ($PSVersionTable.PSVersion.Major -lt 7) {
    Write-Error "PowerShell 7+ is required for -Parallel support. Current: $($PSVersionTable.PSVersion)"
}

# ── Build chunk list ──────────────────────────────────────────────────────────
$start  = [datetime]::ParseExact($DateFrom, "yyyy-MM-dd", $null)
$end    = [datetime]::ParseExact($DateTo,   "yyyy-MM-dd", $null)

$chunks = [System.Collections.Generic.List[hashtable]]::new()
$cursor = $start
while ($cursor -lt $end) {
    $chunkEnd = $cursor.AddDays($ChunkDays - 1)
    if ($chunkEnd -gt $end) { $chunkEnd = $end }
    $chunks.Add(@{
        From  = $cursor.ToString("yyyy-MM-dd")
        To    = $chunkEnd.ToString("yyyy-MM-dd")
        Index = $chunks.Count + 1
    })
    $cursor = $chunkEnd.AddDays(1)
}

$totalChunks = $chunks.Count
Write-Host ""
Write-Host "Range  : $DateFrom -> $DateTo"
Write-Host "Chunks : $totalChunks x $ChunkDays days"
Write-Host "Parallel limit: $ThrottleLimit"
Write-Host ""
Write-Host ("─" * 80)
Write-Host ("{0,-4} {1,-12} {2,-12} {3,6} {4,8} {5,8} {6}" -f "#", "From", "To", "Status", "Records", "ms", "Note")
Write-Host ("─" * 80)

# ── Shared constants passed into each parallel scriptblock ───────────────────
$endpoint       = "https://myaccount.nationalgrid.com/api/energyusage-cu-uwp-gql"
$subscriptionKey = "e674f89d7ed9417194de894b701333dd"

$gqlQuery = @"
query $OperationName(
  \$meterNumber: String!
  \$premiseNumber: String!
  \$servicePointNumber: String!
  \$meterPointNumber: String!
  \$dateFrom: Date!
  \$dateTo: Date!
) {
  $RootField(
    meterNumber: \$meterNumber
    premiseNumber: \$premiseNumber
    servicePointNumber: \$servicePointNumber
    meterPointNumber: \$meterPointNumber
    dateFrom: \$dateFrom
    dateTo: \$dateTo
  ) {
    nodes {
      date
      fuelType
      quantity
    }
  }
}
"@

# ── Fire all chunks in parallel ───────────────────────────────────────────────
$results = $chunks | ForEach-Object -ThrottleLimit $ThrottleLimit -Parallel {
    $chunk           = $_
    $ep              = $using:endpoint
    $subKey          = $using:subscriptionKey
    $token           = $using:BearerToken
    $meter           = $using:MeterNumber
    $premise         = $using:PremiseNumber
    $servicePoint    = $using:ServicePointNumber
    $meterPoint      = $using:MeterPointNumber
    $operationName   = $using:OperationName
    $rootField       = $using:RootField
    $query           = $using:gqlQuery

    $body = @{
        operationName = $operationName
        query         = $query
        variables     = @{
            meterNumber        = $meter
            premiseNumber      = $premise
            servicePointNumber = $servicePoint
            meterPointNumber   = $meterPoint
            dateFrom           = $chunk.From
            dateTo             = $chunk.To
        }
    } | ConvertTo-Json -Depth 5 -Compress

    $headers = @{
        "Authorization"           = "Bearer $token"
        "ocp-apim-subscription-key" = $subKey
        "Content-Type"            = "application/json"
        "Accept"                  = "application/json"
    }

    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    try {
        $resp = Invoke-WebRequest -Uri $ep -Method POST -Headers $headers -Body $body -SkipHttpErrorCheck
        $sw.Stop()

        $statusCode = [int]$resp.StatusCode
        $note       = ""
        $records    = -1

        try {
            $json = $resp.Content | ConvertFrom-Json -Depth 10
            if ($json.errors) {
                $note = "GraphQL error: $($json.errors[0].message)"
            } elseif ($json.data.$rootField.nodes) {
                $records = $json.data.$rootField.nodes.Count
            } elseif ($null -ne $json.data.$rootField) {
                $records = 0
            }
        } catch {
            $note = "JSON parse error"
        }

        # Flag rate-limit and server errors
        if ($statusCode -eq 429) { $note = "RATE LIMITED" }
        elseif ($statusCode -ge 500) { $note = "SERVER ERROR $statusCode" }

        [PSCustomObject]@{
            Index   = $chunk.Index
            From    = $chunk.From
            To      = $chunk.To
            Status  = $statusCode
            Records = $records
            Ms      = $sw.ElapsedMilliseconds
            Note    = $note
        }
    } catch {
        $sw.Stop()
        [PSCustomObject]@{
            Index   = $chunk.Index
            From    = $chunk.From
            To      = $chunk.To
            Status  = 0
            Records = -1
            Ms      = $sw.ElapsedMilliseconds
            Note    = "Exception: $_"
        }
    }
} | Sort-Object Index

# ── Print results ─────────────────────────────────────────────────────────────
foreach ($r in $results) {
    $statusColor = if ($r.Status -eq 200) { "Green" }
                   elseif ($r.Status -eq 429) { "Red" }
                   elseif ($r.Status -ge 500) { "Yellow" }
                   else { "Cyan" }

    $noteStr = if ($r.Note) { " <- $($r.Note)" } else { "" }
    Write-Host ("{0,-4} {1,-12} {2,-12} {3,6} {4,8} {5,8} {6}" -f `
        $r.Index, $r.From, $r.To, $r.Status, $r.Records, $r.Ms, $noteStr) `
        -ForegroundColor $statusColor
}

Write-Host ("─" * 80)

# ── Summary ───────────────────────────────────────────────────────────────────
$ok          = ($results | Where-Object { $_.Status -eq 200 }).Count
$rateLimited = ($results | Where-Object { $_.Status -eq 429 }).Count
$errors      = ($results | Where-Object { $_.Status -ne 200 -and $_.Status -ne 429 }).Count
$totalRecords = ($results | Where-Object { $_.Records -ge 0 } | Measure-Object -Property Records -Sum).Sum
$gqlErrors   = ($results | Where-Object { $_.Note -match "GraphQL error" }).Count

Write-Host ""
Write-Host "Summary"
Write-Host "  Total chunks  : $totalChunks"
Write-Host "  200 OK        : $ok"
Write-Host "  429 Rate limit: $rateLimited"  -ForegroundColor $(if ($rateLimited -gt 0) { "Red" } else { "White" })
Write-Host "  Other errors  : $errors"       -ForegroundColor $(if ($errors -gt 0) { "Yellow" } else { "White" })
Write-Host "  GraphQL errors: $gqlErrors"    -ForegroundColor $(if ($gqlErrors -gt 0) { "Yellow" } else { "White" })
Write-Host "  Total records : $totalRecords"
Write-Host ""

if ($rateLimited -gt 0) {
    Write-Warning "Rate limiting detected. Try a lower -ThrottleLimit or add -ChunkDays to reduce chunks."
} elseif ($ok -eq $totalChunks) {
    Write-Host "All $totalChunks chunks succeeded in parallel with -ThrottleLimit $ThrottleLimit." -ForegroundColor Green
}
