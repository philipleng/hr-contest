<#
.SYNOPSIS
    Black-box HTTP smoke test suite for HR Applicant Pool System (60+ assertions).

.DESCRIPTION
    Exercises Nginx routing, security headers, hardened 404 routes, media upload &
    signed URLs, public H5 applicant submission & deduplication, staff RBAC &
    anti-lockout, applicant workflow & 3-round interviews, bulk Excel import,
    Excel export (masked & PII), soft-delete cleanup, and optional rate-limit checks.
    Compatible with both Windows PowerShell 5.1 and PowerShell 7+.
#>
param(
    [string]$BaseUrl = "http://localhost",
    [string]$AdminUsername = "admin",
    [string]$AdminPassword = $env:HR_SMOKE_ADMIN_PASSWORD,
    [switch]$SkipRateLimit,
    [int]$TimeoutSec = 30
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($AdminPassword)) {
    Write-Host "[ERROR] Admin password is required. Pass -AdminPassword or set `$env:HR_SMOKE_ADMIN_PASSWORD." -ForegroundColor Red
    exit 1
}

Add-Type -AssemblyName System.Net.Http
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem

$BaseUrl = $BaseUrl.TrimEnd("/")

$handler = New-Object System.Net.Http.HttpClientHandler
$handler.AllowAutoRedirect = $true
$script:HttpClient = New-Object System.Net.Http.HttpClient($handler)
$script:HttpClient.Timeout = [TimeSpan]::FromSeconds($TimeoutSec)

$script:PassCount = 0
$script:FailCount = 0
$script:AssertionIndex = 0

function Assert-Check {
    param(
        [string]$Name,
        [bool]$Condition,
        [string]$Detail = ""
    )
    $script:AssertionIndex++
    $num = $script:AssertionIndex
    if ($Condition) {
        $script:PassCount++
        Write-Host ("[PASS] #{0:D2} {1}" -f $num, $Name) -ForegroundColor Green
    }
    else {
        $script:FailCount++
        if ($Detail) {
            Write-Host ("[FAIL] #{0:D2} {1} -- {2}" -f $num, $Name, $Detail) -ForegroundColor Red
        }
        else {
            Write-Host ("[FAIL] #{0:D2} {1}" -f $num, $Name) -ForegroundColor Red
        }
    }
}

function Get-HeaderValue {
    param(
        [System.Net.Http.HttpResponseMessage]$Response,
        [string]$HeaderName
    )
    $values = $null
    if ($Response.Headers.TryGetValues($HeaderName, [ref]$values)) {
        return ($values -join ", ")
    }
    if ($Response.Content -and $Response.Content.Headers.TryGetValues($HeaderName, [ref]$values)) {
        return ($values -join ", ")
    }
    return $null
}

function Invoke-Api {
    param(
        [string]$Method,
        [string]$Path,
        [object]$Body = $null,
        [string]$Token = ""
    )
    $url = if ($Path.StartsWith("http://") -or $Path.StartsWith("https://")) { $Path } else { "$BaseUrl$Path" }
    $httpMethod = New-Object System.Net.Http.HttpMethod($Method.ToUpperInvariant())
    $request = New-Object System.Net.Http.HttpRequestMessage($httpMethod, $url)

    if (-not [string]::IsNullOrWhiteSpace($Token)) {
        $request.Headers.Authorization = New-Object System.Net.Http.Headers.AuthenticationHeaderValue("Bearer", $Token)
    }

    if ($null -ne $Body) {
        $jsonBody = if ($Body -is [string]) { $Body } else { ($Body | ConvertTo-Json -Depth 10 -Compress) }
        $request.Content = New-Object System.Net.Http.StringContent($jsonBody, [System.Text.Encoding]::UTF8, "application/json")
    }

    $response = $script:HttpClient.SendAsync($request).GetAwaiter().GetResult()
    $bytes = $response.Content.ReadAsByteArrayAsync().GetAwaiter().GetResult()
    $text = [System.Text.Encoding]::UTF8.GetString($bytes)

    $parsedJson = $null
    if ($text -and ($text.TrimStart().StartsWith("{") -or $text.TrimStart().StartsWith("["))) {
        try {
            $parsedJson = $text | ConvertFrom-Json
        }
        catch {
            $parsedJson = $null
        }
    }

    return [PSCustomObject]@{
        StatusCode = [int]$response.StatusCode
        Bytes      = $bytes
        Text       = $text
        Json       = $parsedJson
        Response   = $response
    }
}

