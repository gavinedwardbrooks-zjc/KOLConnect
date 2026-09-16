const I18N = {
  zh: {
    appTitle: "KOL联系助手",
    appSubtitle: "海外达人管理与合作工具",
    navDashboard: "控制台",
    navScrape: "邮箱抓取",
    navDiscover: "链接清洗",
    navAccounts: "Chrome 账号",
    navMail: "邮件",
    navSettings: "设置",
    navLogs: "日志",
    dashboardTitle: "控制台",
    dashboardSubtitle: "先看当前配置和运行状态。",
    statProfile: "当前 Profile",
    statTable: "当前飞书表",
    statStatus: "运行状态",
    statResults: "结果文件",
    quickActions: "快捷操作",
    goScrape: "去抓取页",
    openResults: "打开结果文件",
    goSettings: "去设置",
    logPreview: "日志预览",
    scrapeTitle: "邮箱抓取",
    scrapeSubtitle: "从现有任务、审核结果或达人库补全公开联系邮箱，也可手动粘贴主页链接。",
    scrapeTask: "抓取任务",
    linksFile: "links.txt 路径",
    taskLinks: "达人链接",
    taskLinksPlaceholder: "一行一个链接",
    createTask: "创建任务",
    taskNotCreated: "尚未创建任务",
    taskCurrent: "当前任务",
    runProfile: "运行 Profile",
    runtimeLog: "运行日志",
    startScrape: "开始抓取",
    startTask: "开始任务",
    restartTask: "重新开始",
    pauseTask: "暂停任务",
    resumeTask: "继续任务",
    stopScrape: "停止抓取",
    stopTask: "停止任务",
    currentStatus: "当前状态",
    taskStatusCreated: "未开始",
    taskStatusRunning: "运行中",
    taskStatusFinalizing: "入库收尾中",
    taskStatusPaused: "暂停中",
    taskStatusStopping: "停止中",
    taskStatusStopped: "已停止",
    taskStatusCompleted: "已完成",
    taskStatusFailed: "失败",
    taskStatusInterrupted: "检测到任务异常中断",
    taskHeartbeat: "最后心跳",
    taskLastProgress: "最后处理时间",
    taskCurrentItem: "当前处理达人",
    discoverTitle: "链接清洗",
    discoverSubtitle: "把候选链接整理成标准主页链接，方便后续抓取与归档。",
    discoverInputLabel: "一行一个链接",
    discoverOutputTitle: "清洗结果",
    cleanLinks: "清洗链接",
    accountsTitle: "Chrome 账号",
    accountsSubtitle: "配置用于达人抓取的 Chrome Profile；移除配置不会删除浏览器数据。",
    profilesTitle: "Chrome Profile",
    refreshProfiles: "刷新 Profile",
    saveAccounts: "保存账号配置",
    mailTitle: "邮件",
    mailSubtitle: "同步达人回复并维护合作邮件模板。",
    mailTemplateTitle: "邮件模板",
    senderName: "发件人名称",
    mailSubject: "邮件标题",
    mailBody: "邮件正文",
    saveMail: "保存邮件配置",
    settingsTitle: "设置",
    settingsSubtitle: "管理界面语言、默认 Profile 和飞书配置。",
    uiSettingsTitle: "界面设置",
    uiLanguage: "界面语言",
    defaultProfile: "默认 Profile",
    saveUi: "保存界面设置",
    feishuSettingsTitle: "飞书配置（同一个 App）",
    saveFeishu: "保存飞书配置",
    logsTitle: "日志",
    logsSubtitle: "查看完整运行日志。",
    waiting: "等待运行...",
    idle: "空闲",
    running: "运行中",
    saved: "保存成功",
    saveFailed: "保存失败",
    noAccounts: "暂无账号配置",
    profile: "Profile",
    alias: "备注名",
    open: "打开",
  },
  en: {
    appTitle: "KOL Connect",
    appSubtitle: "Global creator management and partnerships",
    navDashboard: "Dashboard",
    navScrape: "Scrape",
    navDiscover: "Link Cleanup",
    navAccounts: "Accounts",
    navMail: "Mail",
    navSettings: "Settings",
    navLogs: "Logs",
    dashboardTitle: "Dashboard",
    dashboardSubtitle: "Check the current configuration and running status.",
    statProfile: "Current profile",
    statTable: "Current Feishu table",
    statStatus: "Status",
    statResults: "Result file",
    quickActions: "Quick actions",
    goScrape: "Open scrape page",
    openResults: "Open result file",
    goSettings: "Open settings",
    logPreview: "Log preview",
    scrapeTitle: "Email Crawl",
    scrapeSubtitle: "Capture homepage emails, external-link emails and latest publish date.",
    scrapeTask: "Scrape task",
    linksFile: "links.txt path",
    taskLinks: "Creator links",
    taskLinksPlaceholder: "One link per line",
    createTask: "Create task",
    taskNotCreated: "No task created",
    taskCurrent: "Current task",
    runProfile: "Run profile",
    runtimeLog: "Runtime log",
    startScrape: "Start",
    startTask: "Start task",
    restartTask: "Restart",
    pauseTask: "Pause",
    resumeTask: "Resume",
    stopScrape: "Stop",
    stopTask: "Stop task",
    currentStatus: "Current status",
    taskStatusCreated: "Not started",
    taskStatusRunning: "Running",
    taskStatusFinalizing: "Finalizing",
    taskStatusPaused: "Paused",
    taskStatusStopping: "Stopping",
    taskStatusStopped: "Stopped",
    taskStatusCompleted: "Completed",
    taskStatusFailed: "Failed",
    taskStatusInterrupted: "Task interrupted",
    taskHeartbeat: "Last heartbeat",
    taskLastProgress: "Last progress",
    taskCurrentItem: "Current creator",
    discoverTitle: "Link Cleanup",
    discoverSubtitle: "Normalize candidate links into standard profile homepages for later crawling.",
    discoverInputLabel: "One link per line",
    discoverOutputTitle: "Normalized result",
    cleanLinks: "Normalize links",
    accountsTitle: "Account Management",
    accountsSubtitle: "Configure Chrome profiles for creator capture; removing a configuration never deletes browser data.",
    profilesTitle: "Profile list",
    refreshProfiles: "Refresh profiles",
    saveAccounts: "Save account settings",
    mailTitle: "Mail",
    mailSubtitle: "Prepare sender settings and templates first.",
    mailTemplateTitle: "Mail template",
    senderName: "Sender name",
    mailSubject: "Subject",
    mailBody: "Body",
    saveMail: "Save mail settings",
    settingsTitle: "Settings",
    settingsSubtitle: "Manage language, default profile and Feishu configuration.",
    uiSettingsTitle: "UI settings",
    uiLanguage: "Language",
    defaultProfile: "Default profile",
    saveUi: "Save UI settings",
    feishuSettingsTitle: "Feishu settings (single app)",
    saveFeishu: "Save Feishu settings",
    logsTitle: "Logs",
    logsSubtitle: "View the full runtime log.",
    waiting: "Waiting...",
    idle: "Idle",
    running: "Running",
    saved: "Saved",
    saveFailed: "Save failed",
    noAccounts: "No accounts",
    profile: "Profile",
    alias: "Alias",
    open: "Open",
  }
};

Object.assign(I18N.zh, {
  statTable: "四表同步"
});

Object.assign(I18N.en, {
  statTable: "Four-table sync"
});

Object.assign(I18N.zh, {
  mailTitle: "邮件",
  mailSubtitle: "同步达人回复并维护合作邮件模板。",
  mailAccountsTitle: "邮箱账户",
  mailAccountsHint: "可配置多个邮箱账号，测试连接时只验证 IMAP/SMTP 登录，不发送真实邮件。",
  mailAddAccount: "新增邮箱账户",
  mailTemplateTitle: "邮件模板",
  mailSubject: "邮件标题",
  mailBody: "邮件正文",
  saveMail: "保存邮箱设置",
  mailEmptyAccounts: "暂无邮箱账户，请先新增一个账户。",
  mailAccountName: "账户名称",
  mailProvider: "邮箱类型",
  mailAddress: "邮箱地址",
  mailSenderName: "发件人名称",
  mailImapHost: "IMAP Host",
  mailImapPort: "IMAP Port",
  mailSmtpHost: "SMTP Host",
  mailSmtpPort: "SMTP Port",
  mailUsername: "用户名",
  mailPassword: "密码/授权码",
  mailEnabled: "启用",
  mailStatusUntested: "未测试",
  mailStatusSuccess: "正常",
  mailStatusFailed: "失败",
  mailTestConnection: "测试连接",
  mailDeleteAccount: "删除",
  mailProviderGmail: "Gmail",
  mailProviderNetease: "网易邮箱",
  mailProviderAliyun: "阿里邮箱",
  mailProviderCustom: "自定义邮箱",
  mailTestSuccess: "IMAP 和 SMTP 登录测试通过。",
  mailSaveSuccess: "邮箱配置保存成功。连接验证需单独执行。",
  mailInboxSyncTitle: "收件箱同步",
  mailInboxSyncHint: "仅手动同步启用邮箱的 INBOX，默认每个账户最近 20 封，不下载附件。",
  mailInboxSyncButton: "同步收件箱",
  mailInboxSummaryAccounts: "已检查账户",
  mailInboxSummaryFetched: "本次读取邮件",
  mailInboxSummaryNew: "新增邮件",
  mailInboxSummaryUnread: "未读邮件",
  mailInboxSummaryMatched: "已匹配达人回复",
  mailInboxMessagesTitle: "最近邮件",
  mailInboxUpdatedAt: "最近同步时间",
  mailInboxNoMessages: "还没有同步到邮件。",
  mailInboxFrom: "发件人",
  mailInboxReceivedAt: "时间",
  mailInboxUnread: "未读",
  mailInboxRead: "已读",
  mailInboxSyncSuccess: "收件箱同步完成。",
  mailMatchedOnly: "仅看达人回复",
  mailMatchedCreator: "达人名称",
  mailMatchedPlatform: "平台",
  mailReplyStatus: "匹配状态",
  mailReplyMatched: "已匹配",
  mailReplyUnmatched: "未匹配"
});

Object.assign(I18N.en, {
  mailTitle: "Mail Accounts",
  mailSubtitle: "Manage multiple sender accounts and keep the mail template below.",
  mailAccountsTitle: "Mail Accounts",
  mailAccountsHint: "Connection tests verify IMAP/SMTP login only and never send a real email.",
  mailAddAccount: "Add mail account",
  mailTemplateTitle: "Mail Template",
  mailSubject: "Subject",
  mailBody: "Body",
  saveMail: "Save mail settings",
  mailEmptyAccounts: "No mail accounts yet. Add one to begin.",
  mailAccountName: "Account name",
  mailProvider: "Provider",
  mailAddress: "Email address",
  mailSenderName: "Sender name",
  mailImapHost: "IMAP Host",
  mailImapPort: "IMAP Port",
  mailSmtpHost: "SMTP Host",
  mailSmtpPort: "SMTP Port",
  mailUsername: "Username",
  mailPassword: "Password / App password",
  mailEnabled: "Enabled",
  mailStatusUntested: "Untested",
  mailStatusSuccess: "Healthy",
  mailStatusFailed: "Failed",
  mailTestConnection: "Test connection",
  mailDeleteAccount: "Delete account",
  mailProviderGmail: "Gmail",
  mailProviderNetease: "NetEase",
  mailProviderAliyun: "Aliyun Mail",
  mailProviderCustom: "Custom",
  mailTestSuccess: "IMAP and SMTP logins both succeeded.",
  mailSaveSuccess: "Mail configuration saved. Connection validation is a separate step.",
  mailInboxSyncTitle: "Inbox Sync",
  mailInboxSyncHint: "Manual sync only. Reads up to 20 recent INBOX messages per enabled account and skips attachments.",
  mailInboxSyncButton: "Sync inbox",
  mailInboxSummaryAccounts: "Accounts checked",
  mailInboxSummaryFetched: "Fetched this run",
  mailInboxSummaryNew: "New messages",
  mailInboxSummaryUnread: "Unread",
  mailInboxSummaryMatched: "Matched creator replies",
  mailInboxMessagesTitle: "Recent Messages",
  mailInboxUpdatedAt: "Last sync",
  mailInboxNoMessages: "No messages have been synced yet.",
  mailInboxFrom: "From",
  mailInboxReceivedAt: "Received",
  mailInboxUnread: "Unread",
  mailInboxRead: "Read",
  mailInboxSyncSuccess: "Inbox sync finished.",
  mailMatchedOnly: "Matched creator replies only",
  mailMatchedCreator: "Creator",
  mailMatchedPlatform: "Platform",
  mailReplyStatus: "Match Status",
  mailReplyMatched: "Matched",
  mailReplyUnmatched: "Unmatched"
});

Object.assign(I18N.zh, {
  mailSyncCrmReplies: "同步回复状态到达人表",
  mailCrmSyncStatus: "达人表同步状态",
  mailCrmPending: "达人表未同步",
  mailCrmSynced: "达人表已同步",
  mailCrmFailed: "达人表同步失败",
  mailReplySyncUpdated: "已更新",
  mailReplySyncProcessed: "处理",
  mailReplySyncSkipped: "跳过",
  mailReplySyncFailed: "失败"
});

