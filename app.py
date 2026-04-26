from flask import Flask, request
import json

app = Flask(__name__)

@app.route("/", methods=["GET"])
def home():
    return "PiXiE LINE webhook is running."

@app.route("/webhook", methods=["POST"])
def webhook():

    data = request.get_json(silent=True)

    print("====== 收到完整 LINE 資料 ======")
    print(json.dumps(data, indent=2, ensure_ascii=False))
    print("================================")

    try:
        events = data.get("events", [])

        for event in events:

            source = event.get("source", {})

            if source.get("type") == "group":

                group_id = source.get("groupId")

                print("====== GROUP ID ======")
                print(group_id)
                print("======================")

    except Exception as e:
        print("Error:", str(e))

    return "OK", 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
