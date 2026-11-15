#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
行事曆多端管理系統 (Multi-Account Schedule Manager)
指導老師：黃彥榮

【雙層權限控制】：
1. 個人生活日常瑣事（剪髮、聚餐、購物、運動等）：
   - 免密碼，隨時自由新增、查詢、刪除。
2. 核心公務（家教、診所排班、學校、論文）：
   - 密碼保護鎖（SHA-256 驗證：baj900923）
   - 必須提供正確密碼才能修改，防止誤觸或越權。
"""

import sys
import os
import json
import hashlib
import subprocess
import argparse
import getpass

DIR = os.path.dirname(os.path.abspath(__file__))
DATA_ENC_FILE = os.path.join(DIR, "schedule_data.enc")
CALENDAR_PASS = os.getenv("CALENDAR_PASS", "0923")

# 管理員密碼 SHA-256 雜湊 (密碼: baj900923)
ADMIN_PWD_HASH = "a748cdbf7def7913d4da74a3611a5efc3f5d8f168b92c8332c6f7c6f22ad1f4f"

# 核心公務關鍵字庫
CORE_KEYWORDS = [
    '家教', '診所', '學生', '學生a', '學生b', '芮晨', '周秉佑', '秉佑',
    '理化', '數學', '英文', '8j', 'a14', 'a15', '班', '休診', '颱風', '學校', '論文'
]

def is_core_event(title):
    lower_title = title.lower()
    return any(kw in lower_title for kw in CORE_KEYWORDS)

def verify_password(input_pwd):
    if not input_pwd:
        return False
    h = hashlib.sha256(input_pwd.strip().encode('utf-8')).hexdigest()
    return h == ADMIN_PWD_HASH

def decrypt_data():
    if not os.path.exists(DATA_ENC_FILE):
        return [], {}
    tmp_out = os.path.join(DIR, "_temp_decrypt.json")
    try:
        cmd = [
            "openssl", "enc", "-d", "-aes-256-cbc", "-pbkdf2",
            "-in", DATA_ENC_FILE,
            "-out", tmp_out,
            "-pass", f"pass:{CALENDAR_PASS}"
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        with open(tmp_out, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("events", []), data.get("notes", {})
    except Exception as e:
        print(f"⚠️ 解密排程失敗: {e}")
        return [], {}
    finally:
        if os.path.exists(tmp_out):
            os.remove(tmp_out)

def pull_latest():
    """從遠端拉取最新進度（含雲端紀錄或他機行程變更），避免覆蓋遠端更新"""
    if not os.path.exists(os.path.join(DIR, ".git")):
        return True
    try:
        subprocess.run(
            ["git", "fetch", "origin", "main"],
            cwd=DIR, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15
        )
        ahead = subprocess.check_output(
            ["git", "rev-list", "--count", "HEAD..origin/main"],
            cwd=DIR, text=True, stderr=subprocess.DEVNULL
        ).strip()
        if ahead and ahead != "0":
            res = subprocess.run(
                ["git", "pull", "--rebase", "--autostash", "origin", "main"],
                cwd=DIR, capture_output=True, text=True
            )
            if res.returncode != 0:
                subprocess.run(["git", "rebase", "--abort"], cwd=DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                print(f"⚠️ 遠端同步衝突，已中止 rebase 以保護本地狀態: {res.stderr.strip() or res.stdout.strip()}")
                return False
    except Exception as e:
        print(f"ℹ️ 略過遠端拉取 (離線或未設定遠端): {e}")
    return True


def _write_events_inplace(path, events):
    """原地寫入 JSON 以保留 hardlink inode 同步關係"""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(events, f, ensure_ascii=False, indent=2)
        f.write("\n")


def _sync_local_workspace(events):
    """若位於主專案目錄內，同步寫回 events.json 並重新打包加密網頁 index.html"""
    import shutil

    parent_dir = os.path.dirname(DIR)
    local_events = os.path.join(parent_dir, "events.json")
    written_inodes = set()
    if os.path.exists(local_events):
        st = os.stat(local_events)
        _write_events_inplace(local_events, events)
        written_inodes.add((st.st_dev, st.st_ino))

    mirror_events = "/Users/buchi/Downloads/家教學費/calendar/events.json"
    if os.path.exists(mirror_events):
        st_m = os.stat(mirror_events)
        if (st_m.st_dev, st_m.st_ino) not in written_inodes:
            _write_events_inplace(mirror_events, events)

    tpl_path = next(
        (p for p in (os.path.join(parent_dir, "template.html"), os.path.join(DIR, "template.html")) if os.path.exists(p)),
        None,
    )
    staticrypt_bin = shutil.which("staticrypt") or (
        "/opt/homebrew/bin/staticrypt" if os.path.exists("/opt/homebrew/bin/staticrypt") else None
    )
    if not (tpl_path and staticrypt_bin):
        return False

    try:
        with open(tpl_path, "r", encoding="utf-8") as f:
            tpl = f.read()
        events_js = f"window.CALENDAR_EVENTS = {json.dumps(events, ensure_ascii=False)};"
        orig_html = os.path.join(DIR, "index_original.html")
        with open(orig_html, "w", encoding="utf-8") as f:
            f.write(tpl.replace("// {{INJECT_EVENTS_HERE}}", events_js))

        subprocess.run(
            [
                staticrypt_bin, "index_original.html",
                "-p", CALENDAR_PASS,
                "-o", "index.html",
                "--template-title", "專屬行事曆",
                "--template-instructions", "請輸入密碼解鎖 (AES-256 安全加密)",
                "--template-remember", "記住密碼（桌面開啟免每次輸入）",
                "--remember", "90",
                "--short",
            ],
            cwd=DIR, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        enc_out = os.path.join(DIR, "encrypted", "index_original.html")
        idx_out = os.path.join(DIR, "index.html")
        if os.path.exists(enc_out):
            shutil.move(enc_out, idx_out)
            try:
                os.rmdir(os.path.join(DIR, "encrypted"))
            except OSError:
                pass
        with open(idx_out, "r", encoding="utf-8") as f:
            html = f.read()
        ios_tags = (
            '\n  <link rel="apple-touch-icon" sizes="180x180" href="apple-touch-icon.png">'
            '\n  <link rel="icon" type="image/png" href="apple-touch-icon.png">'
            '\n  <meta name="apple-mobile-web-app-capable" content="yes">'
            '\n  <meta name="apple-mobile-web-app-status-bar-style" content="default">'
            '\n  <meta name="apple-mobile-web-app-title" content="專屬行事曆">'
            '\n  <meta name="application-name" content="專屬行事曆">'
            '\n  <meta name="theme-color" content="#4338ca">\n'
        )
        if '<link rel="apple-touch-icon"' not in html:
            html = html.replace("<head>", "<head>" + ios_tags, 1)
            with open(idx_out, "w", encoding="utf-8") as f:
                f.write(html)
        return True
    except Exception as e:
        print(f"⚠️ 本地網頁 index.html 重建失敗 (schedule_data.enc 仍已更新): {e}")
        return False


def encrypt_and_push(events, notes, commit_msg, extra_files=None):
    tmp_json = os.path.join(DIR, "_temp_encrypt.json")
    with open(tmp_json, "w", encoding="utf-8") as f:
        json.dump({'events': events, 'notes': notes}, f, ensure_ascii=False)

    try:
        cmd = [
            "openssl", "enc", "-aes-256-cbc", "-salt", "-pbkdf2",
            "-in", tmp_json,
            "-out", DATA_ENC_FILE,
            "-pass", f"pass:{CALENDAR_PASS}"
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    finally:
        if os.path.exists(tmp_json):
            os.remove(tmp_json)

    index_rebuilt = _sync_local_workspace(events)
    files_to_add = ["schedule_data.enc"]
    if index_rebuilt and os.path.exists(os.path.join(DIR, "index.html")):
        files_to_add.append("index.html")
    for ef in (extra_files or []):
        if ef not in files_to_add and os.path.exists(os.path.join(DIR, ef)):
            files_to_add.append(ef)

    # Git 提交與推播
    if not os.path.exists(os.path.join(DIR, ".git")):
        print("✅ 已更新本地加密資料 (未偵測到 Git 倉庫，略過推播)。")
        return

    try:
        subprocess.run(["git", "add", *files_to_add], cwd=DIR, check=True)
        has_staged = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=DIR).returncode != 0
        if has_staged:
            subprocess.run(["git", "commit", "-m", commit_msg], cwd=DIR, check=True)
        subprocess.run(["git", "fetch", "origin", "main"], cwd=DIR, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
        ahead = subprocess.check_output(
            ["git", "rev-list", "--count", "HEAD..origin/main"],
            cwd=DIR, text=True, stderr=subprocess.DEVNULL
        ).strip()
        if ahead and ahead != "0":
            res = subprocess.run(["git", "pull", "--rebase", "origin", "main"], cwd=DIR, capture_output=True, text=True)
            if res.returncode != 0:
                subprocess.run(["git", "rebase", "--abort"], cwd=DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                raise RuntimeError(f"Git rebase 失敗，請先手動整合遠端更新: {res.stderr.strip() or res.stdout.strip()}")
        subprocess.run(["git", "push", "origin", "main"], cwd=DIR, check=True)
        print("🚀 已成功加密並推播至雲端 (GitHub Actions 提醒即刻生效)！")
    except Exception as e:
        print(f"⚠️ Git 推播失敗: {e}")

def parse_time_min(t_str):
    if not t_str or '-' not in t_str:
        return None
    try:
        s, e = t_str.split('-')
        sh, sm = map(int, s.strip().split(':'))
        eh, em = map(int, e.strip().split(':'))
        return (sh * 60 + sm, eh * 60 + em)
    except Exception:
        return None

def check_overlap(date_str, time_str, events, ignore_title=None):
    parsed = parse_time_min(time_str)
    if not parsed:
        return None
    s_min, e_min = parsed
    for e in events:
        if e.get("date") == date_str and e.get("title") != ignore_title:
            ep = parse_time_min(e.get("time", ""))
            if ep:
                es, ee = ep
                if not (e_min <= es or s_min >= ee):
                    return f"【{e.get('title')}】({e.get('time')})"
    return None

def cmd_list(date_filter=None):
    pull_latest()
    events, _ = decrypt_data()
    print("\n==================================================")
    print(f"📅 個人行程總覽 (指導老師：黃彥榮)")
    if date_filter:
        print(f"🔍 篩選: {date_filter}")
    print("==================================================")

    grouped = {}
    for e in events:
        d = e.get('date', '')
        if date_filter and not d.startswith(date_filter):
            continue
        grouped.setdefault(d, []).append(e)

    if not grouped:
        print("（無符合條件之排定行程）")
        return

    for d in sorted(grouped.keys()):
        print(f"\n【{d}】")
        day_evts = grouped[d]
        day_evts.sort(key=lambda x: x.get('time', ''))
        for e in day_evts:
            tag = "🔒 核心" if is_core_event(e.get('title', '')) else "📝 瑣事"
            print(f"  {tag}  {e.get('time', '全天'):<15}  {e.get('title')}")
    print("")

def cmd_add(date_str, time_str, title, password=None):
    is_core = is_core_event(title)
    if is_core:
        if not verify_password(password):
            print("\n🔒 【權限阻擋】此行程涉及「家教 / 診所 / 公務」核心項目！")
            print("   請提供正確管理員密碼 (--password <密碼>) 才能排入。\n")
            sys.exit(1)
        print("🔓 管理員密碼驗證通過！")

    if not pull_latest():
        print("❌ 請先解決遠端同步衝突後再寫入行程。")
        return
    events, notes = decrypt_data()

    # 衝突檢驗
    conflict = check_overlap(date_str, time_str, events)
    if conflict:
        print(f"\n❌ 【時段衝突阻擋】{date_str} {time_str} 與既有行程 {conflict} 重疊！")
        print("   安全防護：禁止重疊排課/行程。\n")
        sys.exit(1)

    events.append({'date': date_str, 'time': time_str, 'title': title})
    def sort_key(e):
        t = e.get('time', '')
        if t == '全天': t = '00:00'
        return (e.get('date', ''), t)
    events.sort(key=sort_key)

    tag = "核心公務" if is_core else "生活瑣事"
    print(f"✅ 成功新增【{tag}】：{date_str} {time_str} {title}")
    encrypt_and_push(events, notes, f"Add {title} ({date_str})")

def cmd_remove(date_str, title, password=None):
    if not pull_latest():
        print("❌ 請先解決遠端同步衝突後再寫入行程。")
        return
    events, notes = decrypt_data()
    matching = [e for e in events if e.get('date') == date_str and title in e.get('title', '')]
    if not matching:
        print(f"⚠️ 在 {date_str} 未找到包含「{title}」的行程。")
        return

    target = matching[0]
    is_core = is_core_event(target.get('title', ''))
    if is_core:
        if not verify_password(password):
            print(f"\n🔒 【權限阻擋】「{target.get('title')}」屬於核心公務（家教/診所）！")
            print("   刪除或修改必須提供正確管理員密碼 (--password <密碼>)。\n")
            sys.exit(1)
        print("🔓 管理員密碼驗證通過！")

    remain = [e for e in events if not (e.get('date') == date_str and title in e.get('title', ''))]
    print(f"🗑️ 已成功刪除：{date_str} {target.get('time')} {target.get('title')}")
    encrypt_and_push(remain, notes, f"Remove {title} ({date_str})")


def main():
    parser = argparse.ArgumentParser(description="多端行事曆管理工具 (黃彥榮老師)")
    subparsers = parser.add_subparsers(dest="action")

    # list
    p_list = subparsers.add_parser("list", help="查看行程總覽")
    p_list.add_argument("date", nargs="?", default=None, help="篩選日期 (YYYY-MM-DD 或 YYYY-MM)")

    # add
    p_add = subparsers.add_parser("add", help="新增行程")
    p_add.add_argument("date", help="日期 (YYYY-MM-DD)")
    p_add.add_argument("time", help="時段 (例: 14:30 - 15:30)")
    p_add.add_argument("title", help="行程名稱")
    p_add.add_argument("--password", "-p", default=None, help="修改核心公務所需密碼")

    # remove
    p_del = subparsers.add_parser("remove", help="刪除行程")
    p_del.add_argument("date", help="日期 (YYYY-MM-DD)")
    p_del.add_argument("title", help="行程名稱關鍵字")
    p_del.add_argument("--password", "-p", default=None, help="刪除核心公務所需密碼")

    args = parser.parse_args()

    if args.action == "list":
        cmd_list(args.date)
    elif args.action == "add":
        cmd_add(args.date, args.time, args.title, args.password)
    elif args.action == "remove":
        cmd_remove(args.date, args.title, args.password)
    else:
        parser.print_help()

if __name__ == '__main__':
    main()
