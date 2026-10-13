#!/usr/bin/env python3
"""每周体检（在 GitHub Actions 里跑，不依赖任何人的电脑开机）。

查三件事：
  1. 线上 https://www.husir.org/tools/ 的工具清单 vs 本仓库顶层目录
  2. 本仓库最后一次提交是多久以前（>60 天提醒一下，避免仓库看着荒废）
  3. 最新 Release 和它的附件（离线包）是否存在

退出码：0 = 正常；3 = 发现差异（工作流会开一个 issue）；4 = 体检本身没跑成（网络/被拦）
"""
import json, os, re, subprocess, sys, urllib.error, urllib.request

SITE = os.environ.get("SITE_URL", "https://www.husir.org/tools/")
REPO = os.environ.get("GITHUB_REPOSITORY", "hu0023-png/husir-tools")
TOKEN = os.environ.get("GITHUB_TOKEN", "")
IGNORE = {"focus-minimal", "scripts", "assets"}
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")

def fetch(url, accept=None, timeout=30):
    h = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"}
    if accept: h["Accept"] = accept
    if TOKEN and url.startswith("https://api.github.com"):
        h["Authorization"] = f"Bearer {TOKEN}"
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read()

def site_slugs():
    status, body = fetch(SITE)
    text = body.decode("utf-8", "replace")
    if status != 200 or "Just a moment" in text or "cf-challenge" in text:
        raise RuntimeError(f"拿不到线上页面（HTTP {status}，可能是 Cloudflare 拦了 GitHub 的 IP）")
    return {s for s in re.findall(r'href="([a-z0-9][a-z0-9\-]*)/"', text)}

def repo_dirs():
    return {d for d in os.listdir(".") if os.path.isdir(d) and not d.startswith(".") and d not in IGNORE}

def last_commit_days():
    iso = subprocess.run(["git", "log", "-1", "--format=%cI"], capture_output=True, text=True).stdout.strip()
    if not iso: return None
    import datetime
    dt = datetime.datetime.fromisoformat(iso)
    return (datetime.datetime.now(datetime.timezone.utc) - dt).days

def latest_release():
    try:
        _, body = fetch(f"https://api.github.com/repos/{REPO}/releases?per_page=1",
                        accept="application/vnd.github+json")
        rel = json.loads(body)
        if not rel: return None
        r = rel[0]
        return {"tag": r["tag_name"], "date": (r.get("published_at") or "")[:10],
                "assets": [(a["name"], a["size"]) for a in r.get("assets", [])]}
    except Exception as e:
        return {"error": str(e)}

def main():
    lines, drift = [], []
    print(f"仓库：{REPO}")
    try:
        site, repo = site_slugs() - IGNORE, repo_dirs()
    except Exception as e:
        print(f"❌ 体检没跑成：{e}")
        return 4

    only_site, only_repo = sorted(site - repo), sorted(repo - site)
    print(f"线上 /tools/ 链接 {len(site)} 个 ｜ 仓库目录 {len(repo)} 个")
    if only_site:
        drift.append("站点有、仓库没有（该同步）：" + "、".join(only_site))
    if only_repo:
        drift.append("仓库有、站点没有（下架/改名？）：" + "、".join(only_repo))

    age = last_commit_days()
    print(f"最近一次提交：{age} 天前")
    if age is not None and age > 60:
        drift.append(f"仓库已经 {age} 天没有提交了 —— 如果本地加了新工具，记得同步")

    rel = latest_release()
    if rel and "error" not in rel:
        size = ", ".join(f"{n}（{s/1048576:.2f} MB）" for n, s in rel["assets"]) or "没有附件"
        print(f"最新 Release：{rel['tag']}（{rel['date']}）｜附件：{size}")
        if not rel["assets"]:
            drift.append("最新 Release 没有离线包附件")
    elif rel:
        print(f"最新 Release 查询失败：{rel['error']}")

    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if drift:
        print("\n⚠️ 发现 " + str(len(drift)) + " 项：")
        for d in drift: print("  - " + d)
        if summary:
            with open(summary, "a") as f:
                f.write("# 每周体检：需要处理\n\n" + "\n".join("- " + d for d in drift) + "\n")
        return 3
    print("\n✅ 一切正常：网站上有的工具仓库里都有，离线包也在。")
    if summary:
        with open(summary, "a") as f:
            f.write("# 每周体检：一切正常 ✅\n\n网站工具清单与仓库一致，Release 附件在位。\n")
    return 0

if __name__ == "__main__":
    sys.exit(main())
