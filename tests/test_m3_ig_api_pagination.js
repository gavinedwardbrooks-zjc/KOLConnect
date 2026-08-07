const assert = require("node:assert/strict");
const path = require("node:path");
const { pathToFileURL } = require("node:url");

const ROOT = path.resolve(__dirname, "..");
const moduleUrl = (relative) => pathToFileURL(path.join(ROOT, relative));

function media(id, overrides = {}) {
  return {
    id: String(id),
    code: `code-${id}`,
    play_count: Number(id) + 100,
    like_count: Number(id) + 10,
    comment_count: Number(id) + 1,
    caption: { text: `Reel ${id}` },
    taken_at: 1_700_000_000 + Number(id),
    is_pinned: false,
    product_type: "clips",
    user: { username: "synthetic_creator" },
    ...overrides
  };
}

(async () => {
  const Instagram = await import(moduleUrl("chrome_extension/platform/instagram.js"));
  const Common = await import(moduleUrl("chrome_extension/platform/common.js"));
  const Normalize = await import(moduleUrl("chrome_extension/core/normalize.js"));
  const Schema = await import(moduleUrl("chrome_extension/core/schema.js"));
  const { IG_APP_ID, INSTAGRAM_MAX_REELS } = await import(
    moduleUrl("chrome_extension/constants.js")
  );

  assert.equal(IG_APP_ID, "936619743392459");
  assert.equal(INSTAGRAM_MAX_REELS, 50);

  const profile = Instagram.mapInstagramProfileResponse({
    ok: true,
    requested_username: "synthetic_creator",
    user: {
      id: "10001",
      username: "synthetic_creator",
      full_name: "This name must not replace the API username",
      biography: "Contato: creator@example.test\nWhatsApp +55 11 99999-0000",
      followers: 12345,
      is_private: false,
      country: "Brazil",
      language: "Portuguese"
    }
  });
  assert.equal(profile.fields.creator_name.value, "synthetic_creator");
  assert.equal(profile.fields.creator_name.source, "web_profile_info");
  assert.equal(profile.fields.followers.value, "12345");
  assert.equal(profile.fields.bio.value.includes("Contato:"), true);
  assert.equal(profile.fields.email.value, "creator@example.test");
  assert.equal(profile.fields.whatsapp.value, "5511999990000");
  assert.equal(profile.fields.country.value, "Brazil");
  assert.equal(profile.fields.language.value, "Portuguese");
  assert.equal(
    Instagram.mapInstagramProfileResponse({
      requested_username: "synthetic_creator",
      user: {
        username: "synthetic_creator",
        followers: 1_734_182,
        followers_source: "web_profile_info.edge_followed_by.count"
      }
    }).fields.followers.value,
    "1734182"
  );

  const profileChrome = global.chrome;
  let apiProfileExecutions = 0;
  global.chrome = {
    scripting: {
      async executeScript({ func }) {
        apiProfileExecutions += 1;
        assert.equal(func.name, "fetchInstagramWebProfilePage");
        return [{ result: {
          ok: true,
          requested_username: "synthetic_creator",
          user: {
            id: "10001",
            username: "synthetic_creator",
            biography: "Digital creator\nPorto Alegre\ncreator@example.test",
            followers: 12345
          }
        } }];
      }
    }
  };
  const apiCollectedProfile = await Instagram.collectProfile(1);
  assert.equal(apiProfileExecutions, 1, "API biography must not invoke DOM fallback");
  assert.equal(
    apiCollectedProfile.fields.bio.value,
    "Digital creator\nPorto Alegre\ncreator@example.test"
  );
  assert.deepEqual(apiCollectedProfile.searched_sources, ["web_profile_info"]);
  global.chrome = profileChrome;

  const savedDocument = global.document;
  const savedWindow = global.window;
  const savedDomLocation = global.location;
  const explicitSelectorMarker = "data-testid";
  const makeBioNode = (text, { explicit = false, blocked = false } = {}) => ({
    innerText: text,
    textContent: text,
    matches(selector) {
      return explicit && selector.includes(explicitSelectorMarker);
    },
    closest(selector) {
      if (explicit && selector.includes(explicitSelectorMarker)) return this;
      if (selector === "header section") return {};
      if (blocked && selector.includes("button") && selector.includes("highlight")) return {};
      return null;
    }
  });
  const domBioNodes = [
    makeBioNode("214帖子", { blocked: true }),
    makeBioNode("1.8万粉丝", { blocked: true }),
    makeBioNode("2205关注", { blocked: true }),
    makeBioNode("Digital creator"),
    makeBioNode("Porto Alegre, RS"),
    makeBioNode("Daily | @demo"),
    makeBioNode("creator@example.test"),
    makeBioNode("creator@example.test"),
    ...["fits", "nails", "L", "gym", "M", "parceiros"]
      .map((text) => makeBioNode(text, { blocked: true }))
  ];
  global.location = { href: "https://www.instagram.com/demo/" };
  global.window = { _sharedData: null, __initialData: null };
  let domFollowerText = "1.8万粉丝";
  const followerNode = {
    getAttribute() { return null; },
    get textContent() { return domFollowerText; }
  };
  global.document = {
    querySelector() { return null; },
    querySelectorAll(selector) {
      if (selector.includes("mailto:") || selector.includes("wa.me/")) return [];
      if (selector.includes('script[type="application/')) return [];
      if (selector.includes('href*="/followers"')) return domFollowerText ? [followerNode] : [];
      if (selector === "header ul li, header section li") return [];
      if (selector.includes('header section span[dir="auto"]')) return domBioNodes;
      return [];
    }
  };
  const domPageResult = Instagram.collectInstagramPage();
  const domBiography = Common.selectBio(domPageResult.bio_candidates, {
    platform: "instagram",
    username: "@demo",
    creatorName: "demo"
  });
  assert.equal(
    domBiography.value,
    "Digital creator\nPorto Alegre, RS\nDaily | @demo\ncreator@example.test"
  );
  for (const forbidden of ["214帖子", "1.8万粉丝", "2205关注", "fits", "nails", "L", "gym", "M", "parceiros"]) {
    assert.equal(domBiography.value.split("\n").includes(forbidden), false);
  }
  const domContactResult = { fields: {}, public_profile: domPageResult.public_profile };
  Common.applyPublicProfileFields(domContactResult);
  assert.equal(domContactResult.fields.email.value, "creator@example.test");
  assert.equal(Schema.finalizeProfile(domPageResult).followers, "18000");
  domFollowerText = "1.8萬粉絲";
  assert.equal(Schema.finalizeProfile(Instagram.collectInstagramPage()).followers, "18000");
  domFollowerText = "18.7K followers";
  assert.equal(Schema.finalizeProfile(Instagram.collectInstagramPage()).followers, "18700");

  domFollowerText = "";
  global.window = {
    _sharedData: {
      first: {
        user: { username: "demo" }
      },
      second: {
        user: {
          username: "demo",
          edge_followed_by: { count: 1_734_182 }
        }
      }
    },
    __initialData: null
  };
  const hydrationFollowers = Instagram.collectInstagramPage().fields.followers;
  assert.equal(hydrationFollowers.value, "1734182");
  assert.equal(hydrationFollowers.source, "hydration.edge_followed_by.count");
  global.document = savedDocument;
  global.window = savedWindow;
  global.location = savedDomLocation;

  for (const statistics of [
    "214帖子",
    "1.8万粉丝",
    "2205关注",
    "214貼文",
    "1.8萬粉絲",
    "2205追蹤中"
  ]) {
    assert.equal(Common.isStatsLine(statistics, "instagram"), true);
  }
  assert.equal(Common.isStatsLine("感谢大家的关注", "instagram"), false);
  assert.equal(Common.isStatsLine("分享粉丝福利", "instagram"), false);

  const savedLocation = global.location;
  const savedFetch = global.fetch;
  global.location = { href: "https://www.instagram.com/synthetic_creator/" };
  let profileRequest = null;
  global.fetch = async (url, options) => {
    profileRequest = { url, options };
    return {
      ok: true,
      status: 200,
      async json() {
        return {
          data: {
            user: {
              id: "10001",
              username: "synthetic_creator",
              edge_followed_by: { count: 1_734_182 },
              follower_count: 99
            }
          }
        };
      }
    };
  };
  const profilePage = await Instagram.fetchInstagramWebProfilePage(IG_APP_ID);
  assert.equal(profilePage.ok, true);
  assert.equal(profileRequest.url, "/api/v1/users/web_profile_info/?username=synthetic_creator");
  assert.equal(profileRequest.options.credentials, "include");
  assert.equal(profileRequest.options.headers["X-IG-App-ID"], IG_APP_ID);
  assert.equal(profilePage.user.followers, 1_734_182);
  assert.equal(profilePage.user.followers_source, "web_profile_info.edge_followed_by.count");

  global.fetch = async () => ({
    ok: true,
    status: 200,
    async json() {
      return {
        data: {
          user: {
            id: "10002",
            username: "fallback_count",
            follower_count: 1_734_182
          }
        }
      };
    }
  });
  const directFollowerCountPage = await Instagram.fetchInstagramWebProfilePage(IG_APP_ID);
  assert.equal(directFollowerCountPage.user.followers, 1_734_182);
  assert.equal(
    directFollowerCountPage.user.followers_source,
    "web_profile_info.follower_count"
  );

  let clipsRequest = null;
  global.document = { cookie: "mid=fixture; csrftoken=runtime-csrf-token; ig_did=fixture" };
  global.fetch = async (url, options) => {
    clipsRequest = { url, options };
    return {
      ok: true,
      status: 200,
      async json() {
        return {
          items: [{ media: media(1) }],
          more_available: false,
          paging_info: { max_id: "" }
        };
      }
    };
  };
  const clipsPage = await Instagram.fetchInstagramClipsPage("10001", "cursor-2", IG_APP_ID, 50);
  assert.equal(clipsPage.ok, true);
  assert.equal(clipsRequest.url, "/api/v1/clips/user/");
  assert.equal(clipsRequest.options.credentials, "include");
  assert.equal(clipsRequest.options.headers["X-IG-App-ID"], IG_APP_ID);
  assert.equal(clipsRequest.options.headers["X-CSRFToken"], "runtime-csrf-token");
  assert.equal(clipsRequest.options.headers["Content-Type"], "application/x-www-form-urlencoded");
  assert.equal(new URLSearchParams(clipsRequest.options.body).get("target_user_id"), "10001");
  assert.equal(new URLSearchParams(clipsRequest.options.body).get("page_size"), "50");
  assert.equal(new URLSearchParams(clipsRequest.options.body).get("max_id"), "cursor-2");
  assert.equal(JSON.stringify(clipsPage).includes("runtime-csrf-token"), false);
  assert.equal(Instagram.fetchInstagramClipsPage.toString().includes("localStorage"), false);
  assert.equal(Instagram.fetchInstagramClipsPage.toString().includes("chrome.storage"), false);

  let missingTokenFetchCalled = false;
  const csrfWarnings = [];
  const savedWarnForCsrf = console.warn;
  console.warn = (...args) => csrfWarnings.push(args.join(" "));
  global.document = { cookie: "mid=fixture; ig_did=fixture" };
  global.fetch = async () => {
    missingTokenFetchCalled = true;
    throw new Error("fetch should not run without csrftoken");
  };
  const missingCsrf = await Instagram.fetchInstagramClipsPage("10001", "", IG_APP_ID, 50);
  assert.equal(missingTokenFetchCalled, false);
  assert.equal(missingCsrf.reason, "csrf_token_unavailable");
  assert.equal(JSON.stringify(missingCsrf).includes("runtime-csrf-token"), false);
  assert.equal(csrfWarnings.some((line) => line.includes("csrf_token_unavailable")), true);
  assert.equal(csrfWarnings.some((line) => line.includes("runtime-csrf-token")), false);
  console.warn = savedWarnForCsrf;

  const csrfErrorBody = JSON.stringify({ message: "CSRF token missing or incorrect" });
  global.document = { cookie: "csrftoken=runtime-csrf-token" };
  global.fetch = async (url, options) => {
    clipsRequest = { url, options };
    return {
      ok: false,
      status: 403,
      url,
      headers: { get: () => "application/json" },
      clone() { return { text: async () => csrfErrorBody }; },
      async json() { return JSON.parse(csrfErrorBody); }
    };
  };
  const rejectedCsrf = await Instagram.fetchInstagramClipsPage("10001", "", IG_APP_ID, 50);
  assert.equal(clipsRequest.options.headers["X-CSRFToken"], "runtime-csrf-token");
  assert.equal(rejectedCsrf.reason, "csrf_rejected");
  assert.equal(JSON.stringify(rejectedCsrf).includes("runtime-csrf-token"), false);
  global.document = savedDocument;
  global.location = savedLocation;
  global.fetch = savedFetch;

  for (const [raw, expected] of [
    ["18K", 18000],
    ["18.7K", 18700],
    ["1.8万", 18000],
    ["1.8萬", 18000],
    ["1.8M", 1800000],
    ["1,734,182", 1734182],
    ["1.8万粉丝", 18000],
    ["1.8萬粉絲", 18000],
    ["18.7K followers", 18700]
  ]) {
    assert.equal(Normalize.parseHumanCount(raw), expected, raw);
  }

  const followersMergeChrome = global.chrome;
  let followersMergeCalls = 0;
  global.chrome = {
    scripting: {
      async executeScript({ func }) {
        followersMergeCalls += 1;
        if (func.name === "fetchInstagramWebProfilePage") {
          return [{ result: {
            ok: true,
            requested_username: "synthetic_creator",
            user: {
              id: "10001",
              username: "synthetic_creator",
              biography: "Public biography",
              followers: null
            }
          } }];
        }
        if (func.name === "collectInstagramPage") {
          return [{ result: {
            platform: "Instagram",
            supported: true,
            fields: {
              followers: {
                value: "1.8万粉丝",
                source: "profile_dom",
                confidence: "high",
                missing_reason: ""
              }
            },
            searched_sources: ["structured_data", "page_dom", "meta", "url"]
          } }];
        }
        throw new Error(`Unexpected profile function: ${func.name}`);
      }
    }
  };
  const followersMergedProfile = await Instagram.collectProfile(1);
  assert.equal(followersMergeCalls, 2);
  assert.equal(followersMergedProfile.fields.followers.value, "1.8万粉丝");
  assert.equal(followersMergedProfile.fields.bio.value, "Public biography");
  assert.equal(followersMergedProfile.followers_fallback_used, true);
  global.chrome = followersMergeChrome;

  const pageCalls = [];
  const threePages = [
    { ok: true, items: Array.from({ length: 20 }, (_, index) => media(index)), more_available: true, max_id: "page-2" },
    { ok: true, items: Array.from({ length: 20 }, (_, index) => media(index + 20)), more_available: true, max_id: "page-3" },
    { ok: true, items: Array.from({ length: 20 }, (_, index) => media(index + 40)), more_available: false, max_id: "" }
  ];
  const paginated = await Instagram.paginateInstagramClips({
    targetUserId: "10001",
    fetchPage: async (request) => {
      pageCalls.push(request);
      return threePages[pageCalls.length - 1];
    },
    sleep: async () => {},
    random: () => 0
  });
  assert.equal(pageCalls.length, 3);
  assert.equal(paginated.items.length, 50);
  assert.equal(new Set(paginated.items.map((item) => item.id)).size, 50);
  assert.equal(paginated.stop_reason, "max_reels_reached");

  const duplicatePages = [
    { ok: true, items: [media(1), media(2)], more_available: true, max_id: "next" },
    { ok: true, items: [media(2), media(3)], more_available: false, max_id: "" }
  ];
  let duplicateCalls = 0;
  const deduplicated = await Instagram.paginateInstagramClips({
    targetUserId: "10001",
    fetchPage: async () => duplicatePages[duplicateCalls++],
    sleep: async () => {}
  });
  assert.deepEqual(deduplicated.items.map((item) => item.id), ["1", "2", "3"]);

  let shortCalls = 0;
  const shortAccount = await Instagram.paginateInstagramClips({
    targetUserId: "10001",
    fetchPage: async () => {
      shortCalls += 1;
      return {
        ok: true,
        items: Array.from({ length: 27 }, (_, index) => media(index)),
        more_available: false,
        max_id: "unused"
      };
    },
    sleep: async () => {}
  });
  assert.equal(shortAccount.items.length, 27);
  assert.equal(shortCalls, 1);

  let cursorCalls = 0;
  const cursorWarnings = [];
  const repeatedCursor = await Instagram.paginateInstagramClips({
    targetUserId: "10001",
    fetchPage: async () => {
      cursorCalls += 1;
      return {
        ok: true,
        items: [media(cursorCalls)],
        more_available: true,
        max_id: "same-cursor"
      };
    },
    sleep: async () => {},
    warn: (message) => cursorWarnings.push(message)
  });
  assert.equal(cursorCalls, 2);
  assert.equal(repeatedCursor.stop_reason, "repeated_cursor");
  assert.equal(cursorWarnings.length, 1);

  let rateLimitCalls = 0;
  await assert.rejects(
    Instagram.paginateInstagramClips({
      targetUserId: "10001",
      fetchPage: async () => {
        rateLimitCalls += 1;
        return { ok: false, status: 429, reason: "clips_user_http_429" };
      },
      sleep: async () => {}
    }),
    (error) => error.status === 429 && error.message === "clips_user_http_429"
  );
  assert.equal(rateLimitCalls, 1);

  const mapped = Instagram.mapInstagramMedia(media(9));
  assert.equal(mapped.video_id, "9");
  assert.equal(mapped.video_url, "https://www.instagram.com/reel/code-9/");
  assert.equal(mapped.views, 109);
  assert.equal(mapped.likes, 19);
  assert.equal(mapped.comments, 10);
  assert.equal(mapped.published_at, 1_700_000_009);

  const savedChrome = global.chrome;
  let apiClipCalls = 0;
  const apiClipPages = [
    { ok: true, items: Array.from({ length: 20 }, (_, index) => media(index, { is_pinned: index === 0 })), more_available: true, max_id: "page-2" },
    { ok: true, items: Array.from({ length: 20 }, (_, index) => media(index + 20)), more_available: true, max_id: "page-3" },
    { ok: true, items: Array.from({ length: 20 }, (_, index) => media(index + 40)), more_available: false, max_id: "" }
  ];
  global.chrome = {
    scripting: {
      async executeScript({ func, args }) {
        if (func.name === "fetchInstagramWebProfilePage") {
          assert.equal(args[0], IG_APP_ID);
          return [{ result: {
            ok: true,
            requested_username: "synthetic_creator",
            user: { id: "10001", username: "synthetic_creator" }
          } }];
        }
        if (func.name === "fetchInstagramClipsPage") {
          assert.equal(args[0], "10001");
          assert.equal(args[2], IG_APP_ID);
          assert.equal(args[3], 50);
          const response = apiClipPages[apiClipCalls++];
          return [{ result: response }];
        }
        throw new Error(`Unexpected MAIN-world function: ${func.name}`);
      }
    }
  };
  const apiAnalysis = await Instagram.collectRecentContent(1, {
    limit: 50,
    excludePinned: false,
    paginationSleep: async () => {}
  });
  assert.equal(apiClipCalls, 3);
  assert.equal(apiAnalysis.returned_count, 50);
  assert.equal(apiAnalysis.excluded_pinned_count, 0);
  assert.equal(apiAnalysis.collector_mode, "instagram_internal_api");
  assert.equal(apiAnalysis.data_source, "clips_user_api");
  assert.equal(new Set(apiAnalysis.contents.map((item) => item.video_id)).size, 50);

  const savedWarn = console.warn;
  const warnings = [];
  console.warn = (...args) => warnings.push(args.join(" "));
  const fallbackItem = media(501, {
    video_id: "legacy-501",
    video_url: "https://www.instagram.com/reel/legacy-501/",
    views: 5000,
    likes: 500,
    comments: 50,
    published_at: 1_700_000_000,
    source: "structured_data"
  });
  global.chrome = {
    scripting: {
      async executeScript({ func }) {
        if (func.name === "fetchInstagramWebProfilePage") {
          return [{ result: {
            ok: true,
            requested_username: "synthetic_creator",
            user: { id: "10001", username: "synthetic_creator" }
          } }];
        }
        if (func.name === "fetchInstagramClipsPage") {
          return [{ result: {
            ok: false,
            status: 0,
            reason: "csrf_token_unavailable"
          } }];
        }
        if (func.name === "discoverInstagramReels") return [{ result: [fallbackItem] }];
        throw new Error(`Unexpected MAIN-world function: ${func.name}`);
      }
    }
  };
  const missingCsrfFallback = await Instagram.collectRecentContent(1, { limit: 1, excludePinned: true });
  assert.equal(missingCsrfFallback.collector_mode, "legacy_fallback");
  assert.equal(
    missingCsrfFallback.api_diagnostics.some((item) => item.reason === "csrf_token_unavailable"),
    true
  );

  global.chrome = {
    scripting: {
      async executeScript({ func }) {
        if (func.name === "fetchInstagramWebProfilePage") {
          return [{ result: {
            ok: true,
            requested_username: "synthetic_creator",
            user: { id: "10001", username: "synthetic_creator" }
          } }];
        }
        if (func.name === "fetchInstagramClipsPage") {
          return [{ result: { ok: false, status: 401, reason: "clips_user_http_401" } }];
        }
        if (func.name === "discoverInstagramReels") return [{ result: [fallbackItem] }];
        throw new Error(`Unexpected MAIN-world function: ${func.name}`);
      }
    }
  };
  const fallback = await Instagram.collectRecentContent(1, { limit: 1, excludePinned: true });
  assert.equal(fallback.collector_mode, "legacy_fallback");
  assert.equal(fallback.data_source, "hydration_dom");
  assert.equal(fallback.contents[0].views.value, 5000);
  assert.equal(fallback.api_diagnostics.some((item) => item.reason === "feed_fallback_not_verified"), true);
  assert.equal(fallback.api_diagnostics.some((item) => item.reason === "graphql_doc_id_not_available"), true);
  assert.equal(warnings.some((message) => message.includes("clips_user_http_401")), true);
  assert.equal(warnings.some((message) => message.includes("feed fallback unavailable / not verified")), true);

  global.chrome = savedChrome;
  console.warn = savedWarn;
  console.log("M3-A Instagram profile API, clips pagination, and fallback tests passed.");
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
