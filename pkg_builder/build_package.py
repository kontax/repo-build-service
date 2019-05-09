import json
import os

from aws import send_to_queue, start_ecs_task, get_running_task_count
from common import return_code

BUILD_QUEUE = os.environ.get('BUILD_QUEUE')
ECS_CLUSTER = os.environ.get('ECS_CLUSTER')
TASK_DEFN = os.environ.get('TASK_DEFN')
TASK_FAMILY = os.environ.get('TASK_FAMILY')
MAX_TASK_COUNT = int(os.environ.get('MAX_TASK_COUNT'))


def lambda_handler(event, context):
    print(event)
    package_dict = event

    # Send the package to the build queue for any ECS instances to consume
    send_to_queue(BUILD_QUEUE, json.dumps(package_dict))

    # Start a new task if it's less than the max required
    if get_running_task_count(ECS_CLUSTER, TASK_FAMILY) < MAX_TASK_COUNT:
        start_ecs_task(ECS_CLUSTER, TASK_DEFN)

    return return_code(200, {'status': 'Package building'})
