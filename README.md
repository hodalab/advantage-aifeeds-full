## advantage-aifeeds-full
This repo contains boths cli and aws stack

The cli version needs OPENROUTER_API_KEY to be set in environment variables
To set it:
Windows: set OPENROUTER_API_KEY=your_key_here
Linux/Mac: export OPENROUTER_API_KEY=your_key_here


# how to run from cmd
set OPENROUTER_API_KEY
cd src
pip install -f requirements
python news_search.py 1 5 --locale IT

# TODO
- Paremetrize summary URL
- Externalize json configuration files
- Add html files