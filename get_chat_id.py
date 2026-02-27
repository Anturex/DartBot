"""그룹 채팅 ID 확인 스크립트"""
import asyncio
from dotenv import load_dotenv

load_dotenv()

from config import load_config
from utils.http_client import HttpClient


async def main():
    config = load_config()
    http = HttpClient(config)
    await http.start()

    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/getUpdates"
    async with http.session.get(url) as resp:
        data = await resp.json()

    if not data.get("result"):
        print("업데이트가 없습니다. 그룹에 봇을 추가한 후 아무 메시지나 보내주세요.")
    else:
        seen = set()
        for update in data["result"]:
            msg = update.get("message", {})
            chat = msg.get("chat", {})
            chat_id = chat.get("id")
            chat_type = chat.get("type", "")
            title = chat.get("title", chat.get("first_name", ""))

            if chat_id and chat_id not in seen:
                seen.add(chat_id)
                print(f"  채팅: {title} | 타입: {chat_type} | ID: {chat_id}")

    await http.close()


asyncio.run(main())
