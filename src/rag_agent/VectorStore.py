import os, vertexai, bs4
from dotenv import load_dotenv
from typing_extensions import List, TypedDict, Optional, Any
from langchain_google_vertexai import VertexAIEmbeddings
from langchain_core.vectorstores import InMemoryVectorStore
from langchain_core.documents import Document
from langchain_community.document_loaders import WebBaseLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
load_dotenv()
"""
https://cloud.google.com/vertex-ai/generative-ai/docs/embeddings/get-text-embeddings
https://realpython.com/python-class-constructor/
https://stackoverflow.com/questions/79506120/python-subclass-constructor-calls-metaclass-with-args-and-kwargs
"""
class VectorStoreSingleton(type): # Inherit from "type" in order to gain access to method __call__
    __registry = {}
    def __call__(cls, *args, **kwargs):
        registry = type(cls).__registry
        if cls not in registry:
              registry[cls] = (super().__call__(*args, **kwargs), args, kwargs)
        elif registry[cls][1] != args or registry(cls)[2] != kwargs:
              raise TypeError(f"Class already initialized with different arguments!")
        return registry[cls][0]
class VectorStore(metaclass=VectorStoreSingleton):
    """
    Class constructor
    https://python.langchain.com/api_reference/_modules/langchain_core/vectorstores/in_memory.html#InMemoryVectorStore
    """
    _model: str = None
    _embeddings: VertexAIEmbeddings = None
    _vector_store: InMemoryVectorStore = None
    _docs = set()
    def __new__(cls, *args, **kwargs):
        return super().__new__(cls)
    def __init__(self, model="text-embedding-005"):
        self._model = model
        vertexai.init(project=os.environ.get("GOOGLE_CLOUD_PROJECT"), location=os.environ.get("GOOGLE_CLOUD_LOCATION"))
        self._embeddings = VertexAIEmbeddings(model=self._model) # "text-embedding-005"
        self._vector_store = InMemoryVectorStore(self._embeddings)
        print(f"VectorStore::__init__ {self._model}")

    async def LoadDocuments(self, url: str):
        # Load and chunk contents of the blog
        if url not in self._docs:
            print(f"\n=== {self.LoadDocuments.__name__} ===")
            loader = WebBaseLoader(
                web_paths=(url,),
                bs_kwargs=dict(
                    parse_only=bs4.SoupStrainer(
                        class_=("post-content", "post-title", "post-header")
                    )
                ),
            )
            docs = loader.load()
            assert len(docs) == 1
            print(f"Total characters: {len(docs[0].page_content)}")
            subdocs = self.SplitDocuments(docs)
            await self.IndexChunks(subdocs)
            self._docs.add(url)

    def SplitDocuments(self, docs):
        print(f"\n=== {self.SplitDocuments.__name__} ===")
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
        subdocs = text_splitter.split_documents(docs)
        print(f"Split blog post into {len(subdocs)} sub-documents.")
        return subdocs

    async def IndexChunks(self, subdocs):
        # Index chunks
        print(f"\n=== {self.IndexChunks.__name__} ===")
        ids = await self.aadd_documents(documents=subdocs)
        print(f"{len(ids)} documents added successfully!")

    def add_documents(
        self,
        documents: list[Document],
        ids: Optional[list[str]] = None,
        **kwargs: Any,
    ) -> list[str]:
        return self._vector_store.add_documents(documents=documents, ids=ids, **kwargs)
    
    async def aadd_documents(
        self, documents: list[Document], ids: Optional[list[str]] = None, **kwargs: Any
    ) -> list[str]:
        print(f"\n=== {self.aadd_documents.__name__} ===")
        return await self._vector_store.aadd_documents(documents=documents, ids=ids, **kwargs)
    
    def similarity_search(
        self, query: str, k: int = 4, **kwargs: Any
    ) -> list[Document]:
        return self._vector_store.similarity_search(query-query, k=k, **kwargs)
    
    async def asimilarity_search(
        self, query: str, k: int = 4, **kwargs: Any
    ) -> list[Document]:
        print(f"\n=== {self.asimilarity_search.__name__} ===")
        return await self._vector_store.asimilarity_search(query=query, k=k, **kwargs)

vector_store = VectorStore()    