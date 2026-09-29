(function createKOLConnectI18n(global) {
  "use strict";

  const DEFAULT_LOCALE = "zh";
  const dictionaries = { zh: Object.create(null), en: Object.create(null) };

  Object.assign(dictionaries.zh, {
    apiServerUnreachable: "无法连接 KOLConnect 服务，请确认程序正在运行。",
    apiServerError: "服务处理请求时发生错误，请稍后重试。",
    apiInvalidResponse: "服务返回了无法识别的响应，请稍后重试。",
    apiErrorReference: "错误参考：{trace_id}",
    mailGmailPasswordHint: "Gmail 通常需要应用专用密码；普通账号密码可能无法用于 IMAP/SMTP 登录。",
    mailGmailAuthRejected: "Gmail 拒绝当前登录凭据。KOLConnect 当前使用 IMAP/SMTP 密码登录；普通 Google 账号密码可能无法使用。如账号支持，请使用 Google 应用专用密码；OAuth2 暂不支持。",
    mailGmailAppPasswordMayBeRequired: "Gmail 可能要求应用专用密码。KOLConnect 当前使用 IMAP/SMTP 密码登录；如账号支持，请在密码/授权码字段填写 Google 应用专用密码。",
    mailGmailWebLoginRequired: "Gmail 要求先在网页中完成登录或安全验证。完成后请重试；普通账号密码可能仍无法用于 IMAP/SMTP 登录。",
    mailFollowupSummary: "当前显示 {visible} 个邮件跟进项，共 {total} 个已同步联系人组。",
    mailFollowupNoItems: "暂无符合条件的邮件跟进项。",
    mailFollowupWaitingMe: "待我回复",
    mailFollowupWaitingCreator: "待对方回复",
    mailFollowupWaitingUnknown: "状态未知",
    mailFollowupHistoryPartial: "部分历史",
    mailFollowupHistoryUnknown: "历史范围未知",
    mailFollowupHistorySynced: "已同步范围内",
    mailFollowupDays: "{days} 天",
    mailFollowupResume: "恢复跟进",
    mailFollowupSnooze: "稍后处理 ▼",
    mailFollowupTomorrow: "明天再处理",
    mailFollowupThreeDays: "3 天后再处理",
    mailFollowupChooseDate: "选择日期…",
    mailFollowupClearSnooze: "取消稍后处理",
    mailFollowupStop: "停止跟进",
    mailFollowupExportAdd: "加入导出队列",
    mailFollowupExportRemove: "移出导出队列",
    unnamedCreator: "未命名达人",
    settingsExchangeRateInvalid: "{currency} 汇率必须是大于 0 的数字。",
    settingsExchangeRateSaved: "汇率已保存，后续 USD 派生计算将使用新汇率。",
    googleSheetsSaved: "Google Sheets 配置已保存。",
    googleSheetsConnected: "Google OAuth 连接成功。",
    googleSheetsDisconnected: "Google OAuth 连接已断开。",
    googleSheetsSynced: "Google Sheets 数据同步完成：{count} 个工作表。",
    googleSheetsAuthRequired: "Google 授权已失效或尚未完成，请重新连接 Google 后再同步。",
    dashboardFixedFirst: "固定显示，固定在首位", dashboardMoveUp: "上移", dashboardMoveDown: "下移",
    dashboardNoTrend: "暂无趋势数据", dashboardMedianViews: "中位播放", dashboardFollowers: "粉丝",
    dashboardGrowth: "增长", dashboardDecline: "下降", dashboardUnspecifiedCurrency: "未标币种",
    creatorAnalysisTimeUnknown: "分析时间未知", creatorFreshnessFresh: "最新（{days} 天前）",
    creatorFreshnessUpdate: "建议更新（{days} 天前）", creatorFreshnessStale: "数据过期（{days} 天前）",
    creatorAccount: "账号", creatorUnknownPlatform: "未知平台", creatorFollowers: "粉丝 {count}",
    creatorAccountCount: "{count} 个", creatorDataLoading: "正在加载达人资料...",
    accountsTitle: "Chrome 账号", accountsSubtitle: "管理用于达人抓取的 Chrome Profile 配置；删除配置不会删除浏览器数据。", accountsConfigurationTitle: "Chrome Profile 配置", refreshProfiles: "刷新 Chrome 账号", addAccountConfiguration: "+ 添加账号配置", saveAccounts: "保存账号配置", accountsProfileLabel: "Chrome Profile", alias: "备注名", notes: "备注", accountsAutomationProfile: "KOLConnect 独立自动化 Profile", accountsAvailable: "可用", accountsUnavailable: "不可用", accountsCurrentDefaultProfile: "当前默认 Profile", accountsOpenBrowser: "打开浏览器", accountsRemoveConfiguration: "移除配置", accountsOpened: "已打开：{profile}{alias}", accountsRemoveConfirm: "删除 {profile} 的 KOLConnect 配置？不会删除 Chrome 浏览器资料。",
    productCount: "{count} 个产品", productEyebrow: "产品管理", productTitle: "产品", productSubtitle: "管理产品资料，并查看每个产品当前关联的 Campaign 数量。", productShowArchived: "显示已归档", productListTitle: "产品列表", productNameLabel: "产品名称", productCompanyNameLabel: "公司名称", productCampaignCountLabel: "Campaign 数量", productCreatedAtLabel: "创建时间", productUpdatedAtLabel: "更新时间", productStatusLabel: "状态", productNoteLabel: "备注", productNotePlaceholder: "记录产品定位、市场或合作注意事项", productLoading: "正在加载产品...", productRetry: "重新加载", productEmpty: "暂无产品。点击“创建产品”建立第一条产品记录。", productCreate: "创建产品", productEdit: "编辑产品", productSave: "保存产品",
    productSaving: "正在保存...", productRestore: "恢复", productArchive: "归档", productListLoadFailed: "产品列表加载失败，请稍后重试。",
    productNameRequired: "请输入产品名称。", productCompanyRequired: "请输入公司名称。", productCreated: "产品已创建。",
    productUpdated: "产品已更新。", productSaveFailed: "产品保存失败。", productArchiveConfirm: "归档后，该产品将从默认列表隐藏。已有 Campaign 和合作数据不会删除。",
    productRestoreConfirm: "恢复该产品？历史 Campaign 和合作数据将保持不变。", productArchived: "产品已归档。", productRestored: "产品已恢复。",
    agencyCount: "{count} 个 Agency", agencyEyebrow: "合作机构", agencyTitle: "Agency", agencySubtitle: "查看合作机构、联系人覆盖和已关联的达人资源。", agencyRefreshList: "刷新列表", agencyOverviewAria: "Agency 概览", agencyAssociatedCreators: "已关联达人", agencyContactsLabel: "联系人", agencyListTitle: "Agency 列表", agencyLoading: "正在加载 Agency...", agencyRetry: "重新加载", agencyEmpty: "暂无 Agency。可以在现有 Agency 数据入口建立第一条记录。", agencyCountryRegion: "国家/地区", agencyUpdatedAt: "更新时间", agencyContacts: "{count} 位联系人", agencyCreators: "{count} 位达人", agencyMore: "更多",
    agencyDelete: "删除 Agency", agencyListLoadFailed: "Agency 列表加载失败，请稍后重试。", agencyProfileSaved: "Agency 资料已保存。",
    agencyDeleteConfirm: "删除 Agency？\n删除后无法恢复。", agencyDeleted: "Agency 已删除。", agencyContactSaved: "联系人资料已保存。",
    agencyContactDeleted: "联系人已删除。", agencyUnlinked: "已解除达人与 Agency 的关联。", agencyViewCreator: "查看达人", agencyUnlink: "解除关联",
    campaignStatusDraft: "草稿", campaignStatusSourcing: "招募中", campaignStatusRunning: "进行中", campaignStatusCompleted: "已完成", campaignStatusArchived: "已归档", campaignEyebrow: "合作项目管理", campaignTitle: "Campaign", campaignSubtitle: "按产品和状态管理达人合作项目，集中查看预算、周期与执行负责人。", campaignProductLabel: "产品", campaignStatusLabel: "状态", campaignAllActiveStatuses: "全部进行中状态", campaignStartDateLabel: "开始日期", campaignEndDateLabel: "结束日期", campaignShowArchived: "显示已归档", campaignApplyFilters: "应用筛选", campaignListTitle: "Campaign 列表", campaignNameLabel: "Campaign 名称", campaignCreatorCountLabel: "达人数", campaignBusinessStatusLabel: "业务状态", campaignArchiveStatusLabel: "归档状态", campaignPlatformLabel: "平台", campaignBudgetLabel: "预算", campaignOwnerLabel: "负责人", campaignGoalLabel: "目标", campaignGoalPlaceholder: "记录本次 Campaign 的目标", campaignCountryEditNote: "国家/地区仅在创建时录入，本阶段编辑不修改该字段。", campaignLoading: "正在加载 Campaign...", campaignRetry: "重新加载", campaignEmpty: "当前筛选条件下暂无 Campaign。", campaignListCount: "{count} 个 Campaign", campaignArchived: "已归档", campaignActive: "进行中", campaignAnyPlatform: "不限平台", campaignView: "查看", campaignRestore: "恢复", campaignEdit: "编辑", campaignArchive: "归档", campaignAllProducts: "全部产品", campaignSelectProduct: "请选择产品", campaignUnnamedProduct: "未命名产品", campaignProductsLoadFailed: "产品选项加载失败，暂时无法创建或筛选 Campaign。", campaignListResponseInvalid: "Campaign 列表响应格式异常，请稍后重试。", campaignListLoadFailed: "Campaign 列表加载失败，请稍后重试。", campaignCreate: "创建 Campaign", campaignSaving: "正在保存...", campaignSave: "保存 Campaign", campaignNameRequired: "请输入 Campaign 名称。", campaignUpdated: "Campaign 已更新。", campaignCreated: "Campaign 已创建。", campaignSaveFailed: "Campaign 保存失败。", campaignArchiveConfirm: "归档后，该 Campaign 将从默认列表隐藏，已有达人合作数据不会删除。", campaignRestoreConfirm: "恢复后，该 Campaign 将重新显示，原有业务状态和达人合作数据保持不变。", campaignArchivedSaved: "Campaign 已归档。", campaignRestoredSaved: "Campaign 已恢复，业务状态未改变。",
    creatorStatusDiscovered: "已发现", creatorStatusContacted: "已联系", creatorStatusNegotiating: "洽谈中", creatorStatusCooperating: "合作中", creatorStatusCompleted: "已完成", creatorStatusRejected: "已拒绝",
    creatorLibraryConfirmAdd: "确认加入", creatorLibraryLoading: "正在加载...", creatorLibraryJoining: "正在加入...", creatorLibraryUnnamedAccount: "未命名账号", creatorLibraryUnspecifiedPlatform: "未标注平台", creatorLibraryCampaignPlatformMatch: "（匹配 Campaign 平台）",
    creatorLibraryChooseAccount: "请选择执行账号", creatorLibraryNoAccounts: "暂无可用账号", creatorLibraryNoAccountsHint: "该达人暂无可用社交账号，请先完善达人账号信息。", creatorLibraryOneAccountHint: "已自动选择该达人的唯一社交账号。", creatorLibraryMatchingAccountHint: "已优先排列与 {platform} 匹配的账号，请人工确认执行账号。", creatorLibraryMultipleAccountsHint: "该达人有多个账号，请人工选择本次合作的执行账号。",
    creatorLibraryChooseCampaign: "请选择 Campaign", creatorLibraryNoCampaigns: "暂无可用 Campaign", creatorLibraryNoCampaignsMessage: "当前没有可加入的 Campaign。", creatorLibraryMissingCreator: "缺少 Creator ID，无法加入 Campaign。", creatorLibraryCampaignModalMissing: "加入 Campaign 窗口未加载。", creatorLibraryLoadCampaignFailed: "无法加载 Campaign 或达人账号。", creatorLibraryCampaignSelectedRequired: "请选择 Campaign。", creatorLibraryAccountSelectedRequired: "请选择本次合作的执行账号。", creatorLibraryCampaignAdded: "{creator} 已加入 Campaign。", creatorLibraryCampaignAlreadyAdded: "该达人已经加入此 Campaign。", creatorLibraryCampaignAddFailed: "加入 Campaign 失败。",
    creatorDeleteCreators: "达人主记录", creatorDeleteAccounts: "账号", creatorDeleteVideos: "视频", creatorDeleteCampaignRelations: "Campaign 关系", creatorDeleteFollowUpLogs: "跟进记录", creatorDeleteTaskArtifacts: "任务文件", creatorDeleteProtectionRecords: "数据保护记录", creatorDeleteLegacySources: "Legacy 记录", creatorDeleteCooperations: "历史合作", creatorDeleteEmbeddedReferences: "嵌入式 Analysis 引用", creatorDeleteUnmappedArtifacts: "未解析任务文件", creatorDeleteSubmitting: "正在永久删除...", creatorDeleteConfirm: "确认永久删除", creatorDeleteUnknownBlocker: "存在无法安全处理的关联数据。", creatorDeleteReady: "影响检查已通过，可以继续确认。", creatorDeleteBlocked: "当前无法永久删除。请先处理下列阻止项。", creatorDeleteChecking: "正在检查永久删除影响...", creatorDeleteLoadFailed: "无法读取永久删除影响。", creatorDeleteMissingCreator: "缺少 Creator ID，无法检查永久删除影响。", creatorDeleteModalMissing: "永久删除确认窗口未加载。", creatorDeleteSuccess: "达人已永久删除。", creatorDeleteStale: "相关数据已发生变化，请重新确认删除影响。", creatorDeleteNewBlocker: "当前出现新的安全阻止项，已刷新删除影响。", creatorDeleteStorageLocked: "当前数据正在被其他操作修改，请稍后重新检查影响。", creatorDeleteNotFound: "达人已不存在，列表已刷新。", creatorDeleteFailed: "永久删除失败，数据已保持或恢复到安全状态。请稍后重试。",
    creatorImportMissingRequired: "必填字段缺失", creatorImportInvalidPlatform: "平台无效", creatorImportInvalidProfileUrl: "主页链接无效", creatorImportDuplicateInFile: "文件内存在重复达人", creatorImportUnknownAgency: "Agency 不存在", creatorImportNoHistory: "暂无历史数据", creatorTrendGrowth: "↑ 增长 {amount}", creatorTrendDecline: "↓ 下降 {amount}", creatorTrendNoChange: "— 无变化",
    creatorLibraryPageSummary: "第 {start}-{end} 条，共 {total} 位达人", creatorLibraryPrevious: "上一页", creatorLibraryNext: "下一页", creatorLibrarySelectedCount: "已选 {count} 人", creatorLibraryExportSelectedCount: "导出选中达人（{count}）", creatorLibraryExportSelected: "导出选中达人", creatorLibraryCampaignSelectedCount: "加入 Campaign（{count}）", creatorLibrarySelectCreator: "选择达人", creatorLibraryInsufficientData: "⚠ 数据不足", creatorLibraryCountry: "国家", creatorLibraryLanguage: "语言", creatorLibraryCategory: "分类", creatorLibraryEmail: "邮箱", creatorLibraryFollowers: "粉丝", creatorLibraryAverageViews: "平均播放", creatorLibraryViewCreator: "查看达人", creatorLibraryRestoreCreator: "恢复达人", creatorLibraryMore: "更多 ▼", creatorLibraryArchiveCreator: "归档达人", creatorLibraryMergeCreator: "合并达人", creatorLibraryDeleteCreator: "永久删除", creatorLibraryArchived: "已归档", creatorLibraryViewAnalysis: "查看分析", creatorLibraryRestore: "恢复", creatorLibraryCreateTask: "创建合作任务", creatorLibraryArchive: "归档",
    creatorLibraryAllContentCategories: "全部内容类型", creatorLibraryAllCountries: "全部国家/地区", creatorLibraryAllLanguages: "全部语言", creatorLibraryAllTags: "全部标签", creatorLibraryAllAiTags: "全部 AI Tags", creatorLibraryAllAgencies: "全部 Agency", creatorLibraryFileSaveFailed: "文件保存失败，请稍后重试。", creatorLibraryDownloadFailed: "下载失败，请稍后重试。", creatorLibraryTemplateSaved: "模板已保存到：{path}", creatorLibraryExportSaved: "已保存到：{path}", creatorLibraryExportFailed: "导出失败，请刷新达人库后重试。", creatorLibraryExported: "已导出 {count} 位达人。", creatorLibraryBatchSelected: "已选择 {count} 位达人", creatorLibraryBatchAdded: "成功加入 {count}", creatorLibraryBatchRestored: "恢复 {count}", creatorLibraryBatchPresent: "已存在 {count}", creatorLibraryBatchFailed: "失败 {count}", creatorLibraryUnknownCreator: "未知达人", creatorLibraryAddFailed: "加入失败", creatorLibraryBatchAddFailed: "批量加入 Campaign 失败。", creatorLibraryImportComplete: "导入完成：新增 {created}，跳过已有 {skipped}。", creatorLibraryImportNotRun: "导入未执行：共 {total} 行，无效 {invalid} 行。", creatorLibraryInvalidData: "数据无效", creatorLibraryImportRow: "第 {row} 行：{label}{field}", creatorLibraryExcelImported: "Creator Excel 导入完成。", creatorLibraryTaskMissing: "未找到关联的审核任务。", creatorLibraryTaskOpened: "已打开关联的审核任务。", creatorLibraryArchiveConfirm: "归档后，达人将从默认列表隐藏，历史分析和 Campaign 关联会保留。", creatorLibraryRestoreConfirm: "恢复该达人到默认达人库？", creatorLibraryArchivedSaved: "达人已归档。", creatorLibraryRestoredSaved: "达人已恢复。", creatorLibraryMergeUnavailable: "达人合并功能未加载，请刷新页面后重试。", creatorLibraryStatusSaved: "达人状态已保存。", creatorLibraryMoreFiltersClose: "收起更多筛选", creatorLibraryMoreFiltersOpen: "更多筛选",
  });
  Object.assign(dictionaries.zh, {
    campaignDetailTitle: "Campaign 详情", campaignDetailSubtitle: "Campaign 执行与合作记录", campaignDetailProductSubtitle: "{product} · Campaign 执行与合作记录", campaignDetailProduct: "产品", campaignDetailCountry: "国家/地区", campaignDetailPlatform: "平台", campaignDetailStartDate: "开始日期", campaignDetailEndDate: "结束日期", campaignDetailBudget: "预算", campaignDetailOwner: "负责人", campaignDetailCreatedAt: "创建时间", campaignDetailViewPublication: "查看发布内容", campaignDetailPublicationNumber: "发布内容 {number}", campaignDetailCreatorCount: "{count} 位达人", campaignDetailViewAccount: "查看账号", campaignDetailRemove: "移除", campaignDetailDueToday: "今天要处理", campaignDetailDueSoon: "即将到期", campaignDetailOverdue: "已超时", campaignDetailWaitingCreator: "等待达人", campaignDetailWaitingInternal: "等待内部", campaignDetailWaitingClient: "等待客户", campaignDetailWaitingSelf: "本人决策", campaignDetailNone: "无", campaignDetailNeedsDecision: "需要决策", campaignDetailStalled: "已卡住", campaignDetailNormal: "正常",
    campaignDetailStagePendingContact: "待联系", campaignDetailStageContacted: "已联系", campaignDetailStageQuoted: "已报价", campaignDetailStageNegotiating: "谈判中", campaignDetailStageAgreed: "已确认", campaignDetailStageExecuting: "执行中", campaignDetailStageCompleted: "已完成", campaignDetailStageRejected: "已拒绝",
    campaignDetailPendingHumanReview: "待人工审核", campaignDetailAiReviewUnavailable: "AI 一审：未配置（不影响人工审核）", campaignDetailRulesFirstPass: "规则一审", campaignDetailReviewApproved: "通过", campaignDetailReviewChangesRequested: "要求修改", campaignDetailReviewRejected: "拒绝", campaignDetailFirstPassFindings: "规则一审发现 {count} 项，人工审核状态未改变。", campaignDetailFirstPassClear: "规则一审未发现 Brief 明确规则冲突，仍需人工审核。", campaignDetailBriefSaved: "Campaign Brief 已保存。",
    campaignDetailRecordCount: "{count} 条", campaignDetailMissingPublishUnavailable: "缺失发布信息暂不可用，请稍后重试。", campaignDetailNoMissingPublish: "暂无缺失发布信息。", campaignDetailCoverage: "{valid} / {total} 条有数据", campaignDetailTopCreator: "最佳达人", campaignDetailTopVideo: "最佳视频", campaignDetailHighestEngagement: "最高互动率", campaignDetailTotalViews: "累计播放 {count}", campaignDetailPublicationViews: "{publication} · 播放 {count}", campaignDetailNoViews: "暂无可用播放数据", campaignDetailNoEngagement: "暂无可用互动率", campaignDetailFastestGrowth: "最快增长（播放/天）", campaignDetailGrowthPeriod: "{rate} / 天 · {start} 至 {end}", campaignDetailNeedTwoObservations: "至少需要两个不同时间的播放观察", campaignDetailMoneySummary: "确认成本：{cost} · 历史报价：{quote} · 未知币种成本/报价记录 {unknownCost}/{unknownQuote}（不纳入币种汇总） · ROI：—（缺少权威回报数据）", campaignDetailAccountUnrecorded: "账号未记录", campaignDetailObservedAt: "观察时间", campaignDetailViews: "播放", campaignDetailLikes: "点赞", campaignDetailComments: "评论", campaignDetailShares: "分享", campaignDetailEngagementRate: "互动率", campaignDetailEngagementRatePoints: "ER（百分点）", campaignDetailGrowthUnavailable: "{label}增长 —", campaignDetailPercentageUnavailable: "百分比不可用", campaignDetailGrowthValue: "{label}增长 {value} ({percentage}) · {start} 至 {end}{decrease}", campaignDetailObservationDecreased: " · 观察值下降", campaignDetailLastChecked: "最近检查 {observedAt}", campaignDetailNotChecked: "尚未检查", campaignDetailRefresh: "刷新", campaignDetailObservationSource: "来源 {source} · 置信度 {confidence}", campaignDetailTrackingUnavailable: "追踪状态：Unavailable", campaignDetailPublicationRefreshed: "发布内容指标已刷新。", campaignDetailRefreshUnavailable: "暂不可刷新：{reason}", campaignDetailRefreshFailed: "刷新失败。", campaignDetailAllPublicationsRefreshed: "全部发布内容指标已刷新。", campaignDetailBatchRefreshResult: "批量刷新 {status}：成功 {succeeded}，未完成 {failed}。", campaignDetailBatchRefreshFailed: "批量刷新失败。",
    campaignDetailCampaignMissing: "Campaign 数据不存在。", campaignDetailNotFound: "Campaign 不存在或已删除。", campaignDetailLoadFailed: "Campaign 详情加载失败，请稍后重试。", campaignDetailSelectCreator: "请选择达人", campaignDetailLoadingCreators: "正在加载达人...", campaignDetailCreatorListLoadFailed: "达人列表加载失败", campaignDetailCreatorListLoadFailedRetry: "达人列表加载失败，请稍后重试。", campaignDetailSelectedAccount: "已选择：{account}", campaignDetailSelectedAccounts: "已选择 {count} 个账号", campaignDetailSelectPlannedAccount: "请选择计划发布账号", campaignDetailNoEligibleAccounts: "该达人暂无符合平台的账号", campaignDetailLoadingAccounts: "正在加载账号...", campaignDetailAccountLoadFailed: "达人账号加载失败，请稍后重试。", campaignDetailAddCreator: "添加达人", campaignDetailCostCurrencyDefault: "默认同报价币种", campaignDetailSelectCurrency: "请选择币种", campaignDetailRateUnset: "尚未设置 {currency} 汇率", campaignDetailSetCurrencyRate: "设置 {currency} 汇率", campaignDetailSetRate: "设置汇率", campaignDetailRateInvalid: "请输入大于 0 的汇率。", campaignDetailActualAccountUnknown: "实际账号未知", campaignDetailRecordedAt: "记录于 {observedAt}", campaignDetailObservationAtSave: "保存时记录观察时间", campaignDetailEditRelation: "编辑合作记录 · {creator}", campaignDetailCreator: "达人", campaignDetailSaveRelation: "保存合作记录", campaignDetailExecutionAccountRequired: "请选择本次合作使用的执行账号。", campaignDetailCreatorRequired: "请选择要加入 Campaign 的达人。", campaignDetailRelationUpdated: "达人合作记录已更新。", campaignDetailCreatorAdded: "达人已加入 Campaign。", campaignDetailRelationSaveFailed: "合作记录保存失败。", campaignDetailRemoveCreatorConfirm: "确认从 Campaign 移除“{creator}”？达人资料和其他 Campaign 关系将保留。", campaignDetailCreatorRemoved: "达人已从 Campaign 移除，达人资料保持不变。", campaignDetailDeleteConfirm: "删除 Campaign 后，该 Campaign 与达人关系会被删除，但达人资料不会删除。", campaignDetailDeleted: "Campaign 已删除，达人资料保持不变。", campaignDetailGoogleSheetsSync: "同步报告到 Google Sheets", campaignDetailGoogleSheetsPartial: "Google Sheets 报告仅部分写入，请检查各工作表状态后重试。", campaignDetailGoogleSheetsFailed: "Google Sheets 报告同步失败：{reason}", campaignDetailWorksheetRows: "{worksheet}: {count} 行", campaignDetailGoogleSheetsSynced: "Google Sheets 报告同步成功。{detail}", campaignDetailMissingId: "缺少 Campaign ID，请返回列表重新进入。",
  });

  Object.assign(dictionaries.en, {
    apiServerUnreachable: "Cannot connect to KOLConnect. Confirm the application is running.",
    apiServerError: "The service could not process this request. Please try again later.",
    apiInvalidResponse: "The service returned an unrecognized response. Please try again later.",
    apiErrorReference: "Error reference: {trace_id}",
    mailGmailPasswordHint: "Gmail commonly requires an App Password; a normal account password may not work for IMAP/SMTP.",
    mailGmailAuthRejected: "Gmail rejected the current credentials. KOLConnect currently uses IMAP/SMTP password login; a normal Google account password may not work. If the account supports it, use a Google App Password. OAuth2 is not supported yet.",
    mailGmailAppPasswordMayBeRequired: "Gmail may require an App Password. KOLConnect currently uses IMAP/SMTP password login; if the account supports it, enter a Google App Password in the password/App Password field.",
    mailGmailWebLoginRequired: "Gmail requires a web login or security check first. Complete it and try again; a normal account password may still not work for IMAP/SMTP.",
    campaignDetailTitle: "Campaign details", campaignDetailSubtitle: "Campaign execution and partnership records", campaignDetailProductSubtitle: "{product} · Campaign execution and partnership records", campaignDetailProduct: "Product", campaignDetailCountry: "Country/region", campaignDetailPlatform: "Platform", campaignDetailStartDate: "Start date", campaignDetailEndDate: "End date", campaignDetailBudget: "Budget", campaignDetailOwner: "Owner", campaignDetailCreatedAt: "Created", campaignDetailViewPublication: "View publication", campaignDetailPublicationNumber: "Publication {number}", campaignDetailCreatorCount: "{count} creators", campaignDetailViewAccount: "View account", campaignDetailRemove: "Remove", campaignDetailDueToday: "Due today", campaignDetailDueSoon: "Due soon", campaignDetailOverdue: "Overdue", campaignDetailWaitingCreator: "Waiting for creator", campaignDetailWaitingInternal: "Waiting internally", campaignDetailWaitingClient: "Waiting for client", campaignDetailWaitingSelf: "My decision", campaignDetailNone: "None", campaignDetailNeedsDecision: "Decision needed", campaignDetailStalled: "Stalled", campaignDetailNormal: "Normal",
    campaignDetailStagePendingContact: "Pending contact", campaignDetailStageContacted: "Contacted", campaignDetailStageQuoted: "Quoted", campaignDetailStageNegotiating: "Negotiating", campaignDetailStageAgreed: "Agreed", campaignDetailStageExecuting: "Executing", campaignDetailStageCompleted: "Completed", campaignDetailStageRejected: "Rejected",
    campaignDetailPendingHumanReview: "Pending human review", campaignDetailAiReviewUnavailable: "AI first pass is unavailable; human review is unaffected.", campaignDetailRulesFirstPass: "Rules first pass", campaignDetailReviewApproved: "Approve", campaignDetailReviewChangesRequested: "Request changes", campaignDetailReviewRejected: "Reject", campaignDetailFirstPassFindings: "Rules first pass found {count} items; the human-review status is unchanged.", campaignDetailFirstPassClear: "Rules first pass found no explicit Brief conflicts; human review is still required.", campaignDetailBriefSaved: "Campaign Brief saved.",
    campaignDetailRecordCount: "{count} records", campaignDetailMissingPublishUnavailable: "Missing publication information is temporarily unavailable. Try again later.", campaignDetailNoMissingPublish: "No missing publication information.", campaignDetailCoverage: "{valid} / {total} with data", campaignDetailTopCreator: "Top creator", campaignDetailTopVideo: "Top video", campaignDetailHighestEngagement: "Highest engagement rate", campaignDetailTotalViews: "Total views {count}", campaignDetailPublicationViews: "{publication} · {count} views", campaignDetailNoViews: "No usable view data", campaignDetailNoEngagement: "No usable engagement data", campaignDetailFastestGrowth: "Fastest growth (views/day)", campaignDetailGrowthPeriod: "{rate} / day · {start} to {end}", campaignDetailNeedTwoObservations: "At least two view observations at different times are required", campaignDetailMoneySummary: "Confirmed cost: {cost} · Historical quote: {quote} · Unknown-currency cost/quote records {unknownCost}/{unknownQuote} (excluded from currency totals) · ROI: — (no authoritative return data)", campaignDetailAccountUnrecorded: "Account not recorded", campaignDetailObservedAt: "Observed at", campaignDetailViews: "Views", campaignDetailLikes: "Likes", campaignDetailComments: "Comments", campaignDetailShares: "Shares", campaignDetailEngagementRate: "Engagement rate", campaignDetailEngagementRatePoints: "ER (percentage points)", campaignDetailGrowthUnavailable: "{label} growth —", campaignDetailPercentageUnavailable: "Percentage unavailable", campaignDetailGrowthValue: "{label} growth {value} ({percentage}) · {start} to {end}{decrease}", campaignDetailObservationDecreased: " · observation decreased", campaignDetailLastChecked: "Last checked {observedAt}", campaignDetailNotChecked: "Not checked", campaignDetailRefresh: "Refresh", campaignDetailObservationSource: "Source {source} · confidence {confidence}", campaignDetailTrackingUnavailable: "Tracking status: unavailable", campaignDetailPublicationRefreshed: "Publication metrics refreshed.", campaignDetailRefreshUnavailable: "Cannot refresh yet: {reason}", campaignDetailRefreshFailed: "Refresh failed.", campaignDetailAllPublicationsRefreshed: "All publication metrics refreshed.", campaignDetailBatchRefreshResult: "Batch refresh {status}: {succeeded} succeeded, {failed} incomplete.", campaignDetailBatchRefreshFailed: "Batch refresh failed.",
    campaignDetailCampaignMissing: "Campaign data is unavailable.", campaignDetailNotFound: "Campaign does not exist or was deleted.", campaignDetailLoadFailed: "Campaign details could not be loaded. Try again later.", campaignDetailSelectCreator: "Select a creator", campaignDetailLoadingCreators: "Loading creators...", campaignDetailCreatorListLoadFailed: "Creator list failed to load", campaignDetailCreatorListLoadFailedRetry: "Creator list could not be loaded. Try again later.", campaignDetailSelectedAccount: "Selected: {account}", campaignDetailSelectedAccounts: "{count} accounts selected", campaignDetailSelectPlannedAccount: "Select planned publishing accounts", campaignDetailNoEligibleAccounts: "This creator has no accounts matching the Campaign platform", campaignDetailLoadingAccounts: "Loading accounts...", campaignDetailAccountLoadFailed: "Creator accounts could not be loaded. Try again later.", campaignDetailAddCreator: "Add creator", campaignDetailCostCurrencyDefault: "Same as quote currency by default", campaignDetailSelectCurrency: "Select currency", campaignDetailRateUnset: "No {currency} exchange rate is set", campaignDetailSetCurrencyRate: "Set {currency} exchange rate", campaignDetailSetRate: "Set exchange rate", campaignDetailRateInvalid: "Enter an exchange rate greater than 0.", campaignDetailActualAccountUnknown: "Actual account unknown", campaignDetailRecordedAt: "Recorded at {observedAt}", campaignDetailObservationAtSave: "Observation time is recorded when saved", campaignDetailEditRelation: "Edit partnership record · {creator}", campaignDetailCreator: "Creator", campaignDetailSaveRelation: "Save partnership record", campaignDetailExecutionAccountRequired: "Select execution accounts for this partnership.", campaignDetailCreatorRequired: "Select a creator to add to the Campaign.", campaignDetailRelationUpdated: "Creator partnership record updated.", campaignDetailCreatorAdded: "Creator added to Campaign.", campaignDetailRelationSaveFailed: "Partnership record could not be saved.", campaignDetailRemoveCreatorConfirm: "Remove “{creator}” from this Campaign? Creator data and relationships in other Campaigns will be retained.", campaignDetailCreatorRemoved: "Creator removed from Campaign. Creator data is unchanged.", campaignDetailDeleteConfirm: "Deleting this Campaign removes its creator relationships but does not delete creator data.", campaignDetailDeleted: "Campaign deleted. Creator data is unchanged.", campaignDetailGoogleSheetsSync: "Sync report to Google Sheets", campaignDetailGoogleSheetsPartial: "The Google Sheets report was only partially written. Check each worksheet and try again.", campaignDetailGoogleSheetsFailed: "Google Sheets report sync failed: {reason}", campaignDetailWorksheetRows: "{worksheet}: {count} rows", campaignDetailGoogleSheetsSynced: "Google Sheets report synced successfully. {detail}", campaignDetailMissingId: "Campaign ID is missing. Return to the list and open it again.",
  });

  Object.assign(dictionaries.zh, {
    settingsAvailable: "可用", settingsUnavailable: "不可用", settingsNeedsAttention: "需处理", settingsConfigurationError: "配置异常", settingsCreated: "已创建", settingsMigrationError: "迁移错误", settingsUnsupportedSchema: "不支持的 Schema",
    settingsFeishuSchemaNeedsReview: "飞书表结构需要补充", settingsFeishuMissingFields: "{table} 缺少：", settingsFeishuIncompatibleFields: "{table} 字段类型不兼容：", settingsFeishuCurrentType: "{field}（当前类型：{type}）",
    settingsFeishuSyncComplete: "同步完成：达人新增 {creatorCreated}、更新 {creatorUpdated}；账号新增 {accountCreated}、更新 {accountUpdated}；关系更新 {relationUpdated}。", settingsFeishuValidationPassed: "连接与字段合同验证通过。", settingsFeishuDryRunComplete: "预检查完成，未写入飞书。", settingsFeishuSyncPartial: "同步部分完成，失败记录 {count} 条；后续批次已停止，可修复后重新同步。", settingsFeishuSyncConfirm: "KOLConnect / Excel 将保持为权威数据源。同步可能在飞书创建缺失记录并更新精确匹配记录；M7.1 不会删除任何飞书记录。确认继续吗？", settingsListSeparator: "、",
  });
  Object.assign(dictionaries.en, {
    settingsAvailable: "Available", settingsUnavailable: "Unavailable", settingsNeedsAttention: "Needs Attention", settingsConfigurationError: "Configuration Error", settingsCreated: "Created", settingsMigrationError: "Migration Error", settingsUnsupportedSchema: "Unsupported Schema",
    settingsFeishuSchemaNeedsReview: "Feishu table schema needs attention", settingsFeishuMissingFields: "{table} is missing:", settingsFeishuIncompatibleFields: "{table} has incompatible field types:", settingsFeishuCurrentType: "{field} (current type: {type})",
    settingsFeishuSyncComplete: "Sync complete: creators created {creatorCreated}, updated {creatorUpdated}; accounts created {accountCreated}, updated {accountUpdated}; relations updated {relationUpdated}.", settingsFeishuValidationPassed: "Connection and field contract validation passed.", settingsFeishuDryRunComplete: "Preflight complete; Feishu was not modified.", settingsFeishuSyncPartial: "Sync partially completed with {count} failed records. Later batches stopped; repair and sync again.", settingsFeishuSyncConfirm: "KOLConnect / Excel remains authoritative. Sync may create missing Feishu records and update exact matches; M7.1 never deletes Feishu records. Continue?", settingsListSeparator: ", ",
  });

  Object.assign(dictionaries.zh, {
    settingsFeishuChatTestPassed: "本机配置与 SDK 检查通过。连接状态请以启用后的实时状态为准。", settingsFeishuChatStopped: "飞书 AI 助手已停止。", settingsFeishuChatConnected: "飞书 AI 助手已连接。", settingsFeishuChatConnecting: "飞书 AI 助手正在连接。", settingsFeishuCredentialsInvalid: "请检查并重新保存 App ID / App Secret。", settingsFeishuSdkUnavailable: "飞书官方 SDK 未安装或未包含在当前应用包中。", settingsFeishuBotCapabilityMissing: "请在飞书开放平台启用机器人能力并发布应用。", settingsFeishuBotPermissionMissing: "请启用机器人发送消息权限并重新发布应用。", settingsFeishuEventPermissionMissing: "请订阅消息接收事件并授予消息读取权限。", settingsFeishuEventConfigurationError: "请检查长连接模式、消息事件订阅和机器人能力。", settingsFeishuNetworkError: "请检查本机网络、代理、防火墙和飞书服务状态。", settingsFeishuConnectTimeout: "飞书长连接建立超时。请检查网络、飞书应用长连接配置及应用凭据后重试。", settingsFeishuSdkError: "飞书官方 SDK 无法建立长连接，请查看安全日志后重试。", settingsFeishuLongConnectionFailed: "请检查网络、应用发布状态和飞书服务状态。", settingsFeishuReviewLogs: "请查看运行日志中的 trace 信息。", settingsFeishuChatFailed: "操作未完成：{code}\n{guidance}",
  });
  Object.assign(dictionaries.en, {
    settingsFeishuChatTestPassed: "Local configuration and SDK checks passed. Check live status after enabling the assistant.", settingsFeishuChatStopped: "Feishu AI Assistant stopped.", settingsFeishuChatConnected: "Feishu AI Assistant connected.", settingsFeishuChatConnecting: "Feishu AI Assistant is connecting.", settingsFeishuCredentialsInvalid: "Check and save the App ID and App Secret again.", settingsFeishuSdkUnavailable: "The official Feishu SDK is unavailable or missing from this application package.", settingsFeishuBotCapabilityMissing: "Enable bot capability in Feishu Open Platform and publish the app.", settingsFeishuBotPermissionMissing: "Enable bot message-send permission and publish the app again.", settingsFeishuEventPermissionMissing: "Subscribe to the message-receive event and grant message-read permission.", settingsFeishuEventConfigurationError: "Check long connection mode, message event subscriptions, and bot capability.", settingsFeishuNetworkError: "Check local network, proxy, firewall, and Feishu service status.", settingsFeishuConnectTimeout: "Feishu long connection timed out. Check network, long-connection configuration, and credentials, then try again.", settingsFeishuSdkError: "The official Feishu SDK could not establish a long connection. Review the safe runtime log and retry.", settingsFeishuLongConnectionFailed: "Check network, app publication status, and Feishu service status.", settingsFeishuReviewLogs: "Review trace information in the runtime log.", settingsFeishuChatFailed: "Operation did not complete: {code}\n{guidance}",
  });

  Object.assign(dictionaries.zh, {
    mailFollowupTitle: "邮件跟进", mailFollowupSubtitle: "根据已同步的收发邮件记录查看当前跟进状态；不会发送邮件或改变达人、Campaign 状态。",
    mailFollowupRefresh: "刷新", mailFollowupFilterLabel: "跟进状态筛选", mailFollowupFilterActionable: "待处理", mailFollowupFilterAll: "全部",
    mailFollowupExportQueue: "导出队列", mailFollowupExportCsv: "导出 CSV", mailFollowupExportXlsx: "导出 Excel", mailFollowupLoading: "正在读取邮件跟进状态…",
    mailFollowupCreator: "Creator", mailFollowupContactEmail: "联系邮箱", mailFollowupStatus: "状态", mailFollowupWaiting: "等待", mailFollowupLatestMail: "最近邮件",
    mailFollowupInbound: "收件", mailFollowupOutbound: "发件", mailFollowupHistory: "历史", mailFollowupActions: "操作",
    mailFollowupEmpty: "暂无待跟进邮件。同步邮件后，这里会根据收发记录显示待跟进状态。", mailFollowupExportHint: "导出仅生成文件，不代表已发送邮件，也不会移除队列成员。",
    mailFollowupClose: "关闭", mailFollowupExportEmpty: "导出队列为空。", mailFollowupUnknownHelp: "当前邮件时间或联系人归属证据不足，暂时无法可靠判断由谁继续回复。",
    mailFollowupHistoryHelp: "当前同步的数据无法确认是否包含该联系人全部历史邮件，但不影响系统基于已同步邮件判断当前跟进状态。",
    mailFollowupPromptDate: "输入提醒时间（例如 2026-09-20T09:00:00Z）：", mailFollowupInvalidDate: "请选择有效的提醒时间。", mailFollowupInvalidDateFormat: "提醒时间格式无效。",
    mailFollowupStopConfirm: "停止后，该邮箱对应的跟进项将不再出现在正常待跟进列表中。邮件同步仍会继续。", mailFollowupUpdated: "邮件跟进状态已更新。",
    mailFollowupExportFailed: "导出失败，请稍后重试。", mailFollowupFileSaveFailed: "文件保存失败，请稍后重试。", mailFollowupExportSaved: "导出完成：{path}", mailFollowupExported: "导出完成。",
    mailSyncFollowupGoogle: "同步邮件跟进到 Google Sheets", mailPageSize: "每页", mailPageCount: "共 {count} 封", mailPageSummary: "第 {page} / {total} 页", mailPrevious: "上一页", mailNext: "下一页", mailAccountsSave: "保存邮箱账户",
    mailGoogleFollowupSynced: "已同步 {count} 个邮件跟进联系人组到 Google Sheets。", mailGoogleConfigurationRequired: "请先在设置中配置并连接 Google Sheets。",
    settingsSystemTools: "系统工具", settingsDebug: "系统调试", settingsEnableDebug: "开启 Debug 模式", settingsDebugHint: "开启后显示本机运行信息，不会显示密码、Token 或邮件授权码。",
    settingsHealth: "系统健康检查", settingsHealthHint: "检查本地数据目录、达人库 Excel、插件最近导入记录与飞书配置，不会写入 Excel 或发送飞书请求。", settingsRunHealth: "运行健康检查",
    settingsCreatorLibraryFile: "达人库文件", settingsWorkbookPath: "Excel 工作簿路径", settingsWorkbookPathPlaceholder: "例如：WPS云盘\\KOLConnect\\Creator_Library.xlsx", settingsWorkbookPathHint: "这是运行 KOLConnect 的本机文件路径。", settingsSaveCreatorLibrary: "保存达人库文件设置",
    settingsFxTitle: "货币与汇率", settingsFxHint: "Campaign 中使用非 USD 报价时，可在录入过程中直接设置汇率。这里用于统一管理已设置汇率。", settingsFxManage: "添加或管理更多币种", settingsFxCollapse: "收起更多币种", settingsFxSave: "保存并更新", settingsQuickConversion: "快速换算", settingsAmount: "金额", settingsCurrency: "币种", settingsFxCalculatorHint: "输入金额和币种以换算 USD。", settingsFxUsdFixed: "USD（固定）", settingsFxRate: "{currency}：1 USD =", settingsFxUnavailable: "当前币种未配置有效汇率，无法换算。", settingsFxResult: "{amount} {currency} ≈ {usd} USD（1 USD = {rate} {currency}）",
    settingsBackupTitle: "Creator Library 备份", settingsCurrentWorkbook: "当前工作簿", settingsLatestBackup: "最近创建的备份", settingsNoBackupThisSession: "本次会话尚未创建备份", settingsBackupHint: "备份将保存到当前工作簿目录下的 backups 文件夹。", settingsCreateBackup: "创建备份", settingsBackupCreated: "达人库 Excel 备份已创建。",
    settingsStorageMigrationTitle: "本地数据存储升级", settingsStorageMigrationHint: "将本地业务数据从 Excel 迁移到 SQLite。原 Excel 会保留且不会删除；确认后 SQLite 将成为唯一运行数据源。", settingsCurrentDataSource: "当前数据源", settingsMigrationStatus: "迁移状态", settingsBackup: "备份", settingsMigrationId: "迁移 ID", settingsCheckMigration: "检查迁移", settingsPrepareMigration: "开始准备", settingsConfirmMigration: "确认迁移到 SQLite", settingsRecoverMigration: "恢复已确认迁移", settingsMigrationReady: "准备完成：Creators {creators}，Accounts {accounts}，Campaigns {campaigns}。请核对后明确确认。", settingsSqliteActive: "SQLite 已启用。旧 Excel 已保留为迁移前文件；实时数据请通过导出生成。", settingsMigrationCancelled: "迁移已取消，当前数据源仍为 Excel。", settingsMigrationDetected: "检测到旧 Excel，可在确认后准备迁移。", settingsMigrationNotRequired: "当前不需要迁移。", settingsMigrationConfirmText: "将把本地业务数据从 Excel 迁移到 SQLite。\n原 Excel 会保留，不会删除。\n迁移完成后 SQLite 将成为唯一运行数据源。\n\n确认迁移吗？",
    settingsResetTitle: "高级 / 数据重置", settingsResetHint: "此操作删除本地业务数据，但保留应用配置和数据结构。执行前会创建时间戳 Excel 备份，不会修改或同步飞书数据。", settingsResetWarning: "该操作会清空 Creator、Account、分析快照、Campaign 等本机历史业务记录。请先预览并核对数量。", settingsResetRetained: "Chrome 配置：保留 · 邮箱配置：保留 · 飞书配置：保留 · Schema：保留", settingsPreviewReset: "预览清空内容", settingsExecuteReset: "清空本地业务数据", settingsResetPreviewDone: "预览完成，尚未修改任何本地数据。确认数量后方可执行清空。", settingsResetDone: "本地业务数据已清空。备份：{backup}", settingsOperationNotRun: "操作未执行：{reason}", settingsResetConfirm: "将永久清空本机历史业务数据：\n\nCreators: {creators}\nAccounts: {accounts}\nVideos: {videos}\nSnapshots: {snapshots}\nCampaigns: {campaigns}\n\nChrome 配置：保留\n邮箱配置：保留\n飞书配置：保留\nSchema：保留\n\n执行前将创建可恢复的时间戳备份。确认继续吗？",
    settingsFeishuCreatorTable: "达人 Table ID", settingsFeishuAccountTable: "达人账号 Table ID", settingsFeishuContactTable: "Agency 联系人 Table ID", settingsSecretPlaceholder: "留空表示不修改", settingsFeishuCaptureHint: "抓取结果仅同步到达人表和达人账号表；当前任务可在“审核结果”页手动同步。",
    settingsGoogleTitle: "Google Sheets 数据同步", settingsGoogleHint: "手动将当前 SQLite 达人与账号数据同步到指定 Spreadsheet；Campaign 页面仍可单独导出 Campaign 报告。SQLite 始终是权威数据源，不会从 Google 回写。", settingsSpreadsheetId: "Spreadsheet URL 或 ID", settingsConnectionStatus: "连接状态", settingsSaveConfiguration: "保存配置", settingsConnectGoogle: "连接 Google", settingsDisconnect: "断开连接", settingsSyncGoogle: "同步数据到 Google Sheets",
    settingsFeishuSyncTitle: "飞书数据同步", settingsFeishuSyncHint: "KOLConnect / Excel 始终是权威数据源。M7.1 仅手动创建或更新匹配记录，不会删除飞书记录，也不会读取飞书修改写回本地。", settingsNotValidated: "未验证", settingsValidateConnection: "验证连接", settingsDryRun: "预检查 / Dry Run", settingsSyncFeishu: "同步到飞书", settingsLocalCreators: "本地达人", settingsRemoteCreators: "飞书达人", settingsToCreate: "待新增", settingsToUpdate: "待更新", settingsConflicts: "冲突", settingsUnmanaged: "未管理记录", settingsRelationAdd: "关系待建立", settingsRelationUpdate: "关系待更新", settingsRelationRemove: "关系待移除", settingsRelationConflicts: "关系冲突",
    settingsFeishuChatTitle: "飞书 AI 助手", settingsFeishuChatHint: "通过飞书官方长连接接收文字消息，并复用现有 App ID / App Secret。助手只调用 KOLConnect 已授权能力；写操作仍需在同一会话中明确确认。", settingsTransport: "传输方式", settingsBot: "机器人", settingsLastConnected: "最近连接", settingsLastError: "最近错误", settingsCheckLocalConfiguration: "检查本机配置", settingsEnableAssistant: "启用助手", settingsDisableAssistant: "停止助手",
    settingsConnected: "已连接", settingsAuthRequired: "需要授权", settingsNotConnected: "未连接", settingsNotConfigured: "未配置", settingsDisabled: "未启用", settingsConnecting: "正在连接", settingsConnectionFailed: "连接失败", settingsUnknown: "未知", settingsFeishuLongConnection: "飞书官方长连接", settingsEnabled: "已启用",
  });

  Object.assign(dictionaries.en, {
    mailFollowupTitle: "Mail Follow-up", mailFollowupSubtitle: "Review follow-up status from synced inbound and outbound mail. This never sends mail or changes Creator or Campaign status.",
    mailFollowupRefresh: "Refresh", mailFollowupFilterLabel: "Follow-up status filters", mailFollowupFilterActionable: "Actionable", mailFollowupFilterAll: "All", mailFollowupExportQueue: "Export Queue", mailFollowupExportCsv: "Export CSV", mailFollowupExportXlsx: "Export Excel", mailFollowupLoading: "Loading mail follow-up status…",
    mailFollowupCreator: "Creator", mailFollowupContactEmail: "Contact Email", mailFollowupStatus: "Status", mailFollowupWaiting: "Waiting", mailFollowupLatestMail: "Latest Mail", mailFollowupInbound: "Inbound", mailFollowupOutbound: "Outbound", mailFollowupHistory: "History", mailFollowupActions: "Actions",
    mailFollowupEmpty: "No mail follow-up items yet. Sync mail to derive follow-up status from message records.", mailFollowupExportHint: "Export only creates a file. It does not send mail or remove queue members.", mailFollowupClose: "Close", mailFollowupExportEmpty: "The export queue is empty.", mailFollowupUnknownHelp: "The available mail time or ownership evidence is insufficient to reliably determine who should reply next.", mailFollowupHistoryHelp: "The synced data cannot confirm whether it contains this contact's complete mail history, but it can still derive follow-up status from the synced messages.", mailFollowupPromptDate: "Enter a reminder time (for example 2026-09-20T09:00:00Z):", mailFollowupInvalidDate: "Choose a valid reminder time.", mailFollowupInvalidDateFormat: "The reminder time format is invalid.", mailFollowupStopConfirm: "After stopping, this email's follow-up item will no longer appear in the normal follow-up list. Mail sync will continue.", mailFollowupUpdated: "Mail follow-up status updated.", mailFollowupExportFailed: "Export failed. Please try again later.", mailFollowupFileSaveFailed: "File save failed. Please try again later.", mailFollowupExportSaved: "Export complete: {path}", mailFollowupExported: "Export complete.",
    mailSyncFollowupGoogle: "Sync Mail Follow-up to Google Sheets", mailPageSize: "Per page", mailPageCount: "{count} messages", mailPageSummary: "Page {page} of {total}", mailPrevious: "Previous", mailNext: "Next", mailAccountsSave: "Save Mail Accounts", mailGoogleFollowupSynced: "Synced {count} mail follow-up contact groups to Google Sheets.", mailGoogleConfigurationRequired: "Configure and connect Google Sheets in Settings first.",
    settingsSystemTools: "System Tools", settingsDebug: "System Debugging", settingsEnableDebug: "Enable Debug Mode", settingsDebugHint: "Shows local runtime information without passwords, tokens, or mail app passwords.", settingsHealth: "System Health Check", settingsHealthHint: "Checks local data directories, the Creator Library Excel workbook, recent extension imports, and Feishu configuration without writing Excel or sending Feishu requests.", settingsRunHealth: "Run Health Check", settingsCreatorLibraryFile: "Creator Library File", settingsWorkbookPath: "Excel Workbook Path", settingsWorkbookPathPlaceholder: "For example: WPS Drive\\KOLConnect\\Creator_Library.xlsx", settingsWorkbookPathHint: "This is the local path used by KOLConnect.", settingsSaveCreatorLibrary: "Save Creator Library File Settings",
    settingsFxTitle: "Currencies and Exchange Rates", settingsFxHint: "When a Campaign uses a non-USD quote, rates can be set while editing it. Manage configured rates here.", settingsFxManage: "Manage More Currencies", settingsFxCollapse: "Show Fewer Currencies", settingsFxSave: "Save and Update", settingsQuickConversion: "Quick Conversion", settingsAmount: "Amount", settingsCurrency: "Currency", settingsFxCalculatorHint: "Enter an amount and currency to convert to USD.", settingsFxUsdFixed: "USD (fixed)", settingsFxRate: "{currency}: 1 USD =", settingsFxUnavailable: "The selected currency does not have a valid configured rate.", settingsFxResult: "{amount} {currency} ≈ {usd} USD (1 USD = {rate} {currency})",
    settingsBackupTitle: "Creator Library Backup", settingsCurrentWorkbook: "Current workbook", settingsLatestBackup: "Latest created backup", settingsNoBackupThisSession: "No backup was created in this session", settingsBackupHint: "Backups are stored in the backups folder beside the current workbook.", settingsCreateBackup: "Create Backup", settingsBackupCreated: "Creator Library Excel backup created.", settingsStorageMigrationTitle: "Local Data Storage Upgrade", settingsStorageMigrationHint: "Migrate local business data from Excel to SQLite. The original Excel file is retained; after confirmation, SQLite becomes the sole runtime authority.", settingsCurrentDataSource: "Current data source", settingsMigrationStatus: "Migration status", settingsBackup: "Backup", settingsMigrationId: "Migration ID", settingsCheckMigration: "Check Migration", settingsPrepareMigration: "Prepare", settingsConfirmMigration: "Confirm Migration to SQLite", settingsRecoverMigration: "Recover Confirmed Migration", settingsMigrationReady: "Ready: Creators {creators}, Accounts {accounts}, Campaigns {campaigns}. Review the counts and confirm explicitly.", settingsSqliteActive: "SQLite is active. The legacy Excel file is retained as the pre-migration file; export current data when needed.", settingsMigrationCancelled: "Migration was cancelled. Excel remains the current data source.", settingsMigrationDetected: "A legacy Excel file was found. You can prepare migration after confirmation.", settingsMigrationNotRequired: "No migration is currently required.", settingsMigrationConfirmText: "Local business data will be migrated from Excel to SQLite.\nThe original Excel file will be retained.\nAfter migration, SQLite becomes the sole runtime authority.\n\nContinue?",
    settingsResetTitle: "Advanced / Data Reset", settingsResetHint: "Deletes local business data while preserving application configuration and data structures. A timestamped Excel backup is created first; Feishu data is neither changed nor synchronized.", settingsResetWarning: "This clears local historical Creator, Account, analysis snapshot, and Campaign records. Preview and verify counts first.", settingsResetRetained: "Chrome configuration: retained · Mail configuration: retained · Feishu configuration: retained · Schema: retained", settingsPreviewReset: "Preview Data to Clear", settingsExecuteReset: "Clear Local Business Data", settingsResetPreviewDone: "Preview complete. No local data was changed. Verify the counts before clearing.", settingsResetDone: "Local business data cleared. Backup: {backup}", settingsOperationNotRun: "Operation not run: {reason}", settingsResetConfirm: "Local historical business data will be permanently cleared:\n\nCreators: {creators}\nAccounts: {accounts}\nVideos: {videos}\nSnapshots: {snapshots}\nCampaigns: {campaigns}\n\nChrome configuration: retained\nMail configuration: retained\nFeishu configuration: retained\nSchema: retained\n\nA recoverable timestamped backup will be created first. Continue?",
    settingsFeishuCreatorTable: "Creator Table ID", settingsFeishuAccountTable: "Creator Account Table ID", settingsFeishuContactTable: "Agency Contact Table ID", settingsSecretPlaceholder: "Leave blank to keep the current value", settingsFeishuCaptureHint: "Capture results sync only to the Creator and Creator Account tables; the current task can be synced manually from Review Results.", settingsGoogleTitle: "Google Sheets Data Sync", settingsGoogleHint: "Manually sync current SQLite Creator and account data to the selected spreadsheet. Campaign reports can still be exported from their Campaign page. SQLite remains authoritative and Google never writes back.", settingsSpreadsheetId: "Spreadsheet URL or ID", settingsConnectionStatus: "Connection status", settingsSaveConfiguration: "Save Configuration", settingsConnectGoogle: "Connect Google", settingsDisconnect: "Disconnect", settingsSyncGoogle: "Sync Data to Google Sheets", settingsFeishuSyncTitle: "Feishu Data Sync", settingsFeishuSyncHint: "KOLConnect / Excel remains authoritative. M7.1 manually creates or updates matched records only; it never deletes Feishu records or writes Feishu edits back locally.", settingsNotValidated: "Not Validated", settingsValidateConnection: "Validate Connection", settingsDryRun: "Preflight / Dry Run", settingsSyncFeishu: "Sync to Feishu", settingsLocalCreators: "Local Creators", settingsRemoteCreators: "Feishu Creators", settingsToCreate: "To Create", settingsToUpdate: "To Update", settingsConflicts: "Conflicts", settingsUnmanaged: "Unmanaged Records", settingsRelationAdd: "Relations to Add", settingsRelationUpdate: "Relations to Update", settingsRelationRemove: "Relations to Remove", settingsRelationConflicts: "Relation Conflicts", settingsFeishuChatTitle: "Feishu AI Assistant", settingsFeishuChatHint: "Receives text through Feishu's official long connection and reuses the current App ID and App Secret. The assistant uses only KOLConnect-authorized capabilities; writes still require explicit confirmation in the same session.", settingsTransport: "Transport", settingsBot: "Bot", settingsLastConnected: "Last Connected", settingsLastError: "Last Error", settingsCheckLocalConfiguration: "Check Local Configuration", settingsEnableAssistant: "Enable Assistant", settingsDisableAssistant: "Stop Assistant", settingsConnected: "Connected", settingsAuthRequired: "Authorization Required", settingsNotConnected: "Not Connected", settingsNotConfigured: "Not Configured", settingsDisabled: "Disabled", settingsConnecting: "Connecting", settingsConnectionFailed: "Connection Failed", settingsUnknown: "Unknown", settingsFeishuLongConnection: "Official Feishu Long Connection", settingsEnabled: "Enabled",
  });

  Object.assign(dictionaries.en, {
    mailFollowupSummary: "Showing {visible} mail follow-up items out of {total} synced correspondent groups.",
    mailFollowupNoItems: "No mail follow-up items match the current filter.",
    mailFollowupWaitingMe: "Waiting for Me",
    mailFollowupWaitingCreator: "Waiting for Creator",
    mailFollowupWaitingUnknown: "Status Unknown",
    mailFollowupHistoryPartial: "Partial History",
    mailFollowupHistoryUnknown: "History Scope Unknown",
    mailFollowupHistorySynced: "Within Synced Scope",
    mailFollowupDays: "{days} days",
    mailFollowupResume: "Resume Follow-up",
    mailFollowupSnooze: "Snooze ▼",
    mailFollowupTomorrow: "Tomorrow",
    mailFollowupThreeDays: "In 3 Days",
    mailFollowupChooseDate: "Choose Date…",
    mailFollowupClearSnooze: "Clear Snooze",
    mailFollowupStop: "Stop Follow-up",
    mailFollowupExportAdd: "Add to Export Queue",
    mailFollowupExportRemove: "Remove from Export Queue",
    unnamedCreator: "Unnamed Creator",
    settingsExchangeRateInvalid: "{currency} exchange rate must be greater than 0.",
    settingsExchangeRateSaved: "Exchange rates saved. Future USD-derived values use the new rates.",
    googleSheetsSaved: "Google Sheets configuration saved.",
    googleSheetsConnected: "Google OAuth connected.",
    googleSheetsDisconnected: "Google OAuth disconnected.",
    googleSheetsSynced: "Google Sheets data sync completed: {count} worksheets.",
    googleSheetsAuthRequired: "Google authorization has expired or is incomplete. Reconnect Google before syncing.",
    dashboardFixedFirst: "Always visible and fixed first", dashboardMoveUp: "Move Up", dashboardMoveDown: "Move Down",
    dashboardNoTrend: "No trend data", dashboardMedianViews: "Median Views", dashboardFollowers: "Followers",
    dashboardGrowth: "up", dashboardDecline: "down", dashboardUnspecifiedCurrency: "Unspecified currency",
    creatorAnalysisTimeUnknown: "Analysis time unknown", creatorFreshnessFresh: "Fresh ({days} days ago)",
    creatorFreshnessUpdate: "Update recommended ({days} days ago)", creatorFreshnessStale: "Data is stale ({days} days ago)",
    creatorAccount: "Account", creatorUnknownPlatform: "Unknown platform", creatorFollowers: "{count} followers",
    creatorAccountCount: "{count}", creatorDataLoading: "Loading creator details...",
    accountsTitle: "Accounts", accountsSubtitle: "Manage Chrome Profile configurations used for creator discovery. Deleting a configuration does not delete browser data.", accountsConfigurationTitle: "Chrome Profile Configuration", refreshProfiles: "Refresh Chrome Accounts", addAccountConfiguration: "+ Add Account Configuration", saveAccounts: "Save Account Configuration", accountsProfileLabel: "Chrome Profile", alias: "Alias", notes: "Notes", accountsAutomationProfile: "KOLConnect Dedicated Automation Profile", accountsAvailable: "Available", accountsUnavailable: "Unavailable", accountsCurrentDefaultProfile: "Current Default Profile", accountsOpenBrowser: "Open Browser", accountsRemoveConfiguration: "Remove Configuration", accountsOpened: "Opened: {profile}{alias}", accountsRemoveConfirm: "Remove the KOLConnect configuration for {profile}? Chrome browser data will not be deleted.",
    productCount: "{count} product{plural}", productEyebrow: "PRODUCT MANAGEMENT", productTitle: "Products", productSubtitle: "Manage product information and view the number of Campaigns associated with each product.", productShowArchived: "Show Archived", productListTitle: "Product List", productNameLabel: "Product Name", productCompanyNameLabel: "Company Name", productCampaignCountLabel: "Campaign Count", productCreatedAtLabel: "Created At", productUpdatedAtLabel: "Updated At", productStatusLabel: "Status", productNoteLabel: "Notes", productNotePlaceholder: "Record product positioning, market, or partnership notes", productLoading: "Loading products...", productRetry: "Retry", productEmpty: "No products yet. Create the first product record.", productCreate: "Create Product", productEdit: "Edit Product", productSave: "Save Product",
    productSaving: "Saving...", productRestore: "Restore", productArchive: "Archive", productListLoadFailed: "Product list could not be loaded. Please try again.",
    productNameRequired: "Enter a product name.", productCompanyRequired: "Enter a company name.", productCreated: "Product created.",
    productUpdated: "Product updated.", productSaveFailed: "Product could not be saved.", productArchiveConfirm: "Archiving hides this product from the default list. Existing Campaign and partnership data is retained.",
    productRestoreConfirm: "Restore this product? Historical Campaign and partnership data is retained.", productArchived: "Product archived.", productRestored: "Product restored.",
    agencyCount: "{count} agenc{pluralY}", agencyEyebrow: "PARTNER NETWORK", agencyTitle: "Agency", agencySubtitle: "View partner agencies, contact coverage, and associated creator resources.", agencyRefreshList: "Refresh List", agencyOverviewAria: "Agency overview", agencyAssociatedCreators: "Associated Creators", agencyContactsLabel: "Contacts", agencyListTitle: "Agency List", agencyLoading: "Loading agencies...", agencyRetry: "Retry", agencyEmpty: "No agencies yet. Create the first record from the existing Agency data entry point.", agencyCountryRegion: "Country/Region", agencyUpdatedAt: "Updated At", agencyContacts: "{count} contact{plural}", agencyCreators: "{count} creator{plural}", agencyMore: "More",
    agencyDelete: "Delete Agency", agencyListLoadFailed: "Agency list could not be loaded. Please try again.", agencyProfileSaved: "Agency profile saved.",
    agencyDeleteConfirm: "Delete this Agency? This cannot be undone.", agencyDeleted: "Agency deleted.", agencyContactSaved: "Contact saved.",
    agencyContactDeleted: "Contact deleted.", agencyUnlinked: "Creator unlinked from Agency.", agencyViewCreator: "View Creator", agencyUnlink: "Unlink",
    campaignStatusDraft: "Draft", campaignStatusSourcing: "Sourcing", campaignStatusRunning: "Running", campaignStatusCompleted: "Completed", campaignStatusArchived: "Archived", campaignEyebrow: "CAMPAIGN MANAGEMENT", campaignTitle: "Campaigns", campaignSubtitle: "Manage creator partnership campaigns by product and status, with centralized views of budget, schedule, and ownership.", campaignProductLabel: "Product", campaignStatusLabel: "Status", campaignAllActiveStatuses: "All Active Statuses", campaignStartDateLabel: "Start Date", campaignEndDateLabel: "End Date", campaignShowArchived: "Show Archived", campaignApplyFilters: "Apply Filters", campaignListTitle: "Campaign List", campaignNameLabel: "Campaign Name", campaignCreatorCountLabel: "Creators", campaignBusinessStatusLabel: "Business Status", campaignArchiveStatusLabel: "Archive Status", campaignPlatformLabel: "Platform", campaignBudgetLabel: "Budget", campaignOwnerLabel: "Owner", campaignGoalLabel: "Goal", campaignGoalPlaceholder: "Record the goal for this Campaign", campaignCountryEditNote: "Country/Region is recorded only at creation. This field cannot be edited at the current stage.", campaignLoading: "Loading Campaigns...", campaignRetry: "Retry", campaignEmpty: "No Campaigns match the current filters.", campaignListCount: "{count} Campaign{plural}", campaignArchived: "Archived", campaignActive: "Active", campaignAnyPlatform: "All platforms", campaignView: "View", campaignRestore: "Restore", campaignEdit: "Edit", campaignArchive: "Archive", campaignAllProducts: "All products", campaignSelectProduct: "Select a product", campaignUnnamedProduct: "Unnamed product", campaignProductsLoadFailed: "Product options could not be loaded. Campaigns cannot be created or filtered right now.", campaignListResponseInvalid: "Campaign list response was invalid. Try again later.", campaignListLoadFailed: "Campaign list could not be loaded. Try again later.", campaignCreate: "Create Campaign", campaignSaving: "Saving...", campaignSave: "Save Campaign", campaignNameRequired: "Enter a Campaign name.", campaignUpdated: "Campaign updated.", campaignCreated: "Campaign created.", campaignSaveFailed: "Campaign could not be saved.", campaignArchiveConfirm: "Archiving hides this Campaign from the default list. Existing creator partnership data is retained.", campaignRestoreConfirm: "Restoring shows this Campaign again. Its business status and creator partnership data are retained.", campaignArchivedSaved: "Campaign archived.", campaignRestoredSaved: "Campaign restored. Its business status is unchanged.",
    creatorStatusDiscovered: "Discovered", creatorStatusContacted: "Contacted", creatorStatusNegotiating: "Negotiating", creatorStatusCooperating: "Collaborating", creatorStatusCompleted: "Completed", creatorStatusRejected: "Rejected",
    creatorLibraryConfirmAdd: "Confirm Add", creatorLibraryLoading: "Loading...", creatorLibraryJoining: "Adding...", creatorLibraryUnnamedAccount: "Unnamed account", creatorLibraryUnspecifiedPlatform: "Unspecified platform", creatorLibraryCampaignPlatformMatch: " (matches Campaign platform)",
    creatorLibraryChooseAccount: "Select an execution account", creatorLibraryNoAccounts: "No available accounts", creatorLibraryNoAccountsHint: "This creator has no available social accounts. Complete account details first.", creatorLibraryOneAccountHint: "The creator's only social account was selected automatically.", creatorLibraryMatchingAccountHint: "Accounts matching {platform} are listed first. Confirm the execution account.", creatorLibraryMultipleAccountsHint: "This creator has multiple accounts. Select the account for this collaboration.",
    creatorLibraryChooseCampaign: "Select a Campaign", creatorLibraryNoCampaigns: "No available Campaigns", creatorLibraryNoCampaignsMessage: "There are no available Campaigns to join.", creatorLibraryMissingCreator: "Creator ID is required to add a Campaign.", creatorLibraryCampaignModalMissing: "The Add to Campaign dialog is not loaded.", creatorLibraryLoadCampaignFailed: "Campaigns or creator accounts could not be loaded.", creatorLibraryCampaignSelectedRequired: "Select a Campaign.", creatorLibraryAccountSelectedRequired: "Select the execution account for this collaboration.", creatorLibraryCampaignAdded: "{creator} was added to the Campaign.", creatorLibraryCampaignAlreadyAdded: "This creator is already in this Campaign.", creatorLibraryCampaignAddFailed: "Could not add the creator to the Campaign.",
    creatorDeleteCreators: "Creator record", creatorDeleteAccounts: "Accounts", creatorDeleteVideos: "Videos", creatorDeleteCampaignRelations: "Campaign relationships", creatorDeleteFollowUpLogs: "Follow-up logs", creatorDeleteTaskArtifacts: "Task files", creatorDeleteProtectionRecords: "Data-protection records", creatorDeleteLegacySources: "Legacy records", creatorDeleteCooperations: "Historical cooperations", creatorDeleteEmbeddedReferences: "Embedded analysis references", creatorDeleteUnmappedArtifacts: "Unresolved task files", creatorDeleteSubmitting: "Deleting permanently...", creatorDeleteConfirm: "Confirm Permanent Delete", creatorDeleteUnknownBlocker: "Related data cannot be handled safely.", creatorDeleteReady: "Impact check passed. You can confirm the deletion.", creatorDeleteBlocked: "Permanent deletion is unavailable. Resolve the blockers below first.", creatorDeleteChecking: "Checking permanent-delete impact...", creatorDeleteLoadFailed: "Could not load permanent-delete impact.", creatorDeleteMissingCreator: "Creator ID is required to check permanent-delete impact.", creatorDeleteModalMissing: "The permanent-delete dialog is not loaded.", creatorDeleteSuccess: "Creator permanently deleted.", creatorDeleteStale: "Related data changed. Confirm the deletion impact again.", creatorDeleteNewBlocker: "A new safety blocker appeared. The deletion impact was refreshed.", creatorDeleteStorageLocked: "Data is being changed by another operation. Check the impact again shortly.", creatorDeleteNotFound: "Creator no longer exists. The list was refreshed.", creatorDeleteFailed: "Permanent deletion failed. Data remains in a safe state. Try again later.",
    creatorImportMissingRequired: "Required field missing", creatorImportInvalidPlatform: "Invalid platform", creatorImportInvalidProfileUrl: "Invalid profile URL", creatorImportDuplicateInFile: "Duplicate creator in file", creatorImportUnknownAgency: "Agency does not exist", creatorImportNoHistory: "No history data", creatorTrendGrowth: "↑ Up {amount}", creatorTrendDecline: "↓ Down {amount}", creatorTrendNoChange: "— No change",
    creatorLibraryPageSummary: "{start}-{end} of {total} creators", creatorLibraryPrevious: "Previous", creatorLibraryNext: "Next", creatorLibrarySelectedCount: "{count} selected", creatorLibraryExportSelectedCount: "Export Selected Creators ({count})", creatorLibraryExportSelected: "Export Selected Creators", creatorLibraryCampaignSelectedCount: "Add to Campaign ({count})", creatorLibrarySelectCreator: "Select creator", creatorLibraryInsufficientData: "⚠ Insufficient data", creatorLibraryCountry: "Country", creatorLibraryLanguage: "Language", creatorLibraryCategory: "Category", creatorLibraryEmail: "Email", creatorLibraryFollowers: "Followers", creatorLibraryAverageViews: "Average views", creatorLibraryViewCreator: "View Creator", creatorLibraryRestoreCreator: "Restore Creator", creatorLibraryMore: "More ▼", creatorLibraryArchiveCreator: "Archive Creator", creatorLibraryMergeCreator: "Merge Creator", creatorLibraryDeleteCreator: "Delete Permanently", creatorLibraryArchived: "Archived", creatorLibraryViewAnalysis: "View Analysis", creatorLibraryRestore: "Restore", creatorLibraryCreateTask: "Create Partnership Task", creatorLibraryArchive: "Archive",
    creatorLibraryAllContentCategories: "All content categories", creatorLibraryAllCountries: "All countries/regions", creatorLibraryAllLanguages: "All languages", creatorLibraryAllTags: "All tags", creatorLibraryAllAiTags: "All AI tags", creatorLibraryAllAgencies: "All agencies", creatorLibraryFileSaveFailed: "Could not save the file. Try again later.", creatorLibraryDownloadFailed: "Download failed. Try again later.", creatorLibraryTemplateSaved: "Template saved to: {path}", creatorLibraryExportSaved: "Saved to: {path}", creatorLibraryExportFailed: "Export failed. Refresh Creator Library and try again.", creatorLibraryExported: "Exported {count} creators.", creatorLibraryBatchSelected: "{count} creators selected", creatorLibraryBatchAdded: "Added {count}", creatorLibraryBatchRestored: "Restored {count}", creatorLibraryBatchPresent: "Already present {count}", creatorLibraryBatchFailed: "Failed {count}", creatorLibraryUnknownCreator: "Unknown creator", creatorLibraryAddFailed: "Add failed", creatorLibraryBatchAddFailed: "Could not batch add creators to the Campaign.", creatorLibraryImportComplete: "Import complete: created {created}, skipped existing {skipped}.", creatorLibraryImportNotRun: "Import was not run: {total} rows, {invalid} invalid.", creatorLibraryInvalidData: "Invalid data", creatorLibraryImportRow: "Row {row}: {label}{field}", creatorLibraryExcelImported: "Creator Excel import complete.", creatorLibraryTaskMissing: "No related review task was found.", creatorLibraryTaskOpened: "Opened the related review task.", creatorLibraryArchiveConfirm: "Archiving hides this creator from the default list. Historical analysis and Campaign relationships are retained.", creatorLibraryRestoreConfirm: "Restore this creator to the default Creator Library?", creatorLibraryArchivedSaved: "Creator archived.", creatorLibraryRestoredSaved: "Creator restored.", creatorLibraryMergeUnavailable: "Creator merge is unavailable. Refresh the page and try again.", creatorLibraryStatusSaved: "Creator status saved.", creatorLibraryMoreFiltersClose: "Show fewer filters", creatorLibraryMoreFiltersOpen: "More filters",
  });

  Object.assign(dictionaries.zh, {
    creatorLibraryTitle: "达人库", creatorLibrarySubtitle: "集中查看已从 KOL Connect 插件导入的达人分析，并在本地记录合作进度。", creatorLibrarySearch: "搜索达人", creatorLibrarySearchPlaceholder: "达人名称、邮箱、主页链接或标签", creatorLibraryCountryRegion: "国家/地区", creatorLibraryContentCategory: "内容类型", creatorLibraryTag: "标签", creatorLibraryFollowersMinimum: "最少粉丝", creatorLibraryFollowersMaximum: "最多粉丝", creatorLibraryFollowersMinimumPlaceholder: "例如 100K", creatorLibraryFollowersMaximumPlaceholder: "例如 1M", creatorLibraryInsightLevel: "Insight 等级", creatorLibraryAllLevels: "全部等级", creatorLibrarySort: "排序", creatorLibrarySortCreatedDesc: "创建时间（最新添加）", creatorLibrarySortCreatedAsc: "创建时间（最早添加）", creatorLibrarySortUpdatedDesc: "更新时间（最近更新）", creatorLibrarySortUpdatedAsc: "更新时间（最早更新）", creatorLibrarySortNameAsc: "达人名称（A-Z / 拼音）", creatorLibrarySortNameDesc: "达人名称（Z-A / 拼音倒序）", creatorLibrarySortFollowersDesc: "粉丝数（高到低）", creatorLibrarySortFollowersAsc: "粉丝数（低到高）", creatorLibrarySortPlatformAsc: "平台（Instagram → TikTok → YouTube）", creatorLibrarySortPlatformDesc: "平台（YouTube → TikTok → Instagram）", creatorLibraryPerPage: "每页显示", creatorLibraryCurrentStatus: "当前状态", creatorLibraryAllStatuses: "全部状态", creatorLibraryViewMode: "达人库视图", creatorLibraryCardView: "卡片", creatorLibraryTableView: "表格", creatorLibrarySelectPage: "本页全选", creatorLibraryDownloadTemplate: "下载模板", creatorLibraryImportExcel: "导入 Excel", creatorLibraryRefresh: "刷新达人库", creatorLibraryImportResult: "Excel 导入结果", creatorLibrarySelect: "选择", creatorLibraryCreatorName: "达人名称", commonPlatform: "平台", creatorLibraryProfileUrl: "主页链接", creatorLibraryFollowerCount: "粉丝数", creatorLibraryMedianViews: "中位播放", creatorLibraryFollowerChange: "粉丝变化", creatorLibraryMedianViewChange: "中位播放变化", creatorLibraryScoreChange: "评分变化", creatorLibraryLatestAnalysis: "最新分析时间", creatorLibraryDataUpdated: "数据更新时间", commonActions: "操作", creatorLibraryEmpty: "暂无达人分析数据。请先在插件中导入达人。",
  });
  Object.assign(dictionaries.en, {
    creatorLibraryTitle: "Creator Library", creatorLibrarySubtitle: "Review creator analyses imported from the KOL Connect extension and record partnership progress locally.", creatorLibrarySearch: "Search creators", creatorLibrarySearchPlaceholder: "Creator name, email, profile URL, or tag", creatorLibraryCountryRegion: "Country/Region", creatorLibraryContentCategory: "Content category", creatorLibraryTag: "Tag", creatorLibraryFollowersMinimum: "Minimum followers", creatorLibraryFollowersMaximum: "Maximum followers", creatorLibraryFollowersMinimumPlaceholder: "For example, 100K", creatorLibraryFollowersMaximumPlaceholder: "For example, 1M", creatorLibraryInsightLevel: "Insight level", creatorLibraryAllLevels: "All levels", creatorLibrarySort: "Sort", creatorLibrarySortCreatedDesc: "Created time (newest first)", creatorLibrarySortCreatedAsc: "Created time (oldest first)", creatorLibrarySortUpdatedDesc: "Updated time (newest first)", creatorLibrarySortUpdatedAsc: "Updated time (oldest first)", creatorLibrarySortNameAsc: "Creator name (A-Z)", creatorLibrarySortNameDesc: "Creator name (Z-A)", creatorLibrarySortFollowersDesc: "Followers (high to low)", creatorLibrarySortFollowersAsc: "Followers (low to high)", creatorLibrarySortPlatformAsc: "Platform (Instagram → TikTok → YouTube)", creatorLibrarySortPlatformDesc: "Platform (YouTube → TikTok → Instagram)", creatorLibraryPerPage: "Per page", creatorLibraryCurrentStatus: "Current status", creatorLibraryAllStatuses: "All statuses", creatorLibraryViewMode: "Creator Library view", creatorLibraryCardView: "Cards", creatorLibraryTableView: "Table", creatorLibrarySelectPage: "Select page", creatorLibraryDownloadTemplate: "Download template", creatorLibraryImportExcel: "Import Excel", creatorLibraryRefresh: "Refresh Creator Library", creatorLibraryImportResult: "Excel import results", creatorLibrarySelect: "Select", creatorLibraryCreatorName: "Creator name", commonPlatform: "Platform", creatorLibraryProfileUrl: "Profile URL", creatorLibraryFollowerCount: "Followers", creatorLibraryMedianViews: "Median views", creatorLibraryFollowerChange: "Follower change", creatorLibraryMedianViewChange: "Median view change", creatorLibraryScoreChange: "Score change", creatorLibraryLatestAnalysis: "Latest analysis time", creatorLibraryDataUpdated: "Data updated", commonActions: "Actions", creatorLibraryEmpty: "No creator analysis data yet. Import creators from the extension first.",
  });

  Object.assign(dictionaries.zh, {
    commonCancel: "取消", campaignDetailCurrencyUsd: "USD · 美元", campaignDetailCurrencyBrl: "BRL · 巴西雷亚尔", campaignDetailCurrencyCny: "CNY · 人民币", campaignDetailCurrencyEur: "EUR · 欧元", campaignDetailCurrencyGbp: "GBP · 英镑", campaignDetailCurrencyJpy: "JPY · 日元", campaignDetailCurrencyKrw: "KRW · 韩元", campaignDetailIntro: "查看项目信息、参与达人和执行结果。", campaignDetailBack: "返回 Campaign 列表", campaignDetailDelete: "删除 Campaign", campaignDetailLoading: "正在加载 Campaign 详情...", campaignDetailRetry: "重新加载", campaignDetailOverview: "项目概览", campaignDetailGoal: "Campaign 目标", campaignDetailReadOnly: "此 Campaign 已归档，当前不可新增或编辑合作记录；仍可移除达人关系或删除 Campaign。", campaignDetailMissingPublish: "缺失发布信息", campaignDetailInitialRecordCount: "0 条", campaignDetailTableCampaign: "Campaign", campaignDetailTableCreator: "Creator", campaignDetailTableStage: "Stage", campaignDetailTablePublishDate: "Publish Date", campaignDetailTablePublishLink: "Publish Link", campaignDetailTableRisk: "Risk", campaignDetailPublishedPerformance: "发布内容表现", campaignDetailRefreshAll: "刷新全部", campaignDetailPerformanceHint: "显示每条实际发布内容最近一次可靠观察；缺失指标不会显示为 0。", campaignDetailTotalViewsLabel: "总播放", campaignDetailTotalLikesLabel: "总点赞", campaignDetailTotalCommentsLabel: "总评论", campaignDetailAverageEngagement: "平均互动率", campaignDetailInitialCoverage: "0 / 0 条有数据", campaignDetailInitialMoneySummary: "确认成本：— · 历史报价：— · ROI：—（缺少权威回报数据）", campaignDetailNoPublications: "暂无实际发布内容。", campaignDetailCreatorManagement: "达人合作管理", campaignDetailInitialCreatorCount: "0 位达人", campaignDetailCreatorRequiredLabel: "达人 *", campaignDetailPlannedAccountRequiredLabel: "计划发布账号 *", campaignDetailSelectCreatorFirst: "请先选择达人", campaignDetailAccountPickerHint: "勾选后立即生效，可选择多个符合 Campaign 平台的账号。", campaignDetailStage: "合作阶段", campaignDetailQuoteCurrency: "报价币种", campaignDetailQuoteUnitAmount: "报价单价", campaignDetailQuantity: "数量", campaignDetailPricingUnit: "计价单位", campaignDetailSelect: "请选择", campaignDetailCreatorQuoteTotal: "达人报价总额", campaignDetailQuoteTotalHint: "由单价 × 数量自动计算；旧记录可保留 total-only。", campaignDetailActualCost: "实际成本", campaignDetailCostCurrency: "成本币种", campaignDetailPlannedPublishDate: "计划发布日期", campaignDetailAddDate: "+ 添加日期", campaignDetailSaveRate: "保存汇率", campaignDetailActualPublications: "实际发布内容", campaignDetailActualPublicationHint: "实际发布账号和时间独立于计划；未知信息可留空。", campaignDetailAddActualPublication: "+ 添加实际发布内容", campaignDetailPerformanceReview: "效果复盘", campaignDetailViewCount: "播放量", campaignDetailLikeCount: "点赞数", campaignDetailCommentCount: "评论数", campaignDetailPerformanceNote: "复盘备注", campaignDetailNoCreators: "暂无参与达人。点击“添加达人”建立第一条合作记录。", campaignDetailCreatorName: "达人名称", campaignDetailExecutionAccount: "执行账号", campaignDetailQuote: "报价", campaignDetailCost: "成本", campaignDetailPublishLinks: "发布链接", campaignDetailBrief: "Campaign Brief", campaignDetailBriefTitle: "Brief 标题", campaignDetailPlatformGuidance: "平台指引", campaignDetailCoreSellingPoints: "核心卖点", campaignDetailMustInclude: "必须包含", campaignDetailMustAvoid: "禁止表达", campaignDetailBrandRequirements: "品牌要求", campaignDetailContentRequirements: "内容要求", campaignDetailPublishingRequirements: "发布要求", campaignDetailReferenceNotes: "参考 / 备注", campaignDetailSaveBrief: "保存 Brief", campaignDetailContentReview: "内容提交与人工审核", campaignDetailHumanReviewHint: "AI 一审为未来可选辅助，人工审核始终是最终状态。", campaignDetailPartnerCreator: "合作达人", campaignDetailContentType: "内容类型", campaignDetailContentScript: "脚本", campaignDetailContentCopy: "文案", campaignDetailContentVideoDraft: "视频审核稿", campaignDetailContentOther: "其他", campaignDetailContentReference: "内容 / 文件引用", campaignDetailSubmitForReview: "提交审核内容",
  });
  Object.assign(dictionaries.en, {
    commonCancel: "Cancel", campaignDetailCurrencyUsd: "USD · US Dollar", campaignDetailCurrencyBrl: "BRL · Brazilian Real", campaignDetailCurrencyCny: "CNY · Chinese Yuan", campaignDetailCurrencyEur: "EUR · Euro", campaignDetailCurrencyGbp: "GBP · British Pound", campaignDetailCurrencyJpy: "JPY · Japanese Yen", campaignDetailCurrencyKrw: "KRW · Korean Won", campaignDetailIntro: "Review Campaign information, participating creators, and execution results.", campaignDetailBack: "Back to Campaigns", campaignDetailDelete: "Delete Campaign", campaignDetailLoading: "Loading Campaign details...", campaignDetailRetry: "Reload", campaignDetailOverview: "Campaign overview", campaignDetailGoal: "Campaign goal", campaignDetailReadOnly: "This Campaign is archived. Partnership records cannot be added or edited, but creator relationships can still be removed and the Campaign can be deleted.", campaignDetailMissingPublish: "Missing publication information", campaignDetailInitialRecordCount: "0 records", campaignDetailTableCampaign: "Campaign", campaignDetailTableCreator: "Creator", campaignDetailTableStage: "Stage", campaignDetailTablePublishDate: "Publish date", campaignDetailTablePublishLink: "Publish link", campaignDetailTableRisk: "Risk", campaignDetailPublishedPerformance: "Published content performance", campaignDetailRefreshAll: "Refresh all", campaignDetailPerformanceHint: "Shows the latest reliable observation for each actual publication; missing metrics are not shown as zero.", campaignDetailTotalViewsLabel: "Total views", campaignDetailTotalLikesLabel: "Total likes", campaignDetailTotalCommentsLabel: "Total comments", campaignDetailAverageEngagement: "Average engagement rate", campaignDetailInitialCoverage: "0 / 0 with data", campaignDetailInitialMoneySummary: "Confirmed cost: — · Historical quote: — · ROI: — (no authoritative return data)", campaignDetailNoPublications: "No actual publications.", campaignDetailCreatorManagement: "Creator partnership management", campaignDetailInitialCreatorCount: "0 creators", campaignDetailCreatorRequiredLabel: "Creator *", campaignDetailPlannedAccountRequiredLabel: "Planned publishing accounts *", campaignDetailSelectCreatorFirst: "Select a creator first", campaignDetailAccountPickerHint: "Selections apply immediately. Multiple accounts matching the Campaign platform can be selected.", campaignDetailStage: "Partnership stage", campaignDetailQuoteCurrency: "Quote currency", campaignDetailQuoteUnitAmount: "Quote unit amount", campaignDetailQuantity: "Quantity", campaignDetailPricingUnit: "Pricing unit", campaignDetailSelect: "Select", campaignDetailCreatorQuoteTotal: "Creator quote total", campaignDetailQuoteTotalHint: "Calculated from unit amount × quantity; legacy total-only records remain valid.", campaignDetailActualCost: "Actual cost", campaignDetailCostCurrency: "Cost currency", campaignDetailPlannedPublishDate: "Planned publish dates", campaignDetailAddDate: "+ Add date", campaignDetailSaveRate: "Save rate", campaignDetailActualPublications: "Actual publications", campaignDetailActualPublicationHint: "Actual account and time are independent of the plan; unknown information may be left blank.", campaignDetailAddActualPublication: "+ Add actual publication", campaignDetailPerformanceReview: "Performance review", campaignDetailViewCount: "Views", campaignDetailLikeCount: "Likes", campaignDetailCommentCount: "Comments", campaignDetailPerformanceNote: "Performance notes", campaignDetailNoCreators: "No participating creators. Select Add creator to create the first partnership record.", campaignDetailCreatorName: "Creator name", campaignDetailExecutionAccount: "Execution account", campaignDetailQuote: "Quote", campaignDetailCost: "Cost", campaignDetailPublishLinks: "Publication links", campaignDetailBrief: "Campaign Brief", campaignDetailBriefTitle: "Brief title", campaignDetailPlatformGuidance: "Platform guidance", campaignDetailCoreSellingPoints: "Core selling points", campaignDetailMustInclude: "Must include", campaignDetailMustAvoid: "Must avoid", campaignDetailBrandRequirements: "Brand requirements", campaignDetailContentRequirements: "Content requirements", campaignDetailPublishingRequirements: "Publishing requirements", campaignDetailReferenceNotes: "References / notes", campaignDetailSaveBrief: "Save Brief", campaignDetailContentReview: "Content submissions and human review", campaignDetailHumanReviewHint: "AI first pass is an optional future aid; human review remains the final status.", campaignDetailPartnerCreator: "Partner creator", campaignDetailContentType: "Content type", campaignDetailContentScript: "Script", campaignDetailContentCopy: "Copy", campaignDetailContentVideoDraft: "Video review draft", campaignDetailContentOther: "Other", campaignDetailContentReference: "Content / file reference", campaignDetailSubmitForReview: "Submit for review",
  });

  Object.assign(dictionaries.zh, {
    campaignDetailEyebrow: "CAMPAIGN 详情", campaignDetailOverviewEyebrow: "CAMPAIGN 概览", campaignDetailPublishingRisksEyebrow: "发布风险", campaignDetailPublishedContentEyebrow: "已发布内容", campaignDetailCreatorManagementEyebrow: "达人合作管理", campaignDetailBriefEyebrow: "CAMPAIGN Brief", campaignDetailContentReviewEyebrow: "内容审核", campaignDetailAgency: "Agency",
    campaignDetailUnitVideo: "视频", campaignDetailUnitPost: "帖子", campaignDetailUnitReel: "Reel", campaignDetailUnitShort: "短视频", campaignDetailUnitStory: "Story", campaignDetailUnitPackage: "套餐", campaignDetailUnitOther: "其他",
  });
  Object.assign(dictionaries.en, {
    campaignDetailEyebrow: "CAMPAIGN DETAIL", campaignDetailOverviewEyebrow: "CAMPAIGN OVERVIEW", campaignDetailPublishingRisksEyebrow: "PUBLISHING RISKS", campaignDetailPublishedContentEyebrow: "PUBLISHED CONTENT", campaignDetailCreatorManagementEyebrow: "CREATOR MANAGEMENT", campaignDetailBriefEyebrow: "CAMPAIGN BRIEF", campaignDetailContentReviewEyebrow: "CONTENT REVIEW", campaignDetailAgency: "Agency",
    campaignDetailUnitVideo: "Video", campaignDetailUnitPost: "Post", campaignDetailUnitReel: "Reel", campaignDetailUnitShort: "Short", campaignDetailUnitStory: "Story", campaignDetailUnitPackage: "Package", campaignDetailUnitOther: "Other",
  });

  Object.assign(dictionaries.zh, {
    dashboardModuleToday: "今日待处理", dashboardModuleTodayDescription: "可直接进入待联系或数据过期对象",
    dashboardModuleMailFollowUp: "邮件跟进", dashboardModuleMailFollowUpDescription: "按已同步邮件记录查看当前待处理联系人",
    dashboardModuleMissingInfo: "待补充信息", dashboardModuleMissingInfoDescription: "账号邮箱与达人基础资料缺口",
    dashboardModuleCampaigns: "Campaign 概览", dashboardModuleCampaignsDescription: "项目成员与发布进度",
    dashboardModuleCreatorOverview: "达人数据概览", dashboardModuleCreatorOverviewDescription: "Creator 与平台账号构成",
    dashboardModuleDataFreshness: "数据更新状态", dashboardModuleDataFreshnessDescription: "快照新鲜度与现有趋势",
    dashboardModuleGeography: "地区与语言", dashboardModuleGeographyDescription: "已录入 Creator 基础资料分布",
    dashboardModuleRoi: "ROI / Performance", dashboardModuleRoiDescription: "仅展示已录入的表现数据",
    dashboardCreatorCount: "达人数量", dashboardNewCreators: "新增达人", dashboardUnnamedCreator: "未命名达人",
    dashboardNoRisingCreators: "暂无上升达人。", dashboardNoFallingCreators: "暂无下滑达人。", dashboardNoExpiredData: "暂无过期数据。",
    dashboardNoDataToUpdate: "暂无需要更新的数据。", dashboardNoPendingContact: "暂无待联系达人。", dashboardNoReviewItems: "暂无待复盘事项。",
    dashboardNoCooperationData: "暂无合作数据。", dashboardRecentAnalysis: "最近分析：{time}", dashboardExpiredDays: "已过期 {days} 天",
    dashboardPendingContactStatus: "状态：待联系", dashboardCampaignLabel: "Campaign：{campaign}", dashboardUnnamedCampaign: "未命名 Campaign",
    dashboardRoiUnavailable: "ROI 暂无", dashboardRoiValue: "ROI {value}", dashboardAverageRecordedRoi: "平均已记录 ROI", dashboardOtherUnknown: "其他/未知", dashboardUnknown: "未知", dashboardCampaignSummary: "{count} 个 Campaign · {roi}", dashboardHomepageUnavailable: "主页链接未录入",
    dashboardDataExpired: "数据过期", dashboardPendingContact: "待联系", dashboardWaitingToConnect: "等待建立联系",
    dashboardNoPriorityItems: "暂无需要优先处理的事项。", dashboardUnnamedObject: "未命名对象", dashboardNoCampaigns: "暂无 Campaign。",
    dashboardCampaignProgress: "{status} · {creators} 位达人 · 已发布 {published}", dashboardNoPlatformAccounts: "暂无平台账号数据。",
    dashboardOtherPlatform: "其他", dashboardAccountCount: "{count} 个账号", dashboardHealthScore: "{score} 分", dashboardNoData: "暂无数据",
    dashboardDrawerCount: "共 {count} {unit}", dashboardNoSearchMatches: "没有符合当前搜索条件的对象。", dashboardAccountUnavailable: "账号信息未录入",
    dashboardCountryLanguageMissing: "国家/语言待补充", dashboardViewCreator: "查看达人", dashboardMissingEmailAccounts: "缺少邮箱的账号",
    dashboardMissingCountryCreators: "缺少国家/地区的达人", dashboardMissingLanguageCreators: "缺少语言的达人", dashboardMissingContentTypeCreators: "缺少内容类型的达人",
    dashboardAccountUnit: "个账号", dashboardCreatorUnit: "位达人", dashboardBulkFillEmail: "批量补全邮箱", dashboardCreatorChart: "达人",
    dashboardCooperationChart: "合作", dashboardPublishedChart: "已发布", dashboardActiveCreators: "活跃 {count}", dashboardNoRecordedRoi: "暂无已录入 ROI",
    dashboardTitle: "工作台", dashboardSubtitle: "从当前数据进入具体达人、账号与合作事项。", dashboardCustomize: "自定义工作台", dashboardRefreshData: "刷新数据", dashboardEyebrow: "KOL 运营", dashboardTodayEyebrow: "今日", dashboardMailEyebrow: "邮件跟进", dashboardDataCompletenessEyebrow: "数据完整度", dashboardCampaignsEyebrow: "Campaign", dashboardCreatorLibraryEyebrow: "达人库", dashboardDataHealthEyebrow: "数据健康", dashboardGeographyEyebrow: "地区", dashboardPerformanceEyebrow: "已记录表现", dashboardCampaignLabelShort: "Campaign",
    dashboardAriaLabel: "KOL 运营工作台", dashboardCoreSummary: "核心业务摘要", dashboardCreators: "达人", dashboardCreatorUnitLabel: "位达人",
    dashboardPlatformAccounts: "平台账号", dashboardCreatorAccountUnitLabel: "个平台账号", dashboardSavedCampaigns: "个已保存项目",
    dashboardCooperationSpend: "合作花费", dashboardGroupedByCurrency: "按币种分组", dashboardRecordedRoi: "已录入 ROI", dashboardNoAutomaticConversion: "不自动换算",
    dashboardOpenItems: "可直接进入对象", dashboardViewAll: "查看全部", dashboardMailSummary: "邮件跟进摘要", dashboardActionableTotal: "待处理总数",
    dashboardNoActionableMail: "暂无待处理邮件跟进。", dashboardMailUnavailable: "邮件跟进数据暂不可用。", dashboardActualFieldCounts: "按实际字段统计",
    dashboardMissingEmail: "缺邮箱", dashboardMissingCountry: "缺国家/地区", dashboardMissingLanguage: "缺语言", dashboardMissingContentType: "缺内容类型",
    dashboardViewAccounts: "查看账号", dashboardHealthy: "正常", dashboardTrendDeclining: "趋势下滑", dashboardHealthHint: "基于达人快照新鲜度与现有趋势数据，不代表合作履约评价。",
    dashboardRoiHint: "仅展示已录入的 ROI；多币种金额不做静默换算。", dashboardCustomizationHint: "选择显示内容并调整排列顺序，仅保存在当前设备浏览器中。",
    dashboardRestoreDefaultLayout: "恢复默认布局", dashboardDone: "完成", dashboardDetails: "明细", dashboardSearchCreatorOrAccount: "搜索达人或账号", dashboardSearchPlaceholder: "输入名称、平台或账号名",
    dashboardClose: "关闭", dashboardCountryRegion: "国家/地区", dashboardLanguage: "语言",
  });
  Object.assign(dictionaries.en, {
    dashboardModuleToday: "Today's action items", dashboardModuleTodayDescription: "Open contacts awaiting action or expired data directly",
    dashboardModuleMailFollowUp: "Mail follow-up", dashboardModuleMailFollowUpDescription: "Review contacts awaiting action from synced mail records",
    dashboardModuleMissingInfo: "Missing information", dashboardModuleMissingInfoDescription: "Gaps in account email and creator profile data",
    dashboardModuleCampaigns: "Campaign overview", dashboardModuleCampaignsDescription: "Project members and publication progress",
    dashboardModuleCreatorOverview: "Creator overview", dashboardModuleCreatorOverviewDescription: "Creator and platform account composition",
    dashboardModuleDataFreshness: "Data freshness", dashboardModuleDataFreshnessDescription: "Snapshot freshness and available trends",
    dashboardModuleGeography: "Regions and languages", dashboardModuleGeographyDescription: "Distribution of recorded creator profile data",
    dashboardModuleRoi: "ROI / Performance", dashboardModuleRoiDescription: "Shows only recorded performance data",
    dashboardCreatorCount: "Creator count", dashboardNewCreators: "New creators", dashboardUnnamedCreator: "Unnamed creator",
    dashboardNoRisingCreators: "No rising creators.", dashboardNoFallingCreators: "No declining creators.", dashboardNoExpiredData: "No expired data.",
    dashboardNoDataToUpdate: "No data needs updating.", dashboardNoPendingContact: "No creators awaiting contact.", dashboardNoReviewItems: "No items awaiting review.",
    dashboardNoCooperationData: "No partnership data.", dashboardRecentAnalysis: "Last analysis: {time}", dashboardExpiredDays: "Expired {days} days ago",
    dashboardPendingContactStatus: "Status: awaiting contact", dashboardCampaignLabel: "Campaign: {campaign}", dashboardUnnamedCampaign: "Unnamed Campaign",
    dashboardRoiUnavailable: "ROI unavailable", dashboardRoiValue: "ROI {value}", dashboardAverageRecordedRoi: "Average recorded ROI", dashboardOtherUnknown: "Other/unknown", dashboardUnknown: "Unknown", dashboardCampaignSummary: "{count} Campaigns · {roi}", dashboardHomepageUnavailable: "Profile URL is unavailable",
    dashboardDataExpired: "Data expired", dashboardPendingContact: "Awaiting contact", dashboardWaitingToConnect: "Waiting to establish contact",
    dashboardNoPriorityItems: "No priority items.", dashboardUnnamedObject: "Unnamed item", dashboardNoCampaigns: "No Campaigns.",
    dashboardCampaignProgress: "{status} · {creators} creators · {published} published", dashboardNoPlatformAccounts: "No platform account data.",
    dashboardOtherPlatform: "Other", dashboardAccountCount: "{count} accounts", dashboardHealthScore: "{score} points", dashboardNoData: "No data yet",
    dashboardDrawerCount: "{count} {unit} total", dashboardNoSearchMatches: "No items match the current search.", dashboardAccountUnavailable: "Account information is unavailable",
    dashboardCountryLanguageMissing: "Country/language needs completion", dashboardViewCreator: "View creator", dashboardMissingEmailAccounts: "Accounts missing email",
    dashboardMissingCountryCreators: "Creators missing country/region", dashboardMissingLanguageCreators: "Creators missing language", dashboardMissingContentTypeCreators: "Creators missing content category",
    dashboardAccountUnit: "accounts", dashboardCreatorUnit: "creators", dashboardBulkFillEmail: "Fill emails in bulk", dashboardCreatorChart: "Creators",
    dashboardCooperationChart: "Partnerships", dashboardPublishedChart: "Published", dashboardActiveCreators: "Active {count}", dashboardNoRecordedRoi: "No recorded ROI",
    dashboardTitle: "Dashboard", dashboardSubtitle: "Open the relevant creators, accounts, and partnership items from current data.", dashboardCustomize: "Customize dashboard", dashboardRefreshData: "Refresh data", dashboardEyebrow: "KOL operations", dashboardTodayEyebrow: "Today", dashboardMailEyebrow: "Mail follow-up", dashboardDataCompletenessEyebrow: "Data completeness", dashboardCampaignsEyebrow: "Campaigns", dashboardCreatorLibraryEyebrow: "Creator Library", dashboardDataHealthEyebrow: "Data health", dashboardGeographyEyebrow: "Geography", dashboardPerformanceEyebrow: "Recorded performance", dashboardCampaignLabelShort: "Campaign",
    dashboardAriaLabel: "KOL operations dashboard", dashboardCoreSummary: "Core business summary", dashboardCreators: "Creators", dashboardCreatorUnitLabel: "Creator records",
    dashboardPlatformAccounts: "Platform accounts", dashboardCreatorAccountUnitLabel: "CreatorAccount records", dashboardSavedCampaigns: "saved Campaigns",
    dashboardCooperationSpend: "Partnership spend", dashboardGroupedByCurrency: "Grouped by currency", dashboardRecordedRoi: "Recorded ROI", dashboardNoAutomaticConversion: "No automatic conversion",
    dashboardOpenItems: "Open items directly", dashboardViewAll: "View all", dashboardMailSummary: "Mail follow-up summary", dashboardActionableTotal: "Actionable total",
    dashboardNoActionableMail: "No actionable mail follow-up items.", dashboardMailUnavailable: "Mail follow-up data is unavailable.", dashboardActualFieldCounts: "Counted from recorded fields",
    dashboardMissingEmail: "Missing email", dashboardMissingCountry: "Missing country/region", dashboardMissingLanguage: "Missing language", dashboardMissingContentType: "Missing content category",
    dashboardViewAccounts: "View accounts", dashboardHealthy: "Healthy", dashboardTrendDeclining: "Declining trend", dashboardHealthHint: "Based on creator snapshot freshness and available trends; it is not a partnership fulfillment assessment.",
    dashboardRoiHint: "Shows only recorded ROI; amounts in multiple currencies are not silently converted.", dashboardCustomizationHint: "Choose visible modules and their order. This setting is stored only in the current device browser.",
    dashboardRestoreDefaultLayout: "Restore default layout", dashboardDone: "Done", dashboardDetails: "Details", dashboardSearchCreatorOrAccount: "Search creators or accounts", dashboardSearchPlaceholder: "Enter a name, platform, or account name",
    dashboardClose: "Close", dashboardCountryRegion: "Country/region", dashboardLanguage: "Language",
  });

  Object.assign(dictionaries.zh, {
    creatorHistoryCooperations: "合作次数", creatorHistoryCooperationsHint: "按 CampaignCreator 去重", creatorHistoryCampaigns: "历史 Campaign",
    creatorHistoryCampaignsHint: "按 campaign_id 去重", creatorHistoryAverageViews: "平均播放", creatorHistoryAverageEngagement: "平均互动率",
    creatorHistoryCoverage: "{valid} / {total} 条有数据", creatorHistoryMoneyEfficiency: "金额与效率",
    creatorHistoryMoneySummary: "确认成本：{cost} · 历史报价：{quote} · 未知币种成本/报价记录 {unknownCost}/{unknownQuote}（不纳入币种汇总）",
    creatorHistoryEfficiency: "{currency} · CPV {cpv} · CPE {cpe}", creatorHistoryRoiUnavailable: "ROI：--（缺少权威回报数据）",
    creatorHistoryNoCampaigns: "暂无 Campaign 历史。", creatorHistoryDateUnknown: "日期未记录", creatorDateRange: "{start} 至 {end}", creatorSummaryTimeUnknown: "时间未知",
    creatorFreshnessRecent: "数据较新", creatorFreshnessRecommended: "建议更新数据", creatorFreshnessStaleDecision: "数据更新时间较早，请在决策前重新采集",
    creatorFreshnessUnknown: "数据更新时间未知", creatorSummaryGenerate: "生成摘要", creatorSummaryRegenerate: "重新生成",
    creatorSummaryPrompt: "点击“生成摘要”查看本地确定性分析。", creatorSummaryInsufficient: "数据不足。当前缺少可用于表现分析的数据。",
    creatorSummaryPartial: "摘要已生成，部分数据仍待补充。", creatorSummaryComplete: "摘要已生成。", creatorSummaryGenerating: "正在生成本地摘要...",
    creatorSummaryUnavailable: "摘要暂时无法生成，原始达人资料仍可正常查看", creatorSummaryNoFacts: "暂无可展示的事实摘要。",
    creatorSummaryNoLimits: "当前未发现额外数据限制。", creatorDataSufficient: "数据较完整", creatorDataPartial: "部分数据可用", creatorDataInsufficient: "数据不足",
    creatorFieldName: "达人名称", creatorFieldPlatform: "平台", creatorFieldFollowers: "粉丝数", creatorFieldCountry: "国家/地区", creatorFieldLanguage: "语言",
    creatorFieldContentType: "内容类型", creatorFieldAverageViews: "平均播放", creatorFieldMedianViews: "中位播放", creatorFieldVideoCount: "视频数量", creatorFieldScore: "达人评分",
    creatorFieldStability: "稳定性", creatorFieldProfileUrl: "主页链接", creatorFieldEmail: "邮箱", creatorFieldBio: "简介", creatorFieldSampleSize: "样本数量",
    creatorFieldMaxViews: "最高播放", creatorFieldMinViews: "最低播放", creatorFieldViewStability: "播放稳定性", creatorFieldViewCoverage: "播放完整率",
    creatorVideo: "视频", creatorVideoMetrics: "播放 {views} · 点赞 {likes} · 评论 {comments}", creatorCampaignLoadFailed: "Campaign 数据加载失败。",
    creatorCampaignView: "查看 Campaign", creatorDataMeta: "数据更新时间：{updatedAt} · 来源：{source} · 最近分析时间：{analyzedAt}",
    creatorManualReview: "请结合主页内容进行人工判断。", creatorNoStrengths: "暂无优势结论。", creatorNoRisks: "暂无风险结论。",
    creatorRestore: "恢复达人", creatorArchive: "归档达人", creatorReviewTaskMissing: "未找到关联的审核任务。", creatorReviewTaskOpened: "已打开关联的审核任务。",
    creatorArchivedCampaignBlocked: "已归档达人需恢复后才能加入 Campaign。", creatorNoAgency: "未关联 Agency", creatorUnnamedAgency: "未命名 Agency", creatorSummarySourceSnapshot: "快照", creatorSummarySourceInsights: "洞察",
    creatorNoAccounts: "暂无已关联的平台账号。", creatorProfileUrlUnavailable: "主页链接不可用", creatorUnlinkAccount: "移除关联",
    creatorAgencyLoadFailed: "Agency 列表加载失败。", creatorProfileSaved: "达人资料已保存。", creatorProfileSaveFailed: "达人资料保存失败。",
    creatorRestoreConfirm: "恢复该达人到默认达人库？", creatorArchiveConfirm: "归档后，达人将从默认列表隐藏，Campaign、Snapshot 和 Insight 数据会保留。",
    creatorRestored: "达人已恢复。", creatorArchived: "达人已归档。", creatorProfileUrlRequired: "请输入主页链接。",
    creatorAccountAlreadyLinked: "该账号已经属于当前达人。", creatorAccountLinked: "平台账号已关联。", creatorAccountOwnedBy: "该账号已属于【{creator}】。",
    creatorAnotherCreator: "另一位达人", creatorViewExistingCreator: "查看现有达人", creatorMergeCreator: "合并达人", creatorAccountLinkFailed: "账号关联失败。",
    creatorAccountRemoveConfirm: "移除仅允许无历史引用的账号；已有合作或表现历史的账号会被安全保留。", creatorAccountRemoved: "平台账号已移除。",
    creatorAccountRemoveBlocked: "该账号无法移除。", creatorSimilarityMethod: "仅基于本地达人库的结构化证据评分；缺失维度不计零分。",
    creatorNoSimilarCandidates: "暂无具备可用匹配证据的本地达人。", creatorSimilarityScore: "相似度 {score}% · 可用证据权重 {weight}/100",
    creatorSimilarityUnavailable: "相似度 -- · 可比证据不足", creatorHistoricalEvidence: "历史证据（不改变评分）：{cooperations} 次合作 · {publications} 条发布 · 平均播放 {views} · 平均 ER {er}",
    creatorDimensionTag: "标签", creatorDimensionContent: "内容", creatorDimensionFollowers: "粉丝", creatorDimensionPrice: "报价", creatorDimensionEngagement: "互动率",
    creatorDimensionCountryLanguage: "国家/语言", creatorDimensionPlatform: "平台", creatorSimilarityExcluded: "未纳入评分：{dimensions}",
    creatorSimilarityAllComparable: "所有维度均有可比证据", creatorCountryLanguageMissing: "国家/语言缺项：{dimensions}",
    creatorAiSupplement: "AI 补充说明（不改变评分）：{text}", creatorSimilaritySearching: "正在查找本地达人库候选...",
    creatorSimilaritySummary: "本地候选 {total} 个，展示 {shown} 个；按确定性评分排序，缺失证据不计零分。", creatorSimilarityFailed: "相似达人搜索失败。",
    creatorMissingId: "缺少 Creator ID，请返回达人库重新进入。",
    creatorDetailTitle: "达人分析", creatorBackToLibrary: "返回达人库", creatorEditProfile: "编辑资料", creatorAddCampaign: "加入 Campaign",
    creatorFindSimilar: "查找相似达人", creatorCreateTask: "创建合作任务", creatorSocialAccounts: "社媒账号", creatorSocialAccountsHint: "切换账号查看对应平台资料和表现数据。",
    creatorSocialAccountsAria: "达人社媒账号", creatorNoSocialAccounts: "暂无可用社媒账号。", creatorDetailTabs: "达人详情", creatorOverview: "概览",
    creatorContentPerformance: "内容表现", creatorHistoryTrend: "历史趋势", creatorBasicInformation: "基础信息", creatorVideoAnalysis: "视频分析", creatorDataUpdated: "数据更新时间", creatorFactSummary: "事实摘要",
    creatorDataFreshness: "数据新鲜度", creatorSimilarCandidates: "相似达人候选", creatorCampaignParticipation: "参与 Campaign",
    creatorCampaignParticipationHint: "当前达人已加入的 Campaign，不包含旧版合作记录。", creatorNoCampaignParticipation: "暂未加入 Campaign。",
    creatorAiSummary: "AI 达人摘要", creatorAiDisclosure: "当前为本地规则生成，未连接真实 AI", creatorBasicProfile: "基础资料",
    creatorPerformanceData: "表现数据", creatorDataStatus: "数据状态", creatorDataLimitations: "数据限制", creatorStrengths: "优势", creatorRisks: "风险",
    creatorRecentVideos: "最近视频", creatorPerformanceHistory: "合作表现历史", creatorPerformanceHistoryHint: "基于实际发布内容的最近有效观察；金额按币种分组，不进行汇率换算。",
    creatorNoPerformanceHistory: "暂无可用合作表现历史。", creatorHistoricalAnalysis: "历史分析", creatorNoSnapshots: "暂无历史 Snapshot 数据。",
    creatorEditTitle: "编辑达人资料", creatorBasicProfileTitle: "基本资料", creatorWhatsAppOptional: "可留空", creatorImproveAnalysisHint: "完善国家和语言信息，可提升达人分析准确度。",
    creatorAccountIdentityHint: "主页链接用于识别平台和账号身份，无需填写内部 ID。", creatorAccountUrlPlaceholder: "粘贴 TikTok、Instagram 或 YouTube 主页链接",
    creatorAddProfileUrl: "+ 添加主页链接", creatorSaveProfile: "保存资料",
    creatorInsight: "Creator Insight", creatorCampaignColumn: "Campaign", creatorProductColumn: "产品", creatorStatusColumn: "状态", creatorDateColumn: "日期", creatorAiTags: "AI 标签", creatorContentCategories: "内容分类", creatorAudienceSignals: "受众信号", creatorContentSignals: "内容信号", creatorFollowerBand: "粉丝区间", creatorEngagementBand: "互动率区间", creatorPriceBand: "报价区间", creatorConfidence: "可信度", creatorSnapshotTime: "时间", creatorSnapshotFollowers: "粉丝", creatorSnapshotScore: "评分", creatorSnapshotInsight: "Insight",
    creatorCampaignModalTitle: "加入 Campaign", creatorBatchCampaignCount: "已选择 0 位达人", creatorCampaignSelectPlaceholder: "请选择 Campaign", creatorExecutionAccount: "执行账号", creatorExecutionAccountPlaceholder: "请选择执行账号", creatorExecutionAccountHint: "选择本次合作使用的社交账号。", creatorConfirmAdd: "确认加入", creatorPermanentDelete: "永久删除达人", creatorDeleteChecking: "正在检查永久删除影响...", creatorRecheckImpact: "重新检查影响", creatorConfirmPermanentDelete: "确认永久删除", creatorMergeTitle: "合并达人", creatorMergePrimary: "主达人 · 保留", creatorMergeSecondary: "待合并达人 · 合并后删除", creatorMergeNotSelected: "尚未选择", creatorMergeSearch: "搜索待合并达人", creatorMergeSearchPlaceholder: "名称、用户名、平台或主页链接", creatorMergeResultAccounts: "合并后账号", creatorMergeMigratedAccounts: "迁移账号", creatorMergeVideos: "视频", creatorMergeSnapshots: "Snapshots", creatorMergeCampaignRelations: "Campaign 关系", creatorPreviewMergeImpact: "预览合并影响", creatorConfirmMerge: "确认合并达人",
  });
  Object.assign(dictionaries.en, {
    creatorHistoryCooperations: "Partnerships", creatorHistoryCooperationsHint: "Deduplicated by CampaignCreator", creatorHistoryCampaigns: "Historical Campaigns",
    creatorHistoryCampaignsHint: "Deduplicated by campaign_id", creatorHistoryAverageViews: "Average views", creatorHistoryAverageEngagement: "Average engagement rate",
    creatorHistoryCoverage: "{valid} / {total} with data", creatorHistoryMoneyEfficiency: "Cost and efficiency",
    creatorHistoryMoneySummary: "Confirmed cost: {cost} · Historical quote: {quote} · Unknown-currency cost/quote records {unknownCost}/{unknownQuote} (excluded from currency totals)",
    creatorHistoryEfficiency: "{currency} · CPV {cpv} · CPE {cpe}", creatorHistoryRoiUnavailable: "ROI: -- (no authoritative return data)",
    creatorHistoryNoCampaigns: "No Campaign history.", creatorHistoryDateUnknown: "Date not recorded", creatorDateRange: "{start} to {end}", creatorSummaryTimeUnknown: "Time unknown",
    creatorFreshnessRecent: "Data is recent", creatorFreshnessRecommended: "Data update recommended", creatorFreshnessStaleDecision: "Data is outdated; collect it again before making a decision",
    creatorFreshnessUnknown: "Data update time is unknown", creatorSummaryGenerate: "Generate summary", creatorSummaryRegenerate: "Regenerate",
    creatorSummaryPrompt: "Select Generate summary to view deterministic local analysis.", creatorSummaryInsufficient: "Insufficient data. Performance analysis data is currently unavailable.",
    creatorSummaryPartial: "Summary generated; some data still needs completion.", creatorSummaryComplete: "Summary generated.", creatorSummaryGenerating: "Generating local summary...",
    creatorSummaryUnavailable: "The summary is temporarily unavailable; the original creator profile can still be viewed", creatorSummaryNoFacts: "No fact summary to display.",
    creatorSummaryNoLimits: "No additional data limitations found.", creatorDataSufficient: "Data is fairly complete", creatorDataPartial: "Partial data available", creatorDataInsufficient: "Insufficient data",
    creatorFieldName: "Creator name", creatorFieldPlatform: "Platform", creatorFieldFollowers: "Followers", creatorFieldCountry: "Country/region", creatorFieldLanguage: "Language",
    creatorFieldContentType: "Content category", creatorFieldAverageViews: "Average views", creatorFieldMedianViews: "Median views", creatorFieldVideoCount: "Video count", creatorFieldScore: "Creator score",
    creatorFieldStability: "Stability", creatorFieldProfileUrl: "Profile URL", creatorFieldEmail: "Email", creatorFieldBio: "Bio", creatorFieldSampleSize: "Sample size",
    creatorFieldMaxViews: "Maximum views", creatorFieldMinViews: "Minimum views", creatorFieldViewStability: "View stability", creatorFieldViewCoverage: "View coverage",
    creatorVideo: "Video", creatorVideoMetrics: "Views {views} · Likes {likes} · Comments {comments}", creatorCampaignLoadFailed: "Campaign data could not be loaded.",
    creatorCampaignView: "View Campaign", creatorDataMeta: "Data updated: {updatedAt} · Source: {source} · Last analysis: {analyzedAt}",
    creatorManualReview: "Review the profile content manually.", creatorNoStrengths: "No strengths available.", creatorNoRisks: "No risks available.",
    creatorRestore: "Restore creator", creatorArchive: "Archive creator", creatorReviewTaskMissing: "The linked review task was not found.", creatorReviewTaskOpened: "The linked review task is open.",
    creatorArchivedCampaignBlocked: "Restore the archived creator before adding it to a Campaign.", creatorNoAgency: "No Agency", creatorUnnamedAgency: "Unnamed Agency", creatorSummarySourceSnapshot: "Snapshot", creatorSummarySourceInsights: "Insights",
    creatorNoAccounts: "No linked platform accounts.", creatorProfileUrlUnavailable: "Profile URL unavailable", creatorUnlinkAccount: "Remove link",
    creatorAgencyLoadFailed: "Agency list could not be loaded.", creatorProfileSaved: "Creator profile saved.", creatorProfileSaveFailed: "Creator profile could not be saved.",
    creatorRestoreConfirm: "Restore this creator to the default Creator Library?", creatorArchiveConfirm: "Archiving hides the creator from the default list. Campaign, snapshot, and insight data are retained.",
    creatorRestored: "Creator restored.", creatorArchived: "Creator archived.", creatorProfileUrlRequired: "Enter a profile URL.",
    creatorAccountAlreadyLinked: "This account already belongs to the current creator.", creatorAccountLinked: "Platform account linked.", creatorAccountOwnedBy: "This account already belongs to {creator}.",
    creatorAnotherCreator: "another creator", creatorViewExistingCreator: "View existing creator", creatorMergeCreator: "Merge creators", creatorAccountLinkFailed: "Account could not be linked.",
    creatorAccountRemoveConfirm: "Only accounts with no historical references can be removed; accounts with partnership or performance history are retained safely.", creatorAccountRemoved: "Platform account removed.",
    creatorAccountRemoveBlocked: "This account cannot be removed.", creatorSimilarityMethod: "Scores use only structured evidence in the local Creator Library; missing dimensions are not scored as zero.",
    creatorNoSimilarCandidates: "No local creators have usable matching evidence.", creatorSimilarityScore: "Similarity {score}% · Available evidence weight {weight}/100",
    creatorSimilarityUnavailable: "Similarity -- · Insufficient comparable evidence", creatorHistoricalEvidence: "Historical evidence (does not change the score): {cooperations} partnerships · {publications} publications · Average views {views} · Average ER {er}",
    creatorDimensionTag: "Tags", creatorDimensionContent: "Content", creatorDimensionFollowers: "Followers", creatorDimensionPrice: "Price", creatorDimensionEngagement: "Engagement rate",
    creatorDimensionCountryLanguage: "Country/language", creatorDimensionPlatform: "Platform", creatorSimilarityExcluded: "Excluded from scoring: {dimensions}",
    creatorSimilarityAllComparable: "All dimensions have comparable evidence", creatorCountryLanguageMissing: "Missing country/language: {dimensions}",
    creatorAiSupplement: "AI supplementary note (does not change the score): {text}", creatorSimilaritySearching: "Searching local Creator Library candidates...",
    creatorSimilaritySummary: "{total} local candidates; showing {shown}, sorted by deterministic score with missing evidence not scored as zero.", creatorSimilarityFailed: "Similar creator search failed.",
    creatorMissingId: "Creator ID is missing. Return to the Creator Library and open it again.",
    creatorDetailTitle: "Creator analysis", creatorBackToLibrary: "Back to Creator Library", creatorEditProfile: "Edit profile", creatorAddCampaign: "Add to Campaign",
    creatorFindSimilar: "Find similar creators", creatorCreateTask: "Create partnership task", creatorSocialAccounts: "Social accounts", creatorSocialAccountsHint: "Switch accounts to view platform-specific profile and performance data.",
    creatorSocialAccountsAria: "Creator social accounts", creatorNoSocialAccounts: "No social accounts are available.", creatorDetailTabs: "Creator details", creatorOverview: "Overview",
    creatorContentPerformance: "Content performance", creatorHistoryTrend: "History trends", creatorBasicInformation: "Basic information", creatorVideoAnalysis: "Video analysis", creatorDataUpdated: "Data updated", creatorFactSummary: "Fact summary",
    creatorDataFreshness: "Data freshness", creatorSimilarCandidates: "Similar creator candidates", creatorCampaignParticipation: "Campaign participation",
    creatorCampaignParticipationHint: "Campaigns the creator has joined; legacy cooperation records are excluded.", creatorNoCampaignParticipation: "Not yet added to a Campaign.",
    creatorAiSummary: "AI creator summary", creatorAiDisclosure: "Generated by local rules; no live AI is connected", creatorBasicProfile: "Basic profile",
    creatorPerformanceData: "Performance data", creatorDataStatus: "Data status", creatorDataLimitations: "Data limitations", creatorStrengths: "Strengths", creatorRisks: "Risks",
    creatorRecentVideos: "Recent videos", creatorPerformanceHistory: "Partnership performance history", creatorPerformanceHistoryHint: "Based on the latest valid observation for actual publications; amounts are grouped by currency with no FX conversion.",
    creatorNoPerformanceHistory: "No partnership performance history is available.", creatorHistoricalAnalysis: "Historical analysis", creatorNoSnapshots: "No historical snapshot data.",
    creatorEditTitle: "Edit creator profile", creatorBasicProfileTitle: "Basic profile", creatorWhatsAppOptional: "Optional", creatorImproveAnalysisHint: "Completing country and language improves creator analysis accuracy.",
    creatorAccountIdentityHint: "Profile URLs identify the platform and account; no internal ID is required.", creatorAccountUrlPlaceholder: "Paste a TikTok, Instagram, or YouTube profile URL",
    creatorAddProfileUrl: "+ Add profile URL", creatorSaveProfile: "Save profile",
    creatorInsight: "Creator Insight", creatorCampaignColumn: "Campaign", creatorProductColumn: "Product", creatorStatusColumn: "Status", creatorDateColumn: "Date", creatorAiTags: "AI tags", creatorContentCategories: "Content categories", creatorAudienceSignals: "Audience signals", creatorContentSignals: "Content signals", creatorFollowerBand: "Follower band", creatorEngagementBand: "Engagement band", creatorPriceBand: "Price band", creatorConfidence: "Confidence", creatorSnapshotTime: "Time", creatorSnapshotFollowers: "Followers", creatorSnapshotScore: "Score", creatorSnapshotInsight: "Insight",
    creatorCampaignModalTitle: "Add to Campaign", creatorBatchCampaignCount: "0 creators selected", creatorCampaignSelectPlaceholder: "Select a Campaign", creatorExecutionAccount: "Execution account", creatorExecutionAccountPlaceholder: "Select an execution account", creatorExecutionAccountHint: "Choose the social account used for this partnership.", creatorConfirmAdd: "Confirm add", creatorPermanentDelete: "Permanently delete creator", creatorDeleteChecking: "Checking permanent-delete impact...", creatorRecheckImpact: "Recheck impact", creatorConfirmPermanentDelete: "Confirm permanent deletion", creatorMergeTitle: "Merge creators", creatorMergePrimary: "Primary creator · retain", creatorMergeSecondary: "Creator to merge · delete after merge", creatorMergeNotSelected: "Not selected", creatorMergeSearch: "Search creator to merge", creatorMergeSearchPlaceholder: "Name, username, platform, or profile URL", creatorMergeResultAccounts: "Accounts after merge", creatorMergeMigratedAccounts: "Migrated accounts", creatorMergeVideos: "Videos", creatorMergeSnapshots: "Snapshots", creatorMergeCampaignRelations: "Campaign relationships", creatorPreviewMergeImpact: "Preview merge impact", creatorConfirmMerge: "Confirm merge creators",
  });

  // These are UI-only literals from the shared shell and page renderers.  They
  // deliberately use exact matches, so creator data, mail content, URLs and
  // other externally supplied text is never translated by this layer.
  const literals = {
    zh: {
      "工作台": "Dashboard", "发现达人": "Discover Creators", "达人库": "Creator Library",
      "合作管理": "Partnerships", "设置": "Settings", "邮箱抓取": "Email Capture",
      "审核结果": "Review Results", "链接清洗": "Link Cleanup", "产品": "Products",
      "邮件": "Mail", "邮件跟进": "Mail Follow-up", "邮箱账户": "Mail Accounts",
      "日志": "Logs", "Chrome 账号": "Chrome Accounts", "账号主页": "Account Homepage",
      "概览": "Overview", "内容表现": "Content Performance", "历史趋势": "History Trends",
      "刷新": "Refresh", "刷新数据": "Refresh Data", "查看全部": "View All",
      "查看结果": "View Results", "查看账号": "View Accounts", "搜索": "Search",
      "平台": "Platform", "邮箱": "Email", "状态": "Status", "操作": "Actions",
      "备注": "Notes", "保存": "Save", "取消": "Cancel", "删除": "Delete",
      "编辑": "Edit", "关闭": "Close", "返回": "Back", "加载中…": "Loading…",
      "暂无数据": "No data yet", "暂无结果": "No results", "未找到": "Not Found",
      "成功": "Success", "失败": "Failed", "已完成": "Completed", "运行中": "Running",
      "未开始": "Not Started", "暂停": "Pause", "继续": "Resume", "停止": "Stop",
      "创建": "Create", "导出": "Export", "导入 Excel": "Import Excel",
      "国家/地区": "Country/Region", "语言": "Language", "内容类型": "Content Category",
      "粉丝数": "Followers", "主页链接": "Profile URL", "账号": "Account",
      "达人名称": "Creator Name", "基础信息": "Basic Information", "简介": "Bio",
      "数据更新时间": "Data Updated", "来源": "Source", "加入 Campaign": "Add to Campaign",
      "Campaign": "Campaign", "Agency": "Agency", "Creator": "Creator",
      "联系邮箱": "Contact Email", "等待": "Waiting", "最近邮件": "Latest Mail",
      "收件": "Inbound", "发件": "Outbound", "历史": "History", "待我回复": "Waiting for Me",
      "待对方回复": "Waiting for Creator", "状态未知": "Status Unknown", "待处理": "Actionable",
      "全部": "All", "稍后处理 ▼": "Snooze ▼", "明天再处理": "Tomorrow",
      "3 天后再处理": "In 3 Days", "选择日期…": "Choose Date…", "取消稍后处理": "Clear Snooze",
      "停止跟进": "Stop Follow-up", "恢复跟进": "Resume Follow-up",
      "加入导出队列": "Add to Export Queue", "移出导出队列": "Remove from Export Queue",
      "导出队列": "Export Queue", "导出 CSV": "Export CSV", "导出 Excel": "Export Excel",
      "部分历史": "Partial History", "历史范围未知": "History Scope Unknown",
      "界面设置": "UI Settings", "界面语言": "Language", "默认 Profile": "Default Profile",
      "保存界面设置": "Save UI Settings", "货币与汇率": "Currencies and Exchange Rates",
      "保存并更新": "Save and Update", "添加或管理更多币种": "Manage More Currencies",
      "收起更多币种": "Show Fewer Currencies", "快速换算": "Quick Conversion", "金额": "Amount",
      "已连接": "Connected", "未连接": "Not Connected", "未配置": "Not Configured",
      "同步收件箱": "Sync Inbox", "同步回复状态到飞书表": "Sync Reply Status to Feishu",
      "同步邮件跟进到 Google Sheets": "Sync Mail Follow-up to Google Sheets",
      "最近同步时间": "Last Synced", "已检查账户": "Accounts Checked", "本次读取邮件": "Messages Read",
      "新增邮件": "New Messages", "未读邮件": "Unread Messages", "已匹配达人回复": "Matched Creator Replies",
      "仅看达人回复": "Creator Replies Only", "发件人": "Sender", "时间": "Time",
      "运行日志": "Runtime Log", "系统健康检查": "System Health Check", "调试模式": "Debug Mode"
      ,"创建产品": "Create Product", "编辑产品": "Edit Product", "保存产品": "Save Product",
      "正在保存...": "Saving...", "恢复": "Restore", "归档": "Archive", "更多": "More",
      "查看": "View", "查看达人": "View Creator", "解除关联": "Unlink",
      "暂无事项。": "No items yet.", "打开 Campaign": "Open Campaign",
      "执行看板暂时不可用，请稍后重试。": "The execution board is temporarily unavailable. Please try again later.",
      "需要授权": "Authorization Required", "未启用": "Disabled", "正在连接": "Connecting", "连接失败": "Connection Failed",
      "可用": "Available", "不可用": "Unavailable", "配置异常": "Configuration Error", "需处理": "Needs Attention",
      "部分不可用": "Partially Available", "未命名达人": "Unnamed Creator", "未命名产品": "Unnamed Product",
      "全部产品": "All Products", "请选择产品": "Select a Product", "不限平台": "All Platforms",
      "创建 Campaign": "Create Campaign", "编辑 Campaign": "Edit Campaign", "保存 Campaign": "Save Campaign",
      "已连接": "Connected", "已创建": "Created", "已更新": "Updated", "已归档": "Archived",
      "打开浏览器": "Open Browser", "移除配置": "Remove Configuration", "当前默认 Profile": "Current Default Profile",
      "KOLConnect 独立自动化 Profile": "KOLConnect Dedicated Automation Profile",
      "检查邮箱": "Check Emails", "有效": "Valid", "已标准化": "Normalized", "重复": "Duplicate", "无效": "Invalid", "未知": "Unknown"
      ,"已发现": "Discovered", "已联系": "Contacted", "洽谈中": "Negotiating", "合作中": "Collaborating", "已拒绝": "Rejected",
      "卡片": "Cards", "表格": "Table", "更多筛选": "More Filters", "排序": "Sort",
      "本页全选": "Select Page", "导出选中达人": "Export Selected Creators", "下载模板": "Download Template",
      "刷新达人库": "Refresh Creator Library", "加入 Campaign": "Add to Campaign", "编辑资料": "Edit Profile",
      "归档达人": "Archive Creator", "查找相似达人": "Find Similar Creators", "创建合作任务": "Create Partnership Task",
      "社媒账号": "Social Accounts", "数据新鲜度": "Data Freshness", "参与 Campaign": "Campaign Participation",
      "AI 达人摘要": "AI Creator Summary", "生成摘要": "Generate Summary", "本地规则生成": "Generated by Local Rules",
      "未连接真实 AI": "No Live AI Connected", "基础资料": "Basic Profile", "表现数据": "Performance Data",
      "数据状态": "Data Status", "事实摘要": "Fact Summary", "数据限制": "Data Limitations",
      "账号唯一ID": "Account ID", "最近发布日期": "Latest Publication Date", "抓取状态": "Capture Status",
      "每页条数": "Per Page", "重新抓取": "Retry Capture", "待补充资料": "Needs More Information",
      "未抓取到": "Not Captured", "页面无法访问": "Page Unavailable", "需要人工确认": "Needs Manual Review",
      "邮箱冲突，未覆盖": "Email Conflict: Not Overwritten", "待抓取": "Pending Capture",
      "请输入产品名称。": "Enter a product name.", "请输入公司名称。": "Enter a company name.",
      "请输入 Campaign 名称。": "Enter a Campaign name.", "当前没有可加入的 Campaign。": "There are no available Campaigns to join."
    },
    en: {}
  };
  Object.entries(literals.zh).forEach(([zh, en]) => { literals.en[en] = zh; });

  let locale = DEFAULT_LOCALE;
  let localeHydrated = false;
  let userSelectedLocale = false;
  let observing = false;

  function normalize(value) {
    const normalized = String(value || "").trim().toLowerCase().replace(/_/g, "-");
    if (["en", "en-us", "english"].includes(normalized)) return "en";
    if (["zh", "zh-cn", "chinese", "\u4e2d\u6587"].includes(normalized)) return DEFAULT_LOCALE;
    return DEFAULT_LOCALE;
  }

  function format(value, params) {
    return String(value || "").replace(/\{(\w+)\}/g, (_, name) => String(params?.[name] ?? ""));
  }

  function t(key, params) {
    const source = dictionaries[locale] || dictionaries[DEFAULT_LOCALE];
    const fallback = dictionaries[DEFAULT_LOCALE];
    const value = source[key] ?? fallback[key];
    return value == null || value === "" ? `[missing:${key}]` : format(value, params);
  }

  function localizeLiteral(value) {
    // Markup uses Chinese fallback text.  In English mode map that fallback to
    // English; in Chinese mode map a previous English render back to Chinese.
    const table = locale === "en" ? literals.zh : literals.en;
    return Object.prototype.hasOwnProperty.call(table, value) ? table[value] : value;
  }

  function localizeNode(node) {
    if (!node || node.nodeType !== Node.ELEMENT_NODE) return;
    if (node.matches?.("script, style, textarea, input, option, [data-i18n-no-auto]")) return;
    // This compatibility path is intentionally opt-in. Tag names and generic
    // UI classes can later receive Creator, Campaign, Agency, or mail data.
    // Only static application chrome explicitly marked for literal migration
    // may be translated after MutationObserver-driven DOM updates.
    if (!node.matches?.("[data-i18n-literal]")) return;
    ["title", "aria-label", "placeholder"].forEach(name => {
      const value = node.getAttribute?.(name);
      if (value) node.setAttribute(name, localizeLiteral(value));
    });
    const walker = document.createTreeWalker(node, NodeFilter.SHOW_TEXT, {
      acceptNode(textNode) {
        const parent = textNode.parentElement;
        if (!parent || parent.closest("script, style, textarea, input, option, [data-i18n-no-auto]")) return NodeFilter.FILTER_REJECT;
        return NodeFilter.FILTER_ACCEPT;
      },
    });
    const pending = [];
    while (walker.nextNode()) {
      const current = walker.currentNode;
      const raw = current.nodeValue;
      const translated = localizeLiteral(raw.trim());
      if (translated !== raw.trim()) pending.push([current, raw.replace(raw.trim(), translated)]);
    }
    pending.forEach(([textNode, value]) => { textNode.nodeValue = value; });
  }

  function apply(root = document) {
    document.documentElement.lang = locale === "en" ? "en" : "zh-CN";
    document.documentElement.dataset.locale = locale;
    root.querySelectorAll?.("[data-i18n]").forEach(element => {
      const value = t(element.dataset.i18n);
      if (!value.startsWith("[missing:")) element.textContent = value;
    });
    root.querySelectorAll?.("[data-i18n-placeholder]").forEach(element => {
      const value = t(element.dataset.i18nPlaceholder);
      if (!value.startsWith("[missing:")) element.placeholder = value;
    });
    root.querySelectorAll?.("[data-i18n-aria-label]").forEach(element => {
      const value = t(element.dataset.i18nAriaLabel);
      if (!value.startsWith("[missing:")) element.setAttribute("aria-label", value);
    });
    if (root.nodeType === Node.ELEMENT_NODE) localizeNode(root);
    root.querySelectorAll?.("*").forEach(localizeNode);
  }

  function beginObserving() {
    if (observing || !global.MutationObserver || !document.body) return;
    observing = true;
    new MutationObserver(records => {
      records.forEach(record => record.addedNodes.forEach(node => {
        if (node.nodeType === Node.ELEMENT_NODE) localizeNode(node);
        if (node.nodeType === Node.TEXT_NODE) localizeNode(node.parentElement);
      }));
    }).observe(document.body, { childList: true, subtree: true });
  }

  function setLocale(value, options = {}) {
    locale = normalize(value);
    if (options.source === "persisted") localeHydrated = true;
    else userSelectedLocale = true;
    apply();
    if (typeof global.CustomEvent === "function") {
      global.dispatchEvent(new global.CustomEvent("kolconnect:localechange", {
        detail: { locale, refreshCurrent: options.refreshCurrent !== false },
      }));
    }
    return locale;
  }

  function hydrateLocale(value) {
    // A delayed settings response must never undo an explicit in-session choice.
    if (localeHydrated || userSelectedLocale) return locale;
    return setLocale(value, { source: "persisted", refreshCurrent: false });
  }

  global.KOLConnectI18n = Object.freeze({
    register(source) {
      ["zh", "en"].forEach(name => Object.assign(dictionaries[name], source?.[name] || {}));
    },
    t,
    text: localizeLiteral,
    apply,
    setLocale,
    hydrateLocale,
    normalize,
    getLocale: () => locale,
    getDictionaries: () => ({ zh: { ...dictionaries.zh }, en: { ...dictionaries.en } }),
    start: beginObserving,
  });
})(window);
