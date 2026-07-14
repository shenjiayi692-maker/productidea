// 通用工具：缓存 + fetch + 统一响应格式

const cache = new Map();
const DEFAULT_TTL = 10 * 60 * 1000; // 10 分钟

export async function cached(key, ttl, fn) {
  const hit = cache.get(key);
  if (hit && Date.now() - hit.at < ttl) {
    return { ...hit.data, fromCache: true };
  }
  const data = await fn();
  cache.set(key, { at: Date.now(), data });
  return { ...data, fromCache: false };
}

export async function fetchWith(url, options = {}, timeoutMs = 15000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(url, {
      ...options,
      signal: controller.signal,
      headers: {
        "User-Agent":
          "Mozilla/5.0 (compatible; english-hot-api/0.1; +https://github.com/)",
        ...options.headers,
      },
    });
    if (!res.ok) throw new Error(`HTTP ${res.status} from ${url}`);
    return res;
  } finally {
    clearTimeout(timer);
  }
}

// 统一列表响应，对齐 DailyHotApi 的风格
export function ok(name, title, items, params = {}) {
  return {
    code: 200,
    name,
    title,
    total: items.length,
    params,
    updateTime: new Date().toISOString(),
    data: items,
  };
}

export function err(name, message) {
  return { code: 500, name, message };
}
