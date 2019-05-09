import os

from aws import invoke_lambda, get_dynamo_resource
from common import return_code
from enums import Status

BUILD_FUNC = os.environ.get('BUILD_FUNC')
PERSONAL_REPO = os.environ.get('PERSONAL_REPO')
FANOUT_STATUS = os.environ.get('FANOUT_STATUS')


def lambda_handler(event, context):
    print(event)
    pkgbuild_url = event['git_url']
    built_packages = get_built_packages()
    build_event = {
        "PackageName": "GIT_REPO",
        "Repo": PERSONAL_REPO,
        "git_url": pkgbuild_url,
        "built_packages": built_packages
    }
    invoke_lambda(BUILD_FUNC, build_event)
    return return_code(200, {'status': 'Metapackage sent to build queue'})


def get_built_packages():
    dynamo = get_dynamo_resource()
    fanout_table = dynamo.Table(FANOUT_STATUS)
    resp = fanout_table.scan()
    return [x['PackageName'] for x in resp['Items'] if x['BuildStatus'] == Status.Complete.name]
