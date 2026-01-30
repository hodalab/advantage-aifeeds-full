# src/app.py
import json
import logging
import time
import boto3
from json_repair import repair_json
from openrouter_client import OpenRouterClient
from secretmanager_client import get_secret

import os

# Load taxonomy from JSON
def load_taxonomy_mapping():
    taxonomy_path = os.path.join(os.path.dirname(__file__), 'iab-taxonomy.json')
    try:
        with open(taxonomy_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        mapping = {}
        for cluster in data.get('clusters', []):
            cluster_id = cluster['cluster_id']
            mapping[cluster_id] = {}
            for category in cluster.get('categories', []):
                mapping[cluster_id][category['iab_code']] = category.get('iab_keywords', [])
        return mapping
    except Exception as e:
        logger.error(f"Error loading taxonomy: {e}")
        return {}

IAB_CLUSTER_MAPPING = load_taxonomy_mapping()


logger = logging.getLogger()
logger.setLevel(logging.INFO)

bedrock = boto3.client("bedrock-runtime")

#MODEL_ID = "google/gemini-2.5-flash"
MODEL_ID = "openai/gpt-oss-120b"

DEFAULT_LANG ="it"
CHAR_SIZE ="2000"
MAX_TOKENS=int(int(CHAR_SIZE)*1.3)

SYSTEM_MESSAG_TEMPLATE_o1 = """
                    Perform a summary of the sources provided, they are different article on the same topic,  
                    The output must be a new article that doesn't cite the source articles, please discard possible unrelated content.
                    Output ONLY a valid JSON with these fields:  title, subtitle, summary, products, brands.
                    summary: return around {char_size} chars organized in paragraph (use html <p> tag for output) add 2 titled paragraphs (title must be seperated in a dedicated <p> section). Brands and products in bold.
                    products: an array [] with an item for every product present in summary
                    brands: an array [] with an item for every brand present in summary

                    keywords: a JSON object containing relevance scores (1-100) for each of the following category IDs: {category_ids}. Evaluate how relevant each category is to the summary content based on these category definitions: {iab_keywords}. Assign scores where 80-100 indicates the category is a primary theme in the summary, 40-79 indicates secondary relevance, and 1-39 indicates marginal or tangential relevance. Output format example: {{"381": 85, "406": 45, "466": 90, "550": 20}}
                    
                    All text genereted must be in {lang}.
                """
SYSTEM_MESSAG_TEMPLATE = """
                        Perform a summary of the sources provided, they are different articles on the same topic. The output must be a new article that doesn't cite the source articles, please discard possible unrelated content.
                        Output ONLY a valid JSON with these fields: title, subtitle, summary, products, brands, keywords.
                        title: a concise title for the article
                        subtitle: a descriptive subtitle
                        summary: return around {char_size} chars organized in 2 sections using <section> tags. Each section must contain a title in a <p class="title"> tag followed by content paragraphs in <p> tags. Brands and products must be in bold using <strong> tags. Structure example: <section><p class="title">Section Title</p><p>Content with <strong>Brand</strong> and <strong>Product</strong>...</p></section>. Add citations to the source articles in the format: [id ] where id is the id of the source article, specify only one citation per section.
                        products: an array [] with an item for every product present in summary. 
                        brands: an array [] with an item for every brand present in summary
                        keywords: a JSON object containing relevance scores (1-100) for each of the following category IDs: {category_ids}. Evaluate how relevant each category is to the summary content based on these category definitions: {iab_keywords}. Higher scores indicate greater relevance to the summary content. Output format example: {{"381": 85, "406": 45, "466": 90, "550": 20}}
                        All text generated must be in {lang}.
                """

#POST /feedsummary
def handler(event, context):
    start_ts = time.time()

    # Enforce POST
    method = event.get("httpMethod")
    if method != "POST":
        return {
            "statusCode": 405,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": "Only POST is supported"}),
        }

    logger.info("Event: %s", json.dumps(event))

    service = "feedsummary"
    version = "1.0"

    secret_name = os.environ.get("SECRET_NAME")
    if secret_name:
        logger.info(f"Fetching secret: {secret_name}")
        secret_value = get_secret(secret_name)
        secret_json = json.loads(secret_value)
        api_key = secret_json.get("OPENROUTER_API_KEY")
    else:
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json"},
            "body": "bad configuration",
        }


    or_client = OpenRouterClient(
        api_key=api_key,
        x_title="advantage-bai-feed-summary",
    )





    # Read payload as raw text
    body = event.get("body") or ""
    if event.get("isBase64Encoded"):
        import base64
        body = base64.b64decode(body).decode("utf-8")

    """input format expected.
        {
            "cluster_id":id,
            "language":"it"
            "contents":[
                {
                    "id":1,
                    "content":"text1",
                    "source":"corrier.it"
                },
                {
                    "id":2,
                    "content":"text1",
                    "source":"corrier.it"
                },
                {
                    "id":3,
                    "content":"text1",
                    "source":"corrier.it"
                }
            ]
        }
    """
    json_body=json.loads(body)  #if not json -> error
    cluster_id = json_body["cluster_id"]
    language = json_body.get("language",DEFAULT_LANG)
    llm =json_body.get("model",MODEL_ID)
    try:
        contents = json_body["contents"]
    except Exception as e:
        logger.error("Error parsing contents: %s , trying with articles", e)
        contents = json_body["articles"]

    logger.info("json contents %s",contents)
    logger.info("cluster_id %s",cluster_id)
    logger.info("language %s",language)
    # convert language code if needed (eg. "it" -> "italian")
    lang_map = { "it": "italian", "en": "english", "de": "german", "fr": "french", "es": "spanish" }
    language = lang_map.get(language.lower(), language.lower())
    
    logger.info("iab code %s",json.dumps(IAB_CLUSTER_MAPPING[int(cluster_id)],indent=2))
    system_message = SYSTEM_MESSAG_TEMPLATE.format(
        char_size=CHAR_SIZE,
        lang=language,
        category_ids=",".join(IAB_CLUSTER_MAPPING[int(cluster_id)].keys()),
        iab_keywords=json.dumps(IAB_CLUSTER_MAPPING[int(cluster_id)]),
    )
    logger.info("system message %s",system_message)
    logger.info("cluster_id %s",cluster_id)
    logger.info("contents %s",contents)
    
    response = or_client.chat_completions(
        model=llm,
        messages=[
            # One or more system prompts
            {"role": "system", "content": system_message},
            {"role": "user", "content": json.dumps(contents)},
        ],
        temperature=0.1,
        max_tokens=MAX_TOKENS,
    )
    
    content=response["choices"][0]["message"]["content"]
    elapsed_ms = int((time.time() - start_ts) * 1000)
    output_text = None
    output_type = None
    usage = response["usage"]
    stop_reason = response["choices"][0].get("native_finish_reason","unknown")
    output_json = json.loads(repair_json(content))
    logger.info("output json %s",output_json)
    result = {
        "meta":{
            "llm": llm,
            "service": service,
            "language": language,
            "version": version,
            "output": output_text,
            "output_type": output_type,
            "input_tokens": usage.get("prompt_tokens"),
            "output_tokens": usage.get("completion_tokens"),
            "max_tokens":MAX_TOKENS,
            "elapsed": elapsed_ms,
            "stop_reason": stop_reason,
            "cost": usage.get("cost","N/A")
        },
        "title":output_json["title"],
        "subtitle":output_json["subtitle"],
        "summary":output_json["summary"],
        "products":output_json["products"],
        "brands":output_json["brands"],
        "keywords":output_json["keywords"],
        
    }

    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(result),
    }
