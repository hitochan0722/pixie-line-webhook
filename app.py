from flask import Flask, request

app = Flask(__name__)

@app.route("/", methods=["GET"])
def home():
    return "PiXiE LINE webhook is running."

@app.route("/callback", methods=["POST"])
def callback():
    data = request.get_json(silent=True) or {}

    print("收到 LINE 訊息：")
    print(data)

    events = data.get("events", [])

    for event in events:
        source = event.get("source", {})
        if source.get("type") == "group":
            group_id = source.get("groupId")
            print("====== LINE GROUP ID ======")
            print(group_id)
            print("===========================")

    return "OK", 200


@app.route("/webhook", methods=["POST"])
def webhook():
    return callback()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
