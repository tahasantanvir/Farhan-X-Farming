import os
import time
import logging
from datetime import datetime, timedelta
import random

import tweepy
from openai import OpenAI
from apscheduler.schedulers.background import BackgroundScheduler

# ------- CONFIG -------
X_API_KEY = os.environ.get("th29GG6QHb0n9Q8BRrjh0p8C3
")
X_API_KEY_SECRET = os.environ.get("6ic3C8Tsx8bbiQADkk1MQ8wA6R4u5Cz04nA4i4QRlYonwgbXsF")
X_ACCESS_TOKEN = os.environ.get("1855827048838950913-IcaQeiLpT2U16zozzpqFOuUM7p1VqF")
X_ACCESS_TOKEN_SECRET = os.environ.get("ORtMRylbRhpqP7kFE77GLqqWKN3xfGtQNkiszggEkduw8")

OPENAI_API_KEY = os.environ.get("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
")

MAX_REPLIES_PER_HOUR = int(os.environ.get("MAX_REPLIES_PER_HOUR", "10"))
MIN_SECONDS_BETWEEN_REPLIES = int(
    os.environ.get("MIN_SECONDS_BETWEEN_REPLIES", "30"))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Validate required environment variables
required_vars = {
    "X_API_KEY": X_API_KEY,
    "X_API_KEY_SECRET": X_API_KEY_SECRET,
    "X_ACCESS_TOKEN": X_ACCESS_TOKEN,
    "X_ACCESS_TOKEN_SECRET": X_ACCESS_TOKEN_SECRET,
    "OPENAI_API_KEY": OPENAI_API_KEY
}

missing_vars = [name for name, value in required_vars.items() if not value]
if missing_vars:
    logger.error(
        f"Missing required environment variables: {', '.join(missing_vars)}")
    logger.info("Please set the following environment variables:")
    for var in missing_vars:
        logger.info(f"  - {var}")
    logger.info("Then restart the bot.")
    exit(1)

auth = tweepy.OAuth1UserHandler(consumer_key=X_API_KEY,
                                consumer_secret=X_API_KEY_SECRET,
                                access_token=X_ACCESS_TOKEN,
                                access_token_secret=X_ACCESS_TOKEN_SECRET)
api = tweepy.API(auth, wait_on_rate_limit=True)

openai_client = OpenAI(api_key=OPENAI_API_KEY)

last_reply_time = datetime.min
replies_this_hour = 0
hour_window_start = datetime.utcnow()


def can_reply():
    global last_reply_time, replies_this_hour, hour_window_start
    now = datetime.utcnow()
    if now - hour_window_start >= timedelta(hours=1):
        hour_window_start = now
        replies_this_hour = 0
    if replies_this_hour >= MAX_REPLIES_PER_HOUR:
        return False
    if (now - last_reply_time).total_seconds() < MIN_SECONDS_BETWEEN_REPLIES:
        return False
    return True


def generate_ai_reply(prompt_text):
    resp = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{
            "role":
            "system",
            "content":
            "You are a friendly social media assistant, short replies (<=120 chars). Avoid abusive content."
        }, {
            "role": "user",
            "content": prompt_text
        }],
        max_tokens=80,
        temperature=0.7,
        n=1)
    out = resp.choices[0].message.content.strip()
    if len(out) > 250:
        out = out[:240] + "..."
    return out


def moderate_text(text):
    forbidden = ["kill", "bomb", "suicide", "rape", "hate"]
    t = text.lower()
    for w in forbidden:
        if w in t:
            return False
    return True


def search_and_reply():
    global last_reply_time, replies_this_hour
    try:
        query = "airdrop OR giveaway -is:retweet lang:en"
        tweets = api.search_tweets(q=query,
                                   count=5,
                                   result_type='recent',
                                   tweet_mode='extended')
        for t in tweets:
            if not can_reply():
                return
            tweet_id = t.id
            username = t.user.screen_name
            prompt = f"Write a friendly short reply to @{username}: '{t.full_text}'"
            reply_text = generate_ai_reply(prompt)
            if not moderate_text(reply_text):
                continue
            delay = random.uniform(5, 18)
            time.sleep(delay)
            try:
                api.update_status(status=f"@{username} {reply_text}",
                                  in_reply_to_status_id=tweet_id)
                replies_this_hour += 1
                last_reply_time = datetime.utcnow()
            except Exception as e:
                logger.exception("Error sending reply: %s", e)
    except Exception as e:
        logger.exception("Search/reply loop failed: %s", e)


def scheduled_post():
    try:
        text = os.environ.get(
            "SCHEDULE_POST_TEXT",
            f"Auto post at {datetime.utcnow().isoformat()}")[:280]
        if not moderate_text(text):
            return
        api.update_status(status=text)
    except Exception as e:
        logger.exception("Scheduled post failed: %s", e)


if __name__ == "__main__":
    sched = BackgroundScheduler()
    sched.add_job(search_and_reply, 'interval', seconds=60, id='search_reply')
    sched.add_job(scheduled_post, 'cron', hour=2, minute=0, id='daily_post')
    sched.start()
    try:
        while True:
            time.sleep(10)
    except (KeyboardInterrupt, SystemExit):
        sched.shutdown()
