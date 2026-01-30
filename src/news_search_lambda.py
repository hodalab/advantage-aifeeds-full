import json
import os
import boto3
from news_search import generate_feed
import logging
from urllib.parse import urlparse
from secretmanager_client import get_secret

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def process_cluster(cluster_id, max_results, geo, locale, s3_destination):
    """
    Generates feed for a single cluster and uploads to S3 if configured.
    Returns the generated feed (list) or raises an exception.
    """
    logger.info("params %s %s %s %s %s", cluster_id, max_results, geo, locale, s3_destination)
    
    feed, _ = generate_feed(
        cluster_id=int(cluster_id),
        max_results=int(max_results),
        geo=geo,
        locale=locale
    )

    if s3_destination and feed:
        try:
            output_file = f"feed{cluster_id}_{locale.lower()}.json"
            # Handle s3:// format or plain bucket name
            if s3_destination.startswith("s3://"):
                parsed = urlparse(s3_destination)
                bucket_name = parsed.netloc
                # Remove leading slash from path and allow for empty path
                prefix = parsed.path.lstrip('/')
                if prefix and not prefix.endswith('/'):
                        prefix += '/'
                object_key = f"{prefix}{output_file}"
            else:
                bucket_name = s3_destination
                object_key = output_file
            
            logger.info(f"☁️ Uploading {len(feed)} items for cluster {cluster_id} to S3: s3://{bucket_name}/{object_key}")
            s3_client = boto3.client('s3')
            json_data = json.dumps(feed, indent=2, ensure_ascii=False)
            
            s3_client.put_object(
                Bucket=bucket_name,
                Key=object_key,
                Body=json_data,
                ContentType='application/json'
            )
            logger.info("   ✅ Upload successful")
        except Exception as e:
            logger.error(f"   ❌ Error uploading cluster {cluster_id} to S3: {e}")
            # We log the S3 error but return the feed successfully as the generation worked
            
    return feed

def handler(event, context):
    """
    Lambda handler for news search.
    """
    logger.info(f"Received event: {json.dumps(event)}")

    # 1. Handle Secrets
    secret_name = os.environ.get("SECRET_NAME")
    if secret_name:
        logger.info(f"Fetching secret: {secret_name}")
        secret_value = get_secret(secret_name)
        if secret_value:
            try:
                secret_json = json.loads(secret_value)
                if isinstance(secret_json, dict) and "OPENROUTER_API_KEY" in secret_json:
                     os.environ["OPENROUTER_API_KEY"] = secret_json["OPENROUTER_API_KEY"]
                else:
                     pass 
            except json.JSONDecodeError:
                os.environ["PPLX_API_KEY"] = secret_value
            
    # 2. Parse Event Body
    body = {}
    if "body" in event:
        try:
            if event.get("isBase64Encoded", False):
                import base64
                body = json.loads(base64.b64decode(event["body"]).decode("utf-8"))
            else:
                 body = json.loads(event["body"]) if isinstance(event["body"], str) else event["body"]
        except Exception as e:
            logger.error(f"Error parsing body: {e}")
            return {
                "statusCode": 400,
                "body": json.dumps({"error": "Invalid JSON body"})
            }
    else:
        body = event

    # 3. Extract Parameters
    cluster_id = body.get("cluster_id")
    if not cluster_id:
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "Missing cluster_id"})
        }

    max_results = body.get("max_results", 10)
    geo = body.get("geo","IT")
    locale = body.get("locale","IT")
    
    s3_destination = os.environ.get("S3_DESTINATION")

    logger.info(f"Request parameters - cluster: {cluster_id}, max_results: {max_results}, geo: {geo}, locale: {locale}")
    
    # 4. Processing
    try:
        # Single cluster processing
        feed = process_cluster(cluster_id, max_results, geo, locale, s3_destination)
        
        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*"
            },
            "body": json.dumps(feed)
        }

    except Exception as e:
        logger.exception(f"Error in handler: {e}", exc_info=True)
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }
