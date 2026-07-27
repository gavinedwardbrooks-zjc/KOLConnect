const DEFAULT_API_URL = "http://127.0.0.1:8765/api/tasks/manual";

const form = document.querySelector("#capture-form");
const status = document.querySelector("#status");
const sendButton = document.querySelector("#send");
const field = (id) => document.querySelector(`#${id}`);

function setStatus(message, type = "") {
  status.textContent = message;
  status.className = `status ${type}`.trim();
}

// This function runs in the active social-media page, so keep all helpers inside it.
function collectCurrentProfile() {
  const pageText = (selector) => document.querySelector(selector)?.textContent?.replace(/\s+/g, " ").trim() || "";
  const metaContent = (name, attribute = "property") => document.querySelector(`meta[${attribute}="${name}"]`)?.content?.trim() || "";
  const firstMatch = (text, patterns) => {
    for (const pattern of patterns) {
      const match = text.match(pattern);
      if (match?.[1]) return match[1];
    }
    return "";
  };
  const compactFollowerText = (value) => {
    const raw = String(value || "").trim();
    const match = raw.match(/([\d.,]+)\s*([KMB])/i);
    if (!match) return raw.replace(/[^\d]/g, "");
    let number = match[1];
    const suffix = match[2].toUpperCase();
    if (number.includes(",") && !number.includes(".")) {
      const decimals = number.split(",").at(-1);
      number = decimals.length <= 2 ? number.replace(",", ".") : number.replace(/,/g, "");
    } else {
      number = number.replace(/,/g, "");
    }
    return `${number}${suffix}`;
  };
  const current = new URL(window.location.href);
  const hostname = current.hostname.toLowerCase().replace(/^www\./, "");
  const page = document.documentElement.outerHTML;
  const title = metaContent("og:title") || document.title;
  const description = metaContent("og:description") || metaContent("description", "name");
  let platform = "";
  let username = "";
  let profileUrl = "";
  let name = "";
  let bio = "";
  let followers = "";

  if (hostname.endsWith("tiktok.com")) {
    const handle = current.pathname.match(/^\/@([^/?#]+)/)?.[1];
    if (!handle) throw new Error("请先打开 TikTok 达人主页。");
    platform = "TikTok";
    username = `@${handle}`;
    profileUrl = `https://www.tiktok.com/@${handle}`;
    name = firstMatch(page, [/"nickname"\s*:\s*"([^"]+)"/i, /"displayName"\s*:\s*"([^"]+)"/i]) || title.replace(/\s*(\|\s*TikTok|on TikTok.*)$/i, "");
    followers = firstMatch(page, [/"followerCount"\s*:\s*(\d+)/i]) || firstMatch(document.body.innerText, [/([\d.,]+\s*[KMB]?)\s*Followers/i]);
    bio = firstMatch(page, [/"signature"\s*:\s*"([^"]+)"/i]) || pageText('[data-e2e="user-bio"]');
  } else if (hostname.endsWith("instagram.com")) {
    const handle = current.pathname.split("/").filter(Boolean)[0];
    if (!handle || ["p", "reel", "reels", "explore", "stories"].includes(handle.toLowerCase())) {
      throw new Error("请先打开 Instagram 达人主页。");
    }
    platform = "Instagram";
    username = `@${handle}`;
    profileUrl = `https://www.instagram.com/${handle}/`;
    name = firstMatch(page, [/"full_name"\s*:\s*"([^"]+)"/i]) || title.replace(/\s*\(@[^)]+\).*$/, "");
    followers = firstMatch(page, [/"edge_followed_by"\s*:\s*\{[^}]*"count"\s*:\s*(\d+)/i, /"follower_count"\s*:\s*(\d+)/i]) || firstMatch(description, [/([\d.,]+\s*[KMB]?)\s*Followers/i]);
    bio = pageText('header section div[dir="auto"]') || firstMatch(page, [/"biography"\s*:\s*"([^"]+)"/i]);
  } else if (hostname.endsWith("youtube.com")) {
    const parts = current.pathname.split("/").filter(Boolean);
    const first = parts[0] || "";
    if (!first || !(/^@/.test(first) || ["channel", "c", "user"].includes(first))) {
      throw new Error("请先打开 YouTube 频道主页。");
    }
    platform = "YouTube";
    username = first === "channel" || first === "c" || first === "user" ? parts[1] || "" : first;
    profileUrl = `https://www.youtube.com/${first}${first.startsWith("@") ? "" : `/${username}`}`;
    name = firstMatch(page, [/"channelName"\s*:\s*"([^"]+)"/i, /"ownerChannelName"\s*:\s*"([^"]+)"/i]) || title.replace(/\s*-\s*YouTube.*$/i, "");
    followers = firstMatch(page, [/"subscriberCountText"\s*:\s*\{[^}]*"simpleText"\s*:\s*"([^"]+)"/i]) || pageText("#subscriber-count");
    bio = pageText("#description") || pageText("ytd-channel-about-metadata-renderer #description");
  } else {
    throw new Error("仅支持 TikTok、Instagram 和 YouTube 主页。");
  }

  return {
    platform,
    username,
    profileUrl,
    name: name.replace(/\\u002F/g, "/").replace(/\\n/g, " ").trim(),
    followerCount: compactFollowerText(followers),
    bio: bio.replace(/\\n/g, " ").replace(/\s+/g, " ").trim()
  };
}

async function collect() {
  form.hidden = true;
  setStatus("正在读取当前页面...");
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab?.id) throw new Error("未找到当前标签页。");
    const [injected] = await chrome.scripting.executeScript({ target: { tabId: tab.id }, func: collectCurrentProfile });
    const data = injected?.result;
    if (!data?.profileUrl) throw new Error("未能读取主页信息。");
    field("platform").value = data.platform;
    field("username").value = data.username;
    field("name").value = data.name;
    field("profile-url").value = data.profileUrl;
    field("follower-count").value = data.followerCount;
    field("bio").value = data.bio;
    if (!field("task-name").value) field("task-name").value = `浏览器采集-${new Date().toISOString().slice(0, 10)}`;
    form.hidden = false;
    setStatus("已读取，请确认后发送。", "success");
  } catch (error) {
    setStatus(error.message || "读取失败，请确认当前页面是支持的平台主页。", "error");
  }
}

async function sendCapture(event) {
  event.preventDefault();
  sendButton.disabled = true;
  setStatus("正在发送到本地 KOL联系助手...");
  const apiUrl = field("api-url").value.trim() || DEFAULT_API_URL;
  await chrome.storage.local.set({ localApiUrl: apiUrl });
  const bio = field("bio").value.trim();
  const username = field("username").value.trim();
  const noteParts = [];
  if (username) noteParts.push(`用户名：${username}`);
  if (bio) noteParts.push(`简介：${bio}`);
  const payload = {
    task_name: field("task-name").value.trim(),
    name: field("name").value.trim(),
    platform: field("platform").value,
    profile_url: field("profile-url").value,
    follower_count: field("follower-count").value.trim(),
    email: "",
    whatsapp: "",
    note: noteParts.join("\n")
  };
  try {
    const response = await fetch(apiUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || !data.ok) throw new Error(data.error || "本地 KOL联系助手未接受该记录。");
    setStatus("已发送，记录已进入 KOL联系助手审核任务。", "success");
  } catch (error) {
    setStatus(`发送失败：${error.message || "请确认 KOL联系助手已启动。"}`, "error");
  } finally {
    sendButton.disabled = false;
  }
}

async function initialize() {
  const { localApiUrl } = await chrome.storage.local.get("localApiUrl");
  field("api-url").value = localApiUrl || DEFAULT_API_URL;
  await collect();
}

document.querySelector("#reload").addEventListener("click", collect);
form.addEventListener("submit", sendCapture);
initialize();
