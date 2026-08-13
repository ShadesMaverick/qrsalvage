# Stop-Hook: Qualitaetsgates am Ende eines Durchgangs.
#
# Grundsatz: Dieser Hook darf eine Sitzung niemals haengen lassen. Jeder unerwartete
# Zustand -- fehlendes Venv, fehlendes Werkzeug, kaputtes JSON -- fuehrt zu Exit 0.
# Exit 2 gibt es ausschliesslich fuer ein echtes rotes Gate, und hoechstens einmal
# pro Nutzeranfrage (Sperrdatei unter out/), damit keine Endlosschleife entsteht.

$ErrorActionPreference = 'Continue'

try {
    $root = if ($env:CLAUDE_PROJECT_DIR) { $env:CLAUDE_PROJECT_DIR } else { (Get-Location).Path }
    Set-Location -LiteralPath $root

    # --- Ereignis-JSON von stdin, nur fuer die Sperrdatei ---------------------
    $promptId = 'unknown'
    try {
        $raw = [Console]::In.ReadToEnd()
        if ($raw) {
            $evt = $raw | ConvertFrom-Json
            if ($evt.prompt_id) { $promptId = $evt.prompt_id }
        }
    } catch { }

    # --- Nur laufen, wenn Python-Code beruehrt wurde --------------------------
    # Bewusst ueber den Arbeitsbaum statt ueber den Verlauf: was im Durchgang
    # bereits committet wurde, gilt als geprueft.
    $dirty = & git status --porcelain -- "*.py" 2>$null
    if (-not $dirty) { exit 0 }

    $py = Join-Path $root '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $py)) {
        Write-Output "Gates uebersprungen: .venv fehlt. Setup steht in CLAUDE.md."
        exit 0
    }

    # Fehlende Werkzeuge sind ein Hinweis, kein rotes Gate -- sonst blockiert der
    # Hook bei jedem frisch geklonten Arbeitsplatz.
    & $py -m ruff --version *> $null
    $ruffOk = ($LASTEXITCODE -eq 0)
    & $py -m pytest --version *> $null
    $pytestOk = ($LASTEXITCODE -eq 0)
    if (-not ($ruffOk -and $pytestOk)) {
        Write-Output "Gates uebersprungen: ruff/pytest nicht im .venv. Siehe requirements.txt."
        exit 0
    }

    # --- Gates ----------------------------------------------------------------
    # pytest liefert 5, wenn nichts eingesammelt wurde. Solange tests/ noch leer
    # ist, ist das kein Fehler.
    $failed = @()

    & $py -m ruff check . 2>&1 | Out-String -OutVariable ruffOut | Out-Null
    if ($LASTEXITCODE -ne 0) { $failed += "ruff check" }

    & $py -m pytest -m "not regression" 2>&1 | Out-String -OutVariable unitOut | Out-Null
    if ($LASTEXITCODE -notin @(0, 5)) { $failed += "pytest (Unit)" }

    & $py -m pytest -m regression 2>&1 | Out-String -OutVariable regOut | Out-Null
    if ($LASTEXITCODE -notin @(0, 5)) { $failed += "pytest -m regression (Bildkorpus)" }

    if ($failed.Count -eq 0) { exit 0 }

    # --- Rotes Gate -----------------------------------------------------------
    $outDir = Join-Path $root 'out'
    if (-not (Test-Path -LiteralPath $outDir)) {
        New-Item -ItemType Directory -Path $outDir | Out-Null
    }
    $guard = Join-Path $outDir ".gate-$promptId"

    $detail = (@($ruffOut, $unitOut, $regOut) -join "`n").Trim()
    if ($detail.Length -gt 4000) { $detail = $detail.Substring(0, 4000) + "`n[gekuerzt]" }

    if (Test-Path -LiteralPath $guard) {
        # Zweiter Durchlauf derselben Anfrage: melden, aber nicht erneut blockieren.
        Write-Output "Gates weiterhin rot ($($failed -join ', ')). Nicht erneut blockiert."
        exit 0
    }

    New-Item -ItemType File -Path $guard -Force | Out-Null
    [Console]::Error.WriteLine("Qualitaetsgates rot: $($failed -join ', ')")
    [Console]::Error.WriteLine($detail)
    [Console]::Error.WriteLine("Ursache beheben, nicht das Gate umgehen. Faellt ein Fixture um, ist das ein Befund.")
    exit 2

} catch {
    Write-Output "Gate-Hook uebersprungen (interner Fehler): $($_.Exception.Message)"
    exit 0
}
