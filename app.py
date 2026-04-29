from flask import Flask, request, jsonify, Response
import os
import csv
import json
import requests
from datetime import datetime

app = Flask(__name__)

CHANNEL_ACCESS_TOKEN = os.getenv("CHANNEL_ACCESS_TOKEN", "")
CHANNEL_SECRET = os.getenv("CHANNEL_SECRET", "")
TEACHER_GROUP_ID = os.getenv("TEACHER_GROUP_ID", "")

STUDENTS_FILE = "students.csv"

pickup_queue = []
pickup_records = {}


# =========================
# LINE 基本功能
# =========================

def line_headers():
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}"
    }


def reply_to_line(reply_token, text):
    if not reply_token:
        return

    url = "https://api.line.me/v2/bot/message/reply"
    payload = {
        "replyToken": reply_token,
        "messages": [{"type": "text", "text": text}]
    }
    requests.post(url, headers=line_headers(), json=payload)


def push_to_line(to, messages):
    if not to:
        return

    url = "https://api.line.me/v2/bot/message/push"
    payload = {
        "to": to,
        "messages": messages
    }
    requests.post(url, headers=line_headers(), json=payload)


# =========================
# 學生資料
# =========================

def load_students():
    students = []

    if not os.path.exists(STUDENTS_FILE):
        return students

    with open(STUDENTS_FILE, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            students.append(row)

    return students


def find_student_by_parent_user_id(user_id):
    students = load_students()

    for s in students:
        parent_id = (
            s.get("parent_user_id")
            or s.get("家長LINE_ID")
            or s.get("家長LINE ID")
            or s.get("line_user_id")
            or ""
        ).strip()

        if parent_id == user_id:
            return s

    return None


def find_student_by_text(text):
    students = load_students()

    for s in students:
        name = (
            s.get("學生姓名")
            or s.get("student_name")
            or s.get("姓名")
            or ""
        ).strip()

        if name and name in text:
            return s

    return None


def get_student_name(student):
    return (
        student.get("學生姓名")
        or student.get("student_name")
        or student.get("姓名")
        or "學生"
    ).strip()


# =========================
# 接送廣播邏輯
# =========================

def add_pickup(student_name, parent_user_id):
    now = datetime.now().strftime("%H:%M:%S")

    record_id = f"{student_name}_{datetime.now().strftime('%Y%m%d%H%M%S')}"

    item = {
        "id": record_id,
        "student_name": student_name,
        "parent_user_id": parent_user_id,
        "time": now,
        "played": False
    }

    pickup_queue.append(item)
    pickup_records[record_id] = item

    return item


def notify_teacher_group(item):
    if not TEACHER_GROUP_ID:
        return

    student_name = item["student_name"]
    record_id = item["id"]

    message = {
        "type": "template",
        "altText": f"{student_name} 家長已到，請老師確認狀態",
        "template": {
            "type": "buttons",
            "title": "接送通知",
            "text": f"{student_name} 家長已到\n廣播已同步播放\n請老師選擇學生狀態",
            "actions": [
                {
                    "type": "postback",
                    "label": "收拾書包",
                    "data": f"action=packing&id={record_id}"
                },
                {
                    "type": "postback",
                    "label": "5–10分鐘",
                    "data": f"action=wait&id={record_id}"
                },
                {
                    "type": "postback",
                    "label": "已下樓",
                    "data": f"action=downstairs&id={record_id}"
                },
                {
                    "type": "postback",
                    "label": "取消",
                    "data": f"action=cancel&id={record_id}"
                }
            ]
        }
    }

    push_to_line(TEACHER_GROUP_ID, [message])


def handle_teacher_postback(event):
    data = event.get("postback", {}).get("data", "")
    reply_token = event.get("replyToken")

    params = {}
    for part in data.split("&"):
        if "=" in part:
            k, v = part.split("=", 1)
            params[k] = v

    action = params.get("action")
    record_id = params.get("id")

    item = pickup_records.get(record_id)

    if not item:
        reply_to_line(reply_token, "找不到這筆接送資料，可能已過期。")
        return

    student_name = item["student_name"]
    parent_user_id = item["parent_user_id"]

    if action == "packing":
        msg = f"{student_name} 正在收拾書包，請稍候一下。"

    elif action == "wait":
        msg = f"{student_name} 約 5–10 分鐘後下樓，請稍候。"

    elif action == "downstairs":
        msg = f"{student_name} 已經下樓囉。"

    elif action == "cancel":
        msg = f"{student_name} 的接送通知已取消。"

    else:
        msg = f"{student_name} 狀態已更新。"

    push_to_line(parent_user_id, [{"type": "text", "text": msg}])
    reply_to_line(reply_token, f"已通知家長：{msg}")


# =========================
# Webhook
# =========================

@app.route("/callback", methods=["POST"])
def callback():
    body = request.get_json()

    events = body.get("events", [])

    for event in events:
        event_type = event.get("type")
        source = event.get("source", {})
        user_id = source.get("userId")
        reply_token = event.get("replyToken")

        if event_type == "message":
            message = event.get("message", {})
            text = message.get("text", "").strip()

            if not text:
                continue

            # 家長傳「接」或「接小孩」
            if text.startswith("接"):
                student = find_student_by_parent_user_id(user_id)

                # 如果還沒綁定家長ID，就先用文字裡的學生姓名判斷
                if not student:
                    student = find_student_by_text(text)

                if not student:
                    reply_to_line(
                        reply_token,
                        "系統找不到對應學生，請輸入：接＋學生姓名，例如：接賴灝宇。"
                    )
                    continue

                student_name = get_student_name(student)

                # 這裡是重點：家長一傳，立刻加入廣播佇列
                item = add_pickup(student_name, user_id)

                # 同步通知老師群組，但老師按鈕不是觸發廣播，只是確認狀態
                notify_teacher_group(item)

                # 家長端先簡短確認
                reply_to_line(
                    reply_token,
                    f"已收到 {student_name} 的接送通知，現場已同步廣播。"
                )

        elif event_type == "postback":
            handle_teacher_postback(event)

    return "OK"


# =========================
# 看板 API
# =========================

@app.route("/api/pickup")
def api_pickup():
    unplayed = []

    for item in pickup_queue:
        if not item.get("played"):
            unplayed.append(item)
            item["played"] = True

    return jsonify(unplayed)


@app.route("/api/queue")
def api_queue():
    return jsonify(pickup_queue[-30:])


# =========================
# 廣播看板
# =========================

@app.route("/board")
def board():
    return """
<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="UTF-8">
<title>皮克西美語 接送廣播看板</title>
<style>
body {
    margin: 0;
    font-family: "Microsoft JhengHei", Arial, sans-serif;
    background: #fff7fb;
    color: #333;
    text-align: center;
}
.header {
    background: #ff8fb3;
    color: white;
    padding: 24px;
    font-size: 38px;
    font-weight: bold;
}
.sub {
    font-size: 22px;
    margin-top: 8px;
}
.now {
    margin-top: 60px;
    font-size: 36px;
    color: #777;
}
.student {
    margin-top: 30px;
    font-size: 96px;
    font-weight: bold;
    color: #e8437c;
}
.time {
    margin-top: 20px;
    font-size: 32px;
    color: #666;
}
.queue {
    width: 80%;
    margin: 60px auto;
    font-size: 28px;
}
.queue-title {
    font-weight: bold;
    margin-bottom: 20px;
}
.item {
    background: white;
    margin: 12px;
    padding: 18px;
    border-radius: 18px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.08);
}
</style>
</head>
<body>

<div class="header">
    皮克西美語 接送廣播看板
    <div class="sub">家長通知後，系統自動廣播</div>
</div>

<div class="now">目前接送學生</div>
<div class="student" id="student">等待通知</div>
<div class="time" id="time"></div>

<div class="queue">
    <div class="queue-title">最近接送紀錄</div>
    <div id="queueList"></div>
</div>

<script>
let recentQueue = [];

function speakStudent(name) {
    const text = name + "，家長到了，請準備放學。";
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = "zh-TW";
    utterance.rate = 0.9;
    utterance.pitch = 1;
    utterance.volume = 1;
    window.speechSynthesis.speak(utterance);
}

async function checkPickup() {
    try {
        const res = await fetch("/api/pickup");
        const data = await res.json();

        if (data.length > 0) {
            data.forEach(item => {
                document.getElementById("student").innerText = item.student_name;
                document.getElementById("time").innerText = item.time;

                speakStudent(item.student_name);

                recentQueue.unshift(item);
                recentQueue = recentQueue.slice(0, 10);
                renderQueue();
            });
        }
    } catch (e) {
        console.log(e);
    }
}

function renderQueue() {
    const list = document.getElementById("queueList");
    list.innerHTML = "";

    recentQueue.forEach(item => {
        const div = document.createElement("div");
        div.className = "item";
        div.innerText = item.time + "　" + item.student_name;
        list.appendChild(div);
    });
}

setInterval(checkPickup, 2000);
checkPickup();
</script>

</body>
</html>
"""


# =========================
# 首頁
# =========================

@app.route("/")
def home():
    return """
<h2>皮克西美語 LINE 系統運作中</h2>
<p><a href="/board">開啟接送廣播看板</a></p>
"""


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
