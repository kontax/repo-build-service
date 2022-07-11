import boto3
import botocore
import json
import hashlib
import hmac
import os
import pytest
import sys

from moto import mock_sqs, mock_sts, mock_dynamodb

# Get the root path of the project to allow importing
ROOT_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
sys.path.append(ROOT_PATH)
sys.path.append(os.path.join(ROOT_PATH, "metapackage_builder"))
sys.path.append(os.path.join(ROOT_PATH, "src/python"))

TEMPLATE = os.path.join(ROOT_PATH, 'tests/inputs/sqs-template.json')
INPUTS = {
    'metapackage': 'tests/inputs/metapackage_builder/metapackage.json',
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


@pytest.fixture()
def dynamodb_table():

    package_name = 'fanout-status'

    with mock_dynamodb():
        client = boto3.client('dynamodb')
        client.create_table(
            TableName=package_name,
            AttributeDefinitions=[
                {'AttributeName': 'PackageName', 'AttributeType': 'S'}
            ],
            KeySchema=[{"KeyType": "HASH", "AttributeName": "PackageName"}],
            ProvisionedThroughput={
                'ReadCapacityUnits': 5,
                'WriteCapacityUnits': 5
            }
        )

        tbl = boto3.resource('dynamodb').Table(package_name)
        yield tbl


@mock_sqs
def test_failed_packages_get_removed_from_table(dynamodb_table):

    # Add a test item to the status table
    dynamodb_table.update_item(
        Key={'PackageName': 'GIT_REPO'},
        UpdateExpression="set BuildStatus = :s, IsMeta = :m, GitUrl = :g, repo = :r",
        ExpressionAttributeValues={
            ':s': "Initialized",
            ':m': True,
            ':g': "https://raw.githubusercontent.com/test_user/master/pkg/PKGBUILD",
            ':r': "couldinho-test"
        }
    )

    # Add a different package than the one being sent in the message
    dynamodb_table.update_item(
        Key={'PackageName': 'random-package'},
        UpdateExpression="set BuildStatus = :s, IsMeta = :m, GitUrl = :g, repo = :r",
        ExpressionAttributeValues={
            ':s': "Complete",
            ':m': False,
            ':g': None,
            ':r': "couldinho-test"
        }
    )

    # Add the package that is going to fail
    dynamodb_table.update_item(
        Key={'PackageName': 'mce-dev'},
        UpdateExpression="set BuildStatus = :s, IsMeta = :m, GitUrl = :g, repo = :r",
        ExpressionAttributeValues={
            ':s': "Complete",
            ':m': False,
            ':g': None,
            ':r': "couldinho-test"
        }
    )

    data = dynamodb_table.scan()
    assert len(data['Items']) == 3

    sqs = boto3.resource("sqs", region_name='eu-west-1')
    build_function_queue = sqs.create_queue(QueueName="BuildFunctionQueue")

    os.environ["FANOUT_STATUS"] = dynamodb_table.table_name
    os.environ["BUILD_FUNCTION_QUEUE"] = build_function_queue.url

    from metapackage_builder.metapackage import lambda_handler

    message = get_input("metapackage")
    res = lambda_handler(message, None)
    assert res['statusCode'] == 200

    messages = build_function_queue.receive_messages(MaxNumberOfMessages=10)
    assert len(messages) == 1
    msg = json.loads(messages[0].body)

    assert msg['PackageName'] == 'GIT_REPO'
    assert msg['Repo'] == 'couldinho-test'
    assert msg['git_url'] == 'https://raw.githubusercontent.com/test_user/master/pkg/PKGBUILD'
    assert set(['random-package', 'mce-dev']) == set(msg['built_packages'])