Object.assign(I18N.en, {
  mailSyncCrmReplies: "Sync reply status to Creator Table",
  mailCrmSyncStatus: "Creator Table Sync Status",
  mailCrmPending: "Creator Table Pending",
  mailCrmSynced: "Creator Table Synced",
  mailCrmFailed: "Creator Table Failed",
  mailReplySyncUpdated: "Updated",
  mailReplySyncProcessed: "Processed",
  mailReplySyncSkipped: "Skipped",
  mailReplySyncFailed: "Failed"
});

Object.assign(I18N.zh, {
  discoverRawTitle: "原始链接",
  discoverSubtitle: "将原始达人链接整理为标准主页链接。",
  discoverOutputTitle: "标准主页链接",
  discoverInvalidTitle: "异常链接",
  discoverClear: "清空",
  discoverCopyLinks: "复制标准主页链接",
  discoverCopyInvalid: "复制异常链接"
});

Object.assign(I18N.en, {
  discoverRawTitle: "Raw Links",
  discoverSubtitle: "Normalize raw creator links into standard profile homepages.",
  discoverOutputTitle: "Standard profile links",
  discoverInvalidTitle: "Invalid links",
  discoverClear: "Clear",
  discoverCopyLinks: "Copy profile links",
  discoverCopyInvalid: "Copy invalid links"
});

Object.assign(I18N.zh, {
  targetPlatform: "目标平台",
  platformAll: "全部",
  taskOriginalLinks: "原始链接",
  taskDetected: "识别",
  taskSelectedPlatform: "当前选择",
  taskActualLinks: "实际抓取",
  taskFilteredLinks: "过滤"
});

Object.assign(I18N.en, {
  targetPlatform: "Target platform",
  platformAll: "All",
  taskOriginalLinks: "Original links",
  taskDetected: "Detected",
  taskSelectedPlatform: "Selected",
  taskActualLinks: "To crawl",
  taskFilteredLinks: "Filtered"
});

Object.assign(I18N.zh, {
  taskName: "任务名称",
  taskNamePlaceholder: "留空则自动命名",
  taskManagerTitle: "任务管理",
  taskManagerHint: "选择一个任务后再开始抓取，进度每2秒刷新。",
  taskRefresh: "刷新任务",
  taskRename: "重命名",
  taskDelete: "删除任务",
  taskDeleteConfirm: "确定删除任务“{name}”吗？\n删除后本地抓取记录、审核数据无法恢复，但不会删除飞书中的任何数据。",
  taskRenamePrompt: "请输入新的任务名称",
  taskProgress: "进度",
  taskCompleted: "完成",
  taskFailed: "失败",
    taskPending: "剩余",
    taskNoItems: "暂无任务，请先创建任务。",
    taskTypeManual: "人工录入",
    taskTypeScrape: "抓取任务",
    manualSupplement: "补充抓取信息",
    taskTypeEmailRecheck: "缺失邮箱补全",
    reviewScanMissingEmail: "扫描达人库缺失邮箱",
    reviewScanMissingEmailConfirm: "将扫描本地达人库账号并创建缺失邮箱补全任务，是否继续？",
    reviewScanMissingEmailResult: "已扫描 {scanned} 个账号，创建补全任务 {created} 条，跳过 {skipped} 条。",
    taskEmailFound: "已补全邮箱",
    taskEmailFailed: "未补全邮箱"
});

Object.assign(I18N.en, {
  taskName: "Task name",
  taskNamePlaceholder: "Leave empty to auto-name",
  taskManagerTitle: "Task Management",
  taskManagerHint: "Select a task before starting. Progress refreshes every 2 seconds.",
  taskRefresh: "Refresh tasks",
  taskRename: "Rename",
  taskDelete: "Delete task",
  taskDeleteConfirm: "Delete task “{name}”?\nLocal crawl and review data cannot be recovered. Existing Feishu data will not be deleted.",
  taskRenamePrompt: "Enter a new task name",
  taskProgress: "Progress",
  taskCompleted: "Completed",
  taskFailed: "Failed",
    taskPending: "Pending",
    taskNoItems: "No tasks yet. Create one first.",
    taskTypeManual: "Manual entry",
    taskTypeScrape: "Scrape task",
    manualSupplement: "Supplement crawl data",
    taskTypeEmailRecheck: "Missing email recheck",
    reviewScanMissingEmail: "Scan missing account emails",
    reviewScanMissingEmailConfirm: "Scan local Creator Library accounts and create a missing-email recheck task?",
    reviewScanMissingEmailResult: "Scanned {scanned} accounts, created {created} recheck rows, skipped {skipped}.",
    taskEmailFound: "Emails found",
    taskEmailFailed: "Emails not found"
});

Object.assign(I18N.zh, {
  navReview: "审核结果",
  reviewTitle: "审核结果",
  reviewSubtitle: "查看任务抓取结果，补充人工确认的数据后单条保存。",
  reviewTask: "任务",
  reviewSearch: "搜索平台、达人名称或邮箱",
  reviewPageSize: "每页条数",
  reviewRefresh: "刷新任务",
  reviewPlatform: "平台",
  reviewLink: "账号主页",
  reviewAccountUid: "账号唯一ID",
  reviewLatestDate: "最近发布日期",
  reviewScrapeStatus: "抓取状态",
  reviewName: "达人名称",
  reviewEmail: "邮箱",
  reviewFollowerCount: "粉丝数",
  reviewNote: "备注",
  reviewDataStatus: "数据状态",
  reviewAction: "操作",
  reviewSave: "保存",
  reviewNoTasks: "暂无可审核任务。请先创建并完成一个抓取任务。",
  reviewSelectTask: "请选择一个已有任务。",
  reviewNoRecords: "该任务暂无抓取结果。",
  reviewSummary: "共 {count} 条结果，当前显示 {shown} 条。",
  reviewSaved: "审核结果已保存。",
});

Object.assign(I18N.en, {
  navReview: "Review Results",
  reviewTitle: "Review Results",
  reviewSubtitle: "Review task output and save manually confirmed fields one record at a time.",
  reviewTask: "Task",
  reviewSearch: "Search platform, creator name, or email",
  reviewPageSize: "Rows per page",
  reviewRefresh: "Refresh tasks",
  reviewPlatform: "Platform",
  reviewLink: "Account homepage",
  reviewAccountUid: "Account UID",
  reviewLatestDate: "Latest publish date",
  reviewScrapeStatus: "Scrape status",
  reviewName: "Creator name",
  reviewEmail: "Email",
  reviewFollowerCount: "Followers",
  reviewNote: "Note",
  reviewDataStatus: "Data status",
  reviewAction: "Action",
  reviewSave: "Save",
  reviewNoTasks: "No reviewable tasks yet. Create and complete a scrape task first.",
  reviewSelectTask: "Select an existing task.",
  reviewNoRecords: "This task has no scrape results yet.",
  reviewSummary: "{count} results total, showing {shown}.",
  reviewSaved: "Review result saved.",
});

const MAIL_PROVIDER_DEFAULTS = {
  gmail: {
    imap_host: "imap.gmail.com",
    imap_port: "993",
    smtp_host: "smtp.gmail.com",
    smtp_port: "587"
  },
  netease: {
    imap_host: "imap.163.com",
    imap_port: "993",
    smtp_host: "smtp.163.com",
    smtp_port: "465"
  }
};

const state = {
  language: "zh",
  scrapeStatusTimer: null,
  taskStatusTimer: null,
  currentTaskId: window.localStorage.getItem("kolconnect.currentTaskId") || "",
  currentTask: null,
  scrapeJob: {},
  tasks: [],
  review: {
    tasks: [],
    taskId: "",
    records: [],
    platforms: [],
    platformResults: {},
    reviewTotal: 0,
    reviewedCount: 0,
    pendingCount: 0,
    submitting: false,
    page: 1
  },
  creatorLibrary: {
    records: [],
    viewMode: window.localStorage.getItem("creator_library_view_mode") || "card",
    page: 1,
    pageSize: 24,
    sort: "created_at",
    order: "desc",
    filters: {
      search: "",
      country: "",
      language: "",
      content_category: "",
      tag: "",
      insight_level: "",
      status: ""
    },
    detailTab: "overview"
  },
  taskDetails: {
    taskId: "",
    task: null,
    links: []
  },
  discover: {
    results: [],
    summary: {}
  },
  emailEnrichment: {
    candidates: [],
    previewed: false,
    source: "task",
    taskId: ""
  },
  mailInbox: {
    messages: [],
    page: 1,
    pageSize: 20
  }
};

function $(id) {
  return document.getElementById(id);
}

function valueOf(id, fallback = "") {
  const el = $(id);
  return el ? (el.value ?? fallback) : fallback;
}

function checkedOf(id, fallback = false) {
  const el = $(id);
  return el ? !!el.checked : fallback;
}

function setValue(id, value) {
  const el = $(id);
  if (el) el.value = value;
}

function setText(id, value) {
  const el = $(id);
  if (el) el.textContent = value;
}

function scrapeStatusLabel(status) {
  const labels = {
    running: "taskStatusRunning",
    finalizing: "taskStatusFinalizing",
    paused: "taskStatusPaused",
    stopping: "taskStatusStopping",
    stopped: "taskStatusStopped",
    completed: "taskStatusCompleted",
    failed: "taskStatusFailed",
    interrupted: "taskStatusInterrupted",
    created: "taskStatusCreated",
    idle: "idle"
  };
  return t(labels[status] || "idle");
}

function renderScrapeControls(job = {}) {
  const start = $("scrape-start");
  const pause = $("scrape-pause");
  const stop = $("scrape-stop");
  if (!start || !pause || !stop) return;

  job = Object.keys(job).length ? job : (state.scrapeJob || {});
  const taskStatus = state.currentTask?.status || "created";
  const status = job.status && job.status !== "idle" ? job.status : taskStatus;
  const resumablePaused = status === "paused" && !job.running;
  const active = ["running", "finalizing", "paused", "stopping"].includes(status) && !resumablePaused;
  const finalizing = status === "finalizing";
  const paused = status === "paused";
  const stopping = status === "stopping";

  start.hidden = active;
  pause.hidden = !["running", "paused"].includes(status);
  stop.hidden = finalizing || (!active && !(status === "paused" && !job.running));
  pause.textContent = t(paused ? "resumeTask" : "pauseTask");
  stop.textContent = t("stopTask");
  stop.disabled = stopping;
  start.textContent = status === "interrupted" || resumablePaused
    ? (state.language === "en" ? "Resume task" : "恢复任务")
    : t(["stopped", "completed", "failed"].includes(status) ? "restartTask" : "startTask");
  setText("scrape-control-status", `${t("currentStatus")}：${scrapeStatusLabel(status)}`);
}

function renderCurrentTask() {
  const task = state.currentTask;
  updateTaskResultActions();
  if (!task) {
    const value = state.currentTaskId
      ? `${t("taskCurrent")}：${state.currentTaskId}`
      : t("taskNotCreated");
    setText("task-current", value);
    return;
  }
  const summary = task.platform_summary || {};
  const totalLinks = task.total_links ?? task.valid_count ?? 0;
  const value = [
    `${t("taskCurrent")}：${task.name || task.id || state.currentTaskId}`,
    `${t("taskOriginalLinks")}：${task.input_count ?? totalLinks}`,
    `${t("taskDetected")}：TikTok ${summary.TikTok || 0} / Instagram ${summary.Instagram || 0} / YouTube ${summary.YouTube || 0}`,
    `${t("taskSelectedPlatform")}：${task.target_platform || "全部"}`,
    `${t("taskActualLinks")}：${totalLinks}`,
    `${t("taskFilteredLinks")}：${task.filtered_count || 0}`,
    `${t("taskProgress")}：${task.completed_links || 0}/${totalLinks} (${task.progress || 0}%)`,
    `${t("currentStatus")}：${scrapeStatusLabel(task.status || "created")}`
  ];
  if (task.status === "interrupted") {
    value.push(
      `${t("taskHeartbeat")}：${task.heartbeat_time || "--"}`,
      `${t("taskLastProgress")}：${task.last_progress_time || "--"}`,
      `${t("taskCurrentItem")}：${task.current_item || "--"}`
    );
  }
  if (task.instagram_status === "login_required") {
    value.push(`Instagram：${task.instagram_message || "登录状态异常，请重新登录后继续。"}`);
  }
  if (Number(task.retry_round) > 0) {
    value.push(`异常重试：第 ${task.retry_round} 轮`);
  }
  setText("task-current", value.join("\n"));
}

function taskPlatformEntries(task) {
  const progress = task.platform_progress || {};
  return (task.available_platforms || task.platforms || [])
    .map(value => {
      const key = String(value || "").toLowerCase();
      const label = { tiktok: "TikTok", instagram: "Instagram", youtube: "YouTube" }[key] || String(value || "");
      const values = progress[label] || { total: 0, processed: 0, unfinished: 0 };
      return { key, label, total: Number(values.total || 0), processed: Number(values.processed || 0), unfinished: Number(values.unfinished || 0) };
    })
    .filter(item => item.key && item.total > 0);
}

