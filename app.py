from flask import Flask, request, jsonify, render_template
import csv
import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests


app = Flask(__name__)

CHANNEL_ACCESS_TOKEN = (
    os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
    or os.getenv("CHANNEL_ACCESS_TOKEN")
    or ""
)
TEACHER_GROUP_ID = os.getenv("TEACHER_GROUP_ID") or ""
STUDENT_GAS_URL = os.getenv("STUDENT_GAS_URL") or ""
NEW_STUDENT_GAS_URL = os.getenv("NEW_STUDENT_GAS_URL") or STUDENT_GAS_URL
STUDENTS_FILE = "students.csv"

pickup_queue: List[Dict[str, Any]] = []
pickup_records: Dict[str, Dict[str, Any]] = {}


# ======================================================
# 共用工具
# ======================================================

def clean(value: Any) -> str:
    return str(value or "").strip()


def student_id_of(student: Dict[str, Any]) -> str:
    return clean(
        student.get("student_id")
        or student.get("學生ID")
        or student.get("學生代碼")
    )


def student_name_of(student: Dict[str, Any]) -> str:
    return clean(
        student.get("學生姓名")
        or student.get("student_name")
        or student.get("name")
    )


def student_payload(student: Dict[str, Any]) -> Dict[str, str]:
    return {
        "student_id": student_id_of(student),
        "student_name": student_name_of(student),
        "english_name": clean(
            student.get("英文姓名") or student.get("english_name")
        ),
        "grade": clean(student.get("年級") or student.get("grade")),
        "class_name": clean(student.get("班級") or student.get("class_name")),
    }


def line_headers() -> Dict[str, str]:
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}",
    }


def reply_to_line(reply_token: str, text: str) -> bool:
    if not reply_token or not CHANNEL_ACCESS_TOKEN:
        return False

    try:
        response = requests.post(
            "https://api.line.me/v2/bot/message/reply",
            headers=line_headers(),
            json={
                "replyToken": reply_token,
                "messages": [{"type": "text", "text": text}],
            },
            timeout=15,
        )
        print("LINE reply status:", response.status_code, response.text)
        return response.ok
    except Exception as error:
        print("LINE reply failed:", error)
        return False


def push_to_line(to: str, messages: List[Dict[str, Any]]) -> bool:
    if not to:
        print("沒有推播對象，無法推送 LINE")
        return False

    if not CHANNEL_ACCESS_TOKEN:
        print("沒有 LINE CHANNEL ACCESS TOKEN，無法推送 LINE")
        return False

    try:
        response = requests.post(
            "https://api.line.me/v2/bot/message/push",
            headers=line_headers(),
            json={"to": to, "messages": messages},
            timeout=15,
        )
        print("LINE push status:", response.status_code, response.text)
        return response.ok
    except Exception as error:
        print("LINE push failed:", error)
        return False


# ======================================================
# students.csv
# ======================================================

def load_students() -> List[Dict[str, str]]:
    if not os.path.exists(STUDENTS_FILE):
        print("找不到 students.csv")
        return []

    with open(
        STUDENTS_FILE,
        newline="",
        encoding="utf-8-sig",
    ) as file:
        return list(csv.DictReader(file))


