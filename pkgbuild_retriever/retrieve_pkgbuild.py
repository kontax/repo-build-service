import json
import os
from urllib.parse import unquote

from botocore.vendored import requests
from aws import invoke_lambda

import commit_parser
import github_token_validator

NEXT_FUNC = os.environ.get("NEXT_FUNC")


def lambda_handler(event, context):
    print(event)
    
    # Validate github token
    response = github_token_validator.validate(event)
    if response['statusCode'] != 200:
        return response

    commit_payload = json.loads(unquote(event['body']).replace("payload=", ""))
    full_name = commit_parser.get_full_name(commit_payload)
    pkgbuild_location = commit_parser.get_pkgbuild_location(commit_payload)
    if pkgbuild_location is None:
        return {
            'statusCode': 401,
            'headers': { 'Content-Type': 'text/plain' },
            'body': 'No updated PKGBUILD found'
        }

    # Pull latest PKGBUILD
    pkgbuild_url = f"https://raw.githubusercontent.com/{full_name}/master/{pkgbuild_location}"
    pkgbuild = requests.get(pkgbuild_url).text
    github_repository = f"https://github.com/{full_name}.git"
    payload = {"payload": pkgbuild, "url": github_repository}

    response = invoke_lambda(NEXT_FUNC, payload)
    print(response)
    
    return {
        'statusCode': 200,
        'body': json.dumps('PKGBUILD extracted')
    }