function Invoke-FileUpload {
    param(
        [string]$Path,
        [string]$FileName,
        [byte[]]$FileBytes,
        [string]$ContentType,
        [hashtable]$ExtraFields = @{},
        [string]$Token = ""
    )
    $url = "$BaseUrl$Path"
    $request = New-Object System.Net.Http.HttpRequestMessage([System.Net.Http.HttpMethod]::Post, $url)
    if (-not [string]::IsNullOrWhiteSpace($Token)) {
        $request.Headers.Authorization = New-Object System.Net.Http.Headers.AuthenticationHeaderValue("Bearer", $Token)
    }

    $multipart = New-Object System.Net.Http.MultipartFormDataContent
    foreach ($key in $ExtraFields.Keys) {
        $strContent = New-Object System.Net.Http.StringContent([string]$ExtraFields[$key], [System.Text.Encoding]::UTF8)
        $multipart.Add($strContent, $key)
    }

    $byteContent = New-Object System.Net.Http.ByteArrayContent(,$FileBytes)
    $byteContent.Headers.ContentType = [System.Net.Http.Headers.MediaTypeHeaderValue]::Parse($ContentType)
    $multipart.Add($byteContent, "file", $FileName)
    $request.Content = $multipart

    $response = $script:HttpClient.SendAsync($request).GetAwaiter().GetResult()
    $bytes = $response.Content.ReadAsByteArrayAsync().GetAwaiter().GetResult()
    $text = [System.Text.Encoding]::UTF8.GetString($bytes)

    $parsedJson = $null
    if ($text -and ($text.TrimStart().StartsWith("{") -or $text.TrimStart().StartsWith("["))) {
        try {
            $parsedJson = $text | ConvertFrom-Json
        }
        catch {
            $parsedJson = $null
        }
    }

    return [PSCustomObject]@{
        StatusCode = [int]$response.StatusCode
        Bytes      = $bytes
        Text       = $text
        Json       = $parsedJson
        Response   = $response
    }
}

function Escape-Xml {
    param([string]$Value)
    if ($null -eq $Value) { return "" }
    return [System.Security.SecurityElement]::Escape($Value)
}

function New-MinimalXlsxBytes {
    param(
        [object[]]$Rows
    )
    $ms = New-Object System.IO.MemoryStream
    $archive = New-Object System.IO.Compression.ZipArchive($ms, [System.IO.Compression.ZipArchiveMode]::Create, $true)

    function Add-ZipEntry {
        param([string]$EntryPath, [string]$XmlText)
        $entry = $archive.CreateEntry($EntryPath)
        $stream = $entry.Open()
        $writer = New-Object System.IO.StreamWriter($stream, (New-Object System.Text.UTF8Encoding($false)))
        $writer.Write($XmlText)
        $writer.Dispose()
        $stream.Dispose()
    }

    $contentTypes = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">' +
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-officedocument.relationships+xml"/>' +
        '<Default Extension="xml" ContentType="application/xml"/>' +
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>' +
        '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' +
        '</Types>'

    $rootRels = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' +
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>' +
        '</Relationships>'

    $workbook = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">' +
        '<sheets><sheet name="Applicants" sheetId="1" r:id="rId1"/></sheets>' +
        '</workbook>'

    $workbookRels = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' +
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>' +
        '</Relationships>'

    $sb = New-Object System.Text.StringBuilder
    [void]$sb.Append('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>')
    [void]$sb.Append('<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>')

    for ($r = 0; $r -lt $Rows.Count; $r++) {
        $rowNum = $r + 1
        $rowCells = $Rows[$r]
        [void]$sb.Append("<row r=`"$rowNum`">")
        for ($c = 0; $c -lt $rowCells.Count; $c++) {
            $colLetter = [char]([int][char]'A' + $c)
            $cellRef = "$colLetter$rowNum"
            $cellVal = $rowCells[$c]
            if ($null -ne $cellVal -and [string]$cellVal -ne "") {
                $escaped = Escape-Xml ([string]$cellVal)
                [void]$sb.Append("<c r=`"$cellRef`" t=`"inlineStr`"><is><t>$escaped</t></is></c>")
            }
        }
        [void]$sb.Append('</row>')
    }
    [void]$sb.Append('</sheetData></worksheet>')

    Add-ZipEntry "[Content_Types].xml" $contentTypes
    Add-ZipEntry "_rels/.rels" $rootRels
    Add-ZipEntry "xl/workbook.xml" $workbook
    Add-ZipEntry "xl/_rels/workbook.xml.rels" $workbookRels
    Add-ZipEntry "xl/worksheets/sheet1.xml" $sb.ToString()

    $archive.Dispose()
    $resultBytes = $ms.ToArray()
    $ms.Dispose()
    return ,$resultBytes
}

$runSuffix = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds().ToString()
$randDigits = (Get-Random -Minimum 1000000 -Maximum 9999999).ToString()
$publicPhone = "099" + $randDigits.Substring(0, 8)
$staffPhone = "098" + $randDigits.Substring(0, 7) + "1"
$importPhoneValid = "097" + $randDigits.Substring(0, 7) + "2"
$importPhoneInvalid = "096" + $randDigits.Substring(0, 7) + "3"
$tempStaffUsername = "smoke_staff_$runSuffix"
$tempStaffPassword = "SmokePass!$runSuffix"

