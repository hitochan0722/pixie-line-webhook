from flask import Flask, request, jsonify
import os
import csv
import requests
from datetime import datetime

app = Flask(__name__)

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

    with open(STUDENTS_FILE,
              newline="",
              encoding="utf-8-sig") as f:

        reader = csv.DictReader(f)

        for row in reader:
            students.append(row)

    return students


def find_student_by_parent(user_id):

    students = load_students()

    for s in students:

        pid = (
            s.get("parent_user_id")
            or s.get("家長LINE_ID")
            or s.get("line_user_id")
            or ""
        ).strip()

        if pid == user_id:
            return s

    return None


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
        "type": "template",
        "altText": "接送通知",
        "template": {
            "type": "buttons",
            "title": "接送通知",
            "text": f"{student_name} 家長已到\n已同步廣播",
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

    push_to_line(
        TEACHER_GROUP_ID,
        [message]
    )


def handle_teacher_postback(event):

    data = event["postback"]["data"]

    reply_token = event["replyToken"]

    params = {}

    for part in data.split("&"):

        if "=" in part:
            k, v = part.split("=")
            params[k] = v

    action = params.get("action")
    rid = params.get("id")

    item = pickup_records.get(rid)

    if not item:
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

    push_to_line(parent, [{
        "type": "text",
        "text": msg
    }])

    reply_to_line(
        reply_token,
        f"已通知家長：{msg}"
    )


# ======================
# webhook
# ======================

@app.route("/callback", methods=["POST"])
def callback():

    body = request.get_json()

    events = body.get("events", [])

    for event in events:

        etype = event["type"]

        source = event["source"]

        user_id = source.get("userId")

        reply_token = event.get("replyToken")

        if etype == "message":

            text = event["message"]["text"]

            if text.startswith("接"):

                student = find_student_by_parent(user_id)

                if not student:
                    student = find_student_by_text(text)

                if not student:

                    reply_to_line(
                        reply_token,
                        "請輸入：接＋學生姓名"
                    )

                    continue

                name = get_student_name(student)

                item = add_pickup(name, user_id)

                notify_teacher(item)

                reply_to_line(
                    reply_token,
                    f"{name} 已廣播通知老師。"
                )

        elif etype == "postback":

            handle_teacher_postback(event)

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

<title>接送看板</title>

<style>

body {

font-family: Microsoft JhengHei;

text-align: center;

background: #fff7fb;

}

.student {

font-size: 90px;

margin-top: 30px;

color: #e8437c;

}

.enable {

font-size: 30px;

padding: 20px 40px;

background: #e8437c;

color: white;

border: none;

border-radius: 12px;

}

</style>

</head>

<body>

<h1>皮克西美語 接送廣播</h1>

<button class="enable" onclick="enableSound()">

啟用廣播

</button>

<div id="student" class="student">

等待通知

</div>

<script>

let enabled=false;

function enableSound(){

enabled=true;

let u=new SpeechSynthesisUtterance("廣播啟用");

u.lang="zh-TW";

speechSynthesis.speak(u);

}

function speak(name){

if(!enabled)return;

let text=name+"，家長到了";

let u=new SpeechSynthesisUtterance(text);

u.lang="zh-TW";

speechSynthesis.cancel();

speechSynthesis.speak(u);

}

async function check(){

let r=await fetch("/api/pickup");

let data=await r.json();

if(data.length>0){

data.forEach(item=>{

document.getElementById("student").innerText=item.student_name;

speak(item.student_name);

});

}

}

setInterval(check,2000);

</script>

</body>

</html>

"""


@app.route("/")
def home():

    return "System Running"
