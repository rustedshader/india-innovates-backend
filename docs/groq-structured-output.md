# Structured JSON Output with Groq + LangChain

How to reliably get structured JSON from Groq LLMs using LangChain's `JsonOutputParser` with Pydantic validation.

## Why Not `with_structured_output()`?

Groq's API routes structured output through **tool/function calling**. This fails when:

- The model doesn't support tool use (e.g. `openai/gpt-oss-20b`)
- The response is large — Groq truncates the JSON mid-generation, causing `tool_use_failed` errors
- The JSON contains special characters (e.g. Cypher queries with `\n`, nested quotes)

**Error you'll see:**
```
groq.BadRequestError: Error code: 400 - {'error': {'message': 'Failed to parse tool call arguments as JSON', 'type': 'invalid_request_error', 'code': 'tool_use_failed'}}
```

## The Working Approach: `JsonOutputParser`

### 1. Define Pydantic Models

```python
from pydantic import BaseModel, Field

class CypherQuery(BaseModel):
    purpose: str = Field(description="What this query retrieves")
    cypher: str = Field(description="A valid Cypher READ query")

class CypherQueryPlan(BaseModel):
    queries: list[CypherQuery] = Field(
        description="List of queries to execute"
    )
```

### 2. Create the Parser

```python
from langchain_core.output_parsers import JsonOutputParser

parser = JsonOutputParser(pydantic_object=CypherQueryPlan)
```

`parser.get_format_instructions()` auto-generates instructions like:
```
The output should be formatted as a JSON instance that conforms to the JSON schema below.
{"properties": {"queries": {"items": {"properties": ...}}}}
```

### 3. Build the System Prompt

Append the parser's format instructions to your system prompt:

```python
system_prompt = YOUR_SYSTEM_PROMPT + "\n" + parser.get_format_instructions()
```

> ⚠️ **Don't use `ChatPromptTemplate`** if your system prompt contains literal curly braces
> (e.g. Cypher's `{relation: r.type}`). The template engine will try to resolve them as
> variables and crash. Build messages manually instead.

### 4. Invoke and Parse

```python
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_groq import ChatGroq

llm = ChatGroq(model_name="openai/gpt-oss-20b", temperature=0, max_tokens=4096)

messages = [
    SystemMessage(content=system_prompt),
    HumanMessage(content=user_question),
]

response = llm.invoke(messages)
data = parser.parse(response.content)  # returns a dict

# Validate with Pydantic
plan = CypherQueryPlan(**data)
for q in plan.queries:
    print(f"{q.purpose}: {q.cypher}")
```

### 5. Add Error Handling

The LLM might occasionally produce malformed JSON. Always wrap with a fallback:

```python
try:
    response = llm.invoke(messages)
    data = parser.parse(response.content)
    plan = CypherQueryPlan(**data)
except Exception as e:
    logger.error(f"Failed to parse: {e}")
    # fallback logic here
```

## Key Tips

| Tip | Details |
|-----|---------|
| **Bump `max_tokens`** | Multi-query responses are large. Use 4096+ for the structured LLM |
| **Separate LLM instances** | Use a regular LLM (2048 tokens) for routing/synthesis, a larger one for structured output |
| **Avoid `ChatPromptTemplate`** | If your prompt has literal `{` `}` (Cypher, JSON examples), build messages manually |
| **Don't use `with_structured_output()`** | It routes through Groq's tool calling, which truncates large responses |
| **Don't use `response_format={"type": "json_object"}`** | Not reliably supported across all Groq models |

## Full Pattern

```python
class MyAgent:
    def __init__(self, model="openai/gpt-oss-20b"):
        self.llm = ChatGroq(model_name=model, temperature=0, max_tokens=2048)

        # Structured output setup
        self.parser = JsonOutputParser(pydantic_object=CypherQueryPlan)
        self.structured_llm = ChatGroq(model_name=model, temperature=0, max_tokens=4096)
        self.structured_system = BASE_PROMPT + "\n" + self.parser.get_format_instructions()

    def generate(self, question: str) -> CypherQueryPlan:
        messages = [
            SystemMessage(content=self.structured_system),
            HumanMessage(content=question),
        ]
        resp = self.structured_llm.invoke(messages)
        data = self.parser.parse(resp.content)
        return CypherQueryPlan(**data)
```