$adminToken = ""
$adminId = 0
$staffToken = ""
$tempStaffId = 0
$uploadedKey = ""
$publicApplicantId = 0
$staffApplicantId = 0
$importBatchId = 0
$importApplicantId = 0

Write-Host "=== HR Smoke Test Suite ===" -ForegroundColor Cyan
Write-Host "Target: $BaseUrl"

# ------------------------------------------------------------------
# 1. Health & Nginx Routing
# ------------------------------------------------------------------
$res = Invoke-Api "GET" "/healthz"
Assert-Check "GET /healthz returns 200 ok" ($res.StatusCode -eq 200 -and $res.Text.Trim() -eq "ok") "status=$($res.StatusCode)"
$nosniff = Get-HeaderValue $res.Response "X-Content-Type-Options"
Assert-Check "Security header X-Content-Type-Options is nosniff" ($nosniff -eq "nosniff") "header=$nosniff"

$res = Invoke-Api "GET" "/api/health"
Assert-Check "GET /api/health returns 200 connected" ($res.StatusCode -eq 200 -and $null -ne $res.Json -and $res.Json.status -eq "ok" -and $res.Json.database -eq "connected") "status=$($res.StatusCode) body=$($res.Text)"

$h5Res = Invoke-Api "GET" "/"
Assert-Check "GET / (H5 root) returns 200 HTML" ($h5Res.StatusCode -eq 200 -and $h5Res.Text -match "<html") "status=$($h5Res.StatusCode)"

$applyRes = Invoke-Api "GET" "/apply"
Assert-Check "GET /apply (H5 history route) returns 200 HTML" ($applyRes.StatusCode -eq 200 -and $applyRes.Text -match "<html") "status=$($applyRes.StatusCode)"

$adminRes = Invoke-Api "GET" "/admin/"
Assert-Check "GET /admin/ returns 200 HTML" ($adminRes.StatusCode -eq 200 -and $adminRes.Text -match "<html") "status=$($adminRes.StatusCode)"

$h5AssetMatch = [regex]::Match($h5Res.Text, '(?:href|src)="(/assets/[^"]+)"')
if ($h5AssetMatch.Success) {
    $h5AssetPath = $h5AssetMatch.Groups[1].Value
    $assetRes = Invoke-Api "GET" $h5AssetPath
    Assert-Check "H5 referenced asset $h5AssetPath returns 200" ($assetRes.StatusCode -eq 200) "status=$($assetRes.StatusCode)"
}
else {
    Assert-Check "H5 index references /assets/* bundle" $false "no /assets/ tag found in /"
}

$adminAssetMatch = [regex]::Match($adminRes.Text, '(?:href|src)="(/admin/assets/[^"]+)"')
if ($adminAssetMatch.Success) {
    $adminAssetPath = $adminAssetMatch.Groups[1].Value
    $assetRes = Invoke-Api "GET" $adminAssetPath
    Assert-Check "Admin referenced asset $adminAssetPath returns 200" ($assetRes.StatusCode -eq 200) "status=$($assetRes.StatusCode)"
}
else {
    Assert-Check "Admin index references /admin/assets/* bundle" $false "no /admin/assets/ tag found in /admin/"
}

# ------------------------------------------------------------------
# 2. Hardened 404 Routes
# ------------------------------------------------------------------
foreach ($blockedPath in @("/docs", "/redoc", "/openapi.json", "/learning", "/uploads/test.jpg")) {
    $res = Invoke-Api "GET" $blockedPath
    Assert-Check "Hardened route GET $blockedPath returns 404" ($res.StatusCode -eq 404) "status=$($res.StatusCode)"
}

# ------------------------------------------------------------------
# 3. Auth & Staff RBAC
# ------------------------------------------------------------------
$res = Invoke-Api "POST" "/api/auth/login" @{ username = $AdminUsername; password = "WrongPassword!999" }
Assert-Check "POST /api/auth/login with wrong password returns 401" ($res.StatusCode -eq 401) "status=$($res.StatusCode)"

$res = Invoke-Api "POST" "/api/auth/login" @{ username = $AdminUsername; password = $AdminPassword }
$loginOk = ($res.StatusCode -eq 200 -and $null -ne $res.Json -and $null -ne $res.Json.data -and -not [string]::IsNullOrWhiteSpace($res.Json.data.token))
Assert-Check "POST /api/auth/login with valid admin returns 200 JWT" $loginOk "status=$($res.StatusCode)"
if ($loginOk) {
    $adminToken = [string]$res.Json.data.token
    $adminId = [int]$res.Json.data.staff.id
}

