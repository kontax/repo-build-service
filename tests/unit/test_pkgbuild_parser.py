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
sys.path.append(os.path.join(ROOT_PATH, "pkgbuild_parser"))
sys.path.append(os.path.join(ROOT_PATH, "src/python"))

TEMPLATE = os.path.join(ROOT_PATH, 'tests/inputs/sqs-template.json')
INPUTS = {
    'master_test': 'tests/inputs/pkgbuild_parser/master_test.json',
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

@mock_sqs
def test_output_matches_packages():


    deps = ['bash', 'linux', 'vim', 'zsh', 'couldinho-base',
            'xorg-server', 'mce-dev']
    sqs = boto3.resource("sqs", region_name='eu-west-1')
    new_queue = sqs.create_queue(QueueName="FanoutStarterQueue")

    os.environ["NEXT_QUEUE"] = new_queue.url
    from pkgbuild_parser.parse_pkgbuild import lambda_handler

    message = get_input('master_test')

    resp = lambda_handler(message, None)
    assert resp['statusCode'] == 200

    messages = new_queue.receive_messages()
    assert len(messages) == 1

    body = json.loads(messages[0].body)
    print(body)

    assert set(body['dependencies']) == set(deps)
    assert body['stage'] == 'prod'
    assert body['git_branch'] == 'master'
    assert body['git_url'] == 'https://raw.githubusercontent.com/test_user/master/pkg/PKGBUILD'

