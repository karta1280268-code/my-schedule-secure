#!/usr/bin/env python3
import os
import sys
import json
import datetime
import subprocess
import urllib.request
import urllib.error
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

DIR = os.path.dirname(os.path.abspath(__file__))
DATA_ENC_FILE = os.path.join(DIR, "schedule_data.enc")
HISTORY_FILE = os.path.join(DIR, "reminder_history.json")

# Environment variables from GitHub Secrets
CALENDAR_PASS = os.getenv("CALENDAR_PASS", "0923")
LINE_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
GMAIL_SENDER = os.getenv("GMAIL_SENDER", "")
GMAIL_APP_PASS = os.getenv("GMAIL_APP_PASSWORD", "")
GMAIL_RECIPIENT = os.getenv("GMAIL_RECIPIENT", "")

WEEKDAYS = ["一", "二", "三", "四", "五", "六", "日"]

def load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def save_json(path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error saving {path}: {e}")

def decrypt_data():
    if not os.path.exists(DATA_ENC_FILE):
        print(f"Error: {DATA_ENC_FILE} does not exist.")
        return [], {}
    
    tmp_out = os.path.join(DIR, "temp_data.json")
    try:
        cmd = [
            "openssl", "enc", "-d", "-aes-256-cbc", "-pbkdf2",
            "-in", DATA_ENC_FILE,
            "-out", tmp_out,
            "-pass", f"pass:{CALENDAR_PASS}"
        ]
        subprocess.run(cmd, check=True)
        with open(tmp_out, "r", encoding="utf-8") as f:
            data = json.load(f)
        if os.path.exists(tmp_out):
            os.remove(tmp_out)
        return data.get("events", []), data.get("notes", {})
    except Exception as e:
        print(f"Decryption failed: {e}")
        if os.path.exists(tmp_out):
            os.remove(tmp_out)
        return [], {}

def send_line(text):
    if not LINE_TOKEN:
        print("LINE_TOKEN not set, skipping LINE broadcast.")
        return
    
    # 嚴格守則：無論如何，22:00 ~ 08:00 絕對不發送任何 LINE 訊息（避免吵到媽媽與您）
    tz = datetime.timezone(datetime.timedelta(hours=8))
    now_tw = datetime.datetime.now(tz)
    if now_tw.hour >= 22 or now_tw.hour < 8:
        print(f"[{now_tw.strftime('%H:%M:%S')}] In quiet hours (22:00 - 08:00). Suppressing LINE message.")
        return
    
    url = "https://api.line.me/v2/bot/message/broadcast"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_TOKEN}"
    }
    payload = {
        "messages": [
            {
                "type": "text",
                "text": text
            }
        ]
    }
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=15) as resp:
            if resp.status == 200:
                print("LINE broadcast sent successfully.")
    except Exception as e:
        print(f"Failed to send LINE broadcast: {e}")

def send_email(subject, body):
    if not GMAIL_SENDER or not GMAIL_APP_PASS or not GMAIL_RECIPIENT:
        print("Gmail configuration incomplete, skipping email.")
        return
    
    msg = MIMEMultipart()
    msg['From'] = GMAIL_SENDER
    msg['To'] = GMAIL_RECIPIENT
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain', 'utf-8'))
    
    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(GMAIL_SENDER, GMAIL_APP_PASS)
        server.send_message(msg)
        server.quit()
        print(f"Email sent successfully to {GMAIL_RECIPIENT}.")
    except Exception as e:
        print(f"Failed to send email: {e}")

def format_summary_message(date_str, events, notes_dict, is_tomorrow=False):
    target_dt = datetime.datetime.strptime(date_str, "%Y-%m-%d")
    weekday_str = f"星期{WEEKDAYS[target_dt.weekday()]}"

    target_events = [e for e in events if e.get("date") == date_str]
    target_notes = notes_dict.get(date_str, [])

    label = "明日行程預告" if is_tomorrow else "今日行程總覽"

    msg = f"📅【{label}】\n"
    msg += f"🗓️ {date_str}（{weekday_str}）\n"
    msg += "━━━━━━━━━━━━━━━\n"

    if target_events:
        msg += "⏰ 預定行程：\n"
        for e in sorted(target_events, key=lambda x: x.get("time", "")):
            time_part = e.get("time", "")
            title_part = e.get("title", "")
            msg += f"• {time_part}｜{title_part}\n"
    else:
        msg += "⏰ 預定行程：\n• 目前無預定行程\n"

    if target_notes:
        msg += "\n💡 貼心備忘：\n"
        for n in target_notes:
            msg += f"• {n}\n"

    msg += "━━━━━━━━━━━━━━━\n"
    if is_tomorrow:
        msg += "請提早確認教材並做好準備，祝明天順利！"
    else:
        msg += "祝您今天一切順利，充實愉快！"

    return msg