$res = Invoke-Api "POST" "/api/staff" @{ username = "shortpw_$runSuffix"; password = "short"; real_name = "Short PW"; role = "staff" } $adminToken
Assert-Check "POST /api/staff rejects password < 8 chars with 422" ($res.StatusCode -eq 422) "status=$($res.StatusCode)"

$res = Invoke-Api "POST" "/api/staff" @{ username = $tempStaffUsername; password = $tempStaffPassword; real_name = "Smoke Staff"; role = "staff" } $adminToken
$staffCreated = ($res.StatusCode -eq 200 -and $null -ne $res.Json -and $null -ne $res.Json.data -and [int]$res.Json.data.id -gt 0)
Assert-Check "POST /api/staff creates temp staff (200)" $staffCreated "status=$($res.StatusCode) body=$($res.Text)"
if ($staffCreated) {
    $tempStaffId = [int]$res.Json.data.id
}

$res = Invoke-Api "POST" "/api/auth/login" @{ username = $tempStaffUsername; password = $tempStaffPassword }
$staffLoginOk = ($res.StatusCode -eq 200 -and $null -ne $res.Json -and $null -ne $res.Json.data -and -not [string]::IsNullOrWhiteSpace($res.Json.data.token))
Assert-Check "POST /api/auth/login as temp staff returns 200 JWT" $staffLoginOk "status=$($res.StatusCode)"
if ($staffLoginOk) {
    $staffToken = [string]$res.Json.data.token
}

$res = Invoke-Api "GET" "/api/staff/list" $null $staffToken
Assert-Check "GET /api/staff/list as staff returns 403" ($res.StatusCode -eq 403) "status=$($res.StatusCode)"

$res = Invoke-Api "GET" "/api/export/applicant" $null $staffToken
Assert-Check "GET /api/export/applicant as staff returns 403" ($res.StatusCode -eq 403) "status=$($res.StatusCode)"

$res = Invoke-Api "GET" "/api/staff/list?keyword=$tempStaffUsername" $null $adminToken
$staffListOk = ($res.StatusCode -eq 200 -and $null -ne $res.Json -and $res.Json.data.total -ge 1)
Assert-Check "GET /api/staff/list as admin finds temp staff (200)" $staffListOk "status=$($res.StatusCode)"

$res = Invoke-Api "PATCH" "/api/staff/$adminId/status" @{ status = "disabled" } $adminToken
Assert-Check "Admin self-disable returns 400 (anti-lockout)" ($res.StatusCode -eq 400) "status=$($res.StatusCode)"

$activeAdminsRes = Invoke-Api "GET" "/api/staff/list?role=admin&status=active&page_size=100" $null $adminToken
$activeAdminCount = if ($activeAdminsRes.StatusCode -eq 200 -and $null -ne $activeAdminsRes.Json) { [int]$activeAdminsRes.Json.data.total } else { 0 }
if ($activeAdminCount -eq 1) {
    $res = Invoke-Api "PATCH" "/api/staff/$adminId" @{ role = "staff" } $adminToken
    Assert-Check "Last active admin self-demote returns 400 (anti-lockout)" ($res.StatusCode -eq 400) "status=$($res.StatusCode)"
}
else {
    Assert-Check "Admin role anti-lockout check skipped safely (active_admins=$activeAdminCount)" ($activeAdminCount -gt 1) "activeAdminCount=$activeAdminCount"
}

# ------------------------------------------------------------------
# 4. Upload & Signed Media
# ------------------------------------------------------------------
$dummyBytes = [System.Text.Encoding]::ASCII.GetBytes("not-allowed")
$res = Invoke-FileUpload "/api/oss/upload" "malware.exe" $dummyBytes "application/octet-stream" @{ kind = "media" }
Assert-Check "Upload .exe rejected with 415" ($res.StatusCode -eq 415) "status=$($res.StatusCode)"

$res = Invoke-FileUpload "/api/oss/upload" "phish.html" $dummyBytes "text/html" @{ kind = "media" }
Assert-Check "Upload .html rejected with 415" ($res.StatusCode -eq 415) "status=$($res.StatusCode)"

# Valid 1x1 transparent PNG
$pngBase64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
$pngBytes = [Convert]::FromBase64String($pngBase64)
$res = Invoke-FileUpload "/api/oss/upload" "smoke.png" $pngBytes "image/png" @{ kind = "media" }
$uploadOk = ($res.StatusCode -eq 200 -and $null -ne $res.Json -and $null -ne $res.Json.data -and [string]$res.Json.data.key -like "local/*")
Assert-Check "Upload valid 1x1 PNG returns 200 with local/ key" $uploadOk "status=$($res.StatusCode) body=$($res.Text)"
if ($uploadOk) {
    $uploadedKey = [string]$res.Json.data.key
}

