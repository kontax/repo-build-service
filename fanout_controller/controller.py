import json
import os

from boto3.dynamodb.conditions import Key

from aws import get_dynamo_resource, invoke_lambda
from enums import Status

FANOUT_STATUS = os.environ.get('FANOUT_STATUS')
METAPACKAGE_BUILDER = os.environ.get('METAPACKAGE_BUILDER')


def lambda_handler(event, context):
    print(event)
    package_state = event

    # The dynamoDB table containing the running status of each package
    dynamo = get_dynamo_resource()
    fanout_table = dynamo.Table(FANOUT_STATUS)
    fanout_table.update_item(
        Key={'PackageName': package_state['PackageName']},
        UpdateExpression="set BuildStatus = :s",
        ExpressionAttributeValues={
            ':s': package_state['BuildStatus']
        }
    )

    # Delete completed items
    all_items = fanout_table.scan()
    deleted_items = [item for item in all_items['Items'] if item['BuildStatus'] == Status.Complete.name]
    for item in deleted_items:
        fanout_table.delete_item(Key={"PackageName": item['PackageName']})

    # Check remaining items
    resp = fanout_table.scan()

    # If items are still running quit and wait for the next invocation
    if len(resp['Items']) > 1:
        print(f"{len(resp['Items'])} still in table")
        return return_code(200, {"status": "Items are still running"})

    # Otherwise if everything has completed, invoke the meta-package building function
    resp = fanout_table.query(KeyConditionExpression=Key('PackageName').eq("METAPACKAGE_URL"))
    invoke_lambda(METAPACKAGE_BUILDER, {"url": resp['Items'][0]['BuildStatus']})

    return return_code(200, {"status": "All packages built"})


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
