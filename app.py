import os
import csv
import json
import requests
from flask import Flask, request, jsonify, render_template

app = Flask(__name__)

LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
TEACHER_GROUP_ID = os.getenv("TEACHER_GROUP_ID", "")

STUDENTS_FILE = "students.csv"

pickup_queue = []
last_event_info = {}


# =========================
# 讀學生名單
# =========================

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

    print(f"📋 載入學生數量：{len(students)}")
    return students


# =========================
# LINE 一般推播
# =========================

def push_to_line(to_id, message):
    print("📤 發送 LINE")
    print("to_id:", to_id)
    print("message:", message)

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


# =========================
# 老師群組快速選項
# =========================

def send_teacher_quick_reply(group_id, student_name, english_name="", class_name=""):
    print("📤 發送老師群組快速選項")

    if not LINE_CHANNEL_ACCESS_TOKEN:
        print("❌ 沒有 LINE_CHANNEL_ACCESS_TOKEN")
        return False

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


# =========================
# 找 queue 裡的學生
# =========================

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


# =========================
# 首頁
# =========================

@app.route("/")
def home():
    return "PiXiE 接送系統 V14 運作中"


# =========================
# Debug
# =========================

@app.route("/debug")
def debug():
    return jsonify(last_event_info)


# =========================
# 看板
# =========================

@app.route("/board")
def board():
    return render_template("board.html")


# =========================
# Queue API
# =========================

@app.route("/api/queue")
def api_queue():
    return jsonify(pickup_queue)


# =========================
# 看板叫號
# =========================

@app.route("/api/call/<int:index>", methods=["POST"])
def call_student(index):
    print("🔔 看板叫號")

    if index < 0 or index >= len(pickup_queue):
        print("❌ index 錯誤")
        return jsonify({"success": False})

    item = pickup_queue[index]

    student_name = item["student_name"]
    user_id = item["user_id"]

    message = f"老師已叫號：{student_name}，請準備到門口接送。"

    if user_id:
        push_to_line(user_id, message)
    else:
        print("❌ 沒有家長 user_id")

    pickup_queue.pop(index)

    return jsonify({
        "success": True,
        "student_name": student_name
    })


# =========================
# 清空
# =========================

@app.route("/api/clear", methods=["POST"])
def clear_queue():
    pickup_queue.clear()
    print("🧹 已清空 queue")
    return jsonify({"success": True})


# =========================
# LINE Webhook
# =========================

@app.route("/callback", methods=["POST"])
def callback():
    global last_event_info

    body = request.get_json()
    print("📩 webhook 收到")

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
        # 老師群組按選項
        # =========================

        if source_type == "group":
            for student in students:
                student_name = student["name"]

                if student_name in text:
                    item = find_queue_student(student_name)

                    if not item:
                        print("⚠️ 群組回覆，但 queue 找不到學生:", student_name)
                        break

                    parent_user_id = item.get("user_id", "")

                    if "收拾書包" in text:
                        push_to_line(
                            parent_user_id,
                            f"{student_name} 正在收拾書包，請稍候。"
                        )

                    elif "5到10分鐘" in text or "5-10分鐘" in text or "5–10分鐘" in text:
                        push_to_line(
                            parent_user_id,
                            f"{student_name} 約 5–10 分鐘後可以下樓，請稍候。"
                        )

                    elif "已下樓" in text:
                        push_to_line(
                            parent_user_id,
                            f"{student_name} 已經下樓，請到門口接送。"
                        )
                        remove_queue_student(student_name)

                    elif "取消接送" in text or "取消" in text:
                        push_to_line(
                            parent_user_id,
                            f"{student_name} 本次接送通知已取消。"
                        )
                        remove_queue_student(student_name)

                    break

            return "OK"

        # =========================
        # 家長私訊：接學生姓名
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

                print("✅ 找到學生:", student_name)

                already_exists = any(
                    item["student_name"] == student_name
                    for item in pickup_queue
                )

                if not already_exists:
                    pickup_queue.append({
                        "student_name": student_name,
                        "english_name": english_name,
                        "class_name": class_name,
                        "user_id": user_id
                    })

                    print("📥 加入 queue:", student_name)

                    if TEACHER_GROUP_ID:
                        send_teacher_quick_reply(
                            TEACHER_GROUP_ID,
                            student_name,
                            english_name,
                            class_name
                        )
                    else:
                        print("⚠️ 尚未設定 TEACHER_GROUP_ID")

                else:
                    print("⚠️ 已在 queue，不重複加入")

            else:
                print("❌ 找不到學生:", text)

    return "OK"


# =========================
# 啟動
# =========================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))

    app.run(
        host="0.0.0.0",
        port=port
    )
