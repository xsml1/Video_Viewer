<#
    统一 Windows 控制台与其子进程的编码为 UTF-8，永久解决 PowerShell 中文乱码。

    背景：中文版 Windows 的控制台默认代码页是 936(GBK)，而现代命令行工具（Python、git、ffmpeg、
    node 等）默认按 UTF-8 输出；PowerShell 7 也按 UTF-8 解码。两边不一致时，中文就会在控制台、
    管道和重定向日志里变成 "��"、"锟斤拷" 之类的乱码。

    本脚本做三件事：
      1. 必要时把「当前用户」执行策略设为 RemoteSigned —— 执行策略为 Restricted 时，PowerShell
         会拒绝加载 profile.ps1，本项目自带的 .ps1 脚本也无法运行（本机原状就是 Restricted）。
      2. 写入两个 profile.ps1（Windows PowerShell 5.1 与 PowerShell 7 各自一个），把控制台输出代码页、
         $OutputEncoding、PYTHONIOENCODING 统一为 UTF-8，并让 5.1 的日志重定向写 UTF-8 而不是 UTF-16；
      3. 把 PYTHONIOENCODING=utf-8 写入用户环境变量，使 -NoProfile 或非 PowerShell 宿主启动的
         Python 也按 UTF-8 输出；
         最后启动两种 PowerShell 读回实际生效的编码设置，确认修复结果。

    有意不改动的内容：系统 ANSI 代码页（保持 936）、cmd.exe 的默认代码页。这样老的中文程序、
    GBK 编码的批处理仍按原样工作，避免为了修乱码而破坏其它软件。控制台「输入」代码页同样保持系统
    默认值：Windows PowerShell 5.1 自带的 PSReadLine 2.0 在 65001 输入代码页下有已知的中文/韩文
    输入缺陷（PowerShell/PSReadLine#1326），而中文乱码来自输出侧，改输出编码即可。

    可重复执行：内容相同时不重复写入；已有自定义 profile 时先备份再覆盖（本脚本自己生成的 profile 不算自定义）。
#>

[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

$profileBody = @'
# ---------------------------------------------------------------------------
# UTF-8 控制台设置（由 scripts/setup_powershell_utf8.ps1 生成，可重复生成）
# 作用：PowerShell 与命令行工具（Python/git/ffmpeg/node 等）统一按 UTF-8 交换中文，
#       避免控制台、管道与重定向日志出现乱码。
# 说明：只改输出编码，不改控制台输入代码页 —— Windows PowerShell 5.1 自带的
#       PSReadLine 2.0 在 65001 输入代码页下对中文/韩文输入有已知缺陷。
# ---------------------------------------------------------------------------
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)

# 控制台输出代码页 -> 65001：Python/git/ffmpeg 等按 UTF-8 输出的中文不再显示为乱码
try { [Console]::OutputEncoding = $utf8NoBom } catch { Write-Warning "设置输出编码失败: $($_.Exception.Message)" }
# PowerShell 通过管道送给原生程序（stdin）的编码
try { $global:OutputEncoding = $utf8NoBom } catch { Write-Warning "设置管道编码失败: $($_.Exception.Message)" }

# Python 输出到管道/重定向目标时也按 UTF-8 编码（控制台直连输出由 Python 自己正确写入）
$env:PYTHONIOENCODING = 'utf-8'

Remove-Variable -Name utf8NoBom -ErrorAction SilentlyContinue

# Windows PowerShell 5.1 的 > 与 Tee-Object 默认写 UTF-16，其它工具读取时会出现乱码；改为 UTF-8。
if ($PSVersionTable.PSVersion.Major -lt 6) {
    $PSDefaultParameterValues['Out-File:Encoding'] = 'utf8'
    $PSDefaultParameterValues['Tee-Object:Encoding'] = 'utf8'
}
'@

