import boto3
import botocore
import json
import hashlib
import hmac
import os
import pytest
import sys

from mock import patch
from moto import mock_sqs, mock_sts, mock_dynamodb2
from urllib.parse import urlparse, parse_qs

# Get the root path of the project to allow importing
ROOT_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
sys.path.append(ROOT_PATH)
sys.path.append(os.path.join(ROOT_PATH, "tests"))
sys.path.append(os.path.join(ROOT_PATH, "fanout_starter"))
sys.path.append(os.path.join(ROOT_PATH, "src/python"))

from test_common import dynamodb_table

PERSONAL_REPO = 'personal-prod'
PERSONAL_REPO_DEV = 'personal-dev'
OFFICIAL_PKG_API = "https://www.archlinux.org/packages/search/json"
OFFICIAL_PKGS = ["bash", "linux", "vim", "zsh", "xorg-server"]

TEMPLATE = os.path.join(ROOT_PATH, 'tests/inputs/sqs-template.json')
INPUTS = {
    'master_test': 'tests/inputs/fanout_starter/master_test.json',
    'dev_test': 'tests/inputs/fanout_starter/dev_test.json',
    'extra_pkg': 'tests/inputs/fanout_starter/extra_pkg.json',
    'no_build_pkg': 'tests/inputs/fanout_starter/no_build_pkg.json',
    'official_api_vim': 'tests/inputs/fanout_starter/official_api_vim.json',
    'official_api_empty': 'tests/inputs/fanout_starter/official_api_empty.json',
}


def get_input(input_name):
    input_location = INPUTS[input_name]
    filename = os.path.join(ROOT_PATH, input_location)

    with open(TEMPLATE, 'r') as f:
        output = json.loads(f.read())

    with open(filename, 'r') as f:
        data = f.read()
        for record in output["Records"]:
            record['body'] = data

    return output


class UrlOpenMockContext:
    """ Mock context for urlopen """

    def __init__(self, *args, **kwargs):
        self.url = args[0] if isinstance(args[0], str) \
                   else args[0].get_full_url()

    def __enter__(self, *args, **kwargs):
        if self.url.startswith(OFFICIAL_PKG_API):
            return self.parse_pkg_api()
        else:
            raise Exception(self.url)

    def __exit__(self, *args, **kwargs):
        pass

    def parse_pkg_api(self):
        qs = parse_qs(urlparse(self.url).query)
        if 'name' not in qs:
            raise Exception(f'"name" not in {self.url}')
        if len(qs['name']) != 1:
            raise Exception(f"More than one 'name' in {self.url}")

        pkg = qs['name'][0]
        if pkg in OFFICIAL_PKGS:
            return open(INPUTS['official_api_vim'], 'rb')
        else:
            return open(INPUTS['official_api_empty'], 'rb')


@mock_sqs
@patch('urllib.request.urlopen', UrlOpenMockContext)
def test_build_package_status_is_set_to_building(dynamodb_table):

    sqs = boto3.resource("sqs", region_name='eu-west-1')
    fanout_queue = sqs.create_queue(QueueName="FanoutQueue")
    build_function_queue = sqs.create_queue(QueueName="BuildFunctionQueue")

    os.environ["FANOUT_QUEUE"] = fanout_queue.url
    os.environ["BUILD_FUNCTION_QUEUE"] = build_function_queue.url
    os.environ["PACKAGE_TABLE"] = "package-table"
    os.environ["PERSONAL_REPO"] = PERSONAL_REPO
    os.environ["DEV_REPO"] = PERSONAL_REPO_DEV
    resp = dynamodb_table.scan()

    from fanout_starter.starter import lambda_handler

    message = get_input("master_test")
    lambda_handler(message, None)

    messages = fanout_queue.receive_messages(MaxNumberOfMessages=10)
    assert len(messages) == 2
    packages = []
    for msg in messages:
        packages.append(json.loads(msg.body))

    assert 'mce-dev' in [pkg['PackageName'] for pkg in packages]
    assert 'GIT_REPO' in [pkg['PackageName'] for pkg in packages]

    mce_dev = [pkg for pkg in packages if pkg['PackageName'] == 'mce-dev'][0]
    metapkg = [pkg for pkg in packages if pkg['PackageName'] == 'GIT_REPO'][0]

    assert mce_dev['BuildStatus'] == 'Building'
    assert metapkg['BuildStatus'] == 'Initialized'


@mock_sqs
@patch('urllib.request.urlopen', UrlOpenMockContext)
def test_build_package_sends_message_to_build_function_queue(dynamodb_table):

    sqs = boto3.resource("sqs", region_name='eu-west-1')
    fanout_queue = sqs.create_queue(QueueName="FanoutQueue")
    build_function_queue = sqs.create_queue(QueueName="BuildFunctionQueue")

    os.environ["FANOUT_QUEUE"] = fanout_queue.url
    os.environ["BUILD_FUNCTION_QUEUE"] = build_function_queue.url
    os.environ["PACKAGE_TABLE"] = "package-table"
    os.environ["PERSONAL_REPO"] = PERSONAL_REPO
    os.environ["DEV_REPO"] = PERSONAL_REPO_DEV

    from fanout_starter.starter import lambda_handler

    message = get_input("master_test")
    lambda_handler(message, None)

    messages = build_function_queue.receive_messages(MaxNumberOfMessages=10)
    assert len(messages) == 1
    mce_dev = json.loads(messages[0].body)

    assert mce_dev['PackageName'] == 'mce-dev'
    assert mce_dev['Repo'] == PERSONAL_REPO


