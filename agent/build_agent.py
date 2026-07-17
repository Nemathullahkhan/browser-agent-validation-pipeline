from langchain.agents import AgentExecutor, create_react_agent
from langchain_core.prompts import PromptTemplate
from langchain_ollama import OllamaLLM
from agent.tools_wrapped import fetch_tool, extract_tool, compare_tool
from agent.output_parser import CleanReActOutputParser

llm = OllamaLLM(model="llama3.1")

REACT_PROMPT = PromptTemplate.from_template(
    "You are an agent that compares product prices across two approved websites.\n\n"
    "Tools available: {tool_names}\n\n"
    "Tool descriptions:\n{tools}\n\n"
    "Format (follow exactly, one item per line, no backticks):\n"
    "Thought: <reasoning>\n"
    "Action: <tool name exactly as listed above>\n"
    "Action Input: <input>\n"
    "Observation: <tool result>\n\n"
    "STOP RULE: As soon as compare_prices returns an Observation with cheaper_site, "
    "price_a, price_b, and difference — stop calling tools. "
    "Output the raw JSON string from that Observation unchanged as the Final Answer.\n\n"
    "Begin!\n\n"
    "Question: {input}\n"
    "Thought:{agent_scratchpad}"
)

tools = [fetch_tool, extract_tool, compare_tool]
agent = create_react_agent(llm, tools, REACT_PROMPT, output_parser=CleanReActOutputParser())
agent_executor = AgentExecutor(
    agent=agent, tools=tools, verbose=True,
    handle_parsing_errors=True, max_iterations=20,
)