function openContinueScrapeDialog(task) {
  const entries = taskPlatformEntries(task);
  if (!entries.length) throw new Error("当前任务没有可继续抓取的原始链接。");
  const unfinished = entries.filter(item => item.unfinished > 0);
  const defaultKeys = new Set((unfinished.length ? unfinished : entries).map(item => item.key));
  const dialog = document.createElement("dialog");
  dialog.className = "task-continue-dialog";
  const title = document.createElement("h2");
  title.textContent = `继续抓取：${task.name || "未命名任务"}`;
  const hint = document.createElement("p");
  hint.className = "hint";
  hint.textContent = "使用此任务已保存的原始链接；本次执行会保留在同一任务下。";
  const list = document.createElement("div");
  list.className = "task-continue-platforms";
  entries.forEach(item => {
    const label = document.createElement("label");
    label.className = "task-continue-platform";
    const input = document.createElement("input");
    input.type = "checkbox";
    input.value = item.key;
    input.checked = defaultKeys.has(item.key);
    const name = document.createElement("strong");
    name.textContent = item.label;
    const original = document.createElement("span");
    original.textContent = `原始链接 ${item.total}`;
    const completed = document.createElement("span");
    completed.textContent = `当前完成 ${item.processed}${item.unfinished === 0 ? " ✓" : ""}`;
    label.append(input, name, original, completed);
    list.appendChild(label);
  });
  const actions = document.createElement("div");
  actions.className = "action-row";
  const cancel = document.createElement("button");
  cancel.type = "button";
  cancel.className = "soft-btn";
  cancel.textContent = "取消";
  cancel.addEventListener("click", () => dialog.close());
  const start = document.createElement("button");
  start.type = "button";
  start.className = "primary-btn";
  start.textContent = "开始抓取";
  start.addEventListener("click", async () => {
    const platforms = [...list.querySelectorAll("input:checked")].map(input => input.value);
    if (!platforms.length) return showError(new Error("请选择至少一个平台。"));
    start.disabled = true;
    try {
      await apiPost("/api/scrape/start", { taskId: task.id, profile: valueOf("profile-select"), platforms });
      dialog.close();
      await refreshScrapeStatus();
      await loadTaskList();
    } catch (error) {
      showError(error);
      start.disabled = false;
    }
  });
  actions.append(cancel, start);
  dialog.append(title, hint, list, actions);
  dialog.addEventListener("close", () => dialog.remove());
  dialog.addEventListener("click", event => {
    const rect = dialog.getBoundingClientRect();
    if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) dialog.close();
  });
  document.body.appendChild(dialog);
  dialog.showModal();
}

function renderTaskList() {
  const wrap = $("task-list");
  if (!wrap) return;
  wrap.textContent = "";
  if (!state.tasks.length) {
    const empty = document.createElement("div");
    empty.className = "empty-note";
    empty.textContent = t("taskNoItems");
    wrap.appendChild(empty);
    return;
  }

  const selector = document.createElement("select");
  selector.className = "task-selector";
  state.tasks.forEach(task => {
    selector.add(new Option(
      `${task.name || task.id} · ${scrapeStatusLabel(task.status || "created")}`,
      task.id, false, task.id === state.currentTaskId,
    ));
  });
  selector.addEventListener("change", () => {
    state.currentTaskId = selector.value;
    state.currentTask = state.tasks.find(task => task.id === selector.value) || null;
    window.localStorage.setItem("kolconnect.currentTaskId", selector.value);
    renderCurrentTask();
    renderTaskList();
  });
  wrap.appendChild(selector);

  state.tasks.filter(task => task.id === state.currentTaskId).forEach(task => {
    const card = document.createElement("div");
    card.className = "task-card";
    card.classList.toggle("selected", task.id === state.currentTaskId);
    card.addEventListener("click", () => {
      state.currentTaskId = task.id;
      state.currentTask = task;
      window.localStorage.setItem("kolconnect.currentTaskId", task.id);
      renderCurrentTask();
      renderTaskList();
    });

    const head = document.createElement("div");
    head.className = "task-card-head";
    const name = document.createElement("strong");
    name.className = "task-card-name";
    name.textContent = task.name || t("taskNotCreated");
    const rename = document.createElement("button");
    rename.type = "button";
    rename.className = "mini-btn";
    rename.textContent = t("taskRename");
    rename.addEventListener("click", async event => {
      event.stopPropagation();
      const nextName = window.prompt(t("taskRenamePrompt"), task.name || "");
      if (nextName === null) return;
      try {
        const data = await apiPost(`/api/tasks/${encodeURIComponent(task.id)}/rename`, { name: nextName });
        task.name = data.task?.name || nextName.trim();
        if (state.currentTaskId === task.id) state.currentTask = task;
        renderCurrentTask();
        renderTaskList();
        showSaved();
      } catch (error) {
        showError(error);
      }
    });
    const actions = document.createElement("div");
    actions.className = "action-row";
    const review = document.createElement("button");
    review.type = "button";
    review.className = "mini-btn";
    review.textContent = "查看结果";
    review.addEventListener("click", async event => {
      event.stopPropagation();
      try {
        state.review.taskId = task.id;
        await setPage("review");
        await loadReviewResults();
      } catch (error) {
        showError(error);
      }
    });
    const hasRunnableLinks = taskPlatformEntries(task).length > 0;
    const canContinue = task.task_type !== "manual" && hasRunnableLinks;
    const run = document.createElement("button");
    run.type = "button";
    run.className = "mini-btn";
    run.textContent = "继续抓取";
    run.addEventListener("click", event => {
      event.stopPropagation();
      try { openContinueScrapeDialog(task); } catch (error) { showError(error); }
    });
    const copyTaskLinks = async scope => {
      const data = await apiGet(`/api/tasks/${encodeURIComponent(task.id)}/links?scope=${scope}`);
      return (data.links || []).join("\n");
    };
    const copyAll = document.createElement("button");
    copyAll.type = "button";
    copyAll.className = "mini-btn";
    copyAll.textContent = "复制全部原始链接";
    copyAll.addEventListener("click", async event => {
      event.stopPropagation();
      try { await navigator.clipboard.writeText(await copyTaskLinks("all")); showSaved("全部原始链接已复制。"); } catch (error) { showError(error); }
    });
    const copyUnfinished = document.createElement("button");
    copyUnfinished.type = "button";
    copyUnfinished.className = "mini-btn";
    copyUnfinished.textContent = "复制未完成链接";
    copyUnfinished.addEventListener("click", async event => {
      event.stopPropagation();
      try { await navigator.clipboard.writeText(await copyTaskLinks("unfinished")); showSaved("未完成链接已复制。"); } catch (error) { showError(error); }
    });
    const exportLinks = document.createElement("button");
    exportLinks.type = "button";
    exportLinks.className = "mini-btn";
    exportLinks.textContent = "导出全部原始链接";
    exportLinks.addEventListener("click", async event => {
      event.stopPropagation();
      try {
        const blob = new Blob([`${await copyTaskLinks("all")}\n`], { type: "text/plain;charset=utf-8" });
        const link = document.createElement("a");
        link.href = URL.createObjectURL(blob);
        link.download = `${task.name || task.id}-links.txt`;
        link.click();
        URL.revokeObjectURL(link.href);
      } catch (error) { showError(error); }
    });
    const viewOriginal = document.createElement("button");
    viewOriginal.type = "button";
    viewOriginal.className = "mini-btn";
    viewOriginal.textContent = "查看原始链接";
    viewOriginal.addEventListener("click", async event => {
      event.stopPropagation();
      try { await openTaskDetails(task.id); } catch (error) { showError(error); }
    });
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "mini-btn danger";
    remove.textContent = t("taskDelete");
    remove.addEventListener("click", async event => {
      event.stopPropagation();
      const confirmation = t("taskDeleteConfirm").replace("{name}", task.name || task.id);
      if (!window.confirm(confirmation)) return;
      try {
        await apiDelete(`/api/tasks/${encodeURIComponent(task.id)}`);
        if (state.currentTaskId === task.id) {
          state.currentTaskId = "";
          state.currentTask = null;
          window.localStorage.removeItem("kolconnect.currentTaskId");
        }
        await loadTaskList();
        showSaved();
      } catch (error) {
        showError(error);
      }
    });
    if (task.task_type === "manual" && hasRunnableLinks) {
      const supplement = document.createElement("button");
      supplement.type = "button";
      supplement.className = "mini-btn";
      supplement.textContent = t("manualSupplement");
      supplement.addEventListener("click", async event => {
        event.stopPropagation();
        try {
          state.currentTaskId = task.id;
          state.currentTask = task;
          window.localStorage.setItem("kolconnect.currentTaskId", task.id);
          await apiPost("/api/scrape/start", { taskId: task.id, profile: valueOf("profile-select") });
          await refreshScrapeStatus();
        } catch (error) {
          showError(error);
        }
      });
      actions.appendChild(supplement);
    }
    if (task.status === "interrupted") {
      const recover = document.createElement("button");
      recover.type = "button";
      recover.className = "mini-btn";
      recover.textContent = "恢复任务";
      recover.addEventListener("click", async event => {
        event.stopPropagation();
        try {
          await apiPost(`/api/tasks/${encodeURIComponent(task.id)}/resume`, {});
          state.currentTaskId = task.id;
          await refreshScrapeStatus();
          await loadTaskList();
        } catch (error) { showError(error); }
      });
      actions.append(recover);
    }
    const more = document.createElement("details");
    more.className = "task-card-more";
    const moreSummary = document.createElement("summary");
    moreSummary.textContent = "更多";
    const moreActions = document.createElement("div");
    moreActions.className = "task-card-more-actions";
    moreActions.append(viewOriginal, copyAll, copyUnfinished, exportLinks, rename, remove);
    more.append(moreSummary, moreActions);
    actions.append(review);
    if (canContinue) actions.append(run);
    actions.append(more);
    head.append(name, actions);

    const meta = document.createElement("div");
    meta.className = "task-card-meta";
    const taskType = task.task_type === "manual"
      ? t("taskTypeManual")
      : task.task_type === "email_recheck" ? t("taskTypeEmailRecheck") : t("taskTypeScrape");
    const platforms = task.available_platforms || task.platforms || [task.target_platform || "全部"];
    const timestamp = task.latest_run_at || task.updated_at || task.created_at || "";
    meta.textContent = `${taskType} · 原始链接 ${task.total_links || 0} · ${scrapeStatusLabel(task.status || "created")}${timestamp ? ` · ${timestamp}` : ""}`;

    const track = document.createElement("div");
    track.className = "task-progress-track";
    const bar = document.createElement("div");
    bar.className = "task-progress-bar";
    bar.style.width = `${Math.min(100, Math.max(0, Number(task.progress) || 0))}%`;
    track.appendChild(bar);

    const progress = document.createElement("div");
    progress.className = "task-card-progress-row";
    progress.textContent = task.task_type === "email_recheck"
      ? `${t("taskEmailFound")} ${task.email_found_count || 0} · ${t("taskEmailFailed")} ${task.email_failed_count || 0} · ${t("taskPending")} ${task.pending_links || 0} · ${task.progress || 0}%`
      : `${t("taskCompleted")} ${task.completed_links || 0} · ${t("taskFailed")} ${task.failed_links || 0} · ${t("taskPending")} ${task.pending_links || 0} · ${task.progress || 0}%`;
    card.classList.toggle("task-card-completed", task.status === "completed");
    card.append(head, meta, track, progress);
    const platformProgress = document.createElement("div");
    platformProgress.className = "task-card-progress-row";
    platformProgress.textContent = Object.entries(task.platform_progress || {})
      .filter(([, value]) => Number(value?.total || 0) > 0)
      .map(([platform, value]) => `${platform} ${value.processed || 0}/${value.total || 0}，未完成 ${value.unfinished || 0}`)
      .join(" · ");
    if (platformProgress.textContent) card.appendChild(platformProgress);
    if (task.instagram_status === "login_required") {
      const warning = document.createElement("div");
      warning.className = "task-instagram-warning";
      warning.textContent = `Instagram：${task.instagram_message || "登录状态异常，请重新登录后继续。"}`;
      card.appendChild(warning);
    }
    wrap.appendChild(card);
  });
}

async function loadTaskList() {
  const data = await apiGet("/api/tasks");
  state.tasks = Array.isArray(data.tasks) ? data.tasks : [];
  const selected = state.tasks.find(task => task.id === state.currentTaskId);
  if (selected) {
    state.currentTask = selected;
  } else if (state.tasks.length) {
    state.currentTaskId = state.tasks[0].id;
    state.currentTask = state.tasks[0];
    window.localStorage.setItem("kolconnect.currentTaskId", state.currentTaskId);
  } else if (!selected) {
    state.currentTask = null;
  }
  renderCurrentTask();
  renderTaskList();
  renderEmailTaskOptions();
  renderScrapeControls();
}

function taskDetailsFilteredLinks() {
  const search = valueOf("task-detail-search").trim().toLowerCase();
  const platform = valueOf("task-detail-platform");
  const status = valueOf("task-detail-status");
  return state.taskDetails.links.filter(item => {
    const haystack = `${item.url || ""} ${item.platform || ""} ${item.status || ""}`.toLowerCase();
    return (!search || haystack.includes(search))
      && (!platform || item.platform === platform)
      && (!status || item.status === status);
  });
}

