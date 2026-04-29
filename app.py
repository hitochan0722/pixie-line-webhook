from flask import Flask, request, jsonify
import os
import csv
import requests
from datetime import datetime

app = Flask(__name__)

print("===== PICKUP SYSTEM FINAL VERSION =====")

CHANNEL_ACCESS_TOKEN = os.getenv("CHANNEL_ACCESS_TOKEN")
TEACHER_GROUP_ID = os.getenv("TEACHER_GROUP_ID")
STUDENTS_FILE = "students.csv"

pickup_queue = []
pickup_records = {}


def line_headers():
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}"
    }


def reply_to_line(reply_token, text):
    if not reply_token:
        return

    requests.post(
        "https://api.line.me/v2/bot/message/reply",
        headers=line_headers(),
        json={
            "replyToken": reply_token,
            "messages": [{"type": "text", "text": text}]
        }
    )


def push_to_line(to, messages):
    if not to:
        print("沒有接收對象，push 取消")
        return

    res = requests.post(
        "https://api.line.me/v2/bot/message/push",
        headers=line_headers(),
        json={
            "to": to,
            "messages": messages
        }
    )

    print("LINE PUSH STATUS:", res.status_code)
    print("LINE PUSH RESPONSE:", res.text)


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


def notify_teacher(item):
    student_name = item["student_name"]
    record_id = item["id"]

    print("TEACHER_GROUP_ID =", TEACHER_GROUP_ID)

    if not TEACHER_GROUP_ID:
        print("沒有 TEACHER_GROUP_ID，無法通知老師群組")
        return

    message = {
        "type": "template",
        "altText": f"{student_name} 接送通知",
        "template": {
            "type": "buttons",
            "title": "接送通知",
            "text": f"{student_name} 家長已到\n廣播已播放，請老師確認狀態",
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

    student = item["student_name"]
    parent = item["parent_user_id"]

    if action == "packing":
        msg = f"{student} 正在收拾書包。"
    elif action == "wait":
        msg = f"{student} 約 5–10 分鐘後下樓。"
    elif action == "downstairs":
        msg = f"{student} 已經下樓囉。"
    elif action == "cancel":
        msg = f"{student} 接送已取消。"
    else:
        msg = f"{student} 狀態已更新。"

    push_to_line(parent, [{"type": "text", "text": msg}])
    reply_to_line(reply_token, f"已通知家長：{msg}")


@app.route("/callback", methods=["POST"])
def callback():
    body = request.get_json()
    print("CALLBACK BODY:", body)

    events = body.get("events", [])

    for event in events:
        event_type = event.get("type")
        source = event.get("source", {})
        user_id = source.get("userId")
        reply_token = event.get("replyToken")

        if event_type == "message":
            message = event.get("message", {})
            text = message.get("text", "").strip()

            if text.startswith("接"):
                student = find_student_by_text(text)

                if not student:
                    reply_to_line(reply_token, "請輸入：接＋學生姓名，例如：接賴灝宇")
                    continue

                name = get_student_name(student)

                item = add_pickup(name, user_id)

                notify_teacher(item)

                reply_to_line(reply_token, f"{name} 已廣播通知。")

        elif event_type == "postback":
            handle_teacher_postback(event)

    return "OK"


@app.route("/api/pickup")
def api_pickup():
    new_items = []

    for item in pickup_queue:
        if not item["played"]:
            new_items.append(item)
            item["played"] = True

    return jsonify(new_items)


@app.route("/board")
def board():
    return """
<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="UTF-8">
<title>皮克西美語 接送廣播看板</title>

<style>
body{
    font-family: Microsoft JhengHei, Arial, sans-serif;
    text-align:center;
    background:#fff7fb;
    margin:0;
}
.header{
    background:#f58ab0;
    color:white;
    padding:30px;
    font-size:42px;
    font-weight:bold;
}
.sub{
    font-size:24px;
    margin-top:10px;
}
.enable{
    margin-top:40px;
    padding:24px 60px;
    font-size:34px;
    background:#e8437c;
    color:white;
    border:none;
    border-radius:18px;
    font-weight:bold;
}
.student{
    margin-top:40px;
    font-size:110px;
    color:#e8437c;
    font-weight:bold;
}
.time{
    font-size:36px;
    margin-top:15px;
    color:#555;
}
.status{
    margin-top:20px;
    font-size:24px;
    color:#555;
}
.record-title{
    margin-top:60px;
    font-size:32px;
    font-weight:bold;
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

<div class="student" id="student">等待通知</div>

<div class="time" id="time"></div>

<div class="record-title">最近接送紀錄</div>

<script>
let enabled = false;

function enableSound(){
    enabled = true;

    speechSynthesis.cancel();

    let u = new SpeechSynthesisUtterance("廣播已啟用");
    u.lang = "zh-TW";
    u.rate = 0.9;
    u.volume = 1;

    speechSynthesis.speak(u);

    document.getElementById("status").innerText = "廣播已啟用";
}

function speak(name){
    if(!enabled){
        document.getElementById("status").innerText = "請先按「啟用廣播」";
        return;
    }

    speechSynthesis.cancel();

    let text = name + "，家長到了";
    let count = 0;

    function speakOnce(){
        if(count >= 3) return;

        let u = new SpeechSynthesisUtterance(text);
        u.lang = "zh-TW";
        u.rate = 0.85;
        u.volume = 1;

        speechSynthesis.speak(u);

        count++;

        if(count < 3){
            setTimeout(speakOnce, 2200);
        }
    }

    setTimeout(speakOnce, 200);
}

async function check(){
    try{
        let r = await fetch("/api/pickup?t=" + Date.now());
        let data = await r.json();

        if(data.length > 0){
            data.forEach(item => {
                document.getElementById("student").innerText = item.student_name;
                document.getElementById("time").innerText = item.time;
                speak(item.student_name);
            });
        }
    }catch(e){
        console.log(e);
    }
}

setInterval(check, 2000);
check();
</script>

</body>
</html>
"""


@app.route("/")
def home():
    return "System Running"


@app.route("/version")
def version():
    return "FINAL PICKUP VERSION - ENABLE BUTTON - SPEAK THREE TIMES - TEACHER GROUP NOTICE"


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
