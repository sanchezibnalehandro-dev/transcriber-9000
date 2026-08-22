param(
    [switch]$SmokeTest
)

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

[System.Windows.Forms.Application]::EnableVisualStyles()

$ErrorActionPreference = "Stop"
$AppDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$InputDir = Join-Path $AppDir "input"
$OutputDir = Join-Path $AppDir "output"
$PythonExe = Join-Path $AppDir ".venv\Scripts\python.exe"
$CoreScript = Join-Path $AppDir "topgun_razbor.py"
$RunDir = Join-Path $AppDir ".cache\topgun_razbor\runs"

function Quote-Arg([string]$Value) {
    return '"' + ($Value -replace '"', '\"') + '"'
}

function Is-InInput([string]$Path) {
    $full = [System.IO.Path]::GetFullPath($Path)
    $inputFull = [System.IO.Path]::GetFullPath($InputDir)
    if (-not $inputFull.EndsWith([System.IO.Path]::DirectorySeparatorChar)) {
        $inputFull += [System.IO.Path]::DirectorySeparatorChar
    }
    return $full.StartsWith($inputFull, [System.StringComparison]::OrdinalIgnoreCase)
}

function New-Label($text, $x, $y, $w, $h, $fontSize, $style) {
    $label = New-Object System.Windows.Forms.Label
    $label.Text = $text
    $label.Location = New-Object System.Drawing.Point($x, $y)
    $label.Size = New-Object System.Drawing.Size($w, $h)
    $label.Font = New-Object System.Drawing.Font("Segoe UI", $fontSize, $style)
    $label.ForeColor = [System.Drawing.Color]::FromArgb(23, 32, 51)
    return $label
}

function Set-UiBusy([bool]$busy) {
    $chooseButton.Enabled = -not $busy
    $startButton.Enabled = -not $busy
    $languageRu.Enabled = -not $busy
    $languageAuto.Enabled = -not $busy
    $qualityFast.Enabled = -not $busy
    $qualityBalanced.Enabled = -not $busy
    $qualityBest.Enabled = -not $busy
    $qualityPremium.Enabled = -not $busy
    $qualityMaximum.Enabled = -not $busy
    $formatTxt.Enabled = -not $busy
    $formatSrt.Enabled = -not $busy
}

function Append-Log([string]$text) {
    $logBox.AppendText(($text.Trim() + [Environment]::NewLine + [Environment]::NewLine))
}

function Show-Error([string]$text) {
    $statusLabel.Text = "Ошибка. Подробности показаны в сообщении."
    Append-Log("Ошибка:`r`n$text")
    [System.Windows.Forms.MessageBox]::Show($text, "Ошибка расшифровки", "OK", "Error") | Out-Null
}

if ($SmokeTest) {
    $form = New-Object System.Windows.Forms.Form
    $form.Text = "Транскрибатор 9000"
    $form.Dispose()

    if (-not (Test-Path $PythonExe)) { throw "Python was not found: $PythonExe" }
    if (-not (Test-Path $CoreScript)) { throw "Core script was not found: $CoreScript" }

    Write-Output "GUI_SMOKE_TEST_OK"
    exit 0
}

[System.IO.Directory]::CreateDirectory($InputDir) | Out-Null
[System.IO.Directory]::CreateDirectory($OutputDir) | Out-Null

$form = New-Object System.Windows.Forms.Form
$form.Text = "Транскрибатор 9000"
$form.StartPosition = "CenterScreen"
$form.Size = New-Object System.Drawing.Size(950, 700)
$form.MinimumSize = New-Object System.Drawing.Size(880, 660)
$form.BackColor = [System.Drawing.Color]::FromArgb(245, 247, 251)

$titleLabel = New-Label "ТРАНСКРИБАТОР / 9000" 24 18 860 48 28 ([System.Drawing.FontStyle]::Bold)
$form.Controls.Add($titleLabel)

$subtitleLabel = New-Label "Локальная расшифровка аудио и видео без отправки во внешние сервисы" 26 66 860 24 10 ([System.Drawing.FontStyle]::Regular)
$subtitleLabel.ForeColor = [System.Drawing.Color]::FromArgb(91, 100, 117)
$form.Controls.Add($subtitleLabel)

$chooseButton = New-Object System.Windows.Forms.Button
$chooseButton.Text = "Выбрать аудио или видео"
$chooseButton.Location = New-Object System.Drawing.Point(26, 106)
$chooseButton.Size = New-Object System.Drawing.Size(220, 42)
$chooseButton.Font = New-Object System.Drawing.Font("Segoe UI", 11, [System.Drawing.FontStyle]::Bold)
$form.Controls.Add($chooseButton)

