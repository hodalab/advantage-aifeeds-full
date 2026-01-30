import boto3
from botocore.exceptions import ClientError
import logging
logger = logging.getLogger()

def get_secret(secret_name, region_name="eu-west-1"):
    """
    Retrieves the secret from AWS Secrets Manager.
    """
    # Create a Secrets Manager client
    session = boto3.session.Session()
    client = session.client(
        service_name='secretsmanager',
        region_name=region_name
    )

    try:
        get_secret_value_response = client.get_secret_value(
            SecretId=secret_name
        )
    except ClientError as e:
        logger.error(f"Error retrieving secret {secret_name}: {e}")
        return None

    # Decrypts secret using the associated KMS key.
    if 'SecretString' in get_secret_value_response:
        return get_secret_value_response['SecretString']
    return None