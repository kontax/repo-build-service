import json


def return_code(code, body):
    """Returns a JSON response

    :param (int) code: The HTTP response code
    :param (dict) body: The data to return

    :return: A JSON object containing the code and body
    :rtype: dict
    """
    return {
        "statusCode": code,
        "body": json.dumps(body)
    }
