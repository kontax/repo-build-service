import json
import os
import requests
from urllib.parse import unquote

import github_token_validator
from aws import invoke_lambda
from common import return_code

NEXT_FUNC = os.environ.get("NEXT_FUNC")
STAGE_NAME = os.environ.get("STAGE_NAME")


def lambda_handler(event, context):
    print(event)
    branch_check = 'master' if STAGE_NAME == 'prod' else STAGE_NAME

    # Validate github token
    response = github_token_validator.validate(event)
    if response['statusCode'] != 200:
        return response

    commit_payload = json.loads(unquote(event['body']).replace("payload=", ""))
    full_name = get_full_name(commit_payload)

    branch = commit_payload['ref'].replace('refs/heads/', '')
    if branch_check != branch:
        return return_code(401, 
            {'headers': {'Content-Type': 'text/plain'}, 
            'body': f'branch name {branch_check} does not match stage {branch}'}
        )

    pkgbuild_location = get_pkgbuild_location(commit_payload)
    if pkgbuild_location is None:
        print("No PKGBUILD commit found, exiting")
        return return_code(401, {'headers': {'Content-Type': 'text/plain'}, 'body': 'No updated PKGBUILD found'})

    # Pull latest PKGBUILD
    print(f"Found PKGBUILD at {pkgbuild_location}")
    pkgbuild_url = f"https://raw.githubusercontent.com/{full_name}/master/{pkgbuild_location}"
    pkgbuild = requests.get(pkgbuild_url).text
    github_repository = f"https://github.com/{full_name}.git"
    payload = {"payload": pkgbuild, "url": github_repository}

    response = invoke_lambda(NEXT_FUNC, payload)
    print(response)

    return return_code(200, {'status': 'PKGBUILD extracted'})


def get_pkgbuild_location(payload):
    if 'commits' not in payload:
        return None

    pkgbuild = [x for x in payload['commits'][0]['modified'] if x.endswith("PKGBUILD")]
    if len(pkgbuild) == 0:
        return None

    return pkgbuild[0]


def get_full_name(payload):
    return payload['repository']['full_name']
