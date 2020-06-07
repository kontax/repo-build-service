import json
import os
from concurrent.futures import ThreadPoolExecutor
from boto3.dynamodb.conditions import Key

from arch_packages import get_packages
from aws import get_dynamo_resource
from best_mirror import get_best_mirror
from common import return_code

PACKAGE_TABLE = os.environ.get('PACKAGE_TABLE')
COUNTRIES = os.environ.get('COUNTRIES')
PERSONAL_REPO = os.environ.get('PERSONAL_REPO')
PERSONAL_REPO_DEV = os.environ.get('PERSONAL_REPO_DEV')
REPOS = ["core", "extra", "community"]


def lambda_handler(event, context):
    response_body = {
        'current': {},
        'new': {},
        'deleted': {}
    }

    # Get the best mirror containing the packages
    mirrors = get_best_mirror(COUNTRIES.split(','), REPOS)
    mirrors.append({'repo': 'personal-prod', 'mirror': PERSONAL_REPO})
    mirrors.append({'repo': 'personal-dev', 'mirror': PERSONAL_REPO_DEV})

    # The dynamoDB table containing the packages
    dynamo = get_dynamo_resource()
    table = dynamo.Table(PACKAGE_TABLE)

    # Get any new packages that have been added to the repositories and upload them
    print("Getting all current items in the table")
    for mirror in mirrors:
        repo_name = mirror['repo']
        response_body['current'][repo_name] = get_current_package_count(table, repo_name)

    new_packages = add_new_packages(mirrors, table)
    for repo in new_packages:
        repo_name = repo['repo']
        print(f"Adding new packages to {repo_name}")
        new_pkg_count = len(repo['packages'])
        new_diff = new_pkg_count - response_body['current'][repo_name]
        new_diff = new_diff if new_diff > 0 else 0
        print(f"Added {new_diff} items to {repo_name}")
        response_body['new'][repo_name] = new_diff

    # Remove any packages no longer contained within the repositories
    for repo in new_packages:
        repo_name = repo['repo']
        print(f"Removing packages from {repo_name}")
        resp = table.query(KeyConditionExpression=Key('Repository').eq(repo_name))
        all_packages = [x['PackageName'] for x in resp['Items']]
        to_delete = delete_old_packages(repo_name, all_packages, repo['packages'], table)
        print(f"Removed {len(to_delete)} items from {repo_name}")
        response_body['deleted'][repo_name] = len(to_delete)

    # Return the number of changes being made
    print(json.dumps(response_body))
    return return_code(200, response_body)


def get_current_package_count(table, repo_name):
    """ Get the current number of packages within a repository

    Args:
        table (dynamodb.Table): Table containing the packages
        repo_name (str): Name of the repository containing the packages

    Returns:
        int: Number of packages within the repository
    """

    resp = table.query(KeyConditionExpression=Key('Repository').eq(repo_name))
    num_packages = len(resp['Items'])
    print(f"Currently {num_packages} in {repo_name}")
    return num_packages


def add_new_packages(mirrors, table):
    """ Add new packages to the database

    Args:
        mirrors (list): A list of mirrors to download the packages from
        table (dynamodb.Table): The dynamodb table to update

    Returns:
        list: A collection of all packages within the mirrors.
    """

    new_packages = []
    with ThreadPoolExecutor() as executor:
        new_packages.extend([x for x in executor.map(get_packages, mirrors)])

    primary_key = ['Repository', 'PackageName']
    with table.batch_writer(overwrite_by_pkeys=primary_key) as batch:
        for i in new_packages:
            for p in i['packages']:
                item = {'Repository': i['repo'], 'PackageName': p}
                batch.put_item(Item=item)

    return new_packages


def delete_old_packages(repo_name, all_packages, new_packages, table):
    """ Deletes packages that are no longer within the mirror from the database

    Args:
        repo_name (str): Name of the repository containing the packages
        all_packages (list): Lst of all current packages within the database
        new_packages (list): Lst of all the new packages within the repository
        table (dynamo.Table): The dynamodb table to delete packages from

    Returns:
        list: The collection of packages removed from the database
    """

    to_delete = set(all_packages).difference(new_packages)
    with table.batch_writer() as batch:
        for package in to_delete:
            key = {'Repository': repo_name, 'PackageName': package}
            batch.delete_item(Key=key)
    return to_delete
