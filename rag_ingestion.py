import os
import pandas as pd
from dotenv import load_dotenv
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document

# Load environment variables
load_dotenv()

def ingest_data(file_path, db_path):
    print(f"Reading {file_path}...")
    xls = pd.ExcelFile(file_path)
    
    documents = []
    
    for sheet_name in xls.sheet_names:
        print(f"Processing sheet: {sheet_name}")
        df = pd.read_excel(xls, sheet_name=sheet_name)

        # Convert each row to a descriptive text chunk
        # Robust header detection: Find the first row that has 'SKU_Name' or 'Sheet' or 'Store_Name'
        header_row_idx = None
        for idx, row in df.iterrows():
            row_vals = [str(x).lower() for x in row.values]
            if any(h in row_vals for h in ['sku_name', 'sheet', 'store_name', 'sku_code', 'category', 'problem area']):
                header_row_idx = idx
                break
        
        if header_row_idx is not None:
            df.columns = df.iloc[header_row_idx]
            df = df.iloc[header_row_idx+1:].reset_index(drop=True)
            df = df.dropna(how='all')

        for _, row in df.iterrows():
            # Filter out NaN values and rows that are likely headers or separators
            row_dict = row.dropna().to_dict()
            if not row_dict or len(row_dict) < 3:
                continue
                
            chunk_content = f"Sheet: {sheet_name}\n"
            content_parts = []
            for key, value in row_dict.items():
                if pd.isna(key) or "Unnamed" in str(key):
                    continue
                content_parts.append(f"{key}: {value}")
            
            chunk_content += "\n".join(content_parts)
            
            # Create a Document object
            doc = Document(
                page_content=chunk_content,
                metadata={"source": file_path, "sheet": sheet_name}
            )
            documents.append(doc)
            
    print(f"Total chunks created: {len(documents)}")
    
    # Initialize Embeddings
    print("Initializing Google Generative AI Embeddings...")
    embeddings = GoogleGenerativeAIEmbeddings(model="models/gemini-embedding-001")
    
    # Store in ChromaDB
    print(f"Storing embeddings in {db_path}...")
    vectorstore = Chroma.from_documents(
        documents=documents,
        embedding=embeddings,
        persist_directory=db_path
    )
    print("Ingestion complete!")

if __name__ == "__main__":
    FILE_PATH = "MedChain_PharmaIQ_DummyData.xlsx"
    DB_PATH = "rag_db"
    
    ingest_data(FILE_PATH, DB_PATH)
