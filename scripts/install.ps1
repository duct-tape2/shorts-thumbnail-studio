param([switch]$NoLaunch)
$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$base = Split-Path -Parent $MyInvocation.MyCommand.Path
function File-Hash($path) {
    $stream = [IO.File]::OpenRead($path)
    $sha = [Security.Cryptography.SHA256]::Create()
    try { return [BitConverter]::ToString($sha.ComputeHash($stream)).Replace('-','') }
    finally { $stream.Dispose(); $sha.Dispose() }
}
function Hash-Matches($path, $expected) {
    return (Test-Path -LiteralPath $path -PathType Leaf) -and ((File-Hash $path) -eq $expected)
}
try {
    $manifestPath = Join-Path $base 'manifest.json'
    $manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $appRoot = Join-Path $base 'app-v1.2.0'
    $app = Join-Path $appRoot 'ThumbnailStudio'
    $exe = Join-Path $app 'ThumbnailStudio.exe'
    $marker = Join-Path $appRoot 'installed.json'
    $fingerprint = File-Hash $manifestPath
    if ((Test-Path -LiteralPath $marker) -and (Hash-Matches $exe $manifest.exeSha256)) {
        $installed = Get-Content -LiteralPath $marker -Raw | ConvertFrom-Json
        if ($installed.fingerprint -eq $fingerprint) {
            Write-Host 'Installation already verified. Starting the app.'
            if (-not $NoLaunch) { Start-Process -FilePath $exe -WorkingDirectory $app -WindowStyle Normal }
            exit 0
        }
    }
    $cache = Join-Path $base 'downloads'
    New-Item -ItemType Directory -Path $cache -Force | Out-Null
    $index = 0
    foreach ($part in $manifest.parts) {
        $index++
        if ($part.name -notmatch '^runtime-v1\.2\.0\.zip\.\d{3}$') { throw 'Invalid package name.' }
        $target = Join-Path $cache $part.name
        if (Hash-Matches $target $part.sha256) { Write-Host "[$index/$($manifest.parts.Count)] Verified cached $($part.name)"; continue }
        $partial = $target + '.partial'
        $ok = $false
        for ($attempt = 1; $attempt -le 3; $attempt++) {
            try {
                Write-Host "[$index/$($manifest.parts.Count)] Downloading $($part.name), attempt $attempt..."
                Invoke-WebRequest -Uri $part.url -OutFile $partial -UseBasicParsing -TimeoutSec 1800
                if (-not (Hash-Matches $partial $part.sha256)) { throw 'Downloaded file checksum mismatch.' }
                Move-Item -LiteralPath $partial -Destination $target -Force
                $ok = $true; break
            } catch {
                if ($attempt -eq 3) { throw }
                Write-Host 'Download interrupted. Retrying; completed parts are preserved.'
            }
        }
        if (-not $ok) { throw 'Download failed.' }
    }
    $archive = Join-Path $cache 'runtime.zip'
    if (-not (Hash-Matches $archive $manifest.archiveSha256)) {
        Write-Host 'Combining verified files...'
        $destination = [IO.File]::Create($archive)
        try {
            foreach ($part in $manifest.parts) {
                $inputStream = [IO.File]::OpenRead((Join-Path $cache $part.name))
                try { $inputStream.CopyTo($destination) } finally { $inputStream.Dispose() }
            }
        } finally { $destination.Dispose() }
        if (-not (Hash-Matches $archive $manifest.archiveSha256)) { throw 'Combined package checksum mismatch.' }
    }
    Write-Host 'Extracting application...'
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = [IO.Compression.ZipFile]::OpenRead($archive)
    try {
        $prefix = [IO.Path]::GetFullPath($appRoot) + [IO.Path]::DirectorySeparatorChar
        foreach ($entry in $zip.Entries) {
            $targetPath = [IO.Path]::GetFullPath((Join-Path $appRoot $entry.FullName))
            if (-not $targetPath.StartsWith($prefix,[StringComparison]::OrdinalIgnoreCase)) { throw 'Unsafe archive path.' }
            if ($entry.FullName.EndsWith('/')) { [IO.Directory]::CreateDirectory($targetPath) | Out-Null; continue }
            [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($targetPath)) | Out-Null
            $entryStream = $entry.Open(); $fileStream = [IO.File]::Create($targetPath)
            try { $entryStream.CopyTo($fileStream) } finally { $entryStream.Dispose(); $fileStream.Dispose() }
        }
    } finally { $zip.Dispose() }
    if (-not (Hash-Matches $exe $manifest.exeSha256)) { throw 'Application checksum mismatch.' }
    if ($manifest.templateSha256) {
        $template = Join-Path $base 'template.psd'
        if (-not (Hash-Matches $template $manifest.templateSha256)) { throw 'Private template checksum mismatch.' }
        Copy-Item -LiteralPath $template -Destination (Join-Path $app 'assets/template.psd') -Force
    }
    Copy-Item -LiteralPath (Join-Path $base 'README.md') -Destination (Join-Path $app 'README.md') -Force
    Copy-Item -LiteralPath (Join-Path $base 'README.md') -Destination (Join-Path $app '사용법.txt') -Force
    @{fingerprint=$fingerprint} | ConvertTo-Json | Set-Content -LiteralPath $marker -Encoding UTF8
    Write-Host 'Ready. Future runs work offline. Close any older app from its tray menu first.'
    if (-not $NoLaunch) { Start-Process -FilePath $exe -WorkingDirectory $app -WindowStyle Normal }
    exit 0
} catch {
    Write-Host ('Setup failed: ' + $_.Exception.Message) -ForegroundColor Red
    Write-Host 'Run again to resume. Do not delete the downloads folder.'
    exit 1
}
