# KOLConnect v2 Phase 2 API Report

## 1. 实施范围

本阶段仅建立 Product-Campaign API 基础，并补齐 API 所依赖的数据校验与软归档能力。

未修改 Web UI、Chrome Extension、飞书同步、旧 Cooperations 数据、Creator ID、account_uid，也未构建 EXE、提交 Git 或推送远端。

## 2. 冻结规则

- CampaignCreator 唯一键：`campaign_id + creator_id`。
- `account_id`：本次 Campaign 的默认合作账号，必须存在且属于所选 Creator。
- ROI：保存为倍数，语义固定为 `revenue / cost`，例如 `2.5` 表示 2.5 倍。
- Campaign 状态：`draft`、`sourcing`、`running`、`completed`、`archived`。
- CampaignCreator 阶段：`pending_contact`、`contacted`、`quoted`、`negotiating`、`agreed`、`executing`、`completed`、`rejected`。
- Product、Campaign、CampaignCreator 不通过 API 物理删除。

## 3. API

### Product

- `GET /api/products`
- `POST /api/products`
- `GET /api/products/{product_id}`
- `PATCH /api/products/{product_id}`

归档请求：

```json
{
  "archived": true
}
```

默认列表不返回已归档 Product；可使用 `GET /api/products?include_archived=true` 查看。Product 仍有关联的未归档 Campaign 时拒绝归档。

### Campaign

- `GET /api/campaigns`
- `POST /api/campaigns`
- `GET /api/campaigns/{campaign_id}`
- `PATCH /api/campaigns/{campaign_id}`

列表支持：

- `product_id` 过滤。
- `status` 过滤。
- `include_archived=true` 包含归档 Campaign。

归档通过 `PATCH` 的 `{"archived": true}` 完成，持久化为 `status=archived`。

### CampaignCreator

- `GET /api/campaigns/{campaign_id}/creators`
- `POST /api/campaigns/{campaign_id}/creators`
- `PATCH /api/campaign-creators/{id}`

支持更新合作阶段、报价、默认合作账号、成本、发布链接、发布时间、播放、点赞、评论、ROI 和表现备注。默认列表不返回已归档关系；可使用 `include_archived=true` 查看。

## 4. 数据安全与归档

- 所有读写均通过 ProductRepository、CampaignRepository、CampaignCreatorRepository。
- Repository 继续复用 CreatorRepository 的全局工作簿锁、备份和原子保存。
- Windows 偶发临时文件占用时，原子替换执行三次短暂重试；重试失败仍返回原有友好错误，不覆盖旧工作簿。
- Product 与 CampaignCreator 使用新增 `archived_at` 字段保存软归档时间。
- Campaign 使用既有 `status=archived`。
- 原有 `deleteProduct()`、`deleteCampaign()`、`deleteCampaignCreator()` 名称仅为旧调用兼容，内部已经改为归档，不再删除工作表行。
- 工作簿 Schema 标识更新为 `2.0-product-campaign-phase2-api`；旧工作簿通过现有缺列追加机制补齐归档字段，既有数据行不变。
- Cooperations Sheet 及其代码未修改。

## 5. 错误规则

- 无效字段或枚举：HTTP 400。
- 外键对象不存在：HTTP 404。
- 重复添加达人、修改已归档对象、存在未归档子 Campaign 时归档 Product：HTTP 409。
- Excel 保存失败：HTTP 500，并返回现有友好提示。
- 请求路径中的 Campaign ID 与请求体不一致：HTTP 400。

## 6. 修改文件

- `app/server.py`
- `app/product_repository.py`
- `app/campaign_repository.py`
- `app/campaign_creator_repository.py`
- `app/creator_repository.py`
- `tests/test_v2_phase1_data_foundation.py`
- `tests/test_v2_phase2_api.py`
- `docs/KOLConnect_v2_Phase2_API_Report.md`

`app/data_repository_base.py` 为 Phase 1 已有的新数据层基础，本阶段继续复用，未绕过该层。

## 7. 测试结果

- Python 全部 `app/*.py` 逐文件语法检查：通过。
- `git diff --check`：通过。
- Phase 1 Product-Campaign 数据基础测试：8/8 通过。
- Phase 2 API 测试：5/5 通过。
- 全量 Python 回归：32/32 通过。

API 测试覆盖：

- Product 创建、读取、更新、归档。
- Campaign 创建、读取、更新、按 Product/状态过滤、归档。
- CampaignCreator 创建、读取、更新默认账号、阶段、报价和结果数据。
- Product、Campaign、Creator、CreatorAccount 外键错误。
- `campaign_id + creator_id` 重复添加拒绝。
- Campaign 状态和 CampaignCreator 阶段枚举校验。
- Product 归档保护。
- CampaignCreator 归档后 Excel 原始行仍存在。
- 旧 API 与原有 Python 回归保持通过。

## 8. 当前限制

- 当前 Schema 未保存 `revenue` 字段；API 中的 `roi` 必须由调用方按 `revenue / cost` 计算后传入，系统按“倍数”校验并保存。
- 本阶段没有页面入口，API 供后续 Phase 使用。
- 未增加取消归档操作；归档数据仅可通过 `include_archived=true` 查询。

## 9. 结论

Phase 2 API Foundation 已完成。新 API 使用现有 Repository 和 Excel 安全写入机制，旧 API 保持兼容，三类新实体均无物理删除入口，可以进入后续独立的 UI 接入阶段。
