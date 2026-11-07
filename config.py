"""Shared configuration for all agent-memory examples."""

LLM_MODEL = "claude-sonnet-4-6"
KEEP_LAST = 2

EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIMS = 384

CLOUD = "aws"
REGION = "us-east-1"
PINECONE_INDEX_NAME = "agent-memory-demo-384"
MEM0_INDEX_NAME = "agent-memory-mem0"
MEM0_NAMESPACE = "mem0"

LETTA_URL = "http://localhost:8283"

MEM0_USER_ID = "maya-demo"
MEM0_CONFIG = {
    "llm": {"provider": "anthropic", "config": {"model": LLM_MODEL, "max_tokens": 2000, "enable_sampling_parameters": False}},
    "embedder": {"provider": "fastembed", "config": {"model": EMBEDDING_MODEL, "embedding_dims": EMBEDDING_DIMS}},
    "vector_store": {"provider": "pinecone", "config": {
        "collection_name": MEM0_INDEX_NAME,
        "namespace": MEM0_NAMESPACE,
        "embedding_model_dims": EMBEDDING_DIMS,
        "serverless_config": {"cloud": CLOUD, "region": REGION},
    }},
}