$fileLabel = New-Label "Файл не выбран" 264 108 640 40 10 ([System.Drawing.FontStyle]::Regular)
$form.Controls.Add($fileLabel)

$languageBox = New-Object System.Windows.Forms.GroupBox
$languageBox.Text = "Язык"
$languageBox.Location = New-Object System.Drawing.Point(26, 168)
$languageBox.Size = New-Object System.Drawing.Size(220, 178)
$languageBox.Font = New-Object System.Drawing.Font("Segoe UI", 10, [System.Drawing.FontStyle]::Bold)
$form.Controls.Add($languageBox)

$languageRu = New-Object System.Windows.Forms.RadioButton
$languageRu.Text = "русский"
$languageRu.Checked = $true
$languageRu.Location = New-Object System.Drawing.Point(16, 30)
$languageRu.Size = New-Object System.Drawing.Size(180, 24)
$languageRu.Font = New-Object System.Drawing.Font("Segoe UI", 10)
$languageBox.Controls.Add($languageRu)

$languageAuto = New-Object System.Windows.Forms.RadioButton
$languageAuto.Text = "определить автоматически"
$languageAuto.Location = New-Object System.Drawing.Point(16, 62)
$languageAuto.Size = New-Object System.Drawing.Size(190, 24)
$languageAuto.Font = New-Object System.Drawing.Font("Segoe UI", 10)
$languageBox.Controls.Add($languageAuto)

$qualityBox = New-Object System.Windows.Forms.GroupBox
$qualityBox.Text = "Качество"
$qualityBox.Location = New-Object System.Drawing.Point(272, 168)
$qualityBox.Size = New-Object System.Drawing.Size(330, 178)
$qualityBox.Font = New-Object System.Drawing.Font("Segoe UI", 10, [System.Drawing.FontStyle]::Bold)
$form.Controls.Add($qualityBox)

$qualityFast = New-Object System.Windows.Forms.RadioButton
$qualityFast.Text = "быстро (tiny)"
$qualityFast.Checked = $true
$qualityFast.Location = New-Object System.Drawing.Point(16, 28)
$qualityFast.Size = New-Object System.Drawing.Size(180, 22)
$qualityFast.Font = New-Object System.Drawing.Font("Segoe UI", 10)
$qualityBox.Controls.Add($qualityFast)

$qualityBalanced = New-Object System.Windows.Forms.RadioButton
$qualityBalanced.Text = "оптимально (base)"
$qualityBalanced.Location = New-Object System.Drawing.Point(16, 56)
$qualityBalanced.Size = New-Object System.Drawing.Size(180, 22)
$qualityBalanced.Font = New-Object System.Drawing.Font("Segoe UI", 10)
$qualityBox.Controls.Add($qualityBalanced)

$qualityBest = New-Object System.Windows.Forms.RadioButton
$qualityBest.Text = "высокое качество (small)"
$qualityBest.Location = New-Object System.Drawing.Point(16, 84)
$qualityBest.Size = New-Object System.Drawing.Size(290, 22)
$qualityBest.Font = New-Object System.Drawing.Font("Segoe UI", 10)
$qualityBox.Controls.Add($qualityBest)

$qualityPremium = New-Object System.Windows.Forms.RadioButton
$qualityPremium.Text = "премиум (medium, медленнее)"
$qualityPremium.Location = New-Object System.Drawing.Point(16, 112)
$qualityPremium.Size = New-Object System.Drawing.Size(290, 22)
$qualityPremium.Font = New-Object System.Drawing.Font("Segoe UI", 10)
$qualityBox.Controls.Add($qualityPremium)

$qualityMaximum = New-Object System.Windows.Forms.RadioButton
$qualityMaximum.Text = "максимум (large-v3, очень долго)"
$qualityMaximum.Location = New-Object System.Drawing.Point(16, 140)
$qualityMaximum.Size = New-Object System.Drawing.Size(300, 22)
$qualityMaximum.Font = New-Object System.Drawing.Font("Segoe UI", 10)
$qualityBox.Controls.Add($qualityMaximum)

$formatBox = New-Object System.Windows.Forms.GroupBox
$formatBox.Text = "Формат результата"
$formatBox.Location = New-Object System.Drawing.Point(628, 168)
$formatBox.Size = New-Object System.Drawing.Size(250, 178)
$formatBox.Font = New-Object System.Drawing.Font("Segoe UI", 10, [System.Drawing.FontStyle]::Bold)
$form.Controls.Add($formatBox)

$formatTxt = New-Object System.Windows.Forms.CheckBox
$formatTxt.Text = "TXT"
$formatTxt.Checked = $true
$formatTxt.Location = New-Object System.Drawing.Point(16, 32)
$formatTxt.Size = New-Object System.Drawing.Size(160, 24)
$formatTxt.Font = New-Object System.Drawing.Font("Segoe UI", 10)
$formatBox.Controls.Add($formatTxt)

