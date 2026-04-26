        # 老師狀態回覆
        if text in ["1", "2", "3", "4", "5"]:

            status_map = {
                "1": "家長您好，孩子正在收拾書包中。",
                "2": "家長您好，孩子作業尚未完成，還需約 5–10 分鐘。",
                "3": "家長您好，孩子已準備下樓。",
                "4": "家長您好，老師正在確認學生狀態。",
                "5": "家長您好，學生已完成接送。"
            }

            reply_message = status_map[text]

            # 先從 Sheet 找最後一位家長
            url = f"{SHEET_API}?action=lastPickup"

            try:
                res = requests.get(url)
                data = res.json()

                parent_user_id = data.get("parent_user_id")

                if parent_user_id:

                    # 推送給家長
                    requests.post(
                        "https://api.line.me/v2/bot/message/push",
                        headers={
                            "Content-Type": "application/json",
                            "Authorization": "Bearer " + CHANNEL_ACCESS_TOKEN
                        },
                        json={
                            "to": parent_user_id,
                            "messages": [{
                                "type": "text",
                                "text": reply_message
                            }]
                        }
                    )

                    # 回老師確認
                    reply_to_line(
                        reply_token,
                        "已通知家長。"
                    )

            except Exception as e:
                print("status reply error:", e)

            return "OK", 200
