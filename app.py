from flask import Flask, request, jsonify
import os
import csv
import requests
from datetime import datetime

app = Flask(__name__)

print("===== PIXIE PICKUP FINAL SAFE VERSION =====")

CHANNEL_ACCESS_TOKEN = os.getenv("CHANNEL_ACCESS_TOKEN")
TEACHER_GROUP_ID = os.getenv("TEACHER_GROUP_ID")
STUDENTS_FILE = "students.csv"

pickup_queue = []
pickup_records = {}


# ======================
# LINE 基本功能
# ======================

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
        "messages": [
            {
                "type": "text",
                "text": text
            }
        ]
    }

    res = requests.post(url, headers=line_headers(), json=payload)
    print("REPLY STATUS:", res.status_code)
    print("REPLY RESPONSE:", res.text)


def push_to_line(to, messages):
    if not to:
        print("PUSH FAILED: no target")
        return

    url = "https://api.line.me/v2/bot/message/push"

    payload = {
        "to": to,
        "messages": messages
    }

    res = requests.post(url, headers=line_headers(), json=payload)
    print("PUSH TO:", to)
    print("PUSH STATUS:", res.status_code)
    print("PUSH RESPONSE:", res.text)


# ======================
# 學生資料
# ======================

def load_students():
    students = []

    if not os.path.exists(STUDENTS_FILE):
        print("找不到 students.csv")
        return students

    with open(STUDENTS_FILE, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            students.append(row)

    return students


def get_student_name(student):
    return (
        student.get("學生姓名")
        or student.get("student_name")
        or student.get("姓名")
        or ""
    ).strip()


def find_student_by_text(text):
    students = load_students()

    for student in students:
        name = get_student_name(student)

        if name and name in text:
            return student

    return None


def find_student_by_parent_id(user_id):
    students = load_students()

    for student in students:
        parent_id = (
            student.get("parent_user_id")
            or student.get("家長LINE_ID")
            or student.get("家長LINE ID")
            or student.get("line_user_id")
            or ""
        ).strip()

        if parent_id and parent_id == user_id:
            return student

    return None


# ======================
# 接送資料
# ======================

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

    print("ADD PICKUP:", item)

    return item


# ======================
# 通知老師群組
# ======================

def notify_teacher_group(item):
    student_name = item["student_name"]
    record_id = item["id"]

    print("TEACHER_GROUP_ID:", TEACHER_GROUP_ID)

    if not TEACHER_GROUP_ID:
        print("沒有 TEACHER_GROUP_ID，無法通知老師群組")
        return

    message = {
        "type": "template",
        "altText": f"{student_name} 接送通知",
        "template": {
            "type": "buttons",
            "title": "接送通知",
            "text": f"{student_name} 家長已到\n系統已自動廣播3次\n請老師回報學生狀態",
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


# ======================
# 老師按鈕回報
# ======================

def handle_teacher_postback(event):
    reply_token = event.get("replyToken")
    data = event.get("postback", {}).get("data", "")

    params = {}

    for part in data.split("&"):
        if "=" in part:
            key, value = part.split("=", 1)
            params[key] = value

    action = params.get("action")
    record_id = params.get("id")

    item = pickup_records.get(record_id)

    if not item:
        reply_to_line(reply_token, "找不到這筆接送資料，可能系統已重新啟動。")
        return

    student_name = item["student_name"]
    parent_user_id = item["parent_user_id"]

    if action == "packing":
        parent_msg = f"{student_name} 正在收拾書包，請稍候一下。"
        teacher_msg = f"已回報家長：{student_name} 正在收拾書包。"

    elif action == "wait":
        parent_msg = f"{student_name} 約 5–10 分鐘後下樓，請稍候。"
        teacher_msg = f"已回報家長：{student_name} 約 5–10 分鐘後下樓。"

    elif action == "downstairs":
        parent_msg = f"{student_name} 已經下樓囉。"
        teacher_msg = f"已回報家長：{student_name} 已經下樓。"

    elif action == "cancel":
        parent_msg = f"{student_name} 的接送通知已取消。"
        teacher_msg = f"已回報家長：{student_name} 接送通知已取消。"

    else:
        parent_msg = f"{student_name} 狀態已更新。"
        teacher_msg = f"已回報家長：{student_name} 狀態已更新。"

    push_to_line(parent_user_id, [
        {
            "type": "text",
            "text": parent_msg
        }
    ])

    reply_to_line(reply_token, teacher_msg)


# ======================
# LINE Webhook
# ======================

@app.route("/callback", methods=["POST"])
def callback():
    body = request.get_json()
    print("CALLBACK BODY:", body)

    events = body.get("events", [])

    for event in events:
        event_type = event.get("type")
        reply_token = event.get("replyToken")
        source = event.get("source", {})
        user_id = source.get("userId")

        if event_type == "message":
            message = event.get("message", {})
            text = message.get("text", "").strip()

            if not text:
                continue

            if text.startswith("接"):
                student = find_student_by_parent_id(user_id)

                if not student:
                    student = find_student_by_text(text)

                if not student:
                    reply_to_line(
                        reply_token,
                        "系統找不到學生，請輸入：接＋學生姓名，例如：接賴灝宇"
                    )
                    continue

                student_name = get_student_name(student)

                item = add_pickup(student_name, user_id)

                # 1. 加入看板廣播佇列
                # 2. 通知老師群組
                notify_teacher_group(item)

                # 3. 回訊息給家長
                reply_to_line(
                    reply_token,
                    f"已收到 {student_name} 的接送通知，現場已同步廣播，請稍候老師回報。"
                )

        elif event_type == "postback":
            handle_teacher_postback(event)

    return "OK"


# ======================
# 看板 API
# ======================

@app.route("/api/pickup")
def api_pickup():
    new_items = []

    for item in pickup_queue:
        if not item.get("played"):
            new_items.append(item)
            item["played"] = True

    return jsonify(new_items)


@app.route("/api/queue")
def api_queue():
    return jsonify(pickup_queue[-30:])


# ======================
# 測試接送
# ======================

@app.route("/test-pickup")
def test_pickup():
    item = add_pickup("賴灝宇", "test_parent")
    notify_teacher_group(item)
    return "已送出測試接送：賴灝宇"


# ======================
# 廣播看板
# ======================

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
    font-family: Microsoft JhengHei, Arial, sans-serif;
    text-align: center;
    background: #fff7fb;
    margin: 0;
}

.header {
    background: #f58ab0;
    color: white;
    padding: 30px;
    font-size: 42px;
    font-weight: bold;
}

.sub {
    font-size: 24px;
    margin-top: 10px;
}

.enable {
    margin-top: 40px;
    padding: 24px 60px;
    font-size: 34px;
    background: #e8437c;
    color: white;
    border: none;
    border-radius: 18px;
    font-weight: bold;
}

.status {
    margin-top: 20px;
    font-size: 26px;
    color: #555;
}

.label {
    margin-top: 50px;
    font-size: 38px;
    color: #777;
}

.student {
    margin-top: 30px;
    font-size: 110px;
    color: #e8437c;
    font-weight: bold;
}

.time {
    font-size: 36px;
    margin-top: 15px;
    color: #555;
}

.record-title {
    margin-top: 60px;
    font-size: 32px;
    font-weight: bold;
}

.record {
    margin-top: 18px;
    font-size: 26px;
    color: #333;
}
</style>
</head>

<body>

<div class="header">
    皮克西美語 接送廣播看板
    <div class="sub">家長通知後，系統自動廣播三次</div>
</div>

<button class="enable" onclick="enableSound()">啟用廣播</button>

<div class="status" id="status">請先按「啟用廣播」</div>

<div class="label">目前接送學生</div>

<div class="student" id="student">等待通知</div>

<div class="time" id="time"></div>

<div class="record-title">最近接送紀錄</div>

<div id="records"></div>

<script>
let enabled = false;
let records = [];

function enableSound() {
    enabled = true;

    speechSynthesis.cancel();

    let u = new SpeechSynthesisUtterance("廣播已啟用");
    u.lang = "zh-TW";
    u.rate = 0.9;
    u.volume = 1;

    speechSynthesis.speak(u);

    document.getElementById("status").innerText = "廣播已啟用";
}

function speak(name) {
    if (!enabled) {
        document.getElementById("status").innerText = "請先按「啟用廣播」";
        return;
    }

    speechSynthesis.cancel();

    let text = name + "，家長到了，請準備放學";
    let count = 0;

    function speakOnce() {
        if (count >= 3) {
            return;
        }

        let u = new SpeechSynthesisUtterance(text);
        u.lang = "zh-TW";
        u.rate = 0.85;
        u.volume = 1;

        speechSynthesis.speak(u);

        count = count + 1;

        if (count < 3) {
            setTimeout(speakOnce, 2300);
        }
    }

    setTimeout(speakOnce, 200);
}

function renderRecords() {
    let box = document.getElementById("records");
    box.innerHTML = "";

    records.slice(0, 10).forEach(function(item) {
        let div = document.createElement("div");
        div.className = "record";
        div.innerText = item.time + "　" + item.student_name;
        box.appendChild(div);
    });
}

async function checkPickup() {
    try {
        let res = await fetch("/api/pickup?t=" + Date.now());
        let data = await res.json();

        if (data.length > 0) {
            data.forEach(function(item) {
                document.getElementById("student").innerText = item.student_name;
                document.getElementById("time").innerText = item.time;

                records.unshift(item);
                renderRecords();

                speak(item.student_name);
            });
        }
    } catch (e) {
        console.log(e);
    }
}

setInterval(checkPickup, 2000);
checkPickup();
</script>

</body>
</html>
"""


# ======================
# 首頁與版本
# ======================

@app.route("/")
def home():
    return "System Running"


@app.route("/version")
def version():
    return "PIXIE PICKUP FINAL SAFE VERSION: broadcast 3 times + teacher group + teacher reply + parent reply"


# ======================
# 啟動
# ======================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
