from src.ingestion.create_doc import documents

from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings

# Load BGE embedding model
embeddings = HuggingFaceEmbeddings(
    model_name="BAAI/bge-small-en-v1.5",
    model_kwargs={"device": "cpu"},
    encode_kwargs={"normalize_embeddings": True}
)

# Create FAISS index
vector_store = FAISS.from_documents(
    documents,
    embeddings
)

# Save index locally
vector_store.save_local("src/rag/vector_index")

print("Vector index created successfully!")