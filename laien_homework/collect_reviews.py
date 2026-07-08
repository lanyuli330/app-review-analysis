"""
Step 1: Data Collection — App Store Reviews Scraper
=====================================================
使用 Apple 官方 RSS Feed API 采集 App Store 用户评价。

数据源: Apple RSS Feed (官方接口)
接口: https://itunes.apple.com/{country}/rss/customerreviews/page={n}/id={app_id}/sortby=mostrecent/json

使用方法:
    python collect_reviews.py              # 在线爬取
    python collect_reviews.py --cached     # 使用缓存数据
"""

import json
import os
import sys
import time
import subprocess
from datetime import datetime


APP_ID = 839285684
APP_NAME = "Workout for Women: Home Gym"
COUNTRY = "us"
OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "reviews_raw.json")
CACHED_FILE = os.path.join(OUTPUT_DIR, "reviews_raw_cached.json")
CURL_TIMEOUT = 30

RSS_URL_TEMPLATE = (
    "https://itunes.apple.com/{country}/rss/customerreviews"
    "/page={page}/id={app_id}/sortby=mostrecent/json"
)


def fetch_page(country, app_id, page):
    url = RSS_URL_TEMPLATE.format(country=country, page=page, app_id=app_id)
    r = subprocess.run(
        ["curl", "-s", "-L", "--connect-timeout", str(CURL_TIMEOUT), url],
        capture_output=True, encoding="utf-8", errors="replace",
        timeout=CURL_TIMEOUT + 5, env={**os.environ},
    )
    if r.returncode != 0:
        raise RuntimeError(f"curl exit code {r.returncode}: {r.stderr[:200]}")
    stdout = (r.stdout or "").strip()
    if not stdout:
        raise RuntimeError("empty response")
    return json.loads(stdout)


def parse_review_entry(entry):
    return {
        "id": entry.get("id", {}).get("label", ""),
        "user_name": entry.get("author", {}).get("name", {}).get("label", "Anonymous"),
        "user_uri": entry.get("author", {}).get("uri", {}).get("label", ""),
        "rating": int(entry.get("im:rating", {}).get("label", 0)),
        "title": entry.get("title", {}).get("label", ""),
        "content": entry.get("content", {}).get("label", ""),
        "version": entry.get("im:version", {}).get("label", ""),
        "updated": entry.get("updated", {}).get("label", ""),
        "vote_sum": int(entry.get("im:voteSum", {}).get("label", 0)),
        "vote_count": int(entry.get("im:voteCount", {}).get("label", 0)),
    }


def collect_reviews(app_id, app_name, country, sleep_interval=1, max_pages=10):
    print(f"[初始化] App ID={app_id}, 区域={country}")
    all_reviews = []
    start_time = time.time()

    for page in range(1, max_pages + 1):
        try:
            print(f"[采集] 第 {page}/{max_pages} 页 ...", end=" ")
            data = fetch_page(country, app_id, page)
            entries = data.get("feed", {}).get("entry", [])
            review_entries = [e for e in entries if "im:rating" in e]

            for entry in review_entries:
                all_reviews.append(parse_review_entry(entry))

            print(f"获取 {len(review_entries)} 条 (累计 {len(all_reviews)})")

            if len(review_entries) < 50:
                if page == 1 and len(review_entries) == 0:
                    print(f"\n[错误] RSS Feed 返回 0 条评价。")
                    print(f"  Apple 已关闭 itunes.apple.com/rss/customerreviews 公开接口。")
                    print(f"  使用缓存数据: python collect_reviews.py --cached")
                    print(f"  或直接在 Web 端点击「📦 离线演示」。")
                break

            if page < max_pages:
                time.sleep(sleep_interval)

        except Exception as e:
            print(f"\n[警告] 失败: {e}")
            continue

    elapsed = time.time() - start_time

    result = {
        "metadata": {
            "app_id": app_id, "app_name": app_name, "country": country,
            "collected_at": datetime.now().isoformat(),
            "total_reviews": len(all_reviews),
            "collection_time_seconds": round(elapsed, 2),
            "method": "Apple RSS Feed API",
        },
        "reviews": all_reviews,
    }
    return result


def load_cached():
    if not os.path.exists(CACHED_FILE):
        print(f"[错误] 缓存文件不存在: {CACHED_FILE}")
        sys.exit(1)
    with open(CACHED_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    use_cached = "--cached" in sys.argv

    print("=" * 60)
    print("  LaienTech App Store Review Collector (Step 1)")
    print("=" * 60)
    print(f"  App: {APP_NAME} | ID: {APP_ID} | Region: {COUNTRY}")
    print(f"  Mode: {'Cached' if use_cached else 'RSS Feed'}")
    print()

    if use_cached:
        data = load_cached()
        print(f"  从缓存加载 {data['metadata']['total_reviews']} 条评价")
    else:
        data = collect_reviews(APP_ID, APP_NAME, COUNTRY)

    # 保存
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    cnt = len(data["reviews"])
    size = os.path.getsize(OUTPUT_FILE) / 1024
    print(f"\n[完成] {cnt} 条评价 → {OUTPUT_FILE} ({size:.1f} KB)")

    if cnt > 0:
        ratings = [r.get("rating", 0) for r in data["reviews"]]
        for score in sorted(set(ratings)):
            count = ratings.count(score)
            bar = "█" * max(1, count // max(1, len(ratings) // 40))
            print(f"  {score}★: {count:4d}  {bar}")
        print(f"  Avg: {sum(ratings)/len(ratings):.2f}")

    print("✅ Done.")


if __name__ == "__main__":
    main()
