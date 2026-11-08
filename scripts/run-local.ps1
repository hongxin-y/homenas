param(
  [int]$Port = 8787
)

$env:HOMENAS_PORT = $Port
$pythonCandidate = Join-Path (Get-Location) ".venv\Scripts\python.exe"
$python = "python"
if (Test-Path -LiteralPath $pythonCandidate) {
  & $pythonCandidate -c "import psutil" 2>$null
  if ($LASTEXITCODE -eq 0) { $python = $pythonCandidate }
}

& $python -c "import importlib.util; raise SystemExit(0 if importlib.util.find_spec('fastapi') else 1)"
if ($LASTEXITCODE -eq 0) {
  & $python -m uvicorn homenas.main:app --app-dir backend --host 127.0.0.1 --port $Port
} else {
  Write-Host "FastAPI not installed; using dependency-free local fallback server." -ForegroundColor Yellow
  $env:PYTHONPATH = (Join-Path (Get-Location) "backend")
  & $python -m homenas.standalone
}

