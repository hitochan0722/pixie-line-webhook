from flask import Flask, request, jsonify, render_template
import os, csv, requests
from datetime import datetime

app = Flask(__name__)

CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN") or os.getenv("CHANNEL_ACCESS_TOKEN")
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
        json={"replyToken": reply_token, "messages": [{"type": "text", "text": text}]}
    )

def push_to_line(to, messages):
    if not to:
        print("NO PUSH TARGET")
        return
    res = requests.post(
        "https://api.line.me/v2/bot/message/push",
        headers=line_headers(),
        json={"to": to, "messages": messages}
    )
    print("PUSH STATUS:", res.status_code)
    print("PUSH RESPONSE:", res.text)

def load_students():
    if not os.path.exists(STUDENTS_FILE):
        print("students.csv not found")
        return []

    with open(STUDENTS_FILE, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))

def get_student_name(student):
    return (
        student.get("學生姓名")
        or student.get("student_name")
        or student.get("姓名")
        or ""
    ).strip()

def find_student(text, user_id):
    students = load_students()

    for s in students:
        name = get_student_name(s)
        parent_id = (
            s.get("parent_user_id")
            or s.get("家長LINE_ID")
            or s.get("家長LINE ID")
            or s.get("line_user_id")
            or ""
        ).strip()

        if parent_id and parent_id == user_id:
            return s

        if name and name in text:
            return s

    return None

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
    if not TEACHER_GROUP_ID:
        print("NO TEACHER_GROUP_ID")
        return

    student_name = item["student_name"]
    record_id = item["id"]

    message = {
        "type": "template",
        "altText": f"{student_name} 接送通知",
        "template": {
            "type": "buttons",
            "title": "接送通知",
            "text": f"{student_name} 家長已到\n系統已自動廣播3次",
            "actions": [
                {"type": "postback", "label": "收拾書包", "data": f"action=packing&id={record_id}"},
                {"type": "postback", "label": "5–10分鐘", "data": f"action=wait&id={record_id}"},
                {"type": "postback", "label": "已下樓", "data": f"action=down&id={record_id}"},
                {"type": "postback", "label": "取消", "data": f"action=cancel&id={record_id}"}
            ]
        }
    }

    push_to_line(TEACHER_GROUP_ID, [message])

def handle_postback(event):
    reply_token = event.get("replyToken")
    data = event.get("postback", {}).get("data", "")

    params = {}
    for p in data.split("&"):
        if "=" in p:
            k, v = p.split("=", 1)
            params[k] = v

    record_id = params.get("id")
    action = params.get("action")

    item = pickup_records.get(record_id)

    if not item:
        reply_to_line(reply_token, "找不到這筆接送資料，可能系統重新啟動過。")
        return

    student_name = item["student_name"]
    parent_id = item["parent_user_id"]

    if action == "packing":
        msg = f"{student_name} 正在收拾書包，請稍候一下。"
    elif action == "wait":
        msg = f"{student_name} 約 5–10 分鐘後下樓，請稍候。"
    elif action == "down":
        msg = f"{student_name} 已經下樓囉。"
    elif action == "cancel":
        msg = f"{student_name} 的接送通知已取消。"
    else:
        msg = f"{student_name} 狀態已更新。"

    push_to_line(parent_id, [{"type": "text", "text": msg}])
    reply_to_line(reply_token, f"已通知家長：{msg}")

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
        group_id = source.get("groupId")

        if event_type == "message":
            message = event.get("message", {})
            text = message.get("text", "").strip()

            if text == "查群組ID":
                if group_id:
                    reply_to_line(reply_token, f"這個群組ID是：{group_id}")
                else:
                    reply_to_line(reply_token, "這不是群組訊息，抓不到群組ID。")
                continue

            if text.startswith("接"):
                student = find_student(text, user_id)

                if not student:
                    reply_to_line(reply_token, "系統找不到學生，請輸入：接＋學生姓名，例如：接賴灝宇")
                    continue

                student_name = get_student_name(student)
                item = add_pickup(student_name, user_id)

                notify_teacher(item)

                reply_to_line(
                    reply_token,
                    f"已收到 {student_name} 的接送通知，現場已同步廣播，請稍候老師回報。"
                )

        elif event_type == "postback":
            handle_postback(event)

    return "OK"
@app.route("/api/students")
def api_students():
    names = []

    for s in load_students():
        name = get_student_name(s)
        if name:
            names.append(name)

    return jsonify(names)
@app.route("/api/pickup")
def api_pickup():
    new_items = []

    for item in pickup_queue:
        if not item.get("played"):
            new_items.append(item)
            item["played"] = True

    return jsonify(new_items)
@app.route("/api/send-pickup", methods=["POST"])
def api_send_pickup():
    data = request.get_json() or {}
    student_name = (data.get("student_name") or "").strip()
    parent_user_id = (data.get("parent_user_id") or "parent_portal").strip()

    if not student_name:
        return jsonify({
            "ok": False,
            "message": "請輸入學生姓名"
        }), 400

    item = add_pickup(student_name, parent_user_id)
    notify_teacher(item)

    return jsonify({
        "ok": True,
        "message": f"已收到 {student_name} 的接送通知，已同步通知老師與看板。"
    })
@app.route("/test-pickup")
def test_pickup():
    item = add_pickup("賴灝宇", "test_parent")
    notify_teacher(item)
    return "TEST PICKUP OK"

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
        if (count >= 3) return;

        let u = new SpeechSynthesisUtterance(text);
        u.lang = "zh-TW";
        u.rate = 0.85;
        u.volume = 1;
        speechSynthesis.speak(u);

        count += 1;

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
    } catch(e) {
        console.log(e);
    }
}

setInterval(checkPickup, 2000);
checkPickup();
</script>

</body>
</html>
"""
@app.route("/parent")
def parent_page():
    return render_template("parent.html")

@app.route("/new")
def new_page():
    return render_template("new.html")

@app.route("/parent/pickup")
def parent_pickup_page():
    return render_template("pickup.html")

@app.route("/parent/leave")
def parent_leave_page():
    return render_template("leave.html")

@app.route("/parent/attendance")
def parent_attendance_page():
    return render_template("attendance.html")

@app.route("/contact")
def contact_page():
    return render_template("contact.html")
@app.route("/")
def home():
    return "PIXIE PICKUP SYSTEM RUNNING"
@app.route("/")
def home():
    return "PIXIE PICKUP SYSTEM RUNNING"


@app.route("/new-student")
def new_student():
    return render_template("new-student.html")


@app.route("/version")
def version():
    return "PIXIE PICKUP EMBEDDED BOARD VERSION"


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
