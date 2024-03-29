import boto3
import pytest

from moto import mock_dynamodb

@pytest.fixture()
def dynamodb_table():

    table_name = 'package-table'

    # List of packages that already exist in the table
    packages = [
        {'repo': 'personal-prod', 'package': 'couldinho-base'},
        {'repo': 'personal-prod', 'package': 'ida-free'},
        {'repo': 'personal-dev', 'package': 'couldinho-base'},
        {'repo': 'personal-dev', 'package': 'rr'}
    ]

    with mock_dynamodb():
        client = boto3.client('dynamodb')
        client.create_table(
            TableName=table_name,
            AttributeDefinitions=[
                {'AttributeName': 'Repository', 'AttributeType': 'S'},
                {'AttributeName': 'PackageName', 'AttributeType': 'S'}
            ],
            KeySchema=[
                {"KeyType": "HASH", "AttributeName": "Repository"},
                {"KeyType": "RANGE", "AttributeName": "PackageName"}
            ],
            ProvisionedThroughput={
                'ReadCapacityUnits': 5,
                'WriteCapacityUnits': 5
            }
        )

        tbl = boto3.resource('dynamodb').Table(table_name)
        for pkg in packages:
            item = {
                'Repository': pkg['repo'],
                'PackageName': pkg['package']
            }
            tbl.put_item(Item=item)

        yield tbl


def pkgcomp(pkgdict1, pkgdict2):
    """ Compare two package table entries """
    def pkgsort(key):
        return (key['Repository'], key['PackageName'])

    return sorted(pkgdict1, key=pkgsort) == sorted(pkgdict2, key=pkgsort)