function renderTaskDetails() {
  const body = $("task-detail-body");
  const empty = $("task-detail-empty");
  const task = state.taskDetails.task;
  if (!body || !empty) return;
  body.textContent = "";
  if (!task) {
    setText("task-detail-summary", "请选择任务。");
    empty.hidden = false;
    return;
  }
  setText(
    "task-detail-summary",
    `${task.name || task.id}\n创建时间：${String(task.created_at || "").replace("T", " ").replace("Z", "")}\n进度：${task.completed_links || 0}/${task.total_links || 0}，剩余 ${task.pending_links || 0}\n平台：TikTok ${task.platform_summary?.TikTok || 0} / Instagram ${task.platform_summary?.Instagram || 0} / YouTube ${task.platform_summary?.YouTube || 0}`
  );
  const records = taskDetailsFilteredLinks();
  empty.hidden = records.length > 0;
  records.forEach(item => {
    const row = document.createElement("tr");
    [item.index, item.url, item.platform, item.status].forEach(value => {
      const cell = document.createElement("td");
      cell.textContent = String(value || "");
      row.appendChild(cell);
    });
    const actions = document.createElement("td");
    if (item.status !== "已完成") {
      const edit = document.createElement("button");
      edit.type = "button";
      edit.className = "mini-btn";
      edit.textContent = "修改";
      edit.addEventListener("click", async () => {
        const nextUrl = window.prompt("修改达人主页链接", item.url || "");
        if (nextUrl === null || nextUrl.trim() === item.url) return;
        try {
          await apiPost(`/api/tasks/${encodeURIComponent(state.taskDetails.taskId)}/links`, {
            action: "update", index: item.index, url: nextUrl
          });
          await loadTaskDetails();
          await loadTaskList();
        } catch (error) { showError(error); }
      });
      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "mini-btn danger";
      remove.textContent = "删除";
      remove.addEventListener("click", async () => {
        if (!window.confirm(`确定删除第 ${item.index} 条待处理链接吗？`)) return;
        try {
          await apiPost(`/api/tasks/${encodeURIComponent(state.taskDetails.taskId)}/links`, {
            action: "delete", index: item.index
          });
          await loadTaskDetails();
          await loadTaskList();
        } catch (error) { showError(error); }
      });
      actions.append(edit, remove);
    } else {
      actions.textContent = "已完成，受保护";
    }
    row.appendChild(actions);
    body.appendChild(row);
  });
}

async function loadTaskDetails(taskId = state.taskDetails.taskId) {
  if (!taskId) return;
  const data = await apiGet(`/api/tasks/${encodeURIComponent(taskId)}/details`);
  state.taskDetails.taskId = taskId;
  state.taskDetails.task = data.task || null;
  state.taskDetails.links = Array.isArray(data.links) ? data.links : [];
  renderTaskDetails();
}

async function openTaskDetails(taskId) {
  state.taskDetails.taskId = taskId;
  await setPage("task-details");
  await loadTaskDetails(taskId);
}

function textAreaOrInputValue(row, selector) {
  const el = row.querySelector(selector);
  return el ? el.value.trim() : "";
}

async function apiGet(url, options = {}) {
  return window.KOLConnectAPI.get(url, options);
}

async function apiPost(url, payload, options = {}) {
  return window.KOLConnectAPI.post(url, payload, options);
}

async function apiPatch(url, payload, options = {}) {
  return window.KOLConnectAPI.patch(url, payload, options);
}

async function apiDelete(url, options = {}) {
  return window.KOLConnectAPI.delete(url, options);
}

function t(key) {
  return (I18N[state.language] && I18N[state.language][key]) || key;
}

function showToast(message) {
  window.alert(message);
}

function showError(error) {
  const raw = String(error?.message || error || "");
  const lowered = raw.toLowerCase();
  const message = lowered.includes("failed to fetch") || lowered.includes("networkerror")
    ? "服务连接失败，请确认 KOLConnect 正在运行。"
    : lowered.includes("traceback")
      ? "操作失败，请查看系统日志中的详细原因。"
      : raw || "操作失败，请查看系统日志中的详细原因。";
  showToast(message);
}

function showSaved(message = t("saved")) {
  showToast(message);
}

function formatMailReplySyncSummary(data) {
  if ((state.language || "zh") === "en") {
    return `${t("mailReplySyncUpdated")} ${data.updated || 0}, time only ${data.time_only || 0}, ${t("mailReplySyncProcessed")} ${data.processed_messages || 0}, ${t("mailReplySyncSkipped")} ${data.skipped || 0}, ${t("mailReplySyncFailed")} ${data.failed || 0}`;
  }
  return `${t("mailReplySyncUpdated")} ${data.updated || 0} 位达人，仅更新最近联系时间 ${data.time_only || 0} 位，${t("mailReplySyncProcessed")} ${data.processed_messages || 0} 封邮件，${t("mailReplySyncSkipped")} ${data.skipped || 0} 位，${t("mailReplySyncFailed")} ${data.failed || 0} 位`;
}

function crmSyncStatusLabel(message) {
  if (message.crm_sync_status === "failed") return t("mailCrmFailed");
  if (message.crm_synced || message.crm_sync_status === "synced") return t("mailCrmSynced");
  return t("mailCrmPending");
}

function crmSyncStatusTone(message) {
  if (message.crm_sync_status === "failed") return "failed";
  if (message.crm_synced || message.crm_sync_status === "synced") return "success";
  return "pending";
}

async function openResults() {
  if (!state.currentTaskId) {
    throw new Error(state.language === "en" ? "Select a task first." : "请选择任务。")
  }
  await apiPost(`/api/tasks/${encodeURIComponent(state.currentTaskId)}/results/open`, {});
}

async function openResultFolder() {
  if (!state.currentTaskId) {
    throw new Error(state.language === "en" ? "Select a task first." : "请选择任务。")
  }
  await apiPost(`/api/tasks/${encodeURIComponent(state.currentTaskId)}/results/open-folder`, {});
}

async function copyText(text) {
  await navigator.clipboard.writeText(text);
  showSaved();
}

function reviewField(record, field) {
  return String(record?.[field] ?? "");
}

function reviewFilteredRecords() {
  const query = valueOf("review-search").trim().toLowerCase();
  const filter = valueOf("review-status-filter");
  return state.review.records.filter(record => {
    const matchesQuery = !query || ["平台", "账号名", "达人名称", "邮箱"]
      .some(field => reviewField(record, field).toLowerCase().includes(query));
    const scrapeStatus = reviewField(record, "scrape_status");
    const attention = reviewField(record, "review_state") === "rejected" || scrapeStatus !== "success";
    const failed = ["failed", "missing_data", "login_required", "platform_error"].includes(scrapeStatus);
    return matchesQuery && (!filter || (filter === "attention" && attention) || (filter === "failed" && failed));
  });
}

function reviewCell(row, value, className = "") {
  const cell = document.createElement("td");
  if (className) cell.className = className;
  const content = document.createElement("span");
  content.className = "review-readonly";
  content.textContent = value || "--";
  cell.appendChild(content);
  row.appendChild(cell);
  return cell;
}

function reviewEditableCell(row, value, field, multiline = false, inputType = "text") {
  const cell = document.createElement("td");
  const input = document.createElement(multiline ? "textarea" : "input");
  if (!multiline) input.type = inputType;
  if (inputType === "number") {
    input.min = "0";
    input.step = "1";
    input.inputMode = "numeric";
  }
  input.value = value;
  input.dataset.reviewField = field;
  cell.appendChild(input);
  row.appendChild(cell);
}

function renderReviewPagination(total, pageSize) {
  const pagination = $("review-pagination");
  if (!pagination) return;
  pagination.textContent = "";
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const goToPage = page => {
    const normalized = Math.min(totalPages, Math.max(1, Number(page) || 1));
    state.review.page = normalized;
    renderReviewResults();
  };
  const button = (label, page, disabled = false, active = false) => {
    const item = document.createElement("button");
    item.type = "button";
    item.className = "mini-btn";
    item.textContent = label;
    item.disabled = disabled;
    if (active) item.classList.add("active");
    item.addEventListener("click", () => goToPage(page));
    return item;
  };
  pagination.append(button(state.language === "en" ? "First" : "首页", 1, state.review.page <= 1));
  const previous = document.createElement("button");
  previous.type = "button";
  previous.className = "mini-btn";
  previous.textContent = state.language === "en" ? "Previous" : "上一页";
  previous.disabled = state.review.page <= 1;
  previous.addEventListener("click", () => goToPage(state.review.page - 1));
  pagination.appendChild(previous);

  const pages = new Set([1, totalPages]);
  for (let page = state.review.page - 2; page <= state.review.page + 2; page += 1) {
    if (page >= 1 && page <= totalPages) pages.add(page);
  }
  let previousPage = 0;
  [...pages].sort((a, b) => a - b).forEach(page => {
    if (previousPage && page - previousPage > 1) {
      const ellipsis = document.createElement("span");
      ellipsis.textContent = "…";
      pagination.appendChild(ellipsis);
    }
    pagination.append(button(String(page), page, false, page === state.review.page));
    previousPage = page;
  });
  const next = document.createElement("button");
  next.type = "button";
  next.className = "mini-btn";
  next.textContent = state.language === "en" ? "Next" : "下一页";
  next.disabled = state.review.page >= totalPages;
  next.addEventListener("click", () => goToPage(state.review.page + 1));
  pagination.append(next, button(state.language === "en" ? "Last" : "尾页", totalPages, state.review.page >= totalPages));

  const jumpLabel = document.createElement("span");
  jumpLabel.textContent = state.language === "en" ? "Go to" : "跳转到";
  const jumpInput = document.createElement("input");
  jumpInput.type = "number";
  jumpInput.min = "1";
  jumpInput.max = String(totalPages);
  jumpInput.value = String(state.review.page);
  jumpInput.className = "review-page-jump";
  const jumpButton = document.createElement("button");
  jumpButton.type = "button";
  jumpButton.className = "mini-btn";
  jumpButton.textContent = state.language === "en" ? "Go" : "确认";
  jumpButton.addEventListener("click", () => goToPage(jumpInput.value));
  jumpInput.addEventListener("keydown", event => {
    if (event.key === "Enter") goToPage(jumpInput.value);
  });
  pagination.append(jumpLabel, jumpInput, jumpButton);
}

function reviewScrapeStatusLabel(status) {
  const labels = {
    success: "正常完成",
    partial_success: "部分完成",
    missing_data: "缺少有效数据",
    failed: "抓取失败",
    login_required: "需要重新登录",
    platform_error: "平台异常"
  };
  return labels[String(status || "success").trim()] || String(status || "success");
}

function isRetryableReviewStatus(status) {
  return ["missing_data", "failed", "login_required", "platform_error"].includes(String(status || "").trim());
}

function reviewPrimaryResultLabel(status) {
  const normalized = String(status || "").trim();
  if (normalized === "success") return "已获取";
  if (normalized === "partial_success") return "部分待补充";
  if (["missing_data", "login_required", "platform_error"].includes(normalized)) return "待补充资料";
  return "抓取异常";
}

function pendingReviewRecords() {
  return state.review.records.filter(record => record.review_eligible === true && record.review_state === "pending");
}

function reviewQueueField(label, field, value, multiline = false) {
  const labelElement = document.createElement("label");
  labelElement.className = "field";
  const title = document.createElement("span");
  title.textContent = label;
  const input = document.createElement(multiline ? "textarea" : "input");
  input.value = value || "";
  input.dataset.queueField = field;
  labelElement.append(title, input);
  return labelElement;
}

async function submitReviewQueueAction(action, record) {
  if (state.review.submitting || !state.review.taskId) return;
  const actions = $("review-queue-actions");
  const fields = {};
  document.querySelectorAll("[data-queue-field]").forEach(input => {
    fields[input.dataset.queueField] = input.value;
  });
  const payload = { account_uid: reviewField(record, "account_uid"), action };
  if (action === "reject") payload.rejection_reason = fields.rejection_reason || "";
  if (action === "edit_approve") {
    delete fields.rejection_reason;
    payload.fields = fields;
  }
  state.review.submitting = true;
  actions?.querySelectorAll("button").forEach(button => { button.disabled = true; });
  try {
    await apiPost(`/api/tasks/${encodeURIComponent(state.review.taskId)}/results/review`, payload);
    await loadReviewResults();
    showSaved(action === "reject" ? "已拒绝，已切换至下一条。" : "已审核，已切换至下一条。");
  } catch (error) {
    if (String(error?.message || error).includes("REVIEW_CREATOR_MUTATION_FAILED")) {
      await loadReviewResults();
    }
    showError(error);
  } finally {
    state.review.submitting = false;
    renderReviewQueue();
  }
}

