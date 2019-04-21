import json
import os

from aws import invoke_lambda

BUILD_FUNC = os.environ.get('BUILD_FUNC')
PERSONAL_REPO = os.environ.get('PERSONAL_REPO')


def lambda_handler(event, context):
    print(event)
    pkgbuild_url = event['git_url']
    invoke_lambda(BUILD_FUNC, {"PackageName": "GIT_REPO", "Repo": PERSONAL_REPO, "git_url": pkgbuild_url})
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
