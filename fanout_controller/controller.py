import json
import os

from boto3.dynamodb.conditions import Key

from aws import get_dynamo_resource, send_to_queue
from common import return_code
from enums import Status

FANOUT_STATUS = os.environ.get('FANOUT_STATUS')
METAPACKAGE_QUEUE = os.environ.get('METAPACKAGE_QUEUE')
PACKAGE_UPDATE_QUEUE = os.environ.get('PACKAGE_UPDATE_QUEUE')


def lambda_handler(event, context):
    print(event)

    # Set default return message
    return_message = return_code(200, {"status": "No package found"})

    # Loop through each message received
    for message in event['Records']:

        # If the metapackage has been built, clear the table.
        if json.loads(message['body']).get("FanoutStatus") == "Complete":
            print("Fanout status complete")
            clear_table()
            print("Updating package table")
            send_to_queue(PACKAGE_UPDATE_QUEUE, {})
            return return_code(200, {"status": "Fanout status complete"})

        # Handle the message and set the final status - this is all we need to return
        return_message = handle_fanout_status(message)

    # Return the final status message
    return return_message


def clear_table():
    """ Clears the fanout status table completely on completion. """
    print("Clearing fanout status table")
    dynamo = get_dynamo_resource()
    fanout_table = dynamo.Table(FANOUT_STATUS)
    resp = fanout_table.scan()
    to_delete = [x['PackageName'] for x in resp['Items']]
    with fanout_table.batch_writer() as batch:
        for package in to_delete:
            batch.delete_item(Key={'PackageName': package})


def handle_fanout_status(package_message):
    """ Handle a single message by updating the package state in the fanout table and, if all have either
    failed or been built, build the metapackage.

    :param (dict) package_message: The JSON message containing the package state within the 'body' key
    :return: A HTTP return code containing the status of the fanout process
    :rtype: dict
    """
    package_state = json.loads(package_message['body'])

    # The dynamoDB table containing the running status of each package
    dynamo = get_dynamo_resource()
    fanout_table = dynamo.Table(FANOUT_STATUS)
    update_sent_item(fanout_table, package_state)

    # Delete failed items
    delete_failed(fanout_table)

    # Check remaining items
    resp = fanout_table.scan()
    still_building = packages_still_building(resp['Items'])
    if still_building > 0:
        print(f"{still_building} items still in table")
        return return_code(200, {"status": "Items are still running"})

    # Otherwise if everything has completed, invoke the meta-package building function
    build_metapackage(fanout_table)
    return return_code(200, {"status": "All packages built"})


def packages_still_building(fanout_list):
    """ Checks how many packages are being built or are in the queue to be built, so we can decide
    whether to move forward with the process.

    :param (list) fanout_list:
    :return: The number of packages (excluding metapackages) building or queued to be built
    :rtype: int
    """

    # Check how many metapackages are yet to be built, as these are done at the later stage
    meta_package_count = len([x for x in fanout_list if x.get('IsMeta')])  # Should only be one

    # See how many total packages are in the build or init status
    incomplete_count = len([x for x in fanout_list
                            if x['BuildStatus'] == Status.Initialized.name
                            or x['BuildStatus'] == Status.Building.name])

    # Ignore the metapackages
    return incomplete_count - meta_package_count


def update_sent_item(fanout_table, package_state):
    """ Updates the item sent via the lambda event in the fanout table

    :param (Table) fanout_table: The table containing the status of each package
    :param (dict) package_state: The name and state of the package to update
    """
    print(f"Updating state:\n{package_state}")
    fanout_table.update_item(
        Key={'PackageName': package_state['PackageName']},
        UpdateExpression="set BuildStatus = :s, IsMeta = :m, GitUrl = :g",
        ExpressionAttributeValues={
            ':s': package_state['BuildStatus'],
            ':m': package_state.get('IsMeta'),
            ':g': package_state.get('GitUrl'),
        }
    )


def delete_failed(fanout_table):
    """ Deletes any failed items from the fanout table, as these packages can be ignored when
    processing the metapackage.

    :param (Table) fanout_table: The table containing the status of each package within the process
    """
    all_items = fanout_table.scan()
    deleted_items = [item for item in all_items['Items'] if item['BuildStatus'] == Status.Failed.name]
    for item in deleted_items:
        print(f"Removing item {item['PackageName']}")
        fanout_table.delete_item(Key={"PackageName": item['PackageName']})


def build_metapackage(fanout_table):
    """ Adds the metapackage to the build queue.

    :param (Table) fanout_table: The table containing the status of each package
    """
    print("All packages finished - invoking the metapackage builder")
    resp = fanout_table.query(KeyConditionExpression=Key('PackageName').eq("GIT_REPO"))
    send_to_queue(METAPACKAGE_QUEUE, {"git_url": resp['Items'][0]['GitUrl']})
    fanout_table.delete_item(Key={"PackageName": "GIT_REPO"})