$formatSrt = New-Object System.Windows.Forms.CheckBox
$formatSrt.Text = "SRT с таймкодами"
$formatSrt.Location = New-Object System.Drawing.Point(16, 64)
$formatSrt.Size = New-Object System.Drawing.Size(180, 24)
$formatSrt.Font = New-Object System.Drawing.Font("Segoe UI", 10)
$formatBox.Controls.Add($formatSrt)

$startButton = New-Object System.Windows.Forms.Button
$startButton.Text = "Запустить расшифровку"
$startButton.Location = New-Object System.Drawing.Point(26, 368)
$startButton.Size = New-Object System.Drawing.Size(852, 44)
$startButton.Font = New-Object System.Drawing.Font("Segoe UI", 12, [System.Drawing.FontStyle]::Bold)
$form.Controls.Add($startButton)

$statusLabel = New-Label "Готово. Выберите файл из папки input." 26 430 852 44 10 ([System.Drawing.FontStyle]::Regular)
$statusLabel.BackColor = [System.Drawing.Color]::FromArgb(238, 243, 255)
$statusLabel.Padding = New-Object System.Windows.Forms.Padding(10)
$form.Controls.Add($statusLabel)

$logBox = New-Object System.Windows.Forms.TextBox
$logBox.Multiline = $true
$logBox.ReadOnly = $true
$logBox.ScrollBars = "Vertical"
$logBox.Location = New-Object System.Drawing.Point(26, 490)
$logBox.Size = New-Object System.Drawing.Size(852, 94)
$logBox.Font = New-Object System.Drawing.Font("Segoe UI", 10)
$logBox.Text = "Здесь появятся сообщения о ходе обработки и список созданных файлов.`r`n"
$form.Controls.Add($logBox)

$openOutputButton = New-Object System.Windows.Forms.Button
$openOutputButton.Text = "Открыть папку с результатами"
$openOutputButton.Location = New-Object System.Drawing.Point(26, 604)
$openOutputButton.Size = New-Object System.Drawing.Size(852, 34)
$openOutputButton.Font = New-Object System.Drawing.Font("Segoe UI", 10)
$form.Controls.Add($openOutputButton)

$script:selectedFile = $null

$chooseButton.Add_Click({
    $dialog = New-Object System.Windows.Forms.OpenFileDialog
    $dialog.Title = "Выберите аудио или видео из папки input"
    $dialog.InitialDirectory = $InputDir
    $dialog.Filter = "Аудио и видео|*.mp3;*.wav;*.m4a;*.aac;*.ogg;*.flac;*.mp4;*.mov;*.mkv;*.avi;*.webm|Все файлы|*.*"
    if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
        if (-not (Is-InInput $dialog.FileName)) {
            [System.Windows.Forms.MessageBox]::Show("Выбран файл не из папки input.`r`n`r`nПоложите файл в папку:`r`n$InputDir", "Файл не из input", "OK", "Error") | Out-Null
            return
        }
        $script:selectedFile = $dialog.FileName
        $fileLabel.Text = $dialog.FileName
        $statusLabel.Text = "Файл выбран. Можно запускать расшифровку."
    }
})

$openOutputButton.Add_Click({
    [System.IO.Directory]::CreateDirectory($OutputDir) | Out-Null
    Start-Process -FilePath $OutputDir
})

$script:activeProcess = $null
$script:statusFile = $null
$script:resultJson = $null
$script:lastStatusLineCount = 0

function Read-NewStatusLines {
    if ([string]::IsNullOrWhiteSpace($script:statusFile) -or -not (Test-Path $script:statusFile)) {
        return
    }

    try {
        $lines = [System.IO.File]::ReadAllLines($script:statusFile, [System.Text.Encoding]::UTF8)
    }
    catch {
        return
    }
    for ($i = $script:lastStatusLineCount; $i -lt $lines.Count; $i++) {
        $line = $lines[$i]
        if ([string]::IsNullOrWhiteSpace($line)) {
            continue
        }
        $message = $line -replace "^STATUS:\s*", ""
        $statusLabel.Text = $message
        Append-Log $message
    }
    $script:lastStatusLineCount = $lines.Count
}

