import os

def load_documents(folder_path: str = "rag") -> list:
    documents = []
    if not os.path.exists(folder_path):
        os.makedirs(folder_path)
        return []

    for filename in os.listdir(folder_path):
        if filename.endswith(".txt"):
            with open(os.path.join(folder_path, filename), "r", encoding="utf-8") as f:
                content = f.read()
                paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
                documents.extend(paragraphs)
    return documents

def retrieve_context(query: str, documents: list, top_k: int = 3) -> str:
    if not documents:
        return "لا يوجد سياق علمي متوفر."

    query_words = set(query.lower().split())
    scores = []

    for doc in documents:
        doc_words = set(doc.lower().split())
        common_words = query_words.intersection(doc_words)
        scores.append((len(common_words), doc))

    scores.sort(key=lambda x: x[0], reverse=True)
    top_docs = [doc for score, doc in scores[:top_k] if score > 0]

    if not top_docs:
        return "\n\n".join(documents[:2])

    return "\n\n".join(top_docs)

documents = load_documents()