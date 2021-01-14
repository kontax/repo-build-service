import json
import os

from boto3.dynamodb.conditions import Key
from concurrent.futures import ThreadPoolExecutor
from urllib.request import urlopen
from urllib.parse import urlencode

from aws import get_dynamo_resource, send_to_queue
from common import return_code
from enums import Status

FANOUT_QUEUE = os.environ.get('FANOUT_QUEUE')
PACKAGE_TABLE = os.environ.get('PACKAGE_TABLE')
BUILD_FUNCTION_QUEUE = os.environ.get('BUILD_FUNCTION_QUEUE')
PERSONAL_REPO = os.environ.get('PERSONAL_REPO')
DEV_REPO = os.environ.get('DEV_REPO')
OFFICIAL_PKG_API = "https://www.archlinux.org/packages/search/json/"


def lambda_handler(event, context):
    print(json.dumps(event))

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
        build_packages = get_packages_to_build(package_table, deps, stage)

        if len(build_packages) > 0:
            print(f"Building the following packages: {build_packages}")
        else:
            print("No new packages to build")

        process_packages(build_packages, git_url, git_branch, stage)

    return return_code(200, {'packages': build_packages})


def get_packages_to_build(package_table, pkgbuild_packages, stage):
    """ Compare the packages contained within the PKGBUILD to those already
    available in various repositories, returning only those which need to be
    built.

    Args:
        package_table (Table):    The table containing all packages already
                                  available.
        pkgbuild_packages (list): The collection of packages to check against
                                  those available.
        stage (str):              Whether the dev or prod repo is in use.

    Returns:
        (list): A list of packages to send to the build queue.
    """

    print("Check packages against official repositories")
    initial_to_build = []
    with ThreadPoolExecutor() as executor:
        pkgs = [x for x in \
                executor.map(check_packages_against_official, pkgbuild_packages) \
                if x is not None]
        initial_to_build.extend(pkgs)

    print("Getting all current and new items in the table")

    # Get the list of repositories we're pulling from
    repo_name = PERSONAL_REPO if stage == 'prod' else DEV_REPO

    # Pull the list of packages within those repos
    resp = package_table.query(KeyConditionExpression=Key('Repository').eq(repo_name))
    aur_packages = [x['PackageName'] for x in resp['Items']]

    # Retrieve those packages that aren't available yet
    to_build = list(set(initial_to_build).difference(aur_packages))
    return to_build


def check_packages_against_official(pkgbuild_package):
    """ Check which packages are already contained within the official repos

    Args:
        pkgbuild_package (str): Name of package to check repository for

    Returns:
        list: List of packages not already contained in official repos
    """

    to_build = []
    params = urlencode({'name': pkgbuild_package})
    url = f"{OFFICIAL_PKG_API}?{params}"
    print(f"Checking official packages from {url}")
    with urlopen(url) as resp:
        data = json.loads(resp.read())
        print("Results from official packages:")
        print(json.dumps(data))
        assert len(data['results']) <= 1
        if len(data['results']) == 0:
            return pkgbuild_package

    return None


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
    repo = PERSONAL_REPO if branch == 'master' else DEV_REPO
    metapackage_msg = {
        "PackageName": "GIT_REPO",
        "BuildStatus": Status.Initialized.name,
        "IsMeta": True,
        "GitUrl": metapackage_url,
        "repo": repo
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

    repo = PERSONAL_REPO if branch == 'master' else DEV_REPO

    # Update the status to say the package is building
    message = {
        "PackageName": package,
        "BuildStatus": Status.Building.name,
        "repo": repo,
        "IsMeta": False
    }
    send_to_queue(FANOUT_QUEUE, json.dumps(message))

    # Add them to the build queue and start the build VM
    build_msg = {
        "PackageName": package,
        "Repo": repo
    }
    send_to_queue(BUILD_FUNCTION_QUEUE, json.dumps(build_msg))

