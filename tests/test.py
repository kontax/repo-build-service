import boto3
import botocore
import json

lambda_client = boto3.client('lambda',
        region_name='eu-west-1',
        endpoint_url="http://127.0.0.1:3001",
        use_ssl=False,
        verify=False,
        config=botocore.client.Config(
            signature_version=botocore.UNSIGNED,
            read_timeout=10,
            retries={'max_attempts': 0},
        )
    )

with open('inputs/webhook-template.json', 'r') as f:
    webhook = json.loads(f.read())

with open('inputs/pkgbuild_retriever/master_commit.json', 'r') as f:
    webhook['body'] = f.read()

response = lambda_client.invoke(FunctionName='PkgbuildRetrieverFunction', Payload=json.dumps(webhook).encode('utf-8'))
print(response)
