# promptview Documentation

## 1. Introduction

**promptview** is a modular, extensible framework for building, managing, and interacting with prompt-based AI systems. It is designed to help developers create, test, and deploy complex prompt workflows, manage conversational agents, and integrate with various language models and vector stores.

Key features include:
- A flexible Block system for composing and rendering prompt components.
- Agent architecture for orchestrating actions and managing conversations.
- Support for multiple model backends (OpenAI, Anthropic, custom models, etc.).
- Integration with vector databases (Qdrant, Neo4j, Postgres) for advanced retrieval and context management.
- Extensible API layer for building custom endpoints and integrations.
- Comprehensive testing and evaluation tools for prompt and agent workflows.

promptview aims to accelerate the development of robust, production-ready AI applications by providing reusable abstractions, clear architectural patterns, and developer-friendly tooling.

---

## 2. Getting Started

### Prerequisites

- Python 3.8 or higher
- [Poetry](https://python-poetry.org/) (recommended) or `pip`
- (Optional) Docker, if you want to run services in containers

### Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/your-org/promptview.git
   cd promptview
   ```

2. **Install dependencies using Poetry:**
   ```bash
   poetry install
   ```
   Or, using pip:
   ```bash
   pip install -r services/socket_manager/requirements.txt
   ```

3. **(Optional) Set up environment variables:**
   - Copy `.env.example` to `.env` and adjust as needed.

### Basic Usage Example

To run the main application:
```bash
poetry run python -m promptview.app.main
```
Or, if using pip:
```bash
python -m promptview.app.main
```

To run tests:
```bash
poetry run pytest
```
or
```bash
pytest
```

---

## 3. Architecture Overview

promptview is organized as a modular Python application, designed for extensibility and clarity. The architecture is centered around several core components:

- **Block System:** Provides composable building blocks for prompt construction, rendering, and serialization.
- **Agent System:** Manages conversational agents, orchestrates actions, and routes messages.
- **Model Layer:** Handles data models, vector storage, and integration with databases (e.g., Qdrant, Neo4j, Postgres).
- **API Layer:** Exposes RESTful endpoints for interacting with models, sessions, users, and artifacts.
- **LLM Integration:** Supports multiple language model backends (OpenAI, Anthropic, Azure, etc.) via a unified interface.
- **Testing & Evaluation:** Includes tools and frameworks for testing blocks, agents, and workflows.

### Component Relationships

- The **Agent System** uses the **Block System** to construct and process prompts.
- The **Model Layer** provides persistent storage and retrieval for artifacts, sessions, and vector data.
- The **API Layer** enables external access to core functionality and data.
- **LLM Integration** is abstracted so that agents and blocks can work with any supported model backend.

---

## 4. Core Concepts

### Block

Blocks are the fundamental building units in promptview. They represent discrete components of a prompt or workflow, such as text, variables, or logic. Blocks can be composed, rendered, and serialized, enabling flexible construction of complex prompts and workflows.

- **Purpose:** Encapsulate logic, content, or formatting for a part of a prompt.
- **Usage:** Combine multiple blocks to build dynamic prompts or conversational flows.
- **Key files:** `promptview/block/block.py`, `promptview/block/block_renderer.py`

**Example:** Creating and rendering a nested block structure.

```python
from promptview.block.block import Block

def test_wrapper_block():
    with Block(tags=["system"]) as b:
        b /= "you are a helpful assistant"
        with b("Task", style="md", tags=["task"]):
            b /= "this is task you need to complete"

    assert b.render() == "you are a helpful assistant\n# Task\nthis is task you need to complete"
```

### Advanced Example: The block Decorator

The `block` decorator allows you to encapsulate block-building logic in reusable functions, and enables context management for nested blocks. This is especially useful for building complex, structured prompts or code blocks.

```python
from promptview.block.block import block, Block

@block()
def create_table_block(blk: Block, name: str, *fields):
    with blk(f"CREATE TABLE IF NOT EXISTS {name}", style="func-col") as blk:
        for field in fields:
            blk /= f'"{field.name}"', field.sql_type
            if field.is_primary_key:
                blk += "PRIMARY KEY"
            else:
                blk += "NULL" if field.is_optional else "NOT NULL"

# Usage:
with create_table_block("users", field1, field2) as table_blk:
    print(table_blk.render())
```

This pattern ensures that nested blocks and content are appended to the correct parent, making your block logic modular and maintainable.

### Agent

Agents are responsible for managing conversations, orchestrating actions, and interacting with language models. They use blocks to construct prompts and handle the flow of information between users, models, and the system.

- **Purpose:** Manage the lifecycle of a conversation or task, including prompt generation and response handling.
- **Usage:** Implement custom agents to define specific behaviors or workflows.
- **Key files:** `promptview/agent/action_agent.py`, `promptview/agent/function_agent.py`

**Example:** Defining an ActionAgent with prompt and reducer logic.

```python
from promptview.agent.action_agent import ActionAgent
from promptview import ChatPrompt

pirate_agent = ActionAgent(
    name="pirate_agent", 
    prompt_cls=ChatPrompt, 
    add_input_history=True,
    iterations=2
)

@pirate_agent.prompt(
    model="claude-3-5-sonnet-20240620",
    background="you are a pirate by the name of Jack Sparrow.",
    rules=[
        "you can answer with a regular message or use an action.",
        "if you provide a message, it should be without formatting. you should answer as if you are speaking.",
    ],
    actions=[AttackAction, GiveQuestAction, MoveAction, ChangeReputationAction],
)
def pirate_prompt(context, message, pirate_stats, user_stats):
    if message.role == 'tool':
        return [*context.history.get(10), message]
    return [*context.history.get(10), pirate_view(pirate_stats, user_stats), message]
```

### Model

The model layer provides abstractions for data storage, retrieval, and manipulation. It supports integration with various backends, such as vector databases (Qdrant, Neo4j, Postgres), and manages artifacts, sessions, and other persistent data.

- **Purpose:** Store and retrieve data required for prompt workflows and agent operations.
- **Usage:** Define and interact with models for artifacts, sessions, users, etc.
- **Key files:** `promptview/model/`, `promptview/model/neo4j/`, `promptview/model/postgres/`, `promptview/model/qdrant/`

**Example:** Defining and using a model with relations.

```python
from promptview.model import Model, ModelField, KeyField, RelationField, Relation

class User(Model):
    id: int = KeyField(primary_key=True)
    name: str = ModelField()
    age: int = ModelField()
    posts: Relation["Post"] = RelationField(foreign_key="user_id")

class Post(Model):
    id: int = KeyField(primary_key=True)
    title: str = ModelField()
    content: str = ModelField()
    user_id: int = ModelField(foreign_key=True)
```

---

## 5. Component Deep Dives
For each major component, provide:
- **Purpose**
- **How it works**
- **Key classes/functions**
- **Example usage**

### 5.1 Block System
- Description and usage
- Key files/classes

### 5.2 Agent System
- Description and usage
- Key files/classes

### 5.3 Model Layer
- Description and usage
- Key files/classes

### 5.4 API Layer
- Description and usage
- Key files/classes

### 5.5 Other Components
- Add more as needed (e.g., Vectorizers, Auth, etc.)

---

## 6. Testing
- How to run tests
- Testing philosophy and structure

---

## 7. Extending and Contributing
- How to add new features or components
- Coding standards and guidelines
- Contribution process

---

## 8. FAQ / Troubleshooting
- Common issues and solutions

---

## 9. References & Further Reading
- Links to related documentation, papers, or resources
