import os
import csv
import json
import time
import requests
from datetime import datetime, timezone, timedelta
from flask import Flask, request, jsonify, render_template

app = Flask(__name__)

LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
TEACHER_GROUP_ID = os.getenv("TEACHER_GROUP_ID", "")

STUDENTS_FILE = "students.csv"

pickup_queue = []
last_event_info = {}

TAIWAN_TZ = timezone(timedelta(hours=8))


def now_text():
    return datetime.now(TAIWAN_TZ).strftime("%H:%M:%S")


def load_students():
    students = []

    if not os.path.exists(STUDENTS_FILE):
        print("❌ 找不到 students.csv")
        return students

    with open(STUDENTS_FILE, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)

        for row in reader:
            name = row.get("學生姓名", "").strip()
            english_name = row.get("英文姓名", "").strip()
            class_name = row.get("班級", "").strip()

            if name:
                students.append({
                    "name": name,
                    "english_name": english_name,
                    "class_name": class_name
                })

    return students


def push_to_line(to_id, message):
    if not LINE_CHANNEL_ACCESS_TOKEN:
        print("❌ 沒有 LINE_CHANNEL_ACCESS_TOKEN")
        return False

    if not to_id:
        print("❌ 沒有 to_id")
        return False

    url = "https://api.line.me/v2/bot/message/push"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
    }

    data = {
        "to": to_id,
        "messages": [
            {
                "type": "text",
                "text": message
            }
        ]
    }

    r = requests.post(url, headers=headers, data=json.dumps(data))
    print("📨 LINE status:", r.status_code)
    print("📨 response:", r.text)

    return r.status_code == 200


def send_teacher_quick_reply(group_id, student_name, english_name="", class_name=""):
    if not group_id:
        print("❌ 沒有 TEACHER_GROUP_ID")
        return False

    url = "https://api.line.me/v2/bot/message/push"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
    }

    display_name = student_name
    if english_name:
        display_name += f" {english_name}"

    text = (
        f"📢 接送通知\n"
        f"學生：{display_name}\n"
        f"班級：{class_name if class_name else '未填'}\n\n"
        f"請老師選擇目前狀態："
    )

    data = {
        "to": group_id,
        "messages": [
            {
                "type": "text",
                "text": text,
                "quickReply": {
                    "items": [
                        {
                            "type": "action",
                            "action": {
                                "type": "message",
                                "label": "🎒 收拾書包",
                                "text": f"{student_name} 收拾書包"
                            }
                        },
                        {
                            "type": "action",
                            "action": {
                                "type": "message",
                                "label": "⏳ 5–10分鐘",
                                "text": f"{student_name} 5到10分鐘"
                            }
                        },
                        {
                            "type": "action",
                            "action": {
                                "type": "message",
                                "label": "🚶 已下樓",
                                "text": f"{student_name} 已下樓"
                            }
                        },
                        {
                            "type": "action",
                            "action": {
                                "type": "message",
                                "label": "❌ 取消",
                                "text": f"{student_name} 取消接送"
                            }
                        }
                    ]
                }
            }
        ]
    }

    r = requests.post(url, headers=headers, data=json.dumps(data))
    print("📨 QuickReply status:", r.status_code)
    print("📨 QuickReply response:", r.text)

    return r.status_code == 200


def find_queue_student(student_name):
    for item in pickup_queue:
        if item["student_name"] == student_name:
            return item
    return None


def remove_queue_student(student_name):
    global pickup_queue
    pickup_queue = [
        item for item in pickup_queue
        if item["student_name"] != student_name
    ]


def check_time_reminders():
    now = time.time()

    for item in pickup_queue:
        if item.get("status") == "5–10分鐘" and item.get("remind_at"):
            if now >= item["remind_at"] and not item.get("reminder_sent"):
                item["reminder_sent"] = True
                item["status"] = "提醒中"
                item["status_text"] = "⏰ 已超過 10 分鐘，請老師再次確認"

                if TEACHER_GROUP_ID:
                    push_to_line(
                        TEACHER_GROUP_ID,
                        f"⏰ 接送提醒\n學生：{item['student_name']}\n剛剛已選擇 5–10 分鐘，現在請老師再次確認。"
                    )


@app.route("/")
def home():
    return "PiXiE 接送系統 V15 自動叫號＋時間提醒版 運作中"


@app.route("/debug")
def debug():
    return jsonify(last_event_info)


@app.route("/board")
def board():
    return render_template("board.html")


@app.route("/api/queue")
def api_queue():
    check_time_reminders()
    return jsonify(pickup_queue)


