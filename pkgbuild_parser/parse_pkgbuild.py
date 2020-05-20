import json
import os
import re
import string

from aws import send_to_queue
from common import return_code

NEXT_QUEUE = os.environ.get('NEXT_QUEUE')
ALLOWED_CHARS = set(string.ascii_lowercase + string.digits + '@._+-')


def lambda_handler(event, context):
    print(event)
    for record in event['Records']:
        run(record['body'])
    return return_code(200, {'status': "PKGBUILD added to queue"})


def _get_dependencies(pkgbuild):
    """ Extracts items from within 'depends()' sections in the PKGBUILD

    The PKGBUILD is looped through line by line, noting when we are within a 
    depends() statement and extracting every word prior to a comment (#) until 
    the closing bracket. Multiple packages on a single line are handled by 
    being split by whitespace.

    Args:
        pkgbuild (str): The PKGBUILD file

    Returns:
        list: The collection of dependencies for each metapackage
    """

    print(f"Getting all dependencies within PKGBUILD file")
    dependencies = []

    within_depends = False
    for line in pkgbuild.split('\n'):

        # Remove any unnecessary whitespace
        line = line.strip()

        # Search until we find depends
        if not within_depends and line.startswith('depends'):
            within_depends = True
            continue

        # Extract the packages
        if within_depends and line != ')':
            # Remove comments
            pkgs = [pkg for pkg in re.sub('#.*', '', line).strip().split(' ')
                    if len(pkg) > 0]

            # Ensure there are no issues with the packages by checking if there
            # are any disallowed characters within the package name.
            assert(all([set(x) <= ALLOWED_CHARS for x in pkgs]))
            dependencies.extend(pkgs)

        # Continue until the closing bracket
        if within_depends and line == ')':
            within_depends = False

    print(f"Pulled {len(dependencies)} dependencies")
    return dependencies


def run(pkgbuild_file):
    """ Extracts metapackages and their dependencies from a PKGBUILD

    Args:
        pkgbuild_file (json): The PKGBUILD file for the metapackages

    Returns:
        list: A list of packages required by the metapackages
    """

    # Convert the event to JSON
    pkgbuild_json = json.loads(pkgbuild_file)

    deps = _get_dependencies(pkgbuild_json['payload'])
    pkgbuild_json['dependencies'] = deps
    pkgbuild_json.pop('payload', None)

    # Send to next function
    print(f"NEXT_QUEUE: {NEXT_QUEUE}")
    send_to_queue(NEXT_QUEUE, json.dumps(pkgbuild_json))