function Complete-ActiveProcess {
    $process = $script:activeProcess
    $exitCode = $process.ExitCode
    $process.Dispose()
    $script:activeProcess = $null
    $pollTimer.Stop()
    Set-UiBusy $false

    Read-NewStatusLines

    if (Test-Path $script:resultJson) {
        try {
            $result = Get-Content -LiteralPath $script:resultJson -Raw -Encoding UTF8 | ConvertFrom-Json
            if ($result.success) {
                $created = @($result.created_files)
                $message = "Расшифровка успешно завершена.`r`n`r`nСозданы файлы:`r`n" + ($created -join "`r`n")
                $statusLabel.Text = "Расшифровка успешно завершена."
                Append-Log $message
                [System.Windows.Forms.MessageBox]::Show($message, "Готово", "OK", "Information") | Out-Null
                return
            }

            $errorText = [string]$result.error
            if ([string]::IsNullOrWhiteSpace($errorText)) {
                $errorText = "Python завершился с кодом $exitCode."
            }
            Show-Error $errorText
            return
        }
        catch {
            Show-Error ("Не удалось прочитать результат обработки.`r`n`r`nПричина: " + $_.Exception.Message)
            return
        }
    }

    if ($exitCode -eq 0) {
        Show-Error "Обработка завершилась, но файл результата не найден. Попробуйте запустить расшифровку еще раз."
    }
    else {
        Show-Error "Python завершился с кодом $exitCode, но не записал подробности ошибки."
    }
}

$pollTimer = New-Object System.Windows.Forms.Timer
$pollTimer.Interval = 500
$pollTimer.Add_Tick({
    try {
        Read-NewStatusLines

        if ($script:activeProcess -and $script:activeProcess.HasExited) {
            Complete-ActiveProcess
        }
    }
    catch {
        $pollTimer.Stop()
        if ($script:activeProcess -and -not $script:activeProcess.HasExited) {
            try { $script:activeProcess.Kill() } catch {}
        }
        $script:activeProcess = $null
        Set-UiBusy $false
        Show-Error ("Не удалось обновить статус обработки.`r`n`r`nПричина: " + $_.Exception.Message)
    }
})

function Start-TranscriptionProcess($request) {
    [System.IO.Directory]::CreateDirectory($RunDir) | Out-Null
    $runId = (Get-Date -Format "yyyyMMdd-HHmmss") + "-" + ([Guid]::NewGuid().ToString("N").Substring(0, 8))
    $runPath = Join-Path $RunDir $runId
    [System.IO.Directory]::CreateDirectory($runPath) | Out-Null

    $script:statusFile = Join-Path $runPath "status.txt"
    $script:resultJson = Join-Path $runPath "result.json"
    $script:lastStatusLineCount = 0

    $argList = @(
        $CoreScript,
        "--transcribe-once", $request.Source,
        "--language", $request.Language,
        "--quality", $request.Quality,
        "--status-file", $script:statusFile,
        "--result-json", $script:resultJson,
        "--formats"
    ) + $request.Formats

    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $PythonExe
    $psi.WorkingDirectory = $AppDir
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $psi.EnvironmentVariables["PYTHONIOENCODING"] = "utf-8"
    $psi.Arguments = ($argList | ForEach-Object { Quote-Arg ([string]$_) }) -join " "

    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $psi
    [void]$process.Start()

    $script:activeProcess = $process
    Append-Log "Запускаю локальный Whisper."
    $statusLabel.Text = "Запускаю локальный Whisper."
    $pollTimer.Start()
}

$startButton.Add_Click({
    if ([string]::IsNullOrWhiteSpace($script:selectedFile)) {
        Show-Error "Файл не выбран.`r`n`r`nЧто сделать: нажмите «Выбрать аудио или видео» и выберите файл из папки input."
        return
    }

    $formats = @()
    if ($formatTxt.Checked) { $formats += "txt" }
    if ($formatSrt.Checked) { $formats += "srt" }
    if ($formats.Count -eq 0) {
        Show-Error "Не выбран формат результата.`r`n`r`nЧто сделать: отметьте TXT, SRT или оба формата."
        return
    }

    $language = if ($languageRu.Checked) { "ru" } else { "auto" }
    $quality = "fast"
    if ($qualityBalanced.Checked) { $quality = "balanced" }
    if ($qualityBest.Checked) { $quality = "best" }
    if ($qualityPremium.Checked) { $quality = "premium" }
    if ($qualityMaximum.Checked) { $quality = "maximum" }

    $statusLabel.Text = "Начинаю расшифровку."
    Append-Log ("Начинаю расшифровку файла:`r`n" + $script:selectedFile)
    Set-UiBusy $true

    try {
        Start-TranscriptionProcess ([PSCustomObject]@{
            Source = $script:selectedFile
            Language = $language
            Quality = $quality
            Formats = $formats
        })
    }
    catch {
        Set-UiBusy $false
        Show-Error ("Не удалось запустить обработку.`r`n`r`nПричина: " + $_.Exception.Message)
    }
})

[System.Windows.Forms.Application]::Run($form)
