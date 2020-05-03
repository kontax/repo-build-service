import boto3
import botocore
import json
import hashlib
import hmac
import os
import pytest
import sys

from moto import mock_sqs, mock_sts

# Get the root path of the project to allow importing
ROOT_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
sys.path.append(ROOT_PATH)
sys.path.append(os.path.join(ROOT_PATH, "pkgbuild_retriever"))
sys.path.append(os.path.join(ROOT_PATH, "src/python"))

TEMPLATE = os.path.join(ROOT_PATH, 'tests/inputs/webhook-template.json')
INPUTS = {
    'dev_commit': 'tests/inputs/pkgbuild_retriever/dev_commit.json',
    'no_commits': 'tests/inputs/pkgbuild_retriever/no_commits.json',
    'master_commit': 'tests/inputs/pkgbuild_retriever/master_commit.json',
    'random_branch': 'tests/inputs/pkgbuild_retriever/random_branch.json',
}


def get_digest(token, data):
    return hmac.new(
            token.encode('utf-8'), 
            data.encode('utf-8'), 
            hashlib.sha1).hexdigest()


def get_input(input_name, token):
    input_location = INPUTS[input_name]
    filename = os.path.join(ROOT_PATH, input_location)

    with open(TEMPLATE, 'r') as f:
        output = json.loads(f.read())

    with open(filename, 'r') as f:
        data = f.read()
        sig = get_digest(token, data)
        output['body'] = data
        output['headers']['X-Hub-Signature'] = f"sha1={sig}"

    return output


def test_validation_fails_on_incorrect_token():

    from pkgbuild_retriever.retrieve_pkgbuild import lambda_handler

    os.environ['GITHUB_WEBHOOK_SECRET'] = "ABCD1234ABCD1234"
    webhook = get_input('master_commit', "INCORRECT_SECRET")

    resp = lambda_handler(webhook, None)
    assert resp['statusCode'] == 401
    assert resp['body'] == \
        "X-Hub-Signature is incorrect. Github webhook token doesn't match"

@mock_sqs
def test_git_url_is_correct():

    from pkgbuild_retriever.retrieve_pkgbuild import lambda_handler

    sqs = boto3.resource("sqs", region_name='eu-west-1')
    new_queue = sqs.create_queue(QueueName="PkgbuildParserQueue")

    os.environ["NEXT_QUEUE"] = new_queue.url
    os.environ['GITHUB_WEBHOOK_SECRET'] = "ABCD1234ABCD1234"

    webhook = get_input(
        'master_commit',
        os.environ.get('GITHUB_WEBHOOK_SECRET'))

    resp = lambda_handler(webhook, None)
    assert resp['statusCode'] == 200
    messages = new_queue.receive_messages()
    assert len(messages) == 1

    pkgbuild = json.loads(messages[0].body)
    url = pkgbuild['url']
    assert url == 'https://github.com/kontax/arch-packages.git'


@mock_sqs
def test_payload_gets_correctly_received():

    from pkgbuild_retriever.retrieve_pkgbuild import lambda_handler

    sqs = boto3.resource("sqs", region_name='eu-west-1')
    new_queue = sqs.create_queue(QueueName="PkgbuildParserQueue")

    os.environ["NEXT_QUEUE"] = new_queue.url
    os.environ['GITHUB_WEBHOOK_SECRET'] = "ABCD1234ABCD1234"

    webhook = get_input(
        'master_commit',
        os.environ.get('GITHUB_WEBHOOK_SECRET'))

    resp = lambda_handler(webhook, None)
    assert resp['statusCode'] == 200
    messages = new_queue.receive_messages()
    assert len(messages) == 1

    pkgbuild = json.loads(messages[0].body)
    payload = pkgbuild['payload']
    payload_first_line = payload.split()[0]
    assert payload_first_line == "pkgbase='couldinho'"

