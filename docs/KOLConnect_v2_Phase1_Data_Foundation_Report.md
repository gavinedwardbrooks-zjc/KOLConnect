# KOLConnect v2 Phase 1 Data Foundation Report

## 1. 实施范围

本阶段仅建立 Product-Campaign Excel 数据基础，没有修改 Web 页面、Chrome Extension、飞书同步、EXE 打包、Creator ID 或 account_uid。

## 2. Excel Schema

新增三个工作表：

- `Products`
- `Campaigns`
- `CampaignCreators`

Creator Library 打开旧工作簿时会检测缺失工作表并追加创建。旧 `Cooperations` 保留原字段和原有读写逻辑，不迁移、不删除。

工作簿 Schema 标识更新为：

```text
2.0-product-campaign-phase1
```

## 3. Repository

新增：

- `app/data_repository_base.py`：复用 CreatorRepository 的进程锁、旧工作簿检测、临时文件校验、备份和原子保存。
- `app/product_repository.py`：Product 创建、读取、更新和删除保护。
- `app/campaign_repository.py`：Campaign 创建、读取、更新和删除保护。
- `app/campaign_creator_repository.py`：CampaignCreator 创建、读取、更新、唯一性校验和删除。

`creator_repository.py` 只增加新 Sheet 注册和 Legacy Cooperations 说明，没有加入 Product/Campaign CRUD。

## 4. 数据约束

- Campaign 必须引用已存在的 Product。
- CampaignCreator 必须引用已存在的 Campaign、Creator 和 CreatorAccount。
- CreatorAccount 必须属于 CampaignCreator 指定的 Creator。
- 同一 Campaign 中同一 Creator 只能存在一条 CampaignCreator 记录。
- 不存在的外键不会被自动创建。
- Product 被 Campaign 使用时禁止删除。
- Campaign 已关联 Creator 时禁止删除。
- `id`、`creator_id`、`account_id` 和 `account_uid` 生成规则未修改。

## 5. 兼容性验证

自动化测试覆盖：

1. 空工作簿创建完整新 Schema。
2. 旧工作簿自动补充三个 Sheet。
3. 重复打开工作簿保持幂等。
4. Product CRUD。
5. Campaign CRUD。
6. CampaignCreator CRUD 与唯一性。
7. 无效 Product、Campaign、Creator、Account 外键拒绝。
8. 原有 Creator、CreatorAccount 和 Cooperations 数据不变化。

正式工作簿验证使用临时副本完成：

- 三个新 Sheet 创建成功。
- 除 `_Metadata` 的 Schema/更新时间外，全部原有业务 Sheet 单元格保持不变。
- 正式 `%APPDATA%\KOLConnect\Creator_Library.xlsx` 未被修改。

## 6. 测试结果

- 新增 Phase 1 测试：`8/8` 通过。
- Python 完整回归：`27/27` 通过。
- Python 语法检查：`14/14` 文件通过。
- `node --check webapp/app.js`：通过。
- Creator 详情/趋势前端回归：通过。
- 邮件安全渲染回归：通过。
- `git diff --check`：通过，仅有现有 Windows 行尾提示。

## 7. 未进入范围

- 未增加 Product/Campaign API。
- 未修改 Dashboard 或 Creator Library 页面。
- 未迁移 Cooperations。
- 未修改飞书四表或邮件逻辑。
- 未修改 Chrome Extension。
- 未构建 EXE。
- 未执行 git commit、push 或 tag。

## 8. 结论

Phase 1 Data Foundation 已完成。当前代码可以进入下一阶段 API 设计与实现，但在明确要求前不会自动接入 Web 页面或迁移 Legacy Cooperations。
