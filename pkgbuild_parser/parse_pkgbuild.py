import json
import parser


def lambda_handler(event, context):
    print(event)
    parser.run(json.dumps(event))
    return {
        'statusCode': 200,
        'body': json.dumps('PKGBUILD added to queue')
    }