$res = Invoke-Api "GET" "/api/media/bad-token"
Assert-Check "GET /api/media/bad-token returns 404" ($res.StatusCode -eq 404) "status=$($res.StatusCode)"

# ------------------------------------------------------------------
# 5. Public H5 Flows & Submit
# ------------------------------------------------------------------
$res = Invoke-Api "POST" "/api/applicant/check-phone" @{ phone = $publicPhone }
Assert-Check "POST /api/applicant/check-phone returns 200 exists=false for fresh phone" ($res.StatusCode -eq 200 -and $null -ne $res.Json -and $res.Json.data.exists -eq $false) "status=$($res.StatusCode)"

$res = Invoke-Api "POST" "/api/applicant/submit" @{
    privacy_agreed = $false
    first_name     = "Smoke"
    last_name      = "NoPrivacy"
    phone          = $publicPhone
}
Assert-Check "POST /api/applicant/submit without privacy_agreed returns 422" ($res.StatusCode -eq 422) "status=$($res.StatusCode)"

$res = Invoke-Api "POST" "/api/applicant/submit" @{
    privacy_agreed = $true
    first_name     = "Smoke"
    last_name      = "BadGender"
    phone          = $publicPhone
    gender         = "other"
}
Assert-Check "POST /api/applicant/submit with gender='other' returns 422" ($res.StatusCode -eq 422) "status=$($res.StatusCode)"

$res = Invoke-Api "POST" "/api/applicant/submit" @{
    privacy_agreed = $true
    first_name     = "Smoke"
    last_name      = "Public"
    phone          = $publicPhone
    gender         = $null
    photo_oss_key  = $uploadedKey
}
$pubSubmitOk = ($res.StatusCode -eq 200 -and $null -ne $res.Json -and [int]$res.Json.data.applicant_id -gt 0)
Assert-Check "POST /api/applicant/submit with gender=null returns 200" $pubSubmitOk "status=$($res.StatusCode) body=$($res.Text)"
if ($pubSubmitOk) {
    $publicApplicantId = [int]$res.Json.data.applicant_id
}

$res = Invoke-Api "POST" "/api/applicant/check-phone" @{ phone = $publicPhone }
Assert-Check "POST /api/applicant/check-phone returns 200 exists=true after submit" ($res.StatusCode -eq 200 -and $null -ne $res.Json -and $res.Json.data.exists -eq $true) "status=$($res.StatusCode)"

$res = Invoke-Api "POST" "/api/applicant/submit" @{
    privacy_agreed = $true
    first_name     = "Smoke"
    last_name      = "Duplicate"
    phone          = $publicPhone
}
Assert-Check "POST /api/applicant/submit duplicate phone returns 409 soft dedup" ($res.StatusCode -eq 409) "status=$($res.StatusCode)"

$res = Invoke-Api "POST" "/api/applicant/submit" @{
    privacy_agreed = $true
    first_name     = "Smoke"
    last_name      = "StaffEntry"
    phone          = $staffPhone
} $staffToken
$staffSubmitOk = ($res.StatusCode -eq 200 -and $null -ne $res.Json -and [int]$res.Json.data.applicant_id -gt 0)
Assert-Check "POST /api/applicant/submit authenticated as staff returns 200" $staffSubmitOk "status=$($res.StatusCode) body=$($res.Text)"
if ($staffSubmitOk) {
    $staffApplicantId = [int]$res.Json.data.applicant_id
}

$res = Invoke-Api "GET" "/api/applicant/$staffApplicantId" $null $adminToken
Assert-Check "Staff-submitted applicant has source_type='staff'" ($res.StatusCode -eq 200 -and $res.Json.data.source_type -eq "staff" -and $res.Json.data.source_ref -eq $tempStaffUsername) "status=$($res.StatusCode)"

# ------------------------------------------------------------------
# 6. Signed Media URL Read
# ------------------------------------------------------------------
$encodedKey = [Uri]::EscapeDataString($uploadedKey)
$res = Invoke-Api "GET" "/api/applicant/$publicApplicantId/media-url?key=$encodedKey" $null $adminToken
$mediaUrl = ""
$mediaUrlOk = ($res.StatusCode -eq 200 -and $null -ne $res.Json -and [string]$res.Json.data.url -like "/api/media/*")
Assert-Check "GET /api/applicant/{id}/media-url issues signed /api/media/ URL" $mediaUrlOk "status=$($res.StatusCode) body=$($res.Text)"
if ($mediaUrlOk) {
    $mediaUrl = [string]$res.Json.data.url
}

