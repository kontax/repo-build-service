import json
import os

from aws import send_to_queue, get_dynamo_resource
from common import return_code
from enums import Status

BUILD_FUNCTION_QUEUE = os.environ.get('BUILD_FUNCTION_QUEUE')
FANOUT_STATUS = os.environ.get('FANOUT_STATUS')


def lambda_handler(event, context):
    print(event)

    for record in event['Records']:
        msg = json.loads(record['body'])
        pkgbuild_url = msg['git_url']
        built_packages = get_built_packages()
        repo = msg['repo']
        build_event = {
            "PackageName": "GIT_REPO",
            "Repo": repo,
            "git_url": pkgbuild_url,
            "built_packages": built_packages
        }
        send_to_queue(BUILD_FUNCTION_QUEUE, json.dumps(build_event))

    return return_code(200, {'status': 'Metapackage sent to build queue'})


def get_built_packages():
    dynamo = get_dynamo_resource()
    fanout_table = dynamo.Table(FANOUT_STATUS)
    resp = fanout_table.scan()
    return [x['PackageName'] 
            for x in resp['Items'] 
            if x['BuildStatus'] == Status.Complete.name]

