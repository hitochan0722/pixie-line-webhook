from flask import Flask, request, jsonify
import os
import csv
import requests
from datetime import datetime

app = Flask(__name__)

print("===== NEW VERSION WITH ENABLE BUTTON =====")

CHANNEL_ACCESS_TOKEN = os.getenv("CHANNEL_ACCESS_TOKEN")
TEACHER_GROUP_ID = os.getenv("TEACHER_GROUP_ID")

STUDENTS_FILE = "students.csv"

pickup_queue = []
pickup_records = {}

# ======================
# LINE 基本
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
        "messages": [{
            "type": "text",
            "text": text
        }]
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


# ======================
# 學生資料
# ======================

def load_students():

    students = []

    if not os.path.exists(STUDENTS_FILE):
        return students

    with open(
        STUDENTS_FILE,
        newline="",
        encoding="utf-8-sig"
    ) as f:

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
            or ""
        ).strip()

        if name in text:
            return s

    return None


def get_student_name(student):

    return (
        student.get("學生姓名")
        or student.get("student_name")
        or "學生"
    )


# ======================
# 接送邏輯
# ======================

def add_pickup(student_name, parent_id):

    now = datetime.now().strftime("%H:%M:%S")

    record_id = f"{student_name}_{datetime.now().strftime('%Y%m%d%H%M%S')}"

    item = {
        "id": record_id,
        "student_name": student_name,
        "parent_user_id": parent_id,
        "time": now,
        "played": False
    }

    pickup_queue.append(item)

    pickup_records[record_id] = item

    return item


def notify_teacher(item):

    student_name = item["student_name"]
    record_id = item["id"]

    message = {
        "type": "text",
        "text": f"📢 {student_name} 家長已到（已同步廣播）"
    }

    push_to_line(
        TEACHER_GROUP_ID,
        [message]
    )


# ======================
# webhook
# ======================

@app.route("/callback", methods=["POST"])
def callback():

    body = request.get_json()

    events = body.get("events", [])

    for event in events:

        if event["type"] == "message":

            text = event["message"]["text"]

            reply_token = event.get("replyToken")

            if text.startswith("接"):

                student = find_student_by_text(text)

                if not student:

                    reply_to_line(
                        reply_token,
                        "請輸入：接＋學生姓名"
                    )

                    continue

                name = get_student_name(student)

                item = add_pickup(name, "parent")

                notify_teacher(item)

                reply_to_line(
                    reply_token,
                    f"{name} 已廣播通知。"
                )

    return "OK"


# ======================
# API
# ======================

@app.route("/api/pickup")
def api_pickup():

    new_items = []

    for item in pickup_queue:

        if not item["played"]:

            new_items.append(item)

            item["played"] = True

    return jsonify(new_items)


# ======================
# 看板
# ======================

@app.route("/board")
def board():

    return """
<!DOCTYPE html>
<html>

<head>

<meta charset="UTF-8">

<title>接送廣播</title>

<style>

body{
font-family:Microsoft JhengHei;
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

</style>

</head>

<body>

<div class="header">

皮克西美語 接送廣播看板

</div>

<button class="enable" onclick="enableSound()">

啟用廣播

</button>

<div class="status" id="status">

請先按「啟用廣播」

</div>

<div class="student" id="student">

等待通知

</div>

<div class="time" id="time"></div>

<script>

let enabled=false;

function enableSound(){

enabled=true;

speechSynthesis.cancel();

let u=new SpeechSynthesisUtterance("廣播已啟用");

u.lang="zh-TW";

speechSynthesis.speak(u);

document.getElementById("status").innerText="廣播已啟用";

}

function speak(name){

if(!enabled)return;

speechSynthesis.cancel();

setTimeout(function(){

let u=new SpeechSynthesisUtterance(name+"，家長到了");

u.lang="zh-TW";

speechSynthesis.speak(u);

},200);

}

async function check(){

let r=await fetch("/api/pickup?t="+Date.now());

let data=await r.json();

if(data.length>0){

data.forEach(item=>{

document.getElementById("student").innerText=item.student_name;

document.getElementById("time").innerText=item.time;

speak(item.student_name);

});

}

}

setInterval(check,2000);

check();

</script>

</body>

</html>

"""


@app.route("/")
def home():

    return "System Running"


# ======================
# 啟動
# ======================

if __name__ == "__main__":

    port = int(os.environ.get("PORT", 5000))

    app.run(
        host="0.0.0.0",
        port=port
    )