@app.route("/api/call/<int:index>", methods=["POST"])
def call_student(index):
    if index < 0 or index >= len(pickup_queue):
        return jsonify({"success": False})

    item = pickup_queue[index]

    student_name = item["student_name"]
    user_id = item["user_id"]

    message = f"老師已叫號：{student_name}，請準備到門口接送。"

    if user_id:
        push_to_line(user_id, message)

    pickup_queue.pop(index)

    return jsonify({
        "success": True,
        "student_name": student_name
    })


@app.route("/api/announced/<student_name>", methods=["POST"])
def announced_student(student_name):
    remove_queue_student(student_name)
    return jsonify({"success": True})


@app.route("/api/clear", methods=["POST"])
def clear_queue():
    pickup_queue.clear()
    return jsonify({"success": True})


@app.route("/callback", methods=["POST"])
def callback():
    global last_event_info

    body = request.get_json()

    if not body:
        return "OK"

    events = body.get("events", [])
    students = load_students()

    for event in events:
        if event.get("type") != "message":
            continue

        message = event.get("message", {})

        if message.get("type") != "text":
            continue

        text = message.get("text", "").strip()
        source = event.get("source", {})

        user_id = source.get("userId", "")
        group_id = source.get("groupId", "")
        source_type = source.get("type", "")

        last_event_info = {
            "text": text,
            "source_type": source_type,
            "user_id": user_id,
            "group_id": group_id
        }

        print("📨 訊息:", text)
        print("來源:", source_type)
        print("👤 user_id:", user_id)
        print("👥 group_id:", group_id)

        # =========================
        # 老師群組選項
        # =========================
        if source_type == "group":
            for student in students:
                student_name = student["name"]

                if student_name in text:
                    item = find_queue_student(student_name)

                    if not item:
                        print("⚠️ queue 找不到學生:", student_name)
                        break

                    parent_user_id = item.get("user_id", "")

                    if "收拾書包" in text:
                        item["status"] = "收拾書包"
                        item["status_text"] = "🎒 正在收拾書包"
                        item["updated_at"] = now_text()

                        push_to_line(
                            parent_user_id,
                            f"{student_name} 正在收拾書包，請稍候。"
                        )

                    elif "5到10分鐘" in text or "5-10分鐘" in text or "5–10分鐘" in text:
                        item["status"] = "5–10分鐘"
                        item["status_text"] = "⏳ 約 5–10 分鐘"
                        item["updated_at"] = now_text()
                        item["remind_at"] = time.time() + 600
                        item["reminder_sent"] = False

                        push_to_line(
                            parent_user_id,
                            f"{student_name} 約 5–10 分鐘後可以下樓，請稍候。"
                        )

                    elif "已下樓" in text:
                        item["status"] = "已下樓"
                        item["status_text"] = "🚶 已下樓，自動叫號中"
                        item["updated_at"] = now_text()
                        item["announce"] = True

                        push_to_line(
                            parent_user_id,
                            f"{student_name} 已經下樓，請到門口接送。"
                        )

                    elif "取消接送" in text or "取消" in text:
                        push_to_line(
                            parent_user_id,
                            f"{student_name} 本次接送通知已取消。"
                        )
                        remove_queue_student(student_name)

                    break

            return "OK"

        # =========================
        # 家長私訊：接學生
        # =========================
        if "接" in text:
            matched_student = None

            for student in students:
                if student["name"] in text:
                    matched_student = student
                    break

            if matched_student:
                student_name = matched_student["name"]
                english_name = matched_student.get("english_name", "")
                class_name = matched_student.get("class_name", "")

                already_exists = any(
                    item["student_name"] == student_name
                    for item in pickup_queue
                )

                if not already_exists:
                    pickup_queue.append({
                        "student_name": student_name,
                        "english_name": english_name,
                        "class_name": class_name,
                        "user_id": user_id,
                        "status": "等待處理",
                        "status_text": "等待老師處理",
                        "created_at": now_text(),
                        "updated_at": now_text(),
                        "announce": False,
                        "remind_at": None,
                        "reminder_sent": False
                    })

                    if TEACHER_GROUP_ID:
                        send_teacher_quick_reply(
                            TEACHER_GROUP_ID,
                            student_name,
                            english_name,
                            class_name
                        )
                else:
                    print("⚠️ 已在 queue，不重複加入")

            else:
                print("❌ 找不到學生:", text)

    return "OK"


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))

    app.run(
        host="0.0.0.0",
        port=port
    )
