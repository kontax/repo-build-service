import json
import os

from botocore.vendored import requests

from aws import invoke_lambda

BUILD_FUNC = os.environ.get('BUILD_FUNC')
PERSONAL_REPO = os.environ.get('PERSONAL_REPO')


def lambda_handler(event, context):
    print(event)

    pkgbuild_url = event['url']
    pkgbuild = requests.get(pkgbuild_url).text

    invoke_lambda(BUILD_FUNC, {"PackageName": "PKGBUILD_METAPACKGE", "Repo": PERSONAL_REPO, "PKGBUILD": pkgbuild})

    return return_code(200, {'status': 'Metapackage sent to build queue'})


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
