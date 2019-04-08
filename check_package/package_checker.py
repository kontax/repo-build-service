import json
import os

from boto3.dynamodb.conditions import Key

from aws import get_dynamo_resource, invoke_lambda
from enums import Status

FANOUT_CONTROLLER = os.environ.get('FANOUT_CONTROLLER')
PACKAGE_TABLE = os.environ.get('PACKAGE_TABLE')
BUILD_FUNC = os.environ.get('BUILD_FUNC')
PERSONAL_REPO = os.environ.get('PERSONAL_REPO')


def lambda_handler(event, context):
    print(event)
    package = event

    # The dynamoDB table containing the running status of each package
    dynamo = get_dynamo_resource()
    package_table = dynamo.Table(PACKAGE_TABLE)

    # Check whether the package exists or not
    resp = package_table.query(KeyConditionExpression=Key('PackageName').eq(package))

    # If they're built then ignore
    # Send it to the fanout controller marking its completion
    if len(resp['Items']) > 0:
        invoke_lambda(FANOUT_CONTROLLER, {"PackageName": package, "BuildStatus": Status.Complete.name})
        return return_code(200, {'status': 'Package exists already'})

    # If they're not then add them to the build queue and start the build VM
    invoke_lambda(BUILD_FUNC, {"PackageName": package, "Repo": PERSONAL_REPO})

    # Update the status to say the package is building
    invoke_lambda(FANOUT_CONTROLLER, {"PackageName": package, "BuildStatus": Status.Building.name})

    return return_code(200, {'status': 'Package sent to build queue'})


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
