import json
import os

from aws import send_to_queue, start_ecs_task

BUILD_QUEUE = os.environ.get('BUILD_QUEUE')
ECS_CLUSTER = os.environ.get('ECS_CLUSTER')
TASK_DEFN = os.environ.get('TASK_DEFN')


def lambda_handler(event, context):
    print(event)
    package_dict = event

    start_ecs_task(ECS_CLUSTER, TASK_DEFN)
    send_to_queue(BUILD_QUEUE, json.dumps(package_dict))

    return return_code(200, {'status': 'Package building'})


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
