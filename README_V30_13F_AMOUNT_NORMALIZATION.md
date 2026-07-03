# V30 — SEC 13F Amount Normalization Repair

本版本专门修复机构巨鲸 SEC 13F 持仓金额仍然偏大 1000 倍的问题。

## 问题

V27/V28/V29 中，部分 13F 记录已经写入 GitHub Actions 持久化数据库缓存。由于项目使用 `source_id` 去重并执行 `INSERT OR IGNORE`，后续 collector 即使修正了解析逻辑，也不会覆盖旧的错误记录。

典型错误：

- `$497.04B` 应为 `$497.04M`
- `$2,154.93B` 应为 `$2.15B`

## 修复

1. `app/collectors/sec_13f.py`
   - 明确 SEC 13F information table 的 `<value>` 字段是“千美元”。
   - 只转换一次：`amount_usd = value * 1000`。
   - 删除旧版本中对 `> $500B` 的不稳定猜测逻辑。

2. `app/db.py`
   - `normalize_institutional_13f_amounts()` 改为从 `raw_json.value_reported` 和 `raw_json.value_unit` 重算历史缓存行。
   - 对没有 raw_json 的旧记录，使用保守 fallback：`INSTITUTIONAL_13F` 且单项持仓 `> $100B` 时除以 1000。
   - 解决 `$497.04B` 这类低于旧 `$500B` 阈值、但仍然错误的记录。

3. `tests/test_sec_13f_collector.py`
   - 新增测试，验证旧缓存 `$497.044B` 可修复为 `$497.044M`。

## 使用方式

覆盖本包后，手动 Run workflow 一次即可触发数据库修复。后续日报中的“四、机构巨鲸 13F 持仓雷达”金额应恢复到百万/十亿级别。

## 测试

```bash
pytest -q
```

本地结果：

```text
20 passed
```
