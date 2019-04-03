import datetime
import hashlib
import hmac
import json
import os
import sys

import boto3
from botocore.vendored import requests

ALGORITHM = 'AWS4-HMAC-SHA256'


def invoke_lambda(func_name, payload):
    client = boto3.client('lambda')
    payload = json.dumps(payload)
    response = client.invoke(
        FunctionName=func_name,
        InvocationType='Event',
        LogType='None',
        Payload=payload
    )
    return response


def send_to_queue_name(queue_name, message):
    # Create SQS client
    sqs = boto3.resource('sqs')
    # Get queue
    queue = sqs.get_queue_by_name(QueueName=queue_name)
    # Send message
    response = queue.send_message(
        MessageBody=message
    )
    print(f"Message sent: {response['MessageId']}")


def send_to_queue(queue_url, message):
    # Create SQS client
    sqs = boto3.client('sqs')
    response = sqs.send_message(
        QueueUrl=queue_url,
        MessageBody=(message)
    )
    print(f"Message sent: {response['MessageId']}")


class ExecuteApiRequest:

    def __init__(self, method, service, host, region, endpoint, content_type):
        self.method = method
        self.service = service
        self.host = host
        self.region = region
        self.endpoint = endpoint
        self.content_type = content_type

        # Access keys
        self.access_key = os.environ.get('AWS_ACCESS_KEY_ID')
        self.secret_key = os.environ.get('AWS_SECRET_ACCESS_KEY')
        if self.access_key is None or self.secret_key is None:
            print("No access key available.")
            sys.exit()

    def send_to_api(self, payload):
        headers = self.get_signed_headers(payload)
        r = requests.post(self.endpoint, data=payload, headers=headers)
        return r.text

    def get_signed_headers(self, payload):
        # Create date for headers
        t = datetime.datetime.utcnow()
        amz_date = t.strftime('%Y%m%dT%H%M%SZ')
        date_stamp = t.strftime('%Y%m%d')

        # Create canonical request
        signed_headers = 'content-type;host;x-amz-date'
        canonical_request = self._get_canonical_request(payload, amz_date, signed_headers)

        # Create string to sign
        credential_scope = date_stamp + '/' + self.region + '/' + self.service + '/aws4_request'
        string_to_sign = self._get_string_to_sign(credential_scope, amz_date, canonical_request)

        # Calculate signature
        signing_key = self._get_signature_key(self.secret_key, date_stamp)
        signature = hmac.new(signing_key, (string_to_sign).encode('utf-8'), hashlib.sha256).hexdigest()

        # Get authorization header
        authorization_header = self._get_auth_header(credential_scope, signed_headers, signature)

        # Add to headers
        headers = {'Content-Type': self.content_type,
                   'X-Amz-Date': amz_date,
                   'Authorization': authorization_header}

        return headers

    def _get_canonical_request(self, payload, amz_date, signed_headers):
        canonical_uri = self.endpoint.replace(f"https://{self.host}", '')
        canonical_querystring = ''
        canonical_headers = \
            'content-type:' + self.content_type + '\n' + \
            'host:' + self.host + '\n' + \
            'x-amz-date:' + amz_date + '\n'

        payload_hash = hashlib.sha256(payload.encode('utf-8')).hexdigest()

        canonical_request = self.method + '\n' + \
                            canonical_uri + '\n' + \
                            canonical_querystring + '\n' + \
                            canonical_headers + '\n' + \
                            signed_headers + '\n' + \
                            payload_hash

        return canonical_request

    @staticmethod
    def _get_string_to_sign(credential_scope, amz_date, canonical_request):
        request_digest = hashlib.sha256(canonical_request.encode('utf-8')).hexdigest()
        string_to_sign = ALGORITHM + '\n' + \
                         amz_date + '\n' + \
                         credential_scope + '\n' + \
                         request_digest

        return string_to_sign

    @staticmethod
    def _sign(key, msg):
        return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()

    def _get_signature_key(self, key, date_stamp):
        k_date = self._sign(('AWS4' + key).encode('utf-8'), date_stamp)
        k_region = self._sign(k_date, self.region)
        k_service = self._sign(k_region, self.service)
        k_signing = self._sign(k_service, 'aws4_request')
        return k_signing

    def _get_auth_header(self, credential_scope, signed_headers, signature):
        authorization_header = ALGORITHM + ' ' + \
                               'Credential=' + self.access_key + '/' + credential_scope + ', ' + \
                               'SignedHeaders=' + signed_headers + ', ' + \
                               'Signature=' + signature
        return authorization_header
