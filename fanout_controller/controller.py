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
    update_sent_item(fanout_table, package_state)

    # Delete completed items
    delete_completed(fanout_table)

    # Check remaining items
    resp = fanout_table.scan()

    # If items are still running quit and wait for the next invocation
    if len(resp['Items']) > 1:
        print(f"{len(resp['Items'])} still in table")
        return return_code(200, {"status": "Items are still running"})

    # Otherwise if everything has completed, invoke the meta-package building function
    build_metapackage(fanout_table)

    return return_code(200, {"status": "All packages built"})


def update_sent_item(fanout_table, package_state):
    """ Updates the item sent via the lambda event in the fanout table

    :param (Table) fanout_table: The table containing the status of each package
    :param (dict) package_state: The name and state of the package to update
    """
    fanout_table.update_item(
        Key={'PackageName': package_state['PackageName']},
        UpdateExpression="set BuildStatus = :s",
        ExpressionAttributeValues={
            ':s': package_state['BuildStatus']
        }
    )


def delete_completed(fanout_table):
    """ Deletes any completed items from the fanout table

    :param (Table) fanout_table: The table containing the status of each package within the process
    """
    all_items = fanout_table.scan()
    deleted_items = [item for item in all_items['Items'] if item['BuildStatus'] == Status.Complete.name]
    for item in deleted_items:
        fanout_table.delete_item(Key={"PackageName": item['PackageName']})


def build_metapackage(fanout_table):
    """ Adds the metapackage to the build queue.

    :param (Table) fanout_table: The table containing the status of each package
    """
    print("All packages finished - invoking the metapackage builder")
    resp = fanout_table.query(KeyConditionExpression=Key('PackageName').eq("GIT_REPO"))
    invoke_lambda(METAPACKAGE_BUILDER, {"git_url": resp['Items'][0]['BuildStatus']})
    fanout_table.delete_item(Key={"PackageName": "GIT_REPO"})


def return_code(code, body):
    """Returns a JSON response

    :param (int) code: The HTTP response code
    :param (dict) body: The data to return

    :return: A JSON object containing the code and body
    :rtype: dict
    """
    return {
        "statusCode": code,
        "body": json.dumps(body)
    }
