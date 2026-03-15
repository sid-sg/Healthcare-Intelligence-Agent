from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings

embeddings = HuggingFaceEmbeddings(
    model_name="BAAI/bge-small-en-v1.5",
    encode_kwargs={"normalize_embeddings": True}
)

vector_store = FAISS.load_local(
    "src/rag/vector_index",
    embeddings,
    allow_dangerous_deserialization=True
)

query = "What services does Abura Health Centre offer?"

results = vector_store.similarity_search(query, k=5)

for doc in results:
    print(doc.page_content)
    print("-----")