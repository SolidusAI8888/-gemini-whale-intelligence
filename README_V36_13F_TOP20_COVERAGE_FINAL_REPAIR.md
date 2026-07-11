# V36 — 13F Top20 Coverage + Amount Final Repair

本版本针对“四、机构巨鲸 13F 持仓雷达”做结构性修复。

## 核心修复

### 1. Top20 机构不再只是“最多20家”

13F 模块现在按默认 Top20 机构巨鲸名单作为固定目标。即使 GitHub Variables 里误设：

```text
INSTITUTIONAL_13F_MAX_MANAGERS=12
```

代码也会至少尝试默认 Top20 机构，除非用户自定义 watchlist 本身少于 20 家。

### 2. 新增 Top20 采集覆盖率表

“四、机构巨鲸 13F 持仓雷达”新增：

```text
13F Top20 机构采集覆盖率
```

报告会逐家显示：

- 序号
- 机构
- 代表人物
- CIK
- 状态
- 最新报告期
- 已入库期数
- 最新期行数
- 诊断

少于20家成功时，所有 13F Top5 表都会明确显示“不完整样本”。

### 3. 采集端逐家诊断

每次运行时，13F collector 会输出逐家日志，并把本轮采集状态传入报告。状态包括：

- 成功：两期可比
- 仅最新期
- 无13F
- 未找到InfoTable
- 索引读取失败/为空
- InfoTable读取失败
- 解析0行
- 采集失败

### 4. 13F 金额最终显示修复

报告层继续优先从 `raw_json.value_reported` 重新计算 SEC 13F 金额，并新增“隐含股价”兜底：

```text
如果 amount / shares 明显不合理，例如 > $10,000/股，
则判断为旧缓存 1000x 脏数据并自动除以1000。
```

因此类似：

```text
Appaloosa / GOOGL $497.04B
```

会显示为：

```text
$497.04M
```

## 覆盖文件

```text
app/collectors/sec_13f.py
app/reports/html_report.py
app/main.py
tests/test_report_quality.py
README_V36_13F_TOP20_COVERAGE_FINAL_REPAIR.md
```

## 验证

本地测试：

```text
25 passed
```

覆盖后手动 Run workflow 一次。查看报告中的：

```text
13F Top20 机构采集覆盖率
```

若不是 20/20，报告会明确列出缺失机构及诊断状态；13F Top5 表也会显示“不完整样本”。
