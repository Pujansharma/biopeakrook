from time import time

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings

from core.utils.log import logger

WAKE_MESSAGE_BODY = "process_communication_outbox"
WAKE_MESSAGE_GROUP_ID = "communication-outbox"


def outbox_wake_queue_url():
    return getattr(settings, "COMMUNICATION_OUTBOX_WAKE_QUEUE_URL", None) or ""


def outbox_wake_region():
    return getattr(settings, "AWS_REGION", None)


def is_fifo_queue(queue_url):
    return queue_url.endswith(".fifo")


def wake_message_deduplication_id():
    return f"communication-outbox-{int(time()) // 60}"


def publish_outbox_wake():
    queue_url = outbox_wake_queue_url()
    if not queue_url:
        return
    request = {
        "QueueUrl": queue_url,
        "MessageBody": WAKE_MESSAGE_BODY,
    }
    if is_fifo_queue(queue_url):
        request["MessageGroupId"] = WAKE_MESSAGE_GROUP_ID
        request["MessageDeduplicationId"] = wake_message_deduplication_id()
    try:
        client = boto3.client("sqs", region_name=outbox_wake_region())
        client.send_message(**request)
    except (BotoCoreError, ClientError) as error:
        logger.warning(f"Failed to publish communication outbox wake: {error}")
