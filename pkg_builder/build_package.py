import json
import os

import boto3
from aws_xray_sdk.core import patch_all

from aws import send_to_queue

if "AWS_SAM_LOCAL" not in os.environ:
    patch_all()

BUILD_QUEUE = os.environ.get('BUILD_QUEUE')
ECS_CLUSTER = os.environ.get('ECS_CLUSTER')
TASK_DEFN = os.environ.get('TASK_DEFN')


def lambda_handler(event, context):
    print(event)
    package_dict = event

    _start_ecs_task(ECS_CLUSTER, TASK_DEFN)
    send_to_queue(BUILD_QUEUE, json.dumps(package_dict))

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
