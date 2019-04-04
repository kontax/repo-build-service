import json
import os

from aws import get_dynamo_resource, send_to_queue
from enums import Status

FANOUT_STATUS = os.environ.get('FANOUT_STATUS')
FANOUT_QUEUE = os.environ.get('FANOUT_QUEUE')


def lambda_handler(event, context):
    print(event)
    # Get Dependencies
    deps = event['dependencies']
    url = event['url']

    # The dynamoDB table containing the running status of each package
    dynamo = get_dynamo_resource()
    table = dynamo.Table(FANOUT_STATUS)

    # Store the metapackage URL for building on completion
    table.update_item(Key={'PackageName': "METAPACKGE_URL", 'Status': url})

    # Put each one in the FANOUT_STATUS table with an "Initialized" status and add it to the queue
    for dep in deps:
        table.update_item(Key={'PackageName': dep, 'Status': Status.Initialized.name})
        send_to_queue(FANOUT_QUEUE, dep)

    return {
        'statusCode': 200,
        'body': json.dumps('PKGBUILD added to queue')
    }
