import json
import os

from aws import get_dynamo_resource, send_to_queue
from common import return_code
from enums import Status

FANOUT_QUEUE = os.environ.get('FANOUT_QUEUE')
PACKAGE_TABLE = os.environ.get('PACKAGE_TABLE')
BUILD_FUNCTION_QUEUE = os.environ.get('BUILD_FUNCTION_QUEUE')
PERSONAL_REPO = os.environ.get('PERSONAL_REPO')


def lambda_handler(event, context):
    print(event)

    # The dynamoDB table containing the running status of each package
    dynamo = get_dynamo_resource()
    package_table = dynamo.Table(PACKAGE_TABLE)

    for record in event['Records']:

        json_record = json.loads(record['body'])
        # Get Dependencies
        deps = json_record['dependencies']
        git_url = json_record['git_url']
        git_branch = json_record['git_branch']
        stage = json_record['stage']

        # Put each one in the FANOUT_STATUS table with an "Initialized"
        # status and add it to the queue
        build_packages = get_packages_to_build(package_table, deps)
        process_packages(build_packages, git_url, git_branch, stage)

    return return_code(200, {'packages': build_packages})


def get_packages_to_build(package_table, pkgbuild_packages):
    """ Compare the packages contained within the PKGBUILD to those already
    available in various repositories, returning only those which need to be
    built.

    Args:
        package_table (Table):    The table containing all packages already
                                  available.
        pkgbuild_packages (list): The collection of packages to check against
                                  those available.

    Returns:
        (list): A list of packages to send to the build queue.
    """

    print("Getting all current and new items in the table")
    resp = package_table.scan()
    all_packages = [x['PackageName'] for x in resp['Items']]
    to_build = list(set(pkgbuild_packages).difference(all_packages))
    return to_build


def process_packages(build_packages, metapackage_url, branch, stage):
    """ Add packages to be built to a build queue including the metapackage
    URL for building after completion.

    Args:
        build_packages (list): The collection of packages to build as a list 
                               of package names
        metapackage_url (str): The URL of the repository for the metapackage 
                               to build after the rest
        branch (str):          Branch of the triggering git commit
        stage (str):           Whether the commit is from a prod or dev branch
    """

    # Build the other packages
    for pkg in build_packages:
        process_package(pkg, branch, stage)

    # Store the metapackage URL for building on completion
    metapackage_msg = {
        "PackageName": "GIT_REPO",
        "BuildStatus": Status.Initialized.name,
        "IsMeta": True,
        "GitUrl": metapackage_url,
        "Branch": branch,
        "Stage": stage
    }
    send_to_queue(FANOUT_QUEUE, json.dumps(metapackage_msg))


def process_package(package, branch, stage):
    """ Adds packages to the build queue and updates their status

    Args:
        package (str): The package to check
        branch (str):  Branch of the triggering git commit
        stage (str):   Whether the commit is from a prod or dev branch
    """

    print(f"Building package: {package}")

    # Update the status to say the package is building
    message = {
        "PackageName": package,
        "BuildStatus": Status.Building.name,
        "IsMeta": False,
        "Branch": branch,
        "Stage": stage
    }
    send_to_queue(FANOUT_QUEUE, json.dumps(message))

    # Add them to the build queue and start the build VM
    build_msg = {
        "PackageName": package,
        "Repo": PERSONAL_REPO,
        "Branch": branch,
        "Stage": stage
    }
    send_to_queue(BUILD_FUNCTION_QUEUE, json.dumps(build_msg))

