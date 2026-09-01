param(
  [int]$Port = 4174,
  [string]$FrontendDir = $PSScriptRoot,
  [string]$ReportPath = ''
)

$ErrorActionPreference = 'Stop'
$frontend = (Resolve-Path -LiteralPath $FrontendDir).Path
$results = [System.Collections.Generic.List[object]]::new()
$serverProcess = $null
$baseUrl = "http://127.0.0.1:$Port"

function Add-Result {
  param([string]$Name, [bool]$Passed, [string]$Detail)
  $script:results.Add([PSCustomObject]@{
    name = $Name
    passed = $Passed
    detail = $Detail
  })
}

function Test-HttpReady {
  try {
    $response = Invoke-WebRequest -Uri "$baseUrl/index.html" -UseBasicParsing -TimeoutSec 2
    return $response.StatusCode -eq 200
  } catch {
    return $false
  }
}

try {
  $requiredFiles = @(
    'index.html', 'models.html', 'chat.html', 'image.html',
    'audio.html', 'video.html', 'tasks.html', 'profile.html', 'auth.html',
    'css/app.css', 'css/hardening.css', 'css/auth.css', 'js/api.js', 'js/app.js', 'js/auth.js',
    'vendor/jquery/jquery-3.7.1.min.js',
    'vendor/layui/layui.js', 'vendor/layui/css/layui.css',
    'vendor/layui/font/iconfont.woff2'
  )
  $missing = @($requiredFiles | Where-Object { -not (Test-Path -LiteralPath (Join-Path $frontend $_)) })
  Add-Result 'required_files' ($missing.Count -eq 0) $(if ($missing.Count -gt 0) { 'Missing: ' + ($missing -join ', ') } else { "$($requiredFiles.Count) required files found" })

  $node = Get-Command node -ErrorAction SilentlyContinue
  if ($node) {
    $syntaxErrors = @()
    foreach ($scriptFile in @('js/api.js', 'js/app.js', 'js/auth.js')) {
      $output = & $node.Source --check (Join-Path $frontend $scriptFile) 2>&1
      if ($LASTEXITCODE -ne 0) { $syntaxErrors += "${scriptFile}: $output" }
    }
    Add-Result 'javascript_syntax' ($syntaxErrors.Count -eq 0) $(if ($syntaxErrors.Count -gt 0) { $syntaxErrors -join '; ' } else { 'api.js, app.js and auth.js passed node --check' })
  } else {
    Add-Result 'javascript_syntax' $false 'node command not found'
  }

  $textFiles = Get-ChildItem -LiteralPath $frontend -Recurse -File | Where-Object { $_.Extension -in '.html', '.js', '.css', '.md' }
  $conflictMarkers = @($textFiles | Select-String -Pattern '^(<<<<<<<|=======|>>>>>>>)' -ErrorAction SilentlyContinue)
  Add-Result 'git_conflict_markers' ($conflictMarkers.Count -eq 0) $(if ($conflictMarkers.Count -gt 0) { "Found $($conflictMarkers.Count) conflict markers" } else { 'No conflict markers found' })

  $secretPattern = 'sk-[A-Za-z0-9]{16,}|AKIA[0-9A-Z]{16}|BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY|SILICONFLOW_API_KEY\s*=\s*[^\s]+'
  $secretHits = @($textFiles | Select-String -Pattern $secretPattern -AllMatches -ErrorAction SilentlyContinue)
  Add-Result 'common_secret_patterns' ($secretHits.Count -eq 0) $(if ($secretHits.Count -gt 0) { "Found $($secretHits.Count) possible secret patterns" } else { 'No common key or private-key patterns found' })

  $htmlFiles = Get-ChildItem -LiteralPath $frontend -Filter '*.html' -File
  $cdnHits = @($htmlFiles | Select-String -Pattern 'cdn\.staticfile|unpkg\.com|cdn\.jsdelivr|cdnjs\.cloudflare' -ErrorAction SilentlyContinue)
  Add-Result 'external_cdn' ($cdnHits.Count -eq 0) $(if ($cdnHits.Count -gt 0) { "Found $($cdnHits.Count) external CDN references" } else { "All $($htmlFiles.Count) pages use local static dependencies" })

  if (-not (Test-HttpReady)) {
    $python = Get-Command python -ErrorAction SilentlyContinue
    if (-not $python) { throw 'python command not found and no frontend server is listening on the selected port' }
    $serverProcess = Start-Process -FilePath $python.Source -ArgumentList @('-m', 'http.server', $Port, '--bind', '127.0.0.1', '--directory', $frontend) -WindowStyle Hidden -PassThru
    $ready = $false
    foreach ($attempt in 1..20) {
      Start-Sleep -Milliseconds 250
      if (Test-HttpReady) { $ready = $true; break }
    }
    if (-not $ready) { throw "Local server did not start on port $Port" }
  }

  $pageResults = @()
  foreach ($page in @('index.html', 'models.html', 'chat.html', 'image.html', 'audio.html', 'video.html', 'tasks.html', 'profile.html', 'auth.html')) {
    $watch = [System.Diagnostics.Stopwatch]::StartNew()
    try {
      $response = Invoke-WebRequest -Uri "$baseUrl/${page}?offline_check=1" -UseBasicParsing -TimeoutSec 10
      $watch.Stop()
      $pageResults += [PSCustomObject]@{ page = $page; status = $response.StatusCode; milliseconds = $watch.ElapsedMilliseconds }
    } catch {
      $watch.Stop()
      $pageResults += [PSCustomObject]@{ page = $page; status = 0; milliseconds = $watch.ElapsedMilliseconds; error = $_.Exception.Message }
    }
  }
  $badPages = @($pageResults | Where-Object { $_.status -ne 200 })
  $maxMilliseconds = ($pageResults | Measure-Object -Property milliseconds -Maximum).Maximum
  Add-Result 'page_http_access' ($badPages.Count -eq 0) $(if ($badPages.Count -gt 0) { 'Failed pages: ' + (($badPages | ForEach-Object page) -join ', ') } else { "All $($pageResults.Count) pages returned 200; slowest ${maxMilliseconds}ms" })

  $assetResults = @()
  foreach ($asset in @('css/app.css', 'css/hardening.css', 'css/auth.css', 'js/api.js', 'js/app.js', 'js/auth.js', 'vendor/jquery/jquery-3.7.1.min.js', 'vendor/layui/layui.js', 'vendor/layui/font/iconfont.woff2')) {
    try {
      $response = Invoke-WebRequest -Uri "$baseUrl/${asset}?offline_check=1" -UseBasicParsing -TimeoutSec 10
      $assetResults += [PSCustomObject]@{ asset = $asset; status = $response.StatusCode; bytes = $response.RawContentLength }
    } catch {
      $assetResults += [PSCustomObject]@{ asset = $asset; status = 0; bytes = 0; error = $_.Exception.Message }
    }
  }
  $badAssets = @($assetResults | Where-Object { $_.status -ne 200 -or $_.bytes -le 0 })
  Add-Result 'local_static_assets' ($badAssets.Count -eq 0) $(if ($badAssets.Count -gt 0) { 'Failed assets: ' + (($badAssets | ForEach-Object asset) -join ', ') } else { "All $($assetResults.Count) core assets are accessible" })

  $passed = @($results | Where-Object { -not $_.passed }).Count -eq 0
  $report = [PSCustomObject]@{
    generated_at = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss zzz')
    frontend_dir = $frontend
    base_url = $baseUrl
    passed = $passed
    checks = $results
    pages = $pageResults
    assets = $assetResults
  }

  if ($ReportPath) {
    $parent = Split-Path -Parent $ReportPath
    if ($parent -and -not (Test-Path -LiteralPath $parent)) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
    $report | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $ReportPath -Encoding UTF8
  }

  $results | Select-Object @{Name='result';Expression={if($_.passed){'PASS'}else{'FAIL'}}},@{Name='check';Expression={$_.name}},detail | Format-Table -AutoSize
  if (-not $passed) { exit 1 }
} catch {
  Write-Error $_
  exit 1
} finally {
  if ($serverProcess -and -not $serverProcess.HasExited) {
    Stop-Process -Id $serverProcess.Id -Force
  }
}
