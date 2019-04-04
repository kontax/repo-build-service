import boto3
import json
import os

from aws import get_dynamo_resource, send_to_queue, invoke_lambda
from boto3.dynamodb.conditions import Key
from enums import Status


FANOUT_CONTROLLER = os.environ.get('FANOUT_CONTROLLER')
PACKAGE_TABLE = os.environ.get('PACKAGE_TABLE')
BUILD_QUEUE = os.environ.get('BUILD_QUEUE')
ECS_CLUSTER = os.environ.get('ECS_CLUSTER')
TASK_DEFN = os.environ.get('TASK_DEFN')


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
        invoke_lambda(FANOUT_CONTROLLER, {"PackageName": package, "Status": Status.Complete.name})
        return return_code(200, {'status': 'Package exists already'})

    # If they're not then add them to the build queue and start the build VM
    _start_ecs_task(ECS_CLUSTER, TASK_DEFN)
    send_to_queue(BUILD_QUEUE, package)

    # Update the status to say the package is building
    invoke_lambda(FANOUT_CONTROLLER, {"PackageName": package, "Status": Status.Building.name})

    return return_code(200, {'status': 'Package building'})


def _start_ecs_task(cluster, task_definition):
    """Starts a new ECS task within a Fargate cluster to build the packages

    The ECS task pulls each package built one by one from the queue and adds
    them to the personal repository.

    Args:
        cluster (str): The name of the cluster to start the task in
        task_definition (str); The name of the task definition to run
    """
    print(f"Starting new ECS task to build the package(s)")

    client = boto3.client('ecs')
    response = client.run_task(
        cluster=cluster,
        launchType='FARGATE',
        taskDefinition=task_definition,
        count=1,
        platformVersion='LATEST',
        networkConfiguration={
            'awsvpcConfiguration': {
                'subnets': [
                    'subnet-9f4b60c6'
                ],
                'assignPublicIp': 'ENABLED'
            }
        }
    )
    print(f"Run task complete: {str(response)}")


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
