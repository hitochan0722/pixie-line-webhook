import os
import csv
import json
import requests
from flask import Flask, request, jsonify, render_template

app = Flask(__name__)

LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")

STUDENTS_FILE = "students.csv"

pickup_queue = []

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

            if name:
                students.append({
                    "name": name
                })

    print(f"📋 載入學生數量：{len(students)}")

    return students


# =========================
# LINE Push
# =========================

def push_to_line(user_id, message):

    print("📤 準備發送 LINE")

    print("user_id:", user_id)
    print("message:", message)

    if not LINE_CHANNEL_ACCESS_TOKEN:
        print("❌ 沒有 LINE_CHANNEL_ACCESS_TOKEN")
        return

    url = "https://api.line.me/v2/bot/message/push"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
    }

    data = {
        "to": user_id,
        "messages": [
            {
                "type": "text",
                "text": message
            }
        ]
    }

    r = requests.post(url, headers=headers, data=json.dumps(data))

    print("📨 LINE push status:", r.status_code)
    print("📨 LINE push response:", r.text)


# =========================
# 首頁
# =========================

@app.route("/")
def home():
    return "PiXiE 接送系統運作中"


# =========================
# 看板
# =========================

@app.route("/board")
def board():
    return render_template("board.html")


# =========================
# 取得 queue
# =========================

@app.route("/api/queue")
def api_queue():
    return jsonify(pickup_queue)


# =========================
# 叫號
# =========================

@app.route("/api/call/<int:index>", methods=["POST"])
def call_student(index):

    print("🔔 收到叫號")

    if index < 0 or index >= len(pickup_queue):
        print("❌ index 錯誤")
        return jsonify({"success": False})

    item = pickup_queue[index]

    student_name = item["student_name"]
    user_id = item["user_id"]

    print("👦 叫號學生:", student_name)
    print("🆔 user_id:", user_id)

    message = f"老師已叫號：{student_name}，請準備到門口接送。"

    if user_id:

        push_to_line(user_id, message)

    else:

        print("❌ 沒有 user_id")

    pickup_queue.pop(index)

    return jsonify({
        "success": True,
        "student_name": student_name
    })


# =========================
# 清空 queue
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

    body = request.get_json()

    print("📩 收到 LINE webhook")

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

        print("📨 收到訊息:", text)
        print("🆔 user_id:", user_id)

        if "接" in text:

            matched_student = None

            for student in students:

                if student["name"] in text:

                    matched_student = student
                    break

            if matched_student:

                print("✅ 找到學生:", matched_student["name"])

                already_exists = any(
                    item["student_name"] == matched_student["name"]
                    for item in pickup_queue
                )

                if not already_exists:

                    pickup_queue.append({
                        "student_name": matched_student["name"],
                        "user_id": user_id
                    })

                    print("📥 加入 queue:", matched_student["name"])

                else:

                    print("⚠️ 已存在 queue")

            else:

                print("❌ 找不到學生:", text)

    return "OK"


# =========================

if __name__ == "__main__":

    port = int(os.environ.get("PORT", 5000))

    app.run(host="0.0.0.0", port=port)
