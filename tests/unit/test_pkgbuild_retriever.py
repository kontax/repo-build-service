import boto3
import botocore
import json
import hashlib
import hmac
import os
from mock import patch
import pytest
import re
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
PKGBUILDS = {
    'master': 'tests/inputs/pkgbuild_retriever/master_pkgbuild.json',
    'dev': 'tests/inputs/pkgbuild_retriever/dev_pkgbuild.json',
    'random': 'tests/inputs/pkgbuild_retriever/random_pkgbuild.json',
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

class UrlOpenMockContext:
    """ Mock context for urlopen """

    def __init__(self, *args, **kwargs):
        self.url = args[0] if isinstance(args[0], str) \
                   else args[0].get_full_url()

        if match := re.search(
                    'https://raw.githubusercontent.com/(.+/.+)/(.+)/(.+/.*)',
                    self.url,
                    re.IGNORECASE):
            self.repo_name = match.group(1)
            self.branch = match.group(2)
            self.location = match.group(3)

    def __enter__(self, *args, **kwargs):
        if self.branch in PKGBUILDS:
            return open(PKGBUILDS[self.branch], 'rb')
        else:
            raise Exception(self.url)

    def __exit__(self, *args, **kwargs):
        pass


@mock_sqs
@patch('urllib.request.urlopen', UrlOpenMockContext)
def test_git_url_is_correct():

    sqs = boto3.resource("sqs", region_name='eu-west-1')
    new_queue = sqs.create_queue(QueueName="PkgbuildParserQueue")

    os.environ["NEXT_QUEUE"] = new_queue.url
    os.environ['GITHUB_WEBHOOK_SECRET'] = "ABCD1234ABCD1234"
    from pkgbuild_retriever.retrieve_pkgbuild import lambda_handler

    webhook = get_input(
        'master_commit',
        os.environ.get('GITHUB_WEBHOOK_SECRET'))

    resp = lambda_handler(webhook, None)
    assert resp['statusCode'] == 200
    messages = new_queue.receive_messages()
    assert len(messages) == 1

    pkgbuild = json.loads(messages[0].body)
    url = pkgbuild['git_url']
    assert url == 'https://github.com/kontax/arch-packages.git'


@patch('urllib.request.urlopen', UrlOpenMockContext)
def test_validation_fails_on_incorrect_token():

    os.environ['GITHUB_WEBHOOK_SECRET'] = "ABCD1234ABCD1234"
    webhook = get_input('master_commit', "INCORRECT_SECRET")
    from pkgbuild_retriever.retrieve_pkgbuild import lambda_handler

    resp = lambda_handler(webhook, None)
    assert resp['statusCode'] == 401
    assert resp['body'] == \
        "X-Hub-Signature is incorrect. Github webhook token doesn't match"


@mock_sqs
@patch('urllib.request.urlopen', UrlOpenMockContext)
def test_git_branch_is_master():

    sqs = boto3.resource("sqs", region_name='eu-west-1')
    new_queue = sqs.create_queue(QueueName="PkgbuildParserQueue")

    os.environ["NEXT_QUEUE"] = new_queue.url
    os.environ['GITHUB_WEBHOOK_SECRET'] = "ABCD1234ABCD1234"
    from pkgbuild_retriever.retrieve_pkgbuild import lambda_handler

    webhook = get_input(
        'master_commit',
        os.environ.get('GITHUB_WEBHOOK_SECRET'))

    resp = lambda_handler(webhook, None)
    assert resp['statusCode'] == 200
    messages = new_queue.receive_messages()
    assert len(messages) == 1

    pkgbuild = json.loads(messages[0].body)
    branch = pkgbuild['git_branch']
    assert branch == 'master'

    stage = pkgbuild['stage']
    assert stage == 'prod'

@mock_sqs
@patch('urllib.request.urlopen', UrlOpenMockContext)
def test_git_branch_is_dev():

    sqs = boto3.resource("sqs", region_name='eu-west-1')
    new_queue = sqs.create_queue(QueueName="PkgbuildParserQueue")

    os.environ["NEXT_QUEUE"] = new_queue.url
    os.environ['GITHUB_WEBHOOK_SECRET'] = "ABCD1234ABCD1234"
    from pkgbuild_retriever.retrieve_pkgbuild import lambda_handler

    webhook = get_input(
        'dev_commit',
        os.environ.get('GITHUB_WEBHOOK_SECRET'))

    resp = lambda_handler(webhook, None)
    assert resp['statusCode'] == 200
    messages = new_queue.receive_messages()
    assert len(messages) == 1

    pkgbuild = json.loads(messages[0].body)
    branch = pkgbuild['git_branch']
    assert branch == 'dev'

    stage = pkgbuild['stage']
    assert stage == 'dev'


@mock_sqs
@patch('urllib.request.urlopen', UrlOpenMockContext)
def test_git_branch_is_random():

    sqs = boto3.resource("sqs", region_name='eu-west-1')
    new_queue = sqs.create_queue(QueueName="PkgbuildParserQueue")

    os.environ["NEXT_QUEUE"] = new_queue.url
    os.environ['GITHUB_WEBHOOK_SECRET'] = "ABCD1234ABCD1234"
    from pkgbuild_retriever.retrieve_pkgbuild import lambda_handler

    webhook = get_input(
        'random_branch',
        os.environ.get('GITHUB_WEBHOOK_SECRET'))

    resp = lambda_handler(webhook, None)
    assert resp['statusCode'] == 200
    messages = new_queue.receive_messages()
    assert len(messages) == 1

    pkgbuild = json.loads(messages[0].body)
    branch = pkgbuild['git_branch']
    assert branch == 'random'

    stage = pkgbuild['stage']
    assert stage == 'dev'

@mock_sqs
@patch('urllib.request.urlopen', UrlOpenMockContext)
def test_payload_gets_correctly_received():

    sqs = boto3.resource("sqs", region_name='eu-west-1')
    new_queue = sqs.create_queue(QueueName="PkgbuildParserQueue")

    os.environ["NEXT_QUEUE"] = new_queue.url
    os.environ['GITHUB_WEBHOOK_SECRET'] = "ABCD1234ABCD1234"
    from pkgbuild_retriever.retrieve_pkgbuild import lambda_handler

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


@mock_sqs
@patch('urllib.request.urlopen', UrlOpenMockContext)
def test_no_commit_throws_401():

    sqs = boto3.resource("sqs", region_name='eu-west-1')
    new_queue = sqs.create_queue(QueueName="PkgbuildParserQueue")

    os.environ["NEXT_QUEUE"] = new_queue.url
    os.environ['GITHUB_WEBHOOK_SECRET'] = "ABCD1234ABCD1234"
    from pkgbuild_retriever.retrieve_pkgbuild import lambda_handler

    webhook = get_input(
        'no_commits',
        os.environ.get('GITHUB_WEBHOOK_SECRET'))

    resp = lambda_handler(webhook, None)
    assert resp['statusCode'] == 401