function Set-CurrentUserExecutionPolicy {
    # profile.ps1 与仓库内的 .ps1 都受执行策略约束：Restricted/AllSigned 下 5.1 不会加载 profile。
    # 这里直接读写「Windows PowerShell 当前用户」的注册表值（Set-ExecutionPolicy -Scope CurrentUser 写的就是它）：
    #   1. 5.1 与 PowerShell 7 的 CurrentUser 取值分属不同键，直接指定 5.1 的键才不受「脚本由哪个宿主启动」影响；
    #   2. Get-ExecutionPolicy 不带 -Scope 时会把 -ExecutionPolicy 临时指定的进程值算进去（脚本常用 Bypass 启动），
    #      直接读注册表才能看到真实持久化取值；
    #   3. 5.1 在 -ExecutionPolicy 临时启动时，Set-ExecutionPolicy 会在写入后补抛一次 Security error，易误报失败。
    # PowerShell 7 的缺省执行策略即 RemoteSigned，profile 已能正常加载，因此不额外改动它的设置。
    $machinePolicy = Get-ExecutionPolicy -Scope MachinePolicy
    $userPolicy = Get-ExecutionPolicy -Scope UserPolicy
    if ($machinePolicy -ne 'Undefined' -or $userPolicy -ne 'Undefined') {
        Write-Warning "执行策略由组策略控制（MachinePolicy=$machinePolicy, UserPolicy=$userPolicy），本脚本不再改动；profile 可能无法加载。"
        return
    }

    $key = 'HKCU:\Software\Microsoft\PowerShell\1\ShellIds\Microsoft.PowerShell'
    if (-not (Test-Path -LiteralPath $key)) {
        New-Item -Path $key -Force | Out-Null
    }
    $current = (Get-ItemProperty -LiteralPath $key -Name ExecutionPolicy -ErrorAction SilentlyContinue).ExecutionPolicy
    $currentLabel = if ($null -eq $current -or "$current" -eq '') { '未设置(即 Restricted)' } else { $current }

    if ($null -eq $current -or $current -in @('Restricted', 'AllSigned')) {
        Set-ItemProperty -LiteralPath $key -Name ExecutionPolicy -Value 'RemoteSigned'
        Write-Host "Windows PowerShell 5.1 执行策略已从 $currentLabel 改为 CurrentUser=RemoteSigned（本机脚本可运行，来自网络的脚本仍需签名）。"
    } else {
        Write-Host "Windows PowerShell 5.1 执行策略已为 $currentLabel，无需修改（profile 与本地 .ps1 可运行）。"
    }
}

function Clear-PowerShellConsoleCodePage {
    # HKCU:\Console 下的 CodePage 会同时影响输入与输出代码页，与上面 profile 的「只改输出」策略冲突，
    # 因此这里只做清理：早期版本的本脚本曾写入 65001，现在统一由 profile.ps1 负责输出编码。
    $keys = @(
        'HKCU:\Console\%SystemRoot%_System32_WindowsPowerShell_v1.0_powershell.exe',
        'HKCU:\Console\%SystemRoot%_SysWOW64_WindowsPowerShell_v1.0_powershell.exe'
    )

    foreach ($key in $keys) {
        if (-not (Test-Path -LiteralPath $key)) {
            continue
        }
        $current = (Get-ItemProperty -LiteralPath $key -Name CodePage -ErrorAction SilentlyContinue).CodePage
        if ($null -ne $current) {
            Remove-ItemProperty -LiteralPath $key -Name CodePage -ErrorAction Stop
            Write-Host "已移除控制台注册表代码页覆盖（改由 profile 设置输出编码）: $key"
        }
    }
}

function Write-Utf8BomFile {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][string]$Content
    )

    $directory = Split-Path -Parent $Path
    if (-not (Test-Path -LiteralPath $directory)) {
        New-Item -ItemType Directory -Path $directory -Force | Out-Null
    }

    if (Test-Path -LiteralPath $Path -PathType Leaf) {
        $existing = [System.IO.File]::ReadAllText($Path)
        if ($existing -eq $Content) {
            return 'unchanged'
        }
        # 本脚本自己生成的 profile 直接覆盖；用户自己写的 profile 先备份，避免误删用户配置。
        if ($existing -notmatch 'setup_powershell_utf8\.ps1') {
            $backup = "$Path.bak-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
            Copy-Item -LiteralPath $Path -Destination $backup -Force
            Write-Host "已备份原 profile: $backup"
        }
    }

    # 固定写 UTF-8 with BOM：Windows PowerShell 5.1 读到无 BOM 的中文脚本会按 ANSI 解析而乱码。
    [System.IO.File]::WriteAllText($Path, $Content, (New-Object System.Text.UTF8Encoding($true)))
    return 'written'
}