if ($mediaUrl) {
    $res = Invoke-Api "GET" $mediaUrl
    $ct = Get-HeaderValue $res.Response "Content-Type"
    $isPng = ($res.Bytes.Length -ge 4 -and $res.Bytes[0] -eq 0x89 -and $res.Bytes[1] -eq 0x50 -and $res.Bytes[2] -eq 0x4E -and $res.Bytes[3] -eq 0x47)
    Assert-Check "GET signed media URL returns 200 image/png" ($res.StatusCode -eq 200 -and $ct -like "image/png*" -and $isPng) "status=$($res.StatusCode) ct=$ct"
}
else {
    Assert-Check "GET signed media URL returns 200 image/png" $false "no signed media URL issued"
}

# ------------------------------------------------------------------
# 7. Applicant Workflow & 3-Round Interviews
# ------------------------------------------------------------------
$res = Invoke-Api "GET" "/api/applicant/list?gender=unspecified&keyword=$publicPhone" $null $adminToken
Assert-Check "GET /api/applicant/list?gender=unspecified finds blank-gender applicant" ($res.StatusCode -eq 200 -and $res.Json.data.total -ge 1) "status=$($res.StatusCode)"

$res = Invoke-Api "GET" "/api/applicant/list?source_type=staff&keyword=$staffPhone" $null $adminToken
Assert-Check "GET /api/applicant/list?source_type=staff finds staff-entry applicant" ($res.StatusCode -eq 200 -and $res.Json.data.total -ge 1) "status=$($res.StatusCode)"

$res = Invoke-Api "GET" "/api/applicant/stats/today" $null $adminToken
Assert-Check "GET /api/applicant/stats/today returns 200 with today_total >= 2" ($res.StatusCode -eq 200 -and $res.Json.data.today_total -ge 2) "status=$($res.StatusCode)"

$res = Invoke-Api "GET" "/api/applicant/$publicApplicantId" $null $adminToken
Assert-Check "GET /api/applicant/{id} returns 200 with gender=null and privacy_agreed_at" ($res.StatusCode -eq 200 -and $null -eq $res.Json.data.gender -and -not [string]::IsNullOrWhiteSpace([string]$res.Json.data.privacy_agreed_at)) "status=$($res.StatusCode)"

$res = Invoke-Api "PATCH" "/api/applicant/$publicApplicantId" @{
    middle_name      = "Santos"
    email            = "smoke.$runSuffix@example.com"
    address_city     = "Makati"
    target_job       = "Customer Service"
    expected_salary  = 28000
    availability     = 1
    intent_tags      = "bpo,voice"
    english_level    = "fluent"
    internal_remark  = "Smoke internal note"
} $adminToken
$patchOk = ($res.StatusCode -eq 200 -and $res.Json.data.middle_name -eq "Santos" -and $res.Json.data.address_city -eq "Makati" -and $res.Json.data.intent_tags -eq "bpo,voice")
Assert-Check "PATCH /api/applicant/{id} updates fields (200)" $patchOk "status=$($res.StatusCode) body=$($res.Text)"

$res = Invoke-Api "PATCH" "/api/applicant/$publicApplicantId" @{
    middle_name     = $null
    internal_remark = $null
} $adminToken
Assert-Check "PATCH /api/applicant/{id} explicit null clears nullable fields" ($res.StatusCode -eq 200 -and $null -eq $res.Json.data.middle_name -and $null -eq $res.Json.data.internal_remark) "status=$($res.StatusCode)"

$res = Invoke-Api "PATCH" "/api/applicant/$publicApplicantId/status" @{
    to_status = "contacted"
    note      = "Smoke contacted"
} $adminToken
Assert-Check "PATCH /api/applicant/{id}/status transitions to contacted (200)" ($res.StatusCode -eq 200 -and $res.Json.data.status -eq "contacted") "status=$($res.StatusCode)"

$res = Invoke-Api "GET" "/api/applicant/$publicApplicantId/history" $null $adminToken
Assert-Check "GET /api/applicant/{id}/history returns timeline with contacted" ($res.StatusCode -eq 200 -and $res.Json.data.Count -ge 2 -and $res.Json.data[0].to_status -eq "contacted") "status=$($res.StatusCode)"

$manilaTz = [System.TimeZoneInfo]::FindSystemTimeZoneById("Singapore Standard Time")
$manilaNow = [System.TimeZoneInfo]::ConvertTimeFromUtc([DateTime]::UtcNow, $manilaTz)
$followAtStr = $manilaNow.ToString("yyyy-MM-ddTHH:mm:ss")

$res = Invoke-Api "POST" "/api/applicant/$publicApplicantId/contacts" @{
    channel        = "phone"
    result         = "reached"
    note           = "Smoke call log"
    next_follow_at = $followAtStr
} $adminToken
Assert-Check "POST /api/applicant/{id}/contacts creates contact log (200)" ($res.StatusCode -eq 200 -and $res.Json.data.note -eq "Smoke call log") "status=$($res.StatusCode) body=$($res.Text)"