def main():
    events, notes = decrypt_data()
    if not events and not notes:
        print("No schedule data found or decrypted. Exiting.")
        return

    history = load_json(HISTORY_FILE, {})
    
    # Use Taiwan Time (UTC+8)
    tz = datetime.timezone(datetime.timedelta(hours=8))
    now = datetime.datetime.now(tz)
    now_date_str = now.strftime("%Y-%m-%d")
    updated = False

    print(f"Current Taiwan Time: {now.strftime('%Y-%m-%d %H:%M:%S')}")

    # 1. 早上 08:00 寄送今日行程
    if now.hour >= 8:
        today_key = f"summary_today_{now_date_str}"
        if today_key not in history:
            msg = format_summary_message(now_date_str, events, notes, is_tomorrow=False)
            send_email(f"📅 今日行程總覽 ({now_date_str})", msg)
            send_line(msg)
            history[today_key] = now.isoformat()
            updated = True
            print(f"Sent 08:00 summary for {now_date_str}")

    # 2. 晚上 21:30 寄送明日行程 (避開 22:00 ~ 08:00 靜音勿擾時段)
    if (now.hour == 21 and now.minute >= 30) or now.hour >= 22:
        tomorrow_key = f"summary_tomorrow_{now_date_str}"
        if tomorrow_key not in history:
            tomorrow = now + datetime.timedelta(days=1)
            tomorrow_date_str = tomorrow.strftime("%Y-%m-%d")
            msg = format_summary_message(tomorrow_date_str, events, notes, is_tomorrow=True)
            send_email(f"📅 明日行程預告 ({tomorrow_date_str})", msg)
            send_line(msg)
            history[tomorrow_key] = now.isoformat()
            updated = True
            print(f"Sent 21:30 preview for {tomorrow_date_str}")

    # 3. 行程提醒：依日期分析連續行程，只提醒每串連續行程的第一堂課 (或自訂 remind_at)
    today_events = [e for e in events if e.get("date") == now_date_str and e.get("time") and "全天" not in e.get("time")]
    
    parsed_today = []
    for e in today_events:
        parts = e.get("time", "").split("-")
        st_str = parts[0].strip()
        try:
            st = datetime.datetime.strptime(f"{now_date_str} {st_str}", "%Y-%m-%d %H:%M").replace(tzinfo=tz)
        except ValueError:
            continue
        if len(parts) > 1:
            et_str = parts[1].strip()
            try:
                et = datetime.datetime.strptime(f"{now_date_str} {et_str}", "%Y-%m-%d %H:%M").replace(tzinfo=tz)
            except ValueError:
                et = st + datetime.timedelta(hours=1)
        else:
            et = st + datetime.timedelta(hours=1)
        parsed_today.append({"raw": e, "st": st, "et": et, "st_str": st_str, "title": e.get("title", "")})

    parsed_today.sort(key=lambda x: x["st"])

    # 鏈狀串聯判定：相鄰行程間隔 <= 60 分鐘視為連續行程
    consecutive_groups = []
    curr_group = []
    for item in parsed_today:
        if not curr_group:
            curr_group.append(item)
        else:
            gap = (item["st"] - curr_group[-1]["et"]).total_seconds() / 60.0
            if -30.0 <= gap <= 60.0:
                curr_group.append(item)
            else:
                consecutive_groups.append(curr_group)
                curr_group = [item]
    if curr_group:
        consecutive_groups.append(curr_group)

    # 針對每個連續行程群組進行提醒處理
    for group in consecutive_groups:
        first_item = group[0]
        following_items = group[1:]
        
        # 3-A. 第一堂課的常規課前 1 小時提醒 (後續連堂自動靜音免打擾)
        first_raw = first_item["raw"]
        first_title = first_item["title"]
        first_st_str = first_item["st_str"]
        diff_minutes = (first_item["st"] - now).total_seconds() / 60.0
        event_key = f"{now_date_str}_{first_st_str}_{first_title}_1h"

        is_tutor = ("學生" in first_title or "家教" in first_title)
        
        # 如果第一堂課未設自訂 remind_at，走常規 1 小時提醒 (0 < diff_minutes <= 75.0)
        if not first_raw.get("remind_at") and 0.0 < diff_minutes <= 75.0:
            if event_key not in history:
                notif_title = "🔔 家教上課提醒" if is_tutor else "🔔 行程提醒"
                
                # 若有接續的連續行程，在第一則提醒中貼心附註
                subsequent_note = ""
                if following_items:
                    chain_lines = [f"• {x['raw'].get('time', '')}｜{x['title']}" for x in following_items]
                    subsequent_note = "\n\n📌 本日接續行程：\n" + "\n".join(chain_lines) + "\n（以上為連續行程，出門後將不再重複推播，請安心專心上課！）"

                if is_tutor:
                    email_body = f"您好，\n\n您的行程「{first_title}」將於一小時後（{first_st_str}）開始，請記得準時上課！{subsequent_note}\n\n- 家教提醒系統自動發送"
                    line_msg = f"🔔 上課提醒\n\n還有 1 小時！（{first_st_str}）\n「{first_title}」即將開始，請記得準時上課！{subsequent_note}"
                else:
                    email_body = f"您好，\n\n您的行程「{first_title}」將於一小時後（{first_st_str}）開始，請做好準備！{subsequent_note}\n\n- 專屬行事曆系統自動發送"
                    line_msg = f"🔔 行程提醒\n\n「{first_title}」將於 {first_st_str} 開始，請做好準備！{subsequent_note}"

                send_email(notif_title, email_body)
                send_line(line_msg)

                history[event_key] = now.isoformat()
                updated = True
                print(f"Sent 1-hour alert for {first_title} at {first_st_str} (chain has {len(group)} events)")

        # 3-B. 任何行程若有明確指定「remind_at」（例如指定 13:30 提醒），依然精準觸發
        for item in group:
            raw_e = item["raw"]
            remind_at = raw_e.get("remind_at")
            if remind_at:
                try:
                    remind_dt = datetime.datetime.strptime(f"{now_date_str} {remind_at}", "%Y-%m-%d %H:%M").replace(tzinfo=tz)
                    remind_diff = (now - remind_dt).total_seconds() / 60.0
                    remind_key = f"{now_date_str}_{remind_at}_{item['title']}_custom"

                    if -2.0 <= remind_diff <= 25.0 and remind_key not in history:
                        note_custom = raw_e.get("remind_note", f"「{item['title']}」預定於 {item['st_str']} 開始，請做好準備！")
                        item_is_tutor = ("學生" in item["title"] or "家教" in item["title"])
                        notif_title = f"🔔 行程出發提醒：{item['title']}" if not item_is_tutor else f"🔔 家教提醒：{item['title']}"
                        line_msg = f"🔔 行程出發提醒\n\n⏰ 提醒時間：{remind_at}\n\n🚆 行程：「{item['title']}」\n⏱️ 開始／發車時間：{item['st_str']}\n\n💡 溫馨提醒：{note_custom}"
                        email_body = f"您好，\n\n您設定的提醒時間（{remind_at}）已到！\n\n行程：「{item['title']}」\n時間：{item['st_str']}\n備註：{note_custom}\n\n- 專屬行事曆系統自動發送"

                        send_email(notif_title, email_body)
                        send_line(line_msg)

                        history[remind_key] = now.isoformat()
                        updated = True
                        print(f"Sent custom alert for {item['title']} scheduled at {remind_at}")
                except Exception as ex:
                    print(f"Error processing custom remind_at for {item['title']}: {ex}")

    # Prune history entries older than 7 days
    cutoff = (now - datetime.timedelta(days=7)).isoformat()
    pruned_history = {k: v for k, v in history.items() if v >= cutoff}
    if len(pruned_history) != len(history):
        updated = True
        history = pruned_history

    if updated:
        save_json(HISTORY_FILE, history)
        print("History updated.")

if __name__ == "__main__":
    main()
