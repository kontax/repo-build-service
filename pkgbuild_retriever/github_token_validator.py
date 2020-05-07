import hashlib
import hmac
import json
import os

TOKEN = os.environ.get("GITHUB_WEBHOOK_SECRET")

def validate(event):
    """Validates the payload sent to ensure it comes from a valid Github repository

    Args:
        event (dict): The full payload sent by a Github webhook

    Returns:
        dict: An HTTP response outlining whether validation passed or threw an error
    """

    headers = event['headers']
    sig = headers['X-Hub-Signature'].split('=')[1]
    github_event = headers['X-GitHub-Event']
    github_id = headers['X-GitHub-Delivery']
    digest = _get_digest(TOKEN, event['body'])

    if TOKEN is None:
        return _get_error(401, "Must provide a 'GITHUB_WEBHOOK_SECRET' env variable")

    if github_event is None:
        return _get_error(422, "No X-GitHub-Event found in request")

    if github_id is None:
        return _get_error(401, "No X-GitHub-Delivery found in request")

    if sig != digest:
        return _get_error(401, "X-Hub-Signature is incorrect. Github webhook token doesn't match")

    return {
        "statusCode": 200,
        "body": json.dumps(event['body'])
    }


def _get_digest(token, data):
    """Calculate the digest from the data and Github token

    Args:
        token (str): The secret Github token.
        data (str): The github payload

    Returns:
        str: The calculated digest of the data using the token
    """
    return hmac.new(token.encode('utf-8'), data.encode('utf-8'), hashlib.sha1).hexdigest()


def _get_error(code, msg):
    """Returns an HTTP error with a specified code and message

    Args:
        code (int): The HTTP status code to return.
        msg (str): The error message of the response.

    Returns:
        dict: The HTTP error response
    """
    return {
        "statusCode": code,
        "headers": {"Content-Type": "text/plain"},
        "body": msg
    }
