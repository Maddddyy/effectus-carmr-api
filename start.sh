#!/bin/bash
cd /home/azureuser/effectus-api
source venv/bin/activate
export PYTHONPATH=/home/azureuser/effectus-api

# Pre-warm the sentence-transformers model so it is cached before the first request.
# This avoids a slow first-job download. Fails silently - the lexical fallback handles
# any load failure at runtime.
python3 -c "
from pipeline.semantic_divergence import _get_embedding_model
_get_embedding_model()
" 2>/dev/null && echo '[start.sh] Embedding model pre-warmed OK' || echo '[start.sh] Embedding model pre-warm failed - lexical fallback will be used'

uvicorn main:app --host 0.0.0.0 --port 8001 --workers 1 --log-level info
