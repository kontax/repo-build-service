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
sys.path.append(os.path.join(ROOT_PATH, "package_updater"))
sys.path.append(os.path.join(ROOT_PATH, "src/python"))

MIRROR = "https://mirror.rackspace.com/archlinux/$repo/os/$arch"
PERSONAL_REPO = 'https://test-repo.s3.amazonaws.com'
PKG_URL = "https://www.archlinux.org/mirrors/status/json/"


def dummy_url():
    msg = {
        'cutoff': 86400,
        'last_check': datetime.today().strftime('%Y-%m-%dT%H:%M:%SZ'),
        'num_checks': 10,
        'check_frequency': 100,
        'urls': [{
            'url': 'https://mirror.rackspace.com/archlinux/',
            'protocol': 'https',
            'last_sync': datetime.today().strftime('%Y-%m-%dT%H:%M:%SZ'),
            'completion_pct': 1.0,
            'delay': 2479,
            'duration_avg': 0.2864674810153335,
            'duration_stddev': 0.16080441224983974,
            'score': 1.1358830043762842,
            'active': True,
            'country': '',
            'country_code': 'IE',
            'isos': True,
            'ipv4': True,
            'ipv6': False,
            'details': 'https://www.archlinux.org/mirrors/rackspace.com/1316/'
        }],
        'version': 3
    }
    return json.dumps(msg).encode('utf-8')


class UrlOpenMockContext:
    """ Mock context for urlopen """

    def __init__(self, *args, **kwargs):
        self.url = args[0] if isinstance(args[0], str) \
                   else args[0].get_full_url()

    def __enter__(self, *args, **kwargs):
        if self.url == PKG_URL:
            return BytesIO(dummy_url())
        elif 'core.db' in self.url:
            return open('tests/inputs/package_updater/core.db', 'rb')
        elif 'extra.db' in self.url:
            return open('tests/inputs/package_updater/extra.db', 'rb')
        elif 'community.db' in self.url:
            return open('tests/inputs/package_updater/community.db', 'rb')
        elif self.url == PERSONAL_REPO:
            return open('tests/inputs/package_updater/test-repo.db', 'rb')
        else:
            raise Exception(self.url)

    def __exit__(self, *args, **kwargs):
        pass


@pytest.fixture()
def dynamodb_table():

    table_name = 'package-table'

    # List of packages that already exist in the table
    packages = ['bash', 'linux', 'vim', 'zsh', 'xorg-server',
                'chromium', 'couldinho-base']

    with mock_dynamodb2():
        client = boto3.client('dynamodb')
        client.create_table(
            TableName=table_name,
            AttributeDefinitions=[
                {'AttributeName': 'PackageName', 'AttributeType': 'S'}
            ],
            KeySchema=[{"KeyType": "HASH", "AttributeName": "PackageName"}]
        )

        tbl = boto3.resource('dynamodb').Table(table_name)
        for pkg in packages:
            tbl.put_item(Item={'PackageName': pkg})

        yield tbl


@patch('urllib.request.urlopen', UrlOpenMockContext)
def test_packages_in_table_get_added_and_removed(dynamodb_table):

    pre_packages = ['bash', 'linux', 'vim', 'zsh', 'xorg-server',
                'chromium', 'couldinho-base']
    post_packages = ['bash', 'linux', 'vim', 'zsh', 'xorg-server', 
                'couldinho-base', 'parole', '010editor', 'couldinho-desktop',
                'couldinho-laptop', 'couldinho-sec', 'gef-git', 'ghidra-bin',
                'mce-dev', 'pass-git-helper', 'vivaldi']

    os.environ['PACKAGE_TABLE'] = 'package-table'
    os.environ['COUNTRIES'] = 'IE,GB'
    os.environ['PERSONAL_REPO'] = PERSONAL_REPO

    packages = dynamodb_table.scan()
    assert set([p['PackageName'] for p in packages['Items']]) == \
            set(pre_packages)

    from package_updater.update_packages import lambda_handler

    lambda_handler(None, None)

    packages = dynamodb_table.scan()
    assert set([p['PackageName'] for p in packages['Items']]) == \
            set(post_packages)

