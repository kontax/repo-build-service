import json
import os

from aws import get_dynamo_resource, invoke_lambda, send_to_queue
from common import return_code
from enums import Status

FANOUT_QUEUE = os.environ.get('FANOUT_QUEUE')
PACKAGE_TABLE = os.environ.get('PACKAGE_TABLE')
BUILD_FUNC = os.environ.get('BUILD_FUNC')
PERSONAL_REPO = os.environ.get('PERSONAL_REPO')


def lambda_handler(event, context):
    print(event)
    # Get Dependencies
    deps = event['dependencies']
    url = event['url']

    # The dynamoDB table containing the running status of each package
    dynamo = get_dynamo_resource()
    package_table = dynamo.Table(PACKAGE_TABLE)

    # Put each one in the FANOUT_STATUS table with an "Initialized" status and add it to the queue
    build_packages = get_packages_to_build(package_table, deps)
    process_packages(build_packages, url)

    return return_code(200, {'packages': build_packages})


def get_packages_to_build(package_table, pkgbuild_packages):
    """ Compare the packages contained within the PKGBUILD to those already available in various repositories,
    returning only those which need to be built.

    :param (Table) package_table: The table containing all packages already available.
    :param (list) pkgbuild_packages: The collection of packages to check against those available.
    :return: A list of packages to send to the build queue.
    :rtype: list
    """
    print("Getting all current and new items in the table")
    resp = package_table.scan()
    all_packages = [x['PackageName'] for x in resp['Items']]
    to_build = list(set(pkgbuild_packages).difference(all_packages))
    return to_build


def process_packages(build_packages, metapackage_url):
    """ Add packages to be built to a build queue including the metapackage URL for building after completion.

    :param (list) build_packages: The collection of packages to build as a list of package names
    :param (str) metapackage_url: The URL of the repository for the metapackage to build after the rest
    """

    # Build the other packages
    for pkg in build_packages:
        process_package(pkg)

    # Store the metapackage URL for building on completion
    metapackage_msg = {
        "PackageName": "GIT_REPO",
        "BuildStatus": Status.Initialized.name,
        "IsMeta": True,
        "GitUrl": metapackage_url
    }
    send_to_queue(FANOUT_QUEUE, json.dumps(metapackage_msg))


def process_package(package):
    """Adds packages to the build queue and updates their status

    :param (str) package: The package to check
    """
    print(f"Building package: {package}")

    # Update the status to say the package is building
    message = {"PackageName": package, "BuildStatus": Status.Building.name, "IsMeta": False}
    send_to_queue(FANOUT_QUEUE, json.dumps(message))

    # Add them to the build queue and start the build VM
    invoke_lambda(BUILD_FUNC, {"PackageName": package, "Repo": PERSONAL_REPO})