$res = Invoke-Api "GET" "/api/applicant/$publicApplicantId/contacts" $null $adminToken
Assert-Check "GET /api/applicant/{id}/contacts lists created contact log" ($res.StatusCode -eq 200 -and $res.Json.data.Count -ge 1 -and $res.Json.data[0].note -eq "Smoke call log") "status=$($res.StatusCode)"

$res = Invoke-Api "GET" "/api/contact/follow-ups" $null $adminToken
$hasFollowUp = $false
if ($res.StatusCode -eq 200 -and $null -ne $res.Json.data) {
    foreach ($item in $res.Json.data) {
        if ([int]$item.applicant_id -eq $publicApplicantId) {
            $hasFollowUp = $true
            break
        }
    }
}
Assert-Check "GET /api/contact/follow-ups includes applicant scheduled for today" $hasFollowUp "status=$($res.StatusCode)"

$res = Invoke-Api "POST" "/api/applicant/$publicApplicantId/interviews" @{
    round  = 4
    result = "pass"
} $adminToken
Assert-Check "POST /api/applicant/{id}/interviews rejects invalid round=4 with 422" ($res.StatusCode -eq 422) "status=$($res.StatusCode)"

$res = Invoke-Api "POST" "/api/applicant/$publicApplicantId/interviews" @{
    round        = 1
    interview_at = $followAtStr
    result       = "pass"
    comment      = "Round 1 passed in smoke test"
} $adminToken
Assert-Check "POST /api/applicant/{id}/interviews creates Round 1 pass (200)" ($res.StatusCode -eq 200 -and [int]$res.Json.data.round -eq 1 -and $res.Json.data.result -eq "pass") "status=$($res.StatusCode) body=$($res.Text)"

$res = Invoke-Api "GET" "/api/applicant/$publicApplicantId/interviews" $null $adminToken
Assert-Check "GET /api/applicant/{id}/interviews returns Round 1 record" ($res.StatusCode -eq 200 -and $res.Json.data.Count -ge 1 -and [int]$res.Json.data[0].round -eq 1) "status=$($res.StatusCode)"

# ------------------------------------------------------------------
# 8. Bulk Excel Import
# ------------------------------------------------------------------
$res = Invoke-Api "GET" "/api/import/template" $null $adminToken
$tplCt = Get-HeaderValue $res.Response "Content-Type"
$tplIsZip = ($res.Bytes.Length -ge 2 -and $res.Bytes[0] -eq 0x50 -and $res.Bytes[1] -eq 0x4B)
Assert-Check "GET /api/import/template returns 200 .xlsx" ($res.StatusCode -eq 200 -and $tplCt -like "*spreadsheetml.sheet*" -and $tplIsZip) "status=$($res.StatusCode) ct=$tplCt"

$txtBytes = [System.Text.Encoding]::UTF8.GetBytes("not an xlsx file")
$res = Invoke-FileUpload "/api/import/applicant" "not_excel.txt" $txtBytes "text/plain" @{} $adminToken
Assert-Check "POST /api/import/applicant rejects non-.xlsx with 400" ($res.StatusCode -eq 400) "status=$($res.StatusCode)"

$xlsxRows = @(
    @("First Name*", "Last Name*", "Mobile*", "Gender"),
    @("Smoke", "ImportValid", $importPhoneValid, ""),
    @("Smoke", "ImportInvalid", $importPhoneInvalid, "other")
)
$xlsxBytes = New-MinimalXlsxBytes -Rows $xlsxRows
$res = Invoke-FileUpload "/api/import/applicant" "smoke_import_$runSuffix.xlsx" $xlsxBytes "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" @{} $adminToken
$importOk = ($res.StatusCode -eq 200 -and $null -ne $res.Json -and [int]$res.Json.data.total_count -eq 2 -and [int]$res.Json.data.success_count -eq 1 -and [int]$res.Json.data.fail_count -eq 1)
Assert-Check "POST /api/import/applicant imports blank-gender row and rejects gender='other' (200)" $importOk "status=$($res.StatusCode) body=$($res.Text)"
if ($importOk) {
    $importBatchId = [int]$res.Json.data.batch_id
}

$res = Invoke-Api "GET" "/api/import/batches?page=1&page_size=5" $null $adminToken
$batchFound = $false
if ($res.StatusCode -eq 200 -and $null -ne $res.Json.data.items) {
    foreach ($b in $res.Json.data.items) {
        if ([int]$b.id -eq $importBatchId) {
            $batchFound = $true
            break
        }
    }
}
Assert-Check "GET /api/import/batches lists the import batch (200)" $batchFound "status=$($res.StatusCode)"

