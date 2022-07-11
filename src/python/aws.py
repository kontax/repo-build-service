import boto3
import json
import os


def send_to_queue_name(queue_name, message):
    # Create SQS client
    if os.getenv("AWS_SAM_LOCAL"):
        sqs = boto3.resource('sqs', endpoint_url='http://localhost:4566')
    else:
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
    print(f"Sending the following message to SQS {queue_url}:")
    print(message)
    if os.getenv("AWS_SAM_LOCAL"):
        sqs = boto3.client('sqs', endpoint_url='http://localhost:4566')
    else:
        sqs = boto3.client('sqs')
    response = sqs.send_message(
        QueueUrl=queue_url,
        MessageBody=(message)
    )
    print(f"Message sent: {response['MessageId']}")


def start_ecs_task(cluster, task_definition, overrides={}):
    """Starts a new ECS task within a Fargate cluster to build the packages

    The ECS task pulls each package built one by one from the queue and adds
    them to the personal repository.

    Args:
        cluster (str): The name of the cluster to start the task in
        task_definition (str); The name of the task definition to run
        overrides (dict): Any ECS variable overrides to push to the container
    """

    print(f"Starting new ECS task to build the package(s)")

    # Note: There's no ECS in the free version of localstack
    client = boto3.client('ecs')
    response = client.run_task(
        cluster=cluster,
        launchType='FARGATE',
        taskDefinition=task_definition,
        count=1,
        platformVersion='LATEST',
        networkConfiguration={
            'awsvpcConfiguration': {
                'subnets': [
                    'subnet-9f4b60c6'
                ],
                'assignPublicIp': 'ENABLED'
            }
        },
        overrides=overrides
    )
    print(f"Run task complete: {str(response)}")


def get_running_task_count(cluster, task_definition):
    """ Retrieves the number of ECS tasks for a specified cluster and task
    family that are currently either running or are in a pending state waiting
    to be run.

    Args:
        cluster (str): The name of the cluster containing the running tasks
        task_definition (str): The family of task to search for

    Returns:
        (int): The number of tasks in a running/soon to be running state
    """

    client = boto3.client('ecs')
    response = client.list_tasks(
        cluster=cluster,
        family=task_definition,
        desiredStatus="RUNNING"
    )
    return len(response['taskArns'])


def get_dynamo_resource():
    """
    Get a dynamodb resource depending on which environment the function is
    running in
    """

    if os.getenv("AWS_SAM_LOCAL"):
        dynamo = boto3.resource('dynamodb', endpoint_url="http://dynamodb:8000")
    else:
        dynamo = boto3.resource('dynamodb')
    return dynamo

