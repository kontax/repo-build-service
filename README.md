# Repo Build Service

An AWS lambda service used to keep a personal repository of Arch packages up to date. This service automatically 
monitors a Github repository for AUR packages to build and store.

```
.
├── README.md                   <-- This instructions file
├── event.json                  <-- API Gateway Proxy Integration event payload
├── hello_world                 <-- Source code for a lambda function
│   ├── __init__.py
│   ├── app.py                  <-- Lambda function code
│   ├── requirements.txt        <-- Lambda function code
├── template.yaml               <-- SAM Template
└── tests                       <-- Unit tests
    └── unit
        ├── __init__.py
        └── test_handler.py
```

## Requirements

* AWS Administrator access
* [Python 3](https://www.python.org/downloads/)
* [Docker](https://www.docker.com/community-edition)
* [Pushover](https://pushover.net/)
* [AWS SAM CLI](https://github.com/awslabs/aws-sam-cli)
* [Personal repository in S3](https://disconnected.systems/blog/archlinux-repo-in-aws-bucket)
* [Meta-packages stored in GitHub](https://github.com/kontax/arch-packages)

## Prerequisites

### AWS Setup
Firstly we need to create an AWS account, and configure it to be used on our Development system. The reasons for this 
are twofold - firstly we need a place to store the AUR packages, hooking up pacman to them; and secondly we need an S3 
container to publish AWS SAM deployments. Create an AWS account and create a new Administrator account with programmatic 
access, and use `aws configure` to set it up locally (assuming aws-cli is installed). Once done, create a new bucket for 
hosting SAM deployments:

```bash
aws s3api create-bucket \
    --bucket ${BUCKET_NAME} \
    --region ${REGION}
```

Follow the steps in [Disconnected's blog post](https://disconnected.systems/blog/archlinux-repo-in-aws-bucket) first, 
then resume here. A new public-read bucket may be created with the following command, ensuring to change the bucket name 
and region:

```bash
aws s3api create-bucket \
    --acl public-read \
    --bucket ${BUCKET_NAME} \
    --region ${REGION}
```

### Github Webhook
The build service relies on a Github hook in order to kick off the build process. A repository containing the PKGBUILD
with all AUR packages to be built must be set up to notify the process on each commit pushed. This can be found in 
the repository settings page, under the Webhooks heading.

Create a new Webhook, and enter `https://example.com` as the Payload URL. This will need to be changed once the build
service has been published. The Content-Type should be `application/json`. For the secret, create a new UUID and 
populate the form with it. This should be noted down, as it will be needed later on when pushing to SSM. Finally, just
select the push event and click the Add Webhook button.

### Pushover
[Pushover](https://pushover.net/) is used to send notifications of new/updated packages as well as failures. We need to
create an account and set up an API key in order to use them. After creating an account, take note of the user key. 
Create a new application and note down the API key there. Also register a phone so notifications have somewhere to be 
sent.

### GPG Key
A GPG key is used to sign packages and ensure they haven't been tampered with after being built. Create a GPG key with
the following steps:
TODO: Figure out steps for this
```bash
export GNUPGHOME=/tmp   # Create a temporary GPG directory (if required)
gpg --full-generate-key
```
The key must then be exported as text, which can then be uploaded to SSM as described below.

### SSM
All the keys that have been generated need to be uploaded to SSM

1. Create an administrator account in AWS for deployment and set up locally with `aws configure`
2. Follow the steps within disconnected's blog to set up an S3 repo, ensuring a PKGBUILD file is in a Github repo
3. Set up a webhook within that Github repo, using a temporary URL and generating a UUID for the secret key
4. Upload the secret key to SSM
5. Create a separate S3 bucket for deployment
6. Create a pushover account and create an app to get an API key
7. Upload the pushover key to SSM
8. Create a signing key for packages, and upload that to SSM
9. Create a decryption key for the key in the step above

## Template Parameters

### Repository Details
* **PersonalRepository**: Full URL to the AUR repository DB eg. `https://s3.us-west-1.amazonaws.com/my-aur-bucket/x86_64/my-aur-repo.db`
* **PersonalRepoBucket**: Name of the S3 bucket containing the repostitory eg. `my-aur-bucket`
* **RepoName**: Name of the repository as set up in pacman eg. `my-aur-repo`
* **RepoArch**: Architecture of the repository eg. `x86_64`
* **AurPackager**: Name/email assigned to the package build eg. `Package Builder <aur@example.com>`

### AWS Setup
* **PackageTable**: Name of the DynamoDB table storing package details, defaults to `package-list`
* **FanoutStatusTable**: Name of the table used to control the fan-in / fan-out status of package building, defaults to `fanout-status`
* **FanoutController**: Name of the lambda function used to control fan-in / fan-out state, defaults to `fanout-controller`
* **BuildQueueName**: Name of the queue that the ECS tasks use to pull package details from to build, defaults to `fanout-queue`

### Reflector Variables
* **RepositoryCountries**: Comma-separated country codes used for finding the best mirror for package downloads, defaults to `IE,GB`

### Secret Keys
* **GithubWebhookSecret**: Secret key set up within the Github repository containing the PKGBUILD meta-package, defaults to `{{resolve:ssm:githubToken:1}}` which needs to be set up as described above
* **PushoverToken**: Token used to notify built packages via pushover, defaults to `{{resolve:ssm:pushoverToken:1}}`, however this needs to be set up within AWS SSM as outlined above
* **PushoverUser**: Username created within Pushover, defaults to `{{resolve:ssm:pushoverUser:1}}`, which needs to be set up as described above
* **AurKeyParam**: Name of the private key within the Paramter Store used to sign built packages, defaults to `aur_key`
* **AurKeyDecrypt**: The KMS key used to encrypt/decrypt the parameter store above, eg. `key/abcdef-1234-5678-ghijkl123456`

### ECS Objects
* **ECSCluster**: Name of the cluster used to contain the packages building ECS tasks, defaults to `aur-pkgbuild-cluster`
* **TaskDefinition**: Name of the ECS task used to build packages, defaults to `aur-pkgbuild-task`
* **RepoUpdater**: Name of the ECS task used to update the full repository, defaults to `aur-repo-update-task`
* **MaxTaskCount**: Maximum number of ECS tasks to run simultaneously, defaults to 4

