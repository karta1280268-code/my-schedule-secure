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

    # 2. 晚上 22:00 寄送明日行程
    if now.hour >= 22:
        tomorrow_key = f"summary_tomorrow_{now_date_str}"
        if tomorrow_key not in history:
            tomorrow = now + datetime.timedelta(days=1)
            tomorrow_date_str = tomorrow.strftime("%Y-%m-%d")
            msg = format_summary_message(tomorrow_date_str, events, notes, is_tomorrow=True)
            send_email(f"📅 明日行程預告 ({tomorrow_date_str})", msg)
            send_line(msg)
            history[tomorrow_key] = now.isoformat()
            updated = True
            print(f"Sent 22:00 preview for {tomorrow_date_str}")

    # 3. 行程提醒：支援自訂提醒時間 (remind_at) 或 預設課前 1 小時提醒
    for e in events:
        date_str = e.get("date", "")
        time_str = e.get("time", "")
        title = e.get("title", "")
        remind_at = e.get("remind_at")

        if not date_str or not time_str or "全天" in time_str:
            continue

        parts = time_str.split("-")
        start_time_str = parts[0].strip()

        try:
            event_dt_naive = datetime.datetime.strptime(f"{date_str} {start_time_str}", "%Y-%m-%d %H:%M")
            event_dt = event_dt_naive.replace(tzinfo=tz)
        except ValueError:
            continue

        is_tutor = ("學生" in title or "家教" in title)

        # 3-A. 自訂提醒時間 (remind_at)
        if remind_at:
            try:
                remind_dt_naive = datetime.datetime.strptime(f"{date_str} {remind_at}", "%Y-%m-%d %H:%M")
                remind_dt = remind_dt_naive.replace(tzinfo=tz)
                remind_diff = (now - remind_dt).total_seconds() / 60.0
                remind_key = f"{date_str}_{remind_at}_{title}_custom"

                # 在提醒時間前後窗口內觸發 (-2 分鐘 ~ +25 分鐘，相容 cron-job 10 分鐘間隔)
                if -2.0 <= remind_diff <= 25.0 and remind_key not in history:
                    note_custom = e.get("remind_note", f"「{title}」預定於 {start_time_str} 開始，請做好準備！")
                    notif_title = f"🔔 行程出發提醒：{title}" if not is_tutor else f"🔔 家教提醒：{title}"
                    line_msg = f"🔔 行程出發提醒\n\n⏰ 提醒時間：{remind_at}\n\n🚆 行程：「{title}」\n⏱️ 開始／發車時間：{start_time_str}\n\n💡 溫馨提醒：{note_custom}"
                    email_body = f"您好，\n\n您設定的提醒時間（{remind_at}）已到！\n\n行程：「{title}」\n時間：{start_time_str}\n備註：{note_custom}\n\n- 專屬行事曆系統自動發送"

                    send_email(notif_title, email_body)
                    send_line(line_msg)

                    history[remind_key] = now.isoformat()
                    updated = True
                    print(f"Sent custom alert for {title} scheduled at {remind_at}")
            except Exception as ex:
                print(f"Error processing custom remind_at for {title}: {ex}")

        # 3-B. 預設 1 小時前提醒 (若未指定自訂 remind_at)
        else:
            diff_minutes = (event_dt - now).total_seconds() / 60.0
            event_key = f"{date_str}_{start_time_str}_{title}_1h"

            if 0.0 < diff_minutes <= 75.0:
                if event_key not in history:
                    notif_title = "🔔 家教上課提醒" if is_tutor else "🔔 行程提醒"
                    if is_tutor:
                        email_body = f"您好，\n\n您的行程「{title}」將於一小時後（{start_time_str}）開始，請記得準時上課！\n\n- 家教提醒系統自動發送"
                        line_msg = f"🔔 上課提醒\n\n還有 1 小時！（{start_time_str}）\n「{title}」即將開始，請記得準時上課！"
                    else:
                        email_body = f"您好，\n\n您的行程「{title}」將於一小時後（{start_time_str}）開始，請做好準備！\n\n- 專屬行事曆系統自動發送"
                        line_msg = f"🔔 行程提醒\n\n「{title}」將於 {start_time_str} 開始，請做好準備！"

                    send_email(notif_title, email_body)
                    send_line(line_msg)

                    history[event_key] = now.isoformat()
                    updated = True
                    print(f"Sent 1-hour alert for {title} at {start_time_str}")

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
