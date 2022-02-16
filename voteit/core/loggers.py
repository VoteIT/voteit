import logging
from os import getenv

from slack_logger import SlackHandler, SlackFormatter

slack_logger = logging.getLogger("slack")
slack_logger.setLevel(logging.INFO)

if slack_webhook_url := getenv("SLACK_LOGGER_WEBHOOK"):
    slack_handler = SlackHandler(username="logger", icon_emoji=":robot_face:", url=slack_webhook_url)
    slack_handler.setLevel(logging.INFO)
    slack_handler.setFormatter(SlackFormatter())
    slack_logger.addHandler(slack_handler)