$documents = [Environment]::GetFolderPath('MyDocuments')
if ([string]::IsNullOrWhiteSpace($documents)) {
    $documents = Join-Path $HOME 'Documents'
}

$profileTargets = @(
    @{ Label = 'Windows PowerShell 5.1'; Path = Join-Path $documents 'WindowsPowerShell\profile.ps1' },
    @{ Label = 'PowerShell 7'; Path = Join-Path $documents 'PowerShell\profile.ps1' }
)

Set-CurrentUserExecutionPolicy

foreach ($target in $profileTargets) {
    $result = Write-Utf8BomFile -Path $target.Path -Content $profileBody
    $word = if ($result -eq 'written') { '已写入' } else { '已是最新' }
    Write-Host "$($target.Label) profile ${word}: $($target.Path)"
}

Clear-PowerShellConsoleCodePage

$env:PYTHONIOENCODING = 'utf-8'
[Environment]::SetEnvironmentVariable('PYTHONIOENCODING', 'utf-8', 'User')
Write-Host '用户环境变量 PYTHONIOENCODING=utf-8 已设置（影响之后新启动的进程）。'

# 通知正在运行的资源管理器刷新环境变量，使新启动的程序立即看到新值（失败不影响修复本身）。
try {
    Add-Type -Namespace Win32 -Name EnvironmentBroadcast -MemberDefinition @'
[DllImport("user32.dll", SetLastError = true, CharSet = CharSet.Auto)]
public static extern IntPtr SendMessageTimeout(IntPtr hWnd, uint Msg, UIntPtr wParam, string lParam, uint fuFlags, uint uTimeout, out UIntPtr lpdwResult);
'@ -ErrorAction Stop
    $broadcastResult = [UIntPtr]::Zero
    [Win32.EnvironmentBroadcast]::SendMessageTimeout([IntPtr]0xffff, 0x1A, [UIntPtr]::Zero, 'Environment', 2, 1000, [ref]$broadcastResult) | Out-Null
} catch {
    Write-Warning "刷新环境变量通知发送失败（不影响后续新开的终端）: $($_.Exception.Message)"
}

Write-Host ''
Write-Host '编码自检（新开进程读回实际生效值；OutputEncodingVar 应为 utf-8，代码页应为 65001）：'

# 去掉调用方可能继承来的 -ExecutionPolicy 偏好，让自检反映注册表里的真实策略与 profile 是否真的能加载。
Remove-Item Env:PSExecutionPolicyPreference -ErrorAction SilentlyContinue

# 只用单引号拼接输出，避免 5.1 向原生程序传参时内嵌双引号被破坏。
$probe = "chcp; 'ExecutionPolicy=' + (Get-ExecutionPolicy); 'OutputEncoding=' + [Console]::OutputEncoding.WebName; 'OutputEncodingVar=' + `$OutputEncoding.WebName; 'PYTHONIOENCODING=' + `$env:PYTHONIOENCODING"
$shells = @(
    @{ Label = 'Windows PowerShell 5.1'; Exe = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe' },
    @{ Label = 'PowerShell 7'; Exe = (Get-Command 'pwsh.exe' -ErrorAction SilentlyContinue | Select-Object -First 1).Source }
)

foreach ($shell in $shells) {
    if (-not $shell.Exe -or -not (Test-Path -LiteralPath $shell.Exe -PathType Leaf)) {
        Write-Host "$($shell.Label): 未找到可执行文件，已跳过。"
        continue
    }
    Write-Host "--- $($shell.Label) ($($shell.Exe)) ---"
    & $shell.Exe -NoLogo -Command $probe
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "$($shell.Label) 自检命令退出码 $LASTEXITCODE"
    }
}

Write-Host ''
Write-Host '完成。请新开一个 PowerShell 窗口（已开着的窗口不会自动生效）。'
