import logging
import telebot
import os
import openai
import boto3
import time
import json
import threading
from dotenv import load_dotenv

load_dotenv()

TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN")
TG_BOT_CHATS = os.getenv("TG_BOT_CHATS").lower().split(",")
PROXY_API_KEY = os.getenv("PROXY_API_KEY")
YANDEX_KEY_ID = os.getenv("YANDEX_KEY_ID")
YANDEX_KEY_SECRET = os.getenv("YANDEX_KEY_SECRET")
YANDEX_BUCKET = os.getenv("YANDEX_BUCKET")
ASSISTANT_ID = os.getenv("ASSISTANT_ID")

logger = telebot.logger
telebot.logger.setLevel(logging.INFO)

bot = telebot.TeleBot(TG_BOT_TOKEN, threaded=False)

client = openai.Client(
    api_key=os.getenv("PROXY_API_KEY"),
    base_url="https://api.proxyapi.ru/openai/v1"
)


def get_s3_client():
    session = boto3.session.Session(
        aws_access_key_id=YANDEX_KEY_ID,
        aws_secret_access_key=YANDEX_KEY_SECRET
    )
    return session.client(
        service_name="s3",
        endpoint_url="https://storage.yandexcloud.net"
    )

is_typing = False

def start_typing(chat_id):
    global is_typing
    is_typing = True
    typing_thread = threading.Thread(target=typing, args=(chat_id,))
    typing_thread.start()

def typing(chat_id):
    global is_typing
    while is_typing:
        bot.send_chat_action(chat_id, "typing")
        time.sleep(4)

def stop_typing():
    global is_typing
    is_typing = False

@bot.message_handler(commands=["help", "start"])
def send_welcome(message):
    bot.reply_to(message, "Привет! Я Assistant API бот. Спроси меня что-нибудь!")

@bot.message_handler(commands=["new"])
def clear_history(message):
    clear_history_for_chat(message.chat.id)
    bot.reply_to(message, "История чата очищена!")

@bot.message_handler(func=lambda message: True, content_types=["text"])
def echo_message(message):
    start_typing(message.chat.id)

    try:
        text = message.text
        ai_response = process_text_message(text, message.chat.id)
    except Exception as e:
        stop_typing()
        bot.reply_to(message, f"Произошла ошибка, попробуйте позже! {e}")
        return

    stop_typing()
    bot.reply_to(message, ai_response)

def process_text_message(text, chat_id) -> str:
    s3client = get_s3_client()

    try:
        thread_obj = s3client.get_object(
            Bucket=YANDEX_BUCKET,
            Key=f"{chat_id}_thread.txt"
        )
        thread_id = thread_obj["Body"].read().decode("utf-8")
    except:
        thread = client.beta.threads.create()
        thread_id = thread.id
        s3client.put_object(
            Bucket=YANDEX_BUCKET,
            Key=f"{chat_id}_thread.txt",
            Body=thread_id.encode("utf-8"),
        )

    client.beta.threads.messages.create(
        thread_id=thread_id,
        role="user",
        content=text
    )

    run = client.beta.threads.runs.create_and_poll(
        thread_id=thread_id,
        assistant_id=ASSISTANT_ID
    )

    response_msg = run.latest_message()
    return response_msg.content[0].text.value

def clear_history_for_chat(chat_id):
    try:
        s3client = get_s3_client()
        s3client.put_object(
            Bucket=YANDEX_BUCKET,
            Key=f"{chat_id}_thread.txt",
            Body=b""
        )
    except:
        pass

def handler(event, context):
    message = json.loads(event["body"])
    update = telebot.types.Update.de_json(message)

    if (
        update.message is not None
    ):
        try:
            bot.process_new_updates([update])
        except Exception as e:
            print(e)

    return {
        "statusCode": 200,
        "body": "ok",
    }