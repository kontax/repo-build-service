import json
import os
from concurrent.futures import ThreadPoolExecutor

from arch_packages import get_packages
from aws import get_dynamo_resource
from best_mirror import get_best_mirror
from common import return_code

PACKAGE_TABLE = os.environ.get('PACKAGE_TABLE')
COUNTRIES = os.environ.get('COUNTRIES')
PERSONAL_REPO = os.environ.get('PERSONAL_REPO')
REPOS = ["core", "extra", "community"]


def lambda_handler(event, context):
    response_body = {}

    # Get the best mirror containing the packages
    mirrors = get_best_mirror(COUNTRIES.split(','), REPOS)
    mirrors.append(PERSONAL_REPO)

    # The dynamoDB table containing the packages
    dynamo = get_dynamo_resource()
    table = dynamo.Table(PACKAGE_TABLE)

    # Get any new packages that have been added to the repositories and upload them
    print("Getting all current items in the table")
    resp = table.scan()
    response_body['current'] = len(resp['Items'])

    print("Adding new packages")
    new_packages = add_new_packages(mirrors, table)
    new_diff = len(new_packages) - response_body['current']
    response_body['new'] = new_diff if new_diff > 0 else 0

    # Remove any packages no longer contained within the repositories
    print("Getting all current and new items in the table")
    resp = table.scan()
    all_packages = [x['PackageName'] for x in resp['Items']]

    print("Removing old packages")
    to_delete = delete_old_packages(all_packages, new_packages, table)
    response_body['deleted'] = len(to_delete)

    # Return the number of changes being made
    print(response_body)
    return return_code(200, response_body)


def add_new_packages(mirrors, table):
    """Add new packages to the database

    Args:
        mirrors (list): A list of mirrors to download the packages from
        table (dynamo.Table): The dynamodb table to update

    Returns:
        list: A collection of all packages within the mirrors.
    """
    new_packages = []
    with ThreadPoolExecutor() as executor:
        new_packages.extend([x for x in executor.map(get_packages, mirrors)])

    # ThreadPoolExecutors returns a list of lists, which needs to be unwrapped here
    new_packages = [item for sublist in new_packages for item in sublist]

    with table.batch_writer(overwrite_by_pkeys=['PackageName']) as batch:
        for i in new_packages:
            batch.put_item(Item={'PackageName': i})

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
    with table.batch_writer() as batch:
        for package in to_delete:
            batch.delete_item(Key={'PackageName': package})
    return to_delete
