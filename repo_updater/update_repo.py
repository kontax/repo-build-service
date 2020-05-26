import json
import os

from aws import start_ecs_task
from common import return_code

ECS_CLUSTER = os.environ.get('ECS_CLUSTER')
TASK_DEFN = os.environ.get('TASK_DEFN')


def lambda_handler(event, context):
    print(json.dumps(event))
    start_ecs_task(ECS_CLUSTER, TASK_DEFN)
    return return_code(200, {'status': 'Repository updating'})