function renderReviewQueue() {
  const panel = $("review-queue");
  const progress = $("review-queue-progress");
  const queueState = $("review-queue-state");
  const current = $("review-queue-current");
  const actions = $("review-queue-actions");
  if (!panel || !progress || !queueState || !current || !actions) return;
  const queue = pendingReviewRecords();
  panel.hidden = !state.review.taskId;
  current.textContent = "";
  actions.textContent = "";
  progress.textContent = `审核进度 ${state.review.reviewedCount} / ${state.review.reviewTotal}，剩余 ${state.review.pendingCount} 条`;
  if (!state.review.reviewTotal) {
    queueState.textContent = "暂无待审核结果";
    return;
  }
  if (!queue.length) {
    queueState.textContent = "当前任务审核完成";
    return;
  }
  queueState.textContent = `待审核 ${queue.length} 条`;
  const record = queue[0];
  const identity = document.createElement("p");
  identity.className = "hint";
  identity.textContent = `${reviewField(record, "平台")} · ${reviewField(record, "达人名称") || "未命名达人"} · ${reviewField(record, "达人链接")}`;
  const fields = document.createElement("div");
  fields.className = "form-grid two";
  fields.append(
    reviewQueueField("达人名称", "达人名称", reviewField(record, "达人名称")),
    reviewQueueField("邮箱", "邮箱", reviewField(record, "邮箱")),
    reviewQueueField("粉丝数", "粉丝数", reviewField(record, "粉丝数")),
    reviewQueueField("WhatsApp", "WhatsApp", reviewField(record, "WhatsApp")),
    reviewQueueField("备注", "备注", reviewField(record, "备注"), true),
    reviewQueueField("拒绝原因（可选）", "rejection_reason", "", true),
  );
  current.append(identity, fields);
  [
    ["approve", "通过", "primary-btn"],
    ["reject", "拒绝", "soft-btn"],
    ["edit_approve", "编辑并通过", "soft-btn"],
  ].forEach(([action, label, className]) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = className;
    button.textContent = label;
    button.disabled = state.review.submitting;
    button.addEventListener("click", () => submitReviewQueueAction(action, record));
    actions.appendChild(button);
  });
}

async function retryAllFailedReviewRecords() {
  if (!state.review.taskId) throw new Error("请选择任务。");
  const data = await apiPost(`/api/tasks/${encodeURIComponent(state.review.taskId)}/results/retry-failed`, {
    profile: valueOf("profile-select")
  });
  showSaved(`已在当前任务中开始重新抓取（${data.retried_count || 0} 条）。`);
  await loadTaskList();
  await refreshScrapeStatus();
}

async function retryFailedReviewRecord(record) {
  const accountUid = reviewField(record, "account_uid");
  if (!accountUid || !state.review.taskId) return;
  const data = await apiPost(`/api/tasks/${encodeURIComponent(state.review.taskId)}/results/retry-failed`, {
    account_uids: [accountUid],
    profile: valueOf("profile-select")
  });
  showSaved(`已在当前任务中开始重新抓取（${data.retried_count || 0} 条）。`);
  await loadTaskList();
  await refreshScrapeStatus();
}

function readableAccountHomepage(rawUrl) {
  try {
    const url = new URL(String(rawUrl || ""));
    const host = url.hostname.replace(/^www\./i, "");
    let path = url.pathname.replace(/\/$/, "");
    if (/youtube\.com$/i.test(host) && /^\/channel\/[^/]+/i.test(path)) {
      const channelId = path.split("/")[2] || "";
      path = `/channel/${channelId.length > 12 ? `${channelId.slice(0, 12)}…` : channelId}`;
    }
    return `${host}${path}` || host;
  } catch (_error) {
    return "--";
  }
}

function selectedEmailSource() {
  return document.querySelector('input[name="email-source"]:checked')?.value || "task";
}

function selectedEmailPlatforms() {
  return [...document.querySelectorAll(".email-platform-option:checked")].map(input => input.value);
}

function emailMissingOnly() {
  return (document.querySelector('input[name="email-scope"]:checked')?.value || "missing") === "missing";
}

function emailStatusLabel(status) {
  return {
    created: "已获取",
    updated: "已获取",
    unchanged: "已存在",
    email_not_found: "未找到",
    capture_failed: "页面无法访问",
    login_required: "需要人工确认",
    platform_error: "页面无法访问",
    profile_identity_unresolved: "需要人工确认",
    ambiguous_account: "需要人工确认",
    email_conflict: "邮箱冲突，未覆盖",
    pending: "待抓取",
  }[String(status || "")] || "待抓取";
}

function renderEmailEnrichmentRows(rows) {
  const body = $("email-enrichment-results");
  const wrap = $("email-enrichment-results-wrap");
  if (!body || !wrap) return;
  body.textContent = "";
  rows.forEach(item => {
    const row = document.createElement("tr");
    const values = [
      item.platform || "--",
      readableAccountHomepage(item.profile_url),
      item.email || "—",
      item.email_source || "—",
      emailStatusLabel(item.status),
    ];
    values.forEach((value, index) => {
      const cell = document.createElement("td");
      if (index === 1 && /^https?:\/\//i.test(item.profile_url || "")) {
        const link = document.createElement("a");
        link.href = item.profile_url;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        link.textContent = value;
        cell.appendChild(link);
      } else {
        cell.textContent = value;
      }
      row.appendChild(cell);
    });
    body.appendChild(row);
  });
  wrap.hidden = rows.length === 0;
}

function renderEmailSourceControls() {
  const source = selectedEmailSource();
  state.emailEnrichment.source = source;
  $("email-existing-source-fields").hidden = source === "manual";
  $("email-manual-source-field").hidden = source !== "manual";
  $("email-scope-selector").hidden = source === "manual";
  $("email-source-task-field").hidden = source === "creator_library";
  state.emailEnrichment.previewed = false;
  $("email-enrichment-start").disabled = true;
  setText("email-enrichment-summary", "请选择来源并预览待处理账号。");
  renderEmailEnrichmentRows([]);
}

function renderEmailTaskOptions() {
  const select = $("email-source-task");
  if (!select) return;
  const selected = select.value || state.currentTaskId;
  select.replaceChildren();
  state.tasks.filter(task => task.task_type !== "manual").forEach(task => {
    select.add(new Option(`${task.name || "未命名任务"} · 原始链接 ${task.total_links || 0}`, task.id));
  });
  if ([...select.options].some(option => option.value === selected)) select.value = selected;
}

async function previewEmailEnrichment() {
  const source = selectedEmailSource();
  if (source === "manual") {
    const links = valueOf("email-manual-links").split(/\r?\n/).map(value => value.trim()).filter(Boolean);
    if (!links.length) throw new Error("请粘贴至少一个主页或视频链接。");
    state.emailEnrichment.candidates = links.map(profileUrl => ({ profile_url: profileUrl, status: "pending" }));
    state.emailEnrichment.previewed = true;
    setText("email-enrichment-summary", `待处理链接：${links.length}`);
    renderEmailEnrichmentRows(state.emailEnrichment.candidates);
    $("email-enrichment-start").disabled = false;
    return;
  }
  const taskId = source === "creator_library" ? "" : valueOf("email-source-task");
  if (source !== "creator_library" && !taskId) throw new Error("请选择抓取任务。");
  const params = new URLSearchParams({ source, task_id: taskId, missing_only: String(emailMissingOnly()) });
  selectedEmailPlatforms().forEach(platform => params.append("platform", platform));
  const data = await apiGet(`/api/tasks/email-recheck/candidates?${params}`);
  state.emailEnrichment = { candidates: data.candidates || [], previewed: true, source, taskId };
  setText("email-enrichment-summary", `总账号：${data.scanned_accounts || 0} · 待处理：${data.candidate_count || 0} · 缺少邮箱：${data.missing_email_count || 0}`);
  renderEmailEnrichmentRows(state.emailEnrichment.candidates);
  $("email-enrichment-start").disabled = !state.emailEnrichment.candidates.length;
}

async function startEmailEnrichment() {
  if (!state.emailEnrichment.previewed) throw new Error("请先预览待处理账号。");
  const source = state.emailEnrichment.source;
  const button = $("email-enrichment-start");
  button.disabled = true;
  if (source === "manual") {
    const results = [];
    for (const candidate of state.emailEnrichment.candidates) {
      try {
        const data = await apiPost("/api/creator-library/email-capture", { url: candidate.profile_url });
        results.push({
          platform: data.resolution?.platform || "",
          profile_url: data.resolution?.canonical_profile_url || candidate.profile_url,
          email: data.email || "",
          email_source: data.email_source || "",
          status: data.status,
        });
      } catch (_error) {
        results.push({ ...candidate, status: "capture_failed" });
      }
    }
    state.emailEnrichment.candidates = results;
    renderEmailEnrichmentRows(results);
    const found = results.filter(item => ["created", "updated", "unchanged"].includes(item.status)).length;
    setText("email-enrichment-summary", `处理完成：${results.length} · 已获取/已有：${found} · 未找到或需处理：${results.length - found}`);
    button.disabled = false;
    return;
  }
  const data = await apiPost("/api/tasks/email-recheck/scan", {
    source,
    task_id: state.emailEnrichment.taskId,
    platforms: selectedEmailPlatforms(),
    missing_only: emailMissingOnly(),
  });
  if (!data.task) throw new Error("当前范围没有需要抓取邮箱的账号。");
  state.currentTaskId = data.task.id;
  state.currentTask = data.task;
  window.localStorage.setItem("kolconnect.currentTaskId", data.task.id);
  await apiPost("/api/scrape/start", { taskId: data.task.id, profile: valueOf("profile-select"), platforms: selectedEmailPlatforms() });
  await loadTaskList();
  await refreshScrapeStatus();
  showSaved(`邮箱补全任务已开始：${data.created_count || 0} 个账号。`);
}

async function openReviewEmailEnrichment() {
  if (!state.review.taskId) throw new Error("请选择审核任务。");
  const source = document.querySelector('input[name="email-source"][value="review_results"]');
  const taskSelect = $("email-source-task");
  if (!source || !taskSelect) throw new Error("邮箱补全入口暂不可用。");
  source.checked = true;
  await setPage("scrape");
  renderEmailTaskOptions();
  taskSelect.value = state.review.taskId;
  renderEmailSourceControls();
  setText("email-enrichment-summary", "已选中当前审核任务；默认仅处理缺少邮箱的账号。");
}

function renderReviewResults() {
  const body = $("review-results-body");
  const empty = $("review-empty");
  const summary = $("review-summary");
  if (!body || !empty || !summary) return;
  body.textContent = "";
  const records = reviewFilteredRecords();
  const pageSize = Number(valueOf("review-page-size", "20")) || 20;
  const totalPages = Math.max(1, Math.ceil(records.length / pageSize));
  state.review.page = Math.min(Math.max(1, state.review.page), totalPages);
  const start = (state.review.page - 1) * pageSize;
  const visible = records.slice(start, start + pageSize);

  empty.hidden = visible.length > 0;
  empty.textContent = state.review.taskId ? t("reviewNoRecords") : t("reviewSelectTask");
  summary.textContent = state.review.taskId
    ? t("reviewSummary").replace("{count}", records.length).replace("{shown}", visible.length)
    : t("reviewSelectTask");
  if (state.review.taskId) {
    const statusCounts = { success: 0, partial_success: 0, missing_data: 0, failed: 0, login_required: 0, platform_error: 0 };
    state.review.records.forEach(record => {
      const status = reviewField(record, "scrape_status") || "success";
      if (Object.hasOwn(statusCounts, status)) statusCounts[status] += 1;
    });
    const labels = { tiktok: "TikTok", instagram: "Instagram", youtube: "YouTube" };
    const platforms = (state.review.platforms || []).map(item => labels[item] || item).join("、") || "全部";
    const counts = state.review.platformResults || {};
    summary.textContent += `\n成功：${statusCounts.success} / 部分成功：${statusCounts.partial_success} / 缺少数据：${statusCounts.missing_data} / 失败：${statusCounts.failed + statusCounts.login_required + statusCounts.platform_error}`;
    summary.textContent += `\n本次抓取：${platforms}\n结果：TikTok ${counts.TikTok || 0} / Instagram ${counts.Instagram || 0} / YouTube ${counts.YouTube || 0}`;
  }

  visible.forEach(record => {
    const row = document.createElement("tr");
    reviewCell(row, reviewField(record, "平台"));
    const profileUrl = reviewField(record, "达人链接");
    const profileCell = document.createElement("td");
    if (/^https?:\/\//i.test(profileUrl)) {
      const link = document.createElement("a");
      link.href = profileUrl;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.className = "account-homepage-link";
      link.textContent = readableAccountHomepage(profileUrl);
      link.title = readableAccountHomepage(profileUrl);
      profileCell.appendChild(link);
    } else profileCell.textContent = "--";
    row.appendChild(profileCell);
    reviewCell(row, reviewPrimaryResultLabel(reviewField(record, "scrape_status")));
    reviewCell(row, reviewField(record, "最近发布日期"));
    reviewEditableCell(row, reviewField(record, "邮箱"), "邮箱");
    reviewEditableCell(row, reviewField(record, "粉丝数"), "粉丝数");
    reviewEditableCell(row, reviewField(record, "WhatsApp"), "WhatsApp");
    reviewEditableCell(row, reviewField(record, "备注"), "备注", true);
    reviewCell(row, reviewField(record, "数据状态"));

    const actionCell = document.createElement("td");
    const saveButton = document.createElement("button");
    saveButton.type = "button";
    saveButton.className = "mini-btn";
    saveButton.textContent = t("reviewSave");
    saveButton.addEventListener("click", async () => {
      try {
        const fields = {};
        row.querySelectorAll("[data-review-field]").forEach(input => {
          fields[input.dataset.reviewField] = input.value;
        });
        saveButton.disabled = true;
        await apiPost(`/api/tasks/${encodeURIComponent(state.review.taskId)}/results/update`, {
          account_uid: reviewField(record, "account_uid"),
          fields
        });
        showSaved(t("reviewSaved"));
        await loadReviewResults();
      } catch (error) {
        showError(error);
      } finally {
        saveButton.disabled = false;
      }
    });
    actionCell.appendChild(saveButton);
    if (isRetryableReviewStatus(reviewField(record, "scrape_status"))) {
      const retryButton = document.createElement("button");
      retryButton.type = "button";
      retryButton.className = "mini-btn";
      retryButton.textContent = "重新抓取";
      retryButton.addEventListener("click", async () => {
        retryButton.disabled = true;
        try {
          await retryFailedReviewRecord(record);
        } catch (error) {
          showError(error);
        } finally {
          retryButton.disabled = false;
        }
      });
      actionCell.appendChild(retryButton);
    }
    row.appendChild(actionCell);
    body.appendChild(row);
  });
  renderReviewPagination(records.length, pageSize);
}

