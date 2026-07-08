## advantage-aifeeds-full
This repo contains boths cli and aws stack

The cli version needs OPENROUTER_API_KEY to be set in environment variables
To set it:
Windows: set OPENROUTER_API_KEY=your_key_here
Linux/Mac: export OPENROUTER_API_KEY=your_key_here


# how to run from cli
cd src
pip install -f requirements
set OPENROUTER_API_KEY
# first parameter is cluster, second max_news, --model is optional
python news_search.py 6 1 --locale IT --model openai/gpt-oss-120b

# models available:
google/gemini-3-flash-preview
google/gemini-2.5-flash-lite
google/gemini-2.5-flash
anthropic/claude-haiku-4.5
anthropic/claude-sonnet-4.5
openai/gpt-5.2-chat
qwen/qwen3-235b-a22b
deepseek/deepseek-chat-v3-0324
meta-llama/llama-3.3-70b-instruct
qwen/qwen3-8b
moonshotai/kimi-k2-0905
moonshotai/kimi-k2.5
z-ai/glm-4.6


# TODO
- Paremetrize summary URL
- Externalize json configuration files
- Add html files