@mock_sqs
@patch('urllib.request.urlopen', UrlOpenMockContext)
def test_two_packages_get_sent_to_build(dynamodb_table):

    packages_to_test = ["mce-dev", "extra-pkg", "GIT_REPO"]

    sqs = boto3.resource("sqs", region_name='eu-west-1')
    fanout_queue = sqs.create_queue(QueueName="FanoutQueue")
    build_function_queue = sqs.create_queue(QueueName="BuildFunctionQueue")

    os.environ["FANOUT_QUEUE"] = fanout_queue.url
    os.environ["BUILD_FUNCTION_QUEUE"] = build_function_queue.url
    os.environ["PACKAGE_TABLE"] = "package-table"
    os.environ["PERSONAL_REPO"] = PERSONAL_REPO
    os.environ["DEV_REPO"] = PERSONAL_REPO_DEV

    from fanout_starter.starter import lambda_handler

    message = get_input("extra_pkg")
    lambda_handler(message, None)

    messages = fanout_queue.receive_messages(MaxNumberOfMessages=10)
    assert len(messages) == 3
    build_packages = [json.loads(m.body)['PackageName'] for m in messages]
    assert set(build_packages) == set(packages_to_test)

    statuses = [json.loads(m.body)['BuildStatus'] for m in messages]
    assert set(statuses) == set(['Building', 'Initialized'])


@mock_sqs
@patch('urllib.request.urlopen', UrlOpenMockContext)
def test_no_build_packages_builds_metapackage(dynamodb_table):

    sqs = boto3.resource("sqs", region_name='eu-west-1')
    fanout_queue = sqs.create_queue(QueueName="FanoutQueue")
    build_function_queue = sqs.create_queue(QueueName="BuildFunctionQueue")

    os.environ["FANOUT_QUEUE"] = fanout_queue.url
    os.environ["BUILD_FUNCTION_QUEUE"] = build_function_queue.url
    os.environ["PACKAGE_TABLE"] = "package-table"
    os.environ["PERSONAL_REPO"] = PERSONAL_REPO
    os.environ["DEV_REPO"] = PERSONAL_REPO_DEV

    from fanout_starter.starter import lambda_handler

    message = get_input("no_build_pkg")
    resp = lambda_handler(message, None)

    assert resp['statusCode'] == 200

    messages = fanout_queue.receive_messages(MaxNumberOfMessages=10)
    assert len(messages) == 1

    metapkg = json.loads(messages[0].body)
    assert metapkg['PackageName'] == 'GIT_REPO'
    assert metapkg['BuildStatus'] == 'Initialized'
    assert metapkg['IsMeta']
    assert metapkg['repo'] == PERSONAL_REPO
    assert metapkg['GitUrl'] == 'https://raw.githubusercontent.com/test_user/master/pkg/PKGBUILD'


@mock_sqs
@patch('urllib.request.urlopen', UrlOpenMockContext)
def test_dev_branch_uses_dev_repo(dynamodb_table):

    sqs = boto3.resource("sqs", region_name='eu-west-1')
    fanout_queue = sqs.create_queue(QueueName="FanoutQueue")
    build_function_queue = sqs.create_queue(QueueName="BuildFunctionQueue")

    os.environ["FANOUT_QUEUE"] = fanout_queue.url
    os.environ["BUILD_FUNCTION_QUEUE"] = build_function_queue.url
    os.environ["PACKAGE_TABLE"] = "package-table"
    os.environ["PERSONAL_REPO"] = PERSONAL_REPO
    os.environ["DEV_REPO"] = PERSONAL_REPO_DEV

    from fanout_starter.starter import lambda_handler

    message = get_input("dev_test")
    lambda_handler(message, None)

    messages = fanout_queue.receive_messages(MaxNumberOfMessages=10)
    assert len(messages) == 2
    packages = []
    for msg in messages:
        packages.append(json.loads(msg.body))

    assert 'ida-free' in [pkg['PackageName'] for pkg in packages]
    assert 'GIT_REPO' in [pkg['PackageName'] for pkg in packages]

    ida_free = [pkg for pkg in packages if pkg['PackageName'] == 'ida-free'][0]
    metapkg = [pkg for pkg in packages if pkg['PackageName'] == 'GIT_REPO'][0]

    assert ida_free['BuildStatus'] == 'Building'
    assert ida_free['repo'] == PERSONAL_REPO_DEV

    assert metapkg['BuildStatus'] == 'Initialized'
    assert metapkg['GitUrl'] == 'https://raw.githubusercontent.com/test_user/dev/pkg/PKGBUILD'
    assert metapkg['repo'] == PERSONAL_REPO_DEV

@mock_sqs
@patch('urllib.request.urlopen', UrlOpenMockContext)
def test_dev_branch_doesnt_use_prod_repo(dynamodb_table):

    sqs = boto3.resource("sqs", region_name='eu-west-1')
    fanout_queue = sqs.create_queue(QueueName="FanoutQueue")
    build_function_queue = sqs.create_queue(QueueName="BuildFunctionQueue")

    os.environ["FANOUT_QUEUE"] = fanout_queue.url
    os.environ["BUILD_FUNCTION_QUEUE"] = build_function_queue.url
    os.environ["PACKAGE_TABLE"] = "package-table"
    os.environ["PERSONAL_REPO"] = PERSONAL_REPO
    os.environ["DEV_REPO"] = PERSONAL_REPO_DEV

    from fanout_starter.starter import lambda_handler

    message = get_input("dev_test")
    lambda_handler(message, None)

    messages = fanout_queue.receive_messages(MaxNumberOfMessages=10)
    assert len(messages) == 2
    packages = []
    for msg in messages:
        packages.append(json.loads(msg.body))

    assert 'ida-free' in [pkg['PackageName'] for pkg in packages]
    assert 'GIT_REPO' in [pkg['PackageName'] for pkg in packages]

