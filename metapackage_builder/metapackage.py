import json
import os

from aws import get_dynamo_resource, invoke_lambda
from enums import Status

FANOUT_STATUS = os.environ.get('FANOUT_STATUS')
METAPACKAGE_BUILDER = os.environ.get('METAPACKAGE_BUILDER')


def delete_completed_items(table):
    table.delete_item(Key={"Status": Status.Complete.name})


def lambda_handler(event, context):
    print(event)


def return_code(code, body):
    """Returns a JSON response

    Args:
        code (int): The HTTP response code
        body (dict): The data to return

    Returns:
        (dict): A JSON object containing the code and body
    """
    return {
        "statusCode": code,
        "body": json.dumps(body)
    }
