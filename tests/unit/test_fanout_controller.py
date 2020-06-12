import boto3
import botocore
import json
import hashlib
import hmac
import os
import pytest
import sys

from moto import mock_sqs, mock_sts, mock_dynamodb2
from moto.dynamodb2 import dynamodb_backend2

# Get the root path of the project to allow importing
ROOT_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
sys.path.append(ROOT_PATH)
sys.path.append(os.path.join(ROOT_PATH, "fanout_controller"))
sys.path.append(os.path.join(ROOT_PATH, "src/python"))

TEMPLATE = os.path.join(ROOT_PATH, 'tests/inputs/sqs-template.json')
INPUTS = {
    'initialized_package': 'tests/inputs/fanout_controller/initialized_package.json',
    'building_package': 'tests/inputs/fanout_controller/building_package.json',
    'failed_package': 'tests/inputs/fanout_controller/failed_package.json',
    'completed_package': 'tests/inputs/fanout_controller/completed_package.json',
    'metapackage': 'tests/inputs/fanout_controller/metapackage.json',
    'complete-dev': 'tests/inputs/fanout_controller/complete-dev.json',
    'complete-prod': 'tests/inputs/fanout_controller/complete-prod.json',
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

    with mock_dynamodb2():
        client = boto3.client('dynamodb')
        client.create_table(
            TableName=package_name,
            AttributeDefinitions=[
                {'AttributeName': 'PackageName', 'AttributeType': 'S'}
            ],
            KeySchema=[{"KeyType": "HASH", "AttributeName": "PackageName"}]
        )

        tbl = boto3.resource('dynamodb').Table(package_name)
        yield tbl


@mock_sqs
def test_fanout_status_table_gets_updated_with_regular_package(dynamodb_table):

    # The item which should be in the table after running the function
    package_check = {
        "PackageName": "mce-dev",
        "BuildStatus": "Initialized",
        "IsMeta": False,
        "repo": "couldinho-test",
        "GitUrl": None
    }

    sqs = boto3.resource("sqs", region_name='eu-west-1')
    metapackage_queue = sqs.create_queue(QueueName="MetapackageQueue")
    package_update_queue = sqs.create_queue(QueueName="PackageUpdateQueue")

    os.environ["FANOUT_STATUS"] = dynamodb_table.table_name
    os.environ["METAPACKAGE_QUEUE"] = metapackage_queue.url
    os.environ["PACKAGE_UPDATE_QUEUE"] = package_update_queue.url

    from fanout_controller.controller import lambda_handler

    message = get_input("initialized_package")
    res = lambda_handler(message, None)
    assert res['statusCode'] == 200

    data = dynamodb_table.scan()
    assert len(data['Items']) == 1
    package_details = data['Items'][0]
    assert package_details == package_check


@mock_sqs
def test_package_update_queue_gets_notified_on_completion(dynamodb_table):

    # Queue item to check
    queue_output = {
        "repository": "personal-prod",
        "url": "https://test-repo.s3.amazonaws.com"
    }

    sqs = boto3.resource("sqs", region_name='eu-west-1')
    metapackage_queue = sqs.create_queue(QueueName="MetapackageQueue")
    package_update_queue = sqs.create_queue(QueueName="PackageUpdateQueue")

    os.environ["FANOUT_STATUS"] = dynamodb_table.table_name
    os.environ["METAPACKAGE_QUEUE"] = metapackage_queue.url
    os.environ["PACKAGE_UPDATE_QUEUE"] = package_update_queue.url

    from fanout_controller.controller import lambda_handler

    message = get_input("complete-prod")
    res = lambda_handler(message, None)
    assert res['statusCode'] == 200

    messages = package_update_queue.receive_messages(MaxNumberOfMessages=10)
    assert len(messages) == 1
    msg = json.loads(messages[0].body)

    assert msg == queue_output


@mock_sqs
def test_status_table_gets_cleared_on_completion(dynamodb_table):

    # Add a test item to the status table
    dynamodb_table.update_item(
        Key={'PackageName': 'GIT_REPO'},
        UpdateExpression="set BuildStatus = :s, IsMeta = :m, GitUrl = :g, repo = :r",
        ExpressionAttributeValues={
            ':s': "Complete",
            ':m': True,
            ':g': "https://raw.githubusercontent.com/test_user/master/pkg/PKGBUILD",
            ':r': "couldinho-test"
        }
    )

    sqs = boto3.resource("sqs", region_name='eu-west-1')
    metapackage_queue = sqs.create_queue(QueueName="MetapackageQueue")
    package_update_queue = sqs.create_queue(QueueName="PackageUpdateQueue")

    os.environ["FANOUT_STATUS"] = dynamodb_table.table_name
    os.environ["METAPACKAGE_QUEUE"] = metapackage_queue.url
    os.environ["PACKAGE_UPDATE_QUEUE"] = package_update_queue.url

    from fanout_controller.controller import lambda_handler

    message = get_input("complete-dev")
    res = lambda_handler(message, None)
    assert res['statusCode'] == 200

    data = dynamodb_table.scan()
    assert len(data['Items']) == 0


@mock_sqs
def test_metapackage_gets_built_after_other_packages(dynamodb_table):

    # Queue item to check
    queue_output = {
        "git_url": "https://raw.githubusercontent.com/test_user/master/pkg/PKGBUILD",
        "repo": "couldinho-test"
    }

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

    # Add the package currently building
    dynamodb_table.update_item(
        Key={'PackageName': 'mce-dev'},
        UpdateExpression="set BuildStatus = :s, IsMeta = :m, GitUrl = :g, repo = :r",
        ExpressionAttributeValues={
            ':s': "Building",
            ':m': False,
            ':g': None,
            ':r': "couldinho-test"
        }
    )

    sqs = boto3.resource("sqs", region_name='eu-west-1')
    metapackage_queue = sqs.create_queue(QueueName="MetapackageQueue")
    package_update_queue = sqs.create_queue(QueueName="PackageUpdateQueue")

    os.environ["FANOUT_STATUS"] = dynamodb_table.table_name
    os.environ["METAPACKAGE_QUEUE"] = metapackage_queue.url
    os.environ["PACKAGE_UPDATE_QUEUE"] = package_update_queue.url

    from fanout_controller.controller import lambda_handler

    message = get_input("completed_package")
    res = lambda_handler(message, None)
    assert res['statusCode'] == 200

    messages = metapackage_queue.receive_messages(MaxNumberOfMessages=10)
    assert len(messages) == 1
    assert json.loads(messages[0].body) == queue_output


@mock_sqs
def test_no_metapackage_build_when_packages_still_building(dynamodb_table):

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
            ':s': "Building",
            ':m': False,
            ':g': None,
            ':r': "couldinho-test"
        }
    )

    sqs = boto3.resource("sqs", region_name='eu-west-1')
    metapackage_queue = sqs.create_queue(QueueName="MetapackageQueue")
    package_update_queue = sqs.create_queue(QueueName="PackageUpdateQueue")

    os.environ["FANOUT_STATUS"] = dynamodb_table.table_name
    os.environ["METAPACKAGE_QUEUE"] = metapackage_queue.url
    os.environ["PACKAGE_UPDATE_QUEUE"] = package_update_queue.url

    from fanout_controller.controller import lambda_handler

    message = get_input("building_package")
    res = lambda_handler(message, None)
    assert res['statusCode'] == 200
    assert json.loads(res['body']) == {"status": "Items are still running"}

    messages = metapackage_queue.receive_messages(MaxNumberOfMessages=10)
    assert len(messages) == 0


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
            ':s': "Building",
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
            ':s': "Building",
            ':m': False,
            ':g': None,
            ':r': "couldinho-test"
        }
    )

    data = dynamodb_table.scan()
    assert len(data['Items']) == 3

    sqs = boto3.resource("sqs", region_name='eu-west-1')
    metapackage_queue = sqs.create_queue(QueueName="MetapackageQueue")
    package_update_queue = sqs.create_queue(QueueName="PackageUpdateQueue")

    os.environ["FANOUT_STATUS"] = dynamodb_table.table_name
    os.environ["METAPACKAGE_QUEUE"] = metapackage_queue.url
    os.environ["PACKAGE_UPDATE_QUEUE"] = package_update_queue.url

    from fanout_controller.controller import lambda_handler

    message = get_input("failed_package")
    res = lambda_handler(message, None)
    assert res['statusCode'] == 200

    data = dynamodb_table.scan()
    assert len(data['Items']) == 2
    assert 'mce-dev' not in [i['PackageName'] for i in data['Items']]

