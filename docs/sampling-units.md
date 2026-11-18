# 采样单位约定（sample schema 2）

这里沿用 Linux 工具的二进制单位：**1 KB = 1024 B，1 MB = 1024 KB**。
`SamplingItem` 的字段值和 `sample.csv` 单位一致；表头明确标注单位。
`summary.txt` 的 config 中记录 `sampleSchema=2`、容量/带宽/bd 计数单位，便于区分旧数据。

| 字段 | 采样/CSV 单位 | 处理方式 |
|---|---|---|
| meminfo 容量、vmstat 内存容量、启动 totalPss | KB | 原始值已经是 KB，不再换算 |
| zramOrigDataSize / ComprDataSize / MemUsedTotal / MemUsedMax | KB | mm_stat 原始字节数 ÷ 1024 |
| zramBdCount / Reads / Writes | **4 KB 计数** | 保留 bd_stat 原始值，不除以 1024，也不乘以 4 |
| vmstatSi / So / Bi / Bo | **MB/s，浮点数** | 原始 KB/s ÷ 1024 |
| zramBdReadBw / WriteBw | **MB/s，浮点数** | 相邻 bd 计数增量 × 4 KB ÷ 实际时间间隔 ÷ 1024 |
| zswapPoolTotalSize | KB | pool_total_size 原始字节数 ÷ 1024 |
| zswapStoredPages / WrittenBackPages | 页数 | 保留原始计数；不是 KB |
| zswapStoredSize / WrittenBackSize | KB | CSV 补充容量列：页数 × pageSizeKb |
| zswapWriteBw | **MB/s，浮点数** | 相邻 written_back_pages 增量 × pageSizeKb ÷ 实际间隔 ÷ 1024 |
| zswapPoolLimitHit | 事件计数 | 不算入写回带宽 |
| psiSome / psiFull | 微秒 us | 保留内核原始累计时间；旧 CSV 的 ms 表头不正确 |
| 时间戳 / 温度 / CPU / 进程数 | ms / °C / % / 个 | 按各字段语义保留，不换算成容量 |

zswap 页大小通过 `getconf PAGESIZE` 采集（字节数转 KB），默认兼容值为 4 KB。
**bd_stat 的 4 KB 计数单位固定，不随内核页大小变化。**

## 例子

内核原始输出：

```text
bd_stat: 262112 95025 672844
```

新采样值保持一致：

```text
zramBdCount=262112, zramBdReads=95025, zramBdWrites=672844
```

当前后端占用 = `262112 × 4 KB = 1048448 KB = 1023.875 MB`。
Count 是当前占用，Reads/Writes 是累计流量，不能把 `Writes - Reads` 当作当前占用。

若两次采样相隔 3000 ms，累计写入增加 256 个单位：

```text
写回带宽 = 256 × 4 × 1000 ÷ 3000 ÷ 1024 = 0.333333... MB/s
```

带宽使用采样时间戳的**实际差值**，不使用名义采样周期；计算过程保留浮点小数。
首个样本没有运行前计数基线，累计计数类带宽输出 0；计数回退（reset）或时间戳
不递增的区间也输出 0，避免负数和除零。vmstat 带宽是工具自身计算的速率，不受此基线规则影响。

## 旧数据兼容性

本次只修改新采样和输出，**不会自动改写历史日志或 CSV**。

- 旧版 zramBd* 曾错误地把原始计数整数除以 1024，且表头未标单位。
  例如旧的 `255` 不是原始计数 255。原始值已被截断，不能精确逆推；
  若仅有旧采样值 n，原始计数只可确定在 `[n×1024, (n+1)×1024-1]` 区间。
  有原始 bd_stat 日志时，应以原始值重新解析。
- 若历史表头显示 `(KB)`，必须按该版本实际处理代码核对，不能套用新的 `(4KB)` 解释。
- 旧版 zswapPoolTotalSize 是 B；新表头明确标成 KB。
- 旧版 vmstat 带宽为 KB/s；新采样/CSV 为 MB/s。
- 旧版 zram 派生带宽还混用了计数单位和毫秒换算，不建议只把旧带宽列除以 1024。
  有原始累计计数和时间戳时，应重新计算。
- summary 的压缩容量展示仍使用其明确命名的 `*MiB` 字段；zswap 汇总计算已适配
  新的 KB 池容量，不会再次误除以 1024。summary schema 与 sample schema 是独立版本号。

## 单元测试

无需访问设备：

```bash
./gradlew :app:test \
  --tests com.junj.metrics.MetricsCollectorTest \
  --tests com.junj.output.csv.CsvWriterTest \
  --tests com.junj.output.reporting.SummaryReporterTest \
  --tests com.junj.output.reporting.RunHeaderTest
```
