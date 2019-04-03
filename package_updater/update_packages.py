import json
import os

import boto3

from arch_packages import get_packages
from best_mirror import get_best_mirror

PACKAGE_TABLE = os.environ['PACKAGE_TABLE']
COUNTRIES = os.environ.get('COUNTRIES')
REPOS = ["core", "extra", "community"]
PERSONAL_REPO = os.environ.get('PERSONAL_REPO')


def lambda_handler(event, context):
    response_body = {}

    # Get the best mirror containing the packages
    mirrors = get_best_mirror(COUNTRIES.split(','), REPOS)
    mirrors.append(PERSONAL_REPO)

    # The dynamoDB table containing the packages
    dynamo = get_dynamo_resource()
    table = dynamo.Table(PACKAGE_TABLE)

    # Get any new packages that have been added to the repositories and upload them
    resp = table.scan()
    response_body['current'] = len(resp['Items'])
    new_packages = add_new_packages(mirrors, table)
    response_body['new'] = len(new_packages) - response_body['current']

    # Remove any packages no longer contained within the repositories
    resp = table.scan()
    all_packages = [x['PackageName'] for x in resp['Items']]
    to_delete = delete_old_packages(all_packages, new_packages, table)
    response_body['deleted'] = len(to_delete)

    # Return the number of changes being made
    return return_code(200, response_body)


def get_dynamo_resource():
    """Get a dynamodb resource depending on which environment the function is running in"""
    if os.getenv("AWS_SAM_LOCAL"):
        dynamo = boto3.resource('dynamodb', endpoint_url="http://dynamodb:8000")
    else:
        dynamo = boto3.resource('dynamodb')
    return dynamo


def add_new_packages(mirrors, table):
    """Add new packages to the database

    Args:
        mirrors (list): A list of mirrors to download the packages from
        table (dynamo.Table): The dynamodb table to update

    Returns:
        list: A collection of all packages within the mirrors.
    """
    new_packages = []
    for mirror in mirrors:
        packages = get_packages(mirror)
        for package in packages:
            table.update_item(Key={'PackageName': package})
            new_packages.append(package)
    return new_packages


def delete_old_packages(all_packages, new_packages, table):
    """Deletes packages that are no longer within the mirror from the database

    Args:
        all_packages (list): A list of all current packages within the database
        new_packages (list): A list of all the new packages within the repository
        table (dynamo.Table): The dynamodb table to delete packages from

    Returns:
        list: The collection of packages removed from the database
    """
    to_delete = set(all_packages).difference(new_packages)
    for package in to_delete:
        table.delete_item(Key={'PackageName': package})
    return to_delete


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

