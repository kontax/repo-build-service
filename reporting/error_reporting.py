import boto3
import http.client
import json
import os
import urllib

from urllib.request import urlopen, Request

PUSHOVER_TOKEN = os.environ.get("PUSHOVER_TOKEN")
PUSHOVER_USER = os.environ.get("PUSHOVER_USER")


def handler(event, context):
    print(json.dumps(event))
    for record in event['Records']:
        print(json.dumps(record))
        parse_and_send(record)


def parse_and_send(record):
    message = json.loads(record['body'])
    error = record['messageAttributes']

    message = {
        'OriginalMessage': message,
        'Error': error
    }
    send_to_pushover('repo-build-service error', json.dumps(message, indent=2))


def send_to_pushover(title, message):
    conn = http.client.HTTPSConnection("api.pushover.net:443")
    conn.request("POST", "/1/messages.json",
            urllib.parse.urlencode({
                "token": PUSHOVER_TOKEN,
                "user": PUSHOVER_USER,
                "title": title,
                "message": message,
            }), { "Content-type": "application/x-www-form-urlencoded" })
    resp = conn.getresponse()
    print(f"[*] Pushover Response: {resp.read().decode('utf-8')}")

