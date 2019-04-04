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
    package_state = event

    # The dynamoDB table containing the running status of each package
    dynamo = get_dynamo_resource()
    fanout_table = dynamo.Table(FANOUT_STATUS)
    fanout_table.update_item(Key={'PackageName': package_state['PackageName'], 'Status': package_state['Status']})

    # Delete completed items
    delete_completed_items(fanout_table)

    # Check remaining items
    resp = fanout_table.scan()

    # If items are still running quit and wait for the next invocation
    if len(resp['Items']) > 0:
        return return_code(200, {"status": "Items are still running"})

    # Otherwise if everything has completed, invoke the meta-package building function
    invoke_lambda(METAPACKAGE_BUILDER, None)

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
