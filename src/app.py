# src/app.py
import json
import logging
import time
import boto3
import base64

logger = logging.getLogger()
logger.setLevel(logging.INFO)

bedrock_runtime = boto3.client("bedrock-runtime")
bedrock_control = boto3.client("bedrock")

def resolve_latest(prompt_id: str) -> str:
    resp = bedrock_control.list_prompt_versions(
        promptIdentifier=prompt_id
    )
    print("resp:",resp)
    versions = resp.get("promptVersions", [])
    
    if not versions:
        raise RuntimeError("No prompt versions found")

    latest = max(v["version"] for v in versions)
    print("latest:",latest)
    return f"{prompt_id}:{latest}"


def handler(event, context):
    start_ts = time.time()

    if event.get("httpMethod") != "POST":
        return {
            "statusCode": 405,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": "Only POST is supported"}),
        }



    path_params = event.get("pathParameters") or {}
    service = path_params.get("service")
    resolved_prompt = resolve_latest(service)
    body = event.get("body") or ""
    if event.get("isBase64Encoded"):
        body = base64.b64decode(body).decode("utf-8")

    try:
        response = bedrock_runtime.invoke_prompt(
            promptIdentifier=resolved_prompt,
            inputText=body
        )
    except Exception:
        logger.exception("Prompt invocation failed: %s", service)
        return {
            "statusCode": 400,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": f"Invalid prompt: {service}"}),
        }
    
    elapsed_ms = int((time.time() - start_ts) * 1000)

    result_body = json.loads(response["body"].read())

    # Claude-compatible normalization
    content = result_body.get("content", [])
    usage = result_body.get("usage", {})

    result = {
        "service": service,
        "output": content[0]["text"] if content else None,
        "output_type": content[0]["type"] if content else None,
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "elapsed": elapsed_ms,
        "stop_reason": result_body.get("stop_reason"),
    }

    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(result),
    }
