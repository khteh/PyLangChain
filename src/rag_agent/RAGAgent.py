import os, bs4, vertexai, asyncio, logging
from dotenv import load_dotenv
from datetime import datetime
from typing import Annotated
from google.api_core.exceptions import ResourceExhausted
from langchain import hub
from langchain.chat_models import init_chat_model
from langchain_openai import OpenAIEmbeddings
from langchain_google_vertexai import VertexAIEmbeddings
from langchain_core.vectorstores import InMemoryVectorStore
from langchain_community.document_loaders import WebBaseLoader
from langchain_core.documents import Document
from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
from langchain_core.messages import SystemMessage
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langgraph.graph import StateGraph, MessagesState
from langgraph.graph.graph import (
    END,
    START,
    CompiledGraph,
    Graph,
    Send,
)
from langgraph.prebuilt import ToolNode, tools_condition, create_react_agent, InjectedStore
from langgraph.checkpoint.memory import MemorySaver
from typing_extensions import List, TypedDict
from langchain_core.prompts import ChatPromptTemplate
from langgraph.managed import IsLastStep
from langgraph.store.base import BaseStore
from langgraph.store.memory import InMemoryStore
"""
https://python.langchain.com/docs/tutorials/qa_chat_history/
https://python.langchain.com/api_reference/langchain/chat_models/langchain.chat_models.base.init_chat_model.html
https://cloud.google.com/vertex-ai/generative-ai/docs/embeddings/get-text-embeddings
https://langchain-ai.github.io/langgraph/how-tos/streaming/#values
"""
load_dotenv()
from .Tools import TOOLS
from .VectorStore import vector_store
from .State import CustomAgentState
from ..utils.image import show_graph
#agent = None
class RAGAgent():
    _llm = None
    _config = None
    _urls = [
        "https://lilianweng.github.io/posts/2023-06-23-agent/",
        "https://lilianweng.github.io/posts/2023-03-15-prompt-engineering/",
        "https://lilianweng.github.io/posts/2023-10-25-adv-attack-llm/",
    ]    
    _prompt = ChatPromptTemplate.from_messages([
                ("system", "You are a helpful AI assistant named Bob."),
                ("placeholder", "{messages}"),
                ("user", "Remember, always provide accurate answer!"),
        ])
    # Class constructor
    def __init__(self, config: RunnableConfig={}):
        """
        Class RAGAgent Constructor
        """
        #vertexai.init(project=os.environ.get("GOOGLE_CLOUD_PROJECT"), location=os.environ.get("GOOGLE_CLOUD_LOCATION"))
        self._config = config
        """
        .bind_tools() gives the agent LLM descriptions of each tool from their docstring and input arguments. 
        If the agent LLM determines that its input requires a tool call, it’ll return a JSON tool message with the name of the tool it wants to use, along with the input arguments.        
        """
        self._llm = init_chat_model("gemini-2.0-flash", model_provider="google_vertexai", streaming=True).bind_tools(TOOLS)
        # https://python.langchain.com/docs/integrations/chat/google_vertex_ai_palm/
        """
        self._llm = ChatVertexAI(
                        model="gemini-2.0-flash",
                        temperature=0,
                        max_tokens=None,
                        max_retries=6,
                        stop=None,
                        streaming=True
                    )
        """
    async def prepare_model_inputs(self, state: CustomAgentState, config: RunnableConfig, store: BaseStore):
        # Retrieve user memories and add them to the system message
        # This function is called **every time** the model is prompted. It converts the state to a prompt
        user_id = config.get("configurable", {}).get("user_id")
        namespace = ("memories", user_id)
        memories = [m.value["data"] for m in await store.asearch(namespace)]
        system_msg = f"User memories: {', '.join(memories)}"
        return [{"role": "system", "content": system_msg}] + state["messages"]

    async def CreateGraph(self, config: RunnableConfig) -> CompiledGraph:
        logging.debug(f"\n=== {self.CreateGraph.__name__} ===")
        try:
            await vector_store.LoadDocuments(self._urls)
            # https://langchain-ai.github.io/langgraph/reference/prebuilt/#langgraph.prebuilt.chat_agent_executor.create_react_agent
            return create_react_agent(self._llm, TOOLS, store=InMemoryStore(), checkpointer=MemorySaver(), state_schema=CustomAgentState, name="RAG ReAct Agent", prompt=self._prompt)
        except ResourceExhausted as e:
            logging.exception(f"google.api_core.exceptions.ResourceExhausted")

async def make_graph(config: RunnableConfig) -> CompiledGraph:
    return await RAGAgent(config).CreateGraph(config)

async def ChatAgent(agent, config, messages: List[str]):
    logging.info(f"\n=== {ChatAgent.__name__} ===")
    async for event in agent.astream(
        {"messages": [{"role": "user", "content": messages}]},
        stream_mode="values", # Use this to stream all values in the state after each step.
        config=config, # This is needed by Checkpointer
    ):
        event["messages"][-1].pretty_print()

async def main():
    # httpx library is a dependency of LangGraph and is used under the hood to communicate with the AI models.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.basicConfig(format='%(asctime)s %(levelname)-8s %(message)s', level=logging.DEBUG, datefmt='%Y-%m-%d %H:%M:%S')
    vertexai.init(project=os.environ.get("GOOGLE_CLOUD_PROJECT"), location=os.environ.get("GOOGLE_CLOUD_LOCATION"))
    config = RunnableConfig(run_name="RAG ReAct Agent", thread_id=datetime.now())
    agent = await make_graph(config)
    #show_graph(agent, "RAG ReAct Agent") # This blocks
    """
    graph = agent.get_graph().draw_mermaid_png()
    # Save the PNG data to a file
    with open("/tmp/agent_graph.png", "wb") as f:
        f.write(graph)
    img = Image.open("/tmp/agent_graph.png")
    img.show()
    """
    input_message = ["What is the standard method for Task Decomposition?", "Once you get the answer, look up common extensions of that method."]
    await ChatAgent(agent, config, input_message)

if __name__ == "__main__":
    asyncio.run(main())
