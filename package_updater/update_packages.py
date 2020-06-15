import json
import os
import time

from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

from arch_packages import get_packages
from aws import get_dynamo_resource
from common import return_code

PACKAGE_TABLE = os.environ.get('PACKAGE_TABLE')
DYNAMODB_MAX_RETRIES = 12


def lambda_handler(event, context):
    """ Function used to update packages within the packages table.

    The package table contains details on the packages within personal
    repository. This table is updated each run so as to keep track of when
    new packages need to be built, or they already exist. The official repo's
    do not need to be included as they can be queried from the API.

    An example of the event passed to this function is as follows:
    {
        'repository': 'personal-prod',
        'url': 'https://s3-eu-west-1.amazonaws.com/personalrepo/x64_86/repo.db
    }
    This is wrapped in an SQS message.

    Args:
        event (dict): Contains packages to be updated from SNS
        context (object): Lambda context runtime methods and attributes

    Returns:
        dict: HTTP response based on success of the function
    """

    print(json.dumps(event))
    retval = {}
    for record in event['Records']:
        msg = json.loads(record['body'])
        repo_name = msg['repository']
        url = msg['url']
        retval[repo_name] = update_repository(repo_name, url)

    return return_code(200, retval)


def update_repository(repo_name, url):
    response_body = {}

    # The dynamoDB table containing the packages
    dynamo = get_dynamo_resource()
    table = dynamo.Table(PACKAGE_TABLE)

    # Get any new packages that have been added to the repositories and upload them
    print("Getting all current items in the table")
    response_body['current'] = get_current_package_count(table, repo_name)

    new_packages = add_new_packages(repo_name, url, table)
    print(f"Adding new packages to {repo_name}")
    new_pkg_count = len(new_packages['packages'])
    new_diff = new_pkg_count - response_body['current']
    new_diff = new_diff if new_diff > 0 else 0
    print(f"Added {new_diff} items to {repo_name}")
    response_body['new'] = new_diff

    # Remove any packages no longer contained within the repositories
    print(f"Removing packages from {repo_name}")
    resp = table.query(KeyConditionExpression=Key('Repository').eq(repo_name))
    all_packages = [x['PackageName'] for x in resp['Items']]
    to_delete = delete_old_packages(repo_name, all_packages, new_packages['packages'], table)
    print(f"Removed {len(to_delete)} items from {repo_name}")
    response_body['deleted'] = len(to_delete)

    # Return the number of changes being made
    print(json.dumps(response_body))
    return response_body


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


def add_new_packages(repo_name, url, table):
    """ Add new packages to the database

    Args:
        repo_name (str): Name of the reponew packages are being added for
        url (str): Mirror of the repository to download the package DB from
        table (dynamodb.Table): The dynamodb table to update

    Returns:
        list: A collection of all packages within the mirror.
    """

    new_pkgs = get_packages({'repo': repo_name, 'mirror': url})

    primary_key = ['Repository', 'PackageName']
    with table.batch_writer(overwrite_by_pkeys=primary_key) as batch:
        for p in new_pkgs['packages']:
            retry_count = 0
            while retry_count <= DYNAMODB_MAX_RETRIES:
                try:
                    item = {'Repository': new_pkgs['repo'], 'PackageName': p}
                    batch.put_item(Item=item)
                except ClientError:
                    retry_count += 1
                    time.sleep(2 ** retry_count)
                    continue
                else:
                    retry_count = 0
                    break
            else:
                raise RuntimeError("Write operation failed - AWS errors")

    return new_pkgs


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