async function loadReviewResults() {
  if (!state.review.taskId) {
    state.review.records = [];
    renderReviewResults();
    return;
  }
  const data = await apiGet(`/api/tasks/${encodeURIComponent(state.review.taskId)}/results`);
  state.review.records = Array.isArray(data.records) ? data.records : [];
  state.review.platforms = Array.isArray(data.platforms) ? data.platforms : [];
  state.review.platformResults = data.platform_results || {};
  state.review.reviewTotal = Number(data.review_total || 0);
  state.review.reviewedCount = Number(data.reviewed_count || 0);
  state.review.pendingCount = Number(data.pending_count || 0);
  renderReviewResults();
}

async function loadReviewTasks() {
  const select = $("review-task-select");
  if (!select) return;
  const data = await apiGet("/api/tasks");
  const tasks = Array.isArray(data.tasks) ? data.tasks : [];
  const selected = state.review.taskId || state.currentTaskId;
  state.review.tasks = tasks;
  select.textContent = "";

  if (!tasks.length) {
    state.review.taskId = "";
    select.add(new Option(t("reviewNoTasks"), ""));
    $("review-summary").textContent = t("reviewNoTasks");
    state.review.records = [];
    renderReviewResults();
    return;
  }

  tasks.forEach(task => {
    const createdAt = String(task.created_at || "").replace("T", " ").replace("Z", "");
    const label = `${task.name || task.id} · ${createdAt} · ${task.valid_count || 0} links · ${task.status || ""}`;
    select.add(new Option(label, task.id, false, task.id === selected));
  });
  state.review.taskId = select.value || tasks[0].id;
  if (select.value !== state.review.taskId) select.value = state.review.taskId;
  state.review.page = 1;
  await loadReviewResults();
}

function healthStatusLabel(status) {
  return status === "ok" ? "正常" : status === "warning" ? "需要关注" : "异常";
}

function renderSystemHealth(data) {
  const result = $("system-health-result");
  const info = $("debug-system-info");
  if (!result || !info) return;
  const checks = Array.isArray(data?.checks) ? data.checks : [];
  result.hidden = false;
  result.replaceChildren(...checks.map(check => {
    const item = document.createElement("p");
    item.className = `health-check-${check.status || "warning"}`;
    const icon = check.status === "ok" ? "✓" : check.status === "warning" ? "!" : "×";
    item.textContent = `${icon} ${check.label || "检查项目"}：${check.message || healthStatusLabel(check.status)}`;
    return item;
  }));
  const debug = data?.debug || {};
  info.replaceChildren(...[
    ["版本", debug.version || "KOLConnect v1.0.0"],
    ["API状态", debug.api_status || "正常"],
    ["Excel路径", debug.excel_path || "--"],
    ["Excel状态", healthStatusLabel(debug.excel_status)],
    ["最后一次插件导入", debug.last_extension_import?.time || "暂无记录"],
    ["最后错误", debug.last_error?.message || "暂无"],
  ].map(([label, value]) => {
    const item = document.createElement("p");
    item.textContent = `${label}：${value}`;
    return item;
  }));
}

function setDebugModeVisible(enabled) {
  const info = $("debug-system-info");
  if (info) info.hidden = !enabled;
}

async function loadSystemHealth(options = {}) {
  const data = await apiGet("/api/system/health", options);
  renderSystemHealth(data);
  return data;
}

function setPage(pageName, params = {}) {
  if (pageName === "creator-library" || pageName === "creator-library-detail") {
    return window.KOLConnectPages.navigate(pageName, {
      state,
      api: window.KOLConnectAPI,
      resources: window.KOLConnectPageResources.create(),
      params,
      navigate: setPage,
      ui: { showSaved, showError },
    });
  }
  return window.KOLConnectPages.navigate(pageName, params);
}

function registerLegacyPages() {
  const registry = window.KOLConnectPages;
  const noop = () => {};
  const pageLoaders = {
    review: () => loadReviewTasks(),
  };
  [
    "scrape", "task-details", "review", "discover", "accounts",
    "mail", "mail-accounts", "logs",
  ].forEach(pageName => {
    if (registry.getPage(pageName)) return;
    registry.registerPage(pageName, {
      load: pageLoaders[pageName] || noop,
      bind: noop,
      unbind: noop,
    });
  });
}

function renderStaticText() {
  document.title = t("appTitle");
  document.querySelectorAll("[data-i18n]").forEach(el => {
    const key = el.dataset.i18n;
    if (t(key) !== key) el.textContent = t(key);
  });
  document.querySelectorAll("[data-i18n-placeholder]").forEach(el => {
    const key = el.dataset.i18nPlaceholder;
    if (t(key) !== key) el.placeholder = t(key);
  });
  const scrapeLog = $("scrape-log");
  const logsPanel = $("logs-panel");
  if (scrapeLog) scrapeLog.textContent ||= t("waiting");
  if (logsPanel) logsPanel.textContent ||= t("waiting");
}

function renderProfiles(profiles, selected) {
  const profileSelect = $("profile-select");
  const defaultProfile = $("default-profile");
  if (!profileSelect || !defaultProfile) return;
  profileSelect.innerHTML = "";
  defaultProfile.innerHTML = "";
  profiles.forEach(profile => {
    const option = new Option(profile, profile, false, profile === selected);
    const option2 = new Option(profile, profile, false, profile === selected);
    profileSelect.add(option);
    defaultProfile.add(option2);
  });
}

function renderFourTableConfig(feishu) {
  setValue("feishu-app-id", feishu.app_id || "");
  // The API never returns the saved secret, so always start with an empty field.
  setValue("feishu-app-secret", "");
  setValue("feishu-app-token", feishu.app_token || "");
  setValue("feishu-creator-table-id", feishu.creator_table_id || "");
  setValue("feishu-account-table-id", feishu.account_table_id || "");
  setValue("feishu-contact-table-id", feishu.contact_table_id || "");
}

function renderCreatorLibraryConfig(config) {
  setValue("creator-library-workbook-path", config?.workbook_path || "");
}

function renderGoogleSheetsConfig(config) {
  setValue("google-sheets-client-id", config?.client_id || "");
  setValue("google-sheets-client-secret", "");
  setValue("google-sheets-spreadsheet-id", config?.spreadsheet_id || "");
  const labels = { CONNECTED: "已连接", NOT_CONNECTED: "未连接", NOT_CONFIGURED: "未配置" };
  setText("google-sheets-status", labels[config?.status] || "未配置");
}

function renderSettingsState(data) {
  state.language = data.ui?.language || "zh";
  setValue("ui-language", state.language);
  const debugMode = !!data.ui?.debug_mode;
  const debugInput = $("debug-mode");
  if (debugInput) debugInput.checked = debugMode;
  setDebugModeVisible(debugMode);
  renderStaticText();
  renderProfiles(data.profiles || [], data.selectedProfile || "Default");
  renderFourTableConfig(data.feishu || {});
  renderGoogleSheetsConfig(data.google_sheets || {});
  renderCreatorLibraryConfig(data.creator_library || {});
  return debugMode;
}

async function loadSettingsState(options = {}) {
  const data = await apiGet("/api/state", options);
  const debugMode = renderSettingsState(data);
  if (debugMode) {
    loadSystemHealth(options).catch(error => {
      if (error?.name !== "AbortError") console.warn("[KOLConnect] health check unavailable", error);
    });
  }
  return data;
}

function renderAccounts(accounts) {
  const wrap = $("accounts-list");
  if (!wrap) return;
  wrap.innerHTML = "";
  if (!accounts || accounts.length === 0) {
    wrap.innerHTML = `<div class="empty-note">${t("noAccounts")}</div>`;
    return;
  }

  accounts.forEach(account => {
    const row = document.createElement("article");
    row.className = "chrome-profile-card";
    const field = (label, key, value, readOnly = false) => {
      const wrap = document.createElement("div");
      wrap.className = "field-inline";
      const title = document.createElement("label");
      title.textContent = label;
      const input = document.createElement("input");
      input.type = "text";
      input.dataset.key = key;
      input.value = String(value || "");
      input.readOnly = readOnly;
      wrap.append(title, input);
      return wrap;
    };
    row.append(
      field("Chrome Profile", "profile", account.profile, true),
      field("备注名", "alias", account.alias),
      field("备注", "note", account.note),
    );
    const status = document.createElement("span");
    status.className = "hint";
    status.textContent = account.is_automation
      ? "KOLConnect 独立自动化 Profile"
      : (account.available ? "可用" : "不可用");
    const selected = document.createElement("span");
    selected.className = "hint";
    selected.textContent = account.is_default ? "当前默认 Profile" : "";
    const open = document.createElement("button");
    open.type = "button";
    open.className = "mini-btn";
    open.textContent = "打开浏览器";
    open.disabled = !account.available;
    open.addEventListener("click", async () => {
      try {
        await apiPost("/api/account/open", { profile: account.profile });
        showSaved(`已打开：${account.profile}${account.alias ? ` · ${account.alias}` : ""}`);
      } catch (error) {
        showError(error);
      }
    });
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "mini-btn";
    remove.textContent = "移除配置";
    remove.addEventListener("click", () => {
      if (window.confirm(`删除 ${account.profile} 的 KOLConnect 配置？不会删除 Chrome 浏览器资料。`)) row.remove();
    });
    const statusGroup = document.createElement("div");
    statusGroup.className = "chrome-profile-status";
    statusGroup.append(status, selected);
    const actions = document.createElement("div");
    actions.className = "chrome-profile-actions";
    actions.append(open, remove);
    row.append(statusGroup, actions);
    wrap.append(row);
  });
}

function getMailProviderOptions() {
  return [
    { value: "aliyun", label: t("mailProviderAliyun") },
    { value: "netease", label: t("mailProviderNetease") },
    { value: "gmail", label: t("mailProviderGmail") },
    { value: "custom", label: t("mailProviderCustom") }
  ];
}

function getMailProviderDefaults(provider) {
  return MAIL_PROVIDER_DEFAULTS[provider] || {};
}

function normalizeMailAccount(account = {}) {
  return {
    name: account.name || "",
    provider: account.provider || "custom",
    email: account.email || "",
    sender_name: account.sender_name || "",
    imap_host: account.imap_host || "",
    imap_port: account.imap_port || "",
    smtp_host: account.smtp_host || "",
    smtp_port: account.smtp_port || "",
    username: account.username || "",
    password: account.password || "",
    enabled: account.enabled !== false,
    connection_status: account.connection_status || "untested"
  };
}

function createEmptyMailAccount() {
  return normalizeMailAccount({ enabled: true, provider: "custom" });
}

function statusLabelForMail(status) {
  if (status === "success") return t("mailStatusSuccess");
  if (status === "failed") return t("mailStatusFailed");
  return t("mailStatusUntested");
}

function updateMailAccountStatus(card, status) {
  const badge = card.querySelector('[data-role="mail-status"]');
  if (!badge) return;
  badge.dataset.status = status;
  badge.textContent = statusLabelForMail(status);
}

function applyProviderDefaultsToCard(card, force = false) {
  const provider = textAreaOrInputValue(card, '[data-key="provider"]');
  const defaults = getMailProviderDefaults(provider);
  Object.entries(defaults).forEach(([key, value]) => {
    const input = card.querySelector(`[data-key="${key}"]`);
    if (input && (force || !String(input.value || "").trim())) {
      input.value = value;
    }
  });
}

function collectMailAccountFromCard(card) {
  return {
    name: textAreaOrInputValue(card, '[data-key="name"]'),
    provider: textAreaOrInputValue(card, '[data-key="provider"]') || "custom",
    email: textAreaOrInputValue(card, '[data-key="email"]'),
    sender_name: textAreaOrInputValue(card, '[data-key="sender_name"]'),
    imap_host: textAreaOrInputValue(card, '[data-key="imap_host"]'),
    imap_port: textAreaOrInputValue(card, '[data-key="imap_port"]'),
    smtp_host: textAreaOrInputValue(card, '[data-key="smtp_host"]'),
    smtp_port: textAreaOrInputValue(card, '[data-key="smtp_port"]'),
    username: textAreaOrInputValue(card, '[data-key="username"]'),
    password: card.querySelector('[data-key="password"]')?.value || "",
    enabled: !!card.querySelector('[data-key="enabled"]')?.checked
  };
}