# ------------------------------------------------------------------
# 9. Excel Export
# ------------------------------------------------------------------
$res = Invoke-Api "GET" "/api/export/applicant" $null $adminToken
$expTruncated = Get-HeaderValue $res.Response "X-Export-Truncated"
$expMaxRows = Get-HeaderValue $res.Response "X-Export-Max-Rows"
$expIsZip = ($res.Bytes.Length -ge 2 -and $res.Bytes[0] -eq 0x50 -and $res.Bytes[1] -eq 0x4B)
Assert-Check "GET /api/export/applicant (admin default masked) returns 200 with truncation headers" ($res.StatusCode -eq 200 -and $null -ne $expTruncated -and $null -ne $expMaxRows -and $expIsZip) "status=$($res.StatusCode) trunc=$expTruncated max=$expMaxRows"

$res = Invoke-Api "GET" "/api/export/applicant?include_pii=true" $null $adminToken
$piiIsZip = ($res.Bytes.Length -ge 2 -and $res.Bytes[0] -eq 0x50 -and $res.Bytes[1] -eq 0x4B)
Assert-Check "GET /api/export/applicant?include_pii=true as admin returns 200 .xlsx" ($res.StatusCode -eq 200 -and $piiIsZip) "status=$($res.StatusCode)"

$res = Invoke-Api "GET" "/api/export/applicant?include_pii=true" $null $staffToken
Assert-Check "GET /api/export/applicant?include_pii=true as staff returns 403" ($res.StatusCode -eq 403) "status=$($res.StatusCode)"

# ------------------------------------------------------------------
# 10. Staff Disable & Soft-Delete Cleanup
# ------------------------------------------------------------------
$res = Invoke-Api "PATCH" "/api/staff/$tempStaffId/status" @{ status = "disabled" } $adminToken
Assert-Check "PATCH /api/staff/{id}/status disables temp staff (200)" ($res.StatusCode -eq 200 -and $res.Json.data.status -eq "disabled") "status=$($res.StatusCode)"

$res = Invoke-Api "POST" "/api/auth/login" @{ username = $tempStaffUsername; password = $tempStaffPassword }
Assert-Check "Disabled temp staff login rejected with 403" ($res.StatusCode -eq 403) "status=$($res.StatusCode)"

$impList = Invoke-Api "GET" "/api/applicant/list?keyword=$importPhoneValid" $null $adminToken
if ($impList.StatusCode -eq 200 -and $impList.Json.data.items.Count -ge 1) {
    $importApplicantId = [int]$impList.Json.data.items[0].id
}

$res = Invoke-Api "DELETE" "/api/applicant/$publicApplicantId" $null $adminToken
Assert-Check "DELETE /api/applicant/{publicId} soft-deletes public applicant (200)" ($res.StatusCode -eq 200) "status=$($res.StatusCode)"

$res = Invoke-Api "DELETE" "/api/applicant/$staffApplicantId" $null $adminToken
Assert-Check "DELETE /api/applicant/{staffId} soft-deletes staff applicant (200)" ($res.StatusCode -eq 200) "status=$($res.StatusCode)"

if ($importApplicantId -gt 0) {
    $res = Invoke-Api "DELETE" "/api/applicant/$importApplicantId" $null $adminToken
    Assert-Check "DELETE /api/applicant/{importId} soft-deletes imported applicant (200)" ($res.StatusCode -eq 200) "status=$($res.StatusCode)"
}
else {
    Assert-Check "DELETE imported applicant" $false "imported applicant id not found"
}

$res = Invoke-Api "GET" "/api/applicant/$publicApplicantId" $null $adminToken
Assert-Check "GET /api/applicant/{publicId} after soft-delete returns 404" ($res.StatusCode -eq 404) "status=$($res.StatusCode)"

# ------------------------------------------------------------------
# 11. Anonymous Submit Rate Limit (optional)
# ------------------------------------------------------------------
if (-not $SkipRateLimit) {
    $hit429 = $false
    for ($i = 1; $i -le 7; $i++) {
        $rlRes = Invoke-Api "POST" "/api/applicant/submit" @{
            privacy_agreed = $true
            first_name     = "Smoke"
            last_name      = "RateLimit"
            phone          = $publicPhone
        }
        if ($rlRes.StatusCode -eq 429) {
            $hit429 = $true
            break
        }
    }
    Assert-Check "Anonymous POST /api/applicant/submit triggers 429 rate limit" $hit429 "did not hit 429 within 7 attempts"
}
else {
    Write-Host "[SKIP] Anonymous submit rate-limit check skipped (-SkipRateLimit)" -ForegroundColor Yellow
}

Write-Host ""
Write-Host ("=== Summary: {0} passed, {1} failed (total {2} assertions) ===" -f $script:PassCount, $script:FailCount, $script:AssertionIndex) -ForegroundColor Cyan

$script:HttpClient.Dispose()

if ($script:FailCount -gt 0) {
    exit 1
}
exit 0
