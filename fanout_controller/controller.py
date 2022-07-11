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
    print(json.dumps(event))

    # Set default return message
    return_message = return_code(200, {"status": "No package found"})

    # Loop through each message received
    for message in event['Records']:

        # If the metapackage has been built the message will simply contain
        # {'FanoutStatus': 'Complete'}, so we can clear the fanout status
        # table and update all packages in the package table.
        msg_body = json.loads(message['body'])
        if msg_body.get("FanoutStatus") == "Complete":
            print("Fanout status complete")
            clear_table()
            print("Updating package table")
            pkg_msg = {
                'repository': msg_body['RepoName'],
                'url': msg_body['RepoUrl']
            }
            send_to_queue(PACKAGE_UPDATE_QUEUE, json.dumps(pkg_msg))
            return return_code(200, {"status": "Fanout status complete"})

        # Handle the message and set the final status, including updating
        # the fanout status table
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
    print(f"Deleting the following items: {to_delete}")
    with fanout_table.batch_writer() as batch:
        for package in to_delete:
            batch.delete_item(Key={'PackageName': package})


def handle_fanout_status(package_message):
    """ Handle a single message by updating the package state in the fanout
    table and, if all have either failed or been built, build the metapackage.

    Args:
        package_message (dict): JSON message containing hte package state 
                                within the 'body' key, ie. Complete or Failed

    Returns:
        (dict): HTTP return code containing the status of the fanout process
    """
    package_state = json.loads(package_message['body'])

    # The dynamoDB table containing the running status of each package
    dynamo = get_dynamo_resource()
    fanout_table = dynamo.Table(FANOUT_STATUS)
    update_package_state(fanout_table, package_state)

    # Delete failed items - this doesn't end the process as we still want
    # a new metapackage to be built regardless of the failed packages.
    delete_failed(fanout_table)

    # Check remaining items
    resp = fanout_table.scan()
    still_building = packages_still_building(resp['Items'])
    if still_building > 0:
        print(f"{still_building} items still in table")
        return return_code(200, {"status": "Items are still running"})

    # Otherwise if everything has completed, invoke the meta-package 
    # building function
    build_metapackage(fanout_table)
    return return_code(200, {"status": "All packages built"})


def packages_still_building(fanout_list):
    """ Checks how many packages are being built or are in the queue to be 
    built, so we can decide whether to move forward with the process.

    Args:
        fanout_list (list): All items within the fanout status table

    Returns:
        (int): The number of packages (excluding metapackages) building or
               queued to be built
    """

    # Check how many metapackages are yet to be built, as these are done at
    # the later stage
    meta_package_count = len([x for x in fanout_list
                              if x.get('IsMeta')])  # Should only be one

    # See how many total packages are in the build or init status
    incomplete_count = len([x for x in fanout_list
                            if x['BuildStatus'] == Status.Initialized.name
                            or x['BuildStatus'] == Status.Building.name])

    # Ignore the metapackages
    return incomplete_count - meta_package_count


def update_package_state(fanout_table, package_state):
    """ Updates the state of the package being built within the fanout status
    table argument.

    Args:
        fanout_table (Table): Table containing the status of each package
        package_state (dict): Name and state of the package to update
    """

    print(f"Updating state:")
    print(json.dumps(package_state))
    fanout_table.update_item(
        Key={'PackageName': package_state['PackageName']},
        UpdateExpression="set BuildStatus = :s, IsMeta = :m, GitUrl = :g, repo = :r, GitBranch = :b",
        ExpressionAttributeValues={
            ':s': package_state['BuildStatus'],
            ':m': package_state.get('IsMeta'),
            ':g': package_state.get('GitUrl'),
            ':r': package_state.get('repo'),
            ':b': package_state.get('GitBranch'),
        }
    )


def delete_failed(fanout_table):
    """ Deletes any failed items from the fanout table, as these packages can
    be ignored when processing the metapackage.

    Args:
        fanout_table (Table): Table containing the status of each package
    """

    all_items = fanout_table.scan()
    deleted_items = [item for item in all_items['Items']
                     if item['BuildStatus'] == Status.Failed.name]
    print(f"Removing {len(deleted_items)} failed items from the fanout table")
    for item in deleted_items:
        print(f"Removing item {item['PackageName']}")
        fanout_table.delete_item(Key={"PackageName": item['PackageName']})


def build_metapackage(fanout_table):
    """ Adds the metapackage to the build queue.

    Args:
        fanout_table (Table): Table containing the status of each package
    """

    print("All packages finished - invoking the metapackage builder")
    resp = fanout_table.query(
            KeyConditionExpression=Key('PackageName').eq("GIT_REPO"))
    msg = {
        "git_url": resp['Items'][0]['GitUrl'],
        "repo": resp['Items'][0]['repo'],
        "git_branch": resp['Items'][0]['GitBranch'],
    }
    send_to_queue(METAPACKAGE_QUEUE, json.dumps(msg))
    print("Removing the metapackage from the fanout table")
    fanout_table.delete_item(Key={"PackageName": "GIT_REPO"})

