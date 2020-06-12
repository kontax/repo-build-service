import boto3
import json
import os
import pytest
import sys

from datetime import datetime
from io import BytesIO
from mock import patch
from moto import mock_dynamodb2

# Get the root path of the project to allow importing
ROOT_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
sys.path.append(ROOT_PATH)
sys.path.append(os.path.join(ROOT_PATH, "tests"))
sys.path.append(os.path.join(ROOT_PATH, "package_updater"))
sys.path.append(os.path.join(ROOT_PATH, "src/python"))

from test_common import dynamodb_table, pkgcomp

PERSONAL_REPO = 'https://test-repo.s3.amazonaws.com'
PERSONAL_REPO_DEV = 'https://test-repo-dev.s3.amazonaws.com'

TEMPLATE = os.path.join(ROOT_PATH, 'tests/inputs/sqs-template.json')
INPUTS = {
    'prod_test': 'tests/inputs/package_updater/prod_test.json',
    'dev_test': 'tests/inputs/package_updater/dev_test.json',
}


def get_input(input_name):
    input_location = INPUTS[input_name]
    filename = os.path.join(ROOT_PATH, input_location)

    with open(TEMPLATE, 'r') as f:
        output = json.loads(f.read())

    with open(filename, 'r') as f:
        data = f.read()
        for record in output["Records"]:
            record['body'] = data

    return output


class UrlOpenMockContext:
    """ Mock context for urlopen """

    def __init__(self, *args, **kwargs):
        self.url = args[0] if isinstance(args[0], str) \
                   else args[0].get_full_url()

    def __enter__(self, *args, **kwargs):
        if self.url == PERSONAL_REPO:
            return open('tests/inputs/package_updater/test-repo.db', 'rb')
        elif self.url == PERSONAL_REPO_DEV:
            return open('tests/inputs/package_updater/test-repo-dev.db', 'rb')
        else:
            raise Exception(self.url)

    def __exit__(self, *args, **kwargs):
        pass


@patch('urllib.request.urlopen', UrlOpenMockContext)
def test_packages_in_prod_repo_get_added_and_removed(dynamodb_table):

    pre_packages = [
        {'Repository': 'personal-prod', 'PackageName': 'couldinho-base'},
        {'Repository': 'personal-prod', 'PackageName': 'ida-free'},
        {'Repository': 'personal-dev', 'PackageName': 'couldinho-base'},
        {'Repository': 'personal-dev', 'PackageName': 'rr'}
    ]

    post_packages = [
        {'Repository': 'personal-prod', 'PackageName': '010editor'},
        {'Repository': 'personal-prod', 'PackageName': 'couldinho-base'},
        {'Repository': 'personal-prod', 'PackageName': 'couldinho-desktop'},
        {'Repository': 'personal-prod', 'PackageName': 'couldinho-laptop'},
        {'Repository': 'personal-prod', 'PackageName': 'couldinho-sec'},
        {'Repository': 'personal-prod', 'PackageName': 'gef-git'},
        {'Repository': 'personal-prod', 'PackageName': 'ghidra-bin'},
        {'Repository': 'personal-prod', 'PackageName': 'mce-dev'},
        {'Repository': 'personal-prod', 'PackageName': 'pass-git-helper'},
        {'Repository': 'personal-prod', 'PackageName': 'vivaldi'},
        {'Repository': 'personal-dev', 'PackageName': 'couldinho-base'},
        {'Repository': 'personal-dev', 'PackageName': 'rr'},
    ]

    os.environ['PACKAGE_TABLE'] = 'package-table'

    packages = dynamodb_table.scan()
    assert pkgcomp(packages['Items'], pre_packages)

    from package_updater.update_packages import lambda_handler

    message = get_input("prod_test")
    lambda_handler(message, None)

    packages = dynamodb_table.scan()
    assert pkgcomp(packages['Items'], post_packages)


@patch('urllib.request.urlopen', UrlOpenMockContext)
def test_packages_in_dev_repo_get_added_and_removed(dynamodb_table):

    pre_packages = [
        {'Repository': 'personal-prod', 'PackageName': 'couldinho-base'},
        {'Repository': 'personal-prod', 'PackageName': 'ida-free'},
        {'Repository': 'personal-dev', 'PackageName': 'couldinho-base'},
        {'Repository': 'personal-dev', 'PackageName': 'rr'}
    ]

    post_packages = [
        {'Repository': 'personal-prod', 'PackageName': 'couldinho-base'},
        {'Repository': 'personal-prod', 'PackageName': 'ida-free'},
        {'Repository': 'personal-dev', 'PackageName': 'couldinho-base'},
        {'Repository': 'personal-dev', 'PackageName': 'couldinho-desktop'},
        {'Repository': 'personal-dev', 'PackageName': 'couldinho-laptop'},
        {'Repository': 'personal-dev', 'PackageName': 'couldinho-sec'},
        {'Repository': 'personal-dev', 'PackageName': '010editor'},
        {'Repository': 'personal-dev', 'PackageName': 'gef-git'},
        {'Repository': 'personal-dev', 'PackageName': 'mce-dev'},
        {'Repository': 'personal-dev', 'PackageName': 'pass-git-helper'},
        {'Repository': 'personal-dev', 'PackageName': 'pwngdb'},
        {'Repository': 'personal-dev', 'PackageName': 'vivaldi'},
    ]

    os.environ['PACKAGE_TABLE'] = 'package-table'

    packages = dynamodb_table.scan()
    assert pkgcomp(packages['Items'], pre_packages)

    from package_updater.update_packages import lambda_handler

    message = get_input("dev_test")
    lambda_handler(message, None)

    packages = dynamodb_table.scan()
    assert pkgcomp(packages['Items'], post_packages)

