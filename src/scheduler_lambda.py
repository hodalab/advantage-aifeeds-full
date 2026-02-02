import json
import os
import boto3
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)
lambda_client = boto3.client("lambda")
TARGET_FUNCTION = os.environ["TARGET_FUNCTION"]

def handler(event, context):
    payload = _parse_event(event)
    clusters = payload.get("clusters", [])
    locales = payload.get("locales", []) # possible values it,en,es,fr
    max_results = payload.get("max_results", 10)
    model = payload.get("model", None)
    logger.info("Triggering NewsSearchFunction for clusters: %s, locales: %s, max_results: %s, lambda: %s", clusters, locales, max_results, TARGET_FUNCTION)

    if not clusters or not locales:
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "clusters and locales are required"})
        }

    #check if locales has correct values
    for locale in locales:
        if locale.lower() not in ["it", "en", "es", "fr"]:
            return {
                "statusCode": 400,
                "body": json.dumps({"error": "locales must be it,en,es,fr - received: " + locale})
            }   

    for cluster_id in clusters:
        for locale in locales:
            body: dict[str, str] ={
                    "cluster_id": cluster_id,
                    "geo": locale,
                    "locale": locale,
                    "max_results": max_results
                }
            if model:
                body["model"] = model
            logger.info("Invoking lambda for cluster %s, locale %s, body %s", cluster_id, locale, body)
            lambda_client.invoke(
                FunctionName=TARGET_FUNCTION,
                InvocationType="Event",  # async
                Payload = json.dumps(body).encode("utf-8"),
            )

    return {
        "statusCode": 202,
        "body": json.dumps({
            "invoked": len(clusters) * len(locales)
        })
    }


def _parse_event(event):
    if "body" in event and event["body"]:
        body = event["body"]
        if isinstance(body, str):
            return json.loads(body)
        return body
    return event