function renderMailAccountCard(account = {}) {
  const item = normalizeMailAccount(account);
  const card = document.createElement("div");
  card.className = "mail-account-card";
  card.innerHTML = `
    <div class="mail-account-header">
      <div class="mail-account-header-main">
        <strong>${item.name || item.email || t("mailAccountsTitle")}</strong>
        <span class="status-pill" data-role="mail-status" data-status="${item.connection_status}">${statusLabelForMail(item.connection_status)}</span>
      </div>
      <div class="action-row">
        <button type="button" class="soft-btn" data-action="test">${t("mailTestConnection")}</button>
        <button type="button" class="danger-btn" data-action="delete">${t("mailDeleteAccount")}</button>
      </div>
    </div>
    <div class="form-grid two mail-account-grid">
      <label class="field"><span>${t("mailAccountName")}</span><input type="text" data-key="name" value="${item.name}"></label>
      <label class="field">
        <span>${t("mailProvider")}</span>
        <select data-key="provider">
          ${getMailProviderOptions().map(option => `<option value="${option.value}" ${option.value === item.provider ? "selected" : ""}>${option.label}</option>`).join("")}
        </select>
      </label>
      <label class="field"><span>${t("mailAddress")}</span><input type="text" data-key="email" value="${item.email}"></label>
      <label class="field"><span>${t("mailSenderName")}</span><input type="text" data-key="sender_name" value="${item.sender_name}"></label>
      <label class="field"><span>${t("mailImapHost")}</span><input type="text" data-key="imap_host" value="${item.imap_host}"></label>
      <label class="field"><span>${t("mailImapPort")}</span><input type="text" data-key="imap_port" value="${item.imap_port}"></label>
      <label class="field"><span>${t("mailSmtpHost")}</span><input type="text" data-key="smtp_host" value="${item.smtp_host}"></label>
      <label class="field"><span>${t("mailSmtpPort")}</span><input type="text" data-key="smtp_port" value="${item.smtp_port}"></label>
      <label class="field"><span>${t("mailUsername")}</span><input type="text" data-key="username" value="${item.username}"></label>
      <label class="field"><span>${t("mailPassword")}</span><input type="password" data-key="password" value="${item.password}"></label>
      <label class="checkbox-line mail-checkbox-line"><input type="checkbox" data-key="enabled" ${item.enabled ? "checked" : ""}><span>${t("mailEnabled")}</span></label>
    </div>
  `;
  card.querySelector('[data-action="delete"]').addEventListener("click", () => {
    card.remove();
    const wrap = $("mail-accounts-list");
    if (wrap && !wrap.querySelector(".mail-account-card")) {
      wrap.innerHTML = `<div class="empty-note">${t("mailEmptyAccounts")}</div>`;
    }
  });
  card.querySelector('[data-action="test"]').addEventListener("click", async () => {
    try {
      const accountPayload = collectMailAccountFromCard(card);
      await apiPost("/api/mail/test", { account: accountPayload });
      updateMailAccountStatus(card, "success");
      showSaved(t("mailTestSuccess"));
    } catch (error) {
      updateMailAccountStatus(card, "failed");
      showError(error);
    }
  });
  card.querySelector('[data-key="provider"]').addEventListener("change", () => {
    applyProviderDefaultsToCard(card, true);
    updateMailAccountStatus(card, "untested");
  });
  card.querySelectorAll('input, select').forEach(input => {
    input.addEventListener("input", () => updateMailAccountStatus(card, "untested"));
    input.addEventListener("change", () => updateMailAccountStatus(card, "untested"));
  });
  return card;
}

function renderMail(mail) {
  const wrap = $("mail-accounts-list");
  if (wrap) {
    wrap.innerHTML = "";
    const accounts = Array.isArray(mail.accounts) ? mail.accounts : [];
    if (accounts.length === 0) {
      wrap.innerHTML = `<div class="empty-note">${t("mailEmptyAccounts")}</div>`;
    } else {
      accounts.forEach(account => wrap.appendChild(renderMailAccountCard(account)));
    }
  }
  setValue("mail-template-subject", mail.template_subject || "");
  setValue("mail-template-body", mail.template_body || "");
}

function addMailAccount(account = createEmptyMailAccount()) {
  const wrap = $("mail-accounts-list");
  if (!wrap) return;
  if (wrap.querySelector(".empty-note")) wrap.innerHTML = "";
  wrap.appendChild(renderMailAccountCard(account));
}

function collectMailAccounts() {
  return Array.from(document.querySelectorAll("#mail-accounts-list .mail-account-card")).map(card => collectMailAccountFromCard(card));
}

function formatMailSyncUpdatedAt(value) {
  if (!value) return "--";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function createTextElement(tagName, className, text) {
  const element = document.createElement(tagName);
  if (className) element.className = className;
  element.textContent = String(text ?? "");
  return element;
}

function renderMailMessages() {
  const wrap = $("mail-inbox-messages");
  if (!wrap) return;
  wrap.replaceChildren();
  const matchedOnly = checkedOf("mail-matched-only");
  const filtered = matchedOnly
    ? state.mailInbox.messages.filter(message => message.reply_status === "matched")
    : state.mailInbox.messages;
  const pageSize = Number(valueOf("mail-page-size", state.mailInbox.pageSize)) || 20;
  state.mailInbox.pageSize = pageSize;
  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
  state.mailInbox.page = Math.min(Math.max(1, state.mailInbox.page), totalPages);
  const start = (state.mailInbox.page - 1) * pageSize;
  const messages = filtered.slice(start, start + pageSize);
  if (filtered.length === 0) {
    wrap.appendChild(createTextElement("div", "empty-note", t("mailInboxNoMessages")));
  } else messages.forEach(message => {
    const item = document.createElement("div");
    item.className = "mail-message-item";

    const head = document.createElement("div");
    head.className = "mail-message-head";
    head.appendChild(createTextElement("strong", "", message.subject || "(No subject)"));

    const actions = document.createElement("div");
    actions.className = "action-row";
    const readStatus = createTextElement(
      "span",
      "status-pill",
      message.is_unread ? t("mailInboxUnread") : t("mailInboxRead"),
    );
    readStatus.dataset.status = message.is_unread ? "failed" : "success";
    actions.appendChild(readStatus);

    const syncStatus = createTextElement("span", "status-pill", crmSyncStatusLabel(message));
    syncStatus.dataset.status = crmSyncStatusTone(message);
    actions.appendChild(syncStatus);
    head.appendChild(actions);
    item.appendChild(head);

    const metadata = [
      [t("mailInboxFrom"), message.from_name || message.from_email || "--"],
      [t("mailMatchedCreator"), message.matched_creator_name || "--"],
      [t("mailMatchedPlatform"), message.matched_platform || "--"],
      [t("mailReplyStatus"), message.reply_status === "matched" ? t("mailReplyMatched") : t("mailReplyUnmatched")],
      [t("mailCrmSyncStatus"), crmSyncStatusLabel(message)],
      [t("mailInboxReceivedAt"), formatMailSyncUpdatedAt(message.received_at || message.synced_at || "")],
    ];
    metadata.forEach(([label, value]) => {
      item.appendChild(createTextElement("div", "mail-message-meta", `${label}：${value}`));
    });
    item.appendChild(createTextElement("div", "mail-message-snippet", message.snippet || "--"));
    wrap.appendChild(item);
  });

  const pagination = $("mail-pagination");
  if (pagination) pagination.hidden = filtered.length === 0;
  setText("mail-page-total", `共 ${filtered.length} 封`);
  setText("mail-page-summary", `第 ${state.mailInbox.page} / ${totalPages} 页`);
  const previous = $("mail-page-previous");
  const next = $("mail-page-next");
  if (previous) previous.disabled = state.mailInbox.page <= 1;
  if (next) next.disabled = state.mailInbox.page >= totalPages;
}

function renderMailInbox(data = {}) {
  const summary = data.summary || {};
  setText("mail-summary-accounts", String(data.accounts_checked || Object.keys(data.accounts || {}).length || 0));
  setText("mail-summary-fetched", String(data.messages_fetched || 0));
  setText("mail-summary-new", String(data.messages_new || 0));
  setText("mail-summary-unread", String(summary.unread || 0));
  setText("mail-summary-matched", String(summary.matched || data.matched_messages || 0));
  setText("mail-inbox-updated-at", `${t("mailInboxUpdatedAt")}：${formatMailSyncUpdatedAt(data.updated_at || "")}`);
  state.mailInbox.messages = Array.isArray(data.messages) ? data.messages : [];
  renderMailMessages();
}

async function loadMailInbox() {
  try {
    const data = await apiGet("/api/mail/inbox/messages");
    renderMailInbox(data);
  } catch (error) {
    const wrap = $("mail-inbox-messages");
    if (wrap) {
      wrap.replaceChildren(createTextElement("div", "empty-note", error.message));
    }
  }
}

async function loadState(options = {}) {
  const data = await apiGet("/api/state", options);
  const debugMode = renderSettingsState(data);
  renderAccounts(data.accounts || []);
  renderMail(data.mail || {});
  await loadMailInbox();
  if (debugMode) loadSystemHealth().catch(error => console.warn("[KOLConnect] health check unavailable", error));
}

async function refreshScrapeStatus() {
  try {
    const data = await apiGet("/api/scrape/status");
    state.scrapeJob = data;
    const statusText = scrapeStatusLabel(data.status || (data.running ? "running" : "idle"));
    setText("scrape-log", data.logs || t("waiting"));
    setText("logs-panel", data.logs || t("waiting"));
    renderScrapeControls(data);
  } catch (error) {
    setText("scrape-log", error.message);
    setText("logs-panel", error.message);
  }
}

function collectAccounts() {
  return Array.from(document.querySelectorAll("#accounts-list .chrome-profile-card")).map(row => ({
    profile: textAreaOrInputValue(row, '[data-key="profile"]'),
    alias: textAreaOrInputValue(row, '[data-key="alias"]'),
    note: textAreaOrInputValue(row, '[data-key="note"]')
  })).filter(item => item.profile);
}

function clearDiscoverOutputs() {
  state.discover.results = [];
  state.discover.summary = {};
  setValue("discover-output", "");
  setValue("discover-invalid-output", "");
  setText("discover-count-input", "0");
  setText("discover-count-accepted", "0");
  setText("discover-count-duplicate", "0");
  setText("discover-count-rejected", "0");
  setText("discover-count-equation", "0 = 0 + 0 + 0");
  setValue("discover-status-filter", "");
  renderDiscoverDetails();
}

function clearDiscoverAll() {
  setValue("discover-input", "");
  clearDiscoverOutputs();
}

function formatInvalidLinks(items) {
  if (!Array.isArray(items)) return "";
  return items.map(item => {
    if (typeof item === "string") return item;
    const originalUrl = String(item?.original_url || "").trim();
    const reason = String(item?.reason || "").trim();
    return reason ? `${originalUrl}\n原因：${reason}` : originalUrl;
  }).filter(Boolean).join("\n\n");
}

function discoverStatusLabel(status) {
  return {
    valid: "有效",
    normalized: "已标准化",
    duplicate: "重复",
    invalid: "无效",
  }[status] || "未知";
}

function discoverPlatformLabel(platform) {
  return {
    tiktok: "TikTok",
    instagram: "Instagram",
    youtube: "YouTube",
  }[String(platform || "").toLowerCase()] || "未知";
}

function renderDiscoverDetails() {
  const body = $("discover-detail-body");
  const empty = $("discover-detail-empty");
  if (!body || !empty) return;
  const statusFilter = valueOf("discover-status-filter");
  const visible = state.discover.results.filter(item => !statusFilter || item.status === statusFilter);
  body.textContent = "";
  visible.forEach(item => {
    const row = document.createElement("tr");
    const duplicateNote = item.status === "duplicate" && item.duplicate_of_line
      ? `，与第 ${item.duplicate_of_line} 行重复`
      : "";
    [
      item.line_number,
      item.original,
      item.normalized || "--",
      discoverPlatformLabel(item.platform),
      discoverStatusLabel(item.status),
      `${item.reason || "--"}${duplicateNote}`,
    ].forEach(value => {
      const cell = document.createElement("td");
      cell.textContent = String(value ?? "");
      row.appendChild(cell);
    });
    row.dataset.status = item.status || "unknown";
    body.appendChild(row);
  });
  empty.hidden = visible.length > 0;
}

function renderDiscoverResults(data) {
  state.discover.results = Array.isArray(data?.link_results) ? data.link_results : [];
  state.discover.summary = data?.summary && typeof data.summary === "object" ? data.summary : {};
  const nonEmpty = Number(state.discover.summary.non_empty_count || 0);
  const accepted = Number(state.discover.summary.accepted_unique_count || 0);
  const duplicate = Number(state.discover.summary.duplicate_count || 0);
  const rejected = Number(state.discover.summary.rejected_count || 0);
  setValue("discover-output", (data?.normalized_links || []).join("\n"));
  setValue("discover-invalid-output", formatInvalidLinks(data?.invalid_links));
  setText("discover-count-input", String(nonEmpty));
  setText("discover-count-accepted", String(accepted));
  setText("discover-count-duplicate", String(duplicate));
  setText("discover-count-rejected", String(rejected));
  setText("discover-count-equation", `${nonEmpty} = ${accepted} + ${duplicate} + ${rejected}`);
  renderDiscoverDetails();
}

function updateTaskLinkCounts() {
  const text = valueOf("task-links");
  const lines = text ? text.split(/\r?\n/) : [];
  const nonEmpty = lines.map(line => line.trim()).filter(Boolean);
  const duplicateCount = nonEmpty.length - new Set(nonEmpty).size;
  setText("task-link-counts", `共 ${lines.length} 行 · 非空 ${nonEmpty.length} 行 · 原样重复 ${duplicateCount} 行`);
}

function updateTaskResultActions() {
  const folderButton = $("scrape-open-result-folder");
  if (folderButton) folderButton.disabled = !state.currentTaskId;
}

async function saveMailConfiguration(payload) {
  await apiPost("/api/settings/mail", payload);
  showSaved(t("mailSaveSuccess"));
  await loadState();
}

async function saveMailTemplate() {
  await saveMailConfiguration({
    template_subject: valueOf("mail-template-subject"),
    template_body: valueOf("mail-template-body")
  });
}

async function saveMailAccounts() {
  await saveMailConfiguration({ accounts: collectMailAccounts() });
}

function selectedTaskPlatforms() {
  return [...document.querySelectorAll(".task-platform-option:checked")]
    .map(input => String(input.value || "").trim())
    .filter(Boolean);
}

function bindTaskPlatformSelector() {
  const all = $("task-platform-all");
  const options = [...document.querySelectorAll(".task-platform-option")];
  if (!all || !options.length) return;
  const updateSummary = () => {
    const selected = options.filter(item => item.checked);
    const labels = selected.map(item => item.parentElement?.textContent?.trim()).filter(Boolean);
    setText("task-platform-summary", selected.length === options.length ? "全部平台" : labels.join("、") || "请选择平台");
  };
  all.addEventListener("change", () => {
    options.forEach(option => { option.checked = all.checked; });
    updateSummary();
  });
  options.forEach(option => {
    option.addEventListener("change", () => {
      all.checked = options.every(item => item.checked);
      updateSummary();
    });
  });
  updateSummary();
}

function bindEvents() {
  // Keep enrichment available, but place it after the primary discovery action.
  const capturePanel = $("capture-automatic-panel");
  const emailPanel = $("email-enrichment-card");
  if (capturePanel && emailPanel && capturePanel.parentElement === emailPanel.parentElement) {
    capturePanel.after(emailPanel);
  }
  bindTaskPlatformSelector();
  updateTaskLinkCounts();
  document.querySelectorAll(".nav-btn").forEach(btn => {
    btn.addEventListener("click", () => setPage(btn.dataset.page).catch(showError));
  });
  $("task-links").addEventListener("input", updateTaskLinkCounts);
  document.querySelectorAll('input[name="email-source"]').forEach(input => {
    input.addEventListener("change", renderEmailSourceControls);
  });
  ["email-source-task", "email-scope-selector"].forEach(id => {
    $(id).addEventListener("change", () => {
      state.emailEnrichment.previewed = false;
      $("email-enrichment-start").disabled = true;
    });
  });
  document.querySelectorAll(".email-platform-option").forEach(input => {
    input.addEventListener("change", () => {
      state.emailEnrichment.previewed = false;
      $("email-enrichment-start").disabled = true;
    });
  });
  $("email-enrichment-preview").addEventListener("click", () => previewEmailEnrichment().catch(showError));
  $("email-enrichment-start").addEventListener("click", () => startEmailEnrichment().catch(error => {
    $("email-enrichment-start").disabled = false;
    showError(error);
  }));
  renderEmailSourceControls();

  $("review-task-select").addEventListener("change", async () => {
    try {
      state.review.taskId = valueOf("review-task-select");
      state.review.page = 1;
      await loadReviewResults();
    } catch (error) {
      showError(error);
    }
  });
  $("review-search").addEventListener("input", () => {
    state.review.page = 1;
    renderReviewResults();
  });
  $("review-status-filter").addEventListener("change", () => {
    state.review.page = 1;
    renderReviewResults();
  });
  $("review-page-size").addEventListener("change", () => {
    state.review.page = 1;
    renderReviewResults();
  });
  $("task-detail-back").addEventListener("click", () => setPage("scrape").catch(showError));
  $("task-detail-refresh").addEventListener("click", () => loadTaskDetails().catch(showError));
  ["task-detail-search", "task-detail-platform", "task-detail-status"].forEach(id => {
    const eventName = id === "task-detail-search" ? "input" : "change";
    $(id).addEventListener(eventName, renderTaskDetails);
  });
  $("task-detail-add").addEventListener("click", async () => {
    try {
      if (!state.taskDetails.taskId) throw new Error("请选择任务。");
      const url = valueOf("task-detail-add-url").trim();
      if (!url) throw new Error("请输入达人主页链接。");
      await apiPost(`/api/tasks/${encodeURIComponent(state.taskDetails.taskId)}/links`, { action: "add", url });
      setValue("task-detail-add-url", "");
      await loadTaskDetails();
      await loadTaskList();
    } catch (error) { showError(error); }
  });
  $("review-refresh").addEventListener("click", () => {
    loadReviewTasks().catch(showError);
  });
  $("review-fill-missing-email").addEventListener("click", () => {
    openReviewEmailEnrichment().catch(showError);
  });
  $("review-retry-failed").addEventListener("click", async () => {
    try {
      const failedCount = state.review.records.filter(record => isRetryableReviewStatus(reviewField(record, "scrape_status"))).length;
      if (!failedCount) throw new Error("当前任务没有需要重新抓取的异常记录。 ");
      if (!window.confirm(`将在当前任务中重新抓取 ${failedCount} 条异常记录，是否继续？`)) return;
      await retryAllFailedReviewRecords();
    } catch (error) {
      showError(error);
    }
  });
  $("review-scan-missing-email").addEventListener("click", async () => {
    if (!window.confirm(t("reviewScanMissingEmailConfirm"))) return;
    try {
      const data = await apiPost("/api/tasks/email-recheck/scan", {});
      const task = data.task || null;
      if (task) {
        state.currentTaskId = task.id;
        state.currentTask = task;
        state.review.taskId = task.id;
        window.localStorage.setItem("kolconnect.currentTaskId", task.id);
      }
      await loadTaskList();
      await loadReviewTasks();
      if (task) await loadReviewResults();
      showSaved(t("reviewScanMissingEmailResult")
        .replace("{scanned}", String(data.scanned_accounts || 0))
        .replace("{created}", String(data.created_count || 0))
        .replace("{skipped}", String(data.skipped_count || 0)));
    } catch (error) {
      showError(error);
    }
  });
  $("task-list-refresh").addEventListener("click", () => {
    loadTaskList().catch(showError);
  });

  $("task-create").addEventListener("click", async () => {
    try {
      const text = valueOf("task-links");
      if (!text.trim()) throw new Error(state.language === "en" ? "Paste at least one link." : "请粘贴至少一个链接。");
      if (!selectedTaskPlatforms().length) {
        throw new Error(state.language === "en" ? "Select at least one platform." : "请至少选择一个平台。");
      }
      const data = await apiPost("/api/tasks", {
        text,
        name: valueOf("task-name").trim(),
        platforms: selectedTaskPlatforms(),
        target_platform: valueOf("task-target-platform", "全部")
      });
      state.currentTaskId = data.task?.id || "";
      state.currentTask = data.task || null;
      window.localStorage.setItem("kolconnect.currentTaskId", state.currentTaskId);
      setValue("task-links", "");
      setValue("task-name", "");
      renderCurrentTask();
      await loadTaskList();
      const invalidCount = Array.isArray(data.invalid_links) ? data.invalid_links.length : 0;
      showSaved(state.language === "en"
        ? `Task created: ${data.task.valid_count} valid, ${invalidCount} invalid.`
        : `任务已创建：有效链接 ${data.task.valid_count} 条，异常链接 ${invalidCount} 条。`);
    } catch (error) {
      showError(error);
    }
  });

  $("scrape-start").addEventListener("click", async () => {
    try {
      if (!state.currentTaskId) {
        throw new Error(state.language === "en" ? "Create a task first." : "请先创建任务。");
      }
      if (state.currentTask?.status === "interrupted") {
        await apiPost(`/api/tasks/${encodeURIComponent(state.currentTaskId)}/resume`, {});
      } else {
        await apiPost("/api/scrape/start", {
          taskId: state.currentTaskId,
          profile: valueOf("profile-select")
        });
      }
      await refreshScrapeStatus();
    } catch (error) {
      showError(error);
    }
  });

  $("scrape-stop").addEventListener("click", async () => {
    try {
      if (state.currentTaskId && !state.scrapeJob?.running) {
        await apiPost(`/api/tasks/${encodeURIComponent(state.currentTaskId)}/stop`, {});
      } else {
        await apiPost("/api/scrape/stop", {});
      }
      await refreshScrapeStatus();
    } catch (error) {
      showError(error);
    }
  });

  $("scrape-pause").addEventListener("click", async () => {
    try {
      const status = await apiGet("/api/scrape/status");
      if (status.status === "paused" && !status.running) {
        await apiPost(`/api/tasks/${encodeURIComponent(state.currentTaskId)}/resume`, {});
      } else {
        await apiPost(status.status === "paused" ? "/api/scrape/resume" : "/api/scrape/pause", {});
      }
      await refreshScrapeStatus();
      await loadTaskList();
    } catch (error) {
      showError(error);
    }
  });

  $("scrape-open-results").addEventListener("click", async () => {
    try { await openResults(); } catch (error) { showError(error); }
  });
  $("scrape-open-result-folder").addEventListener("click", async () => {
    try { await openResultFolder(); } catch (error) { showError(error); }
  });

  $("discover-clean").addEventListener("click", async () => {
    try {
      const data = await apiPost("/api/normalize-links", {
        text: valueOf("discover-input")
      });
      renderDiscoverResults(data);
    } catch (error) {
      clearDiscoverOutputs();
      showError(error);
    }
  });
  $("discover-clear").addEventListener("click", () => {
    clearDiscoverAll();
  });
  $("discover-status-filter").addEventListener("change", renderDiscoverDetails);
  $("discover-copy-links").addEventListener("click", async () => {
    try {
      await copyText(valueOf("discover-output"));
    } catch (error) {
      showError(error);
    }
  });
  $("discover-copy-invalid").addEventListener("click", async () => {
    try {
      await copyText(valueOf("discover-invalid-output"));
    } catch (error) {
      showError(error);
    }
  });

  $("accounts-refresh").addEventListener("click", loadState);
  $("accounts-add").addEventListener("click", () => {
    const rows = Array.from(document.querySelectorAll("#accounts-list .chrome-profile-card"));
    const candidate = rows.find(row => !textAreaOrInputValue(row, '[data-key="alias"]') && !textAreaOrInputValue(row, '[data-key="note"]'));
    if (!candidate) return showError(new Error("所有已发现的 Chrome Profile 都已有配置。"));
    candidate.querySelector('[data-key="alias"]')?.focus();
  });
  $("accounts-save").addEventListener("click", async () => {
    try {
      await apiPost("/api/settings/accounts", { entries: collectAccounts() });
      showSaved();
      await loadState();
    } catch (error) {
      showError(error);
    }
  });

  $("mail-save").addEventListener("click", async () => {
    try {
      await saveMailTemplate();
    } catch (error) {
      showError(error);
    }
  });

  $("mail-accounts-save").addEventListener("click", async () => {
    try {
      await saveMailAccounts();
    } catch (error) {
      showError(error);
    }
  });

  $("mail-add-account").addEventListener("click", () => addMailAccount());
  $("mail-matched-only").addEventListener("change", () => {
    state.mailInbox.page = 1;
    renderMailMessages();
  });
  $("mail-page-size").addEventListener("change", () => {
    state.mailInbox.page = 1;
    renderMailMessages();
  });
  $("mail-page-previous").addEventListener("click", () => {
    state.mailInbox.page = Math.max(1, state.mailInbox.page - 1);
    renderMailMessages();
  });
  $("mail-page-next").addEventListener("click", () => {
    state.mailInbox.page += 1;
    renderMailMessages();
  });
  $("mail-inbox-sync").addEventListener("click", async () => {
    try {
      const data = await apiPost("/api/mail/inbox/sync", { limit_per_account: 20 });
      renderMailInbox({
        updated_at: data.updated_at || "",
        accounts_checked: data.accounts_checked || 0,
        messages_fetched: data.messages_fetched || 0,
        messages_new: data.messages_new || 0,
        matched_messages: data.matched_messages || 0,
        summary: { unread: 0, matched: data.matched_messages || 0 },
        messages: []
      });
      await loadMailInbox();
      showSaved(t("mailInboxSyncSuccess"));
    } catch (error) {
      showError(error);
    }
  });

  $("mail-sync-crm-replies").addEventListener("click", async () => {
    try {
      const data = await apiPost("/api/mail/inbox/sync-crm-replies", {});
      await loadMailInbox();
      showSaved(formatMailReplySyncSummary(data));
    } catch (error) {
      showError(error);
    }
  });

}

async function init() {
  registerLegacyPages();
  bindEvents();
  renderStaticText();
  renderCurrentTask();
  await loadState();
  await loadTaskList();
  await refreshScrapeStatus();
  // Dashboard availability must not prevent task controls from initializing.
  await setPage("dashboard").catch(error => console.warn("[KOLConnect] dashboard unavailable during startup", error));
  state.scrapeStatusTimer = window.setInterval(refreshScrapeStatus, 3000);
  state.taskStatusTimer = window.setInterval(() => loadTaskList().catch(() => {}), 2000);
}

window.KOLConnectApp = Object.freeze({
  valueOf,
  checkedOf,
  loadSettingsState,
  loadSystemHealth,
  setDebugModeVisible,
  renderStaticText,
  renderCurrentTask,
  showSaved,
  showError,
  navigate: setPage,
  setLanguage(language) {
    state.language = language;
  },
});

window.addEventListener("DOMContentLoaded", init);
