import os
from dotenv import load_dotenv
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_community.vectorstores import Chroma

# Load environment variables
load_dotenv()

def verify_retrieval(db_path, queries):
    print(f"Loading vector store from {db_path}...")
    embeddings = GoogleGenerativeAIEmbeddings(model="models/gemini-embedding-001")
    vectorstore = Chroma(persist_directory=db_path, embedding_function=embeddings)
    
    for query in queries:
        print(f"\n--- Query: {query} ---")
        results = vectorstore.similarity_search(query, k=3)
        for i, doc in enumerate(results):
            print(f"\nResult {i+1}:")
            print(f"Source: {doc.metadata['source']} (Sheet: {doc.metadata['sheet']})")
            print("-" * 20)
            print(doc.page_content)
            print("-" * 20)

if __name__ == "__main__":
    DB_PATH = "rag_db"
    TEST_QUERIES = [
        "What is the status of stock in the East Delhi zone?",
        "Tell me about cold chain monitoring results.",
        "Which medications are nearing expiry?"
    ]
    
    verify_retrieval(DB_PATH, TEST_QUERIES)
