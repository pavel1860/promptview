import pytest_asyncio
import pytest
from promptview.model.model import Model, Field
from promptview.model.fields import ModelField, IndexType
from promptview.model.vectors.openai_vectorizer import OpenAISmallVectorizer, OpenAILargeVectorizer
from promptview.model.resource_manager import connection_manager
import datetime as dt





