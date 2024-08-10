# PromptView

promptview leverages the Model-View-Controller (MVC) design pattern for building applications with Large Language Models (LLMs). The framework is designed to enable reusable and composable components, intelligent data processing, and contextual state management, making it easier to develop sophisticated AI-driven applications.

## Features

- **Dynamic Views:** Create reusable, composable views that can adapt based on model outputs and user interactions, similar to React but implemented in Python.
- **State Management:** Maintain and manage conversational context or application state, enabling more personalized and context-aware AI interactions.
- **Extensible and Customizable:** Easily extend or customize the framework with new views, controllers, or models to fit your specific use case.

## Installation

To install and use this framework, you can clone the repository and install any required dependencies:

```bash
git clone https://github.com/yourusername/llm-mvc-framework.git
cd llm-mvc-framework
pip install -r requirements.txt
```


## Usage

```python
from pydantic import BaseModel
from promptview import prompt, view



class GiveQuest(BaseModel):
    """ Give a quest to the user """
    description: str
    reward: int
    
class Fight(BaseModel):
    """ Fight with the user """
    weapon: str
    demange: int

class RunAway(BaseModel):
    """ Run away from the user """
    direction: str


class UserStats(BaseModel):
    health: int = 100
    gold: int = 0
    strength: int = 10
    intelligence: int = 10


@view(
    title="User Stats",
    wrap="xml"
)
def stats_view(stats: BaseModel):
    return f"Health: {stats.health}\nGold: {stats.gold}\nStrength: {stats.strength}\nIntelligence: {stats.intelligence}"

@view(
    title="user message",    
)
def message_view(message: str):
    return message

@prompt(
    background="you need to response to every message like a pirate",
    task="your tasks is to interact with the user, respond with the appropriate tool",
    actions=[GiveQuest, Fight, RunAway]
)
def pirate_prompt(message: str, stats: UserStats):
    return (
        stats_view(stats),
        message_view(message)
    )


stats = UserStats(
    health=100,
    gold=0,
    strength=10,
    intelligence=7
)


ai_message = await pirate_prompt(message="Hello, how are you? I am looking for a quest.", stats=stats)
print("Response:", ai_message.content)
print("action:", ai_message.output)
print(type(ai_message.output))
```

this code will produce the following:
```bash
Response: Ahoy matey! Ye be lookin' fer adventure, eh? I be having just the quest for ye.

I'll be offerin' ye a quest to retrieve the lost treasure from the haunted island of Skull Cove. Beware, for the path be fraught with peril and ghosts of pirates' past!

Let me set ye up with this grand quest. Hold tight!


action: description="Retrieve the lost treasure from the haunted island of Skull Cove. Beware of the ghosts of pirates' past!" reward=50
<class '__main__.GiveQuest'>

```

after defining the prompt, views and the actions, the prompt renderer with generate a system message and a user message based on the state of the application.

#### System Message
```bash
you need to response to every message like a pirate
Task:
your tasks is to interact with the user, respond with the appropriate tool

you should use one of the following actions:
{
    "description": "Give a quest to the user ",
    "properties": {
        "description": {
            "title": "Description",
            "type": "string"
        },
        "reward": {
            "title": "Reward",
            "type": "integer"
        }
    },
    "required": [
        "description",
        "reward"
    ],
    "title": "GiveQuest",
    "type": "object"
}

{
    "description": "Fight with the user ",
    "properties": {
        "weapon": {
            "title": "Weapon",
            "type": "string"
        },
        "demange": {
            "title": "Demange",
            "type": "integer"
        }
    },
    "required": [
        "weapon",
        "demange"
    ],
    "title": "Fight",
    "type": "object"
}

{
    "description": "Run away from the user ",
    "properties": {
        "direction": {
            "title": "Direction",
            "type": "string"
        }
    },
    "required": [
        "direction"
    ],
    "title": "RunAway",
    "type": "object"
}
```

### User Message
```bash
<User Stats>
ֿ	Health: 100
ֿ	Gold: 0
ֿ	Strength: 10
ֿ	Intelligence: 7
</User Stats>
user message:
ֿ	Hello, how are you?

```