def save_students(students: List[Dict[str, str]]) -> None:
    fieldnames = [
        "student_id",
        "學生姓名",
        "英文姓名",
        "年級",
        "班級",
        "家長ID1",
        "家長ID2",
        "家長姓名",
        "家長LINE名稱",
        "接送方式",
        "備註",
    ]

    with open(
        STUDENTS_FILE,
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames,
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(students)


def find_local_student_by_id(student_id: str) -> Optional[Dict[str, str]]:
    target = clean(student_id)
    for student in load_students():
        if student_id_of(student) == target:
            return student
    return None


def find_student(text: str, user_id: str) -> Optional[Dict[str, str]]:
    message_text = clean(text)
    line_user_id = clean(user_id)

    for student in load_students():
        name = student_name_of(student)
        parent_id_1 = clean(student.get("家長ID1"))
        parent_id_2 = clean(student.get("家長ID2"))

        if line_user_id and line_user_id in (parent_id_1, parent_id_2):
            return student

        if name and name in message_text:
            return student

    return None


# ======================================================
# Apps Script 溝通
# ======================================================

def parse_apps_script_response(response_text: str) -> Dict[str, Any]:
    text = clean(response_text)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    first_parenthesis = text.find("(")
    last_parenthesis = text.rfind(")")

    if first_parenthesis >= 0 and last_parenthesis > first_parenthesis:
        json_text = text[first_parenthesis + 1:last_parenthesis]
        return json.loads(json_text)

    raise ValueError("無法解析 Apps Script 回傳內容")


def gas_get(params: Dict[str, Any]) -> Dict[str, Any]:
    if not STUDENT_GAS_URL:
        raise RuntimeError("沒有設定 STUDENT_GAS_URL")

    response = requests.get(
        STUDENT_GAS_URL,
        params=params,
        timeout=15,
    )
    response.raise_for_status()
    return parse_apps_script_response(response.text)


def gas_post(payload: Dict[str, Any], url: Optional[str] = None) -> Dict[str, Any]:
    target_url = url or STUDENT_GAS_URL

    if not target_url:
        raise RuntimeError("沒有設定 Apps Script URL")

    response = requests.post(
        target_url,
        json=payload,
        timeout=15,
    )
    response.raise_for_status()
    return parse_apps_script_response(response.text)


def update_student_binding_to_sheet(
    student_id: str,
    line_user_id: str,
    display_name: str = "",
) -> Dict[str, Any]:
    payload = {
        "form_type": "bind_student",
        "student_id": clean(student_id),
        "line_user_id": clean(line_user_id),
        "line_display_name": clean(display_name),
    }

    try:
        result = gas_post(payload)
        print("綁定寫入 Sheet result:", result)
        return result
    except Exception as error:
        print("綁定寫入 Sheet 失敗:", error)
        return {
            "status": "error",
            "message": str(error),
        }


def lookup_parent_students_from_sheet(
    line_user_id: str,
) -> List[Dict[str, str]]:
    result = gas_get({
        "action": "lookup",
        "userId": clean(line_user_id),
        "callback": "pixieCallback",
    })

    if result.get("status") != "ok":
        raise RuntimeError(
            result.get("message") or "Apps Script 查詢失敗"
        )

    students = result.get("students") or []
    return [student_payload(student) for student in students]


# ======================================================
# 接送系統
# ======================================================

def add_pickup(
    student_name: str,
    parent_user_id: str,
) -> Dict[str, Any]:
    now = datetime.now()
    record_id = (
        f"{student_name}_{now.strftime('%Y%m%d%H%M%S%f')}"
    )

    item = {
        "id": record_id,
        "student_name": student_name,
        "parent_user_id": parent_user_id,
        "time": now.strftime("%H:%M:%S"),
        "played": False,
    }

    pickup_queue.append(item)
    pickup_records[record_id] = item
    return item


def notify_teacher(item: Dict[str, Any]) -> None:
    student_name = item["student_name"]
    record_id = item["id"]

    message = {
        "type": "template",
        "altText": f"{student_name} 接送通知",
        "template": {
            "type": "buttons",
            "title": "接送通知",
            "text": f"{student_name} 家長已到",
            "actions": [
                {
                    "type": "postback",
                    "label": "收拾書包",
                    "data": f"action=packing&id={record_id}",
                },
                {
                    "type": "postback",
                    "label": "5–10分鐘",
                    "data": f"action=wait&id={record_id}",
                },
                {
                    "type": "postback",
                    "label": "已下樓",
                    "data": f"action=down&id={record_id}",
                },
                {
                    "type": "postback",
                    "label": "取消",
                    "data": f"action=cancel&id={record_id}",
                },
            ],
        },
    }

    push_to_line(TEACHER_GROUP_ID, [message])


def handle_pickup_postback(event: Dict[str, Any]) -> None:
    postback_data = clean(
        (event.get("postback") or {}).get("data")
    )
    reply_token = clean(event.get("replyToken"))

    values: Dict[str, str] = {}
    for part in postback_data.split("&"):
        if "=" in part:
            key, value = part.split("=", 1)
            values[key] = value

    action = values.get("action", "")
    record_id = values.get("id", "")
    item = pickup_records.get(record_id)

    if not item:
        reply_to_line(reply_token, "找不到接送紀錄，可能已失效。")
        return

    replies = {
        "packing": "孩子正在收拾書包，請稍候。",
        "wait": "孩子約 5–10 分鐘後下樓。",
        "down": "孩子已下樓，請留意。",
        "cancel": "本次接送通知已取消。",
    }

    parent_message = replies.get(action)
    if not parent_message:
        reply_to_line(reply_token, "無法辨識此操作。")
        return

    parent_user_id = clean(item.get("parent_user_id"))
    student_name = clean(item.get("student_name"))

    if parent_user_id:
        push_to_line(
            parent_user_id,
            [{
                "type": "text",
                "text": f"【皮克西接送通知】\n{student_name}：{parent_message}",
            }],
        )

    reply_to_line(
        reply_token,
        f"{student_name}：{parent_message}",
    )

    if action in ("down", "cancel"):
        pickup_records.pop(record_id, None)


# ======================================================
# LINE Webhook
# ======================================================

@app.route("/callback", methods=["POST"])
def callback():
    body = request.get_json(silent=True) or {}
    events = body.get("events") or []

    for event in events:
        event_type = clean(event.get("type"))
        reply_token = clean(event.get("replyToken"))
        source = event.get("source") or {}
        user_id = clean(source.get("userId"))

        if event_type == "message":
            message = event.get("message") or {}
            text = clean(message.get("text"))

            if text.startswith("接"):
                student = find_student(text, user_id)

                if not student:
                    reply_to_line(
                        reply_token,
                        "請輸入：接＋學生姓名",
                    )
                    continue

                student_name = student_name_of(student)
                item = add_pickup(student_name, user_id)
                notify_teacher(item)
                reply_to_line(
                    reply_token,
                    f"已收到 {student_name} 接送通知",
                )

        elif event_type == "postback":
            handle_pickup_postback(event)

    return "OK"


# ======================================================
# API：學生及家長
# ======================================================

@app.route("/api/bind-student")
def api_bind_student():
    student_id = clean(request.args.get("student_id"))

    if not student_id:
        return jsonify({
            "ok": False,
            "message": "缺少學生代碼。",
        }), 400

    try:
        result = gas_get({
            "action": "student",
            "student_id": student_id,
            "callback": "pixieCallback",
        })

        if result.get("status") == "ok" and result.get("student"):
            student = student_payload(result["student"])
            return jsonify({
                "ok": True,
                **student,
            })
    except Exception as error:
        print("Google Sheet 查詢學生失敗，改用 CSV：", error)

    student = find_local_student_by_id(student_id)

    if student:
        return jsonify({
            "ok": True,
            **student_payload(student),
        })

    return jsonify({
        "ok": False,
        "message": "找不到學生資料，請聯絡老師。",
    })


@app.route("/api/bind-confirm", methods=["POST"])
def api_bind_confirm():
    data = request.get_json(silent=True) or {}

    student_id = clean(
        data.get("student_id")
        or data.get("bind")
        or data.get("student")
    )
    line_user_id = clean(
        data.get("line_user_id")
        or data.get("userId")
    )
    display_name = clean(
        data.get("line_display_name")
        or data.get("displayName")
    )

    if not student_id:
        return jsonify({
            "ok": False,
            "message": "缺少學生代碼，請重新開啟連結。",
        }), 400

    if not line_user_id:
        return jsonify({
            "ok": False,
            "message": "無法取得 LINE 身分，請用 LINE 開啟連結。",
        }), 400

    result = update_student_binding_to_sheet(
        student_id,
        line_user_id,
        display_name,
    )

    if result.get("status") == "ok":
        message = result.get("message_zh") or "綁定成功！"
        return jsonify({
            "ok": True,
            "message": message,
            "slot": result.get("slot"),
            "student": result.get("student"),
        })

    return jsonify({
        "ok": False,
        "message": result.get("message") or "綁定失敗，請聯絡老師。",
    }), 400


@app.route("/api/parent-student")
def api_parent_student():
    line_user_id = clean(
        request.args.get("line_user_id")
        or request.args.get("userId")
    )

    if not line_user_id:
        return jsonify({
            "ok": False,
            "students": [],
            "message": "缺少 LINE User ID",
        }), 400

    try:
        students = lookup_parent_students_from_sheet(line_user_id)
        return jsonify({
            "ok": True,
            "students": students,
        })
    except Exception as error:
        print("Google Sheet 查詢家長資料失敗，改用 CSV：", error)

    matched_students = []
    for student in load_students():
        parent_id_1 = clean(student.get("家長ID1"))
        parent_id_2 = clean(student.get("家長ID2"))

        if line_user_id in (parent_id_1, parent_id_2):
            matched_students.append(student_payload(student))

    return jsonify({
        "ok": True,
        "students": matched_students,
    })



@app.route("/api/parent-leave", methods=["POST"])
def api_parent_leave():
    data = request.get_json(silent=True) or {}

    line_user_id = clean(data.get("line_user_id") or data.get("userId"))
    student_id = clean(data.get("student_id") or data.get("studentId"))
    leave_date = clean(data.get("date") or data.get("leave_date"))
    leave_type = clean(data.get("type") or data.get("leave_type"))
    reason = clean(data.get("reason"))
    display_name = clean(data.get("line_display_name") or data.get("displayName"))

    if not line_user_id:
        return jsonify({"ok": False, "message": "無法取得 LINE 家長身分。"}), 400
    if not student_id:
        return jsonify({"ok": False, "message": "請選擇學生。"}), 400
    if not leave_date:
        return jsonify({"ok": False, "message": "請選擇請假日期。"}), 400
    if not leave_type:
        return jsonify({"ok": False, "message": "請選擇請假類型。"}), 400

    try:
        students = lookup_parent_students_from_sheet(line_user_id)
    except Exception as error:
        print("請假前查詢綁定資料失敗：", error)
        return jsonify({"ok": False, "message": "目前無法確認家長身分，請稍後再試。"}), 500

    student = next(
        (item for item in students if clean(item.get("student_id")) == student_id),
        None,
    )
    if not student:
        return jsonify({"ok": False, "message": "此 LINE 帳號未綁定該學生。"}), 403

    payload = {
        "form_type": "leave",
        "student_id": student_id,
        "name": clean(student.get("student_name")),
        "english_name": clean(student.get("english_name")),
        "class_name": clean(student.get("class_name")),
        "date": leave_date,
        "type": leave_type,
        "reason": reason,
        "line_user_id": line_user_id,
        "line_display_name": display_name,
    }

    try:
        result = gas_post(payload)
    except Exception as error:
        print("請假資料寫入失敗：", error)
        return jsonify({"ok": False, "message": "請假資料送出失敗，請稍後再試。"}), 500

    if result.get("status") == "ok":
        return jsonify({
            "ok": True,
            "message": result.get("message_zh") or "請假申請已送出。",
        })

    return jsonify({
        "ok": False,
        "message": result.get("message") or "請假申請送出失敗。",
    }), 400


@app.route("/api/parent-pickup", methods=["POST"])
def api_parent_pickup():
    data = request.get_json(silent=True) or {}

    line_user_id = clean(data.get("line_user_id") or data.get("userId"))
    student_id = clean(data.get("student_id") or data.get("studentId"))
    display_name = clean(data.get("line_display_name") or data.get("displayName"))

    if not line_user_id:
        return jsonify({"ok": False, "message": "無法取得 LINE 家長身分。"}), 400
    if not student_id:
        return jsonify({"ok": False, "message": "請選擇學生。"}), 400

    try:
        students = lookup_parent_students_from_sheet(line_user_id)
    except Exception as error:
        print("接送前查詢綁定資料失敗：", error)
        return jsonify({"ok": False, "message": "目前無法確認家長身分，請稍後再試。"}), 500

    student = next(
        (item for item in students if clean(item.get("student_id")) == student_id),
        None,
    )
    if not student:
        return jsonify({"ok": False, "message": "此 LINE 帳號未綁定該學生。"}), 403

    payload = {
        "form_type": "pickup",
        "student_id": student_id,
        "name": clean(student.get("student_name")),
        "english_name": clean(student.get("english_name")),
        "class_name": clean(student.get("class_name")),
        "parent_user_id": line_user_id,
        "parent_name": display_name,
        "status": "待處理",
    }

    try:
        result = gas_post(payload)
    except Exception as error:
        print("接送資料寫入失敗：", error)
        return jsonify({"ok": False, "message": "接送通知送出失敗，請稍後再試。"}), 500

    if result.get("status") == "ok":
        return jsonify({
            "ok": True,
            "message": result.get("message_zh") or "接送通知已送出。",
        })

    return jsonify({
        "ok": False,
        "message": result.get("message") or "接送通知送出失敗。",
    }), 400


@app.route("/api/debug-student")
def api_debug_student():
    student_id = clean(request.args.get("student_id"))

    try:
        result = gas_get({
            "action": "student",
            "student_id": student_id,
            "callback": "pixieCallback",
        })
        return jsonify(result)
    except Exception as error:
        student = find_local_student_by_id(student_id)

        if student:
            return jsonify(student)

        return jsonify({
            "ok": False,
            "message": f"找不到學生：{error}",
        }), 404


# ======================================================
# API：接送看板
# ======================================================

@app.route("/api/pickup")
def api_pickup():
    new_items = []

    for item in pickup_queue:
        if not item.get("played"):
            new_items.append(item)
            item["played"] = True

    return jsonify(new_items)


# ======================================================
# 頁面 Routes
# ======================================================

@app.route("/")
def home():
    return render_template("index.html")


@app.route("/parent")
def parent_page():
    return render_template("parent.html")


@app.route("/new-parent")
def new_parent_page():
    return render_template("new-parent.html")


@app.route("/bind")
def bind_page():
    return render_template("bind.html")


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


@app.route("/parent/new-student")
def parent_new_student_page():
    return render_template("new-student.html")


# ======================================================
# 新生問班送出
# ======================================================

@app.route("/parent/new-student-submit", methods=["POST"])
def parent_new_student_submit():
    student_name = clean(request.form.get("student_name"))
    school = clean(request.form.get("school"))
    learning_experience = clean(
        request.form.get("learning_experience")
    )
    parent_name = clean(request.form.get("parent_name"))
    phone = clean(request.form.get("phone"))

    data = {
        "form_type": "new_student",
        "student_name": student_name,
        "school": school,
        "learning_experience": learning_experience,
        "parent_name": parent_name,
        "phone": phone,
        "source": "新生入口",
        "created_at": datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        ),
    }

    if NEW_STUDENT_GAS_URL:
        try:
            result = gas_post(data, NEW_STUDENT_GAS_URL)
            print("新生 Sheet result:", result)
        except Exception as error:
            print("新生 Sheet 寫入失敗:", error)
    else:
        print("沒有設定 NEW_STUDENT_GAS_URL，所以沒有寫入 Sheet")

    message = (
        "📢【皮克西｜新生問班】\n\n"
        f"學生姓名：{student_name}\n"
        f"就讀學校：{school}\n"
        f"學習經歷：{learning_experience}\n"
        f"家長姓名：{parent_name}\n"
        f"電話：{phone}"
    )

    push_to_line(
        TEACHER_GROUP_ID,
        [{"type": "text", "text": message}],
    )

    return """
    <html>
      <head>
        <meta charset="UTF-8">
        <meta name="viewport"
              content="width=device-width, initial-scale=1.0">
        <title>資料已送出</title>
      </head>
      <body style="
        font-family:'Microsoft JhengHei',Arial;
        text-align:center;
        padding:40px;
        background:#fff7ef;
      ">
        <div style="
          background:white;
          border-radius:22px;
          padding:30px 20px;
          max-width:480px;
          margin:0 auto;
          box-shadow:0 8px 24px rgba(0,0,0,0.08);
        ">
          <h2 style="color:#e28a4f;">資料已送出</h2>
          <p style="font-size:18px;line-height:1.7;">
            謝謝您填寫問班資料，老師會盡快與您聯繫。
          </p>
          <a href="/new-parent" style="
            display:inline-block;
            margin-top:18px;
            background:#e28a4f;
            color:white;
            padding:12px 22px;
            border-radius:16px;
            text-decoration:none;
            font-weight:bold;
          ">回新生專區</a>
        </div>
      </body>
    </html>
    """


@app.route("/version")
def version():
    return (
        "PIXIE PARENT LOOKUP + PICKUP + NEW STUDENT + "
        "BIND + SHEET SYNC VERSION 2026-07-11"
    )


@app.route("/health")
def health():
    return jsonify({
        "ok": True,
        "student_gas_url": bool(STUDENT_GAS_URL),
        "new_student_gas_url": bool(NEW_STUDENT_GAS_URL),
        "line_token": bool(CHANNEL_ACCESS_TOKEN),
        "teacher_group_id": bool(TEACHER_GROUP_ID),
        "time": datetime.now().isoformat(),
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(
        host="0.0.0.0",
        port=port,
    )
