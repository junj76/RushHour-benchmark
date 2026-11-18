# Windows 版 test.sh：与 main 的批量矩阵保持一致。
#
# 用法（在项目根目录）：
#   .\test.ps1                         # 全部矩阵（耗时会非常长）
#   .\test.ps1 -Workload 12 -Size 4096  # 只跑一个数量 + 一个容量
#   .\test.ps1 -SwapType 1              # 只跑指定 swap 类型
#
# 注意：-a/--apps 现在是"应用数量"（1..33），不再是 0/1/2 的应用组编号；
#       -f/--flash_size 是后端存储容量（MB），-w 是 zRAM 回写间隔，-m 是 zswap 池上限。

param(
    [ValidateRange(0, 5)][int[]] $SwapType = 0, 1, 2, 3, 4, 5,
    [int[]] $Workload = 12, 14, 16,
    [int[]] $Size = 1024, 4096,
    [int[]] $Interval = 10, 60,
    [int[]] $Pool = 5, 10,
    [switch] $SkipWarmup
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root
New-Item -ItemType Directory -Force -Path "logs" | Out-Null
$terminalLog = "logs/test_terminal_$(Get-Date -Format yyyyMMdd_HHmmss).log"
Start-Transcript -Path $terminalLog -ErrorAction SilentlyContinue | Out-Null
Write-Host "终端日志：$terminalLog" -ForegroundColor DarkGray

function Invoke-Config([string] $arguments) {
    Write-Host "`n运行配置：$arguments" -ForegroundColor Cyan
    & .\gradlew.bat --console=plain run --args="$arguments"
    $code = $LASTEXITCODE
    if ($code -ne 0) {
        Write-Host "[测试失败] exit=$code args=$arguments；继续下一组。" -ForegroundColor Red
    }
}

function Test-Has([int] $type) { return $SwapType -contains $type }

try {
    if (-not $SkipWarmup) {
        Invoke-Config "-t 0 -a 17 -p warmup"
    }

    foreach ($count in $Workload) {
        if (Test-Has 0) { Invoke-Config "-t 0 -a $count" }
        if (Test-Has 1) { Invoke-Config "-t 1 -a $count" }

        if (Test-Has 2) {
            foreach ($intervalSec in $Interval) {
                foreach ($sizeMb in $Size) {
                    Invoke-Config "-t 2 -a $count -f $sizeMb -w $intervalSec"
                }
            }
        }

        if (Test-Has 3) {
            foreach ($sizeMb in $Size) {
                Invoke-Config "-t 3 -a $count -f $sizeMb"
            }
        }

        if (Test-Has 4 -or Test-Has 5) {
            foreach ($poolPercent in $Pool) {
                foreach ($sizeMb in $Size) {
                    if (Test-Has 4) { Invoke-Config "-t 4 -a $count -f $sizeMb -m $poolPercent" }
                    if (Test-Has 5) { Invoke-Config "-t 5 -a $count -f $sizeMb -m $poolPercent" }
                }
            }
        }
    }
} finally {
    Stop-Transcript -ErrorAction SilentlyContinue | Out-Null
}

Write-Host "全部批次执行完毕，结果在 logs\ 下。" -ForegroundColor Green
