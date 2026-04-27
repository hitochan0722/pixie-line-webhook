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

# debug用
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
# LINE 發送
# =========================

def push_to_line(to_id, message):

    print("📤 發送 LINE")
    print("to_id:", to_id)

    if not LINE_CHANNEL_ACCESS_TOKEN:
        print("❌ 沒有 TOKEN")
        return

    if not to_id:
        print("❌ 沒有 to_id")
        return

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

    r = requests.post(
        url,
        headers=headers,
        data=json.dumps(data)
    )

    print("📨 LINE status:", r.status_code)
    print("📨 response:", r.text)


# =========================
# 首頁
# =========================

@app.route("/")
def home():
    return "PiXiE 接送系統 V13 運作中"


# =========================
# Debug頁
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
# 叫號
# =========================

@app.route("/api/call/<int:index>", methods=["POST"])
def call_student(index):

    print("🔔 叫號")

    if index < 0 or index >= len(pickup_queue):
        print("❌ index 錯")
        return jsonify({"success": False})

    item = pickup_queue[index]

    student_name = item["student_name"]
    user_id = item["user_id"]

    print("👦 叫:", student_name)

    message = f"老師已叫號：{student_name}，請準備到門口接送。"

    if user_id:

        push_to_line(
            user_id,
            message
        )

    pickup_queue.pop(index)

    return jsonify({
        "success": True
    })


# =========================
# 清空
# =========================

@app.route("/api/clear", methods=["POST"])
def clear_queue():

    pickup_queue.clear()

    print("🧹 清空 queue")

    return jsonify({
        "success": True
    })


# =========================
# LINE Webhook
# =========================

@app.route("/callback", methods=["POST"])
def callback():

    global last_event_info

    body = request.get_json()

    print("📩 webhook 收到")

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

        # 存 debug
        last_event_info = {
            "text": text,
            "source_type": source_type,
            "user_id": user_id,
            "group_id": group_id
        }

        print("📨 訊息:", text)
        print("來源:", source_type)
        print("👤 user:", user_id)
        print("👥 group:", group_id)

        # 家長傳 接XXX
        if "接" in text:

            matched_student = None

            for student in students:

                if student["name"] in text:

                    matched_student = student
                    break

            if matched_student:

                student_name = matched_student["name"]
                english_name = matched_student["english_name"]
                class_name = matched_student["class_name"]

                print("✅ 找到:", student_name)

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

                    print("📥 加入 queue")

                    # 通知老師群組
                    if TEACHER_GROUP_ID:

                        teacher_message = (
                            f"📢 接送通知\n"
                            f"學生：{student_name}\n"
                            f"班級：{class_name if class_name else '未填'}"
                        )

                        push_to_line(
                            TEACHER_GROUP_ID,
                            teacher_message
                        )

                    else:

                        print("⚠️ 尚未設定 TEACHER_GROUP_ID")

            else:

                print("❌ 找不到學生")

    return "OK"


# =========================

if __name__ == "__main__":

    port = int(os.environ.get("PORT", 5000))

    app.run(
        host="0.0.0.0",
        port=port
    )
