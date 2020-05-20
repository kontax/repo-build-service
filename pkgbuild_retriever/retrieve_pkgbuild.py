import json
import os
import requests
import sys
from urllib.parse import unquote

import github_token_validator
from aws import send_to_queue
from common import return_code

NEXT_QUEUE = os.environ.get("NEXT_QUEUE")

def lambda_handler(event, context):

    # Validate github token
    response = github_token_validator.validate(event)
    if response['statusCode'] != 200:
        print(f"Token not valid: {response}")
        return response

    commit_payload = json.loads(unquote(event['body']).replace("payload=", ""))
    full_name = get_full_name(commit_payload)

    branch = commit_payload['ref'].replace('refs/heads/', '')
    stage = 'prod' if branch == 'master' else 'dev'

    pkgbuild_location = get_pkgbuild_location(commit_payload)
    if pkgbuild_location is None:
        print("No PKGBUILD commit found, exiting")
        retval = {
            'headers': { 'Content-Type': 'text/plain' }, 
            'body': 'No updated PKGBUILD found'
        }
        return return_code(401, retval)

    # Pull latest PKGBUILD
    print(f"Found PKGBUILD at {pkgbuild_location}")
    pkgbuild_url = f"https://raw.githubusercontent.com/{full_name}/{branch}/{pkgbuild_location}"
    pkgbuild = requests.get(pkgbuild_url).text
    github_repository = f"https://github.com/{full_name}.git"
    payload = json.dumps({
        "payload": pkgbuild,
        "git_url": github_repository,
        "git_branch": branch,
        "stage": stage
    })

    send_to_queue(NEXT_QUEUE, payload)

    return return_code(200, {'status': 'PKGBUILD extracted'})


def get_pkgbuild_location(payload):
    if 'commits' not in payload or len(payload['commits']) == 0:
        return None

    pkgbuild = [x for x in payload['commits'][0]['modified'] if x.endswith("PKGBUILD")]
    if len(pkgbuild) == 0:
        return None

    return pkgbuild[0]


def get_full_name(payload):
    return payload['repository']['full_name']
