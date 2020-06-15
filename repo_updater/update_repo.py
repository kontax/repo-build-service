import json
import os

from aws import start_ecs_task
from common import return_code

ECS_CLUSTER = os.environ.get('ECS_CLUSTER')
TASK_DEFN = os.environ.get('TASK_DEFN')
REPO_ARCH = os.environ.get('REPO_ARCH')
PERSONAL_REPO_BUCKET = os.environ.get('PERSONAL_REPO_BUCKET')
DEV_REPO_BUCKET = os.environ.get('DEV_REPO_BUCKET')


def lambda_handler(event, context):
    print(json.dumps(event))
    start_ecs_task(ECS_CLUSTER, TASK_DEFN, get_env_overrides(PERSONAL_REPO_BUCKET))
    start_ecs_task(ECS_CLUSTER, TASK_DEFN, get_env_overrides(DEV_REPO_BUCKET))
    return return_code(200, {'status': 'Repository updating'})


def get_env_overrides(bucket):
    return {
        'containerOverrides': [{
            'name': 'aur-pkg-update',
            'environment': [{
                'name': 'REMOTE_PATH',
                'value': f's3://{bucket}/{REPO_ARCH}'
            }]
        }]
    }
