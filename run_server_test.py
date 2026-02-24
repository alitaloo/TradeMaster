#!/usr/bin/env python3
from api_server import create_app, load_config
import logging

logging.basicConfig(level=logging.INFO)

app = create_app(load_config())
print(f"Routes: {[rule.rule for rule in app.url_map.iter_rules()]}")
print("Starting server...")
app.run(host='127.0.0.1', port=8082, debug=False, use_reloader=False)
